#!/usr/bin/env python3
"""Reduce selected per-level REAL32 KDM6 total-water checkpoint streams."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

import netCDF4
import numpy as np
from native_kdm6_trace import read_dump
from pr95_call_budget import _read_map_geometry

COORDINATES = ((192, 71), (161, 57))
WATER_FIELDS = ("Q", "QC", "QI", "QR", "QS", "QG")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def analyze(arm: str, run: Path, native: Path, history: Path,
            manifest_path: Path, source: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pre_path, post_path = native / "kdm6_first_call_pre.raw", native / "kdm6_first_call_post.raw"
    if (manifest.get("arm") != arm or manifest.get("returncode") != 0 or
            manifest.get("completion_marker_observed") is not True or
            manifest.get("all_17_fields_and_XLAND_byte_equal") is not True or
            manifest.get("pre_sha256") != sha256(pre_path) or
            manifest.get("native_post_sha256") != sha256(post_path)):
        raise ValueError("checkpoint reducer inputs are not bound to a successful native replay")
    checkpoint = run / "pr99_total_water_checkpoints.raw"
    pre, post = read_dump(pre_path), read_dump(post_path)
    bounds = pre["bounds"]
    if bounds != post["bounds"]:
        raise ValueError("pre/post state bounds differ")
    with netCDF4.Dataset(history) as dataset:
        dataset.set_auto_mask(False)
        area, _, _ = _read_map_geometry(dataset,
            slice(bounds["jts"] - 1, bounds["jte"]),
            slice(bounds["its"] - 1, bounds["ite"]))
    density = pre["fields"]["DEN"].astype(float)
    thickness = pre["fields"]["DELZ"].astype(float)
    previous: dict[tuple[int, int, int, int], float] = {}
    site_changes: dict[tuple[int, int, int, int], float] = defaultdict(float)
    selected_rows = 0
    tokens = checkpoint.read_text(encoding="ascii").split()
    if len(tokens) % 16:
        raise ValueError("checkpoint stream has an incomplete record")
    for offset in range(0, len(tokens), 16):
        record = tokens[offset:offset + 16]
        i, j, k, loop, site = map(int, record[:5])
        if (i, j) not in COORDINATES:
            continue
        level = k - bounds["kts"]
        row, col = j - bounds["jts"], i - bounds["its"]
        if not (0 <= level < thickness.shape[1]):
            raise ValueError(f"checkpoint k={k} outside native state bounds")
        key = (i, j, loop, k)
        total = float(record[5])
        scale = density[row, level, col] * thickness[row, level, col] * area[row, col]
        delta = 0.0 if site == 0 or key not in previous else total - previous[key]
        previous[key] = total
        site_changes[(i, j, loop, site)] += delta * scale
        selected_rows += 1
    results = {}
    for i, j in COORDINATES:
        row, col = j - bounds["jts"], i - bounds["its"]
        sites = []
        for (si, sj, loop, site), mass in site_changes.items():
            if (si, sj) == (i, j) and site != 0:
                sites.append({"loop": loop, "source_line": site, "total_water_change_kg": mass})
        sites.sort(key=lambda item: (item["loop"], item["source_line"]))
        checkpoint_change = math.fsum(item["total_water_change_kg"] for item in sites)
        endpoint_change = math.fsum(float(np.sum(
            (post["fields"][name][row, :, col].astype(float) -
             pre["fields"][name][row, :, col].astype(float)) *
            density[row, :, col] * thickness[row, :, col] * area[row, col]))
            for name in WATER_FIELDS)
        results[f"{i},{j}"] = {
            "checkpoint_telescoped_total_water_change_kg": checkpoint_change,
            "native_pre_to_post_total_water_change_kg": endpoint_change,
            "checkpoint_minus_endpoint_kg": checkpoint_change - endpoint_change,
            "source_ordered_assignment_changes": sites,
        }
    max_error = max(abs(value["checkpoint_minus_endpoint_kg"]) for value in results.values())
    if max_error > 1e-5:
        raise ValueError(f"checkpoint telescope misses native endpoint by {max_error} kg")
    return {
        "schema": "pr99_total_water_checkpoints_v1", "arm": arm,
        "measure": "actual REAL32 total Q+QC+QI+QR+QS+QG; input DEN*DELZ*history map area",
        "returncode": manifest["returncode"],
        "completion_marker_observed": manifest["completion_marker_observed"],
        "all_17_fields_and_XLAND_byte_equal": manifest["all_17_fields_and_XLAND_byte_equal"],
        "checkpoint_rows_selected": selected_rows,
        "checkpoint_sha256": sha256(checkpoint), "source_sha256": sha256(source),
        "manifest_sha256": sha256(manifest_path), "pre_sha256": sha256(pre_path),
        "native_post_sha256": sha256(post_path), "history_sha256": sha256(history),
        "coordinates": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("OFF", "HYDRO", "COUPLED"), required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.arm, args.run, args.native, args.history,
                     args.manifest, args.source)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for coordinate, values in result["coordinates"].items():
        print(args.arm, coordinate, values["checkpoint_telescoped_total_water_change_kg"],
              values["native_pre_to_post_total_water_change_kg"],
              values["checkpoint_minus_endpoint_kg"])


if __name__ == "__main__":
    main()
