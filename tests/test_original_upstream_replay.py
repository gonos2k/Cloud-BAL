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
from datetime import datetime, timedelta
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

    def test_cli_materializes_declared_lrs_and_rehashes_inventory(self) -> None:
        manifest, spec_path, _ = self.make_contract()
        specification = json.loads(spec_path.read_text())
        lrs_directory = self.workspace / "ANAL/NE57/DAOU/00/lapsprd/lrs"
        lrs_declarations: list[dict[str, str]] = []
        with manifest.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        for row in rows:
            source = lrs_directory / f"{row['laps_stamp']}.lrs"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(f"declared LRS {row['case_id']}\n".encode())
            lrs_declarations.append({
                "path": source.relative_to(self.workspace).as_posix(),
                "sha256": sha256(source),
            })
        specification["lrs_inputs"] = lrs_declarations
        spec_path.write_text(json.dumps(specification, indent=2) + "\n")

        output = self.test_root / "declared_lrs_generation"
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
        self.assertEqual(completed.returncode, 3, completed.stderr)
        receipt = json.loads((output / "PRE_QBAL_MANIFEST.json").read_text())
        for case in receipt["cases"]:
            selection = case["lrs_selection"]
            self.assertEqual(selection["status"], "SELECTED", selection)
            self.assertEqual(
                selection["inventory_sha256"],
                REPLAY.canonical_sha256(selection["inventory"]),
            )
            self.assertEqual(len(selection["inventory"]), len(rows))
            for inventory in selection["inventory"]:
                self.assertEqual(inventory["status"], "PASS")
                self.assertEqual(
                    inventory["materialized_sha256"], inventory["sha256"]
                )
                copied = (
                    output
                    / "cases"
                    / case["case_id"]
                    / "declared_inputs"
                    / "lrs"
                    / Path(str(inventory["source_path"])).name
                )
                self.assertTrue(copied.is_file())
                self.assertEqual(copied.stat().st_mode & 0o222, 0)

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

    def test_default_replay_spec_hash_pin_matches_repository_file(self) -> None:
        specification = REPO_ROOT / "tests/original_upstream_replay_20260816.json"
        self.assertEqual(sha256(specification), REPLAY.DEFAULT_REPLAY_SPEC_SHA256)

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

    def test_vrt_hash_binding_rejects_replacement_before_validation(self) -> None:
        valid_time = REPLAY.EXPECTED_CASES[0][1]
        relative = "ANAL/NE57/DAOU/00/lapsprd/vrt/262281200.vrt"
        source = self.workspace / relative
        write_vrt(source, valid_time)
        expected_hash = sha256(source)
        receipt, bound_path, findings = REPLAY.audit_declared_file(
            self.workspace,
            relative,
            expected_hash,
            "vrt",
            REPLAY.CASE_ALLOWED_ROOTS["vrt"],
        )
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(findings, [])
        self.assertIsNotNone(bound_path)

        write_vrt(source, valid_time)
        with netCDF4.Dataset(source, "r+") as dataset:
            dataset.variables["tid"][0, 10, 100, 100] = np.float32(1.0)
        self.assertNotEqual(sha256(source), expected_hash)
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.read_verified_bytes(source, expected_hash)

        write_vrt(source, valid_time)
        verified = REPLAY.read_verified_bytes(source, expected_hash)
        write_vrt(source, valid_time)
        with netCDF4.Dataset(source, "r+") as dataset:
            dataset.variables["tid"][0, 10, 100, 100] = np.float32(1.0)
        status, vrt_findings = REPLAY.vrt_complete(verified, valid_time)
        self.assertEqual(status, "PASS")
        self.assertEqual(vrt_findings, [])

    def test_encode_systime_matches_original_six_line_format(self) -> None:
        row = {
            "case_id": "20260816T120000Z",
            "valid_time_utc": "2026-08-16T12:00:00Z",
            "laps_stamp": "262281200",
        }
        self.assertEqual(
            REPLAY.encode_systime(row),
            b"  2102500800\n 262281200\n12\n00\n16-AUG-2026 1200\n26228\n",
        )

    def test_encode_systime_rejects_time_and_int32_contract_violations(self) -> None:
        valid = {
            "case_id": "20260816T120000Z",
            "valid_time_utc": "2026-08-16T12:00:00Z",
            "laps_stamp": "262281200",
        }
        for name, changes in (
            ("utc mismatch", {"valid_time_utc": "2026-08-16T12:00:00+01:00"}),
            ("stamp mismatch", {"laps_stamp": "262281201"}),
            ("nonzero seconds", {"valid_time_utc": "2026-08-16T12:00:30Z"}),
            (
                "int32 overflow",
                {
                    "case_id": "20290101T000000Z",
                    "valid_time_utc": "2029-01-01T00:00:00Z",
                    "laps_stamp": "290010000",
                },
            ),
        ):
            invalid = dict(valid)
            invalid.update(changes)
            with self.subTest(name=name), self.assertRaises(REPLAY.ReplayError):
                REPLAY.encode_systime(invalid)

    def _runtime_row(self) -> dict[str, str]:
        return {
            "case_id": "20260816T120000Z",
            "valid_time_utc": "2026-08-16T12:00:00Z",
            "laps_stamp": "262281200",
        }

    def _runtime_sources(
        self,
    ) -> tuple[list[tuple[dict[str, object], Path]], list[tuple[dict[str, object], Path]]]:
        assets: list[tuple[dict[str, object], Path]] = []
        for role, filename in (
            ("lc3_cdl_template", "lc3.cdl"),
            ("lcb_cdl_template", "lcb.cdl"),
            ("lcv_cdl_template", "lcv.cdl"),
            ("lps_cdl_template", "lps.cdl"),
            ("lt1_cdl_template", "lt1.cdl"),
            ("lsx_cdl_template", "lsx.cdl"),
            ("pbl_cdl_template", "pbl.cdl"),
            ("static_grid", "static.nest7grid"),
            ("grid_configuration_template", "nest7grid.parms"),
            ("pressure_configuration", "pressures.nl"),
            ("background_configuration", "background.nl"),
            ("temperature_configuration", "temp.nl"),
            ("surface_configuration", "surface_analysis.nl"),
            ("surface_drag_table", "drag_coef.dat"),
            ("cloud_configuration", "cloud.nl"),
            ("satellite_configuration_template", "satellite_lvd.nl"),
            ("goeslib_table", "for044.dat"),
        ):
            source = self.test_root / filename
            if role == "grid_configuration_template":
                content = (
                    "GRID_ROOT=${KL05DABA}\n"
                    "OBS_ROOT=${KL05DAIO}\n"
                    "NX=235\nMODEL=KLAPS\n"
                )
            elif role == "background_configuration":
                content = (
                    "BGPATHS = '/legacy/background/one', '', '/legacy/background/three'\n"
                    "CMODEL = WRF\nBGMODELS = RAP,GFS\n"
                    "OTHER_SETTING = unchanged\n"
                )
            else:
                content = f"fixture:{role}\n"
            source.write_bytes(content.encode())
            assets.append((
                {"role": role, "status": "PASS", "sha256": sha256(source)},
                source,
            ))
        inputs: list[tuple[dict[str, object], Path]] = []
        for role, filename in (
            ("fua", "source.fua"), ("fsf", "source.fsf"),
            ("lw3", "source.lw3"), ("vrz", "source.vrz"),
            ("vrt", "source.vrt"),
        ):
            source = self.test_root / filename
            source.write_bytes(f"fixture:{role}\n".encode())
            inputs.append((
                {"role": role, "status": "PASS", "sha256": sha256(source)},
                source,
            ))
        return assets, inputs

    def _temperature_observation_declarations(
        self,
        row: dict[str, str],
        present_roles: set[str],
        *,
        unexpected_absent_file: bool = False,
    ) -> tuple[list[dict[str, object]], dict[str, Path]]:
        declarations: list[dict[str, object]] = []
        paths: dict[str, Path] = {}
        for role in ("snd", "pin", "adb"):
            relative = Path("ANAL/NE57/DAOU/00/lapsprd") / role / (
                f"{row['laps_stamp']}.{role}"
            )
            path = self.workspace / relative
            paths[role] = path
            if role in present_roles or unexpected_absent_file:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"temperature observation:{role}\n".encode())
            else:
                path.unlink(missing_ok=True)
            declarations.append({
                "role": role,
                "path": relative.as_posix(),
                "sha256": sha256(path) if role in present_roles else None,
            })
        return declarations, paths

    def _assert_observation_rejected(
        self, row: dict[str, str], declarations: list[dict[str, object]]
    ) -> None:
        try:
            _, _, findings = REPLAY.audit_temperature_observations(
                self.workspace, row, declarations
            )
        except REPLAY.ReplayError:
            return
        self.assertTrue(findings, declarations)

    def _write_lso(self, row: dict[str, str], payload: bytes = b"lso bytes\n") -> Path:
        path = (
            self.workspace
            / "ANAL/NE57/DAOU/00/lapsprd/lso"
            / f"{row['laps_stamp']}.lso"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def _write_previous_lso(
        self, row: dict[str, str], payload: bytes = b"previous lso bytes\n"
    ) -> Path:
        instant = datetime.fromisoformat(
            row["valid_time_utc"].replace("Z", "+00:00")
        ) - timedelta(hours=1)
        path = (
            self.workspace
            / "ANAL/NE57/DAOU/00/lapsprd/lso"
            / f"{instant.strftime('%y%j%H%M')}.lso"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def _lso_declaration(self, path: Path, expected_hash: str | None = None) -> dict[str, object]:
        return {
            "path": path.relative_to(self.workspace).as_posix(),
            "sha256": sha256(path) if expected_hash is None else expected_hash,
        }

    def _write_lvd(self, row: dict[str, str], payload: bytes = b"lvd bytes\n") -> Path:
        path = (
            self.workspace
            / "ANAL/NE57/DAOU/00/lapsprd/lvd/kogk2a"
            / f"{row['laps_stamp']}.lvd"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def _lvd_declaration(self, path: Path, expected_hash: str | None = None) -> dict[str, object]:
        return {
            "path": path.relative_to(self.workspace).as_posix(),
            "sha256": sha256(path) if expected_hash is None else expected_hash,
        }

    def _assert_lvd_rejected(self, row: dict[str, str], declaration: object) -> None:
        try:
            _, _, findings = REPLAY.audit_satellite_observation(
                self.workspace, row, declaration
            )
        except REPLAY.ReplayError:
            return
        self.assertTrue(findings, declaration)

    def _assert_lso_rejected(
        self, row: dict[str, str], declaration: object, *, previous: bool = False
    ) -> None:
        try:
            _, _, findings = REPLAY.audit_surface_observation(
                self.workspace, row, declaration, previous=previous
            )
        except REPLAY.ReplayError:
            return
        self.assertTrue(findings, declaration)

    def test_audit_surface_observation_accepts_only_exact_present_lso(self) -> None:
        row = self._runtime_row()
        path = self._write_lso(row)
        before = sha256(path)
        receipt, source, findings = REPLAY.audit_surface_observation(
            self.workspace, row, self._lso_declaration(path)
        )
        self.assertFalse(findings)
        self.assertEqual(receipt["role"], "lso")
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["scope"], "INPUT_BYTES_ONLY")
        self.assertEqual(source, path)
        self.assertEqual(sha256(path), before)

    def test_audit_surface_observation_rejects_missing_or_alias_inputs(self) -> None:
        row = self._runtime_row()
        self._assert_lso_rejected(row, None)
        self._assert_lso_rejected(row, {})

        path = self._write_lso(row)
        self._assert_lso_rejected(
            row,
            {"path": path.relative_to(self.workspace).as_posix(), "sha256": None},
        )
        self._assert_lso_rejected(row, self._lso_declaration(path, "0" * 64))
        path.unlink()
        self._assert_lso_rejected(row, self._lso_declaration(path, "1" * 64))

        wrong_hour = self.workspace / (
            "ANAL/NE57/DAOU/00/lapsprd/lso/262281300.lso"
        )
        wrong_hour.parent.mkdir(parents=True, exist_ok=True)
        wrong_hour.write_bytes(b"wrong hour\n")
        self._assert_lso_rejected(row, self._lso_declaration(wrong_hour))

        wrong_root = self.workspace / (
            "ANAL/NE57/DAOU/00/lapsprd/snd/262281200.lso"
        )
        wrong_root.parent.mkdir(parents=True, exist_ok=True)
        wrong_root.write_bytes(b"wrong root\n")
        self._assert_lso_rejected(row, self._lso_declaration(wrong_root))

        alias = self.workspace / "ANAL/NE57/DAOU/00/lapsprd/lso/262281200.LSO"
        alias.symlink_to(wrong_root)
        self._assert_lso_rejected(row, self._lso_declaration(alias))

        target = self.test_root / "lso-directory-target"
        target.mkdir()
        parent = self.workspace / "ANAL/NE57/DAOU/00/lapsprd/lso"
        shutil.rmtree(parent)
        parent.symlink_to(target, target_is_directory=True)
        symlinked = parent / "262281200.lso"
        symlinked.write_bytes(b"symlink parent\n")
        self._assert_lso_rejected(row, self._lso_declaration(symlinked))

    def test_audit_surface_observation_previous_binds_prior_hour_and_absence(self) -> None:
        row = {
            "case_id": "20260816T000000Z",
            "valid_time_utc": "2026-08-16T00:00:00Z",
            "laps_stamp": "262280000",
        }
        previous = self._write_previous_lso(row)
        receipt, source, findings = REPLAY.audit_surface_observation(
            self.workspace, row, self._lso_declaration(previous), previous=True
        )
        self.assertFalse(findings)
        self.assertEqual(receipt["role"], "previous_lso")
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(source, previous)
        self.assertEqual(previous.name, "262272300.lso")

        shutil.rmtree(previous.parent)
        previous.parent.mkdir(parents=True, exist_ok=True)
        absent = {
            "path": previous.relative_to(self.workspace).as_posix(),
            "sha256": None,
        }
        receipt, source, findings = REPLAY.audit_surface_observation(
            self.workspace, row, absent, previous=True
        )
        self.assertFalse(findings)
        self.assertEqual(receipt["role"], "previous_lso")
        self.assertEqual(receipt["status"], "EXPECTED_ABSENT")
        self.assertIsNone(source)

    def test_audit_surface_observation_previous_rejects_nonexact_declarations(self) -> None:
        row = {
            "case_id": "20260816T000000Z",
            "valid_time_utc": "2026-08-16T00:00:00Z",
            "laps_stamp": "262280000",
        }
        previous = self._write_previous_lso(row)
        missing_hash = self._lso_declaration(previous)
        del missing_hash["sha256"]
        self._assert_lso_rejected(row, missing_hash, previous=True)

        unexpected_absent = {
            "path": previous.relative_to(self.workspace).as_posix(),
            "sha256": None,
        }
        self._assert_lso_rejected(row, unexpected_absent, previous=True)

        wrong_hour = previous.with_name("262272200.lso")
        wrong_hour.write_bytes(b"wrong previous hour\n")
        self._assert_lso_rejected(row, self._lso_declaration(wrong_hour), previous=True)

        wrong_root = self.workspace / (
            "ANAL/NE57/DAOU/00/lapsprd/snd/262272300.lso"
        )
        wrong_root.parent.mkdir(parents=True, exist_ok=True)
        wrong_root.write_bytes(b"wrong previous root\n")
        self._assert_lso_rejected(row, self._lso_declaration(wrong_root), previous=True)

        alias = previous.with_name("262272300.LSO")
        alias.symlink_to(previous)
        self._assert_lso_rejected(row, self._lso_declaration(alias), previous=True)

    def test_materialize_case_runtime_copies_current_and_previous_lso(self) -> None:
        row = {
            "case_id": "20260816T000000Z",
            "valid_time_utc": "2026-08-16T00:00:00Z",
            "laps_stamp": "262280000",
        }
        assets, inputs = self._runtime_sources()
        current = self._write_lso(row, b"current lso\n")
        previous = self._write_previous_lso(row)
        current_receipt, current_source, current_findings = (
            REPLAY.audit_surface_observation(
                self.workspace, row, self._lso_declaration(current)
            )
        )
        previous_receipt, previous_source, previous_findings = (
            REPLAY.audit_surface_observation(
                self.workspace,
                row,
                self._lso_declaration(previous),
                previous=True,
            )
        )
        self.assertFalse(current_findings)
        self.assertFalse(previous_findings)
        self.assertEqual(current_receipt["status"], "PASS")
        self.assertEqual(previous_receipt["status"], "PASS")
        source_hashes = {source: sha256(source) for source in (current, previous)}
        output = self.test_root / "current_previous_lso_runtime_generation"
        result = REPLAY.materialize_case_runtime(
            output,
            row,
            assets,
            input_sources=inputs
            + [(current_receipt, current_source), (previous_receipt, previous_source)],
        )
        self.assertEqual(result["status"], "PREPARED", result)
        runtime_lso = output / "cases/20260816T000000Z/runtime/lapsprd/lso"
        for source in (current, previous):
            destination = runtime_lso / source.name
            self.assertTrue(destination.is_file(), source.name)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertEqual(destination.stat().st_mode & 0o222, 0)
        for source, source_hash in source_hashes.items():
            self.assertEqual(sha256(source), source_hash)

    def test_audit_satellite_observation_accepts_exact_lvd_bytes(self) -> None:
        row = self._runtime_row()
        source = self._write_lvd(row)
        source_hash = sha256(source)
        receipt, audited_source, findings = REPLAY.audit_satellite_observation(
            self.workspace, row, self._lvd_declaration(source)
        )
        self.assertFalse(findings)
        self.assertEqual(receipt["role"], "lvd")
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["scope"], "INPUT_BYTES_ONLY")
        self.assertEqual(audited_source, source)
        self.assertEqual(sha256(source), source_hash)

    def test_audit_satellite_observation_rejects_missing_and_alias_paths(self) -> None:
        row = self._runtime_row()
        self._assert_lvd_rejected(row, None)

        source = self._write_lvd(row)
        self._assert_lvd_rejected(row, self._lvd_declaration(source, "0" * 64))

        missing = self._lvd_declaration(source)
        source.unlink()
        self._assert_lvd_rejected(row, missing)

        wrong_hour = source.with_name("262281300.lvd")
        wrong_hour.write_bytes(b"wrong hour\n")
        self._assert_lvd_rejected(row, self._lvd_declaration(wrong_hour))

        wrong_root = self.workspace / (
            "ANAL/NE57/DAOU/00/lapsprd/lvd/other/262281200.lvd"
        )
        wrong_root.parent.mkdir(parents=True, exist_ok=True)
        wrong_root.write_bytes(b"wrong root\n")
        self._assert_lvd_rejected(row, self._lvd_declaration(wrong_root))

        alias = self.workspace / (
            "ANAL/NE57/DAOU/00/lapsprd/lvd/kogk2a/262281200.LVD"
        )
        alias.symlink_to(wrong_root)
        self._assert_lvd_rejected(row, self._lvd_declaration(alias))

    def test_materialize_case_runtime_copies_lvd_and_creates_contained_outputs(self) -> None:
        row = self._runtime_row()
        assets, inputs = self._runtime_sources()
        source = self._write_lvd(row)
        receipt, audited_source, findings = REPLAY.audit_satellite_observation(
            self.workspace, row, self._lvd_declaration(source)
        )
        self.assertFalse(findings)
        self.assertEqual(receipt["status"], "PASS")
        source_hash = sha256(source)
        output = self.test_root / "lvd_runtime_generation"
        result = REPLAY.materialize_case_runtime(
            output, row, assets, input_sources=inputs + [(receipt, audited_source)]
        )
        self.assertEqual(result["status"], "PREPARED", result)
        runtime = output / "cases/20260816T120000Z/runtime"
        destination = runtime / "lapsprd/lvd/kogk2a" / source.name
        self.assertTrue(destination.is_file())
        self.assertEqual(destination.read_bytes(), source.read_bytes())
        self.assertEqual(destination.stat().st_mode & 0o222, 0)
        self.assertEqual(sha256(source), source_hash)

        expected_output_dirs = {
            "lapsprd/lc3",
            "lapsprd/lcb",
            "lapsprd/lcv",
            "lapsprd/lps",
            "lapsprd/lsx",
            "lapsprd/tmp",
            "lapsprd/lt1",
            "lapsprd/tmg",
            "lapsprd/lpbl",
            "lapsprd/pbl",
            "log",
            "log/qc",
        }
        self.assertEqual(set(result["output_directories"]), expected_output_dirs)
        for relative in expected_output_dirs:
            directory = runtime / relative
            self.assertTrue(directory.is_dir(), relative)
            self.assertTrue(
                directory.resolve().is_relative_to(runtime.resolve()), relative
            )
            self.assertEqual(directory.stat().st_mode & 0o077, 0, relative)
            self.assertNotEqual(directory.stat().st_mode & 0o200, 0, relative)
            children = list(directory.iterdir())
            self.assertTrue(all(child.is_dir() for child in children), relative)
            if relative == "log":
                self.assertEqual({child.name for child in children}, {"qc"})
            else:
                self.assertEqual(children, [])
            probe = directory / ".write-probe"
            probe.write_bytes(b"ok\n")
            probe.unlink()

    def test_materialize_case_runtime_copies_cloud_bundle(self) -> None:
        row = self._runtime_row()
        assets, inputs = self._runtime_sources()
        output = self.test_root / "cloud_runtime_generation"
        result = REPLAY.materialize_case_runtime(
            output, row, assets, input_sources=inputs
        )
        self.assertEqual(result["status"], "PREPARED", result)
        runtime = output / "cases/20260816T120000Z/runtime"
        expected = {
            "lc3_cdl_template": "cdl/lc3.cdl",
            "lcb_cdl_template": "cdl/lcb.cdl",
            "lcv_cdl_template": "cdl/lcv.cdl",
            "lps_cdl_template": "cdl/lps.cdl",
            "cloud_configuration": "static/cloud.nl",
            "goeslib_table": "static/goeslib/for044.dat",
        }
        for role, relative in expected.items():
            source = next(path for receipt, path in assets if receipt["role"] == role)
            destination = runtime / relative
            self.assertEqual(destination.read_bytes(), source.read_bytes(), role)
            self.assertEqual(destination.stat().st_mode & 0o222, 0, role)
        for relative in ("lapsprd/lc3", "lapsprd/lcb", "lapsprd/lcv", "lapsprd/lps"):
            self.assertTrue((runtime / relative).is_dir(), relative)

    def test_materialize_case_runtime_copies_optional_lso_immutably(self) -> None:
        row = self._runtime_row()
        assets, inputs = self._runtime_sources()
        source = self._write_lso(row)
        receipt, lso_source, findings = REPLAY.audit_surface_observation(
            self.workspace, row, self._lso_declaration(source)
        )
        self.assertFalse(findings)
        self.assertEqual(receipt["status"], "PASS")
        source_hash = sha256(source)
        output = self.test_root / "lso_runtime_generation"
        result = REPLAY.materialize_case_runtime(
            output, row, assets, input_sources=inputs + [(receipt, lso_source)]
        )
        self.assertEqual(result["status"], "PREPARED", result)
        destination = (
            output
            / "cases/20260816T120000Z/runtime/lapsprd/lso"
            / source.name
        )
        self.assertTrue(destination.is_file())
        self.assertEqual(destination.read_bytes(), source.read_bytes())
        self.assertEqual(destination.stat().st_mode & 0o222, 0)
        self.assertEqual(sha256(source), source_hash)

    def test_audit_temperature_observations_present_and_expected_absent(self) -> None:
        row = self._runtime_row()
        declarations, paths = self._temperature_observation_declarations(
            row, {"snd", "pin", "adb"}
        )
        before = {role: sha256(path) for role, path in paths.items()}
        receipts, sources, findings = REPLAY.audit_temperature_observations(
            self.workspace, row, declarations
        )
        self.assertFalse(findings)
        self.assertEqual({item["role"] for item in receipts}, {"snd", "pin", "adb"})
        self.assertTrue(all(item["status"] == "PASS" for item in receipts))
        self.assertEqual(len(sources), 3)
        for role, path in paths.items():
            self.assertEqual(sha256(path), before[role])

        absent_declarations, absent_paths = self._temperature_observation_declarations(
            row, set()
        )
        receipts, sources, findings = REPLAY.audit_temperature_observations(
            self.workspace, row, absent_declarations
        )
        self.assertFalse(findings)
        self.assertEqual(sources, [])
        self.assertTrue(all(item["status"] == "EXPECTED_ABSENT" for item in receipts))
        self.assertTrue(all(not path.exists() for path in absent_paths.values()))

    def test_audit_temperature_observations_rejects_bad_declarations(self) -> None:
        row = self._runtime_row()
        declarations, paths = self._temperature_observation_declarations(
            row, {"snd", "pin", "adb"}
        )

        bad_hash = [dict(item) for item in declarations]
        bad_hash[0]["sha256"] = "0" * 64
        self._assert_observation_rejected(row, bad_hash)

        missing_present = [dict(item) for item in declarations]
        paths["pin"].unlink()
        self._assert_observation_rejected(row, missing_present)

        unexpected = [dict(item) for item in declarations]
        unexpected[1]["sha256"] = None
        paths["pin"].write_bytes(b"unexpected pin\n")
        self._assert_observation_rejected(row, unexpected)

        unknown = [dict(item) for item in declarations]
        unknown[0]["role"] = "qc"
        self._assert_observation_rejected(row, unknown)

        duplicate = declarations + [dict(declarations[0])]
        self._assert_observation_rejected(row, duplicate)

        wrong_timestamp = [dict(item) for item in declarations]
        wrong_timestamp[0]["path"] = "ANAL/NE57/DAOU/00/lapsprd/snd/262281201.snd"
        self._assert_observation_rejected(row, wrong_timestamp)

        wrong_root = [dict(item) for item in declarations]
        wrong_root[0]["path"] = "ANAL/NE57/DAOU/00/lapsprd/fua/262281200.snd"
        self._assert_observation_rejected(row, wrong_root)

        _, _, findings = REPLAY.audit_temperature_observations(
            self.workspace, row, []
        )
        self.assertIn("TEMPERATURE_OBSERVATIONS_NOT_DECLARED", findings)

    def test_audit_temperature_observations_rejects_absent_path_aliases(self) -> None:
        row = self._runtime_row()
        declarations, paths = self._temperature_observation_declarations(row, set())

        missing_hash = [dict(item) for item in declarations]
        del missing_hash[0]["sha256"]
        self._assert_observation_rejected(row, missing_hash)

        leaf = paths["snd"]
        leaf.parent.mkdir(parents=True, exist_ok=True)
        leaf.symlink_to(self.test_root / "missing-observation-target")
        self._assert_observation_rejected(row, declarations)
        leaf.unlink()

        parent = paths["pin"].parent
        parent.mkdir(parents=True, exist_ok=True)
        parent.rmdir()
        outside = self.test_root / "observation-directory-target"
        outside.mkdir()
        parent.symlink_to(outside, target_is_directory=True)
        self._assert_observation_rejected(row, declarations)

    def test_materialize_case_runtime_copies_optional_temperature_observations(self) -> None:
        row = self._runtime_row()
        assets, inputs = self._runtime_sources()
        declarations, paths = self._temperature_observation_declarations(
            row, {"snd", "pin", "adb"}
        )
        observation_receipts, observations, observation_findings = (
            REPLAY.audit_temperature_observations(self.workspace, row, declarations)
        )
        self.assertFalse(observation_findings)
        self.assertTrue(all(item["status"] == "PASS" for item in observation_receipts))
        source_hashes = {role: sha256(path) for role, path in paths.items()}
        result = REPLAY.materialize_case_runtime(
            self.test_root / "temperature_observation_runtime_generation",
            row,
            assets,
            input_sources=inputs + observations,
        )
        self.assertEqual(result["status"], "PREPARED", result)
        runtime = self.test_root / "temperature_observation_runtime_generation/cases/20260816T120000Z/runtime"
        for role, source in paths.items():
            destination = runtime / "lapsprd" / role / source.name
            self.assertTrue(destination.is_file(), role)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertEqual(destination.stat().st_mode & 0o222, 0)
            self.assertEqual(sha256(source), source_hashes[role])

    def test_materialize_case_runtime_accepts_only_one_optional_observation(self) -> None:
        row = self._runtime_row()
        assets, inputs = self._runtime_sources()
        declarations, paths = self._temperature_observation_declarations(
            row, {"adb"}
        )
        observation_receipts, observations, observation_findings = (
            REPLAY.audit_temperature_observations(self.workspace, row, declarations)
        )
        self.assertFalse(observation_findings)
        self.assertEqual(
            [item["role"] for item in observation_receipts if item["status"] == "PASS"],
            ["adb"],
        )
        output = self.test_root / "one_temperature_observation_runtime_generation"
        result = REPLAY.materialize_case_runtime(
            output, row, assets, input_sources=inputs + observations
        )
        self.assertEqual(result["status"], "PREPARED", result)
        destination = (
            output / "cases/20260816T120000Z/runtime/lapsprd/adb/262281200.adb"
        )
        self.assertTrue(destination.is_file())
        self.assertEqual(destination.read_bytes(), paths["adb"].read_bytes())

    def test_materialize_case_runtime_is_read_only_and_hash_pinned(self) -> None:
        row = self._runtime_row()
        assets, inputs = self._runtime_sources()
        cdl_source = next(path for receipt, path in assets if receipt["role"] == "lt1_cdl_template")
        receipt = next(receipt for receipt, path in assets if receipt["role"] == "lt1_cdl_template")
        source_hash = sha256(cdl_source)
        receipts_before = [dict(item) for item, _ in assets + inputs]
        output = self.test_root / "runtime_generation"
        result = REPLAY.materialize_case_runtime(
            output, row, assets, input_sources=inputs
        )
        self.assertEqual(result["status"], "PREPARED", result)
        self.assertFalse(result["execution_ready"])
        self.assertIn("CURRENT_TIME_LSX_NOT_PRODUCED", result["execution_blockers"])
        self.assertIn(
            "RUNTIME_MOUNT_AND_REFERENCED_INPUTS_REQUIRED",
            result["execution_blockers"],
        )
        self.assertEqual(
            result["configuration_status"],
            "PATHS_REBOUND_REFERENCED_INPUTS_INCOMPLETE",
        )
        systime = output / "cases/20260816T120000Z/runtime/time/systime.dat"
        self.assertEqual(systime.read_bytes(), REPLAY.encode_systime(row))
        expected = {
            "lc3_cdl_template": "cdl/lc3.cdl",
            "lcb_cdl_template": "cdl/lcb.cdl",
            "lcv_cdl_template": "cdl/lcv.cdl",
            "lps_cdl_template": "cdl/lps.cdl",
            "lt1_cdl_template": "cdl/lt1.cdl",
            "lsx_cdl_template": "cdl/lsx.cdl",
            "pbl_cdl_template": "cdl/pbl.cdl",
            "static_grid": "static/static.nest7grid",
            "pressure_configuration": "static/pressures.nl",
            "surface_configuration": "static/surface_analysis.nl",
            "surface_drag_table": "static/drag_coef.dat",
            "cloud_configuration": "static/cloud.nl",
            "satellite_configuration_template": "static/satellite_lvd.nl",
            "goeslib_table": "static/goeslib/for044.dat",
            "temperature_configuration": "static/temp.nl",
            "fua": "lapsprd/fua/wrf/source.fua",
            "fsf": "lapsprd/fsf/wrf/source.fsf",
            "lw3": "lapsprd/lw3/source.lw3",
            "vrz": "lapsprd/vrz/source.vrz",
            "vrt": "lapsprd/vrt/source.vrt",
        }
        runtime = output / "cases/20260816T120000Z/runtime"
        copied = [systime]
        for copy_receipt, copy_source in assets + inputs:
            role = str(copy_receipt["role"])
            if role in {
                "grid_configuration_template",
                "background_configuration",
            }:
                destinations = [
                    f"templates/static/{copy_source.name}",
                    f"static/{copy_source.name}",
                ]
            else:
                destinations = [expected[role]]
            for relative in destinations:
                destination = runtime / relative
                self.assertTrue(destination.is_file(), role)
                if relative.startswith("templates/") or role not in {
                    "grid_configuration_template", "background_configuration",
                }:
                    self.assertEqual(destination.read_bytes(), copy_source.read_bytes())
                copied.append(destination)
        grid_source = next(path for receipt, path in assets if receipt["role"] == "grid_configuration_template")
        grid_derived = (runtime / "static/nest7grid.parms").read_bytes()
        self.assertEqual(
            REPLAY.rebind_runtime_configuration(
                "grid_configuration_template", grid_source.read_bytes()
            ),
            grid_derived,
        )
        background_source = next(path for receipt, path in assets if receipt["role"] == "background_configuration")
        self.assertEqual(
            REPLAY.rebind_runtime_configuration(
                "background_configuration", background_source.read_bytes()
            ),
            (runtime / "static/background.nl").read_bytes(),
        )
        for path in copied:
            self.assertEqual(path.stat(follow_symlinks=False).st_nlink, 1)
            self.assertEqual(path.stat().st_mode & 0o222, 0)
        self.assertEqual(sha256(cdl_source), source_hash)
        self.assertEqual(receipt["sha256"], source_hash)
        self.assertEqual(
            [dict(item) for item, _ in assets + inputs], receipts_before
        )
        with self.assertRaises((REPLAY.ReplayError, FileExistsError)):
            REPLAY.materialize_case_runtime(output, row, assets, input_sources=inputs)

        wrong_hash_output = self.test_root / "wrong_hash_runtime_generation"
        wrong_receipt = dict(receipt, sha256="0" * 64)
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.materialize_case_runtime(
                wrong_hash_output, row, [
                    (wrong_receipt, cdl_source),
                    *[item for item in assets if item[0]["role"] != "lt1_cdl_template"],
                ], input_sources=inputs
            )

    def test_rebind_runtime_configuration_supported_paths_and_preservation(self) -> None:
        grid = (
            b"GRID_ROOT=${KL05DABA}\n"
            b"OBS_ROOT=${KL05DAIO}\n"
            b"NX=235\nMODEL=KLAPS\n"
        )
        self.assertEqual(
            REPLAY.rebind_runtime_configuration("grid_configuration_template", grid),
            (
                b"GRID_ROOT=/cloud-bal-case/static-assets\n"
                b"OBS_ROOT=/cloud-bal-case/observations/raw\n"
                b"NX=235\nMODEL=KLAPS\n"
            ),
        )
        background = (
            b"BGPATHS = '/legacy/background/one', '', '/legacy/background/three'\n"
            b"CMODEL = WRF\nBGMODELS = RAP,GFS\nOTHER_SETTING = unchanged\n"
        )
        rebound = REPLAY.rebind_runtime_configuration(
            "background_configuration", background
        )
        self.assertIn(
            b"BGPATHS = '/cloud-bal-case/background-source/01', '', '/cloud-bal-case/background-source/03'\n",
            rebound,
        )
        self.assertIn(b"CMODEL = WRF\nBGMODELS = RAP,GFS\n", rebound)
        self.assertIn(b"OTHER_SETTING = unchanged\n", rebound)

    def test_rebind_runtime_configuration_rejects_unsupported_or_ambiguous_paths(self) -> None:
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.rebind_runtime_configuration("temperature_configuration", b"X=1\n")
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.rebind_runtime_configuration(
                "grid_configuration_template", b"GRID_ROOT=${UNSUPPORTED}\n"
            )
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.rebind_runtime_configuration(
                "background_configuration", b"CMODEL = WRF\n"
            )
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.rebind_runtime_configuration(
                "background_configuration",
                b"BGPATHS = '/one', '/two'\nBGPATHS = '/three'\n",
            )

    def _write_lrs(self, valid_time: str, payload: bytes = b"lrs bytes\n") -> Path:
        instant = datetime.fromisoformat(valid_time.replace("Z", "+00:00"))
        stamp = instant.strftime("%y%j%H%M")
        path = (
            self.workspace / "ANAL/NE57/DAOU/00/lapsprd/lrs" / f"{stamp}.lrs"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def _lrs_declaration(self, path: Path, expected_hash: str | None = None) -> dict[str, object]:
        relative = path.relative_to(self.workspace).as_posix()
        return {
            "path": relative,
            "sha256": sha256(path) if expected_hash is None else expected_hash,
        }

    def _assert_lrs_rejected(
        self, row: dict[str, str], declarations: object, expected: str | None = None
    ) -> None:
        try:
            selection, _, findings = REPLAY.audit_lrs_selection(
                self.workspace, row, declarations
            )
        except REPLAY.ReplayError:
            return
        if expected is not None and selection.get("status") == expected:
            self.fail(f"LRS selection unexpectedly accepted: {selection}")
        self.assertTrue(findings, selection)

    def test_audit_lrs_selection_absent_and_undeclared(self) -> None:
        row = self._runtime_row()
        (self.workspace / "ANAL/NE57/DAOU/00/lapsprd/lrs").mkdir(
            parents=True, exist_ok=True
        )
        selection, sources, findings = REPLAY.audit_lrs_selection(
            self.workspace, row, []
        )
        self.assertEqual(selection["status"], "EXPECTED_ABSENT", selection)
        self.assertEqual(sources, [])
        self.assertFalse(findings)

        selection, sources, findings = REPLAY.audit_lrs_selection(
            self.workspace, row, None
        )
        self.assertEqual(sources, [])
        self.assertIn("LRS_INPUTS_NOT_DECLARED", findings)

    def test_audit_lrs_selection_window_and_tie_contract(self) -> None:
        row = self._runtime_row()
        outside = self._write_lrs("2026-08-16T13:01:00Z")
        selection, sources, findings = REPLAY.audit_lrs_selection(
            self.workspace, row, [self._lrs_declaration(outside)]
        )
        self.assertEqual(selection["status"], "OUTSIDE_WINDOW", selection)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0][0]["role"], "lrs")
        self.assertEqual(sources[0][0]["status"], "PASS")
        self.assertFalse(findings)

        shutil.rmtree(outside.parent)
        selected = self._write_lrs("2026-08-16T11:00:00Z")
        selection, sources, findings = REPLAY.audit_lrs_selection(
            self.workspace, row, [self._lrs_declaration(selected)]
        )
        self.assertEqual(selection["status"], "SELECTED", selection)
        self.assertFalse(findings)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0][0]["role"], "lrs")
        self.assertEqual(sources[0][0]["status"], "PASS")

        tie_later = self._write_lrs("2026-08-16T13:00:00Z")
        declarations = [
            self._lrs_declaration(selected), self._lrs_declaration(tie_later)
        ]
        selection, sources, findings = REPLAY.audit_lrs_selection(
            self.workspace, row, declarations
        )
        self.assertEqual(selection["status"], "SELECTED", selection)
        self.assertEqual(
            selection["selected_path"], selected.relative_to(self.workspace).as_posix()
        )
        self.assertEqual(len(sources), 2)
        self.assertFalse(findings)

    def test_audit_lrs_selection_uses_legacy_year_and_time_bounds(self) -> None:
        row = self._runtime_row()
        directory = self.workspace / "ANAL/NE57/DAOU/00/lapsprd/lrs"

        historical = directory / "650011200.lrs"
        directory.mkdir(parents=True, exist_ok=True)
        historical.write_bytes(b"historical lrs\n")
        selection, sources, findings = REPLAY.audit_lrs_selection(
            self.workspace, row, [self._lrs_declaration(historical)]
        )
        self.assertEqual(selection["status"], "OUTSIDE_WINDOW", selection)
        self.assertEqual(len(sources), 1)
        self.assertFalse(findings)

        shutil.rmtree(directory)
        invalid_julian = directory / "233661200.lrs"
        directory.mkdir(parents=True, exist_ok=True)
        invalid_julian.write_bytes(b"invalid julian day\n")
        self._assert_lrs_rejected(
            row, [self._lrs_declaration(invalid_julian)]
        )

        shutil.rmtree(directory)
        overflow = directory / "490010000.lrs"
        directory.mkdir(parents=True, exist_ok=True)
        overflow.write_bytes(b"native time overflow\n")
        self._assert_lrs_rejected(row, [self._lrs_declaration(overflow)])

    def test_audit_lrs_selection_rejects_bad_inventory_and_aliases(self) -> None:
        row = self._runtime_row()
        actual = self._write_lrs("2026-08-16T12:00:00Z")

        wrong_hash = [self._lrs_declaration(actual, "0" * 64)]
        self._assert_lrs_rejected(row, wrong_hash)

        duplicate = [self._lrs_declaration(actual), self._lrs_declaration(actual)]
        self._assert_lrs_rejected(row, duplicate)

        malformed = self.workspace / "ANAL/NE57/DAOU/00/lapsprd/lrs/bad-name.lrs"
        malformed.write_bytes(b"bad\n")
        self._assert_lrs_rejected(row, [self._lrs_declaration(malformed)])

        undeclared = self.workspace / "ANAL/NE57/DAOU/00/lapsprd/lrs/262281201.lrs"
        undeclared.write_bytes(b"undeclared\n")
        self._assert_lrs_rejected(row, [self._lrs_declaration(actual)])

        symlink_dir = self.test_root / "lrs-target"
        symlink_dir.mkdir()
        symlink_file = symlink_dir / actual.name
        symlink_file.write_bytes(actual.read_bytes())
        actual.parent.rename(self.test_root / "lrs-real")
        (self.workspace / "ANAL/NE57/DAOU/00/lapsprd/lrs").symlink_to(
            symlink_dir, target_is_directory=True
        )
        symlink_path = self.workspace / "ANAL/NE57/DAOU/00/lapsprd/lrs" / actual.name
        self._assert_lrs_rejected(row, [self._lrs_declaration(symlink_path)])

    def test_materialize_case_runtime_copies_selected_optional_lrs(self) -> None:
        row = self._runtime_row()
        assets, inputs = self._runtime_sources()
        lrs_path = self._write_lrs("2026-08-16T11:00:00Z")
        lrs_outside = self._write_lrs("2026-08-16T13:01:00Z", b"outside lrs\n")
        selection, lrs_sources, findings = REPLAY.audit_lrs_selection(
            self.workspace,
            row,
            [self._lrs_declaration(lrs_path), self._lrs_declaration(lrs_outside)],
        )
        self.assertEqual(selection["status"], "SELECTED", selection)
        self.assertFalse(findings)
        self.assertEqual(len(lrs_sources), 2)
        source_hash = sha256(lrs_path)
        result = REPLAY.materialize_case_runtime(
            self.test_root / "lrs_runtime_generation",
            row,
            assets,
            input_sources=inputs + lrs_sources,
        )
        self.assertEqual(result["status"], "PREPARED", result)
        runtime_lrs = self.test_root / "lrs_runtime_generation/cases/20260816T120000Z/runtime/lapsprd/lrs"
        for source in (lrs_path, lrs_outside):
            destination = runtime_lrs / source.name
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertEqual(destination.stat().st_mode & 0o222, 0)
        self.assertEqual(sha256(lrs_path), source_hash)
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.materialize_case_runtime(
                self.test_root / "lrs_duplicate_runtime_generation",
                row,
                assets,
                input_sources=inputs + lrs_sources + [lrs_sources[0]],
            )

    def test_materialize_case_runtime_copies_case_inputs_to_role_paths(self) -> None:
        row = self._runtime_row()
        assets, inputs = self._runtime_sources()
        output = self.test_root / "case_input_runtime_generation"
        result = REPLAY.materialize_case_runtime(
            output, row, assets, input_sources=inputs
        )
        self.assertEqual(result["status"], "PREPARED", result)
        runtime = output / "cases/20260816T120000Z/runtime"
        for receipt, source in inputs:
            role = str(receipt["role"])
            if role in ("fua", "fsf"):
                destination = runtime / "lapsprd" / role / "wrf" / source.name
            else:
                destination = runtime / "lapsprd" / role / source.name
            self.assertTrue(destination.is_file(), role)
            self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_materialize_case_runtime_missing_required_role_is_partial(self) -> None:
        row = self._runtime_row()
        assets, inputs = self._runtime_sources()
        for missing_role in (
            "lc3_cdl_template",
            "lcb_cdl_template",
            "lcv_cdl_template",
            "lps_cdl_template",
            "lsx_cdl_template",
            "pbl_cdl_template",
            "static_grid",
            "surface_configuration",
            "surface_drag_table",
            "cloud_configuration",
            "goeslib_table",
        ):
            with self.subTest(missing_role=missing_role):
                partial_assets = [
                    item for item in assets if item[0]["role"] != missing_role
                ]
                result = REPLAY.materialize_case_runtime(
                    self.test_root / f"missing_{missing_role}_runtime_generation",
                    row,
                    partial_assets,
                    input_sources=inputs,
                )
                self.assertEqual(result["status"], "PARTIAL", result)
                self.assertFalse(result["execution_ready"])
                self.assertTrue(
                    any(missing_role.upper() in str(item) for item in result["findings"]),
                    result["findings"],
                )

    def test_materialize_case_runtime_is_partial_without_lt1_cdl(self) -> None:
        row = self._runtime_row()
        output = self.test_root / "partial_runtime_generation"
        result = REPLAY.materialize_case_runtime(output, row, [])
        self.assertEqual(result["status"], "PARTIAL", result)
        self.assertFalse(result["execution_ready"])
        self.assertIn("CURRENT_TIME_LSX_NOT_PRODUCED", result["execution_blockers"])
        self.assertTrue(
            any("LT1_CDL" in str(item) for item in result["findings"])
        )
        systime = output / "cases/20260816T120000Z/runtime/time/systime.dat"
        self.assertEqual(systime.read_bytes(), REPLAY.encode_systime(row))
        self.assertFalse(
            (output / "cases/20260816T120000Z/runtime/cdl/lt1.cdl").exists()
        )
        self.assertFalse(result.get("execution_ready", False))
        self.assertFalse(result.get("execution_authorized", False))

if __name__ == "__main__":
    unittest.main()
