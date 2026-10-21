from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/pr98_boundary_audit.py"
SPEC = importlib.util.spec_from_file_location("pr98_boundary_audit", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def runtime_rows() -> tuple[dict, dict, dict, dict]:
    build = {"receipt_sha256": "build", "executable_sha256": MODULE.EXPECTED_EXE}
    base_receipt = {
        "arm": "OFF", "candidate_build": build,
        "candidate_wrfinput_sha256": "input", "candidate_wrfbdy_sha256": "boundary",
    }
    run_receipt = {
        **base_receipt, "duration_seconds": 640,
        "executed_executable_sha256": MODULE.EXPECTED_EXE,
        "expected_executed_executable_sha256": MODULE.EXPECTED_EXE,
        "changed_original_inputs": [], "changed_staged_inputs": [],
        "candidate_build_unchanged": True, "candidate_input_unchanged": True,
    }
    base_preflight = {
        "arm": "OFF", "duration_seconds": 600, "candidate_build": build,
        "input_hashes": {"wrfinput_d01": "input", "wrfbdy_d01": "boundary"},
        "source_namelist_sha256": "source-namelist",
        "candidate_wrfinput_sha256": "input", "candidate_wrfbdy_sha256": "boundary",
    }
    run_preflight = {
        **base_preflight, "duration_seconds": 640,
    }
    return run_receipt, base_receipt, run_preflight, base_preflight


def test_c1_runtime_binding_rejects_wrong_generation_input() -> None:
    run, baseline, run_preflight, baseline_preflight = runtime_rows()
    run["candidate_wrfinput_sha256"] = "different-generation"
    with pytest.raises(ValueError, match="candidate_wrfinput_sha256"):
        MODULE.validate_c1_runtime_binding(Path("/run"), "OFF", run, baseline,
                                           run_preflight, baseline_preflight)


def test_closed_reader_rejects_early_running_receipt(tmp_path: Path) -> None:
    (tmp_path / "receipt.json").write_text(json.dumps({"arm": "OFF", "status": "RUNNING"}))
    auditor = MODULE.load_closed_auditor()
    with pytest.raises(auditor.AuditError, match="not finalized"):
        auditor.closed_receipt(tmp_path, "OFF")


def test_snapshot_schedule_comes_from_pinned_frozen_runner() -> None:
    runner = MODULE.load_frozen_runner()
    schedule = runner.snapshot_schedule(640)
    assert tuple(sorted(step * 20 for step in schedule)) == (20, 60, 300, 320, 480, 500, 600, 640)


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


def test_all_frozen_runner_snapshots_are_mandatory() -> None:
    runner = MODULE.load_frozen_runner()
    schedule = runner.snapshot_schedule(640)
    labels = set(schedule.values())
    assert MODULE.missing_snapshot_labels({"snapshots": {label: {} for label in labels}}, schedule) == []
    labels.remove("320s")
    assert MODULE.missing_snapshot_labels({"snapshots": {label: {} for label in labels}}, schedule) == ["320s"]


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
