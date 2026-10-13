"""Small NetCDF controls for the declared PR83 moment readback contract."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import pr83_moment_candidate_readback as candidate_readback  # noqa: E402
from pr83_moment_candidate_readback import (  # noqa: E402
    build_report, compare_native_initial_outputs,
)


MASS_DIMS = ("Time", "bottom_top", "south_north", "west_east")
STAG_DIMS = ("Time", "bottom_top_stag", "south_north", "west_east")
UNITS = {
    "QVAPOR": "kg kg-1", "QCLOUD": "kg kg-1", "QICE": "kg kg-1",
    "QRAIN": "kg kg-1", "QSNOW": "kg kg-1", "QGRAUP": "kg kg-1",
    "QNCLOUD": "kg-1", "QNICE": "kg-1", "QNRAIN": "kg-1",
    "QIB": "m3 kg-1", "T": "K", "P": "Pa", "PB": "Pa",
    "PH": "m2 s-2", "PHB": "m2 s-2", "U": "m s-1",
    "V": "m s-1", "W": "m s-1", "AL": "m3 kg-1", "ALB": "m3 kg-1",
    "XLAT": "degree_north", "XLONG": "degree_east",
    "XLAT_U": "degree_north", "XLONG_U": "degree_east",
    "XLAT_V": "degree_north", "XLONG_V": "degree_east",
}


class Pr83MomentCandidateReadbackTests(unittest.TestCase):
    def _write_native(self, path: Path, *, initialized: bool, orphan_number: bool = False,
                      horizontal_size: int = 2) -> None:
        h = horizontal_size
        with netCDF4.Dataset(path, "w") as dataset:
            for name, length in (("Time", 1), ("bottom_top", 2),
                                 ("bottom_top_stag", 3), ("south_north", h),
                                 ("west_east", h), ("west_east_stag", h + 1),
                                 ("south_north_stag", h + 1), ("DateStrLen", 19)):
                dataset.createDimension(name, length)
            dataset.MP_PHYSICS = 37
            dataset.DX = 5000.0
            dataset.DY = 5000.0
            dataset.MAP_PROJ = 1
            dataset.CEN_LAT = 35.0
            dataset.CEN_LON = 128.0
            dataset.TRUELAT1 = 30.0
            dataset.TRUELAT2 = 60.0
            dataset.STAND_LON = 126.0
            times = dataset.createVariable("Times", "S1", ("Time", "DateStrLen"))
            times[0, :] = np.asarray(list("2026-08-16_13:00:00"), dtype="S1")
            arrays = {
                "QVAPOR": np.full((1, 2, h, h), 0.005, dtype=np.float32),
                "QCLOUD": np.full((1, 2, h, h), 1.0e-5, dtype=np.float32),
                "QICE": np.full((1, 2, h, h), 1.0e-5, dtype=np.float32),
                "QRAIN": np.full((1, 2, h, h), 1.0e-5, dtype=np.float32),
                "QSNOW": np.full((1, 2, h, h), 1.0e-5, dtype=np.float32),
                "QGRAUP": np.full((1, 2, h, h), 1.0e-5, dtype=np.float32),
                "QNCLOUD": np.zeros((1, 2, h, h), dtype=np.float32),
                "QNICE": np.zeros((1, 2, h, h), dtype=np.float32),
                "QNRAIN": np.zeros((1, 2, h, h), dtype=np.float32),
                "QIB": np.zeros((1, 2, h, h), dtype=np.float32),
                "T": np.full((1, 2, h, h), 1.0, dtype=np.float32),
                "P": np.full((1, 2, h, h), 100.0, dtype=np.float32),
                "PB": np.full((1, 2, h, h), 90000.0, dtype=np.float32),
                "PH": np.zeros((1, 3, h, h), dtype=np.float32),
                "PHB": np.full((1, 3, h, h), 10.0, dtype=np.float32),
                "U": np.zeros((1, 2, h, h + 1), dtype=np.float32),
                "V": np.zeros((1, 2, h + 1, h), dtype=np.float32),
                "W": np.zeros((1, 3, h, h), dtype=np.float32),
                "AL": np.ones((1, 2, h, h), dtype=np.float32),
                "ALB": np.zeros((1, 2, h, h), dtype=np.float32),
                "XLAT": np.full((1, h, h), 35.0, dtype=np.float32),
                "XLONG": np.full((1, h, h), 128.0, dtype=np.float32),
                "XLAT_U": np.full((1, h, h + 1), 35.0, dtype=np.float32),
                "XLONG_U": np.full((1, h, h + 1), 128.0, dtype=np.float32),
                "XLAT_V": np.full((1, h + 1, h), 35.0, dtype=np.float32),
                "XLONG_V": np.full((1, h + 1, h), 128.0, dtype=np.float32),
            }
            if initialized:
                arrays["QNCLOUD"][:] = 1.0e8
                arrays["QNICE"][:] = 1.0e5
                arrays["QNRAIN"][:] = 1.0e3
                arrays["QIB"][:] = 2.5e-8
                if orphan_number:
                    arrays["QNCLOUD"][0, 0, 0, 0] = 0.0
                    arrays["QNRAIN"][0, 0, 0, 0] = 0.0
            for name, data in arrays.items():
                coordinate_dims = {
                    "XLAT": ("Time", "south_north", "west_east"),
                    "XLONG": ("Time", "south_north", "west_east"),
                    "XLAT_U": ("Time", "south_north", "west_east_stag"),
                    "XLONG_U": ("Time", "south_north", "west_east_stag"),
                    "XLAT_V": ("Time", "south_north_stag", "west_east"),
                    "XLONG_V": ("Time", "south_north_stag", "west_east"),
                }
                dimensions = coordinate_dims[name] if name in coordinate_dims else STAG_DIMS if name in ("PH", "PHB", "W") else (
                    ("Time", "bottom_top", "south_north", "west_east_stag")
                    if name == "U" else
                    ("Time", "bottom_top", "south_north_stag", "west_east")
                    if name == "V" else MASS_DIMS
                )
                variable = dataset.createVariable(name, "f4", dimensions,
                                                  fill_value=np.float32(-9999.0))
                variable.units = ("kg(-1)" if name in ("QNCLOUD", "QNICE", "QNRAIN") else
                                  "m(3) kg(-1)" if name == "QIB" else UNITS[name])
                if name == "T":
                    variable.description = "perturbation potential temperature theta-t0"
                variable[:] = data

    def _write_receipt(self, path: Path, source: Path, candidate: Path, policy: Path) -> None:
        def digest(file_path: Path) -> str:
            return hashlib.sha256(file_path.read_bytes()).hexdigest()

        path.write_text(json.dumps({
            "schema": "pr83_same13_native_moment_prior_receipt_v1",
            "status": "RESEARCH_PRIOR_CREATED",
            "policy_id": "SAME13_KDM6_NATIVE_MOMENT_PRIOR_20261013",
            "policy_sha256": digest(policy),
            "initializer_sha256": digest(ROOT / "tools/initialize_native_moments.py"),
            "source_input_sha256": digest(source),
            "output_input_sha256": digest(candidate),
            "all_other_variables_unchanged": True,
        }), encoding="utf-8")

    def test_candidate_and_native_pair_readback_uses_same_time_carrier(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            policy = root / "policy.json"
            declaration = json.loads((ROOT / "docs/PR83_NATIVE_MOMENT_POLICY_20261013.json").read_text())
            declaration["preflight"]["expected_input_spatial_shape_bottom_top_south_north_west_east"] = [2, 2, 2]
            policy.write_text(json.dumps(declaration), encoding="utf-8")
            source, candidate, native, off, receipt = (
                root / name for name in ("source.nc", "candidate.nc", "native.nc", "off.nc", "receipt.json")
            )
            self._write_native(source, initialized=False)
            self._write_native(candidate, initialized=True)
            self._write_native(native, initialized=True)
            self._write_native(off, initialized=False)
            with netCDF4.Dataset(off, "a") as dataset:
                dataset.variables["QCLOUD"][:] *= np.float32(1.1)
            declaration["preflight"]["expected_source_input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            policy.write_text(json.dumps(declaration), encoding="utf-8")
            self._write_receipt(receipt, source, candidate, policy)

            with patch.object(candidate_readback, "EXPECTED_POLICY_SHA256", hashlib.sha256(policy.read_bytes()).hexdigest()):
                report = build_report(source, candidate, native, receipt, policy,
                                      paired_off_native=off)

        self.assertEqual(report["status"], "PASS_SCOPED_MOMENT_CANDIDATE_READBACK")
        self.assertEqual(report["candidate_moment_validity"]["QNCLOUD"]["positive_mass_zero_moment_cells"], 0)
        self.assertEqual(report["candidate_moment_validity"]["QSNOW"]["native_snow_number_moment"], "NOT_DECLARED")
        pair = report["paired_native_comparison"]["native_field_deltas"]
        self.assertEqual(pair["QCLOUD"]["changed_cells"], 8)
        self.assertEqual(pair["QNCLOUD"]["changed_cells"], 8)
        self.assertGreater(pair["QNCLOUD"]["max_abs_difference"], 0.0)

    def test_positive_carrier_without_moment_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            policy = root / "policy.json"
            declaration = json.loads((ROOT / "docs/PR83_NATIVE_MOMENT_POLICY_20261013.json").read_text())
            declaration["preflight"]["expected_input_spatial_shape_bottom_top_south_north_west_east"] = [2, 2, 2]
            policy.write_text(json.dumps(declaration), encoding="utf-8")
            source, candidate, native, receipt = (
                root / name for name in ("source.nc", "candidate.nc", "native.nc", "receipt.json")
            )
            self._write_native(source, initialized=False)
            self._write_native(candidate, initialized=True, orphan_number=True)
            self._write_native(native, initialized=True, orphan_number=True)
            declaration["preflight"]["expected_source_input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            policy.write_text(json.dumps(declaration), encoding="utf-8")
            self._write_receipt(receipt, source, candidate, policy)
            with patch.object(candidate_readback, "EXPECTED_POLICY_SHA256", hashlib.sha256(policy.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError, "positive-mass support has unresolved zero moments"):
                    build_report(source, candidate, native, receipt, policy)

    def test_positive_moment_above_native_internal_number_cap_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            policy = root / "policy.json"
            declaration = json.loads((ROOT / "docs/PR83_NATIVE_MOMENT_POLICY_20261013.json").read_text())
            declaration["preflight"]["expected_input_spatial_shape_bottom_top_south_north_west_east"] = [2, 2, 2]
            source, candidate, native, receipt = (
                root / name for name in ("source.nc", "candidate.nc", "native.nc", "receipt.json")
            )
            self._write_native(source, initialized=False)
            self._write_native(candidate, initialized=True)
            self._write_native(native, initialized=True)
            with netCDF4.Dataset(candidate, "a") as dataset:
                dataset.variables["QNICE"][:] = np.float32(2.0e6)
            declaration["preflight"]["expected_source_input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            policy.write_text(json.dumps(declaration), encoding="utf-8")
            self._write_receipt(receipt, source, candidate, policy)
            with patch.object(candidate_readback, "EXPECTED_POLICY_SHA256", hashlib.sha256(policy.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError, "native internal number exceeds source cap"):
                    build_report(source, candidate, native, receipt, policy)

    def _pr84_test_policy(self) -> dict:
        policy = json.loads((ROOT / "docs/PR83_NATIVE_MOMENT_POLICY_20261013.json").read_text())
        policy["schema"] = candidate_readback.PR84_POLICY_SCHEMA
        policy["policy_id"] = "SAME13_KDM6_NATIVE_MOMENT_PRIOR_20261013_V2"
        policy["prior"]["active_domain_mode"] = "FULL_NATIVE_HORIZONTAL"
        ice = policy["species"]["QICE"]
        ice["internal_number_cap_mode"] = "SOURCE_PSD_COMPATIBLE_ENTRY_GUARD"
        pidni = np.float32(np.pi * 500.0)
        ice["source_pidni_binary32_value"] = float(pidni)
        ice["source_pidni_binary32_hex"] = f"{int(pidni.view(np.uint32)):08x}"
        ice["lambda_min_m-1"] = 9080.0
        policy["preflight"]["authorized_source_inputs"] = [
            {"role": role, "sha256": digest}
            for role, digest in candidate_readback.PR84_SOURCE_INPUTS.items()
        ]
        return policy

    def test_v2_policy_requires_both_exact_source_bindings(self):
        policy = self._pr84_test_policy()
        candidate_readback._validate_policy(policy)
        policy["preflight"]["authorized_source_inputs"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "authorized source input pair mismatch"):
            candidate_readback._validate_policy(policy)

    def test_v2_actual_first_high_ice_pair_uses_binary32_source_coefficient(self):
        policy = self._pr84_test_policy()
        qice = 0.003110517282038927
        qnice = np.float32(1482416.625)
        declaration = policy["species"]["QICE"]
        source_bounds = candidate_readback._mean_particle_mass_bounds(
            policy, "QICE", declaration
        )
        actual_ratio = qice / float(qnice)
        old_v1_bounds = declaration["particle_mean_mass_bounds_kg"]
        self.assertGreater(actual_ratio, old_v1_bounds[1])
        self.assertLessEqual(actual_ratio, source_bounds[1])
        predecessor = np.nextafter(qnice, np.float32(-np.inf), dtype=np.float32)
        self.assertGreater(qice / float(predecessor), source_bounds[1])

    def test_v2_accepts_derived_high_qnice_but_rejects_larger_value(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            candidate = Path(temporary_directory) / "candidate.nc"
            self._write_native(candidate, initialized=True)
            policy = self._pr84_test_policy()
            mass = np.float64(3.0e-3)
            pidni = np.float64(policy["species"]["QICE"]["source_pidni_binary32_value"])
            public_floor64 = mass * 9080.0**3 / pidni
            public_floor = candidate_readback._float32_ceiling(np.asarray([public_floor64]))[0]
            with netCDF4.Dataset(candidate, "a") as dataset:
                dataset.variables["QICE"][:] = np.float32(mass)
                dataset.variables["QNICE"][:] = public_floor
            with netCDF4.Dataset(candidate) as dataset:
                report = candidate_readback._validate_moments(dataset, policy)
            self.assertGreater(report["QNICE"]["maximum_native_internal_number_m-3"], 1.0e6)
            self.assertEqual(report["QNICE"]["internal_number_cap_mode"],
                             "SOURCE_PSD_COMPATIBLE_ENTRY_GUARD")
            with netCDF4.Dataset(candidate, "a") as dataset:
                dataset.variables["QNICE"][:] = np.nextafter(
                    public_floor, np.float32(np.inf), dtype=np.float32
                )
            with netCDF4.Dataset(candidate) as dataset:
                with self.assertRaisesRegex(ValueError, "native internal number exceeds source cap"):
                    candidate_readback._validate_moments(dataset, policy)

    def test_v2_checks_full_horizontal_perimeter(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            candidate = Path(temporary_directory) / "candidate.nc"
            self._write_native(candidate, initialized=True, horizontal_size=4)
            policy = self._pr84_test_policy()
            with netCDF4.Dataset(candidate, "a") as dataset:
                dataset.variables["QNCLOUD"][0, 0, 0, 0] = 0.0
            with netCDF4.Dataset(candidate) as dataset:
                with self.assertRaisesRegex(ValueError, "positive-mass support has unresolved zero moments"):
                    candidate_readback._validate_moments(dataset, policy)

    def test_candidate_coordinate_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            policy = root / "policy.json"
            declaration = json.loads((ROOT / "docs/PR83_NATIVE_MOMENT_POLICY_20261013.json").read_text())
            declaration["preflight"]["expected_input_spatial_shape_bottom_top_south_north_west_east"] = [2, 2, 2]
            source, candidate, native, receipt = (
                root / name for name in ("source.nc", "candidate.nc", "native.nc", "receipt.json")
            )
            self._write_native(source, initialized=False)
            self._write_native(candidate, initialized=True)
            self._write_native(native, initialized=True)
            with netCDF4.Dataset(candidate, "a") as dataset:
                dataset.variables["XLAT"][0, 0, 0] += np.float32(0.01)
            declaration["preflight"]["expected_source_input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            policy.write_text(json.dumps(declaration), encoding="utf-8")
            self._write_receipt(receipt, source, candidate, policy)
            with patch.object(candidate_readback, "EXPECTED_POLICY_SHA256", hashlib.sha256(policy.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError, "undeclared source field: XLAT"):
                    build_report(source, candidate, native, receipt, policy)

    def test_native_pair_coordinate_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            xa, xb = root / "xa.nc", root / "xb.nc"
            self._write_native(xa, initialized=True)
            self._write_native(xb, initialized=False)
            with netCDF4.Dataset(xb, "a") as dataset:
                dataset.variables["XLONG_V"][0, 0, 0] += np.float32(0.01)
            with self.assertRaisesRegex(ValueError, "paired native coordinates differ: XLONG_V"):
                compare_native_initial_outputs(xa, xb)


if __name__ == "__main__":
    unittest.main()
