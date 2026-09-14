#!/usr/bin/env python3
"""Check the generated Fortran sequential LUT against its range contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import struct

import numpy as np


def read_fortran_record(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if len(data) < 8:
        raise AssertionError(f"LUT is too short: {path}")
    record_length = struct.unpack(">i", data[:4])[0]
    if record_length != len(data) - 8:
        raise AssertionError("LUT record markers do not bound one complete record")
    trailing_length = struct.unpack(">i", data[4 + record_length : 8 + record_length])[0]
    if trailing_length != record_length:
        raise AssertionError("LUT trailing record marker differs")
    if record_length % 4:
        raise AssertionError("LUT record is not a 32-bit integer array")
    return np.frombuffer(data[4 : 4 + record_length], dtype=">i4")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lut", type=Path, required=True)
    parser.add_argument("--first-gate-m", type=float, required=True)
    parser.add_argument("--spacing-m", type=float, required=True)
    parser.add_argument("--range-interval-m", type=float, default=500.0)
    parser.add_argument("--gate-interval", type=int, default=1)
    args = parser.parse_args()

    values = read_fortran_record(args.lut)
    if len(values) < 3:
        raise AssertionError("LUT lacks the first three gate values")
    expected = np.floor(
        (args.first_gate_m
         + np.arange(3) * args.spacing_m * args.gate_interval)
        / args.range_interval_m
    ).astype(np.int32)
    actual = values[:3].astype(np.int32)
    if not np.array_equal(actual, expected):
        raise AssertionError(f"LUT gate 1..3 {actual.tolist()} != {expected.tolist()}")
    # This fixture distinguishes the metadata-bound 125 m origin from the
    # old zero-origin gate formula (gate 2 would have been floor(500/500)=1).
    if args.first_gate_m == 125.0 and args.spacing_m == 250.0:
        if int(actual[1]) != 0:
            raise AssertionError("GSN gate 2 still uses the old zero-origin LUT")
        old_zero_origin_gate2 = int(
            np.floor(2.0 * args.spacing_m / args.range_interval_m)
        )
        if int(actual[1]) == old_zero_origin_gate2:
            raise AssertionError("GSN gate 2 matches the old zero-origin value")
    print(
        "RADAR_REMAP_LUT_RANGE_PASS",
        {"path": str(args.lut), "gate_1_to_3": actual.tolist(),
         "expected": expected.tolist(), "record_ints": len(values)},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
