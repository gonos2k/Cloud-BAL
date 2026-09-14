#!/usr/bin/env python3
"""Tests for the independent NumPy pressure-column remap oracle."""

from pathlib import Path
import sys
from fractions import Fraction

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pressure_transition_reference as reference  # noqa: E402
from pressure_transition_reference import (  # noqa: E402
    THERMO_CP_DRY,
    THERMO_SPECIES_CP,
    THERMO_SPECIES_H0,
    THERMO_T0,
    _check_conservation,
    dry_mass_from_pressure_width_reference,
    reconstruct_thermo_state_reference,
    remap_pressure_column_bounds_reference,
    remap_pressure_column_intervals_reference,
    remap_pressure_column_reference,
    remap_surface_pressure_reference,
    saturation_adjust_reference,
    saturation_equilibrium_certificate_reference,
    validate_transition_seed_mass_reference,
)


def mixture_enthalpy(temperature: np.ndarray, species: np.ndarray) -> np.ndarray:
    capacity = THERMO_CP_DRY + THERMO_SPECIES_CP @ species
    return capacity * (temperature - THERMO_T0) + THERMO_SPECIES_H0 @ species


def saturation_mixing_ratio(
    pressure: float, temperature: float, *, over_ice: bool = False
) -> float:
    """Independent copy of the canonical saturation curve used by the fixture."""
    tc = temperature - THERMO_T0
    if over_ice:
        vapor_pressure = 611.15 * np.exp(22.452 * tc / (temperature - 0.55))
    else:
        vapor_pressure = 611.20 * np.exp(17.67 * tc / (tc + 243.5))
    vapor_pressure = min(0.99 * pressure, max(0.0, float(vapor_pressure)))
    return float(0.622 * vapor_pressure / (pressure - vapor_pressure))


def temperature_for_final_state(
    target_temperature: float,
    initial_species: np.ndarray,
    final_species: np.ndarray,
) -> float:
    """Construct an initial T with the same mixture enthalpy as a final state."""
    final_enthalpy = float(mixture_enthalpy(target_temperature, final_species))
    initial_capacity = THERMO_CP_DRY + THERMO_SPECIES_CP @ initial_species
    return float(
        THERMO_T0
        + (final_enthalpy - THERMO_SPECIES_H0 @ initial_species) / initial_capacity
    )


def assert_thermo_conservation(
    initial_temperature: float,
    initial_species: np.ndarray,
    final_temperature: float,
    final_species: np.ndarray,
) -> None:
    np.testing.assert_allclose(
        final_species.sum(), initial_species.sum(), rtol=0.0, atol=2.0e-14
    )
    np.testing.assert_allclose(
        mixture_enthalpy(final_temperature, final_species),
        mixture_enthalpy(initial_temperature, initial_species),
        rtol=0.0,
        atol=1.0e-7,
    )


def expect_value_error(callable_, label: str) -> None:
    try:
        callable_()
    except ValueError:
        return
    raise AssertionError(f"accepted invalid saturation input: {label}")


def hand_boundary_transition(
    old_mass: np.ndarray,
    old_temperature: np.ndarray,
    old_species: np.ndarray,
    boundary_mass: float,
    boundary_temperature: float,
    boundary_species: np.ndarray,
    donor_fractions: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Hand extensive-moment calculation for the compact boundary fixtures."""
    donor_mass = np.concatenate(([boundary_mass], old_mass))
    donor_temperature = np.concatenate(([boundary_temperature], old_temperature))
    donor_species = np.column_stack((boundary_species, old_species))
    mass = donor_fractions @ donor_mass
    species_mass = donor_fractions @ (donor_mass[:, None] * donor_species.T)
    result_species = (species_mass / mass[:, None]).T
    donor_capacity = THERMO_CP_DRY + THERMO_SPECIES_CP @ donor_species
    temperature_moment = donor_fractions @ (donor_mass * donor_capacity * donor_temperature)
    mixture_capacity = THERMO_CP_DRY * mass + species_mass @ THERMO_SPECIES_CP
    result_temperature = temperature_moment / mixture_capacity
    return mass, result_temperature, result_species


def _read_fixture(path: Path) -> dict[str, np.ndarray]:
    lines = [line.strip() for line in path.read_text().splitlines()]
    if not lines or lines[0] != "PRESSURE_TRANSITION_REMAP_FIXTURE_V1":
        raise AssertionError(f"invalid remap fixture header: {path}")
    cursor = 1

    def read_vector(label: str) -> np.ndarray:
        nonlocal cursor
        parts = lines[cursor].split()
        cursor += 1
        if len(parts) != 2 or parts[0] != label:
            raise AssertionError(f"expected {label} section")
        count = int(parts[1])
        if count < 1 or cursor + count > len(lines):
            raise AssertionError(f"invalid {label} count")
        values = np.asarray([float(lines[cursor + i]) for i in range(count)], dtype=np.float64)
        cursor += count
        return values

    def read_matrix(label: str) -> np.ndarray:
        nonlocal cursor
        parts = lines[cursor].split()
        cursor += 1
        if len(parts) != 3 or parts[0] != label:
            raise AssertionError(f"expected {label} section")
        rows, columns = (int(parts[1]), int(parts[2]))
        if rows < 1 or columns < 1 or cursor + rows * columns > len(lines):
            raise AssertionError(f"invalid {label} shape")
        values = np.asarray(
            [float(lines[cursor + i]) for i in range(rows * columns)],
            dtype=np.float64,
        ).reshape(rows, columns)
        cursor += rows * columns
        return values

    fixture = {
        "old_interfaces": read_vector("OLD_INTERFACES"),
        "old_mass": read_vector("OLD_DRY_MASS"),
        "old_temperature": read_vector("OLD_TEMPERATURE"),
        "old_species": read_matrix("OLD_SPECIES"),
        "new_interfaces": read_vector("NEW_INTERFACES"),
        "result_mass": read_vector("RESULT_DRY_MASS"),
        "result_temperature": read_vector("RESULT_TEMPERATURE"),
        "result_species": read_matrix("RESULT_SPECIES"),
    }
    if cursor >= len(lines) or lines[cursor] != "END" or cursor + 1 != len(lines):
        raise AssertionError("remap fixture has trailing or missing data")
    return fixture


def check_fortran_fixture(path: Path) -> None:
    fixture = _read_fixture(path)
    expected_mass, expected_temperature, expected_species = remap_pressure_column_reference(
        fixture["old_interfaces"],
        fixture["old_mass"],
        fixture["old_temperature"],
        fixture["old_species"],
        fixture["new_interfaces"],
    )
    np.testing.assert_allclose(
        fixture["result_mass"], expected_mass, rtol=2.0e-13, atol=2.0e-12,
        err_msg="Fortran remap dry mass differs from independent reference",
    )
    np.testing.assert_allclose(
        fixture["result_temperature"], expected_temperature, rtol=2.0e-13, atol=2.0e-11,
        err_msg="Fortran remap temperature differs from independent reference",
    )
    np.testing.assert_allclose(
        fixture["result_species"], expected_species, rtol=2.0e-13, atol=2.0e-14,
        err_msg="Fortran remap species differs from independent reference",
    )
    bounds = remap_pressure_column_bounds_reference(
        fixture["old_interfaces"], fixture["old_mass"], fixture["old_temperature"],
        fixture["old_species"], fixture["new_interfaces"],
    )
    (mass_lower, mass_upper), (temperature_lower, temperature_upper), (
        species_lower, species_upper,
    ) = bounds
    assert np.all((mass_lower <= fixture["result_mass"]) &
                  (fixture["result_mass"] <= mass_upper))
    assert np.all((temperature_lower <= fixture["result_temperature"]) &
                  (fixture["result_temperature"] <= temperature_upper))
    assert np.all((species_lower <= fixture["result_species"]) &
                  (fixture["result_species"] <= species_upper))


def test_remap_bounds_enclose_hand_calculated_extremes() -> None:
    old_interfaces = np.array([100.0, 80.0, 60.0])
    old_mass = np.array([2.0, 4.0])
    old_temperature = np.array([250.0, 300.0])
    old_species = np.array(
        [[.02, .04], [.01, .02], [.001, .003], [.002, .004], [.001, .002], [.003, .005]],
        dtype=np.float64,
    )
    new_interfaces = np.array([100.0, 90.0, 75.0, 60.0])
    bounds = remap_pressure_column_bounds_reference(
        old_interfaces, old_mass, old_temperature, old_species, new_interfaces,
        dry_mass_error=np.array([.1, .2]),
        temperature_error=np.array([1.0, 2.0]),
        species_error=np.full((6, 2), .001),
    )
    (mass_lower, mass_upper), (temperature_lower, temperature_upper), (
        species_lower, species_upper,
    ) = bounds
    # The first destination is exactly half of donor 0: its mass extrema are
    # 0.5*(2 +/- 0.1), widened only by arithmetic enclosure.
    assert mass_lower[0] < .95 < mass_upper[0]
    assert mass_lower[0] < .5 * (2.0 - .1)
    assert mass_upper[0] > .5 * (2.0 + .1)
    nominal = remap_pressure_column_reference(
        old_interfaces, old_mass, old_temperature, old_species, new_interfaces,
    )
    assert np.all(nominal[0] >= mass_lower)
    assert np.all(nominal[0] <= mass_upper)
    assert np.all(nominal[1] >= temperature_lower)
    assert np.all(nominal[1] <= temperature_upper)
    assert np.all(nominal[2] >= species_lower)
    assert np.all(nominal[2] <= species_upper)

    perturbed = remap_pressure_column_reference(
        old_interfaces,
        old_mass + np.array([.1, -.2]),
        old_temperature + np.array([1.0, -2.0]),
        old_species + .001,
        new_interfaces,
    )
    assert np.all(perturbed[0] >= mass_lower)
    assert np.all(perturbed[0] <= mass_upper)
    assert np.all(perturbed[1] >= temperature_lower)
    assert np.all(perturbed[1] <= temperature_upper)
    assert np.all(perturbed[2] >= species_lower)
    assert np.all(perturbed[2] <= species_upper)


def test_remap_bounds_zero_uncertainty_is_arithmetic_only_and_tightens() -> None:
    interfaces = np.array([100000.0, 92000.0, 84000.0])
    mass = np.array([2.0, 3.0])
    temperature = np.array([260.0, 280.0])
    species = np.full((6, 2), .001)
    exact = remap_pressure_column_bounds_reference(
        interfaces, mass, temperature, species,
        np.array([100000.0, 96000.0, 88000.0, 84000.0]),
    )
    uncertain = remap_pressure_column_bounds_reference(
        interfaces, mass, temperature, species,
        np.array([100000.0, 96000.0, 88000.0, 84000.0]),
        dry_mass_error=np.full(2, .01),
        temperature_error=np.full(2, .5),
        species_error=np.full((6, 2), 1.0e-4),
    )
    for exact_interval, uncertain_interval in zip(exact, uncertain):
        exact_lower, exact_upper = exact_interval
        uncertain_lower, uncertain_upper = uncertain_interval
        assert np.all(exact_upper >= exact_lower)
        assert np.all(uncertain_lower <= exact_lower)
        assert np.all(uncertain_upper >= exact_upper)
        assert np.all((uncertain_upper - uncertain_lower) >=
                      (exact_upper - exact_lower))
    nominal = remap_pressure_column_reference(
        interfaces, mass, temperature, species,
        np.array([100000.0, 96000.0, 88000.0, 84000.0]),
    )
    assert np.all(exact[0][0] <= nominal[0]) and np.all(nominal[0] <= exact[0][1])


def test_remap_bounds_reject_malformed_or_unbounded_uncertainty() -> None:
    interfaces = np.array([100.0, 80.0, 60.0])
    mass = np.array([2.0, 3.0])
    temperature = np.array([250.0, 300.0])
    species = np.zeros((6, 2))
    destination = np.array([100.0, 90.0, 60.0])
    cases = (
        {"dry_mass_error": np.array([-1.0, 0.0])},
        {"temperature_error": np.array([np.inf, 0.0])},
        {"species_error": np.zeros((5, 2))},
        {"dry_mass_error": np.array([2.0, 0.0])},
        {"species_error": np.full((6, 2), .3)},
        {"species_error": np.array([[0.0, 0.0], [.01, 0.0],
                                    [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]])},
        {"dry_mass_error": np.ma.array([0.0, 0.0], mask=[True, False])},
    )
    for kwargs in cases:
        expect_value_error(
            lambda kwargs=kwargs: remap_pressure_column_bounds_reference(
                interfaces, mass, temperature, species, destination, **kwargs
            ),
            "invalid remap uncertainty",
        )


def test_asymmetric_remap_intervals_enclose_condensate_creation() -> None:
    interfaces = np.array([100.0, 80.0, 60.0])
    destination = np.array([100.0, 90.0, 60.0])
    mass = np.array([2.0, 3.0])
    temperature = np.array([250.0, 300.0])
    lower = np.zeros((6, 2))
    upper = lower.copy()
    upper[1] = [0.001, 0.002]
    bounds = remap_pressure_column_intervals_reference(
        interfaces, (mass, mass), (temperature, temperature),
        (lower, upper), destination,
    )
    for first in (0.0, 0.001):
        for second in (0.0, 0.002):
            species = lower.copy()
            species[1] = [first, second]
            actual = remap_pressure_column_reference(
                interfaces, mass, temperature, species, destination,
            )
            for value, (lo, hi) in zip(actual, bounds):
                assert np.all(lo <= value) and np.all(value <= hi)
    # The second destination receives half the first donor and all the second.
    exact_upper = (Fraction.from_float(0.001) + 3 * Fraction.from_float(0.002)) / 4
    assert Fraction.from_float(bounds[2][0][1, 1]) <= 0
    assert Fraction.from_float(bounds[2][1][1, 1]) >= exact_upper


def test_thermo_storage_intervals_feed_pressure_remap() -> None:
    initial = [np.array([0.001, 1e-8, 0.0, 0.0, 0.0, 0.0]),
               np.array([0.015, 0.001, 0.0, 0.0, 0.0, 0.0])]
    certificates = [saturation_equilibrium_certificate_reference(
        pressure, temperature, species, 1.0,
    ) for pressure, temperature, species in zip([95000., 75000.], [280., 280.], initial)]
    assert certificates[0].exhausted
    t_bounds = tuple(np.array([c.stored_temperature_bounds[i] for c in certificates])
                     for i in (0, 1))
    q_bounds = tuple(np.column_stack([c.stored_species_bounds[i] for c in certificates])
                     for i in (0, 1))
    interfaces = np.array([100000., 85000., 65000.])
    destination = np.array([100000., 90000., 65000.])
    mass = np.array([2., 3.])
    bounds = remap_pressure_column_intervals_reference(
        interfaces, (mass, mass), t_bounds, q_bounds, destination,
    )
    stored_t = np.array([c.equilibrium_temperature for c in certificates], dtype=np.float32)
    stored_q = np.column_stack([c.equilibrium_species for c in certificates]).astype(np.float32)
    actual = remap_pressure_column_reference(interfaces, mass, stored_t, stored_q, destination)
    for value, (lower, upper) in zip(actual, bounds):
        assert np.all(lower <= value) and np.all(value <= upper)


def test_explicit_remap_intervals_reject_invalid_endpoints() -> None:
    interfaces = np.array([100.0, 80.0])
    mass = np.array([2.0])
    temperature = np.array([280.0])
    species = np.zeros((6, 1))
    cases = (
        ((mass, mass / 2), (temperature, temperature), (species, species)),
        ((mass, mass), (temperature, temperature - 1), (species, species)),
        ((mass, mass), (temperature, temperature), (species - 0.001, species)),
        ((mass, mass), (temperature, temperature), (species, np.zeros((5, 1)))),
        ((mass, mass), (temperature, temperature), (np.ma.array(species), species)),
    )
    for mb, tb, qb in cases:
        expect_value_error(
            lambda mb=mb, tb=tb, qb=qb: remap_pressure_column_intervals_reference(
                interfaces, mb, tb, qb, interfaces,
            ), 'invalid explicit donor interval',
        )


def test_remap_bounds_endpoint_rounding_is_outward() -> None:
    interfaces = np.array([100.0, 80.0])
    mass = np.array([1.1])
    temperature = np.array([250.3])
    species = np.full((6, 1), .1)
    destination = interfaces.copy()
    mass_error = np.array([.1])
    temperature_error = np.array([.1])
    species_error = np.full((6, 1), .05)
    (mass_lower, mass_upper), (temperature_lower, temperature_upper), (
        species_lower, species_upper,
    ) = remap_pressure_column_bounds_reference(
        interfaces, mass, temperature, species, destination,
        dry_mass_error=mass_error,
        temperature_error=temperature_error,
        species_error=species_error,
    )
    exact_mass_lower = Fraction.from_float(1.1) - Fraction.from_float(.1)
    exact_mass_upper = Fraction.from_float(1.1) + Fraction.from_float(.1)
    exact_temperature_lower = Fraction.from_float(250.3) - Fraction.from_float(.1)
    exact_temperature_upper = Fraction.from_float(250.3) + Fraction.from_float(.1)
    assert Fraction.from_float(float(mass_lower[0])) <= exact_mass_lower
    assert Fraction.from_float(float(mass_upper[0])) >= exact_mass_upper
    assert Fraction.from_float(float(temperature_lower[0])) <= exact_temperature_lower
    assert Fraction.from_float(float(temperature_upper[0])) >= exact_temperature_upper
    exact_q_lower = (
        (Fraction.from_float(.1) - Fraction.from_float(.05))
        * exact_mass_lower / exact_mass_upper
    )
    exact_q_upper = (
        (Fraction.from_float(.1) + Fraction.from_float(.05))
        * exact_mass_upper / exact_mass_lower
    )
    assert Fraction.from_float(float(species_lower[0, 0])) <= exact_q_lower
    assert Fraction.from_float(float(species_upper[0, 0])) >= exact_q_upper


def test_identity_is_bitwise_exact() -> None:
    old_interfaces = np.array([100000.0, 93000.0, 87000.0, 80000.0])
    old_mass = np.array([2.0, 3.0, 4.0])
    old_temperature = np.array([260.0, 275.0, 290.0])
    old_species = np.array(
        [[.02, .01, .03], [.003, .004, .002], [.001, .002, .001],
         [.001, .001, .002], [.001, .001, .001], [.001, .002, .001]],
        dtype=np.float64,
    )
    new_mass, new_temperature, new_species = remap_pressure_column_reference(
        old_interfaces, old_mass, old_temperature, old_species, old_interfaces
    )
    np.testing.assert_array_equal(new_mass, old_mass)
    np.testing.assert_array_equal(new_temperature, old_temperature)
    np.testing.assert_array_equal(new_species, old_species)


def test_split_merge_conserves_dry_species_and_mixture_enthalpy() -> None:
    old_interfaces = np.array([100000.0, 92000.0, 84000.0, 78000.0])
    old_mass = np.array([2.0, 5.0, 3.0])
    old_temperature = np.array([255.0, 320.0, 280.0])
    old_species = np.array(
        [[.020, .010, .030], [.003, .004, .002], [.001, .002, .001],
         [.001, .001, .002], [.001, .001, .001], [.001, .002, .001]],
        dtype=np.float64,
    )
    new_interfaces = np.array([100000.0, 96000.0, 88000.0, 82000.0, 78000.0])
    new_mass, new_temperature, new_species = remap_pressure_column_reference(
        old_interfaces, old_mass, old_temperature, old_species, new_interfaces
    )

    expected_mass = np.array([1.0, 3.5, 3.5, 2.0])
    expected_temperature = np.array(
        [255.0, 301.30233183, 308.35228067, 280.0]
    )
    expected_species = np.array(
        [[.02000000, .0128571428571429, .0157142857142857, .03000000],
         [.00300000, .0037142857142857, .0034285714285714, .00200000],
         [.00100000, .0017142857142857, .0017142857142857, .00100000],
         [.00100000, .0010000000000000, .0012857142857143, .00200000],
         [.00100000, .0010000000000000, .0010000000000000, .00100000],
         [.00100000, .0017142857142857, .0017142857142857, .00100000]],
        dtype=np.float64,
    )
    np.testing.assert_allclose(new_mass, expected_mass, rtol=0.0, atol=1.0e-14)
    np.testing.assert_allclose(new_temperature, expected_temperature, rtol=0.0, atol=1.0e-8)
    np.testing.assert_allclose(new_species, expected_species, rtol=0.0, atol=1.0e-14)
    np.testing.assert_allclose(new_mass.sum(), old_mass.sum(), rtol=0.0, atol=1.0e-13)
    np.testing.assert_allclose(
        new_mass @ new_species.T,
        old_mass @ old_species.T,
        rtol=0.0,
        atol=1.0e-13,
    )
    np.testing.assert_allclose(
        new_mass @ mixture_enthalpy(new_temperature, new_species),
        old_mass @ mixture_enthalpy(old_temperature, old_species),
        rtol=0.0,
        atol=1.0e-8,
    )
    naive_temperature = (old_mass[0] * old_temperature[0] + old_mass[1] * old_temperature[1]) / (
        old_mass[0] + old_mass[1]
    )
    assert abs(new_temperature[1] - naive_temperature) > 1.0e-3


def test_asymmetric_center_split_preserves_untouched_upper_donor() -> None:
    old_interfaces = np.array([99999.125, 92500.0, 87500.0])
    old_mass = np.array([7.0, 4.0])
    old_temperature = np.array([281.0, 294.0])
    old_species = np.array(
        [[.018, .006], [.004, .003], [.002, .003], [.001, .002], [.001, .001], [.001, .002]],
        dtype=np.float64,
    )
    new_interfaces = np.array([99999.125, 97500.0, 92500.0, 87500.0])
    new_mass, new_temperature, new_species = remap_pressure_column_reference(
        old_interfaces, old_mass, old_temperature, old_species, new_interfaces
    )
    np.testing.assert_allclose(
        new_mass[0], old_mass[0] * 2499.125 / 7499.125, rtol=0.0, atol=1.0e-13
    )
    np.testing.assert_array_equal(new_mass[2:], old_mass[1:])
    np.testing.assert_array_equal(new_temperature[2:], old_temperature[1:])
    np.testing.assert_array_equal(new_species[:, 2:], old_species[:, 1:])


def test_stored_dry_mass_is_not_reconstructed_from_pressure_width() -> None:
    old_interfaces = np.array([100000.0, 92000.0, 84000.0])
    species_reference = np.array(
        [[.01327193, .01327193], [.00234117, .00234117], [.00071329, .00071329],
         [.00121731, .00121731], [.00038127, .00038127], [.00062919, .00062919]],
        dtype=np.float64,
    )
    stored_species = np.asarray(species_reference, dtype=np.float32).astype(np.float64)
    area = 173456.75
    gravity = 9.80665
    pressure_mass = area * (old_interfaces[:-1] - old_interfaces[1:]) / gravity
    # The retained dry mass came from the unrounded source mixture.  The
    # oracle must preserve that supplied value instead of recomputing it from
    # the subsequently stored float32 species.
    stored_dry_mass = pressure_mass / (1.0 + species_reference.sum(axis=0))
    new_interfaces = np.array([100000.0, 96000.0, 88000.0, 84000.0])
    new_mass, _, new_species = remap_pressure_column_reference(
        old_interfaces,
        stored_dry_mass,
        np.array([255.1234567, 320.7654321]),
        stored_species,
        new_interfaces,
    )
    overlap_fraction = np.array([[.5, .5, 0.0], [0.0, .5, .5]])
    expected_mass = overlap_fraction.T @ stored_dry_mass
    np.testing.assert_allclose(new_mass, expected_mass, rtol=0.0, atol=1.0e-12)
    # The oracle preserves the supplied stored masses; it does not silently
    # replace them with a fresh A*dp/g reconstruction.
    geometric_pressure_mass = area * (new_interfaces[:-1] - new_interfaces[1:]) / gravity
    geometric_mass = geometric_pressure_mass / (1.0 + new_species.sum(axis=0))
    assert np.any(
        np.abs(new_mass * (1.0 + new_species.sum(axis=0)) - geometric_mass) > 1.0e-9
    )


def test_conservation_gate_rejects_independent_output_perturbations() -> None:
    old_interfaces = np.array([100000.0, 92000.0, 84000.0, 78000.0])
    old_mass = np.array([2.0, 5.0, 3.0])
    old_temperature = np.array([255.0, 320.0, 280.0])
    old_species = np.array(
        [[.020, .010, .030], [.003, .004, .002], [.001, .002, .001],
         [.001, .001, .002], [.001, .001, .001], [.001, .002, .001]],
        dtype=np.float64,
    )
    new_interfaces = np.array([100000.0, 96000.0, 88000.0, 82000.0, 78000.0])
    new_mass, new_temperature, new_species = remap_pressure_column_reference(
        old_interfaces, old_mass, old_temperature, old_species, new_interfaces
    )

    perturbed_mass = new_mass.copy()
    perturbed_mass[1] += 1.0e-8
    try:
        _check_conservation(
            old_mass, old_temperature, old_species,
            perturbed_mass, new_temperature, new_species,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("accepted an independent dry-mass perturbation")

    perturbed_species = new_species.copy()
    perturbed_species[0, 1] += 1.0e-8
    try:
        _check_conservation(
            old_mass, old_temperature, old_species,
            new_mass, new_temperature, perturbed_species,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("accepted a tiny high-enthalpy species perturbation")


def test_isothermal_dry_remap_preserves_temperature() -> None:
    old_interfaces = np.array([100050.0, 100000.0, 95000.0, 90000.0])
    old_mass = np.array([1.3, 5.5, 3.25])
    old_temperature = np.full(3, THERMO_T0)
    old_species = np.zeros((6, 3), dtype=np.float64)
    new_interfaces = np.array([100050.0, 98000.0, 93000.0, 90000.0])
    new_mass, new_temperature, new_species = remap_pressure_column_reference(
        old_interfaces, old_mass, old_temperature, old_species, new_interfaces
    )
    np.testing.assert_allclose(
        new_temperature, np.full(new_temperature.size, THERMO_T0),
        rtol=0.0, atol=1.0e-12,
    )
    np.testing.assert_allclose(new_species, 0.0, rtol=0.0, atol=0.0)

    perturbed_temperature = new_temperature.copy()
    perturbed_temperature[1] += 1.0e-8
    try:
        _check_conservation(
            old_mass, old_temperature, old_species,
            new_mass, perturbed_temperature, new_species,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("accepted a meaningful isothermal energy perturbation")


def test_saturation_adjust_liquid_condensation_evaporation_and_exhaustion() -> None:
    pressure = 85000.0
    target_rh = 0.8
    target_temperature = 300.0
    target_vapor = target_rh * saturation_mixing_ratio(
        pressure, target_temperature
    )

    # Condensation: construct the initial state from a known final saturated
    # state so the expected root is independent of the implementation solver.
    initial = np.array(
        [target_vapor + 0.001, 0.0, 0.001, 0.01, 0.02, 0.03],
        dtype=np.float64,
    )
    expected = initial.copy()
    expected[0] = target_vapor
    expected[1] = 0.001
    initial_temperature = temperature_for_final_state(
        target_temperature, initial, expected
    )
    saved = initial.copy()
    result_temperature, result_species = saturation_adjust_reference(
        pressure, initial_temperature, initial, target_rh
    )
    assert isinstance(result_temperature, float)
    assert result_species.dtype == np.float64
    np.testing.assert_allclose(result_temperature, target_temperature, rtol=0.0, atol=2.0e-12)
    np.testing.assert_allclose(result_species, expected, rtol=0.0, atol=2.0e-12)
    np.testing.assert_array_equal(result_species[2:], initial[2:])
    np.testing.assert_array_equal(initial, saved)
    assert_thermo_conservation(
        initial_temperature, initial, result_temperature, result_species
    )

    # Evaporation is the reverse transfer and must cool the mixture while
    # preserving the unrelated ice and precipitation reservoirs bitwise.
    initial = np.array(
        [target_vapor - 0.001, 0.003, 0.001, 0.01, 0.02, 0.03],
        dtype=np.float64,
    )
    expected = initial.copy()
    expected[0] = target_vapor
    expected[1] = 0.002
    initial_temperature = temperature_for_final_state(
        target_temperature, initial, expected
    )
    saved = initial.copy()
    result_temperature, result_species = saturation_adjust_reference(
        pressure, initial_temperature, initial, target_rh
    )
    np.testing.assert_allclose(result_temperature, target_temperature, rtol=0.0, atol=2.0e-12)
    np.testing.assert_allclose(result_species, expected, rtol=0.0, atol=2.0e-12)
    np.testing.assert_array_equal(result_species[2:], initial[2:])
    np.testing.assert_array_equal(initial, saved)
    assert result_temperature < initial_temperature
    assert_thermo_conservation(
        initial_temperature, initial, result_temperature, result_species
    )

    # Exhaustion of the selected liquid reservoir is a valid endpoint even
    # though the remaining vapor is subsaturated; a vapor/temperature bound is
    # not allowed to masquerade as reservoir exhaustion.
    initial = np.array(
        [0.001, 1.0e-8, 0.001, 0.01, 0.02, 0.03], dtype=np.float64
    )
    initial_temperature = 280.0
    saved = initial.copy()
    result_temperature, result_species = saturation_adjust_reference(
        pressure, initial_temperature, initial, 1.0
    )
    assert result_species[1] == 0.0
    assert result_species[0] < saturation_mixing_ratio(
        pressure, result_temperature
    )
    assert result_temperature < initial_temperature
    np.testing.assert_array_equal(result_species[2:], initial[2:])
    np.testing.assert_array_equal(initial, saved)
    assert_thermo_conservation(
        initial_temperature, initial, result_temperature, result_species
    )


def test_saturation_adjust_ice_sublimation_and_deposition() -> None:
    pressure = 85000.0
    target_rh = 0.8
    target_temperature = 250.0
    target_vapor = target_rh * saturation_mixing_ratio(
        pressure, target_temperature, over_ice=True
    )

    # Deposition into an initially empty ice reservoir.
    initial = np.array(
        [target_vapor + 0.001, 0.0, 0.0, 0.01, 0.02, 0.03], dtype=np.float64
    )
    expected = initial.copy()
    expected[0] = target_vapor
    expected[2] = 0.001
    initial_temperature = temperature_for_final_state(
        target_temperature, initial, expected
    )
    saved = initial.copy()
    result_temperature, result_species = saturation_adjust_reference(
        pressure, initial_temperature, initial, target_rh, over_ice=True
    )
    assert result_temperature <= THERMO_T0
    np.testing.assert_allclose(result_temperature, target_temperature, rtol=0.0, atol=2.0e-12)
    np.testing.assert_allclose(result_species, expected, rtol=0.0, atol=2.0e-12)
    np.testing.assert_array_equal(result_species[[1, 3, 4, 5]], initial[[1, 3, 4, 5]])
    np.testing.assert_array_equal(initial, saved)
    assert_thermo_conservation(
        initial_temperature, initial, result_temperature, result_species
    )

    # Sublimation cools the mixture and consumes only the selected ice
    # reservoir; liquid and all precipitation stay exact.
    initial = np.array(
        [target_vapor - 0.0002, 0.0, 0.0012, 0.01, 0.02, 0.03], dtype=np.float64
    )
    expected = initial.copy()
    expected[0] = target_vapor
    expected[2] = 0.001
    initial_temperature = temperature_for_final_state(
        target_temperature, initial, expected
    )
    saved = initial.copy()
    result_temperature, result_species = saturation_adjust_reference(
        pressure, initial_temperature, initial, target_rh, over_ice=True
    )
    np.testing.assert_allclose(result_temperature, target_temperature, rtol=0.0, atol=2.0e-12)
    np.testing.assert_allclose(result_species, expected, rtol=0.0, atol=2.0e-12)
    np.testing.assert_array_equal(result_species[[1, 3, 4, 5]], initial[[1, 3, 4, 5]])
    np.testing.assert_array_equal(initial, saved)
    assert result_temperature < initial_temperature
    assert_thermo_conservation(
        initial_temperature, initial, result_temperature, result_species
    )


def test_saturation_adjust_ice_warming_is_rejected_atomically() -> None:
    pressure = 85000.0
    target_temperature = 275.0
    target_vapor = saturation_mixing_ratio(
        pressure, target_temperature, over_ice=True
    )
    initial = np.array(
        [target_vapor + 0.001, 0.0, 0.0, 0.01, 0.02, 0.03], dtype=np.float64
    )
    expected = initial.copy()
    expected[0] = target_vapor
    expected[2] = 0.001
    initial_temperature = temperature_for_final_state(
        target_temperature, initial, expected
    )
    assert 150.0 < initial_temperature < THERMO_T0
    saved = initial.copy()
    expect_value_error(
        lambda: saturation_adjust_reference(
            pressure, initial_temperature, initial, 1.0, over_ice=True
        ),
        "ice equilibrium requiring warming above freezing",
    )
    np.testing.assert_array_equal(initial, saved)

    # The phase selector itself also rejects an already-warm ice state.
    expect_value_error(
        lambda: saturation_adjust_reference(
            pressure, 280.0, saved, 0.8, over_ice=True
        ),
        "warm input on ice surface",
    )


def test_saturation_equilibrium_certificate_liquid_and_storage() -> None:
    pressure = 85000.0
    target_temperature = 300.0
    target_rh = 0.8
    target_vapor = target_rh * saturation_mixing_ratio(pressure, target_temperature)
    final_species = np.array(
        [target_vapor, 0.001, 0.001, 0.01, 0.02, 0.03], dtype=np.float64
    )
    initial_species = final_species.copy()
    initial_species[0] += 0.001
    initial_species[1] = 0.0
    initial_temperature = temperature_for_final_state(
        target_temperature, initial_species, final_species
    )
    certificate = saturation_equilibrium_certificate_reference(
        pressure, initial_temperature, initial_species, target_rh
    )
    assert not certificate.exhausted
    np.testing.assert_allclose(
        certificate.equilibrium_temperature, target_temperature, rtol=0.0, atol=2.0e-12
    )
    np.testing.assert_allclose(
        certificate.equilibrium_species, final_species, rtol=0.0, atol=2.0e-14
    )
    assert certificate.temperature_bounds[0] <= certificate.equilibrium_temperature <= certificate.temperature_bounds[1]
    assert np.all(certificate.species_bounds[0] <= certificate.equilibrium_species)
    assert np.all(certificate.equilibrium_species <= certificate.species_bounds[1])
    stored_temperature = float(np.float32(certificate.equilibrium_temperature))
    stored_species = certificate.equilibrium_species.astype(np.float32).astype(np.float64)
    assert certificate.stored_temperature_bounds[0] <= stored_temperature <= certificate.stored_temperature_bounds[1]
    assert np.all(certificate.stored_species_bounds[0] <= stored_species)
    assert np.all(stored_species <= certificate.stored_species_bounds[1])
    assert certificate.temperature_error > 0.0
    assert np.all(certificate.species_error >= 0.0)

    # At low pressure the raw saturation pressure exceeds 0.99*p.  The
    # interval qsat implementation must clamp both endpoints monotonically.
    capped = saturation_equilibrium_certificate_reference(
        100.0, 350.0, np.array([0.01, 0.1, 0.0, 0.0, 0.0, 0.0]), 0.8
    )
    assert 229.8 < capped.equilibrium_temperature < 229.9
    assert capped.temperature_bounds[0] <= capped.equilibrium_temperature <= capped.temperature_bounds[1]


def test_saturation_equilibrium_certificate_ice_boundary_and_exhaustion() -> None:
    pressure = 85000.0
    target_rh = 0.8
    target_temperature = THERMO_T0
    target_vapor = target_rh * saturation_mixing_ratio(
        pressure, target_temperature, over_ice=True
    )
    final_species = np.array(
        [target_vapor, 0.0, 0.001, 0.01, 0.02, 0.03], dtype=np.float64
    )
    initial_species = final_species.copy()
    initial_species[0] += 0.001
    initial_species[2] = 0.0
    initial_temperature = temperature_for_final_state(
        target_temperature, initial_species, final_species
    )
    boundary = saturation_equilibrium_certificate_reference(
        pressure, initial_temperature, initial_species, target_rh, over_ice=True
    )
    assert boundary.temperature_bounds[0] <= boundary.equilibrium_temperature <= boundary.temperature_bounds[1]
    np.testing.assert_allclose(
        boundary.equilibrium_temperature, THERMO_T0, rtol=0.0, atol=2.0e-12
    )
    assert np.all(boundary.species_bounds[0] <= boundary.equilibrium_species)
    assert np.all(boundary.equilibrium_species <= boundary.species_bounds[1])

    exhausted_species = np.array(
        [0.001, 1.0e-8, 0.001, 0.01, 0.02, 0.03], dtype=np.float64
    )
    exhausted = saturation_equilibrium_certificate_reference(
        pressure, 280.0, exhausted_species, 1.0
    )
    assert exhausted.exhausted
    assert exhausted.equilibrium_species[1] == 0.0
    assert exhausted.species_bounds[0][1] <= 0.0 <= exhausted.species_bounds[1][1]
    assert exhausted.temperature_bounds[0] <= exhausted.equilibrium_temperature <= exhausted.temperature_bounds[1]


def test_saturation_equilibrium_certificate_rejects_uncertified_cases() -> None:
    species = np.array([0.19, 0.1, 0.001, 0.0, 0.0, 0.0], dtype=np.float64)
    cases = (
        (np.nan, 300.0, species, 0.8, False),
        (85000.0, 280.0, np.zeros(5), 0.8, False),
        (85000.0, 280.0, species, 1.1, False),
        (85000.0, 280.0, species, 0.8, True),
        # The vapor cap is an invalid equilibrium endpoint; reservoir
        # exhaustion is the only permitted subsaturated endpoint.
        (1000.0, 350.0, species, 1.0, False),
    )
    for pressure, temperature, values, rh, over_ice in cases:
        expect_value_error(
            lambda pressure=pressure, temperature=temperature, values=values,
            rh=rh, over_ice=over_ice: saturation_equilibrium_certificate_reference(
                pressure, temperature, values, rh, over_ice=over_ice
            ),
            "uncertified thermo certificate input",
        )

    original_residual = reference._decimal_transfer_residual

    def ambiguous_residual(*args, **kwargs):
        lower, upper, trial_temperature = original_residual(*args, **kwargs)
        from decimal import Decimal
        return min(lower, Decimal("-1e-30")), max(upper, Decimal("1e-30")), trial_temperature

    reference._decimal_transfer_residual = ambiguous_residual
    try:
        expect_value_error(
            lambda: saturation_equilibrium_certificate_reference(
                85000.0, 280.0,
                np.array([0.011, 0.0, 0.001, 0.01, 0.02, 0.03]),
                0.8,
            ),
            "ambiguous endpoint residual sign",
        )
    finally:
        reference._decimal_transfer_residual = original_residual


def test_saturation_adjust_rejects_nonfinite_bad_shapes_and_invalid_rh() -> None:
    pressure = 85000.0
    temperature = 280.0
    species = np.array(
        [0.01, 0.001, 0.001, 0.01, 0.02, 0.03], dtype=np.float64
    )
    calls = (
        ("nonfinite pressure", lambda: saturation_adjust_reference(np.nan, temperature, species, 0.8)),
        ("infinite pressure", lambda: saturation_adjust_reference(np.inf, temperature, species, 0.8)),
        ("pressure below bound", lambda: saturation_adjust_reference(99.0, temperature, species, 0.8)),
        ("pressure above bound", lambda: saturation_adjust_reference(120001.0, temperature, species, 0.8)),
        ("nonfinite temperature", lambda: saturation_adjust_reference(pressure, np.nan, species, 0.8)),
        ("temperature below bound", lambda: saturation_adjust_reference(pressure, 149.0, species, 0.8)),
        ("temperature above bound", lambda: saturation_adjust_reference(pressure, 350.1, species, 0.8)),
        ("species too short", lambda: saturation_adjust_reference(pressure, temperature, np.zeros(5), 0.8)),
        ("species too long", lambda: saturation_adjust_reference(pressure, temperature, np.zeros(7), 0.8)),
        ("species matrix", lambda: saturation_adjust_reference(pressure, temperature, np.zeros((6, 1)), 0.8)),
        ("nonfinite species", lambda: saturation_adjust_reference(pressure, temperature, np.array([0.01, 0.001, np.nan, 0.01, 0.02, 0.03]), 0.8)),
        ("negative species", lambda: saturation_adjust_reference(pressure, temperature, np.array([0.01, -1.0e-3, 0.001, 0.01, 0.02, 0.03]), 0.8)),
        ("vapor above bound", lambda: saturation_adjust_reference(pressure, temperature, np.array([0.2000001, 0.001, 0.001, 0.01, 0.02, 0.03]), 0.8)),
        ("RH below bound", lambda: saturation_adjust_reference(pressure, temperature, species, -1.0e-12)),
        ("RH above bound", lambda: saturation_adjust_reference(pressure, temperature, species, 1.0 + 1.0e-12)),
        ("nonfinite RH", lambda: saturation_adjust_reference(pressure, temperature, species, np.nan)),
    )
    for label, call in calls:
        expect_value_error(call, label)


def test_saturation_then_float32_storage_remap_conserves_post_thermo_state() -> None:
    old_interfaces = np.array([100000.0, 93000.0, 86000.0, 80000.0])
    old_mass = np.array([2.0, 3.0, 4.0])
    layer_pressure = np.array([96500.0, 89500.0, 83000.0])
    old_temperature = np.array([300.0, 285.0, 260.0])
    old_species = np.array(
        [[.028, .010, .001], [.001, .002, .003], [.001, .002, .004],
         [.010, .020, .030], [.020, .030, .040], [.030, .040, .050]],
        dtype=np.float64,
    )

    thermo_temperature = []
    thermo_species = []
    for pressure, temperature, species in zip(
        layer_pressure, old_temperature, old_species.T
    ):
        result_temperature, result_species = saturation_adjust_reference(
            pressure, temperature, species, 0.9
        )
        thermo_temperature.append(result_temperature)
        thermo_species.append(result_species)
    thermo_temperature = np.asarray(thermo_temperature, dtype=np.float64)
    thermo_species = np.asarray(thermo_species, dtype=np.float64).T

    # This is the canonical float32 storage boundary: remap sees the actual float32
    # values, while the saturation oracle above deliberately returned float64.
    stored_temperature = thermo_temperature.astype(np.float32).astype(np.float64)
    stored_species = thermo_species.astype(np.float32).astype(np.float64)
    assert np.any(stored_temperature != thermo_temperature)
    assert np.any(stored_species != thermo_species)

    new_interfaces = np.array([100000.0, 96500.0, 90000.0, 86000.0, 80000.0])
    new_mass, new_temperature, new_species = remap_pressure_column_reference(
        old_interfaces,
        old_mass,
        stored_temperature,
        stored_species,
        new_interfaces,
    )
    np.testing.assert_allclose(
        new_mass.sum(), old_mass.sum(), rtol=0.0, atol=1.0e-13
    )
    np.testing.assert_allclose(
        new_mass @ new_species.T,
        old_mass @ stored_species.T,
        rtol=0.0,
        atol=1.0e-13,
    )
    np.testing.assert_allclose(
        new_mass @ mixture_enthalpy(new_temperature, new_species),
        old_mass @ mixture_enthalpy(stored_temperature, stored_species),
        rtol=0.0,
        atol=1.0e-7,
    )
    # The uppermost destination cell is an untouched donor and must retain all
    # six post-thermo stored species exactly.
    np.testing.assert_array_equal(new_species[:, -1], stored_species[:, -1])


def test_reconstruct_thermo_state_analytic_small_2x2() -> None:
    pressure = np.array([[85000.0, 90000.0], [70000.0, 100000.0]])
    pressure_mass = np.array([[1.25, 2.75], [4.5, 6.25]])
    temperature = np.array([[280.0, 0.0], [250.0, 0.0]])
    species = np.zeros((6, 2, 2), dtype=np.float64)
    species[:, 0, 0] = [
        0.0101234567, 0.0012345678, 0.0013456789,
        0.0101111111, 0.0202222222, 0.0303333333,
    ]
    species[:, 1, 0] = [0.00024574359736225404, 0.0, 0.0012, 0.01, 0.02, 0.03]
    # These unsupported columns include a below-ground temperature sentinel;
    # they must not be sent through the thermodynamic solver.
    species[:, 0, 1] = [
        0.0155555555, 0.0022222222, 0.0033333333,
        0.0111111111, 0.0222222222, 0.0333333333,
    ]
    species[:, 1, 1] = [
        0.0066666666, 0.0044444444, 0.0055555555,
        0.0122222222, 0.0244444444, 0.0366666666,
    ]
    support = np.array([[True, False], [True, False]], dtype=bool)
    surface = np.array([[1, 1], [2, 2]], dtype=np.int64)
    target_rh = 0.8
    saved = (pressure.copy(), pressure_mass.copy(), temperature.copy(), species.copy(),
             support.copy(), surface.copy())

    stored_temperature, stored_species, dry_mass = reconstruct_thermo_state_reference(
        pressure, pressure_mass, temperature, species, support, surface, target_rh
    )
    assert stored_temperature.dtype == np.float64
    assert stored_species.dtype == np.float64
    assert dry_mass.dtype == np.float64
    assert stored_temperature.shape == temperature.shape
    assert stored_species.shape == species.shape
    assert dry_mass.shape == pressure_mass.shape

    expected_temperature = temperature.copy()
    expected_species = species.copy()
    for i, j in ((0, 0), (1, 0)):
        adjusted_temperature, adjusted_species = saturation_adjust_reference(
            pressure[i, j], temperature[i, j], species[:, i, j], target_rh,
            over_ice=surface[i, j] == 2,
        )
        expected_temperature[i, j] = float(np.float32(adjusted_temperature))
        expected_species[:, i, j] = np.asarray(
            adjusted_species.astype(np.float32), dtype=np.float64
        )
    np.testing.assert_array_equal(stored_temperature, expected_temperature)
    np.testing.assert_array_equal(stored_species, expected_species)
    # Unsupported cells, including their sentinel temperatures, are exact
    # copies rather than float32-reconstructed thermodynamic states.
    np.testing.assert_array_equal(stored_temperature[~support], temperature[~support])
    np.testing.assert_array_equal(stored_species[:, ~support], species[:, ~support])

    # The denominator is explicitly pre-thermo: using the post-phase float32
    # mixture would produce a different dry mass in these fixtures.
    expected_dry_mass = pressure_mass / (1.0 + np.sum(species, axis=0))
    post_storage_dry_mass = pressure_mass / (1.0 + np.sum(stored_species, axis=0))
    np.testing.assert_allclose(dry_mass, expected_dry_mass, rtol=0.0, atol=1.0e-15)
    assert np.any(dry_mass[support] != post_storage_dry_mass[support])

    np.testing.assert_array_equal(pressure, saved[0])
    np.testing.assert_array_equal(pressure_mass, saved[1])
    np.testing.assert_array_equal(temperature, saved[2])
    np.testing.assert_array_equal(species, saved[3])
    np.testing.assert_array_equal(support, saved[4])
    np.testing.assert_array_equal(surface, saved[5])


def test_reconstruct_thermo_state_rejects_active_failure_atomically() -> None:
    pressure = np.full((2, 2), 85000.0, dtype=np.float64)
    pressure_mass = np.full((2, 2), 2.0, dtype=np.float64)
    temperature = np.array([[280.0, 0.0], [250.0, 0.0]], dtype=np.float64)
    species = np.zeros((6, 2, 2), dtype=np.float64)
    species[:, 0, 0] = [0.01, 0.001, 0.001, 0.01, 0.02, 0.03]
    species[:, 1, 0] = [0.0002, 0.0, 0.001, 0.01, 0.02, 0.03]
    support = np.array([[True, False], [True, False]], dtype=bool)
    surface = np.array([[1, 1], [2, 2]], dtype=np.int64)
    saved = (pressure.copy(), pressure_mass.copy(), temperature.copy(), species.copy(),
             support.copy(), surface.copy())

    # The liquid cell is feasible, but the active ice cell is warm and must
    # fail the whole transaction rather than returning a partially adjusted
    # candidate.
    temperature[1, 0] = 280.0
    expect_value_error(
        lambda: reconstruct_thermo_state_reference(
            pressure, pressure_mass, temperature, species, support, surface, 0.8
        ),
        "warm active ice reconstruction",
    )
    np.testing.assert_array_equal(pressure, saved[0])
    np.testing.assert_array_equal(pressure_mass, saved[1])
    np.testing.assert_array_equal(temperature, np.array([[280.0, 0.0], [280.0, 0.0]]))
    np.testing.assert_array_equal(species, saved[3])
    np.testing.assert_array_equal(support, saved[4])
    np.testing.assert_array_equal(surface, saved[5])


def test_reconstruct_thermo_state_rejects_shapes_values_and_surface_contract() -> None:
    pressure = np.full((2, 2), 85000.0, dtype=np.float64)
    pressure_mass = np.full((2, 2), 2.0, dtype=np.float64)
    temperature = np.full((2, 2), 280.0, dtype=np.float64)
    species = np.full((6, 2, 2), 0.001, dtype=np.float64)
    species[0] = 0.01
    support = np.ones((2, 2), dtype=bool)
    surface = np.ones((2, 2), dtype=np.int64)

    calls = (
        ("pressure shape", lambda: reconstruct_thermo_state_reference(
            pressure[:1], pressure_mass, temperature, species, support, surface, 0.8)),
        ("mass shape", lambda: reconstruct_thermo_state_reference(
            pressure, pressure_mass[:1], temperature, species, support, surface, 0.8)),
        ("temperature shape", lambda: reconstruct_thermo_state_reference(
            pressure, pressure_mass, temperature[:1], species, support, surface, 0.8)),
        ("species shape", lambda: reconstruct_thermo_state_reference(
            pressure, pressure_mass, temperature, species[:5], support, surface, 0.8)),
        ("support shape", lambda: reconstruct_thermo_state_reference(
            pressure, pressure_mass, temperature, species, support[:1], surface, 0.8)),
        ("surface shape", lambda: reconstruct_thermo_state_reference(
            pressure, pressure_mass, temperature, species, support, surface[:1], 0.8)),
        ("support is not bool", lambda: reconstruct_thermo_state_reference(
            pressure, pressure_mass, temperature, species, support.astype(np.int8), surface, 0.8)),
        ("active surface is not liquid or ice", lambda: reconstruct_thermo_state_reference(
            pressure, pressure_mass, temperature, species, support,
            np.full((2, 2), 3, dtype=np.int64), 0.8)),
        ("support on zero mass", lambda: reconstruct_thermo_state_reference(
            pressure, np.where(support, 0.0, pressure_mass), temperature,
            species, support, surface, 0.8)),
        ("negative pressure mass", lambda: reconstruct_thermo_state_reference(
            pressure, np.where(support, -1.0, pressure_mass), temperature,
            species, support, surface, 0.8)),
        ("negative species", lambda: reconstruct_thermo_state_reference(
            pressure, pressure_mass, temperature,
            np.where(np.indices(species.shape)[0] == 0, -0.001, species),
            support, surface, 0.8)),
        ("nonfinite pressure", lambda: reconstruct_thermo_state_reference(
            np.where(np.indices(pressure.shape)[0] == 0, np.nan, pressure),
            pressure_mass, temperature, species, support, surface, 0.8)),
        ("nonfinite species", lambda: reconstruct_thermo_state_reference(
            pressure, pressure_mass, temperature,
            np.where(np.indices(species.shape)[0] == 0, np.nan, species),
            support, surface, 0.8)),
        ("nonfinite RH", lambda: reconstruct_thermo_state_reference(
            pressure, pressure_mass, temperature, species, support, surface, np.nan)),
        ("non-scalar RH", lambda: reconstruct_thermo_state_reference(
            pressure, pressure_mass, temperature, species, support, surface, np.array([0.8]))),
    )
    for label, call in calls:
        expect_value_error(call, label)


def test_surface_pressure_remap_same_domain_uses_explicit_boundary_strip() -> None:
    old_interfaces = np.array([100000.0, 90000.0, 80000.0])
    old_mass = np.array([2.75, 4.25])
    old_temperature = np.array([278.0, 302.0])
    old_species = np.array(
        [[.011, .021], [.002, .003], [.001, .004],
         [.010, .020], [.015, .025], [.005, .035]],
        dtype=np.float64,
    )
    new_interfaces = np.array([100050.0, 90000.0, 80000.0])
    boundary_temperature = 290.0
    boundary_species = np.array(
        [.004, .001, .002, .003, .005, .007], dtype=np.float64
    )
    area = 2.0
    boundary_mass = area * 50.0 / 9.80665 / (1.0 + boundary_species.sum())
    expected = hand_boundary_transition(
        old_mass,
        old_temperature,
        old_species,
        boundary_mass,
        boundary_temperature,
        boundary_species,
        np.array([[1.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
    )
    result = remap_surface_pressure_reference(
        old_interfaces,
        old_mass,
        old_temperature,
        old_species,
        new_interfaces,
        boundary_temperature,
        boundary_species,
        area,
    )
    for actual, expected_value in zip(result, expected):
        np.testing.assert_allclose(actual, expected_value, rtol=0.0, atol=2.0e-13)
    # The seed full-cell pressure width must not replace the explicit strip
    # mass, and the original lower donor mass must not be renormalized.
    full_cell_mass = area * (new_interfaces[0] - new_interfaces[1]) / 9.80665
    assert abs(result[0][0] - full_cell_mass / (1.0 + boundary_species.sum())) > 1.0
    assert result[0][1] == old_mass[1]
    np.testing.assert_array_equal(result[2][:, 1], old_species[:, 1])
    assert result[1][1] == old_temperature[1]
    np.testing.assert_allclose(
        result[0] @ mixture_enthalpy(result[1], result[2]),
        expected[0] @ mixture_enthalpy(expected[1], expected[2]),
        rtol=0.0,
        atol=1.0e-8,
    )


def test_pressure_width_dry_mass_separates_full_seed_cell_from_boundary_strip() -> None:
    area = 173456.75
    species = np.array(
        [.01327193, .00234117, .00071329, .00121731, .00038127, .00062919],
        dtype=np.float64,
    )
    full_cell_mass = dry_mass_from_pressure_width_reference(area, 5000.0, species)
    boundary_strip_mass = dry_mass_from_pressure_width_reference(area, 50.0, species)

    # A seed cell's stored dry mass is based on its complete pressure width;
    # the remap donor is only the requested surface-pressure increment.
    np.testing.assert_allclose(
        full_cell_mass / boundary_strip_mass, 100.0, rtol=0.0, atol=1.0e-13
    )
    np.testing.assert_allclose(
        boundary_strip_mass * (1.0 + species.sum()),
        area * 50.0 / 9.80665,
        rtol=0.0,
        atol=1.0e-12,
    )
    assert full_cell_mass > boundary_strip_mass

    for bad_area, bad_width, bad_species, label in (
        (0.0, 50.0, species, "zero area"),
        (area, 0.0, species, "zero pressure width"),
        (area, 50.0, species[:5], "species shape"),
        (area, 50.0, np.array([.01327193, -.001, .00071329, .00121731, .00038127, .00062919]), "negative species"),
        (area, 50.0, np.array([.200001, .00234117, .00071329, .00121731, .00038127, .00062919]), "vapor range"),
    ):
        expect_value_error(
            lambda: dry_mass_from_pressure_width_reference(
                bad_area, bad_width, bad_species
            ),
            label,
        )


def test_transition_seed_mass_matches_pressure_and_stored_species() -> None:
    shape = (3, 1, 1)
    seed_pressure_mass = np.array([[[100.0]], [[220.0]], [[300.0]]])
    seed_species = np.zeros((6, *shape), dtype=np.float64)
    seed_species[0, :, 0, 0] = [.01, .02, .03]
    seed_species[1, :, 0, 0] = [.002, .003, .004]
    seed_domain = np.ones(shape, dtype=bool)
    seed_dry_mass = seed_pressure_mass / (1.0 + seed_species.sum(axis=0))

    validate_transition_seed_mass_reference(
        seed_pressure_mass,
        seed_species,
        seed_domain,
        seed_dry_mass,
    )

    # Retained dry mass remains valid after float32 species storage.
    seed_species = seed_species.astype(np.float32).astype(np.float64)
    validate_transition_seed_mass_reference(
        seed_pressure_mass,
        seed_species,
        seed_domain,
        seed_dry_mass,
    )

    bad_unchanged = seed_dry_mass.copy()
    bad_unchanged[0, 0, 0] += 1.0e-6
    expect_value_error(
        lambda: validate_transition_seed_mass_reference(
            seed_pressure_mass,
            seed_species,
            seed_domain,
            bad_unchanged,
        ),
        "mutated retained donor mass",
    )

    bad_changed = seed_dry_mass.copy()
    bad_changed[1, 0, 0] *= 0.9
    expect_value_error(
        lambda: validate_transition_seed_mass_reference(
            seed_pressure_mass,
            seed_species,
            seed_domain,
            bad_changed,
        ),
        "mutated full-cell seed mass",
    )
    seed_species[0, 0, 0, 0] = .08
    expect_value_error(
        lambda: validate_transition_seed_mass_reference(
            seed_pressure_mass, seed_species, seed_domain, seed_dry_mass,
        ),
        "composition change without a matching mass update",
    )


def test_surface_pressure_remap_one_center_split_conserves_hand_moments() -> None:
    old_interfaces = np.array([100000.0, 90000.0, 80000.0])
    old_mass = np.array([2.75, 4.25])
    old_temperature = np.array([278.0, 302.0])
    old_species = np.array(
        [[.011, .021], [.002, .003], [.001, .004],
         [.010, .020], [.015, .025], [.005, .035]],
        dtype=np.float64,
    )
    new_interfaces = np.array([100050.0, 95000.0, 90000.0, 80000.0])
    boundary_temperature = 290.0
    boundary_species = np.array(
        [.004, .001, .002, .003, .005, .007], dtype=np.float64
    )
    area = 2.0
    boundary_mass = area * 50.0 / 9.80665 / (1.0 + boundary_species.sum())
    expected = hand_boundary_transition(
        old_mass,
        old_temperature,
        old_species,
        boundary_mass,
        boundary_temperature,
        boundary_species,
        np.array([[1.0, .5, 0.0], [0.0, .5, 0.0], [0.0, 0.0, 1.0]]),
    )
    result = remap_surface_pressure_reference(
        old_interfaces,
        old_mass,
        old_temperature,
        old_species,
        new_interfaces,
        boundary_temperature,
        boundary_species,
        area,
    )
    for actual, expected_value in zip(result, expected):
        np.testing.assert_allclose(actual, expected_value, rtol=0.0, atol=2.0e-13)
    # The old upper cell is the sole donor for the final destination cell.
    assert result[0][-1] == old_mass[1]
    assert result[1][-1] == old_temperature[1]
    np.testing.assert_array_equal(result[2][:, -1], old_species[:, 1])
    np.testing.assert_allclose(
        result[0] @ result[2].T,
        expected[0] @ expected[2].T,
        rtol=0.0,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        result[0] @ mixture_enthalpy(result[1], result[2]),
        expected[0] @ mixture_enthalpy(expected[1], expected[2]),
        rtol=0.0,
        atol=1.0e-8,
    )


def test_surface_pressure_remap_rejects_invalid_boundary_transition() -> None:
    old_interfaces = np.array([100000.0, 90000.0, 80000.0])
    old_mass = np.array([2.75, 4.25])
    old_temperature = np.array([278.0, 302.0])
    old_species = np.array(
        [[.011, .021], [.002, .003], [.001, .004],
         [.010, .020], [.015, .025], [.005, .035]],
        dtype=np.float64,
    )
    new_interfaces = np.array([100050.0, 90000.0, 80000.0])
    boundary_temperature = 290.0
    boundary_species = np.array(
        [.004, .001, .002, .003, .005, .007], dtype=np.float64
    )
    area = 2.0
    base = lambda **kwargs: remap_surface_pressure_reference(
        old_interfaces,
        old_mass,
        old_temperature,
        old_species,
        kwargs.pop("new_interfaces", new_interfaces),
        kwargs.pop("boundary_temperature", boundary_temperature),
        kwargs.pop("boundary_species", boundary_species),
        kwargs.pop("area", area),
    )
    for delta, label in (
        (0.0, "zero pressure delta"),
        (-1.0, "negative pressure delta"),
        (100.1, "pressure delta above bound"),
    ):
        expect_value_error(
            lambda delta=delta: base(
                new_interfaces=np.array(
                    [old_interfaces[0] + delta, new_interfaces[1], new_interfaces[2]]
                )
            ),
            label,
        )
    invalid_boundary_cases = (
        ("boundary species shape", {"boundary_species": boundary_species[:5]}),
        ("boundary species nonfinite", {"boundary_species": np.array([.004, .001, np.nan, .003, .005, .007])}),
        ("boundary species negative", {"boundary_species": np.array([.004, -.001, .002, .003, .005, .007])}),
        ("boundary temperature shape", {"boundary_temperature": np.array([290.0])}),
        ("boundary temperature nonfinite", {"boundary_temperature": np.nan}),
        ("area zero", {"area": 0.0}),
        ("area negative", {"area": -2.0}),
        ("area nonfinite", {"area": np.inf}),
        ("changed endpoint", {"new_interfaces": np.array([100050.0, 90000.0, 80001.0])}),
        ("non-descending destination", {"new_interfaces": np.array([100050.0, 90000.0, 90001.0])}),
        ("too many destination cells", {"new_interfaces": np.array([100050.0, 95000.0, 90000.0, 85000.0, 80000.0])}),
    )
    for label, kwargs in invalid_boundary_cases:
        expect_value_error(lambda kwargs=kwargs: base(**kwargs), label)


def test_invalid_shapes_and_geometry_are_rejected() -> None:
    old_interfaces = np.array([100000.0, 92000.0, 84000.0])
    old_mass = np.array([2.0, 3.0])
    old_temperature = np.array([270.0, 280.0])
    old_species = np.zeros((6, 2), dtype=np.float64)
    new_interfaces = np.array([100000.0, 96000.0, 88000.0, 84000.0])

    try:
        remap_pressure_column_reference(
            old_interfaces, old_mass, old_temperature, old_species[:5], new_interfaces
        )
    except ValueError:
        pass
    else:
        raise AssertionError("accepted malformed species shape")

    bad_interface_cases = (
        (np.array([100000.0, 90000.0]), "interface shape"),
        (np.array([100000.0, 90000.0, 91000.0, 84000.0]), "non-monotone destination"),
        (np.array([100001.0, 96000.0, 88000.0, 84000.0]), "endpoint mismatch"),
        (np.array([100000.0, 96000.0, 88000.0, 0.0]), "non-positive interface"),
    )
    for bad_new_interfaces, label in bad_interface_cases:
        try:
            remap_pressure_column_reference(
                old_interfaces,
                old_mass,
                old_temperature,
                old_species,
                bad_new_interfaces,
            )
        except ValueError:
            continue
        raise AssertionError(f"accepted malformed {label}")

    for bad_mass, bad_temperature, bad_species, label in (
        (np.array([0.0, 3.0]), old_temperature, old_species, "non-positive mass"),
        (old_mass, np.array([149.0, 280.0]), old_species, "temperature range"),
        (old_mass, old_temperature, np.array([[-.1, 0.0]] + [[0.0, 0.0]] * 5), "negative species"),
    ):
        try:
            remap_pressure_column_reference(
                old_interfaces, bad_mass, bad_temperature, bad_species, new_interfaces
            )
        except ValueError:
            continue
        raise AssertionError(f"accepted malformed {label}")


def main() -> None:
    test_identity_is_bitwise_exact()
    test_remap_bounds_enclose_hand_calculated_extremes()
    test_remap_bounds_zero_uncertainty_is_arithmetic_only_and_tightens()
    test_remap_bounds_reject_malformed_or_unbounded_uncertainty()
    test_remap_bounds_endpoint_rounding_is_outward()
    test_asymmetric_remap_intervals_enclose_condensate_creation()
    test_explicit_remap_intervals_reject_invalid_endpoints()
    test_thermo_storage_intervals_feed_pressure_remap()
    test_split_merge_conserves_dry_species_and_mixture_enthalpy()
    test_asymmetric_center_split_preserves_untouched_upper_donor()
    test_stored_dry_mass_is_not_reconstructed_from_pressure_width()
    test_conservation_gate_rejects_independent_output_perturbations()
    test_isothermal_dry_remap_preserves_temperature()
    test_saturation_adjust_liquid_condensation_evaporation_and_exhaustion()
    test_saturation_adjust_ice_sublimation_and_deposition()
    test_saturation_adjust_ice_warming_is_rejected_atomically()
    test_saturation_equilibrium_certificate_liquid_and_storage()
    test_saturation_equilibrium_certificate_ice_boundary_and_exhaustion()
    test_saturation_equilibrium_certificate_rejects_uncertified_cases()
    test_saturation_adjust_rejects_nonfinite_bad_shapes_and_invalid_rh()
    test_saturation_then_float32_storage_remap_conserves_post_thermo_state()
    test_reconstruct_thermo_state_analytic_small_2x2()
    test_reconstruct_thermo_state_rejects_active_failure_atomically()
    test_reconstruct_thermo_state_rejects_shapes_values_and_surface_contract()
    test_pressure_width_dry_mass_separates_full_seed_cell_from_boundary_strip()
    test_transition_seed_mass_matches_pressure_and_stored_species()
    test_surface_pressure_remap_same_domain_uses_explicit_boundary_strip()
    test_surface_pressure_remap_one_center_split_conserves_hand_moments()
    test_surface_pressure_remap_rejects_invalid_boundary_transition()
    test_invalid_shapes_and_geometry_are_rejected()
    if len(sys.argv) > 2:
        raise SystemExit("usage: test_pressure_transition_reference.py [fixture]")
    if len(sys.argv) == 2:
        check_fortran_fixture(Path(sys.argv[1]))
    print("Pressure-transition reference tests passed")


if __name__ == "__main__":
    main()
