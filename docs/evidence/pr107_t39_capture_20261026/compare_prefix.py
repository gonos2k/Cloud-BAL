#!/usr/bin/env python3
"""Compare receipt-bound HYDRO diagnostics through the shared 600-second prefix."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

import native_kdm6_trace
import pr94_longrun_audit
import pr102_capture_noninterference as capture


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_receipt(root: Path) -> tuple[dict, Path]:
    path = root / "receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if (receipt.get("arm") != "HYDRO" or receipt.get("status") not in {"INCOMPLETE", "COMPLETE"} or
            receipt.get("candidate_input_unchanged") is not True or
            receipt.get("candidate_build_unchanged") is not True or
            receipt.get("changed_original_inputs") or receipt.get("changed_staged_inputs") or
            receipt.get("processing_errors")):
        raise ValueError(f"HYDRO receipt is not closed with unchanged inputs/build: {path}")
    return receipt, path


def verify_common_inputs(old: dict, diagnostic: dict, diagnostic_root: Path) -> dict:
    for name in ("candidate_wrfinput_sha256", "candidate_wrfbdy_sha256"):
        if old.get(name) != diagnostic.get(name):
            raise ValueError(f"HYDRO {name} differs between runs")
    binding = diagnostic.get("candidate_build")
    if not isinstance(binding, dict):
        raise ValueError("diagnostic receipt lacks its candidate build binding")
    build_path = Path(binding["receipt_path"])
    if not build_path.is_file() or sha256(build_path) != binding.get("receipt_sha256"):
        raise ValueError("diagnostic overlay receipt is missing or changed")
    build = json.loads(build_path.read_text(encoding="utf-8"))
    if (build.get("executable_sha256") != diagnostic.get("executed_executable_sha256") or
            build.get("base_c2_executable_sha256") != old.get("executed_executable_sha256") or
            build.get("changed_archive_members") != ["module_em.o"] or
            build.get("status") != "PASS_OVERLAY_BUILD" or
            build.get("full_clean_build") is not False):
        raise ValueError("diagnostic build is not a module_em-only overlay on the old C2 executable")
    proof_row = build.get("source_transform_proof", {})
    proof_path = Path(proof_row.get("path", ""))
    if (not proof_path.is_file() or sha256(proof_path) != proof_row.get("sha256") or
            proof_row.get("math_source_unchanged") is not True):
        raise ValueError("diagnostic source proof is missing, changed, or does not certify unchanged math")
    executable = Path(build.get("executable_path", ""))
    if not executable.is_file() or sha256(executable) != build.get("executable_sha256"):
        raise ValueError("diagnostic build executable is missing or changed")
    staged_executable = diagnostic_root / "run" / "wrf.exe"
    if not staged_executable.is_file() or sha256(staged_executable) != build["executable_sha256"]:
        raise ValueError("run-staged diagnostic executable differs from its build receipt")
    return {"wrfinput_sha256": diagnostic["candidate_wrfinput_sha256"],
            "wrfbdy_sha256": diagnostic["candidate_wrfbdy_sha256"],
            "base_c2_executable_sha256": old["executed_executable_sha256"],
            "diagnostic_executable_sha256": build["executable_sha256"],
            "diagnostic_executable_path": str(executable),
            "source_proof_path": str(proof_path),
            "source_proof_sha256": proof_row["sha256"],
            "diagnostic_build_receipt": {"path": str(build_path), "sha256": sha256(build_path)}}


def compare_t1_raw(old_root: Path, old: dict, diagnostic_root: Path,
                   diagnostic: dict) -> dict:
    fields = {}
    t1_paths = []
    with tempfile.TemporaryDirectory(prefix="pr107_t39_t1_prefix_") as temp_dir:
        temp = Path(temp_dir)
        for capture_name, expected_stage in (("pre", 1), ("post", 2)):
            name = f"kdm6_first_call_{capture_name}.raw"
            decoded = []
            artifact_rows = []
            for label, root, receipt in (("old", old_root, old),
                                         ("diagnostic", diagnostic_root, diagnostic)):
                compressed = capture.verify_output(root, receipt, name, compressed=True)
                t1_paths.append((compressed, sha256(compressed)))
                raw = temp / f"{label}_{name}"
                with gzip.open(compressed, "rb") as src, raw.open("wb") as dst:
                    for block in iter(lambda: src.read(1 << 20), b""):
                        dst.write(block)
                decoded.append(native_kdm6_trace.read_dump(raw))
                artifact_rows.append({"path": str(compressed), "sha256": sha256(compressed)})
            before, after = decoded
            identity = ("stage", "itimestep", "bounds", "params")
            if tuple(before[key] for key in identity) != tuple(after[key] for key in identity):
                raise ValueError(f"T1 {capture_name} capture headers differ")
            if before["stage"] != expected_stage or before["itimestep"] != 1:
                raise ValueError(f"T1 {capture_name} artifact is not the expected first-call stage")
            field_rows = {}
            for field in native_kdm6_trace.FIELDS_3D + native_kdm6_trace.FIELDS_2D:
                left, right = before["fields"][field], after["fields"][field]
                equal = (left.shape == right.shape and left.dtype == right.dtype and
                         left.tobytes() == right.tobytes())
                field_rows[field] = {"equal": equal, "shape": list(left.shape),
                                     "dtype": str(left.dtype),
                                     "sha256": hashlib.sha256(left.tobytes()).hexdigest()}
                if not equal:
                    raise ValueError(f"T1 {capture_name} field differs: {field}")
            fields[capture_name] = {"field_count": len(field_rows), "fields": field_rows,
                                   "artifacts": artifact_rows}
    for path, expected_hash in t1_paths:
        if sha256(path) != expected_hash:
            raise ValueError(f"T1 capture changed during read: {path}")
    return {"status": "PASS", "timestep": 1, "captures": fields,
            "method": "Existing native_kdm6_trace.read_dump; exact field bytes for PRE and POST."}


def compare(old_root: Path, diagnostic_root: Path) -> dict:
    old_root, diagnostic_root = old_root.resolve(strict=True), diagnostic_root.resolve(strict=True)
    old, old_receipt_path = read_receipt(old_root)
    diagnostic, diagnostic_receipt_path = read_receipt(diagnostic_root)
    inputs = verify_common_inputs(old, diagnostic, diagnostic_root)
    old_receipt_hash = sha256(old_receipt_path)
    diagnostic_receipt_hash = sha256(diagnostic_receipt_path)
    trace = pr94_longrun_audit.compare_first_600_seconds(
        old_root, old, diagnostic_root, diagnostic, "HYDRO")
    if trace["status"] != "PASS" or trace.get("common_prefix_steps") != 30:
        raise ValueError(f"600-second raw stage-trace prefix did not pass: {trace}")
    history = pr94_longrun_audit.compare_closed_histories(
        old_root, old, diagnostic_root, diagnostic, "HYDRO")
    if history["status"] != "PASS" or history.get("compared_frames") != 11:
        raise ValueError(f"0..600-second native history prefix did not pass: {history}")
    t1 = compare_t1_raw(old_root, old, diagnostic_root, diagnostic)
    if sha256(old_receipt_path) != old_receipt_hash or sha256(diagnostic_receipt_path) != diagnostic_receipt_hash:
        raise ValueError("a HYDRO receipt changed during prefix comparison")
    build_receipt = inputs["diagnostic_build_receipt"]
    if sha256(Path(build_receipt["path"])) != build_receipt["sha256"]:
        raise ValueError("diagnostic build receipt changed during prefix comparison")
    if (sha256(Path(inputs["diagnostic_executable_path"])) != inputs["diagnostic_executable_sha256"] or
            sha256(Path(inputs["source_proof_path"])) != inputs["source_proof_sha256"]):
        raise ValueError("diagnostic executable or source proof changed during prefix comparison")
    return {
        "schema": "pr107_hydro_diagnostic_prefix_comparison_v1",
        "status": "PASS",
        "scope": "HYDRO only; shared 0..600 s prefix, exact POST_KDM6 trace state bytes, ten native history fields at 11 minute frames, and T1 PRE/POST captures.",
        "old_receipt": {"path": str(old_receipt_path), "sha256": old_receipt_hash},
        "diagnostic_receipt": {"path": str(diagnostic_receipt_path),
                               "sha256": diagnostic_receipt_hash},
        "common_inputs_and_executable_lineage": inputs,
        "raw_stage_trace": trace,
        "history": history,
        "t1_pre_post": t1,
        "limitations": [
            "This is output noninterference evidence for the compared HYDRO prefix only.",
            "It does not classify or resolve the T39 grouped failure, and it is not physical validation.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-hydro", type=Path, required=True,
                        help="closed PR104 HYDRO run root")
    parser.add_argument("--diagnostic-hydro", type=Path, required=True,
                        help="closed PR107 T39 HYDRO run root")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.old_hydro, args.diagnostic_hydro)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "output": str(output),
                      "trace_records": result["raw_stage_trace"]["compared_state_records"],
                      "history_frames": result["history"]["compared_frames"],
                      "t1_fields_per_stage": len(result["t1_pre_post"]["captures"]["pre"]["fields"])},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
