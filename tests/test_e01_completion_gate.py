#!/usr/bin/env python3
"""Unit tests for the isolated E01 completion gate."""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import netCDF4
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools/e01_completion_gate.py"
MODULE_SPEC = importlib.util.spec_from_file_location("e01_completion_gate", TOOL_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
GATE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(GATE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_times(path: Path, valid_time: str, background_time: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    valid_epoch = datetime.fromisoformat(valid_time.replace("Z", "+00:00")).timestamp()
    background_epoch = datetime.fromisoformat(
        background_time.replace("Z", "+00:00")
    ).timestamp()
    with netCDF4.Dataset(path, "w", format="NETCDF4") as dataset:
        dataset.createDimension("record", 1)
        for name, value in (("valtime", valid_epoch), ("reftime", background_epoch)):
            variable = dataset.createVariable(name, "f8", ("record",))
            variable.units = GATE.REPLAY.UTC_EPOCH_UNITS
            variable[:] = value


def write_vrt(path: Path, valid_time: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    epoch = datetime.fromisoformat(valid_time.replace("Z", "+00:00")).timestamp()
    with netCDF4.Dataset(path, "w", format="NETCDF4") as dataset:
        for name, size in (
            ("record", 1),
            ("z", 22),
            ("y", 283),
            ("x", 235),
            ("nav", 1),
            ("namelen", 132),
        ):
            dataset.createDimension(name, size)
        tid = dataset.createVariable("tid", "f4", ("record", "z", "y", "x"))
        tid.units = "NUL"
        tid[:] = np.float32(-10.0)
        tid[0, 10, 100, 100] = np.float32(2.0)
        level = dataset.createVariable("level", "f4", ("z",))
        level.units = "hectopascals"
        level[:] = np.arange(50.0, 1100.1, 50.0, dtype=np.float32)
        for name in ("valtime", "reftime"):
            variable = dataset.createVariable(name, "f8", ("record",))
            variable.units = GATE.REPLAY.UTC_EPOCH_UNITS
            variable[:] = epoch


class E01GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="e01-gate-test-"))
        self.valid_time = "2026-08-16T12:00:00Z"
        self.background_time = "2026-08-16T06:00:00Z"
        self.row: dict[str, str] = {
            "case_id": "20260816T120000Z",
            "valid_time_utc": self.valid_time,
            "background_reftime_utc": self.background_time,
            "laps_stamp": "262281200",
        }
        for role in ("fua", "fsf"):
            relative = f"ANAL/NE57/DAOU/00/lapsprd/{role}/wrf/{role}.nc"
            path = self.root / relative
            write_times(path, self.valid_time, self.background_time)
            self.row[f"{role}_path"] = relative
            self.row[f"{role}_sha256"] = sha256(path)
        for role in ("vrz", "vrt"):
            relative = f"ANAL/NE57/DAOU/00/lapsprd/{role}/{self.row['laps_stamp']}.{role}"
            path = self.root / relative
            if role == "vrt":
                write_vrt(path, self.valid_time)
            else:
                write_times(path, self.valid_time, self.valid_time)
            self.row[f"{role}_path"] = relative
            self.row[f"{role}_sha256"] = sha256(path)
        lw3 = self.root / "klaps-v5.0_/baseline/results/input.lw3"
        lw3.parent.mkdir(parents=True, exist_ok=True)
        lw3.write_bytes(b"lw3 input\n")
        self.row["lw3_path"] = str(lw3.relative_to(self.root))
        self.row["lw3_sha256"] = sha256(lw3)
        lgt = self.root / "ANAL/NE57/DAOU/00/lapsprd/lgt/262281200.lgt"
        lgt.parent.mkdir(parents=True, exist_ok=True)
        lgt.write_bytes(b"1       1        0\n")
        self.lgt_hash = sha256(lgt)

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def test_bind_case_inputs_checks_cycle_and_vrt_snapshot(self) -> None:
        receipt = GATE.bind_case_inputs(
            self.root,
            self.row,
            "20260816T060000Z",
            self.lgt_hash,
        )
        self.assertEqual(receipt["vrt_status"], "PASS")
        self.assertEqual(receipt["source_cycle_id"], "20260816T060000Z")
        self.assertEqual(len(receipt["input_hashes"]), 6)

    def test_equal_valid_time_with_different_cycle_is_rejected(self) -> None:
        with self.assertRaises(GATE.GateError):
            GATE.bind_case_inputs(
                self.root,
                self.row,
                "20260816T070000Z",
                self.lgt_hash,
            )

    def test_preexisting_generated_com_is_rejected(self) -> None:
        stale = self.root / "lapsprd/lco/262281200.lco"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"stale COM")
        with self.assertRaises(GATE.GateError):
            GATE.assert_fresh_generated_namespace(GATE.inventory(self.root))

    def test_missing_producer_is_rejected_by_hash_binding(self) -> None:
        producer = self.root / "build/klps_anal_temp.exe"
        producer.parent.mkdir()
        producer.write_bytes(b"producer")
        with self.assertRaises(GATE.GateError):
            GATE.bind_producer_executable(
                producer, "0" * 64, "temperature"
            )

    def test_missing_producer_path_is_rejected_before_launch(self) -> None:
        with self.assertRaises(GATE.GateError):
            GATE.bind_producer_executable(
                self.root / "build/does-not-exist.exe",
                "0" * 64,
                "temperature",
            )

    def test_nonzero_exit_is_fail_stop(self) -> None:
        with self.assertRaises(GATE.GateError):
            GATE.assert_stage_success("temperature", 127, "surface", "surface")

    def test_stage_order_requires_vrt_before_temperature(self) -> None:
        with self.assertRaises(GATE.GateError):
            GATE.assert_stage_success(
                "temperature", 0, "surface", "vrt_complete_gate"
            )

    def test_stage_predecessor_cannot_be_caller_selected(self) -> None:
        with self.assertRaises(GATE.GateError):
            GATE.assert_stage_success(
                "temperature", 0, "vrt_complete_gate", "surface"
            )

    def test_stage_predecessor_is_derived_for_canonical_sequence(self) -> None:
        GATE.assert_stage_success("temperature", 0, "vrt_complete_gate")

    def test_negative_cause_must_match_named_fault(self) -> None:
        with self.assertRaises(GATE.GateError):
            GATE.assert_fault_specific_rejection(
                "stale-com", ["stage wind_openmp exited 127"], []
            )

    def test_negative_cause_and_prefix_are_checked(self) -> None:
        GATE.assert_fault_specific_rejection(
            "fail-stage",
            ["stage temperature exited 1"],
            [
                {"stage": "wind_openmp", "exit": 0},
                {"stage": "surface", "exit": 0},
                {"stage": "vrt_complete_gate", "exit": 0},
                {"stage": "temperature", "exit": 1},
            ],
        )


if __name__ == "__main__":
    unittest.main()
