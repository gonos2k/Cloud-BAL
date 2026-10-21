from __future__ import annotations

import importlib.util
import datetime as dt
from pathlib import Path
from unittest.mock import patch

import numpy as np

MODULE = Path(__file__).resolve().parents[1] / "tools/pr94_hydro_response.py"
spec = importlib.util.spec_from_file_location("pr94_hydro_response", MODULE)
hydro = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(hydro)


def receipt(arm: str, *, executable: str = hydro.FROZEN_C4_EXECUTABLE,
            current_generation: bool = True) -> dict:
    timestamps = [(dt.datetime(2026, 8, 16, 13) + dt.timedelta(seconds=20 * step)).strftime("%Y-%m-%d_%H:%M:%S") for step in range(1, 31)]
    result = {
        "arm": arm, "status": "COMPLETE", "returncode": 0,
        "final_completed_step": 30,
        "executed_executable_sha256": executable,
        "expected_executed_executable_sha256": executable,
        "candidate_wrfbdy_sha256": "bdy-sha",
        "candidate_namelist_sha256": "same-physics-namelist",
        "candidate_wrfinput_sha256": {"OFF": "off-sha", "COUPLED": "coupled-sha",
                                       "HYDRO": "hydro-sha"}[arm],
        "model_timestamps": [{"timestamp": value} for value in timestamps],
        "expected_model_timestamps": timestamps,
    }
    if arm == "HYDRO":
        result["candidate_input_binding"] = {
            "comparison_contract": {"current_generation": current_generation},
            "artifacts": {"wrfinput": {"sha256": "hydro-sha"},
                          "wrfbdy": {"sha256": "bdy-sha"}},
        }
    return result


def valid_triplet() -> dict:
    return {arm: receipt(arm) for arm in ("OFF", "COUPLED", "HYDRO")}


def test_receipt_triplet_accepts_closed_same_c4_current_generation_inputs() -> None:
    with patch.object(hydro, "_input_binding_unchanged", return_value=True):
        hydro.validate_receipt_triplet(valid_triplet())


def test_receipt_triplet_rejects_wrong_hydro_generation() -> None:
    receipts = valid_triplet()
    receipts["HYDRO"] = receipt("HYDRO", current_generation=False)

    with np.testing.assert_raises_regex(ValueError, "current-generation"):
        hydro.validate_receipt_triplet(receipts)


def test_receipt_triplet_rejects_unmatched_hydro_boundary() -> None:
    receipts = valid_triplet()
    receipts["HYDRO"]["candidate_input_binding"]["artifacts"]["wrfbdy"]["sha256"] = "other-bdy"

    with np.testing.assert_raises_regex(ValueError, "boundary"):
        hydro.validate_receipt_triplet(receipts)


def test_receipt_triplet_rejects_diagnostic_or_other_executable() -> None:
    receipts = valid_triplet()
    receipts["HYDRO"] = receipt("HYDRO", executable="compact-overlay-sha")

    with np.testing.assert_raises_regex(ValueError, "expected executable SHA-256"):
        hydro.validate_receipt_triplet(receipts)


def test_receipt_triplet_accepts_explicit_c1_executable() -> None:
    c1_sha = "a" * 64
    receipts = {arm: receipt(arm, executable=c1_sha)
                for arm in ("OFF", "COUPLED", "HYDRO")}

    with patch.object(hydro, "_input_binding_unchanged", return_value=True):
        hydro.validate_receipt_triplet(
            receipts, expected_executable_sha256=c1_sha)


def test_receipt_triplet_rejects_one_arm_executable_mismatch() -> None:
    c1_sha = "a" * 64
    receipts = {arm: receipt(arm, executable=c1_sha)
                for arm in ("OFF", "COUPLED", "HYDRO")}
    receipts["COUPLED"]["executed_executable_sha256"] = "b" * 64

    with np.testing.assert_raises_regex(ValueError, "expected executable SHA-256"):
        hydro.validate_receipt_triplet(
            receipts, expected_executable_sha256=c1_sha)


def test_receipt_triplet_rejects_invalid_expected_executable_sha256() -> None:
    with np.testing.assert_raises_regex(ValueError, "64 hexadecimal"):
        hydro.validate_receipt_triplet(
            valid_triplet(), expected_executable_sha256="not-a-sha")


def test_pointwise_three_arm_identity_is_checked_on_arrays() -> None:
    off = np.array([1.0, -2.0, 4.0])
    hydro_state = np.array([2.0, 3.0, -1.0])
    coupled = np.array([5.0, 1.0, 8.0])

    result = hydro.pointwise_decomposition(off, coupled, hydro_state)

    assert result["identity_holds_within_roundoff"]
    assert result["max_abs_identity_residual"] < 1e-14


def test_pointwise_decomposition_rejects_shape_mismatch() -> None:
    with np.testing.assert_raises_regex(ValueError, "identical shape"):
        hydro.pointwise_decomposition(np.zeros((2,)), np.zeros((2,)), np.zeros((3,)))


def test_receipt_triplet_rejects_changed_physics_namelist() -> None:
    receipts = valid_triplet()
    receipts["HYDRO"]["candidate_namelist_sha256"] = "other-physics"
    with np.testing.assert_raises_regex(ValueError, "namelist"):
        hydro.validate_receipt_triplet(receipts)


def test_receipt_triplet_rejects_consistently_relabelled_model_times() -> None:
    receipts = valid_triplet()
    for row in receipts.values():
        row["model_timestamps"] = [{"timestamp": f"step-{step}"} for step in range(1, 31)]
        row["expected_model_timestamps"] = [value["timestamp"] for value in row["model_timestamps"]]
    with np.testing.assert_raises_regex(ValueError, "30-step schedule"):
        hydro.validate_receipt_triplet(receipts)
