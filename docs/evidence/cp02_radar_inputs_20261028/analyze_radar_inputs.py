#!/usr/bin/env python3
"""Validate and join the scoped CP02 radar-input capture to canonical samples."""

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import struct
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
INNER_PATH = REPO / "docs/evidence/cp02_inner_capture_20261028/analyze_inner.py"
BACKGROUND_CSV = REPO / "docs/evidence/cp02_initial_species_20261027/final/shadow/shadow_species_profiles.csv"
INNER_SPEC = importlib.util.spec_from_file_location("cp02_analyze_inner", INNER_PATH)
INNER = importlib.util.module_from_spec(INNER_SPEC)
INNER_SPEC.loader.exec_module(INNER)

RADAR_ARRAYS = {
    "radar_observed": ("logical", 4),
    "phase": ("integer", 4),
    "phase_uncertain": ("logical", 4),
    "zlinear": ("real", 8),
    "radar_derived": ("logical", 4),
}
OBSERVATION_ARRAYS = {
    "radar_reflectivity": {"value": ("real", 4), "valid": ("logical", 4), "quality": ("integer", 4), "source": ("integer", 4)},
    "precipitation_phase": {"value": ("integer", 4), "valid": ("logical", 4), "quality": ("integer", 4), "source": ("integer", 4)},
}
LOCAL_STAGES = ("density_entry", "density_return", "phase_allocation_return", "store_after")
LOCAL_FIELDS = {
    "density_entry": ("pressure", "temperature", "vapor"),
    "density_return": ("rho_d",),
    "phase_allocation_return": ("rho_d", "total", "new_rain", "new_snow", "new_graupel", "allocation_status"),
    "store_after": ("rain", "snow", "graupel"),
}
LOCAL_WIDTHS = {name: (4 if name == "allocation_status" else 8)
                for fields in LOCAL_FIELDS.values() for name in fields}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def raw_value(record, width, label, expected_kind=None):
    require(isinstance(record, dict) and record.get("status") == "readable", f"{label}: unreadable value")
    type_name = record.get("type", "").lower()
    require(type_name and any(token in type_name for token in ("real", "float", "integer", "logical")),
            f"{label}: missing or unsupported raw type")
    if expected_kind:
        require(expected_kind in type_name, f"{label}: expected {expected_kind} raw type")
    raw = bytes.fromhex(record.get("raw_bytes_le_hex", ""))
    require(len(raw) == width, f"{label}: expected {width}-byte raw value")
    if width == 8:
        value = struct.unpack("<d", raw)[0]
        require(math.isfinite(value), f"{label}: non-finite REAL*8")
        return value
    if width == 4:
        if expected_kind == "real":
            value = struct.unpack("<f", raw)[0]
            require(math.isfinite(value), f"{label}: non-finite REAL*4")
            return value
        return struct.unpack("<i", raw)[0]
    raise ValueError(f"{label}: unsupported raw width {width}")


def sampled_array_values(array, label, kind, width, canonical_keys):
    require(isinstance(array, dict) and array.get("status") == "readable", f"{label}: array is not readable")
    type_name = array.get("type", "").lower()
    require(kind in type_name and (f"kind={width}" in type_name or f"*{width}" in type_name),
            f"{label}: wrong raw type {array.get('type')!r}")
    require(array.get("bounds_i_j_k") == [[1, 235], [1, 283], [1, 22]], f"{label}: wrong bounds")
    points = array.get("points", [])
    require(len(points) == 20, f"{label}: expected 20 canonical points")
    result = {}
    raw_values = {}
    for point in points:
        i, j = point.get("fortran_i"), point.get("fortran_j")
        require(type(i) is int and type(j) is int, f"{label}: invalid point indices")
        levels = point.get("levels", [])
        require([level.get("fortran_k") for level in levels] == list(range(1, 23)), f"{label}: invalid level keys")
        for level in levels:
            key = (i, j, level["fortran_k"])
            require(key not in result, f"{label}: duplicate sample {key}")
            value = raw_value(level, width, f"{label}{key}", kind)
            if kind == "real":
                require(math.isfinite(value), f"{label}{key}: non-finite value")
            result[key] = bool(value) if kind == "logical" else value
            raw_values[key] = level["raw_bytes_le_hex"].lower()
    require(set(result) == set(canonical_keys), f"{label}: keys differ from canonical background")
    return result, raw_values


def array_values(array, name, canonical_keys):
    kind, width = RADAR_ARRAYS[name]
    result, raw_values = sampled_array_values(array, name, kind, width, canonical_keys)
    require(len(result) == 440, f"{name}: expected 440 unique samples")
    return result, raw_values


def background_samples(path):
    result = {}
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"arm", "shadow_i", "shadow_j", "z_index", "background_rain", "background_snow"}
        require(required.issubset(reader.fieldnames or ()), f"background CSV missing columns {sorted(required)}")
        for row in reader:
            if row["arm"].strip().upper() != "HYDRO":
                continue
            key = (int(row["shadow_i"]) + 1, int(row["shadow_j"]) + 1, int(row["z_index"]) + 1)
            require(key not in result, f"duplicate background sample {key}")
            result[key] = row
    require(len(result) == 440, f"expected 440 HYDRO background rows, found {len(result)}")
    return result


def validate_radar(capture, background):
    require(capture.get("schema") == "cp02-gdb-inner-capture-v1", "unsupported capture schema")
    records = capture.get("records", [])
    boundary_records = {}
    boundary_event_records = {}
    for stage in ("diagnose_radar_cells_pre", "diagnose_radar_cells_post",
                  "publish_hydrometeor_candidate_pre", "publish_hydrometeor_candidate_post"):
        hits = [record for record in records if record.get("stage") == stage]
        require(len(hits) == 1, f"expected one {stage} event")
        radar = hits[0].get("radar")
        require(isinstance(radar, dict), f"{stage}: radar payload missing")
        boundary_records[stage] = radar
        boundary_event_records[stage] = hits[0]

    arrays = {}
    array_raw = {}
    state_values = {}
    cfg_values = {}
    for stage, radar in boundary_records.items():
        decoded = {}
        for name in RADAR_ARRAYS:
            require(name in radar.get("inputs", {}), f"{stage}: missing {name}")
            decoded[name], raw = array_values(radar["inputs"][name], name, background)
            array_raw.setdefault(stage, {})[name] = raw
        arrays[stage] = decoded

        state = radar.get("actual_input_state")
        if stage.endswith("_pre"):
            require(isinstance(state, dict), f"{stage}: actual input state missing")
            INNER.validate_state_record(state, "HYDRO")
            state_values[stage] = INNER.sample_map(state)
            require(set(state_values[stage]) == set(background), f"{stage}: actual state keys differ from canonical background")
            cfg = radar.get("cfg", {})
            require(cfg.get("status") == "readable" and isinstance(cfg.get("fields"), dict), f"{stage}: cfg missing or unreadable")
            require(cfg["fields"], f"{stage}: cfg has no captured scalar fields")
            cfg_values[stage] = {}
            for name, value in cfg["fields"].items():
                raw = bytes.fromhex(value.get("raw_bytes_le_hex", ""))
                require(value.get("status") == "readable" and len(raw) in (4, 8), f"{stage}: invalid cfg field {name}")
                field_type = value.get("type", "").lower()
                require("real" in field_type or "integer" in field_type, f"{stage}: unsupported cfg field type {name}")
                if "real" in field_type:
                    number = struct.unpack("<d" if len(raw) == 8 else "<f", raw)[0]
                    require(math.isfinite(number), f"{stage}: non-finite cfg field {name}")
                else:
                    number = struct.unpack("<q" if len(raw) == 8 else "<i", raw)[0]
                cfg_values[stage][name] = number

    boundary_species = {}
    boundary_species_raw = {}
    for stage, event in boundary_event_records.items():
        boundary_species[stage], boundary_species_raw[stage] = {}, {}
        for species in INNER.SPECIES:
            array = event.get("arrays", {}).get(species)
            INNER.validate_selected_array(array, f"{stage}:{species}")
            samples, raw_samples = {}, {}
            for point in array["points"]:
                for level in point["levels"]:
                    key = (point["fortran_i"], point["fortran_j"], level["fortran_k"])
                    raw = level["raw_bytes_le_hex"].lower()
                    number = struct.unpack("<d", bytes.fromhex(raw))[0]
                    require(math.isfinite(number), f"{stage}:{species}{key}: non-finite REAL*8")
                    samples[key], raw_samples[key] = number, raw
            require(set(samples) == set(background), f"{stage}:{species}: keys differ from canonical background")
            boundary_species[stage][species] = samples
            boundary_species_raw[stage][species] = raw_samples

    require(state_values["diagnose_radar_cells_pre"].keys() == state_values["publish_hydrometeor_candidate_pre"].keys(),
            "diagnose and publish actual input state keys differ")
    actual_state_raw_differences = {
        field: sum(state_values["diagnose_radar_cells_pre"][key][field]["raw_bytes_le_hex"] !=
                   state_values["publish_hydrometeor_candidate_pre"][key][field]["raw_bytes_le_hex"]
                   for key in background)
        for field in INNER.FIELDS
    }

    observation_payload = boundary_records["diagnose_radar_cells_pre"].get("actual_observation_state")
    require(isinstance(observation_payload, dict), "actual observation state is missing")
    observation_values = {}
    observation_metadata = {}
    for field, members in OBSERVATION_ARRAYS.items():
        require(field in observation_payload and isinstance(observation_payload[field], dict),
                f"actual observation state missing {field}")
        observation_values[field] = {}
        field_payload = observation_payload[field]
        for member, (kind, width) in members.items():
            require(member in field_payload, f"actual observation {field} missing {member}")
            values, _raw = sampled_array_values(field_payload[member], f"actual_observation.{field}.{member}",
                                                kind, width, background)
            observation_values[field][member] = values
        observation_metadata[field] = {name: value for name, value in field_payload.items()
                                       if name not in members}

    # The status slot sampled at entry must be the same storage written at return.
    for label in ("diagnose_radar_cells", "publish_hydrometeor_candidate"):
        pre = boundary_records[label + "_pre"]
        post = boundary_records[label + "_post"]
        storage = pre.get("status_storage", {})
        returned = post.get("status_return", {})
        require(returned.get("status") == "readable", f"{label}: status return unreadable")
        address = storage.get("pointer_value")
        require(isinstance(storage.get("slot_address"), str) and storage["slot_address"].startswith("0x"),
                f"{label}: status slot address is invalid")
        require(isinstance(address, str) and address.startswith("0x") and int(address, 16) > 0,
                f"{label}: status storage address is invalid")
        pointer_raw = bytes.fromhex(storage.get("raw_bytes_le_hex", ""))
        require(len(pointer_raw) == 8 and int.from_bytes(pointer_raw, "little") == int(address, 16),
                f"{label}: status pointer raw bytes disagree with its value")
        require(address == returned.get("address"), f"{label}: status return address differs from captured storage")
        require("integer" in returned.get("type", "").lower() and "4" in returned.get("type", ""),
                f"{label}: return status is not INTEGER*4")
        raw = bytes.fromhex(returned.get("raw_bytes_le_hex", ""))
        require(len(raw) == 4, f"{label}: status return must preserve INTEGER*4 bytes")
        require(struct.unpack("<i", raw)[0] == returned.get("value"), f"{label}: status raw bytes disagree with decoded value")
        require(returned["value"] == 20, f"{label}: expected successful status code 20")

    boundary_array_changes = {}
    boundary_species_changes = {}
    for label in ("diagnose_radar_cells", "publish_hydrometeor_candidate"):
        pre, post = label + "_pre", label + "_post"
        boundary_array_changes[label] = {
            name: sum(array_raw[pre][name][key] != array_raw[post][name][key] for key in background)
            for name in RADAR_ARRAYS
        }
        boundary_species_changes[label] = {
            species: sum(boundary_species_raw[pre][species][key] != boundary_species_raw[post][species][key]
                         for key in background)
            for species in INNER.SPECIES
        }
    diagnose_after, publish_before = "diagnose_radar_cells_post", "publish_hydrometeor_candidate_pre"
    publish_input_match = {
        name: sum(array_raw[diagnose_after][name][key] == array_raw[publish_before][name][key] for key in background)
        for name in RADAR_ARRAYS
    }
    require(all(publish_input_match[name] == len(background) for name in RADAR_ARRAYS if name != "radar_derived"),
            "publish pre input arrays differ from diagnose post arrays outside radar_derived")
    array_value_summaries = {}
    for stage, values in arrays.items():
        array_value_summaries[stage] = {
            "radar_observed_true": sum(values["radar_observed"].values()),
            "phase_counts": {str(phase): count for phase, count in sorted(Counter(values["phase"].values()).items())},
            "phase_uncertain_true": sum(values["phase_uncertain"].values()),
            "radar_derived_true": sum(values["radar_derived"].values()),
        }
    observation_summaries = {}
    for field, members in observation_values.items():
        observation_summaries[field] = {
            "valid_count": sum(members["valid"].values()),
            "value_counts": {str(value): count for value, count in sorted(Counter(members["value"].values()).items())},
            "quality_counts": {str(value): count for value, count in sorted(Counter(members["quality"].values()).items())},
            "source_counts": {str(value): count for value, count in sorted(Counter(members["source"].values()).items())},
        }

    local_by_stage = {stage: {} for stage in LOCAL_STAGES}
    local_order = {}
    local_frames = {}
    for index, record in enumerate(capture.get("radar_local_records", [])):
        stage = record.get("stage")
        require(stage in local_by_stage, f"unknown radar local stage {stage!r}")
        i, j, k = (record.get(f"fortran_{axis}") for axis in ("i", "j", "k"))
        key = (i, j, k)
        require(type(i) is int and type(j) is int and type(k) is int and key in background,
                f"{stage}: invalid or noncanonical sample key {key}")
        require(record.get("parent_derive_call") == 1, f"{stage}{key}: local event is outside first derive")
        frame = record.get("diagnose_frame_address")
        require(isinstance(frame, str) and frame.startswith("0x") and int(frame, 16) > 0,
                f"{stage}{key}: invalid diagnose frame address")
        require(local_frames.setdefault(key, frame) == frame, f"{stage}{key}: diagnose frame changed across local events")
        require(key not in local_by_stage[stage], f"{stage}: duplicate sample {key}")
        local_order[(stage, key)] = index
        values = record.get("values", {})
        expected = LOCAL_FIELDS[stage]
        require(set(values) == set(expected), f"{stage}{key}: value fields differ from expected")
        local_by_stage[stage][key] = {name: raw_value(values[name], LOCAL_WIDTHS[name], f"{stage}{key}.{name}",
                                                       "integer" if name == "allocation_status" else "real")
                                      for name in expected}

    observed = arrays["diagnose_radar_cells_post"]["radar_observed"]
    hit_keys = {key for key, is_observed in observed.items() if is_observed}
    entry_keys = set(local_by_stage["density_entry"])
    require(entry_keys == hit_keys,
            f"density-entry keys differ from observed radar hits: missing={sorted(hit_keys - entry_keys)[:5]}, extra={sorted(entry_keys - hit_keys)[:5]}")
    for key in entry_keys:
        previous_stage = "density_entry"
        for stage in LOCAL_STAGES[1:]:
            require(key in local_by_stage[stage], f"density_entry{key}: missing subsequent {stage}")
            require(local_order[(stage, key)] > local_order[(previous_stage, key)],
                    f"local chain{key}: {stage} did not follow {previous_stage}")
            previous_stage = stage
    for stage in LOCAL_STAGES[1:]:
        orphaned = set(local_by_stage[stage]) - entry_keys
        require(not orphaned, f"{stage}: records without density_entry, first keys {sorted(orphaned)[:5]}")
    for key, values in local_by_stage["phase_allocation_return"].items():
        require(values["allocation_status"] == 20, f"phase_allocation_return{key}: expected success status 20")

    profiles = []
    final_records = [record for record in records if record.get("stage") == "derive_return_state_out" and record.get("call_number") == 1]
    require(len(final_records) == 1, "missing unique primary derive final state")
    final_values = INNER.sample_map(final_records[0])
    require(set(final_values) == set(background), "final derive state keys differ from canonical background")
    for key in sorted(background):
        row = background[key]
        i, j, k = key
        out = {"fortran_i": i, "fortran_j": j, "fortran_k": k,
               "shadow_i": i - 1, "shadow_j": j - 1, "z_index": k - 1,
               "losthit_rank": row["losthit_rank"], "lat": row["lat"], "lon": row["lon"],
               "background_rain": row["background_rain"], "background_snow": row["background_snow"]}
        for name in INNER.FIELDS:
            field_record = state_values["diagnose_radar_cells_pre"][key][name]
            value = struct.unpack("<f", bytes.fromhex(field_record["raw_bytes_le_hex"]))[0]
            require(math.isfinite(value), f"actual_input.{key}.{name}: non-finite REAL*4")
            out[f"actual_input.{name}"] = value
            final_record = final_values[key][name]
            final_value = struct.unpack("<f", bytes.fromhex(final_record["raw_bytes_le_hex"]))[0]
            require(math.isfinite(final_value), f"final.{key}.{name}: non-finite REAL*4")
            out[f"final.{name}"] = final_value
        for stage, values in arrays.items():
            for name, samples in values.items():
                out[f"{stage}.{name}"] = samples[key]
        for stage, values in boundary_species.items():
            for species, samples in values.items():
                out[f"{stage}.{species}"] = samples[key]
        for field, members in observation_values.items():
            for member, samples in members.items():
                out[f"actual_observation.{field}.{member}"] = samples[key]
        for stage in LOCAL_STAGES:
            sample = local_by_stage[stage].get(key)
            out[f"{stage}.status"] = "CAPTURED" if sample is not None else "NOT_CAPTURED"
            for name in LOCAL_FIELDS[stage]:
                out[f"{stage}.{name}"] = "NOT_CAPTURED" if sample is None or name not in sample else sample[name]
        profiles.append(out)
    return {
        "schema": "cp02-radar-input-analysis-v1",
        "status": "SCOPED_PASS",
        "scope": "First HYDRO derive, canonical 20 points x 22 levels. diagnose pre arrays are helper-entry values; diagnose post observed/phase/zlinear are helper outputs. The captured actual source state includes reflectivity and precipitation phase with validity, quality, and source flags. Raw debugger observations only; no inferred values for unvisited branches, no conservation or forecast-cause conclusion.",
        "sample_count": len(profiles),
        "observed_hit_count": len(hit_keys),
        "local_record_counts": {stage: len(events) for stage, events in local_by_stage.items()},
        "array_counts": {stage: {name: len(samples) for name, samples in values.items()} for stage, values in arrays.items()},
        "array_raw_bitwise_changes_pre_to_post": boundary_array_changes,
        "species_raw_bitwise_changes_pre_to_post": boundary_species_changes,
        "diagnose_post_publish_pre_bitwise_matches": publish_input_match,
        "actual_state_raw32_differences_diagnose_vs_publish_pre": actual_state_raw_differences,
        "array_value_summaries": array_value_summaries,
        "radar_status": {label: boundary_records[label + "_post"]["status_return"]["value"]
                         for label in ("diagnose_radar_cells", "publish_hydrometeor_candidate")},
        "cfg": cfg_values,
        "actual_observation_state": "CAPTURED",
        "actual_observation_metadata": observation_metadata,
        "actual_observation_value_validity_quality_source_counts": observation_summaries,
        "profiles": profiles,
    }


def analyze(capture_path, background_path=BACKGROUND_CSV, prior_outer=None):
    capture = INNER.read_capture(capture_path)
    background_sha256 = hashlib.sha256(Path(background_path).read_bytes()).hexdigest()
    require(capture.get("points_csv_sha256") == background_sha256,
            "background CSV SHA-256 does not match capture points_csv_sha256")
    # Reuse the original full-capture checks and analysis before inspecting new radar fields.
    inner_report = INNER.analyze(capture_path, "HYDRO", prior_outer)
    radar_report = validate_radar(capture, background_samples(background_path))
    return {"schema": radar_report["schema"], "status": radar_report["status"],
            "scope": radar_report["scope"], "inner_analysis": inner_report,
            "capture_path": str(capture_path),
            "capture_sha256": hashlib.sha256(Path(capture_path).read_bytes()).hexdigest(),
            "background_csv_path": str(background_path),
            "background_csv_sha256": background_sha256,
            **{key: value for key, value in radar_report.items() if key not in ("schema", "status", "scope", "profiles")},
            "profiles": radar_report["profiles"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--background-csv", type=Path, default=BACKGROUND_CSV)
    parser.add_argument("--prior-outer", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.profiles):
        require(not path.exists() and not path.is_symlink(), "refusing to overwrite existing output: " + str(path))
    report = analyze(args.capture, args.background_csv, args.prior_outer)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump({key: value for key, value in report.items() if key != "profiles"}, stream, indent=2, allow_nan=False)
        stream.write("\n")
    with args.profiles.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(report["profiles"][0]))
        writer.writeheader()
        writer.writerows(report["profiles"])
    print(f"HYDRO: {report['status']} -> {args.output}")


if __name__ == "__main__":
    main()
