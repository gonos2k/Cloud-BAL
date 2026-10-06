#!/usr/bin/env python3
"""Contract tests for the explicit, source-bounded PR61 research prior."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import initialize_native_moments as initializer  # noqa: E402
import native_kdm6_trace  # noqa: E402


class NativeMomentInitializationTests(unittest.TestCase):
    def _write_small_input(self, path: Path) -> None:
        with Dataset(path, "w") as dataset:
            dataset.createDimension("Time", 1)
            dataset.createDimension("bottom_top", 3)
            dataset.createDimension("south_north", 3)
            dataset.createDimension("west_east", 3)
            dataset.createDimension("DateStrLen", 19)
            dataset.MP_PHYSICS = 37
            times = dataset.createVariable("Times", "S1", ("Time", "DateStrLen"))
            times[0] = np.asarray(list(b"2026-08-16_12:00:00"), dtype="S1")
            for name in (
                "QCLOUD", "QICE", "QRAIN", "QGRAUP", "QNCLOUD", "QNICE",
                "QNRAIN", "QIB", "QNCCN",
            ):
                variable = dataset.createVariable(name, "f4", initializer.DIMENSIONS)
                variable[:] = np.zeros((1, 3, 3, 3), dtype=np.float32)
            dataset["QRAIN"][0, 1, 1, 1] = 1.0e-6

    def test_prior_fills_only_eligible_cells_and_exposes_cap_infeasibility(self):
        mass = np.array([1.0e-3, 1.0e-15, 1.0e-2], dtype=np.float32)
        old = np.zeros(3, dtype=np.float32)
        density = np.array([1.0, 1.0, 1.0e8], dtype=np.float32)
        result, report = initializer._prepare_moments(
            mass, old, density,
            threshold=1.0e-15, lambda_min=10.0, lambda_max=100.0,
            power=3, pidn=1.0, internal_cap=1.0e6,
        )
        self.assertGreater(result[0], 0.0)
        self.assertEqual(result[1], 0.0)  # Declared strict threshold.
        self.assertEqual(result[2], 0.0)  # Source-cap-infeasible; never replaced.
        self.assertEqual(report["initialized_cells"], 1)
        self.assertEqual(report["left_unchanged_infeasible_cells"], 1)
        self.assertLessEqual(result[0] * density[0], np.float32(1.0e6))

    def test_empty_validation_mask_is_not_reported_as_pass(self):
        report = initializer._validate_mass_prior(
            np.array([0.0]), np.array([0.0]), np.array([False]),
            m_min=1.0e-15, m_max=1.0e-12, bound_source="test source",
        )
        self.assertEqual(report["status"], "NOT_RUN")
        self.assertEqual(report["checked_count"], 0)

    def test_policy_file_is_bound_to_the_implementation_declarations(self):
        if initializer.EXPECTED_POLICY_SHA256 == "POLICY_HASH_PENDING":
            self.fail("Policy SHA-256 has not been frozen")
        policy = initializer._validate_policy_file(initializer.DEFAULT_POLICY)
        self.assertTrue(policy["declared_before_experiment"])
        self.assertEqual(policy["policy_id"], "PSD_PRIOR_RESEARCH_20261006")
        with tempfile.TemporaryDirectory() as temporary_directory:
            altered = Path(temporary_directory) / "altered-policy.json"
            altered.write_bytes(initializer.DEFAULT_POLICY.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                initializer.InitializationError, "POLICY_HASH_MISMATCH"
            ):
                initializer._validate_policy_file(altered)
            altered.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(
                initializer.InitializationError, "POLICY_ROOT_MUST_BE_OBJECT"
            ):
                initializer._validate_policy_file(altered)

    def test_receipt_temp_failure_removes_candidate_and_all_temporary_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.nc"
            output = root / "candidate.nc"
            receipt = root / "receipt.json"
            trace_path = root / "trace.bin"
            self._write_small_input(source)
            source_hash = initializer.file_sha256(source)
            bounds = {"its": 1, "ite": 1, "jts": 1, "jte": 1,
                      "kts": 1, "kte": 3}
            trace = {
                "stage": 1,
                "itimestep": 1,
                "sha256": "a" * 64,
                "bounds": bounds,
                "active_shape_xyz": [1, 1, 3],
                "fields": {"DEN": np.ones((1, 3, 1), dtype=np.float32)},
            }
            real_mkstemp = initializer.tempfile.mkstemp
            calls = 0

            def fail_receipt_temp(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("forced receipt tempfile failure")
                return real_mkstemp(*args, **kwargs)

            with (
                mock.patch.object(initializer, "EXPECTED_INPUT_SHA256", source_hash),
                mock.patch.object(initializer, "EXPECTED_TRACE_SHA256", trace["sha256"]),
                mock.patch.object(initializer, "EXPECTED_TRACE_BOUNDS", bounds),
                mock.patch.object(initializer, "_validate_policy_file",
                                  return_value={"policy_id": "test"}),
                mock.patch.object(initializer, "_verify_source_identities"),
                mock.patch.object(initializer, "_check_input_metadata"),
                mock.patch.object(native_kdm6_trace, "read_dump", return_value=trace),
                mock.patch.object(initializer.tempfile, "mkstemp",
                                  side_effect=fail_receipt_temp),
            ):
                with self.assertRaisesRegex(OSError, "forced receipt tempfile failure"):
                    initializer.initialize_copy(source, output, trace_path, receipt)

            self.assertFalse(output.exists())
            self.assertFalse(receipt.exists())
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["source.nc"])

            successful_output = root / "successful-candidate.nc"
            successful_receipt = root / "successful-receipt.json"
            with (
                mock.patch.object(initializer, "EXPECTED_INPUT_SHA256", source_hash),
                mock.patch.object(initializer, "EXPECTED_TRACE_SHA256", trace["sha256"]),
                mock.patch.object(initializer, "EXPECTED_TRACE_BOUNDS", bounds),
                mock.patch.object(initializer, "_validate_policy_file",
                                  return_value={"policy_id": "test"}),
                mock.patch.object(initializer, "_verify_source_identities"),
                mock.patch.object(initializer, "_check_input_metadata"),
                mock.patch.object(native_kdm6_trace, "read_dump", return_value=trace),
            ):
                receipt_data = initializer.initialize_copy(
                    source, successful_output, trace_path, successful_receipt
                )

            code_hash = initializer.file_sha256(
                Path(initializer.__file__).resolve()
            )
            self.assertEqual(receipt_data["initializer_sha256_before"], code_hash)
            self.assertEqual(receipt_data["initializer_sha256_after"], code_hash)
            self.assertTrue(receipt_data["initializer_unchanged_during_initialization"])
            self.assertEqual(
                initializer.file_sha256(successful_output),
                receipt_data["output_input_sha256"],
            )
            self.assertEqual(
                successful_receipt.read_text(encoding="utf-8"),
                json.dumps(
                    receipt_data, indent=2, sort_keys=True, allow_nan=False
                ) + "\n",
            )

            existing_bytes = b"preserve existing candidate"
            successful_output.write_bytes(existing_bytes)
            with (
                mock.patch.object(initializer, "EXPECTED_INPUT_SHA256", source_hash),
                mock.patch.object(initializer, "EXPECTED_TRACE_SHA256", trace["sha256"]),
                mock.patch.object(initializer, "EXPECTED_TRACE_BOUNDS", bounds),
                mock.patch.object(initializer, "_validate_policy_file",
                                  return_value={"policy_id": "test"}),
                mock.patch.object(initializer, "_verify_source_identities"),
                mock.patch.object(initializer, "_check_input_metadata"),
                mock.patch.object(native_kdm6_trace, "read_dump", return_value=trace),
            ):
                with self.assertRaisesRegex(
                    initializer.InitializationError,
                    "OUTPUT_AND_RECEIPT_MUST_BE_NEW_PATHS",
                ):
                    initializer.initialize_copy(
                        source, successful_output, trace_path, successful_receipt
                    )
            self.assertEqual(successful_output.read_bytes(), existing_bytes)

            failed_output = root / "link-failure-candidate.nc"
            failed_receipt = root / "link-failure-receipt.json"
            real_link = initializer.os.link
            link_calls = 0

            def fail_receipt_link(source_path, destination_path):
                nonlocal link_calls
                link_calls += 1
                if link_calls == 2:
                    raise OSError("forced receipt link failure")
                return real_link(source_path, destination_path)

            with (
                mock.patch.object(initializer, "EXPECTED_INPUT_SHA256", source_hash),
                mock.patch.object(initializer, "EXPECTED_TRACE_SHA256", trace["sha256"]),
                mock.patch.object(initializer, "EXPECTED_TRACE_BOUNDS", bounds),
                mock.patch.object(initializer, "_validate_policy_file",
                                  return_value={"policy_id": "test"}),
                mock.patch.object(initializer, "_verify_source_identities"),
                mock.patch.object(initializer, "_check_input_metadata"),
                mock.patch.object(native_kdm6_trace, "read_dump", return_value=trace),
                mock.patch.object(initializer.os, "link", side_effect=fail_receipt_link),
            ):
                with self.assertRaisesRegex(OSError, "forced receipt link failure"):
                    initializer.initialize_copy(
                        source, failed_output, trace_path, failed_receipt
                    )
            self.assertFalse(failed_output.exists())
            self.assertFalse(failed_receipt.exists())
            self.assertEqual(list(root.glob(".link-failure-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
