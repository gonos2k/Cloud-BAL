#!/usr/bin/env python3
"""Verify the closed N20 pair against its proposal-bound launch preflights."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr102_native_structure20_capture_20261025")
EXPECTED = {
    "proposal_sha256": "451e4e9110d3b921507e311be56328ad05e13ee20e1fedd2d9c60ce8ef94eeb8",
    "candidate_sha256": "b26e5f3d712732c3459d59b82a4b44fe53eebd9be1fd450d13640d2d8398343f",
    "boundary_sha256": "885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7",
    "namelist_sha256": "bd668a0f54fdc05996782adf472c78834cfc4829a05645fad8c68531a0be52d3",
    "runner_sha256": "35adaa773773c046311d731ea1426821befb225a444092405098b4ee4e8baa43",
    "model_timestamp": "2026-08-16_13:00:20",
    "preflights": {
        "baseline20_preflight.json": "b08960c3309ed5e8f8b7e261ab3fb4c8c6b7d0a8983227e2c19885aa85e3ea58",
        "candidate20_preflight.json": "e3a4013660015c79600bd320d95461a68d6029080ced6d99005c426f09be21ee",
    },
}
EXPECTED_ENVIRONMENT = {
    "OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE", "status": "CONFIGURED_BY_RUNNER",
    "launch_request_sha256": "6a64ae6f037396da0900a25b9012257045b017051cfb659321b1bfdc8d629a89",
}
EXPECTED_LAUNCHES = {
    "BASELINE20": {"arm": "STRUCTURED_BASELINE20",
                   "input_sha256": EXPECTED["candidate_sha256"],
                   "exe_sha256": "387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a"},
    "CANDIDATE_CAPTURE": {"arm": "STRUCTURED_CAPTURE",
                          "input_sha256": EXPECTED["candidate_sha256"],
                          "exe_sha256": "aca04cd72a886d41fedcae51e2bbb9cc0b03688e4b9db96ddd12ebc62981b6e0"},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_pin(path: Path, digest: str) -> dict:
    actual = sha256(path)
    if actual != digest:
        raise ValueError(f"artifact hash mismatch: {path}")
    return {"path": str(path), "sha256": actual}


def checked_reference(row: dict) -> dict:
    return checked_pin(Path(row["path"]), row["sha256"])


def analyze(output: Path) -> dict:
    manifest_path = CAPTURE / "n20_launch_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "pr102_n20_launch_manifest_v1" or manifest.get("closed_pair_status") != "PASS":
        raise ValueError("N20 launch manifest is not a successful closed pair")
    manifest_pin = checked_pin(manifest_path, sha256(manifest_path))
    manifest_refs = {name: checked_reference(manifest[name]) for name in
                     ("root_go", "review_bundle", "runner_bundle_manifest", "consumer_assessment")}
    proposal = manifest["proposal"]
    if (proposal.get("sha256") != EXPECTED["proposal_sha256"] or
            proposal.get("candidate_sha256") != EXPECTED["candidate_sha256"]):
        raise ValueError("N20 manifest does not bind the frozen proposal and candidate")
    proposal_pin = checked_pin(Path(proposal["path"]), EXPECTED["proposal_sha256"])
    candidate_pin = checked_pin(Path(json.loads(Path(proposal["path"]).read_text())["candidate"]["path"]),
                                EXPECTED["candidate_sha256"])

    preflight_pins = {}
    preflights = {}
    for name, expected_hash in EXPECTED["preflights"].items():
        path = CAPTURE / name
        preflight = json.loads(path.read_text())
        if (preflight.get("schema") != "pr102_capture20_runner_preflight_v1" or
                preflight.get("status") != "READY_FOR_ROOT_REVIEW_NO_LAUNCH" or
                preflight.get("candidate_wrfinput_sha256") != EXPECTED["candidate_sha256"] or
                preflight.get("candidate_wrfbdy_sha256") != EXPECTED["boundary_sha256"] or
                preflight.get("candidate_namelist_sha256") != EXPECTED["namelist_sha256"] or
                preflight.get("launch_environment") != EXPECTED_ENVIRONMENT):
            raise ValueError(f"preflight is not bound to the shared N20 inputs/environment: {name}")
        preflight_pins[name] = checked_pin(path, expected_hash)
        preflights[name] = preflight
    if preflights["baseline20_preflight.json"]["arm"] != "STRUCTURED_BASELINE20" or \
            preflights["candidate20_preflight.json"]["arm"] != "STRUCTURED_CAPTURE":
        raise ValueError("N20 preflight arm roles changed")

    runs = {}
    artifacts = [manifest_pin, proposal_pin, candidate_pin, *preflight_pins.values(),
                 *manifest_refs.values()]
    actual_receipt_roots = {
        "BASELINE20": CAPTURE / "BASELINE20_RUN",
        "CANDIDATE_CAPTURE": CAPTURE / "CANDIDATE_RUN",
    }
    for label, expectation in EXPECTED_LAUNCHES.items():
        launch = manifest["launches"][label]
        receipt_path = Path(launch["receipt_path"])
        receipt = json.loads(receipt_path.read_text())
        if receipt_path != actual_receipt_roots[label] / "receipt.json":
            raise ValueError(f"N20 manifest receipt path mismatch for {label}")
        receipt_pin = checked_pin(receipt_path, launch["receipt_sha256"])
        launch_preflight_path = Path(launch["preflight_path"])
        if launch_preflight_path != actual_receipt_roots[label] / "preflight.json":
            raise ValueError(f"N20 run preflight path mismatch for {label}")
        run_preflight = json.loads(launch_preflight_path.read_text())
        run_preflight_pin = checked_pin(launch_preflight_path, launch["preflight_sha256"])
        if (launch.get("state") != "CLOSED_COMPLETE" or launch.get("status") != "COMPLETE" or
                launch.get("returncode") != 0 or launch.get("timestep_count") != 1 or
                receipt.get("arm") != expectation["arm"] or receipt.get("status") != "COMPLETE" or
                receipt.get("returncode") != 0 or receipt.get("timestep_count") != 1 or
                receipt.get("candidate_wrfinput_sha256") != expectation["input_sha256"] or
                receipt.get("executed_executable_sha256") != expectation["exe_sha256"] or
                receipt.get("candidate_wrfbdy_sha256") != EXPECTED["boundary_sha256"] or
                receipt.get("candidate_namelist_sha256") != EXPECTED["namelist_sha256"] or
                receipt.get("launch_environment") != EXPECTED_ENVIRONMENT or
                run_preflight.get("candidate_wrfinput_sha256") != EXPECTED["candidate_sha256"] or
                run_preflight.get("candidate_wrfbdy_sha256") != EXPECTED["boundary_sha256"] or
                run_preflight.get("candidate_namelist_sha256") != EXPECTED["namelist_sha256"] or
                run_preflight.get("launch_environment") != EXPECTED_ENVIRONMENT or
                launch.get("actual_launch_environment") != EXPECTED_ENVIRONMENT or
                launch.get("runner_source_sha256") != EXPECTED["runner_sha256"] or
                [row.get("timestamp") for row in receipt.get("model_timestamps", [])] !=
                [EXPECTED["model_timestamp"]]):
            raise ValueError(f"closed run does not match its preflight/launch manifest: {label}")
        runs[label] = {"receipt": receipt_pin, "arm": expectation["arm"],
                       "input_sha256": receipt["candidate_wrfinput_sha256"],
                       "executable_sha256": receipt["executed_executable_sha256"],
                       "boundary_sha256": receipt["candidate_wrfbdy_sha256"],
                       "namelist_sha256": receipt["candidate_namelist_sha256"],
                       "launch_environment": receipt["launch_environment"],
                       "runner_source_sha256": launch["runner_source_sha256"],
                       "model_timestamp": EXPECTED["model_timestamp"]}
        artifacts.extend((receipt_pin, run_preflight_pin))

    baseline, diagnostic = runs["BASELINE20"], runs["CANDIDATE_CAPTURE"]
    if any(baseline[key] != diagnostic[key] for key in
           ("input_sha256", "boundary_sha256", "namelist_sha256", "launch_environment",
            "runner_source_sha256", "model_timestamp")):
        raise ValueError("N20 baseline and capture launches do not share expected inputs and environment")
    capture_path = ROOT / "docs/evidence/pr102_execution_20261025/candidate_n20_capture_noninterference.json"
    capture_report = json.loads(capture_path.read_text())
    if (capture_report.get("schema") != "pr102_closed_c2_candidate_n_noninterference_v1" or
            capture_report.get("status") != "PASS_CAPTURE_NONINTERFERENCE" or
            capture_report.get("candidate_input_sha256") != EXPECTED["candidate_sha256"] or
            capture_report.get("control_receipt", {}).get("sha256") != baseline["receipt"]["sha256"] or
            capture_report.get("diagnostic_receipt", {}).get("sha256") != diagnostic["receipt"]["sha256"] or
            capture_report.get("t0_history", {}).get("status") != "PASS" or
            capture_report.get("first20_trace", {}).get("status") != "PASS" or
            capture_report.get("t1_post", {}).get("status") != "PASS"):
        raise ValueError("candidate N capture comparison does not bind the closed launch pair")
    capture_pin = checked_pin(capture_path, sha256(capture_path))
    analysis_tool_path = ROOT / "tools/pr102_capture_noninterference.py"
    analysis_tool_pin = {"path": str(analysis_tool_path), "sha256": sha256(analysis_tool_path)}
    artifacts.extend((capture_pin, analysis_tool_pin))
    result = {"schema": "pr102_n20_actual_launch_identity_v1", "status": "PASS",
              "candidate_sha256": EXPECTED["candidate_sha256"],
              "baseline": baseline, "diagnostic": diagnostic,
              "shared_launch_identity": {key: baseline[key] for key in
                                          ("input_sha256", "boundary_sha256", "namelist_sha256",
                                           "launch_environment", "runner_source_sha256", "model_timestamp")},
              "preflights": preflight_pins, "proposal": proposal_pin,
              "candidate_file": candidate_pin,
              "root_go_review_runner_consumer_pins": manifest_refs,
              "capture_noninterference": capture_pin,
              "capture_analysis_tool": analysis_tool_pin,
              "launch_manifest": manifest_pin,
              "artifacts": artifacts,
              "scope": "Provenance equality for the closed first 20-second N comparison only; no 640-second integration or physics acceptance.",
              "physical_approval": "FAIL_OPEN"}
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs/evidence/pr102_execution_20261025/n20_actual_launch_identity.json")
    args = parser.parse_args()
    result = analyze(args.output)
    print(json.dumps({"schema": result["schema"], "status": result["status"],
                      "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
