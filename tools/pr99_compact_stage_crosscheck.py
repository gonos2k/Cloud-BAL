#!/usr/bin/env python3
"""Cross-check selected compact stage sums against the superseded OFF full-row capture."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from native_kdm6_trace import read_dump
from pr99_full_stage_reducer import event_residual

COORDS = ((192, 71), (161, 57))
FILES = {
    "melt": ("pr85_kdm6_melt_budget.raw", "PR85_MELT", True),
    "freezing": ("pr85_kdm6_freezing_budget.raw", None, False),
    "rain_freezing": ("pr85_rain_freezing_budget.raw", "PR85_RAIN_FREEZE", False),
    "cold": ("pr85_kdm6_cold_budget.raw", "PR85_KDM6_COLD", True),
    "warm": ("pr85_kdm6_warm_budget.raw", "WARM", True),
    "ice_transition": ("pr85_ice_transition_branch.raw", "PR85_ICE_TRANSITION", True),
}
STAGE_ID = {"melt": 1, "freezing": 2, "cold": 3, "warm": 4,
            "ice_transition": 5, "rain_freezing": 6}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-run", type=Path, required=True)
    parser.add_argument("--compact", type=Path, required=True)
    parser.add_argument("--pre", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pre = read_dump(args.pre)
    bounds = pre["bounds"]
    density = pre["fields"]["DEN"].astype(np.float64)
    thickness = pre["fields"]["DELZ"].astype(np.float64)
    compact = {}
    for line in args.compact.read_text(encoding="ascii").splitlines():
        fields = line.split()
        i, j, stage = map(int, fields[1:4])
        if (i, j) in COORDS:
            compact[(i, j, stage)] = (int(fields[4]), float(fields[6]))
    result = {"schema": "pr99_compact_selected_full_raw_crosscheck_v1",
              "scope": "OFF selected rows only; raw full-row files are superseded diagnostic artifacts",
              "all_values_before_area_weighting_kg_m2": True,
              "coordinates": {}, "raw_stage_sha256": {},
              "compact_sha256": sha256(args.compact), "pre_sha256": sha256(args.pre)}
    for coord in COORDS:
        result["coordinates"][f"{coord[0]},{coord[1]}"] = {}
    for name, (filename, tag, with_density) in FILES.items():
        path = args.raw_run / filename
        result["raw_stage_sha256"][filename] = sha256(path)
        terms = {coord: [] for coord in COORDS}
        with path.open(encoding="ascii", errors="replace") as stream:
            for line in stream:
                fields = line.split()
                if len(fields) < 4 or fields[0].startswith("#"):
                    continue
                if tag is not None and fields[0] != tag:
                    continue
                try:
                    coord = (int(fields[1]), int(fields[2]))
                except ValueError:
                    continue
                if coord not in terms:
                    continue
                k = int(fields[3])
                row, col, level = coord[1]-bounds["jts"], coord[0]-bounds["its"], k-bounds["kts"]
                mass = event_residual(name, fields) * float(thickness[row, level, col])
                if with_density:
                    mass *= float(density[row, level, col])
                terms[coord].append(mass)
        stage = STAGE_ID[name]
        for coord in COORDS:
            raw_sum = math.fsum(terms[coord])
            compact_count, compact_sum = compact[(coord[0], coord[1], stage)]
            delta = raw_sum - compact_sum
            if compact_count != len(terms[coord]) or abs(delta) > 1.0e-18:
                raise ValueError(f"{name} {coord}: compact/raw mismatch count={compact_count}/{len(terms[coord])}, delta={delta}")
            result["coordinates"][f"{coord[0]},{coord[1]}"][name] = {
                "events": compact_count, "raw_stream_sum_kg_m2": raw_sum,
                "compact_sum_kg_m2": compact_sum, "difference_kg_m2": delta}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("OFF compact sums match streamed full rows for both selected columns")


if __name__ == "__main__":
    main()
