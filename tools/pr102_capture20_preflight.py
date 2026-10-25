#!/usr/bin/env python3
"""Prepare root-review-only 20-second PR102 baseline/capture runner receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pr86_time_response as runner


ARMS = {"baseline": "STRUCTURED_BASELINE20", "capture": "STRUCTURED_CAPTURE"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha256(path)}


def make_preflight(mode: str, proposal_path: Path, build_path: Path, output_run_root: Path,
                   output_receipt_path: Path, consumer_path: Path | None = None) -> dict:
    if mode not in ARMS:
        raise ValueError("mode must be baseline or capture")
    arm = ARMS[mode]
    if output_run_root.exists():
        raise FileExistsError(f"future run root must be fresh: {output_run_root}")
    if output_receipt_path.exists():
        raise FileExistsError(f"refusing to replace root preflight receipt: {output_receipt_path}")
    if (mode == "capture") != (consumer_path is not None):
        raise ValueError("capture mode requires exactly one archived-consumer receipt")

    prepared = runner.prepare(
        arm, 20, output_run_root, candidate_build_path=build_path,
        wind_structure_input_receipt_path=proposal_path,
        pr102_consumer_receipt_path=consumer_path)
    command = ["python3", str(Path(runner.__file__).resolve()), "--arm", arm,
               "--duration-seconds", "20", "--output", str(output_run_root),
               "--candidate-build", str(build_path),
               "--wind-structure-input-receipt", str(proposal_path)]
    if consumer_path is not None:
        command.extend(("--pr102-consumer-receipt", str(consumer_path)))
    dependencies = [artifact(proposal_path), artifact(build_path)]
    consumer = prepared.get("pr102_native_consumer")
    consumer_detail = None
    if consumer:
        dependencies.append({"path": consumer["path"], "sha256": consumer["sha256"]})
        dependencies.extend(consumer["artifacts"])
        consumer_record = json.loads(Path(consumer["path"]).read_text())
        consumer_detail = {key: consumer_record.get(key) for key in (
            "native_consumer", "archive_member_sha256", "compiler_profile_sha256",
            "candidate_wrfinput_sha256", "dry_mass_check")}
    record = {
        "schema": "pr102_capture20_runner_preflight_v1",
        "status": ("READY_FOR_ROOT_REVIEW_NO_LAUNCH"
                   if prepared["disk_guard"]["status"] == "PASS"
                   else "REJECTED_DISK_GUARD"),
        "launch_authorized": False,
        "mode": mode,
        "arm": arm,
        "duration_seconds": 20,
        "expected_timesteps": 1,
        "runner": artifact(Path(runner.__file__).resolve()),
        "candidate_build": prepared["candidate_build"],
        "candidate_input_binding": prepared["candidate_input_binding"],
        "candidate_wrfinput_sha256": prepared["candidate_wrfinput_sha256"],
        "candidate_wrfbdy_sha256": prepared["candidate_wrfbdy_sha256"],
        "candidate_namelist_sha256": prepared["candidate_namelist_sha256"],
        "source_receipt": prepared["source_receipt"],
        "source_receipt_sha256": prepared["source_receipt_sha256"],
        "launch_environment": prepared["launch_environment"],
        "diagnostic_environment": prepared["diagnostic_environment"],
        "disk_guard": prepared["disk_guard"],
        "consumer": consumer,
        "consumer_check": consumer_detail,
        "evidence_artifacts": dependencies,
        "launch_argv_without_execute": command,
        "future_output_root": str(output_run_root.resolve()),
        "execution_performed": False,
    }
    output_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output_receipt_path.write_text(json.dumps(record, indent=2) + "\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=tuple(ARMS), required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--candidate-build", type=Path, required=True)
    parser.add_argument("--consumer-receipt", type=Path)
    parser.add_argument("--future-output-root", type=Path, required=True)
    parser.add_argument("--output-receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        record = make_preflight(args.mode, args.proposal, args.candidate_build,
                                args.future_output_root, args.output_receipt,
                                args.consumer_receipt)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": record["status"], "launch_authorized": False,
                      "output_receipt": str(args.output_receipt.resolve()),
                      "candidate_wrfinput_sha256": record["candidate_wrfinput_sha256"],
                      "candidate_executable_sha256": record["candidate_build"]["executable_sha256"]}, indent=2))
    return 0 if record["status"] == "READY_FOR_ROOT_REVIEW_NO_LAUNCH" else 2


if __name__ == "__main__":
    raise SystemExit(main())
