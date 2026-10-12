#!/usr/bin/env python3
"""Regression test that candidate replays cannot mutate their source case."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
from pr81_native_case_copy import copy_case, file_sha256


class NativeCaseCopyTest(unittest.TestCase):
    def test_candidate_copy_keeps_source_executable_and_inputs_private(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pr81_case_copy_") as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "run"
            source.mkdir()
            (source / "namelist.input").write_text("&time_control /\n")
            (source / "wrfinput_d01").write_bytes(b"input-state")
            (source / "wrfbdy_d01").write_bytes(b"boundary-state")
            (source / "URBPARM.TBL").write_bytes(b"table-data")
            (source / "runtime_reference_manifest.json").write_text("{}\n")
            (source / "wrf.exe").write_bytes(b"baseline-executable")
            (source / "wrfout_d01_old").write_bytes(b"old-output")
            (source / "rsl.error.0000").write_text("old run log")
            candidate = root / "candidate.exe"
            candidate.write_bytes(b"candidate-executable")
            candidate.chmod(0o755)

            source_executable = source / "wrf.exe"
            source_digest = file_sha256(source_executable)
            source_identity = (source_executable.stat().st_dev,
                               source_executable.stat().st_ino)
            before = copy_case(source, candidate, destination)

            self.assertEqual(before["wrf.exe"], source_digest)
            self.assertEqual(file_sha256(source_executable), source_digest)
            self.assertEqual((source_executable.stat().st_dev,
                              source_executable.stat().st_ino), source_identity)
            self.assertEqual((destination / "wrf.exe").read_bytes(),
                             b"candidate-executable")
            self.assertNotEqual((
                (destination / "wrf.exe").stat().st_dev,
                (destination / "wrf.exe").stat().st_ino), source_identity)
            self.assertEqual((destination / "URBPARM.TBL").read_bytes(),
                             b"table-data")
            self.assertNotEqual(
                ((destination / "URBPARM.TBL").stat().st_dev,
                 (destination / "URBPARM.TBL").stat().st_ino),
                ((source / "URBPARM.TBL").stat().st_dev,
                 (source / "URBPARM.TBL").stat().st_ino))
            self.assertFalse((destination / "wrfout_d01_old").exists())
            self.assertFalse((destination / "rsl.error.0000").exists())
            self.assertEqual(file_sha256(source / "wrf.exe"), source_digest)

    def test_existing_destination_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pr81_case_copy_") as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "run"
            source.mkdir()
            destination.mkdir()
            candidate = root / "candidate.exe"
            candidate.write_bytes(b"candidate")
            candidate.chmod(0o755)
            with self.assertRaises(FileExistsError):
                copy_case(source, candidate, destination)


if __name__ == "__main__":
    unittest.main()
