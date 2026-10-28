#!/usr/bin/env python3
"""Validate and summarize the focused CP02 inner GDB capture."""

import argparse
import csv
import gzip
import json
import math
import struct
from collections import Counter
from pathlib import Path


FIELDS = ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel", "temperature", "pressure")
SPECIES = ("rain", "snow", "graupel")
SHAPE = [[1, 235], [1, 283], [1, 22]]
POINTS, LEVELS = 20, 22
BOUNDARIES = ("transport_precipitation_flux", "diagnose_radar_cells", "publish_hydrometeor_candidate")
STATE_STAGES = {"pipeline_entry_state_in", "derive_entry_state_in", "derive_return_state_out", "pipeline_return_candidate_out"}


def read_capture(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def valid_address(value):
    try:
        return isinstance(value, str) and value.startswith("0x") and int(value, 16) > 0
    except ValueError:
        return False


def record_index(capture, arm):
    require(capture.get("schema") == "cp02-gdb-inner-capture-v1", f"{arm}: unsupported schema")
    require(capture.get("status") == "CAPTURE_COMPLETE", f"{arm}: capture is incomplete")
    require(capture.get("inferior_exit_code") == 0, f"{arm}: inferior did not exit successfully")
    require(capture.get("arm") == arm, f"{arm}: wrong experiment arm")
    require(capture.get("levels_captured") == LEVELS, f"{arm}: expected 22 levels")
    counts = capture.get("counts", {})
    nderive = 2 if arm == "HYDRO" else 6
    require(counts.get("pipeline_entries") == counts.get("pipeline_returns") == 2, f"{arm}: expected two balanced pipeline calls")
    require(counts.get("derive_entries") == counts.get("derive_returns") == nderive, f"{arm}: expected {nderive} balanced derive calls")
    require(counts.get("derive_preprologue_abi_entries") == nderive, f"{arm}: expected ABI event per derive call")
    for boundary in BOUNDARIES:
        event = counts.get("candidate_boundary_counts", {}).get(boundary, {"entries": 0, "returns": 0})
        expected_boundary = 1 if arm == "HYDRO" else 0
        require(event.get("entries") == event.get("returns") == expected_boundary, f"{arm}: {boundary} must have {expected_boundary} balanced pairs")
    for entry, ret, label in (("saturation_adjust_pressure_state_entries", "saturation_adjust_pressure_state_returns", "saturation"), ("refresh_dry_air_mass_measure_entries", "refresh_dry_air_mass_measure_returns", "refresh")):
        require(counts.get(entry) == counts.get(ret), f"{arm}: unbalanced {label} calls")
    require(counts.get("saturation_adjust_pressure_state_entries") == 0, f"{arm}: unexpected saturation call in scoped capture")
    require(counts.get("refresh_dry_air_mass_measure_entries") == (1 if arm == "HYDRO" else 0), f"{arm}: unexpected refresh coverage count")
    records = capture.get("records")
    require(isinstance(records, list), f"{arm}: records must be a list")
    for record in records:
        if "call_number" in record:
            require(type(record["call_number"]) is int, f"{arm}:{record.get('stage')}: call number must be an integer")
    observed = Counter(r.get("stage") for r in records)
    declared = {"pipeline_entry_state_in": 2, "pipeline_return_candidate_out": 2,
                "derive_entry_state_in": nderive, "derive_return_state_out": nderive,
                "derive_arguments": nderive, "derive_preprologue_abi_pointers": nderive}
    for name in BOUNDARIES:
        if arm == "HYDRO":
            declared[f"{name}_pre"] = declared[f"{name}_post"] = 1
    for stage, count in (("refresh_dry_air_mass_measure_entry", counts["refresh_dry_air_mass_measure_entries"]), ("refresh_dry_air_mass_measure_return", counts["refresh_dry_air_mass_measure_returns"]), ("saturation_adjust_pressure_state_entry", counts["saturation_adjust_pressure_state_entries"]), ("saturation_adjust_pressure_state_return", counts["saturation_adjust_pressure_state_returns"])):
        if count:
            declared[stage] = count
    require(set(observed) == set(declared), f"{arm}: unknown or missing stages: {sorted(set(observed) ^ set(declared))}")
    require(observed == Counter(declared), f"{arm}: stage event counts disagree with declared counts")
    pos = [r.get("stage") for r in records]
    if arm == "HYDRO":
        hydro_order = ["pipeline_entry_state_in", "derive_preprologue_abi_pointers", "derive_entry_state_in", "derive_arguments",
                       "diagnose_radar_cells_pre", "diagnose_radar_cells_post", "transport_precipitation_flux_pre",
                       "transport_precipitation_flux_post", "publish_hydrometeor_candidate_pre",
                       "refresh_dry_air_mass_measure_entry", "refresh_dry_air_mass_measure_return",
                       "publish_hydrometeor_candidate_post", "derive_return_state_out", "pipeline_return_candidate_out",
                       "pipeline_entry_state_in", "derive_preprologue_abi_pointers", "derive_entry_state_in",
                       "derive_arguments", "derive_return_state_out", "pipeline_return_candidate_out"]
        require(pos == hydro_order, f"{arm}: complete event order differs from the scoped contract")
    else:
        require(pos == ["pipeline_entry_state_in"] + [s for _ in range(3) for s in ("derive_preprologue_abi_pointers", "derive_entry_state_in", "derive_arguments", "derive_return_state_out")] + ["pipeline_return_candidate_out", "pipeline_entry_state_in"] + [s for _ in range(3) for s in ("derive_preprologue_abi_pointers", "derive_entry_state_in", "derive_arguments", "derive_return_state_out")] + ["pipeline_return_candidate_out"], f"{arm}: expected primary then writer derive order")
    indexed = {}
    for r in records:
        stage = r["stage"]
        if stage in STATE_STAGES or stage in ("derive_arguments", "derive_preprologue_abi_pointers"):
            call = r.get("call_number")
            role = r.get("parent", {}).get("role") or ("primary" if call == 1 or (arm != "HYDRO" and call <= 3) else "writer")
            expected_role = "primary" if (stage.startswith("pipeline_") and call == 1) or (arm == "HYDRO" and call == 1) or (arm != "HYDRO" and call <= 3) else "writer"
            if stage.startswith("pipeline_"):
                expected_role = "primary" if call == 1 else "writer"
            if stage in ("derive_arguments", "derive_preprologue_abi_pointers", "derive_return_state_out"):
                require(role == expected_role, f"{arm}:{stage} call {call}: incorrect role")
            key = (stage, call)
            require(key not in indexed, f"{arm}: duplicate {stage} for {role}")
            indexed[key] = r
            if stage in STATE_STAGES:
                validate_state_record(r, arm)
    for stage in STATE_STAGES | {"derive_arguments", "derive_preprologue_abi_pointers"}:
        calls = [r["call_number"] for r in records if r.get("stage") == stage]
        expected_calls = [1, 2] if stage.startswith("pipeline_") else list(range(1, nderive + 1))
        require(calls == expected_calls, f"{arm}: {stage} calls are missing, duplicated, or out of order")
    # Every caller bracket is tied to the first derive invocation.
    for name in BOUNDARIES if arm == "HYDRO" else ():
        pre, post = get_stage(records, name + "_pre"), get_stage(records, name + "_post")
        require(pre.get("parent") == post.get("parent") and pre.get("call_number") == post.get("call_number"), f"{arm}: orphan caller pair for {name}")
        require(pre.get("parent", {}).get("role") == "first_hydro_derive" and pre.get("parent", {}).get("derive_call_number") == 1 and pre.get("call_number") == 1, f"{arm}: caller pair outside first derive")
        require(valid_address(pre.get("caller_frame_address")) and pre.get("caller_frame_address") == post.get("caller_frame_address"), f"{arm}:{name}: caller frame address missing or changed")
        for field in SPECIES:
            before, after = pre["arrays"][field], post["arrays"][field]
            validate_selected_array(before, f"{arm}:{name}_pre:{field}")
            validate_selected_array(after, f"{arm}:{name}_post:{field}")
            require(valid_address(before.get("value_address")) and before.get("value_address") == after.get("value_address"), f"{arm}:{name}:{field}: workarray address missing or changed")
            require([(p["fortran_i"], p["fortran_j"]) for p in before["points"]] == [(p["fortran_i"], p["fortran_j"]) for p in after["points"]], f"{arm}:{name}:{field}: point order changed")
    if arm == "HYDRO":
        for stage in ("refresh_dry_air_mass_measure_entry", "refresh_dry_air_mass_measure_return"):
            event = get_stage(records, stage)
            require(event.get("call_number") == 1 and event.get("parent", {}).get("role") == "first_hydro_derive" and event.get("parent", {}).get("derive_call_number") == 1, f"{arm}: orphan refresh event {stage}")
        pre = get_stage(records, "publish_hydrometeor_candidate_pre").get("candidate_state_pre", {})
        require(pre.get("points") and pre.get("field_shapes"), f"{arm}: publish pre candidate state unavailable")
        validate_state_record(pre, arm)
        post_state = get_stage(records, "publish_hydrometeor_candidate_post").get("candidate_state", {})
        validate_state_record(post_state, arm)
        storage_address = get_stage(records, "publish_hydrometeor_candidate_post").get("candidate_storage_address")
        require(valid_address(pre.get("address")) and pre.get("address") == post_state.get("address") == storage_address, f"{arm}: publish candidate storage address missing or changed")
    state_signatures = [point_signature(r) for r in records if r.get("stage") in STATE_STAGES]
    require(all(signature == state_signatures[0] for signature in state_signatures[1:]), f"{arm}: state sample points differ across records")
    if arm == "HYDRO":
        reference = tuple(item[:3] for item in state_signatures[0])
        for name in BOUNDARIES:
            for suffix in ("_pre", "_post"):
                stage_record = get_stage(records, name + suffix)
                for field in SPECIES:
                    signature = tuple((p["fortran_i"], p["fortran_j"], p.get("point_id")) for p in stage_record["arrays"][field]["points"])
                    require(signature == reference, f"{arm}:{name}{suffix}:{field}: sample keys differ from state capture")
    validate_abi_arguments(records, arm)
    if arm == "LIQUID_RADAR_RH1":
        for record in records:
            if record.get("stage") == "derive_arguments":
                evaluation = record.get("evaluation_state", {})
                require(evaluation.get("readability") == "readable" and evaluation.get("fields"), f"{arm}: evaluation_state missing at derive {record['call_number']}")
                validate_state_record(evaluation["fields"], arm)
                require(point_signature(evaluation["fields"]) == state_signatures[0], f"{arm}: evaluation_state sample keys differ at derive {record['call_number']}")
    return indexed


def get_stage(records, stage):
    found = [r for r in records if r.get("stage") == stage]
    require(len(found) == 1, f"expected exactly one {stage}")
    return found[0]


def point_signature(record):
    return tuple((point["fortran_i"], point["fortran_j"], point.get("point_id"), point.get("lat"), point.get("lon")) for point in record["points"])


def compact_metrics(metrics):
    result = {}
    for name, value in metrics.items():
        result[name] = {key: value.get(key) for key in ("status", "reason", "type", "bounds_i_j_k", "expected_bounds_i_j_k") if key in value}
    return result


def compact_selected_arrays(arrays):
    return {field: {key: arrays[field].get(key) for key in ("status", "type", "bounds_i_j_k", "value_address")}
            | {"point_count": len(arrays[field].get("points", [])),
               "level_count": sum(len(point.get("levels", [])) for point in arrays[field].get("points", []))}
            for field in SPECIES}


def compact_optional_call(record):
    result = {key: record.get(key) for key in ("stage", "call_number", "actual_pc", "parent", "state_address", "status_return") if key in record}
    if "state" in record:
        state = record["state"]
        result["state"] = {"status": "readable" if "points" in state else "unreadable",
                            "address": state.get("address"),
                            "missing_fields": state.get("missing_fields"),
                            "grid_mass_metrics": compact_metrics(state.get("grid_mass_metrics", {}))}
    return result


def validate_selected_array(array, label):
    require(isinstance(array, dict) and array.get("status") == "readable", f"{label}: array missing/unreadable")
    require(array.get("bounds_i_j_k") == SHAPE, f"{label}: wrong bounds")
    pts = array.get("points", [])
    require(len(pts) == POINTS, f"{label}: expected 20 sample points")
    samples = set()
    point_order = []
    for point in pts:
        i, j = point.get("fortran_i"), point.get("fortran_j")
        require((i, j) not in samples, f"{label}: duplicate point")
        require(type(i) is int and type(j) is int and 1 <= i <= 235 and 1 <= j <= 283, f"{label}: point outside captured bounds")
        samples.add((i, j))
        point_order.append((i, j))
        require(len(point.get("levels", [])) == LEVELS, f"{label}: point missing levels")
        require([level.get("fortran_k") for level in point["levels"]] == list(range(1, LEVELS + 1)), f"{label}: level order invalid")
        for level in point["levels"]:
            raw = bytes.fromhex(level.get("raw_bytes_le_hex", ""))
            require(level.get("status") == "readable" and len(raw) == 8 and math.isfinite(struct.unpack("<d", raw)[0]), f"{label}: invalid REAL*8 raw sample")
    require(len(samples) == POINTS and len(set(point_order)) == POINTS, f"{label}: duplicate/missing point")


def validate_state_record(record, arm):
    shapes = record.get("field_shapes")
    require(shapes and set(shapes) == set(FIELDS), f"{arm}:{record['stage']}: missing state shapes")
    require(all(shapes[f].get("fortran_bounds_i_j_k") == SHAPE and shapes[f].get("shape_i_j_k") == [235, 283, 22] for f in FIELDS), f"{arm}:{record['stage']}: state bounds/shape mismatch")
    require(len(record.get("points", [])) == POINTS, f"{arm}:{record['stage']}: expected 20 state points")
    point_keys = set()
    for point in record["points"]:
        i, j = point.get("fortran_i"), point.get("fortran_j")
        require(type(i) is int and type(j) is int and i > 0 and j > 0, f"{arm}:{record['stage']}: invalid point indices")
        require(i <= 235 and j <= 283, f"{arm}:{record['stage']}: point outside captured bounds")
        require((point.get("shadow_i_zero_based"), point.get("shadow_j_zero_based")) == (i - 1, j - 1), f"{arm}:{record['stage']}: index conversion mismatch")
        require((i, j) not in point_keys, f"{arm}:{record['stage']}: duplicate point")
        point_keys.add((i, j))
        require(len(point.get("levels", [])) == LEVELS, f"{arm}:{record['stage']}: expected 22 state levels")
        require([level.get("fortran_k") for level in point["levels"]] == list(range(1, LEVELS + 1)), f"{arm}:{record['stage']}: level order mismatch")
        for level in point["levels"]:
            for field in FIELDS:
                raw = bytes.fromhex(level[field]["raw_bytes_le_hex"])
                require(len(raw) == 4 and math.isfinite(struct.unpack("<f", raw)[0]), f"{arm}:{record['stage']}: invalid REAL*4 {field}")
                valid = level[field].get("valid", {})
                validraw = bytes.fromhex(valid.get("raw_bytes_le_hex", ""))
                require(valid.get("value") in (True, False) and len(validraw) == 4, f"{arm}:{record['stage']}: invalid valid-flag bytes for {field}")
                require(valid["value"] == (struct.unpack("<i", validraw)[0] != 0), f"{arm}:{record['stage']}: valid flag value/raw bytes disagree")
    require(len(point_keys) == POINTS, f"{arm}:{record['stage']}: duplicate state point")


def sample_map(record):
    return {(p["fortran_i"], p["fortran_j"], l["fortran_k"]): l for p in record["points"] for l in p["levels"]}


def state_diff(a, b):
    aa, bb = sample_map(a), sample_map(b)
    require(aa.keys() == bb.keys(), "state sample key sets differ")
    return {field: sum(aa[k][field]["raw_bytes_le_hex"] != bb[k][field]["raw_bytes_le_hex"] for k in aa) for field in FIELDS}


def conversion_check(work_arrays, state):
    state_values = sample_map(state)
    result = {}
    for field in SPECIES:
        checked = mismatches = 0
        for point in work_arrays[field]["points"]:
            i, j = point["fortran_i"], point["fortran_j"]
            for level in point["levels"]:
                k = level["fortran_k"]
                number = struct.unpack("<d", bytes.fromhex(level["raw_bytes_le_hex"]))[0]
                checked += 1
                mismatches += struct.pack("<f", number).hex() != state_values[(i, j, k)][field]["raw_bytes_le_hex"]
        result[field] = {"samples": checked, "mismatches": mismatches, "exact": checked == 440 and mismatches == 0}
    return result


def argument_summary(records):
    def raw_values(value):
        if value.get("status") != "readable":
            return None
        if "raw_bytes_le_hex" in value:
            return {"scalar": value["raw_bytes_le_hex"]}
        return {(point["fortran_i"], point["fortran_j"], level["fortran_k"]): level.get("raw_bytes_le_hex")
                for point in value.get("points", []) for level in point.get("levels", [])}

    summary = []
    for record in records:
        if record.get("stage") != "derive_arguments":
            continue
        fields = {}
        for name in ("thermo_active", "thermo_surface", "target_rh"):
            value = record.get(name, {})
            fields[name] = {"status": value.get("status"), "bounds_i_j_k": value.get("bounds_i_j_k"),
                            "sample_count": 1 if "raw_bytes_le_hex" in value else sum(len(point.get("levels", [])) for point in value.get("points", [])),
                            "address": value.get("address") or value.get("value_address"),
                            "raw_bytes_le_hex": value.get("raw_bytes_le_hex")}
        config = record.get("config", {})
        config_raw = {name: member.get("raw_bytes_le_hex") for name, member in config.get("fields", {}).items()}
        evaluation = record.get("evaluation_state", {})
        raw_args = {name: raw_values(record.get(name, {})) for name in ("thermo_active", "thermo_surface", "target_rh")}
        role = record.get("parent", {}).get("role")
        calls_for_role = [r for r in records if r.get("stage") == "derive_arguments" and r.get("parent", {}).get("role") == role]
        prior = max((r for r in calls_for_role if r.get("call_number", 0) < record.get("call_number", 0)), key=lambda r: r["call_number"], default=None)
        argument_differences = {}
        config_differences = {}
        if prior:
            prior_config = prior.get("config", {}).get("fields", {})
            config_differences = {name: member.get("raw_bytes_le_hex") != config_raw.get(name)
                                  for name, member in prior_config.items()}
            for name in raw_args:
                before = raw_values(prior.get(name, {}))
                now = raw_args[name]
                argument_differences[name] = {"status": "unavailable", "left": prior.get(name, {}).get("status"), "right": record.get(name, {}).get("status")}
                if before is not None and now is not None:
                    require(before.keys() == now.keys(), f"derive argument {name} sample keys changed")
                    argument_differences[name] = {"compared_samples": len(now), "raw_byte_mismatches": sum(before[k] != now[k] for k in now)}
        summary.append({"call_number": record.get("call_number"), "role": record.get("parent", {}).get("role"),
                        "config_raw_bytes": config_raw, "selected_arguments": fields,
                        "config_field_changed_vs_previous_same_role_call": config_differences,
                        "selected_argument_raw_differences_vs_previous_same_role_call": argument_differences,
                        "evaluation_state": {"presence": evaluation.get("presence"), "readability": evaluation.get("readability"),
                                             "reason": evaluation.get("reason"), "address": evaluation.get("address")}})
    return summary


def abi_summary(records):
    result = []
    for record in records:
        if record.get("stage") != "derive_preprologue_abi_pointers":
            continue
        slots = {"r8_thermo_active": record.get("r8_thermo_active_pointer"),
                 "r9_thermo_surface": record.get("r9_thermo_surface_pointer"),
                 **record.get("stack_pointer_words", {})}
        compact = {}
        for name, slot in slots.items():
            if slot is None:
                compact[name] = {"status": "unreadable"}
                continue
            raw = slot.get("raw_bytes_le_hex")
            pointer = slot.get("pointer_value")
            if raw is not None:
                require(len(bytes.fromhex(raw)) == 8, f"ABI {name}: expected raw 8-byte slot")
                require(pointer == hex(int.from_bytes(bytes.fromhex(raw), "little")), f"ABI {name}: pointer disagrees with raw slot bytes")
            compact[name] = {"slot_address": slot.get("slot_address"), "raw_bytes_le_hex": raw,
                             "pointer_value": pointer, "slot_value": slot.get("slot_value")}
        result.append({"call_number": record.get("call_number"), "role": record.get("parent", {}).get("role"), "arguments": compact})
    return result


def validate_abi_arguments(records, arm):
    args = {r.get("call_number"): r for r in records if r.get("stage") == "derive_arguments"}
    abis = [r for r in records if r.get("stage") == "derive_preprologue_abi_pointers"]
    for abi in abis:
        call = abi["call_number"]
        record = args[call]
        stack = abi.get("stack_pointer_words", {})
        evaluation_pointer = stack.get("evaluation_state_arg10", {}).get("pointer_value")
        evaluation = record.get("evaluation_state", {})
        if arm == "LIQUID_RADAR_RH1":
            require(evaluation_pointer not in (None, "0x0") and evaluation.get("readability") == "readable", f"{arm}: expected readable evaluation_state at derive {call}")
            require(evaluation.get("address") == evaluation_pointer, f"{arm}: ABI evaluation_state pointer differs at derive {call}")
        elif evaluation_pointer == "0x0":
            require(evaluation.get("readability") in ("unreadable", "unresolved"), f"{arm}: null ABI pointer conflicts with readable evaluation_state")
        if arm == "HYDRO":
            require(evaluation_pointer == "0x0" and evaluation.get("readability") in ("unreadable", "unresolved"), f"{arm}: expected null ABI slot with unresolved/unreadable DWARF state at derive {call}")


def species_stats(records, arm):
    rows = []
    for stage, record in records:
        for field in SPECIES:
            numbers = []
            if "arrays" in record:
                samples = record["arrays"][field]
                if samples.get("status") == "readable":
                    numbers = [struct.unpack("<d", bytes.fromhex(level["raw_bytes_le_hex"]))[0]
                               for point in samples["points"] for level in point["levels"]]
                representation = "REAL*8 raw workarray"
            elif "points" in record:
                numbers = [struct.unpack("<f", bytes.fromhex(level[field]["raw_bytes_le_hex"]))[0]
                           for point in record["points"] for level in point["levels"]]
                representation = "REAL*4 state"
            if not numbers:
                continue
            changed = None
            if stage.endswith("_post"):
                pre = next((item for prior, item in records if prior == stage[:-5] + "_pre"), None)
                if pre and "arrays" in pre:
                    a, b = pre["arrays"][field]["points"], record["arrays"][field]["points"]
                    changed = sum(x["raw_bytes_le_hex"] != y["raw_bytes_le_hex"]
                                  for pa, pb in zip(a, b) for x, y in zip(pa["levels"], pb["levels"]))
                elif pre and "points" in pre:
                    before, after = sample_map(pre), sample_map(record)
                    changed = sum(before[key][field]["raw_bytes_le_hex"] != after[key][field]["raw_bytes_le_hex"] for key in before)
            mean = sum(numbers) / len(numbers)
            role = record.get("parent", {}).get("role")
            if role == "first_hydro_derive":
                role = "primary"
            if role is None:
                call = record.get("call_number", 1)
                role = "primary" if call == 1 or (arm != "HYDRO" and call <= 3) else "writer"
            rows.append({"stage": stage, "call_number": record.get("call_number", 1), "role": role,
                         "representation": representation, "species": field, "sample_count": len(numbers),
                         "unweighted_mean_kg_per_kg": mean, "unweighted_mean_g_per_kg": mean * 1000.0,
                         "changed_count": changed})
    return rows


def analyze(path, arm, prior_path=None):
    capture = read_capture(path)
    indexed = record_index(capture, arm)
    records = capture["records"]
    primary_entry = indexed[("pipeline_entry_state_in", 1)]
    primary_out = indexed[("pipeline_return_candidate_out", 1)]
    writer_entry = indexed[("pipeline_entry_state_in", 2)]
    writer_out = indexed[("pipeline_return_candidate_out", 2)]
    inner_stages = []
    for stage in ("derive_entry_state_in", "diagnose_radar_cells_pre", "diagnose_radar_cells_post", "transport_precipitation_flux_pre", "transport_precipitation_flux_post", "publish_hydrometeor_candidate_pre", "refresh_dry_air_mass_measure_entry", "refresh_dry_air_mass_measure_return", "publish_hydrometeor_candidate_post", "derive_return_state_out"):
        hits = [r for r in records if r.get("stage") == stage]
        inner_stages.extend((stage, r) for r in hits)
    if arm == "HYDRO":
        publish_pre = get_stage(records, "publish_hydrometeor_candidate_pre")["candidate_state_pre"]
        publish_post = get_stage(records, "publish_hydrometeor_candidate_post")["candidate_state"]
        inner_stages.extend([("publish_candidate_state_pre", publish_pre), ("publish_candidate_state_post", publish_post)])
    result = {
        "schema": "cp02-inner-analysis-v1", "arm": arm, "status": "SCOPED_PASS",
        "scope": "Selected 20 points x 22 stored levels. Observed debugger values only; no mass conservation, domainwide budget, or forecast-cause conclusion.",
        "events": capture["counts"],
        "inner_boundary_coverage": ("instrumented on the first HYDRO derive call" if arm == "HYDRO"
                                     else "not instrumented for LIQUID; empty event set is not evidence of zero calls"),
        "optional_inner_call_coverage": ("saturation and refresh hooks were enabled during the first HYDRO derive" if arm == "HYDRO"
                                          else "not instrumented for LIQUID; empty event set is not evidence of zero calls"),
        "primary_writer_outer_state8_raw32_bitwise_differences": state_diff(primary_out, writer_out),
        "primary_entry_vs_writer_entry_state8_raw32_bitwise_differences": state_diff(primary_entry, writer_entry),
        "stages": {},
        "species_profiles": species_stats(inner_stages, arm),
        "state_capture_metadata": [{"stage": r.get("stage"), "call_number": r.get("call_number"),
                                    "missing_fields": r.get("missing_fields"),
                                    "grid_mass_metrics": compact_metrics(r.get("grid_mass_metrics", {})),
                                    "field_shapes": r.get("field_shapes")}
                                   for r in records if r.get("stage") in STATE_STAGES],
        "abi": abi_summary(records),
        "optional_calls": {name: [compact_optional_call(r) for r in records if r.get("stage", "").startswith(name)] for name in ("saturation_adjust_pressure_state", "refresh_dry_air_mass_measure")},
        "derive_arguments": argument_summary(records),
    }
    require(not any(result["primary_writer_outer_state8_raw32_bitwise_differences"].values()), f"{arm}: primary/writer outer selected states differ")
    # Pair summaries carry species bytes and per-point address/bounds metadata from the receipt.
    for name in BOUNDARIES if arm == "HYDRO" else ():
        pre, post = get_stage(records, name + "_pre"), get_stage(records, name + "_post")
        result["stages"][name] = {"caller_frame_address": pre.get("caller_frame_address"),
                                  "pre": compact_selected_arrays(pre["arrays"]),
                                  "post": compact_selected_arrays(post["arrays"]),
                                  "changed_samples": {field: sum(a["raw_bytes_le_hex"] != b["raw_bytes_le_hex"] for pa, pb in zip(pre["arrays"][field]["points"], post["arrays"][field]["points"]) for a, b in zip(pa["levels"], pb["levels"])) for field in SPECIES}}
        if name == "publish_hydrometeor_candidate":
            pre_state, post_state = pre["candidate_state_pre"], post["candidate_state"]
            result["stages"][name]["candidate_state_pre_address"] = pre_state.get("address")
            result["stages"][name]["candidate_state_post_address"] = post_state.get("address")
            result["stages"][name]["candidate_state_pre_to_post_raw32_differences"] = state_diff(pre_state, post_state)
            conversion = conversion_check(post["arrays"], post_state)
            require(all(item["exact"] for item in conversion.values()), f"{arm}: published REAL*4 species do not match REAL*8 workarray conversion")
            result["stages"][name]["workarray_to_published_state_conversion"] = conversion
    if arm == "HYDRO":
        refresh_entry = get_stage(records, "refresh_dry_air_mass_measure_entry")["state"]
        refresh_return = get_stage(records, "refresh_dry_air_mass_measure_return")["state"]
        result["refresh_state_raw32_differences"] = state_diff(refresh_entry, refresh_return)
        pre_entry_diff = state_diff(
            get_stage(records, "publish_hydrometeor_candidate_pre")["candidate_state_pre"],
            indexed[("derive_entry_state_in", 1)])
        require(not any(pre_entry_diff.values()), f"{arm}: publish candidate pre-state differs from first derive entry")
        result["publish_candidate_pre_vs_derive_entry_raw32_differences"] = pre_entry_diff
    if arm != "HYDRO":
        args = {r["call_number"]: r for r in records if r.get("stage") == "derive_arguments"}
        eval_states = {call: rec.get("evaluation_state", {}) for call, rec in args.items()}
        eval_diffs = {}
        for left, right, label in ((1, 2, "eval2_vs_eval1"), (1, 3, "eval3_vs_eval1"), (2, 3, "eval3_vs_eval2")):
            a, b = eval_states[left], eval_states[right]
            if a.get("readability") == b.get("readability") == "readable":
                eval_diffs[label] = state_diff(a["fields"], b["fields"])
            else:
                eval_diffs[label] = {"status": "not_comparable", "left": a.get("readability"), "right": b.get("readability")}
        eval1 = eval_states[1]
        if eval1.get("readability") == "readable":
            eval_diffs["eval1_vs_derive_entry1"] = state_diff(eval1["fields"], indexed[("derive_entry_state_in", 1)])
            eval_diffs["eval2_vs_derive_return1"] = state_diff(eval_states[2]["fields"], indexed[("derive_return_state_out", 1)])
            eval_diffs["eval3_vs_derive_return2"] = state_diff(eval_states[3]["fields"], indexed[("derive_return_state_out", 2)])
        result["evaluation_state_differences"] = eval_diffs
    result["state_endpoints"] = {"derive_entry_to_return": state_diff(indexed[("derive_entry_state_in", 1)], indexed[("derive_return_state_out", 1)]),
                                 "primary_to_writer_return": state_diff(primary_out, writer_out)}
    if prior_path:
        prior = read_capture(prior_path)
        old = {r["stage"]: r for r in prior.get("records", []) if r.get("stage") in ("pipeline_entry_state_in", "pipeline_return_candidate_out")}
        result["outer_capture_comparison"] = {}
        for stage, fresh in (("pipeline_entry_state_in", primary_entry), ("pipeline_return_candidate_out", primary_out)):
            candidates = [r for r in prior.get("records", []) if r.get("stage") == stage and r.get("call_number") == 1]
            require(len(candidates) == 1, f"prior outer capture lacks unique {stage} call 1")
            result["outer_capture_comparison"][stage] = state_diff(fresh, candidates[0])
        require(not any(value for diff in result["outer_capture_comparison"].values() for value in diff.values()), f"{arm}: selected outer state differs from prior original capture")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--arm", required=True, choices=("HYDRO", "LIQUID_RADAR_RH1"))
    parser.add_argument("--prior-outer", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.profiles):
        require(not path.exists() and not path.is_symlink(), "refusing to overwrite existing output: " + str(path))
    report = analyze(args.capture, args.arm, args.prior_outer)
    encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(encoded)
    with args.profiles.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("stage", "call_number", "role", "representation", "species", "sample_count", "unweighted_mean_kg_per_kg", "unweighted_mean_g_per_kg", "changed_count"))
        writer.writeheader()
        writer.writerows(report["species_profiles"])
    print(f"{args.arm}: {report['status']} -> {args.output}")


if __name__ == "__main__":
    main()
