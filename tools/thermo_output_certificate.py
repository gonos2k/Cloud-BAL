"""Diagnostics for a stored saturation-adjustment result.

The verifier treats the supplied initial state as the exact float64 state seen
by the thermodynamic kernel and the result as exact float32 storage promoted to
float64.  It reports bounds and closure defects; it does not apply a pass/fail
tolerance to the production solver.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

import numpy as np

import pressure_transition_reference as reference


@dataclass(frozen=True)
class ActualThermoCertificate:
    """Ideal-output and actual-storage diagnostics for one thermodynamic cell."""

    ideal: reference.ThermoEquilibriumCertificate
    actual_temperature: float
    actual_species: np.ndarray
    temperature_error_bound: float
    species_error_bounds: np.ndarray
    storage_temperature_contained: bool
    storage_species_contained: bool
    vapor_transfer_bounds: tuple[float, float]
    residual_magnitude_bound: float | None
    transfer_error_bound: float | None
    transfer_physical_bounds: tuple[float, float]
    transfer_in_physical_bounds: bool
    transfer_root_bounds: tuple[float, float] | None
    residual_interval: tuple[float, float] | None
    phase_closure_interval: tuple[float, float]
    enthalpy_closure_interval: tuple[float, float]

    @property
    def storage_contained(self) -> bool:
        return self.storage_temperature_contained and self.storage_species_contained


def _scalar(value: Any, name: str) -> float:
    if np.ma.isMaskedArray(value) and np.any(np.ma.getmaskarray(value)):
        raise ValueError(f"{name} contains masked values")
    array = np.asarray(value)
    if array.shape != ():
        raise ValueError(f"{name} must be scalar")
    result = float(array)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _stored_scalar(value: Any, name: str) -> float:
    result = _scalar(value, name)
    rounded = np.float32(result)
    if not np.isfinite(rounded) or float(rounded) != result:
        raise ValueError(f"{name} must be an exact float32 value")
    return float(rounded)


def _stored_species(value: Any) -> np.ndarray:
    if np.ma.isMaskedArray(value) and np.any(np.ma.getmaskarray(value)):
        raise ValueError("stored species contains masked values")
    array = np.asarray(value)
    if array.shape != (6,):
        raise ValueError("stored species must have six values")
    if not np.all(np.isfinite(array)):
        raise ValueError("stored species must be finite")
    rounded = np.asarray(array, dtype=np.float32)
    if not np.all(np.isfinite(rounded)) or not np.all(rounded.astype(np.float64) == array):
        raise ValueError("stored species must contain exact float32 values")
    return rounded.astype(np.float64)


def _decimal_state_intervals(
    pressure: float,
    temperature: float,
    species: np.ndarray,
    target_rh: float,
    *,
    over_ice: bool,
) -> tuple[
    reference._DecimalInterval,
    reference._DecimalInterval,
    list[reference._DecimalInterval],
    reference._DecimalInterval,
    reference._DecimalInterval,
    reference._DecimalInterval,
    reference._DecimalInterval,
]:
    point = lambda value: reference._decimal_interval(reference._decimal_float(value))
    p = point(pressure)
    initial_t = point(temperature)
    initial_q = [point(value) for value in species]
    rh = point(target_rh)
    capacity = point(reference.THERMO_CP_DRY)
    cp = [point(value) for value in reference.THERMO_SPECIES_CP]
    h0 = [point(value) for value in reference.THERMO_SPECIES_H0]
    for index in range(6):
        capacity = reference._decimal_add(
            capacity, reference._decimal_multiply(cp[index], initial_q[index])
        )
    phase = 2 if over_ice else 1
    delta_cp = reference._decimal_subtract(cp[0], cp[phase])
    latent = reference._decimal_add(
        reference._decimal_subtract(h0[0], h0[phase]),
        reference._decimal_multiply(
            delta_cp,
            reference._decimal_subtract(initial_t, point(reference.THERMO_T0)),
        ),
    )
    return p, initial_t, initial_q, rh, capacity, latent, delta_cp


def _decimal_enthalpy(
    temperature: reference._DecimalInterval,
    species: list[reference._DecimalInterval],
) -> reference._DecimalInterval:
    point = lambda value: reference._decimal_interval(reference._decimal_float(value))
    capacity = point(reference.THERMO_CP_DRY)
    enthalpy = point(0.0)
    for index, value in enumerate(species):
        capacity = reference._decimal_add(
            capacity,
            reference._decimal_multiply(point(reference.THERMO_SPECIES_CP[index]), value),
        )
        enthalpy = reference._decimal_add(
            enthalpy,
            reference._decimal_multiply(point(reference.THERMO_SPECIES_H0[index]), value),
        )
    sensible = reference._decimal_multiply(
        capacity,
        reference._decimal_subtract(temperature, point(reference.THERMO_T0)),
    )
    return reference._decimal_add(sensible, enthalpy)


def certify_actual_saturation_output(
    pressure: float,
    temperature: float,
    species: np.ndarray,
    target_rh: float,
    stored_temperature: float,
    stored_species: np.ndarray,
    *,
    over_ice: bool = False,
) -> ActualThermoCertificate:
    """Diagnose one stored output against the directed ideal certificate.

    ``temperature`` and ``species`` are the exact float64 kernel inputs.
    Stored values must be exact float32 values promoted to float64.  For an
    exhausted reservoir, the endpoint is certified separately and no claim is
    made that a zero of the unconstrained residual exists.
    """
    input_temperature = _scalar(temperature, "temperature")
    input_species = np.asarray(species)
    if np.ma.isMaskedArray(species) and np.any(np.ma.getmaskarray(species)):
        raise ValueError("species contains masked values")
    if input_species.shape != (6,):
        raise ValueError("species must have six values")
    input_species = np.asarray(input_species, dtype=np.float64)
    if not np.all(np.isfinite(input_species)):
        raise ValueError("species must be finite")

    actual_temperature = _stored_scalar(stored_temperature, "stored temperature")
    actual_species = _stored_species(stored_species)
    maximum_temperature = reference.THERMO_T0 if over_ice else reference.MAX_TEMPERATURE_K
    if not reference.MIN_TEMPERATURE_K <= actual_temperature <= maximum_temperature:
        raise ValueError("stored temperature outside canonical range")
    if np.any(actual_species < 0.0) or np.any(actual_species > reference.MAX_FLOAT32):
        raise ValueError("stored species outside canonical range")
    if actual_species[0] > float(np.float32(reference.MAX_VAPOR_MIXING_RATIO)):
        raise ValueError("stored vapor outside canonical range")
    ideal = reference.saturation_equilibrium_certificate_reference(
        pressure, input_temperature, input_species, target_rh, over_ice=over_ice,
    )
    temperature_error_bound = np.nextafter(max(
        abs(actual_temperature - ideal.temperature_bounds[0]),
        abs(actual_temperature - ideal.temperature_bounds[1]),
    ), np.inf)
    species_error_bounds = np.nextafter(np.maximum(
        np.abs(actual_species - ideal.species_bounds[0]),
        np.abs(actual_species - ideal.species_bounds[1]),
    ), np.inf)
    storage_temperature_contained = (
        ideal.stored_temperature_bounds[0]
        <= actual_temperature
        <= ideal.stored_temperature_bounds[1]
    )
    storage_species_contained = bool(
        np.all(actual_species >= ideal.stored_species_bounds[0])
        and np.all(actual_species <= ideal.stored_species_bounds[1])
    )

    phase = 2 if over_ice else 1
    with localcontext() as context:
        context.prec = reference._DECIMAL_PRECISION
        p, initial_t, initial_q, rh, capacity, latent, delta_cp = (
            _decimal_state_intervals(
                pressure, input_temperature, input_species, target_rh,
                over_ice=over_ice,
            )
        )
        actual_q = [reference._decimal_interval(reference._decimal_float(value)) for value in actual_species]
        transfer_interval = reference._decimal_subtract(actual_q[0], initial_q[0])
        transfer_at_temperature = lambda bound: reference._decimal_divide(
            reference._decimal_multiply(
                reference._decimal_subtract(initial_t, reference._decimal_interval(
                    reference._decimal_float(bound)
                )),
                capacity,
            ),
            reference._decimal_subtract(
                latent,
                reference._decimal_multiply(
                    reference._decimal_subtract(initial_t, reference._decimal_interval(
                        reference._decimal_float(bound)
                    )),
                    delta_cp,
                ),
            ),
        )
        physical_lower = max(
            initial_q[0].upper.copy_negate(),
            transfer_at_temperature(maximum_temperature).upper,
        )
        physical_upper = min(
            initial_q[phase].lower,
            reference._decimal_subtract(
                reference._decimal_interval(reference._decimal_float(float(np.float32(0.2)))),
                initial_q[0],
            ).lower,
            transfer_at_temperature(reference.MIN_TEMPERATURE_K).lower,
        )
        transfer_in_physical_bounds = (
            physical_lower <= transfer_interval.lower
            and transfer_interval.upper <= physical_upper
        )
        transfer_physical_bounds = reference._outward_float_interval(physical_lower, physical_upper)
        residual_interval = None
        residual_magnitude_bound = None
        transfer_error_bound = None
        transfer_root_bounds = None
        if transfer_in_physical_bounds:
            residual_lower_at_lo, residual_upper_at_lo, _ = reference._decimal_transfer_residual(
                p, initial_t, initial_q[0], rh, transfer_interval.lower,
                capacity, latent, delta_cp, over_ice,
            )
            residual_lower_at_hi, residual_upper_at_hi, _ = reference._decimal_transfer_residual(
                p, initial_t, initial_q[0], rh, transfer_interval.upper,
                capacity, latent, delta_cp, over_ice,
            )
            # F is increasing on the physical transfer interval, so endpoint
            # evaluation encloses F for the subtraction interval.
            residual_lower = min(residual_lower_at_lo, residual_lower_at_hi)
            residual_upper = max(residual_upper_at_lo, residual_upper_at_hi)
            residual_interval = reference._outward_float_interval(
                residual_lower, residual_upper,
            )
            residual_magnitude_bound = np.nextafter(
                max(abs(residual_interval[0]), abs(residual_interval[1])), np.inf
            )
        if ideal.exhausted or not transfer_in_physical_bounds:
            transfer_error_bound = None
            transfer_root_bounds = None
        else:
            lower = reference._decimal_subtract(
                transfer_interval,
                reference._decimal_interval(max(Decimal(0), residual_upper)),
            ).lower
            upper = reference._decimal_subtract(
                transfer_interval,
                reference._decimal_interval(min(Decimal(0), residual_lower)),
            ).upper
            lower = max(lower, physical_lower)
            upper = min(upper, physical_upper)
            if lower <= upper:
                transfer_root_bounds = reference._outward_float_interval(lower, upper)
                transfer_error_bound = residual_magnitude_bound
            else:
                transfer_root_bounds = None
                transfer_error_bound = None

        actual_t = reference._decimal_interval(reference._decimal_float(actual_temperature))
        phase_closure = reference._decimal_add(
            reference._decimal_subtract(actual_q[phase], initial_q[phase]),
            transfer_interval,
        )
        actual_enthalpy = _decimal_enthalpy(actual_t, actual_q)
        initial_enthalpy = _decimal_enthalpy(initial_t, initial_q)
        enthalpy_closure = reference._decimal_subtract(actual_enthalpy, initial_enthalpy)
        phase_closure_interval = reference._outward_float_interval(phase_closure.lower, phase_closure.upper)
        enthalpy_closure_interval = reference._outward_float_interval(enthalpy_closure.lower, enthalpy_closure.upper)

    return ActualThermoCertificate(
        ideal=ideal,
        actual_temperature=actual_temperature,
        actual_species=actual_species,
        temperature_error_bound=float(temperature_error_bound),
        species_error_bounds=np.asarray(species_error_bounds, dtype=np.float64),
        storage_temperature_contained=storage_temperature_contained,
        storage_species_contained=storage_species_contained,
        vapor_transfer_bounds=reference._outward_float_interval(
            transfer_interval.lower, transfer_interval.upper,
        ),
        residual_magnitude_bound=(
            None if residual_magnitude_bound is None
            else float(residual_magnitude_bound)
        ),
        transfer_error_bound=(
            None if transfer_error_bound is None else float(transfer_error_bound)
        ),
        transfer_physical_bounds=transfer_physical_bounds,
        transfer_in_physical_bounds=transfer_in_physical_bounds,
        transfer_root_bounds=transfer_root_bounds,
        residual_interval=residual_interval,
        phase_closure_interval=phase_closure_interval,
        enthalpy_closure_interval=enthalpy_closure_interval,
    )


__all__ = ["ActualThermoCertificate", "certify_actual_saturation_output"]
