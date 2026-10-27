#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(
    "/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_actual12_liquid_wps.HisIOM"
)
MAP = (
    REPO
    / "docs/evidence/precip_transitions_20261027/native_trace/final-v2/losthit_mapping.csv"
)
PAYLOAD = Path(
    "/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_maintained_derived_O0_qej27s72/matched_control_chain12_O0.ym17bs9h/prepared/payload.nc"
)
ANCHOR = ROOT / "source_anchor.sha256"


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    outdir = parser.parse_args().output_dir.resolve()
    if outdir.exists():
        raise FileExistsError(f"refusing to reuse existing output directory: {outdir}")
    outdir.mkdir(parents=True)
    if sha(PAYLOAD) != ANCHOR.read_text().split()[0]:
        raise RuntimeError("prepared payload does not match source_anchor.sha256")
    points = {}
    for r in csv.DictReader(MAP.open()):
        points[int(r["losthit_rank"])] = r
    out = []
    source = []
    payload_matches = {}
    for arm in ("HYDRO", "LIQUID_RADAR_RH1"):
        path = ROOT / f"{arm}_vapor2.wps.shadow.nc"
        source.append(
            {
                "arm": arm,
                "path": str(path),
                "sha256": sha(path),
                "size": path.stat().st_size,
            }
        )
        with Dataset(path) as d:
            if int(d.getncattr("valid_time_epoch")) != 1786881600:
                raise RuntimeError(f"unexpected valid time: {path}")
            for name in ("background_rain", "background_snow", "candidate_rain", "candidate_snow"):
                var = d[name]
                data = np.ma.asarray(var[:])
                if var.dimensions != ("z", "y", "x") or var.shape != (22, 283, 235):
                    raise RuntimeError(f"unexpected shape: {name}: {path}")
                if str(var.units) != "kg kg-1 dryair":
                    raise RuntimeError(f"unexpected units: {name}: {path}")
                if np.ma.getmaskarray(data).any() or not np.isfinite(data).all() or (data < 0).any():
                    raise RuntimeError(f"invalid values: {name}: {path}")
            lat = np.asarray(d["latitude"][:])
            lon = np.asarray(d["longitude"][:])
            for rank, p in points.items():
                dd = (lat - float(p["lat"])) ** 2 + (
                    (lon - float(p["lon"])) * np.cos(np.deg2rad(float(p["lat"])))
                ) ** 2
                j, i = np.unravel_index(np.nanargmin(dd), dd.shape)
                if (
                    abs(float(lat[j, i]) - float(p["lat"])) > 1e-8
                    or abs(float(lon[j, i]) - float(p["lon"])) > 1e-8
                ):
                    raise RuntimeError(f"no exact shadow grid match point {rank}")
                for k in range(len(d.dimensions["z"])):
                    row = {
                        "arm": arm,
                        "losthit_rank": rank,
                        "lat": float(lat[j, i]),
                        "lon": float(lon[j, i]),
                        "shadow_j": int(j),
                        "shadow_i": int(i),
                        "z_index": k,
                        "pressure_pa": float(d["pressure"][k]),
                    }
                    for species in ("rain", "snow"):
                        for phase in ("background", "candidate"):
                            row[f"{phase}_{species}"] = float(
                                d[f"{phase}_{species}"][k, j, i]
                            )
                    out.append(row)
    fields = out[0].keys()
    with (outdir / "shadow_species_profiles.csv").open("x", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    summaries = []
    for species in ("rain", "snow"):
        for arm in ("HYDRO", "LIQUID_RADAR_RH1"):
            r = [x for x in out if x["arm"] == arm]
            b = np.array([x[f"background_{species}"] for x in r])
            c = np.array([x[f"candidate_{species}"] for x in r])
            summaries.append(
                {
                    "arm": arm,
                    "species": species,
                    "n": len(b),
                    "background_mean": float(b.mean()),
                    "candidate_mean": float(c.mean()),
                    "mean_delta_candidate_minus_background": float((c - b).mean()),
                    "mean_abs_delta": float(np.abs(c - b).mean()),
                    "max_abs_delta": float(np.abs(c - b).max()),
                    "exact_equal": bool(np.array_equal(b, c)),
                }
            )
    with (outdir / "shadow_species_summary.csv").open("x", newline="") as f:
        w = csv.DictWriter(f, fieldnames=summaries[0].keys())
        w.writeheader()
        w.writerows(summaries)
    with Dataset(PAYLOAD) as payload, Dataset(
        ROOT / "HYDRO_vapor2.wps.shadow.nc"
    ) as shadow:
        for species in ("rain", "snow"):
            receipt_match = bool(
                np.array_equal(
                    np.asarray(payload[species][0]),
                    np.asarray(shadow[f"background_{species}"][:]),
                )
            )
            if not receipt_match:
                raise RuntimeError(
                    f"prepared payload {species} differs from shadow background"
                )
            payload_matches[species] = receipt_match
    for item in source:
        if sha(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"input changed: {item['path']}")
    receipt = {
        "valid_time_utc": "2026-08-16T12:00:00Z",
        "source_hashes_unchanged_after_read": True,
        "status": "PASS_EXACT_COORDINATE_SHADOW_EXTRACTION",
        "point_mapping": str(MAP),
        "point_mapping_sha256": sha(MAP),
        "exact_point_count": len(points),
        "vertical_levels": 22,
        "coordinate_matching": "exact latitude/longitude match in shadow grid for every canonical point; no vertical remapping",
        "sources": source,
        "prepared_payload": {
            "path": str(PAYLOAD),
            "sha256": sha(PAYLOAD),
            "source_anchor_sha256": sha(ANCHOR),
            "source_anchor_matches": sha(PAYLOAD) == ANCHOR.read_text().split()[0],
        },
        "payload_to_hydro_shadow_background_exact": payload_matches,
        "pair_receipt_sha256": sha(ROOT / "PAIR_RECEIPT.json"),
        "thermo_receipt_sha256": sha(ROOT / "THERMO_RECEIPT.json"),
        "outputs": {
            "profiles_sha256": sha(outdir / "shadow_species_profiles.csv"),
            "summary_sha256": sha(outdir / "shadow_species_summary.csv"),
        },
        "limitations": [
            "Shadow candidate/background fields are diagnostic products, not the ordinary WPS output itself.",
            "The 22 shadow levels and 39 WRF mass levels are different vertical grids; no level-by-level numeric equality is asserted.",
            "The ordinary OFF WPS stage is not archived as an inspectable NetCDF shadow for this comparison.",
        ],
    }
    (outdir / "shadow_extraction_receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
