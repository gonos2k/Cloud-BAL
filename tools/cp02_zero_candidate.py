#!/usr/bin/env python3
"""Validate the selected zero-candidate arithmetic and source path."""
import argparse
import copy
import csv
import gzip
import json
import math
import os
import re
import shutil
import struct
import tempfile
from pathlib import Path
from cp02_kdm6_inner_response import *
import cp02_source_write as source

ROOT = source.ROOT
EVIDENCE = ROOT / 'docs/evidence/cp02_zero_candidate_20261029'
WATCH_FIELDS = ('qrs', 'q')
require = source.require
scalar = source.scalar
reg = source.reg

# Scoped copies bind this capture helper and its two watched inner fields without
# changing the frozen source-write analyzer or its module globals.
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
    source_helper = EVIDENCE / "capture_plan/capture_source.gdb"
    helper_hash = sha256_file(source_helper)
    archived_helper = capture_dir / "capture_preclamp.gdb"
    require(archived_helper.is_file() and sha256_file(archived_helper) == helper_hash and
            receipt.get("helper_sha256") == context.get("helper_sha256") == helper_hash,
            "helper hash mismatch")
    require(receipt.get("binary", {}).get("sha256") == EXPECTED_BINARY_SHA256 == context.get("binary_sha256"),
            "binary hash mismatch")
    require(receipt.get("binary", {}).get("size_bytes") == preparation.get("binary", {}).get("size_bytes"),
            "binary size differs from frozen preparation")
    require(receipt.get("binary", {}).get("build_id") == EXPECTED_BUILD_ID == context.get("build_id"),
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
            receipt.get("input_manifest_sha256"),
            "input copy manifest hash differs from frozen preparation")
    require(preparation.get("copy_manifest_sha256") == EXPECTED_COPY_MANIFEST_SHA256,
            "preparation does not bind the reviewed PR126 copy manifest")
    copy_manifest_path = ROOT / "docs/evidence/cp02_kdm6_controls_20261029/inputs/copy_manifest.json"
    require(sha256_file(copy_manifest_path) == EXPECTED_COPY_MANIFEST_SHA256,
            "reviewed PR126 copy manifest bytes differ")
    require(arm in preparation.get("arms", {}), "arm absent from frozen preparation receipt")
    prepared_files = preparation["arms"][arm]["files"]
    reviewed_files = load_json(copy_manifest_path)["arms"][arm]["copy_files"]
    keys = ("source_path", "destination_name", "size_bytes", "sha256")
    require([{key: item[key] for key in keys} for item in prepared_files] ==
            [{key: item[key] for key in keys} for item in reviewed_files],
            "preparation inventory differs from reviewed copy manifest")
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
        require(type(record.get("pid")) is int and record["pid"] > 0, f"invalid PID: {name}")
        require(str(item.get("rank")) == str(record.get("rank")) and type(item.get("pid")) is int and item.get("pid") == record.get("pid"),
                f"receipt rank/PID mismatch: {name}")
        expected_name = f"raw_{context['stage_id']}_rank{record.get('rank')}_pid{record['pid']}.json.gz"
        require(name == expected_name, f"capture filename rank/PID mismatch: {name}")
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
        require(maps_name == f"maps_{context['stage_id']}_rank{record['rank']}_pid{record['pid']}.txt",
                f"runtime maps filename rank/PID mismatch: {name}")
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

def validate_source_inner_records(records, targets, outer_by_rank):
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



def vector(event, name, width):
    item = event['scalar_registers'][name]
    raw = item['raw_hex64']
    require(isinstance(raw, str) and re.fullmatch('[0-9a-f]{16}', raw), 'invalid vector64 bytes')
    require(item['raw_hex32'] == raw[:8], 'vector low32 differs')
    line = re.findall(r'^zmm' + name[3:] + r'\s+(.+)$', event['registers_at_breakpoint'], re.MULTILINE)
    require(len(line) == 1, 'missing vector register text')
    match = re.search(r'v8_int64 = \{(0x[0-9a-f]+)', line[0])
    require(match and struct.pack('<Q', int(match.group(1), 16)).hex() == raw, 'vector low64 differs from register text')
    for bits, fmt in ((32, '<f'), (64, '<d')):
        value = struct.unpack(fmt, bytes.fromhex(item['raw_hex' + str(bits)]))[0]
        recorded = item['value_f' + str(bits)]
        require((math.isfinite(value) and recorded == value) or (not math.isfinite(value) and recorded is None), 'vector decode differs')
    if width is None: return None
    value = struct.unpack('<f' if width == 32 else '<d', bytes.fromhex(item['raw_hex' + str(width)]))[0]
    require(math.isfinite(value), 'nonfinite arithmetic operand')
    return value


def branch(value):
    require(math.isfinite(value), 'nonfinite branch candidate')
    return 'min' if value >= 0.0 else 'max'


def f32(value):
    require(math.isfinite(value), 'nonfinite arithmetic result')
    return struct.unpack('<f', struct.pack('<f', value))[0]


def same(value, item, width):
    require(math.isfinite(value), 'nonfinite arithmetic result')
    require(struct.pack('<f' if width == 32 else '<d', value).hex() == item['raw_hex' + str(width)], 'candidate arithmetic differs')


def validate_candidate(records, inner, arm):
    roles = [('before_array_load', 0x25ef8ca), ('before_subtract', 0x25ef8d8),
             ('before_convert_to_double', 0x25ef8dc), ('before_double_multiply', 0x25ef8e7),
             ('before_product', 0x25ef928), ('before_divide', 0x25ef933),
             ('before_convert_to_single', 0x25ef93c), ('before_single_multiply', 0x25ef940),
             ('before_compare', 0x25ef944), ('before_branch', 0x25ef947)]
    rows = []
    for record in records:
        if str(record['rank']) not in source.producer.TARGETS.values():
            require(not record['candidate_events'] and not record['b_events'], 'unselected rank has candidate events')
    for target, rank in source.producer.TARGETS.items():
        record = next(r for r in records if str(r['rank']) == rank)
        events = record['candidate_events']
        require([(e['role'], int(e['pc_hex'], 16)) for e in events] == roles, 'candidate stage sequence differs')
        first = events[0]; index = first['index_r15']; frame_addr = int(first['frame_rbx_hex'], 16)
        for event in events:
            text = event['registers_at_breakpoint']; frame = bytes.fromhex(event['frame_rbx_raw_hex'])
            require(event['target'] == target and event['index_r15'] == index == reg(text, 'r15'), 'candidate target/index differs')
            require(len(frame) == 0x960 and int(event['frame_rbx_hex'], 16) == frame_addr == reg(text, 'rbx'), 'candidate frame differs')
            require(reg(text, 'rip') == int(event['pc_hex'], 16), 'candidate PC differs')
            mxcsr = event['mxcsr']
            require(type(mxcsr) is int and mxcsr == reg(text, 'mxcsr'), 'MXCSR differs from register text')
            require((mxcsr & 0x6000) == 0, 'non-nearest MXCSR rounding unsupported')
            require((mxcsr & 0x8040) == 0, 'FTZ/DAZ unsupported for arithmetic reconstruction')
            operands = event['operands']
            require(set(operands) == {'array_0x1b8', 'array_0xb0', 'array_0x120', 'array_0xe8', 'array_0x160', 'constant_34b9028', 'constant_34bbaf4', 'frame_0x18', 'frame_0x50', 'frame_0x140'}, 'operand inventory differs')
            for offset in (0x1b8, 0xb0, 0x120, 0xe8, 0x160):
                item = operands['array_0x%x' % offset]; width = 8 if offset in (0xe8, 0x160) else 4
                require(int(item['address_hex'], 16) == struct.unpack_from('<Q', frame, offset)[0] + width * index, 'candidate operand address differs')
                if width == 4: scalar(item, 'candidate operand')
                else:
                    raw = bytes.fromhex(item['raw_hex']); require(len(raw) == 8, 'double operand size differs')
                    value = struct.unpack('<d', raw)[0]
                    require(math.isfinite(value) and item['finite'] is True and item['value_f64'] == value, 'double operand differs')
            const = operands['constant_34b9028']; scalar(const, 'constant')
            require(int(const['address_hex'], 16) == 0x34b9028, 'constant address differs')
            for off in (0x18, 0x50, 0x140):
                item = operands['frame_0x%x' % off]; scalar(item, 'candidate frame operand')
                require(int(item['address_hex'], 16) == frame_addr + off and bytes.fromhex(item['raw_hex']) == frame[off:off+4], 'candidate frame operand differs')
            scalar(operands['constant_34bbaf4'], 'minimum divisor')
            require(int(operands['constant_34bbaf4']['address_hex'], 16) == 0x34bbaf4, 'minimum constant address differs')
            require(set(event['scalar_registers']) == {'xmm0','xmm1','xmm2','xmm4','xmm5','xmm6'}, 'candidate register inventory differs')
            for name in event['scalar_registers']:
                # Both interpretations are checked; the active interpretation must be finite below.
                item = event['scalar_registers'][name]
                vector(event, name, None)
        by = {e['role']: e for e in events}
        for name in ('array_0x1b8','array_0xb0','array_0x120','array_0xe8','array_0x160','constant_34b9028','constant_34bbaf4'):
            require(all(e['operands'][name] == first['operands'][name] for e in events), 'candidate operand changed')
        def v(role, name, width): return vector(by[role], name, width)
        def item(role, name): return by[role]['scalar_registers'][name]
        a = scalar(first['operands']['array_0x1b8'], 'candidate input')
        const = scalar(first['operands']['constant_34b9028'], 'constant')
        factor = struct.unpack('<d', bytes.fromhex(first['operands']['array_0xe8']['raw_hex']))[0]
        divisor = struct.unpack('<d', bytes.fromhex(first['operands']['array_0x160']['raw_hex']))[0]
        require(divisor != 0, 'zero candidate divisor')
        require(first['operands']['array_0xe8']['raw_hex'] in ('0000000000000000','0000000000000080') and factor == 0.0, 'REAL64 factor is not exact zero')
        same(const, item('before_subtract', 'xmm6'), 32)
        same(const, item('before_single_multiply', 'xmm6'), 32)
        same(a, item('before_subtract', 'xmm2'), 32)
        difference = f32(a - const); same(difference, item('before_convert_to_double', 'xmm2'), 32)
        same(float(difference), item('before_double_multiply', 'xmm2'), 64)
        product = float(difference) * factor; same(product, item('before_product', 'xmm2'), 64)
        other = v('before_product', 'xmm4', 64)
        require(difference != 0.0 and other != 0.0, 'candidate factors do not establish zero origin')
        product2 = other * product; same(product2, item('before_divide', 'xmm4'), 64)
        quotient = product2 / divisor; same(quotient, item('before_convert_to_single', 'xmm4'), 64)
        single = f32(quotient); same(single, item('before_single_multiply', 'xmm0'), 32)
        candidate = f32(single * const); same(candidate, item('before_compare', 'xmm0'), 32)
        same(candidate, item('before_branch', 'xmm0'), 32)
        require(item('before_compare','xmm0')['raw_hex32'] in ('00000000','00000080'), 'candidate is not bit-exact zero')
        require(v('before_compare', 'xmm5', 32) == 0.0, 'comparison zero differs')
        s = next(e for e in record['source_events'] if e['role'] == ('before_min_29d' if candidate >= 0 else 'before_max_97a'))
        require(s['event_ordinal'] > by['before_branch']['event_ordinal'], 'candidate/source chronology differs')
        operands = by['before_branch']['operands']
        bound = f32(scalar(operands['frame_0x18'], 'frame bound') / scalar(operands['constant_34bbaf4'], 'bound divisor'))
        lower = -f32(scalar(operands['frame_0x50'], 'frame lower') / scalar(operands['frame_0x140'], 'frame scale'))
        rows.append(dict(arm=arm, target=target, rank=rank, candidate=candidate,
                         bound=bound, lower_bound=lower,
                         candidate_raw_hex=item('before_compare','xmm0')['raw_hex32'],
                         input=a, difference=difference, factor64=factor, factor64_raw_hex=first['operands']['array_0xe8']['raw_hex'], other_factor64=other,
                         divisor64=divisor, branch=branch(candidate),
                         mxcsr=hex(first['mxcsr']), ftz=False, daz=False))
    return rows


def counterfactual(value, bound, lower):
    require(all(math.isfinite(x) for x in (value, bound, lower)), 'nonfinite counterfactual')
    if branch(value) == 'min': return value if value < bound else bound
    first = value if value > lower else lower
    return first if first > bound else bound


def validate_chronology(records, inner):
    scoped = copy.deepcopy(records)
    for record in scoped:
        for name in ('candidate_events', 'b_events'):
            events = record.pop(name)
            require([e['event_ordinal'] for e in events] == sorted(e['event_ordinal'] for e in events), 'event list chronology differs')
            record['write_events'].extend(events)
        record['write_events'].sort(key=lambda e: e['event_ordinal'])
    source.validate_chronology(scoped, inner)
    for record in records:
        events = [record['outer']['entry'], record['outer']['return']]
        for call in record['inner']: events.extend((call, call['return']))
        for name in ('write_events','source_events','producer_events','preclamp_events','candidate_events','b_events'):
            events.extend(record[name])
        events.sort(key=lambda e: e['event_ordinal'])
        require(all(type(e['callback_ordinal']) is int and e['callback_ordinal'] > 0 and e['selected_inner_id'] == e['inner_call_id'] for e in events), 'callback identity differs')
        callbacks = [e['callback_ordinal'] for e in events]
        require(callbacks == sorted(callbacks), 'callback chronology differs')


def raw32(item):
    raw = item['raw_hex']
    require(isinstance(raw, str) and re.fullmatch('[0-9a-f]{8}', raw), 'invalid REAL32 bits')
    value = struct.unpack('<f', bytes.fromhex(raw))[0]
    require((math.isfinite(value) and item['value_f32'] == value) or (not math.isfinite(value) and item['value_f32'] is None), 'REAL32 decode differs')
    if 'finite' in item: require(item['finite'] is math.isfinite(value), 'REAL32 finite flag differs')
    return value


def b_register(event, name):
    item = event['scalar_registers'][name]; value = raw32(item)
    line = re.findall(r'^zmm' + name[3:] + r'\s+(.+)$', event['registers_at_breakpoint'], re.MULTILINE)
    require(len(line) == 1, 'B register text missing')
    match = re.search(r'v16_int32 = \{(0x[0-9a-f]+)', line[0])
    require(match and struct.pack('<I', int(match.group(1),16)).hex() == item['raw_hex'], 'B register text differs')
    return value


def validate_b_writer(events, address):
    expected = [('before_b_min', 0x25e5c4a), ('before_b_divide', 0x25e5c63),
                ('before_b_floor', 0x25e5c6f), ('before_b_store', 0x25e5c77)]
    require([(e['role'], int(e['pc_hex'],16)) for e in events] == expected, 'B writer sequence differs')
    for event in events:
        frame = bytes.fromhex(event['frame_rbx_raw_hex']); text = event['registers_at_breakpoint']
        rbx = reg(text, 'rbx'); index = reg(text, 'r14')
        require(len(frame) == 0x960 and int(event['frame_rbx_hex'],16) == rbx and event['index_r14_bytes'] == index, 'B writer frame/index differs')
        require(reg(text,'rip') == int(event['pc_hex'],16) and int(event['address_hex'],16) == address == struct.unpack_from('<Q',frame,0x20)[0] + index, 'B writer PC/address differs')
        require(event['mxcsr'] == reg(text,'mxcsr') and event['mxcsr'] & 0xe040 == 0, 'B writer MXCSR unsupported')
        operands = event['operands']
        require(set(operands) == {'array_0x30','frame_0x50','frame_0x470','frame_0x1d0','constant_34c0e5c'}, 'B writer operands differ')
        for name,item in operands.items(): raw32(item)
        require(int(operands['array_0x30']['address_hex'],16) == struct.unpack_from('<Q',frame,0x30)[0]+index, 'B writer array address differs')
        for offset in (0x50,0x470,0x1d0):
            item=operands['frame_0x%x' % offset]
            require(int(item['address_hex'],16) == rbx+offset and bytes.fromhex(item['raw_hex']) == frame[offset:offset+4], 'B writer frame operand differs')
        require(int(operands['constant_34c0e5c']['address_hex'],16) == 0x34c0e5c, 'B writer constant differs')
        require(set(event['scalar_registers']) == {'xmm0','xmm1','xmm2'}, 'B writer register inventory differs')
        for name in event['scalar_registers']: b_register(event,name)
    pre, divide, floor, store = events
    v = lambda e,n: b_register(e,n)
    require(all(math.isfinite(v(pre,n)) for n in ('xmm0','xmm1','xmm2')), 'nonfinite B minimum operand')
    require(pre['scalar_registers']['xmm2']['raw_hex'] == pre['operands']['array_0x30']['raw_hex'], 'B indexed input differs')
    limit = f32(scalar(pre['operands']['constant_34c0e5c'],'B limit factor') * v(pre,'xmm2'))
    require(struct.pack('<f',limit).hex() == pre['scalar_registers']['xmm1']['raw_hex'], 'B limit product differs')
    min_value = v(pre,'xmm0') if v(pre,'xmm0') < v(pre,'xmm1') else v(pre,'xmm1')
    require(struct.pack('<f',min_value).hex() == divide['scalar_registers']['xmm0']['raw_hex'], 'B minimum differs')
    require(pre['scalar_registers']['xmm2']['raw_hex'] == divide['operands']['frame_0x50']['raw_hex'], 'B prior frame store differs')
    numerator = f32(scalar(divide['operands']['frame_0x470'],'B numerator factor') * min_value)
    denominator = f32(scalar(divide['operands']['frame_0x50'],'B prior') - min_value)
    require(struct.pack('<f',numerator).hex() == divide['scalar_registers']['xmm1']['raw_hex'] and struct.pack('<f',denominator).hex() == divide['scalar_registers']['xmm2']['raw_hex'], 'B division operands differ')
    quotient = f32(numerator / denominator)
    require(struct.pack('<f',quotient).hex() == floor['scalar_registers']['xmm1']['raw_hex'], 'B division differs')
    floor_value = scalar(floor['operands']['frame_0x1d0'],'B floor')
    require(struct.pack('<f',floor_value).hex() == floor['scalar_registers']['xmm2']['raw_hex'], 'B floor operand differs')
    result = quotient if quotient > floor_value else floor_value
    require(struct.pack('<f',result).hex() == store['scalar_registers']['xmm1']['raw_hex'], 'B maximum differs')
    return store['scalar_registers']['xmm1']['raw_hex']


def validate_b(records, rows):
    for row in rows:
        record = next(r for r in records if str(r['rank']) == row['rank'])
        events = record['b_events']; require(events and events[0]['role'] == 'arm', 'B watch arm missing')
        arm = events[0]; address = int(arm['address_hex'], 16)
        require([e['role'] for e in events] == ['arm','before_b_min','before_b_divide','before_b_floor','before_b_store'] + ['watch_access'] * 6, 'B event order differs')
        accesses = [e for e in events if e['role'] == 'watch_access']
        writers = [e for e in events if e['role'].startswith('before_b_')]
        require(len(events) == 1 + len(accesses) + len(writers), 'unknown B event')
        writer_raw = validate_b_writer(writers, address)
        require([e['pc_after_access_hex'] for e in accesses] == ['0x25e5c7d','0x25eed31','0x25ef2ee','0x25f6311','0x25f6244','0x25f6f90'], 'B access sequence differs')
        candidate = record['candidate_events'][0]; source_arm = record['source_events'][0]
        frame = bytes.fromhex(candidate['frame_rbx_raw_hex'])
        base = struct.unpack_from('<Q', frame, 0xb0)[0]
        require(address == int(arm['base_hex'], 16) + 4 * arm['offset_f32'] == base + 4 * candidate['index_r15'], 'B watch address differs')
        require(arm['pc_hex'] == '0x25e2fc0', 'B arm PC differs')
        require(int(arm['value']['address_hex'], 16) == address, 'B arm value address differs'); raw32(arm['value'])
        state = arm['value']['raw_hex']
        for event in accesses:
            require(event['role'] == 'watch_access' and int(event['address_hex'], 16) == address, 'B access differs')
            require(reg(event['registers_at_breakpoint'], 'rip') == int(event['pc_after_access_hex'], 16), 'B access PC differs')
            require(event['instructions_near_pc'], 'B access disassembly absent')
            for name in ('before', 'after'):
                require(int(event[name]['address_hex'], 16) == address, 'B value address differs'); raw32(event[name])
            require(event['before']['raw_hex'] == state, 'B access chain differs')
            if event['pc_after_access_hex'] == '0x25e5c7d':
                text = event['registers_at_breakpoint']
                require(reg(text, 'rax') + reg(text, 'r14') == address, 'B writer address differs')
                line = re.findall(r'^zmm1\s+(.+)$', text, re.MULTILINE)
                require(len(line) == 1, 'B writer xmm1 missing')
                match = re.search(r'v16_int32 = \{(0x[0-9a-f]+)', line[0])
                require(match and struct.pack('<I', int(match.group(1), 16)).hex() == event['after']['raw_hex'] == writer_raw, 'B writer value differs')
                require(writers[-1]['event_ordinal'] < event['event_ordinal'] < candidate['event_ordinal'], 'B writer chronology differs')
            state = event['after']['raw_hex']
        before = [e for e in accesses if e['event_ordinal'] < candidate['event_ordinal']]
        require(len(before) == 3, 'B access stage count differs')
        if before: state = before[-1]['after']['raw_hex']
        else: state = arm['value']['raw_hex']
        require(state == candidate['operands']['array_0xb0']['raw_hex'], 'B watch does not reach candidate')
        upstream = next(e for e in record['source_events'] if e['role'] == 'before_upstream_2cf')
        state = arm['value']['raw_hex']
        for event in accesses:
            if event['event_ordinal'] < upstream['event_ordinal']: state = event['after']['raw_hex']
        require(state == upstream['operands']['array_0xb0']['raw_hex'], 'B watch does not reach upstream')
        row.update(b_address_hex=hex(address), b_armed_raw_hex=arm['value']['raw_hex'], b_written_raw_hex=writer_raw, b_access_count=len(accesses),
                   b_last_write_before_candidate_pc='0x25e5c77', b_last_write_after_pc='0x25e5c7d',
                   b_changed_access_pcs=';'.join(e['pc_after_access_hex'] for e in accesses if e['before']['raw_hex'] != e['after']['raw_hex']))


def analyze(capture_dir, prior_dir, selection_path, prepare_path, arm):
    receipt, _, records = read_new_stage(capture_dir, arm, prepare_path)
    prior = source.producer.prior
    selection = prior.validate_selection(selection_path)
    old_root = prior_dir.parent.parent
    require(sha256_file(old_root / 'analysis/summary.json') == EXPECTED_PRIOR_SUMMARY_SHA256 and
            sha256_file(old_root / 'analysis/selected_profiles.csv') == EXPECTED_PRIOR_PROFILES_SHA256, 'prior analysis hash differs')
    summary = {r['arm']: r for r in load_json(old_root / 'analysis/summary.json')['arms']}
    old_receipt, old = prior.read_prior_stage(prior_dir, arm, summary)
    require(receipt['initial_history']['sha256'] == old_receipt['initial_history']['sha256'], 'initial history differs')
    outer, _ = prior.validate_outer_continuity(records, old, selection)
    inner = validate_source_inner_records(records, prior.selected_targets(selection), outer)
    validate_chronology(records, inner)
    legacy = copy.deepcopy(records)
    for record in legacy:
        for name in ('producer_events', 'preclamp_events'):
            for event in record[name]:
                event.pop('event_ordinal'); event.pop('inner_call_id'); event.pop('callback_ordinal'); event.pop('selected_inner_id')
    preclamp = prior.validate_events(legacy, arm)
    producer_rows = source.producer.validate_producers(legacy, arm, inner, preclamp)
    source_rows = source.validate_source(records, inner, producer_rows)
    rows = validate_candidate(records, inner, arm)
    validate_b(records, rows)
    for row in rows:
        log = (capture_dir / ('gdb_rank' + row['rank'] + '.txt')).read_text()
        for address in (row['b_address_hex'], row['source_address_hex'] if 'source_address_hex' in row else next(r['source_address_hex'] for r in source_rows if r['target'] == row['target'])):
            pattern = r'^Hardware access \(read/write\) watchpoint [0-9]+: \*\(unsigned int \*\)' + re.escape(address) + r'$'
            require(len(re.findall(pattern, log, re.MULTILINE)) == 1, 'access watch log differs')
    for row in rows:
        src = next(r for r in source_rows if r['target'] == row['target'])
        event = next(e for e in next(r for r in records if str(r['rank']) == row['rank'])['source_events'] if e['role'] == 'before_min_29d')
        require(event['scalar_registers']['xmm0']['raw_hex'] == row['candidate_raw_hex'], 'candidate does not reach minimum')
        row.update(source_raw_hex=src['written_raw_hex'], preclamp=src['qr_preclamp'], store=src['qr_store'])
    return {'arm': arm, 'status': 'PASS_SCOPED_CAPTURE_CONTINUITY', 'forecast_status': 'NOT_COMPLETED',
            'receipt_sha256': sha256_file(capture_dir / 'receipt.json'), 'helper_sha256': receipt['helper_sha256'],
            'binary_sha256': receipt['binary']['sha256'], 'analysis_tool_sha256': sha256_file(Path(__file__))}, rows


def publish(output, summaries, rows):
    import ctypes
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output = Path(output); require(not output.exists() and not output.is_symlink(), 'output directory already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.' + output.name + '.', dir=output.parent))
    try:
        scope = ('Six selected first-outer KDM6 paths. Native breakpoint observations and ordered IEEE arithmetic; physical variable identity and units are unproven. Forecast not completed. Counterfactual signs describe the binary comparison rule only and are not WRF mutations or forecasts.')
        (temp / 'summary.json').write_text(json.dumps({'schema':'cp02-zero-candidate-v1','scope':scope,'arms':summaries,
            'counterfactual_rule':{'+0':'min', '-0':'min', 'small_finite_negative':'max'}}, indent=2, sort_keys=True)+'\n')
        with (temp / 'candidate.csv').open('w', newline='') as f:
            w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        with (temp / 'counterfactual.csv').open('w', newline='') as f:
            fields = ['arm','target','input','input_raw_hex','branch','result','result_raw_hex']
            w = csv.DictWriter(f,fieldnames=fields); w.writeheader()
            for row in rows:
                for value in (0.0, -0.0, f32(-1e-12)):
                    result = counterfactual(value,row['bound'],row['lower_bound'])
                    w.writerow(dict(arm=row['arm'],target=row['target'],input=value,input_raw_hex=struct.pack('<f',value).hex(),branch=branch(value),result=result,result_raw_hex=struct.pack('<f',result).hex()))
        fig, ax = plt.subplots(figsize=(9,4), constrained_layout=True)
        ax.bar([r['arm']+' '+r['target'] for r in rows], [r['candidate'] for r in rows]); ax.axhline(0, color='black', linewidth=.7)
        ax.set_ylabel('Candidate (units unresolved)'); ax.set_title('Selected native candidates; no forecast claim')
        fig.savefig(temp / 'candidates.png', dpi=150); plt.close(fig)
        manifest = {p.name: sha256_file(p) for p in sorted(temp.iterdir())}
        (temp / 'artifact_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
        rename=ctypes.CDLL(None,use_errno=True).renameat2
        rename.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint)
        if rename(-100,os.fsencode(temp),-100,os.fsencode(output),1):
            err=ctypes.get_errno(); raise OSError(err,os.strerror(err),str(output))
    except Exception:
        shutil.rmtree(temp,ignore_errors=True); raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-root',type=Path,default=EVIDENCE/'captures')
    parser.add_argument('--prior-root',type=Path,default=ROOT/'docs/evidence/cp02_kdm6_controls_20261029/captures')
    parser.add_argument('--selection',type=Path,default=ROOT/'docs/evidence/cp02_kdm6_controls_20261029/selection.json')
    parser.add_argument('--prepare',type=Path,default=EVIDENCE/'runtime/prepare.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        results=[analyze(args.capture_root/arm,args.prior_root/arm,args.selection,args.prepare,arm) for arm in ('OFF','HYDRO','LIQUID')]
        publish(args.output,[s for s,_ in results],[r for _,rows in results for r in rows])
    except (ValueError,OSError,KeyError,TypeError,gzip.BadGzipFile,struct.error,ZeroDivisionError,OverflowError) as exc:
        parser.error(str(exc))


if __name__ == '__main__': main()
