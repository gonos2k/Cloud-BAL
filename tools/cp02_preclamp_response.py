#!/usr/bin/env python3
"""Validate and report direct KDM62D pre-clamp breakpoint observations."""

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import struct
import tempfile
from pathlib import Path

from cp02_kdm6_inner_response import *


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scalar(raw, label):
    """Decode an exact little-endian REAL32 and validate its metadata."""
    require(isinstance(raw, dict), f"{label}: scalar record missing")
    text = raw.get("raw_hex")
    require(isinstance(text, str) and len(text) == 8 and
            all(c in "0123456789abcdef" for c in text), f"{label}: invalid raw bytes")
    value = struct.unpack("<f", bytes.fromhex(text))[0]
    require(math.isfinite(value), f"{label}: nonfinite scalar")
    number = raw.get("value_f32")
    require(type(number) in (int, float) and math.isfinite(number) and
            number == value, f"{label}: decoded scalar differs from raw bytes")
    require(raw.get("finite") is True, f"{label}: finite flag differs")
    return value


def rounded(value):
    try:
        value = struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError as exc:
        raise ValueError("nonfinite intermediate") from exc
    require(math.isfinite(value), "nonfinite intermediate")
    return value


def reconstruct(operands, frame_before):
    """Apply scalar SSE instructions in their exact order, rounding each step."""
    values = {name: scalar(operands[name], name) for name in
              ("xmm2", "xmm6", "xmm7", "xmm9", "xmm10", "xmm14", "xmm15")}
    before = scalar(frame_before, "frame+0x40")
    value = values["xmm2"]
    for sign, name in ((1, "xmm14"), (1, "xmm6"), (1, "xmm9"), (1, "xmm9"),
                       (-1, "xmm7"), (-1, "xmm10")):
        value = rounded(value + sign * values[name])
    tendency = rounded(value * values["xmm15"])
    return rounded(before + tendency), tendency


def validate_register_evidence(event):
    text = event["registers_at_breakpoint"]
    def register(name):
        matches = re.findall(r"^" + name + r"\s+(0x[0-9a-f]+)\b", text, re.MULTILINE)
        require(len(matches) == 1, f"missing or duplicate register {name}")
        return int(matches[0], 16)
    require(register("rip") == int(event["pc_hex"], 16), "PC register differs")
    require(register("rbx") == int(event["frame_rbx_hex"], 16), "frame register differs")
    require(register("r12") + 4 * register("r8") == int(event["qrs_address_hex"], 16), "destination registers differ")
    for name, item in event["scalar_registers"].items():
        vector = "zmm" + name[3:]
        lines = re.findall(r"^" + vector + r"\s+(.+)$", text, re.MULTILINE)
        require(len(lines) == 1, f"missing or duplicate {vector}")
        match = re.search(r"v16_int32 = \{(0x[0-9a-f]+)", lines[0])
        require(match is not None and struct.pack("<I", int(match.group(1), 16)).hex() == item["raw_hex"],
                f"{vector} raw scalar differs from register evidence")


def validate_events(records, arm):
    """Validate event completeness, registers, addresses, and SSE arithmetic."""
    roles = {"before_sum": "0x25f4e24", "before_clamp": "0x25f4e50",
             "before_store": "0x25f4e58", "after_store": "0x25f4e5e"}
    targets = {"P05_00": "1", "P01_00": "3"}
    events = {}
    sequence = []
    for record in records:
        rank = str(record["rank"])
        for event in record.get("preclamp_events", []):
            require(set(event) == {"target", "role", "pc_hex", "rank", "pid", "registers_at_breakpoint", "scalar_registers", "backtrace", "instructions", "frame_rbx_hex", "frame_rbx_raw_hex", "qrs_address_hex", "values"}, "event keys differ")
            label, role = event["target"], event["role"]
            sequence.append((label, role))
            require(label in targets and rank == targets[label], "unexpected target or owner")
            require(role in roles and event["pc_hex"] == roles[role], "unexpected role or PC")
            require(str(event["rank"]) == rank and event["pid"] == record["pid"], "event rank/PID mismatch")
            require((label, role) not in events, "duplicate event")
            require(set(event["scalar_registers"]) == {"xmm2", "xmm6", "xmm7", "xmm9", "xmm10", "xmm14", "xmm15"}, "register set differs")
            for name, item in event["scalar_registers"].items():
                scalar(item, f"{label} {role} {name}")
            qrs = event["values"]["qrs"]
            scalar(qrs, f"{label} {role} qrs")
            require(qrs["address_hex"] == event["qrs_address_hex"], "destination address mismatch")
            require(all(isinstance(event.get(key), str) and event[key] for key in
                        ("backtrace", "instructions", "registers_at_breakpoint", "frame_rbx_hex")), "missing event evidence")
            validate_register_evidence(event)
            frame = bytes.fromhex(event["frame_rbx_raw_hex"])
            require(len(frame) == 0x500, "frame bytes length differs")
            events[label, role] = event
    require(set(events) == {(label, role) for label in targets for role in roles}, "event completeness differs")
    for label in targets:
        require([role for target, role in sequence if target == label] == list(roles), "event sequence differs")
    rows = []
    for label in targets:
        before, clamp, store, after = (events[label, role] for role in roles)
        require(len({e["qrs_address_hex"] for e in (before, clamp, store, after)}) == 1, "destination changed")
        frame = bytes.fromhex(before["frame_rbx_raw_hex"])[0x40:0x44]
        require(frame == bytes.fromhex(clamp["frame_rbx_raw_hex"])[0x40:0x44], "frame operand changed before clamp")
        frame_value = struct.unpack("<f", frame)[0]
        frame_scalar = {"raw_hex": frame.hex(), "value_f32": frame_value, "finite": math.isfinite(frame_value)}
        computed, tendency = reconstruct(before["scalar_registers"], frame_scalar)
        require(struct.pack("<f", tendency) == bytes.fromhex(clamp["scalar_registers"]["xmm2"]["raw_hex"]), "computed term differs from captured register")
        observed = scalar(clamp["scalar_registers"]["xmm9"], "direct pre-clamp")
        require(struct.pack("<f", computed) == struct.pack("<f", observed), "pre-clamp arithmetic differs")
        stored = scalar(after["values"]["qrs"], "actual store")
        expected = max(observed, 0.0)
        require(struct.pack("<f", stored) == struct.pack("<f", expected), "actual store differs from clamp")
        require(store["scalar_registers"]["xmm9"]["raw_hex"] == after["values"]["qrs"]["raw_hex"], "store register differs")
        require(before["values"]["qrs"]["raw_hex"] == clamp["values"]["qrs"]["raw_hex"] == store["values"]["qrs"]["raw_hex"], "destination changed before store")
        row = {"arm": arm, "target": label, "rank": targets[label], "before": scalar(before["values"]["qrs"], "before"),
               "frame_before": frame_value, "computed_term": tendency, "reconstructed_preclamp": computed,
               "direct_preclamp": observed, "actual_store": stored,
               "before_raw_hex": before["values"]["qrs"]["raw_hex"],
               "direct_preclamp_raw_hex": clamp["scalar_registers"]["xmm9"]["raw_hex"],
               "actual_store_raw_hex": after["values"]["qrs"]["raw_hex"]}
        row.update({name: scalar(item, name) for name, item in before["scalar_registers"].items()})
        rows.append(row)
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
    source_helper = ROOT / "docs/evidence/cp02_preclamp_20261029/capture_plan/capture_preclamp.gdb"
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
    capture_dir, prior_dir = Path(capture_dir), Path(prior_dir)
    selection = validate_selection(Path(selection_path))
    receipt, context, records = read_new_stage(capture_dir, arm, Path(prepare_path))
    prior_root = prior_dir.parent.parent
    summary_path = prior_root / "analysis/summary.json"
    profiles_path = prior_root / "analysis/selected_profiles.csv"
    require(sha256_file(summary_path) == EXPECTED_PRIOR_SUMMARY_SHA256, "prior summary hash differs")
    require(sha256_file(profiles_path) == EXPECTED_PRIOR_PROFILES_SHA256, "prior profiles hash differs")
    prior_summary = {row["arm"]: row for row in load_json(summary_path)["arms"]}
    prior_receipt, prior = read_prior_stage(prior_dir, arm, prior_summary)
    require(receipt["initial_history"]["sha256"] == prior_receipt["initial_history"]["sha256"], "initial history differs")
    outer, optional = validate_outer_continuity(records, prior, selection)
    inner = validate_inner_records(records, selected_targets(selection), outer)
    rows = validate_events(records, arm)
    for record in records:
        for event in record.get("preclamp_events", []):
            entry = inner["entry_records"][event["target"]][2]
            require(event["qrs_address_hex"] == entry["entry"]["qrs"]["address_hex"], "destination does not match selected inner target")
    baseline = ROOT / "docs/evidence/cp02_thermo_response_20261029/binary/arm_qrs_branch_comparison.csv"
    require(sha256_file(baseline) == "943006253c811b441b568ef52c19466cc5000b361a3868a2f2c6d3e60539bcca", "PR127 baseline hash differs")
    with baseline.open(newline="", encoding="utf-8") as stream:
        old = [r for r in csv.DictReader(stream) if r["arm"] == arm and r["target"] in ("P01_00", "P05_00") and r["field"] == "qrs" and r["pc_after_write"] == "0x25f4e5e"]
    require(len(old) == 2 and {r["target"] for r in old} == {r["target"] for r in rows}, "prior baseline event set differs")
    for row in rows:
        previous = next(r for r in old if r["target"] == row["target"])
        row["pr127_before_raw_hex"] = previous["raw_before_hex"]
        row["pr127_store_raw_hex"] = previous["raw_after_hex"]
        previous_before = struct.unpack("<f", bytes.fromhex(previous["raw_before_hex"]))[0]
        previous_after = struct.unpack("<f", bytes.fromhex(previous["raw_after_hex"]))[0]
        row["pr127_reconstructed_change"] = previous_after - previous_before
    return {"arm": arm, "status": "PASS_SCOPED_CAPTURE_CONTINUITY", "forecast_status": "NOT_COMPLETED",
            "binary_sha256": EXPECTED_BINARY_SHA256, "capture_receipt_sha256": sha256_file(capture_dir / "receipt.json"),
            "context_sha256": receipt["context_sha256"], "helper_sha256": receipt["helper_sha256"],
            "preparation_sha256": sha256_file(Path(prepare_path)), "selection_sha256": EXPECTED_SELECTION_SHA256,
            "outer_core_equal_values": 624 * len(CORE_OUTER_FIELDS) * 2,
            "outer_optional_byte_comparison_by_endpoint": {
                endpoint: {field: {name: optional[(endpoint, field, name)] for name in
                          ("compared", "byte_equal", "byte_different", "new_nonfinite", "prior_nonfinite")}
                           for field in sorted(OPTIONAL_FIELDS)}
                for endpoint in ("entry", "return")},
            "analysis_tool_sha256": sha256_file(Path(__file__)),
            "pr127_comparison_sha256": sha256_file(baseline),
            "pr127_before_and_store_bytes_match": all(row["before_raw_hex"] == row["pr127_before_raw_hex"] and row["actual_store_raw_hex"] == row["pr127_store_raw_hex"] for row in rows),
            "scope": "Direct breakpoint observations and ordered REAL32 arithmetic at two selected points. PR127 watchpoint bytes are historical comparison, not direct pre-clamp measurements. Candidate names do not establish physical process, units, conservation, or forecast skill."}, rows


def publish(output_dir, summaries, rows):
    import ctypes
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output_dir = Path(output_dir)
    require(not output_dir.exists() and not output_dir.is_symlink(), "output directory already exists")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="." + output_dir.name + ".", dir=output_dir.parent))
    try:
        (temp / "summary.json").write_text(json.dumps({"schema": "cp02-preclamp-response-v1", "arms": summaries}, indent=2, sort_keys=True) + "\n")
        with (temp / "preclamp.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        for target in ("P05_00", "P01_00"):
            fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
            subset = [row for row in rows if row["target"] == target]
            labels = ("before", "frame_before", "computed_term", "direct_preclamp", "actual_store")
            for row in subset:
                ax.plot(range(len(labels)), [row[k] for k in labels], marker="o", label=row["arm"])
            ax.axhline(0, color="black", linewidth=0.7)
            ax.set_xticks(range(len(labels)), ["Destination before", "Frame +0x40", "Computed term", "Direct pre-clamp", "Actual store"], rotation=20, ha="right")
            ax.set_title(target + " — captured values and ordered REAL32 term")
            ax.set_ylabel("Captured scalar (units unresolved)")
            ax.legend()
            fig.savefig(temp / (target + ".png"), dpi=150)
            plt.close(fig)
        manifest = {p.name: sha256_file(p) for p in sorted(temp.iterdir())}
        (temp / "artifact_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renameat2
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        if rename(-100, os.fsencode(temp), -100, os.fsencode(output_dir), 1) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(output_dir))
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--prior-root", type=Path, default=ROOT / "docs/evidence/cp02_kdm6_controls_20261029/captures")
    parser.add_argument("--selection", type=Path, default=ROOT / "docs/evidence/cp02_kdm6_controls_20261029/selection.json")
    parser.add_argument("--prepare", type=Path, default=ROOT / "docs/evidence/cp02_preclamp_20261029/runtime/prepare_v2.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        results = [analyze(args.capture_root / arm, args.prior_root / arm, args.selection, args.prepare, arm)
                   for arm in ("OFF", "HYDRO", "LIQUID")]
        publish(args.output, [s for s, _ in results], [row for _, rows in results for row in rows])
    except (ValueError, OSError, KeyError, TypeError, gzip.BadGzipFile, struct.error) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
