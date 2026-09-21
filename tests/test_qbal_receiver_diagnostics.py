#!/usr/bin/env python3
"""Independent geometric tests for the Q-BAL receiver diagnostic."""

from __future__ import annotations

from dataclasses import replace
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnose_qbal_boundary as boundary  # noqa: E402
import diagnose_qbal_receivers as diagnostic  # noqa: E402


SHAPE = (4, 4, 4)
ACTIVE = np.asarray(((2, 2, 2), (2, 2, 4), (3, 2, 2)), dtype=np.int32)


def make_fixture() -> tuple[boundary.Snapshot, boundary.SparseRows]:
    """Make three active rows with two unique receivers and one shared receiver."""

    beta = np.zeros(SHAPE, dtype=np.float32)
    for i, j, k in ACTIVE:
        beta[i - 1, j - 1, k - 1] = 1.0
    fields = [np.zeros(SHAPE, dtype=np.float32) for _ in range(3)]
    # A's upper omega face and C's upper omega face have distinct receivers.
    # A's receiver is also reached by B's lower omega face.
    fields[2][1, 1, 1] = 1.0
    fields[2][1, 1, 2] = 0.0
    fields[2][2, 1, 1] = 0.0
    dimensions = SHAPE
    dx = np.full((4, 4), 10.0, dtype=np.float32)
    ps = np.full((4, 4), 1000.0, dtype=np.float32)
    pressure = np.asarray((500.0, 400.0, 300.0, 200.0), dtype=np.float32)
    snapshot = boundary.Snapshot(
        dimensions=dimensions,
        relaxation_tolerance=1.0,
        multiplier=np.zeros(SHAPE, dtype=np.float32),
        legacy_rhs=np.zeros(SHAPE, dtype=np.float32),
        erru=np.ones(SHAPE, dtype=np.float32),
        beta=beta,
        tau=np.ones((4, 4), dtype=np.float32),
        dx=dx,
        dy=dx.copy(),
        ps=ps,
        p=pressure,
        dp=np.ones(4, dtype=np.float32),
        u=fields[0],
        v=fields[1],
        w=fields[2],
        raw_sha256="receiver-test-snapshot",
    )
    coefficients = np.zeros((len(ACTIVE), 6), dtype=np.float64)
    rhs = -diagnostic.divergence(snapshot, (snapshot.u, snapshot.v, snapshot.w), ACTIVE)
    rows = boundary.SparseRows(
        dimensions=dimensions,
        ijk=ACTIVE.copy(),
        rhs=rhs,
        coefficients=coefficients,
        raw_sha256="receiver-test-rows",
    )
    return snapshot, rows


def candidate_for(snapshot: boundary.Snapshot, *, shared: float = 0.0,
                  separate: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    candidate = tuple(np.array(field, copy=True) for field in (snapshot.u, snapshot.v, snapshot.w))
    candidate[2][1, 1, 1] = np.float32(shared)
    candidate[2][1, 1, 2] = np.float32(0.0)
    candidate[2][2, 1, 1] = np.float32(separate)
    return candidate


class ReceiverDiagnosticTests(unittest.TestCase):
    def test_inventory_deduplicates_shared_receiver_and_couples_components(self) -> None:
        snapshot, rows = make_fixture()
        _, labels, source, direction, stored, receiver, receiver_index = diagnostic.receiver_inventory(
            snapshot, rows
        )

        np.testing.assert_array_equal(receiver, np.asarray(((2, 2, 3), (3, 2, 3)), dtype=np.int32))
        np.testing.assert_array_equal(receiver_index, np.asarray((0, 1, 0), dtype=np.int64))
        self.assertEqual(set(direction.tolist()), {4, 5})
        self.assertEqual(len(source), 3)
        active_group, receiver_group = diagnostic.coupled_groups(
            labels, source, receiver_index, len(receiver)
        )
        self.assertEqual(len(np.unique(active_group)), 2)
        self.assertEqual(active_group[0], active_group[1])
        self.assertEqual(active_group[0], receiver_group[0])

    def test_audit_closes_shared_face_and_reports_before_delta_after(self) -> None:
        snapshot, rows = make_fixture()
        summary, payload = diagnostic.audit(snapshot, rows, candidate_for(snapshot))

        np.testing.assert_allclose(
            payload["receiver_before"] + payload["receiver_delta"],
            payload["receiver_after"],
        )
        np.testing.assert_allclose(payload["receiver_before"], [1.0, 0.0])
        np.testing.assert_allclose(payload["receiver_delta"], [-1.0, 2.0])
        np.testing.assert_allclose(payload["receiver_after"], [0.0, 2.0])
        self.assertAlmostEqual(summary["shared_face_closure"], 0.0)
        self.assertAlmostEqual(
            summary["active_weighted_change"] + summary["receiver_weighted_change"],
            0.0,
        )
        self.assertEqual(summary["changed_faces_uvomega"], [0, 0, 2])
        self.assertEqual(summary["receiver_changed"], 2)
        self.assertEqual(summary["improved_abs"], 1)
        self.assertEqual(summary["worsened_abs"], 1)
        self.assertGreater(summary["after"]["rms"], summary["before"]["rms"])

    def test_zero_demand_has_zero_necessary_bounds(self) -> None:
        result = diagnostic.necessary_bounds(0.0, 0.0, 10.0)
        self.assertEqual(result["delta_inf_lower_bound"], 0.0)
        self.assertEqual(result["final_inf_lower_bound"], 0.0)
        self.assertFalse(result["missing_receiver_for_nonzero_demand"])

    def test_nonzero_demand_has_relative_delta_and_final_lower_bounds(self) -> None:
        result = diagnostic.necessary_bounds(4.0, 1.0, 10.0)
        self.assertAlmostEqual(result["delta_inf_lower_bound"], 0.4)
        self.assertAlmostEqual(result["final_inf_lower_bound"], 0.3)
        self.assertAlmostEqual(result["required_final_sum"], -3.0)

    def test_hypothetical_float32_face_changes_are_accepted(self) -> None:
        snapshot, rows = make_fixture()
        _, _, _, _, stored, _, _ = diagnostic.receiver_inventory(snapshot, rows)
        masks, counts = diagnostic.validate_candidate(
            snapshot, rows, candidate_for(snapshot), stored
        )
        self.assertEqual(counts, [0, 0, 2])
        self.assertTrue(masks[2][1, 1, 1])
        self.assertTrue(masks[2][2, 1, 1])

    def test_candidate_shape_is_rejected(self) -> None:
        snapshot, rows = make_fixture()
        _, _, _, _, stored, _, _ = diagnostic.receiver_inventory(snapshot, rows)
        candidate = list(candidate_for(snapshot))
        candidate[0] = np.zeros((3, 4, 4), dtype=np.float32)
        with self.assertRaisesRegex(ValueError, "matching shape"):
            diagnostic.validate_candidate(snapshot, rows, tuple(candidate), stored)

    def test_candidate_dtype_is_rejected(self) -> None:
        snapshot, rows = make_fixture()
        _, _, _, _, stored, _, _ = diagnostic.receiver_inventory(snapshot, rows)
        candidate = list(candidate_for(snapshot))
        candidate[2] = candidate[2].astype(np.float64)
        with self.assertRaisesRegex(ValueError, "float32"):
            diagnostic.validate_candidate(snapshot, rows, tuple(candidate), stored)

    def test_nonfinite_candidate_is_rejected(self) -> None:
        snapshot, rows = make_fixture()
        _, _, _, _, stored, _, _ = diagnostic.receiver_inventory(snapshot, rows)
        candidate = list(candidate_for(snapshot))
        candidate[2][1, 1, 1] = np.nan
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            diagnostic.validate_candidate(snapshot, rows, tuple(candidate), stored)

    def test_candidate_sentinel_mask_is_frozen(self) -> None:
        snapshot, rows = make_fixture()
        _, _, _, _, stored, _, _ = diagnostic.receiver_inventory(snapshot, rows)
        candidate = list(candidate_for(snapshot))
        candidate[2][1, 1, 1] = diagnostic.boundary.SENTINEL
        with self.assertRaisesRegex(ValueError, "sentinel mask"):
            diagnostic.validate_candidate(snapshot, rows, tuple(candidate), stored)

    def test_face_outside_hypothetical_set_is_rejected(self) -> None:
        snapshot, rows = make_fixture()
        _, _, _, _, stored, _, _ = diagnostic.receiver_inventory(snapshot, rows)
        candidate = list(candidate_for(snapshot))
        candidate[0][0, 0, 0] = np.float32(1.0)
        with self.assertRaisesRegex(ValueError, "outside the hypothetical set"):
            diagnostic.validate_candidate(snapshot, rows, tuple(candidate), stored)

    def test_signed_zero_change_on_frozen_face_is_rejected(self) -> None:
        snapshot, rows = make_fixture()
        _, _, _, _, stored, _, _ = diagnostic.receiver_inventory(snapshot, rows)
        candidate = list(candidate_for(snapshot))
        candidate[0][0, 0, 0] = np.float32(-0.0)
        with self.assertRaisesRegex(ValueError, "outside the hypothetical set"):
            diagnostic.validate_candidate(snapshot, rows, tuple(candidate), stored)

    def test_altered_rhs_is_rejected_against_snapshot_divergence(self) -> None:
        snapshot, rows = make_fixture()
        altered_rhs = rows.rhs.copy()
        altered_rhs[0] += 1.0e-4
        altered_rows = replace(rows, rhs=altered_rhs)
        with self.assertRaisesRegex(ValueError, "RHS"):
            diagnostic.audit(snapshot, altered_rows, candidate_for(snapshot))

    def test_dx_dy_metric_mismatch_is_rejected(self) -> None:
        snapshot, rows = make_fixture()
        dy = snapshot.dy.copy()
        dy[1, 1] += 1.0
        with self.assertRaisesRegex(ValueError, "dx=dy"):
            diagnostic.receiver_inventory(replace(snapshot, dy=dy), rows)

    def test_exported_active_mask_must_match_beta_support(self) -> None:
        snapshot, rows = make_fixture()
        beta = snapshot.beta.copy()
        beta[1, 1, 1] = 0.0
        with self.assertRaisesRegex(ValueError, "active rows differ"):
            diagnostic.receiver_inventory(replace(snapshot, beta=beta), rows)

    def test_empty_receiver_set_reports_nonzero_demand_obstruction(self) -> None:
        snapshot, rows = make_fixture()
        # Keep active levels above the surface while placing the intermediate
        # receiver level below it. This leaves the exported active mask valid
        # but removes every valid receiver from the hypothetical set.
        no_receiver = replace(
            snapshot,
            ps=np.full((4, 4), 200.0, dtype=np.float32),
            p=np.asarray((500.0, 100.0, 300.0, 100.0), dtype=np.float32),
        )
        unchanged = tuple(np.array(field, copy=True) for field in (no_receiver.u, no_receiver.v, no_receiver.w))
        summary, payload = diagnostic.audit(no_receiver, rows, unchanged)
        self.assertEqual(payload["receiver_ijk"].shape, (0, 3))
        self.assertTrue(summary["exact_active_target_bounds"]["missing_receiver_for_nonzero_demand"])


if __name__ == "__main__":
    unittest.main()
