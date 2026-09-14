#!/usr/bin/env python3
"""Consumer tests for the isolated CP02 CDL metadata stage."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import netCDF4
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT.parent / "ANAL/NE57/DABA/cdl"
GRID_PATH = REPO_ROOT.parent / "ANAL/NE57/DABA/static.nest7grid"
TOOL_PATH = REPO_ROOT / "tools/stage_cp02_metadata.py"
PINNED_NCGEN_PATH = (
    REPO_ROOT.parent
    / "klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/bin/ncgen"
)
PINNED_NCGEN_SHA256 = (
    "b83acc5e06621d9e15c3e92b7c1592ca6fcf5d62593c95d8f87fa76cbcfb549e"
)
MODULE_SPEC = importlib.util.spec_from_file_location("cp02_metadata", TOOL_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
METADATA = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(METADATA)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _ncgen_path() -> Path | None:
    configured = os.environ.get("NCGEN_BIN")
    candidate = Path(configured) if configured else PINNED_NCGEN_PATH
    if not candidate.is_file() or not candidate.stat().st_mode & 0o111:
        return None
    if _sha256(candidate) != PINNED_NCGEN_SHA256:
        raise RuntimeError(
            f"unpinned ncgen rejected: expected {PINNED_NCGEN_SHA256}, found {_sha256(candidate)}"
        )
    return candidate


NCGEN = _ncgen_path()


def _decode_chars(value: np.ndarray) -> str:
    if hasattr(value, "filled"):
        value = value.filled(b"\x00")
    return value.tobytes().decode("ascii").rstrip("\x00 ")


def _compile_cdl(cdl: Path, destination: Path) -> None:
    if NCGEN is None:
        raise unittest.SkipTest("ncgen is required for the NetCDF consumer test")
    subprocess.run(
        [str(NCGEN), "-k", "4", "-o", str(destination), str(cdl)],
        check=True,
        capture_output=True,
        text=True,
    )


class CP02MetadataStagingTest(unittest.TestCase):
    def setUp(self) -> None:
        if not SOURCE_ROOT.is_dir() or not GRID_PATH.is_file():
            self.skipTest("the reviewed KLAPS source CDL/static-grid inputs are unavailable")
        self.temporary = tempfile.TemporaryDirectory(prefix="cp02-metadata-test-")
        self.root = Path(self.temporary.name)
        self.source = self.root / "source-cdl"
        self.source.mkdir()
        for name in METADATA.PRODUCT_VARIABLES:
            shutil.copyfile(SOURCE_ROOT / name, self.source / name)
        self.source_hashes = {
            name: _sha256(self.source / name) for name in METADATA.PRODUCT_VARIABLES
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def stage(self, *, with_grid: bool = True) -> tuple[Path, dict]:
        return self.stage_with_grid_path(with_grid=with_grid, grid_path=GRID_PATH)

    def stage_with_grid_path(
        self, *, with_grid: bool = True, grid_path: Path | None = None
    ) -> tuple[Path, dict]:
        output = self.root / ("staged-with-grid" if with_grid else "staged-no-grid")
        selected_grid = grid_path or GRID_PATH
        receipt = METADATA.stage_templates(
            self.source,
            output,
            expected_source_sha256=self.source_hashes,
            grid_path=selected_grid if with_grid else None,
            expected_grid_sha256=_sha256(selected_grid) if with_grid else None,
        )
        return output, receipt

    def test_ncgen_identity_is_pinned(self) -> None:
        if NCGEN is None:
            self.skipTest(f"pinned ncgen is unavailable: {PINNED_NCGEN_PATH}")
        self.assertEqual(NCGEN, PINNED_NCGEN_PATH)
        self.assertEqual(_sha256(NCGEN), PINNED_NCGEN_SHA256)

    def test_stage_is_hash_bound_and_leaves_source_untouched(self) -> None:
        self.assertEqual(_sha256(GRID_PATH), METADATA.CANONICAL_STATIC_GRID_SHA256)
        source_before = {
            name: (self.source / name).read_bytes() for name in METADATA.PRODUCT_VARIABLES
        }
        output, receipt = self.stage()

        self.assertEqual(receipt["status"], "STAGED")
        self.assertEqual(len(receipt["transformations"]), 8)
        self.assertEqual(receipt["source_sha256_verified"], self.source_hashes)
        self.assertEqual(receipt["grid_sha256"], _sha256(GRID_PATH))
        self.assertEqual(
            {name: (self.source / name).read_bytes() for name in METADATA.PRODUCT_VARIABLES},
            source_before,
        )
        for name, digest in self.source_hashes.items():
            self.assertEqual(receipt["outputs"][name]["source_sha256"], digest)
            self.assertEqual(receipt["outputs"][name]["output_sha256"], _sha256(output / name))
        self.assertEqual(
            json.loads((output / "metadata_stage_receipt.json").read_text()),
            receipt,
        )

    def test_staged_cdls_change_default_reader_masking(self) -> None:
        output, _ = self.stage(with_grid=False)
        samples = {
            "lt1.cdl": {"t3": 273.15},
            "lh3.cdl": {"rh3": 50.0, "rhl": 75.0},
            "lmr.cdl": {"r": -10.0},
            "lmt.cdl": {"lmt": 1000.0, "llr": -5.0},
            "pbl.cdl": {"ptp": 90000.0, "pdm": 500.0},
        }
        for name, variables in samples.items():
            original_product = self.root / ("original-" + name.replace(".cdl", ".nc"))
            staged_product = self.root / ("staged-" + name.replace(".cdl", ".nc"))
            _compile_cdl(self.source / name, original_product)
            _compile_cdl(output / name, staged_product)
            with netCDF4.Dataset(original_product, "r+") as dataset:
                for variable_name, sample in variables.items():
                    dataset.variables[variable_name][0, ...] = np.float32(sample)
            with netCDF4.Dataset(staged_product, "r+") as dataset:
                for variable_name, sample in variables.items():
                    dataset.variables[variable_name][0, ...] = np.float32(sample)

            with netCDF4.Dataset(original_product) as original, netCDF4.Dataset(staged_product) as staged:
                for variable_name, sample in variables.items():
                    old_variable = original.variables[variable_name]
                    new_variable = staged.variables[variable_name]
                    self.assertIn("valid_range", old_variable.ncattrs())
                    self.assertNotIn("valid_range", new_variable.ncattrs())
                    old_raw = old_variable[:]
                    new_values = new_variable[:]
                    self.assertTrue(np.ma.isMaskedArray(old_raw))
                    self.assertGreater(np.ma.count_masked(old_raw), 0)
                    self.assertFalse(np.ma.isMaskedArray(new_values) and np.ma.count_masked(new_values) > 0)
                    self.assertTrue(np.allclose(np.asarray(new_values), sample))

    def test_pbl_navigation_comes_from_exact_static_grid(self) -> None:
        output, receipt = self.stage()
        staged_product = self.root / "pbl.nc"
        _compile_cdl(output / "pbl.cdl", staged_product)
        with netCDF4.Dataset(GRID_PATH) as grid, netCDF4.Dataset(staged_product) as product:
            for name in METADATA.PBL_NAV_NUMERIC:
                self.assertEqual(float(product.variables[name][0]), float(grid.variables[name][0]))
            for name in (*METADATA.PBL_NAV_TEXT, METADATA.PBL_ORIGIN_TEXT):
                self.assertEqual(
                    _decode_chars(product.variables[name][:]),
                    _decode_chars(grid.variables[name][:]),
                )
            for name in ("ptp", "pdm"):
                self.assertNotIn("valid_range", product.variables[name].ncattrs())
        self.assertEqual(receipt["outputs"]["pbl.cdl"]["navigation"]["status"], "populated")

    def test_pbl_navigation_is_not_invented_without_grid_source(self) -> None:
        output, receipt = self.stage(with_grid=False)
        product = self.root / "pbl-no-grid.nc"
        _compile_cdl(output / "pbl.cdl", product)
        with netCDF4.Dataset(product) as dataset:
            self.assertTrue(np.ma.is_masked(dataset.variables["Nx"][0]))
            self.assertTrue(np.ma.is_masked(dataset.variables["La1"][0]))
        self.assertEqual(
            receipt["outputs"]["pbl.cdl"]["navigation"]["status"],
            "not_requested",
        )

    def test_grid_mismatch_and_source_hash_mismatch_fail_closed(self) -> None:
        wrong_grid = self.root / "wrong-grid.nc"
        shutil.copyfile(GRID_PATH, wrong_grid)
        with netCDF4.Dataset(wrong_grid, "r+") as dataset:
            dataset.variables["Nx"][0] = np.int16(234)
        with self.assertRaises(METADATA.MetadataStageError):
            self.stage_templates_with_grid(
                wrong_grid, expected_hash=METADATA.CANONICAL_STATIC_GRID_SHA256
            )
        self.assertFalse((self.root / "rejected-grid").exists())

        same_shape_grid = self.root / "same-shape-grid.nc"
        shutil.copyfile(GRID_PATH, same_shape_grid)
        with netCDF4.Dataset(same_shape_grid, "r+") as dataset:
            dataset.variables["lat"][0, 0, 0, 0] += np.float32(1.0)
        with netCDF4.Dataset(same_shape_grid) as dataset:
            self.assertEqual(
                tuple(dataset.dimensions[name].size for name in ("x", "y")),
                (235, 283),
            )
        with self.assertRaises(METADATA.MetadataStageError):
            self.stage_templates_with_grid(same_shape_grid)
        self.assertFalse((self.root / "rejected-grid").exists())

        changed_source = self.source / "lt1.cdl"
        changed_source.write_bytes(changed_source.read_bytes() + b"\n")
        with self.assertRaises(METADATA.MetadataStageError):
            METADATA.stage_templates(
                self.source,
                self.root / "rejected-source",
                expected_source_sha256=self.source_hashes,
            )
        self.assertFalse((self.root / "rejected-source").exists())

        with self.assertRaises(METADATA.MetadataStageError):
            METADATA.stage_templates(
                self.source,
                self.root / "ANAL" / "metadata-stage",
                expected_source_sha256=self.source_hashes,
            )
        self.assertFalse((self.root / "ANAL" / "metadata-stage").exists())

    def test_source_bytes_are_transformed_after_one_bound_read(self) -> None:
        original = (self.source / "lt1.cdl").read_bytes()
        bound_read = METADATA._read_bound_file

        def read_then_replace(path: Path, label: str):
            result = bound_read(path, label)
            if path.name == "lt1.cdl":
                path.write_bytes(original + b"\nRACE_REPLACEMENT")
            return result

        output = self.root / "staged-bound-read"
        with patch.object(METADATA, "_read_bound_file", side_effect=read_then_replace):
            receipt = METADATA.stage_templates(
                self.source,
                output,
                expected_source_sha256=self.source_hashes,
            )
        expected_output, _ = METADATA._remove_stale_ranges(
            "lt1.cdl", original.decode("ascii")
        )
        self.assertEqual((output / "lt1.cdl").read_bytes(), expected_output.encode("ascii"))
        self.assertNotEqual((self.source / "lt1.cdl").read_bytes(), original)
        self.assertEqual(
            receipt["source_sha256_verified"]["lt1.cdl"], self.source_hashes["lt1.cdl"]
        )

    def test_grid_bytes_are_consumed_after_one_bound_read(self) -> None:
        race_grid = self.root / "race-grid.nc"
        shutil.copyfile(GRID_PATH, race_grid)
        with netCDF4.Dataset(GRID_PATH) as dataset:
            original_la1 = float(dataset.variables["La1"][0])
        bound_read = METADATA._read_bound_file

        def read_then_mutate(path: Path, label: str):
            result = bound_read(path, label)
            if path == race_grid:
                with netCDF4.Dataset(path, "r+") as dataset:
                    dataset.variables["La1"][0] = np.float32(original_la1 + 10.0)
            return result

        with patch.object(METADATA, "_read_bound_file", side_effect=read_then_mutate):
            output, receipt = self.stage_with_grid_path(grid_path=race_grid)
        self.assertNotEqual(_sha256(race_grid), METADATA.CANONICAL_STATIC_GRID_SHA256)
        self.assertEqual(receipt["grid_sha256"], METADATA.CANONICAL_STATIC_GRID_SHA256)
        self.assertIn(f"La1 = {original_la1:.9g};", (output / "pbl.cdl").read_text())

    def test_publication_fails_without_replacing_racing_output(self) -> None:
        output = self.root / "racing-output"
        publish = METADATA._rename_noreplace

        def publish_with_competitor(source: Path, destination: Path) -> None:
            destination.mkdir()
            (destination / "competitor-marker").write_text("retained")
            publish(source, destination)

        with patch.object(
            METADATA, "_rename_noreplace", side_effect=publish_with_competitor
        ):
            with self.assertRaises(METADATA.MetadataStageError):
                METADATA.stage_templates(
                    self.source,
                    output,
                    expected_source_sha256=self.source_hashes,
                )
        self.assertEqual((output / "competitor-marker").read_text(), "retained")
        self.assertFalse((output / "lt1.cdl").exists())

    def test_cli_rejects_fifo_without_blocking(self) -> None:
        fifo_source = self.root / "fifo-source"
        fifo_source.mkdir()
        for name in METADATA.PRODUCT_VARIABLES:
            if name != "lt1.cdl":
                shutil.copyfile(self.source / name, fifo_source / name)
        os.mkfifo(fifo_source / "lt1.cdl")
        output = self.root / "fifo-output"
        command = [
            sys.executable,
            str(TOOL_PATH),
            "--source-dir",
            str(fifo_source),
            "--output-dir",
            str(output),
        ]
        for name, digest in self.source_hashes.items():
            command.extend(("--expected-source-sha256", f"{name}={digest}"))
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=3
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be a regular file", result.stderr)
        self.assertFalse(output.exists())

    def test_cli_rejects_regular_output_parent_with_typed_error(self) -> None:
        regular_parent = self.root / "regular-parent"
        regular_parent.write_bytes(b"retained")
        output = regular_parent / "metadata-stage"
        command = [
            sys.executable,
            str(TOOL_PATH),
            "--source-dir",
            str(self.source),
            "--output-dir",
            str(output),
        ]
        for name, digest in self.source_hashes.items():
            command.extend(("--expected-source-sha256", f"{name}={digest}"))
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=3
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("metadata output parent must be a directory", result.stderr)
        self.assertEqual(regular_parent.read_bytes(), b"retained")
        self.assertFalse(output.exists())

    def stage_templates_with_grid(
        self, grid: Path, *, expected_hash: str | None = None
    ) -> dict:
        return METADATA.stage_templates(
            self.source,
            self.root / "rejected-grid",
            expected_source_sha256=self.source_hashes,
            grid_path=grid,
            expected_grid_sha256=expected_hash or _sha256(grid),
        )


if __name__ == "__main__":
    unittest.main()
