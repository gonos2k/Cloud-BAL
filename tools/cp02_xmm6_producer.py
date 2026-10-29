#!/usr/bin/env python3
"""Validate direct XMM6 producer observations and their pre-clamp path."""
import argparse
import csv
import gzip
import json
import hashlib
import math
import os
import re
import shutil
import struct
import tempfile
from pathlib import Path

import cp02_preclamp_response as prior

ROOT = prior.ROOT
EVIDENCE = ROOT / 'docs/evidence/cp02_xmm6_producer_20261029'
ROLES = {'before_load': '0x25f4492', 'after_load': '0x25f4498',
         'before_compare': '0x25f44a4', 'before_multiply': '0x25f44be',
         'after_multiply': '0x25f44c2', 'branch_join': '0x25f44f7',
         'path_to_sum': '0x25f4a59'}
TARGETS = {'P05_00': '1', 'P01_00': '3'}
from cp02_kdm6_inner_response import *

require = prior.require
scalar = prior.scalar


def reg(text, name):
    matches = re.findall(r'^' + name + r'\s+(0x[0-9a-f]+)\b', text, re.MULTILINE)
    require(len(matches) == 1, 'missing or duplicate register ' + name)
    return int(matches[0], 16)


def validate_event(event, record):
    required = {'target', 'role', 'pc_hex', 'rank', 'pid', 'inner_event_id',
                'qrs_address_hex', 'qrs_base_hex', 'index_r8', 'frame_rbx_hex',
                'frame_rbx_raw_hex', 'source_base_hex', 'source', 'frame_scale_0x140',
                'scalar_registers', 'registers_at_breakpoint', 'backtrace', 'values'}
    require(set(event) == required, 'producer event keys differ')
    text = event['registers_at_breakpoint']
    require(isinstance(text, str) and isinstance(event['backtrace'], str) and event['backtrace'], 'missing breakpoint evidence')
    require(event['role'] in ROLES and event['pc_hex'] == ROLES[event['role']], 'producer PC differs')
    require(reg(text, 'rip') == int(event['pc_hex'], 16), 'PC register differs')
    frame_addr = reg(text, 'rbx')
    index = reg(text, 'r8')
    require(frame_addr == int(event['frame_rbx_hex'], 16) and index == event['index_r8'], 'frame/index register differs')
    frame = bytes.fromhex(event['frame_rbx_raw_hex'])
    require(len(frame) == 0x500, 'frame bytes length differs')
    dest_base = struct.unpack_from('<Q', frame, 0x18)[0]
    source_base = struct.unpack_from('<Q', frame, 0xc0)[0]
    require(dest_base == int(event['qrs_base_hex'], 16) and source_base == int(event['source_base_hex'], 16), 'frame pointer differs')
    require(dest_base + 4 * index == int(event['qrs_address_hex'], 16), 'destination address differs')
    source = event['source']
    require(int(source['address_hex'], 16) == source_base + 4 * index, 'source address differs')
    scalar(source, 'source')
    scale = event['frame_scale_0x140']
    scalar(scale, 'frame scale')
    require(int(scale['address_hex'], 16) == frame_addr + 0x140 and bytes.fromhex(scale['raw_hex']) == frame[0x140:0x144], 'frame scale differs')
    require(event['values']['qrs']['address_hex'] == event['qrs_address_hex'], 'destination value address differs')
    scalar(event['values']['qrs'], 'destination')
    registers = event['scalar_registers']
    require(set(registers) == {f'xmm{i}' for i in range(16)}, 'producer register set differs')
    for name, item in registers.items():
        scalar(item, name)
        lines = re.findall(r'^zmm' + name[3:] + r'\s+(.+)$', text, re.MULTILINE)
        require(len(lines) == 1, 'missing or duplicate vector register ' + name)
        match = re.search(r'v16_int32 = \{(0x[0-9a-f]+)', lines[0])
        require(match and struct.pack('<I', int(match.group(1), 16)).hex() == item['raw_hex'], 'vector low bits differ: ' + name)
    require(str(event['rank']) == str(record['rank']) and event['pid'] == record['pid'], 'producer rank/PID differs')


def validate_producers(records, arm, inner, preclamp_rows):
    events = {}
    for record in records:
        require('producer_events' in record and isinstance(record['producer_events'], list), 'producer events missing')
        for event in record['producer_events']:
            validate_event(event, record)
            label, role = event['target'], event['role']
            require(label in TARGETS and str(record['rank']) == TARGETS[label], 'producer owner differs')
            entry = inner['entry_records'][label]
            require(event['inner_event_id'] == entry[1]['event_id'] and event['qrs_address_hex'] == entry[2]['entry']['qrs']['address_hex'], 'producer selected inner target differs')
            events.setdefault(label, []).append(event)
    require(set(events) == set(TARGETS), 'producer target set differs')
    rows = []
    for label in TARGETS:
        seq = events[label]
        by_role = {event['role']: event for event in seq}
        require(len(seq) == len(by_role), 'duplicate producer event')
        require('before_compare' in by_role, 'missing comparison')
        compare = by_role['before_compare']
        lhs = scalar(compare['scalar_registers']['xmm4'], 'comparison lhs')
        rhs = scalar(compare['scalar_registers']['xmm3'], 'comparison rhs')
        scaled = lhs > rhs
        expected = ['before_load', 'after_load', 'before_compare']
        if scaled:
            expected += ['before_multiply', 'after_multiply']
        expected += ['branch_join', 'path_to_sum']
        require([e['role'] for e in seq] == expected, 'producer event sequence differs from comparison')
        for key in ('qrs_address_hex', 'qrs_base_hex', 'source_base_hex', 'index_r8', 'frame_rbx_hex', 'inner_event_id'):
            require(len({e[key] for e in seq}) == 1, 'producer context changed: ' + key)
        load, loaded = by_role['before_load'], by_role['after_load']
        source_hex = load['source']['raw_hex']
        require(reg(load['registers_at_breakpoint'], 'rax') == int(load['source_base_hex'], 16), 'load base register differs')
        require(loaded['scalar_registers']['xmm6']['raw_hex'] == source_hex == loaded['source']['raw_hex'], 'source load differs')
        require(load['scalar_registers']['xmm4']['raw_hex'] == loaded['scalar_registers']['xmm4']['raw_hex'], 'xmm4 changed during load')
        require(load['scalar_registers']['xmm3']['raw_hex'] == loaded['scalar_registers']['xmm3']['raw_hex'] == compare['scalar_registers']['xmm3']['raw_hex'], 'comparison rhs changed')
        require(load['frame_scale_0x140']['raw_hex'] == loaded['frame_scale_0x140']['raw_hex'] == compare['frame_scale_0x140']['raw_hex'], 'frame scale changed before comparison')
        require(compare['source']['raw_hex'] == source_hex, 'source changed before comparison')
        x4 = scalar(loaded['scalar_registers']['xmm4'], 'loaded xmm4')
        source = scalar(load['source'], 'source')
        frame_scale = scalar(loaded['frame_scale_0x140'], 'frame scale')
        reconstructed_compare = prior.rounded(prior.rounded(x4 - source) * frame_scale)
        require(struct.pack('<f', reconstructed_compare).hex() == compare['scalar_registers']['xmm4']['raw_hex'], 'comparison arithmetic differs')
        require(compare['scalar_registers']['xmm6']['raw_hex'] == source_hex, 'loaded xmm6 changed before comparison')
        result_hex = source_hex
        multiplier = None
        if scaled:
            before, after = by_role['before_multiply'], by_role['after_multiply']
            require(before['scalar_registers']['xmm6']['raw_hex'] == source_hex, 'multiply input differs')
            multiplier = scalar(before['scalar_registers']['xmm3'], 'multiplier')
            expected_multiplier = prior.rounded(rhs / lhs)
            require(struct.pack('<f', expected_multiplier).hex() == before['scalar_registers']['xmm3']['raw_hex'], 'multiplier differs')
            result_hex = struct.pack('<f', prior.rounded(source * multiplier)).hex()
            require(after['scalar_registers']['xmm6']['raw_hex'] == result_hex, 'multiply result differs')
            require(after['source']['raw_hex'] == source_hex, 'source changed before write')
        for role in ('branch_join', 'path_to_sum'):
            require(by_role[role]['scalar_registers']['xmm6']['raw_hex'] == result_hex, 'producer value changed on path')
            require(by_role[role]['source']['raw_hex'] == result_hex, 'source memory differs at join')
        presums = [e for record in records for e in record['preclamp_events'] if e['target'] == label and e['role'] == 'before_sum']
        require(len(presums) == 1 and presums[0]['scalar_registers']['xmm6']['raw_hex'] == result_hex and presums[0]['qrs_address_hex'] == load['qrs_address_hex'], 'pre-sum xmm6 differs')
        presum = presums[0]
        require(presum['frame_rbx_hex'] == load['frame_rbx_hex'] and reg(presum['registers_at_breakpoint'], 'r8') == load['index_r8'] and str(presum['rank']) == str(load['rank']) and presum['pid'] == load['pid'], 'pre-sum context differs')
        row = next(row for row in preclamp_rows if row['target'] == label)
        rows.append({'arm': arm, 'target': label, 'rank': TARGETS[label], 'source_address_hex': load['source']['address_hex'],
                     'observed_source': source, 'observed_source_raw_hex': source_hex,
                     'observed_frame_scale': frame_scale, 'observed_compare_xmm4': lhs,
                     'observed_compare_xmm3': rhs, 'branch': 'multiply' if scaled else 'skip',
                     'observed_multiplier': multiplier, 'observed_xmm6_presum': scalar(presums[0]['scalar_registers']['xmm6'], 'pre-sum xmm6'),
                     'observed_xmm6_raw_hex': result_hex, 'reconstructed_compare_xmm4': reconstructed_compare,
                     'reconstructed_xmm6': struct.unpack('<f', bytes.fromhex(result_hex))[0],
                     'reconstructed_term': row['computed_term'], 'observed_preclamp': row['direct_preclamp'],
                     'observed_preclamp_raw_hex': row['direct_preclamp_raw_hex'],
                     'observed_qr_store': row['actual_store'], 'observed_qr_store_raw_hex': row['actual_store_raw_hex']})
    return rows


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
    source_helper = EVIDENCE / "capture_plan/capture_producer.gdb"
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


def analyze(capture_dir, prior_dir, selection_path, prepare_path, arm):
    selection = prior.validate_selection(selection_path)
    receipt, context, records = read_new_stage(capture_dir, arm, prepare_path)
    root = prior_dir.parent.parent
    summary_path = root / 'analysis/summary.json'
    profiles_path = root / 'analysis/selected_profiles.csv'
    require(prior.sha256_file(summary_path) == prior.EXPECTED_PRIOR_SUMMARY_SHA256 and prior.sha256_file(profiles_path) == prior.EXPECTED_PRIOR_PROFILES_SHA256, 'prior analysis hash differs')
    old_summary = {row['arm']: row for row in prior.load_json(summary_path)['arms']}
    old_receipt, old = prior.read_prior_stage(prior_dir, arm, old_summary)
    require(receipt['initial_history']['sha256'] == old_receipt['initial_history']['sha256'], 'initial history differs')
    outer, _ = prior.validate_outer_continuity(records, old, selection)
    inner = prior.validate_inner_records(records, prior.selected_targets(selection), outer)
    preclamp = prior.validate_events(records, arm)
    rows = validate_producers(records, arm, inner, preclamp)
    return {'arm': arm, 'status': 'PASS_SCOPED_CAPTURE_CONTINUITY', 'forecast_status': 'NOT_COMPLETED',
            'receipt_sha256': prior.sha256_file(capture_dir / 'receipt.json'), 'context_sha256': receipt['context_sha256'],
            'helper_sha256': receipt['helper_sha256'], 'prepare_sha256': prior.sha256_file(prepare_path),
            'analysis_tool_sha256': prior.sha256_file(Path(__file__)),
            'binary_sha256': prior.EXPECTED_BINARY_SHA256, 'selection_sha256': prior.EXPECTED_SELECTION_SHA256,
            'scope': 'Breakpoint observations and reconstructed ordered REAL32 arithmetic; candidate units and physical identity unresolved. No forecast evaluation.'}, rows


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
        (temp / 'summary.json').write_text(json.dumps({'schema': 'cp02-xmm6-producer-v1', 'arms': summaries}, indent=2, sort_keys=True) + '\n')
        with (temp / 'producer.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        for target in TARGETS:
            fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), constrained_layout=True)
            for row in (r for r in rows if r['target'] == target):
                axes[0].plot(range(2), [row[k] for k in ('observed_source', 'observed_xmm6_presum')], marker='o', label=row['arm'])
                axes[1].plot(range(2), [row[k] for k in ('observed_preclamp', 'observed_qr_store')], marker='o', label=row['arm'])
            axes[0].set_xticks(range(2), ['Source memory', 'XMM6 pre-sum'])
            axes[1].set_xticks(range(2), ['Pre-clamp', 'QR store'])
            for ax in axes:
                ax.set_ylabel('Observed scalar (candidate units unresolved)')
                ax.axhline(0, color='black', linewidth=.7)
                ax.legend()
            fig.suptitle(target + ' — direct observations; no forecast claim')
            fig.savefig(temp / (target + '.png'), dpi=150)
            plt.close(fig)
        manifest = {p.name: prior.sha256_file(p) for p in sorted(temp.iterdir())}
        (temp / 'artifact_manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renameat2
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        if rename(-100, os.fsencode(temp), -100, os.fsencode(output), 1) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(output))
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
        results = [analyze(args.capture_root / arm, args.prior_root / arm, args.selection, args.prepare, arm) for arm in ('OFF', 'HYDRO', 'LIQUID')]
        publish(args.output, [s for s, _ in results], [r for _, rows in results for r in rows])
    except (ValueError, OSError, KeyError, TypeError, gzip.BadGzipFile, struct.error, ZeroDivisionError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
