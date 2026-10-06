"""Manufactured checks for dry-air hydrometeor moment contracts."""
from __future__ import annotations

import numpy as np

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from hydrometeor_moments import (  # noqa: E402
    BULK_VOLUME_UNITS,
    DRY_AIR_BASIS,
    MASS_UNITS,
    NUMBER_UNITS,
    conservative_remap_moments,
    validate_bulk_volume,
    validate_mass_number,
)


def _mass_number(mass, number, **overrides):
    declarations = {
        "mass_units": MASS_UNITS,
        "number_units": NUMBER_UNITS,
        "mass_basis": DRY_AIR_BASIS,
        "number_basis": DRY_AIR_BASIS,
        "particle_mass_min_kg": 1.0e-12,
        "particle_mass_max_kg": 1.0e-9,
        "bound_source": "manufactured test bounds",
        "uncertainty_description": "declared interval; statistical uncertainty not assessed",
    }
    declarations.update(overrides)
    return validate_mass_number(mass, number, **declarations)


def _bulk_volume(mass, volume, **overrides):
    declarations = {
        "mass_units": MASS_UNITS,
        "volume_units": BULK_VOLUME_UNITS,
        "mass_basis": DRY_AIR_BASIS,
        "volume_basis": DRY_AIR_BASIS,
        "bulk_density_min_kg_m3": 100.0,
        "bulk_density_max_kg_m3": 900.0,
        "bound_source": "manufactured test bounds",
        "uncertainty_description": "declared interval; statistical uncertainty not assessed",
    }
    declarations.update(overrides)
    return validate_bulk_volume(mass, volume, **declarations)


def test_mass_number_checks_finite_declared_bounds_and_reports_masks():
    result = _mass_number(
        np.array([1.0e-6, 2.0e-6, 0.0]),
        np.array([1.0e3, 2.0e3, 0.0]),
    )
    assert result["status"] == "PASS_SCOPED"
    assert result["valid"] is True
    assert result["violation_count"] == 0
    assert result["mutated_input"] is False

    invalid = _mass_number([1.0e-6], [1.0e3], particle_mass_max_kg=np.inf)
    assert invalid["status"] == "REJECTED"
    assert invalid["reason"] == "INVALID_PARTICLE_MASS_BOUNDS"


def test_positive_mass_with_zero_number_is_unrealizable_and_not_floored():
    mass = np.array([0.0, 1.0e-6, 1.0e-6])
    number = np.array([0.0, 0.0, 1.0e6])
    mass_before, number_before = mass.copy(), number.copy()
    result = _mass_number(mass, number)
    assert result["status"] == "FAIL"
    assert result["violation_count"] == 1
    np.testing.assert_array_equal(result["violation_mask"], [False, True, False])
    np.testing.assert_array_equal(mass, mass_before)
    np.testing.assert_array_equal(number, number_before)

    underflow = _mass_number([0.0], [1.0e-320])
    assert underflow["status"] == "FAIL"


def test_missing_number_is_explicitly_unsupported_and_declarations_are_checked():
    missing = _mass_number([1.0e-6], None)
    assert missing["status"] == "UNSUPPORTED"
    assert missing["valid"] is None

    wrong_basis = _mass_number([1.0e-6], [1.0e3], number_basis="moist_air")
    assert wrong_basis["status"] == "REJECTED"
    assert wrong_basis["reason"] == "BASIS_MISMATCH"

    missing_bounds = _mass_number(
        [1.0e-6], [1.0e3], particle_mass_min_kg=None, particle_mass_max_kg=None
    )
    assert missing_bounds["status"] == "UNSUPPORTED"
    assert missing_bounds["source_authentication"] == "NOT_ASSESSED"

    malformed_source = _mass_number([1.0e-6], [1.0e3], bound_source="  ")
    assert malformed_source["status"] == "REJECTED"

    complex_values = _mass_number(np.array([1.0e-6 + 0.0j]), [1.0e3])
    assert complex_values["status"] == "REJECTED"
    assert complex_values["reason"] == "NONREAL_FIELD:mass"

    string_values = _mass_number(["1e-6"], [1.0e3])
    assert string_values["status"] == "REJECTED"
    assert string_values["reason"] == "NONREAL_FIELD:mass"

    boolean_bounds = _mass_number(
        [1.0e-6], [1.0e3], particle_mass_min_kg=True
    )
    assert boolean_bounds["status"] == "REJECTED"


def test_bulk_volume_bounds_and_missing_volume_support():
    result = _bulk_volume([0.09, 0.0], [0.0003, 0.0])
    assert result["status"] == "PASS_SCOPED"

    boundary = _bulk_volume([0.09, 0.09], [0.09 / 900.0, 0.09 / 100.0])
    assert boundary["status"] == "PASS_SCOPED"

    invalid = _bulk_volume([0.09], [0.00005])
    assert invalid["status"] == "FAIL"
    assert invalid["violation_count"] == 1

    positive_mass_zero_volume = _bulk_volume([1.0e-320], [0.0])
    assert positive_mass_zero_volume["status"] == "FAIL"
    zero_mass_positive_volume = _bulk_volume([0.0], [1.0e-320])
    assert zero_mass_positive_volume["status"] == "FAIL"

    missing = _bulk_volume([0.09], None)
    assert missing["status"] == "UNSUPPORTED"

    wrong_units = _bulk_volume([0.09], [0.0003], volume_units="m3 kg-1 moist air")
    assert wrong_units["status"] == "REJECTED"

    empty = _bulk_volume([], [])
    assert empty["status"] == "UNSUPPORTED"
    assert empty["reason"] == "EMPTY_VALIDATION_DOMAIN"


def test_conservative_remap_transfers_mass_number_and_volume_extensively():
    dry_mass = np.array([2.0, 3.0])
    weights = np.array([[0.25, 0.0], [0.75, 0.4], [0.0, 0.6]])
    mass = {"rain": np.array([2.0e-6, 4.0e-6])}
    number = {"rain": np.array([2.0e4, 4.0e4])}
    volume = {"rain": np.array([4.0e-9, 8.0e-9])}
    result = conservative_remap_moments(
        dry_mass,
        weights,
        mass,
        number,
        volume,
        particle_mass_bounds_kg={"rain": (1.0e-10, 2.0e-10)},
        bulk_density_bounds_kg_m3={"rain": (100.0, 900.0)},
        particle_mass_bound_source={"rain": "manufactured bounds"},
        particle_mass_uncertainty={"rain": "interval only; sigma not assessed"},
        bulk_density_bound_source={"rain": "manufactured bounds"},
        bulk_density_uncertainty={"rain": "interval only; sigma not assessed"},
        mass_units=MASS_UNITS,
        number_units=NUMBER_UNITS,
        volume_units=BULK_VOLUME_UNITS,
        mass_basis=DRY_AIR_BASIS,
        number_basis=DRY_AIR_BASIS,
        volume_basis=DRY_AIR_BASIS,
    )
    np.testing.assert_allclose(result["dry_air_mass"], [0.5, 2.7, 1.8])
    for key, donor in (("mass_mixing_ratios", mass),
                       ("number_concentrations", number),
                       ("bulk_volume_moments", volume)):
        before = np.sum(dry_mass * donor["rain"])
        after = np.sum(result["dry_air_mass"] * result[key]["rain"])
        np.testing.assert_allclose(after, before, rtol=0.0, atol=1.0e-18)
    assert result["validation"]["rain"]["number"]["status"] == "PASS_SCOPED"
    assert result["validation"]["rain"]["bulk_volume"]["status"] == "PASS_SCOPED"


def test_remap_rejects_bad_weights_shapes_and_zero_target_carrier():
    base = dict(
        dry_air_mass=[1.0, 1.0],
        mass_mixing_ratios={"snow": [1.0e-5, 1.0e-5]},
        number_concentrations={},
        bulk_volume_moments={},
        particle_mass_bounds_kg={},
        bulk_density_bounds_kg_m3={},
        particle_mass_bound_source={},
        particle_mass_uncertainty={},
        bulk_density_bound_source={},
        bulk_density_uncertainty={},
        mass_units=MASS_UNITS,
        number_units=NUMBER_UNITS,
        volume_units=BULK_VOLUME_UNITS,
        mass_basis=DRY_AIR_BASIS,
        number_basis=DRY_AIR_BASIS,
        volume_basis=DRY_AIR_BASIS,
    )
    try:
        conservative_remap_moments(weights=[[1.1, 0.0], [-0.1, 1.0]], **base)
    except ValueError as exc:
        assert "NEGATIVE_REMAP_WEIGHT" in str(exc)
    else:
        raise AssertionError("negative weights were accepted")

    try:
        conservative_remap_moments(weights=[[1.0]], **base)
    except ValueError as exc:
        assert "MALFORMED_REMAP_SHAPE" in str(exc)
    else:
        raise AssertionError("malformed weights were accepted")

    try:
        conservative_remap_moments(weights=[[0.9, 1.0]], **base)
    except ValueError as exc:
        assert "REMAP_WEIGHTS_MUST_CONSERVE_EACH_DONOR" in str(exc)
    else:
        raise AssertionError("open-domain weights were accepted as closed-domain")

    malformed_declarations = dict(base, particle_mass_bounds_kg=None)
    try:
        conservative_remap_moments(weights=[[0.5, 0.5], [0.5, 0.5]],
                                   **malformed_declarations)
    except ValueError as exc:
        assert "INVALID_DECLARATION_MAPPING" in str(exc)
    else:
        raise AssertionError("malformed declaration mapping was accepted")

    try:
        conservative_remap_moments(weights=[[1.0, 1.0], [0.0, 0.0]], **base)
    except ValueError as exc:
        assert "ZERO_OR_INVALID_TARGET_DRY_MASS" in str(exc)
    else:
        raise AssertionError("zero target carrier was accepted")


def test_remap_preserves_unsupported_species_moments_as_none():
    result = conservative_remap_moments(
        [1.0, 2.0],
        [[0.5, 0.0], [0.5, 1.0]],
        {"ice": [1.0e-6, 2.0e-6], "snow": [0.0, 1.0e-6]},
        {"ice": None},
        {},
        particle_mass_bounds_kg={},
        bulk_density_bounds_kg_m3={},
        particle_mass_bound_source={},
        particle_mass_uncertainty={},
        bulk_density_bound_source={},
        bulk_density_uncertainty={},
        mass_units=MASS_UNITS,
        number_units=NUMBER_UNITS,
        volume_units=BULK_VOLUME_UNITS,
        mass_basis=DRY_AIR_BASIS,
        number_basis=DRY_AIR_BASIS,
        volume_basis=DRY_AIR_BASIS,
    )
    assert result["number_concentrations"]["ice"] is None
    assert result["number_concentrations"]["snow"] is None
    assert result["bulk_volume_moments"]["ice"] is None
    assert result["unsupported"]["ice"] == ["number", "bulk_volume"]
    assert result["unsupported"]["snow"] == ["number", "bulk_volume"]


def test_remap_rejects_overflowing_totals_without_an_infinite_error_budget():
    declarations = dict(
        weights=np.eye(2), mass_mixing_ratios={"ice": [0.0, 0.0]},
        number_concentrations={}, bulk_volume_moments={},
        particle_mass_bounds_kg={}, bulk_density_bounds_kg_m3={},
        particle_mass_bound_source={}, particle_mass_uncertainty={},
        bulk_density_bound_source={}, bulk_density_uncertainty={},
        mass_units=MASS_UNITS, number_units=NUMBER_UNITS,
        volume_units=BULK_VOLUME_UNITS, mass_basis=DRY_AIR_BASIS,
        number_basis=DRY_AIR_BASIS, volume_basis=DRY_AIR_BASIS,
    )
    # Both endpoint totals fit; adding their scales before multiplying by
    # epsilon does not. The returned arithmetic budget must stay finite.
    result = conservative_remap_moments([5.0e307, 5.0e307], **declarations)
    assert np.isfinite(result["conservation"]["dry_air_mass"]["roundoff_bound"])
    try:
        conservative_remap_moments([1.0e308, 1.0e308], **declarations)
    except ValueError as exc:
        assert str(exc) == "NONFINITE_CONSERVATION_TOTAL"
    else:
        raise AssertionError("an overflowing total passed conservation")


def test_remap_rejects_underflow_of_positive_mass_number_and_volume_products():
    common = dict(
        weights=[[1.0]], mass_mixing_ratios={"rain": [1.0e-30]},
        number_concentrations={}, bulk_volume_moments={},
        particle_mass_bounds_kg={}, bulk_density_bounds_kg_m3={},
        particle_mass_bound_source={}, particle_mass_uncertainty={},
        bulk_density_bound_source={}, bulk_density_uncertainty={},
        mass_units=MASS_UNITS, number_units=NUMBER_UNITS,
        volume_units=BULK_VOLUME_UNITS, mass_basis=DRY_AIR_BASIS,
        number_basis=DRY_AIR_BASIS, volume_basis=DRY_AIR_BASIS,
    )

    cases = (
        ([1.0e-300], common, "UNDERFLOW:MASS_EXTENSIVE:rain"),
        ([1.0e-20], dict(
            common,
            number_concentrations={"rain": [1.0e-320]},
            particle_mass_bounds_kg={"rain": (1.0e289, 1.0e291)},
            particle_mass_bound_source={"rain": "manufactured bounds"},
            particle_mass_uncertainty={"rain": "interval only; sigma not assessed"},
        ), "UNDERFLOW:NUMBER_EXTENSIVE:rain"),
        ([1.0e-20], dict(
            common,
            bulk_volume_moments={"rain": [1.0e-320]},
            bulk_density_bounds_kg_m3={"rain": (1.0e289, 1.0e291)},
            bulk_density_bound_source={"rain": "manufactured bounds"},
            bulk_density_uncertainty={"rain": "interval only; sigma not assessed"},
        ), "UNDERFLOW:VOLUME_EXTENSIVE:rain"),
    )
    for dry_mass, declarations, expected in cases:
        try:
            conservative_remap_moments(dry_mass, **declarations)
        except ValueError as exc:
            assert expected in str(exc), str(exc)
        else:
            raise AssertionError(f"positive extensive product underflow passed: {expected}")

    weighted = dict(common, weights=[[1.0e-320], [1.0]])
    try:
        conservative_remap_moments([1.0], **weighted)
    except ValueError as exc:
        assert "UNDERFLOW:REMAP_MASS_EXTENSIVE:rain" in str(exc)
    else:
        raise AssertionError("positive weighted extensive product underflow passed")

    try:
        conservative_remap_moments(
            [1.0, 1.0e308], [[1.0, 1.0]],
            {"rain": [np.nextafter(0.0, 1.0), 0.0]}, {}, {},
            particle_mass_bounds_kg={}, bulk_density_bounds_kg_m3={},
            particle_mass_bound_source={}, particle_mass_uncertainty={},
            bulk_density_bound_source={}, bulk_density_uncertainty={},
            mass_units=MASS_UNITS, number_units=NUMBER_UNITS,
            volume_units=BULK_VOLUME_UNITS, mass_basis=DRY_AIR_BASIS,
            number_basis=DRY_AIR_BASIS, volume_basis=DRY_AIR_BASIS,
        )
    except ValueError as exc:
        assert "UNDERFLOW:RECOVER_MASS:rain" in str(exc)
    else:
        raise AssertionError("positive intensive recovery underflow passed")


def main():
    tests = (
        test_mass_number_checks_finite_declared_bounds_and_reports_masks,
        test_positive_mass_with_zero_number_is_unrealizable_and_not_floored,
        test_missing_number_is_explicitly_unsupported_and_declarations_are_checked,
        test_bulk_volume_bounds_and_missing_volume_support,
        test_conservative_remap_transfers_mass_number_and_volume_extensively,
        test_remap_rejects_bad_weights_shapes_and_zero_target_carrier,
        test_remap_preserves_unsupported_species_moments_as_none,
        test_remap_rejects_overflowing_totals_without_an_infinite_error_budget,
        test_remap_rejects_underflow_of_positive_mass_number_and_volume_products,
    )
    for test in tests:
        test()
    print(f"Hydrometeor moment contract tests passed ({len(tests)})")


if __name__ == "__main__":
    main()
