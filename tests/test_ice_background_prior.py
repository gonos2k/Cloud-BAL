"""Native boundary and handoff tests for independently attested ice backgrounds."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zlib

import numpy as np
from netCDF4 import Dataset, default_fillvals

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import initialize_model_moments as moments
import propose_ice_background as proposal


class IceBackgroundPriorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all(os.environ.get(k) for k in ("ICE_BACKGROUND_DRIVER", "MODEL_MOMENT_DRIVER")):
            raise unittest.SkipTest("requires compiled Intel ice and model moment drivers")

    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(temp.cleanup)
        self.p = Path(temp.name)
        self.analysis, self.background = self.p / "analysis.nc", self.p / "background.nc"
        self.make_native(self.analysis, False)
        self.make_native(self.background, True)
        self.mask = self.p / "mask.npz"
        self.write_mask(np.array([[[1, 0]], [[0, 0]]], dtype=np.int32))
        self.policy = self.p / "policy.json"
        self.policy.write_text(json.dumps({"source": "fixture", "declared_before_experiment": True,
            "mp_physics": 37, "mass_threshold": [0]*5, "lower": [1e-14, 1e-15, 3e-10, 0, 100],
            "upper": [2e-10, 1e-9, 1e-5, 0, 900], "number_cap": [5e10, 1e6, 5e7, 2e10]}))
        self.authority = self.p / "authority.json"
        self.write_authority()
        self.manifest = self.p / "manifest.json"
        self.refresh_manifest()
        self.output, self.receipt = self.p / "proposal.npz", self.p / "receipt.json"

    def make_native(self, path, background):
        with Dataset(path, "w") as ds:
            for name, length in zip(moments.DIMS, (1, 2, 1, 2)):
                ds.createDimension(name, length)
            ds.createDimension("bottom_top_stag", 3)
            ds.createDimension("DateStrLen", 19)
            ds.MP_PHYSICS, ds.USE_THETA_M = 37, 0
            ds.START_DATE = ds.SIMULATION_START_DATE = ("2026-08-16_06:00:00" if background else "2026-08-16_12:00:00")
            for name, value in zip(proposal.GRID_ATTRIBUTES, (1, 5000., 5000., 38., 126., 30., 60., 126.)):
                ds.setncattr(name, value)
            ds.createVariable("Times", "S1", ("Time", "DateStrLen"))[:] = np.frombuffer(
                b"2026-08-16_12:00:00", dtype="S1").reshape(1, 19)
            for name, dims in proposal.GRID_VARIABLES.items():
                ds.createVariable(name, "f4", dims)[:] = np.arange(np.prod([len(ds.dimensions[d]) for d in dims]), dtype="f4").reshape(tuple(len(ds.dimensions[d]) for d in dims))
            values = {**dict.fromkeys(moments.MASS, 1e-6), **dict.fromkeys(moments.MOMENT, 0),
                      "QICE": 1e-6 if background else 2e-6, "QSNOW": 3e-6 if background else 6e-6,
                      "QNICE": 1e4 if background else 0, "AL": .2, "ALB": .8, "P": 1000,
                      "PB": 99000, "T": 0, "QVAPOR": .01, "U": 3}
            for name, value in values.items():
                var = ds.createVariable(name, "f4", moments.DIMS)
                if name in moments.UNITS:
                    var.units = moments.UNITS[name]
                var[:] = value

    def item(self, path):
        return {"path": str(path), "sha256": moments.sha(path)}

    def write_mask(self, mask):
        np.savez(self.mask, valid=mask, source_sha256=moments.sha(self.analysis))

    def write_authority(self, **updates):
        authority = {"kind": "prior_cycle_forecast", "source": "fixture prior cycle",
                     "independence_attestation": "independent fixture forecast",
                     "cycle_start": "2026-08-16_06:00:00", "mass_basis": "dry_air",
                     "microphysics_source_sha256": moments.KDM6_REFERENCE_SHA256,
                     "analysis_sha256": moments.sha(self.analysis), "background_sha256": moments.sha(self.background)}
        authority.update(updates)
        self.authority.write_text(json.dumps(authority))

    def refresh_manifest(self):
        manifest = {"schema": "background_ice_prior_v1", "mass_basis": "dry_air"}
        for key, path in (("analysis", self.analysis), ("background", self.background),
                          ("authority", self.authority), ("mask", self.mask),
                          ("driver", Path(os.environ["ICE_BACKGROUND_DRIVER"])), ("policy", self.policy)):
            manifest[key] = self.item(path)
        self.manifest.write_text(json.dumps(manifest))

    def run_proposal(self):
        return proposal.generate(self.manifest, self.output, self.receipt, self.p)

    def reject(self):
        with self.assertRaises((ValueError, KeyError, OSError)):
            self.run_proposal()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.receipt.exists())

    def update_background(self, **values):
        with Dataset(self.background, "r+") as ds:
            for name, value in values.items():
                ds[name][:] = value
        self.write_authority()
        self.refresh_manifest()

    def test_fraction_number_and_selection(self):
        report = self.run_proposal()
        self.assertEqual(report["selected_cells"], 1)
        with np.load(self.output) as result:
            np.testing.assert_array_equal(result["valid"], np.array([[[1, 0]], [[0, 0]]]))
            self.assertEqual(result["provenance"].item(), 2)
            np.testing.assert_allclose([result[n][0, 0, 0] for n in ("qi", "qs", "ni")],
                                       [2e-6, 6e-6, 2e4], rtol=2e-7)
            self.assertEqual(result["source_sha256"].item(), moments.sha(self.analysis))

    def test_all_snow_and_zero_mass(self):
        self.update_background(QICE=0, QSNOW=4e-6, QNICE=0)
        report = self.run_proposal()
        with np.load(self.output) as data:
            self.assertEqual(data["qi"][0, 0, 0], 0)
            self.assertAlmostEqual(float(data["qs"][0, 0, 0]), 8e-6, delta=1e-12)
            self.assertEqual(data["ni"][0, 0, 0], 0)
        self.assertEqual(report["selected_cells"], 1)
        self.output.unlink(); self.receipt.unlink()
        with Dataset(self.analysis, "r+") as ds:
            ds["QICE"][:] = 0; ds["QSNOW"][:] = 0
        self.write_mask(np.ones((2, 1, 2), dtype=np.int32))
        self.update_background(QICE=0, QSNOW=0, QNICE=0)
        self.run_proposal()
        with np.load(self.output) as data:
            for name in ("qi", "qs", "ni"):
                self.assertTrue(np.all(data[name] == 0))

    def test_missing_background_support_zero_number_and_cap_reject(self):
        for values in ({"QICE": 0, "QSNOW": 0, "QNICE": 0}, {"QICE": 1e-6, "QSNOW": 3e-6, "QNICE": 0},
                       {"QICE": 1e-6, "QSNOW": 3e-6, "QNICE": 6e5}):
            with self.subTest(values=values):
                self.update_background(**values)
                self.reject()

    def test_time_grid_units_and_authority_rejected(self):
        changes = ("same_cycle", "valid_time", "grid", "units", "authority")
        for change in changes:
            with self.subTest(change=change):
                self.make_native(self.background, True) if not self.background.exists() else None
                if change == "same_cycle":
                    with Dataset(self.background, "r+") as ds:
                        ds.START_DATE = ds.SIMULATION_START_DATE = "2026-08-16_12:00:00"
                    self.write_authority(cycle_start="2026-08-16_12:00:00")
                elif change == "valid_time":
                    with Dataset(self.background, "r+") as ds:
                        ds["Times"][:] = np.frombuffer(b"2026-08-16_13:00:00", dtype="S1").reshape(1, 19)
                    self.write_authority()
                elif change == "grid":
                    with Dataset(self.background, "r+") as ds:
                        ds["XLAT"][0, 0, 0] += 1
                    self.write_authority()
                elif change == "units":
                    with Dataset(self.background, "r+") as ds:
                        ds["QICE"].units = "g kg-1"
                    self.write_authority()
                else:
                    self.write_authority(independence_attestation="")
                self.refresh_manifest()
                self.reject()
                self.background.unlink()
                self.make_native(self.background, True)
                self.write_authority()
                self.refresh_manifest()

    def test_input_identity_changes_during_driver_rejected(self):
        run = proposal.subprocess.run
        def mutate(*args, **kwargs):
            result = run(*args, **kwargs)
            self.authority.write_text(self.authority.read_text() + " ")
            return result
        with mock.patch.object(proposal.subprocess, "run", side_effect=mutate):
            self.reject()

    def test_preexisting_and_publication_failure_preserve_files(self):
        for existing in (self.output, self.receipt):
            with self.subTest(existing=existing):
                existing.write_bytes(b"keep")
                with self.assertRaises(ValueError):
                    self.run_proposal()
                self.assertEqual(existing.read_bytes(), b"keep")
                existing.unlink()
        original_link = os.link
        def fail_second(source, target):
            if Path(target) == self.output:
                raise OSError("proposal link failure")
            return original_link(source, target)
        with mock.patch.object(proposal.os, "link", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "proposal link failure"):
                self.run_proposal()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.receipt.exists())

    def test_rollback_does_not_unlink_replacement_receipt(self):
        original_link = os.link
        def replace_then_fail(source, target):
            if Path(target) == self.output:
                self.receipt.unlink()
                self.receipt.write_bytes(b"replacement")
                raise OSError("proposal link failure")
            return original_link(source, target)
        with mock.patch.object(proposal.os, "link", side_effect=replace_then_fail):
            with self.assertRaisesRegex(OSError, "proposal link failure"):
                self.run_proposal()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.receipt.read_bytes(), b"replacement")

    def test_missing_or_corrupt_producer_receipt_rejected_by_handoff(self):
        self.run_proposal()
        original = self.receipt.read_text()
        for replacement in (None, original.replace('"status": "PASS"', '"status": "FAIL"')):
            with self.subTest(replacement=replacement is not None):
                if replacement is None:
                    self.receipt.unlink()
                else:
                    self.receipt.write_text(replacement)
                with self.assertRaises((ValueError, OSError)):
                    moments.write_ice_snow_partition(self.output, moments.sha(self.analysis),
                                                      (2, 1, 2), self.p / "partition.bin")
                self.assertFalse((self.p / "partition.bin").exists())
        self.receipt.write_text(original)

    def test_implicit_default_fill_in_grid_rejected(self):
        with Dataset(self.background, "r+") as ds:
            self.assertNotIn("_FillValue", ds["XLAT"].ncattrs())
            ds["XLAT"][0, 0, 0] = np.float32(default_fillvals["f4"])
        self.write_authority()
        self.refresh_manifest()
        self.reject()

    def test_proposal_handoff_to_model_completion(self):
        self.run_proposal()
        shape = (5, 2, 1, 2)
        zero = np.zeros(shape)
        prior = np.ones(shape) * 1e-9
        prior[0] = 1e-10; prior[1] = 1e-10; prior[3] = 5; prior[4] = 400
        candidates = self.p / "candidates.npz"
        np.savez(candidates, source_sha256=moments.sha(self.analysis),
                 background_value=zero, background_valid=zero.astype("i4"), background_provenance=zero.astype("i4"),
                 prior_value=prior, prior_valid=np.ones(shape, dtype="i4"), prior_provenance=np.full(shape, 3, dtype="i4"),
                 observed_value=zero, observed_valid=zero.astype("i4"), observed_provenance=zero.astype("i4"))
        work = self.p / "completion"; work.mkdir()
        output = self.p / "completed.nc"
        result = moments.complete_file(self.analysis, output, Path(os.environ["MODEL_MOMENT_DRIVER"]),
            json.loads(self.policy.read_text()), candidates, work, 0, self.output)
        provenance = np.frombuffer(zlib.decompress(base64.b64decode(result["provenance_data"])), dtype="<i4").reshape(shape)
        self.assertEqual(provenance[1, 0, 0, 0], 2)
        with Dataset(output) as ds, Dataset(self.analysis) as original, np.load(self.output) as part:
            for var, key in (("QICE", "qi"), ("QSNOW", "qs"), ("QNICE", "ni")):
                self.assertEqual(ds[var][0, 0, 0, 0], part[key][0, 0, 0])
            for name in ("T", "QVAPOR", "QCLOUD", "QRAIN", "QGRAUP"):
                np.testing.assert_array_equal(ds[name][:], original[name][:])


if __name__ == "__main__":
    unittest.main()
