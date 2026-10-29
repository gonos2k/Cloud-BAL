#!/usr/bin/env python3
"""Validate and summarize two-call CP02 KDM6 captures for three control arms."""

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
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/cp02_kdm6_controls_20261029"
INPUTS = EVIDENCE / "inputs"
DEFAULT_SELECTION = EVIDENCE / "selection.json"
CAPTURE_SCRIPT = EVIDENCE / "capture_kdm6.gdb"
PROFILE = ROOT / "tests/intel_toolchain.sh"
ARMS = ("OFF", "HYDRO", "LIQUID")
RANKS = tuple(range(8))
EXPECTED_BINARY_SHA256 = "de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168"
EXPECTED_SCRIPT_SHA256 = "e71414d285a0b4ca0d891eb772a16d8796e064f59ca3de7f52462c0a1172c4b0"
EXPECTED_PROFILE_SHA256 = "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4"
EXPECTED_SELECTION_SHA256 = "38602c67768d0836c5f911c43ff4bcced57073f6f222f1c91a63499c16956c6e"
ARG_NAMES = """th q qc qr qi qs qg nn nc ni nr bg diag_rhog den pii p delz delt g cpd cpv ccn0 rd rv t0c ep1 ep2 qmin xls xlv0 xlf0 den0 denr scale_h qnn_land_mult qnn_sea_mult ncmin_land ncmin_sea cliq cice psat xland rain rainncv snow snowncv sr refl_10cm diagflag do_radar_ref graupel graupelncv itimestep has_reqc has_reqi has_reqs re_cloud re_ice re_snow ids ide jds jde kds kde ims ime jms jme kms kme its ite jts jte kts kte""".split()
REGISTERS = ("rdi", "rsi", "rdx", "rcx", "r8", "r9")
SCALAR_REAL = {name for index, name in enumerate(ARG_NAMES, 1) if 18 <= index < 42}
SCALAR_INT = {name for index, name in enumerate(ARG_NAMES, 1)
              if index in (49, 50) or 53 <= index <= 56 or 60 <= index <= 77}
ARRAY_3D = {name for index, name in enumerate(ARG_NAMES, 1)
            if 1 <= index <= 17 or index == 48 or 57 <= index <= 59}
ARRAY_2D = {name for index, name in enumerate(ARG_NAMES, 1)
            if 42 <= index <= 47 or index in (51, 52)}
ARRAY_FIELDS = ARRAY_3D | ARRAY_2D
OPTIONAL_FIELDS = {"refl_10cm", "re_cloud", "re_ice", "re_snow"}
CORE_FIELDS = ARRAY_FIELDS - OPTIONAL_FIELDS
PAIR_FIELDS = {"cloud_water": ("qc", "nc"), "rain": ("qr", "nr"), "cloud_ice": ("qi", "ni")}
SOURCE_CANDIDATES = {"th": "T", "q": "QVAPOR", "qc": "QCLOUD", "qr": "QRAIN",
                     "qi": "QICE", "qs": "QSNOW", "qg": "QGRAUP", "nn": "QNCCN",
                     "nc": "QNCLOUD", "ni": "QNICE", "nr": "QNRAIN", "bg": "QIB"}
NETCDF_NAMES = {"qc": "QCLOUD", "nc": "QNCLOUD", "qr": "QRAIN", "nr": "QNRAIN",
                "qi": "QICE", "ni": "QNICE"}
BOUND_NAMES = ("ims", "ime", "jms", "jme", "kms", "kme")
TILE_NAMES = ("its", "ite", "jts", "jte", "kts", "kte")
CAPTURE_FILENAME = re.compile(r"^capture_rank([0-7])_pid([0-9]+)\.json(?:\.gz)?$")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    try:
        if path.name.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as source:
                return json.load(source)
        with path.open(encoding="utf-8") as source:
            return json.load(source)
    except (OSError, EOFError, gzip.BadGzipFile, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc


def real4(record, label, *, allow_nonfinite=False):
    require(isinstance(record, dict), f"{label}: malformed REAL*4 record")
    raw_hex = record.get("raw_hex")
    require(type(raw_hex) is str and re.fullmatch(r"[0-9a-f]{8}", raw_hex) is not None,
            f"{label}: expected eight lowercase hex bytes")
    raw = bytes.fromhex(raw_hex)
    value = struct.unpack("<f", raw)[0]
    finite = math.isfinite(value)
    require(record.get("finite") is finite, f"{label}: finite flag disagrees with raw bytes")
    if finite:
        require(type(record.get("value_f32")) is float and record["value_f32"] == value,
                f"{label}: decoded value disagrees with raw bytes")
    else:
        require(allow_nonfinite, f"{label}: nonfinite core/active value")
        require(record.get("value_f32") is None, f"{label}: nonfinite value must serialize as null")
    return value, raw


def integer_pointer(value, label):
    require(type(value) is str and re.fullmatch(r"0x[0-9a-f]+", value) is not None,
            f"{label}: malformed pointer hex")
    result = int(value, 16)
    require(result != 0, f"{label}: null argument pointer")
    return result


def selection_map(path):
    require(sha256(path) == EXPECTED_SELECTION_SHA256,
            "selection.json SHA-256 differs from the original 624-point mapping")
    raw = read_json(path)
    points = raw if isinstance(raw, list) else raw.get("points")
    require(isinstance(points, list) and len(points) == 624, "expected exactly 624 selected 3-D keys")
    selected, labels, horizontal = {}, {}, set()
    for point in points:
        require(isinstance(point, dict), "malformed selection point")
        i, j, k, label = point.get("i"), point.get("j"), point.get("k"), point.get("label")
        require(type(i) is int and type(j) is int and type(k) is int and type(label) is str,
                "selection key fields must have integer coordinates and string label")
        key = (i, j, k)
        require(key not in selected, f"duplicate selected 3-D key {key}")
        selected[key] = label
        labels.setdefault(label, set()).add(key)
        horizontal.add((i, j))
    require(len(horizontal) == 16, f"expected 16 distinct selected horizontal cells, got {len(horizontal)}")
    require(sorted(k for _, _, k in selected) == sorted(list(range(1, 40)) * 16),
            "selection must contain every level 1..39 at each of 16 horizontal cells")
    require(len(labels) == 16 and all(len(keys) == 39 for keys in labels.values()),
            "selection labels must identify 16 complete 39-level columns")
    return selected


def load_input_evidence(inputs_dir):
    copy_path = inputs_dir / "copy_manifest.json"
    provenance_path = inputs_dir / "provenance.json"
    verification_path = inputs_dir / "source_verification.json"
    require(read_json(verification_path).get("status") == "PASS_UNCHANGED_BEFORE_AFTER_READ",
            "source input verification is missing or failed")
    copy_manifest = read_json(copy_path)
    provenance = read_json(provenance_path)
    require(provenance.get("binary", {}).get("sha256") == EXPECTED_BINARY_SHA256,
            "original binary hash is not pinned by input provenance")
    require(provenance.get("binary", {}).get("readelf_has_debug_sections") is False,
            "provenance must retain the no-DWARF limitation")
    require(set(copy_manifest.get("arms", {})) == set(ARMS), "input manifest must bind all three arms")
    return copy_path, copy_manifest, provenance


def validate_receipt(arm, capture_dir, inputs_dir, selection_path, copy_path, copy_manifest,
                     provenance, capture_script, profile):
    receipt_path = capture_dir / arm / "receipt.json"
    receipt = read_json(receipt_path)
    require(receipt.get("status") == "TWO_CALLS_CAPTURED_INTENTIONAL_STOP",
            f"{arm}: runtime receipt status is not complete two-call capture")
    require(receipt.get("forecast_status") == "NOT_COMPLETED", f"{arm}: forecast unexpectedly completed")
    require(receipt.get("arm") == arm, f"{arm}: receipt arm mismatch")
    require(type(receipt.get("ranks")) is int and receipt["ranks"] == 8,
            f"{arm}: receipt must bind eight MPI ranks")
    require(type(receipt.get("omp_threads")) is int and receipt["omp_threads"] == 1,
            f"{arm}: receipt must bind OMP_NUM_THREADS=1")
    launcher_exit = receipt.get("launcher_exit")
    require(type(launcher_exit) is int and launcher_exit not in (124, 137),
            f"{arm}: timeout or forced-kill launcher exit is not analyzable")
    binary = receipt.get("binary", {})
    bound_binary = provenance["binary"]
    require(type(binary.get("path")) is str and binary.get("sha256") == EXPECTED_BINARY_SHA256 and
            binary.get("size_bytes") == bound_binary.get("size_bytes"),
            f"{arm}: runtime binary bytes do not match original receipt-bound executable")
    for key, path in (("script_sha256", capture_script), ("profile_sha256", profile),
                      ("selection_sha256", selection_path), ("copy_manifest_sha256", copy_path)):
        require(receipt.get(key) == sha256(path), f"{arm}: {key} mismatch")
    require(receipt.get("input_files_unchanged") == 88 and
            receipt.get("original_input_files_unchanged") == 88,
            f"{arm}: before/after 88-file input checks did not pass")
    expected_files = {Path(row["source_path"]).name: row
                      for row in copy_manifest["arms"][arm]["copy_files"]}
    require(len(expected_files) == 88, f"{arm}: historical input manifest must list 88 unique files")
    require(len({row["destination_name"] for row in copy_manifest["arms"][arm]["copy_files"]}) == 88,
            f"{arm}: historical input manifest destination names are not unique")
    for name, expected in expected_files.items():
        require(expected["destination_name"] == name,
                f"{arm}: copied input destination differs from historical basename for {name}")
        require(type(expected.get("sha256")) is str and re.fullmatch(r"[0-9a-f]{64}", expected["sha256"]) and
                type(expected.get("size_bytes")) is int and expected["size_bytes"] > 0,
                f"{arm}: malformed historical input manifest record {name}")
    namelists = read_json(inputs_dir / "namelist_comparison.json")
    require(namelists.get("identical_sha256") is True and
            expected_files["namelist.input"]["sha256"] == namelists["configs"][arm]["sha256"] and
            expected_files["namelist.input"]["size_bytes"] == namelists["configs"][arm]["size_bytes"],
            f"{arm}: copied namelist identity differs from the preserved arm comparison")
    netcdf = copy_manifest["arms"][arm]["netcdf_sources"]
    for name in ("wrfinput_d01", "wrfbdy_d01"):
        item = netcdf[name]["file"]
        require(expected_files[name]["sha256"] == item["sha256"] and
                expected_files[name]["size_bytes"] == item["size_bytes"],
                f"{arm}: NetCDF {name} identity differs from launch-copy manifest")
    mapped = receipt.get("runtime_mapped_files")
    require(isinstance(mapped, dict) and mapped,
            f"{arm}: runtime mapped file receipt is missing")
    mapped_executable = []
    for path, item in mapped.items():
        require(type(path) is str and isinstance(item, dict) and
                type(item.get("sha256")) is str and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) and
                type(item.get("size_bytes")) is int and item["size_bytes"] > 0,
                f"{arm}: malformed mapped runtime file record {path!r}")
        if path == binary["path"]:
            mapped_executable.append(item)
    require(len(mapped_executable) == 1 and
            mapped_executable[0]["sha256"] == EXPECTED_BINARY_SHA256 and
            mapped_executable[0]["size_bytes"] == bound_binary["size_bytes"],
            f"{arm}: mapped executable is missing or differs from pinned original")
    history = receipt.get("initial_history", {})
    expected_history = copy_manifest["arms"][arm]["netcdf_sources"]["initial_history_12z"]["file"]
    require(history.get("sha256") == expected_history["sha256"] and
            history.get("archived_sha256") == expected_history["sha256"] and
            history.get("byte_identical") is True and
            history.get("size_bytes") == expected_history["size_bytes"],
            f"{arm}: initial history is not byte-identical to retained source")
    statuses = receipt.get("rank_status")
    require(isinstance(statuses, list) and len(statuses) == 8, f"{arm}: expected eight rank status records")
    status_by_rank = {}
    for item in statuses:
        rank = item.get("rank")
        require(type(rank) is int and rank in RANKS and rank not in status_by_rank,
                f"{arm}: duplicate or malformed rank status")
        require(type(item.get("calls")) is int and item["calls"] == 2 and
                item.get("status") == "two_calls_returned",
                f"{arm}: rank {rank} did not return both calls")
        steps, dts = item.get("steps"), item.get("dts")
        require(isinstance(steps, list) and len(steps) == 2 and
                all(type(step) is int and step >= 0 for step in steps),
                f"{arm}: rank {rank} has invalid observed timestep receipts")
        require(isinstance(dts, list) and len(dts) == 2 and
                all(type(dt) in (int, float) and math.isfinite(dt) and dt > 0 for dt in dts),
                f"{arm}: rank {rank} has invalid observed dt receipts")
        status_by_rank[rank] = item
    require(set(status_by_rank) == set(RANKS), f"{arm}: rank status coverage incomplete")
    listed = receipt.get("captures")
    require(isinstance(listed, list) and len(listed) == 8, f"{arm}: expected eight hash-bound capture files")
    capture_paths = {}
    for item in listed:
        path = item.get("path")
        name = Path(path).name if isinstance(path, str) else ""
        match = CAPTURE_FILENAME.fullmatch(name)
        require(match is not None, f"{arm}: malformed capture receipt path {path!r}")
        rank = int(match.group(1))
        require(rank not in capture_paths, f"{arm}: duplicate capture path for rank {rank}")
        local_path = capture_dir / arm / name
        require(local_path.is_file(), f"{arm}: missing capture file {local_path}")
        raw = local_path.read_bytes()
        require(len(raw) == item.get("size_bytes") and sha256(local_path) == item.get("sha256"),
                f"{arm}: capture file hash/size mismatch for rank {rank}")
        decoded = gzip.decompress(raw) if name.endswith(".gz") else raw
        require(item.get("uncompressed_sha256") == hashlib.sha256(decoded).hexdigest() and
                item.get("uncompressed_size_bytes") == len(decoded),
                f"{arm}: uncompressed capture hash/size mismatch for rank {rank}")
        capture_paths[rank] = (local_path, int(match.group(2)))
    require(set(capture_paths) == set(RANKS), f"{arm}: capture files do not cover all ranks")
    return receipt, status_by_rank, capture_paths


def validate_bounds_and_arguments(entry, arm, rank, call_number):
    require(type(entry.get("call_number")) is int and entry["call_number"] == call_number,
            f"{arm} rank {rank}: call ordinal mismatch")
    require(str(entry.get("rank")) == str(rank), f"{arm} rank {rank}: entry rank mismatch")
    require(type(entry.get("pid")) is int and entry["pid"] > 0, f"{arm} rank {rank}: invalid pid")
    require(entry.get("binary_symbol") == "module_mp_kdm6_mp_kdm6_",
            f"{arm} rank {rank}: unexpected symbol identity")
    require(type(entry.get("argument_count")) is int and entry["argument_count"] == 77,
            f"{arm} rank {rank}: expected 77 arguments")
    raw_stack_hex = entry.get("raw_stack_hex_from_rsp_including_return_and_padding")
    require(type(raw_stack_hex) is str and len(raw_stack_hex) == 8 * 73 * 2 and
            re.fullmatch(r"[0-9a-f]+", raw_stack_hex) is not None,
            f"{arm} rank {rank}: malformed raw stack bytes")
    stack = bytes.fromhex(raw_stack_hex)
    require(entry.get("rsp_bytes_hex") == stack[:8].hex(), f"{arm} rank {rank}: RSP bytes mismatch")
    registers = entry.get("registers_hex")
    require(isinstance(registers, dict) and set(registers) == set(REGISTERS),
            f"{arm} rank {rank}: register pointer set mismatch")
    args = entry.get("arguments")
    require(isinstance(args, list) and len(args) == len(ARG_NAMES),
            f"{arm} rank {rank}: argument vector malformed")
    pointers = []
    for index, (arg, name) in enumerate(zip(args, ARG_NAMES), 1):
        require(type(arg.get("index")) is int and arg["index"] == index and arg.get("name") == name,
                f"{arm} rank {rank}: argument order/name mismatch at {index}")
        pointer = integer_pointer(arg.get("pointer_hex"), f"arg {index}/{name}")
        expected_location = "register:" + REGISTERS[index - 1] if index <= 6 else "stack:+%d" % (8 + 8 * (index - 7))
        require(arg.get("location") == expected_location, f"{arm} rank {rank}: argument location mismatch at {name}")
        if index <= 6:
            require(integer_pointer(registers[REGISTERS[index - 1]], name) == pointer,
                    f"{arm} rank {rank}: {name} register pointer mismatch")
        else:
            offset = 8 + (index - 7) * 8
            stack_pointer = struct.unpack_from("<Q", stack, offset)[0]
            require(pointer == stack_pointer, f"{arm} rank {rank}: {name} raw stack pointer mismatch")
        pointers.append(pointer)
    scalar = entry.get("scalar_raw4")
    require(isinstance(scalar, dict) and set(scalar) == SCALAR_REAL | SCALAR_INT,
            f"{arm} rank {rank}: scalar argument set mismatch")
    decoded = {}
    for name in SCALAR_REAL | SCALAR_INT:
        item = scalar[name]
        arg_index = ARG_NAMES.index(name) + 1
        require(type(item.get("arg")) is int and item["arg"] == arg_index,
                f"{arm} rank {rank}: scalar argument index mismatch: {name}")
        raw_hex = item.get("raw_hex")
        require(type(raw_hex) is str and re.fullmatch(r"[0-9a-f]{8}", raw_hex) is not None,
                f"{arm} rank {rank}: malformed {name} raw bytes")
        raw = bytes.fromhex(raw_hex)
        is_real = name in SCALAR_REAL
        value = struct.unpack("<f" if is_real else "<i", raw)[0]
        require(item.get("finite") is (math.isfinite(value) if is_real else True),
                f"{arm} rank {rank}: {name} finite flag mismatch")
        if is_real and not math.isfinite(value):
            require(item.get("decoded") is None, f"{arm} rank {rank}: nonfinite {name} must be null")
        else:
            require(type(item.get("decoded")) is (float if is_real else int),
                    f"{arm} rank {rank}: {name} decoded scalar has wrong type")
            require(item.get("decoded") == value, f"{arm} rank {rank}: {name} decoded scalar mismatch")
        decoded[name] = value
    require(decoded["itimestep"] >= 0 and math.isfinite(decoded["delt"]) and decoded["delt"] > 0,
            f"{arm} rank {rank}: invalid observed step or dt")
    require(type(entry.get("observed_itimestep")) is int and
            type(entry.get("observed_dt")) is float and
            entry.get("observed_itimestep") == decoded["itimestep"] and
            entry.get("observed_dt") == decoded["delt"],
            f"{arm} rank {rank}: observed step/dt disagree with raw scalar values")
    bounds, tile = entry.get("memory_bounds_ims_ime_jms_jme_kms_kme"), entry.get("tile_bounds_its_ite_jts_jte_kts_kte")
    require(isinstance(bounds, dict) and set(bounds) == set(BOUND_NAMES),
            f"{arm} rank {rank}: memory bounds malformed")
    require(isinstance(tile, dict) and set(tile) == set(TILE_NAMES),
            f"{arm} rank {rank}: tile bounds malformed")
    for low, high in (("ims", "ime"), ("jms", "jme"), ("kms", "kme")):
        require(type(bounds[low]) is int and type(bounds[high]) is int and bounds[low] <= bounds[high],
                f"{arm} rank {rank}: invalid memory bounds {low}/{high}")
        require(bounds[high] - bounds[low] < 1000, f"{arm} rank {rank}: oversized memory bounds")
    for low, high, mlow, mhigh in (("its", "ite", "ims", "ime"), ("jts", "jte", "jms", "jme"), ("kts", "kte", "kms", "kme")):
        require(type(tile[low]) is int and type(tile[high]) is int and
                bounds[mlow] <= tile[low] <= tile[high] <= bounds[mhigh],
                f"{arm} rank {rank}: tile bounds are outside memory bounds")
    for name, expected in {**bounds, **tile}.items():
        require(decoded[name] == expected, f"{arm} rank {rank}: scalar/map bounds disagree for {name}")
    return decoded, bounds, tile, pointers


def optional_is_active(name, scalar):
    return {"refl_10cm": bool(scalar["diagflag"]) and scalar["do_radar_ref"] == 1,
            "re_cloud": bool(scalar["has_reqc"]),
            "re_ice": bool(scalar["has_reqi"]),
            "re_snow": bool(scalar["has_reqs"])}[name]


def validate_samples(samples, selected, bounds, tile, arm, rank, call_number, endpoint,
                     scalar):
    require(isinstance(samples, list) and len(samples) == len(selected),
            f"{arm} rank {rank} call {call_number} {endpoint}: expected 624 sample rows")
    indexed = {}
    for sample in samples:
        key = (sample.get("i"), sample.get("j"), sample.get("k"))
        require(all(type(value) is int for value in key) and key in selected,
                f"{arm} rank {rank} call {call_number} {endpoint}: unselected sample key {key}")
        require(key not in indexed, f"{arm} rank {rank}: duplicate sample key {key}")
        require(sample.get("label") == selected[key], f"{arm} rank {rank}: sample label mismatch at {key}")
        require(sample.get("i_wrf_1based") == key[0] and sample.get("j_wrf_1based") == key[1] and
                sample.get("k_wrf_1based") == key[2], f"{arm} rank {rank}: coordinate alias mismatch at {key}")
        in_memory = all(bounds[lo] <= value <= bounds[hi] for lo, hi, value in
                        (("ims", "ime", key[0]), ("jms", "jme", key[1]), ("kms", "kme", key[2])))
        in_tile = all(tile[lo] <= value <= tile[hi] for lo, hi, value in
                      (("its", "ite", key[0]), ("jts", "jte", key[1]), ("kts", "kte", key[2])))
        status = sample.get("status")
        require(status == ("owned_tile" if in_memory and in_tile else
                           "halo_or_not_owned" if in_memory else "outside_memory_bounds"),
                f"{arm} rank {rank}: sample ownership contradicts captured bounds at {key}")
        if status == "owned_tile":
            values = sample.get("values")
            require(isinstance(values, dict) and set(values) == ARRAY_FIELDS,
                    f"{arm} rank {rank}: owned sample field set mismatch at {key}")
            nx = bounds["ime"] - bounds["ims"] + 1
            nz = bounds["kme"] - bounds["kms"] + 1
            for name in ARRAY_FIELDS:
                item = values[name]
                expected_offset = ((key[0] - bounds["ims"]) + (key[2] - bounds["kms"]) * nx +
                                   (key[1] - bounds["jms"]) * nx * nz) if name in ARRAY_3D else (
                                   (key[0] - bounds["ims"]) + (key[1] - bounds["jms"]) * nx)
                require(type(item.get("offset_f32")) is int and item["offset_f32"] == expected_offset,
                        f"{arm} rank {rank}: {name} sample offset mismatch at {key}")
                active = name not in OPTIONAL_FIELDS or optional_is_active(name, scalar)
                _, raw = real4(item, f"{arm} rank {rank} {name} {key}",
                               allow_nonfinite=not active)
                if active:
                    require(math.isfinite(struct.unpack("<f", raw)[0]),
                            f"{arm} rank {rank}: required finite {name} at {key}")
        else:
            require("values" not in sample, f"{arm} rank {rank}: non-owned sample contains values at {key}")
        indexed[key] = sample
    require(set(indexed) == set(selected), f"{arm} rank {rank}: selected sample coverage incomplete")
    return indexed


def load_capture(path, expected_pid, arm, rank, selected, receipt_rank):
    capture = read_json(path)
    require((type(capture.get("rank")) is str and capture["rank"] == str(rank)) or
            (type(capture.get("rank")) is int and capture["rank"] == rank),
            f"{arm} rank {rank}: capture rank identity mismatch")
    require(type(capture.get("pid")) is int and capture["pid"] > 0,
            f"{arm} rank {rank}: invalid capture pid")
    require(capture["pid"] == expected_pid, f"{arm} rank {rank}: capture PID differs from receipt path")
    require(capture.get("status") == "two_calls_returned", f"{arm} rank {rank}: capture incomplete")
    calls = capture.get("calls")
    require(isinstance(calls, list) and len(calls) == 2,
            f"{arm} rank {rank}: expected exactly two complete calls")
    result = {"arm": arm, "rank": rank, "pid": capture["pid"], "calls": []}
    for ordinal, envelope in enumerate(calls, 1):
        require(isinstance(envelope, dict) and isinstance(envelope.get("entry"), dict) and
                isinstance(envelope.get("return"), dict),
                f"{arm} rank {rank} call {ordinal}: missing entry/return event")
        entry, returned = envelope["entry"], envelope["return"]
        scalar, bounds, tile, _ = validate_bounds_and_arguments(entry, arm, rank, ordinal)
        require(entry["pid"] == capture["pid"], f"{arm} rank {rank}: entry pid mismatch")
        require(entry.get("pc") == "0x25df680" and entry.get("return_pc") == "0x20c3722",
                f"{arm} rank {rank}: entry/expected return PC mismatch")
        require(returned.get("pc") == entry["return_pc"],
                f"{arm} rank {rank} call {ordinal}: return event PC mismatch")
        require(receipt_rank["steps"][ordinal - 1] == scalar["itimestep"] and
                receipt_rank["dts"][ordinal - 1] == scalar["delt"],
                f"{arm} rank {rank} call {ordinal}: step/dt differs from runtime receipt")
        entry_samples = validate_samples(entry.get("samples"), selected, bounds, tile,
                                         arm, rank, ordinal, "entry", scalar)
        return_samples = validate_samples(returned.get("samples"), selected, bounds, tile,
                                          arm, rank, ordinal, "return", scalar)
        result["calls"].append({"ordinal": ordinal, "itimestep": scalar["itimestep"],
                                "dt": scalar["delt"], "diagflag": scalar["diagflag"],
                                "do_radar_ref": scalar["do_radar_ref"],
                                "has_reqc": scalar["has_reqc"], "has_reqi": scalar["has_reqi"],
                                "has_reqs": scalar["has_reqs"],
                                "entry": entry_samples, "return": return_samples})
    return result


def canonical_2d(values, field, arm):
    result = {}
    for i, j in {(key[0], key[1]) for key in values}:
        column = [values[(i, j, k)][field] for k in range(1, 40)]
        require(len(set(column)) == 1, f"{arm}: 2-D {field} differs across K at {(i, j)}")
        result[(i, j)] = column[0]
    return result


def endpoint_stats(raw_map, endpoint, arm, call_number, units):
    rowset = []
    pair_metrics = []
    for field in sorted(ARRAY_FIELDS):
        if field in ARRAY_2D:
            sampled = canonical_2d(raw_map, field, arm).values()
        else:
            sampled = (values[field] for values in raw_map.values())
        raws = [bytes.fromhex(value) for value in sampled]
        decoded = [struct.unpack("<f", raw)[0] for raw in raws]
        rowset.append({"arm": arm, "call_ordinal": call_number, "endpoint": endpoint,
                       "field": field, "sample_count": len(raws),
                       "finite_count": sum(math.isfinite(value) for value in decoded),
                       "exact_zero_count": sum(value == 0.0 for value in decoded),
                       "min_finite": min((value for value in decoded if math.isfinite(value)), default=None),
                       "max_finite": max((value for value in decoded if math.isfinite(value)), default=None)})
    for label, (mass_name, aux_name) in PAIR_FIELDS.items():
        ratios = []
        mass_zeros = aux_zeros = aux_positive = aux_negative = 0
        mass_positive = mass_negative = mass_positive_aux_zero = mass_positive_aux_positive = 0
        for values in raw_map.values():
            mass = struct.unpack("<f", bytes.fromhex(values[mass_name]))[0]
            aux = struct.unpack("<f", bytes.fromhex(values[aux_name]))[0]
            mass_zeros += mass == 0.0
            aux_zeros += aux == 0.0
            mass_positive += mass > 0.0
            mass_negative += mass < 0.0
            aux_negative += aux < 0.0
            mass_positive_aux_zero += mass > 0.0 and aux == 0.0
            mass_positive_aux_positive += mass > 0.0 and aux > 0.0
            if aux > 0.0:
                aux_positive += 1
                ratios.append(mass / aux)
        pair_metrics.append({"arm": arm, "call_ordinal": call_number, "endpoint": endpoint,
                             "pair": label, "mass_field": mass_name, "aux_field": aux_name,
                             "mass_source_candidate": SOURCE_CANDIDATES[mass_name],
                             "mass_source_units_netcdf": units[NETCDF_NAMES[mass_name]],
                             "aux_source_candidate": SOURCE_CANDIDATES[aux_name],
                             "aux_source_units_netcdf": units[NETCDF_NAMES[aux_name]],
                             "sample_count": len(raw_map), "mass_exact_zero_count": mass_zeros,
                             "aux_exact_zero_count": aux_zeros,
                             "mass_positive_count": mass_positive, "mass_negative_count": mass_negative,
                             "mass_positive_aux_zero_count": mass_positive_aux_zero,
                             "mass_positive_aux_positive_count": mass_positive_aux_positive,
                             "aux_positive_count": aux_positive, "aux_negative_count": aux_negative,
                             "ratio_count_aux_positive": len(ratios),
                             "raw_mass_to_aux_min": min(ratios, default=None),
                             "raw_mass_to_aux_max": max(ratios, default=None),
                             "raw_mass_to_aux_mean": sum(ratios) / len(ratios) if ratios else None,
                             "source_label_limit": "Candidate source argument labels only; archived executable has no DWARF.",
                             "interpretation": "Numeric ratio only; NetCDF units are provenance, and no physical closure or mass denominator is inferred."})
    return rowset, pair_metrics


def summarize_arm(arm, rank_records, units):
    field_delta_rows, pair_rows = [], []
    merged = {}
    for rank, record in rank_records.items():
        for call in record["calls"]:
            for endpoint in ("entry", "return"):
                for key, sample in call[endpoint].items():
                    if sample["status"] != "owned_tile":
                        continue
                    require(key not in merged.setdefault((call["ordinal"], endpoint), {}),
                            f"{arm}: selected key {key} is owned by multiple ranks")
                    owned = dict(sample)
                    owned["owner_rank"] = rank
                    merged[(call["ordinal"], endpoint)][key] = owned
    expected = 624
    for (call_number, endpoint), samples in merged.items():
        require(len(samples) == expected,
                f"{arm} call {call_number} {endpoint}: expected 624 uniquely owned selected keys, got {len(samples)}")
        rows, pairs = endpoint_stats({key: {field: sample["values"][field]["raw_hex"]
                                             for field in ARRAY_FIELDS}
                                        for key, sample in samples.items()}, endpoint, arm,
                                     call_number, units)
        field_delta_rows.extend(rows)
        pair_rows.extend(pairs)
    for call_number in (1, 2):
        entry, returned = merged[(call_number, "entry")], merged[(call_number, "return")]
        for field in sorted(ARRAY_FIELDS):
            before, after = ({key: sample["values"][field]["raw_hex"] for key, sample in end.items()}
                             for end in (entry, returned))
            field_delta_rows.append(delta_record(arm, call_number, "entry_to_return_delta", field,
                                                 before, after, field in ARRAY_2D))
    first_post, second_pre = merged[(1, "return")], merged[(2, "entry")]
    for field in sorted(ARRAY_FIELDS):
        before = {key: sample["values"][field]["raw_hex"] for key, sample in first_post.items()}
        after = {key: sample["values"][field]["raw_hex"] for key, sample in second_pre.items()}
        field_delta_rows.append(delta_record(arm, "1_return_to_2_entry", "inter_call_delta",
                                             field, before, after, field in ARRAY_2D))
    observed, call_rows = [], []
    for rank, record in sorted(rank_records.items()):
        observed.append({"rank": rank,
                         "calls": [{"ordinal": call["ordinal"], "itimestep": call["itimestep"], "dt": call["dt"]}
                                   for call in record["calls"]]})
    for call_number in (1, 2):
        call0 = rank_records[0]["calls"][call_number - 1]
        call_rows.append({"arm": arm, "call_ordinal": call_number,
                          "observed_itimestep": call0["itimestep"], "observed_dt": call0["dt"],
                          "diagflag": call0["diagflag"], "do_radar_ref": call0["do_radar_ref"],
                          "has_reqc": call0["has_reqc"], "has_reqi": call0["has_reqi"],
                          "has_reqs": call0["has_reqs"],
                          "optional_gate_interpretation": "Runtime flags are recorded as captured. Candidate co-located KDM6 source uses diagflag AND do_radar_ref==1 for refl_10cm; exact compiled source identity is unverified.",
                          "rank_count": len(rank_records), "events_per_rank": 2,
                          "entry_keys_owned_once": len(merged[(call_number, "entry")]),
                          "return_keys_owned_once": len(merged[(call_number, "return")]),
                          "event_order": "entry_then_return; next ordinal is recorded independently"})
    summary = {"arm": arm, "rank_count": len(rank_records), "calls_per_rank": 2,
               "selected_3d_keys_per_endpoint": 624, "deduplicated_horizontal_columns": 16,
               "observed_rank_steps_and_dt": observed,
               "event_sequence_complete": True,
               "optional_state_scope": "diagflag/do_radar_ref and has_re* are runtime flags, not proof arrays were initialized or consumed. Candidate co-located source gates refl_10cm with diagflag AND do_radar_ref==1; the no-DWARF binary is not source-bound.",
               "scope": "Captured endpoint arrays and selected raw REAL*4 state only; no process-causality or mass/number closure claim. QIB is retained separately and is not used as a number denominator."}
    return summary, call_rows, field_delta_rows, pair_rows, merged


def profile_rows(arm, merged):
    rows = []
    for (call_number, endpoint), samples in sorted(merged.items()):
        for (i, j, k), sample in sorted(samples.items()):
            row = {"arm": arm, "rank": sample["owner_rank"], "call_ordinal": call_number,
                   "endpoint": endpoint, "label": sample["label"], "i": i, "j": j, "k": k}
            for field in sorted(ARRAY_FIELDS):
                value = sample["values"][field]
                row[field] = value["value_f32"]
                row[field + "_raw_hex"] = value["raw_hex"]
                row[field + "_finite"] = value["finite"]
            rows.append(row)
    return rows


def delta_record(arm, call_number, endpoint, field, before, after, is_2d):
    if is_2d:
        before, after = canonical_2d({key: {field: value} for key, value in before.items()}, field, arm), \
                        canonical_2d({key: {field: value} for key, value in after.items()}, field, arm)
    require(set(before) == set(after), f"{arm}: {field} delta endpoints have different selected keys")
    changed = increase = decrease = 0
    for key in before:
        left, right = bytes.fromhex(before[key]), bytes.fromhex(after[key])
        left_value, right_value = struct.unpack("<f", left)[0], struct.unpack("<f", right)[0]
        changed += left != right
        if math.isfinite(left_value) and math.isfinite(right_value):
            increase += right_value > left_value
            decrease += right_value < left_value
    return {"arm": arm, "call_ordinal": call_number, "endpoint": endpoint, "field": field,
            "sample_count": len(before), "raw_changed_count": changed,
            "raw_unchanged_count": len(before) - changed,
            "finite_increase_count": increase, "finite_decrease_count": decrease,
            "comparison": "raw REAL*4 bytes; finite numeric direction also counted"}


def validate_arm(arm, capture_dir, inputs_dir, selection_path, copy_path, copy_manifest,
                 provenance, capture_script, profile, selected):
    receipt, receipt_ranks, paths = validate_receipt(
        arm, capture_dir, inputs_dir, selection_path, copy_path, copy_manifest,
        provenance, capture_script, profile)
    rank_records = {}
    for rank, (path, expected_pid) in paths.items():
        rank_records[rank] = load_capture(path, expected_pid, arm, rank, selected, receipt_ranks[rank])
    unit_metadata = copy_manifest["arms"][arm]["netcdf_sources"]["wrfinput_d01"]["variables"]
    units = {name: unit_metadata[name].get("units", "(attribute absent)")
             for name in set(NETCDF_NAMES.values())}
    summary, call_rows, deltas, pairs, merged = summarize_arm(arm, rank_records, units)
    # Every captured rank must report the same timeline as its peer; actual values may be any valid step.
    timeline = [[call["itimestep"], call["dt"]] for call in rank_records[0]["calls"]]
    for rank, record in rank_records.items():
        require([[call["itimestep"], call["dt"]] for call in record["calls"]] == timeline,
                f"{arm}: rank {rank} observed step/dt timeline differs from rank 0")
    summary["runtime_receipt_sha256"] = sha256(capture_dir / arm / "receipt.json")
    summary["runtime_mapped_file_count"] = len(receipt["runtime_mapped_files"])
    summary["unavailable_mappings"] = receipt.get("unavailable_mappings", [])
    summary["unavailable_mapping_count"] = len(summary["unavailable_mappings"])
    return summary, call_rows, deltas, pairs, merged


def write_csv(path, rows):
    require(rows, f"refusing to write empty CSV: {path.name}")
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def analyze(capture_dir, output_dir, *, inputs_dir=INPUTS, selection_path=DEFAULT_SELECTION,
            capture_script=CAPTURE_SCRIPT, profile=PROFILE):
    capture_dir, output_dir = Path(capture_dir), Path(output_dir)
    inputs_dir, selection_path = Path(inputs_dir), Path(selection_path)
    capture_script, profile = Path(capture_script), Path(profile)
    require(capture_dir.is_dir(), f"capture root is not a directory: {capture_dir}")
    require(not output_dir.exists(), f"output path already exists: {output_dir}")
    for path in (selection_path, capture_script, profile):
        require(path.is_file(), f"required provenance file is missing: {path}")
    require(sha256(capture_script) == EXPECTED_SCRIPT_SHA256,
            "capture GDB script does not match the reviewed frozen bytes")
    require(sha256(profile) == EXPECTED_PROFILE_SHA256,
            "pinned Intel profile does not match the runtime receipt bytes")
    copy_path, copy_manifest, provenance = load_input_evidence(inputs_dir)
    selected = selection_map(selection_path)
    results = {"schema": "cp02-kdm6-three-control-capture-v1", "status": "PASS_SCOPED_CAPTURE_COMPLETE",
               "inputs": {"copy_manifest_sha256": sha256(copy_path),
                          "selection_sha256": sha256(selection_path),
                          "capture_script_sha256": sha256(capture_script),
                          "intel_profile_sha256": sha256(profile)},
               "arms": []}
    all_call_rows, all_deltas, all_pairs, all_profiles = [], [], [], []
    for arm in ARMS:
        summary, call_rows, deltas, pairs, merged = validate_arm(
            arm, capture_dir, inputs_dir, selection_path, copy_path, copy_manifest,
            provenance, capture_script, profile, selected)
        results["arms"].append(summary)
        all_call_rows.extend(call_rows)
        all_deltas.extend(deltas)
        all_pairs.extend(pairs)
        all_profiles.extend(profile_rows(arm, merged))
    staging = None
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        staging = Path(tempfile.mkdtemp(prefix="." + output_dir.name + ".", dir=output_dir.parent))
        (staging / "summary.json").write_text(json.dumps(results, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        write_csv(staging / "per_arm_call.csv", all_call_rows)
        write_csv(staging / "field_deltas.csv", all_deltas)
        write_csv(staging / "mass_aux_ratios.csv", all_pairs)
        write_csv(staging / "selected_profiles.csv", all_profiles)
        os.replace(staging, output_dir)
        staging = None
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", required=True, type=Path,
                        help="directory containing OFF/, HYDRO/, LIQUID/ with rank captures and receipts")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="new, nonexistent output directory (writes atomically after all validation)")
    parser.add_argument("--inputs-dir", type=Path, default=INPUTS)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--capture-script", type=Path, default=CAPTURE_SCRIPT)
    parser.add_argument("--profile", type=Path, default=PROFILE)
    args = parser.parse_args(argv)
    try:
        summary = analyze(args.capture_dir, args.output_dir, inputs_dir=args.inputs_dir,
                          selection_path=args.selection, capture_script=args.capture_script,
                          profile=args.profile)
    except (ValueError, OSError, KeyError, TypeError, struct.error) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": summary["status"], "output_dir": str(args.output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
