#!/usr/bin/env python3
"""Validate the staged CP02 KDM6 outer/internal diagnostic capture."""

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import shutil
import struct
import tempfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BINARY_SHA256 = "de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168"
EXPECTED_BUILD_ID = "8baf18e56c6a582ccc7a27fb4d1653ad18fb8810"
EXPECTED_SELECTION_SHA256 = "38602c67768d0836c5f911c43ff4bcced57073f6f222f1c91a63499c16956c6e"
EXPECTED_PRIOR_SUMMARY_SHA256 = "776a90a8f8de2946f0ca25feb68f010e44009e72c10468efb6684f67f4191524"
EXPECTED_PRIOR_PROFILES_SHA256 = "d07ccf07dddcccd285bddb9cd77d475deb5c8773142a4edaa466c6e9d184860d"
EXPECTED_COPY_MANIFEST_SHA256 = "01e00d732b1f983f55247e3ce97568a536a3aa6465059c864a0f292b93ca2f7e"
EXPECTED_RANKS = 8
EXPECTED_PREPARE = ROOT / "docs/evidence/cp02_thermo_response_20261029/runtime/prepare_v6.json"
OUTER_ENTRY_PC = "0x25df680"
OUTER_RETURN_PC = "0x20c3722"
INNER_CALL_PC = "0x25e0fe4"
INNER_ENTRY_PC = "0x25e2490"
INNER_RETURN_PC = "0x25e0fe9"
TARGET_LABELS = {"P01_00", "P01_10", "P01_01", "P01_11",
                 "P05_00", "P05_10", "P05_01", "P05_11"}
WATCH_TARGET_RANK = {"P01_00": "3", "P05_00": "1"}
WATCH_FIELDS = ("qrs", "qci", "q", "t")
INNER_FIELDS = ("qrs", "qci", "q", "t", "nci", "nrs")
OUTER_FIELDS = ("th", "q", "qc", "qr", "qi", "qs", "qg", "nn", "nc", "ni", "nr",
                "bg", "diag_rhog", "den", "pii", "p", "delz", "xland", "rain", "rainncv",
                "snow", "snowncv", "sr", "refl_10cm", "graupel", "graupelncv",
                "re_cloud", "re_ice", "re_snow")
OPTIONAL_FIELDS = {"refl_10cm", "re_cloud", "re_ice", "re_snow"}
CORE_OUTER_FIELDS = tuple(field for field in OUTER_FIELDS if field not in OPTIONAL_FIELDS)
OUTER_ARRAYS_3D = set(range(1, 18)) | {48} | set(range(57, 60))
OUTER_ARRAYS_2D = set(range(42, 48)) | {51, 52}
OUTER_ARG_INDEX = {name: index for index, name in enumerate(
    "th q qc qr qi qs qg nn nc ni nr bg diag_rhog den pii p delz delt g cpd cpv ccn0 rd rv t0c ep1 ep2 qmin xls xlv0 xlf0 den0 denr scale_h qnn_land_mult qnn_sea_mult ncmin_land ncmin_sea cliq cice psat xland rain rainncv snow snowncv sr refl_10cm diagflag do_radar_ref graupel graupelncv itimestep has_reqc has_reqi has_reqs re_cloud re_ice re_snow ids ide jds jde kds kde ims ime jms jme kms kme its ite jts jte kts kte".split(), 1)}
INNER_NULLABLE_POSITIONS = {14, 17, 18, 21, 32, 39, 40, 41, 42, 43, 44,
                            47, 48}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def reject_json_constant(value):
    raise ValueError(f"nonstandard JSON constant {value}")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_profile_binding(profile, current_profile_path):
    require(isinstance(profile.get("path"), str) and profile["path"],
            "capture Intel profile path metadata is absent")
    require(profile.get("sha256") == sha256_file(current_profile_path),
            "capture does not bind the pinned Intel profile bytes")


def raw4(record, label, *, allow_nonfinite=False):
    try:
        raw = bytes.fromhex(record["raw_hex"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label}: malformed raw REAL*4") from exc
    require(len(raw) == 4, f"{label}: expected four raw bytes")
    value = struct.unpack("<f", raw)[0]
    finite = math.isfinite(value)
    if "finite" in record:
        require(record["finite"] is finite,
                f"{label}: finite flag differs from raw bytes")
        require((finite and record.get("value_f32") is not None and
                 math.isfinite(record["value_f32"]) and
                 struct.pack("<f", record["value_f32"]) == raw) or
                (not finite and record.get("value_f32") is None),
                f"{label}: decoded REAL*4 metadata differs from raw bytes")
    require(finite or allow_nonfinite, f"{label}: nonfinite REAL*4")
    return raw


def pointer_hex(value, label):
    require(isinstance(value, str) and value.startswith("0x"),
            f"{label}: malformed pointer value")
    try:
        return int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label}: malformed pointer value") from exc


def raw_address(record, label, *, allow_nonfinite=False):
    raw4(record, label, allow_nonfinite=allow_nonfinite)
    address = pointer_hex(record.get("address_hex"), label + " address")
    require(address != 0, f"{label}: null value address")
    return address


def expected_outer_address(arguments, sample, bounds, name):
    index = OUTER_ARG_INDEX[name]
    pointer = pointer_hex(arguments[index - 1].get("pointer_hex"), f"outer {name} pointer")
    i, j, k = coordinate_key(sample)
    nx = bounds["ime"] - bounds["ims"] + 1
    if index in OUTER_ARRAYS_3D:
        nk = bounds["kme"] - bounds["kms"] + 1
        offset = (i - bounds["ims"]) + (k - bounds["kms"]) * nx + (j - bounds["jms"]) * nx * nk
    elif index in OUTER_ARRAYS_2D:
        offset = (i - bounds["ims"]) + (j - bounds["jms"]) * nx
    else:
        raise ValueError(f"{name}: not a captured outer array argument")
    return pointer + 4 * offset


def validate_inner_argument_vector(inner, rank):
    pointers = inner.get("argument_pointers_hex", [])
    require(inner.get("argument_count") == 62 and len(pointers) == 62,
            f"rank {rank}: inner argument vector must contain 62 pointer words")
    values = [pointer_hex(value, f"rank {rank} inner argument {i}")
              for i, value in enumerate(pointers, 1)]
    registers = inner.get("registers_hex", {})
    reg_names = ("rdi", "rsi", "rdx", "rcx", "r8", "r9")
    require(all(pointer_hex(registers.get(reg), f"rank {rank} register {reg}") == values[i]
                for i, reg in enumerate(reg_names)),
            f"rank {rank}: register pointers differ from argument vector")
    stack = bytes.fromhex(inner.get("stack_hex_from_rsp", ""))
    require(len(stack) == 8 * 58, f"rank {rank}: inner stack capture length differs")
    require(struct.unpack_from("<Q", stack, 0)[0] == int(INNER_RETURN_PC, 16),
            f"rank {rank}: raw inner return address differs")
    for arg_index in range(7, 63):
        stack_value = struct.unpack_from("<Q", stack, 8 + (arg_index - 7) * 8)[0]
        require(stack_value == values[arg_index - 1],
                f"rank {rank}: argument {arg_index} differs from raw stack slot")
    nulls = [i for i, value in enumerate(values, 1) if value == 0]
    require(nulls == inner.get("null_argument_positions"),
            f"rank {rank}: inner null-index record mismatch")
    require(all(position in INNER_NULLABLE_POSITIONS for position in nulls),
            f"rank {rank}: null pointer outside explicitly nullable/unused ABI slots")
    return values


def coordinate_key(sample):
    return (int(sample["i"]), int(sample["j"]), int(sample["k"]))


def sample_index(samples, label):
    indexed = {}
    for sample in samples:
        key = coordinate_key(sample)
        require(key not in indexed, f"{label}: duplicate selected coordinate {key}")
        indexed[key] = sample
    return indexed


def validate_outer_samples(new_samples, prior_samples, expected_keys, expected_labels,
                           optional_counts, endpoint, label):
    require(len(new_samples) == 624, f"{label}: expected 624 outer points")
    require(len(prior_samples) == 624, f"{label}: expected 624 prior outer points")
    new = sample_index(new_samples, label + " new")
    prior = sample_index(prior_samples, label + " prior")
    require(set(new) == expected_keys, f"{label}: new outer coordinate set differs from selection")
    require(set(prior) == expected_keys, f"{label}: prior outer coordinate set differs from selection")
    for key in sorted(expected_keys):
        n, p = new[key], prior[key]
        require(n.get("label") == p.get("label") == expected_labels[key],
                f"{label}: point label differs from frozen selection at {key}")
        require(n.get("status") == p.get("status") or
                (n.get("status") == "not_owned_tile" and p.get("status") == "halo_or_not_owned"),
                f"{label}: ownership status differs at {key}")
        if n.get("status") != "owned_tile":
            continue
        require(p.get("status") == "owned_tile", f"{label}: prior owner differs at {key}")
        require(set(n.get("values", {})) == set(OUTER_FIELDS), f"{label}: new field set differs at {key}")
        require(set(p.get("values", {})) == set(OUTER_FIELDS), f"{label}: prior field set differs at {key}")
        for field in OUTER_FIELDS:
            optional = field in OPTIONAL_FIELDS
            nr = raw4(n["values"][field], f"{label} {key}.{field} new",
                      allow_nonfinite=optional)
            pr = raw4(p["values"][field], f"{label} {key}.{field} prior",
                      allow_nonfinite=optional)
            if optional:
                optional_counts[(endpoint, field, "compared")] += 1
                optional_counts[(endpoint, field, "byte_equal")] += nr == pr
                optional_counts[(endpoint, field, "byte_different")] += nr != pr
                optional_counts[(endpoint, field, "new_nonfinite")] += not math.isfinite(struct.unpack("<f", nr)[0])
                optional_counts[(endpoint, field, "prior_nonfinite")] += not math.isfinite(struct.unpack("<f", pr)[0])
            else:
                require(nr == pr, f"{label}: outer bytes differ at {key}.{field}")
    return sum(sample.get("status") == "owned_tile" for sample in new_samples) * len(CORE_OUTER_FIELDS)


def selected_targets(selection):
    targets = [point for point in selection if point.get("label") in TARGET_LABELS and point.get("k") == 8]
    require(len(targets) == 8, "selection must contain the eight P01/P05 k8 corners")
    require({point["label"] for point in targets} == TARGET_LABELS, "target label set differs")
    return {point["label"]: point for point in targets}


def f32(value):
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def ordered_bits(raw):
    bits = struct.unpack("<I", raw)[0]
    return (~bits & 0xffffffff) if bits & 0x80000000 else (bits | 0x80000000)


def within_one_ulp(raw_a, raw_b):
    return abs(ordered_bits(raw_a) - ordered_bits(raw_b)) <= 1


def validate_outer_inner_mapping(point, outer_sample, inner_entry, label):
    outer_values = outer_sample["values"]
    mapping = inner_entry.get("entry_mapping_checks", {})
    require(mapping.get("qrs_equals_outer_qr") is True, f"{label}: qrs/QR map check absent")
    require(mapping.get("qci_equals_outer_qc") is True, f"{label}: qci/QC map check absent")
    require(mapping.get("q_equals_outer_q") is True, f"{label}: q map check absent")
    require(mapping.get("t_equals_real32_th_times_pii_within_1_ulp") is True,
            f"{label}: temperature map check absent")
    values = inner_entry["entry"]
    require(raw4(values["qrs"], label + ".qrs") == raw4(outer_values["qr"], label + ".outer_qr"),
            f"{label}: qrs differs from outer qr at entry")
    require(raw4(values["qci"], label + ".qci") == raw4(outer_values["qc"], label + ".outer_qc"),
            f"{label}: qci differs from outer qc at entry")
    require(raw4(values["q"], label + ".q") == raw4(outer_values["q"], label + ".outer_q"),
            f"{label}: q differs from outer q at entry")
    expected_t = struct.pack("<f", f32(struct.unpack("<f", raw4(outer_values["th"], label+".th"))[0] *
                                       struct.unpack("<f", raw4(outer_values["pii"], label+".pii"))[0]))
    require(within_one_ulp(raw4(values["t"], label+".t"), expected_t),
            f"{label}: t differs from REAL32(th*pii) by more than one ULP")


def validate_inner_records(records, targets, outer_by_rank):
    entry_records = {}
    return_records = {}
    event_by_target = {}
    watch_events = []
    for record in records:
        rank = str(record["rank"])
        require(record.get("status") == "all_ranks_settled", f"rank {rank}: capture is incomplete")
        last_event_id = 0
        for inner in record.get("inner", []):
            require(str(inner.get("rank")) == rank and inner.get("pid") == record.get("pid"),
                    f"rank {rank}: inner event process identity differs")
            require(inner.get("event_id") == last_event_id + 1,
                    f"rank {rank}: inner call sequence is duplicated or out of order")
            last_event_id += 1
            require(inner.get("entry_pc") == INNER_ENTRY_PC, f"rank {rank}: wrong KDM62D entry PC")
            require(inner.get("return_pc") == INNER_RETURN_PC and inner.get("callsite_pc") == INNER_CALL_PC,
                    f"rank {rank}: wrong KDM62D call/return PC")
            pointers = validate_inner_argument_vector(inner, rank)
            require(inner.get("nullable_pointer_positions") == inner.get("null_argument_positions"),
                    f"rank {rank}: nullable pointer slots are not explicitly documented")
            bounds = inner.get("candidate_bounds", {})
            require(isinstance(bounds, dict), f"rank {rank}: inner bounds record absent")
            outer_record = outer_by_rank[rank]
            outer_memory = outer_record.get("memory_bounds")
            outer_tile = outer_record.get("tile_bounds")
            require(isinstance(outer_memory, dict) and isinstance(outer_tile, dict),
                    f"rank {rank}: outer bounds unavailable for inner mapping")
            for name in ("ims", "ime", "kms", "kme"):
                require(bounds.get(name) == outer_memory[name],
                        f"rank {rank}: inner/outer {name} bounds differ")
            for name in ("its", "ite", "jts", "jte", "kts", "kte"):
                require(bounds.get(name) == outer_tile[name],
                        f"rank {rank}: inner/outer {name} bounds differ")
            nx_tile = bounds["ite"] - bounds["its"] + 1
            nx_memory = bounds["ime"] - bounds["ims"] + 1
            nk_memory = bounds["kme"] - bounds["kms"] + 1
            require(nx_tile > 0 and nx_memory > 0 and nk_memory > 0,
                    f"rank {rank}: invalid inner array extents")
            pointers = validate_inner_argument_vector(inner, rank)
            provenance = inner.get("current_j_provenance", {})
            require(provenance.get("method") ==
                    "inner_q_pointer_minus_outer_q_base_divided_by_outer_memory_row_stride",
                    f"rank {rank}: current-j derivation method is not recorded")
            inner_q = pointers[1]
            outer_args = outer_record["arguments"]
            outer_q = pointer_hex(outer_args[OUTER_ARG_INDEX["q"]-1].get("pointer_hex"),
                                  f"rank {rank} outer q pointer")
            row_stride = 4 * nx_memory * nk_memory
            delta = inner_q - outer_q
            require(delta >= 0 and delta % row_stride == 0,
                    f"rank {rank}: inner q pointer is not aligned to an outer row")
            derived_j = outer_memory["jms"] + delta // row_stride
            require(derived_j == bounds.get("current_j_from_q_pointer") ==
                    provenance.get("derived_current_j"),
                    f"rank {rank}: current-j derivation record differs from q-row alias")
            require(bounds.get("q_row_stride_bytes") == row_stride,
                    f"rank {rank}: candidate q-row stride differs from memory bounds")
            require(outer_memory["jms"] <= derived_j <= outer_memory["jme"] and
                    outer_tile["jts"] <= derived_j <= outer_tile["jte"],
                    f"rank {rank}: derived current j is outside outer ownership bounds")
            require(pointer_hex(provenance.get("inner_q_pointer_hex"), f"rank {rank} provenance inner q") == inner_q and
                    pointer_hex(provenance.get("outer_q_base_pointer_hex"), f"rank {rank} provenance outer q") == outer_q and
                    provenance.get("byte_delta") == delta and provenance.get("row_stride_bytes") == row_stride,
                    f"rank {rank}: current-j provenance pointer/stride fields differ")
            unavailable = inner.get("unavailable_argument_positions")
            require(isinstance(unavailable, list) and
                    set(unavailable) == (set(inner.get("null_argument_positions", [])) &
                                         {32, 39, 40, 41, 42, 43, 44, 47, 48}),
                    f"rank {rank}: nullable bounds/current-j slots are not explicitly recorded as unavailable")
            point_entries = inner.get("points", [])
            require(point_entries, f"rank {rank}: inner record has no selected points")
            expected_call_labels = {label for label, selected in targets.items()
                                    if selected["j"] == derived_j}
            require({entry.get("label") for entry in point_entries} == expected_call_labels,
                    f"rank {rank}: inner call selected-point set differs for current j={derived_j}")
            for entry in point_entries:
                label = entry.get("label")
                require(label in targets, f"rank {rank}: orphan inner target {label}")
                point = targets[label]
                require((entry.get("i"), entry.get("j"), entry.get("k")) ==
                        (point["i"], point["j"], point["k"]),
                        f"rank {rank}: target coordinate mismatch for {label}")
                require(derived_j == point["j"], f"rank {rank}: q row pointer does not identify target j for {label}")
                require(bounds["jts"] <= point["j"] <= bounds["jte"] and
                        bounds["its"] <= point["i"] <= bounds["ite"] and
                        bounds["kts"] <= point["k"] <= bounds["kte"],
                        f"rank {rank}: target outside inner tile for {label}")
                require(label not in entry_records, f"duplicate inner entry for {label}")
                outer_sample = outer_by_rank[rank]["entry"][coordinate_key(point)]
                require(outer_sample.get("status") == "owned_tile",
                        f"{label}: inner target rank does not own corresponding outer point")
                validate_outer_inner_mapping(point, outer_sample, entry, label)
                offset = (point["i"] - bounds["its"]) + (point["k"] - bounds["kts"]) * nx_tile
                q_offset = (point["i"] - bounds["ims"]) + (point["k"] - bounds["kms"]) * nx_memory
                outer_q = pointer_hex(outer_args[OUTER_ARG_INDEX["q"]-1]["pointer_hex"],
                                      f"{label} outer q pointer")
                inner_q = pointers[1]
                q_row_bytes = 4 * nx_memory * nk_memory
                q_row_delta = inner_q - outer_q
                require(q_row_delta >= 0 and q_row_delta % q_row_bytes == 0,
                        f"{label}: inner q pointer is not an outer q row alias")
                derived_j = outer_memory["jms"] + q_row_delta // q_row_bytes
                require(derived_j == point["j"],
                        f"{label}: q row alias identifies j={derived_j}, expected {point['j']}")
                addresses = {"qrs": pointers[3] + 4 * offset,
                             "qci": pointers[2] + 4 * offset,
                             "q": inner_q + 4 * q_offset,
                             "t": pointers[0] + 4 * offset,
                             "nci": pointers[4] + 4 * offset,
                             "nrs": pointers[5] + 4 * offset}
                for field in INNER_FIELDS:
                    require(raw_address(entry["entry"][field], f"{label} entry {field}") == addresses[field],
                            f"{label}: inner {field} entry address differs from bounds/index")
                entry_records[label] = (rank, inner, entry)
            returned = inner.get("return")
            require(returned is not None and returned.get("pc") == INNER_RETURN_PC,
                    f"rank {rank}: missing inner return record")
            ret_by_label = {point.get("label"): point for point in returned.get("points", [])}
            require(set(ret_by_label) == {p["label"] for p in point_entries},
                    f"rank {rank}: inner return point set differs")
            for entry in point_entries:
                label = entry["label"]
                require(label not in return_records, f"duplicate inner return for {label}")
                ret = ret_by_label[label]
                require(ret.get("label") == label and
                        all(ret.get(name, targets[label][name]) == targets[label][name]
                            for name in ("i", "j", "k")),
                        f"inner return coordinate mismatch for {label}")
                point = targets[label]
                offset = (point["i"] - bounds["its"]) + (point["k"] - bounds["kts"]) * nx_tile
                q_offset = (point["i"] - bounds["ims"]) + (point["k"] - bounds["kms"]) * nx_memory
                addresses = {"qrs": pointers[3] + 4 * offset,
                             "qci": pointers[2] + 4 * offset,
                             "q": pointers[1] + 4 * q_offset,
                             "t": pointers[0] + 4 * offset,
                             "nci": pointers[4] + 4 * offset,
                             "nrs": pointers[5] + 4 * offset}
                for field in INNER_FIELDS:
                    require(raw_address(ret["values"][field], f"{label} return {field}") == addresses[field],
                            f"{label}: inner {field} return address differs from bounds/index")
                return_records[label] = (rank, inner, ret)
            if inner.get("watch_target"):
                label = inner["watch_target"]
                require(label in WATCH_TARGET_RANK, f"unexpected watch target {label}")
                require(rank == WATCH_TARGET_RANK[label], f"watch target owner mismatch for {label}")
                require(label not in event_by_target, f"duplicate watch target {label}")
                event_by_target[label] = (rank, inner)
        for event in record.get("write_events", []):
            watch_events.append((rank, event))

    require(set(entry_records) == TARGET_LABELS, "missing or orphan inner entry targets")
    require(set(return_records) == TARGET_LABELS, "missing or orphan inner return targets")
    require(set(event_by_target) == set(WATCH_TARGET_RANK), "missing or orphan hardware watch target")

    event_numbers = Counter()
    for rank, event in watch_events:
        ordinal = int(event.get("ordinal", -1))
        require(ordinal > 0, f"rank {rank}: invalid watch event ordinal")
        event_numbers[(rank, ordinal)] += 1
        require(event.get("target") in WATCH_TARGET_RANK, f"rank {rank}: event has unknown target")
        target = event["target"]
        require(rank == WATCH_TARGET_RANK[target], f"rank {rank}: event owner differs for {target}")
        require(event.get("field") in WATCH_FIELDS, f"rank {rank}: event field is not watched")
        require(event.get("mechanism") == "hardware_write_watchpoint_unsigned_32_bit",
                f"rank {rank}: event mechanism is not hardware write watchpoint")
        require(str(event.get("rank")) == rank and event.get("pid") ==
                next(record["pid"] for record in records if str(record["rank"]) == rank),
                f"rank {rank}: watch event process identity differs")
        info = event.get("gdb_breakpoint_info", "").lower()
        require("hardware watchpoint" in info or "hw watchpoint" in info,
                f"rank {rank}: GDB did not report a hardware watchpoint")
        require("pc_after_write_hex" in event and "instructions_near_pc" in event and
                "backtrace" in event and event.get("registers_at_watchpoint"),
                f"rank {rank}: watch event lacks PC/backtrace/instruction evidence")
        require(pointer_hex(event["pc_after_write_hex"], f"rank {rank} watch PC") != 0 and
                isinstance(event["instructions_near_pc"], str) and
                isinstance(event["backtrace"], str),
                f"rank {rank}: malformed watchpoint execution context")
        before = bytes.fromhex(event.get("raw_before_hex", ""))
        after = bytes.fromhex(event.get("raw_after_hex", ""))
        require(len(before) == len(after) == 4, f"rank {rank}: watch event raw width differs")
        actual_after = event.get("values_after_write", {}).get(event["field"], {})
        require(bytes.fromhex(actual_after.get("raw_hex", "")) == after,
                f"rank {rank}: watch event after bytes disagree")
        for field in INNER_FIELDS:
            raw4(event["values_after_write"][field], f"rank {rank} event {ordinal} {field}")
    require(all(count == 1 for count in event_numbers.values()), "duplicate watch event ordinal")
    for rank in {rank for rank, _ in watch_events}:
        ordinals = sorted(ordinal for (event_rank, ordinal), count in event_numbers.items()
                          if event_rank == rank)
        require(ordinals == list(range(1, len(ordinals) + 1)),
                f"rank {rank}: watch event sequence has gaps")
        require(len(ordinals) <= 256, f"rank {rank}: watch event count exceeds capture limit")

    for label, (rank, inner) in event_by_target.items():
        events = sorted((event for event_rank, event in watch_events
                         if event_rank == rank and event.get("target") == label),
                        key=lambda event: event["ordinal"])
        require(len(events) == inner.get("watch_event_count"), f"{label}: watch event count differs")
        entry = next(point for point in inner["points"] if point["label"] == label)["entry"]
        returned = next(point for point in inner["return"]["points"] if point["label"] == label)["values"]
        state = {field: raw4(entry[field], f"{label} entry {field}") for field in WATCH_FIELDS}
        for event in events:
            field = event["field"]
            before, after = bytes.fromhex(event["raw_before_hex"]), bytes.fromhex(event["raw_after_hex"])
            require(before == state[field], f"{label}: discontinuous {field} watchpoint chain")
            state[field] = after
        for field in WATCH_FIELDS:
            require(state[field] == raw4(returned[field], f"{label} return {field}"),
                    f"{label}: watchpoint chain does not reach inner return for {field}")
        qrs_events = [event["ordinal"] for event in events if event["field"] == "qrs"]
        require(inner.get("first_qrs_watch_event") == (qrs_events[0] if qrs_events else None),
                f"{label}: first qrs event index differs")
        # Confirm every event address points to the target's candidate work buffer.
        pointers = validate_inner_argument_vector(inner, rank)
        bounds = inner["candidate_bounds"]
        point = targets[label]
        nx_tile = bounds["ite"] - bounds["its"] + 1
        offset = (point["i"]-bounds["its"]) + (point["k"]-bounds["kts"])*nx_tile
        nx_memory = bounds["ime"] - bounds["ims"] + 1
        q_offset = (point["i"]-bounds["ims"]) + (point["k"]-bounds["kms"])*nx_memory
        addresses = {"qrs": pointers[3] + 4*offset, "qci": pointers[2] + 4*offset,
                     "q": pointers[1] + 4*q_offset, "t": pointers[0] + 4*offset,
                     "nci": pointers[4] + 4*offset, "nrs": pointers[5] + 4*offset}
        for event in events:
            require(pointer_hex(event["watched_address_hex"], f"{label} watch address") ==
                    addresses[event["field"]],
                    f"{label}: watch event address does not match selected buffer point")
            for field in INNER_FIELDS:
                require(raw_address(event["values_after_write"][field],
                                    f"{label} event {event['ordinal']} {field}") ==
                        addresses[field],
                        f"{label}: event snapshot {field} points at the wrong address")

    return {"entry_records": entry_records, "return_records": return_records,
            "watch_events": watch_events, "target_count": len(TARGET_LABELS)}


def reject_failed_capture(capture_dir):
    failed = sorted(capture_dir.glob("failed_*.json"))
    temporary = sorted(capture_dir.glob(".*.tmp*"))
    require(not failed, "capture contains native failure markers: " + ", ".join(p.name for p in failed))
    require(not temporary, "capture contains unfinished temporary artifacts: " + ", ".join(p.name for p in temporary))


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_json_constant)
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc


def read_new_stage(capture_dir, arm, prepare_path):
    reject_failed_capture(capture_dir)
    receipt_path = capture_dir / "receipt.json"
    context_path = capture_dir / "context.json"
    receipt = load_json(receipt_path)
    context = load_json(context_path)
    preparation = load_json(prepare_path)
    prepare_hash = sha256_file(prepare_path)
    require(receipt.get("status") == "FIRST_INNER_CAPTURED_INTENTIONAL_STOP",
            "new capture receipt status is not complete")
    require(receipt.get("forecast_status") == "NOT_COMPLETED", "forecast status must remain NOT_COMPLETED")
    require(receipt.get("arm") == arm and context.get("arm") == arm, "capture arm mismatch")
    require(receipt.get("ranks") == EXPECTED_RANKS and context.get("expected_ranks") == EXPECTED_RANKS,
            "capture rank count mismatch")
    require(receipt.get("context_sha256") == sha256_file(context_path), "context file hash mismatch")
    require(receipt.get("context") == context, "receipt context differs from context file")
    source_helper = ROOT / "docs/evidence/cp02_thermo_response_20261029/capture_plan/capture_thermo_response.gdb"
    helper_hash = sha256_file(source_helper)
    archived_helper = capture_dir / "capture_thermo_response.gdb"
    require(archived_helper.is_file() and sha256_file(archived_helper) == helper_hash and
            receipt.get("helper_sha256") == context.get("helper_sha256") == helper_hash,
            "helper hash mismatch")
    require(receipt.get("binary", {}).get("sha256") == EXPECTED_BINARY_SHA256 == context.get("binary_sha256"),
            "binary hash mismatch")
    require(receipt.get("binary", {}).get("size_bytes") == preparation.get("binary", {}).get("size_bytes"),
            "binary size differs from frozen preparation")
    require(receipt.get("binary", {}).get("build_id", EXPECTED_BUILD_ID) == EXPECTED_BUILD_ID == context.get("build_id"),
            "binary BuildID mismatch")
    require(receipt.get("selection_sha256") == EXPECTED_SELECTION_SHA256 == context.get("selection_sha256"),
            "selection hash mismatch")
    expected_context_id = arm.lower() + "_first_inner"
    require(context.get("stage_id") == expected_context_id,
            "capture stage ID differs from the arm contract")
    profile = context.get("intel_profile", {})
    profile_path = ROOT / "tests/intel_toolchain.sh"
    validate_profile_binding(profile, profile_path)
    require(receipt.get("input_files_unchanged") == receipt.get("original_input_files_unchanged") == 88,
            "expected 88 unchanged input pairs")
    require(receipt.get("prepare_receipt_sha256") == prepare_hash and
            context.get("run_receipt_sha256") == prepare_hash,
            "frozen preparation receipt hash mismatch")
    require(preparation.get("copy_manifest_sha256") ==
            receipt.get("input_manifest_sha256", preparation.get("copy_manifest_sha256")),
            "input copy manifest hash differs from frozen preparation")
    require(preparation.get("copy_manifest_sha256") == EXPECTED_COPY_MANIFEST_SHA256,
            "preparation does not bind the reviewed PR126 copy manifest")
    copy_manifest_path = ROOT / "docs/evidence/cp02_kdm6_controls_20261029/inputs/copy_manifest.json"
    require(sha256_file(copy_manifest_path) == EXPECTED_COPY_MANIFEST_SHA256,
            "reviewed PR126 copy manifest bytes differ")
    require(arm in preparation.get("arms", {}), "arm absent from frozen preparation receipt")
    prepared_files = preparation["arms"][arm]["files"]
    expected_inputs = {item["destination_name"]: item["sha256"] for item in prepared_files}
    input_checks = receipt.get("input_checks", [])
    recorded_inputs = {item.get("name"): item.get("sha256")
                       for item in input_checks if item.get("source_and_copy_unchanged") is True}
    require(len(prepared_files) == 88 and len(expected_inputs) == 88 and
            len(input_checks) == 88 and recorded_inputs == expected_inputs,
            "capture input check inventory differs from frozen preparation")
    require(receipt.get("initial_history", {}).get("byte_identical") is True,
            "initial history is not byte-identical")
    require(type(receipt.get("launcher_exit")) is int and receipt.get("launcher_exit") == 255,
            "diagnostic stop exit code differs")
    require(receipt.get("runtime_mapped_files") is not None and "unavailable_mappings" in receipt,
            "runtime mapping inventory is absent")
    require(isinstance(receipt["runtime_mapped_files"], dict) and
            isinstance(receipt["unavailable_mappings"], list),
            "runtime mapping inventory has the wrong shape")
    captures = receipt.get("captures", [])
    require(len(captures) == EXPECTED_RANKS, "new receipt must pin eight raw captures")
    capture_names = [Path(item.get("path", "")).name for item in captures]
    require(len(set(capture_names)) == EXPECTED_RANKS, "new receipt duplicates raw capture paths")
    on_disk_names = {path.name for path in capture_dir.glob("raw_*_rank*_pid*.json.gz")}
    require(on_disk_names == set(capture_names), "raw capture file inventory differs from receipt")
    records = []
    for item in captures:
        name = Path(item["path"]).name
        path = capture_dir / name
        require(path.is_file(), f"missing new raw capture {name}")
        payload = path.read_bytes()
        require(hashlib.sha256(payload).hexdigest() == item.get("sha256"), f"compressed hash mismatch: {name}")
        require(len(payload) == item.get("size_bytes"), f"compressed size mismatch: {name}")
        raw = gzip.decompress(payload)
        require(hashlib.sha256(raw).hexdigest() == item.get("uncompressed_sha256"), f"raw hash mismatch: {name}")
        require(len(raw) == item.get("uncompressed_size_bytes"), f"raw size mismatch: {name}")
        record = json.loads(raw, parse_constant=reject_json_constant)
        require(record.get("stage_id") == context.get("stage_id"), f"stage ID mismatch: {name}")
        require(record.get("arm") == arm and record.get("status") == "all_ranks_settled", f"incomplete raw record: {name}")
        require(record.get("stage_context_sha256") == receipt.get("context_sha256"), f"raw context hash mismatch: {name}")
        require(record.get("binary_sha256") == EXPECTED_BINARY_SHA256 and record.get("build_id") == EXPECTED_BUILD_ID,
                f"raw binary identity mismatch: {name}")
        require(record.get("helper_sha256") == receipt.get("helper_sha256") and
                record.get("selection_sha256") == EXPECTED_SELECTION_SHA256,
                f"raw helper/selection hash mismatch: {name}")
        require(record.get("run_receipt_sha256") == context.get("run_receipt_sha256"),
                f"raw run receipt hash mismatch: {name}")
        require(record.get("expected_ranks") == EXPECTED_RANKS and
                str(record.get("rank")) in {str(n) for n in range(EXPECTED_RANKS)},
                f"raw rank metadata invalid: {name}")
        maps_name = Path(record.get("proc_maps_file", "")).name
        maps_path = capture_dir / maps_name
        require(maps_path.is_file() and sha256_file(maps_path) == record.get("proc_maps_sha256"),
                f"runtime maps hash mismatch: rank {record.get('rank')}")
        require(record.get("proc_maps_sha256") and maps_path.stat().st_size > 0,
                f"runtime maps evidence is empty: rank {record.get('rank')}")
        records.append(record)
    require({str(record.get("rank")) for record in records} == {str(n) for n in range(EXPECTED_RANKS)},
            "new raw rank set differs")
    require(len({record.get("pid") for record in records}) == EXPECTED_RANKS, "new raw PIDs are not unique")
    require({str(record.get("rank")) for record in records} ==
            {Path(item["path"]).name.split("_rank", 1)[1].split("_pid", 1)[0] for item in captures},
            "capture filenames and embedded ranks differ")
    return receipt, context, records


def read_prior_stage(prior_dir, arm, prior_summary):
    receipt = load_json(prior_dir / "receipt.json")
    require(receipt.get("arm") == arm and receipt.get("ranks") == EXPECTED_RANKS,
            "prior capture receipt arm/rank mismatch")
    require(receipt.get("status") == "TWO_CALLS_CAPTURED_INTENTIONAL_STOP" and
            receipt.get("forecast_status") == "NOT_COMPLETED", "prior first-call receipt incomplete")
    require(receipt.get("binary", {}).get("sha256") == EXPECTED_BINARY_SHA256 and
            receipt.get("selection_sha256") == EXPECTED_SELECTION_SHA256 and receipt.get("selected_points") == 624,
            "prior first-call identity/selection mismatch")
    require(receipt.get("omp_threads") == 1 and receipt.get("launcher_exit") == 255,
            "prior capture launch contract differs")
    require(receipt.get("binary", {}).get("build_id", EXPECTED_BUILD_ID) == EXPECTED_BUILD_ID,
            "prior binary BuildID mismatch")
    expected_receipt_hash = prior_summary.get(arm, {}).get("runtime_receipt_sha256")
    require(expected_receipt_hash == sha256_file(prior_dir / "receipt.json"),
            "prior runtime receipt differs from pinned PR126 summary")
    files = {}
    captures = receipt.get("captures", [])
    require(len(captures) == EXPECTED_RANKS, "prior receipt must bind eight capture files")
    require({Path(item["path"]).name for item in captures} ==
            {path.name for path in prior_dir.glob("capture_rank*_pid*.json.gz")},
            "prior raw capture inventory differs from receipt")
    for item in captures:
        path = prior_dir / Path(item["path"]).name
        payload = path.read_bytes()
        require(hashlib.sha256(payload).hexdigest() == item.get("sha256"), f"prior raw hash mismatch: {path.name}")
        require(len(payload) == item.get("size_bytes"), f"prior raw size mismatch: {path.name}")
        raw = gzip.decompress(payload)
        require(hashlib.sha256(raw).hexdigest() == item.get("uncompressed_sha256"), f"prior uncompressed hash mismatch: {path.name}")
        require(len(raw) == item.get("uncompressed_size_bytes"), f"prior uncompressed size mismatch: {path.name}")
        record = json.loads(raw, parse_constant=reject_json_constant)
        require(record.get("status") == "two_calls_returned", "prior rank capture is incomplete")
        require(record.get("rank") is not None, "prior rank identity is missing")
        files[str(record.get("rank"))] = record
    require(len(files) == EXPECTED_RANKS and
            set(files) == {str(n) for n in range(EXPECTED_RANKS)}, "prior rank set differs")
    require(len({record.get("pid") for record in files.values()}) == EXPECTED_RANKS,
            "prior rank PIDs are not unique")
    return receipt, files


def prior_call_samples(record, endpoint):
    calls = record.get("calls", [])
    require(len(calls) >= 1, f"prior rank {record.get('rank')}: missing first call")
    return calls[0][endpoint]["samples"]


def validate_outer_continuity(records, prior_by_rank, selection):
    expected_keys = {(point["i"], point["j"], point.get("k", 1)) for point in selection}
    expected_labels = {(point["i"], point["j"], point.get("k", 1)): point["label"]
                       for point in selection}
    owner_counts = {"entry": Counter(), "return": Counter()}
    outer_by_rank = {}
    owned_counts = Counter()
    optional_counts = Counter()
    for record in records:
        rank = str(record["rank"])
        outer = record.get("outer")
        require(outer is not None, f"rank {rank}: outer capture absent")
        entry, returned = outer.get("entry"), outer.get("return")
        require(entry and returned, f"rank {rank}: outer entry/return incomplete")
        require(entry.get("pc") == OUTER_ENTRY_PC and entry.get("return_pc") == OUTER_RETURN_PC,
                f"rank {rank}: outer PC contract differs")
        require(returned.get("pc") == OUTER_RETURN_PC, f"rank {rank}: outer return PC differs")
        require(entry.get("argument_count") == 77 and len(entry.get("arguments", [])) == 77,
                f"rank {rank}: outer argument record incomplete")
        arguments = entry["arguments"]
        outer_regs = entry.get("registers_hex", {})
        outer_reg_names = ("rdi", "rsi", "rdx", "rcx", "r8", "r9")
        expected_names = list(OUTER_ARG_INDEX)
        for index, reg in enumerate(outer_reg_names):
            require(pointer_hex(arguments[index].get("pointer_hex"), f"rank {rank} outer arg {index+1}") ==
                    pointer_hex(outer_regs.get(reg), f"rank {rank} outer register {reg}"),
                    f"rank {rank}: outer register mapping differs")
        for n, arg in enumerate(arguments, 1):
            expected_location = ("register:" + outer_reg_names[n-1] if n <= 6 else
                                 "stack:+%d" % (8 + 8 * (n - 7)))
            require(arg.get("index") == n and arg.get("candidate_name") == expected_names[n-1] and
                    arg.get("location") == expected_location,
                    f"rank {rank}: outer argument map differs at position {n}")
        outer_stack = bytes.fromhex(entry.get("stack_hex_from_rsp", ""))
        require(len(outer_stack) == 8 * 73, f"rank {rank}: outer stack capture length differs")
        require(struct.unpack_from("<Q", outer_stack, 0)[0] == int(OUTER_RETURN_PC, 16),
                f"rank {rank}: outer stack return address differs")
        for arg_index in range(7, 78):
            stack_value = struct.unpack_from("<Q", outer_stack, 8 + (arg_index - 7) * 8)[0]
            require(stack_value == pointer_hex(arguments[arg_index-1].get("pointer_hex"),
                                                f"rank {rank} outer arg {arg_index}"),
                    f"rank {rank}: outer argument {arg_index} differs from raw stack")
        require(all(pointer_hex(arg.get("pointer_hex"), f"rank {rank} outer arg {n}") != 0
                    for n, arg in enumerate(arguments, 1)),
                f"rank {rank}: outer argument vector contains null")
        require(entry.get("observed_itimestep") == 1 and entry.get("observed_delt") == 20.0,
                f"rank {rank}: unexpected first-call timestep/dt")
        require(entry.get("memory_bounds") == returned.get("memory_bounds", entry.get("memory_bounds")),
                f"rank {rank}: outer memory bounds changed")
        memory, tile, domain = entry.get("memory_bounds", {}), entry.get("tile_bounds", {}), entry.get("domain_bounds", {})
        for name in ("ims", "ime", "jms", "jme", "kms", "kme"):
            require(type(memory.get(name)) is int, f"rank {rank}: invalid outer memory bound {name}")
        for name in ("its", "ite", "jts", "jte", "kts", "kte"):
            require(type(tile.get(name)) is int, f"rank {rank}: invalid outer tile bound {name}")
        for name in ("ids", "ide", "jds", "jde", "kds", "kde"):
            require(type(domain.get(name)) is int, f"rank {rank}: invalid outer domain bound {name}")
        require(0 < memory["ime"]-memory["ims"]+1 <= 1000 and
                0 < memory["jme"]-memory["jms"]+1 <= 1000 and
                0 < memory["kme"]-memory["kms"]+1 <= 1000,
                f"rank {rank}: invalid outer memory extent")
        require(memory["ims"] <= tile["its"] <= tile["ite"] <= memory["ime"] and
                memory["jms"] <= tile["jts"] <= tile["jte"] <= memory["jme"] and
                memory["kms"] <= tile["kts"] <= tile["kte"] <= memory["kme"],
                f"rank {rank}: outer tile bounds exceed memory bounds")
        new_entry, prior_entry = entry["samples"], prior_call_samples(prior_by_rank[rank], "entry")
        new_return, prior_return = returned["samples"], prior_call_samples(prior_by_rank[rank], "return")
        for endpoint, samples in (("entry", new_entry), ("return", new_return)):
            sample_index(samples, f"rank {rank} {endpoint} address map")
            bounds = entry.get("memory_bounds", {})
            for sample in samples:
                if sample.get("status") != "owned_tile":
                    continue
                require(set(sample.get("values", {})) == set(OUTER_FIELDS),
                        f"rank {rank} {endpoint}: owned outer field set differs")
                for field in OUTER_FIELDS:
                    actual = raw_address(sample["values"][field], f"rank {rank} {endpoint} {field}",
                                         allow_nonfinite=field in OPTIONAL_FIELDS)
                    require(actual == expected_outer_address(arguments, sample, bounds, field),
                            f"rank {rank} {endpoint}: {field} pointer/index address mismatch at {coordinate_key(sample)}")
        new_entry_index = sample_index(new_entry, f"rank {rank} entry")
        new_return_index = sample_index(new_return, f"rank {rank} return")
        require(all(new_entry_index[key].get("status") == new_return_index[key].get("status")
                    for key in expected_keys),
                f"rank {rank}: outer point ownership changed between entry and return")
        owned_counts["entry"] += validate_outer_samples(new_entry, prior_entry, expected_keys,
                                                        expected_labels, optional_counts, "entry",
                                                        f"rank {rank} entry")
        owned_counts["return"] += validate_outer_samples(new_return, prior_return, expected_keys,
                                                         expected_labels, optional_counts, "return",
                                                         f"rank {rank} return")
        outer_by_rank[rank] = {"entry": new_entry_index,
                               "return": new_return_index,
                               "memory_bounds": entry["memory_bounds"],
                               "tile_bounds": entry["tile_bounds"],
                               "arguments": arguments}
        for endpoint, samples in (("entry", new_entry), ("return", new_return)):
            for sample in samples:
                if sample.get("status") == "owned_tile":
                    owner_counts[endpoint][coordinate_key(sample)] += 1
    expected_core_comparisons = 624 * len(CORE_OUTER_FIELDS)
    require(owned_counts["entry"] == owned_counts["return"] == expected_core_comparisons,
            "outer owner samples do not total 624 at both endpoints")
    require(all(owner_counts[endpoint][key] == 1 for endpoint in owner_counts for key in expected_keys),
            "outer point ownership is missing or duplicated")
    return outer_by_rank, optional_counts


def validate_selection(path):
    require(sha256_file(path) == EXPECTED_SELECTION_SHA256, "selection SHA-256 mismatch")
    data = json.loads(path.read_text(encoding="utf-8"))
    points = data if isinstance(data, list) else data.get("points", [])
    require(len(points) == 624 and len({(p["i"], p["j"], p.get("k", 1)) for p in points}) == 624,
            "selection must contain 624 unique coordinates")
    selected_targets(points)
    return points


def summarize(capture_dir, prior_dir, selection_path, prepare_path, arm):
    capture_dir, prior_dir = Path(capture_dir), Path(prior_dir)
    selection = validate_selection(Path(selection_path))
    receipt, context, records = read_new_stage(capture_dir, arm, Path(prepare_path))
    prior_root = prior_dir.parent.parent
    prior_summary_path = prior_root / "analysis/summary.json"
    prior_profiles_path = prior_root / "analysis/selected_profiles.csv"
    require(sha256_file(prior_summary_path) == EXPECTED_PRIOR_SUMMARY_SHA256,
            "prior PR126 summary hash differs from the reviewed capture")
    require(sha256_file(prior_profiles_path) == EXPECTED_PRIOR_PROFILES_SHA256,
            "prior PR126 selected profiles hash differs from the reviewed capture")
    prior_summary_doc = load_json(prior_summary_path)
    prior_summary = {row["arm"]: row for row in prior_summary_doc.get("arms", [])}
    prior_receipt, prior = read_prior_stage(prior_dir, arm, prior_summary)
    require(receipt.get("initial_history", {}).get("sha256") ==
            prior_receipt.get("initial_history", {}).get("sha256") and
            receipt.get("initial_history", {}).get("byte_identical") is True,
            "new capture initial history is not bound to prior PR126 input")
    outer_by_rank, optional_counts = validate_outer_continuity(records, prior, selection)
    targets = selected_targets(selection)
    inner = validate_inner_records(records, targets, outer_by_rank)

    samples = []
    for label in sorted(TARGET_LABELS):
        rank, event, entry = inner["entry_records"][label]
        ret_rank, ret_event, returned = inner["return_records"][label]
        require(rank == ret_rank, f"{label}: owner rank changed between inner endpoints")
        for endpoint, values in (("entry", entry["entry"]), ("return", returned["values"])):
            row = {"arm": arm, "label": label, "i": targets[label]["i"], "j": targets[label]["j"],
                   "k": targets[label]["k"], "rank": rank, "endpoint": endpoint,
                   "inner_event_id": event["event_id"]}
            for field in INNER_FIELDS:
                row[field+"_raw_hex"] = values[field]["raw_hex"]
                row[field+"_f32"] = values[field]["value_f32"]
            samples.append(row)

    summary = {"schema": "cp02-kdm6-inner-response-v1",
        "status": "PASS_SCOPED_CAPTURE_CONTINUITY",
        "scope": "The 25 required outer arrays match the prior first-call capture byte-for-byte at 624 selected points for entry and return. Four optional outer arrays are compared and counted separately without gating pass. Internal candidate buffers and hardware-watchpoint transitions were validated. Candidate ABI labels do not establish source identity, physical units, process attribution, conservation, or forecast skill.",
        "arm": arm, "stage_id": context["stage_id"], "forecast_status": "NOT_COMPLETED",
        "binary_sha256": EXPECTED_BINARY_SHA256, "build_id": EXPECTED_BUILD_ID,
        "helper_sha256": receipt["helper_sha256"],
        "context_sha256": receipt["context_sha256"],
        "prepare_receipt_sha256": receipt["prepare_receipt_sha256"],
        "selection_sha256": EXPECTED_SELECTION_SHA256,
        "prior_capture_receipt_sha256": sha256_file(prior_dir/"receipt.json"),
        "capture_receipt_sha256": sha256_file(capture_dir/"receipt.json"),
        "capture_files": [
            {"rank": str(record["rank"]), "pid": record["pid"],
             "path": Path(item["path"]).name, "sha256": item["sha256"],
             "size_bytes": item["size_bytes"],
             "uncompressed_sha256": item["uncompressed_sha256"],
             "uncompressed_size_bytes": item["uncompressed_size_bytes"]}
            for item in sorted(receipt["captures"], key=lambda capture:
                               int(Path(capture["path"]).name.split("_rank", 1)[1].split("_pid", 1)[0]))
            for record in records
            if Path(item["path"]).name.split("_rank", 1)[1].split("_pid", 1)[0] == str(record["rank"])
        ],
        "analysis_tool_sha256": sha256_file(Path(__file__)),
        "ranks": EXPECTED_RANKS, "outer_points_per_endpoint": 624,
        "outer_byte_equal_values": owned_counts_value(records, selection),
        "outer_core_fields": list(CORE_OUTER_FIELDS),
        "outer_optional_fields": sorted(OPTIONAL_FIELDS),
        "outer_optional_byte_comparison_by_endpoint": {
            endpoint: {
                field: {name: optional_counts[(endpoint, field, name)] for name in
                        ("compared", "byte_equal", "byte_different", "new_nonfinite", "prior_nonfinite")}
                for field in sorted(OPTIONAL_FIELDS)
            }
            for endpoint in ("entry", "return")
        },
        "inner_target_points": len(TARGET_LABELS), "inner_endpoints": 2,
        "hardware_watchpoint_targets": sorted(WATCH_TARGET_RANK),
        "hardware_write_events": len(inner["watch_events"]),
        "watchpoint_event_count_by_rank": dict(Counter(rank for rank, _ in inner["watch_events"])),
        "inner_calls": [
            {"rank": str(record["rank"]), "event_id": call["event_id"],
             "points": [point["label"] for point in call["points"]],
             "null_argument_positions": call.get("null_argument_positions", []),
             "unavailable_pointer_positions": call.get("null_argument_positions", []),
             "candidate_bounds": call.get("candidate_bounds"),
             "current_j_provenance": call.get("current_j_provenance")}
            for record in records for call in record.get("inner", [])
        ],
        "observed_itimestep": 1, "observed_delt": 20.0,
        "source_mapping": "candidate names from co-located source; executable has no DWARF source identity"}
    return summary, samples, inner["watch_events"]


def analyze(capture_dir, prior_dir, selection_path, prepare_path, arm):
    return summarize(capture_dir, prior_dir, selection_path, prepare_path, arm)


def owned_counts_value(records, selection):
    return 624 * len(CORE_OUTER_FIELDS) * 2


def write_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def publish(output_dir, summary, samples, events):
    output_dir = Path(output_dir)
    require(not output_dir.exists() and not output_dir.is_symlink(),
            f"output directory already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="."+output_dir.name+".", dir=output_dir.parent))
    try:
        (temp/"summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        sample_columns = ["arm", "label", "i", "j", "k", "rank", "endpoint", "inner_event_id"] + [f+suffix for f in INNER_FIELDS for suffix in ("_raw_hex", "_f32")]
        write_csv(temp/"inner_samples.csv", samples, sample_columns)
        event_rows = []
        for rank, event in events:
            event_rows.append({"rank": rank, "ordinal": event["ordinal"], "target": event["target"],
                "field": event["field"], "watched_address_hex": event["watched_address_hex"],
                "raw_before_hex": event["raw_before_hex"], "raw_after_hex": event["raw_after_hex"],
                "mechanism": event["mechanism"], "pid": event["pid"],
                "pc_after_write_hex": event["pc_after_write_hex"],
                "gdb_breakpoint_type": event["gdb_breakpoint_type"],
                "gdb_breakpoint_info": event["gdb_breakpoint_info"],
                "backtrace": event["backtrace"], "instructions_near_pc": event["instructions_near_pc"]})
        event_columns = ["rank", "pid", "ordinal", "target", "field", "mechanism",
                         "watched_address_hex", "raw_before_hex",
                         "raw_after_hex", "pc_after_write_hex", "gdb_breakpoint_type", "gdb_breakpoint_info",
                         "backtrace", "instructions_near_pc"]
        write_csv(temp/"write_events.csv", event_rows, event_columns)
        manifest = {name: sha256_file(temp/name) for name in ("summary.json", "inner_samples.csv", "write_events.csv")}
        (temp/"artifact_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        os.replace(temp, output_dir)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--prior-capture-dir", type=Path)
    parser.add_argument("--selection-json", type=Path,
                        default=ROOT/"docs/evidence/cp02_kdm6_controls_20261029/selection.json")
    parser.add_argument("--prepare-json", type=Path, default=EXPECTED_PREPARE)
    parser.add_argument("--arm", choices=("OFF", "HYDRO", "LIQUID"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    prior_dir = args.prior_capture_dir or (
        ROOT / "docs/evidence/cp02_kdm6_controls_20261029/captures" / args.arm)
    try:
        summary, samples, events = analyze(args.capture_dir, prior_dir, args.selection_json,
                                           args.prepare_json, args.arm)
        publish(args.output_dir, summary, samples, events)
    except (ValueError, OSError, KeyError, TypeError, gzip.BadGzipFile,
            json.JSONDecodeError, struct.error) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": summary["status"], "arm": summary["arm"],
                      "samples": len(samples), "write_events": len(events),
                      "output": str(args.output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
