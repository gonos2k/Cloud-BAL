#!/usr/bin/env python3
"""Focused synthetic tests for the same-call KDM6 budget diagnostic."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixtures = load_module("native_geometry_test_fixtures", ROOT / "tests" / "test_native_kdm6_call_geometry.py")
budget = load_module("pr65_samecall_budget_audit", ROOT / "tools" / "pr65_samecall_budget_audit.py")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_receipt_output_hash(receipt_path: Path, artifact: Path) -> None:
    receipt = json.loads(receipt_path.read_text())
    row = next(item for item in receipt["outputs"] if item["path"] == artifact.name)
    row["sha256"] = sha256(artifact)
    receipt_path.write_text(json.dumps(receipt))


def set_first_active_qc(post_path: Path, value: float, *, i_offset: int = 0) -> None:
    data = bytearray(post_path.read_bytes())
    offset = 8 + 20 * 4 + 5 * 4
    for name in fixtures.TRACE_FIELDS_3D:
        field_data = offset + 8
        if name == "QC":
            # The serialized field shape is (j,k,i)=(2,3,2), C order.
            element = i_offset
            struct.pack_into(">f", data, field_data + element * 4, value)
            post_path.write_bytes(data)
            return
        offset = field_data + 2 * 3 * 2 * 4
    raise AssertionError("QC field is missing from synthetic KDM trace")


class PR65SameCallBudgetAuditTests(unittest.TestCase):
    def test_audit_reports_water_storage_and_separates_den_delz_measures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            geometry, pre, post, receipt = fixtures.audit_fixture(
                root, dtm=20.0, grid_dt=25.0, kdm_dt=20.0,
            )
            executable = root / "wrf.exe"
            expected_executable_sha = hashlib.sha256(executable.read_bytes()).hexdigest()
            result = budget.audit(geometry, pre, post, receipt, expected_executable_sha)

        self.assertEqual(result["schema"], "pr65_samecall_kdm6_water_budget_audit_v1")
        self.assertEqual(result["total_water"]["closure"].split(":", 1)[0], "OPEN")
        self.assertEqual(result["total_water"]["relative_delta"], 0.0)
        measures = result["integrated_measures"]
        self.assertIn("pre", measures["DEN_DELZ_diagnostic"])
        self.assertIn("post", measures["DEN_DELZ_diagnostic"])
        self.assertIn("legacy_geometry_audit_float32_product_kg",
                      measures["DEN_DELZ_precision_comparison"])
        self.assertIn("promoted_float64_product_kg",
                      measures["DEN_DELZ_precision_comparison"])
        self.assertEqual(result["temperature_change_diagnostic"]["energy_closure"].split(":", 1)[0], "OPEN")

    def test_relative_change_is_undefined_for_zero_baseline(self) -> None:
        self.assertIsNone(budget._relative_delta(0.0, 0.0))
        with self.assertRaisesRegex(ValueError, "must be finite"):
            budget._relative_delta(float("nan"), 0.0)

    def test_nonzero_qc_storage_change_matches_independent_pressure_measure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            geometry, pre, post, receipt = fixtures.audit_fixture(
                root, dtm=20.0, grid_dt=25.0, kdm_dt=20.0,
            )
            arrays = {name: value.copy() for name, value in fixtures.ARRAYS.items()}
            arrays["c1h"][:] = -1.0
            arrays["c3f"][:] = (1.0, 0.5, 0.0)
            arrays["msftx"] = np.array([[1.0, 2.0], [1.0, 4.0]])
            geometry.write_bytes(
                fixtures.encode_record(fixtures.STAGES[0], arrays=arrays, dtm=20.0, dt=25.0)
                + fixtures.encode_record(fixtures.STAGES[1], arrays=arrays, dtm=20.0, dt=25.0)
            )
            # Change the second i-cell in the first active k/j row.
            set_first_active_qc(post, 0.5, i_offset=1)
            refresh_receipt_output_hash(receipt, geometry)
            refresh_receipt_output_hash(receipt, post)
            expected_executable_sha = sha256(root / "wrf.exe")
            result = budget.audit(geometry, pre, post, receipt, expected_executable_sha)

            # Independent interface-pressure difference and area calculation.
            mu = arrays["mu2"][1, 0]
            mub = arrays["mub"][1, 0]
            dp = ((arrays["c3f"][0] * (mu + mub) + arrays["c4f"][0] + 5000.0)
                  - (arrays["c3f"][1] * (mu + mub) + arrays["c4f"][1] + 5000.0))
            area = 5000.0 * 5000.0 / (arrays["msftx"][1, 0] * arrays["msfty"][1, 0])
            gravity = float(np.float32(9.81))
            expected_delta_kg = -0.5 * dp * area / gravity

        self.assertLess(result["total_water"]["delta_kg"], 0.0)
        self.assertAlmostEqual(result["species_mass_changes"]["QC"]["delta_mass_kg"],
                               expected_delta_kg, delta=abs(expected_delta_kg) * 1.0e-12)
        self.assertAlmostEqual(result["total_water"]["delta_kg"], expected_delta_kg,
                               delta=abs(expected_delta_kg) * 1.0e-12)

    def test_fixed_carrier_scope_rejects_changed_post_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            geometry, pre, post, receipt = fixtures.audit_fixture(
                root, dtm=20.0, grid_dt=25.0, kdm_dt=20.0,
            )
            changed = {name: value.copy() for name, value in fixtures.ARRAYS.items()}
            changed["c1h"][:] = -1.0
            changed["c3f"][:] = (1.0, 0.5, 0.0)
            post_arrays = {name: value.copy() for name, value in changed.items()}
            post_arrays["mu1"][0, 0] += 1.0
            geometry.write_bytes(
                fixtures.encode_record(fixtures.STAGES[0], arrays=changed, dtm=20.0, dt=25.0)
                + fixtures.encode_record(fixtures.STAGES[1], arrays=post_arrays, dtm=20.0, dt=25.0)
            )
            refresh_receipt_output_hash(receipt, geometry)
            expected_executable_sha = sha256(root / "wrf.exe")
            with self.assertRaisesRegex(ValueError, "changed across microphysics"):
                budget.audit(geometry, pre, post, receipt, expected_executable_sha)


if __name__ == "__main__":
    unittest.main()
