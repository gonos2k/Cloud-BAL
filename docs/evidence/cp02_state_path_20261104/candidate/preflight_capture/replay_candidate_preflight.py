#!/usr/bin/env python3
"""Replay the archived B1 candidate first-call ENTRY/PRE_UPDATE source guards."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

import numpy as np
from netCDF4 import Dataset

CASE_ID = "B1_RAIN_NUMBER_PRIOR"
POLICY_SHA256 = "25387970de9685e3024af7983d47650ab6b6068188f765df58243d6ebefa7601"
INPUT_SHA256 = "ad030e8bbfca319c4594dcfa5b0656b9bc387d9fcbe23372fd6ed8808aaf0f21"
PREVIOUS_PREFLIGHT_SHA256 = "4d51c8bf0214dff43a0e1862ab25eebd1bf552f51556a5ae44d57f1657e6949b"
FIX_SOURCE_SHA256 = "0b468be19f7dd66ad2f6e65a53b42f10391a4565831a96c80dddddf21934cf79"
EXPECTED_SHAPE_YXZ = (282, 234, 39)
EXPECTED_SHAPE_TZYX = (1, 39, 282, 234)
EXPECTED_FIELDS_ENTRY = (
    "TH_PUBLIC_RAW", "QV_PUBLIC_RAW", "QC_PUBLIC_RAW", "QR_PUBLIC_RAW",
    "QI_PUBLIC_RAW", "QS_PUBLIC_RAW", "QG_PUBLIC_RAW", "NN_PUBLIC_RAW",
    "NC_PUBLIC_RAW", "NI_PUBLIC_RAW", "NR_PUBLIC_RAW", "BG_PUBLIC_RAW",
    "DEN_ARGUMENT_RAW", "T_K_DERIVED_TH_TIMES_PII",
)
EXPECTED_FIELDS_PRE = (
    "QV_INTERNAL_RAW", "T_K_INTERNAL", "DEN_ARGUMENT_RAW", "QC_INTERNAL",
    "QI_INTERNAL", "QR_INTERNAL", "QS_INTERNAL", "QG_INTERNAL", "NC_INTERNAL",
    "NI_INTERNAL", "NN_INTERNAL", "NR_INTERNAL", "NS_INTERNAL", "NG_INTERNAL",
    "BG_INTERNAL",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def ordered(values: np.ndarray) -> np.ndarray:
    return values.reshape(EXPECTED_SHAPE_YXZ).transpose(2, 0, 1)[None, ...].copy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--candidate-input", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--capture-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    capture = args.capture_dir.resolve()
    repo = args.repo_root.resolve()
    out = args.output.resolve()
    if out.exists():
        parser.error(f"refusing to overwrite replay receipt: {out}")
    manifest_path = capture / "capture_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS" or manifest.get("case_id") != CASE_ID:
        parser.error("capture manifest case/status mismatch")
    if sha256(args.policy) != POLICY_SHA256 or manifest.get("policy_sha256") != POLICY_SHA256:
        parser.error("frozen policy hash mismatch")
    if sha256(args.candidate_input) != INPUT_SHA256 or manifest.get("candidate_input_sha256") != INPUT_SHA256:
        parser.error("frozen candidate input hash mismatch")
    source = repo / "docs/evidence/cp02_state_path_20261104/lineage/sourcepins/module_mp_kdm6_FIX.f90"
    if sha256(source) != FIX_SOURCE_SHA256:
        parser.error("retained FIX source hash mismatch")

    # Verify copied support files and every compressed/raw stream pair.
    for item in manifest["support_files"]:
        path = capture / item["name"]
        if path.stat().st_size != item["size_bytes"] or sha256(path) != item["sha256"]:
            parser.error(f"support-file hash/size mismatch: {path.name}")
    with tempfile.TemporaryDirectory(prefix="b1_preflight_replay_") as scratch_name:
        scratch = Path(scratch_name)
        for item in manifest["state_streams"]:
            compressed = capture / item["name"]
            if compressed.stat().st_size != item["gzip_size_bytes"] or sha256(compressed) != item["gzip_sha256"]:
                parser.error(f"compressed-stream hash/size mismatch: {compressed.name}")
            raw_path = scratch / item["name"][:-3]
            with gzip.open(compressed, "rb") as zipped, raw_path.open("xb") as raw:
                shutil.copyfileobj(zipped, raw)
            if raw_path.stat().st_size != item["source_size_bytes"] or sha256(raw_path) != item["source_sha256"]:
                parser.error(f"decompressed-stream hash/size mismatch: {raw_path.name}")
        for rank in range(8):
            shutil.copy2(capture / f"state_calls_rank{rank}.txt", scratch)

        sys.path.insert(0, str(repo / "tools"))
        import cp02_state_path as state_path
        from initialize_b1_rain_psd_prior import validate_candidate_entry

        schema_path = capture / "state_schema.json"
        schema, specs = state_path.load_schema(schema_path)
        if tuple(schema["global_stages"]["entry"]["fields_float32"]) != EXPECTED_FIELDS_ENTRY:
            parser.error("ENTRY schema field order mismatch")
        if tuple(schema["global_stages"]["pre_update"]["fields_float32"]) != EXPECTED_FIELDS_PRE:
            parser.error("PRE_UPDATE schema field order mismatch")
        calls = state_path.read_call_inventory(scratch, expected_timesteps=(1,))
        entry, called, _, entry_info = state_path.read_global_stage(
            scratch, specs[1], calls, [], EXPECTED_SHAPE_YXZ, scratch / "parse_entry"
        )
        pre, called_pre, _, pre_info = state_path.read_global_stage(
            scratch, specs[2], calls, [], EXPECTED_SHAPE_YXZ, scratch / "parse_pre"
        )
        if not np.array_equal(called, called_pre) or not np.any(called):
            parser.error("ENTRY/PRE_UPDATE called-domain mismatch or empty mask")

        entry_fields = schema["global_stages"]["entry"]["fields_float32"]
        pre_fields = schema["global_stages"]["pre_update"]["fields_float32"]
        field_entry = lambda name: np.asarray(entry[entry_fields.index(name)], dtype=np.float32)
        field_pre = lambda name: np.asarray(pre[pre_fields.index(name)], dtype=np.float32)
        qr = field_entry("QR_PUBLIC_RAW")
        nr = field_entry("NR_PUBLIC_RAW")
        den = field_entry("DEN_ARGUMENT_RAW")
        qr_pre = field_pre("QR_INTERNAL")
        nr_pre = field_pre("NR_INTERNAL")
        den_pre = field_pre("DEN_ARGUMENT_RAW")
        nr_internal_raw = np.multiply(nr, den, dtype=np.float32)
        qr_clipped = np.maximum(qr, np.float32(0.0))
        nr_clipped = np.maximum(nr_internal_raw, np.float32(0.0))
        qr_mismatch = called & (qr_pre != qr_clipped)
        nr_mismatch = called & (nr_pre != nr_clipped)
        den_mismatch = called & (den_pre != den)
        if np.any(qr_mismatch) or np.any(nr_mismatch) or np.any(den_mismatch):
            parser.error("source-ordered ENTRY→PRE_UPDATE clip/density identity failed")
        if not all(np.all(np.isfinite(field[called])) for field in (qr, nr, den, qr_pre, nr_pre, den_pre)):
            parser.error("nonfinite actual called-cell field")
        if np.any(den[called] <= 0.0) or np.any(den_pre[called] <= 0.0):
            parser.error("nonpositive density in actual called cells")

        with Dataset(args.candidate_input, "r") as dataset:
            variable = dataset.variables["QRAIN"]
            variable.set_auto_maskandscale(False)
            initial_qrain = np.asarray(variable[:])
        raw_candidate_entry = validate_candidate_entry(
            initial_qrain, ordered(qr), ordered(nr), ordered(den),
            ordered(called.reshape(EXPECTED_SHAPE_YXZ).astype(np.bool_)),
        )
        source_active = called & (qr_pre >= np.float32(1.0e-9)) & (nr_pre >= np.float32(1.0e-2))
        nrmax_exceed = called & (nr_pre > np.float32(5.0e7))
        if not np.any(source_active) or np.any(nrmax_exceed):
            parser.error("actual PRE_UPDATE source-active/cap gate failed")

        pidnr = np.float32(math.pi * 1000.0 / 6.0 * math.gamma(5.0) / math.gamma(2.0))
        numerator = np.multiply(pidnr, nr_pre, dtype=np.float32)
        denominator = np.multiply(den_pre, qr_pre, dtype=np.float32)
        ratio = np.divide(numerator, denominator, dtype=np.float32)
        lam = np.full(qr.shape, np.nan, dtype=np.float64)
        lam[source_active] = np.exp(
            np.multiply(np.log(ratio[source_active], dtype=np.float32), np.float32(1.0 / 3.0), dtype=np.float32),
            dtype=np.float32,
        ).astype(np.float64)
        active_lam = lam[source_active]
        if not np.all(np.isfinite(active_lam)):
            parser.error("nonfinite source-active lambda reconstruction")

        old_preflight = json.loads((capture / "candidate_entry_preflight.json").read_text(encoding="utf-8"))
        replay_metrics = {
            "entry_called_cells": int(np.count_nonzero(called)),
            "raw_entry_qrain_negative_cells": int(np.count_nonzero(called & (qr < 0.0))),
            "raw_entry_qnrain_negative_cells": int(np.count_nonzero(called & (nr < 0.0))),
            "qr_clip_numeric_mismatch_cells": int(np.count_nonzero(qr_mismatch)),
            "nr_clip_numeric_mismatch_cells": int(np.count_nonzero(nr_mismatch)),
            "den_numeric_mismatch_cells": int(np.count_nonzero(den_mismatch)),
            "pre_update_source_active_cells": int(np.count_nonzero(source_active)),
            "pre_update_nrs_max": float(np.max(nr_pre[called])),
            "pre_update_nrmax_exceeding_cells": int(np.count_nonzero(nrmax_exceed)),
            "lambda_reconstruction_min_m-1": float(np.min(active_lam)),
            "lambda_reconstruction_median_m-1": float(np.median(active_lam)),
            "lambda_reconstruction_max_m-1": float(np.max(active_lam)),
            "lambda_below_source_min_cells": int(np.count_nonzero(active_lam < 961.0)),
            "lambda_above_source_max_cells": int(np.count_nonzero(active_lam > 35000.0)),
        }
        frozen_metrics = old_preflight["actual_pre_update_state"]
        lam_frozen = frozen_metrics["lambda_float32_formula_reconstruction_m-1"]
        if (replay_metrics["entry_called_cells"] != old_preflight["entry_called_cells"]
                or replay_metrics["raw_entry_qrain_negative_cells"] != old_preflight["raw_entry_called_qrain"]["negative_count"]
                or replay_metrics["raw_entry_qnrain_negative_cells"] != old_preflight["raw_entry_called_qnrain"]["negative_count"]
                or replay_metrics["pre_update_source_active_cells"] != frozen_metrics["source_active_cells_qrs_ge_qcrmin_nrs_ge_nrmin"]
                or replay_metrics["pre_update_nrs_max"] != frozen_metrics["nrs_internal_max"]
                or replay_metrics["pre_update_nrmax_exceeding_cells"] != frozen_metrics["nrmax_exceeding_cells"]
                or replay_metrics["lambda_reconstruction_min_m-1"] != lam_frozen["min"]
                or replay_metrics["lambda_reconstruction_median_m-1"] != lam_frozen["median"]
                or replay_metrics["lambda_reconstruction_max_m-1"] != lam_frozen["max"]):
            parser.error("independent replay metrics differ from frozen first-call preflight")

        reader_path = Path(state_path.__file__).resolve()
        helper_path = repo / "tools/initialize_b1_rain_psd_prior.py"
        result = {
            "schema": "b1_candidate_preflight_replay_v1",
            "status": "PASS",
            "case_id": CASE_ID,
            "capture_manifest_path": str(manifest_path),
            "capture_manifest_sha256": sha256(manifest_path),
            "previous_frozen_preflight_sha256": PREVIOUS_PREFLIGHT_SHA256,
            "previous_frozen_preflight_copy_sha256": sha256(capture / "candidate_entry_preflight.json"),
            "policy_sha256": sha256(args.policy),
            "candidate_input_sha256": sha256(args.candidate_input),
            "fixed_forecast_executable_sha256": manifest["fixed_forecast_executable_sha256"],
            "probe_executable_sha256": manifest["probe_executable_sha256"],
            "state_schema_sha256": sha256(schema_path),
            "current_state_reader_path": str(reader_path),
            "current_state_reader_sha256": sha256(reader_path),
            "current_initializer_path": str(helper_path.resolve()),
            "current_initializer_sha256": sha256(helper_path),
            "retained_fix_source_path": str(source.resolve()),
            "retained_fix_source_sha256": sha256(source),
            "source_guards": {
                "qrain_clip_source_line_718": "qrs=max(qrs,0)",
                "nrs_clip_source_line_722": "nrs=max(nrs,0)",
                "psd_activation_source_lines_1364_1366": "qrs>=qcrmin and nrs>=nrmin before lambda reconstruction",
                "lambda_bound_clamps_source_lines_1368_1375": "clamp lambda to [lamdarmin,lamdarmax] and recompute nrs",
                "entry_to_pre_update_numeric_mismatches": replay_metrics["qr_clip_numeric_mismatch_cells"] + replay_metrics["nr_clip_numeric_mismatch_cells"] + replay_metrics["den_numeric_mismatch_cells"],
            },
            "metrics": replay_metrics,
            "raw_entry_validator_metrics": raw_candidate_entry,
            "entry_reader_info": entry_info,
            "pre_update_reader_info": pre_info,
            "limitations": [
                "The saved lambda values are float32 equation reconstructions from PRE_UPDATE operands, not a direct trace of the local lambda variable.",
                "This replay validates only the candidate first-call source state; it is not a forecast score or scientific admission result.",
                "The archived 20-second executable is the instrumented probe; the later six-hour forecast uses the distinct fixed executable hash recorded above.",
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"status": result["status"], "metrics": replay_metrics,
                          "current_reader_sha256": result["current_state_reader_sha256"],
                          "output_path": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
