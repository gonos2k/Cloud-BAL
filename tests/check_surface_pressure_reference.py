#!/usr/bin/env python3
"""Compare pressure-domain transition output with an independent remap oracle."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pressure_transition_reference import (  # noqa: E402
    remap_surface_pressure_reference,
    transition_geopotential_reference,
)


STATUS_OK = 20
EXPECTED_CASES = ("same_domain", "one_center")


def _vector(parts: list[str], label: str) -> np.ndarray:
    if len(parts) < 2 or parts[0] != label:
        raise AssertionError(f"expected {label} record")
    count = int(parts[1])
    if count < 1 or len(parts) != count + 2:
        raise AssertionError(f"invalid {label} record")
    return np.asarray([float(value) for value in parts[2:]], dtype=np.float64)


def _matrix(parts: list[str], label: str) -> np.ndarray:
    if len(parts) < 3 or parts[0] != label:
        raise AssertionError(f"expected {label} record")
    rows, columns = int(parts[1]), int(parts[2])
    if rows < 1 or columns < 1 or len(parts) != rows * columns + 3:
        raise AssertionError(f"invalid {label} record")
    return np.asarray([float(value) for value in parts[3:]], dtype=np.float64).reshape(
        (rows, columns), order="F"
    )


def _scalar(parts: list[str], label: str) -> float:
    if len(parts) != 2 or parts[0] != label:
        raise AssertionError(f"expected {label} record")
    return float(parts[1])


def _read_fixture(path: Path) -> dict[str, dict[str, object]]:
    lines = [line.split() for line in path.read_text().splitlines() if line.strip()]
    if not lines or lines[0] != ["FORMAT", "SURFACE_PRESSURE_REFERENCE_FIXTURE_V1"]:
        raise AssertionError(f"invalid surface-pressure fixture header: {path}")
    cases: dict[str, dict[str, object]] = {}
    cursor = 1
    while cursor < len(lines):
        if len(lines[cursor]) != 2 or lines[cursor][0] != "CASE":
            raise AssertionError("expected CASE record")
        name = lines[cursor][1]
        cursor += 1
        if name in cases:
            raise AssertionError(f"duplicate case: {name}")
        case: dict[str, object] = {
            "old_interfaces": _vector(lines[cursor], "OLD_INTERFACES")
        }
        cursor += 1
        case["new_interfaces"] = _vector(lines[cursor], "NEW_INTERFACES")
        cursor += 1
        case["old_mass"] = _vector(lines[cursor], "OLD_DRY_MASS")
        cursor += 1
        case["old_temperature"] = _vector(lines[cursor], "OLD_TEMPERATURE")
        cursor += 1
        case["old_species"] = _matrix(lines[cursor], "OLD_SPECIES")
        cursor += 1
        if len(lines[cursor]) != 2 or lines[cursor][0] != "BOUNDARY_TEMPERATURE":
            raise AssertionError(f"invalid boundary temperature record for {name}")
        case["boundary_temperature"] = float(lines[cursor][1])
        cursor += 1
        case["boundary_species"] = _vector(lines[cursor], "BOUNDARY_SPECIES")
        cursor += 1
        if len(lines[cursor]) != 2 or lines[cursor][0] != "AREA":
            raise AssertionError(f"invalid area record for {name}")
        case["area"] = float(lines[cursor][1])
        cursor += 1
        if len(lines[cursor]) != 2 or lines[cursor][0] != "RESULT":
            raise AssertionError(f"invalid result record for {name}")
        case["status"] = int(lines[cursor][1])
        cursor += 1
        case["final_mass"] = _vector(lines[cursor], "FINAL_DRY_MASS")
        cursor += 1
        case["final_temperature"] = _vector(lines[cursor], "FINAL_TEMPERATURE")
        cursor += 1
        case["final_species"] = _matrix(lines[cursor], "FINAL_SPECIES")
        cursor += 1
        if lines[cursor] != ["ENDCASE"]:
            optional_records = (
                ("pressure", "PRESSURE_CENTERS", "vector"),
                ("old_geopotential", "OLD_GEOPOTENTIAL", "vector"),
                ("prior_geopotential", "PRIOR_GEOPOTENTIAL", "vector"),
                ("final_geopotential", "FINAL_GEOPOTENTIAL", "vector"),
                ("prior_temperature", "PRIOR_TEMPERATURE", "vector"),
                ("prior_species", "PRIOR_SPECIES", "matrix"),
                ("old_surface_pressure", "OLD_SURFACE_PRESSURE", "scalar"),
                ("new_surface_pressure", "NEW_SURFACE_PRESSURE", "scalar"),
                ("surface_temperature", "SURFACE_TEMPERATURE", "scalar"),
                ("surface_vapor", "SURFACE_VAPOR", "scalar"),
                ("surface_height", "SURFACE_HEIGHT", "scalar"),
            )
            for key, label, kind in optional_records:
                if kind == "vector":
                    case[key] = _vector(lines[cursor], label)
                elif kind == "matrix":
                    case[key] = _matrix(lines[cursor], label)
                else:
                    case[key] = _scalar(lines[cursor], label)
                cursor += 1
            if lines[cursor] != ["ENDCASE"]:
                if lines[cursor][0] == "SEED_GEOPOTENTIAL":
                    case["seed_geopotential"] = _scalar(
                        lines[cursor], "SEED_GEOPOTENTIAL"
                    )
                    cursor += 1
                    case["seed_temperature"] = _scalar(
                        lines[cursor], "SEED_TEMPERATURE"
                    )
                    cursor += 1
                    case["seed_species"] = _vector(lines[cursor], "SEED_SPECIES")
                    cursor += 1
        if lines[cursor] != ["ENDCASE"]:
            raise AssertionError(f"missing ENDCASE for {name}")
        cursor += 1
        cases[name] = case
    return cases


def _float32_storage(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return float32-rounded values and one-ULP bounds in float64 units."""
    values32 = np.asarray(values, dtype=np.float32)
    rounded = values32.astype(np.float64)
    upward = np.nextafter(values32, np.float32(np.inf), dtype=np.float32)
    downward = np.nextafter(values32, np.float32(-np.inf), dtype=np.float32)
    ulp = np.maximum(np.abs(upward - values32), np.abs(values32 - downward))
    return rounded, ulp.astype(np.float64)


def _assert_storage_match(actual: np.ndarray, expected: np.ndarray, label: str) -> float:
    actual_array = np.asarray(actual, dtype=np.float64)
    expected_array = np.asarray(expected, dtype=np.float64)
    if actual_array.shape != expected_array.shape:
        raise AssertionError(
            f"{label} shape differs: actual {actual_array.shape}, "
            f"expected {expected_array.shape}"
        )
    if not np.all(np.isfinite(actual_array)):
        raise AssertionError(f"{label} contains non-finite stored values")
    if not np.all(np.isfinite(expected_array)):
        raise AssertionError(f"{label} reference contains non-finite values")
    expected_stored, ulp = _float32_storage(expected_array)
    # One extra ULP allows for an equivalent Fortran/Python operation landing
    # on the adjacent REAL32 value at a rounding boundary.
    bound = ulp + 64.0 * np.finfo(np.float64).eps * np.abs(expected_stored)
    error = np.abs(actual_array - expected_stored)
    if np.any(error > bound):
        raise AssertionError(
            f"{label} differs beyond float32 storage bound: "
            f"max error {float(np.max(error)):.17g}, "
            f"max bound {float(np.max(bound)):.17g}"
        )
    return float(np.max(error))


def _check_transition_geopotential(case: dict[str, object], name: str) -> float:
    required = {
        "pressure", "old_geopotential", "prior_geopotential", "final_geopotential",
        "prior_temperature", "prior_species", "old_surface_pressure",
        "new_surface_pressure", "surface_temperature", "surface_vapor", "surface_height",
    }
    missing = sorted(required - case.keys())
    if missing:
        raise AssertionError(f"incomplete transition geopotential records for {name}: {missing}")

    pressure = case["pressure"]
    old_phi = case["old_geopotential"]
    prior_phi = case["prior_geopotential"]
    final_phi = case["final_geopotential"]
    old_temperature = case["old_temperature"]
    old_species = case["old_species"]
    prior_temperature = case["prior_temperature"]
    prior_species = case["prior_species"]
    final_temperature = case["final_temperature"]
    final_species = case["final_species"]
    if not (
        pressure.size == prior_phi.size == final_phi.size == prior_temperature.size
        and prior_species.shape == (6, pressure.size)
        and final_temperature.size == pressure.size
        and final_species.shape == (6, pressure.size)
        and old_phi.size == old_temperature.size == old_species.shape[1]
    ):
        raise AssertionError(f"inconsistent transition geopotential shapes for {name}")
    added = pressure.size - old_phi.size
    if added not in (0, 1):
        raise AssertionError(f"unsupported transition geopotential size for {name}")

    # The prior state is the old state plus, at most, its explicit new bottom
    # seed. These identities make the fixture's three state snapshots auditable
    # without trusting the production transition implementation.
    if added:
        if not np.array_equal(prior_phi[1:], old_phi):
            raise AssertionError(f"prior/old Phi mismatch for {name}")
        if not np.array_equal(prior_temperature[1:], old_temperature):
            raise AssertionError(f"prior/old temperature mismatch for {name}")
        if not np.array_equal(prior_species[:, 1:], old_species):
            raise AssertionError(f"prior/old species mismatch for {name}")
        for key in ("seed_geopotential", "seed_temperature", "seed_species"):
            if key not in case:
                raise AssertionError(f"missing {key} record for {name}")
        if (case["seed_geopotential"] != prior_phi[0]
                or case["seed_temperature"] != prior_temperature[0]
                or not np.array_equal(case["seed_species"], prior_species[:, 0])):
            raise AssertionError(f"new-cell seeds do not match prior state for {name}")
        seed_kwargs = {
            "seed_geopotential": case["seed_geopotential"],
            "seed_temperature": case["seed_temperature"],
            "seed_species": case["seed_species"],
        }
    else:
        if (not np.array_equal(prior_phi, old_phi)
                or not np.array_equal(prior_temperature, old_temperature)
                or not np.array_equal(prior_species, old_species)):
            raise AssertionError(f"same-domain prior differs from old state for {name}")
        seed_kwargs = {}

    expected_phi = transition_geopotential_reference(
        pressure,
        old_phi,
        old_temperature,
        old_species,
        final_temperature,
        final_species,
        case["old_surface_pressure"],
        case["new_surface_pressure"],
        case["surface_temperature"],
        case["surface_vapor"],
        case["surface_height"],
        **seed_kwargs,
    )
    phi_error = _assert_storage_match(final_phi, expected_phi, f"final Phi {name}")

    # Exercise the rejection boundary explicitly: a material corruption of a
    # stored Phi must fail the same storage-bound assertion used above.
    for mutation in ("offset", "nan"):
        corrupted = np.asarray(final_phi, dtype=np.float64).copy()
        if mutation == "offset":
            corrupted[0] += 1.0
        else:
            corrupted[0] = np.nan
        try:
            _assert_storage_match(
                corrupted, expected_phi, f"corrupted final Phi ({mutation}) {name}"
            )
        except AssertionError:
            pass
        else:
            raise AssertionError(f"corrupted final Phi ({mutation}) was accepted for {name}")
    return phi_error


def check_fixture(path: Path, *, require_geopotential: bool = False) -> None:
    cases = _read_fixture(path)
    if tuple(cases) != EXPECTED_CASES:
        raise AssertionError("fixture cases do not match expected transition coverage")

    max_remap_defect = 0.0
    phi_errors: list[float] = []
    for name in EXPECTED_CASES:
        case = cases[name]
        if case["status"] != STATUS_OK:
            raise AssertionError(f"Fortran transition failed: {name}")
        old_interfaces = case["old_interfaces"]
        new_interfaces = case["new_interfaces"]
        if name == "same_domain":
            assert new_interfaces.size == old_interfaces.size
        else:
            assert new_interfaces.size == old_interfaces.size + 1
        remapped_mass, expected_temperature, expected_species = (
            remap_surface_pressure_reference(
                old_interfaces,
                case["old_mass"],
                case["old_temperature"],
                case["old_species"],
                new_interfaces,
                case["boundary_temperature"],
                case["boundary_species"],
                case["area"],
            )
        )
        _assert_storage_match(
            case["final_temperature"], expected_temperature,
            f"final temperature {name}",
        )
        _assert_storage_match(
            case["final_species"], expected_species,
            f"final species {name}",
        )

        expected_stored_species, species_ulp = _float32_storage(expected_species)
        pressure_mass = case["area"] * (
            new_interfaces[:-1] - new_interfaces[1:]
        ) / 9.80665
        expected_refreshed_mass = pressure_mass / (
            1.0 + np.sum(expected_stored_species, axis=0)
        )
        denominator = 1.0 + np.sum(expected_stored_species, axis=0)
        propagated_q = pressure_mass * np.sum(species_ulp, axis=0) / denominator**2
        # The fixture stores sixteen decimal digits. The first term covers
        # IEEE-64 arithmetic and the final term covers decimal round-trip.
        mass_bound = (
            256.0 * np.finfo(np.float64).eps
            * np.maximum(1.0, np.abs(expected_refreshed_mass))
            + propagated_q
            + 2.0e-15 * np.maximum(1.0, np.abs(expected_refreshed_mass))
        )
        mass_error = np.abs(case["final_mass"] - expected_refreshed_mass)
        if np.any(mass_error > mass_bound):
            raise AssertionError(
                f"final refreshed dry mass differs for {name}: max error "
                f"{float(np.max(mass_error)):.17g}, max bound "
                f"{float(np.max(mass_bound)):.17g}"
            )
        # The pre-storage remap mass is diagnostic only. The production state
        # refreshes dry mass from pressure geometry and stored float32 q.
        remap_defect = np.abs(remapped_mass - expected_refreshed_mass)
        max_remap_defect = max(max_remap_defect, float(np.max(remap_defect)))
        has_geopotential = "pressure" in case
        if require_geopotential and not has_geopotential:
            raise AssertionError(f"missing transition geopotential records for {name}")
        if has_geopotential:
            phi_errors.append(_check_transition_geopotential(case, name))

    message = (
        "Independent surface-pressure remap reference: two successful cases passed "
        f"(max remap/storage-refresh mass defect {max_remap_defect:.6g} kg)"
    )
    if phi_errors:
        message += f"; max Phi storage error {max(phi_errors):.17g}"
    print(message)


def main() -> None:
    args = sys.argv[1:]
    require_geopotential = "--require-geopotential" in args
    args = [arg for arg in args if arg != "--require-geopotential"]
    if len(args) != 1:
        raise SystemExit(
            f"usage: {sys.argv[0]} [--require-geopotential] FIXTURE"
        )
    check_fixture(Path(args[0]), require_geopotential=require_geopotential)


if __name__ == "__main__":
    main()
