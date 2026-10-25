#!/usr/bin/env python3
"""Compare closed PR102 one-step diagnostic captures with matched C2 controls."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tempfile

import netCDF4
import numpy as np

import native_kdm6_trace
import pr87_native_history as history
import pr86_time_response as response


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr102_native_structure20_capture_20261025")
CONTROL_ROOTS = {
    "HYDRO": Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr99_c2_matched640_20261022/HYDRO"),
    "PROJECTED": Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr101_projected_c2_640_20261023"),
}
BASE_C2_EXE_SHA256 = "387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a"
DIAGNOSTIC_EXE_SHA256 = "aca04cd72a886d41fedcae51e2bbb9cc0b03688e4b9db96ddd12ebc62981b6e0"
CAPTURE_INPUTS = {
    "HYDRO": "46760bdf03e42cbc8e1f5b415e1b304b535d369689f95a421a287d1eb90b679c",
    "PROJECTED": "10aff32bf15887a43141efbb1b14945234e8bbce741a89904d328fb3b1d75cb3",
}
N_CAPTURE_ROOTS = {
    "control": Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr102_native_structure20_capture_20261025/BASELINE20_RUN"),
    "diagnostic": Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr102_native_structure20_capture_20261025/CANDIDATE_RUN"),
}
N_INPUT_SHA256 = "b26e5f3d712732c3459d59b82a4b44fe53eebd9be1fd450d13640d2d8398343f"
BOUNDARY_SHA256 = "885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7"
T0_HISTORY = "wrfout_d01_2026-08-16_13:00:00"
T1_POST = "kdm6_first_call_post.raw.gz"
T0_FIELDS = (history.STATE + tuple(history.WATER) + tuple(history.MOMENTS) +
             ("MU", "MUB", "DNW", "C1H", "C2H", "MAPFAC_MX", "MAPFAC_MY",
              "MAPFAC_UX", "MAPFAC_UY", "MAPFAC_VX", "MAPFAC_VY", "XLAND"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def receipt_artifact(receipt: dict, path_name: str, *, compressed: bool = False) -> dict:
    rows = receipt.get("compressed_outputs" if compressed else "generated_files", [])
    matches = [row for row in rows if row.get("path") == path_name]
    if len(matches) != 1:
        raise ValueError(f"expected one receipt row for {path_name}")
    return matches[0]


def verify_output(root: Path, receipt: dict, name: str, *, compressed: bool = False) -> Path:
    row = receipt_artifact(receipt, name, compressed=compressed)
    path = root / "run" / (row["compressed_path"] if compressed else name)
    actual = sha256(path)
    expected = row["compressed_sha256"] if compressed else row["sha256"]
    if actual != expected:
        raise ValueError(f"closed output changed after its receipt: {path}")
    return path


def _valid_closed_receipt(root: Path, label: str, *, control: bool,
                          expected_arm: str | None = None,
                          expected_input: str | None = None,
                          expected_steps: int | None = None,
                          expected_executable: str | None = None) -> dict:
    path = root / "receipt.json"
    receipt = json.loads(path.read_text())
    if expected_arm is None:
        expected_arm = "HYDRO" if label == "HYDRO" else ("PROJECTED" if control else "COUPLED")
    if expected_input is None:
        expected_input = CAPTURE_INPUTS[label]
    if (receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0 or
            receipt.get("arm") != expected_arm or receipt.get("candidate_wrfinput_sha256") != expected_input or
            receipt.get("candidate_wrfbdy_sha256") != BOUNDARY_SHA256 or
            not receipt.get("candidate_input_unchanged") or receipt.get("changed_original_inputs") or
            receipt.get("changed_staged_inputs") or receipt.get("processing_errors") or
            receipt.get("earliest_fatal") or receipt.get("fatal_lines")):
        raise ValueError(f"{label} closed receipt is incomplete or has changed inputs")
    if control:
        expected_steps = 32 if expected_steps is None else expected_steps
        expected_executable = BASE_C2_EXE_SHA256 if expected_executable is None else expected_executable
        if (receipt.get("executed_executable_sha256") != expected_executable or
                receipt.get("timestep_count") != expected_steps or
                receipt.get("final_completed_step") != expected_steps):
            raise ValueError(f"{label} is not the closed matched-640 C2 control")
    else:
        expected_steps = 1 if expected_steps is None else expected_steps
        expected_executable = DIAGNOSTIC_EXE_SHA256 if expected_executable is None else expected_executable
        if (receipt.get("executed_executable_sha256") != expected_executable or
                receipt.get("timestep_count") != expected_steps or
                receipt.get("final_completed_step") != expected_steps):
            raise ValueError(f"{label} is not the closed one-step C2 diagnostic capture")
    return receipt


def compare_t0(root_new: Path, new: dict, root_control: Path, control: dict) -> dict:
    new_path = verify_output(root_new, new, T0_HISTORY)
    control_path = verify_output(root_control, control, T0_HISTORY)
    fields = {}
    with netCDF4.Dataset(new_path) as diagnostic, netCDF4.Dataset(control_path) as baseline:
        diagnostic.set_auto_mask(False)
        baseline.set_auto_mask(False)
        diagnostic_time, baseline_time = history._times(diagnostic)[0], history._times(baseline)[0]
        if diagnostic_time != baseline_time or diagnostic_time.strftime("%Y-%m-%d_%H:%M:%S") != "2026-08-16_13:00:00":
            raise ValueError("T0 history record timestamps differ")
        for name in T0_FIELDS:
            if name not in diagnostic.variables or name not in baseline.variables:
                raise ValueError(f"T0 history field is missing: {name}")
            left = np.asarray(diagnostic.variables[name][0])
            right = np.asarray(baseline.variables[name][0])
            same = (left.shape == right.shape and left.dtype == right.dtype and
                    left.tobytes() == right.tobytes())
            fields[name] = {"equal": same, "shape": list(left.shape),
                            "dtype": str(left.dtype),
                            "diagnostic_array_sha256": hashlib.sha256(left.tobytes()).hexdigest(),
                            "control_array_sha256": hashlib.sha256(right.tobytes()).hexdigest()}
            if not same:
                raise ValueError(f"T0 history field differs: {name}")
    return {"status": "PASS", "record": "2026-08-16_13:00:00", "field_count": len(fields),
            "fields": fields,
            "diagnostic_file": {"path": str(new_path), "sha256": sha256(new_path)},
            "control_file": {"path": str(control_path), "sha256": sha256(control_path),
                             "whole_file_hash_comparison_used": False}}


def compare_first20(new: dict, control: dict) -> dict:
    new_row = new["snapshots"]["snapshots"].get("20s")
    control_row = control["snapshots"]["snapshots"].get("20s")
    if not new_row or not control_row:
        raise ValueError("20-second post-KDM6 trace record is missing")
    if (new_row.get("timestep") != 1 or control_row.get("timestep") != 1 or
            new_row.get("stage") != "POST_KDM6" or control_row.get("stage") != "POST_KDM6" or
            new_row.get("active_cells") != control_row.get("active_cells") or
            new_row.get("record_sha256") != control_row.get("record_sha256")):
        raise ValueError("first completed 20-second POST_KDM6 trace record differs")
    return {"status": "PASS", "record": "20s POST_KDM6 timestep 1",
            "active_cells": new_row["active_cells"],
            "record_sha256": new_row["record_sha256"],
            "method": "Existing pr86_time_response.read_time_snapshots record digest in receipt"}


def compare_t1_post(root_new: Path, new: dict, root_control: Path, control: dict) -> dict:
    new_path = verify_output(root_new, new, "kdm6_first_call_post.raw", compressed=True)
    control_path = verify_output(root_control, control, "kdm6_first_call_post.raw", compressed=True)
    fields = {}
    with tempfile.TemporaryDirectory(prefix="pr102_closed_t1_compare_") as temp:
        decoded = []
        for label, path in (("diagnostic", new_path), ("control", control_path)):
            raw_path = Path(temp) / f"{label}.raw"
            with gzip.open(path, "rb") as source, raw_path.open("wb") as sink:
                for block in iter(lambda: source.read(1 << 20), b""):
                    sink.write(block)
            decoded.append(native_kdm6_trace.read_dump(raw_path))
        diagnostic, baseline = decoded
        if (diagnostic["stage"], diagnostic["itimestep"], diagnostic["bounds"], diagnostic["params"]) != (
                baseline["stage"], baseline["itimestep"], baseline["bounds"], baseline["params"]):
            raise ValueError("first-call T1 post dump headers differ")
        if diagnostic["stage"] != 2 or diagnostic["itimestep"] != 1:
            raise ValueError("T1 post comparison is not the first returned call state")
        for name in native_kdm6_trace.FIELDS_3D + native_kdm6_trace.FIELDS_2D:
            left, right = diagnostic["fields"][name], baseline["fields"][name]
            same = left.shape == right.shape and left.dtype == right.dtype and left.tobytes() == right.tobytes()
            fields[name] = {"equal": same, "shape": list(left.shape), "dtype": str(left.dtype),
                            "array_sha256": hashlib.sha256(left.tobytes()).hexdigest()}
            if not same:
                raise ValueError(f"T1 post field differs: {name}")
    return {"status": "PASS", "field_count": len(fields), "fields": fields,
            "diagnostic_compressed": {"path": str(new_path), "sha256": sha256(new_path)},
            "control_compressed": {"path": str(control_path), "sha256": sha256(control_path)},
            "method": "Existing native_kdm6_trace.read_dump; field-by-field 17 3D fields plus XLAND"}


def receipt_bound_source_outputs(root: Path, receipt: dict) -> list[dict]:
    rows = [row for row in receipt.get("generated_files", [])
            if Path(row.get("path", "")).name.startswith("pr98_")]
    if not rows:
        raise ValueError("diagnostic receipt has no PR98 source-capture outputs")
    artifacts = []
    for row in rows:
        path = root / "run" / row["path"]
        if not path.is_file() or path.stat().st_size != row["bytes"]:
            raise ValueError(f"receipt-bound PR98 source output is missing or resized: {path}")
        actual = sha256(path)
        if actual != row["sha256"]:
            raise ValueError(f"receipt-bound PR98 source output hash changed: {path}")
        artifacts.append({"path": str(path), "sha256": row["sha256"],
                          "bytes": row["bytes"], "hash_verified_against_run_receipt": True})
    return artifacts


def require_one_step_timestamp(receipt: dict) -> None:
    expected = ["2026-08-16_13:00:20"]
    actual = [row.get("timestamp") for row in receipt.get("model_timestamps", [])]
    if receipt.get("expected_model_timestamps") != expected or actual != expected:
        raise ValueError("N run does not contain exactly the declared first 20-second model timestamp")


def analyze(output: Path) -> dict:
    results = {}
    artifacts = []
    for label in ("HYDRO", "PROJECTED"):
        diagnostic_root = CAPTURE_ROOT / ("HYDRO_RUN" if label == "HYDRO" else "PROJECTED_RUN")
        control_root = CONTROL_ROOTS[label]
        diagnostic = _valid_closed_receipt(diagnostic_root, label, control=False)
        control = _valid_closed_receipt(control_root, label, control=True)
        if diagnostic["candidate_build"]["executable_sha256"] != DIAGNOSTIC_EXE_SHA256:
            raise ValueError(f"{label} diagnostic receipt executable/build mismatch")
        if diagnostic["expected_model_timestamps"][:1] != control["expected_model_timestamps"][:1]:
            raise ValueError(f"{label} diagnostic and C2 control first model time differs")
        diagnostic_receipt_path, control_receipt_path = diagnostic_root / "receipt.json", control_root / "receipt.json"
        d_record = diagnostic["snapshots"]["snapshots"].get("20s")
        c_record = control["snapshots"]["snapshots"].get("20s")
        if not d_record or not c_record:
            raise ValueError(f"{label} first-step trace receipt record is missing")
        result = {"candidate_input_sha256": CAPTURE_INPUTS[label],
                  "control_executable_sha256": control["executed_executable_sha256"],
                  "diagnostic_executable_sha256": diagnostic["executed_executable_sha256"],
                  "control_receipt": {"path": str(control_receipt_path), "sha256": sha256(control_receipt_path)},
                  "diagnostic_receipt": {"path": str(diagnostic_receipt_path), "sha256": sha256(diagnostic_receipt_path)},
                  "t0_history": compare_t0(diagnostic_root, diagnostic, control_root, control),
                  "first20_trace": compare_first20(diagnostic, control),
                  "t1_post": compare_t1_post(diagnostic_root, diagnostic, control_root, control),
                  "source_capture_outputs": receipt_bound_source_outputs(diagnostic_root, diagnostic)}
        results[label] = result
        artifacts.extend((result["control_receipt"], result["diagnostic_receipt"],
                          result["t0_history"]["diagnostic_file"], result["t0_history"]["control_file"],
                          result["t1_post"]["diagnostic_compressed"], result["t1_post"]["control_compressed"]))
        artifacts.extend(result["source_capture_outputs"])
        for run_root, receipt in ((diagnostic_root, diagnostic), (control_root, control)):
            trace = verify_output(run_root, receipt, "pr85_joint_moment_stages.raw.gz")
            artifacts.append({"path": str(trace), "sha256": sha256(trace)})
        for name in ("preflight.json", "launch_provenance.json"):
            path = diagnostic_root / name
            artifacts.append({"path": str(path), "sha256": sha256(path)})
    overlay_path = Path(json.loads((CAPTURE_ROOT / "HYDRO_RUN" / "receipt.json").read_text())[
                         "candidate_build"]["receipt_path"])
    build_path = overlay_path.parent / "pr102_c2_native_capture_build.json"
    build = json.loads(build_path.read_text())
    overlay = json.loads(overlay_path.read_text())
    if (build.get("schema") != "pr102_c2_native_capture_build_v1" or
            build.get("status") != "PASS_C2_CAPTURE_OVERLAY" or
            build.get("base_c2_executable_sha256") != BASE_C2_EXE_SHA256 or
            build.get("executable_sha256") != DIAGNOSTIC_EXE_SHA256 or
            overlay.get("executable_sha256") != DIAGNOSTIC_EXE_SHA256 or
            build.get("diagnostic_build_receipt_sha256") != sha256(overlay_path)):
        raise ValueError("diagnostic build receipt does not bind the matched C2 executable")
    artifacts.extend(({"path": str(build_path), "sha256": sha256(build_path)},
                      {"path": str(overlay_path), "sha256": sha256(overlay_path)}))
    result = {"schema": "pr102_closed_c2_capture_noninterference_v1",
              "status": "PASS_CAPTURE_NONINTERFERENCE",
              "scope": "One completed 20-second diagnostic step for HYDRO and PROJECTED; no forecast or physics acceptance.",
              "controls": results,
              "diagnostic_build": {"path": str(build_path), "sha256": sha256(build_path),
                                   "base_c2_executable_sha256": BASE_C2_EXE_SHA256,
                                   "diagnostic_executable_sha256": DIAGNOSTIC_EXE_SHA256},
              "evidence_artifacts": artifacts,
              "limitations": [
                  "T0 compares the same 30 state, water, moment, grid, and XLAND arrays at the same history record; WRF history whole-file hashes differ with the 1-minute diagnostic output interval.",
                  "First-20 trace comparison is the receipt-bound POST_KDM6 timestep-1 record digest produced by pr86_time_response.read_time_snapshots.",
                  "T1 comparison uses native_kdm6_trace.read_dump and all 17 returned 3D fields plus XLAND.",
                  "This establishes actual output noninterference for the compared fields/records only; it does not establish semantic dry-mass constraint or physical acceptance."]}
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def analyze_candidate_n(output: Path) -> dict:
    control_root, diagnostic_root = N_CAPTURE_ROOTS["control"], N_CAPTURE_ROOTS["diagnostic"]
    control = _valid_closed_receipt(
        control_root, "N", control=True, expected_arm="STRUCTURED_BASELINE20",
        expected_input=N_INPUT_SHA256, expected_steps=1, expected_executable=BASE_C2_EXE_SHA256)
    diagnostic = _valid_closed_receipt(
        diagnostic_root, "N", control=False, expected_arm="STRUCTURED_CAPTURE",
        expected_input=N_INPUT_SHA256, expected_steps=1, expected_executable=DIAGNOSTIC_EXE_SHA256)
    require_one_step_timestamp(control)
    require_one_step_timestamp(diagnostic)
    if diagnostic["candidate_build"]["executable_sha256"] != DIAGNOSTIC_EXE_SHA256:
        raise ValueError("N diagnostic receipt executable/build mismatch")
    if diagnostic["expected_model_timestamps"] != control["expected_model_timestamps"]:
        raise ValueError("N diagnostic and baseline first model time differs")
    control_receipt_path, diagnostic_receipt_path = control_root / "receipt.json", diagnostic_root / "receipt.json"
    result = {"schema": "pr102_closed_c2_candidate_n_noninterference_v1",
              "status": "PASS_CAPTURE_NONINTERFERENCE",
              "scope": "One completed 20-second BASELINE20_RUN versus STRUCTURED_CAPTURE diagnostic step; no forecast or physics acceptance.",
              "candidate_input_sha256": N_INPUT_SHA256,
              "control_arm": control["arm"], "control_executable_sha256": control["executed_executable_sha256"],
              "diagnostic_arm": diagnostic["arm"],
              "diagnostic_executable_sha256": diagnostic["executed_executable_sha256"],
              "control_receipt": {"path": str(control_receipt_path), "sha256": sha256(control_receipt_path)},
              "diagnostic_receipt": {"path": str(diagnostic_receipt_path), "sha256": sha256(diagnostic_receipt_path)},
              "t0_history": compare_t0(diagnostic_root, diagnostic, control_root, control),
              "first20_trace": compare_first20(diagnostic, control),
              "t1_post": compare_t1_post(diagnostic_root, diagnostic, control_root, control),
              "source_capture_outputs": receipt_bound_source_outputs(diagnostic_root, diagnostic),
              "evidence_artifacts": [],
              "limitations": [
                  "Both one-step runs use the exact N input, boundary, and first timestamp; only the diagnostic arm uses the capture overlay.",
                  "T0 history uses field-array comparison because output interval/metadata may differ.",
                  "The check establishes capture noninterference for these fields and this step only; it is not dry-mass semantic or physical acceptance."]}
    artifacts = [{"path": str(control_receipt_path), "sha256": result["control_receipt"]["sha256"]},
                 {"path": str(diagnostic_receipt_path), "sha256": result["diagnostic_receipt"]["sha256"]},
                 result["t0_history"]["diagnostic_file"], result["t0_history"]["control_file"],
                 result["t1_post"]["diagnostic_compressed"], result["t1_post"]["control_compressed"]]
    artifacts.extend(result["source_capture_outputs"])
    for root, receipt in ((control_root, control), (diagnostic_root, diagnostic)):
        trace = verify_output(root, receipt, "pr85_joint_moment_stages.raw.gz")
        artifacts.append({"path": str(trace), "sha256": sha256(trace)})
    for name in ("preflight.json", "launch_provenance.json"):
        path = diagnostic_root / name
        artifacts.append({"path": str(path), "sha256": sha256(path)})
    overlay_path = Path(diagnostic["candidate_build"]["receipt_path"])
    build_path = overlay_path.parent / "pr102_c2_native_capture_build.json"
    build = json.loads(build_path.read_text())
    overlay = json.loads(overlay_path.read_text())
    if (build.get("status") != "PASS_C2_CAPTURE_OVERLAY" or
            build.get("base_c2_executable_sha256") != BASE_C2_EXE_SHA256 or
            build.get("executable_sha256") != DIAGNOSTIC_EXE_SHA256 or
            overlay.get("executable_sha256") != DIAGNOSTIC_EXE_SHA256 or
            build.get("diagnostic_build_receipt_sha256") != sha256(overlay_path)):
        raise ValueError("N diagnostic build receipt does not bind the matched C2 executable")
    result["diagnostic_build"] = {"path": str(build_path), "sha256": sha256(build_path),
                                  "overlay_receipt": {"path": str(overlay_path),
                                                      "sha256": sha256(overlay_path)},
                                  "base_c2_executable_sha256": BASE_C2_EXE_SHA256,
                                  "diagnostic_executable_sha256": DIAGNOSTIC_EXE_SHA256}
    artifacts.extend((result["diagnostic_build"], result["diagnostic_build"]["overlay_receipt"]))
    result["evidence_artifacts"] = artifacts
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate-n", action="store_true",
                        help="analyze only the closed baseline/candidate one-step N pair")
    args = parser.parse_args()
    default_name = ("candidate_n20_capture_noninterference.json" if args.candidate_n
                    else "hp20_capture_noninterference.json")
    output = args.output or ROOT / "docs/evidence/pr102_execution_20261025" / default_name
    result = analyze_candidate_n(output) if args.candidate_n else analyze(output)
    print(json.dumps({"schema": result["schema"], "status": result["status"],
                      "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
