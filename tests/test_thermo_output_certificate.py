"""Focused tests for actual stored thermodynamic-output diagnostics."""

from pathlib import Path
import sys
from fractions import Fraction

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pressure_transition_reference as reference  # noqa: E402
from thermo_output_certificate import (  # noqa: E402
    certify_actual_saturation_output,
)


def saturation_mixing_ratio(pressure: float, temperature: float, *, over_ice: bool = False) -> float:
    tc = temperature - reference.THERMO_T0
    if over_ice:
        es = 611.15 * np.exp(22.452 * tc / (temperature - 0.55))
    else:
        es = 611.20 * np.exp(17.67 * tc / (tc + 243.5))
    es = min(0.99 * pressure, max(0.0, float(es)))
    return float(0.622 * es / (pressure - es))


def mixture_enthalpy(temperature: float, species: np.ndarray) -> float:
    capacity = reference.THERMO_CP_DRY + reference.THERMO_SPECIES_CP @ species
    return float(
        capacity * (temperature - reference.THERMO_T0)
        + reference.THERMO_SPECIES_H0 @ species
    )


def balanced_input(
    target_temperature: float, *, over_ice: bool = False,
) -> tuple[float, np.ndarray, float, float, np.ndarray]:
    pressure = 85000.0
    target_rh = 0.8
    target_vapor = target_rh * saturation_mixing_ratio(
        pressure, target_temperature, over_ice=over_ice
    )
    final = np.array(
        [target_vapor, 0.001, 0.001, 0.01, 0.02, 0.03], dtype=np.float64
    )
    if over_ice:
        final[1] = 0.0
        initial = final.copy()
        initial[0] += 0.001
        initial[2] = 0.0
    else:
        initial = final.copy()
        initial[0] += 0.001
        initial[1] = 0.0
    initial_temperature = float(
        reference.THERMO_T0
        + (
            mixture_enthalpy(target_temperature, final)
            - reference.THERMO_SPECIES_H0 @ initial
        )
        / (reference.THERMO_CP_DRY + reference.THERMO_SPECIES_CP @ initial)
    )
    return pressure, initial, initial_temperature, target_rh, final


def stored_result(
    pressure: float,
    initial: np.ndarray,
    initial_temperature: float,
    target_rh: float,
    *,
    over_ice: bool = False,
) -> tuple[float, np.ndarray]:
    temperature, species = reference.saturation_adjust_reference(
        pressure, initial_temperature, initial, target_rh, over_ice=over_ice
    )
    return float(np.float32(temperature)), species.astype(np.float32).astype(np.float64)


def test_liquid_actual_storage_and_residual_bound() -> None:
    pressure, initial, initial_temperature, target_rh, _ = balanced_input(300.0)
    stored_temperature, stored_species = stored_result(
        pressure, initial, initial_temperature, target_rh
    )
    certificate = certify_actual_saturation_output(
        pressure, initial_temperature, initial, target_rh,
        stored_temperature, stored_species,
    )

    assert not certificate.ideal.exhausted
    assert certificate.storage_contained
    assert certificate.transfer_root_bounds is not None
    assert certificate.transfer_error_bound >= 0.0
    assert certificate.residual_interval[0] <= certificate.residual_interval[1]
    assert certificate.phase_closure_interval[0] <= certificate.phase_closure_interval[1]
    assert certificate.enthalpy_closure_interval[0] <= certificate.enthalpy_closure_interval[1]
    assert certificate.temperature_error_bound >= 0.0
    assert np.all(certificate.species_error_bounds >= 0.0)


def test_independent_temperature_and_phase_closures_are_distinguishable() -> None:
    pressure, initial, initial_temperature, target_rh, _ = balanced_input(300.0)
    stored_temperature, stored_species = stored_result(
        pressure, initial, initial_temperature, target_rh
    )
    base = certify_actual_saturation_output(
        pressure, initial_temperature, initial, target_rh,
        stored_temperature, stored_species,
    )
    temperature_mutation = certify_actual_saturation_output(
        pressure, initial_temperature, initial, target_rh,
        float(np.nextafter(np.float32(stored_temperature), np.float32(np.inf))),
        stored_species,
    )
    phase_mutation = stored_species.copy()
    phase_mutation[1] = float(np.nextafter(np.float32(phase_mutation[1]), np.float32(np.inf)))
    phase_certificate = certify_actual_saturation_output(
        pressure, initial_temperature, initial, target_rh,
        stored_temperature, phase_mutation,
    )

    assert temperature_mutation.phase_closure_interval == base.phase_closure_interval
    assert temperature_mutation.enthalpy_closure_interval != base.enthalpy_closure_interval
    assert phase_certificate.phase_closure_interval != base.phase_closure_interval
    assert phase_certificate.enthalpy_closure_interval != base.enthalpy_closure_interval


def test_ice_and_exhaustion_have_separate_root_status() -> None:
    pressure, initial, initial_temperature, target_rh, _ = balanced_input(
        250.0, over_ice=True
    )
    stored_temperature, stored_species = stored_result(
        pressure, initial, initial_temperature, target_rh, over_ice=True
    )
    ice = certify_actual_saturation_output(
        pressure, initial_temperature, initial, target_rh,
        stored_temperature, stored_species, over_ice=True,
    )
    assert not ice.ideal.exhausted
    assert ice.transfer_root_bounds is not None

    exhausted_species = np.array(
        [0.001, 1.0e-8, 0.001, 0.01, 0.02, 0.03], dtype=np.float64
    )
    exhausted_temperature, exhausted_output = stored_result(
        pressure, exhausted_species, 280.0, 1.0
    )
    exhausted = certify_actual_saturation_output(
        pressure, 280.0, exhausted_species, 1.0,
        exhausted_temperature, exhausted_output,
    )
    assert exhausted.ideal.exhausted
    assert exhausted.transfer_error_bound is None
    assert exhausted.transfer_root_bounds is None


def test_stored_values_must_be_exact_float32() -> None:
    pressure, initial, initial_temperature, target_rh, _ = balanced_input(300.0)
    stored_temperature, stored_species = stored_result(
        pressure, initial, initial_temperature, target_rh
    )
    try:
        certify_actual_saturation_output(
            pressure, initial_temperature, initial, target_rh,
            stored_temperature + 1.0e-10, stored_species,
        )
    except ValueError as error:
        assert "float32" in str(error)
    else:
        raise AssertionError("accepted a non-float32 stored temperature")


def test_out_of_range_vapor_reports_no_physical_root_claim() -> None:
    pressure, initial, initial_temperature, target_rh, _ = balanced_input(300.0)
    stored_temperature, stored_species = stored_result(
        pressure, initial, initial_temperature, target_rh
    )
    mutated_species = stored_species.copy()
    mutated_species[0] = float(np.float32(0.199))
    certificate = certify_actual_saturation_output(
        pressure, initial_temperature, initial, target_rh,
        stored_temperature, mutated_species,
    )
    assert not certificate.transfer_in_physical_bounds
    assert certificate.residual_interval is None
    assert certificate.residual_magnitude_bound is None
    assert certificate.transfer_error_bound is None
    assert certificate.transfer_root_bounds is None
    assert not certificate.storage_species_contained


def test_physical_invalid_transfer_skips_saturation_evaluation() -> None:
    stored_vapor = float(np.float32(0.039369817823171616))
    initial = np.zeros(6, dtype=np.float64)
    stored = np.asarray(
        [stored_vapor, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32,
    ).astype(np.float64)
    certificate = certify_actual_saturation_output(
        85000.0, 150.0, initial, 0.8, 150.0, stored,
    )
    assert not certificate.transfer_in_physical_bounds
    assert certificate.residual_interval is None
    assert certificate.residual_magnitude_bound is None
    assert certificate.transfer_root_bounds is None


def test_vapor_transfer_interval_encloses_exact_fraction_subtraction() -> None:
    # The binary64 subtraction rounds, while the directed Decimal interval
    # retains the exact difference of the two supplied binary64 values.
    initial_vapor = 0.026340177201229543
    stored_vapor = float(np.float32(0.13074146211147308))
    initial = np.array([initial_vapor, 0.2, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
    stored = np.asarray(
        [stored_vapor, 0.2, 0.0, 0.0, 0.0, 0.0], dtype=np.float32,
    ).astype(np.float64)
    certificate = certify_actual_saturation_output(
        85000.0, 280.0, initial, 0.8,
        float(np.float32(280.0)), stored,
    )
    exact = Fraction.from_float(stored_vapor) - Fraction.from_float(initial_vapor)
    rounded = Fraction.from_float(stored_vapor - initial_vapor)
    assert exact != rounded
    lower, upper = certificate.vapor_transfer_bounds
    assert Fraction.from_float(lower) <= exact <= Fraction.from_float(upper)


if __name__ == "__main__":
    test_liquid_actual_storage_and_residual_bound()
    test_independent_temperature_and_phase_closures_are_distinguishable()
    test_ice_and_exhaustion_have_separate_root_status()
    test_stored_values_must_be_exact_float32()
    test_out_of_range_vapor_reports_no_physical_root_claim()
    test_physical_invalid_transfer_skips_saturation_evaluation()
    test_vapor_transfer_interval_encloses_exact_fraction_subtraction()
    print("Thermo output certificate tests passed")
