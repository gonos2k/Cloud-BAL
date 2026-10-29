#!/usr/bin/env python3
"""Make a 20-point CP02 GDB list plus canonical background rows from HYDRO shadow."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from netCDF4 import Dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection", type=Path)
    parser.add_argument("shadow", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise SystemExit(f"refusing to overwrite {args.output}")

    with args.selection.open(newline="", encoding="utf-8") as stream:
        points = list(csv.DictReader(stream))
    if len(points) != 20 or len({row["point_id"] for row in points}) != 20:
        raise SystemExit("selection must contain 20 unique point IDs")
    expected_roles = Counter({
        "lost_hit": 4,
        "retained_hit": 4,
        "removed_false_alarm": 4,
        "RN1_positive_reference_all_forecasts_below5mm": 4,
        "payload_positive_rain_reflectivity_invalid_proxy": 2,
        "payload_positive_snow_reflectivity_invalid_proxy": 2,
    })
    if Counter(row["role"] for row in points) != expected_roles:
        raise SystemExit("selection role counts differ from the frozen 20-point plan")

    fields = ["arm", "losthit_rank", "lat", "lon", "shadow_j", "shadow_i", "z_index",
              "pressure_pa", "background_rain", "candidate_rain", "background_snow", "candidate_snow"]
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    with Dataset(args.shadow) as data, args.output.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in points:
            i = int(row["shadow_i_zero_based"])
            j = int(row["shadow_j_zero_based"])
            if not 0 <= i < 235 or not 0 <= j < 283:
                raise SystemExit(f"{row['point_id']}: index outside archived shadow grid")
            for k in range(22):
                writer.writerow({
                    "arm": "HYDRO",
                    "losthit_rank": row["point_id"],
                    "lat": row["latitude"],
                    "lon": row["longitude"],
                    "shadow_j": j,
                    "shadow_i": i,
                    "z_index": k,
                    "pressure_pa": float(data.variables["pressure"][k]),
                    "background_rain": float(data.variables["background_rain"][k, j, i]),
                    "candidate_rain": float(data.variables["candidate_rain"][k, j, i]),
                    "background_snow": float(data.variables["background_snow"][k, j, i]),
                    "candidate_snow": float(data.variables["candidate_snow"][k, j, i]),
                })

    print(json.dumps({
        "selection": str(args.selection.resolve()),
        "selection_sha256": digest(args.selection),
        "shadow": str(args.shadow.resolve()),
        "shadow_sha256": digest(args.shadow),
        "output": str(args.output.resolve()),
        "output_sha256": digest(args.output),
        "point_count": len(points),
        "level_count": 22,
        "row_count": sum(1 for _ in args.output.open(encoding="utf-8")) - 1,
        "role_counts": Counter(row["role"] for row in points),
    }, indent=2))


if __name__ == "__main__":
    main()
