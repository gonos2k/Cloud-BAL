#!/usr/bin/env python3
"""Hand-calculated continuity checks for terrain-clipped pressure faces."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pressure_transition_reference import reconstruct_prebalance_winds  # noqa: E402
from validate_shadow_diagnostics import continuity_increment, continuity_state  # noqa: E402


def partial_bottom_geometry() -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """Return a three-column face with one cross-level pressure overlap."""
    # Axes are (z, y, x).  The right column has a zero-thickness bottom
    # level, while its level-1 cell overlaps both middle-column levels.  The
    # middle column is interior so a compatible increment can vanish at the
    # physical x boundaries while still exercising both lateral faces.
    pressure_interface = np.array(
        [
            [[100000.0, 100000.0, 94000.0]],
            [[92500.0, 92500.0, 94000.0]],
            [[87500.0, 87500.0, 87500.0]],
        ]
    )
    cell_dp = pressure_interface[:-1] - pressure_interface[1:]
    above_ground = cell_dp > 0.0
    active = above_ground.copy()
    pressure = np.array([95000.0, 90000.0])
    omega_top_boundary = np.zeros((1, 3))
    omega_bottom_boundary = np.zeros((1, 3))
    return (
        pressure,
        pressure_interface,
        cell_dp,
        above_ground,
        active,
        omega_top_boundary,
        omega_bottom_boundary,
    )


def test_partial_bottom_pressure_face_state() -> None:
    (
        pressure,
        pressure_interface,
        cell_dp,
        above_ground,
        active,
        omega_top_boundary,
        omega_bottom_boundary,
    ) = partial_bottom_geometry()
    u = np.array([[[0.0, 2.0, 0.0]], [[0.0, 4.0, 1.0]]])
    v = np.zeros_like(u)
    omega = np.zeros_like(u)

    assert np.any(cell_dp[:, :, 1] != cell_dp[:, :, 2])
    assert not above_ground[0, 0, 2], "the partial-bottom cell must be inactive"
    assert active[0, 0, 1] and active[1, 0, 2], "support must reach both face levels"

    actual = continuity_state(
        u,
        v,
        omega,
        omega_top_boundary,
        omega_bottom_boundary,
        active,
        above_ground,
        1.0,
        1.0,
        pressure,
        pressure_interface,
        cell_dp,
    )

    # The right shared face has two pressure-overlap segments.  The 1500 Pa
    # cross-level segment carries 1500*(2+1)/2, and the 5000 Pa same-level
    # segment carries 5000*(4+1)/2.  The full-level left face carries 7500
    # and 5000 Pa segments from the zero-velocity west column.  The only
    # nonzero domain-boundary flux is +1 on the east.  These values are
    # intentionally independent of the implementation helper.
    expected = np.array(
        [[[1.0, -0.7, 0.0]], [[2.0, 0.5, -33.0 / 26.0]]],
        dtype=np.float64,
    )
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1.0e-12)
    assert actual[0, 0, 2] == 0.0, "inactive support boundary must remain zero"

    # Internal pressure-face fluxes cancel in the pressure-mass-weighted sum;
    # only the west/east boundary fluxes remain.
    np.testing.assert_allclose(
        np.sum(actual * cell_dp), 6500.0, rtol=0.0, atol=1.0e-10
    )


def test_partial_bottom_pressure_face_increment_and_identity() -> None:
    (
        pressure,
        pressure_interface,
        cell_dp,
        above_ground,
        active,
        omega_top_boundary,
        omega_bottom_boundary,
    ) = partial_bottom_geometry()
    u = np.array([[[0.0, 2.0, 0.0]], [[0.0, 4.0, 1.0]]])
    v = np.zeros_like(u)
    omega = np.zeros_like(u)
    # The upper middle cell borders an inactive same-level terrain cell;
    # its normal increment is fixed too, not just the physical x boundaries.
    du = np.array([[[0.0, 0.0, 0.0]], [[0.0, -1.0, 0.0]]])
    dv = np.zeros_like(du)
    domega = np.zeros_like(du)

    increment = continuity_increment(
        du,
        dv,
        domega,
        active,
        1.0,
        1.0,
        pressure,
        pressure_interface,
        cell_dp,
    )

    # Both 5000 Pa lower same-level faces carry 5000*(-1)/2. The
    # upper and cross-level increments vanish because their DOFs are fixed.
    # The east partial cell has thickness 6500 Pa, giving 2500/6500.
    expected_increment = np.array(
        [[[0.0, 0.0, 0.0]],
         [[-1.0 / 2.0, 0.0, 5.0 / 13.0]]],
        dtype=np.float64,
    )
    np.testing.assert_allclose(
        increment, expected_increment, rtol=0.0, atol=1.0e-12
    )
    np.testing.assert_allclose(
        np.sum(increment * cell_dp), 0.0, rtol=0.0, atol=1.0e-10
    )

    # With a support-compatible delta (including fixed normal DOFs),
    # the full-state residual must be affine in the state increment.
    candidate = continuity_state(
        u + du,
        v + dv,
        omega + domega,
        omega_top_boundary,
        omega_bottom_boundary,
        active,
        above_ground,
        1.0,
        1.0,
        pressure,
        pressure_interface,
        cell_dp,
    )
    background = continuity_state(
        u,
        v,
        omega,
        omega_top_boundary,
        omega_bottom_boundary,
        active,
        above_ground,
        1.0,
        1.0,
        pressure,
        pressure_interface,
        cell_dp,
    )
    np.testing.assert_allclose(
        candidate - background, increment, rtol=0.0, atol=1.0e-12
    )


def test_reconstruct_prebalance_winds_keeps_old_and_seeds_added_cells() -> None:
    original_winds = np.array(
        [
            [[[1.0, 11.0]], [[2.0, 12.0]]],
            [[[3.0, 13.0]], [[4.0, 14.0]]],
            [[[5.0, 15.0]], [[6.0, 16.0]]],
        ],
        dtype=np.float64,
    )
    original_above = np.array([[[True, False]], [[True, False]]], dtype=bool)
    candidate_above = np.array([[[True, True]], [[True, False]]], dtype=bool)
    seed_winds = np.array(
        [
            [[[101.0, 21.0]], [[102.0, 22.0]]],
            [[[103.0, 23.0]], [[104.0, 24.0]]],
            [[[105.0, 25.0]], [[106.0, 26.0]]],
        ],
        dtype=np.float64,
    )
    candidate_winds = np.full_like(original_winds, 900.0)
    original_saved = original_winds.copy()
    result = reconstruct_prebalance_winds(
        original_winds, original_above, candidate_above, seed_winds
    )
    assert result.dtype == np.float64
    np.testing.assert_array_equal(result[:, original_above], original_winds[:, original_above])
    np.testing.assert_array_equal(result[:, candidate_above & ~original_above], seed_winds[:, candidate_above & ~original_above])
    # The balanced/final candidate is intentionally not an input source for
    # this reconstruction; only the explicit seed fills newly supported cells.
    assert not np.any(result[:, candidate_above & ~original_above] == candidate_winds[:, candidate_above & ~original_above])
    np.testing.assert_array_equal(original_winds, original_saved)


def test_reconstruct_prebalance_winds_no_domain_change_allows_missing_seed() -> None:
    original_winds = np.array(
        [
            [[[1.0, np.nan]], [[2.0, 12.0]]],
            [[[3.0, np.nan]], [[4.0, 14.0]]],
            [[[5.0, np.nan]], [[6.0, 16.0]]],
        ],
        dtype=np.float64,
    )
    original_above = np.array([[[True, False]], [[True, False]]], dtype=bool)
    seed_winds = np.full(original_winds.shape, np.nan, dtype=np.float64)
    result_without_seed = reconstruct_prebalance_winds(
        original_winds, original_above, original_above
    )
    result_with_missing_seed = reconstruct_prebalance_winds(
        original_winds, original_above, original_above, seed_winds
    )
    np.testing.assert_array_equal(result_without_seed, original_winds)
    np.testing.assert_array_equal(result_with_missing_seed, original_winds)


def test_reconstruct_prebalance_winds_rejects_invalid_transition_atomically() -> None:
    original_winds = np.ones((3, 2, 1, 2), dtype=np.float64)
    original_above = np.array([[[True, False]], [[True, False]]], dtype=bool)
    candidate_above = np.array([[[True, True]], [[True, False]]], dtype=bool)
    seed_winds = np.full(original_winds.shape, 2.0, dtype=np.float64)
    original_saved = original_winds.copy()

    invalid_calls = (
        ("new cell without seed", lambda: reconstruct_prebalance_winds(
            original_winds, original_above, candidate_above
        )),
        ("nonfinite added seed", lambda: reconstruct_prebalance_winds(
            original_winds, original_above, candidate_above,
            np.where(candidate_above[None, ...], np.nan, seed_winds),
        )),
        ("nonfinite original active wind", lambda: reconstruct_prebalance_winds(
            np.where(original_above[None, ...], np.nan, original_winds),
            original_above, candidate_above, seed_winds
        )),
        ("removed original cell", lambda: reconstruct_prebalance_winds(
            original_winds, original_above,
            np.array([[[True, False]], [[False, False]]], dtype=bool),
            seed_winds,
        )),
    )
    for label, call in invalid_calls:
        try:
            call()
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid prebalance transition: {label}")
        np.testing.assert_array_equal(original_winds, original_saved)


def test_prebalance_seed_and_continuity_domain_identity() -> None:
    # The candidate adds a full second column. The original support/geometry
    # and the changed stage support/geometry are deliberately distinct.
    original_above = np.array([[[True, False]], [[True, False]]], dtype=bool)
    original_support = original_above.copy()
    candidate_above = np.ones((2, 1, 2), dtype=bool)
    stage_support = candidate_above.copy()
    original_winds = np.array(
        [
            [[[1.0, 99.0]], [[1.0, 99.0]]],
            [[[0.0, 99.0]], [[0.0, 99.0]]],
            [[[0.0, 99.0]], [[0.0, 99.0]]],
        ],
        dtype=np.float64,
    )
    seed_winds = np.array(
        [
            [[[4.0, 3.0]], [[4.0, 3.0]]],
            [[[0.0, 0.0]], [[0.0, 0.0]]],
            [[[0.0, 0.0]], [[0.0, 0.0]]],
        ],
        dtype=np.float64,
    )
    stage_before = reconstruct_prebalance_winds(
        original_winds, original_above, candidate_above, seed_winds
    )
    stage_after = stage_before.copy()
    assert stage_before[0, 0, 0, 1] == 3.0

    original_interfaces = np.array(
        [
            [[100000.0, 94000.0]],
            [[95000.0, 94000.0]],
            [[90000.0, 90000.0]],
        ],
        dtype=np.float64,
    )
    candidate_interfaces = np.array(
        [
            [[100000.0, 100000.0]],
            [[95000.0, 95000.0]],
            [[90000.0, 90000.0]],
        ],
        dtype=np.float64,
    )
    pressure = np.array([97500.0, 92500.0], dtype=np.float64)
    original_cell_dp = original_interfaces[:-1] - original_interfaces[1:]
    candidate_cell_dp = candidate_interfaces[:-1] - candidate_interfaces[1:]
    zero_horizontal = np.zeros((1, 2), dtype=np.float64)

    before_candidate = continuity_state(
        stage_before[0], stage_before[1], stage_before[2],
        zero_horizontal, zero_horizontal, stage_support, candidate_above,
        1.0, 1.0, pressure, candidate_interfaces, candidate_cell_dp,
    )
    after_candidate = continuity_state(
        stage_after[0], stage_after[1], stage_after[2],
        zero_horizontal, zero_horizontal, stage_support, candidate_above,
        1.0, 1.0, pressure, candidate_interfaces, candidate_cell_dp,
    )
    np.testing.assert_array_equal(after_candidate - before_candidate, 0.0)

    # Evaluating the same stage on the original domain is a separate residual:
    # the added seeded cell and its new pressure faces are outside this mask.
    original_domain_residual = continuity_state(
        stage_before[0], stage_before[1], stage_before[2],
        zero_horizontal, zero_horizontal, original_support, original_above,
        1.0, 1.0, pressure, original_interfaces, original_cell_dp,
    )
    assert np.any(before_candidate != original_domain_residual)
    assert np.any(original_domain_residual[original_support] != 0.0)


if __name__ == "__main__":
    test_partial_bottom_pressure_face_state()
    test_partial_bottom_pressure_face_increment_and_identity()
    test_reconstruct_prebalance_winds_keeps_old_and_seeds_added_cells()
    test_reconstruct_prebalance_winds_no_domain_change_allows_missing_seed()
    test_reconstruct_prebalance_winds_rejects_invalid_transition_atomically()
    test_prebalance_seed_and_continuity_domain_identity()
    print("Pressure continuity oracle tests passed")
