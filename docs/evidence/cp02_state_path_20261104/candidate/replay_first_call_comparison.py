#!/usr/bin/env python3
"""Compare first-call CBSP state for corrected FIX and B1 prior quick probes."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "docs/evidence/cp02_state_path_20261104/candidate"
BASE = OUT / "preflight_baseline"
CANDIDATE = OUT / "preflight_capture"
NATIVE_CAPTURE = REPO / "docs/evidence/cp02_state_path_20261104/native/capture"
FULL_ARCHIVE_MANIFEST = NATIVE_CAPTURE / "capture_archive_manifest.json"
BASE_MANIFEST = BASE / "baseline_manifest.json"
CANDIDATE_MANIFEST = CANDIDATE / "capture_manifest.json"
SCHEMA = NATIVE_CAPTURE / "state_schema.json"
CORNERS = REPO / "docs/evidence/cp02_state_path_20261104/cohorts/point_corners.csv"
EXPECTED_EXE = "6706f6162d37c057b2699afd03ae7c0b4dbf94fe97b925c0369916ba6c708661"
SHAPE = (282, 234, 39)  # y, x, z; history interior, with observed-call mask kept separately
STAGE_FIELDS = {
    "entry": {
        "qv": ("QV_PUBLIC_RAW", "kg kg-1 convention; host denominator basis unbound"),
        "temperature": ("T_K_DERIVED_TH_TIMES_PII", "K; derived actual temperature, distinct from TH"),
        "qr": ("QR_PUBLIC_RAW", "kg kg-1 convention; host denominator basis unbound"),
        "nr": ("NR_PUBLIC_RAW", "raw public number-field value; unit and density basis unassigned"),
    },
    "pre_update": {
        "qv": ("QV_INTERNAL_RAW", "kg kg-1 convention; host denominator basis unbound"),
        "temperature": ("T_K_INTERNAL", "K; actual internal temperature"),
        "qr": ("QR_INTERNAL", "kg kg-1 convention; host denominator basis unbound"),
        "nr": ("NR_INTERNAL", "raw internal nrs representation; density basis unassigned"),
    },
    "post_process": {
        "qv": ("QV_INTERNAL_RAW", "kg kg-1 convention; host denominator basis unbound"),
        "temperature": ("T_K_INTERNAL", "K; actual internal temperature"),
        "qr": ("QR_INTERNAL", "kg kg-1 convention; host denominator basis unbound"),
        "nr": ("NR_INTERNAL", "raw internal nrs representation; density basis unassigned"),
    },
    "kdm62d_return": {
        "qv": ("QV_INTERNAL_RAW", "kg kg-1 convention; host denominator basis unbound"),
        "temperature": ("T_K_INTERNAL", "K; actual internal temperature"),
        "qr": ("QR_INTERNAL", "kg kg-1 convention; host denominator basis unbound"),
        "nr": ("NR_INTERNAL", "raw internal nrs representation; density basis unassigned"),
    },
    "wrapper_return": {
        "qv": ("QV_PUBLIC_RAW", "kg kg-1 convention; host denominator basis unbound"),
        "temperature": ("T_K_DERIVED_TH_TIMES_PII", "K; derived actual temperature, distinct from TH"),
        "qr": ("QR_PUBLIC_RAW", "kg kg-1 convention; host denominator basis unbound"),
        "nr": ("NR_PUBLIC_RAW", "raw public number-field value; unit and density basis unassigned"),
    },
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("cp02_state_path", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_receipt(root: Path, name: str) -> tuple[dict, Path]:
    path = root / name
    if not path.is_file():
        raise RuntimeError(f"missing run receipt: {path}")
    return json.loads(path.read_text()), path


def locate_scan(root: Path) -> Path:
    for name in ("quick_binary_scan.json", "candidate_quick_binary_scan.json"):
        path = root / name
        if path.is_file():
            return path
    raise RuntimeError(f"missing binary scan receipt under {root}")


def verify_baseline_archive() -> tuple[dict, dict]:
    manifest = json.loads(BASE_MANIFEST.read_text())
    full = json.loads(FULL_ARCHIVE_MANIFEST.read_text())
    if manifest.get("status") != "PASS" or manifest.get("raw_quick_vs_full_fix_equal_streams") != 40:
        raise RuntimeError("baseline quick-to-full FIX raw-stream identity proof is absent or failed")
    full_records = {Path(row["raw_path"]).name: row for row in full["files"]
                    if row.get("arm") == "FIX" and row.get("content_type") == "CBSP0001"}
    if digest(FULL_ARCHIVE_MANIFEST) != manifest["archive_sources"]["full_capture_manifest_sha256"]:
        raise RuntimeError("full FIX archive manifest hash differs from baseline proof")
    seen = set()
    for row in manifest["streams"]:
        name = row["archive_name"]
        if name in seen:
            raise RuntimeError(f"duplicate baseline archive entry: {name}")
        seen.add(name)
        path = BASE / name
        full_row = full_records.get(name.removesuffix(".gz"))
        if full_row is None or full_row["archive_sha256"] != row["archive_sha256"]:
            raise RuntimeError(f"{name}: baseline stream is not the corresponding full FIX archive stream")
        if digest(path) != row["archive_sha256"] or path.stat().st_size != row["archive_bytes"]:
            raise RuntimeError(f"{name}: baseline compressed stream hash/size mismatch")
        h = hashlib.sha256()
        byte_count = 0
        with gzip.open(path, "rb") as source:
            for block in iter(lambda: source.read(1 << 20), b""):
                h.update(block)
                byte_count += len(block)
        if h.hexdigest() != row["raw_sha256"] or byte_count != row["raw_bytes"]:
            raise RuntimeError(f"{name}: baseline decompressed bytes differ from pinned quick/full FIX raw SHA")
        if row["raw_sha256"] != full_row["raw_sha256"]:
            raise RuntimeError(f"{name}: quick/full FIX raw SHA proof disagrees with full archive")
    if len(seen) != 40:
        raise RuntimeError(f"baseline archive has {len(seen)} stage/rank streams, expected 40")
    for name, meta in manifest["support_files"].items():
        path = BASE / name
        if digest(path) != meta["sha256"] or path.stat().st_size != meta["bytes"]:
            raise RuntimeError(f"baseline sidecar hash/size mismatch: {name}")
    return manifest, full


def verify_candidate_archive() -> dict:
    manifest = json.loads(CANDIDATE_MANIFEST.read_text())
    if manifest.get("status") != "PASS" or manifest.get("probe_executable_sha256") != EXPECTED_EXE:
        raise RuntimeError("candidate archive status or executable pin is invalid")
    seen = set()
    for row in manifest["state_streams"]:
        name = row["name"]
        if name in seen:
            raise RuntimeError(f"duplicate candidate archive entry: {name}")
        seen.add(name)
        path = CANDIDATE / name
        if digest(path) != row["gzip_sha256"] or path.stat().st_size != row["gzip_size_bytes"]:
            raise RuntimeError(f"{name}: candidate compressed stream hash/size mismatch")
        h = hashlib.sha256()
        byte_count = 0
        with gzip.open(path, "rb") as source:
            for block in iter(lambda: source.read(1 << 20), b""):
                h.update(block)
                byte_count += len(block)
        if h.hexdigest() != row["source_sha256"] or byte_count != row["source_size_bytes"]:
            raise RuntimeError(f"{name}: candidate decompressed stream hash/size mismatch")
    if len(seen) != 56:
        raise RuntimeError(f"candidate archive has {len(seen)} streams, expected 56")
    for row in manifest["support_files"]:
        path = CANDIDATE / row["name"]
        if digest(path) != row["sha256"] or path.stat().st_size != row["size_bytes"]:
            raise RuntimeError(f"candidate sidecar hash/size mismatch: {row['name']}")
    return manifest


def field_index(fields: tuple[str, ...], name: str) -> int:
    try:
        return fields.index(name)
    except ValueError as exc:
        raise RuntimeError(f"schema field {name!r} absent from {fields}") from exc


def f32_bits(value: np.float32) -> str:
    return f"0x{struct.unpack('>I', struct.pack('>f', float(value)))[0]:08x}"


def main() -> None:
    state = load_module(REPO / "tools/cp02_state_path.py")
    base_manifest, full_manifest = verify_baseline_archive()
    candidate_manifest = verify_candidate_archive()
    base_receipt, base_receipt_path = load_receipt(BASE, "quick_run_receipt.json")
    cand_receipt, cand_receipt_path = load_receipt(CANDIDATE, "candidate_quick_run_receipt_v2.json")
    base_case, base_case_path = load_receipt(BASE, "quick_case_receipt.json")
    for receipt, receipt_path in ((base_receipt, base_receipt_path), (cand_receipt, cand_receipt_path)):
        if receipt.get("status") not in {"SUCCESS_FORMAT_VALIDATION_ONLY", "SUCCESS"}:
            raise RuntimeError(f"{receipt_path}: run status is not successful")
        if receipt.get("run_seconds") != 20 or receipt.get("mpi_ranks") != 8:
            raise RuntimeError(f"{receipt_path}: expected the 20-second, 8-rank quick probe")
        if receipt.get("executable_sha256") != EXPECTED_EXE:
            raise RuntimeError(f"{receipt_path}: executable hash differs from pinned quick-probe executable")
    for scan_path in (locate_scan(BASE), locate_scan(CANDIDATE)):
        scan = json.loads(scan_path.read_text())
        if scan.get("status") != "PASS":
            raise RuntimeError(f"{scan_path}: binary scan did not pass")
    binputs = base_case.get("input_files")
    cinputs = cand_receipt.get("staged_input_sha256")
    if not isinstance(binputs, dict) or not isinstance(cinputs, dict) or set(binputs) != set(cinputs):
        raise RuntimeError("the quick-probe receipts do not expose matching complete staged-input inventories")
    changed_inputs = sorted(key for key in binputs if binputs[key] != cinputs[key])
    if changed_inputs != ["wrfinput_d01"]:
        raise RuntimeError(f"expected only wrfinput_d01 to differ, got {changed_inputs}")

    base_calls = state.read_call_inventory(BASE, expected_timesteps=(1,))
    cand_calls = state.read_call_inventory(CANDIDATE, expected_timesteps=(1,))
    state._calls_equal(base_calls, cand_calls)
    ids, selected = state.load_selected_cells(CORNERS)
    if ids[:2] != ["P01", "P02"]:
        raise RuntimeError(f"unexpected selected-cohort order: {ids}")
    base_schema = BASE / "state_schema.json"
    candidate_schema = CANDIDATE / "state_schema.json"
    if digest(base_schema) != digest(SCHEMA) or digest(candidate_schema) != digest(SCHEMA):
        raise RuntimeError("baseline, candidate, and full-run state schemas differ")
    schema, specs = state.load_schema(SCHEMA)
    stage_order = ("entry", "pre_update", "post_process", "kdm62d_return", "wrapper_return")
    owner_and_mask_sha = {}
    metric_rows: list[dict] = []
    corner_rows: list[dict] = []
    work = Path(tempfile.mkdtemp(prefix="cp02-first-call-replay-"))

    for stage_name in stage_order:
        spec = next(item for item in specs.values() if item.name == stage_name)
        base_values, base_mask, base_owner, base_info = state.read_global_stage(
            BASE, spec, base_calls, selected, SHAPE, work / "base")
        cand_values, cand_mask, cand_owner, cand_info = state.read_global_stage(
            CANDIDATE, spec, cand_calls, selected, SHAPE, work / "candidate")
        if not np.array_equal(base_mask, cand_mask):
            raise RuntimeError(f"{stage_name}: observed-call masks differ")
        if not np.array_equal(base_owner, cand_owner):
            raise RuntimeError(f"{stage_name}: cell owner maps differ")
        mask_hash = hashlib.sha256(np.packbits(base_mask, bitorder="little").tobytes()).hexdigest()
        owner_hash = hashlib.sha256(base_owner.astype(">i8", copy=False).tobytes()).hexdigest()
        owner_and_mask_sha[stage_name] = {
            "observed_cells": int(base_mask.sum()),
            "owner_counts_by_rank_call": base_info["owner_cells_by_rank_call"],
            "candidate_observed_cells": int(cand_info["observed_cells"]),
            "observed_mask_sha256_packed_little_bitorder": mask_hash,
            "owner_array_sha256_big_endian_int64": owner_hash,
        }
        for variable, (field, units) in STAGE_FIELDS[stage_name].items():
            idx = field_index(spec.fields, field)
            old = np.asarray(base_values[idx, base_mask], dtype=np.float32)
            new = np.asarray(cand_values[idx, cand_mask], dtype=np.float32)
            old_bits = old.view(np.uint32)
            new_bits = new.view(np.uint32)
            unequal = old_bits != new_bits
            delta = new.astype(np.float64) - old.astype(np.float64)
            abs_delta = np.abs(delta)
            nonzero = old != 0
            rel = abs_delta[nonzero] / np.abs(old[nonzero].astype(np.float64))
            first = None
            if unequal.any():
                # The compact comparison arrays follow increasing full-grid j,k,i indices.
                flat = int(np.flatnonzero(unequal)[0])
                global_index = int(np.flatnonzero(base_mask)[flat])
                plane, i0 = divmod(global_index, SHAPE[1])
                j0, k0 = divmod(plane, SHAPE[2])
                owner_token = int(base_owner[global_index])
                first = {
                    "i_1based": i0 + 1, "j_1based": j0 + 1, "k_1based": k0 + 1,
                    "old_value": float(old[flat]), "candidate_value": float(new[flat]),
                    "signed_delta_candidate_minus_old": float(delta[flat]),
                    "old_bits": f"0x{int(old_bits[flat]):08x}",
                    "candidate_bits": f"0x{int(new_bits[flat]):08x}",
                    "owner_rank": owner_token >> 32, "owner_call_id": owner_token & 0xffffffff,
                }
            metric_rows.append({
                "stage": stage_name, "field": field, "quantity": variable, "units_representation": units,
                "observed_cells": int(base_mask.sum()), "bitwise_equal_cells": int((~unequal).sum()),
                "bitwise_different_cells": int(unequal.sum()), "max_abs_delta": float(abs_delta.max(initial=0.0)),
                "min_signed_delta": float(delta.min(initial=0.0)), "max_signed_delta": float(delta.max(initial=0.0)),
                "max_relative_abs_delta_where_old_nonzero": float(rel.max(initial=0.0)),
                "first_difference_in_j_k_i_order": first,
            })

            for row in selected:
                if row["point_id"] not in {"P01", "P02"}:
                    continue
                i, j, k = int(row["i"]), int(row["j"]), 8
                if not base_mask[state._linear_index(np.array([i]), np.array([j]), np.array([k]), SHAPE)[0]]:
                    raise RuntimeError(f"{stage_name}: selected {row['point_id']} {row['corner']} is outside observed mask")
                cell = int(state._linear_index(np.array([i]), np.array([j]), np.array([k]), SHAPE)[0])
                old_value = np.float32(base_values[idx, cell])
                new_value = np.float32(cand_values[idx, cell])
                corner_rows.append({
                    "stage": stage_name, "point_id": row["point_id"], "corner": row["corner"],
                    "i_1based": i, "j_1based": j, "k_1based": k, "field": field,
                    "units_representation": units, "old_value": float(old_value),
                    "candidate_value": float(new_value), "signed_delta_candidate_minus_old": float(new_value - old_value),
                    "bitwise_equal": bool(old_value.view(np.uint32) == new_value.view(np.uint32)),
                    "old_bits": f32_bits(old_value), "candidate_bits": f32_bits(new_value),
                })
        del base_values, cand_values

    result = {
        "schema": "cp02_first_call_b1_rain_number_prior_vs_corrected_fix_v1",
        "scope": "20-second quick probes; timestep 1 only; first KDM6 global snapshots; identical observed call mask",
        "repository_only_replay": True,
        "interpretation_limit": "Descriptive state comparison only. This does not establish water-budget closure, precipitating-rain causality, or downstream forecast impact.",
        "input_gate": {"only_changed_staged_input": changed_inputs[0],
                       "baseline_wrfinput_sha256": binputs["wrfinput_d01"],
                       "candidate_wrfinput_sha256": cinputs["wrfinput_d01"],
                       "common_executable_sha256": EXPECTED_EXE,
                       "run_seconds": 20, "mpi_ranks": 8,
                       "baseline_run_receipt_sha256": digest(base_receipt_path),
                       "baseline_prepared_case_receipt_sha256": digest(base_case_path),
                       "candidate_run_receipt_sha256": digest(cand_receipt_path),
                       "baseline_scan_sha256": digest(locate_scan(BASE)),
                       "candidate_scan_sha256": digest(locate_scan(CANDIDATE)),
                       "baseline_quick_full_fix_raw_stream_aliases": base_manifest["raw_quick_vs_full_fix_equal_streams"],
                       "baseline_manifest_sha256": digest(BASE_MANIFEST),
                       "full_capture_archive_manifest_sha256": digest(FULL_ARCHIVE_MANIFEST),
                       "candidate_capture_manifest_sha256": digest(CANDIDATE_MANIFEST)},
        "coordinate_and_reader_pins": {"replay_script_sha256": digest(Path(__file__).resolve()),
                                        "reader_sha256": digest(REPO / "tools/cp02_state_path.py"),
                                        "schema_sha256": digest(SCHEMA), "corners_sha256": digest(CORNERS),
                                        "full_manifest_schema_sha256": full_manifest["state_schema"]["sha256"],
                                        "candidate_schema_sha256": candidate_manifest["state_schema_sha256"],
                                        "observed_call_rows": len(base_calls), "selected_points": ids[:2]},
        "coverage": owner_and_mask_sha,
        "global_metrics": metric_rows,
        "selected_p01_p02_k8": corner_rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "first_call_comparison.json"
    json_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    csv_path = OUT / "first_call_comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        rows = []
        for item in metric_rows:
            rows.append({key: value for key, value in item.items() if key != "first_difference_in_j_k_i_order"} |
                        {"record_type": "global_metric", "first_difference_json": json.dumps(item["first_difference_in_j_k_i_order"], separators=(",", ":"))})
        for item in corner_rows:
            rows.append({**item, "record_type": "selected_corner_k8", "first_difference_json": ""})
        columns = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    for path in work.iterdir():
        if path.is_file():
            path.unlink()
        else:
            import shutil
            shutil.rmtree(path)
    work.rmdir()
    print(json.dumps({"json": str(json_path), "json_sha256": digest(json_path),
                      "csv": str(csv_path), "csv_sha256": digest(csv_path),
                      "global_metric_rows": len(metric_rows), "selected_corner_rows": len(corner_rows)}, indent=2))


if __name__ == "__main__":
    main()
