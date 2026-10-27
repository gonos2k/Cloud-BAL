#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, chartostring

REPO = Path(__file__).resolve().parents[3]
ARCHIVE = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch")
MAP = (
    REPO
    / "docs/evidence/precip_transitions_20261027/native_trace/final-v2/losthit_mapping.csv"
)
FILES = {
    "OFF": ARCHIVE
    / "cp02_native_12_15.B4Lwmh/metgrid/met_em.d01.2026-08-16_12:00:00.nc",
    "HYDRO": ARCHIVE
    / "cp02_actual12_liquid_wps.HisIOM/metgrid_HYDRO/met_em.d01.2026-08-16_12:00:00.nc",
    "LIQUID": ARCHIVE
    / "cp02_actual12_liquid_wps.HisIOM/metgrid_LIQUID_RADAR_RH1/met_em.d01.2026-08-16_12:00:00.nc",
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    output = parser.parse_args().output_dir.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to reuse existing output directory: {output}")
    output.mkdir(parents=True)
    points = {}
    with MAP.open() as stream:
        for row in csv.DictReader(stream):
            points.setdefault(int(row["losthit_rank"]), []).append(row)
    if len(points) != 20 or any(len(rows) != 4 for rows in points.values()):
        raise RuntimeError("expected 20 mapped points with four corners each")
    profiles = []
    files = []
    for arm, path in FILES.items():
        files.append(
            {
                "arm": arm,
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
        with Dataset(path) as dataset:
            if chartostring(dataset["Times"][:]).tolist() != ["2026-08-16_12:00:00"]:
                raise RuntimeError(f"unexpected valid time in {path}")
            expected_dims = ("Time", "num_metgrid_levels", "south_north", "west_east")
            for name in ("QR", "QS"):
                var = dataset[name]
                if var.dimensions != expected_dims or var.shape != (1, 21, 282, 234):
                    raise RuntimeError(f"unexpected {name} shape/dimensions in {path}")
                if str(getattr(var, "units", "")).strip() != "kg kg-1":
                    raise RuntimeError(f"unexpected {name} units in {path}")
                data = np.ma.asarray(var[0])
                if (
                    np.ma.getmaskarray(data).any()
                    or not np.isfinite(data.filled(np.nan)).all()
                ):
                    raise RuntimeError(f"masked/nonfinite {name} in {path}")
                if name == "QR":
                    qr = data
                else:
                    qs = data
            lat = np.asarray(dataset["XLAT_M"][0])
            lon = np.asarray(dataset["XLONG_M"][0])
            if lat.shape != (282, 234) or lon.shape != (282, 234):
                raise RuntimeError(f"unexpected coordinate grid in {path}")
            for rank, corners in points.items():
                weights = np.array([float(row["weight"]) for row in corners])
                target_lat = float(corners[0]["lat"])
                target_lon = float(corners[0]["lon"])
                ys = [int(row["native_j"]) for row in corners]
                xs = [int(row["native_i"]) for row in corners]
                if (
                    abs(float(weights @ lat[ys, xs]) - target_lat) > 1e-8
                    or abs(float(weights @ lon[ys, xs]) - target_lon) > 1e-8
                ):
                    raise RuntimeError(
                        f"mapping coordinates mismatch for {arm} point {rank}"
                    )
                for level in range(21):
                    profiles.append(
                        {
                            "arm": arm,
                            "losthit_rank": rank,
                            "target_flat_index_yx": corners[0]["target_flat_index_yx"],
                            "lat": target_lat,
                            "lon": target_lon,
                            "metgrid_level": level,
                            "QR": float(
                                weights
                                @ np.array([qr[level, y, x] for y, x in zip(ys, xs)])
                            ),
                            "QS": float(
                                weights
                                @ np.array([qs[level, y, x] for y, x in zip(ys, xs)])
                            ),
                        }
                    )
    with (output / "metgrid_species_profiles.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=profiles[0].keys())
        writer.writeheader()
        writer.writerows(profiles)
    summaries = []
    for field in ("QR", "QS"):
        arrays = {
            arm: np.array([row[field] for row in profiles if row["arm"] == arm])
            for arm in FILES
        }
        for arm in ("HYDRO", "LIQUID"):
            delta = arrays[arm] - arrays["OFF"]
            summaries.append(
                {
                    "field": field,
                    "arm": arm,
                    "n": len(delta),
                    "off_mean": float(arrays["OFF"].mean()),
                    "arm_mean": float(arrays[arm].mean()),
                    "mean_delta": float(delta.mean()),
                    "mean_abs_delta": float(np.abs(delta).mean()),
                    "max_abs_delta": float(np.abs(delta).max()),
                    "exact_equal": bool(np.array_equal(arrays["OFF"], arrays[arm])),
                }
            )
    with (output / "metgrid_species_summary.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=summaries[0].keys())
        writer.writeheader()
        writer.writerows(summaries)
    for item in files:
        if sha256(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"input changed: {item['path']}")
    receipt = {
        "valid_time_utc": "2026-08-16T12:00:00Z",
        "source_hashes_unchanged_after_read": True,
        "status": "PASS_MAPPED_METGRID_QR_QS_EXTRACTION",
        "point_mapping_path": str(MAP),
        "point_mapping_sha256": sha256(MAP),
        "point_count": len(points),
        "levels": 21,
        "interpolation": "existing four-corner bilinear mapping; mapping latitude/longitude checked against each met_em XLAT_M/XLONG_M grid",
        "sources": files,
        "profiles_sha256": sha256(output / "metgrid_species_profiles.csv"),
        "summary_sha256": sha256(output / "metgrid_species_summary.csv"),
        "limitations": [
            "metgrid levels are not the same as WRF bottom_top levels or the 22-level shadow coordinate; no levelwise cross-stage equality is asserted.",
            "OFF and HYDRO/LIQUID metgrid files come from distinct recorded preparation paths; see source receipts.",
        ],
    }
    (output / "metgrid_extraction_receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
