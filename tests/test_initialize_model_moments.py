"""Integration of the fresh-producer boundary with the compiled common kernel."""
import base64
import importlib.util
import json
import os
import struct
from pathlib import Path
import tempfile
import unittest
import zlib
from unittest import mock

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("model_moments", ROOT / "tools/initialize_model_moments.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ModelMomentBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "MODEL_MOMENT_DRIVER" not in os.environ:
            raise unittest.SkipTest("requires compiled Intel driver; run tests/run_initialize_model_moments.sh")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(self.tmp.cleanup)
        self.p = Path(self.tmp.name)
        self.driver = Path(os.environ["MODEL_MOMENT_DRIVER"])
        self.template = self.p / "template.nc"
        with Dataset(self.template, "w") as ds:
            for name, length in zip(module.DIMS, (1, 2, 2, 3)):
                ds.createDimension(name, length)
            ds.MP_PHYSICS = 37
            ds.USE_THETA_M = 0
            ds.createDimension("DateStrLen", 19)
            times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
            times[:] = np.frombuffer(b"2025-03-10_06:00:00", dtype="S1").reshape(1, 19)
            for name in (*module.MASS, *module.MOMENT, "AL", "ALB", "P", "PB", "T", "QVAPOR", "U"):
                v = ds.createVariable(name, "f4", module.DIMS)
                if name in module.UNITS:
                    v.units = module.UNITS[name]
                v[:] = {**dict.fromkeys(module.MASS, 1e-6), **dict.fromkeys(module.MOMENT, 0),
                        "AL": .2, "ALB": .8, "P": 1000, "PB": 99000, "T": 0, "QVAPOR": .01, "U": 3}[name]
        self.exe = self.p / "producer"
        self.exe.write_text("#!/bin/sh\ncp template.nc wrfinput_d01\n")
        self.exe.chmod(0o755)
        self.namelist = self.p / "namelist.input"
        self.namelist.write_text("&time_control\n restart = .false.\n/\n&dynamics\n use_theta_m = 0\n/\n&physics\n mp_physics = 37\n/\n")
        self.source = self.p / "source.txt"
        self.build = self.p / "build.txt"
        self.source.write_text("fixture source")
        self.build.write_text("fixture build")
        self.policy = self.p / "policy.json"
        self.policy.write_text(json.dumps({"source": "fixture", "declared_before_experiment": True, "mp_physics": 37,
            "mass_threshold": [0]*5, "lower": [1e-14, 1e-15, 3e-10, 0, 100],
            "upper": [2e-10, 1e-9, 1e-5, 0, 900], "number_cap": [5e10, 1e6, 5e7, 2e10]}))
        self.candidates = self.p / "candidates.npz"
        shape = (5, 2, 2, 3)
        bg = np.zeros(shape)
        prior = np.ones(shape) * 1e-9
        prior[0] = 1e-10
        prior[1] = 1e-10
        prior[3] = 5
        prior[4] = 400
        obs = np.zeros(shape)
        obs[0, 0, 0, 0] = 20000
        obs[0, 0, 0, 1] = 1e30  # invalid PSD falls back to valid background
        bg[0, 0, 0, 1] = 10000
        # Make the native background agree with the candidate source.
        with Dataset(self.template, "r+") as ds:
            ds["QNCLOUD"][0, 0, 0, 1] = 10000
        bg_valid = np.zeros(shape, dtype=np.int32)
        bg_valid[0, 0, 0, 1] = 1
        obs_valid = np.zeros(shape, dtype=np.int32)
        obs_valid[0, 0, 0, :2] = 1
        np.savez(self.candidates, source_sha256=module.sha(self.template),
                 background_value=bg, background_valid=bg_valid, background_provenance=bg_valid*2,
                 prior_value=prior, prior_valid=np.ones(shape, dtype=np.int32), prior_provenance=np.full(shape, 3),
                 observed_value=obs, observed_valid=obs_valid, observed_provenance=obs_valid)
        item = lambda path: {"path": str(path), "sha256": module.sha(path)}
        manifest = {"stage": "fresh_real_before_model_launch", "use_theta_m": 0, "mp_physics": 37,
                    "producer": item(self.exe), "driver": item(self.driver),
                    "source": item(self.source), "build": item(self.build),
                    "policy": item(self.policy), "candidates": item(self.candidates),
                    "inputs": [{"name": "namelist.input", **item(self.namelist)},
                               {"name": "template.nc", **item(self.template)}]}
        self.manifest = self.p / "manifest.json"
        self.manifest.write_text(json.dumps(manifest))

    def set_partition(self, *, ni=6000, frozen_error=0):
        shape = (2, 2, 3)
        mask = np.zeros(shape, dtype=np.int32)
        mask[0, 0, 0] = 1
        qi = np.full(shape, 1e-6, dtype=np.float32)
        qs = np.full(shape, 1e-6, dtype=np.float32)
        qi[0, 0, 0] = 0.6e-6
        qs[0, 0, 0] = 1.4e-6 + frozen_error
        path = self.p / "partition.npz"
        np.savez(path, source_sha256=module.sha(self.template), source="synthetic declared frozen partition",
                 provenance=np.int32(3), qi=qi, qs=qs, ni=np.full(shape, ni, dtype=np.float32), valid=mask)
        manifest = json.loads(self.manifest.read_text())
        manifest["ice_snow_partition"] = {"path": str(path), "sha256": module.sha(path)}
        self.manifest.write_text(json.dumps(manifest))
        return path

    def test_joint_partition_and_number_are_published_together(self):
        self.set_partition()
        out, receipt = self.p / "joint.nc", self.p / "joint.json"
        report = module.run_real_and_complete(self.manifest, out, receipt)
        self.assertEqual(report["completion"]["ice_snow_partition"]["selected_cells"], 1)
        self.assertFalse(report["native_first_use_verified"])
        with Dataset(out) as ds, Dataset(self.template) as original:
            self.assertEqual(ds["QICE"][0, 0, 0, 0], np.float32(.6e-6))
            self.assertEqual(ds["QSNOW"][0, 0, 0, 0], np.float32(1.4e-6))
            self.assertEqual(ds["QNICE"][0, 0, 0, 0], 6000)
            for name in ("T", "QVAPOR", "QRAIN", "QGRAUP", "QCLOUD", "U"):
                np.testing.assert_array_equal(ds[name][:], original[name][:])
            for name in ("QICE", "QSNOW"):
                np.testing.assert_array_equal(ds[name][0, 1], original[name][0, 1])
            # Existing independent observations retain their priority for other slots.
            self.assertEqual(ds["QNCLOUD"][0, 0, 0, 0], 20000)
        self.assertEqual(module.sha(self.template), report["producer_output_sha256"])

    def test_joint_bad_number_and_mass_change_never_publish(self):
        for name, kwargs in (("number", {"ni": 2e6}), ("mass", {"frozen_error": 1e-6})):
            with self.subTest(name=name):
                self.set_partition(**kwargs)
                out, receipt = self.p / (name+".nc"), self.p / (name+".json")
                with self.assertRaisesRegex(ValueError, "completion failed"):
                    module.run_real_and_complete(self.manifest, out, receipt)
                self.assertFalse(out.exists())
                self.assertFalse(receipt.exists())

    def test_joint_driver_cannot_substitute_another_conservative_partition(self):
        self.set_partition()
        real_run = module.subprocess.run
        for corruption in ("offmask", "negative", "number", "provenance"):
            def corrupt_output(command, *args, **kwargs):
                result = real_run(command, *args, **kwargs)
                if len(command) == 4:
                    path = Path(command[2])
                    raw = bytearray(path.read_bytes())
                    count, cells = 60, 12
                    mass = np.frombuffer(raw, dtype=np.float32, count=2*cells, offset=48+16*count).reshape(2, 2, 2, 3)
                    if corruption == "offmask":
                        mass[:, 1, 0, 0] = [np.float32(.6e-6), np.float32(1.4e-6)]
                    elif corruption == "negative":
                        mass[:, 0, 0, 0] = [np.float32(-.6e-6), np.float32(2.6e-6)]
                    elif corruption == "number":
                        number = np.frombuffer(raw, dtype=np.float64, count=count, offset=20)
                        number[cells] = 10000
                    else:
                        sources = np.frombuffer(raw, dtype=np.int32, count=count, offset=20+12*count)
                        sources[cells] = 1
                    path.write_bytes(raw)
                return result
            out, receipt = self.p/(corruption+".nc"), self.p/(corruption+".json")
            with self.subTest(corruption=corruption):
                with mock.patch.object(module.subprocess, "run", side_effect=corrupt_output):
                    with self.assertRaisesRegex(ValueError, "joint driver disagrees"):
                        module.run_real_and_complete(self.manifest, out, receipt)
                self.assertFalse(out.exists())
                self.assertFalse(receipt.exists())

    def test_joint_proposal_hash_and_mask_are_required(self):
        path = self.set_partition()
        with np.load(path) as data:
            arrays = {key: data[key] for key in data.files}
        arrays["source_sha256"] = "not-the-source"
        np.savez(path, **arrays)
        manifest = json.loads(self.manifest.read_text())
        manifest["ice_snow_partition"]["sha256"] = module.sha(path)
        self.manifest.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "partition source hash mismatch"):
            module.run_real_and_complete(self.manifest, self.p/"bad.nc", self.p/"bad.json")
        arrays["source_sha256"] = module.sha(self.template)
        arrays["valid"] = np.ones((2, 2, 3), dtype=np.float32)
        np.savez(path, **arrays)
        manifest["ice_snow_partition"]["sha256"] = module.sha(path)
        self.manifest.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "partition mask"):
            module.run_real_and_complete(self.manifest, self.p/"bad.nc", self.p/"bad.json")
        self.assertFalse((self.p/"bad.nc").exists())

    def test_fresh_copy_priorities_and_preservation(self):
        output, receipt = self.p / "output.nc", self.p / "receipt.json"
        report = module.run_real_and_complete(self.manifest, output, receipt)
        self.assertFalse(report["native_first_use_verified"])
        encoded = report["completion"]["provenance_data"]
        provenance = np.frombuffer(zlib.decompress(base64.b64decode(encoded)), dtype="<i4").reshape(5, 2, 2, 3)
        self.assertEqual(provenance[0, 0, 0, 0], 1)
        self.assertEqual(provenance[0, 0, 0, 1], 2)
        self.assertEqual(provenance[0, 0, 0, 2], 3)
        with Dataset(output) as ds:
            self.assertEqual(ds["QNCLOUD"][0, 0, 0, 0], 20000)
            self.assertEqual(ds["QNCLOUD"][0, 0, 0, 1], 10000)
            self.assertEqual(ds["QNCCN"][0, 0, 0, 0], 5)
            self.assertTrue(np.all(ds["U"][:] == 3))
        self.assertEqual(module.sha(self.template), report["producer_output_sha256"])
        self.assertEqual(report, json.loads(receipt.read_text()))
        with self.assertRaises(ValueError):
            module.run_real_and_complete(self.manifest, output, receipt)

    def test_finite_fill_and_packing_are_rejected(self):
        path = self.p / "missing.nc"
        with Dataset(path, "w") as ds:
            for name, length in zip(module.DIMS, (1, 2, 2, 3)):
                ds.createDimension(name, length)
            v = ds.createVariable("X", "f4", module.DIMS, fill_value=-9999.0)
            v.units = "kg kg-1"
            v[:] = -9999.0
        with Dataset(path) as ds:
            ds.set_auto_maskandscale(False)
            with self.assertRaisesRegex(ValueError, "missing field values"):
                module.read_array(ds["X"], "QCLOUD")
        with Dataset(path, "r+") as ds:
            ds["X"][:] = np.float32(module.default_fillvals["f4"])
        with Dataset(path) as ds:
            ds.set_auto_maskandscale(False)
            with self.assertRaisesRegex(ValueError, "missing field values"):
                module.read_array(ds["X"], "QCLOUD")
        with Dataset(path, "r+") as ds:
            ds["X"].setncattr("scale_factor", 2.0)
        with Dataset(path) as ds:
            ds.set_auto_maskandscale(False)
            with self.assertRaisesRegex(ValueError, "unsupported packed"):
                module.read_array(ds["X"], "QCLOUD")

    def test_publication_failure_removes_output_and_temporaries(self):
        output, receipt = self.p / "output.nc", self.p / "receipt.json"
        original_link = os.link
        def fail_receipt(src, dst):
            if Path(dst) == receipt:
                raise OSError("simulated receipt failure")
            original_link(src, dst)
        with mock.patch.object(module.os, "link", side_effect=fail_receipt):
            with self.assertRaisesRegex(OSError, "simulated receipt failure"):
                module.run_real_and_complete(self.manifest, output, receipt)
        self.assertFalse(output.exists())
        self.assertFalse(receipt.exists())
        self.assertEqual([], list(self.p.glob("tmp*")))

    def test_receipt_temporary_creation_failure_cleans_candidate_temporary(self):
        output, receipt = self.p / "output.nc", self.p / "receipt.json"
        original = module.tempfile.NamedTemporaryFile
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated temporary failure")
            return original(*args, **kwargs)
        with mock.patch.object(module.tempfile, "NamedTemporaryFile", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "simulated temporary failure"):
                module.run_real_and_complete(self.manifest, output, receipt)
        self.assertFalse(output.exists())
        self.assertFalse(receipt.exists())
        self.assertEqual([], list(self.p.glob("tmp*")))

    def test_file_units_and_scheme_are_required(self):
        output, receipt = self.p / "output.nc", self.p / "receipt.json"
        manifest = json.loads(self.manifest.read_text())
        with Dataset(self.template, "r+") as ds:
            ds["QCLOUD"].units = "g kg-1"
        manifest["inputs"][1]["sha256"] = module.sha(self.template)
        self.manifest.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "unsupported units"):
            module.run_real_and_complete(self.manifest, output, receipt)
        self.assertFalse(output.exists())
        with Dataset(self.template, "r+") as ds:
            ds["QCLOUD"].units = "kg kg-1"
            ds.MP_PHYSICS = 10
        manifest["inputs"][1]["sha256"] = module.sha(self.template)
        self.manifest.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "unsupported model MP_PHYSICS"):
            module.run_real_and_complete(self.manifest, output, receipt)
        self.assertFalse(output.exists())
        self.assertFalse(receipt.exists())

    def test_moist_theta_branch_and_mismatch(self):
        m = json.loads(self.manifest.read_text())
        m["use_theta_m"] = 1
        self.manifest.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, "use_theta_m"):
            module.run_real_and_complete(self.manifest, self.p / "output.nc", self.p / "receipt.json")
        self.namelist.write_text(self.namelist.read_text().replace("use_theta_m = 0", "use_theta_m = 1"))
        with Dataset(self.template, "r+") as ds:
            ds.USE_THETA_M = 1
        m["inputs"][1]["sha256"] = module.sha(self.template)
        with np.load(self.candidates) as old:
            arrays = {key: old[key] for key in old.files}
        arrays["source_sha256"] = module.sha(self.template)
        np.savez(self.candidates, **arrays)
        m["candidates"]["sha256"] = module.sha(self.candidates)
        m["inputs"][0]["sha256"] = module.sha(self.namelist)
        self.manifest.write_text(json.dumps(m))
        report = module.run_real_and_complete(self.manifest, self.p / "output.nc", self.p / "receipt.json")
        self.assertEqual(report["use_theta_m"], 1)

    def test_file_dry_theta_restores_temperature_for_both_settings(self):
        for setting in (0, 1):
            with self.subTest(use_theta_m=setting):
                with Dataset(self.template, "r+") as ds:
                    ds.USE_THETA_M = setting
                    ds["T"][:] = 0
                    ds["QVAPOR"][:] = .02
                    if "THM" not in ds.variables:
                        ds.createVariable("THM", "f4", module.DIMS)
                    ds["THM"][:] = 300 * (1 + 461.6 / 287 * .02) - 300
                self.namelist.write_text(
                    f"&time_control\n restart = .false.\n/\n&dynamics\n use_theta_m = {setting}\n/\n&physics\n mp_physics = 37\n/\n")
                with np.load(self.candidates) as old:
                    arrays = {key: old[key] for key in old.files}
                arrays["source_sha256"] = module.sha(self.template)
                np.savez(self.candidates, **arrays)
                manifest = json.loads(self.manifest.read_text())
                manifest["use_theta_m"] = setting
                manifest["inputs"][0]["sha256"] = module.sha(self.namelist)
                manifest["inputs"][1]["sha256"] = module.sha(self.template)
                manifest["candidates"]["sha256"] = module.sha(self.candidates)
                self.manifest.write_text(json.dumps(manifest))
                report = module.run_real_and_complete(
                    self.manifest, self.p / f"output{setting}.nc", self.p / f"receipt{setting}.json")
                thermo = report["completion"]["input_thermodynamics"]
                self.assertEqual(thermo["temperature"], "(T+300)*exner")
                np.testing.assert_allclose(thermo["driver_temperature_range_kelvin"], [300, 300], atol=1e-5)

    def test_failed_cell_location_is_reported_without_publication(self):
        with np.load(self.candidates) as old:
            arrays = {key: old[key] for key in old.files}
        arrays["prior_valid"][0, 0, 0, 2] = 0
        np.savez(self.candidates, **arrays)
        manifest = json.loads(self.manifest.read_text())
        manifest["candidates"]["sha256"] = module.sha(self.candidates)
        self.manifest.write_text(json.dumps(manifest))
        output, receipt = self.p / "output.nc", self.p / "receipt.json"
        with self.assertRaisesRegex(ValueError, r"location=\[3, 1, 1, 1\]"):
            module.run_real_and_complete(self.manifest, output, receipt)
        self.assertFalse(output.exists())
        self.assertFalse(receipt.exists())

    def test_empty_feasible_interval_is_reported_without_publication(self):
        policy = json.loads(self.policy.read_text())
        policy["number_cap"][0] = 500
        self.policy.write_text(json.dumps(policy))
        manifest = json.loads(self.manifest.read_text())
        manifest["policy"]["sha256"] = module.sha(self.policy)
        self.manifest.write_text(json.dumps(manifest))
        output, receipt = self.p / "output.nc", self.p / "receipt.json"
        with self.assertRaisesRegex(ValueError, r"location=\[1, 1, 1, 1\], reason=EMPTY_ANALYTICAL_INTERVAL \(2\), feasible_interval=\[") as error:
            module.run_real_and_complete(self.manifest, output, receipt)
        interval = json.loads(str(error.exception).split("feasible_interval=", 1)[1])
        np.testing.assert_allclose(interval, [float(np.float32(1e-6)) / 2e-10, 500], rtol=1e-6)
        self.assertFalse(output.exists())
        self.assertFalse(receipt.exists())

    def test_inconsistent_driver_status_and_reason_roll_back(self):
        original_run = module.subprocess.run
        for status, reason in ((20, 2), (10, 2), (-10, 0), (1, 0)):
            with self.subTest(status=status, reason=reason):
                def corrupt_driver_output(*args, **kwargs):
                    result = original_run(*args, **kwargs)
                    if len(args[0]) == 3 and Path(args[0][1]).name == "driver.in":
                        path = Path(args[0][2])
                        data = bytearray(path.read_bytes())
                        struct.pack_into("=i", data, 0, status)
                        struct.pack_into("=i", data, len(data) - 20, reason)
                        path.write_bytes(data)
                    return result
                output, receipt = self.p / "output.nc", self.p / "receipt.json"
                with mock.patch.object(module.subprocess, "run", side_effect=corrupt_driver_output):
                    with self.assertRaisesRegex(ValueError, "inconsistent driver status and failure reason"):
                        module.run_real_and_complete(self.manifest, output, receipt)
                self.assertFalse(output.exists())
                self.assertFalse(receipt.exists())

    def test_degraded_completion_is_incomplete_and_not_published(self):
        with np.load(self.candidates) as old:
            arrays = {key: old[key] for key in old.files}
        arrays["prior_valid"][0, 0, 0, 2] = 0
        np.savez(self.candidates, **arrays)
        policy = json.loads(self.policy.read_text())
        policy["mass_threshold"][0] = 2e-6
        self.policy.write_text(json.dumps(policy))
        manifest = json.loads(self.manifest.read_text())
        manifest["candidates"]["sha256"] = module.sha(self.candidates)
        manifest["policy"]["sha256"] = module.sha(self.policy)
        self.manifest.write_text(json.dumps(manifest))
        output, receipt = self.p / "output.nc", self.p / "receipt.json"
        with self.assertRaisesRegex(ValueError, r"reason=INCOMPLETE \(0\)"):
            module.run_real_and_complete(self.manifest, output, receipt)
        self.assertFalse(output.exists())
        self.assertFalse(receipt.exists())

    def test_out_of_profile_bounds_and_caps_fail_before_producer(self):
        for key, slot, value in (("upper", 0, 1e-8), ("number_cap", 1, 1.00001e6)):
            with self.subTest(key=key):
                policy = json.loads(self.policy.read_text())
                previous = policy[key][slot]
                policy[key][slot] = value
                self.policy.write_text(json.dumps(policy))
                manifest = json.loads(self.manifest.read_text())
                manifest["policy"]["sha256"] = module.sha(self.policy)
                self.manifest.write_text(json.dumps(manifest))
                output, receipt = self.p / "output.nc", self.p / "receipt.json"
                with mock.patch.object(module.subprocess, "run") as run:
                    with self.assertRaisesRegex(ValueError, "KDM6 source"):
                        module.run_real_and_complete(self.manifest, output, receipt)
                    run.assert_not_called()
                self.assertFalse(output.exists())
                self.assertFalse(receipt.exists())
                policy[key][slot] = previous
                self.policy.write_text(json.dumps(policy))

    def test_source_profile_hash_is_required(self):
        with mock.patch.object(module, "KDM6_REFERENCE", self.source):
            with self.assertRaisesRegex(ValueError, "reference source hash mismatch"):
                module.validate_kdm6_policy(json.loads(self.policy.read_text()))

    def test_policy_tamper_is_rejected(self):
        self.policy.write_text("{}")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            module.run_real_and_complete(self.manifest, self.p / "output.nc", self.p / "receipt.json")

    def test_wrong_source_binding_rolls_back(self):
        with Dataset(self.template, "r+") as ds:
            ds["T"][0, 0, 0, 0] = 2
        m = json.loads(self.manifest.read_text())
        m["inputs"][1]["sha256"] = module.sha(self.template)
        self.manifest.write_text(json.dumps(m))
        output, receipt = self.p / "output.nc", self.p / "receipt.json"
        with self.assertRaisesRegex(ValueError, "candidate source hash mismatch"):
            module.run_real_and_complete(self.manifest, output, receipt)
        self.assertFalse(output.exists())
        self.assertFalse(receipt.exists())


if __name__ == "__main__":
    unittest.main()
