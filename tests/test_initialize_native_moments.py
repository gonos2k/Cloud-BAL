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

    def test_same13_prior_fills_positive_subthreshold_mass_without_a_floor(self):
        mass = np.array([1.0e-30, 0.0], dtype=np.float32)
        existing = np.zeros(2, dtype=np.float32)
        result, report = initializer._prepare_moments(
            mass, existing, np.ones(2, dtype=np.float32),
            threshold=0.0, lambda_min=1.0, lambda_max=100.0,
            power=3, pidn=1.0, internal_cap=1.0e6,
        )
        self.assertGreater(result[0], 0.0)
        self.assertEqual(result[1], 0.0)
        self.assertEqual(report["initialized_cells"], 1)
        self.assertEqual(report["research_fill_cutoff"], "strict mass > declared threshold")

    def test_same13_density_uses_real32_al_plus_alb_inverse(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "same13-density.nc"
            with Dataset(path, "w") as dataset:
                for name, length in zip(initializer.DIMENSIONS, (1, 2, 2, 2)):
                    dataset.createDimension(name, length)
                for name, value in (("AL", 2.0), ("ALB", 0.5)):
                    variable = dataset.createVariable(name, "f4", initializer.DIMENSIONS)
                    variable.units = "m3 kg-1"
                    variable[:] = value
                density = initializer._same13_dry_density(dataset)
        expected = np.float32(1.0) / (np.float32(2.0) + np.float32(0.5))
        np.testing.assert_array_equal(density, np.full((2, 2, 2), expected, dtype="f4"))

    def test_same13_preflight_rejects_mass_number_cap_conflict_without_mutation(self):
        shape = (1, 3, 3)
        arrays = {
            name: np.zeros(shape, dtype=np.float32)
            for name in (
                "QCLOUD", "QICE", "QRAIN", "QGRAUP", "QNCLOUD", "QNICE",
                "QNRAIN", "QIB", "QNCCN", "AL", "ALB",
            )
        }
        arrays["QICE"][0, 1, 1] = 1.0e-2
        before = {name: values.copy() for name, values in arrays.items()}
        with self.assertRaisesRegex(
            initializer.InitializationError, "PR83_SOURCE_CAP_INFEASIBLE:QNICE:1"
        ) as caught:
            initializer._same13_preflight(arrays, np.ones(shape, dtype=np.float32))
        self.assertEqual(
            caught.exception.diagnostics["QNICE"]["positive_mass_without_representable_moment"],
            1,
        )
        for name, values in arrays.items():
            np.testing.assert_array_equal(values, before[name])

    def test_same13_blocked_preflight_writes_receipt_without_candidate(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "same13-source.nc"
            output = root / "candidate.nc"
            receipt_path = root / "preflight.json"
            with Dataset(source, "w") as dataset:
                for name, length in zip(initializer.DIMENSIONS, (1, 3, 3, 3)):
                    dataset.createDimension(name, length)
                for name in (
                    "QCLOUD", "QICE", "QRAIN", "QGRAUP", "QNCLOUD", "QNICE",
                    "QNRAIN", "QIB", "QNCCN", "AL", "ALB",
                ):
                    variable = dataset.createVariable(name, "f4", initializer.DIMENSIONS)
                    variable.units = "m3 kg-1" if name in ("AL", "ALB", "QIB") else (
                        "kg-1" if name in ("QNCLOUD", "QNICE", "QNRAIN", "QNCCN")
                        else "kg kg-1"
                    )
                    variable[:] = 0.0
                dataset["QICE"][0, 1, 1, 1] = 1.0e-2
                dataset["AL"][:] = 1.0
            source_hash = initializer.file_sha256(source)
            with (
                mock.patch.object(initializer, "PR83_EXPECTED_INPUT_SHA256", source_hash),
                mock.patch.object(initializer, "_validate_same13_policy_file",
                                  return_value={"policy_id": "fixture-policy"}),
                mock.patch.object(initializer, "_same13_evidence_hashes",
                                  return_value={"fixture": "stable"}),
                mock.patch.object(initializer, "_check_same13_input_metadata"),
            ):
                result = initializer.initialize_same13_copy(
                    source, output, receipt_path,
                    policy_path=initializer.DEFAULT_PR83_POLICY,
                )
            self.assertEqual(result["status"], "BLOCKED_SOURCE_CAP_INFEASIBLE")
            self.assertFalse(output.exists())
            self.assertTrue(result["source_input_unchanged"])
            self.assertFalse(result["output_input_created"])
            self.assertEqual(result["evidence_integrity"], "PASS_PRE_POST_HASHES_IDENTICAL")
            self.assertEqual(result["committed_initialized_cells"], 0)
            self.assertEqual(
                result["field_prior_preflight"]["QNICE"][
                    "positive_mass_without_representable_moment"
                ],
                1,
            )
            self.assertEqual(
                result["field_prior_preflight"]["QNICE"]["committed_initialized_cells"],
                0,
            )
            self.assertEqual(json.loads(receipt_path.read_text())["status"],
                             "BLOCKED_SOURCE_CAP_INFEASIBLE")

    def test_same13_successful_copy_initializes_and_reads_back_all_moments(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "same13-source.nc"
            output = root / "candidate.nc"
            receipt_path = root / "prior-receipt.json"
            shape = (1, 1, 4, 4)
            field_names = (
                "QCLOUD", "QICE", "QRAIN", "QGRAUP", "QNCLOUD", "QNICE",
                "QNRAIN", "QIB", "QNCCN", "AL", "ALB", "T", "QVAPOR",
            )
            with Dataset(source, "w") as dataset:
                for name, length in zip(initializer.DIMENSIONS, shape):
                    dataset.createDimension(name, length)
                dataset.createDimension("DateStrLen", 19)
                dataset.MP_PHYSICS = 37
                times = dataset.createVariable("Times", "S1", ("Time", "DateStrLen"))
                times[0] = np.asarray(list(b"2026-08-16_13:00:00"), dtype="S1")
                units = {
                    "QNCLOUD": "kg(-1)", "QNICE": "kg(-1)", "QNRAIN": "kg(-1)",
                    "QNCCN": "kg(-1)", "QIB": "m(3) kg(-1)",
                    "AL": "m(3) kg(-1)", "ALB": "m(3) kg(-1)",
                }
                for name in field_names:
                    variable = dataset.createVariable(name, "f4", initializer.DIMENSIONS)
                    variable.units = units.get(name, "kg kg-1")
                    variable[:] = 0.0
                active = (0, 0, slice(1, 3), slice(1, 3))
                dataset["QCLOUD"][active] = 1.0e-6
                dataset["QICE"][active] = 1.0e-7
                dataset["QRAIN"][active] = 1.0e-7
                dataset["QGRAUP"][active] = 1.0e-3
                dataset["AL"][:] = 0.75
                dataset["ALB"][:] = 0.25
                dataset["T"][:] = 275.0
                dataset["QVAPOR"][:] = 0.004
                # A valid same-time background cloud moment must be retained exactly.
                cloud_lambda = 1.0e5
                cloud_pidn = initializer.SPECIES["QCLOUD"]["pidn"]
                background_nc = 1.0e-6 * cloud_lambda**3 / cloud_pidn
                dataset["QNCLOUD"][0, 0, 1, 1] = background_nc
                source_variable_hashes = {
                    name: initializer.variable_sha256(dataset.variables[name])
                    for name in dataset.variables
                }
                source_fields = {
                    name: np.asarray(dataset.variables[name][:]).copy()
                    for name in field_names
                }
            source_hash = initializer.file_sha256(source)
            with (
                mock.patch.object(initializer, "PR83_EXPECTED_INPUT_SHA256", source_hash),
                mock.patch.object(initializer, "_validate_same13_policy_file",
                                  return_value={"policy_id": "fixture-policy"}),
                mock.patch.object(initializer, "_same13_evidence_hashes",
                                  return_value={"fixture": "stable"}),
                mock.patch.object(initializer, "_check_same13_input_metadata"),
            ):
                receipt = initializer.initialize_same13_copy(
                    source, output, receipt_path,
                    policy_path=initializer.DEFAULT_PR83_POLICY,
                )

            self.assertEqual(receipt["status"], "RESEARCH_PRIOR_CREATED")
            self.assertTrue(receipt["all_other_variables_unchanged"])
            self.assertEqual(receipt["source_input_sha256"], source_hash)
            self.assertEqual(receipt["committed_initialized_cells"]["QNCLOUD"], 3)
            self.assertEqual(receipt["committed_initialized_cells"]["QNICE"], 4)
            self.assertEqual(receipt["committed_initialized_cells"]["QNRAIN"], 4)
            self.assertEqual(receipt["committed_initialized_cells"]["QIB"], 4)
            with Dataset(output, "r") as candidate:
                for name in ("QCLOUD", "QICE", "QRAIN", "QGRAUP", "QNCCN", "T", "QVAPOR", "AL", "ALB"):
                    np.testing.assert_array_equal(candidate[name][:], source_fields[name])
                for name in ("QNCLOUD", "QNICE", "QNRAIN", "QIB"):
                    result = np.asarray(candidate[name][:])
                    self.assertTrue(np.all(result[0, 0, 1:3, 1:3] > 0.0))
                    np.testing.assert_array_equal(result[0, 0, 0, :], source_fields[name][0, 0, 0, :])
                    np.testing.assert_array_equal(result[0, 0, -1, :], source_fields[name][0, 0, -1, :])
                    np.testing.assert_array_equal(result[0, 0, :, 0], source_fields[name][0, 0, :, 0])
                    np.testing.assert_array_equal(result[0, 0, :, -1], source_fields[name][0, 0, :, -1])
                self.assertEqual(
                    candidate["QNCLOUD"][0, 0, 1, 1], np.float32(background_nc)
                )
                rho = np.float32(1.0) / np.add(
                    np.asarray(candidate["AL"][0], dtype=np.float32),
                    np.asarray(candidate["ALB"][0], dtype=np.float32),
                    dtype=np.float32,
                )
                for mass_name, moment_name, cap in (
                    ("QCLOUD", "QNCLOUD", 5.0e10),
                    ("QICE", "QNICE", 1.0e6),
                    ("QRAIN", "QNRAIN", 5.0e7),
                ):
                    number_internal = candidate[moment_name][0] * rho
                    self.assertTrue(np.all(number_internal[:, 1:3, 1:3] <= cap))
                    report = receipt["field_prior_receipts"][moment_name]["preflight"]
                    self.assertEqual(report["status"], "PASS_SCOPED")
                np.testing.assert_allclose(
                    candidate["QGRAUP"][0, 0, 1:3, 1:3]
                    / candidate["QIB"][0, 0, 1:3, 1:3],
                    400.0, rtol=1e-6,
                )
                for name in source_variable_hashes:
                    if name not in {"QNCLOUD", "QNICE", "QNRAIN", "QIB"}:
                        self.assertEqual(
                            initializer.variable_sha256(candidate.variables[name]),
                            source_variable_hashes[name],
                        )
            saved_receipt = json.loads(receipt_path.read_text())
            self.assertEqual(saved_receipt["output_input_sha256"], receipt["output_input_sha256"])

    def test_same13_policy_is_separate_from_frozen_pr61_policy(self):
        fixture_path = ROOT / "tests/fixtures/pr83_policy_contract.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        policy = json.loads(initializer.DEFAULT_PR83_POLICY.read_text(encoding="utf-8"))
        self.assertEqual(policy["schema"], fixture["schema"])
        self.assertEqual(policy["policy_id"], fixture["policy_id"])
        self.assertEqual(policy["preflight"]["expected_source_valid_time"],
                         fixture["expected_source_valid_time"])
        self.assertEqual(policy["density_source"]["formula"], fixture["density_formula"])
        self.assertTrue(set(fixture["source_evidence_keys"]).issubset(policy["source"]))
        self.assertEqual(
            initializer.file_sha256(initializer.DEFAULT_PR83_POLICY),
            initializer.PR83_EXPECTED_POLICY_SHA256,
        )

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

    def test_policy_rejects_executable_declaration_drift(self):
        mutations = (
            (initializer.SPECIES["QCLOUD"], "moment", "QNRAIN", "QCLOUD.moment"),
            (initializer.SPECIES["QCLOUD"], "threshold", 2.0e-15, "QCLOUD.threshold"),
            (initializer.SPECIES["QCLOUD"], "power", 4, "QCLOUD.power"),
            (initializer.SPECIES["QCLOUD"], "lambda_min", 12001.0, "QCLOUD.lambda_min"),
            (initializer.SPECIES["QCLOUD"], "lambda_max", 500001.0, "QCLOUD.lambda_max"),
            (initializer.SPECIES["QCLOUD"], "internal_cap", 4.0e10, "QCLOUD.internal_cap"),
            (initializer.SPECIES["QCLOUD"], "m_min", 5.0e-15, "QCLOUD.m_min"),
            (initializer.SPECIES["QCLOUD"], "m_max", 3.1e-10, "QCLOUD.m_max"),
            (initializer.SPECIES["QCLOUD"], "pidn", initializer.SPECIES["QCLOUD"]["pidn"] * 1.01,
             "QCLOUD.pidn_min"),
            (initializer.GRAUPEL, "moment", "QGRAUPEL", "QGRAUP.moment"),
            (initializer.GRAUPEL, "threshold", 2.0e-9, "QGRAUP.threshold"),
            (initializer.GRAUPEL, "rho_center", 500.0, "QGRAUP.rho_center"),
            (initializer.GRAUPEL, "rho_min", 101.0, "QGRAUP.rho_min"),
            (initializer.GRAUPEL, "rho_max", 901.0, "QGRAUP.rho_max"),
        )
        for declarations, key, changed_value, expected in mutations:
            with self.subTest(field=expected), mock.patch.dict(
                declarations, {key: changed_value}
            ):
                with self.assertRaisesRegex(
                    initializer.InitializationError,
                    f"POLICY_IMPLEMENTATION_MISMATCH:{expected}",
                ):
                    initializer._validate_policy_file(initializer.DEFAULT_POLICY)

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
