#!/usr/bin/env python3
"""Prepare a read-only, receipt-bound PR101 PROJECTED launch preflight."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pr86_time_response as response


ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee")
CONTROL_ROOT = ROOT / "pr99_c2_matched640_20261022"
PROJECTED_RUN = ROOT / "pr99_native_uv20_capture_20261022/run"
PROJECTED_INPUT_RECEIPT = Path("/var/tmp/pr99_native_projection_v4_20261022/wrfinput_d01.proposal.json")
BUILD_RECEIPT = Path("/var/tmp/pr99_bulk_candidate_native_c2_20261022/pr87_native_overlay_build.json")
FROZEN_RUNNER = Path("/var/tmp/pr101_runner_frozen_v2_20261023/tools/pr86_time_response.py")
RUN_ROOT = ROOT / "pr101_projected_c2_640_20261023"
EVIDENCE = Path(__file__).resolve().parents[1] / "docs/evidence/pr101_projected_c2_20261023"

PINS = {
    "control_runner_sha256": "80803b6b3e8591053d0524ed9e5b0110dfd7cbf1d105d2e40029addb5f5a55c4",
    "build_receipt_sha256": "9c4802e12ea1d6a8f3c8b5ef1a5ff72116e5fbdbf9f6c78e906935622d45dafb",
    "executable_sha256": "387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a",
    "projected_input_sha256": "10aff32bf15887a43141efbb1b14945234e8bbce741a89904d328fb3b1d75cb3",
    "projected_run_receipt_sha256": "f734125bb30555c30cf6815ab8b61a58d5cb173605c13f4f6ff7ce9d326a90a1",
    "boundary_sha256": "885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7",
    "namelist_sha256": "58c194b8846d25a6c7cbfedac1477fbf65fcc1a12705c8cb11851096ee7d2fc8",
    "source_receipt_sha256": "8dc7aa4c8b1cdffc72ab29da5a8db255ee96a271bb452fb5bd73a1e62f32d675",
    "native_proposal_sha256": "a6fdd4907228b6bcd95d2eba3e61539adcedf69c0154c23a9e1a2edeb6c6b5d0",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    if RUN_ROOT.exists():
        raise FileExistsError(f"reserved run root already exists: {RUN_ROOT}")

    # Run the runner's source, input, executable, namelist, and disk guards without staging or launching.
    prepared = response.prepare(
        "PROJECTED", 640, RUN_ROOT,
        candidate_build_path=BUILD_RECEIPT,
        native_input_receipt_path=PROJECTED_INPUT_RECEIPT,
    )
    assert sha256(FROZEN_RUNNER) == "087f9f3a9f80f5679db7c228d99dde269200028d823553e0a2045a855cbba439"
    assert sha256(Path(__file__).resolve().parents[1] / "tools/pr86_time_response.py") == sha256(FROZEN_RUNNER)
    assert sha256(BUILD_RECEIPT) == PINS["build_receipt_sha256"]
    assert sha256(Path(prepared["candidate_build"]["executable_path"])) == PINS["executable_sha256"]
    assert prepared["candidate_build"]["executable_sha256"] == PINS["executable_sha256"]
    assert prepared["candidate_wrfinput_sha256"] == PINS["projected_input_sha256"]
    assert prepared["candidate_wrfbdy_sha256"] == PINS["boundary_sha256"]
    assert prepared["candidate_namelist_sha256"] == PINS["namelist_sha256"]
    assert prepared["source_receipt_sha256"] == PINS["source_receipt_sha256"]
    assert sha256(PROJECTED_INPUT_RECEIPT) == PINS["native_proposal_sha256"]
    assert prepared["candidate_input_binding"]["receipt_sha256"] == PINS["native_proposal_sha256"]
    assert prepared["template_arm"] == "COUPLED" and prepared["arm"] == "PROJECTED"
    assert prepared["expected_timesteps"] == 32
    assert prepared["disk_guard"]["status"] == "PASS"

    controls = {}
    for arm in ("OFF", "HYDRO", "COUPLED"):
        receipt_path = CONTROL_ROOT / arm / "receipt.json"
        receipt = read_json(receipt_path)
        assert receipt["status"] == "COMPLETE" and receipt["final_completed_step"] == 32
        assert receipt["executed_executable_sha256"] == PINS["executable_sha256"]
        assert receipt["candidate_namelist_sha256"] == PINS["namelist_sha256"]
        assert receipt["candidate_wrfbdy_sha256"] == PINS["boundary_sha256"]
        assert receipt["launch_runner_source_sha256"] == PINS["control_runner_sha256"]
        controls[arm] = {
            "receipt_path": str(receipt_path), "receipt_sha256": sha256(receipt_path),
            "preflight_sha256": sha256(CONTROL_ROOT / arm / "preflight.json"),
            "status": receipt["status"], "completed_steps": receipt["final_completed_step"],
            "candidate_wrfinput_sha256": receipt["candidate_wrfinput_sha256"],
            "candidate_wrfbdy_sha256": receipt["candidate_wrfbdy_sha256"],
            "candidate_namelist_sha256": receipt["candidate_namelist_sha256"],
            "changed_staged_inputs": receipt["changed_staged_inputs"],
            "changed_original_inputs": receipt["changed_original_inputs"],
        }
    capture_receipt_path = PROJECTED_RUN / "receipt.json"
    capture_receipt = read_json(capture_receipt_path)
    assert sha256(capture_receipt_path) == PINS["projected_run_receipt_sha256"]
    assert capture_receipt["status"] == "COMPLETE" and capture_receipt["final_completed_step"] == 1
    assert capture_receipt["candidate_wrfinput_sha256"] == PINS["projected_input_sha256"]

    runner_path = FROZEN_RUNNER
    argv = [sys.executable, str(runner_path), "--arm", "PROJECTED", "--duration-seconds", "640",
            "--output", str(RUN_ROOT), "--candidate-build", str(BUILD_RECEIPT),
            "--native-input-receipt", str(PROJECTED_INPUT_RECEIPT), "--execute"]
    record = {
        "schema": "pr101_projected_c2_preflight_v1",
        "status": "READY_FOR_ROOT_REVIEW_NO_LAUNCH",
        "launch_authorized": False,
        "duration_seconds": 640,
        "expected_timesteps": 32,
        "run_root": str(RUN_ROOT),
        "runner_path": str(runner_path), "runner_sha256": sha256(runner_path),
        "proposed_argv": argv,
        "cwd": "runner stages run in <run_root>/run and invokes ./wrf.exe there",
        "launch_environment": prepared["launch_environment"],
        "source_receipt": prepared["source_receipt"],
        "source_receipt_sha256": prepared["source_receipt_sha256"],
        "template_arm": prepared["template_arm"],
        "candidate_build": prepared["candidate_build"],
        "candidate_input_binding": prepared["candidate_input_binding"],
        "candidate_wrfinput_sha256": prepared["candidate_wrfinput_sha256"],
        "candidate_wrfbdy_sha256": prepared["candidate_wrfbdy_sha256"],
        "candidate_namelist_sha256": prepared["candidate_namelist_sha256"],
        "namelist_diff": prepared["namelist_diff"],
        "disk_guard": prepared["disk_guard"],
        "layout_policy": {"mpi_ranks": 1, "tiles_per_domain": 1, "threads": 1,
                          "OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE"},
        "matched_controls": controls,
        "projected_capture": {"receipt_path": str(capture_receipt_path),
                               "receipt_sha256": sha256(capture_receipt_path),
                               "candidate_input_sha256": PINS["projected_input_sha256"],
                               "completed_steps": 1},
        "validation_scope": "P20 is a one-step capture; this preflight is not a PROJECTED C2 model run or runtime validation.",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "preflight.json").write_text(json.dumps(record, indent=2) + "\n")
    print(EVIDENCE / "preflight.json")


if __name__ == "__main__":
    main()
