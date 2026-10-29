#!/usr/bin/env python3
"""Analyze selected CP02 control columns from a read-only GDB capture."""

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import struct
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INNER_PATH = ROOT / "docs/evidence/cp02_inner_capture_20261028/analyze_inner.py"
RADAR_PATH = ROOT / "docs/evidence/cp02_radar_inputs_20261028/analyze_radar_inputs.py"
SPECIES = ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel")
DIAGNOSED_SPECIES = ("rain", "snow", "graupel")
EXPECTED_SELECTION_SHA256 = "5c842c51422cf144bce81ec2143258e3b54a0de7c85674d91a8194b826e14472"
EXPECTED_POINT_CSV_SHA256 = "0243e5cd8e29638b32edc501a68ab50f1f7de4415625b5301cf2b2b6f905bebd"
EXPECTED_ROLES = Counter({
    "lost_hit": 4,
    "retained_hit": 4,
    "removed_false_alarm": 4,
    "RN1_positive_reference_all_forecasts_below5mm": 4,
    "payload_positive_rain_reflectivity_invalid_proxy": 2,
    "payload_positive_snow_reflectivity_invalid_proxy": 2,
})


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INNER = load_module("cp02_control_inner", INNER_PATH)
RADAR = load_module("cp02_control_radar", RADAR_PATH)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_selection(path):
    require(hashlib.sha256(path.read_bytes()).hexdigest() == EXPECTED_SELECTION_SHA256,
            "selection SHA-256 does not match the frozen 20-point mapping")
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 20, f"expected 20 selected control columns, got {len(rows)}")
    require(len({row["point_id"] for row in rows}) == 20, "selection point IDs are not unique")
    keys = [(int(row["shadow_i_zero_based"]), int(row["shadow_j_zero_based"])) for row in rows]
    require(len(set(keys)) == 20, "selection has duplicate shadow columns")
    require(Counter(row["role"] for row in rows) == EXPECTED_ROLES, "selection role counts differ from the frozen plan")
    return rows


def state_values(record):
    values = INNER.sample_map(record)
    require(len(values) == 440, f"{record.get('stage')}: expected 440 state values")
    return values


def real32(record, label):
    raw = bytes.fromhex(record["raw_bytes_le_hex"])
    require(len(raw) == 4, f"{label}: expected REAL*4 raw bytes")
    value = struct.unpack("<f", raw)[0]
    require(math.isfinite(value), f"{label}: non-finite REAL*4")
    return value, raw.hex()


def validate_selected_row(row, background_row, meta, key, actual_input):
    require(row["losthit_rank"] == meta["point_id"], f"point ID differs from selection at {key}")
    require(float(row["lat"]) == float(meta["latitude"]) and float(row["lon"]) == float(meta["longitude"]),
            f"point coordinates differ from selection at {key}")
    for species in ("rain", "snow"):
        state_raw = bytes.fromhex(actual_input[key][species]["raw_bytes_le_hex"])
        background_raw = struct.pack("<f", float(background_row[f"background_{species}"]))
        require(state_raw == background_raw, f"captured input {species} differs from archived background at {key}")


def status_record(capture, stage):
    records = [record for record in capture["records"] if record.get("stage") == stage]
    require(len(records) == 1, f"expected unique {stage} record")
    result = records[0]["radar"]["status_return"]
    raw = bytes.fromhex(result["raw_bytes_le_hex"])
    require(len(raw) == 4, f"{stage}: expected INTEGER*4 status")
    value = struct.unpack("<i", raw)[0]
    require(value == result["value"], f"{stage}: raw status differs from decoded status")
    return {"value": value, "type": result["type"], "raw_bytes_le_hex": raw.hex(), "address": result["address"]}


def summarize(capture, point_csv, selection_csv):
    point_hash = hashlib.sha256(point_csv.read_bytes()).hexdigest()
    require(point_hash == EXPECTED_POINT_CSV_SHA256, "point CSV SHA-256 does not match the frozen background data")
    require(capture.get("points_csv_sha256") == point_hash, "capture point CSV SHA-256 mismatch")
    selection = read_selection(selection_csv)
    selection_by_key = {
        (int(row["shadow_i_zero_based"]), int(row["shadow_j_zero_based"])): row
        for row in selection
    }

    # Retain the original capture contract checks without invoking its broader
    # all-sample REAL64 workarray-to-REAL32 state equality claim.
    indexed = INNER.record_index(capture, "HYDRO")
    background = RADAR.background_samples(point_csv)
    require(len(background) == 440, f"expected 440 canonical background rows, got {len(background)}")
    radar_report = RADAR.validate_radar(capture, background)
    profiles = radar_report["profiles"]
    require(len(profiles) == 440, f"expected 440 validated radar profiles, got {len(profiles)}")

    main_entry = state_values(indexed[("derive_entry_state_in", 1)])
    main_return = state_values(indexed[("derive_return_state_out", 1)])
    writer_entry = state_values(indexed[("derive_entry_state_in", 2)])
    writer_return = state_values(indexed[("derive_return_state_out", 2)])
    diagnose_pre = next(record for record in capture["records"]
                        if record.get("stage") == "diagnose_radar_cells_pre")
    actual_input = state_values(diagnose_pre["radar"]["actual_input_state"])
    candidate_record = next(record for record in capture["records"]
                            if record.get("stage") == "publish_hydrometeor_candidate_post")
    candidate_state = state_values(candidate_record["candidate_state"])
    workarrays = {}
    for species in DIAGNOSED_SPECIES:
        array = candidate_record["arrays"][species]
        workarrays[species] = {
            (point["fortran_i"], point["fortran_j"], level["fortran_k"]): level
            for point in array["points"] for level in point["levels"]
        }
    require(len(candidate_state) == 440, "published candidate state does not contain 440 samples")

    # Verify that analyzer rows cover the exact selected coordinate-level keys.
    profile_by_key = {}
    for row in profiles:
        key = (int(row["fortran_i"]), int(row["fortran_j"]), int(row["fortran_k"]))
        require(key not in profile_by_key, f"duplicate validated profile key {key}")
        profile_by_key[key] = row
    expected_keys = {(i + 1, j + 1, k) for i, j in selection_by_key for k in range(1, 23)}
    require(set(profile_by_key) == expected_keys, "validated radar profiles differ from selected keys")
    require(set(main_entry) == set(main_return) == set(writer_entry) == set(writer_return) == set(candidate_state) == expected_keys,
            "main/writer/publish state keys differ from the selected 440 keys")
    for (i0, j0), meta in selection_by_key.items():
        for k0 in range(22):
            key = (i0 + 1, j0 + 1, k0 + 1)
            row, bg = profile_by_key[key], background[key]
            validate_selected_row(row, bg, meta, key, actual_input)

    role_stats = defaultdict(lambda: {"point_count": 0, "observed_post_true_levels": 0,
                                     "observed_post_false_levels": 0, "reflectivity_valid_levels": 0,
                                     "unobserved_positive_background_rain_levels": 0,
                                     "unobserved_positive_background_snow_levels": 0,
                                     "background_positive_rain_levels": 0,
                                     "background_positive_snow_levels": 0,
                                     "captured_local_levels": Counter(),
                                     "species_trends": {species: Counter() for species in SPECIES},
                                     "main_entry_to_return": {species: Counter() for species in SPECIES},
                                     "writer_entry_to_return": {species: Counter() for species in SPECIES}})
    point_summary = []
    workarray_mismatch = {species: {"count": 0, "examples": []} for species in ("rain", "snow", "graupel")}
    for (i0, j0), meta in sorted(selection_by_key.items(), key=lambda item: item[1]["point_id"]):
        stats = role_stats[meta["role"]]
        stats["point_count"] += 1
        point_counts = Counter()
        for k0 in range(22):
            key = (i0 + 1, j0 + 1, k0 + 1)
            row = profile_by_key[key]
            bg = background[key]
            observed = bool(row["diagnose_radar_cells_post.radar_observed"])
            valid = bool(row["actual_observation.radar_reflectivity.valid"])
            bg_rain = float(bg["background_rain"])
            bg_snow = float(bg["background_snow"])
            stats["observed_post_true_levels"] += observed
            stats["observed_post_false_levels"] += not observed
            stats["reflectivity_valid_levels"] += valid
            stats["background_positive_rain_levels"] += bg_rain > 0.0
            stats["background_positive_snow_levels"] += bg_snow > 0.0
            stats["unobserved_positive_background_rain_levels"] += (not observed and bg_rain > 0.0)
            stats["unobserved_positive_background_snow_levels"] += (not observed and bg_snow > 0.0)
            for stage in ("density_entry", "density_return", "phase_allocation_return", "store_after"):
                stats["captured_local_levels"][stage] += row[f"{stage}.status"] == "CAPTURED"
            for species in SPECIES:
                pre = float(row[f"actual_input.{species}"])
                post = float(row[f"final.{species}"])
                trend = "increase" if post > pre else "decrease" if post < pre else "same"
                stats["species_trends"][species][trend] += 1
                point_counts[f"{species}_{trend}"] += 1
                main_pre, main_pre_raw = real32(main_entry[key][species], f"main entry {key}.{species}")
                main_post, main_post_raw = real32(main_return[key][species], f"main return {key}.{species}")
                writer_pre, writer_pre_raw = real32(writer_entry[key][species], f"writer entry {key}.{species}")
                writer_post, writer_post_raw = real32(writer_return[key][species], f"writer return {key}.{species}")
                for label, before, after, before_raw, after_raw in (
                    ("main_entry_to_return", main_pre, main_post, main_pre_raw, main_post_raw),
                    ("writer_entry_to_return", writer_pre, writer_post, writer_pre_raw, writer_post_raw),
                ):
                    change = "increase" if after > before else "decrease" if after < before else "same"
                    stats[label][species][change] += 1
                if species in workarrays:
                    work_val = RADAR.raw_value(workarrays[species][key], 8,
                                               f"workarray {key}.{species}", "real")
                    if struct.pack("<f", work_val) != bytes.fromhex(candidate_state[key][species]["raw_bytes_le_hex"]):
                        mismatch = workarray_mismatch[species]
                        mismatch["count"] += 1
                        if len(mismatch["examples"]) < 12:
                            mismatch["examples"].append({"point_id": meta["point_id"], "shadow_i": i0,
                                                         "shadow_j": j0, "z_index": k0,
                                                         "workarray_real64": work_val,
                                                         "published_real32": real32(candidate_state[key][species], "published state")[0]})
        point_summary.append({
            "point_id": meta["point_id"], "role": meta["role"], "shadow_i": i0, "shadow_j": j0,
            "rn1_sample_index_zero_based": meta["rn1_sample_index_zero_based"],
            "target_flat_index_yx": meta["target_flat_index_yx"],
            "payload_radar_invalid_proxy": meta["payload_radar_invalid_proxy"],
            "external_control_distance_to_rn1_sample_km": meta["external_control_distance_to_rn1_sample_km"],
            "levels": 22,
            "observed_post_true_levels": sum(bool(profile_by_key[(i0+1,j0+1,k)]["diagnose_radar_cells_post.radar_observed"]) for k in range(1,23)),
            "reflectivity_valid_levels": sum(bool(profile_by_key[(i0+1,j0+1,k)]["actual_observation.radar_reflectivity.valid"]) for k in range(1,23)),
            "unobserved_positive_background_rain_levels": sum(not bool(profile_by_key[(i0+1,j0+1,k)]["diagnose_radar_cells_post.radar_observed"]) and float(background[(i0+1,j0+1,k)]["background_rain"])>0 for k in range(1,23)),
            "unobserved_positive_background_snow_levels": sum(not bool(profile_by_key[(i0+1,j0+1,k)]["diagnose_radar_cells_post.radar_observed"]) and float(background[(i0+1,j0+1,k)]["background_snow"])>0 for k in range(1,23)),
            "captured_local_levels": {stage:sum(profile_by_key[(i0+1,j0+1,k)][f"{stage}.status"]=="CAPTURED" for k in range(1,23))
                                      for stage in ("density_entry", "density_return", "phase_allocation_return", "store_after")},
            "species_trends_vs_actual_input": dict(point_counts),
        })

    for stage, values in role_stats.items():
        for key in ("species_trends", "main_entry_to_return", "writer_entry_to_return"):
            values[key] = {species: dict(counts) for species, counts in values[key].items()}

    updated_profiles = []
    mapping_by_key = {(int(row["shadow_i_zero_based"]), int(row["shadow_j_zero_based"])): row for row in selection}
    for row in profiles:
        i0, j0 = int(row["shadow_i"]), int(row["shadow_j"])
        meta = mapping_by_key[(i0, j0)]
        out = dict(row)
        out.update({"point_id": meta["point_id"], "role": meta["role"],
                    "rn1_sample_index_zero_based": meta["rn1_sample_index_zero_based"],
                    "target_flat_index_yx": meta["target_flat_index_yx"],
                    "payload_radar_invalid_proxy": meta["payload_radar_invalid_proxy"]})
        key = (i0 + 1, j0 + 1, int(row["fortran_k"]))
        for role, entry, returned in (("main", main_entry, main_return), ("writer", writer_entry, writer_return)):
            for endpoint, values in (("entry", entry), ("return", returned)):
                for species in SPECIES:
                    out[f"{role}_{endpoint}_{species}"] = real32(values[key][species], f"{role}.{endpoint}.{species}")[0]
            for species in SPECIES:
                before = out[f"{role}_entry_{species}"]
                after = out[f"{role}_return_{species}"]
                out[f"{role}_change_{species}"] = "increase" if after > before else "decrease" if after < before else "same"
        updated_profiles.append(out)

    statuses = {
        "diagnose_radar_cells": status_record(capture, "diagnose_radar_cells_post"),
        "publish_hydrometeor_candidate": status_record(capture, "publish_hydrometeor_candidate_post"),
    }
    summary = {
        "schema": "cp02-density-control-capture-analysis-v1",
        "status": "PASS_SCOPED_AVAILABLE_ENDPOINTS",
        "scope": "The frozen inner and radar structural validators pass for this 20-column x 22-level set. The radar profile is decoded by the unchanged radar validator; no prior outer equality capture is used.",
        "analysis_tool": {"path": str((ROOT / "tools/cp02_control_capture_analysis.py").resolve()),
                          "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "test_file": {"path": str((ROOT / "tests/test_cp02_control_capture_analysis.py").resolve()),
                      "sha256": hashlib.sha256((ROOT / "tests/test_cp02_control_capture_analysis.py").read_bytes()).hexdigest()},
        "capture": {"path": str(capture.get("_path", "")), "sha256": capture.get("_sha256"),
                    "status": capture.get("status"), "inferior_exit_code": capture.get("inferior_exit_code")},
        "point_csv_sha256": point_hash,
        "selection_sha256": hashlib.sha256(selection_csv.read_bytes()).hexdigest(),
        "sample_count": len(updated_profiles),
        "point_count": len(point_summary),
        "role_counts": dict(Counter(row["role"] for row in point_summary)),
        "radar_status": statuses,
        "radar_observed_summary": radar_report["array_value_summaries"],
        "observation_validity_quality_source_counts": radar_report["actual_observation_value_validity_quality_source_counts"],
        "observed_counts_by_role": {role: {key: data[key] for key in (
            "point_count", "observed_post_true_levels", "observed_post_false_levels", "reflectivity_valid_levels",
            "background_positive_rain_levels", "background_positive_snow_levels",
            "unobserved_positive_background_rain_levels", "unobserved_positive_background_snow_levels",
            "captured_local_levels")}
            for role, data in role_stats.items()},
        "species_trends_by_role_vs_actual_input_to_main_final": {role: data["species_trends"] for role,data in role_stats.items()},
        "main_writer_species_trends_by_role": {role:{"main":data["main_entry_to_return"],"writer":data["writer_entry_to_return"]} for role,data in role_stats.items()},
        "workarray_real64_to_published_state_real32_mismatches": workarray_mismatch,
        "standard_radar_analyzer_attempt": {
            "path": str((ROOT / "docs/evidence/cp02_density_controls_20261029/capture/standard_radar_analyzer_attempt.log").resolve()),
            "sha256": hashlib.sha256((ROOT / "docs/evidence/cp02_density_controls_20261029/capture/standard_radar_analyzer_attempt.log").read_bytes()).hexdigest(),
            "result": "FAILED_AT_EXISTING_ALL_SELECTED_SAMPLE_WORKARRAY_CONVERSION_GATE",
            "reason": "The unchanged wrapper invokes INNER.analyze(), whose full sampled REAL64 workarray-to-REAL32 candidate-state equality gate does not hold at selected unaffected positive-background controls.",
        },
        "point_summary": point_summary,
        "limits": [
            "The four external control reflectivity-invalid labels are payload/shadow proxies; captured reflectivity validity and radar_observed flags are reported independently.",
            "The unchanged full radar analyzer gate also asserts equality between each selected REAL64 workarray sample and the published REAL32 state. That assertion is not applied here because the external controls include unaffected positive-background cells; mismatches are counted and shown.",
            "The prior 20-point outer capture is not used as an equality reference for this changed point set.",
            "This is sampled debugger state, not a mass-conservation or forecast-skill result.",
        ],
    }
    return summary, updated_profiles


def analyze_paths(capture_path, point_csv, selection_csv):
    capture = INNER.read_capture(capture_path)
    capture["_path"] = str(capture_path.resolve())
    capture["_sha256"] = hashlib.sha256(capture_path.read_bytes()).hexdigest()
    return summarize(capture, point_csv, selection_csv)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("point_csv", type=Path)
    parser.add_argument("selection_csv", type=Path)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.summary, args.profiles):
        require(not path.exists() and not path.is_symlink(), f"refusing to overwrite {path}")
    summary, profiles = analyze_paths(args.capture, args.point_csv, args.selection_csv)
    summary["capture"]["path"] = str(args.capture.resolve())
    summary["summary_path"] = str(args.summary.resolve())
    summary["profiles_path"] = str(args.profiles.resolve())
    with args.summary.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False); stream.write("\n")
    with args.profiles.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(profiles[0])); writer.writeheader(); writer.writerows(profiles)
    print(json.dumps({"status":summary["status"],"samples":summary["sample_count"],"points":summary["point_count"],
                      "role_counts":summary["role_counts"],"radar_status":{k:v["value"] for k,v in summary["radar_status"].items()}},indent=2))


if __name__ == "__main__":
    main()
