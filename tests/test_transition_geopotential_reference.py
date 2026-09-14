#!/usr/bin/env python3
"""Analytic tests for the positive-surface-pressure geopotential replay."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pressure_transition_reference import transition_geopotential_reference  # noqa: E402


G = 9.80665
R_DRY = 287.05
EPSILON = 0.622

def _alpha(temperature, species):
    q = np.asarray(species, dtype=np.float64)
    return R_DRY * temperature * (1.0 + q[0] / EPSILON) / (1.0 + q.sum())

def _surface_alpha(case):
    return _alpha(case["surface_temperature"], np.array([case["surface_vapor"]]))


def _bottom_height(case, pressure, temperature, species, surface_pressure):
    return G * case["surface_height"] + 0.5 * (
        _surface_alpha(case) + _alpha(temperature, species)
    ) * np.log(surface_pressure / pressure)


def _constant_profile(case, pressure, temperature, species, surface_pressure):
    p = np.asarray(pressure, dtype=np.float64)
    bottom = _bottom_height(case, p[0], temperature, species, surface_pressure)
    return bottom + _alpha(temperature, species) * np.log(p[0] / p)


def _stored(values):
    return np.asarray(values, dtype=np.float64).astype(np.float32).astype(np.float64)


def _call(case, **overrides):
    values = dict(case)
    values.update(overrides)
    return transition_geopotential_reference(**values)


def _same_domain_case():
    pressure = np.array([97500.0, 89000.0, 81000.0])
    old_q = np.array([0.015, 0.004, 0.002, 0.001, 0.000, 0.001])
    final_q = np.array([0.023, 0.001, 0.003, 0.002, 0.001, 0.001])
    return {
        "pressure": pressure,
        "old_geopotential": np.array([123.125, -88.5, 431.75]),
        "old_temperature": np.full(3, 260.0),
        "old_species": np.repeat(old_q[:, None], 3, axis=1),
        "final_temperature": np.full(3, 281.0),
        "final_species": np.repeat(final_q[:, None], 3, axis=1),
        "old_surface_pressure": 99990.0,
        "new_surface_pressure": 100010.0,
        "surface_temperature": 272.0,
        "surface_vapor": 0.015,
        "surface_height": 43.0,
    }


def _same_domain_profiles(case):
    old = _constant_profile(
        case, case["pressure"], case["old_temperature"][0],
        case["old_species"][:, 0], case["old_surface_pressure"])
    final = _constant_profile(
        case, case["pressure"], case["final_temperature"][0],
        case["final_species"][:, 0], case["new_surface_pressure"])
    return old, final


def _added_center_case():
    old_q = np.array([0.012, 0.004, 0.002, 0.001, 0.001, 0.003])
    final_q = np.array([0.018, 0.006, 0.001, 0.001, 0.001, 0.002])
    return {
        "pressure": np.array([100000.0, 90000.0]),
        "old_geopotential": np.array([-31.75]),
        "old_temperature": np.array([282.0]),
        "old_species": old_q[:, None],
        "final_temperature": np.full(2, 276.5),
        "final_species": np.repeat(final_q[:, None], 2, axis=1),
        "old_surface_pressure": 99990.0,
        "new_surface_pressure": 100010.0,
        "surface_temperature": 271.0,
        "surface_vapor": 0.009,
        "surface_height": 55.0,
        "seed_geopotential": 777.25,
        "seed_temperature": 260.0,
        "seed_species": np.array([0.025, 0.002, 0.001, 0.001, 0.0, 0.001]),
    }


def test_isothermal_dry_profile_has_the_analytic_log_pressure_shift():
    case = {
        "pressure": np.array([98000.0, 90000.0, 80000.0]),
        "old_geopotential": np.array([101.125, -202.5, 303.875]),
        "old_temperature": np.full(3, 280.0),
        "old_species": np.zeros((6, 3)),
        "final_temperature": np.full(3, 280.0),
        "final_species": np.zeros((6, 3)),
        "old_surface_pressure": 99990.0,
        "new_surface_pressure": 100010.0,
        "surface_temperature": 280.0,
        "surface_vapor": 0.0,
        "surface_height": 120.0,
    }
    result = _call(case)
    shift = R_DRY * 280.0 * np.log(100010.0 / 99990.0)
    np.testing.assert_array_equal(result, _stored(case["old_geopotential"] + shift))


def test_mixture_loading_and_surface_vapor_use_full_specific_volume():
    case = _same_domain_case()
    old_profile, final_profile = _same_domain_profiles(case)
    expected = _stored(case["old_geopotential"] + final_profile - old_profile)
    np.testing.assert_array_equal(_call(case), expected)


def test_same_domain_ps_positive_preserves_nonhydrostatic_phi_residual():
    case = _same_domain_case()
    old_profile, final_profile = _same_domain_profiles(case)
    residual = case["old_geopotential"] - old_profile
    np.testing.assert_array_equal(_call(case), _stored(final_profile + residual))
    assert np.any(np.abs(residual) > 1.0)


def test_one_center_added_cell_uses_separate_seed_residual():
    case = _added_center_case()
    p = case["pressure"]
    old_profile = _constant_profile(
        case, p[1:], case["old_temperature"][0], case["old_species"][:, 0],
        case["old_surface_pressure"]
    )
    final_profile = _constant_profile(
        case, p, case["final_temperature"][0], case["final_species"][:, 0],
        case["new_surface_pressure"]
    )
    prior_bottom = _bottom_height(
        case, p[0], case["seed_temperature"], case["seed_species"],
        case["new_surface_pressure"]
    )
    expected = np.array([
        case["seed_geopotential"] + final_profile[0] - prior_bottom,
        case["old_geopotential"][0] + final_profile[1] - old_profile[0],
    ])
    np.testing.assert_array_equal(_call(case), _stored(expected))
    assert abs(case["old_geopotential"][0] - old_profile[0]) > 1.0


def test_transition_inputs_are_immutable():
    case = _added_center_case()
    names = ("pressure", "old_geopotential", "old_temperature", "old_species",
             "final_temperature", "final_species", "seed_species")
    snapshots = {name: case[name].copy() for name in names}
    _call(case)
    for name, snapshot in snapshots.items():
        np.testing.assert_array_equal(case[name], snapshot)


def test_seed_for_retained_domain_is_ignored():
    case = _same_domain_case()
    expected = _call(case)
    seeded = _call(
        case,
        seed_geopotential=np.array([np.nan, np.nan]),
        seed_temperature=np.array([np.nan]),
        seed_species=np.full((6, 3), np.nan),
    )
    np.testing.assert_array_equal(seeded, expected)

def _expect_value_error(label, call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError(f"accepted invalid transition input: {label}")


def test_rejects_missing_seed_nan_shape_pressure_order_range_and_removal():
    base = _added_center_case()
    cases = {
        "missing seed": {"seed_geopotential": None, "seed_temperature": None,
                         "seed_species": None},
        "NaN seed": {"seed_geopotential": np.nan},
        "seed shape": {"seed_species": np.zeros(5)},
        "pressure ordering": {"pressure": np.array([100000.0, 101000.0])},
        "pressure range": {"new_surface_pressure": 100091.0},
        "removed cell": {
            "pressure": np.array([90000.0]),
            "old_geopotential": np.array([-31.75, 10.0]),
            "old_temperature": np.array([282.0, 280.0]),
            "old_species": np.zeros((6, 2)),
            "final_temperature": np.array([283.2]),
            "final_species": np.zeros((6, 1)),
        },
    }
    for label, overrides in cases.items():
        _expect_value_error(label, lambda overrides=overrides: _call(base, **overrides))


def main():
    tests = (
        test_isothermal_dry_profile_has_the_analytic_log_pressure_shift,
        test_mixture_loading_and_surface_vapor_use_full_specific_volume,
        test_same_domain_ps_positive_preserves_nonhydrostatic_phi_residual,
        test_one_center_added_cell_uses_separate_seed_residual,
        test_transition_inputs_are_immutable,
        test_seed_for_retained_domain_is_ignored,
        test_rejects_missing_seed_nan_shape_pressure_order_range_and_removal,
    )
    for test in tests: test()
    print("Transition geopotential reference tests passed")


if __name__ == "__main__":
    main()
