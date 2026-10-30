#!/usr/bin/env python3
"""Freeze input-only QSNOW gates, stage eight pinned six-hour cases, and audit them."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import netCDF4
import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))
from initial_precip_gate import (GRAVITY, QUANTILE_PAIRS, column_precip_proxy,
                                 case_qsnow_transform, dry_snow_mass, equal_mass_alpha,
                                 freeze, scaled_qsnow)


SOURCE_PLAN = ROOT / "docs/evidence/snow_lower_20261030/runtime/common_plan.json"
SELECTION_PLAN = HERE.parent / "selection_plan.json"
ORIGINAL_RUN = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8/original")
B1_SOURCE = Path("/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED")
OLD_EXE = Path("/var/tmp/firsthour-runtime-plan-20261030/experiment/run_BASE_H/wrf.exe")
B1_EVIDENCE = Path("/var/tmp/cloudbal-six-hour-improved/docs/evidence/six_hour_improvement_20261030/runtime")
OLD_EVIDENCE = Path("/var/tmp/cloudbal-six-hour-improved/docs/evidence/current_forecast_paper_20261029/runtime")
SCRATCH_ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030")
INTEL_PROFILE = ROOT / "tests/intel_toolchain.sh"
INTEL_MPI = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun")
INTEL_MPI_ENV = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh")
INTEL_MPI_VERSION = "Intel(R) MPI Library for Linux* OS, Version 2021.18.0 Build 20260327 (id: 821f207)"
EXPECTED_PROFILE_SHA = "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4"
EXPECTED_SOURCE_PLAN_SHA = "58dae266e4b4f893f5a9d940e30c8e38574823b03785e68b089811ef9d085871"
EXPECTED_SELECTION_PLAN_SHA = "17e8833f2f28da76e1474f82440a88889bd55ba723ef9cd6618d06a0eb786248"
EXPECTED_HOURS = [f"wrfout_d01_2026-08-16_{hour:02d}:00:00" for hour in range(12, 19)]
MIN_RESERVE = 3 * 1024**3
CASE_IDS = ("GATE_G50_90", "EQ_G50_90", "GATE_G75_95", "EQ_G75_95",
            "GATE_G90_99", "EQ_G90_99", "FIXED_ORIGINAL_100", "ORIGINAL_B1_100")
SLOT_CASES = {slot: [case] for slot, case in enumerate(CASE_IDS)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def value_hash(variable) -> str:
    values = np.asanyarray(variable[:])
    digest = hashlib.sha256()
    digest.update(str(values.dtype).encode())
    digest.update(json.dumps(list(values.shape)).encode())
    if np.ma.isMaskedArray(values):
        digest.update(np.ascontiguousarray(np.ma.getmaskarray(values)).tobytes())
        values = np.ma.getdata(values)
    digest.update(np.ascontiguousarray(values).tobytes())
    return digest.hexdigest()


def jsonable(value):
    if isinstance(value, np.ndarray):
        return {"dtype": str(value.dtype), "shape": list(value.shape), "values": value.tolist()}
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(v) for v in value]
    return value


def attrs(obj):
    return {name: obj.getncattr(name) for name in obj.ncattrs()}


def native_contract(path):
    with netCDF4.Dataset(path) as dataset:
        metadata = {
            "global_attrs": jsonable(attrs(dataset)),
            "dimensions": {name: {"size": len(dim), "unlimited": dim.isunlimited()}
                           for name, dim in dataset.dimensions.items()},
            "variables": {name: {"dtype": str(var.dtype), "dimensions": list(var.dimensions),
                                  "shape": list(var.shape), "attrs": jsonable(attrs(var)),
                                  "chunking": var.chunking(), "filters": var.filters(),
                                  "endian": var.endian()}
                          for name, var in dataset.variables.items()},
        }
        hashes = {name: value_hash(var) for name, var in dataset.variables.items()}
        return metadata, hashes


def metadata_equal(left_path, right_path):
    left, _ = native_contract(left_path)
    right, _ = native_contract(right_path)
    return left == right


def proc_table():
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().split(b"\0")
            command = [part.decode(errors="replace") for part in cmdline if part]
            if any(Path(arg).name == "wrf.exe" for arg in command):
                yield int(entry.name), command
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue


def validate_sources(source_plan):
    original_inventory = source_plan["original_source_sha256_before"]
    b1_inventory = source_plan["source_b1_input_sha256_before"]
    assert len(original_inventory) == len(b1_inventory) == 89
    assert set(original_inventory) - set(b1_inventory) == {"namelist.output"}
    assert set(b1_inventory) - set(original_inventory) == {"wrf.exe"}
    shared_names = set(original_inventory) & set(b1_inventory)
    assert [name for name in shared_names if original_inventory[name] != b1_inventory[name]] == ["wrfinput_d01"]
    expected = {
        "wrf.exe": "68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f",
        "wrfinput_d01": "9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5",
        "wrfbdy_d01": "74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45",
    }
    for name, digest in expected.items():
        assert b1_inventory[name] == digest
    assert source_plan["original_executable_sha256"] == "de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168"
    assert original_inventory["wrfinput_d01"] == "5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc"
    assert original_inventory["wrfbdy_d01"] == expected["wrfbdy_d01"]
    assert source_plan["common_six_hour_namelist_sha256"] == "eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df"
    assert sha256(OLD_EXE) == source_plan["original_executable_sha256"]
    assert {name: sha256(ORIGINAL_RUN / name) for name in original_inventory} == original_inventory
    assert sha256(OLD_EXE) == source_plan["original_executable_sha256"]
    assert {name: sha256(B1_SOURCE / name) for name in b1_inventory} == b1_inventory
    evidence = source_plan["source_evidence_sha256_before"]
    assert all(sha256(Path(path)) == digest for path, digest in evidence.items())
    return original_inventory, b1_inventory, evidence


def main():
    if SCRATCH_ROOT.exists():
        raise RuntimeError(f"fresh scratch root already exists: {SCRATCH_ROOT}")
    SCRATCH_ROOT.mkdir(parents=True)
    if len(list(proc_table())):
        raise RuntimeError("another wrf.exe process is active; refusing concurrent batch")
    allowed_cpus = sorted(os.sched_getaffinity(0))
    if len(allowed_cpus) < 64:
        raise RuntimeError(f"need 64 CPUs for eight disjoint 8-rank cases; found {len(allowed_cpus)}")
    cpu_slots = {slot: allowed_cpus[slot * 8:(slot + 1) * 8] for slot in range(8)}
    if len({cpu for cpus in cpu_slots.values() for cpu in cpus}) != 64:
        raise RuntimeError("CPU slots overlap or omit CPUs")

    selection_sha = sha256(SELECTION_PLAN)
    if selection_sha != EXPECTED_SELECTION_PLAN_SHA or sha256(SOURCE_PLAN) != EXPECTED_SOURCE_PLAN_SHA:
        raise RuntimeError("frozen selection or prior source-plan pin mismatch")
    selection = json.loads(SELECTION_PLAN.read_text())
    if (selection["status"] != "FROZEN_BEFORE_NEW_FORECAST_OUTPUTS"
            or selection["forecast_output_or_observation_used_for_gate"] is not False
            or [case["case"] for case in selection["experiment"]["cases"]] != list(CASE_IDS)):
        raise RuntimeError("selection plan is not frozen for the exact eight cases")
    source_plan = json.loads(SOURCE_PLAN.read_text())
    original_inventory, b1_inventory, evidence_hashes = validate_sources(source_plan)
    old_receipt_path = OLD_EVIDENCE / "original_hydro_completed_receipt.json"
    b1_receipt_path = B1_EVIDENCE / "normalized_receipt.json"
    old_receipt = json.loads(old_receipt_path.read_text())
    b1_receipt = json.loads(b1_receipt_path.read_text())
    if old_receipt["ORIGINAL"]["status"] != "COMPLETE" or b1_receipt["status"] != "SUCCESS":
        raise RuntimeError("parent runtime receipts are not complete")
    assert b1_receipt["contract"]["boundary_sha256"] == b1_inventory["wrfbdy_d01"]

    baseline_bytes = sum((B1_SOURCE / name).stat().st_size for name in source_plan["source_b1_input_sha256_before"])
    required = 8 * baseline_bytes + MIN_RESERVE
    free_before = shutil.disk_usage(SCRATCH_ROOT).free
    if free_before < required:
        raise RuntimeError(f"insufficient fresh-scratch space: {free_before} < {required}")
    if sha256(INTEL_PROFILE) != EXPECTED_PROFILE_SHA:
        raise RuntimeError("pinned Intel toolchain profile hash mismatch")
    mpi_version = subprocess.run([str(INTEL_MPI), "--version"], check=True,
                                 capture_output=True, text=True).stdout.splitlines()[0]
    if mpi_version != "Intel(R) MPI Library for Linux* OS, Version 2021.18.0 Build 20260327 (id: 821f207)":
        raise RuntimeError(f"Intel MPI version mismatch: {mpi_version}")
    mpi_contract = {"profile_path": str(INTEL_PROFILE), "profile_sha256": sha256(INTEL_PROFILE),
                    "mpi_path": str(INTEL_MPI), "mpi_sha256": sha256(INTEL_MPI),
                    "mpi_version": mpi_version, "mpi_env_path": str(INTEL_MPI_ENV),
                    "mpi_env_sha256": sha256(INTEL_MPI_ENV)}

    original_input = ORIGINAL_RUN / "wrfinput_d01"
    with netCDF4.Dataset(original_input) as dataset:
        proxy, geometry = column_precip_proxy(dataset, GRAVITY)
        source_qsnow = np.asarray(dataset.variables["QSNOW"][0])
    maps_path = HERE / "frozen" / "initial_precip_gate_maps.npz"
    gate_manifest = freeze(original_input, maps_path)
    frozen_map = np.load(maps_path)
    assert gate_manifest["source_wrfinput_sha256"] == original_inventory["wrfinput_d01"]
    (HERE / "frozen").mkdir(exist_ok=True)
    gate_manifest_path = HERE / "frozen" / "gate_manifest.json"
    gate_manifest_path.write_text(json.dumps(gate_manifest, indent=2, sort_keys=True) + "\n")

    launch_files = ("prepare_cases.py", "run_case.py", "run_all.py", "finalize_batch.py", "env.sh")
    launch_hashes = {name: sha256(HERE / name) for name in launch_files}
    (HERE / "launch_scripts.sha256.json").write_text(json.dumps(launch_hashes, indent=2, sort_keys=True) + "\n")

    b1_metadata, b1_value_hashes = native_contract(B1_SOURCE / "wrfinput_d01")
    original_metadata, original_value_hashes = native_contract(original_input)
    if original_metadata != b1_metadata:
        raise RuntimeError("parent input metadata differs across CONTROL and B1 sources")
    metadata_digest = hashlib.sha256(json.dumps(original_metadata, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    cases, field_hashes, audits = {}, {}, {}
    for case_id in CASE_IDS:
        case_dir = SCRATCH_ROOT / case_id
        case_dir.mkdir()
        input_family = "B1" if case_id == "ORIGINAL_B1_100" else "ORIGINAL"
        exe_family = "B1" if case_id == "FIXED_ORIGINAL_100" else "ORIGINAL"
        input_root = B1_SOURCE if input_family == "B1" else ORIGINAL_RUN
        for name in b1_inventory:
            source_path = B1_SOURCE / name
            subprocess.run(["cp", "--reflink=auto", "--", str(source_path), str(case_dir / name)], check=True)
        shutil.copy2((B1_SOURCE / "wrf.exe") if exe_family == "B1" else OLD_EXE,
                     case_dir / "wrf.exe")
        shutil.copy2(input_root / "wrfinput_d01", case_dir / "wrfinput_d01")
        if len(list(case_dir.iterdir())) != 89:
            raise RuntimeError(f"{case_id}: staged input count is not 89")
        for name in b1_inventory:
            if (case_dir / name).stat().st_nlink != 1:
                raise RuntimeError(f"{case_id}: staged input is hard-linked: {name}")
        alpha_mean = 1.0
        transform = "unchanged input"
        source_field_hashes = original_value_hashes if input_family == "ORIGINAL" else b1_value_hashes
        expected_source_input = original_inventory["wrfinput_d01"] if input_family == "ORIGINAL" else b1_inventory["wrfinput_d01"]
        q_audit = {"source_family": input_family, "executable_family": exe_family,
                   "source_wrfinput_sha256": expected_source_input,
                   "source_qsnow_value_sha256": source_field_hashes["QSNOW"],
                   "changed_variables": [], "other_207_values_unchanged": True,
                   "all_metadata_unchanged": True}
        staged_snow_mass = None
        relative_mass_difference = None
        case_transform = case_qsnow_transform(case_id, source_qsnow, frozen_map)
        gate_name = case_transform["gate_name"]
        alpha = case_transform["alpha"]
        replacement = case_transform["replacement"]
        transform = case_transform["transform"]
        alpha_mean = float(np.mean(alpha, dtype=np.float64)) if isinstance(alpha, np.ndarray) else alpha
        if case_transform["write_qsnow"]:
            with netCDF4.Dataset(case_dir / "wrfinput_d01", "r+") as target:
                target.variables["QSNOW"][:] = replacement[None, ...]
                staged_qsnow = np.asarray(target.variables["QSNOW"][0])
                if not np.array_equal(staged_qsnow, replacement):
                    raise RuntimeError(f"{case_id}: reread staged QSNOW differs from frozen float32 values")
            staged_snow_mass = dry_snow_mass(staged_qsnow, geometry["dry_mass_kg"])
            if case_id.startswith("EQ_"):
                gate_mass = dry_snow_mass(frozen_map[f"{gate_name}_qsn_gated"],
                                          geometry["dry_mass_kg"])
                relative_mass_difference = abs(staged_snow_mass - gate_mass) / gate_mass
                if relative_mass_difference > 1e-6:
                    raise RuntimeError(f"{case_id}: staged equal-mass tolerance exceeded")
            else:
                relative_mass_difference = 0.0
        staged_metadata, staged_values = native_contract(case_dir / "wrfinput_d01")
        expected_metadata = original_metadata if input_family == "ORIGINAL" else b1_metadata
        if staged_metadata != expected_metadata:
            raise RuntimeError(f"{case_id}: native metadata changed")
        with netCDF4.Dataset(input_root / "wrfinput_d01") as src, netCDF4.Dataset(case_dir / "wrfinput_d01") as staged:
            changed = []
            for name, variable in src.variables.items():
                if name == "QSNOW" and case_transform["write_qsnow"]:
                    changed.append(name)
                    continue
                if value_hash(variable) != staged_values[name]:
                    raise RuntimeError(f"{case_id}: non-target variable changed: {name}")
            if changed != (["QSNOW"] if case_transform["write_qsnow"] else []):
                raise RuntimeError(f"{case_id}: unexpected changed variable set {changed}")
        staged_hashes = {name: sha256(case_dir / name) for name in b1_inventory}
        expected_exe = b1_inventory["wrf.exe"] if exe_family == "B1" else source_plan["original_executable_sha256"]
        if staged_hashes["wrf.exe"] != expected_exe or staged_hashes["wrfbdy_d01"] != b1_inventory["wrfbdy_d01"]:
            raise RuntimeError(f"{case_id}: executable or boundary identity mismatch")
        if staged_hashes["namelist.input"] != b1_inventory["namelist.input"]:
            raise RuntimeError(f"{case_id}: namelist changed")
        if input_family == "ORIGINAL" and not case_transform["write_qsnow"]:
            if staged_hashes["wrfinput_d01"] != original_inventory["wrfinput_d01"]:
                raise RuntimeError(f"{case_id}: original cross input identity mismatch")
        elif input_family == "B1":
            if staged_hashes["wrfinput_d01"] != b1_inventory["wrfinput_d01"]:
                raise RuntimeError(f"{case_id}: B1 cross input identity mismatch")
        q_audit.update({"transform": transform, "scaled_qsnow_value_sha256": staged_values["QSNOW"],
                        "changed_variables": changed, "input_alpha_mean": alpha_mean,
                        "staged_diagnostic_snow_mass_kg": staged_snow_mass,
                        "matched_gate_relative_mass_difference": relative_mass_difference,
                        "other_207_values_unchanged": True,
                        "all_metadata_unchanged": True})
        if case_transform["write_qsnow"]:
            q_audit.update(gate_manifest["gate_controls"][gate_name])
            q_audit["frozen_gate_manifest_sha256"] = sha256(gate_manifest_path)
            q_audit["frozen_map_sha256"] = sha256(maps_path)
        field_hashes[case_id] = staged_values
        audits[case_id] = q_audit
        cases[case_id] = {"case": case_id, "group": case_id,
                          "display_label": transform, "alpha": alpha_mean,
                          "input_family": input_family, "executable_family": exe_family,
                          "scratch_directory": str(case_dir), "slot": None, "cpu_set": None,
                          "staged_sha256": staged_hashes, "qsnow_audit": q_audit,
                          "expected_hours": EXPECTED_HOURS}

    for slot, case_ids in SLOT_CASES.items():
        case_id = case_ids[0]
        cases[case_id]["slot"] = slot
        cases[case_id]["cpu_set"] = cpu_slots[slot]

    source_after = validate_sources(source_plan)
    if source_after != (original_inventory, b1_inventory, evidence_hashes):
        raise RuntimeError("source identities changed during staging")
    free_after = shutil.disk_usage(SCRATCH_ROOT).free
    if free_after < MIN_RESERVE:
        raise RuntimeError("scratch reserve fell below 3 GiB")
    plan = {
        "status": "PASS_READY_TO_LAUNCH", "created_utc": datetime.now(timezone.utc).isoformat(),
        "selection_plan_sha256": selection_sha, "launch_scripts_sha256": launch_hashes,
        "scope": "input-only gated QSNOW and matched initial dry-mass QSNOW diagnostics; not conservative or production",
        "scratch_root": str(SCRATCH_ROOT), "case_count": 8, "case_ids": list(CASE_IDS),
        "expected_histories": EXPECTED_HOURS, "declared_input_count_per_case": 89,
        "native_variable_count": 208, "other_207_values_unchanged": True,
        "all_native_metadata_unchanged": True, "native_metadata_sha256": metadata_digest,
        "source_plan_path": str(SOURCE_PLAN), "source_plan_sha256": sha256(SOURCE_PLAN),
        "source_original_input_sha256": original_inventory["wrfinput_d01"],
        "source_b1_input_sha256": b1_inventory["wrfinput_d01"],
        "source_original_executable_sha256": source_plan["original_executable_sha256"],
        "source_fixed_executable_sha256": b1_inventory["wrf.exe"],
        "common_boundary_sha256": b1_inventory["wrfbdy_d01"],
        "common_namelist_sha256": b1_inventory["namelist.input"],
        "source_original_input_manifest_sha256": original_inventory,
        "source_b1_input_manifest_sha256": b1_inventory,
        "source_evidence_sha256": evidence_hashes,
        "gate_map_path": str(maps_path), "gate_map_sha256": sha256(maps_path),
        "gate_manifest_path": str(gate_manifest_path), "gate_manifest_sha256": sha256(gate_manifest_path),
        "gate_manifest": gate_manifest, "gravity_m_s2": GRAVITY,
        "mpi_ranks_per_case": 8, "omp_threads_per_rank": 1, "max_concurrent_cases": 8,
        "intel_runtime": mpi_contract,
        "cpu_affinity": {"method": "taskset per slot and Intel MPI pin list; disjoint 8-CPU sets",
                          "allowed_cpus": allowed_cpus, "slots": cpu_slots, "slot_cases": SLOT_CASES},
        "source_inputs_before_after_equal": True,
        "field_metadata_contract": original_metadata,
        "source_field_value_sha256": {"ORIGINAL": original_value_hashes, "B1": b1_value_hashes},
        "case_records": cases, "case_field_value_sha256": field_hashes,
        "case_qsnow_audit": audits, "free_bytes_before_stage": free_before,
        "free_bytes_after_stage": free_after, "minimum_free_reserve_bytes": MIN_RESERVE,
        "expected_output_bytes_per_case": baseline_bytes,
    }
    (HERE / "common_plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    (HERE / "qsnow_audit.json").write_text(json.dumps(audits, indent=2, sort_keys=True) + "\n")
    (HERE / "field_metadata_contract.json").write_text(json.dumps(original_metadata, indent=2, sort_keys=True) + "\n")
    (HERE / "field_value_source_sha256.json").write_text(json.dumps({"ORIGINAL": original_value_hashes, "B1": b1_value_hashes}, indent=2, sort_keys=True) + "\n")
    (HERE / "field_value_case_sha256.json").write_text(json.dumps(field_hashes, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": plan["status"], "case_ids": CASE_IDS,
                      "selection_plan_sha256": selection_sha,
                      "gate_map_sha256": plan["gate_map_sha256"],
                      "common_boundary_sha256": plan["common_boundary_sha256"],
                      "common_namelist_sha256": plan["common_namelist_sha256"],
                      "native_metadata_sha256": metadata_digest,
                      "other_207_values_unchanged": True,
                      "free_bytes_before_stage": free_before,
                      "free_bytes_after_stage": free_after}, indent=2))


if __name__ == "__main__":
    main()
