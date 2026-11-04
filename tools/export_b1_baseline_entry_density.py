#!/usr/bin/env python3
"""Export a hash-bound first-call DEN and called mask for cap screening only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import numpy as np

import cp02_state_path as state_path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/evidence/cp02_state_path_20261104/native/state_schema.json"
SHAPE_YXZ = (282, 234, 39)
SCHEMA_SHA256 = "96207bce9553f94f0457f1daaea0afb534fd34a07a107f24973adc87141afced"
QUICK_PROBE_EXE_SHA256 = "6706f6162d37c057b2699afd03ae7c0b4dbf94fe97b925c0369916ba6c708661"
EXPECTED_B1_INPUT_SHA256 = "9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5"
FIELDS = ("TH_PUBLIC_RAW", "QV_PUBLIC_RAW", "QC_PUBLIC_RAW", "QR_PUBLIC_RAW",
          "QI_PUBLIC_RAW", "QS_PUBLIC_RAW", "QG_PUBLIC_RAW", "NN_PUBLIC_RAW",
          "NC_PUBLIC_RAW", "NI_PUBLIC_RAW", "NR_PUBLIC_RAW", "BG_PUBLIC_RAW",
          "DEN_ARGUMENT_RAW", "T_K_DERIVED_TH_TIMES_PII")


class ExportError(ValueError):
    """The baseline ENTRY snapshot cannot support a density cap screen."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def export_capture(capture_root: Path, work_root: Path, output_npz: Path,
                   receipt_path: Path, run_receipt: Path) -> dict[str, Any]:
    for path in (output_npz, receipt_path):
        if os.path.lexists(path):
            raise ExportError(f"OUTPUT_ALREADY_EXISTS:{path}")
    if sha256(SCHEMA) != SCHEMA_SHA256:
        raise ExportError("STATE_SCHEMA_HASH_MISMATCH")
    run = json.loads(run_receipt.read_text(encoding="utf-8"))
    prepared_path = capture_root / "quick_case_receipt.json"
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    if (run.get("status") != "SUCCESS_FORMAT_VALIDATION_ONLY"
            or Path(run.get("cwd", "")).resolve() != capture_root.resolve()
            or run.get("executable_sha256") != QUICK_PROBE_EXE_SHA256
            or run.get("run_seconds") != 20
            or run.get("scanner_status") != "PASS"
            or run.get("rank_success_markers") != 8
            or not run.get("all_89_input_hashes_unchanged")
            or prepared.get("input_files", {}).get("wrfinput_d01") != EXPECTED_B1_INPUT_SHA256
            or prepared.get("exe_sha256") != QUICK_PROBE_EXE_SHA256):
        raise ExportError("BASELINE_QUICK_RUN_RECEIPT_INVALID")
    calls = state_path.read_call_inventory(capture_root, expected_timesteps=(1,))
    schema, specs = state_path.load_schema(SCHEMA)
    if tuple(schema["global_stages"]["entry"]["fields_float32"]) != FIELDS:
        raise ExportError("ENTRY_FIELD_ORDER_MISMATCH")
    values, called, owners, info = state_path.read_global_stage(
        capture_root, specs[1], calls, [], SHAPE_YXZ, work_root
    )
    if not np.any(called):
        raise ExportError("EMPTY_BASELINE_CALLED_MASK")
    field_index = FIELDS.index("DEN_ARGUMENT_RAW")
    density = np.asarray(values[field_index], dtype=np.float32)
    if not np.all(np.isfinite(density[called])) or np.any(density[called] <= 0.0):
        raise ExportError("INVALID_BASELINE_ENTRY_DENSITY")
    # The parser's flat order is j,k,i; convert to the NetCDF input order T,k,j,i.
    density = density.reshape(SHAPE_YXZ).transpose(2, 0, 1)[None, ...].copy()
    called = called.reshape(SHAPE_YXZ).transpose(2, 0, 1)[None, ...].copy()
    if density.shape != (1, 39, 282, 234) or called.dtype != np.bool_:
        raise ExportError("EXPORTED_CAPTURE_SHAPE_OR_MASK_TYPE_MISMATCH")

    output_npz.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{output_npz.name}.", suffix=".tmp", dir=output_npz.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        with temp_path.open("wb") as stream:
            np.savez_compressed(stream, DEN_ENTRY=density, CALLED=called)
        os.link(temp_path, output_npz)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    temp_path.unlink(missing_ok=True)

    capture_files = sorted(
        [*capture_root.glob("state_entry_rank*.bin*"), *capture_root.glob("state_calls_rank*.txt")],
        key=lambda p: p.name,
    )
    receipt = {
        "schema": "b1_baseline_entry_density_screen_v1",
        "status": "PASS_BASELINE_ENTRY_DENSITY_CAP_SCREEN_INPUT_ONLY",
        "capture_root": str(capture_root.resolve()),
        "run_receipt_path": str(run_receipt.resolve()),
        "run_receipt_sha256": sha256(run_receipt),
        "prepared_case_receipt_path": str(prepared_path.resolve()),
        "prepared_case_receipt_sha256": sha256(prepared_path),
        "quick_probe_executable_sha256": QUICK_PROBE_EXE_SHA256,
        "quick_probe_role": "20-second trace probe used only for baseline DEN/called-coordinate cap planning; not candidate performance evidence",
        "state_schema_path": str(SCHEMA.resolve()),
        "state_schema_sha256": sha256(SCHEMA),
        "reader_path": str(Path(state_path.__file__).resolve()),
        "reader_sha256": sha256(Path(state_path.__file__).resolve()),
        "capture_files": [{"path": str(path.resolve()), "bytes": path.stat().st_size,
                           "sha256": sha256(path)} for path in capture_files],
        "entry_capture_info": info,
        "called_cells": int(np.count_nonzero(called)),
        "called_density_min": float(np.min(density[called])),
        "called_density_max": float(np.max(density[called])),
        "output_npz": str(output_npz.resolve()),
        "output_npz_sha256": sha256(output_npz),
        "shape": list(density.shape),
        "arrays": {"DEN_ENTRY": "baseline first-call DEN only for cap-screen planning", "CALLED": "boolean actual-call occupancy mask"},
        "limitations": [
            "This is a baseline density planning proxy, not candidate first-entry evidence.",
            "Do not require baseline ENTRY QRAIN/QNRAIN to equal initial wrfinput values.",
            "A separate candidate first-entry capture must validate actual candidate QRAIN/QNRAIN/DEN and source guards before score evaluation."
        ]
    }
    try:
        with receipt_path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt, indent=2) + "\n")
    except Exception:
        output_npz.unlink(missing_ok=True)
        raise
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-root", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--output-npz", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--run-receipt", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = export_capture(args.capture_root, args.work_root, args.output_npz,
                                args.receipt, args.run_receipt)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
