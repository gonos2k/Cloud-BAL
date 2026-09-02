#!/usr/bin/env python3
"""Fixture tests for the fail-closed original-upstream replay planner."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from datetime import datetime
from pathlib import Path

import netCDF4
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools/original_upstream_replay.py"
MODULE_SPEC = importlib.util.spec_from_file_location("upstream_replay", TOOL_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
REPLAY = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(REPLAY)
CHECKER_PATH = REPO_ROOT / "tools/check_qbal_real_inputs.py"
CHECKER_SPEC = importlib.util.spec_from_file_location("qbal_input_checker", CHECKER_PATH)
assert CHECKER_SPEC is not None and CHECKER_SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(CHECKER_SPEC)
CHECKER_SPEC.loader.exec_module(CHECKER)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_vrt(path: Path, valid_time: str, *, all_masked: bool = False) -> None:
    epoch = datetime.fromisoformat(valid_time.replace("Z", "+00:00")).timestamp()
    path.parent.mkdir(parents=True, exist_ok=True)
    with netCDF4.Dataset(path, "w", format="NETCDF4") as dataset:
        dataset.createDimension("record", 1)
        dataset.createDimension("z", 22)
        dataset.createDimension("y", 283)
        dataset.createDimension("x", 235)
        dataset.createDimension("nav", 1)
        dataset.createDimension("namelen", 132)
        options = {"zlib": True, "complevel": 1}
        if all_masked:
            options["fill_value"] = np.float32(-10.0)
        tid = dataset.createVariable("tid", "f4", ("record", "z", "y", "x"), **options)
        tid.units = "NUL"
        if all_masked:
            tid[:] = np.ma.masked_all((1, 22, 283, 235), dtype=np.float32)
        else:
            tid[:] = np.float32(-10.0)
            tid[0, 10, 100, 100] = np.float32(2.0)
        level = dataset.createVariable("level", "f4", ("z",))
        level.units = "hectopascals"
        level[:] = np.arange(50.0, 1100.1, 50.0, dtype=np.float32)
        valtime = dataset.createVariable("valtime", "f8", ("record",))
        valtime.units = REPLAY.UTC_EPOCH_UNITS
        valtime[:] = epoch
        reftime = dataset.createVariable("reftime", "f8", ("record",))
        reftime.units = REPLAY.UTC_EPOCH_UNITS
        reftime[:] = epoch


class ReplayPlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        allowed = REPO_ROOT / "scratch/original_upstream_replay"
        allowed.mkdir(parents=True, exist_ok=True)
        self.test_root = allowed / f"fixture_{uuid.uuid4().hex}"
        self.workspace = self.test_root / "workspace"
        self.workspace.mkdir(parents=True)
        self.source_tree = self.workspace / "klaps-v5.0_/src"
        self.source_tree.mkdir(parents=True)
        (self.source_tree / "source.f90").write_text("program fixture\nend\n")

    def tearDown(self) -> None:
        if self.test_root.exists():
            for path in self.test_root.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    path.chmod(0o600)
            shutil.rmtree(self.test_root)

    def make_contract(self) -> tuple[Path, Path, dict[str, str]]:
        common_inputs: dict[str, Path] = {}
        for role in ("fua", "fsf", "lw3", "vrz"):
            path = self.workspace / REPLAY.CASE_ALLOWED_ROOTS[role] / f"input.{role}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((role + "\n").encode())
            common_inputs[role] = path

        executable_root = self.workspace / "klaps-v5.0_/bin"
        executable_root.mkdir(parents=True)
        executables: dict[str, Path] = {}
        for executable_name in REPLAY.STAGE_EXECUTABLE.values():
            executable = executable_root / executable_name
            shutil.copyfile("/bin/true", executable)
            with executable.open("ab") as stream:
                stream.write(b"Intel(r) Visual Fortran run-time error")
            executable.chmod(0o500)
            executables[executable_name] = executable
        config = self.workspace / "ANAL/NE57/DABA/namelist/fixture.nl"
        config.parent.mkdir(parents=True)
        config.write_text("&fixture /\n")

        rows: list[dict[str, str]] = []
        for case_id, valid_time, laps_stamp in REPLAY.EXPECTED_CASES:
            vrt = self.workspace / REPLAY.CASE_ALLOWED_ROOTS["vrt"] / f"{laps_stamp}.vrt"
            write_vrt(vrt, valid_time)
            row = {
                "case_id": case_id,
                "valid_time_utc": valid_time,
                "background_reftime_utc": "2026-08-16T06:00:00Z",
                "laps_stamp": laps_stamp,
            }
            for role in ("fua", "fsf", "lw3", "vrz"):
                relative = common_inputs[role].relative_to(self.workspace).as_posix()
                row[f"{role}_path"] = relative
                row[f"{role}_sha256"] = sha256(common_inputs[role])
            row["vrt_path"] = vrt.relative_to(self.workspace).as_posix()
            row["vrt_sha256"] = sha256(vrt)
            rows.append(row)

        manifest = self.test_root / "cases.tsv"
        fieldnames = list(rows[0])
        with manifest.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

        config_relative = config.relative_to(self.workspace).as_posix()
        stages = []
        for stage_id in REPLAY.STAGE_SEQUENCE:
            stage = {
                "id": stage_id,
                "product": REPLAY.STAGE_PRODUCT[stage_id],
                "closure_blockers": [] if stage_id == "vrt_complete_gate" else [
                    f"FIXTURE_{stage_id.upper()}_CLOSURE_BLOCKED"
                ],
            }
            executable_name = REPLAY.STAGE_EXECUTABLE.get(stage_id)
            if executable_name is not None:
                executable = executables[executable_name]
                stage["executable"] = executable.relative_to(self.workspace).as_posix()
                stage["executable_sha256"] = sha256(executable)
            stages.append(stage)
        specification = {
            "schema": 1,
            "contract": "original_klaps_upstream_replay_plan_v1",
            "source_tree": "klaps-v5.0_",
            "source_tree_path": "klaps-v5.0_/src",
            "compiler_family": "Intel",
            "case_manifest_sha256": sha256(manifest),
            "sandbox_probe": {
                "executable": "/usr/bin/bwrap",
                "executable_sha256": sha256(Path("/usr/bin/bwrap")),
                "payload": "/usr/bin/true",
                "payload_sha256": sha256(Path("/usr/bin/true")),
            },
            "environment": {"OMP_DYNAMIC": "false"},
            "global_blockers": ["FIXTURE_INPUT_CLOSURE_BLOCKED"],
            "assets": [
                {
                    "role": "fixture_configuration",
                    "path": config_relative,
                    "sha256": sha256(config),
                }
            ],
            "stages": stages,
        }
        spec_path = self.test_root / "spec.json"
        spec_path.write_text(json.dumps(specification, indent=2) + "\n")
        original_hashes = {
            path.relative_to(self.workspace).as_posix(): sha256(path)
            for path in self.workspace.rglob("*")
            if path.is_file()
        }
        return manifest, spec_path, original_hashes

    def assert_blocked_manifest_contract(self, path: Path) -> None:
        parsed = CHECKER.load_pre_qbal_manifest(path.parent, sha256(path))
        self.assertEqual(parsed["status"], "BLOCKED", parsed["findings"])

    def test_only_declared_files_are_copied_and_execution_is_not_authorized(self) -> None:
        manifest, spec_path, original_hashes = self.make_contract()
        output = self.test_root / "generation"
        command = [
            sys.executable,
            str(TOOL_PATH),
            "--workspace-root",
            str(self.workspace),
            "--case-manifest",
            str(manifest),
            "--spec",
            str(spec_path),
            "--spec-sha256",
            sha256(spec_path),
            "--root",
            str(output),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 3, completed.stderr)
        receipt_path = output / "PRE_QBAL_MANIFEST.json"
        self.assertTrue(receipt_path.is_file())
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["generation_status"], "BLOCKED")
        self.assertFalse(receipt["execution_requested"])
        self.assertFalse(receipt["execution_started"])
        self.assertFalse(receipt["final_bigfile_allowed_as_input"])
        self.assertIn("FIXTURE_INPUT_CLOSURE_BLOCKED", receipt["blockers"])
        self.assertIn("UPSTREAM_EXECUTION_NOT_AUTHORIZED", receipt["blockers"])
        self.assertEqual(
            [(case["case_id"], case["vrt_completion_gate"]["status"])
             for case in receipt["cases"]],
            [(case_id, "PASS") for case_id, _, _ in REPLAY.EXPECTED_CASES],
        )
        for case in receipt["cases"]:
            self.assertIsNone(case["input_closure_sha256"])
            self.assertEqual(len(case["declared_input_receipt_sha256"]), 64)
            self.assertEqual(set(case["products"]), set(REPLAY.PRODUCT_STAGE))
            for kind, product in case["products"].items():
                self.assertEqual(product["path"], f"{kind}/{case['laps_stamp']}.{kind}")
                self.assertEqual(product["status"], "NOT_PRODUCED")

        copied = [path for path in output.rglob("*") if path.is_file()]
        self.assertGreater(len(copied), 1)
        self.assertFalse(any(path.is_symlink() for path in output.rglob("*")))
        for path in copied:
            if path.name == "PRE_QBAL_MANIFEST.json":
                continue
            stat = path.stat(follow_symlinks=False)
            self.assertEqual(stat.st_nlink, 1)
            self.assertEqual(stat.st_mode & 0o222, 0)

        after_hashes = {
            path.relative_to(self.workspace).as_posix(): sha256(path)
            for path in self.workspace.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after_hashes, original_hashes)

    def test_forbidden_and_unsafe_paths_fail_closed(self) -> None:
        self.assertIsNotNone(REPLAY.forbidden_input("final/bigfile/input.nc"))
        self.assertIsNotNone(REPLAY.forbidden_input("lapsprep/wps/LAPS:x"))
        self.assertIsNotNone(REPLAY.forbidden_input("prepared/LAPS:final/payload.nc"))
        self.assertIsNotNone(REPLAY.forbidden_input("prepared/KLBG:final/payload.nc"))
        self.assertIsNotNone(REPLAY.forbidden_input("balance/lw3/x.lw3"))
        self.assertIsNotNone(REPLAY.forbidden_input("met_em.d01.nc"))
        self.assertIsNone(REPLAY.forbidden_input("prepared/vrt/input.vrt"))
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.safe_relative("../ANAL/input")

        _, spec_path, _ = self.make_contract()
        specification = json.loads(spec_path.read_text())
        specification["source_tree_path"] = "scratch/bigfile/klaps-v5.0_/src"
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.validate_spec(specification)

        specification["source_tree_path"] = "ANAL/NE57/DABA"
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.validate_spec(specification)

        symlink = self.source_tree / "source-link.f90"
        symlink.symlink_to(self.source_tree / "source.f90")
        _, blockers = REPLAY.hash_tree(self.source_tree)
        self.assertTrue(any("SOURCE_TREE_SYMLINK_FORBIDDEN" in item for item in blockers))
        symlink.unlink()

        hardlink = self.source_tree / "source-hardlink.f90"
        os.link(self.source_tree / "source.f90", hardlink)
        _, blockers = REPLAY.hash_tree(self.source_tree)
        self.assertTrue(any("SOURCE_TREE_HARDLINK_FORBIDDEN" in item for item in blockers))
        hardlink.unlink()

        outside_tree = self.test_root / "outside-source-tree"
        outside_tree.mkdir()
        tree_alias = self.workspace / "klaps-v5.0_/source-alias"
        tree_alias.symlink_to(outside_tree, target_is_directory=True)
        _, tree_error = REPLAY.contained_directory(
            self.workspace, "klaps-v5.0_/source-alias"
        )
        self.assertEqual(tree_error, "SOURCE_TREE_PATH_CONTAINS_SYMLINK")
        tree_alias.unlink()

        non_intel = self.test_root / "not_intel.exe"
        non_intel.write_bytes(b"\x7fELF fixture without compiler identity")
        self.assertFalse(REPLAY.intel_binary(non_intel))

        escaped = self.test_root / "escaped"
        source = self.test_root / "source"
        source.write_text("source")
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.immutable_copy(
                source,
                escaped,
                sha256(source),
                self.test_root / "workspace",
            )

        sentinel = self.test_root / "sandbox_executed"
        fake_bwrap = self.test_root / "bwrap"
        fake_bwrap.write_text(f"#!/bin/sh\ntouch {sentinel}\n")
        fake_bwrap.chmod(0o700)
        probe = REPLAY.probe_strict_sandbox(
            {
                "sandbox_probe": {
                    "executable": str(fake_bwrap),
                    "executable_sha256": sha256(fake_bwrap),
                    "payload": "/usr/bin/true",
                    "payload_sha256": sha256(Path("/usr/bin/true")),
                }
            }
        )
        self.assertEqual(probe["status"], "BLOCKED")
        self.assertFalse(sentinel.exists())

    def test_invalid_spec_still_emits_a_blocked_manifest(self) -> None:
        output = self.test_root / "invalid_generation"
        invalid_spec = self.test_root / "invalid_spec.json"
        invalid_spec.write_text("{}\n")
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOL_PATH),
                "--workspace-root",
                str(self.workspace),
                "--case-manifest",
                str(self.test_root / "missing.tsv"),
                "--spec",
                str(invalid_spec),
                "--spec-sha256",
                sha256(invalid_spec),
                "--root",
                str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 3)
        receipt = json.loads((output / "PRE_QBAL_MANIFEST.json").read_text())
        self.assertEqual(receipt["generation_status"], "BLOCKED")
        self.assertEqual(
            [case["case_id"] for case in receipt["cases"]],
            [case_id for case_id, _, _ in REPLAY.EXPECTED_CASES],
        )
        self.assertTrue(receipt["blockers"][0].startswith("REPLAY_SPEC_OR_CASE_MANIFEST_INVALID"))
        self.assert_blocked_manifest_contract(output / "PRE_QBAL_MANIFEST.json")

    def test_missing_workspace_still_emits_a_blocked_manifest(self) -> None:
        manifest, spec_path, _ = self.make_contract()
        output = self.test_root / "missing_workspace_generation"
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOL_PATH),
                "--workspace-root",
                str(self.test_root / "missing_workspace"),
                "--case-manifest",
                str(manifest),
                "--spec",
                str(spec_path),
                "--spec-sha256",
                sha256(spec_path),
                "--root",
                str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 3)
        receipt = json.loads((output / "PRE_QBAL_MANIFEST.json").read_text())
        self.assertEqual(receipt["generation_status"], "BLOCKED")
        self.assert_blocked_manifest_contract(output / "PRE_QBAL_MANIFEST.json")

    def test_reordered_cases_emit_a_valid_blocked_manifest(self) -> None:
        manifest, spec_path, _ = self.make_contract()
        with manifest.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        with manifest.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=list(rows[0]), delimiter="\t"
            )
            writer.writeheader()
            writer.writerows(reversed(rows))
        specification = json.loads(spec_path.read_text())
        specification["case_manifest_sha256"] = sha256(manifest)
        spec_path.write_text(json.dumps(specification, indent=2) + "\n")

        output = self.test_root / "reordered_case_generation"
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOL_PATH),
                "--workspace-root",
                str(self.workspace),
                "--case-manifest",
                str(manifest),
                "--spec",
                str(spec_path),
                "--spec-sha256",
                sha256(spec_path),
                "--root",
                str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 3)
        self.assert_blocked_manifest_contract(output / "PRE_QBAL_MANIFEST.json")

    def test_vrt_mask_and_stage_order_are_fail_closed(self) -> None:
        masked_vrt = self.test_root / "all_masked.vrt"
        valid_time = REPLAY.EXPECTED_CASES[0][1]
        write_vrt(masked_vrt, valid_time, all_masked=True)
        status, findings = REPLAY.vrt_complete(masked_vrt, valid_time)
        self.assertEqual(status, "BLOCKED")
        self.assertIn("VRT_FINITE_COVERAGE_INSUFFICIENT", findings)

        sparse_vrt = self.test_root / "sparse.vrt"
        write_vrt(sparse_vrt, valid_time, all_masked=True)
        with netCDF4.Dataset(sparse_vrt, "r+") as dataset:
            dataset.variables["tid"][0, 0, 0, 0] = np.float32(0.0)
        status, findings = REPLAY.vrt_complete(sparse_vrt, valid_time)
        self.assertEqual(status, "BLOCKED")
        self.assertIn("VRT_FINITE_COVERAGE_INSUFFICIENT", findings)

        shifted_level_vrt = self.test_root / "shifted_level.vrt"
        write_vrt(shifted_level_vrt, valid_time)
        with netCDF4.Dataset(shifted_level_vrt, "r+") as dataset:
            dataset.variables["level"][0] = np.nextafter(
                np.float32(50.0), np.float32(51.0)
            )
        status, findings = REPLAY.vrt_complete(shifted_level_vrt, valid_time)
        self.assertEqual(status, "BLOCKED")
        self.assertIn("VRT_PRESSURE_LEVELS_INVALID", findings)

        _, spec_path, _ = self.make_contract()
        specification = json.loads(spec_path.read_text())
        stages = specification["stages"]
        stages[2], stages[3] = stages[3], stages[2]
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.validate_spec(specification)

        specification = json.loads(spec_path.read_text())
        specification["assets"][0]["role"] = "../../escape"
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.validate_spec(specification)


if __name__ == "__main__":
    unittest.main()
