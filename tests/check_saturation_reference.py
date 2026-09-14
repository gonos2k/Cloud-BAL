#!/usr/bin/env python3
"""Compare a Fortran saturation fixture with an independent temperature solve."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pressure_transition_reference import (  # noqa: E402
    saturation_adjust_reference,
    saturation_equilibrium_certificate_reference,
)


TEMP_ATOL = 1.0e-9
SPECIES_ATOL = 1.0e-11
STATUS_OK = 20
STATUS_FAILED = -10
EXPECTED_CASES = (
    "liquid_condensation",
    "liquid_evaporation",
    "liquid_reservoir_exhaustion",
    "ice_deposition",
    "ice_sublimation",
    "invalid_ice_warming",
    "nearzero_transfer_root",
    "actual_transition_max_q",
    "actual_transition_p100000",
    "actual_transition_p95000_a",
    "actual_transition_p95000_b",
    "actual_transition_p95000_c",
    "actual_transition_p95000_d",
    "actual_transition_p95000_e",
    "actual_transition_p80000",
    "actual_transition_p65000",
)


def _read_fixture(path: Path) -> dict[str, dict[str, object]]:
    lines = [line.split() for line in path.read_text().splitlines() if line.strip()]
    if not lines or lines[0] != ["FORMAT", "SATURATION_REFERENCE_FIXTURE_V1"]:
        raise AssertionError(f"invalid saturation fixture header: {path}")
    cases: dict[str, dict[str, object]] = {}
    cursor = 1
    while cursor < len(lines):
        if lines[cursor][0] != "CASE" or len(lines[cursor]) != 2:
            raise AssertionError("expected CASE record")
        name = lines[cursor][1]
        cursor += 1
        if cursor >= len(lines) or lines[cursor][0] != "INPUT" or len(lines[cursor]) != 5:
            raise AssertionError(f"invalid INPUT record for {name}")
        pressure, temperature, target_rh = map(float, lines[cursor][1:4])
        surface = int(lines[cursor][4])
        cursor += 1
        if cursor >= len(lines) or lines[cursor][0] != "Q" or len(lines[cursor]) != 7:
            raise AssertionError(f"invalid Q record for {name}")
        species = np.asarray([float(value) for value in lines[cursor][1:]], dtype=np.float64)
        cursor += 1
        if cursor >= len(lines) or lines[cursor][0] != "RESULT" or len(lines[cursor]) != 9:
            raise AssertionError(f"invalid RESULT record for {name}")
        status = int(lines[cursor][1])
        result_temperature = float(lines[cursor][2])
        result_species = np.asarray([float(value) for value in lines[cursor][3:]], dtype=np.float64)
        cursor += 1
        if cursor >= len(lines) or lines[cursor] != ["ENDCASE"]:
            raise AssertionError(f"missing ENDCASE for {name}")
        cursor += 1
        if name in cases:
            raise AssertionError(f"duplicate input case: {name}")
        cases[name] = {
            "pressure": pressure,
            "temperature": temperature,
            "target_rh": target_rh,
            "surface": surface,
            "species": species,
            "status": status,
            "result_temperature": result_temperature,
            "result_species": result_species,
        }
    return cases


def _check_branch(name: str, before: np.ndarray, after: np.ndarray) -> None:
    if name == "liquid_condensation":
        assert after[0] < before[0] and after[1] > before[1]
    elif name == "liquid_evaporation":
        assert after[0] > before[0] and after[1] < before[1]
    elif name == "liquid_reservoir_exhaustion":
        assert after[1] == 0.0 and after[0] > before[0]
    elif name == "ice_deposition":
        assert after[0] < before[0] and after[2] > before[2]
    elif name == "ice_sublimation":
        assert after[0] > before[0] and after[2] < before[2]
    elif name.startswith("actual_transition_"):
        assert after[0] > before[0] and after[1] < before[1]


def check_fixture(path: Path) -> None:
    cases = _read_fixture(path)
    if tuple(cases) != EXPECTED_CASES:
        raise AssertionError("fixture cases do not match the required branch coverage")

    for name in EXPECTED_CASES:
        case = cases[name]
        before = case["species"]
        over_ice = case["surface"] == 2
        expected_valid = name != "invalid_ice_warming"
        try:
            expected_temperature, expected_species = saturation_adjust_reference(
                case["pressure"], case["temperature"], before, case["target_rh"],
                over_ice=over_ice,
            )
        except ValueError:
            if expected_valid:
                raise AssertionError(f"independent oracle rejected valid case {name}")
            if case["status"] != STATUS_FAILED:
                raise AssertionError(f"oracle rejected but Fortran accepted {name}")
            np.testing.assert_array_equal(
                case["result_species"], before,
                err_msg=f"failed saturation adjustment mutated {name} species",
            )
            assert case["result_temperature"] == case["temperature"], name
            continue

        if not expected_valid:
            raise AssertionError(f"independent oracle accepted invalid case {name}")
        if case["status"] != STATUS_OK:
            raise AssertionError(f"oracle accepted but Fortran rejected {name}")
        if name.startswith("actual_transition_"):
            # These records exercise the production boundary where the
            # float64 thermo result is stored canonically as float32.  Exact
            # equality catches a one-ULP solver-selection regression.
            expected_temperature = float(np.float32(expected_temperature))
            expected_species = expected_species.astype(np.float32).astype(np.float64)
            np.testing.assert_equal(
                case["result_temperature"], expected_temperature,
                err_msg=f"canonical temperature differs from independent oracle: {name}",
            )
            np.testing.assert_array_equal(
                case["result_species"], expected_species,
                err_msg=f"canonical species differs from independent oracle: {name}",
            )
        else:
            np.testing.assert_allclose(
                case["result_temperature"], expected_temperature, rtol=0.0, atol=TEMP_ATOL,
                err_msg=f"temperature differs from independent oracle: {name}",
            )
            np.testing.assert_allclose(
                case["result_species"], expected_species, rtol=0.0, atol=SPECIES_ATOL,
                err_msg=f"species differs from independent oracle: {name}",
            )
        certificate = saturation_equilibrium_certificate_reference(
            case["pressure"], case["temperature"], before, case["target_rh"],
            over_ice=over_ice,
        )
        # These fixtures test canonical storage against the independent ideal
        # equilibrium enclosure. This is not a universal bound for the
        # production solver's separate finite stopping criterion.
        stored_t = float(np.float32(case["result_temperature"]))
        stored_q = case["result_species"].astype(np.float32).astype(np.float64)
        t_lower, t_upper = certificate.stored_temperature_bounds
        q_lower, q_upper = certificate.stored_species_bounds
        assert t_lower <= stored_t <= t_upper, f"stored T outside certificate: {name}"
        assert np.all((q_lower <= stored_q) & (stored_q <= q_upper)), (
            f"stored species outside certificate: {name}"
        )
        _check_branch(name, before, case["result_species"])
        # Only vapor and the selected cloud reservoir may change.
        np.testing.assert_array_equal(case["result_species"][3:], before[3:], err_msg=name)

    print("Independent saturation reference: fifteen valid / one rejected cases passed")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} FIXTURE")
    check_fixture(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
