"""The response reader must not treat a partial or changed run as closed evidence."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr99_projection_response import capture_identity, validate_closed_capture


def closed():
    return {"arm": "COUPLED", "status": "COMPLETE", "returncode": 0,
            "final_completed_step": 1, "timestep_count": 1, "maximum_seen_timestep": 1,
            "expected_model_timestamps": ["2026-08-16_13:00:20"],
            "model_timestamps": [{"timestamp": "2026-08-16_13:00:20"}],
            "earliest_fatal": None, "candidate_build_unchanged": True,
            "candidate_input_unchanged": True, "processing_errors": [], "fatal_lines": [],
            "changed_staged_inputs": [], "changed_original_inputs": [],
            "duplicate_post_kdm6_timesteps": []}


def test_accepts_one_closed_clean_step():
    validate_closed_capture(closed(), {"arm": "COUPLED", "duration_seconds": 20})


@pytest.mark.parametrize("changes", [
    {"status": "RUNNING"}, {"returncode": 128}, {"candidate_input_unchanged": False},
    {"processing_errors": ["truncated snapshot"]}, {"changed_staged_inputs": ["wrfinput_d01"]},
    {"model_timestamps": []}, {"model_timestamps": [{"timestamp": "2026-08-16_13:00:40"}]},
    {"fatal_lines": ["joint candidate rejected"]}, {"maximum_seen_timestep": 2},
])
def test_rejects_partial_changed_or_crossed_run(changes):
    receipt = copy.deepcopy(closed())
    receipt.update(changes)
    with pytest.raises(ValueError, match="clean closed"):
        validate_closed_capture(receipt, {"arm": "COUPLED", "duration_seconds": 20})


def test_checkout_relocation_preserves_content_identity_but_not_a_changed_hash():
    old = {"capture_builder_source_path": "/old/tool.py", "capture_builder_source_sha256": "tool",
           "arms": {"COUPLED": {"manifest_path": "/old/manifest.json", "manifest_sha256": "data",
                                "receipt_sha256": "receipt", "candidate_wrfinput_sha256": "state"}}}
    moved = copy.deepcopy(old)
    moved["capture_builder_source_path"] = "/new/tool.py"
    moved["arms"]["COUPLED"]["manifest_path"] = "/new/manifest.json"
    assert capture_identity(old) == capture_identity(moved)
    moved["arms"]["COUPLED"]["manifest_sha256"] = "modified"
    assert capture_identity(old) != capture_identity(moved)
