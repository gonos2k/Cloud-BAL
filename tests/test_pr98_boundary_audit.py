from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/pr98_boundary_audit.py"
SPEC = importlib.util.spec_from_file_location("pr98_boundary_audit", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def runtime_rows(tmp_path: Path) -> tuple[dict, dict, dict, dict, Path]:
    build = {"receipt_sha256": "build", "executable_sha256": MODULE.EXPECTED_EXE}
    start = datetime.strptime("2026-08-16_13:00:00", "%Y-%m-%d_%H:%M:%S")
    baseline_times = [(start + timedelta(seconds=20 * step)).strftime("%Y-%m-%d_%H:%M:%S")
                      for step in range(1, 31)]
    planned_times = [(start + timedelta(seconds=20 * step)).strftime("%Y-%m-%d_%H:%M:%S")
                     for step in range(1, 33)]
    namelist = tmp_path / "run" / "namelist.input"
    namelist.parent.mkdir()
    namelist.write_text("&time_control /\n")
    namelist_hash = MODULE.sha256(namelist)
    base_receipt = {
        "arm": "OFF", "candidate_build": build,
        "candidate_wrfinput_sha256": "input", "candidate_wrfbdy_sha256": "boundary",
        "candidate_namelist_sha256": namelist_hash,
    }
    run_receipt = {
        **base_receipt,
        "expected_model_timestamps": planned_times,
        "executed_executable_sha256": MODULE.EXPECTED_EXE,
        "expected_executed_executable_sha256": MODULE.EXPECTED_EXE,
        "changed_original_inputs": [], "changed_staged_inputs": [],
        "candidate_build_unchanged": True, "candidate_input_unchanged": True,
    }
    baseline_receipt = {**base_receipt, "expected_model_timestamps": baseline_times}
    base_preflight = {
        "arm": "OFF", "duration_seconds": 600, "candidate_build": build,
        "timestep_seconds": 20, "expected_timesteps": 30,
        "input_hashes": {"wrfinput_d01": "input", "wrfbdy_d01": "boundary"},
        "source_namelist_sha256": "source-namelist",
        "candidate_wrfinput_sha256": "input", "candidate_wrfbdy_sha256": "boundary",
        "candidate_namelist_sha256": namelist_hash,
    }
    run_preflight = {
        **base_preflight, "duration_seconds": 640, "expected_timesteps": 32,
    }
    return run_receipt, baseline_receipt, run_preflight, base_preflight, tmp_path


def test_c1_runtime_binding_rejects_wrong_generation_input(tmp_path: Path) -> None:
    run, baseline, run_preflight, baseline_preflight, run_root = runtime_rows(tmp_path)
    run["candidate_wrfinput_sha256"] = "different-generation"
    with pytest.raises(ValueError, match="candidate_wrfinput_sha256"):
        MODULE.validate_c1_runtime_binding(run_root, "OFF", run, baseline,
                                           run_preflight, baseline_preflight)


def test_duration_comes_from_preflight_not_closed_receipt(monkeypatch: pytest.MonkeyPatch,
                                                           tmp_path: Path) -> None:
    run, baseline, run_preflight, baseline_preflight, run_root = runtime_rows(tmp_path)
    monkeypatch.setattr(MODULE, "verify_source_receipt_binding", lambda *args: None)
    runtime = MODULE.validate_c1_runtime_binding(run_root, "OFF", run, baseline,
                                                 run_preflight, baseline_preflight)
    assert "duration_seconds" not in run
    assert runtime["duration_seconds"] == 640
    assert runtime["duration_source"].startswith("run preflight")
    with pytest.raises(ValueError, match="preflight arm, duration, or timestep schedule"):
        MODULE.validate_c1_runtime_binding(run_root, "OFF", run, baseline,
                                           {**run_preflight, "duration_seconds": 620}, baseline_preflight)


def test_duration_binding_rejects_wrong_planned_timestamps_and_namelist(tmp_path: Path) -> None:
    run, baseline, preflight, baseline_preflight, run_root = runtime_rows(tmp_path)
    with pytest.raises(ValueError, match="planned model timestamps"):
        MODULE.validate_c1_runtime_binding(run_root, "OFF", {**run, "expected_model_timestamps":
                                               run["expected_model_timestamps"][:-2]}, baseline,
                                           preflight, baseline_preflight)
    with pytest.raises(ValueError, match="candidate namelist hash"):
        MODULE.validate_c1_runtime_binding(run_root, "OFF", run, baseline,
                                           {**preflight, "candidate_namelist_sha256": "wrong"},
                                           baseline_preflight)


def test_hydro_input_binding_allows_only_same_hash_receipt_path_relocation(tmp_path: Path) -> None:
    payload = b"same pinned HYDRO input receipt"
    baseline_path = tmp_path / "baseline" / "receipt.json"
    run_path = tmp_path / "copied" / "receipt.json"
    baseline_path.parent.mkdir()
    run_path.parent.mkdir()
    baseline_path.write_bytes(payload)
    run_path.write_bytes(payload)
    digest = MODULE.sha256(baseline_path)
    binding = {"receipt_sha256": digest, "artifacts": {"wrfinput": {"sha256": "input"}}}
    baseline_binding = {**binding, "receipt_path": str(baseline_path)}
    run_binding = {**binding, "receipt_path": str(run_path)}
    result = MODULE.verify_hydro_input_binding(
        tmp_path, {"candidate_input_binding": run_binding},
        {"candidate_input_binding": baseline_binding},
        {"candidate_input_binding": run_binding}, {"candidate_input_binding": baseline_binding})
    assert result["status"] == "PASS"
    assert result["all_metadata_equal_except_top_level_receipt_path"]
    changed_binding = {**run_binding, "artifacts": {"wrfinput": {"sha256": "wrong"}}}
    with pytest.raises(ValueError, match="metadata differs"):
        MODULE.verify_hydro_input_binding(
            tmp_path, {"candidate_input_binding": changed_binding},
            {"candidate_input_binding": baseline_binding}, {"candidate_input_binding": changed_binding},
            {"candidate_input_binding": baseline_binding})
    with pytest.raises(ValueError, match="closed receipt input binding"):
        MODULE.verify_hydro_input_binding(
            tmp_path, {"candidate_input_binding": baseline_binding}, {"candidate_input_binding": baseline_binding},
            {"candidate_input_binding": run_binding}, {"candidate_input_binding": baseline_binding})
    run_path.write_bytes(b"changed receipt")
    with pytest.raises(ValueError, match="does not match the pinned"):
        MODULE.verify_hydro_input_binding(
            tmp_path, {"candidate_input_binding": run_binding}, {"candidate_input_binding": baseline_binding},
            {"candidate_input_binding": run_binding}, {"candidate_input_binding": baseline_binding})


def test_closed_reader_rejects_early_running_receipt(tmp_path: Path) -> None:
    (tmp_path / "receipt.json").write_text(json.dumps({"arm": "OFF", "status": "RUNNING"}))
    auditor = MODULE.load_closed_auditor()
    with pytest.raises(auditor.AuditError, match="not finalized"):
        auditor.closed_receipt(tmp_path, "OFF")


def test_complete_duration_requires_zero_exit_no_fatals_and_all_unique_steps() -> None:
    receipt = {"status": "COMPLETE", "returncode": 0, "fatal_lines": [],
               "processing_errors": [], "final_completed_step": 32}
    steps = list(range(1, 33))
    assert MODULE.closed_run_complete(receipt, steps)
    for key, value in (("returncode", 1), ("fatal_lines", ["transaction rejected"]),
                       ("processing_errors", ["trace parse failed"])):
        broken = {**receipt, key: value}
        assert not MODULE.closed_run_complete(broken, steps)
    assert not MODULE.closed_run_complete(receipt, steps[:-1])
    assert not MODULE.closed_run_complete(receipt, steps[:-1] + [31])


def test_compressed_trace_hash_and_size_are_checked_before_decode(tmp_path: Path) -> None:
    trace = tmp_path / "stage_trace.gz"
    trace.write_bytes(b"receipt-bound bytes")
    row = {"compressed_bytes": trace.stat().st_size, "compressed_sha256": MODULE.sha256(trace)}
    MODULE.verify_compressed_output(trace, row, "OFF")
    trace.write_bytes(b"mutated bytes")
    with pytest.raises(ValueError, match="byte count|hash"):
        MODULE.verify_compressed_output(trace, row, "OFF")


def test_scoped_status_keeps_generic_qnb_failure_separate() -> None:
    assert MODULE.scoped_audit_status("PASS", "PASS", "PASS") == "PASS_SCOPED"
    assert MODULE.scoped_audit_status("PASS", "FAIL", "PASS") == "INCOMPLETE_OR_FAIL"


def test_source_receipt_binding_rejects_changed_identity_and_file(tmp_path: Path) -> None:
    receipt_file = tmp_path / "source_receipt.json"
    receipt_file.write_text('{"source":"frozen"}')
    digest = MODULE.sha256(receipt_file)
    base = {"source_receipt_sha256": digest, "source_receipt_path": str(receipt_file)}
    base_preflight = {"source_receipt_sha256": digest, "source_receipt": str(receipt_file)}
    MODULE.verify_source_receipt_binding(tmp_path, base, base, base_preflight, base_preflight)
    with pytest.raises(ValueError, match="source receipt identity"):
        MODULE.verify_source_receipt_binding(tmp_path, {**base, "source_receipt_sha256": "wrong"}, base,
                                             base_preflight, base_preflight)
    receipt_file.write_text('{"source":"mutated"}')
    with pytest.raises(ValueError, match="source receipt file changed"):
        MODULE.verify_source_receipt_binding(tmp_path, base, base, base_preflight, base_preflight)
    receipt_file.unlink()
    with pytest.raises(ValueError, match="source receipt file named by preflight is missing"):
        MODULE.verify_source_receipt_binding(tmp_path, base, base, base_preflight, base_preflight)


def test_history_identity_rejects_mutated_receipt_bound_file(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    history = run / "wrfout_d01_2026-08-16_13:00:00"
    history.write_bytes(b"closed-history")
    receipt = {"generated_files": [{"path": history.name, "sha256": MODULE.sha256(history)}]}
    assert MODULE.verify_receipt_history(tmp_path, receipt) == {history.name: MODULE.sha256(history)}
    history.write_bytes(b"changed-history")
    with pytest.raises(ValueError, match="history changed"):
        MODULE.verify_receipt_history(tmp_path, receipt)
