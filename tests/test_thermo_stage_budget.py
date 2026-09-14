#!/usr/bin/env python3
"""Standalone arithmetic tests for the pre-geometry thermo-stage ledger."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import validate_thermo_stage_budget  # noqa: E402


# Expected totals below use T0=273.15 K, cp_dry=1004.5, species heat
# capacities (1846.4,4190,2106,4190,2106,2106) and h0=(2.5e6,0,-3.5e5,0,-3.5e5,-3.5e5).
NAMES = (
    "species", "thermo_sensible_change_j", "thermo_phase_change_j",
    "thermo_water_error_kg", "thermo_enthalpy_error_j",
)


def invoke(report, state):
    failures = []

    def require(condition, message):
        if not condition:
            failures.append(message)

    try:
        result = validate_thermo_stage_budget(report, *state, require)
    except Exception as error:  # malformed reports must be reported, not raised
        raise AssertionError(f"thermo budget checker raised: {error}") from error
    return bool(result), failures


def assert_reported(report, state, *, accepted):
    result, failures = invoke(report, state)
    assert result is accepted
    if accepted:
        assert not failures
    else:
        assert failures


def one_cell_case():
    selected = np.ones((1, 1, 1), dtype=bool)
    mass = np.array([[[2.0]]])
    before_t = np.array([[[280.0]]])
    after_t = before_t.copy()
    before_q = np.zeros((6, 1, 1, 1))
    after_q = np.zeros_like(before_q)
    before_q[0, 0, 0, 0] = 0.01       # vapor
    after_q[1, 0, 0, 0] = 0.01        # cloud water
    state = (mass, before_t, before_q, after_t, after_q, selected)
    expected = {
        "species": np.array((-0.02, 0.02, 0.0, 0.0, 0.0, 0.0)),
        "thermo_sensible_change_j": 0.0,
        "thermo_phase_change_j": -49678.9268,
        "thermo_water_error_kg": 0.0,
        "thermo_enthalpy_error_j": -49678.9268,
    }
    return state, expected


def two_cell_case():
    selected = np.array([[[True, True, False]]])
    mass = np.array([[[2.0, 3.0, np.nan]]])  # retained proposal dry mass
    before_t = np.array([[[280.0, 282.0, np.nan]]])
    after_t = np.array([[[281.0, 281.0, np.nan]]])
    before_q = np.full((6, 1, 1, 3), np.nan)
    after_q = np.full_like(before_q, np.nan)
    before_q[:, 0, 0, :2] = 0.0
    after_q[:, 0, 0, :2] = 0.0
    before_q[0, 0, 0, 0] = 0.01       # vapor -> cloud water
    after_q[1, 0, 0, 0] = 0.01
    before_q[1, 0, 0, 1] = 0.02       # cloud water -> cloud ice
    after_q[2, 0, 0, 1] = 0.02
    state = (mass, before_t, before_q, after_t, after_q, selected)
    expected = {
        "species": np.array((-0.02, -0.04, 0.06, 0.0, 0.0, 0.0)),
        "thermo_sensible_change_j": -1047.06,
        "thermo_phase_change_j": -71785.5308,
        "thermo_water_error_kg": 0.0,
        "thermo_enthalpy_error_j": -72832.5908,
    }
    return state, expected


def main() -> int:
    one_state, one_expected = one_cell_case()
    assert_reported(one_expected, one_state, accepted=True)

    state, expected = two_cell_case()
    assert_reported(expected, state, accepted=True)

    # Each ledger component is independently required; forged values fail.
    for name in NAMES:
        forged = dict(expected)
        forged[name] = np.asarray(forged[name], dtype=float) + 1.0
        assert_reported(forged, state, accepted=False)

    # The supplied proposal dry mass is part of the stage identity.
    wrong_mass = list(state)
    wrong_mass[0] = state[0].copy()
    wrong_mass[0][0, 0, 0] = 4.0
    assert_reported(expected, tuple(wrong_mass), accepted=False)

    for name in NAMES:
        malformed = dict(expected)
        malformed[name] = np.nan
        assert_reported(malformed, state, accepted=False)
    malformed = dict(expected)
    malformed["species"] = np.zeros(5)
    assert_reported(malformed, state, accepted=False)
    malformed = dict(expected)
    malformed["thermo_sensible_change_j"] = np.zeros(1)
    assert_reported(malformed, state, accepted=False)
    print("Thermo stage budget tests passed")
    return 0


def test_thermo_stage_budget():
    main()


if __name__ == "__main__":
    raise SystemExit(main())
