#!/usr/bin/env python3
"""Receipt and recheck PR103 amplitude-control prerequisites; never launches WRF."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pr86_time_response as runner
import pr102_execution_preflight as pr102


STRUCTURED_ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr102_native_structure640_20261025/STRUCTURED640_RUN")
STRUCTURED_RECEIPT_SHA256 = "313295e9cbf9e30a12a437c501bf3db2cf25c0e6762ec5d51c31d54ba311d4d6"
STRUCTURED_PREFLIGHT_SHA256 = "11b3614e6aceceac3e40e5d4481f6954948210e79d3c6aea799512fa22afad4c"
DIAGNOSTIC_EXECUTABLE_SHA256 = "aca04cd72a886d41fedcae51e2bbb9cc0b03688e4b9db96ddd12ebc62981b6e0"


def artifact(path: Path) -> dict:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": str(path), "sha256": runner.sha256(path)}


def _closed_structured_control() -> dict:
    receipt_path, preflight_path = STRUCTURED_ROOT / "receipt.json", STRUCTURED_ROOT / "preflight.json"
    receipt_pin, preflight_pin = artifact(receipt_path), artifact(preflight_path)
    if (receipt_pin["sha256"] != STRUCTURED_RECEIPT_SHA256 or
            preflight_pin["sha256"] != STRUCTURED_PREFLIGHT_SHA256):
        raise ValueError("PR102 STRUCTURED control differs from its closed receipt pins")
    receipt, preflight = json.loads(receipt_path.read_text()), json.loads(preflight_path.read_text())
    if (receipt.get("arm") != "STRUCTURED" or receipt.get("status") != "COMPLETE" or
            receipt.get("returncode") != 0 or receipt.get("timestep_count") != 32 or
            receipt.get("final_completed_step") != 32 or receipt.get("maximum_seen_timestep") != 32 or
            receipt.get("executed_executable_sha256") != runner.PR102_BASE_C2_EXECUTABLE_SHA256 or
            receipt.get("candidate_wrfbdy_sha256") != runner.PR102_BOUNDARY_C2_SHA256 or
            receipt.get("candidate_namelist_sha256") != "58c194b8846d25a6c7cbfedac1477fbf65fcc1a12705c8cb11851096ee7d2fc8" or
            receipt.get("fatal_lines") or receipt.get("processing_errors") or
            receipt.get("changed_staged_inputs") or receipt.get("changed_original_inputs") or
            preflight.get("arm") != "STRUCTURED" or preflight.get("duration_seconds") != 640):
        raise ValueError("PR102 STRUCTURED control is not a closed matched C2 forecast")
    return {"receipt": receipt_pin, "preflight": preflight_pin,
            "candidate_wrfinput_sha256": receipt["candidate_wrfinput_sha256"]}


def _consumer_assessment(path: Path, binding: dict) -> dict:
    return runner._validate_pr103_consumer_assessment(path, binding)


def _capture(label: str, path: Path, expected_input_sha256: str) -> tuple[dict, list[dict]]:
    pin = artifact(path)
    record = json.loads(path.read_text())
    build_ref = record.get("diagnostic_build_receipt", {})
    build_path = Path(build_ref.get("path", ""))
    build_record = json.loads(build_path.read_text()) if build_path.is_file() else {}
    if (record.get("schema") != "pr102_native_source_capture_v1" or
            record.get("status") != "COMPLETE" or
            record.get("candidate_wrfinput_sha256") != expected_input_sha256 or
            record.get("completed_steps") != 1 or
            set(record.get("captured_sources", [])) != {"RU", "RV", "MUDF"} or
            record.get("noninterference", {}).get("status") != "PASS" or
            record.get("baseline_c2_executable_sha256") != runner.PR102_BASE_C2_EXECUTABLE_SHA256 or
            record.get("diagnostic_executable_sha256") != DIAGNOSTIC_EXECUTABLE_SHA256 or
            not build_path.is_file() or runner.sha256(build_path) != build_ref.get("sha256") or
            record.get("diagnostic_build_receipt_sha256") != build_ref.get("sha256") or
            build_record.get("schema") != "pr102_c2_native_capture_build_v1" or
            build_record.get("status") != "PASS_C2_CAPTURE_OVERLAY" or
            build_record.get("base_c2_executable_sha256") != runner.PR102_BASE_C2_EXECUTABLE_SHA256 or
            build_record.get("executable_sha256") != DIAGNOSTIC_EXECUTABLE_SHA256 or
            not record.get("artifacts")):
        raise ValueError(f"{label} source-capture receipt is not a matched one-step RU/RV/MUDF capture")
    artifacts = [pin, artifact(build_path)]
    for row in record["artifacts"]:
        path = Path(row["path"])
        if not path.is_file() or runner.sha256(path) != row.get("sha256"):
            raise ValueError(f"{label} source-capture artifact changed: {path}")
        artifacts.append({"path": str(path.resolve()), "sha256": row["sha256"]})
    return {"receipt": pin, "candidate_wrfinput_sha256": expected_input_sha256,
            "diagnostic_build_receipt_sha256": build_ref["sha256"],
            "captured_sources": ["RU", "RV", "MUDF"], "noninterference": record["noninterference"]}, artifacts


def _noninterference(path: Path, candidate_sha256: str) -> dict:
    pin = artifact(path)
    record = json.loads(path.read_text())
    t0, first, t1 = (record.get("t0_history", {}), record.get("first20_trace", {}),
                     record.get("t1_post", {}))
    if (record.get("status") != "PASS_CAPTURE_NONINTERFERENCE" or
            record.get("candidate_input_sha256") != candidate_sha256 or
            record.get("control_arm") != "AMPLITUDE_BASELINE20" or
            record.get("diagnostic_arm") != "AMPLITUDE_CAPTURE" or
            t0.get("status") != "PASS" or t0.get("field_count") != 30 or
            len(t0.get("fields", {})) != 30 or
            not all(value.get("equal") is True for value in t0.get("fields", {}).values()) or
            first.get("status") != "PASS" or first.get("record") != "20s POST_KDM6 timestep 1" or
            not first.get("record_sha256") or t1.get("status") != "PASS" or
            t1.get("field_count") != 18 or len(t1.get("fields", {})) != 18 or
            not all(value.get("equal") is True for value in t1.get("fields", {}).values())):
        raise ValueError("PR103 same-input diagnostic noninterference evidence did not pass T0/POST_KDM6/T1")
    for row in runner._artifact_pins(record):
        dependency = Path(row["path"])
        if not dependency.is_file() or runner.sha256(dependency) != row["sha256"]:
            raise ValueError(f"PR103 noninterference evidence changed: {dependency}")
    return pin


def build_preflight(proposal_path: Path, build_path: Path, consumer_path: Path,
                    noninterference_path: Path, captures: dict[str, Path],
                    output_path: Path) -> dict:
    binding = runner._amplitude_control_input_binding(proposal_path)
    candidate_sha256 = binding["artifacts"]["candidate"]["sha256"]
    build = runner._candidate_build_binding(build_path)
    runner._require_pr102_base_c2(build)
    if set(captures) != {"HYDRO", "ORIGINAL_P", "STRUCTURED", "AMPLITUDE"}:
        raise ValueError("source-capture cohort must contain H, P, PR102 N, and PR103 A")

    controls = pr102._controls()
    controls["STRUCTURED"] = _closed_structured_control()
    for key, expected in (("HYDRO", binding["artifacts"]["reference_hydro"]["sha256"]),
                          ("COUPLED", binding["artifacts"]["reference_coupled"]["sha256"]),
                          ("PROJECTED", binding["artifacts"]["original_p"]["sha256"]),
                          ("STRUCTURED", binding["artifacts"]["reference_structured"]["sha256"])):
        if controls[key]["candidate_wrfinput_sha256"] != expected:
            raise ValueError(f"PR103 {key} control differs from the proposal's frozen reference")
    controls["OFF"] = {**controls["OFF"]}

    consumer_pin = _consumer_assessment(consumer_path, binding)
    noninterference_pin = _noninterference(noninterference_path, candidate_sha256)
    expected_capture_inputs = {"HYDRO": binding["artifacts"]["reference_hydro"]["sha256"],
                               "ORIGINAL_P": binding["artifacts"]["original_p"]["sha256"],
                               "STRUCTURED": binding["artifacts"]["reference_structured"]["sha256"],
                               "AMPLITUDE": candidate_sha256}
    capture_rows, capture_artifacts = {}, []
    diagnostic_build_receipts = set()
    for label, capture_path in captures.items():
        row, artifacts = _capture(label, capture_path, expected_capture_inputs[label])
        capture_rows[label] = row
        diagnostic_build_receipts.add(row["diagnostic_build_receipt_sha256"])
        capture_artifacts.extend(artifacts)
    if len(diagnostic_build_receipts) != 1:
        raise ValueError("H/P/N/A source captures must share the exact same diagnostic build receipt")

    controls["STRUCTURED"] = controls["STRUCTURED"]
    consumer_record = json.loads(Path(consumer_pin["path"]).read_text())
    noninterference_record = json.loads(Path(noninterference_pin["path"]).read_text())
    evidence = [artifact(Path(binding["receipt_path"])),
                *runner._artifact_pins(binding),
                *binding["source_receipts"].values(),
                *binding["pr102_execution_evidence"],
                artifact(Path(build["receipt_path"])), consumer_pin, noninterference_pin,
                *runner._artifact_pins(consumer_record),
                *runner._artifact_pins(noninterference_record),
                *capture_artifacts]
    for row in controls.values():
        evidence.extend((row["receipt"], row["preflight"]))
    record = {
        "schema": "pr103_execution_preflight_v1",
        "status": "READY_FOR_ROOT_REVIEW_NO_LAUNCH",
        "launch_authorized": False,
        "arm": "AMPLITUDE",
        "duration_seconds": 640,
        "expected_timesteps": 32,
        "candidate_input_receipt_path": binding["receipt_path"],
        "candidate_input_receipt_sha256": binding["receipt_sha256"],
        "candidate_wrfinput_sha256": candidate_sha256,
        "candidate_build_receipt_sha256": build["receipt_sha256"],
        "candidate_executable_sha256": build["executable_sha256"],
        "candidate_wrfbdy_sha256": runner.PR102_BOUNDARY_C2_SHA256,
        "candidate_namelist_sha256": "58c194b8846d25a6c7cbfedac1477fbf65fcc1a12705c8cb11851096ee7d2fc8",
        "matched_controls": controls,
        "native_consumer_assessment": consumer_pin,
        "actual_A20_noninterference": noninterference_pin,
        "native_source_capture_cohort": {
            "diagnostic_executable_sha256": DIAGNOSTIC_EXECUTABLE_SHA256,
            "diagnostic_build_receipt_sha256": next(iter(diagnostic_build_receipts)),
            "captures": capture_rows,
        },
        "amplitude_metrics": binding["metrics"],
        "evidence_artifacts": evidence,
        "physical_approval": "FAIL_OPEN",
        "observation_skill": "NOT_EVALUATED",
    }
    output_path = output_path.resolve()
    if output_path.exists():
        raise FileExistsError(f"refusing to replace PR103 preflight: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    try:
        runner._validate_pr103_preflight(output_path, binding, build)
    except Exception:
        output_path.unlink()
        raise
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--candidate-build", type=Path, required=True)
    parser.add_argument("--consumer-assessment", type=Path, required=True)
    parser.add_argument("--a20-noninterference", type=Path, required=True)
    parser.add_argument("--capture-hydro", type=Path, required=True)
    parser.add_argument("--capture-p", type=Path, required=True)
    parser.add_argument("--capture-n", type=Path, required=True)
    parser.add_argument("--capture-a", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = build_preflight(args.proposal, args.candidate_build, args.consumer_assessment,
                             args.a20_noninterference,
                             {"HYDRO": args.capture_hydro, "ORIGINAL_P": args.capture_p,
                              "STRUCTURED": args.capture_n, "AMPLITUDE": args.capture_a}, args.output)
    print(json.dumps({"schema": record["schema"], "status": record["status"],
                      "output": str(args.output.resolve()),
                      "evidence_artifact_count": len(record["evidence_artifacts"])}, indent=2))


if __name__ == "__main__":
    main()
