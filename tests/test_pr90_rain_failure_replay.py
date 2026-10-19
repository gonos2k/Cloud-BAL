#!/usr/bin/env python3
"""Parser guards for source-bound PR90 native failure replay."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr90_rain_failure_replay import ReplayError, make_harness, parse_capture  # noqa: E402


HEADER = (
    "PR90_RAIN_FAILURE stages=4 -1 internal_volume_precheck "
    "38D1B717 3B449BA6 3F800000 3F800000 40400000 40000000 40400000\n"
)
DERIVED = "PR90_RAIN_FAILURE_DERIVED_HEX " + " ".join(["3FF0000000000000"] * 11) + "\n"
CALLER = "PR87_RAIN_PUBLIC_STORE_REJECT 7 193 1 4 1.0E-9 2.0E-6 1.1E+0\n"


def test_exact_capture_fields() -> None:
    capture = parse_capture(HEADER + DERIVED + CALLER, derived_count=11)
    assert capture["reason"] == "internal_volume_precheck"
    assert capture["input_hex"]["q_internal"] == "38D1B717"
    assert capture["input_hex"]["nvol_internal"] == "3B449BA6"
    assert capture["derived_hex"] == ["3FF0000000000000"] * 11
    assert capture["caller"] == {
        "timestep": 7, "j": 193, "i": 1, "k": 4,
        "printed_values": ["1.0E-9", "2.0E-6", "1.1E+0"],
    }


def test_native_wrapped_caller_line() -> None:
    native_header = (
        "PR90_RAIN_FAILURE stages=4 -1 internal_volume_precheck "
        "308D0490 38AB5008 3F904AFD 4644597C 40400000 44704000 4708B800\n"
    )
    native_caller = (
        "PR87_RAIN_PUBLIC_STORE_REJECT 7 222 193 4\n"
        "1.0260397E-09 8.1688224E-05 1.127288\n"
    )
    native_derived = "PR90_RAIN_FAILURE_DERIVED_HEX " + " ".join(["3FF0000000000000"] * 12) + "\n"
    capture = parse_capture(native_header + native_derived + native_caller, derived_count=12)
    assert capture["input_hex"]["q_internal"] == "308D0490"
    assert capture["caller"]["timestep"] == 7
    assert capture["caller"]["j"] == 222
    assert capture["caller"]["i"] == 193
    assert capture["caller"]["k"] == 4
    assert capture["caller"]["printed_values"] == ["1.0260397E-09", "8.1688224E-05", "1.127288"]


def test_truncated_records_fail_closed() -> None:
    malformed = HEADER.replace("40400000\n", "4040000\n") + DERIVED + CALLER
    try:
        parse_capture(malformed, derived_count=11)
    except ReplayError:
        pass
    else:
        raise AssertionError("truncated input bits were accepted")

    malformed_derived = HEADER + DERIVED.replace("3FF0000000000000 ", "", 1) + CALLER
    try:
        parse_capture(malformed_derived, derived_count=11)
    except ReplayError:
        pass
    else:
        raise AssertionError("truncated derived bits were accepted")


def test_duplicate_captures_fail_closed() -> None:
    for duplicate in (HEADER + HEADER + DERIVED + CALLER,
                      HEADER + DERIVED + DERIVED + CALLER,
                      HEADER + DERIVED + CALLER + CALLER):
        try:
            parse_capture(duplicate, derived_count=11)
        except ReplayError:
            pass
        else:
            raise AssertionError("duplicate capture records were accepted")


def test_positive_roundtrip_uses_internal_units_for_consumer() -> None:
    harness = make_harness({"input_hex": {
        "q_internal": "38D1B717", "nvol_internal": "3B449BA6",
        "dry_density": "3FC00000", "pidnr": "3F800000", "power": "40400000",
        "lambda_min": "40000000", "lambda_max": "40400000",
    }}, "subroutine kdm6_rain_ng_pair_valid()\nend subroutine kdm6_rain_ng_pair_valid", 12)
    assert "call kdm6_rain_ng_pair_valid(q_restored,nvol_restored," in harness
    assert "kdm6_rain_ng_pair_valid(q_public,n_specific" not in harness
    # Fixture choice used by the source-bound replay: restored N/Q is 16 while
    # Nspecific/Q is 10.67, so a 12..40 consumer interval distinguishes units.
    assert "rain_min=real(dry_density,real64)*real(lambda_min,real64)**real(power,real64)/real(pidnr,real64)" in harness


if __name__ == "__main__":
    test_exact_capture_fields()
    test_native_wrapped_caller_line()
    test_truncated_records_fail_closed()
    test_duplicate_captures_fail_closed()
    test_positive_roundtrip_uses_internal_units_for_consumer()
    print("PR90 rain failure parser tests PASS")
