#!/usr/bin/env python3
"""Focused contract tests for the PR84 native-moment guard."""
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


def _policy(pidni: np.float32) -> dict:
    species = json.loads(initializer.DEFAULT_PR83_POLICY.read_text())["species"]
    species["QICE"].update({
        "internal_number_cap_mode": "SOURCE_PSD_COMPATIBLE_ENTRY_GUARD",
        "source_pidni_binary32_value": float(pidni),
        "source_pidni_binary32_hex": f"{int(np.asarray(pidni).view(np.uint32)):08x}",
    })
    return {
        "schema": initializer.PR84_POLICY_SCHEMA,
        "policy_id": "SAME13_KDM6_NATIVE_MOMENT_PRIOR_20261013_V2",
        "declared_before_experiment": True,
        "prior": {"active_domain_mode": "FULL_NATIVE_HORIZONTAL"},
        "species": species,
        "preflight": {
            "authorized_source_inputs": [
                {"role": role, "sha256": digest}
                for role, digest in initializer.PR84_EXPECTED_SOURCE_INPUTS.items()
            ],
            "expected_source_valid_time": initializer.PR83_EXPECTED_VALID_TIME,
            "expected_input_spatial_shape_bottom_top_south_north_west_east": [39, 282, 234],
        },
    }


class PR84NativeMomentPolicyTests(unittest.TestCase):
    def test_frozen_policy_binds_actual_kdm6_parameters_and_toolchain(self):
        policy_path = ROOT / "docs/PR84_NATIVE_MOMENT_POLICY_20261013.json"
        policy = initializer._validate_same13_policy_file(policy_path)
        self.assertEqual(
            policy["species"]["QICE"]["source_pidni_binary32_hex"], "0x44C4597C"
        )
        self.assertEqual(policy["native_build"]["runtime_consumer_readback_status"], "NOT_RUN")

        # A self-consistent replacement value and bit pattern still fail against
        # the source kdm6init accessor and independently hashed parameter dump.
        tampered = json.loads(json.dumps(policy))
        tampered["species"]["QICE"]["source_pidni_binary32_value"] = 1570.0
        tampered["species"]["QICE"]["source_pidni_binary32_hex"] = "0x44C44000"
        with self.assertRaisesRegex(initializer.InitializationError,
                                    "PR84_QICE_POLICY_PARAMETER_BINDING_MISMATCH"):
            initializer._validate_pr84_evidence_bindings(tampered)

    def test_tampered_frozen_v2_policy_is_rejected_before_copy(self):
        declared = ROOT / "docs/PR84_NATIVE_MOMENT_POLICY_20261013.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tampered = json.loads(declared.read_text())
            tampered["scope"] += " changed after freeze"
            policy_path = root / "policy.json"
            policy_path.write_text(json.dumps(tampered))
            candidate = root / "candidate.nc"
            receipt = root / "receipt.json"
            with self.assertRaisesRegex(initializer.InitializationError,
                                        "PR84_POLICY_HASH_MISMATCH"):
                initializer.initialize_same13_copy(
                    root / "source-not-opened.nc", candidate, receipt,
                    policy_path=policy_path,
                )
            self.assertFalse(candidate.exists())
            self.assertFalse(receipt.exists())

    def test_public_number_floor_is_minimal_real32_ceiling(self):
        bound = np.array([1.0, 1.00000001, 1.00000012, 0.0], dtype=np.float64)
        stored = initializer._pr84_float32_ceiling(bound)
        self.assertTrue(np.all(stored.astype(np.float64) >= bound))
        predecessor = np.nextafter(stored, np.float32(-np.inf), dtype=np.float32)
        self.assertTrue(np.all(predecessor.astype(np.float64) < bound))

    def test_qice_entry_guard_keeps_low_mass_cap_and_covers_source_floor(self):
        pidni = float(np.float32(math_pi_times_500()))
        qice = np.array([1.0e-6, 3.0e-3], dtype=np.float32)
        density = np.array([1.0, 0.8], dtype=np.float32)
        qn_floor, internal_floor, cap = initializer._pr84_qice_entry_guard(
            qice, density, pidni=pidni, lambda_min=9080.0
        )
        self.assertEqual(cap[0], np.float32(1.0e6))
        strict_floor = qice.astype(np.float64) * 9080.0**3 / pidni
        self.assertTrue(np.all(qn_floor.astype(np.float64) >= strict_floor))
        self.assertEqual(cap[1], np.float32(qn_floor[1] * density[1]))
        self.assertTrue(np.all(qn_floor * density >= internal_floor))

    def test_native_low_fixture_matches_r32_reference_bits(self):
        qice = np.array([6.6648876781982835e-6], dtype=np.float64)
        density = np.array([0.750110387802124], dtype=np.float32)
        qn_floor, internal_floor, cap = initializer._pr84_qice_entry_guard(
            qice, density, pidni=1570.79638671875, lambda_min=9080.0,
        )
        self.assertEqual(int(np.asarray(qn_floor[0]).view(np.uint32)), 0x454685DA)
        self.assertEqual(int(np.asarray(internal_floor[0]).view(np.uint32)), 0x4514EA00)
        self.assertEqual(int(np.asarray(cap[0]).view(np.uint32)), 0x49742400)

    def test_internal_floor_roundtrip_advances_one_ulp_when_needed(self):
        pidni = float(np.float32(math_pi_times_500()))
        qice = np.array([0.0007856728043407202], dtype=np.float64)
        density = np.array([0.4555096924304962], dtype=np.float32)
        qn_floor, internal_floor, _ = initializer._pr84_qice_entry_guard(
            qice, density, pidni=pidni, lambda_min=9080.0
        )
        public_min = qice * 9080.0**3 / pidni
        initial_ceil = initializer._pr84_float32_ceiling(public_min)
        self.assertEqual(
            qn_floor[0], np.nextafter(initial_ceil[0], np.float32(np.inf), dtype=np.float32)
        )
        self.assertEqual(int(np.asarray(qn_floor[0]).view(np.uint32)), 0x48B6D4B2)
        self.assertGreaterEqual(float(qn_floor[0]), float(public_min[0]))
        self.assertGreaterEqual(float(np.float32(qn_floor[0] * density[0])),
                                float(internal_floor[0]))
        predecessor = np.nextafter(qn_floor, np.float32(-np.inf), dtype=np.float32)
        self.assertTrue(
            predecessor.astype(np.float64)[0] < public_min[0]
            or np.float32(predecessor[0] * density[0]) < internal_floor[0]
        )

    def test_actual_pr83_high_ice_cell_meets_both_source_floors(self):
        pidni = float(np.float32(math_pi_times_500()))
        qice = np.array([0.0033685904927551746], dtype=np.float64)
        density = np.array([0.6824867725372314], dtype=np.float32)
        qn_floor, internal_floor, cap = initializer._pr84_qice_entry_guard(
            qice, density, pidni=pidni, lambda_min=9080.0
        )
        self.assertGreaterEqual(float(qn_floor[0]),
                                float(qice[0] * 9080.0**3 / pidni))
        self.assertGreaterEqual(np.float32(qn_floor[0] * density[0]),
                                internal_floor[0])
        self.assertEqual(cap[0], np.float32(qn_floor[0] * density[0]))
        self.assertEqual(int(np.asarray(qn_floor[0]).view(np.uint32)), 0x49C3F90E)
        self.assertEqual(int(np.asarray(internal_floor[0]).view(np.uint32)), 0x4985BFB7)

    def test_v2_preflight_initializes_full_horizontal_domain(self):
        pidni = np.float32(math_pi_times_500())
        policy = _policy(pidni)
        shape = (1, 3, 4)
        arrays = {
            name: np.zeros(shape, dtype=np.float32)
            for name in (
                "QCLOUD", "QICE", "QRAIN", "QGRAUP", "QNCLOUD", "QNICE",
                "QNRAIN", "QIB", "QNCCN", "AL", "ALB",
            )
        }
        arrays["QCLOUD"][:] = 1.0e-7
        arrays["QICE"][:] = 3.0e-3
        arrays["QRAIN"][:] = 1.0e-7
        arrays["QGRAUP"][:] = 1.0e-3
        density = np.full(shape, 0.8, dtype=np.float32)
        updated, masks, reports = initializer._same13_preflight(arrays, density, policy)
        self.assertEqual(int(masks["QNICE"].sum()), np.prod(shape))
        self.assertEqual(int(reports["QNICE"]["initialized_cells"]), np.prod(shape))
        self.assertTrue(np.all(updated["QNICE"] == updated["QNICE"][0, 0, 0]))
        qice_floor = arrays["QICE"].astype(np.float64) * 9080.0**3 / float(pidni)
        self.assertTrue(np.all(updated["QNICE"].astype(np.float64) >= qice_floor))
        internal = updated["QNICE"] * density
        _, _, cap = initializer._pr84_qice_entry_guard(
            arrays["QICE"], density, pidni=float(pidni), lambda_min=9080.0
        )
        self.assertTrue(np.all(internal <= cap))

    def test_v2_copy_updates_perimeter_moments_and_preserves_nonmoments(self):
        pidni = np.float32(math_pi_times_500())
        policy = _policy(pidni)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.nc"
            output = root / "output.nc"
            receipt_path = root / "receipt.json"
            field_names = (
                "QCLOUD", "QICE", "QRAIN", "QGRAUP", "QNCLOUD", "QNICE",
                "QNRAIN", "QIB", "QNCCN", "AL", "ALB", "T", "QVAPOR",
                "U", "V", "PH", "PHB",
            )
            dimensions = (1, 1, 3, 3)
            units = {
                "QNCLOUD": "kg-1", "QNICE": "kg-1", "QNRAIN": "kg-1",
                "QNCCN": "kg-1", "QIB": "m3 kg-1", "AL": "m3 kg-1",
                "ALB": "m3 kg-1",
            }
            with Dataset(source, "w") as dataset:
                for name, length in zip(initializer.DIMENSIONS, dimensions):
                    dataset.createDimension(name, length)
                dataset.createDimension("DateStrLen", 19)
                dataset.MP_PHYSICS = 37
                times = dataset.createVariable("Times", "S1", ("Time", "DateStrLen"))
                times[0] = np.asarray(list(b"2026-08-16_13:00:00"), dtype="S1")
                for name in field_names:
                    variable = dataset.createVariable(name, "f4", initializer.DIMENSIONS)
                    variable.units = units.get(name, "kg kg-1")
                    variable[:] = 0.0
                dataset["QCLOUD"][:] = 1.0e-6
                dataset["QICE"][:] = 3.0e-3
                dataset["QRAIN"][:] = 1.0e-7
                dataset["QGRAUP"][:] = 1.0e-3
                dataset["AL"][:] = 1.25
                dataset["ALB"][:] = 0.25
                for name in ("T", "QVAPOR", "U", "V", "PH", "PHB"):
                    dataset[name][:] = 17.0
                source_fields = {name: np.asarray(dataset[name][:]).copy()
                                 for name in field_names}
            source_hash = initializer.file_sha256(source)
            allowed_inputs = {"OFF": "0" * 64, "COUPLED": source_hash}
            with (
                mock.patch.object(initializer, "PR84_EXPECTED_SOURCE_INPUTS", allowed_inputs),
                mock.patch.object(initializer, "_validate_same13_policy_file",
                                  return_value=policy),
                mock.patch.object(initializer, "_same13_evidence_hashes",
                                  return_value={"fixture": "stable"}),
                mock.patch.object(initializer, "_check_same13_input_metadata"),
            ):
                receipt = initializer.initialize_same13_copy(
                    source, output, receipt_path,
                    policy_path=initializer.DEFAULT_PR83_POLICY,
                )
            self.assertEqual(receipt["status"], "RESEARCH_PRIOR_CREATED")
            self.assertEqual(receipt["source_input_role"], "COUPLED")
            self.assertEqual(receipt["policy_schema"], initializer.PR84_POLICY_SCHEMA)
            self.assertEqual(receipt["committed_initialized_cells"]["QNICE"], 9)
            with Dataset(output, "r") as candidate:
                for name in ("QCLOUD", "QICE", "QRAIN", "QGRAUP", "QNCCN",
                             "AL", "ALB", "T", "QVAPOR", "U", "V", "PH", "PHB"):
                    np.testing.assert_array_equal(candidate[name][:], source_fields[name])
                for name in ("QNCLOUD", "QNICE", "QNRAIN", "QIB"):
                    self.assertTrue(np.all(candidate[name][:] > 0.0))

    def test_v2_policy_checks_pair_domain_and_pidni_bits(self):
        pidni = np.float32(math_pi_times_500())
        policy = _policy(pidni)
        initializer._validate_pr84_policy_contract(policy)
        policy["species"]["QICE"]["source_pidni_binary32_hex"] = "00000000"
        with self.assertRaisesRegex(initializer.InitializationError, "PIDNI_VALUE_HEX_MISMATCH"):
            initializer._validate_pr84_policy_contract(policy)

    def test_v2_policy_rejects_non_ice_species_drift(self):
        policy = _policy(np.float32(math_pi_times_500()))
        policy["species"]["QRAIN"]["lambda_min_m-1"] += 1.0
        with self.assertRaisesRegex(initializer.InitializationError,
                                    "PR84_SPECIES_IMPLEMENTATION_MISMATCH"):
            initializer._validate_pr84_policy_contract(policy)


def math_pi_times_500() -> float:
    return np.pi * 500.0


if __name__ == "__main__":
    unittest.main()
