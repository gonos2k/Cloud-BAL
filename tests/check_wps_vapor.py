#!/usr/bin/env python3
"""Independently validate WPS vapor records and legacy byte preservation."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))
from compare_baseline import _records, read_wps  # noqa: E402


NX = 3
NY = 2
RETAINED_LEVELS = {85000.0: 1, 70000.0: 3, 200100.0: 4}
SKIPPED_LEVEL = 105000.0
EXPECTED_QV_UNITS = "kg kg{-1}"


def fail(message: str) -> None:
    raise AssertionError(message)


def groups(path: Path):
    records = list(_records(path))
    if len(records) % 5:
        fail(f"{path}: record count is not a multiple of five")
    result = []
    for offset in range(0, len(records), 5):
        group = records[offset : offset + 5]
        endian, version = group[0]
        if len(version) != 4 or struct.unpack(endian + "i", version)[0] != 5:
            fail(f"{path}: invalid WPS version record")
        metadata = group[1][1]
        if len(metadata) < 156:
            fail(f"{path}: short WPS metadata record")
        field = metadata[60:69].decode("ascii", "replace").strip()
        level = struct.unpack(endian + "f", metadata[140:144])[0]
        result.append((field, level, tuple(group)))
    return result


def assert_non_qv_bytes_equal(legacy: Path, candidate: Path) -> None:
    old = [group for group in groups(legacy) if group[0] != "QV"]
    new = [group for group in groups(candidate) if group[0] != "QV"]
    if old != new:
        fail(f"non-QV WPS records changed: {legacy.name} -> {candidate.name}")


def qv_fields(path: Path):
    fields = read_wps(path)
    qv = [(key, value) for key, value in fields.items() if key[0] == "QV"]
    if len(qv) != len(RETAINED_LEVELS):
        fail(f"{path}: expected three QV levels, found {len(qv)}")
    if any(key[1] == SKIPPED_LEVEL for key, _ in qv):
        fail(f"{path}: skipped 1050 hPa level was emitted")
    return qv


def check_qv(path: Path) -> None:
    fields = read_wps(path)
    qv = qv_fields(path)
    found_levels = {key[1] for key, _ in qv}
    if found_levels != set(RETAINED_LEVELS):
        fail(f"{path}: QV levels {sorted(found_levels)} != {sorted(RETAINED_LEVELS)}")
    if sum(key[0] == "RH" for key in fields) != len(RETAINED_LEVELS):
        fail(f"{path}: RH records were not retained")
    for key, (units, shape, slab, metadata) in qv:
        if units != EXPECTED_QV_UNITS:
            fail(f"{path}: wrong QV units {units!r}")
        if shape != (NX, NY):
            fail(f"{path}: wrong QV shape {shape}")
        k = RETAINED_LEVELS[key[1]]
        expected = np.empty((NX, NY), dtype=np.float32)
        for j in range(NY):
            for i in range(NX):
                expected[i, j] = np.float32((1000 * k + 100 * (i + 1) + 10 * (j + 1)) / 1_000_000.0)
        if k == 1:
            expected[0, 0] = 0.0
        expected_flat = expected.ravel(order="F").astype(np.float64)
        if not np.array_equal(slab, expected_flat):
            fail(f"{path}: QV slab at {key[1]} Pa is transposed, truncated, or altered")
        if metadata["projection"] != 1 or not metadata["wind_grid_relative"]:
            fail(f"{path}: unexpected WPS metadata on QV record")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    root = parser.parse_args().root
    legacy_off = root / "legacy_off.wps"
    legacy_on = root / "legacy_on.wps"
    vapor_off = root / "vapor_off.wps"
    vapor_on = root / "vapor_on.wps"
    required = [legacy_off, legacy_on, vapor_off, vapor_on]
    invalid = [root / f"invalid_{kind}.wps" for kind in ("shape", "nan", "inf", "negative")]
    for path in required + invalid:
        if not path.is_file():
            fail(f"missing WPS test output: {path}")

    legacy_off_fields = read_wps(legacy_off)
    legacy_on_fields = read_wps(legacy_on)
    if any(key[0] == "QV" for key in legacy_off_fields):
        fail("legacy off output unexpectedly contains QV")
    if any(key[0] == "QV" for key in legacy_on_fields):
        fail("legacy on output unexpectedly contains QV")
    if sum(key[0] == "RH" for key in legacy_off_fields) != len(RETAINED_LEVELS):
        fail("legacy off output lost RH")
    if sum(key[0] == "RH" for key in legacy_on_fields) != len(RETAINED_LEVELS):
        fail("legacy on output lost RH")

    check_qv(vapor_off)
    check_qv(vapor_on)
    assert_non_qv_bytes_equal(legacy_off, vapor_off)
    assert_non_qv_bytes_equal(legacy_on, vapor_on)

    for path in invalid:
        if path.read_bytes() != legacy_off.read_bytes():
            fail(f"{path.name}: invalid vapor input changed an existing output")

    print("WPS vapor records, legacy bytes, invalid-input rollback, and input contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
