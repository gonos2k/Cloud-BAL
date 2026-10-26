from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr103_time_response as response


def fixture_readback():
    fields = {name: {"unit": unit, "source_field": response.SOURCE_FIELDS[name]}
              for name, unit in response.FIELDS.items()}
    metrics = {}
    for second in response.SCHEDULE:
        metrics[str(second)] = {}
        for field, unit in response.FIELDS.items():
            metrics[str(second)][field] = {"unit": unit, "minus_OFF": {}}
            for arm, scale in (("HYDRO", 1.0), ("COUPLED", 2.0), ("P", 3.0), ("STRUCTURED", 4.0)):
                rms = scale * second / 60.0
                metrics[str(second)][field]["minus_OFF"][arm] = {
                    region: {"count": count, "rms": rms}
                    for region, count in response.REGIONS.items()}
    return {"times_seconds": list(response.SCHEDULE), "fields": fields,
            "status": "DESCRIPTIVE_ONLY", "physical_approval": "FAIL_OPEN",
            "observation_skill": "NOT_EVALUATED",
            "fixed_support": {"support_cells": 613, "support_columns": 16,
                              "buffer_columns": 196, "buffer_levels": 39},
            "metrics": metrics}


def write_legacy_receipt(tmp_path, readback_path):
    digest = hashlib.sha256(readback_path.read_bytes()).hexdigest()
    receipt = {"status": "COMPLETE", "task": "fivearm", "returncode": 0,
               "products": {"products/fivearm_history_readback.json": digest}}
    path = tmp_path / "execution.json"
    path.write_text(json.dumps(receipt))
    return path


def test_full_response_integrates_squared_rms_on_nonuniform_schedule_fixture(tmp_path):
    # The contract is uniform, while the helper also proves trapezoids use actual deltas.
    assert response._integral((0, 3, 10), [0.0, 2.0, 2.0]) == pytest.approx(34.0)
    readback_path = tmp_path / "readback.json"
    readback_path.write_text(json.dumps(fixture_readback()))
    receipt_path = write_legacy_receipt(tmp_path, readback_path)
    result = response.build_response(json.loads(readback_path.read_text()),
                                     input_path=readback_path, receipt_path=receipt_path)
    metric = result["metrics"]["W"]["N"]["support"]
    assert metric["saved_maximum"] == 40.0
    assert metric["saved_maximum_times_seconds"] == [600]
    assert metric["I_0_60"] == pytest.approx(8.0)
    assert metric["integral_0_60"] == pytest.approx(480.0)
    assert metric["endpoint_0s"] == 0.0
    assert metric["endpoint_60s"] == 4.0
    assert metric["I_0_600"] == pytest.approx(536.0)
    assert result["metrics"]["W"]["OFF"]["buffer"]["I_0_600"] == 0.0


@pytest.mark.parametrize("mutation, message", [
    (lambda d: d.update(times_seconds=[0, 60, 120, 180, 240, 300, 360, 420, 480, 540, 540]), "saved times"),
    (lambda d: d["metrics"]["300"].pop("W"), "missing W metrics at 300s"),
    (lambda d: d["metrics"]["300"]["W"]["minus_OFF"].pop("HYDRO"), "missing HYDRO minus_OFF"),
    (lambda d: d["metrics"]["300"]["W"]["minus_OFF"]["HYDRO"]["support"].update(rms=float("nan")), "finite number"),
    (lambda d: d["metrics"]["300"]["W"]["minus_OFF"]["HYDRO"]["support"].update(count=612), "count/shape"),
    (lambda d: d["fields"]["W"].update(unit="km/s"), "unit differs"),
])
def test_rejects_wrong_missing_duplicate_nonfinite_shape_and_unit(tmp_path, mutation, message):
    data = fixture_readback()
    mutation(data)
    readback_path = tmp_path / "readback.json"
    readback_path.write_text(json.dumps(data))
    receipt_path = write_legacy_receipt(tmp_path, readback_path)
    with pytest.raises(ValueError, match=message):
        response.build_response(data, input_path=readback_path, receipt_path=receipt_path)


def test_rejects_negative_rms(tmp_path):
    data = fixture_readback()
    data["metrics"]["300"]["W"]["minus_OFF"]["HYDRO"]["support"]["rms"] = -0.1
    readback_path = tmp_path / "readback.json"
    readback_path.write_text(json.dumps(data))
    receipt_path = write_legacy_receipt(tmp_path, readback_path)
    with pytest.raises(ValueError, match="must be nonnegative"):
        response.build_response(data, input_path=readback_path, receipt_path=receipt_path)


def test_legacy_execution_receipt_requires_zero_returncode(tmp_path):
    readback_path = tmp_path / "readback.json"
    readback_path.write_text(json.dumps(fixture_readback()))
    receipt_path = write_legacy_receipt(tmp_path, readback_path)
    receipt = json.loads(receipt_path.read_text())
    receipt["returncode"] = 1
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="execution receipt is not complete"):
        response.build_response(json.loads(readback_path.read_text()),
                                input_path=readback_path, receipt_path=receipt_path)


def test_cli_refuses_to_overwrite_existing_output(tmp_path, monkeypatch):
    readback_path = tmp_path / "readback.json"
    readback_path.write_text(json.dumps(fixture_readback()))
    receipt_path = write_legacy_receipt(tmp_path, readback_path)
    output_path = tmp_path / "existing.json"
    output_path.write_text("preserve me\n")
    monkeypatch.setattr("sys.argv", ["pr103_time_response.py", "--input", str(readback_path),
                                      "--receipt", str(receipt_path), "--output", str(output_path)])
    with pytest.raises(FileExistsError):
        response.main()
    assert output_path.read_text() == "preserve me\n"


def test_new_arm_requires_explicit_closed_receipt_and_fixed_schedule(tmp_path, monkeypatch):
    data = fixture_readback()
    for second in response.SCHEDULE:
        for field, unit in response.FIELDS.items():
            data["metrics"][str(second)][field]["minus_OFF"]["A"] = {
                region: {"count": count, "rms": 5.0}
                for region, count in response.REGIONS.items()}
            data.setdefault("paired_metrics", {}).setdefault("A_minus_H", {}).setdefault(str(second), {})[field] = {
                "unit": unit,
                **{region: {"count": count, "rms": 2.0}
                   for region, count in response.REGIONS.items()},
            }
    readback_path = tmp_path / "readback.json"
    readback_path.write_text(json.dumps(data))
    execution_path = write_legacy_receipt(tmp_path, readback_path)
    candidate_path = tmp_path / "candidate.bin"
    proposal_path = tmp_path / "proposal.json"
    candidate_path.write_bytes(b"candidate")
    proposal_path.write_bytes(b"proposal")
    candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    proposal_sha = hashlib.sha256(proposal_path.read_bytes()).hexdigest()
    monkeypatch.setattr(response, "A_CANDIDATE_PATH", candidate_path)
    monkeypatch.setattr(response, "A_CANDIDATE_SHA256", candidate_sha)
    monkeypatch.setattr(response, "A_PROPOSAL_PATH", proposal_path)
    monkeypatch.setattr(response, "A_PROPOSAL_SHA256", proposal_sha)
    executable_sha = response.A_EXECUTABLE_SHA256
    boundary_sha = response.A_BOUNDARY_SHA256
    namelist_sha = response.A_NAMELIST_SHA256
    snapshots = []
    generated_files = []
    run_directory = tmp_path / "AMPLITUDE_RUN" / "run"
    run_directory.mkdir(parents=True)
    snapshot = run_directory / "wrfout_d01_2026-08-16_13:00:00"
    snapshot.write_bytes(b"single history file containing eleven fixed-time records")
    snapshot_sha = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    generated_files.append({"path": snapshot.name, "sha256": snapshot_sha})
    for second in response.SCHEDULE:
        snapshots.append({"time_seconds": second, "record_index": len(snapshots),
                          "path": str(snapshot), "sha256": snapshot_sha})
    model_receipt = tmp_path / "AMPLITUDE_RUN" / "receipt.json"
    model_receipt.parent.mkdir(exist_ok=True)
    preflight_path = tmp_path / "preflight.json"
    preflight = {"schema": "pr103_execution_preflight_v1",
                 "status": "READY_FOR_ROOT_REVIEW_NO_LAUNCH", "launch_authorized": False,
                 "duration_seconds": 640, "expected_timesteps": 32,
                 "candidate_input_receipt_path": str(proposal_path),
                 "candidate_input_receipt_sha256": proposal_sha,
                 "candidate_wrfinput_sha256": candidate_sha,
                 "candidate_executable_sha256": executable_sha,
                 "candidate_wrfbdy_sha256": boundary_sha,
                 "candidate_namelist_sha256": namelist_sha}
    preflight_path.write_text(json.dumps(preflight))
    preflight_sha = hashlib.sha256(preflight_path.read_bytes()).hexdigest()
    model_receipt.write_text(json.dumps({
        "arm": "AMPLITUDE", "status": "COMPLETE", "returncode": 0,
        "timestep_count": 32, "final_completed_step": 32, "maximum_seen_timestep": 32,
        "candidate_wrfinput_sha256": candidate_sha, "executed_executable_sha256": executable_sha,
        "candidate_wrfbdy_sha256": boundary_sha, "candidate_namelist_sha256": namelist_sha,
        "earliest_fatal": None, "fatal_lines": [], "processing_errors": [],
        "changed_staged_inputs": [], "changed_original_inputs": [],
        "candidate_input_binding": {"receipt_path": str(proposal_path),
                                     "receipt_sha256": proposal_sha},
        "pr103_execution_preflight": {"path": str(preflight_path), "sha256": preflight_sha},
        "generated_files": generated_files}))
    arm_receipt_path = tmp_path / "closed_A.json"
    arm_receipt_path.write_text(json.dumps({
        "schema": "pr103_closed_history_readback_receipt_v1", "status": "CLOSED", "arm": "A",
        "readback_path": str(readback_path.resolve()),
        "readback_sha256": hashlib.sha256(readback_path.read_bytes()).hexdigest(),
        "times_seconds": list(response.SCHEDULE), "paired_comparisons": ["A_minus_H"],
        "model_run_receipt": {"path": str(model_receipt),
                               "sha256": hashlib.sha256(model_receipt.read_bytes()).hexdigest()},
        "execution_preflight": {"path": str(preflight_path), "sha256": preflight_sha},
        "history_snapshots": snapshots, "candidate_wrfinput_sha256": candidate_sha,
        "candidate_wrfinput_path": str(candidate_path), "proposal_path": str(proposal_path),
        "proposal_sha256": proposal_sha,
        "executed_executable_sha256": executable_sha, "candidate_wrfbdy_sha256": boundary_sha,
        "candidate_namelist_sha256": namelist_sha}))
    result = response.build_response(data, input_path=readback_path, receipt_path=execution_path,
                                     new_arm_receipt=arm_receipt_path)
    assert result["metrics"]["QC"]["A"]["support"]["saved_maximum"] == 5.0
    assert result["explicit_paired_metrics"]["A_minus_H"]["QC"]["support"]["I_0_600"] == 4.0
    assert result["source_receipt"]["model_run_receipt"]["sha256"] == hashlib.sha256(model_receipt.read_bytes()).hexdigest()
    closed = json.loads(arm_receipt_path.read_text())
    failed_run = json.loads(model_receipt.read_text())
    failed_run["returncode"] = 1
    model_receipt.write_text(json.dumps(failed_run))
    closed["model_run_receipt"]["sha256"] = hashlib.sha256(model_receipt.read_bytes()).hexdigest()
    arm_receipt_path.write_text(json.dumps(closed))
    with pytest.raises(ValueError, match="not a clean, closed 640-second"):
        response.build_response(data, input_path=readback_path, receipt_path=execution_path,
                                new_arm_receipt=arm_receipt_path)
    data["times_seconds"][-1] = 540
    with pytest.raises(ValueError, match="saved times"):
        response.build_response(data, input_path=readback_path, receipt_path=execution_path,
                                new_arm_receipt=arm_receipt_path)
