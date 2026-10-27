#!/usr/bin/env python3
"""Verify the actual static reader's geometry in every binary WPS header."""
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_baseline import _records, read_wps


def verify(path: Path) -> None:
    fields = read_wps(path)
    if not fields:
        raise ValueError("static-reader regression produced no WPS fields")
    for key, (_, shape, slab, metadata) in fields.items():
        if shape != (2, 2) or slab.size != 4 or metadata["projection"] != 1:
            raise ValueError(f"unexpected WPS slab layout for {key}: {shape}")
    records = list(_records(path))
    if len(records) != 5 * len(fields):
        raise ValueError("unexpected WPS record count")
    for endian, geometry in records[2::5]:
        expected = b"SWCORNER" + struct.pack(endian + "5f", 35.0, 126.0, 1.0, 1.0, 30.0)
        if geometry != expected:
            raise ValueError("binary WPS geometry does not match the static fixture")
    print(f"Static reader/WPS header readback passed: {len(fields)} fields")


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
