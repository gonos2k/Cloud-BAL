#!/usr/bin/env python3
"""Stage and audit original-control and improved B1 QSNOW sensitivity cases."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import netCDF4
import numpy as np


B1_SOURCE = Path("/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED")
ORIGINAL_RUN = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8/original")
OLD_EXE = Path("/var/tmp/firsthour-runtime-plan-20261030/experiment/run_BASE_H/wrf.exe")
SCRATCH_ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/snow_extension_20261030")
EVIDENCE = Path(__file__).resolve().parent
B1_RUNTIME_EVIDENCE = Path("/var/tmp/cloudbal-six-hour-improved/docs/evidence/six_hour_improvement_20261030/runtime")
OLD_RUNTIME_EVIDENCE = Path("/var/tmp/cloudbal-six-hour-improved/docs/evidence/current_forecast_paper_20261029/runtime")
OLD_INPUT_MANIFEST = OLD_RUNTIME_EVIDENCE / "original.inflight_inputs.sha256"
OLD_RECEIPT = OLD_RUNTIME_EVIDENCE / "original_hydro_completed_receipt.json"
ALPHAS = (
    ("175", 1.75),
    ("200", 2.0),
    ("250", 2.5),
    ("300", 3.0),
)
B1_PINNED = {
    "wrf.exe": "68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f",
    "wrfinput_d01": "9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5",
    "wrfbdy_d01": "74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45",
}
OLD_PINNED = {
    "wrf.exe": "de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168",
    "wrfinput_d01": "5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc",
    "wrfbdy_d01": "74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45",
}
SELECTION_PLAN = EVIDENCE.parent / "selection_plan.json"
PRIOR_FAILED_ATTEMPT = Path("/var/tmp/cloudbal-snow-sensitivity/docs/evidence/snow_sensitivity_20261030/runtime/attempts/initial_noexec/attempt.json")
HOURS = [f"wrfout_d01_2026-08-16_{hour:02d}:00:00" for hour in range(12, 19)]
MIN_RESERVE = 3 * 1024**3
SLOT_CASES = {
    0: ["CONTROL_SNOW_175"],
    1: ["IMPROVED_SNOW_175"],
    2: ["CONTROL_SNOW_200"],
    3: ["IMPROVED_SNOW_200"],
    4: ["CONTROL_SNOW_250"],
    5: ["IMPROVED_SNOW_250"],
    6: ["CONTROL_SNOW_300"],
    7: ["IMPROVED_SNOW_300"],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def attrs(obj) -> dict:
    return {name: obj.getncattr(name) for name in obj.ncattrs()}


def robust_equal(left, right) -> bool:
    a, b = np.asanyarray(left), np.asanyarray(right)
    if a.shape != b.shape or a.dtype != b.dtype:
        return False
    if np.ma.isMaskedArray(a) or np.ma.isMaskedArray(b):
        if not np.array_equal(np.ma.getmaskarray(a), np.ma.getmaskarray(b)):
            return False
        a, b = np.ma.getdata(a), np.ma.getdata(b)
    if a.dtype.kind in "fc":
        return bool(np.array_equal(a, b, equal_nan=True))
    return bool(np.array_equal(a, b))


def attr_equal(left, right) -> bool:
    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        return robust_equal(left, right)
    if isinstance(left, (float, np.floating)) and isinstance(right, (float, np.floating)):
        return bool(np.isnan(left) and np.isnan(right)) or left == right
    return type(left) is type(right) and left == right


def jsonable(value):
    if isinstance(value, np.ndarray):
        return {"dtype": str(value.dtype), "shape": list(value.shape), "values": [jsonable(x) for x in value.tolist()]}
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, float) and np.isnan(value):
        return {"float": "nan"}
    if isinstance(value, float) and np.isinf(value):
        return {"float": "inf" if value > 0 else "-inf"}
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(x) for x in value]
    return value


def variable_metadata(variable) -> dict:
    return {
        "dtype": str(variable.dtype),
        "dimensions": list(variable.dimensions),
        "shape": list(variable.shape),
        "attrs": attrs(variable),
        "chunking": variable.chunking(),
        "filters": variable.filters(),
        "endian": variable.endian(),
    }


def field_value_sha256(variable) -> str:
    values = np.asanyarray(variable[:])
    digest = hashlib.sha256()
    digest.update(str(values.dtype).encode())
    digest.update(json.dumps(list(values.shape)).encode())
    if np.ma.isMaskedArray(values):
        digest.update(np.ascontiguousarray(np.ma.getmaskarray(values)).tobytes())
        values = np.ma.getdata(values)
    digest.update(np.ascontiguousarray(values).tobytes())
    return digest.hexdigest()


def compare_metadata(source, target) -> bool:
    if source.ncattrs() != target.ncattrs():
        return False
    if any(not attr_equal(source.getncattr(k), target.getncattr(k)) for k in source.ncattrs()):
        return False
    if list(source.dimensions) != list(target.dimensions):
        return False
    for name in source.dimensions:
        left, right = source.dimensions[name], target.dimensions[name]
        if len(left) != len(right) or left.isunlimited() != right.isunlimited():
            return False
    if list(source.variables) != list(target.variables):
        return False
    for name in source.variables:
        left, right = variable_metadata(source.variables[name]), variable_metadata(target.variables[name])
        if left["dtype"] != right["dtype"] or left["dimensions"] != right["dimensions"] or left["shape"] != right["shape"]:
            return False
        if left["chunking"] != right["chunking"] or left["filters"] != right["filters"] or left["endian"] != right["endian"]:
            return False
        if left["attrs"].keys() != right["attrs"].keys():
            return False
        if any(not attr_equal(left["attrs"][k], right["attrs"][k]) for k in left["attrs"]):
            return False
    return True


def native_contract(path: Path):
    with netCDF4.Dataset(path) as dataset:
        metadata = {
            "global_attrs": jsonable(attrs(dataset)),
            "dimensions": {name: {"size": len(dim), "unlimited": dim.isunlimited()} for name, dim in dataset.dimensions.items()},
            "variables": jsonable({name: variable_metadata(var) for name, var in dataset.variables.items()}),
        }
        values = {name: field_value_sha256(variable) for name, variable in dataset.variables.items()}
        data = np.asarray(dataset.variables["QSNOW"][:], dtype=np.float64)
        assert dataset.variables["QSNOW"].dtype == np.dtype("float32")
        assert np.isfinite(data).all() and (data >= 0).all()
        return metadata, values, data.astype(np.float32), len(dataset.variables), len(dataset.dimensions)


def source_hashes_for(group: str, base_hashes: dict) -> dict:
    result = dict(base_hashes)
    if group == "CONTROL":
        result["wrf.exe"] = OLD_PINNED["wrf.exe"]
        result["wrfinput_d01"] = OLD_PINNED["wrfinput_d01"]
    return result


def case_id(group: str, alpha_code: str) -> str:
    return f"{group}_SNOW_{alpha_code}"


def main() -> None:
    if SCRATCH_ROOT.exists():
        assert not any(SCRATCH_ROOT.iterdir()), f"Scratch root must be fresh: {SCRATCH_ROOT}"
    else:
        SCRATCH_ROOT.mkdir(parents=True)
    allowed_cpus = sorted(os.sched_getaffinity(0))
    assert len(allowed_cpus) >= 64, f"Need 64 CPUs for eight concurrent 8-rank runs; found {len(allowed_cpus)}"
    cpu_slots = {slot: allowed_cpus[slot * 8:(slot + 1) * 8] for slot in range(8)}
    assert len({cpu for cpus in cpu_slots.values() for cpu in cpus}) == 64

    b1_manifest = json.loads((B1_SOURCE / "inputs.json").read_text())
    base_hashes = b1_manifest["staged"]
    old_manifest_names = {line.split(None, 1)[1].removeprefix("./") for line in OLD_INPUT_MANIFEST.read_text().splitlines()}
    assert len(base_hashes) == 89 and len(old_manifest_names) == 89
    assert set(base_hashes) == (old_manifest_names - {"namelist.output"}) | {"wrf.exe"}
    assert len(HOURS) == 7 and sorted(path.name for path in B1_SOURCE.glob("wrfout*")) == sorted(HOURS)
    assert json.loads((B1_SOURCE / "receipt.json").read_text())["status"] == "SUCCESS"
    assert json.loads((B1_RUNTIME_EVIDENCE / "normalized_receipt.json").read_text())["contract"]["boundary_sha256"] == B1_PINNED["wrfbdy_d01"]

    b1_before = {name: sha256(B1_SOURCE / name) for name in base_hashes}
    assert b1_before == base_hashes
    assert sha256(OLD_EXE) == OLD_PINNED["wrf.exe"]
    old_input_before = sha256(ORIGINAL_RUN / "wrfinput_d01")
    assert old_input_before == OLD_PINNED["wrfinput_d01"]
    for name, expected in B1_PINNED.items():
        assert base_hashes[name] == expected
    assert OLD_PINNED["wrfbdy_d01"] == B1_PINNED["wrfbdy_d01"]

    old_inventory = {}
    for line in OLD_INPUT_MANIFEST.read_text().splitlines():
        expected, name = line.split(None, 1)
        old_inventory[name.removeprefix("./")] = expected
    assert len(old_inventory) == 89 and old_inventory["wrfinput_d01"] == OLD_PINNED["wrfinput_d01"]
    assert old_inventory["wrfbdy_d01"] == B1_PINNED["wrfbdy_d01"]
    assert old_inventory["namelist.input"] == base_hashes["namelist.input"]
    original_source_before = {name: sha256(ORIGINAL_RUN / name) for name in old_inventory}
    assert original_source_before == old_inventory
    old_common = set(old_inventory) & set(base_hashes)
    assert old_common == set(old_inventory) - {"namelist.output"}
    old_mismatches = [name for name in old_common if old_inventory[name] != base_hashes[name]]
    assert old_mismatches == ["wrfinput_d01"], old_mismatches

    old_receipt = json.loads(OLD_RECEIPT.read_text())
    assert old_receipt["ORIGINAL"]["status"] == "COMPLETE"
    assert len(old_receipt["ORIGINAL"]["histories"]) == 7
    b1_receipt = json.loads((B1_RUNTIME_EVIDENCE / "normalized_receipt.json").read_text())
    assert b1_receipt["status"] == "SUCCESS" and len(b1_receipt["histories"]) == 7
    old_control_history_hashes = {
        item["path"].rsplit("/", 1)[-1]: item["sha256"] for item in old_receipt["ORIGINAL"]["histories"]
    }
    b1_control_history_hashes = b1_receipt["output_sha256"]
    assert set(old_control_history_hashes) == set(HOURS)
    assert set(b1_control_history_hashes) == set(HOURS)
    assert all(sha256(ORIGINAL_RUN / name) == digest for name, digest in old_control_history_hashes.items())
    assert all(sha256(B1_SOURCE / name) == digest for name, digest in b1_control_history_hashes.items())
    source_evidence = [
        B1_SOURCE / "inputs.json", B1_SOURCE / "receipt.json",
        B1_RUNTIME_EVIDENCE / "preflight.json", B1_RUNTIME_EVIDENCE / "normalized_receipt.json",
        *(B1_SOURCE / name for name in HOURS),
        ORIGINAL_RUN / "wrfinput_d01", *(ORIGINAL_RUN / name for name in HOURS),
        OLD_EXE, OLD_RECEIPT, OLD_INPUT_MANIFEST, PRIOR_FAILED_ATTEMPT,
    ]
    source_evidence_before = {str(path): sha256(path) for path in source_evidence}
    baseline_output_bytes = sum((B1_SOURCE / name).stat().st_size for name in HOURS)
    required_free = len(ALPHAS) * 2 * baseline_output_bytes + MIN_RESERVE
    free_before = shutil.disk_usage(SCRATCH_ROOT).free
    assert free_before >= required_free, {
        "free_bytes": free_before, "required_for_outputs_plus_reserve": required_free,
        "expected_output_bytes_each": baseline_output_bytes, "minimum_reserve_bytes": MIN_RESERVE,
    }
    selection_plan_sha = sha256(SELECTION_PLAN)
    assert selection_plan_sha == "36e094ac84d698351cdc477ec0bb58fd7580e0676e9ed830236a7d52b0818642"
    selection = json.loads(SELECTION_PLAN.read_text())
    assert selection["status"] == "FROZEN_BEFORE_EXTENSION_FORECAST_OUTPUTS"
    assert selection["experiment"]["new_cases"] == 8
    assert selection["experiment"]["families"] == ["CONTROL", "IMPROVED"]
    assert selection["experiment"]["snow_factors"] == [1.75, 2.0, 2.5, 3.0]
    launch_scripts = json.loads((EVIDENCE / "launch_scripts.sha256.json").read_text())
    assert all(sha256(EVIDENCE / name) == digest for name, digest in launch_scripts.items())

    b1_metadata, b1_value_hashes, b1_qsnow, field_count, dim_count = native_contract(B1_SOURCE / "wrfinput_d01")
    original_metadata, original_value_hashes, original_qsnow, old_field_count, old_dim_count = native_contract(ORIGINAL_RUN / "wrfinput_d01")
    assert field_count == old_field_count == 208 and dim_count == old_dim_count == 16
    with netCDF4.Dataset(B1_SOURCE / "wrfinput_d01") as b1, netCDF4.Dataset(ORIGINAL_RUN / "wrfinput_d01") as original:
        cross_family_metadata_equal = compare_metadata(b1, original)
    metadata_payload = {"B1": b1_metadata, "ORIGINAL": original_metadata}
    metadata_sha = hashlib.sha256(json.dumps(metadata_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    cases = {}
    case_qsnow_audits = {}
    case_field_hashes = {}
    for group in ("CONTROL", "IMPROVED"):
        source_qsnow = original_qsnow if group == "CONTROL" else b1_qsnow
        source_qhashes = original_value_hashes if group == "CONTROL" else b1_value_hashes
        for alpha_code, alpha in ALPHAS:
            case = case_id(group, alpha_code)
            case_dir = SCRATCH_ROOT / case
            case_dir.mkdir()
            for name in base_hashes:
                subprocess.run(["cp", "--reflink=auto", "--", str(B1_SOURCE / name), str(case_dir / name)], check=True)
            if group == "CONTROL":
                subprocess.run(["cp", "--reflink=auto", "--", str(OLD_EXE), str(case_dir / "wrf.exe")], check=True)
                subprocess.run(["cp", "--reflink=auto", "--", str(ORIGINAL_RUN / "wrfinput_d01"), str(case_dir / "wrfinput_d01")], check=True)
            assert len(list(case_dir.iterdir())) == 89
            assert all((case_dir / name).stat().st_nlink == 1 for name in base_hashes)
            assert all((case_dir / name).stat().st_ino != (B1_SOURCE / name).stat().st_ino for name in base_hashes)

            scaled64 = source_qsnow.astype(np.float64) * np.float64(alpha)
            scaled32 = scaled64.astype(np.float32)
            assert np.isfinite(scaled32).all() and (scaled32 >= 0).all()
            with netCDF4.Dataset(case_dir / "wrfinput_d01", "r+") as target:
                target.variables["QSNOW"][:] = scaled32

            expected_exe = OLD_PINNED["wrf.exe"] if group == "CONTROL" else B1_PINNED["wrf.exe"]
            expected_init = OLD_PINNED["wrfinput_d01"] if group == "CONTROL" else B1_PINNED["wrfinput_d01"]
            staged_hashes = {name: sha256(case_dir / name) for name in base_hashes}
            assert staged_hashes["wrf.exe"] == expected_exe
            assert staged_hashes["wrfbdy_d01"] == B1_PINNED["wrfbdy_d01"]
            assert staged_hashes["namelist.input"] == base_hashes["namelist.input"]
            assert staged_hashes["wrfinput_d01"] != expected_init
            assert all(staged_hashes[n] == base_hashes[n] for n in base_hashes if n not in ("wrf.exe", "wrfinput_d01"))

            with netCDF4.Dataset(B1_SOURCE / "wrfinput_d01") as b1, netCDF4.Dataset(ORIGINAL_RUN / "wrfinput_d01") as original:
                source_dataset = original if group == "CONTROL" else b1
                with netCDF4.Dataset(case_dir / "wrfinput_d01") as target:
                    assert compare_metadata(source_dataset, target), f"{case}: NetCDF metadata changed"
                    assert len(target.variables) == 208
                    changed_names, other_count, hashes = [], 0, {}
                    for name in source_dataset.variables:
                        source_values = source_dataset.variables[name][:]
                        target_values = target.variables[name][:]
                        hashes[name] = field_value_sha256(target.variables[name])
                        if name == "QSNOW":
                            assert robust_equal(target_values, scaled32)
                            changed_names.append(name)
                            continue
                        assert robust_equal(source_values, target_values), f"{case}: {name} changed"
                        assert hashes[name] == source_qhashes[name], f"{case}: {name} stored value hash changed"
                        other_count += 1
                    assert other_count == 207 and changed_names == ["QSNOW"]

            delta = scaled32.astype(np.float64) - source_qsnow.astype(np.float64)
            audit = {
                "group": group,
                "alpha": alpha,
                "source_input_sha256": expected_init,
                "source_qsnow_value_sha256": source_qhashes["QSNOW"],
                "scaled_qsnow_value_sha256": hashes["QSNOW"],
                "scaling_rule": "float64(source QSNOW) * float64(alpha), then cast to native float32",
                "dtype": "float32",
                "shape": list(scaled32.shape),
                "source_min": float(np.min(source_qsnow)),
                "source_max": float(np.max(source_qsnow)),
                "source_mean": float(np.mean(source_qsnow, dtype=np.float64)),
                "source_nonzero_count": int(np.count_nonzero(source_qsnow)),
                "output_min": float(np.min(scaled32)),
                "output_max": float(np.max(scaled32)),
                "output_mean": float(np.mean(scaled32, dtype=np.float64)),
                "output_nonzero_count": int(np.count_nonzero(scaled32)),
                "changed_value_count": int(np.count_nonzero(scaled32 != source_qsnow)),
                "total_value_count": int(scaled32.size),
                "min_difference": float(np.min(delta)),
                "max_difference": float(np.max(delta)),
                "finite": bool(np.isfinite(scaled32).all()),
                "nonnegative": bool((scaled32 >= 0).all()),
                "variable_count": 208,
                "other_variables_unchanged": other_count == 207,
                "all_native_metadata_unchanged": True,
                "native_metadata_contract_sha256": metadata_sha,
            }
            cases[case] = {
                "case": case,
                "group": group,
                "display_label": "규준 실험 (ORIGINAL)" if group == "CONTROL" else "기존 개선안 (IMPROVED_BG_FIXED)",
                "alpha": alpha,
                "scratch_directory": str(case_dir),
                "slot": None,
                "cpu_set": None,
                "staged_sha256": staged_hashes,
                "qsnow_audit": audit,
            }
            case_qsnow_audits[case] = audit
            case_field_hashes[case] = hashes

    slot_map = {}
    for slot, case_names in SLOT_CASES.items():
        for case in case_names:
            assert case in cases and case not in slot_map
            slot_map[case] = slot
            cases[case]["slot"] = slot
            cases[case]["cpu_set"] = cpu_slots[slot]
    assert set(slot_map) == set(cases) and len(cases) == 8

    b1_after = {name: sha256(B1_SOURCE / name) for name in base_hashes}
    original_source_after = {name: sha256(ORIGINAL_RUN / name) for name in original_source_before}
    source_evidence_after = {str(path): sha256(path) for path in source_evidence}
    assert b1_after == b1_before and original_source_after == original_source_before
    assert source_evidence_before == source_evidence_after
    free_after = shutil.disk_usage(SCRATCH_ROOT).free
    assert free_after >= MIN_RESERVE
    plan = {
        "status": "PASS_READY_TO_LAUNCH",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "selection_plan_sha256": selection_plan_sha,
        "prior_attempt_receipt_path": str(PRIOR_FAILED_ATTEMPT),
        "prior_attempt_receipt_sha256": source_evidence_before[str(PRIOR_FAILED_ATTEMPT)],
        "launch_scripts_sha256": launch_scripts,
        "scope": "diagnostic native QSNOW extension; factors above 1.5; no balance correction; not production",
        "scratch_root": str(SCRATCH_ROOT),
        "case_count": len(cases),
        "alphas": dict(ALPHAS),
        "expected_histories": HOURS,
        "declared_input_count_per_case": 89,
        "original_native_variable_count": 208,
        "all_native_metadata_unchanged": True,
        "cross_family_native_metadata_equal": cross_family_metadata_equal,
        "native_metadata_contract_sha256": metadata_sha,
        "fixed_executable_sha256": B1_PINNED["wrf.exe"],
        "original_executable_sha256": OLD_PINNED["wrf.exe"],
        "improved_wrfinput_sha256": B1_PINNED["wrfinput_d01"],
        "original_wrfinput_sha256": OLD_PINNED["wrfinput_d01"],
        "common_boundary_sha256": B1_PINNED["wrfbdy_d01"],
        "common_six_hour_namelist_sha256": base_hashes["namelist.input"],
        "original_vs_improved_baseline_input_differences": ["wrf.exe", "wrfinput_d01"],
        "original_alpha_one_control_reused": {"receipt": str(OLD_RECEIPT), "status": old_receipt["ORIGINAL"]["status"]},
        "improved_alpha_one_control_reused": {"receipt": str(B1_RUNTIME_EVIDENCE / "receipt.json"), "status": "SUCCESS"},
        "original_alpha_one_history_sha256": old_control_history_hashes,
        "improved_alpha_one_history_sha256": b1_control_history_hashes,
        "mpi_ranks_per_case": 8,
        "omp_threads_per_rank": 1,
        "max_concurrent_cases": 8,
        "cpu_affinity": {"method": "taskset per slot and Intel MPI pin list; disjoint 8-CPU sets", "allowed_cpus": allowed_cpus, "slots": cpu_slots, "slot_cases": SLOT_CASES},
        "source_b1_input_sha256_before": b1_before,
        "source_b1_input_sha256_after": b1_after,
        "original_source_wrfinput_sha256_before": old_input_before,
        "original_source_wrfinput_sha256_after": original_source_after["wrfinput_d01"],
        "original_source_sha256_before": original_source_before,
        "original_source_sha256_after": original_source_after,
        "original_historical_full_inventory_timing": old_receipt["ORIGINAL"]["full_input_inventory_timing"],
        "source_evidence_sha256_before": source_evidence_before,
        "source_evidence_sha256_after": source_evidence_after,
        "case_records": cases,
        "case_field_value_sha256": case_field_hashes,
        "source_field_value_sha256": {"CONTROL": original_value_hashes, "IMPROVED": b1_value_hashes},
        "field_metadata_contract": metadata_payload,
        "field_count": field_count,
        "dimension_count": dim_count,
        "free_bytes_before_stage": free_before,
        "free_bytes_after_stage": free_after,
        "expected_outputs_bytes_per_case": baseline_output_bytes,
        "minimum_free_reserve_bytes": MIN_RESERVE,
    }
    (EVIDENCE / "common_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    (EVIDENCE / "qsnow_audit.json").write_text(json.dumps(case_qsnow_audits, indent=2, sort_keys=True) + "\n")
    (EVIDENCE / "field_metadata_contract.json").write_text(json.dumps(metadata_payload, indent=2, sort_keys=True) + "\n")
    (EVIDENCE / "field_value_source_sha256.json").write_text(json.dumps({"CONTROL": original_value_hashes, "IMPROVED": b1_value_hashes}, indent=2, sort_keys=True) + "\n")
    (EVIDENCE / "field_value_case_sha256.json").write_text(json.dumps(case_field_hashes, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "status": plan["status"], "case_count": len(cases),
        "case_ids": list(cases), "free_bytes_before_stage": free_before,
        "free_bytes_after_stage": free_after, "reserve_bytes": MIN_RESERVE,
        "boundary_sha256": B1_PINNED["wrfbdy_d01"],
        "namelist_sha256": base_hashes["namelist.input"],
        "native_metadata_contract_sha256": metadata_sha,
    }, indent=2))


if __name__ == "__main__":
    main()
