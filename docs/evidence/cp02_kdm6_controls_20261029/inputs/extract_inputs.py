#!/usr/bin/env python3
"""Read-only provenance and selected NetCDF field extraction for CP02 controls."""

import csv
import difflib
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL")
EVIDENCE = Path(__file__).resolve().parent
WORKTREE = EVIDENCE.parents[3]
HISTORICAL = ROOT / "scratch/cp02_six_hour_20260914"
ARMS = ("off", "hydro", "liquid")
EXPECTED_BINARY_SHA256 = "de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168"
BINARY = ROOT / "scratch/cp02_host_unit_contract_x3bcr8ui/host/main/wrf.exe"
MAPPING = WORKTREE / "docs/evidence/cp02_density_controls_20261029/controls/wrf_mapping.csv"
POINTS = {"P01", "P05", "P09", "P13"}
FIELDS = ("QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP",
          "QNCCN", "QNCLOUD", "QNICE", "QNRAIN", "QIB")
EXCLUDED = re.compile(r"^(wrfout_.*|rsl\..*|launcher\.log|run\.exit|namelist\.output)$")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path):
    info = path.stat()
    return {"path": str(path), "size_bytes": info.st_size,
            "mtime_ns": info.st_mtime_ns, "mode_octal": oct(stat.S_IMODE(info.st_mode)),
            "sha256": sha256(path)}


def inventory_run(arm):
    run_dir = HISTORICAL / arm / "run"
    if not run_dir.is_dir():
        raise FileNotFoundError(run_dir)
    entries = []
    for path in sorted(run_dir.iterdir()):
        if path.is_file() and not EXCLUDED.match(path.name):
            record = file_record(path)
            record["name"] = path.name
            record["copy_to"] = path.name
            entries.append(record)
    return {"arm": arm.upper(), "source_run_directory": str(run_dir),
            "scope": "Regular run-directory files excluding wrfout_*, rsl.*, launcher.log, run.exit, and namelist.output; includes namelist.input, wrfinput_d01, wrfbdy_d01, physical_history.txt, and physics tables.",
            "files": entries}


def mapping_points():
    points, corners = {}, {}
    with MAPPING.open(newline="") as source:
        for row in csv.DictReader(source):
            point = row["point_id"]
            if point in POINTS:
                points.setdefault(point, row)
                if row["corner"] in {"00", "10", "01", "11"}:
                    corners.setdefault(point, []).append(row)
    if set(points) != POINTS or any(len(corners.get(p, [])) != 4 for p in POINTS):
        raise ValueError("mapping must contain P01/P05/P09/P13 with four corners each")
    return points, corners


def netcdf_record(path):
    ds = Dataset(path, "r")
    try:
        variables = {}
        for name, var in ds.variables.items():
            variables[name] = {"dimensions": list(var.dimensions), "shape": list(var.shape),
                               "dtype": str(var.dtype),
                               "units": getattr(var, "units", "(attribute absent)")}
        return {"file": file_record(path),
                "dimensions": {name: len(dim) for name, dim in ds.dimensions.items()},
                "variables": variables}
    finally:
        ds.close()


def extract_selected_fields(inventories):
    points, corners = mapping_points()
    records, netcdf_metadata = [], {}
    for arm, inventory in zip(ARMS, inventories):
        run_dir = HISTORICAL / arm / "run"
        input_path = run_dir / "wrfinput_d01"
        source_metadata = {"wrfinput_d01": netcdf_record(input_path),
                           "wrfbdy_d01": netcdf_record(run_dir / "wrfbdy_d01"),
                           "initial_history_12z": netcdf_record(run_dir / "wrfout_d01_2026-08-16_12:00:00")}
        ds = Dataset(input_path, "r")
        try:
            netcdf_metadata[arm.upper()] = {
                "netcdf_sources": source_metadata,
            }
            for name in FIELDS:
                if name not in ds.variables:
                    raise KeyError(f"{input_path} lacks {name}")
                var = ds.variables[name]
                netcdf_metadata[arm.upper()]["netcdf_sources"]["wrfinput_d01"]["variables"][name]["selected_field"] = True
            for point in sorted(POINTS):
                for corner in corners[point]:
                    j, i = int(corner["native_j_zero_based"]), int(corner["native_i_zero_based"])
                    for k in range(39):
                        row = {"arm": arm.upper(), "point_id": point,
                               "role": points[point]["role"], "corner": corner["corner"],
                               "native_j0": j, "native_i0": i, "level_k0": k,
                               "weight": corner["weight"]}
                        for name in FIELDS:
                            var = ds.variables[name]
                            row[name] = float(np.asarray(var[0, k, j, i]))
                        records.append(row)
        finally:
            ds.close()
    fields = list(records[0])
    with (EVIDENCE / "selected_initial_fields.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    return netcdf_metadata, len(records)


def namelist_comparison():
    configs = {}
    lines = {}
    for arm in ARMS:
        path = HISTORICAL / arm / "run/namelist.input"
        raw = path.read_text()
        configs[arm.upper()] = file_record(path)
        lines[arm.upper()] = raw.splitlines(keepends=True)
    diffs = {}
    first = lines[ARMS[0].upper()]
    for arm in ARMS[1:]:
        label = arm.upper()
        diffs[f"OFF_vs_{label}"] = list(difflib.unified_diff(
            first, lines[label], fromfile="OFF/namelist.input", tofile=f"{label}/namelist.input"))
    (EVIDENCE / "namelist_comparison.json").write_text(json.dumps(
        {"configs": configs, "identical_sha256": len({x["sha256"] for x in configs.values()}) == 1,
         "unified_diffs_from_OFF": diffs,
         "note": "Historical namelist.input files are read-only sources; no arm configuration was rewritten."}, indent=2) + "\n")


def provenance(inventories):
    running = HISTORICAL / "RUNNING.json"
    receipt = json.loads(running.read_text())
    binary_record = file_record(BINARY)
    if binary_record["sha256"] != EXPECTED_BINARY_SHA256:
        raise ValueError("historical wrf.exe hash does not match expected RUNNING receipt")
    if receipt.get("executable") != str(BINARY) or receipt.get("executable_sha256") != EXPECTED_BINARY_SHA256:
        raise ValueError("RUNNING.json does not bind the requested historical binary")
    arm_receipts = {}
    for arm in ARMS:
        base = HISTORICAL / arm
        arm_receipts[arm.upper()] = {
            name: file_record(base / name)
            for name in ("PREPARE.json", "run.sh")
        }
    run_receipts = {"RUNNING.json": file_record(running), **{
        f"{arm}/{name}": record for arm, rows in arm_receipts.items()
        for name, record in rows.items()}}
    sections = subprocess.run(["readelf", "-S", str(BINARY)], check=True,
                              text=True, capture_output=True).stdout
    has_dwarf_sections = any(".debug_" in line for line in sections.splitlines())
    (EVIDENCE / "provenance.json").write_text(json.dumps({
        "historical_run_root": str(HISTORICAL), "RUNNING_receipt": receipt,
        "RUNNING_receipt_file": file_record(running),
        "per_arm_receipts": arm_receipts,
        "binary": {**binary_record, "receipt_path": receipt["executable"],
                   "receipt_sha256": receipt["executable_sha256"],
                   "readelf_has_debug_sections": has_dwarf_sections,
                   "source_identity_note": "Binary has no DWARF debug sections; adjacent source names and argument labels remain candidates, not proof of exact compiled source identity."},
        "historical_run_directories": {inv["arm"]: inv["source_run_directory"] for inv in inventories},
        "execution_receipt_scope": "Historical RUNNING.json says all three six-hour arms completed at 8 MPI ranks and 1 OMP thread; this is provenance only and does not validate new results."}, indent=2) + "\n")
    if has_dwarf_sections:
        raise ValueError("expected historical no-DWARF executable limitation changed")


def write_copy_manifest(inventories, netcdf_metadata, selected_count):
    arms = {}
    for inventory in inventories:
        arm = inventory["arm"]
        arms[arm] = {
            "source_run_directory": inventory["source_run_directory"],
            "copy_files": [{"source_path": row["path"], "destination_name": row["copy_to"],
                            "size_bytes": row["size_bytes"], "sha256": row["sha256"]}
                           for row in inventory["files"]],
            "netcdf_sources": netcdf_metadata[arm]["netcdf_sources"],
        }
    (EVIDENCE / "copy_manifest.json").write_text(json.dumps({
        "purpose": "Compact source-to-fresh-scratch launch copy plan for the historical CP02 OFF/HYDRO/LIQUID controls.",
        "historical_run_root": str(HISTORICAL), "inventory_exclusions": EXCLUDED.pattern,
        "mapping_source": file_record(MAPPING),
        "arms": arms,
        "selected_initial_fields": {"csv": "selected_initial_fields.csv", "record_count": selected_count,
                                    "fields": list(FIELDS), "points": sorted(POINTS),
                                    "records_per_arm": selected_count // 3,
                                    "meaning": "Input-array samples only; not proof arrays were consumed unchanged at the first physics call."},
        "launch_usage": "Copy each arm's listed files into a separate fresh run directory. Preserve the arm-specific namelist.input bytes unless a separately documented run-time modification is intentionally required; record such changes outside this historical inventory."}, indent=2) + "\n")


def verify_unchanged(inventories, receipt_paths, initial_snapshot):
    final = {}
    for inventory in inventories:
        for row in inventory["files"]:
            final[row["path"]] = file_record(Path(row["path"]))
    for path in receipt_paths:
        final[str(path)] = file_record(path)
    if initial_snapshot != final:
        changed = sorted(k for k in initial_snapshot.keys() | final.keys()
                         if initial_snapshot.get(k) != final.get(k))
        raise RuntimeError("source changed while read: " + ", ".join(changed))
    return final


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    inventories = [inventory_run(arm) for arm in ARMS]
    receipt_paths = [HISTORICAL / "RUNNING.json", BINARY, MAPPING]
    receipt_paths += [HISTORICAL / arm / name for arm in ARMS for name in ("PREPARE.json", "run.sh")]
    receipt_paths += [HISTORICAL / arm / "run" / name for arm in ARMS
                      for name in ("wrfbdy_d01", "wrfout_d01_2026-08-16_12:00:00")]
    initial_snapshot = {row["path"]: {k: row[k] for k in ("path", "size_bytes", "mtime_ns", "mode_octal", "sha256")}
                        for inventory in inventories for row in inventory["files"]}
    initial_snapshot.update({str(path): file_record(path) for path in receipt_paths})
    (EVIDENCE / "runtime_inventory.json").write_text(json.dumps({"arms": inventories}, indent=2) + "\n")
    netcdf_metadata, count = extract_selected_fields(inventories)
    namelist_comparison()
    provenance(inventories)
    write_copy_manifest(inventories, netcdf_metadata, count)
    # Re-hash after all reads, extraction, and metadata probes; source timestamps and bytes must match.
    final = verify_unchanged(inventories, receipt_paths, initial_snapshot)
    (EVIDENCE / "source_verification.json").write_text(json.dumps({
        "status": "PASS_UNCHANGED_BEFORE_AFTER_READ",
        "source_file_count": len(final),
        "sha256_checked_before_and_after": True,
        "size_mtime_mode_checked_before_and_after": True,
        "note": "Read-only source paths were checked before and after the extraction; no source file changed."}, indent=2) + "\n")


if __name__ == "__main__":
    main()
