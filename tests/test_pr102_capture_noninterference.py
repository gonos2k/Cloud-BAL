from pathlib import Path
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr102_capture_noninterference import (  # noqa: E402
    BASE_C2_EXE_SHA256,
    BOUNDARY_SHA256,
    DIAGNOSTIC_EXE_SHA256,
    N_INPUT_SHA256,
    _valid_closed_receipt,
    require_one_step_timestamp,
)


def closed_n_receipt(*, diagnostic=False):
    return {
        "status": "COMPLETE",
        "returncode": 0,
        "arm": "STRUCTURED_CAPTURE" if diagnostic else "STRUCTURED_BASELINE20",
        "candidate_wrfinput_sha256": N_INPUT_SHA256,
        "candidate_wrfbdy_sha256": BOUNDARY_SHA256,
        "candidate_input_unchanged": True,
        "changed_original_inputs": [],
        "changed_staged_inputs": [],
        "processing_errors": [],
        "earliest_fatal": None,
        "fatal_lines": [],
        "executed_executable_sha256": DIAGNOSTIC_EXE_SHA256 if diagnostic else BASE_C2_EXE_SHA256,
        "timestep_count": 1,
        "final_completed_step": 1,
        "expected_model_timestamps": ["2026-08-16_13:00:20"],
        "model_timestamps": [{"timestamp": "2026-08-16_13:00:20"}],
    }


def write_receipt(root: Path, receipt: dict) -> Path:
    root.mkdir()
    path = root / "receipt.json"
    path.write_text(json.dumps(receipt))
    return root


def test_candidate_n_pair_receipt_accepts_exact_closed_identity(tmp_path: Path):
    control_root = write_receipt(tmp_path / "control", closed_n_receipt())
    diagnostic_root = write_receipt(tmp_path / "diagnostic", closed_n_receipt(diagnostic=True))

    control = _valid_closed_receipt(
        control_root, "N", control=True, expected_arm="STRUCTURED_BASELINE20",
        expected_input=N_INPUT_SHA256, expected_steps=1, expected_executable=BASE_C2_EXE_SHA256)
    diagnostic = _valid_closed_receipt(
        diagnostic_root, "N", control=False, expected_arm="STRUCTURED_CAPTURE",
        expected_input=N_INPUT_SHA256, expected_steps=1, expected_executable=DIAGNOSTIC_EXE_SHA256)
    require_one_step_timestamp(control)
    require_one_step_timestamp(diagnostic)


@pytest.mark.parametrize("field,value", [
    ("candidate_wrfinput_sha256", "wrong-input"),
    ("executed_executable_sha256", "wrong-executable"),
    ("timestep_count", 2),
])
def test_candidate_n_pair_rejects_input_executable_or_step_mismatch(tmp_path: Path,
                                                                     field: str,
                                                                     value):
    receipt = closed_n_receipt(diagnostic=True)
    receipt[field] = value
    root = write_receipt(tmp_path / "diagnostic", receipt)

    with pytest.raises(ValueError):
        _valid_closed_receipt(
            root, "N", control=False, expected_arm="STRUCTURED_CAPTURE",
            expected_input=N_INPUT_SHA256, expected_steps=1,
            expected_executable=DIAGNOSTIC_EXE_SHA256)


def test_candidate_n_pair_rejects_wrong_first_model_time():
    receipt = closed_n_receipt()
    receipt["model_timestamps"] = [{"timestamp": "2026-08-16_13:00:40"}]

    with pytest.raises(ValueError, match="first 20-second"):
        require_one_step_timestamp(receipt)
