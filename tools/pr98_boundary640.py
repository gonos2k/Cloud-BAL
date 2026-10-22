#!/usr/bin/env python3
"""Preflight or launch the frozen PR96-C1 640-second boundary cases."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ARMS = ("OFF", "HYDRO", "COUPLED")
DURATION_SECONDS = 640
RUNNER_POST_KDM6_SNAPSHOT_SECONDS = (20, 60, 300, 320, 480, 500, 600, 640)
EXPECTED_EXE_SHA256 = "a714f00d3f81c0b47d94aef815f1f765ae48842e9de629cb869323ccfc22a96d"
FROZEN_RUNNER = Path("/var/tmp/pr96_runner_frozen_20261021/tools/pr86_time_response.py")
EXPECTED_RUNNER_SHA256 = "80803b6b3e8591053d0524ed9e5b0110dfd7cbf1d105d2e40029addb5f5a55c4"
BUILD_RECEIPT = Path("/var/tmp/pr96_native_build_c1_20261021/pr87_native_overlay_build.json")
HYDRO_RECEIPT = Path(__file__).resolve().parents[1] / (
    "docs/evidence/pr94_hydro_control_20261021/current_generation_final2/"
    "hydro_native_input_receipt.json"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command_for(arm: str, output: Path, execute: bool) -> list[str]:
    command = [
        sys.executable, str(FROZEN_RUNNER), "--arm", arm,
        "--output", str(output), "--duration-seconds", str(DURATION_SECONDS),
        "--candidate-build", str(BUILD_RECEIPT),
    ]
    if arm == "HYDRO":
        command.extend(("--hydro-input-receipt", str(HYDRO_RECEIPT)))
    if execute:
        command.append("--execute")
    return command


def invoke(arm: str, output: Path, execute: bool) -> dict:
    completed = subprocess.run(
        command_for(arm, output, execute), cwd=FROZEN_RUNNER.parents[1],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    log_path = output.parent / f"{arm}_{'launch' if execute else 'preflight'}.log"
    log_path.write_text(completed.stdout)
    receipt_path = output / ("receipt.json" if execute else "preflight.json")
    result = {
        "arm": arm,
        "returncode": completed.returncode,
        "output": str(output),
        "log": str(log_path),
        "receipt": str(receipt_path) if receipt_path.exists() else None,
    }
    if receipt_path.exists():
        result["runner_result"] = json.loads(receipt_path.read_text())
        if execute:
            receipt = result["runner_result"]
            closed = receipt.get("status") in ("COMPLETE", "INCOMPLETE")
            unchanged = (
                closed
                and receipt.get("changed_staged_inputs") == []
                and receipt.get("changed_original_inputs") == []
                and receipt.get("candidate_build_unchanged") is True
                and receipt.get("candidate_input_unchanged") is True
                and receipt.get("executed_executable_sha256") == EXPECTED_EXE_SHA256
                and receipt.get("expected_executed_executable_sha256") == EXPECTED_EXE_SHA256
            )
            result["closed_receipt_input_integrity"] = "PASS" if unchanged else "FAIL_OR_UNAVAILABLE"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="launch all three frozen cases")
    args = parser.parse_args()

    output_root = args.output_root.resolve()
    if not FROZEN_RUNNER.is_file() or sha256(FROZEN_RUNNER) != EXPECTED_RUNNER_SHA256:
        raise SystemExit("frozen PR96 runner is absent or its SHA-256 changed")
    if not BUILD_RECEIPT.is_file() or not HYDRO_RECEIPT.is_file():
        raise SystemExit("candidate build or source-bound HYDRO input receipt is absent")
    build = json.loads(BUILD_RECEIPT.read_text())
    if build.get("executable_sha256") != EXPECTED_EXE_SHA256:
        raise SystemExit("candidate build receipt does not bind the frozen C1 executable")
    if output_root.exists():
        raise SystemExit(f"output root already exists: {output_root}")
    output_root.mkdir(parents=True)
    outputs = {arm: output_root / f"{arm}_640s_c1" for arm in ARMS}
    if any(path.exists() for path in outputs.values()):
        raise SystemExit("an arm output path already exists")

    plan = {
        "schema": "pr98_c1_boundary640_launch_v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "execute" if args.execute else "preflight",
        "duration_seconds": DURATION_SECONDS,
        "expected_steps": DURATION_SECONDS // 20,
        "requested_review_checkpoints_seconds": [600, 620, 640],
        "runner_post_kdm6_snapshots_seconds": list(RUNNER_POST_KDM6_SNAPSHOT_SECONDS),
        "mandatory_final_runtime_seconds": 640,
        "stage_trace_includes_620s_record": True,
        "frozen_inputs_requested": True,
        "expected_executable_sha256": EXPECTED_EXE_SHA256,
        "runner_path": str(FROZEN_RUNNER),
        "runner_sha256": EXPECTED_RUNNER_SHA256,
        "build_receipt_sha256": sha256(BUILD_RECEIPT),
        "hydro_input_receipt_sha256": sha256(HYDRO_RECEIPT),
        "arms": {arm: {"output": str(path), "command": command_for(arm, path, args.execute)}
                 for arm, path in outputs.items()},
    }
    plan_path = output_root / "launch_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        pending = {pool.submit(invoke, arm, path, args.execute): arm
                   for arm, path in outputs.items()}
        for future in concurrent.futures.as_completed(pending):
            arm = pending[future]
            results[arm] = future.result()
    summary = {"plan": str(plan_path), "results": results}
    (output_root / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if all(row["returncode"] == 0 for row in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
