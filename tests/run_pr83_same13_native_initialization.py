#!/usr/bin/env python3
"""Apply a same13 input prior once and report initialization and first-step gates separately."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from initialize_native_moments import initialize_same13_copy


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_new(path: Path, record: dict[str, object]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-case", type=Path, required=True)
    parser.add_argument("--real-case", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True,
                        help="fresh evidence root; all model outputs stay below this directory")
    parser.add_argument("--policy", type=Path,
                        default=ROOT / "docs/PR83_NATIVE_MOMENT_POLICY_20261013.json")
    args = parser.parse_args()

    runtime = args.runtime_case.resolve(strict=True)
    real_case = args.real_case.resolve(strict=True)
    executable = args.executable.resolve(strict=True)
    run_root = args.run_dir.absolute()
    if run_root.exists() or run_root.is_symlink():
        raise FileExistsError(f"fresh evidence root required: {run_root}")
    run_root.mkdir(parents=True)

    source_input = real_case / "wrfinput_d01"
    source_hash_before = sha256(source_input)
    candidate_input = run_root / "wrfinput_d01.pr83"
    policy_receipt_path = run_root / "pr83_same13_native_moment_prior.json"
    policy = args.policy.resolve(strict=True)
    policy_receipt = initialize_same13_copy(
        source_input, candidate_input, policy_receipt_path, policy_path=policy
    )
    if sha256(source_input) != source_hash_before:
        raise RuntimeError("source same13 wrfinput changed during prior application")

    native_run: dict[str, object] | None = None
    readback_path: Path | None = None
    native_run_path = run_root / "native"
    if policy_receipt["status"] == "RESEARCH_PRIOR_CREATED":
        command = [
            sys.executable,
            str(ROOT / "tests/run_pr82_same13_native_initialization.py"),
            "--runtime-case", str(runtime),
            "--real-case", str(real_case),
            "--executable", str(executable),
            "--run-dir", str(native_run_path),
            "--initialized-input-receipt", str(policy_receipt_path),
            "--initialized-input-policy", str(policy),
        ]
        run_process = subprocess.run(command, capture_output=True, text=True, check=False)
        native_receipt_path = native_run_path / "pr83_same13_native_initialization.json"
        if native_receipt_path.is_file():
            native_run = json.loads(native_receipt_path.read_text())
        output_path = native_run_path / "wrfout_d01_2026-08-16_13:00:00"
        if output_path.is_file():
            readback_path = run_root / "pr83_same13_native_readback.json"
            checker = ROOT / "tests/pr83_moment_candidate_readback.py"
            check = subprocess.run(
                [sys.executable, str(checker),
                 str(source_input), str(native_run_path / "wrfinput_d01"),
                 str(output_path), str(policy_receipt_path), str(policy), str(readback_path),
                 "--trace-pre", str(native_run_path / "kdm6_first_call_pre.raw")],
                capture_output=True, text=True, check=False,
            )
            readback_result = {
                "checker": str(checker),
                "exit_status": check.returncode,
                "stdout": check.stdout.strip(),
                "stderr": check.stderr.strip(),
                "receipt": str(readback_path) if readback_path.exists() else None,
                "receipt_sha256": sha256(readback_path) if readback_path.is_file() else None,
            }
        else:
            readback_result = {
                "checker": str(ROOT / "tests/pr83_moment_candidate_readback.py"),
                "status": "NOT_RUN_INITIAL_WRFOUT_MISSING",
            }
        if native_run is None:
            native_status = "NATIVE_INITIALIZATION_RECEIPT_MISSING"
        elif native_run.get("initialization_gate") == "PASS_SCOPED_INITIALIZATION_READBACK":
            native_status = "NATIVE_INITIALIZATION_READBACK_PASSED"
        else:
            native_status = "NATIVE_INITIALIZATION_READBACK_FAILED"
        first_step_status = (native_run.get("first_step_gate", "UNASSESSED_NATIVE_RECEIPT_MISSING")
                             if native_run is not None else "UNASSESSED_NATIVE_RECEIPT_MISSING")
        isolation = native_run.get("run_isolation", {}) if native_run is not None else {}
        model_returncode = isolation.get("returncode")
    else:
        run_process = None
        readback_result = {
            "checker": str(ROOT / "tests/pr83_moment_candidate_readback.py"),
            "status": "NOT_RUN_POLICY_REJECTED_BEFORE_NATIVE_LAUNCH",
        }
        native_status = "SKIPPED_SOURCE_CAP_INFEASIBLE"
        first_step_status = "NOT_RUN_POLICY_REJECTED_BEFORE_NATIVE_LAUNCH"
        model_returncode = None

    source_hash_after = sha256(source_input)
    if source_hash_after != source_hash_before:
        raise RuntimeError("source same13 wrfinput changed after native initialization transaction")
    executable_hash = sha256(executable)
    record: dict[str, object] = {
        "schema": "pr83_same13_native_initialization_evidence_v1",
        "artifact_class": "RESEARCH_DIAGNOSTIC",
        "science_authority": "NONE",
        "operational_authority": "NONE",
        "initialization_path": "one pre-run copied-wrfinput transaction before untouched WRF startup",
        "does_not_claim_start_em_source_hook": True,
        "native_run_scope": "same13 cold-start, one rank, one thread; no restart/nest/DFI extension",
        "source_input": str(source_input),
        "source_input_sha256_before": source_hash_before,
        "source_input_sha256_after": source_hash_after,
        "prior_candidate_input": str(candidate_input) if candidate_input.is_file() else None,
        "prior_candidate_input_sha256": sha256(candidate_input) if candidate_input.is_file() else None,
        "policy_receipt": str(policy_receipt_path),
        "policy_receipt_sha256": sha256(policy_receipt_path),
        "policy_sha256": sha256(policy),
        "initializer_sha256": policy_receipt.get("initializer_sha256"),
        "policy_status": policy_receipt["status"],
        "policy_failure": policy_receipt.get("failure"),
        "policy_diagnostics": policy_receipt.get(
            "field_prior_preflight", policy_receipt.get("diagnostics")
        ),
        "policy_evidence_integrity": policy_receipt.get("evidence_integrity"),
        "source_input_unchanged_by_prior": policy_receipt.get("source_input_unchanged"),
        "native_status": native_status,
        "native_runner_returncode": run_process.returncode if run_process else None,
        "native_initialization_gate": (native_run.get("initialization_gate")
                                        if native_run is not None else None),
        "native_model_returncode": model_returncode,
        "first_step_status": first_step_status,
        "wrapper_returncode_scope": (
            "initialization runner and independent input/output readback only; "
            "first-step outcome is reported separately"
        ),
        "native_executable": str(executable),
        "native_executable_sha256": executable_hash,
        "native_run_receipt": (str(native_run_path / "pr83_same13_native_initialization.json")
                               if native_run is not None else None),
        "native_run_receipt_sha256": (
            sha256(native_run_path / "pr83_same13_native_initialization.json")
            if native_run is not None and
            (native_run_path / "pr83_same13_native_initialization.json").is_file() else None
        ),
        "native_launch_attempted": run_process is not None,
        "native_output_directory_created": native_run_path.exists(),
        "native_first_call_trace": (native_run.get("native_trace_outputs", {})
                                    if native_run is not None else {}),
        "independent_readback": readback_result,
        "first_call_post_readback": "unavailable unless candidate supplies both pre and post stages",
    }
    evidence_path = run_root / "pr83_same13_native_initialization_evidence.json"
    write_new(evidence_path, record)
    print(json.dumps({
        "native_status": native_status,
        "native_runner_returncode": run_process.returncode if run_process else None,
        "native_model_returncode": model_returncode,
        "first_step_status": first_step_status,
        "policy_status": policy_receipt["status"],
        "policy_receipt": str(policy_receipt_path),
        "evidence": str(evidence_path),
    }, sort_keys=True))
    if policy_receipt["status"] != "RESEARCH_PRIOR_CREATED":
        return 2
    if run_process is None or run_process.returncode != 0:
        return 1
    return 0 if readback_result.get("exit_status") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
