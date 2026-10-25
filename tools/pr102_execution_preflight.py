#!/usr/bin/env python3
"""Validate candidate-bound PR102 consumer, source-capture, and C2 controls."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pr86_time_response as runner
from pr102_native_wind_candidate import verify_only_wind_changed


ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee")
CONTROL_ROOT = ROOT / "pr99_c2_matched640_20261022"
PROJECTED_CONTROL = ROOT / "pr101_projected_c2_640_20261023"
EXPECTED_EXECUTABLE = "387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a"
BASE_C2_RECEIPT_SHA256 = "9c4802e12ea1d6a8f3c8b5ef1a5ff72116e5fbdbf9f6c78e906935622d45dafb"
EXPECTED_NAMELIST = "58c194b8846d25a6c7cbfedac1477fbf65fcc1a12705c8cb11851096ee7d2fc8"
EXPECTED_BOUNDARY = "885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7"
EXPECTED_CONSUMER_MEMBER = "8f7a0666664bdccb45c414cb9e6ec481f7daaad3fa6170f0d51f524515572343"
EXPECTED_PROFILE = "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4"
CONTROL_PINS = {
    "OFF": ("c4174b0363dc3b6eb5117ae1e011e9bee0f4f70d090036c607331fac7b0d1f8d",
            "3d64c75c70f568fe59f8e42c620811c235b274f29f1ade123537e0fc2392ee2c"),
    "HYDRO": ("1440db5a0178af11ac4d92854b3284cc35cb5a74e5e6f6a14cc59dcac3a00a64",
              "875de6cf8765339c02b5f625151411465e0b199813aa8e6e5386e30beefad7b0"),
    "COUPLED": ("0a7e1c3bcce58dea8433e9bffa615395d923cd05377c5068469af5dba29759cb",
                "19941e93fa9dc7d7f7e840ae80021bd2017ed034072d71871a7cc904a2e0edb3"),
    "PROJECTED": ("d0a7920687aecbef15b91f2641638918f00beea67de5fb2af6e5597175bc5da2",
                  "db19a14accab9958d75a9c83107f317cab4b0b64788789fde60168391418bdaa"),
}
EVIDENCE = Path(__file__).resolve().parents[1] / "docs/evidence/pr102_execution_20261025"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_receipt(path: Path, schema: str, status: str) -> dict:
    path = path.resolve()
    receipt = json.loads(path.read_text())
    if receipt.get("schema") != schema or receipt.get("status") != status:
        raise ValueError(f"{path} must be {schema} / {status}")
    return receipt


def artifact(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha256(path)}


def _candidate_prerequisite(path: Path, schema: str, candidate_sha: str) -> tuple[dict, list[dict]]:
    record = read_receipt(path, schema, "COMPLETE")
    if record.get("candidate_wrfinput_sha256") != candidate_sha:
        raise ValueError(f"{path} is not bound to this candidate")
    rows = [artifact(path.resolve())]
    for row in record.get("artifacts", []):
        dependency = artifact(Path(row["path"]))
        if dependency["sha256"] != row.get("sha256"):
            raise ValueError(f"{path} evidence artifact changed: {dependency['path']}")
        rows.append(dependency)
    return record, rows


def _validate_native_consumer(check: dict, composition_sha256: str) -> None:
    if (check.get("schema") != "pr102_native_drymass_constraint_v1" or
            check.get("status") != "PASS" or
            check.get("consumer") != "module_big_step_utilities_em_mp_calc_ww_cp_" or
            check.get("comparison") != "candidate_minus_HYDRO" or
            check.get("units") != "Pa/s" or
            check.get("composition_sha256") != composition_sha256 or
            check.get("finite") is not True or check.get("support_count", 0) <= 0):
        raise ValueError("native calc_ww_cp result lacks its finite fixed-support contract")
    for gate_name in ("reference_constraint", "source_arithmetic"):
        gate = check.get(gate_name, {})
        values = tuple(gate.get(name) for name in (
            "observed_l2_pa_s", "allowed_l2_pa_s", "observed_max_abs_pa_s", "allowed_max_abs_pa_s"))
        if (gate.get("status") != "PASS" or
                any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
                    for value in values) or
                values[0] > values[1] or values[2] > values[3]):
            raise ValueError(f"native calc_ww_cp {gate_name} gate did not pass its finite bound")
    observed_l2, allowed_l2 = check.get("observed_l2_pa_s"), check.get("allowed_l2_pa_s")
    observed_max, allowed_max = check.get("observed_max_abs_pa_s"), check.get("allowed_max_abs_pa_s")
    values = (observed_l2, allowed_l2, observed_max, allowed_max)
    if (any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
            for value in values) or observed_l2 > allowed_l2 or observed_max > allowed_max):
        raise ValueError("native calc_ww_cp residual exceeds its declared storage bound")


def _controls() -> dict:
    controls = {}
    for arm in ("OFF", "HYDRO", "COUPLED", "PROJECTED"):
        directory = (PROJECTED_CONTROL if arm == "PROJECTED" else CONTROL_ROOT / arm)
        receipt_path, preflight_path = directory / "receipt.json", directory / "preflight.json"
        receipt, preflight = json.loads(receipt_path.read_text()), json.loads(preflight_path.read_text())
        receipt_pin, preflight_pin = CONTROL_PINS[arm]
        expected_runner = ("087f9f3a9f80f5679db7c228d99dde269200028d823553e0a2045a855cbba439"
                           if arm == "PROJECTED" else
                           "80803b6b3e8591053d0524ed9e5b0110dfd7cbf1d105d2e40029addb5f5a55c4")
        if (sha256(receipt_path) != receipt_pin or sha256(preflight_path) != preflight_pin or
                receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0 or
                receipt.get("timestep_count") != 32 or receipt.get("final_completed_step") != 32 or
                receipt.get("maximum_seen_timestep") != 32 or receipt.get("earliest_fatal") is not None or
                receipt.get("processing_errors") != [] or receipt.get("fatal_lines") != [] or
                receipt.get("duplicate_post_kdm6_timesteps") != [] or
                receipt.get("executed_executable_sha256") != EXPECTED_EXECUTABLE or
                receipt.get("candidate_wrfbdy_sha256") != EXPECTED_BOUNDARY or
                receipt.get("candidate_namelist_sha256") != EXPECTED_NAMELIST or
                receipt.get("changed_staged_inputs") != [] or receipt.get("changed_original_inputs") != [] or
                receipt.get("launch_runner_source_sha256") != expected_runner or
                preflight.get("arm") != arm or preflight.get("duration_seconds") != 640 or
                preflight.get("expected_timesteps") != 32 or
                preflight.get("candidate_wrfinput_sha256") != receipt.get("candidate_wrfinput_sha256") or
                preflight.get("candidate_wrfbdy_sha256") != EXPECTED_BOUNDARY or
                preflight.get("candidate_namelist_sha256") != EXPECTED_NAMELIST):
            raise ValueError(f"{arm} is not a matching closed C2 640-second control")
        controls[arm] = {"receipt": artifact(receipt_path), "preflight": artifact(preflight_path),
                         "candidate_wrfinput_sha256": receipt["candidate_wrfinput_sha256"],
                         "completed_steps": 32}
    return controls


def build_preflight(proposal_path: Path, build_path: Path, consumer_path: Path,
                    capture_paths: dict[str, Path], output_path: Path) -> dict:
    binding = runner._wind_structure_input_binding(proposal_path)
    proposal = json.loads(Path(binding["receipt_path"]).read_text())
    candidate_sha = binding["artifacts"]["candidate"]["sha256"]
    original_p_sha = binding["artifacts"]["original_p"]["sha256"]
    controls = _controls()
    for proposal_key, arm in (("original_p", "PROJECTED"),
                              ("reference_hydro", "HYDRO"),
                              ("reference_coupled", "COUPLED")):
        if binding["artifacts"][proposal_key]["sha256"] != controls[arm]["candidate_wrfinput_sha256"]:
            raise ValueError(f"proposal {proposal_key} differs from the closed {arm} input")
    if set(capture_paths) != {"HYDRO", "ORIGINAL_P", "CANDIDATE"}:
        raise ValueError("source capture cohort must contain HYDRO, ORIGINAL_P, and CANDIDATE")
    verify_only_wind_changed(Path(binding["artifacts"]["candidate"]["path"]),
                             Path(binding["artifacts"]["original_p"]["path"]))
    build = runner._candidate_build_binding(build_path)
    exe_sha = build["executable_sha256"]
    if exe_sha != EXPECTED_EXECUTABLE:
        raise ValueError("candidate build executable differs from the matched C2 controls")
    if proposal.get("parent_sha256", original_p_sha) != original_p_sha:
        raise ValueError("proposal parent alias differs from original_p")

    consumer, consumer_artifacts = _candidate_prerequisite(
        consumer_path, "pr102_native_consumer_check_v1", candidate_sha)
    if (consumer.get("native_consumer") != "module_big_step_utilities_em_mp_calc_ww_cp_" or
            consumer.get("archive_member_sha256") != EXPECTED_CONSUMER_MEMBER or
            consumer.get("compiler_profile_sha256") != EXPECTED_PROFILE):
        raise ValueError("native calc_ww_cp dry-mass consumer check did not pass")
    _validate_native_consumer(consumer.get("dry_mass_check", {}), binding["composition_sha256"])
    capture_rows, capture_artifacts = {}, []
    cohort_inputs = {"HYDRO": controls["HYDRO"]["candidate_wrfinput_sha256"],
                     "ORIGINAL_P": controls["PROJECTED"]["candidate_wrfinput_sha256"],
                     "CANDIDATE": candidate_sha}
    for label, path in capture_paths.items():
        capture, rows = _candidate_prerequisite(
            path, "pr102_native_source_capture_v1", cohort_inputs[label])
        diagnostic_build_ref = capture.get("diagnostic_build_receipt", {})
        diagnostic_build_path = Path(diagnostic_build_ref.get("path", ""))
        diagnostic_build_sha = diagnostic_build_ref.get("sha256")
        diagnostic_build_record = json.loads(diagnostic_build_path.read_text())
        if (capture.get("noninterference", {}).get("status") != "PASS" or
                set(capture.get("captured_sources", [])) != {"RU", "RV", "MUDF"} or
                capture.get("completed_steps") != 1 or not capture.get("artifacts") or
                capture.get("baseline_c2_executable_sha256") != EXPECTED_EXECUTABLE or
                diagnostic_build_record.get("schema") != "pr102_c2_native_capture_build_v1" or
                diagnostic_build_record.get("status") != "PASS_C2_CAPTURE_OVERLAY" or
                diagnostic_build_record.get("base_c2_receipt_sha256") != BASE_C2_RECEIPT_SHA256 or
                diagnostic_build_record.get("base_c2_executable_sha256") != EXPECTED_EXECUTABLE or
                diagnostic_build_record.get("executable_sha256") != capture.get("diagnostic_executable_sha256") or
                diagnostic_build_sha != capture.get("diagnostic_build_receipt_sha256") or
                sha256(diagnostic_build_path) != diagnostic_build_sha or
                not any(row.get("path") == str(diagnostic_build_path.resolve()) and
                        row.get("sha256") == diagnostic_build_sha for row in capture.get("artifacts", []))):
            raise ValueError(f"{label} C2 source capture lacks noninterference or required source arrays")
        capture_rows[label] = (capture, rows)
        capture_artifacts.extend(rows)
    diagnostic_exe = {row[0].get("diagnostic_executable_sha256") for row in capture_rows.values()}
    diagnostic_build = {row[0].get("diagnostic_build_receipt_sha256") for row in capture_rows.values()}
    if len(diagnostic_exe) != 1 or None in diagnostic_exe or len(diagnostic_build) != 1 or None in diagnostic_build:
        raise ValueError("HYDRO, original_p, and candidate source captures must share one C2 diagnostic build")

    evidence_artifacts = [artifact(Path(binding["receipt_path"])), artifact(Path(build["receipt_path"])),
                          *consumer_artifacts, *capture_artifacts]
    evidence_artifacts.extend(row for control in controls.values()
                              for row in (control["receipt"], control["preflight"]))
    record = {
        "schema": "pr102_execution_preflight_v1",
        "status": "READY_FOR_ROOT_REVIEW_NO_LAUNCH",
        "launch_authorized": False,
        "arm": "STRUCTURED",
        "duration_seconds": 640,
        "expected_timesteps": 32,
        "candidate_input_receipt": str(Path(binding["receipt_path"])),
        "candidate_input_receipt_sha256": binding["receipt_sha256"],
        "candidate_wrfinput_sha256": candidate_sha,
        "original_p_sha256": original_p_sha,
        "candidate_build_receipt_sha256": build["receipt_sha256"],
        "candidate_executable_sha256": exe_sha,
        "native_consumer": {"receipt": artifact(consumer_path),
                             "dry_mass_check": consumer["dry_mass_check"]},
        "native_source_capture_cohort": {
            "diagnostic_executable_sha256": next(iter(diagnostic_exe)),
            "diagnostic_build_receipt_sha256": next(iter(diagnostic_build)),
            "captures": {label: {"receipt": artifact(path),
                                 "input_sha256": capture_rows[label][0]["candidate_wrfinput_sha256"],
                                 "captured_sources": capture_rows[label][0]["captured_sources"],
                                 "noninterference": capture_rows[label][0]["noninterference"]}
                         for label, path in capture_paths.items()}},
        "matched_controls": controls,
        "evidence_artifacts": evidence_artifacts,
        "validation_scope": "Pre-640 candidate-bound native consumer and first-step source-capture gates; not a forecast or physical approval.",
    }
    output_path = output_path.resolve()
    if output_path.exists():
        raise FileExistsError(f"refusing to replace PR102 preflight: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--candidate-build", type=Path, required=True)
    parser.add_argument("--native-consumer", type=Path, required=True)
    parser.add_argument("--hydro-source-capture", type=Path, required=True)
    parser.add_argument("--original-p-source-capture", type=Path, required=True)
    parser.add_argument("--candidate-source-capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=EVIDENCE / "preflight.json")
    args = parser.parse_args()
    captures = {"HYDRO": args.hydro_source_capture,
                "ORIGINAL_P": args.original_p_source_capture,
                "CANDIDATE": args.candidate_source_capture}
    result = build_preflight(args.proposal, args.candidate_build, args.native_consumer,
                             captures, args.output)
    print(json.dumps({key: result[key] for key in
                      ("status", "candidate_wrfinput_sha256", "candidate_executable_sha256",
                       "matched_controls", "validation_scope")}, indent=2))


if __name__ == "__main__":
    main()
