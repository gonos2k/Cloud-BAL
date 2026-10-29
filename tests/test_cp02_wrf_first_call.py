import copy
import gzip
import hashlib
import importlib.util
import json
import struct
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools/cp02_wrf_first_call.py"
SPEC = importlib.util.spec_from_file_location("cp02_wrf_first_call", TOOL_PATH)
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


def f32(value):
    raw = struct.pack("<f", value)
    return {"raw_hex": raw.hex(), "value_f32": struct.unpack("<f", raw)[0]}


def synthetic_captures():
    points = [{"label": f"P{index:03d}", "i": index, "j": 1, "k": 1}
              for index in (1, 2)]
    captures = {}
    for rank in TOOL.EXPECTED_RANKS:
        rank_number = int(rank)
        memory = {"ims": 1, "ime": 8, "jms": 1, "jme": 1, "kms": 1, "kme": 1}
        tile = {"its": rank_number + 1, "ite": rank_number + 1,
                "jts": 1, "jte": 1, "kts": 1, "kte": 1}
        samples = []
        for point in points:
            owned = point["i"] == rank_number + 1
            sample = {**point, "status": "owned_tile" if owned else "halo_or_not_owned"}
            if owned:
                values = {}
                for index, name in enumerate(sorted(TOOL.ARRAY_FIELDS), 1):
                    item = f32(float(index))
                    if name == "q":
                        item = f32(float(index) + 0.25)
                    item["offset_f32"] = point["i"] - 1
                    values[name] = item
                sample["values"] = values
            samples.append(sample)
        scalars = {}
        for name in TOOL.SCALAR_REAL:
            value = 20.0 if name == "delt" else 1.0
            raw = struct.pack("<f", value)
            scalars[name] = {"arg": TOOL.ARG_NAMES.index(name) + 1,
                             "raw_hex": raw.hex(), "decoded": value}
        for name in TOOL.SCALAR_INT:
            bound_values = {"ims": memory["ims"], "ime": memory["ime"],
                            "jms": memory["jms"], "jme": memory["jme"],
                            "kms": memory["kms"], "kme": memory["kme"],
                            "its": tile["its"], "ite": tile["ite"],
                            "jts": tile["jts"], "jte": tile["jte"],
                            "kts": tile["kts"], "kte": tile["kte"]}
            value = 1 if name == "itimestep" else bound_values.get(name, 0)
            raw = struct.pack("<i", value)
            scalars[name] = {"arg": TOOL.ARG_NAMES.index(name) + 1,
                             "raw_hex": raw.hex(), "decoded": value}
        rsp = 0x100000 + rank_number * 0x1000
        pointers = [0x10000 + index * 16 for index in range(1, 78)]
        stack = struct.pack("<Q", int(TOOL.RETURN_PC, 16))
        stack += b"".join(struct.pack("<Q", pointer) for pointer in pointers[6:])
        stack += struct.pack("<Q", 0)
        args = [{"index": index, "name": name, "pointer_hex": hex(pointers[index - 1]),
                 "location": "register:" + ("rdi", "rsi", "rdx", "rcx", "r8", "r9")[index - 1]
                 if index <= 6 else f"stack:+{8 + 8 * (index - 7)}"}
                for index, name in enumerate(TOOL.ARG_NAMES, 1)]
        entry = {
            "rank": rank, "pid": 4000 + rank_number, "pc": TOOL.ENTRY_PC,
            "return_pc": TOOL.RETURN_PC, "argument_count": 77, "arguments": args,
            "rsp_hex": hex(rsp), "rsp_bytes_hex": stack[:8].hex(),
            "raw_stack_hex_from_rsp_including_return_and_padding": stack.hex(),
            "registers_hex": dict(zip(("rdi", "rsi", "rdx", "rcx", "r8", "r9"),
                                      map(hex, pointers[:6]))),
            "memory_bounds_ims_ime_jms_jme_kms_kme": memory,
            "tile_bounds_its_ite_jts_jte_kts_kte": tile,
            "scalar_raw4": scalars, "selection_points": points, "samples": samples,
        }
        captures[rank] = (Path(f"rank{rank}.json"),
                          {"status": "return_captured", "entry": entry,
                           "return": {"pc": TOOL.RETURN_PC,
                                      "samples": copy.deepcopy(samples)}},
                          memory, tile)
    return captures


def write_captures(captures, directory):
    for rank, (_, capture, _, _) in captures.items():
        path = directory / f"capture_rank{rank}_pid{capture['entry']['pid']}.json"
        path.write_text(json.dumps(capture), encoding="utf-8")


def test_capture_contract_accepts_unique_rank_ownership_and_finite_samples():
    selected, owned = TOOL.validate_captures(synthetic_captures(), expected_points=2)
    assert len(selected) == len(owned) == 2
    assert {rank for rank, _, _ in owned.values()} == {"0", "1"}


def test_malformed_coordinate_type_is_rejected():
    captures = synthetic_captures()
    captures["0"][1]["entry"]["samples"][0]["i"] = True
    with pytest.raises(ValueError, match="coordinates must be integers"):
        TOOL.validate_captures(captures, expected_points=2)


def test_coordinate_alias_mismatch_is_rejected():
    captures = synthetic_captures()
    captures["0"][1]["entry"]["samples"][0]["i_wrf_1based"] = 2
    with pytest.raises(ValueError, match="coordinate alias mismatch"):
        TOOL.validate_captures(captures, expected_points=2)


def test_missing_rank_is_rejected(tmp_path):
    for rank in TOOL.EXPECTED_RANKS[:-1]:
        (tmp_path / f"capture_rank{rank}_pid{rank}.json").write_text(
            json.dumps({"entry": {"rank": rank}}), encoding="utf-8")
    with pytest.raises(ValueError, match="eight rank capture files"):
        TOOL.read_captures(tmp_path)


def test_return_pc_mismatch_is_rejected(tmp_path):
    captures = synthetic_captures()
    captures["0"][1]["return"]["pc"] = "0x123"
    write_captures(captures, tmp_path)
    with pytest.raises(ValueError, match="return PC mismatch"):
        TOOL.read_captures(tmp_path)


def test_duplicate_point_ownership_is_rejected():
    captures = synthetic_captures()
    path, capture, memory, tile = captures["2"]
    tile["its"] = tile["ite"] = 1
    for state in (capture["entry"]["samples"], capture["return"]["samples"]):
        state[0]["status"] = "owned_tile"
        state[0]["values"] = copy.deepcopy(captures["0"][1]["entry"]["samples"][0]["values"])
    captures["2"] = path, capture, memory, tile
    with pytest.raises(ValueError, match="exactly one owned"):
        TOOL.validate_captures(captures, expected_points=2)


def test_out_of_domain_selection_is_rejected():
    captures = synthetic_captures()
    for _, capture, _, _ in captures.values():
        capture["entry"]["selection_points"][0]["i"] = 235
    with pytest.raises(ValueError, match="outside input WRF domain"):
        TOOL.validate_captures(captures, expected_points=2, domain_shape=(234, 282, 39))


def test_raw_sample_mismatch_is_rejected():
    captures = synthetic_captures()
    sample = captures["0"][1]["entry"]["samples"][0]
    sample["values"]["q"]["value_f32"] += 1.0
    with pytest.raises(ValueError, match="raw bytes disagree"):
        TOOL.validate_captures(captures, expected_points=2)


def test_array_offset_mismatch_is_rejected():
    captures = synthetic_captures()
    sample = captures["0"][1]["entry"]["samples"][0]
    sample["values"]["q"]["offset_f32"] += 1
    with pytest.raises(ValueError, match="array offset mismatch"):
        TOOL.validate_captures(captures, expected_points=2)


def test_scalar_memory_bound_mismatch_is_rejected():
    captures = synthetic_captures()
    scalars = captures["0"][1]["entry"]["scalar_raw4"]
    memory, tile = captures["0"][2:]
    with pytest.raises(ValueError, match="ime: scalar bound differs"):
        TOOL.validate_scalar_raw(scalars, {**memory, "ime": 7}, tile)


def test_scalar_argument_index_mismatch_is_rejected():
    captures = synthetic_captures()
    scalars = captures["0"][1]["entry"]["scalar_raw4"]
    memory, tile = captures["0"][2:]
    scalars["ims"]["arg"] = 1
    with pytest.raises(ValueError, match="ims: scalar argument index mismatch"):
        TOOL.validate_scalar_raw(scalars, memory, tile)


def receipt_fixture(tmp_path):
    capture_dir = tmp_path / "capture"
    capture_dir.mkdir()
    captures = synthetic_captures()
    receipt_captures = []
    for rank, (_, capture, memory, tile) in captures.items():
        path = capture_dir / f"capture_rank{rank}_pid{capture['entry']['pid']}.json.gz"
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            json.dump(capture, stream)
        captures[rank] = path, capture, memory, tile
        receipt_captures.append({"path": path.name,
                                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    hashes = {"wrfinput_d01": "1" * 64, "wrfbdy_d01": "2" * 64,
              "namelist.input": "3" * 64, "native_initial_history": "4" * 64}
    manifest_path = tmp_path / "input_manifest.json"
    manifest = {
        "launcher": {"binary_sha256_expected": "a" * 64,
                     "binary_observed_sha256": "a" * 64},
        "sources": {"wrfinput_d01": {"sha256": hashes["wrfinput_d01"]},
                    "native_initial_history": {"sha256": hashes["native_initial_history"]}},
        "boundary": {"sha256": hashes["wrfbdy_d01"]},
        "namelist": {"sha256": hashes["namelist.input"]},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    input_copy_path = capture_dir / "input_copy.json"
    input_copy = {"files": [{"name": name, "sha256": digest}
                             for name, digest in hashes.items()
                             if name != "native_initial_history"]}
    input_copy_path.write_text(json.dumps(input_copy), encoding="utf-8")
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps({"points": captures["0"][1]["entry"]["selection_points"]}),
                              encoding="utf-8")
    receipt_path = capture_dir / "receipt.json"
    receipt = {
        "status": "FIRST_CALL_CAPTURED_INTENTIONAL_STOP", "forecast_status": "NOT_COMPLETED",
        "ranks": 8, "selected_points": 2, "launcher_exit": 255,
        "input_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "selection_sha256": hashlib.sha256(selection_path.read_bytes()).hexdigest(),
        "input_copy_sha256": hashlib.sha256(input_copy_path.read_bytes()).hexdigest(),
        "binary": {"path": "/fake/wrf.exe", "sha256": "a" * 64},
        "runtime_mapped_files": {"/fake/wrf.exe": {"sha256": "a" * 64}},
        "input_files_unchanged": 3, "original_input_files_unchanged": 3,
        "initial_history": {"sha256": hashes["native_initial_history"],
                            "archived_sha256": hashes["native_initial_history"],
                            "byte_identical": True},
        "captures": receipt_captures,
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return capture_dir, receipt_path, manifest_path, selection_path, captures, receipt


@pytest.mark.parametrize("field,error", [
    ("input_manifest_sha256", "input manifest SHA-256 mismatch"),
    ("selection_sha256", "selection SHA-256 mismatch"),
    ("capture_sha256", "capture SHA-256 mismatch"),
    ("input_copy_sha256", "input-copy inventory SHA-256 mismatch"),
    ("binary_sha256", "executable SHA-256 differs"),
    ("manifest_observed_binary_sha256", "manifest observed executable SHA-256 differs"),
    ("runtime_binary_sha256", "runtime mapping does not bind"),
    ("count", "input_files_unchanged"),
    ("original_count", "original_input_files_unchanged"),
    ("bool_count", "input_files_unchanged"),
    ("input_content_hash", "input-copy wrfinput_d01 hash differs"),
    ("history_flag", "equality flag contradicts"),
    ("history_archive", "archived initial-history hash differs"),
    ("history_hash_missing", "initial-history hashes must be lowercase SHA-256"),
    ("launcher_exit", "intentional launcher stop"),
])
def test_receipt_hash_bindings_are_required(tmp_path, field, error):
    capture_dir, receipt_path, manifest_path, selection_path, captures, receipt = receipt_fixture(tmp_path)
    if field == "capture_sha256":
        receipt["captures"][0]["sha256"] = "0" * 64
    elif field == "binary_sha256":
        receipt["binary"]["sha256"] = "0" * 64
    elif field == "manifest_observed_binary_sha256":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["launcher"]["binary_observed_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        receipt["input_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    elif field == "runtime_binary_sha256":
        receipt["runtime_mapped_files"]["/fake/wrf.exe"]["sha256"] = "0" * 64
    elif field == "count":
        receipt["input_files_unchanged"] = 2
    elif field == "bool_count":
        receipt["input_files_unchanged"] = True
    elif field == "original_count":
        receipt["original_input_files_unchanged"] = 2
    elif field == "input_content_hash":
        input_copy_path = capture_dir / "input_copy.json"
        input_copy = json.loads(input_copy_path.read_text(encoding="utf-8"))
        next(item for item in input_copy["files"] if item["name"] == "wrfinput_d01")["sha256"] = "0" * 64
        input_copy_path.write_text(json.dumps(input_copy), encoding="utf-8")
        receipt["input_copy_sha256"] = hashlib.sha256(input_copy_path.read_bytes()).hexdigest()
    elif field == "history_flag":
        receipt["initial_history"]["byte_identical"] = False
    elif field == "history_archive":
        receipt["initial_history"]["archived_sha256"] = "0" * 64
    elif field == "history_hash_missing":
        receipt["initial_history"]["sha256"] = None
    elif field == "launcher_exit":
        receipt["launcher_exit"] = 0
    else:
        receipt[field] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        TOOL.validate_receipt(capture_dir, receipt_path, manifest_path, selection_path, captures)
