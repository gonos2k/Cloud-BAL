#!/usr/bin/env python3
"""Receipt-closure gates for the PR101 C2 response reducer."""
from __future__ import annotations

import sys
import json
from pathlib import Path

import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr101_projected_c2_response import (CONTROL_ROOT, EXPECTED_TIMESTAMPS, _crop_active_grid, _metrics,
                                         _state_field_kji,
                                         REVIEWED_PREFLIGHT, _trace_receipt_row,
                                         _validate_reviewed_control, validate_closed_receipt)

_CONTROL_ASSETS_AVAILABLE = (REVIEWED_PREFLIGHT.is_file() and all(
    (CONTROL_ROOT / arm / name).is_file()
    for arm in ("OFF", "HYDRO", "COUPLED") for name in ("receipt.json", "preflight.json")))
_MISSING_CONTROL_ASSETS = pytest.mark.skipif(
    not _CONTROL_ASSETS_AVAILABLE,
    reason="retained private PR99 closed controls and reviewed PR101 preflight are unavailable")


def closed(arm: str) -> tuple[dict, dict]:
    receipt = {"arm": arm, "status": "COMPLETE", "returncode": 0,
               "timestep_count": 32, "final_completed_step": 32,
               "maximum_seen_timestep": 32,
               "expected_model_timestamps": EXPECTED_TIMESTAMPS,
               "model_timestamps": [{"timestamp": stamp} for stamp in EXPECTED_TIMESTAMPS],
               "earliest_fatal": None, "candidate_build_unchanged": True,
               "candidate_input_unchanged": True, "processing_errors": [], "fatal_lines": [],
               "changed_staged_inputs": [], "changed_original_inputs": [],
               "duplicate_post_kdm6_timesteps": [],
               "candidate_wrfbdy_sha256": "885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7",
               "candidate_namelist_sha256": "58c194b8846d25a6c7cbfedac1477fbf65fcc1a12705c8cb11851096ee7d2fc8",
               "executed_executable_sha256": "387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a",
               "candidate_wrfinput_sha256": "10aff32bf15887a43141efbb1b14945234e8bbce741a89904d328fb3b1d75cb3",
               "execution_layout": {"status": "VERIFIED_SINGLE", "single_execution_layout": True,
                                    "mpi_rank_count": 1, "tiles_per_domain": 1, "threads": 1}}
    preflight = {"arm": arm, "duration_seconds": 640, "expected_timesteps": 32,
                 "candidate_wrfinput_sha256": "10aff32bf15887a43141efbb1b14945234e8bbce741a89904d328fb3b1d75cb3"}
    return receipt, preflight


def test_accepts_only_a_closed_640_second_arm():
    receipt, preflight = closed("PROJECTED")
    validate_closed_receipt(receipt, preflight, "PROJECTED")


@pytest.mark.parametrize("changes", [
    {"status": "RUNNING"}, {"returncode": 128}, {"candidate_input_unchanged": False},
    {"processing_errors": ["truncated trace"]}, {"changed_staged_inputs": ["wrfinput_d01"]},
    {"final_completed_step": 31}, {"earliest_fatal": "FATAL"},
    {"candidate_namelist_sha256": "wrong"},
])
def test_rejects_partial_failed_or_unmatched_run(changes):
    receipt, preflight = closed("PROJECTED")
    receipt.update(changes)
    with pytest.raises(ValueError, match="clean closed 640-second|matched C2|candidate input"):
        validate_closed_receipt(receipt, preflight, "PROJECTED")


def test_rejects_control_arm_identity_mismatch():
    receipt, preflight = closed("HYDRO")
    with pytest.raises(ValueError, match="clean closed 640-second"):
        validate_closed_receipt(receipt, preflight, "PROJECTED")


def test_fortran_trace_jki_payload_maps_to_kji_masks_without_axis_swap():
    ny, nz, nx = 3, 2, 4
    jki = np.empty((ny, nz, nx), dtype=">f4")
    for j in range(ny):
        for k in range(nz):
            for i in range(nx):
                jki[j, k, i] = 100 * j + 10 * k + i
    decoded = _state_field_kji(jki.tobytes(), (nz, ny, nx))
    assert decoded.shape == (nz, ny, nx)
    assert decoded[1, 2, 3] == 213
    assert decoded[0, 1, 2] == 102
    active = _crop_active_grid(decoded, (nz, ny - 2, nx - 2))
    assert active.shape == (nz, 1, 2)
    assert active[1, 0, 1] == 112


def test_response_metrics_reject_nonfinite_selected_values():
    with pytest.raises(ValueError, match="share finite support"):
        _metrics(np.array([1.0, np.nan]), np.array([0.0, 0.0]))


@pytest.mark.parametrize("arm", ["OFF", "HYDRO", "COUPLED"])
@_MISSING_CONTROL_ASSETS
def test_original_c2_trace_inventory_routes_compressed_raw_name(arm):
    receipt = json.loads((CONTROL_ROOT / arm / "receipt.json").read_text())
    row = _trace_receipt_row(receipt)
    compressed_entry = next(item for item in receipt["generated_files"]
                            if item["path"] == row["compressed_path"])
    assert row["path"] == "pr85_joint_moment_stages.raw"
    assert row["compressed_path"] == "pr85_joint_moment_stages.raw.gz"
    assert len(row["sha256"]) == 64 and row["bytes"] > 0
    assert compressed_entry["sha256"] == row["compressed_sha256"]


@pytest.mark.parametrize("arm", ["OFF", "HYDRO", "COUPLED"])
@_MISSING_CONTROL_ASSETS
def test_original_c2_receipt_and_input_match_reviewed_preflight_pin(arm):
    import json
    root = CONTROL_ROOT / arm
    receipt = json.loads((root / "receipt.json").read_text())
    preflight = json.loads((root / "preflight.json").read_text())
    reviewed = json.loads(REVIEWED_PREFLIGHT.read_text())
    _validate_reviewed_control(arm, root, receipt, preflight, reviewed)
    changed = dict(receipt, candidate_wrfinput_sha256="replacement-input")
    with pytest.raises(ValueError, match="reviewed PR101 receipt/preflight/input pins"):
        _validate_reviewed_control(arm, root, changed, preflight, reviewed)
