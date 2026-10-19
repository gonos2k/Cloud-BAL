"""Tests for saved-state ProgB graupel activity classification."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr87_graupel_activity_audit as audit


def state(qg: list[float], bg: list[float], den: list[float] | None = None) -> dict:
    return {
        "timestep": 3, "stage": "PRE_KDM6", "rkstep": 0,
        "bounds": {"its": 10, "jts": 20, "kts": 1},
        "fields": {
            "QG": np.asarray(qg, dtype=np.float32).reshape(1, 1, -1),
            "BG": np.asarray(bg, dtype=np.float32).reshape(1, 1, -1),
            "DEN": np.asarray(den if den is not None else [0.7] * len(qg), dtype=np.float32).reshape(1, 1, -1),
        },
    }


class GraupelActivityAuditTest(unittest.TestCase):
    def test_classifies_source_absent_transient_active_and_density_gates(self):
        record = state([0, 8.0841117220537e-13, 4e-12, 1e-4],
                       [0, 9.122162618311366e-16, 1e-14, 1e-7])
        result = audit.classify_state(record)
        self.assertEqual(result["counts"], {
            "ABSENT": 1, "TRANSIENT": 1, "ACTIVE_GATES_PASS": 1,
            "UNSUPPORTED_PAIR": 0, "UNSUPPORTED_DENSITY": 1,
        })
        first = result["first_by_class"]["TRANSIENT"]
        self.assertEqual(first["indices_ijk"], {"i": 11, "j": 20, "k": 1})
        self.assertEqual(first["QG"]["float32_bits"], "0x2b638c2a")
        self.assertEqual(first["BG"]["float32_bits"], "0x268376d7")

    def test_orphan_negative_and_nonfinite_pairs_are_unsupported(self):
        result = audit.classify_state(state([1e-6, 0, -1, float("nan")], [0, 1e-6, 1e-8, 1e-8]))
        self.assertEqual(result["counts"]["UNSUPPORTED_PAIR"], 4)
        self.assertEqual(result["stored_pair"]["nonfinite_qg_or_bg_cells"], 1)
        self.assertEqual(result["stored_pair"]["orphan_or_negative_pair_cells"], 4)

    def test_raw_density_bounds_are_inclusive(self):
        result = audit.classify_state(state([100, 900], [1, 1]))
        self.assertEqual(result["counts"]["ACTIVE_GATES_PASS"], 2)

    def test_rejects_mismatched_field_shapes(self):
        record = state([1e-6], [1e-8])
        record["fields"]["DEN"] = np.zeros((1, 1, 2), dtype=np.float32)
        with self.assertRaises(audit.ActivityAuditError):
            audit.classify_state(record)

    def test_source_hash_is_required_for_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "module_mp_kdm6.F"
            source.write_text("not the frozen source", encoding="utf-8")
            with self.assertRaises(audit.ActivityAuditError):
                audit.audit(Path("missing-trace"), source)


if __name__ == "__main__":
    unittest.main()
