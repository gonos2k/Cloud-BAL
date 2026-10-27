#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

ROOT = Path(
    "/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914"
)
REPO = Path(__file__).resolve().parents[3]
BASE = REPO / "docs/evidence/precip_transitions_20261027/native_trace/final-v2"
FIELDS = ("QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP", "T", "P", "PB")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    OUT = parser.parse_args().output_dir.resolve()
    if OUT.exists():
        raise FileExistsError(f"refusing to reuse existing output directory: {OUT}")
    OUT.mkdir(parents=True)
    for name in (
        "initial_species_profiles.csv",
        "initial_species_summary.csv",
        "extraction_receipt.json",
    ):
        if (OUT / name).exists():
            raise FileExistsError(f"refusing to overwrite {OUT/name}")
    MAP = BASE / "losthit_mapping.csv"
    with MAP.open() as f:
        m = list(csv.DictReader(f))
    points = {}
    for r in m:
        rank = int(r["losthit_rank"])
        points.setdefault(rank, []).append(r)
    assert len(points) == 20 and all(len(v) == 4 for v in points.values())
    # Validate the saved interpolation stencil against its target coordinates.
    with Dataset(ROOT / "off/run/wrfout_d01_2026-08-16_12:00:00") as grid:
        lat = np.asarray(grid["XLAT"][0])
        lon = np.asarray(grid["XLONG"][0])
        for rank, corners in points.items():
            weights = np.array([float(c["weight"]) for c in corners])
            ylat = np.array(
                [lat[int(c["native_j"]), int(c["native_i"])] for c in corners]
            )
            ylon = np.array(
                [lon[int(c["native_j"]), int(c["native_i"])] for c in corners]
            )
            if (
                abs(float(weights @ ylat) - float(corners[0]["lat"])) > 1e-8
                or abs(float(weights @ ylon) - float(corners[0]["lon"])) > 1e-8
            ):
                raise RuntimeError(f"mapping coordinates mismatch at point {rank}")
    rows = []
    checks = []
    files = []
    stage_profiles = {}
    for arm in ("off", "hydro", "liquid"):
        for stage, fn in [
            ("wrfinput", "wrfinput_d01"),
            ("wrfout_12", "wrfout_d01_2026-08-16_12:00:00"),
        ]:
            path = ROOT / arm / "run" / fn
            files.append(
                {
                    "arm": arm.upper(),
                    "stage": stage,
                    "path": str(path),
                    "size": path.stat().st_size,
                    "sha256": sha(path),
                }
            )
            with Dataset(path) as ds:
                if not np.array_equal(ds["XLAT"][0], lat) or not np.array_equal(ds["XLONG"][0], lon):
                    raise RuntimeError(f"coordinate grid differs from mapping grid: {path}")
                expected_dims = ("Time", "bottom_top", "south_north", "west_east")
                if "Times" not in ds.variables:
                    raise RuntimeError(f"missing Times: {path}")
                from netCDF4 import chartostring

                times = chartostring(ds["Times"][:]).tolist()
                if times != ["2026-08-16_12:00:00"]:
                    raise RuntimeError(f"unexpected time {times}: {path}")
                shape = (
                    len(ds.dimensions["bottom_top"]),
                    len(ds.dimensions["south_north"]),
                    len(ds.dimensions["west_east"]),
                )
                if shape != (39, 282, 234):
                    raise RuntimeError(f"unexpected dimensions {shape}: {path}")
                fields = {}
                for name in FIELDS:
                    if name not in ds.variables:
                        raise RuntimeError(f"missing {name}: {path}")
                    var = ds[name]
                    if var.dimensions != expected_dims or var.shape != (
                        1,
                        39,
                        282,
                        234,
                    ):
                        raise RuntimeError(
                            f"unexpected {name} shape/dimensions: {path}"
                        )
                    units = str(getattr(var, "units", "")).strip()
                    wanted = (
                        "K"
                        if name == "T"
                        else "Pa" if name in ("P", "PB") else "kg kg-1"
                    )
                    if units != wanted:
                        raise RuntimeError(f"unexpected {name} units {units!r}: {path}")
                    data = np.ma.asarray(var[0])
                    if (
                        np.ma.getmaskarray(data).any()
                        or not np.isfinite(data.filled(np.nan)).all()
                    ):
                        raise RuntimeError(f"masked/nonfinite {name}: {path}")
                    fields[name] = data
                stage_profiles[(arm.upper(), stage)] = {name: [] for name in FIELDS}
                for rank, corners in points.items():
                    for k in range(39):
                        vals = {}
                        for name in FIELDS:
                            corner_vals = [
                                float(
                                    fields[name][
                                        k, int(c["native_j"]), int(c["native_i"])
                                    ]
                                )
                                for c in corners
                            ]
                            weights = np.array([float(c["weight"]) for c in corners])
                            vals[name] = float(np.dot(weights, corner_vals))
                            stage_profiles[(arm.upper(), stage)][name].append(
                                vals[name]
                            )
                        r0 = corners[0]
                        row = {
                            "arm": arm.upper(),
                            "stage": stage,
                            "losthit_rank": rank,
                            "target_flat_index_yx": r0["target_flat_index_yx"],
                            "lat": r0["lat"],
                            "lon": r0["lon"],
                            "bottom_top_k": k,
                            **{n: vals[n] for n in FIELDS},
                        }
                        rows.append(row)
    stage_equality = []
    for arm in ("OFF", "HYDRO", "LIQUID"):
        for name in FIELDS:
            a = np.asarray(stage_profiles[(arm, "wrfinput")][name])
            b = np.asarray(stage_profiles[(arm, "wrfout_12")][name])
            stage_equality.append(
                {
                    "arm": arm,
                    "field": name,
                    "exact_equal": bool(np.array_equal(a, b)),
                    "max_abs_difference": float(np.max(np.abs(a - b))),
                }
            )
    fields = rows[0].keys()
    with (OUT / "initial_species_profiles.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    summaries = []
    # Species metrics over 20 points x all 39 levels; aggregate each input/history.
    for stage in ("wrfinput", "wrfout_12"):
        for name in (
            "QRAIN",
            "QSNOW",
            "QVAPOR",
            "QCLOUD",
            "QICE",
            "QGRAUP",
            "T",
            "P",
            "PB",
        ):
            a = {
                arm: np.array(
                    [r[name] for r in rows if r["stage"] == stage and r["arm"] == arm]
                )
                for arm in ("OFF", "HYDRO", "LIQUID")
            }
            ref = a["OFF"]
            for arm in ("HYDRO", "LIQUID"):
                delta = a[arm] - ref
                summaries.append(
                    {
                        "stage": stage,
                        "field": name,
                        "arm": arm,
                        "n": len(delta),
                        "off_mean": float(ref.mean()),
                        "arm_mean": float(a[arm].mean()),
                        "mean_delta": float(delta.mean()),
                        "mean_abs_delta": float(np.abs(delta).mean()),
                        "max_abs_delta": float(np.abs(delta).max()),
                        "exact_equal": bool(np.array_equal(a[arm], ref)),
                        "off_nonzero_count": int(np.count_nonzero(ref)),
                        "arm_nonzero_count": int(np.count_nonzero(a[arm])),
                    }
                )
    with (OUT / "initial_species_summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=summaries[0].keys())
        w.writeheader()
        w.writerows(summaries)
    # Integrity and stage inventory.
    for item in files:
        if sha(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"input changed: {item['path']}")
    receipt = {
        "source_hashes_unchanged_after_read": True,
        "all_native_grids_equal": True,
        "status": "PASS_SCOPED_WRFINPUT_WRFOUT_POINT_EXTRACTION",
        "point_mapping_csv": str(MAP),
        "point_mapping_sha256": sha(MAP),
        "point_count": len(points),
        "corners_per_point": 4,
        "levels": 39,
        "interpolation": "bilinear from archived final-v2 corner/weight mapping; no remapping recomputed",
        "files": files,
        "per_field_wrfinput_to_wrfout12_equality": stage_equality,
        "csv_sha256": sha(OUT / "initial_species_profiles.csv"),
        "summary_csv_sha256": sha(OUT / "initial_species_summary.csv"),
        "lineage_note": "Upstream paired preparation products are described in Cloud-BAL/scratch/cp02_actual12_liquid_wps.HisIOM/PAIR_RECEIPT.json; this extractor focuses on the six-hour archive and does not claim a specific QR/QS assignment operation.",
        "limitations": [
            "Point extraction compares archived initial and first history states. Upstream provenance is in separate archived receipts and requires a separate source-field comparison to identify the exact species assignment.",
            "Fields are bilinearly interpolated to 20 canonical points from four native corners; this summarizes collocated state, not every grid cell.",
            "Saved state differences cannot identify the physical process or code operation that caused them.",
        ],
    }
    (OUT / "extraction_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "receipt": str(OUT / "extraction_receipt.json"),
                "summaries": [s for s in summaries if s["field"] in ("QRAIN", "QSNOW")],
                "receipt_sha256": sha(OUT / "extraction_receipt.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
