"""Focused invariants for the PR99 native U/V projection proposal."""
from __future__ import annotations

import sys
from pathlib import Path

import netCDF4
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr99_native_projection import (  # noqa: E402
    control_faces,
    divergence_matrix,
    face_coefficients,
    project_increment,
    propose,
)


def test_internal_face_incidence_has_closed_boundary_flux() -> None:
    columns = np.ones((4, 5), dtype=bool)
    u_mask, v_mask = control_faces(columns)
    matrix = divergence_matrix(columns, np.ones(u_mask.shape), np.ones(v_mask.shape))

    assert not u_mask[:, (0, -1)].any()
    assert not v_mask[(0, -1), :].any()
    np.testing.assert_array_equal(np.asarray(matrix.sum(axis=0)).ravel(), 0.0)


def test_projection_preserves_a_nonzero_reference_divergence() -> None:
    columns = np.ones((4, 5), dtype=bool)
    u_mask, v_mask = control_faces(columns)
    u_coeff = np.linspace(0.5, 2.0, u_mask.size).reshape(u_mask.shape)
    v_coeff = np.linspace(0.75, 1.5, v_mask.size).reshape(v_mask.shape)
    matrix = divergence_matrix(columns, u_coeff, v_coeff)
    rng = np.random.default_rng(907)
    reference = rng.normal(size=matrix.shape[1])
    increment = rng.normal(size=matrix.shape[1])

    projected, report = project_increment(matrix, increment)
    final = reference + projected
    reference_divergence = matrix @ reference

    assert np.linalg.norm(reference_divergence) > 0.1
    assert np.linalg.norm(matrix @ (final - reference)) < 1.0e-9
    np.testing.assert_allclose(matrix @ final, reference_divergence, rtol=0.0, atol=1.0e-9)
    assert report["initial_divergence_L2"] > report["continuous_divergence_L2"]


@pytest.mark.parametrize(
    "u_coeff,v_coeff",
    [
        (np.ones((3, 4)), np.ones((4, 4))),
        (np.zeros((3, 5)), np.ones((4, 4))),
        (np.full((3, 5), np.nan), np.ones((4, 4))),
    ],
)
def test_invalid_face_geometry_is_rejected(u_coeff: np.ndarray, v_coeff: np.ndarray) -> None:
    with pytest.raises(ValueError, match="invalid face carrier or map geometry"):
        divergence_matrix(np.ones((3, 4), dtype=bool), u_coeff, v_coeff)


def test_invalid_reference_and_increment_fail_without_output(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty or invalid fixed control columns"):
        control_faces(np.zeros((3, 4), dtype=bool))

    columns = np.ones((3, 4), dtype=bool)
    u_mask, v_mask = control_faces(columns)
    matrix = divergence_matrix(columns, np.ones(u_mask.shape), np.ones(v_mask.shape))
    with pytest.raises(ValueError, match="invalid additional native wind"):
        project_increment(matrix, np.full(matrix.shape[1], np.nan))

    hydro = tmp_path / "hydro.nc"
    coupled = tmp_path / "coupled.nc"
    output = tmp_path / "proposal.nc"
    for path, name in ((hydro, "reference_only"), (coupled, "treatment_only")):
        with netCDF4.Dataset(path, "w") as dataset:
            dataset.createDimension("x", 1)
            dataset.createVariable(name, "f4", ("x",))[:] = [1.0]

    with pytest.raises(ValueError, match="variable sets differ"):
        propose(hydro, coupled, output)
    assert not output.exists()


def test_existing_proposal_receipt_blocks_before_opening_inputs(tmp_path: Path) -> None:
    output = tmp_path / "proposal.nc"
    sidecar = output.with_suffix(".proposal.json")
    sidecar.write_text("preserve this receipt\n")

    with pytest.raises(FileExistsError):
        propose(tmp_path / "missing_hydro.nc", tmp_path / "missing_coupled.nc", output)

    assert not output.exists()
    assert sidecar.read_text() == "preserve this receipt\n"


def test_face_mass_weights_follow_calc_ww_cp_source_order(tmp_path: Path) -> None:
    path = tmp_path / "geometry.nc"
    with netCDF4.Dataset(path, "w") as dataset:
        for name, size in (("Time", 1), ("y", 2), ("x", 3),
                           ("xu", 4), ("yv", 3), ("z", 1)):
            dataset.createDimension(name, size)
        def field(name: str, dimensions: tuple[str, ...], values: np.ndarray) -> None:
            dataset.createVariable(name, "f4", dimensions)[:] = values

        mu = np.array([[1.0, 3.0, 5.0], [2.0, 4.0, 6.0]], dtype=np.float32)
        mub = np.array([[0.5, 1.5, 2.5], [1.0, 2.0, 3.0]], dtype=np.float32)
        field("MU", ("Time", "y", "x"), mu[None])
        field("MUB", ("Time", "y", "x"), mub[None])
        field("C1H", ("Time", "z"), np.array([[0.75]], dtype=np.float32))
        field("C2H", ("Time", "z"), np.array([[2.0]], dtype=np.float32))
        field("MAPFAC_MX", ("Time", "y", "x"), np.ones((1, 2, 3), dtype=np.float32))
        field("DNW", ("Time", "z"), np.array([[-1.0]], dtype=np.float32))
        map_u = np.full((2, 4), 2.0, dtype=np.float32)
        map_v = np.full((3, 3), 4.0, dtype=np.float32)
        field("MAPFAC_UY", ("Time", "y", "xu"), map_u[None])
        field("MAPFAC_VX", ("Time", "yv", "x"), map_v[None])
        field("RDX", ("Time",), np.array([3.0], dtype=np.float32))
        field("RDY", ("Time",), np.array([5.0], dtype=np.float32))

        actual_u, actual_v = face_coefficients(dataset, 0)

    muu = np.empty((2, 4), dtype=np.float32)
    muu[:, 1:-1] = np.float32(0.5) * (
        ((mu[:, 1:] + mub[:, 1:]) + mu[:, :-1]) + mub[:, :-1])
    muu[:, 0], muu[:, -1] = muu[:, 1], muu[:, -2]
    muv = np.empty((3, 3), dtype=np.float32)
    muv[1:-1] = np.float32(0.5) * (
        ((mu[1:] + mub[1:]) + mu[:-1]) + mub[:-1])
    muv[0], muv[-1] = muv[1], muv[-2]
    expected_u = (np.float32(0.75) * muu + np.float32(2.0)).astype(np.float64) / map_u * 3.0
    expected_v = ((np.float32(0.75) * muv + np.float32(2.0)).astype(np.float64)
                  * (np.float32(1.0) / map_v) * 5.0)
    np.testing.assert_array_equal(actual_u, expected_u)
    np.testing.assert_array_equal(actual_v, expected_v)
