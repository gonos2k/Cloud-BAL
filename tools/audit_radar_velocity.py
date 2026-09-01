#!/usr/bin/env python3
"""Audit prepared gridded radar velocities without granting update authority."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from pathlib import Path

import netCDF4
import numpy as np


RADARS = ("v01", "v02", "v03", "v04", "v06", "v07", "v08", "v09", "v10", "v11")
BLOCKED_REASON = (
    "MISSING_NYQUIST_FALL_SPEED_AND_WIND_COORDINATE_PROVENANCE"
)
EXPECTED_VELOCITY_MANIFEST_SHA256 = (
    "2a93b8194a78d91e1ebdb5be6706f0f5fa0c354565cdc80cc862b61b5a3afbf6"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()


def values(variable: netCDF4.Variable) -> np.ndarray:
    # Preserve NetCDF fill-value and valid-range masking.  Recovering masked
    # payload bytes would silently turn rejected radar gates into observations.
    return np.asarray(np.ma.asarray(variable[:], dtype=float).filled(np.nan))


def text_row(variable: netCDF4.Variable) -> str:
    row = np.asarray(variable[0, 0, :]).astype("U1")
    return "".join(row).strip()


def site_from_comment(comment: str) -> tuple[float, float, float]:
    match = re.match(r"\s*([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)", comment)
    if match is None:
        raise ValueError(f"radar site metadata is absent: {comment!r}")
    return tuple(float(value) for value in match.groups())


def inspect_radar(
    path: Path,
    epoch: int,
    radar_mask: np.ndarray,
    diagnostic_pressure_hpa: np.ndarray,
) -> tuple[dict[str, object], int]:
    with netCDF4.Dataset(path, "r") as dataset:
        dimensions = {name: len(dim) for name, dim in dataset.dimensions.items()}
        expected_dimensions = {"x": 235, "y": 283, "z": 22}
        if any(dimensions.get(name) != size for name, size in expected_dimensions.items()):
            raise ValueError("unexpected velocity grid dimensions")
        if tuple(dataset["vel"].dimensions) != ("record", "z", "y", "x"):
            raise ValueError("unexpected velocity dimensions")
        if dataset["vel"].shape != (1, 22, 283, 235):
            raise ValueError("unexpected velocity shape")
        if str(getattr(dataset["vel"], "units", "")).lower() != "meters/second":
            raise ValueError("unexpected velocity units")
        if abs(float(values(dataset["valtime"]).reshape(-1)[0]) - epoch) > 0.5:
            raise ValueError("velocity valid-time mismatch")

        levels = values(dataset["level"]).reshape(-1)
        expected_levels = np.arange(50.0, 1100.1, 50.0)
        if not np.array_equal(levels, expected_levels):
            raise ValueError("unexpected radar velocity pressure levels")
        if diagnostic_pressure_hpa.shape != levels.shape:
            raise ValueError("diagnostic pressure-level count mismatch")
        mapping = np.array(
            [int(np.argmin(np.abs(levels - pressure))) for pressure in diagnostic_pressure_hpa]
        )
        if not np.allclose(levels[mapping], diagnostic_pressure_hpa, rtol=0.0, atol=1.0e-6):
            raise ValueError("radar/diagnostic pressure mapping failed")
        if len(np.unique(mapping)) != len(mapping):
            raise ValueError("radar/diagnostic pressure mapping is not one-to-one")
        velocity = values(dataset["vel"])[0][mapping]
        nyquist = values(dataset["nyq"])[0][mapping]
        velocity_valid = np.isfinite(velocity) & (np.abs(velocity) < 200.0)
        nyquist_valid = np.isfinite(nyquist) & (nyquist > 0.0) & (nyquist < 200.0)
        site_lat, site_lon, site_height = site_from_comment(text_row(dataset["vel_comment"]))

    overlap = velocity_valid & radar_mask
    count = int(np.count_nonzero(overlap))
    result = {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "site_latitude": site_lat,
        "site_longitude": site_lon,
        "site_height_m": site_height,
        "velocity_usable_cells": int(np.count_nonzero(velocity_valid)),
        "nyquist_usable_cells": int(np.count_nonzero(nyquist_valid)),
        "vertical_mapping": "PRESSURE_MATCHED",
        "direct_echo_overlap_cells": count,
        "horizontal_only_background_rms_ms": None,
        "horizontal_only_candidate_rms_ms": None,
        "candidate_improved_absolute_residual_cells": None,
    }
    return result, count


def inspect_case(
    workspace: Path,
    diagnostic_root: Path,
    row: dict[str, str],
    velocity_inputs: dict[tuple[str, str], dict[str, str]],
) -> dict[str, object]:
    case_id = row["case_id"]
    diagnostic_path = diagnostic_root / f"{case_id}.nc"
    with netCDF4.Dataset(diagnostic_path, "r") as diagnostic:
        if getattr(diagnostic, "result_authority", "") != "DIAGNOSTIC_PROPOSAL_ONLY":
            raise ValueError("diagnostic proposal contract is missing")
        radar_mask = values(diagnostic["radar_valid"]).astype(bool)
        diagnostic_pressure_hpa = values(diagnostic["pressure"]) / 100.0
        epoch = int(getattr(diagnostic, "valid_time_epoch"))

    entries = []
    total_count = 0
    for radar in RADARS:
        record = velocity_inputs.get((case_id, radar))
        if record is None:
            raise ValueError(f"missing pinned velocity input: {case_id}/{radar}")
        expected_relative = (
            f"ANAL/NE57/DAOU/00/lapsprd/{radar}/{row['laps_stamp']}.{radar}"
        )
        if record["path"] != expected_relative:
            raise ValueError(f"velocity path identity mismatch: {case_id}/{radar}")
        path = workspace / record["path"]
        if (
            not path.is_file()
            or path.is_symlink()
            or path.resolve() != path.absolute()
            or sha256(path) != record["sha256"]
        ):
            raise FileNotFoundError(path)
        entry, overlap_count = inspect_radar(
            path, epoch, radar_mask, diagnostic_pressure_hpa
        )
        if entry["sha256"] != record["sha256"]:
            raise ValueError(f"velocity input changed while reading: {case_id}/{radar}")
        entry["radar_grid"] = radar
        entries.append(entry)
        total_count += overlap_count

    return {
        "case_id": case_id,
        "diagnostic_sha256": sha256(diagnostic_path),
        "velocity_files": entries,
        "usable_velocity_cells": sum(item["velocity_usable_cells"] for item in entries),
        "usable_nyquist_cells": sum(item["nyquist_usable_cells"] for item in entries),
        "direct_echo_overlap_cells": total_count,
        "horizontal_only_background_rms_ms": None,
        "horizontal_only_candidate_rms_ms": None,
        "candidate_improved_absolute_residual_fraction": None,
        "decision": "DIAGNOSTIC_ONLY",
        "blocked_reason": BLOCKED_REASON,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--workspace-root", type=Path, default=root.parent)
    parser.add_argument("--manifest", type=Path, default=root / "tests/qbal_real_cases_20260816.tsv")
    parser.add_argument(
        "--velocity-manifest",
        type=Path,
        default=root / "tests/radar_velocity_cases_20260816.tsv",
    )
    parser.add_argument(
        "--diagnostic-root",
        type=Path,
        default=root / "scratch/publications/real_shadow/current",
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    try:
        with args.manifest.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        with args.velocity_manifest.open(newline="", encoding="utf-8") as stream:
            velocity_rows = list(csv.DictReader(stream, delimiter="\t"))
        if sha256(args.velocity_manifest) != EXPECTED_VELOCITY_MANIFEST_SHA256:
            raise ValueError("velocity manifest identity mismatch")
        velocity_inputs = {
            (item["case_id"], item["radar_grid"]): item for item in velocity_rows
        }
        expected_velocity_keys = {
            (row["case_id"], radar) for row in rows for radar in RADARS
        }
        if set(velocity_inputs) != expected_velocity_keys or len(velocity_rows) != 40:
            raise ValueError("velocity manifest is not the exact four-case/ten-radar set")
        diagnostic_root = args.diagnostic_root.resolve(strict=True)
        cases = [
            inspect_case(
                args.workspace_root.resolve(), diagnostic_root, row, velocity_inputs
            )
            for row in rows
        ]
        report = {
            "contract": "radar_velocity_diagnostic_v1",
            "case_count": len(cases),
            "radar_count_per_case": len(RADARS),
            "velocity_manifest_sha256": sha256(args.velocity_manifest),
            "radar_velocity_authority": False,
            "implemented_observation_operator": "NONE_COUNTS_ONLY",
            "wind_coordinate_contract": "UNRESOLVED_GRID_OR_EARTH",
            "hydrometeor_fall_speed_applied": False,
            "hydrometeor_fall_speed_required_for_authority": True,
            "nyquist_required_for_authority": True,
            "s_band_wavelength_provenance_in_grid_file": False,
            "science_assessed": False,
            "promotion_eligible": False,
            "overall_status": f"DIAGNOSTIC_ONLY_BLOCKED_{BLOCKED_REASON}",
            "cases": cases,
        }
    except Exception as error:
        print(json.dumps({"overall_status": "FAIL", "error": str(error)}, indent=2))
        return 2
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json:
        write_text_atomic(args.json, rendered)
    print(rendered, end="")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
