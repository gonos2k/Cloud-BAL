#!/usr/bin/env python3
"""Validate watched writes to the source subsequently loaded into XMM6."""
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

# Source access watchpoint uses one hardware slot previously assigned to QCI.
WATCH_FIELDS = ("qrs", "q", "t")
import cp02_xmm6_producer as producer

ROOT = producer.ROOT
EVIDENCE = ROOT / 'docs/evidence/cp02_source_write_20261029'
require = producer.require
scalar = producer.scalar
reg = producer.reg


def vector(event, name):
    item = event['scalar_registers'][name]
    raw = item['raw_hex']
    require(isinstance(raw, str) and re.fullmatch('[0-9a-f]{8}', raw), 'invalid vector bytes')
    value = struct.unpack('<f', bytes.fromhex(raw))[0]
    require(math.isfinite(value) and item['value_f32'] == value, 'vector decode differs')
    line = re.findall(r'^zmm' + name[3:] + r'\s+(.+)$', event['registers_at_breakpoint'], re.MULTILINE)
    require(len(line) == 1, 'vector register text missing')
    match = re.search(r'v16_int32 = \{(0x[0-9a-f]+)', line[0])
    require(match and struct.pack('<I', int(match.group(1), 16)).hex() == raw, 'vector text differs')
    return value


def validate_chronology(records, inner):
    for record in records:
        all_events = [event for name in ('write_events', 'source_events', 'producer_events', 'preclamp_events')
                      for event in record[name]]
        structural = [record['outer']['entry'], record['outer']['return']]
        for call in record['inner']:
            require(type(call['event_id']) is int and call['inner_call_id'] == call['event_id'] and
                    call['return']['inner_call_id'] == call['event_id'], 'inner structural call ID differs')
            structural.extend([call, call['return']])
        require(all(event['inner_call_id'] is None for event in structural[:2]), 'outer call ID differs')
        ordinals = [event['event_ordinal'] for event in all_events + structural]
        require(all(type(n) is int for n in ordinals) and sorted(ordinals) == list(range(1, len(ordinals) + 1)),
                'shared event chronology differs')
        outer_entry, outer_return = (e['event_ordinal'] for e in structural[:2])
        require(outer_entry < outer_return, 'outer chronology differs')
        for call in record['inner']:
            require(outer_entry < call['event_ordinal'] < call['return']['event_ordinal'] < outer_return, 'inner boundary chronology differs')
        for event in all_events:
            target = event['target']
            require(target in producer.TARGETS and str(record['rank']) == producer.TARGETS[target], 'event owner differs')
            call = inner['entry_records'][target][1]
            require(type(event['inner_call_id']) is int and event['inner_call_id'] == call['event_id'], 'event inner call differs')
            require(call['event_ordinal'] < event['event_ordinal'] < call['return']['event_ordinal'], 'event outside selected inner call')
        for name in ('write_events', 'source_events', 'producer_events', 'preclamp_events'):
            numbers = [event['event_ordinal'] for event in record[name]]
            require(numbers == sorted(numbers), 'event list chronology differs')


def validate_source(records, inner, producer_rows):
    rows = []
    pcs = {'before_upstream_2cf': '0x25ef2cf', 'before_frame_store_2f6': '0x25ef2f6',
           'after_frame_store_2fb': '0x25ef2fb', 'before_min_29d': '0x25ef29d',
           'writer_before_2a8': '0x25ef2a8', 'writer_after_2a8': '0x25ef2ae'}
    for target, rank in producer.TARGETS.items():
        record = next(r for r in records if str(r['rank']) == rank)
        events = record['source_events']
        roles = [e['role'] for e in events]
        expected = ['arm', *pcs, 'watch_access', 'watch_access']
        if len(events) == len(expected) + 1:
            expected.append('watch_access')
        require(roles == expected, 'source stage count or sequence differs')
        arm = events[0]
        address = int(arm['address_hex'], 16)
        text = arm['registers_at_breakpoint']
        frame_addr = reg(text, 'rbx')
        frame = bytes.fromhex(arm['frame_rbx_raw_hex'])
        require(len(frame) == 0x960 and frame_addr == int(arm['frame_rbx_hex'], 16), 'arm frame differs')
        base = struct.unpack_from('<Q', frame, 0x728)[0]
        qrs_base = struct.unpack_from('<Q', frame, 0x1f0)[0]
        require(arm['pc_hex'] == '0x25ef187' and reg(text, 'rip') == int(arm['pc_hex'], 16), 'arm PC differs')
        require(base == int(arm['source_base_hex'], 16) and qrs_base == int(arm['qrs_base_hex'], 16), 'arm pointers differ')
        selected = inner['entry_records'][target][2]['entry']['qrs']['address_hex']
        call = inner['entry_records'][target][1]
        pointers = validate_inner_argument_vector(call, rank)
        offset = int(selected, 16) - qrs_base
        require(qrs_base == pointers[3] and offset >= 0 and offset % 4 == 0, 'source qrs pointer ownership differs')
        require(arm['qrs_address_hex'] == selected and address == base + offset, 'source mapping differs')
        require(int(arm['source']['address_hex'], 16) == address, 'arm source address differs')
        initial = scalar(arm['source'], 'armed source')
        by_role = {e['role']: e for e in events if e['role'] != 'watch_access'}
        for role, pc in pcs.items():
            event = by_role[role]
            frame = bytes.fromhex(event['frame_rbx_raw_hex'])
            text = event['registers_at_breakpoint']
            require(len(frame) == 0x960 and reg(text, 'rbx') == int(event['frame_rbx_hex'], 16) == frame_addr, 'writer frame differs')
            require(event['pc_hex'] == pc and reg(text, 'rip') == int(pc, 16), 'writer PC differs')
            index = reg(text, 'r15')
            require(struct.unpack_from('<Q', frame, 0x180)[0] + 4 * index == address, 'writer destination differs')
            if role.startswith('writer_'):
                require(reg(text, 'rax') + 4 * index == address, 'writer register address differs')
            require(int(event['address_hex'], 16) == int(event['source']['address_hex'], 16) == address, 'writer source address differs')
            scalar(event['source'], 'writer source')
            require(set(event['scalar_registers']) == {f'xmm{i}' for i in range(16)}, 'writer registers differ')
            for i in range(16): vector(event, f'xmm{i}')
            operands = event['operands']
            require(set(operands) == {'array_0x120', 'array_0xb0', 'frame_0x18', 'frame_0x140', 'constant_34bbaf4'}, 'operand inventory differs')
            for name, offset in (('array_0x120', 0x120), ('array_0xb0', 0xb0)):
                require(int(operands[name]['address_hex'], 16) == struct.unpack_from('<Q', frame, offset)[0] + 4 * index, 'operand pointer differs')
            for name, offset in (('frame_0x18', 0x18), ('frame_0x140', 0x140)):
                require(int(operands[name]['address_hex'], 16) == frame_addr + offset and bytes.fromhex(operands[name]['raw_hex']) == frame[offset:offset+4], 'frame operand differs')
            require(int(operands['constant_34bbaf4']['address_hex'], 16) == 0x34bbaf4, 'constant address differs')
            for name, item in operands.items(): scalar(item, name)
        upstream = by_role['before_upstream_2cf']
        ops = upstream['operands']
        a = scalar(ops['array_0x120'], 'array 120'); floor = vector(upstream, 'xmm9')
        b = scalar(ops['array_0xb0'], 'array b0'); scale = scalar(ops['frame_0x140'], 'scale')
        require(ops['array_0x120']['address_hex'] == upstream['values']['q']['address_hex'] and
                ops['array_0x120']['raw_hex'] == upstream['values']['q']['raw_hex'], 'upstream q snapshot differs')
        require(scale == 20.0, 'upstream divisor differs')
        rounded = producer.prior.rounded
        computed = rounded(rounded(max(a, floor) - b) / scale)
        frame_store = by_role['before_frame_store_2f6']
        require(struct.pack('<f', computed).hex() == frame_store['scalar_registers']['xmm0']['raw_hex'], 'upstream REAL32 arithmetic differs')
        after_frame = by_role['after_frame_store_2fb']
        require(after_frame['operands']['frame_0x18']['raw_hex'] == frame_store['scalar_registers']['xmm0']['raw_hex'], 'frame store differs')
        minimum = by_role['before_min_29d']; x0 = vector(minimum, 'xmm0'); x1 = vector(minimum, 'xmm1')
        require(after_frame['operands']['frame_0x18']['raw_hex'] == minimum['operands']['frame_0x18']['raw_hex'], 'frame value changed before minimum')
        require(upstream['operands']['constant_34bbaf4']['raw_hex'] == minimum['operands']['constant_34bbaf4']['raw_hex'] and
                upstream['operands']['frame_0x140']['raw_hex'] == minimum['operands']['frame_0x140']['raw_hex'], 'arithmetic constants changed')
        divisor = scalar(minimum['operands']['constant_34bbaf4'], 'constant')
        require(divisor == 2.0, 'minimum divisor differs')
        require(struct.pack('<f', rounded(scalar(minimum['operands']['frame_0x18'], 'frame 18') / divisor)).hex() == minimum['scalar_registers']['xmm1']['raw_hex'], 'minimum input arithmetic differs')
        expected_raw = minimum['scalar_registers']['xmm0' if x0 < x1 else 'xmm1']['raw_hex']
        before = by_role['writer_before_2a8']; after = by_role['writer_after_2a8']
        require(before['scalar_registers']['xmm0']['raw_hex'] == expected_raw == after['source']['raw_hex'], 'minimum or store differs')
        require(before['source']['raw_hex'] == arm['source']['raw_hex'], 'source changed before writer')
        access = [e for e in events if e['role'] == 'watch_access']
        require([e['pc_after_write_hex'] for e in access] == ['0x25ef2ae', '0x25f4498'] + (['0x25f44c8'] if len(access) == 3 else []), 'access PCs differ')
        state = arm['source']['raw_hex']
        for e in access:
            require(int(e['address_hex'], 16) == address and reg(e['registers_at_breakpoint'], 'rip') == int(e['pc_after_write_hex'], 16), 'access context differs')
            require(int(e['before']['address_hex'], 16) == address == int(e['after']['address_hex'], 16), 'access address differs')
            scalar(e['before'], 'access before'); scalar(e['after'], 'access after')
            require(e['before']['raw_hex'] == state, 'source access chain differs')
            state = e['after']['raw_hex']
        require(access[0]['after']['raw_hex'] == after['source']['raw_hex'], 'writer access differs')
        require(access[1]['before']['raw_hex'] == access[1]['after']['raw_hex'] == after['source']['raw_hex'], 'load access differs')
        comparisons = {e['role']: e for e in record['producer_events']}
        scaled = scalar(comparisons['before_compare']['scalar_registers']['xmm4'], 'compare lhs') > scalar(comparisons['before_compare']['scalar_registers']['xmm3'], 'compare rhs')
        require(len(access) == 2 + int(scaled), 'producer access count differs')
        if scaled:
            write = access[2]; multiply = comparisons['after_multiply']; join = comparisons['branch_join']
            require(multiply['event_ordinal'] < write['event_ordinal'] < join['event_ordinal'], 'producer write chronology differs')
            require(write['before']['raw_hex'] == after['source']['raw_hex'] and
                    write['after']['raw_hex'] == multiply['scalar_registers']['xmm6']['raw_hex'] == join['source']['raw_hex'], 'producer write differs')
        load = next(e for e in record['producer_events'] if e['role'] == 'before_load')
        loaded = next(e for e in record['producer_events'] if e['role'] == 'after_load')
        require(after['event_ordinal'] < access[0]['event_ordinal'] < load['event_ordinal'] < loaded['event_ordinal'] < access[1]['event_ordinal'], 'writer/load chronology differs')
        path = next(e for e in record['producer_events'] if e['role'] == 'path_to_sum')
        require(path['event_ordinal'] < min(e['event_ordinal'] for e in record['preclamp_events']), 'producer/preclamp chronology differs')
        require(load['source']['address_hex'] == arm['address_hex'] and load['source']['raw_hex'] == after['source']['raw_hex'], 'watched source does not reach load')
        source = next(r for r in producer_rows if r['target'] == target)
        rows.append(dict(arm=source['arm'], target=target, rank=rank, source_address_hex=hex(address), armed_source=initial,
                         loaded_source=source['observed_source'], before_raw_hex=arm['source']['raw_hex'],
                         written_raw_hex=after['source']['raw_hex'], source_write_pc='0x25ef2a8',
                         upstream_array_a=a, upstream_floor=floor, upstream_array_b=b,
                         upstream_difference=rounded(max(a, floor)-b), upstream_divisor=scale,
                         minimum_candidate=x0, minimum_bound=x1, minimum_divisor=divisor,
                         scaled_xmm6=source['observed_xmm6_presum'],
                         access_count=len(access), value_changed=arm['source']['raw_hex'] != after['source']['raw_hex'],
                         qr_preclamp=source['observed_preclamp'], qr_store=source['observed_qr_store']))
    return rows


# Localized copies of the frozen validators: metadata binds the new helper,
# and the watch-chain validator accounts for the three captured inner fields.
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


def analyze(capture_dir, prior_dir, selection_path, prepare_path, arm):
    receipt, _, records = read_new_stage(capture_dir, arm, prepare_path)
    selection = producer.prior.validate_selection(selection_path)
    old_root = prior_dir.parent.parent
    summary = {r['arm']: r for r in producer.load_json(old_root / 'analysis/summary.json')['arms']}
    require(producer.sha256_file(old_root / 'analysis/summary.json') == producer.EXPECTED_PRIOR_SUMMARY_SHA256 and
            producer.sha256_file(old_root / 'analysis/selected_profiles.csv') == producer.EXPECTED_PRIOR_PROFILES_SHA256, 'prior analysis hash differs')
    old_receipt, old = producer.prior.read_prior_stage(prior_dir, arm, summary)
    require(receipt['initial_history']['sha256'] == old_receipt['initial_history']['sha256'], 'initial history differs')
    outer, _ = producer.prior.validate_outer_continuity(records, old, selection)
    inner = validate_source_inner_records(records, producer.prior.selected_targets(selection), outer)
    validate_chronology(records, inner)
    legacy = copy.deepcopy(records)
    for record in legacy:
        for name in ('producer_events', 'preclamp_events'):
            for event in record[name]:
                event.pop('event_ordinal'); event.pop('inner_call_id')
    preclamp = producer.prior.validate_events(legacy, arm)
    producer_rows = producer.validate_producers(legacy, arm, inner, preclamp)
    rows = validate_source(records, inner, producer_rows)
    logs = {}
    for row in rows:
        path = capture_dir / ('gdb_rank' + row['rank'] + '.txt')
        text = path.read_text()
        pattern = r'^Hardware access \(read/write\) watchpoint [0-9]+: \*\(unsigned int \*\)' + re.escape(row['source_address_hex']) + r'$'
        require(len(re.findall(pattern, text, re.MULTILINE)) == 1, 'hardware access watchpoint evidence differs')
        logs[path.name] = producer.sha256_file(path)
    return {'arm': arm, 'access_watch_log_sha256': logs, 'receipt_sha256': producer.sha256_file(capture_dir / 'receipt.json'),
            'helper_sha256': receipt['helper_sha256'], 'binary_sha256': receipt['binary']['sha256'],
            'analysis_tool_sha256': producer.sha256_file(Path(__file__)),
            'status': 'PASS_SCOPED_CAPTURE_CONTINUITY', 'forecast_status': 'NOT_COMPLETED'}, rows


def publish(output, summaries, rows):
    import ctypes
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), 'output directory already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.' + output.name + '.', dir=output.parent))
    try:
        (temp / 'summary.json').write_text(json.dumps({'schema': 'cp02-source-write-v1', 'arms': summaries,
            'scope': 'Six selected first-inner paths. Hardware access watch covers the selected source from arming at 0x25ef187 through the load at 0x25f4492, including same-value writes and reads. Observed last write is 0x25ef2a8; ordered REAL32 inputs and min operation are reconstructed. Scalar units and physical identity unresolved. Forecast not completed. QCI is not watched.'}, indent=2, sort_keys=True) + '\n')
        with (temp / 'source.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        for target in producer.TARGETS:
            fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), constrained_layout=True)
            for row in (r for r in rows if r['target'] == target):
                axes[0].plot([0, 1], [row['armed_source'], row['loaded_source']], marker='o', label=row['arm'])
                axes[1].plot([0, 1], [row['qr_preclamp'], row['qr_store']], marker='o', label=row['arm'])
            axes[0].set_xticks([0, 1], ['Watch armed', 'Source load'])
            axes[1].set_xticks([0, 1], ['Pre-clamp', 'QR store'])
            for axis in axes:
                axis.set_ylabel('Observed scalar (units unresolved)'); axis.axhline(0, color='black', linewidth=.7); axis.legend()
            fig.suptitle(target + ' — direct observations'); fig.savefig(temp / (target + '.png'), dpi=150); plt.close(fig)
        manifest = {p.name: producer.sha256_file(p) for p in sorted(temp.iterdir())}
        (temp / 'artifact_manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        rename = ctypes.CDLL(None, use_errno=True).renameat2
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        if rename(-100, os.fsencode(temp), -100, os.fsencode(output), 1) != 0:
            error = ctypes.get_errno(); raise OSError(error, os.strerror(error), str(output))
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-root', type=Path, default=EVIDENCE / 'captures')
    parser.add_argument('--prior-root', type=Path, default=ROOT / 'docs/evidence/cp02_kdm6_controls_20261029/captures')
    parser.add_argument('--selection', type=Path, default=ROOT / 'docs/evidence/cp02_kdm6_controls_20261029/selection.json')
    parser.add_argument('--prepare', type=Path, default=EVIDENCE / 'runtime/prepare.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        results = [analyze(args.capture_root / arm, args.prior_root / arm, args.selection, args.prepare, arm)
                   for arm in ('OFF', 'HYDRO', 'LIQUID')]
        publish(args.output, [s for s, _ in results], [r for _, rows in results for r in rows])
    except (ValueError, OSError, KeyError, TypeError, gzip.BadGzipFile, struct.error, ZeroDivisionError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
