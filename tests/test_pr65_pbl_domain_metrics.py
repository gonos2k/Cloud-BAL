#!/usr/bin/env python3
"""Focused guards for PR65 domain-metrics extraction."""

from __future__ import annotations

import sys
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr65_pbl_domain_metrics import (  # noqa: E402
    ACTIVE_SHAPE_KJI,
    active_field,
    crop_slices,
    field_summary,
    validate_dataset,
    validate_run_receipt,
    validate_transition_replay_artifacts,
    validate_transition_binding,
)


def capture(stage: int = 1, timestep: int = 1) -> dict:
    bounds = {
        "ids": 1, "ide": 235, "jds": 1, "jde": 283, "kds": 1, "kde": 40,
        "ims": -4, "ime": 240, "jms": -4, "jme": 288, "kms": 1, "kme": 40,
        "its": 2, "ite": 233, "jts": 2, "jte": 281, "kts": 1, "kte": 39,
    }
    return {
        "stage": stage, "itimestep": timestep, "bounds": bounds,
        "params": {"dt_s": 20.0}, "active_shape_xyz": [232, 280, 39],
        "sha256": f"stage-{stage}",
    }


def transition() -> dict:
    return {"counts": {
        "exact_global_overlap": {"i": [2, 233], "j": [2, 281], "k": [1, 39],
                                 "runtime_epsilon": 1e-15},
        "sha256": {"pre": "stage-1", "post": "stage-2"},
    }}


class FakeVariable:
    name = "QCLOUD"
    dimensions = ("Time", "bottom_top", "south_north", "west_east")

    def __init__(self, values: np.ndarray) -> None:
        self.values = values

    def __getitem__(self, key):
        return self.values[key]


class FakeTimes:
    dimensions = ("Time", "DateStrLen")

    def __init__(self, values: tuple[str, ...]) -> None:
        self.values = np.array([[c.encode("ascii") for c in value] for value in values], dtype="S1")

    def __getitem__(self, key):
        return self.values[key]


class FakeDimension:
    def __init__(self, size: int) -> None:
        self.size = size

    def __len__(self) -> int:
        return self.size


class FakeDataset:
    dimensions = {name: FakeDimension(size) for name, size in {
        "Time": 2, "bottom_top": 39, "south_north": 282,
        "west_east": 234, "DateStrLen": 19,
    }.items()}

    def __init__(self, times: tuple[str, ...]) -> None:
        self.variables = {"Times": FakeTimes(times)}
        self.variables.update({name: FakeVariable(np.zeros((2, 39, 282, 234)) )
                               for name in ("QCLOUD", "QNCLOUD", "QGRAUP", "QNCCN", "REFL_10CM")})


class PR65PblDomainMetricsTest(unittest.TestCase):
    def test_crop_is_derived_from_exact_expected_global_bounds(self) -> None:
        slices = crop_slices(capture()["bounds"])
        self.assertEqual(tuple(s.start for s in slices), (0, 1, 1))
        self.assertEqual(tuple(s.stop for s in slices), (39, 281, 233))
        self.assertEqual(tuple(s.stop - s.start for s in slices), ACTIVE_SHAPE_KJI)

    def test_rejects_earlier_or_shifted_active_crop(self) -> None:
        record = capture()
        record["bounds"]["its"] = 1
        with self.assertRaisesRegex(ValueError, "active bounds"):
            crop_slices(record["bounds"])

    def test_transition_must_match_raw_bounds_and_raw_hashes(self) -> None:
        slices, qmin = validate_transition_binding(capture(1), capture(2), transition())
        self.assertEqual(slices[0], slice(0, 39))
        self.assertEqual(qmin, 1e-15)
        bad_hashes = transition()
        bad_hashes["counts"]["sha256"]["pre"] = "other"
        with self.assertRaisesRegex(ValueError, "hashes"):
            validate_transition_binding(capture(1), capture(2), bad_hashes)

    def test_rejects_non_first_capture_timestep(self) -> None:
        with self.assertRaisesRegex(ValueError, "timestep 1"):
            validate_transition_binding(capture(1, 2), capture(2, 2), transition())

    def test_active_field_rejects_masked_values(self) -> None:
        slices = crop_slices(capture()["bounds"])
        values = np.ma.masked_all((1, *ACTIVE_SHAPE_KJI), dtype=np.float32)
        with self.assertRaisesRegex(ValueError, "masked values"):
            active_field(FakeVariable(values), 0, slices)

    def test_field_summary_rejects_empty_finite_set(self) -> None:
        with self.assertRaisesRegex(ValueError, "no finite"):
            field_summary(np.array([np.nan, np.inf]), "test-time")

    def test_field_summary_rejects_overflowed_aggregate(self) -> None:
        values = np.array([np.finfo(np.float64).max, np.finfo(np.float64).max])
        with np.errstate(over="ignore"):
            with self.assertRaisesRegex(ValueError, "nonfinite field reduction"):
                field_summary(values, "overflow-time")

    def test_validates_baseline_and_candidate_layout_and_times(self) -> None:
        self.assertEqual(validate_dataset(FakeDataset((
            "2026-08-16_12:00:00", "2026-08-16_12:00:20")), "fixture"),
            ("2026-08-16_12:00:00", "2026-08-16_12:00:20"))
        with self.assertRaisesRegex(ValueError, "unexpected NetCDF Times"):
            validate_dataset(FakeDataset(("2026-08-16_12:00:00", "2026-08-16_12:01:00")), "fixture")
        bad_dimensions = FakeDataset(("2026-08-16_12:00:00", "2026-08-16_12:00:20"))
        bad_dimensions.dimensions = dict(bad_dimensions.dimensions)
        bad_dimensions.dimensions["west_east"] = FakeDimension(233)
        with self.assertRaisesRegex(ValueError, "unexpected NetCDF dimensions"):
            validate_dataset(bad_dimensions, "baseline-fixture")

    def test_run_receipt_binds_outputs_manifest_hash_and_single_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "runtime_reference_manifest.json"
            output = root / "wrfout"
            manifest.write_text("manifest\n")
            output.write_text("output\n")
            manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
            output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
            receipt = {
                "run_root": str(root), "returncode": 0, "input_integrity": "PASS",
                "output_isolation": "PASS", "changed_inputs": [], "input_read_issues": [],
                "output_issues": [],
                "inputs": [{"path": str(manifest), "sha256_before": manifest_hash,
                            "sha256_after": manifest_hash}],
                "outputs": [{"path": "wrfout", "nlink": 1, "sha256": output_hash}],
            }
            (root / "run-isolation.json").write_text(json.dumps(receipt))
            validate_run_receipt(root, ("wrfout",))
            receipt["outputs"][0]["path"] = "other/wrfout"
            (root / "run-isolation.json").write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "receipt path mismatch"):
                validate_run_receipt(root, ("wrfout",))
            receipt["outputs"][0]["path"] = "wrfout"
            os.link(output, root / "second-link")
            (root / "run-isolation.json").write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "link-count or hash"):
                validate_run_receipt(root, ("wrfout",))
            (root / "second-link").unlink()
            receipt["outputs"][0]["nlink"] = 1
            output.write_text("changed output\n")
            (root / "run-isolation.json").write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "link-count or hash"):
                validate_run_receipt(root, ("wrfout",))
            receipt["outputs"][0]["nlink"] = 2
            with self.assertRaisesRegex(ValueError, "link-count or hash"):
                validate_run_receipt(root, ("wrfout",))
            with self.assertRaisesRegex(ValueError, "required output"):
                validate_run_receipt(root, ("missing-output",))

    def test_transition_stage_and_mask_hashes_bind_to_receipt_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "pr63_transition_stages.raw"
            masks = root / "pr63_transition_masks.bin"
            stage.write_bytes(b"stage")
            masks.write_bytes(b"mask")
            transition_path = root / "replay.json"
            transition_path.write_text(json.dumps({
                "stage_text": {"sha256": hashlib.sha256(stage.read_bytes()).hexdigest()},
                "counts": {"sha256": {"masks": hashlib.sha256(masks.read_bytes()).hexdigest()}},
            }))
            stage_only = {"verified_outputs": ["pr63_transition_stages.raw"]}
            partial = validate_transition_replay_artifacts(root, transition_path, stage_only, False)
            self.assertTrue(partial["stage_raw_receipt_bound"])
            self.assertFalse(partial["mask_raw_receipt_bound"])
            with self.assertRaisesRegex(ValueError, "mask is not receipt-bound"):
                validate_transition_replay_artifacts(root, transition_path, stage_only, True)
            both = {"verified_outputs": ["pr63_transition_stages.raw", "pr63_transition_masks.bin"]}
            bound = validate_transition_replay_artifacts(root, transition_path, both, True)
            self.assertTrue(bound["mask_raw_receipt_bound"])
            stage.write_bytes(b"changed-stage")
            with self.assertRaisesRegex(ValueError, "stage raw hash mismatch"):
                validate_transition_replay_artifacts(root, transition_path, both, True)
            stage.write_bytes(b"stage")
            masks.write_bytes(b"changed-mask")
            with self.assertRaisesRegex(ValueError, "mask raw hash mismatch"):
                validate_transition_replay_artifacts(root, transition_path, both, True)


if __name__ == "__main__":
    unittest.main()
