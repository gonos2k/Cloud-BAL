#!/usr/bin/env python3
"""Verify one complete test-only real-geometry balance generation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


EXPECTED_CONFIGURATION = "real-geometry-manufactured-balance-ifx-2026-v1"
EXPECTED_CONTRACT = "real_geometry_manufactured_balance_ifx_2026_v1"
EXPECTED_MANIFEST_SHA256 = \
    "f0340bb511febbdc29627ccd9c9344e4d47c08dbe9f3d345337c6399c200063a"
EXPECTED_CASE_IDS = [f"20260816T{hour:02d}0000Z" for hour in range(12, 16)]
EXPECTED_VALID_TIMES = [f"2026-08-16T{hour:02d}:00:00Z" for hour in range(12, 16)]
REQUIRED_CASE_FIELDS = [
    "case_id", "valid_time_utc", "fua_path", "fua_sha256",
    "fsf_before_path", "fsf_before_sha256", "fsf_center_path",
    "fsf_center_sha256", "fsf_after_path", "fsf_after_sha256", "lw3_path",
    "lw3_sha256", "vrz_path", "vrz_sha256", "vrt_path", "vrt_sha256",
]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular_unlinked_input(path: Path, expected_hash: str) -> None:
    lexical = Path(os.path.abspath(path))
    if path.is_symlink() or path.resolve() != lexical or not path.is_file():
        raise ValueError(f"input is not an independent regular path: {path}")
    if path.stat().st_nlink != 1 or sha256(path) != expected_hash:
        raise ValueError(f"input identity differs from the case manifest: {path}")


def surface_field(path: Path, name: str) -> np.ndarray:
    with Dataset(path) as dataset:
        # KLAPS PSF has a stale valid_range attribute that masks legitimate
        # 100000 Pa values in the Python client.  Match the Fortran adapter by
        # reading raw values, then enforce the physical range here.
        dataset.set_auto_mask(False)
        raw = dataset[name][:]
    values = np.asarray(raw, dtype=np.float64).squeeze()
    if values.ndim != 2 or np.any(~np.isfinite(values)):
        raise ValueError(f"invalid surface field: {path}:{name}")
    return values


def grid_spacing_m(path: Path, name: str) -> float:
    with Dataset(path) as dataset:
        variable = dataset[name]
        raw = np.asarray(variable[:], dtype=np.float64).squeeze()
        units = str(getattr(variable, "units", "")).strip().lower()
    if raw.ndim != 0 or not np.isfinite(raw) or raw <= 0.0:
        raise ValueError(f"invalid grid spacing: {path}:{name}")
    value = float(raw)
    if units in {"m", "meter", "meters"}:
        return value
    if units in {"km", "kilometer", "kilometers"} and abs(value - 5.0) <= 1.0e-6:
        return 1000.0 * value
    # This exact pinned KLAPS family stores metres numerically with a legacy
    # `kilometers` attribute.  Keep the exception explicit and hash-bound.
    if units in {"km", "kilometer", "kilometers"} and abs(value - 5000.0) <= 1.0e-6:
        return value
    raise ValueError(f"unsupported grid-spacing convention: {path}:{name}")


def independent_bottom_boundary(
    before_path: Path, center_path: Path, after_path: Path
) -> np.ndarray:
    ps_before = surface_field(before_path, "psf")
    ps_center = surface_field(center_path, "psf")
    ps_after = surface_field(after_path, "psf")
    us = surface_field(center_path, "usf")
    vs = surface_field(center_path, "vsf")
    if not (
        ps_before.shape == ps_center.shape == ps_after.shape == us.shape == vs.shape
    ):
        raise ValueError("FSF surface-field shapes differ")
    if any(np.any((field < 50000.0) | (field > 110000.0)) for field in (
        ps_before, ps_center, ps_after
    )) or np.any(np.abs(us) > 100.0) or np.any(np.abs(vs) > 100.0):
        raise ValueError("FSF surface field is outside the numerical boundary contract")
    dx = grid_spacing_m(center_path, "Dx")
    dy = grid_spacing_m(center_path, "Dy")
    dpdx = np.empty_like(ps_center)
    dpdy = np.empty_like(ps_center)
    dpdx[:, 0] = (ps_center[:, 1] - ps_center[:, 0]) / dx
    dpdx[:, -1] = (ps_center[:, -1] - ps_center[:, -2]) / dx
    dpdx[:, 1:-1] = (ps_center[:, 2:] - ps_center[:, :-2]) / (2.0 * dx)
    dpdy[0, :] = (ps_center[1, :] - ps_center[0, :]) / dy
    dpdy[-1, :] = (ps_center[-1, :] - ps_center[-2, :]) / dy
    dpdy[1:-1, :] = (ps_center[2:, :] - ps_center[:-2, :]) / (2.0 * dy)
    return (ps_after - ps_before) / 7200.0 + us * dpdx + vs * dpdy


def verify(root: Path, manifest_path: Path, repo: Path) -> Path:
    transaction = load_module(repo / "tools/cloud_bal_transaction.py", "transaction")
    validator = load_module(
        repo / "tools/validate_real_manufactured_balance.py", "validator"
    )
    plotter = load_module(repo / "tools/plot_real_manufactured_balance.py", "plotter")
    generation = transaction.verify_current_generation(root)
    source_commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    if status:
        raise ValueError("source tree is not clean")

    transaction_manifest = json.loads(
        (generation / "MANIFEST.json").read_text(encoding="utf-8")
    )
    summary = json.loads((generation / "RUN_SUMMARY.json").read_text(encoding="utf-8"))
    regular_unlinked_input(manifest_path, EXPECTED_MANIFEST_SHA256)
    with manifest_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != REQUIRED_CASE_FIELDS:
            raise ValueError("real-geometry manifest schema mismatch")
        cases = list(reader)
    if [case["case_id"] for case in cases] != EXPECTED_CASE_IDS or \
            [case["valid_time_utc"] for case in cases] != EXPECTED_VALID_TIMES:
        raise ValueError("real-geometry manifest is not the reviewed four-case set")
    all_paths = [
        case[field]
        for case in cases
        for field in REQUIRED_CASE_FIELDS
        if field.endswith("_path")
    ]
    if len(all_paths) != len(set(all_paths)):
        raise ValueError("real-geometry manifest contains a duplicate input path")
    workspace = repo.parent
    for case in cases:
        for prefix in ("fua", "fsf_before", "fsf_center", "fsf_after", "lw3", "vrz", "vrt"):
            regular_unlinked_input(
                workspace / case[f"{prefix}_path"], case[f"{prefix}_sha256"]
            )
    case_ids = [case["case_id"] for case in cases]
    expected_products = {"RUN_SUMMARY.json"}
    for case_id in case_ids:
        expected_products.update(
            f"{case_id}.{extension}" for extension in ("nc", "json", "log", "png")
        )
    actual_products = {item["path"] for item in transaction_manifest["products"]}
    if actual_products != expected_products:
        raise ValueError("generation case/product inventory differs from the manifest")
    if transaction_manifest.get("source_commit") != source_commit:
        raise ValueError("generation does not belong to exact source HEAD")
    if transaction_manifest.get("configuration") != EXPECTED_CONFIGURATION:
        raise ValueError("generation configuration mismatch")
    required_summary = {
        "contract": EXPECTED_CONTRACT,
        "source_commit": source_commit,
        "source_tree_clean": True,
        "case_count": 4,
        "background_reftime_utc": "2026-08-16T06:00:00Z",
        "evidence_authority": "NUMERICAL_REAL_GEOMETRY_ONLY",
        "science_authority": "NONE",
        "balance_scope": "TARGET_INCREMENT_PROJECTION_ONLY",
        "target_kind": "MANUFACTURED_TEST",
        "boundary_authority": "MANUFACTURED_TEST_ONLY",
        "surface_wind_frame": "UNRESOLVED_NATIVE",
        "forecast_wave_response_assessed": False,
        "operational_promotion_eligible": False,
        "all_cases_passed": True,
    }
    for key, value in required_summary.items():
        if summary.get(key) != value:
            raise ValueError(f"summary contract mismatch: {key}")
    if summary.get("input_manifest_sha256") != sha256(manifest_path):
        raise ValueError("input manifest hash mismatch")
    if summary.get("input_cases") != cases:
        raise ValueError("input case inventory mismatch")
    if summary.get("case_decisions") != ["NUMERICAL_REAL_GEOMETRY_PASS"] * 4:
        raise ValueError("not every case passed the numerical contract")

    for case_id in case_ids:
        diagnostic = generation / f"{case_id}.nc"
        log = generation / f"{case_id}.log"
        stored_report = json.loads(
            (generation / f"{case_id}.json").read_text(encoding="utf-8")
        )
        if stored_report != validator.validate(diagnostic, log):
            raise ValueError(f"stored validator report differs: {case_id}")
        with Dataset(diagnostic) as dataset:
            persisted_top = np.asarray(
                dataset["omega_top_boundary"][:], dtype=np.float64
            )
            persisted_boundary = np.asarray(
                dataset["omega_bottom_boundary"][:], dtype=np.float64
            )
        case = next(item for item in cases if item["case_id"] == case_id)
        recomputed_boundary = independent_bottom_boundary(
            workspace / case["fsf_before_path"],
            workspace / case["fsf_center_path"],
            workspace / case["fsf_after_path"],
        )
        if persisted_boundary.shape != recomputed_boundary.shape or np.max(
            np.abs(persisted_boundary - recomputed_boundary)
        ) > 2.0e-6:
            raise ValueError(f"surface-boundary recomputation differs: {case_id}")
        if persisted_top.shape != persisted_boundary.shape or np.any(persisted_top != 0.0):
            raise ValueError(f"top test boundary differs from exact zero: {case_id}")
        with tempfile.TemporaryDirectory(prefix="cloud-bal-figure-check-") as temp:
            repeated = Path(temp) / "figure.png"
            plotter.plot(diagnostic, repeated, case_id)
            if sha256(repeated) != sha256(generation / f"{case_id}.png"):
                raise ValueError(f"figure is not reproducible: {case_id}")
    return generation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("publication_root", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args()
    print(verify(args.publication_root, args.manifest, args.repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
