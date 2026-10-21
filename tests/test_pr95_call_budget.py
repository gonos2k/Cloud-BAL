from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

MODULE = Path(__file__).resolve().parents[1] / "tools/pr95_call_budget.py"
sys.path.insert(0, str(MODULE.parent))
SPEC = importlib.util.spec_from_file_location("pr95_call_budget", MODULE)
budget = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(budget)


def test_bottom_phase_conversion_uses_source_density_factor_once():
    fall = np.array([[1.0, 2.0], [0.5, 0.0]])
    dz = np.array([2.0, 3.0])
    area = np.array([4.0, 5.0])

    mapped = budget._bottom_phase_mass(fall, dz, 900.0, 3.0, area)

    np.testing.assert_array_equal(mapped, [[24.0, 90.0], [12.0, 0.0]])


def test_recorded_signed_storage_term_is_subtracted_from_column_residual():
    residual = np.array([[10.0, -4.0]])
    numerical_delta = np.array([[2.0, -1.0]])

    np.testing.assert_array_equal(budget._remove_recorded_term(residual, numerical_delta),
                                  [[8.0, -3.0]])
    with pytest.raises(ValueError, match="matching finite shapes"):
        budget._remove_recorded_term(residual, np.zeros((2, 1)))


def test_executable_identity_must_match_run_and_build_receipts():
    digest = "a" * 64
    receipt = {"candidate_build": {"executable_sha256": digest},
               "executed_executable_sha256": digest,
               "expected_executed_executable_sha256": digest}

    assert budget._verify_executable_binding(receipt, {"executable_sha256": digest}) == digest
    receipt["executed_executable_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="does not match"):
        budget._verify_executable_binding(receipt, {"executable_sha256": digest})


def test_transition_reducer_includes_every_loop_of_first_public_call(tmp_path):
    path = tmp_path / "transition.raw"
    path.write_text(
        "PR85_ICE_TRANSITION_LOOP 1 7 10 10 1 1 20\n"
        "PR85_ICE_TRANSITION 10 7 1 1 20 270 270 0.1 0.20 0.30 1.0 "
        "0.20 0.20 0.31 0.19 0.315 1.0\n"
        "PR85_ICE_TRANSITION_LOOP 2 7 10 10 1 1 20\n"
        "PR85_ICE_TRANSITION 10 7 1 2 20 270 270 0.1 0.20 0.30 1.0 "
        "0.20 0.20 0.40 0.10 0.50 1.0\n")
    bounds = {"its": 10, "ite": 10, "jts": 7, "jte": 7, "kts": 1, "kte": 1}

    delta, count = budget._first_call_transition(path, bounds, np.full((1, 1, 1), 2.0), 20.0)

    assert count == 2
    assert delta[0, 0, 0] == pytest.approx(0.21)


def test_transition_reducer_rejects_event_outside_captured_geometry(tmp_path):
    path = tmp_path / "transition.raw"
    path.write_text(
        "PR85_ICE_TRANSITION_LOOP 1 7 10 10 1 1 20\n"
        "PR85_ICE_TRANSITION 11 7 1 1 20 270 270 0.1 0.20 0.30 1.0 "
        "0.20 0.20 0.31 0.19 0.315 1.0\n")
    bounds = {"its": 10, "ite": 10, "jts": 7, "jte": 7, "kts": 1, "kte": 1}

    with pytest.raises(ValueError, match="outside the captured KDM6 tile"):
        budget._first_call_transition(path, bounds, np.ones((1, 1, 1)), 20.0)


def test_stage_comparison_uses_canonical_float32_bytes():
    assert budget._same_float32_bytes(np.array([1.0, 0.0], dtype="f4"),
                                      np.array([1.0, 0.0], dtype=">f4"))
    assert not budget._same_float32_bytes(np.array([0.0], dtype="f4"),
                                          np.array([-0.0], dtype=">f4"))
    assert not budget._same_float32_bytes(np.array([np.nan], dtype="f4"),
                                          np.array([np.nan], dtype=">f4"))


def test_statistics_label_2d_inputs_as_columns_only():
    result = budget._stats(np.array([[1.0, -2.0]]))
    assert result == {"signed_kg": -1.0, "L1_column_kg": 3.0,
                      "max_abs_column_kg": 2.0}
