#!/usr/bin/env python3
"""Validate and summarize selected PRE/POST samples from a CP02 GDB capture."""

import argparse
import csv
import gzip
import hashlib
import json
import math
import shutil
import struct
from collections import Counter, defaultdict
from pathlib import Path


EVIDENCE = Path(__file__).resolve().parents[1] / "docs/evidence/cp02_wrf_first_call_20261029"
INPUT_MANIFEST = EVIDENCE / "inputs/manifest.json"
EXPECTED_RANKS = tuple(str(rank) for rank in range(8))
EXPECTED_POINTS = 624
ENTRY_PC = "0x25df680"
RETURN_PC = "0x20c3722"
ARG_NAMES = """th q qc qr qi qs qg nn nc ni nr bg diag_rhog den pii p delz delt g cpd cpv ccn0 rd rv t0c ep1 ep2 qmin xls xlv0 xlf0 den0 denr scale_h qnn_land_mult qnn_sea_mult ncmin_land ncmin_sea cliq cice psat xland rain rainncv snow snowncv sr refl_10cm diagflag do_radar_ref graupel graupelncv itimestep has_reqc has_reqi has_reqs re_cloud re_ice re_snow ids ide jds jde kds kde ims ime jms jme kms kme its ite jts jte kts kte""".split()
ARRAY_3D = {name for index, name in enumerate(ARG_NAMES, 1)
            if 1 <= index <= 17 or index == 48 or 57 <= index <= 59}
ARRAY_2D = {name for index, name in enumerate(ARG_NAMES, 1)
            if 42 <= index <= 47 or index in (51, 52)}
ARRAY_FIELDS = ARRAY_3D | ARRAY_2D
SCALAR_REAL = {name for index, name in enumerate(ARG_NAMES, 1) if 18 <= index < 42}
SCALAR_INT = {name for index, name in enumerate(ARG_NAMES, 1)
              if index in (49, 50) or 53 <= index <= 56 or 60 <= index <= 77}

SOURCE_CANDIDATES = {
    "q": "QVAPOR", "qc": "QCLOUD", "qr": "QRAIN", "qi": "QICE",
    "qs": "QSNOW", "qg": "QGRAUP", "nn": "QNCCN", "nc": "QNCLOUD",
    "ni": "QNICE", "nr": "QNRAIN", "bg": "QIB",
}
CORE_ARRAYS = {name for index, name in enumerate(ARG_NAMES, 1) if 1 <= index <= 17}
OPTIONAL_ARRAYS = ARRAY_FIELDS - CORE_ARRAYS


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def valid_sha256(value):
    return (type(value) is str and len(value) == 64 and
            all(character in "0123456789abcdef" for character in value))


def point_key(point):
    values = (point["i"], point["j"], point["k"])
    require(all(type(value) is int for value in values),
            "selection/sample coordinates must be integers")
    return values


def validate_bounds(record):
    memory = record["memory_bounds_ims_ime_jms_jme_kms_kme"]
    tile = record["tile_bounds_its_ite_jts_jte_kts_kte"]
    spans = []
    for low, high in (("ims", "ime"), ("jms", "jme"), ("kms", "kme")):
        require(type(memory[low]) is int and type(memory[high]) is int,
                "memory bounds must be integers")
        require(memory[low] <= memory[high], "invalid memory bounds")
        span = memory[high] - memory[low] + 1
        require(span <= 1000, "oversized memory bounds")
        spans.append(span)
    for low, high, mem_low, mem_high in (
        ("its", "ite", "ims", "ime"), ("jts", "jte", "jms", "jme"),
        ("kts", "kte", "kms", "kme"),
    ):
        require(type(tile[low]) is int and type(tile[high]) is int,
                "tile bounds must be integers")
        require(memory[mem_low] <= tile[low] <= tile[high] <= memory[mem_high],
                "tile bounds outside memory bounds")
    return memory, tile


def validate_scalar_raw(scalars, memory, tile):
    require(set(scalars) == SCALAR_REAL | SCALAR_INT, "unexpected scalar capture fields")
    for name, kind in [(name, "f") for name in SCALAR_REAL] + [(name, "i") for name in SCALAR_INT]:
        item = scalars[name]
        expected_index = ARG_NAMES.index(name) + 1
        require(type(item.get("arg")) is int and item["arg"] == expected_index,
                f"{name}: scalar argument index mismatch")
        raw = bytes.fromhex(item["raw_hex"])
        require(len(raw) == 4, f"{name}: scalar is not four bytes")
        require(raw.hex() == item["raw_hex"], f"{name}: scalar bytes are not canonical hex")
        decoded = struct.unpack("<f" if kind == "f" else "<i", raw)[0]
        require(type(item.get("decoded")) is (float if kind == "f" else int),
                f"{name}: decoded scalar has wrong type")
        require(decoded == item["decoded"], f"{name}: raw scalar bytes disagree with decoded value")
        if kind == "f":
            require(math.isfinite(decoded), f"{name}: non-finite scalar")
    require(scalars["itimestep"]["decoded"] == 1, "unexpected itimestep")
    require(abs(scalars["delt"]["decoded"] - 20.0) <= 1.0e-5,
            "unexpected model timestep")
    bound_scalars = {
        **{name: memory[name] for name in ("ims", "ime", "jms", "jme", "kms", "kme")},
        **{name: tile[name] for name in ("its", "ite", "jts", "jte", "kts", "kte")},
    }
    for name, expected in bound_scalars.items():
        require(scalars[name]["decoded"] == expected,
                f"{name}: scalar bound differs from captured bound mapping")


def sample_map(samples, selected, memory, tile, stage):
    result = {}
    for sample in samples:
        key = point_key(sample)
        require(key in selected, f"{stage}: sample not in selection: {key}")
        require(key not in result, f"{stage}: duplicate sample key {key}")
        expected = selected[key]
        require(sample.get("label") == expected.get("label"), f"{stage}: label mismatch at {key}")
        for short, long in (("i", "i_wrf_1based"), ("j", "j_wrf_1based"),
                            ("k", "k_wrf_1based")):
            if long in sample:
                require(type(sample[long]) is int and sample[long] == sample[short],
                        f"{stage}: coordinate alias mismatch at {key}")
        require(sample.get("status") in {"owned_tile", "halo_or_not_owned", "outside_memory_bounds"},
                f"{stage}: unsupported sample status at {key}")
        in_memory = (memory["ims"] <= key[0] <= memory["ime"] and
                     memory["jms"] <= key[1] <= memory["jme"] and
                     memory["kms"] <= key[2] <= memory["kme"])
        in_tile = (tile["its"] <= key[0] <= tile["ite"] and
                   tile["jts"] <= key[1] <= tile["jte"] and
                   tile["kts"] <= key[2] <= tile["kte"])
        if sample["status"] == "owned_tile":
            require(in_memory and in_tile, f"{stage}: owned sample outside tile/memory bounds: {key}")
            values = sample.get("values")
            require(isinstance(values, dict) and set(values) == ARRAY_FIELDS,
                    f"{stage}: owned sample has wrong array fields at {key}")
        elif sample["status"] == "halo_or_not_owned":
            require(in_memory and not in_tile,
                    f"{stage}: halo sample contradicts tile/memory bounds: {key}")
            require("values" not in sample, f"{stage}: non-owned halo contains array values at {key}")
        else:
            require(not in_memory, f"{stage}: out-of-memory label is in bounds: {key}")
            require("values" not in sample, f"{stage}: out-of-memory sample contains values at {key}")
        result[key] = sample
    require(set(result) == set(selected), f"{stage}: selected sample keys are missing")
    return result


def validate_values(sample, memory, stage):
    if sample["status"] != "owned_tile":
        return
    i, j, k = point_key(sample)
    nx = memory["ime"] - memory["ims"] + 1
    nz = memory["kme"] - memory["kms"] + 1
    for name, value in sample["values"].items():
        require(isinstance(value, dict), f"{stage}: malformed {name} value")
        if name in ARRAY_3D:
            offset = (i - memory["ims"]) + (k - memory["kms"]) * nx + (j - memory["jms"]) * nx * nz
        else:
            offset = (i - memory["ims"]) + (j - memory["jms"]) * nx
        require(type(value.get("offset_f32")) is int and value["offset_f32"] == offset,
                f"{stage}: {name} array offset mismatch at {point_key(sample)}")
        raw = bytes.fromhex(value["raw_hex"])
        require(len(raw) == 4, f"{stage}: {name} is not a REAL*4 sample")
        require(raw.hex() == value["raw_hex"], f"{stage}: {name} bytes are not canonical hex")
        decoded = struct.unpack("<f", raw)[0]
        require(math.isfinite(decoded), f"{stage}: {name} is non-finite")
        require(type(value.get("value_f32")) is float, f"{stage}: {name} decoded value is not REAL*4 numeric")
        require(decoded == value["value_f32"], f"{stage}: {name} raw bytes disagree with decoded value")


def read_captures(capture_dir):
    files = sorted(set(capture_dir.glob("capture_rank*_pid*.json")) |
                   set(capture_dir.glob("capture_rank*_pid*.json.gz")))
    require(len(files) == len(EXPECTED_RANKS),
            f"expected eight rank capture files, found {len(files)}")
    captures = {}
    pids = set()
    for path in files:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                capture = json.load(stream)
        else:
            capture = json.loads(path.read_text(encoding="utf-8"))
        entry = capture.get("entry")
        require(isinstance(entry, dict), f"{path.name}: missing entry")
        require(type(entry.get("rank")) is str, f"{path.name}: rank must be a string")
        rank = str(entry.get("rank"))
        require(rank in EXPECTED_RANKS, f"{path.name}: unexpected rank {rank}")
        require(rank not in captures, f"duplicate rank capture {rank}")
        require(type(entry.get("pid")) is int and entry["pid"] > 0,
                f"{path.name}: invalid PID")
        require(entry["pid"] not in pids, f"duplicate capture PID {entry['pid']}")
        pids.add(entry["pid"])
        require(capture.get("status") == "return_captured", f"rank {rank}: return not captured")
        require(entry.get("pc") == ENTRY_PC and entry.get("return_pc") == RETURN_PC,
                f"rank {rank}: unexpected entry/caller return PC")
        returned = capture.get("return")
        require(isinstance(returned, dict) and returned.get("pc") == RETURN_PC,
                f"rank {rank}: return PC mismatch")
        require(entry.get("argument_count") == 77 and len(entry.get("arguments", [])) == 77,
                f"rank {rank}: expected 77 ABI arguments")
        require([arg.get("name") for arg in entry["arguments"]] == ARG_NAMES,
                f"rank {rank}: ABI argument names/order differ")
        require(all(type(arg.get("index")) is int for arg in entry["arguments"]) and
                [arg.get("index") for arg in entry["arguments"]] == list(range(1, 78)),
                f"rank {rank}: ABI argument indexes differ")
        rsp = int(entry["rsp_hex"], 16)
        rsp_bytes = bytes.fromhex(entry["rsp_bytes_hex"])
        require(len(rsp_bytes) == 8 and rsp_bytes.hex() == entry["raw_stack_hex_from_rsp_including_return_and_padding"][:16],
                f"rank {rank}: saved stack prefix mismatch")
        require(struct.unpack("<Q", rsp_bytes)[0] == int(RETURN_PC, 16),
                f"rank {rank}: raw stack return address mismatch")
        registers = entry["registers_hex"]
        for index, register in enumerate(("rdi", "rsi", "rdx", "rcx", "r8", "r9"), 1):
            require(int(entry["arguments"][index - 1]["pointer_hex"], 16) == int(registers[register], 16),
                    f"rank {rank}: register argument {index} mismatch")
        stack = bytes.fromhex(entry["raw_stack_hex_from_rsp_including_return_and_padding"])
        require(len(stack) == 8 * 73, f"rank {rank}: unexpected raw stack byte count")
        for index in range(7, 78):
            offset = 8 + 8 * (index - 7)
            arg = entry["arguments"][index - 1]
            require(arg.get("location") == f"stack:+{offset}",
                    f"rank {rank}: stack argument location mismatch at {index}")
            require(int(arg["pointer_hex"], 16) == struct.unpack_from("<Q", stack, offset)[0],
                    f"rank {rank}: raw stack pointer mismatch at argument {index}")
        memory, tile = validate_bounds(entry)
        validate_scalar_raw(entry["scalar_raw4"], memory, tile)
        captures[rank] = (path, capture, memory, tile)
    require(set(captures) == set(EXPECTED_RANKS), "capture rank set is incomplete")
    return captures


def read_selection(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    points = value if isinstance(value, list) else value.get("points") if isinstance(value, dict) else None
    require(isinstance(points, list) and len(points) == EXPECTED_POINTS,
            f"selection file must contain {EXPECTED_POINTS} points")
    for point in points:
        point_key(point)
        require(isinstance(point.get("label"), str) and point["label"],
                "selection labels must be non-empty strings")
        weight = point.get("weight")
        require(type(weight) is float and math.isfinite(weight),
                "selection weights must be finite JSON floats")
    return points


def manifest_selection(manifest):
    levels = manifest["sources"]["wrfinput_d01"]["dimensions"]["bottom_top"]
    expected = []
    for point_id, corners in manifest["corners"].items():
        require(len(corners) == 4, f"{point_id}: expected four mapped corners")
        for corner in corners:
            label = f"{point_id}_{corner['corner']}"
            i, j = int(corner["i0"]) + 1, int(corner["j0"]) + 1
            weight = float(corner["weight"])
            require(math.isfinite(weight), f"{label}: non-finite corner weight")
            for k in range(1, levels + 1):
                expected.append({"label": label, "i": i, "j": j, "k": k,
                                 "weight": weight})
    require(len(expected) == EXPECTED_POINTS,
            f"manifest corners produced {len(expected)} keys, expected 624")
    return expected


def validate_selection(captures, selection_path=None, expected_points=EXPECTED_POINTS,
                       domain_shape=None, expected_selection=None):
    baseline = captures[EXPECTED_RANKS[0]][1]["entry"].get("selection_points")
    require(isinstance(baseline, list) and len(baseline) == expected_points,
            f"expected {expected_points} selection points")
    if selection_path is not None:
        frozen = read_selection(selection_path)
        require(baseline == frozen, "capture selection differs from supplied selection file")
    if expected_selection is not None:
        require(baseline == expected_selection,
                "selection does not match the manifest's mapped corners and vertical levels")
    selected = {}
    for point in baseline:
        key = point_key(point)
        require(key not in selected, f"duplicate selection key {key}")
        require(1 <= key[0] and 1 <= key[1] and 1 <= key[2],
                f"selection key outside positive WRF coordinates: {key}")
        if domain_shape is not None:
            ni, nj, nk = domain_shape
            require(key[0] <= ni and key[1] <= nj and key[2] <= nk,
                    f"selection key outside input WRF domain: {key}")
        selected[key] = point
    for rank in EXPECTED_RANKS:
        points = captures[rank][1]["entry"].get("selection_points")
        require(points == baseline, f"rank {rank}: selection differs across ranks")
    return selected


def validate_captures(captures, selection_path=None, expected_points=EXPECTED_POINTS,
                      domain_shape=None, expected_selection=None):
    selected = validate_selection(captures, selection_path, expected_points, domain_shape,
                                  expected_selection)
    owners = Counter()
    owned = {}
    for rank in EXPECTED_RANKS:
        _, capture, memory, tile = captures[rank]
        entry = capture["entry"]
        pre = sample_map(entry.get("samples", []), selected, memory, tile, f"rank {rank} PRE")
        post = sample_map(capture["return"].get("samples", []), selected, memory, tile,
                          f"rank {rank} POST")
        require(set(pre) == set(post), f"rank {rank}: PRE/POST sample keys differ")
        for key in pre:
            validate_values(pre[key], memory, f"rank {rank} PRE")
            validate_values(post[key], memory, f"rank {rank} POST")
            if pre[key]["status"] == "owned_tile":
                require(post[key]["status"] == "owned_tile",
                        f"rank {rank}: ownership changed PRE to POST at {key}")
                owners[key] += 1
                owned[key] = (rank, pre[key], post[key])
            else:
                require(post[key]["status"] == pre[key]["status"],
                        f"rank {rank}: halo status changed PRE to POST at {key}")
    require(set(owners) == set(selected) and all(owners[key] == 1 for key in selected),
            "selection keys do not have exactly one owned rank each")
    return selected, owned


def validate_receipt(capture_dir, receipt_path, manifest_path, selection_path, captures):
    require(receipt_path is not None and receipt_path.is_file(),
            "runtime receipt is required for bound capture/input provenance")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    require(receipt["status"] == "FIRST_CALL_CAPTURED_INTENTIONAL_STOP",
            "receipt does not report the expected intentional first-call stop")
    require(receipt["forecast_status"] == "NOT_COMPLETED",
            "receipt unexpectedly claims forecast completion")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection_points = selection if isinstance(selection, list) else selection.get("points")
    require(isinstance(selection_points, list), "receipt selection file has no point list")
    require(type(receipt.get("ranks")) is int and receipt["ranks"] == 8 and
            type(receipt.get("selected_points")) is int and
            receipt["selected_points"] == len(selection_points),
            "receipt rank or selection count differs")
    require(receipt["input_manifest_sha256"] == sha256(manifest_path),
            "receipt input manifest SHA-256 mismatch")
    require(receipt["selection_sha256"] == sha256(selection_path),
            "receipt selection SHA-256 mismatch")
    require(type(receipt.get("launcher_exit")) is int and receipt["launcher_exit"] == 255,
            "receipt must record the intentional launcher stop (exit 255)")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_binary = manifest["launcher"]["binary_sha256_expected"]
    observed_binary = manifest["launcher"].get("binary_observed_sha256")
    if observed_binary is not None:
        require(observed_binary == expected_binary,
                "input manifest observed executable SHA-256 differs from pinned value")
    binary = receipt["binary"]
    require(binary["sha256"] == expected_binary,
            "receipt executable SHA-256 differs from pinned manifest")
    mapped_binary = receipt["runtime_mapped_files"].get(binary["path"])
    require(isinstance(mapped_binary, dict) and mapped_binary.get("sha256") == binary["sha256"],
            "runtime mapping does not bind the receipt executable hash")
    input_copy_path = capture_dir / "input_copy.json"
    require(input_copy_path.is_file(), "input-copy inventory is missing")
    require(receipt["input_copy_sha256"] == sha256(input_copy_path),
            "receipt input-copy inventory SHA-256 mismatch")
    input_copy = json.loads(input_copy_path.read_text(encoding="utf-8"))
    copied_files = input_copy["files"]
    require(isinstance(copied_files, list) and len(copied_files) > 0,
            "input-copy inventory has no files")
    expected_count = len(copied_files)
    for name in ("input_files_unchanged", "original_input_files_unchanged"):
        count = receipt.get(name)
        require(type(count) is int and count == expected_count,
                f"receipt {name} does not equal input-copy file count")
    require(len({item["name"] for item in copied_files}) == expected_count,
            "input-copy inventory contains duplicate filenames")
    copied_hashes = {item["name"]: item["sha256"] for item in copied_files}
    expected_input_hashes = {
        "wrfinput_d01": manifest["sources"]["wrfinput_d01"]["sha256"],
        "wrfbdy_d01": manifest["boundary"]["sha256"],
        "namelist.input": manifest["namelist"]["sha256"],
    }
    for name, expected in expected_input_hashes.items():
        require(copied_hashes.get(name) == expected,
                f"input-copy {name} hash differs from input manifest")
    history = receipt["initial_history"]
    archived_history = manifest["sources"]["native_initial_history"]["sha256"]
    require(valid_sha256(history.get("sha256")) and
            valid_sha256(history.get("archived_sha256")),
            "initial-history hashes must be lowercase SHA-256 values")
    require(history.get("archived_sha256") == archived_history,
            "archived initial-history hash differs from input manifest")
    same_history = history.get("sha256") == history.get("archived_sha256")
    require(type(history.get("byte_identical")) is bool and
            history["byte_identical"] == same_history,
            "initial-history equality flag contradicts its hashes")
    receipt_captures = {
        Path(item["path"]).name: item["sha256"]
        for item in receipt["captures"]
        if Path(item["path"]).name.startswith("capture_rank") and
        Path(item["path"]).name.endswith(".json.gz")
    }
    require(len(receipt_captures) == 8, "receipt lacks eight archived rank captures")
    for rank in EXPECTED_RANKS:
        path = captures[rank][0]
        require(path.name in receipt_captures,
                f"receipt has no hash for rank {rank} capture")
        require(sha256(path) == receipt_captures[path.name],
                f"receipt capture SHA-256 mismatch for rank {rank}")
    return receipt


def summarize(capture_dir, manifest_path=INPUT_MANIFEST, selection_path=None,
              receipt_path=None):
    captures = read_captures(capture_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(selection_path is not None and selection_path.is_file(),
            "frozen selection file is required")
    dims = manifest["sources"]["wrfinput_d01"]["dimensions"]
    domain_shape = (dims["west_east"], dims["south_north"], dims["bottom_top"])
    expected_selection = manifest_selection(manifest)
    selected, owned = validate_captures(captures, selection_path,
                                        domain_shape=domain_shape,
                                        expected_selection=expected_selection)
    receipt = validate_receipt(capture_dir, receipt_path, manifest_path, selection_path, captures)
    fields = defaultdict(list)
    two_d_columns = {}
    rows = []
    for key, (rank, pre, post) in sorted(owned.items()):
        i, j, k = key
        for name in sorted(ARRAY_FIELDS):
            before = pre["values"][name]
            after = post["values"][name]
            before_raw = before["raw_hex"]
            after_raw = after["raw_hex"]
            before_value = before["value_f32"]
            after_value = after["value_f32"]
            row = {"rank": rank, "label": pre.get("label", ""), "i_wrf_1based": i,
                   "j_wrf_1based": j, "k_wrf_1based": k, "argument": name,
                   "array_rank": "3D" if name in ARRAY_3D else "2D",
                   "source_candidate": SOURCE_CANDIDATES.get(name, ""),
                   "pre_raw_hex": before_raw, "pre_value_f32": before_value,
                   "post_raw_hex": after_raw, "post_value_f32": after_value,
                   "raw_changed": before_raw != after_raw}
            if name in ARRAY_3D:
                fields[name].append((before_value, after_value, before_raw != after_raw))
                rows.append(row)
            else:
                column = (i, j)
                column_key = (name, column)
                state = (before_value, after_value, before_raw, after_raw, rank, pre.get("label", ""))
                if column_key in two_d_columns:
                    require(two_d_columns[column_key][:4] == state[:4],
                            f"2D {name} values differ across repeated vertical keys at {column}")
                else:
                    two_d_columns[column_key] = state
    for (name, (i, j)), state in sorted(two_d_columns.items()):
        before_value, after_value, before_raw, after_raw, rank, label = state
        fields[name].append((before_value, after_value, before_raw != after_raw))
        rows.append({"rank": rank, "label": label, "i_wrf_1based": i,
                     "j_wrf_1based": j, "k_wrf_1based": "", "argument": name,
                     "array_rank": "2D", "source_candidate": SOURCE_CANDIDATES.get(name, ""),
                     "pre_raw_hex": before_raw, "pre_value_f32": before_value,
                     "post_raw_hex": after_raw, "post_value_f32": after_value,
                     "raw_changed": before_raw != after_raw})
    field_summary = {}
    for name, values in sorted(fields.items()):
        pre_values = [row[0] for row in values]
        post_values = [row[1] for row in values]
        field_summary[name] = {
            "source_candidate": SOURCE_CANDIDATES.get(name),
            "array_role": "core_17_candidate_argument" if name in CORE_ARRAYS else "optional_or_output_diagnostic_candidate",
            "array_rank": "3D" if name in ARRAY_3D else "2D",
            "sample_unit": "selected keys" if name in ARRAY_3D else "unique horizontal columns",
            "selected_count": len(values),
            "raw_changed_count": sum(row[2] for row in values),
            "pre_min": min(pre_values), "pre_max": max(pre_values),
            "post_min": min(post_values), "post_max": max(post_values),
        }
    input_hashes = {
        "wrfinput_d01": manifest["sources"]["wrfinput_d01"]["sha256"],
        "native_initial_history": manifest["sources"]["native_initial_history"]["sha256"],
        "wrfbdy_d01": manifest["boundary"]["sha256"],
        "namelist.input": manifest["namelist"]["sha256"],
        "wrf.exe": manifest["launcher"].get(
            "binary_observed_sha256", manifest["launcher"]["binary_sha256_expected"]),
    }
    runtime_outcome = {
        "capture_status": receipt["status"],
        "forecast_status": receipt["forecast_status"],
        "launcher_exit": receipt["launcher_exit"],
        "termination": receipt["termination"],
        "input_files_unchanged": receipt["input_files_unchanged"],
        "original_input_files_unchanged": receipt["original_input_files_unchanged"],
        "initial_history_byte_identical_to_archive": receipt["initial_history"]["byte_identical"],
        "initial_history_sha256": receipt["initial_history"]["sha256"],
        "receipt_sha256": sha256(receipt_path),
        "input_copy_sha256": receipt["input_copy_sha256"],
        "runtime_executable_sha256": receipt["binary"]["sha256"],
    }
    return {
        "status": "PASS_SCOPED_CAPTURE_VALIDATION",
        "scope": "Selected 624 spatial/vertical keys at one candidate MP37 entry/return on eight ranks; candidate source names remain unverified; no process-level budget or full-domain state claim. Two-dimensional fields are summarized once per horizontal column after checking repeated vertical captures agree.",
        "capture_rank_count": len(captures),
        "selected_key_count": len(selected),
        "unique_owner_count": len(owned),
        "entry_pc": ENTRY_PC, "return_pc": RETURN_PC,
        "argument_count": 77, "expected_timestep": 1, "expected_dt_seconds": 20.0,
        "input_hashes": input_hashes,
        "input_manifest_sha256": sha256(manifest_path),
        "selection_sha256": sha256(selection_path) if selection_path else None,
        "runtime_outcome": runtime_outcome,
        "capture_hashes": {rank: sha256(captures[rank][0]) for rank in EXPECTED_RANKS},
        "analysis_tool_sha256": sha256(Path(__file__).resolve()),
        "source_mapping_status": "candidate labels from co-located source; binary has no DWARF; capture alone does not prove semantic source identity",
        "field_summaries": field_summary,
        "core_array_arguments": sorted(CORE_ARRAYS),
        "optional_diagnostic_arrays": sorted(OPTIONAL_ARRAYS),
        "profiles": rows,
    }


def write_outputs(result, output_dir):
    profiles = result.pop("profiles")
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        summary_path = output_dir / "summary.json"
        profiles_path = output_dir / "profiles.csv"
        summary_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8")
        columns = list(profiles[0]) if profiles else []
        with profiles_path.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(profiles)
        manifest = {
            "status": result["status"], "scope": result["scope"],
            "summary": {"path": summary_path.name, "sha256": sha256(summary_path)},
            "profiles": {"path": profiles_path.name, "sha256": sha256(profiles_path)},
            "analysis_tool_sha256": result["analysis_tool_sha256"],
            "input_manifest_sha256": result["input_manifest_sha256"],
            "selection_sha256": result["selection_sha256"],
            "input_hashes": result["input_hashes"],
            "capture_hashes": result["capture_hashes"],
        }
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(output_dir)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--input-manifest", type=Path, default=INPUT_MANIFEST)
    parser.add_argument("--selection", type=Path, default=EVIDENCE / "capture/selection.json")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        result = summarize(args.capture_dir, args.input_manifest, args.selection,
                           args.capture_dir / "receipt.json")
        output_dir = args.output_dir or EVIDENCE / "analysis" / (
            "run_" + result["analysis_tool_sha256"][:12])
        write_outputs(result, output_dir)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"validated {result['capture_rank_count']} ranks and {result['selected_key_count']} selected keys")
    print(f"summary: {output_dir / 'summary.json'}\nprofiles: {output_dir / 'profiles.csv'}")


if __name__ == "__main__":
    main()
