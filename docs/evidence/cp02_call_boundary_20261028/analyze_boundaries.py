#!/usr/bin/env python3
"""Compare archived LAPSPREP GDB captures with shadow endpoints and each other."""

import argparse
import csv
import gzip
import hashlib
import json
import math
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

import netCDF4
import numpy as np


REPO = Path(__file__).resolve().parents[3]
ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50")
DEFAULT_POINTS = REPO / "docs/evidence/cp02_initial_species_20261027/final/shadow/shadow_species_profiles.csv"
DEFAULT_HYDRO_SHADOW = ROOT / "Cloud-BAL/scratch/cp02_actual12_liquid_wps.HisIOM/HYDRO_vapor2.wps.shadow.nc"
DEFAULT_LIQUID_SHADOW = ROOT / "Cloud-BAL/scratch/cp02_actual12_liquid_wps.HisIOM/LIQUID_RADAR_RH1_vapor2.wps.shadow.nc"
EXPECTED = {
    "HYDRO": {
        "shadow_sha256": "c1f5d039ac73c90cb6b21dd619ebc5774f3b6c7387c9b9701af4360fb635f2cb",
        "points": 20,
        "levels": 22,
        "pipelines": 2,
    },
    "LIQUID_RADAR_RH1": {
        "shadow_sha256": "12a9cbc7b895bf5dd7020a85b4590f2f1ef334f74c0505865a961be30ab57bac",
        "points": 20,
        "levels": 22,
        "pipelines": 2,
    },
}
FIELDS = (
    "vapor",
    "cloud_water",
    "cloud_ice",
    "rain",
    "snow",
    "graupel",
    "temperature",
    "pressure",
)
MIXING_RATIO_FIELDS = {"vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel"}
CANONICAL_POINTS = {}
PIPELINE_CALLS = {("primary", 1), ("replay", 2)}
DERIVE_CALLS = {
    "HYDRO": {("primary", 1), ("replay", 2)},
    "LIQUID_RADAR_RH1": {
        ("primary", 1), ("primary", 2), ("primary", 3),
        ("replay", 4), ("replay", 5), ("replay", 6),
    },
}
STAGES = {
    "pipeline_entry_state_in",
    "pipeline_return_candidate_out",
    "derive_entry_state_in",
    "derive_return_state_out",
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def f32_bytes(value):
    return struct.pack("<f", float(value))


def load_points(path):
    points = {}
    csv_rows = {arm: {} for arm in EXPECTED}
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"arm", "shadow_i", "shadow_j", "z_index", "lat", "lon"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"points CSV needs columns {sorted(required)}")
        for row in reader:
            arm = row["arm"].strip().upper()
            if arm not in EXPECTED:
                continue
            i, j, z = int(row["shadow_i"]), int(row["shadow_j"]), int(row["z_index"])
            key = (i, j, z)
            if key in csv_rows[arm]:
                raise ValueError(f"duplicate point row: {arm} {key}")
            csv_rows[arm][key] = row
            point = {
                "shadow_i": i,
                "shadow_j": j,
                "fortran_i": i + 1,
                "fortran_j": j + 1,
                "lat": row["lat"],
                "lon": row["lon"],
                "losthit_rank": row.get("losthit_rank", ""),
            }
            if (i, j) in points and points[(i, j)] != point:
                raise ValueError(f"canonical coordinate metadata differs between arms at {(i, j)}")
            points[(i, j)] = point
    for arm, expected in EXPECTED.items():
        rows = csv_rows[arm]
        if len(rows) != expected["points"] * expected["levels"]:
            raise ValueError(f"{arm}: expected 440 canonical rows, found {len(rows)}")
        point_coords = {(i, j) for i, j, _ in rows}
        if len(point_coords) != expected["points"]:
            raise ValueError(f"{arm}: expected 20 unique canonical points")
        for i, j in point_coords:
            if {(a, b, z) for a, b, z in rows if a == i and b == j} != {
                (i, j, z) for z in range(expected["levels"])
            }:
                raise ValueError(f"{arm}: point {(i, j)} lacks exactly z_index 0..21")
    return points, csv_rows


def validate_capture(path, expected_arm):
    capture = load_json(path)
    if capture.get("status") != "CAPTURE_COMPLETE" or capture.get("inferior_exit_code") != 0:
        raise ValueError(f"{expected_arm}: capture is incomplete or inferior did not exit 0")
    if capture.get("arm") != expected_arm:
        raise ValueError(f"{expected_arm}: capture arm is {capture.get('arm')!r}")
    if capture.get("expected_binary_sha256") != "dbea173ec059afba40ae2d46193e5f5f33a63c18d02d4fd5db5ac23b504e2e65":
        raise ValueError(f"{expected_arm}: wrong pinned executable digest")
    counts = capture["counts"]
    if counts["pipeline_entries"] != 2 or counts["pipeline_returns"] != 2:
        raise ValueError(f"{expected_arm}: expected two balanced pipeline calls")
    expected_derives = 2 if expected_arm == "HYDRO" else 6
    if counts["derive_entries"] != expected_derives or counts["derive_returns"] != expected_derives:
        raise ValueError(f"{expected_arm}: expected {expected_derives} balanced derive calls")
    stage_counts = Counter(record.get("stage") for record in capture.get("records", []))
    if set(stage_counts) != STAGES:
        raise ValueError(f"{expected_arm}: expected exactly four known event stages")
    declared_counts = {
        "pipeline_entry_state_in": counts["pipeline_entries"],
        "pipeline_return_candidate_out": counts["pipeline_returns"],
        "derive_entry_state_in": counts["derive_entries"],
        "derive_return_state_out": counts["derive_returns"],
    }
    if any(stage_counts[stage] != count for stage, count in declared_counts.items()):
        raise ValueError(f"{expected_arm}: observed stage counts differ from declared counts")
    if capture.get("levels_captured") != 22 or len(capture.get("records", [])) != (
        counts["pipeline_entries"] * 2 + counts["derive_entries"] * 2
    ):
        raise ValueError(f"{expected_arm}: record/level capture count mismatch")
    return capture


def classify_record(record):
    stack = record.get("stack", [])
    role = "replay" if any("pipeline_result_replays" in frame for frame in stack) else "primary"
    return role


def index_records(capture):
    """Index events after checking keys and their chronological call order."""
    indexed = defaultdict(dict)
    observed_order = []
    for record in capture["records"]:
        stage = record["stage"]
        role = classify_record(record)
        call = record["call_number"]
        if type(call) is not int:
            raise ValueError(f"{stage}: call number must be an integer")
        key = (role, call)
        if key in indexed[stage]:
            raise ValueError(f"duplicate event {stage} {key}")
        indexed[stage][key] = record
        observed_order.append((stage, role, call))
    if set(indexed) != STAGES:
        raise ValueError("capture must contain exactly four known event stages")
    arm = capture.get("arm")
    expected = {
        "pipeline_entry_state_in": PIPELINE_CALLS,
        "pipeline_return_candidate_out": PIPELINE_CALLS,
        "derive_entry_state_in": DERIVE_CALLS.get(arm, set()),
        "derive_return_state_out": DERIVE_CALLS.get(arm, set()),
    }
    for stage, keys in expected.items():
        if set(indexed[stage]) != keys:
            raise ValueError(f"{arm}: {stage} role/call keys differ from expected capture")
    expected_order = []
    for role, pipeline_call in (("primary", 1), ("replay", 2)):
        expected_order.append(("pipeline_entry_state_in", role, pipeline_call))
        for derive_role, derive_call in sorted(DERIVE_CALLS[arm], key=lambda item: item[1]):
            if derive_role == role:
                expected_order.extend((
                    ("derive_entry_state_in", role, derive_call),
                    ("derive_return_state_out", role, derive_call),
                ))
        expected_order.append(("pipeline_return_candidate_out", role, pipeline_call))
    if observed_order != expected_order:
        raise ValueError(f"{arm}: event order differs from expected call chronology")
    if not any("pipeline_result_replays" in f for r in capture["records"] for f in r.get("stack", [])):
        raise ValueError("second pipeline call lacks pipeline_result_replays stack evidence")
    return indexed


def sample_map(record):
    result = {}
    for point in record["points"]:
        i, j = int(point["shadow_i_zero_based"]), int(point["shadow_j_zero_based"])
        canonical = CANONICAL_POINTS.get((i, j))
        if canonical is None:
            raise ValueError(f"capture point {(i, j)} is absent from the canonical map")
        if (int(point["fortran_i"]), int(point["fortran_j"])) != (i + 1, j + 1):
            raise ValueError(f"capture point {(i, j)} has incorrect Fortran index conversion")
        if (point["lat"], point["lon"]) != (canonical["lat"], canonical["lon"]):
            raise ValueError(f"capture point {(i, j)} differs from canonical coordinates")
        if len(point["levels"]) != 22:
            raise ValueError(f"{record['stage']}: expected 22 levels at {(i, j)}")
        for level in point["levels"]:
            z = int(level["fortran_k"]) - 1
            if not 0 <= z < 22:
                raise ValueError(f"invalid captured Fortran level {z + 1}")
            key = (i, j, z)
            if key in result:
                raise ValueError(f"duplicate capture sample {key}")
            result[key] = level
    if len(result) != 20 * 22:
        raise ValueError(f"{record['stage']}: expected 440 samples, found {len(result)}")
    return result


def nc_value(dataset, endpoint, field, key):
    i, j, z = key
    if field == "pressure":
        variable_name = "pressure"
        indices = (z,)
    else:
        variable_name = f"{endpoint}_{field}"
        indices = (z, j, i)
    if variable_name not in dataset.variables:
        return None
    value = dataset.variables[variable_name][indices]
    if np.ma.is_masked(value):
        raise ValueError(f"masked archive value {variable_name}{indices}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"nonfinite archive value {variable_name}{indices}")
    return f32_bytes(number)


def compare_records(left, right):
    left_map, right_map = sample_map(left), sample_map(right)
    counts = {field: 0 for field in FIELDS}
    for key in left_map:
        a, b = left_map[key], right_map[key]
        if not set(FIELDS).issubset(a) or not set(FIELDS).issubset(b):
            raise ValueError("captured state omitted one or more required fields")
        for field in FIELDS:
            if a[field]["raw_bytes_le_hex"] != b[field]["raw_bytes_le_hex"]:
                counts[field] += 1
    return {"compared_samples_per_field": 440, "bitwise_mismatch_count": counts}


def validate_float_bytes(record):
    for point in record["points"]:
        for level in point["levels"]:
            for field in FIELDS:
                sample = level[field]
                raw = bytes.fromhex(sample["raw_bytes_le_hex"])
                if len(raw) != 4 or struct.unpack("<f", raw)[0].hex() != sample["float_hex"]:
                    raise ValueError(
                        f"{record['stage']} has inconsistent float/raw bytes for {field}"
                    )


def compare_archive(record, dataset, endpoint):
    values = sample_map(record)
    counts = {}
    unavailable = []
    for field in FIELDS:
        if field != "pressure" and f"{endpoint}_{field}" not in dataset.variables:
            unavailable.append(field)
            continue
        mismatch = 0
        for key, level in values.items():
            expected = nc_value(dataset, endpoint, field, key)
            actual = level[field]["raw_bytes_le_hex"]
            mismatch += actual != expected.hex()
        counts[field] = mismatch
    return {
        "endpoint": endpoint,
        "compared_samples_per_field": 440,
        "bitwise_mismatch_count": counts,
        "unavailable_fields": unavailable,
        "exact_for_available_fields": all(value == 0 for value in counts.values()),
    }


def profile_rows(arm, indexed, dataset):
    records_by_role = []
    for stage, stage_records in indexed.items():
        for (role, call), record in stage_records.items():
            label = f"{role}_{stage.removesuffix('_state_in').removesuffix('_candidate_out')}_{call}"
            records_by_role.append((label, record))
    output = []
    for label, record in records_by_role:
        values = sample_map(record)
        for field in FIELDS:
            for z in range(22):
                numbers, changed, valid = [], 0, 0
                background_variable = "pressure" if field == "pressure" else f"background_{field}"
                has_background = background_variable in dataset.variables
                for key, level in values.items():
                    if key[2] != z:
                        continue
                    number = struct.unpack("<f", bytes.fromhex(level[field]["raw_bytes_le_hex"]))[0]
                    numbers.append(number)
                    if level[field]["valid"]["value"]:
                        valid += 1
                    if has_background:
                        background = nc_value(dataset, "background", field, key)
                        changed += level[field]["raw_bytes_le_hex"] != background.hex()
                if not numbers:
                    raise ValueError(f"no values for profile {arm}/{label}/{field}/{z}")
                output.append({
                    "arm": arm,
                    "role": label,
                    "field": field,
                    "z_index": z,
                    "sample_count": len(numbers),
                    "valid_count": valid,
                    "mean_native": sum(numbers) / len(numbers),
                    "mean_g_per_kg": sum(numbers) / len(numbers) * 1000.0
                    if field in MIXING_RATIO_FIELDS else "",
                    "min_native": min(numbers),
                    "max_native": max(numbers),
                    "changed_from_shadow_background_count": changed if has_background else "",
                    "background_comparison": "available" if has_background else "unavailable",
                })
    return output


def check_csv_against_netcdf(arm, rows, dataset):
    mismatches = {field: 0 for field in ("rain", "snow")}
    for key, row in rows[arm].items():
        i, j, z = key
        for field in ("rain", "snow"):
            for endpoint in ("background", "candidate"):
                nc = nc_value(dataset, endpoint, field, key)
                csv_value = f32_bytes(float(row[f"{endpoint}_{field}"]))
                mismatches[f"{endpoint}_{field}"] = mismatches.get(f"{endpoint}_{field}", 0) + (
                    nc != csv_value
                )
    return mismatches


def main():
    global CANONICAL_POINTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hydro-capture", type=Path, required=True)
    parser.add_argument("--liquid-capture", type=Path, required=True)
    parser.add_argument("--points-csv", type=Path, default=DEFAULT_POINTS)
    parser.add_argument("--hydro-shadow", type=Path, default=DEFAULT_HYDRO_SHADOW)
    parser.add_argument("--liquid-shadow", type=Path, default=DEFAULT_LIQUID_SHADOW)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("output directory already exists: " + str(args.output_dir))
    args.output_dir.mkdir(parents=True)

    input_hashes = {str(args.points_csv): sha256(args.points_csv)}
    points, csv_rows = load_points(args.points_csv)
    if sha256(args.points_csv) != input_hashes[str(args.points_csv)]:
        raise ValueError("canonical point CSV changed while being read")
    CANONICAL_POINTS = points
    if len(points) != 20:
        raise ValueError("canonical point map does not contain exactly 20 points")
    capture_paths = {
        "HYDRO": args.hydro_capture,
        "LIQUID_RADAR_RH1": args.liquid_capture,
    }
    shadow_paths = {
        "HYDRO": args.hydro_shadow,
        "LIQUID_RADAR_RH1": args.liquid_shadow,
    }
    captures, indexed, datasets = {}, {}, {}
    summary = {
        "schema": "cp02-call-boundary-analysis-v1",
        "status": "ANALYSIS_INCOMPLETE",
        "scope": (
            "20 selected points x 22 stored shadow levels x 8 captured state fields; "
            "observed debugger values only. evaluation_state and other pipeline arguments "
            "were not captured; no domainwide budget or causal attribution is made."
        ),
        "density": "not stored in cloud_bal_state_type; no density or water-budget inference",
        "pressure_reference": "archive pressure(z) is compared at each selected x/y point without vertical remapping",
        "inputs": {
            "points_csv": {"path": str(args.points_csv), "sha256": sha256(args.points_csv)},
            "captures": {},
            "shadow_netcdf": {},
        },
        "arms": {},
    }
    profiles = []
    endpoint_mismatches = []
    endpoint_unavailable = []
    for arm in EXPECTED:
        capture_path, shadow_path = capture_paths[arm], shadow_paths[arm]
        shadow_hash = sha256(shadow_path)
        if shadow_hash != EXPECTED[arm]["shadow_sha256"]:
            raise ValueError(f"{arm}: archived shadow NetCDF hash mismatch")
        capture_hash = sha256(capture_path)
        capture = validate_capture(capture_path, arm)
        if sha256(capture_path) != capture_hash:
            raise ValueError(f"{arm}: capture JSON changed while being read")
        input_hashes[str(capture_path)] = capture_hash
        input_hashes[str(shadow_path)] = shadow_hash
        if capture.get("points_csv_sha256") != input_hashes[str(args.points_csv)]:
            raise ValueError(f"{arm}: capture used a different canonical point map")
        for record in capture["records"]:
            validate_float_bytes(record)
        dataset = netCDF4.Dataset(shadow_path, "r")
        captures[arm], indexed[arm], datasets[arm] = capture, index_records(capture), dataset
        summary["inputs"]["captures"][arm] = {"path": str(capture_path), "sha256": sha256(capture_path)}
        summary["inputs"]["shadow_netcdf"][arm] = {"path": str(shadow_path), "sha256": sha256(shadow_path)}
        baseline = indexed[arm]["pipeline_entry_state_in"][("primary", 1)]
        candidate = indexed[arm]["pipeline_return_candidate_out"][("primary", 1)]
        replay_entry = indexed[arm]["pipeline_entry_state_in"][("replay", 2)]
        replay_return = indexed[arm]["pipeline_return_candidate_out"][("replay", 2)]
        endpoint_bg = compare_archive(baseline, dataset, "background")
        endpoint_candidate = compare_archive(candidate, dataset, "candidate")
        endpoint_bg["role"] = "primary_pipeline_entry_vs_shadow_background"
        endpoint_candidate["role"] = "primary_pipeline_return_vs_shadow_candidate"
        for endpoint in (endpoint_bg, endpoint_candidate):
            if any(endpoint["bitwise_mismatch_count"].values()):
                endpoint_mismatches.append(f"{arm}:{endpoint['role']}")
            if endpoint["unavailable_fields"]:
                endpoint_unavailable.extend(
                    f"{arm}:{endpoint['role']}:{field}" for field in endpoint["unavailable_fields"]
                )
        replay_entry_cmp = compare_records(baseline, replay_entry)
        replay_return_cmp = compare_records(candidate, replay_return)
        derive_records = []
        for (role, call), entry in sorted(indexed[arm]["derive_entry_state_in"].items(), key=lambda item: item[0][1]):
            ret_key = (role, call)
            returned = indexed[arm]["derive_return_state_out"].get(ret_key)
            if returned is None:
                raise ValueError(f"{arm}: derive call {role}/{call} has no matching return")
            derive_records.append((role, call, entry, returned))
        chain = []
        for index, (role, call, entry, returned) in enumerate(derive_records):
            next_entry = None
            for next_role, next_call, candidate_entry, _ in derive_records[index + 1:]:
                if next_role == role:
                    next_entry = candidate_entry
                    break
            target = next_entry or indexed[arm]["pipeline_return_candidate_out"][
                (role, 1 if role == "primary" else 2)
            ]
            chain.append({
                "pipeline_role": role,
                "derive_call": call,
                "entry_vs_shadow_immutable_background": compare_archive(
                    entry, dataset, "background"
                ),
                "entry_vs_return": compare_records(entry, returned),
                "return_vs_next_derive_entry_or_pipeline_output": compare_records(returned, target),
                "next_boundary": "next_derive_entry" if next_entry else "pipeline_return",
            })
        arm_profiles = profile_rows(arm, indexed[arm], dataset)
        profiles.extend(arm_profiles)
        csv_vs_nc = check_csv_against_netcdf(arm, csv_rows, dataset)
        if any(csv_vs_nc.values()):
            endpoint_mismatches.append(f"{arm}:canonical_csv_vs_shadow_netcdf")
        summary["arms"][arm] = {
            "capture_status": capture["status"],
            "capture_counts": capture["counts"],
            "pipeline_roles_from_stack": {
                role: [r["stack"] for r in capture["records"]
                       if r["stage"] == "pipeline_entry_state_in" and classify_record(r) == role]
                for role in ("primary", "replay")
            },
            "shadow_csv_crosscheck_rain_snow": csv_vs_nc,
            "endpoints": {"background": endpoint_bg, "candidate": endpoint_candidate},
            "pipeline_replay_vs_primary": {
                "replay_entry_vs_primary_entry": replay_entry_cmp,
                "replay_return_vs_primary_candidate": replay_return_cmp,
            },
            "derive_chain": chain,
            "primary_candidate_change_from_shadow_background": {
                "bitwise_changed_sample_count": {
                    field: compare_archive(candidate, dataset, "background")[
                        "bitwise_mismatch_count"
                    ].get(field)
                for field in ("rain", "snow")
                },
                "mean_g_per_kg": {
                    field: sum(
                        row["mean_g_per_kg"]
                        for row in arm_profiles
                        if row["role"] == "primary_pipeline_return_1"
                        and row["field"] == field
                    ) / 22.0
                    for field in ("rain", "snow")
                },
            },
        }
        dataset.close()

    summary["cross_arm_primary_entry_state"] = compare_records(
        indexed["HYDRO"]["pipeline_entry_state_in"][("primary", 1)],
        indexed["LIQUID_RADAR_RH1"]["pipeline_entry_state_in"][("primary", 1)],
    )

    profile_path = args.output_dir / "profiles.csv"
    columns = [
        "arm", "role", "field", "z_index", "sample_count", "valid_count",
        "mean_native", "mean_g_per_kg", "min_native", "max_native",
        "changed_from_shadow_background_count", "background_comparison",
    ]
    with profile_path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(profiles)
    summary["profile_csv"] = {"path": str(profile_path), "sha256": sha256(profile_path), "rows": len(profiles)}
    summary["endpoint_mismatches"] = endpoint_mismatches
    summary["endpoint_unavailable_references"] = endpoint_unavailable
    required_fields = {"rain", "snow", "cloud_water", "cloud_ice", "graupel", "pressure"}
    if any(not required_fields.issubset(arm["endpoints"]["background"]["bitwise_mismatch_count"])
           or not required_fields.issubset(arm["endpoints"]["candidate"]["bitwise_mismatch_count"])
           for arm in summary["arms"].values()):
        raise ValueError("one or more required archived endpoint references are unavailable")
    for path, before_hash in input_hashes.items():
        if sha256(Path(path)) != before_hash:
            raise ValueError(f"input changed while analyzing: {path}")
    summary["inputs_unchanged_after_read"] = True
    if endpoint_mismatches:
        summary["status"] = "ENDPOINT_MISMATCH"
    else:
        summary["status"] = "PASS_SCOPED_AVAILABLE_ENDPOINTS"
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "profiles": len(profiles), "summary": str(summary_path)}))
    return 0 if summary["status"] == "PASS_SCOPED_AVAILABLE_ENDPOINTS" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"analysis failed closed: {exc}", file=sys.stderr)
        raise
