from pathlib import Path
from fractions import Fraction
import shutil
import sys

import netCDF4
import numpy as np
import pytest
from scipy.linalg import null_space

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr102_native_wind_candidate import (  # noqa: E402
    _geometry,
    _roughness_matrix,
    _storage_margin,
    _upper_positive_product,
    _stored_flux_arithmetic_bound,
    _artifact,
    _verify_pr99_receipt,
    propose,
    verify_only_wind_changed,
)
import pr102_native_wind_candidate as producer  # noqa: E402
import pr99_native_projection as projection  # noqa: E402


def geometry_file(path: Path, interfaces=(0.0, 2.0, 6.0), *, map_value=1.0):
    gravity = 9.81000041961669922
    ny, nx, nz = 3, 3, len(interfaces) - 1
    with netCDF4.Dataset(path, "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("bottom_top_stag", nz + 1)
        ds.createDimension("bottom_top", nz)
        ds.createDimension("south_north", ny)
        ds.createDimension("west_east", nx)
        ds.createDimension("west_east_stag", nx + 1)
        ds.createDimension("south_north_stag", ny + 1)
        ds.DX, ds.DY = 10.0, 20.0
        ph = np.broadcast_to(np.asarray(interfaces)[:, None, None] * gravity,
                             (nz + 1, ny, nx)).copy().astype(np.float32)
        for name in ("PH", "PHB"):
            var = ds.createVariable(name, "f4", ("Time", "bottom_top_stag", "south_north", "west_east"))
            var.units = "m2 s-2"
            var[0] = ph if name == "PH" else 0.0
        u = ds.createVariable("U", "f4", ("Time", "bottom_top", "south_north", "west_east_stag"))
        v = ds.createVariable("V", "f4", ("Time", "bottom_top", "south_north_stag", "west_east"))
        u.units = v.units = "m s-1"
        u[0] = np.zeros((nz, ny, nx + 1), dtype=np.float32)
        v[0] = np.zeros((nz, ny + 1, nx), dtype=np.float32)
        for name, dims, shape in (
            ("MAPFAC_UX", ("Time", "south_north", "west_east_stag"), (ny, nx + 1)),
            ("MAPFAC_UY", ("Time", "south_north", "west_east_stag"), (ny, nx + 1)),
            ("MAPFAC_VX", ("Time", "south_north_stag", "west_east"), (ny + 1, nx)),
            ("MAPFAC_VY", ("Time", "south_north_stag", "west_east"), (ny + 1, nx)),
        ):
            var = ds.createVariable(name, "f4", dims)
            var.units = ""
            var[0] = np.full(shape, map_value, dtype=np.float32)
    return gravity


def test_geometry_builds_metric_normalized_boundary_and_vertical_edges(tmp_path: Path):
    source = tmp_path / "geometry.nc"
    gravity = geometry_file(source)
    free_u = np.zeros((2, 3, 4), dtype=bool)
    free_v = np.zeros((2, 4, 3), dtype=bool)
    free_u[:, 1, 1] = True
    with netCDF4.Dataset(source) as ds:
        geo = _geometry(ds, free_u, free_v, gravity)

    matrix, _, _, _ = _roughness_matrix(free_u, free_v, geo)
    row_sizes = np.diff(matrix.indptr)
    assert matrix.shape == (9, 2)
    assert np.count_nonzero(row_sizes == 1) == 8  # all horizontal fixed-zero neighbors
    vertical = np.flatnonzero(row_sizes == 2)
    assert vertical.size == 1
    # Mean dual volume 600 m3 divided by 3 m vertical spacing, then sqrt.
    np.testing.assert_allclose(np.linalg.norm(matrix.data[matrix.indptr[vertical[0]]:
                                                              matrix.indptr[vertical[0]+1]]),
                               np.sqrt(2.0 * 600.0 / 9.0), rtol=2e-6)


def test_geometry_rejects_nonmonotone_height_and_bad_map_factors(tmp_path: Path):
    for interfaces, map_value, match in (
        ((0.0, 2.0, 1.0), 1.0, "strictly increasing"),
        ((0.0, 2.0, 6.0), 0.0, "positive finite metrics"),
    ):
        source = tmp_path / f"bad-{len(list(tmp_path.iterdir()))}.nc"
        gravity = geometry_file(source, interfaces, map_value=map_value)
        free_u = np.zeros((2, 3, 4), dtype=bool)
        free_v = np.zeros((2, 4, 3), dtype=bool)
        free_u[:, 1, 1] = True
        with netCDF4.Dataset(source) as ds, pytest.raises(ValueError, match=match):
            _geometry(ds, free_u, free_v, gravity)


def make_wind_pair(tmp_path: Path, *, candidate_y: str = "y", candidate_y_size: int = 2,
                   candidate_time_unlimited: bool = False,
                   candidate_title: str = "source", candidate_t_units: str = "K",
                   candidate_fill_value=None, wind_fill_value=None):
    parent = tmp_path / "parent.nc"
    candidate = tmp_path / "candidate.nc"
    def create(path, *, yname="y", ysize=2, unlimited=False, title="source",
               t_units="K", fill_value=None, wind_fill=None, change_wind=False):
        with netCDF4.Dataset(path, "w") as ds:
            ds.createDimension("Time", None if unlimited else 1)
            for name, size in (("z", 1), (yname, ysize), ("x", 2), ("xu", 3), ("yv", 3)):
                ds.createDimension(name, size)
            ds.title = title
            for name, dims, shape in (
                ("U", ("Time", "z", yname, "xu"), (1, 1, ysize, 3)),
                ("V", ("Time", "z", "yv", "x"), (1, 1, 3, 2)),
                ("T", ("Time", "z", yname, "x"), (1, 1, ysize, 2)),
            ):
                value_fill = fill_value if name == "T" else wind_fill
                kwargs = {"fill_value": value_fill} if value_fill is not None else {}
                var = ds.createVariable(name, "f4", dims, **kwargs)
                var.units = "m s-1" if name in {"U", "V"} else t_units
                values = np.ones(shape, dtype=np.float32)
                if name == "U" and change_wind:
                    values[..., 1] += np.float32(0.25)
                var[:] = values
    create(parent, wind_fill=wind_fill_value)
    create(candidate, yname=candidate_y, ysize=candidate_y_size,
           unlimited=candidate_time_unlimited, title=candidate_title,
           t_units=candidate_t_units, fill_value=candidate_fill_value,
           wind_fill=wind_fill_value, change_wind=True)
    return parent, candidate


def test_wind_only_verifier_checks_exact_arrays_and_metadata(tmp_path: Path):
    parent, candidate = make_wind_pair(tmp_path)
    verify_only_wind_changed(candidate, parent)
    with netCDF4.Dataset(candidate, "r+") as ds:
        ds["T"][0, 0, 0, 0] = 2.0
    with pytest.raises(ValueError, match="non-wind variable T"):
        verify_only_wind_changed(candidate, parent)


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"candidate_title": "changed"}, "global attributes"),
        ({"candidate_t_units": "C"}, "variable metadata.*T"),
        ({"candidate_fill_value": -999.0}, "variable metadata.*T"),
        ({"candidate_y": "yy"}, "dimension"),
        ({"candidate_y_size": 3}, "dimension"),
        ({"candidate_time_unlimited": True}, "dimension"),
    ],
)
def test_wind_only_verifier_rejects_structure_and_attribute_differences(tmp_path, kwargs, match):
    parent, candidate = make_wind_pair(tmp_path, **kwargs)
    with pytest.raises(ValueError, match=match):
        verify_only_wind_changed(candidate, parent)


def test_wind_only_verifier_rejects_nonfinite_wind(tmp_path):
    parent, candidate = make_wind_pair(tmp_path)
    with netCDF4.Dataset(candidate, "r+") as ds:
        values = ds["U"][:]
        values[0, 0, 0, 0] = np.nan
        ds["U"][:] = values
    with pytest.raises(ValueError, match="nonfinite history values"):
        verify_only_wind_changed(candidate, parent)


def test_wind_only_verifier_rejects_declared_wind_fill_value(tmp_path):
    parent, candidate = make_wind_pair(tmp_path, wind_fill_value=-999.0)
    with netCDF4.Dataset(candidate, "r+") as ds:
        ds["U"][0, 0, 0, 0] = -999.0
    with pytest.raises(ValueError, match="_FillValue sentinel"):
        verify_only_wind_changed(candidate, parent)


def test_storage_margin_is_global_euclidean_half_ulp_bound():
    hydro = np.array([0.0, 100.0, -50.0], dtype=np.float64)
    projected = np.array([1.0, -2.0, 3.0], dtype=np.float64)
    margin = _storage_margin(hydro, projected, 0.5)
    assert np.isfinite(margin) and margin > 0
    assert margin >= 0.5 * float(np.spacing(np.float32(100.0)))


def _exact_fraction_dot(coefficients, values):
    return sum((Fraction.from_float(float(a)) * Fraction.from_float(float(v))
                for a, v in zip(coefficients, values)), Fraction())


def test_positive_product_upper_bound_covers_round_down_and_subnormal_products():
    operands = (1.0 + 2.0**-52, 1.0 + 2.0**-52)
    exact = Fraction.from_float(operands[0]) * Fraction.from_float(operands[1])
    bound = _upper_positive_product(*operands)
    assert exact <= Fraction.from_float(bound)
    assert bound > float(exact)

    tiny = np.nextafter(0.0, 1.0)
    exact_subnormal = Fraction.from_float(float(tiny)) * Fraction(1, 2)
    subnormal_bound = _upper_positive_product(float(tiny), 0.5)
    assert exact_subnormal <= Fraction.from_float(subnormal_bound)
    assert subnormal_bound == tiny


def test_stored_flux_roundoff_bound_covers_fraction_exact_cancellation_cases():
    matrix = np.array([[1.0, 1.0, -1.0, -1.0],
                       [1.0, -1.0, 1.0, -1.0],
                       [-1.0, 1.0, 1.0, -1.0]])
    continuous = np.array([1.0e16, 1.0, 1.0e16, 1.0], dtype=np.float64)
    stored = continuous.copy()
    stored[1] = np.nextafter(stored[1], np.inf)
    stored[3] = np.nextafter(stored[3], -np.inf)
    report = _stored_flux_arithmetic_bound(matrix, continuous, stored)

    for row in range(matrix.shape[0]):
        exact = abs(_exact_fraction_dot(matrix[row], stored))
        assert exact <= Fraction.from_float(float(report["limits"][row]))
        assert abs(report["observed_residual"][row]) <= report["limits"][row]
        assert report["rows"][row]["nnz"] == 4
        assert report["rows"][row]["terms"]["observed_abs_error_dot"] >= 0


def test_stored_flux_roundoff_bound_covers_subnormal_underflow_and_rejects_wide_rows():
    tiny = np.nextafter(0.0, 1.0)
    matrix = np.array([[1.0, -1.0, 1.0, -1.0]])
    continuous = np.array([tiny, 0.0, tiny, 0.0])
    stored = np.array([0.0, tiny, 0.0, tiny])
    report = _stored_flux_arithmetic_bound(matrix, continuous, stored)
    exact = abs(_exact_fraction_dot(matrix[0], stored))
    assert exact <= Fraction.from_float(float(report["limits"][0]))
    assert report["smallest_subnormal"] == tiny

    with pytest.raises(ValueError, match="one to four face terms"):
        _stored_flux_arithmetic_bound(np.ones((1, 5)), np.ones(5), np.zeros(5))


def test_synthetic_candidate_is_receipt_bound_and_changes_only_winds(tmp_path: Path, monkeypatch):
    nz, ny, nx = 2, 4, 4
    hydro, coupled, original_p = (tmp_path / name for name in
                                  ("hydro.nc", "coupled.nc", "original_p.nc"))
    boundary, pr99_receipt, output = (tmp_path / name for name in
                                      ("wrfbdy", "pr99.json", "structured.nc"))
    boundary.write_bytes(b"synthetic boundary")
    u_shape, v_shape = (1, nz, ny, nx + 1), (1, nz, ny + 1, nx)
    columns = np.zeros((ny, nx), dtype=bool)
    columns[1:-1, 1:-1] = True
    u_mask, v_mask = projection.control_faces(columns)
    support = {"original_613_native_support": np.ones((nz, ny - 2, nx - 2), dtype=bool),
               "fixed_5_cell_chebyshev_buffer": np.ones((nz, ny - 2, nx - 2), dtype=bool)}
    monkeypatch.setattr(producer.cloud, "make_masks", lambda *_: support)
    monkeypatch.setattr(producer, "EXPECTED_NATIVE_LEVELS", nz)
    monkeypatch.setattr(producer, "EXPECTED_SUPPORT_LEVELS", nz * (ny - 2) * (nx - 2))
    monkeypatch.setattr(producer, "EXPECTED_SUPPORT_COLUMNS", (ny - 2) * (nx - 2))
    monkeypatch.setattr(producer, "EXPECTED_BUFFER_COLUMNS", int(columns.sum()))
    monkeypatch.setattr(producer, "EXPECTED_FREE_FACES_PER_LAYER", 4)
    monkeypatch.setattr(producer.history, "_constants",
                        lambda path: (9.81000041961669922,
                                      {"path": str(path), "sha256": "a" * 64,
                                       "g_m_s2": 9.81000041961669922}))
    constants = tmp_path / "constants.json"
    constants.write_text("{}")

    def create(path: Path):
        with netCDF4.Dataset(path, "w") as ds:
            for name, size in (("Time", 1), ("bottom_top", nz), ("bottom_top_stag", nz + 1),
                               ("south_north", ny), ("west_east", nx),
                               ("west_east_stag", nx + 1), ("south_north_stag", ny + 1)):
                ds.createDimension(name, size)
            ds.title = "manufactured"
            ds.DX, ds.DY = 10.0, 20.0
            def var(name, dims, value):
                target = ds.createVariable(name, "f4", dims)
                target.units = "1"
                target[:] = value
            var("U", ("Time", "bottom_top", "south_north", "west_east_stag"), np.zeros(u_shape, dtype=np.float32))
            var("V", ("Time", "bottom_top", "south_north_stag", "west_east"), np.zeros(v_shape, dtype=np.float32))
            var("PH", ("Time", "bottom_top_stag", "south_north", "west_east"),
                np.broadcast_to(np.array([0, 20, 50], dtype=np.float32)[None, :, None, None],
                                (1, nz + 1, ny, nx)))
            var("PHB", ("Time", "bottom_top_stag", "south_north", "west_east"), np.zeros((1, nz + 1, ny, nx), dtype=np.float32))
            var("MU", ("Time", "south_north", "west_east"), np.ones((1, ny, nx), dtype=np.float32))
            var("MUB", ("Time", "south_north", "west_east"), np.ones((1, ny, nx), dtype=np.float32))
            var("C1H", ("Time", "bottom_top"), np.ones((1, nz), dtype=np.float32))
            var("C2H", ("Time", "bottom_top"), np.ones((1, nz), dtype=np.float32))
            var("DNW", ("Time", "bottom_top"), -np.ones((1, nz), dtype=np.float32))
            var("RDX", ("Time",), np.ones((1,), dtype=np.float32))
            var("RDY", ("Time",), np.ones((1,), dtype=np.float32))
            var("MAPFAC_MX", ("Time", "south_north", "west_east"), np.ones((1, ny, nx), dtype=np.float32))
            for name, dims, shape in (
                    ("MAPFAC_UX", ("Time", "south_north", "west_east_stag"), (1, ny, nx + 1)),
                    ("MAPFAC_UY", ("Time", "south_north", "west_east_stag"), (1, ny, nx + 1)),
                    ("MAPFAC_VX", ("Time", "south_north_stag", "west_east"), (1, ny + 1, nx)),
                    ("MAPFAC_VY", ("Time", "south_north_stag", "west_east"), (1, ny + 1, nx)),
            ):
                target = ds.createVariable(name, "f4", dims)
                target.units = ""
                target[:] = np.ones(shape, dtype=np.float32)
            ds["PH"].units = ds["PHB"].units = "m2 s-2"
            ds["U"].units = ds["V"].units = "m s-1"
            var("T", ("Time", "bottom_top", "south_north", "west_east"), np.ones((1, nz, ny, nx), dtype=np.float32))

    create(hydro)
    create(coupled)
    shutil.copy2(hydro, original_p)
    with netCDF4.Dataset(hydro) as h, netCDF4.Dataset(coupled, "r+") as c:
        h.set_auto_mask(False); c.set_auto_mask(False)
        u0, v0 = h["U"][0].astype(np.float64), h["V"][0].astype(np.float64)
        coupled_u, coupled_v = u0.astype(np.float32).copy(), v0.astype(np.float32).copy()
        raw_layers, projected_layers = [], []
        for k in range(nz):
            matrix = projection.divergence_matrix(columns,
                *projection.face_coefficients(h, k))
            circulation = null_space(matrix.toarray())[:, 0] * 10.0
            raw = circulation + matrix.T @ np.arange(1, matrix.shape[0] + 1) * 0.001
            projected, _ = projection.project_increment(matrix, raw)
            raw_layers.append(raw); projected_layers.append(projected)
            split = int(u_mask.sum())
            coupled_u[k][u_mask] = raw[:split].astype(np.float32)
            coupled_v[k][v_mask] = raw[split:].astype(np.float32)
        c["U"][0], c["V"][0] = coupled_u, coupled_v
        with netCDF4.Dataset(original_p, "r+") as p:
            p_u, p_v = u0.astype(np.float32).copy(), v0.astype(np.float32).copy()
            for k, projected in enumerate(projected_layers):
                split = int(u_mask.sum())
                p_u[k][u_mask] = projected[:split].astype(np.float32)
                p_v[k][v_mask] = projected[split:].astype(np.float32)
            p["U"][0], p["V"][0] = p_u, p_v

    # Receipt source pins are deliberately created only after every fixture byte is final.
    composition = producer.COMPOSITION
    original_composition = tmp_path / "old-source-composition.json"
    shutil.copy2(composition, original_composition)
    pr99_receipt.write_text(__import__("json").dumps({
        "schema": "pr99_native_uv_projection_proposal_v1",
        "status": "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_TENDENCY_VALIDATION",
        "role": "COUPLED", "reference": _artifact(hydro), "parent": _artifact(coupled),
        "candidate": _artifact(original_p), "boundary": _artifact(boundary),
        "generator": _artifact(Path(projection.__file__)), "composition": _artifact(original_composition),
        "composition_sha256": producer.sha256(original_composition), "fixed_columns": int(columns.sum()),
        "free_faces_per_layer": int(u_mask.sum() + v_mask.sum()),
        "layers": [{} for _ in range(nz)]}, sort_keys=True))

    result = propose(hydro, coupled, original_p, pr99_receipt, boundary, constants, output)
    assert result["status"] == "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_SOURCE_CAPTURE"
    assert set(key for key in result if key in {"candidate", "original_p", "reference_hydro",
                                                 "reference_coupled", "boundary", "generator",
                                                 "policy", "composition"}) == {
        "candidate", "original_p", "reference_hydro", "reference_coupled", "boundary",
        "generator", "policy", "composition"}
    assert result["policy_metrics"]["stored_distance_to_projection"] <= result["policy_metrics"]["pr99_adjustment_delta"]
    assert result["policy_metrics"]["normalized_kkt_residual"] < 1e-8
    assert result["pr99_composition_source"]["path"] == str(original_composition.resolve())
    assert result["current_composition_mirror"]["sha256"] == producer.sha256(composition)
    verify_only_wind_changed(output, original_p)


def test_pr99_composition_relocation_requires_both_source_and_mirror_hashes(tmp_path: Path, monkeypatch):
    hydro, coupled, original_p, boundary = (tmp_path / name for name in
                                            ("hydro", "coupled", "projected", "boundary"))
    for path in (hydro, coupled, original_p, boundary):
        path.write_bytes(path.name.encode())
    original_composition = tmp_path / "source-composition.json"
    shutil.copy2(producer.COMPOSITION, original_composition)
    receipt = {
        "schema": "pr99_native_uv_projection_proposal_v1",
        "status": "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_TENDENCY_VALIDATION",
        "role": "COUPLED", "reference": _artifact(hydro), "parent": _artifact(coupled),
        "candidate": _artifact(original_p), "boundary": _artifact(boundary),
        "composition": _artifact(original_composition),
        "composition_sha256": producer.sha256(original_composition),
        "generator": _artifact(Path(projection.__file__)),
    }
    receipt_path = tmp_path / "pr99.json"
    receipt_path.write_text(__import__("json").dumps(receipt))

    verified = _verify_pr99_receipt(receipt_path, hydro, coupled, original_p, boundary)
    assert verified["_composition_source_binding"]["path"] == str(original_composition.resolve())
    assert verified["_composition_source_binding"]["sha256"] == producer.sha256(producer.COMPOSITION)

    changed_mirror = tmp_path / "changed-current-mirror.json"
    shutil.copy2(producer.COMPOSITION, changed_mirror)
    changed_mirror.write_bytes(changed_mirror.read_bytes() + b"changed")
    monkeypatch.setattr(producer, "COMPOSITION", changed_mirror)
    with pytest.raises(ValueError, match="current PR102 composition mirror"):
        _verify_pr99_receipt(receipt_path, hydro, coupled, original_p, boundary)

    monkeypatch.setattr(producer, "COMPOSITION", producer.ROOT /
                        "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json")
    original_composition.write_bytes(original_composition.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="original PR99 composition path/hash"):
        _verify_pr99_receipt(receipt_path, hydro, coupled, original_p, boundary)
