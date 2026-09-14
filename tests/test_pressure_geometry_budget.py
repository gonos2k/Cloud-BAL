#!/usr/bin/env python3
"""Analytic tests for the pressure-geometry accounting kernel."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import (  # noqa: E402
    THERMO_CP_DRY,
    THERMO_SPECIES_CP,
    THERMO_SPECIES_H0,
    THERMO_T0,
    pressure_geometry_budget,
)


VALUE_KEYS = (
    "geometry_analysis_species_change_kg",
    "geometry_analysis_mixing_ratio_change_kg",
    "geometry_analysis_dry_mass_redistribution_kg",
    "geometry_analysis_dry_air_change_kg",
    "geometry_analysis_enthalpy_change_j",
    "geometry_analysis_geometry_mass_change_kg",
    "geometry_analysis_enthalpy_composition_change_j",
    "geometry_analysis_enthalpy_mass_metric_change_j",
    "geometry_analysis_total_mass_error_kg",
    "geometry_analysis_max_cell_mass_error_kg",
)


def mixture_enthalpy(temperature: np.ndarray, species: np.ndarray) -> np.ndarray:
    axes = (1,) * temperature.ndim
    cp = THERMO_SPECIES_CP.reshape((6,) + axes)
    h0 = THERMO_SPECIES_H0.reshape((6,) + axes)
    capacity = THERMO_CP_DRY + np.sum(cp * species, axis=0)
    return capacity * (temperature - THERMO_T0) + np.sum(h0 * species, axis=0)


def independent_expected_values(
    before_mass: np.ndarray,
    before_temperature: np.ndarray,
    before_species: np.ndarray,
    before_pressure_mass: np.ndarray,
    before_above: np.ndarray,
    after_mass: np.ndarray,
    after_temperature: np.ndarray,
    after_species: np.ndarray,
    after_pressure_mass: np.ndarray,
    after_above: np.ndarray,
) -> dict[str, np.ndarray | float]:
    """Build expected ledgers from masked extensive quantities."""
    mb = np.where(before_above, before_mass, 0.0)
    ma = np.where(after_above, after_mass, 0.0)
    tb = np.where(before_above, before_temperature, THERMO_T0)
    ta = np.where(after_above, after_temperature, THERMO_T0)
    rb = np.where(before_above[None, ...], before_species, 0.0)
    ra = np.where(after_above[None, ...], after_species, 0.0)
    pb = np.where(before_above, before_pressure_mass, 0.0)
    pa = np.where(after_above, after_pressure_mass, 0.0)
    species_terms = ma[None, ...] * ra - mb[None, ...] * rb
    before_h = mixture_enthalpy(tb, rb)
    after_h = mixture_enthalpy(ta, ra)
    dry_change = ma - mb
    geometry = pa - pb
    cell_error = dry_change + np.sum(species_terms, axis=0) - geometry
    return {
        "geometry_analysis_species_change_kg": np.sum(species_terms, axis=tuple(range(1, species_terms.ndim))),
        "geometry_analysis_mixing_ratio_change_kg": np.sum(mb[None, ...] * (ra - rb), axis=tuple(range(1, ra.ndim))),
        "geometry_analysis_dry_mass_redistribution_kg": np.sum(dry_change[None, ...] * ra, axis=tuple(range(1, ra.ndim))),
        "geometry_analysis_dry_air_change_kg": float(np.sum(dry_change)),
        "geometry_analysis_enthalpy_change_j": float(np.sum(ma * after_h - mb * before_h)),
        "geometry_analysis_geometry_mass_change_kg": float(np.sum(geometry)),
        "geometry_analysis_enthalpy_composition_change_j": float(np.sum(mb * (after_h - before_h))),
        "geometry_analysis_enthalpy_mass_metric_change_j": float(np.sum(dry_change * after_h)),
        "geometry_analysis_total_mass_error_kg": float(np.sum(dry_change) + np.sum(species_terms) - np.sum(geometry)),
        "geometry_analysis_max_cell_mass_error_kg": float(np.max(np.abs(cell_error), initial=0.0)),
    }


def assert_budget_values(
    values: dict[str, np.ndarray | float],
    expected: dict[str, np.ndarray | float],
) -> None:
    for key in VALUE_KEYS:
        assert key in values, key
        np.testing.assert_allclose(
            np.asarray(values[key], dtype=np.float64),
            np.asarray(expected[key], dtype=np.float64),
            rtol=0.0,
            atol=1.0e-11,
        )


def assert_scales_are_nonnegative(scales: dict[str, np.ndarray | float]) -> None:
    for key, scale in scales.items():
        assert key.startswith("geometry_analysis_")
        assert np.all(np.isfinite(np.asarray(scale, dtype=np.float64)))
        assert np.all(np.asarray(scale, dtype=np.float64) >= 0.0)


def test_dry_three_dimensional_addition_has_known_budget() -> None:
    old = np.array([True, False]).reshape(2, 1, 1)
    new = np.ones_like(old)
    mb = np.array([2.0, np.nan]).reshape(old.shape)
    ma = np.array([3.0, 4.0]).reshape(old.shape)
    tb = np.array([THERMO_T0 + 1.0, np.nan]).reshape(old.shape)
    ta = np.array([THERMO_T0 + 2.0, THERMO_T0 + 3.0]).reshape(old.shape)
    rb = np.zeros((6, *old.shape))
    rb[:, ~old] = np.nan
    ra = np.zeros_like(rb)
    values, scales = pressure_geometry_budget(mb, tb, rb, mb, old, ma, ta, ra, ma, new)
    expected = {key: np.zeros(6) if "species_change" in key or "mixing_ratio" in key
                or "redistribution" in key else 0.0 for key in VALUE_KEYS}
    expected.update({
        "geometry_analysis_dry_air_change_kg": 5.0,
        "geometry_analysis_geometry_mass_change_kg": 5.0,
        "geometry_analysis_enthalpy_change_j": 16.0 * THERMO_CP_DRY,
        "geometry_analysis_enthalpy_composition_change_j": 2.0 * THERMO_CP_DRY,
        "geometry_analysis_enthalpy_mass_metric_change_j": 14.0 * THERMO_CP_DRY,
    })
    assert_budget_values(values, expected)
    # Exact mass closure must still retain a nonzero rounding-error scale.
    assert scales["geometry_analysis_max_cell_mass_error_kg"] == 8.0


def test_pressure_geometry_budget_same_domain_analytic() -> None:
    before_mass = np.array([2.0, 3.5], dtype=np.float64)
    after_mass = np.array([2.5, 3.0], dtype=np.float64)
    before_temperature = np.array([THERMO_T0 + 1.0, 292.0], dtype=np.float64)
    after_temperature = np.array([THERMO_T0 + 2.0, 288.0], dtype=np.float64)
    before_species = np.array(
        [[0.0, .020], [0.0, .003], [0.0, .004],
         [0.0, .005], [0.0, .007], [0.0, .009]],
        dtype=np.float64,
    )
    after_species = np.array(
        [[0.0, .018], [0.0, .002], [0.0, .0045],
         [0.0, .005], [0.0, .007], [0.0, .009]],
        dtype=np.float64,
    )
    before_pressure_mass = np.array([210.0, 330.0], dtype=np.float64)
    after_pressure_mass = np.array([220.0, 315.0], dtype=np.float64)
    before_above = np.array([True, True], dtype=bool)
    after_above = np.array([True, True], dtype=bool)

    before_h = mixture_enthalpy(before_temperature, before_species)
    after_h = mixture_enthalpy(after_temperature, after_species)
    np.testing.assert_allclose(before_h[0], THERMO_CP_DRY, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(after_h[0], 2.0 * THERMO_CP_DRY, rtol=0.0, atol=0.0)
    expected = independent_expected_values(
        before_mass, before_temperature, before_species, before_pressure_mass, before_above,
        after_mass, after_temperature, after_species, after_pressure_mass, after_above,
    )
    values, scales = pressure_geometry_budget(
        before_mass,
        before_temperature,
        before_species,
        before_pressure_mass,
        before_above,
        after_mass,
        after_temperature,
        after_species,
        after_pressure_mass,
        after_above,
    )
    assert_budget_values(values, expected)
    assert_scales_are_nonnegative(scales)
    np.testing.assert_allclose(
        values["geometry_analysis_species_change_kg"],
        values["geometry_analysis_mixing_ratio_change_kg"]
        + values["geometry_analysis_dry_mass_redistribution_kg"],
        rtol=0.0,
        atol=1.0e-11,
    )
    np.testing.assert_allclose(
        values["geometry_analysis_enthalpy_change_j"],
        values["geometry_analysis_enthalpy_composition_change_j"]
        + values["geometry_analysis_enthalpy_mass_metric_change_j"],
        rtol=0.0,
        atol=1.0e-8,
    )


def test_pressure_geometry_budget_masks_absent_sides_and_garbage_cells() -> None:
    before_mass = np.array([2.0, 3.0, np.nan, np.nan], dtype=np.float64)
    after_mass = np.array([2.5, 2.5, 1.25, np.nan], dtype=np.float64)
    before_temperature = np.array([280.0, 292.0, np.nan, np.nan], dtype=np.float64)
    after_temperature = np.array([283.0, 288.0, 275.0, np.nan], dtype=np.float64)
    before_species = np.array(
        [[.010, .020, np.nan, np.nan], [.002, .003, np.nan, np.nan], [.001, .004, np.nan, np.nan],
         [.003, .005, np.nan, np.nan], [.006, .007, np.nan, np.nan], [.008, .009, np.nan, np.nan]],
        dtype=np.float64,
    )
    after_species = np.array(
        [[.012, .018, .011, np.nan], [.003, .002, .002, np.nan], [.0015, .0045, .001, np.nan],
         [.003, .005, .003, np.nan], [.006, .007, .006, np.nan], [.008, .009, .008, np.nan]],
        dtype=np.float64,
    )
    before_pressure_mass = np.array([210.0, 330.0, np.nan, np.nan], dtype=np.float64)
    after_pressure_mass = np.array([220.0, 315.0, 205.0, np.nan], dtype=np.float64)
    before_above = np.array([True, True, False, False], dtype=bool)
    after_above = np.array([True, True, True, False], dtype=bool)

    # Absent sides are zero before arithmetic; index 2 is a genuinely added
    # cell and index 3 is outside the union entirely.
    expected = independent_expected_values(
        before_mass, before_temperature, before_species, before_pressure_mass, before_above,
        after_mass, after_temperature, after_species, after_pressure_mass, after_above,
    )
    values, scales = pressure_geometry_budget(
        before_mass, before_temperature, before_species, before_pressure_mass, before_above,
        after_mass, after_temperature, after_species, after_pressure_mass, after_above,
    )
    assert_budget_values(values, expected)
    assert_scales_are_nonnegative(scales)

    # Changing placeholders outside the union cannot affect any budget term.
    before_mass[2:] = [12345.0, 54321.0]
    before_temperature[2:] = [1234.0, 4321.0]
    before_species[:, 2:] = 123.0
    before_pressure_mass[2:] = [98765.0, 56789.0]
    changed_values, _ = pressure_geometry_budget(
        before_mass, before_temperature, before_species, before_pressure_mass, before_above,
        after_mass, after_temperature, after_species, after_pressure_mass, after_above,
    )
    for key in VALUE_KEYS:
        np.testing.assert_array_equal(changed_values[key], values[key])


def test_pressure_geometry_budget_empty_union_is_zero() -> None:
    shape = (2,)
    before_above = np.zeros(shape, dtype=bool)
    after_above = np.zeros(shape, dtype=bool)
    before_mass = np.array([2.0, 3.0])
    after_mass = np.array([4.0, 5.0])
    before_temperature = np.array([280.0, 290.0])
    after_temperature = np.array([285.0, 295.0])
    before_species = np.full((6, *shape), 0.01, dtype=np.float64)
    after_species = np.full((6, *shape), 0.02, dtype=np.float64)
    before_pressure_mass = np.array([100.0, 200.0])
    after_pressure_mass = np.array([300.0, 400.0])
    values, scales = pressure_geometry_budget(
        before_mass, before_temperature, before_species, before_pressure_mass, before_above,
        after_mass, after_temperature, after_species, after_pressure_mass, after_above,
    )
    for key in VALUE_KEYS:
        np.testing.assert_array_equal(values[key], 0.0)
    for key, scale in scales.items():
        np.testing.assert_array_equal(scale, 0.0, err_msg=key)


def test_pressure_geometry_budget_reverses_and_telescopes_through_geometry_addition() -> None:
    shape = (3,)
    original_above = np.array([True, True, False], dtype=bool)
    proposal_above = original_above.copy()
    thermo_above = original_above.copy()
    final_above = np.array([True, True, True], dtype=bool)

    original_mass = np.array([2.0, 3.0, 999.0])
    proposal_mass = np.array([2.25, 2.8, 888.0])
    thermo_mass = proposal_mass.copy()
    final_mass = np.array([2.25, 2.8, 1.2])
    original_temperature = np.array([THERMO_T0 + 1.0, THERMO_T0 + 2.0, 999.0])
    proposal_temperature = np.array([THERMO_T0 + 1.5, THERMO_T0 + 2.5, 888.0])
    thermo_temperature = np.array([THERMO_T0 + 2.0, THERMO_T0 + 3.0, 777.0])
    final_temperature = np.array([THERMO_T0 + 2.0, THERMO_T0 + 3.0, THERMO_T0 + 4.0])
    original_species = np.zeros((6, 3), dtype=np.float64)
    proposal_species = np.zeros((6, 3), dtype=np.float64)
    thermo_species = np.zeros((6, 3), dtype=np.float64)
    final_species = np.zeros((6, 3), dtype=np.float64)
    original_species[:, :2] = np.array(
        [[.010, .020], [.002, .003], [.001, .004],
         [.003, .005], [.006, .007], [.008, .009]],
        dtype=np.float64,
    )
    proposal_species[:, :2] = original_species[:, :2] + np.array(
        [[.001, -.001], [.0005, 0.0], [0.0, .0005],
         [0.0, 0.0], [.0005, 0.0], [0.0, -.0005]],
        dtype=np.float64,
    )
    thermo_species[:, :2] = proposal_species[:, :2] + np.array(
        [[-.0005, .0005], [0.0005, -.0005], [0.0, 0.0],
         [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]],
        dtype=np.float64,
    )
    final_species[:, :2] = thermo_species[:, :2]
    final_species[:, 2] = [.004, .001, .002, .003, .005, .007]
    original_pressure_mass = np.array([210.0, 330.0, 9999.0])
    proposal_pressure_mass = np.array([215.0, 325.0, 8888.0])
    thermo_pressure_mass = proposal_pressure_mass.copy()
    final_pressure_mass = np.array([220.0, 320.0, 50.0])

    def budget(
        left_mass, left_temperature, left_species, left_pressure_mass, left_above,
        right_mass, right_temperature, right_species, right_pressure_mass, right_above,
    ):
        return pressure_geometry_budget(
            left_mass, left_temperature, left_species, left_pressure_mass, left_above,
            right_mass, right_temperature, right_species, right_pressure_mass, right_above,
        )[0]

    original_to_proposal = budget(
        original_mass, original_temperature, original_species, original_pressure_mass, original_above,
        proposal_mass, proposal_temperature, proposal_species, proposal_pressure_mass, proposal_above,
    )
    proposal_to_thermo = budget(
        proposal_mass, proposal_temperature, proposal_species, proposal_pressure_mass, proposal_above,
        thermo_mass, thermo_temperature, thermo_species, thermo_pressure_mass, thermo_above,
    )
    thermo_to_geometry = budget(
        thermo_mass, thermo_temperature, thermo_species, thermo_pressure_mass, thermo_above,
        final_mass, final_temperature, final_species, final_pressure_mass, final_above,
    )
    original_to_final = budget(
        original_mass, original_temperature, original_species, original_pressure_mass, original_above,
        final_mass, final_temperature, final_species, final_pressure_mass, final_above,
    )
    direct_keys = (
        "geometry_analysis_species_change_kg",
        "geometry_analysis_dry_air_change_kg",
        "geometry_analysis_enthalpy_change_j",
        "geometry_analysis_geometry_mass_change_kg",
        "geometry_analysis_total_mass_error_kg",
    )
    for key in direct_keys:
        telescoped = (
            np.asarray(original_to_proposal[key], dtype=np.float64)
            + np.asarray(proposal_to_thermo[key], dtype=np.float64)
            + np.asarray(thermo_to_geometry[key], dtype=np.float64)
        )
        np.testing.assert_allclose(
            telescoped,
            original_to_final[key],
            rtol=0.0,
            atol=1.0e-10,
            err_msg=key,
        )

    removed = budget(
        final_mass, final_temperature, final_species, final_pressure_mass, final_above,
        thermo_mass, thermo_temperature, thermo_species, thermo_pressure_mass, thermo_above,
    )
    for key in direct_keys:
        np.testing.assert_allclose(
            np.asarray(removed[key], dtype=np.float64),
            -np.asarray(thermo_to_geometry[key], dtype=np.float64),
            rtol=0.0,
            atol=1.0e-10,
            err_msg=f"reverse {key}",
        )


def main() -> None:
    test_dry_three_dimensional_addition_has_known_budget()
    test_pressure_geometry_budget_same_domain_analytic()
    test_pressure_geometry_budget_masks_absent_sides_and_garbage_cells()
    test_pressure_geometry_budget_empty_union_is_zero()
    test_pressure_geometry_budget_reverses_and_telescopes_through_geometry_addition()
    print("Pressure geometry-budget tests passed")


if __name__ == "__main__":
    main()
