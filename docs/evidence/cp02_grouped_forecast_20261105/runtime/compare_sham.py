#!/usr/bin/env python3
"""Independently verify completed SHAM runs against their historical controls."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np


HISTORY_NAMES = tuple(f"wrfout_d01_2026-08-16_{hour:02d}:00:00" for hour in range(12, 19))
PRECIP_FIELDS = ("RAINC", "RAINNC", "RAINSH")
CORE_FIELDS = ("QVAPOR", "QCLOUD", "QRAIN", "QNRAIN", "QICE", "QSNOW",
               "QGRAUP", "T", "P", "PB", "MU", "MUB", "PH", "PHB", "RAINC", "RAINNC", "RAINSH")
OLD_EXE_SHA256 = "68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f"
OLD_TARGET_OBJECT_SHA256 = "632f8562fc87e5c4dd124966c99d951090022bbd3cd241a3c833010c81553ba1"


def sha256(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def source_hashes(arm: str, root: Path) -> dict[str, str]:
    if arm == "A":
        receipt = load(root / "docs/evidence/six_hour_improvement_20261030/runtime/inputs.json")
        return receipt["staged"]
    receipt = load(root / "docs/evidence/cp02_rain_number_process_20261104/followup/runtime/launch_receipt.json")
    return receipt["inputs_after"]


def history_baseline(arm: str, root: Path) -> dict[str, dict]:
    if arm == "A":
        receipt = load(root / "docs/evidence/six_hour_improvement_20261030/runtime/history_validation.json")
        return {row["name"]: {"sha256": row["sha256"], "valid_time": row["time"]}
                for row in receipt["histories"]}
    receipt = load(root / "docs/evidence/cp02_rain_number_process_20261104/followup/runtime/runtime_gate.json")
    return {name: {"sha256": row["sha256"], "valid_time": row["time"]}
            for name, row in receipt["history"].items()}


def check_history(path: Path, expected_time: str) -> dict:
    require(path.is_file(), f"missing history {path.name}")
    with netCDF4.Dataset(path) as dataset:
        dataset.set_auto_maskandscale(False)
        require("Times" in dataset.variables, f"{path.name}: missing Times")
        raw_time = np.asarray(dataset.variables["Times"][:]).tobytes().decode("ascii").rstrip("\0")
        require(raw_time == expected_time, f"{path.name}: valid time mismatch")
        for field in CORE_FIELDS:
            require(field in dataset.variables, f"{path.name}: missing {field}")
            require(np.isfinite(np.asarray(dataset.variables[field][:])).all(),
                    f"{path.name}: nonfinite {field}")
        precip = [field for field in PRECIP_FIELDS if field in dataset.variables]
        require(precip == list(PRECIP_FIELDS), f"{path.name}: precipitation field set differs")
    return {"name": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size,
            "valid_time": expected_time, "precip_fields": list(PRECIP_FIELDS)}


def verify_run(arm: str, folder: Path, root: Path) -> tuple[dict, dict]:
    case = f"SHAM_{arm}"
    run_path = folder / "run_receipt.json"
    prepared_path = folder / "prepared.json"
    require(run_path.is_file() and prepared_path.is_file(), f"{case}: run is not complete")
    run = load(run_path)
    prepared = load(prepared_path)
    require(run.get("schema") == "cp02_grouped_six_hour_run_v1", f"{case}: wrong run schema")
    require(run.get("status") == "PASS" and run.get("exit_code") == 0 and run.get("failure") is None,
            f"{case}: run receipt is not PASS")
    require(run.get("case") == case and run.get("initialization") == arm,
            f"{case}: case/initialization mismatch")
    expected_cpus = list(range(0, 8)) if arm == "A" else list(range(8, 16))
    require(run.get("cpus") == expected_cpus, f"{case}: CPU placement differs from frozen SHAM plan")
    try:
        started = datetime.fromisoformat(run["start_utc"])
        finished = datetime.fromisoformat(run["end_utc"])
        elapsed = float(run["elapsed_seconds"])
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError(f"{case}: invalid run timing fields") from error
    require(started.tzinfo is not None and finished.tzinfo is not None
            and finished > started and elapsed > 0, f"{case}: run timing bounds are invalid")
    require(prepared.get("case") == case and prepared.get("variant") == "OLD_SHAM",
            f"{case}: prepared input is not OLD_SHAM")
    require(prepared.get("initial_time_utc") == "2026-08-16T12:00:00Z"
            and prepared.get("end_time_utc") == "2026-08-16T18:00:00Z",
            f"{case}: six-hour valid-time bounds differ")
    runtime_dir = Path(root) / "docs/evidence/cp02_grouped_forecast_20261105/runtime"
    require(prepared.get("runner_sha256") == sha256(runtime_dir / "forecast.py")
            and run.get("runner_sha256") == prepared.get("runner_sha256"),
            f"{case}: frozen forecast runner identity changed")
    require(prepared.get("wrapper_sha256") == sha256(runtime_dir / "rank_wrapper.sh"),
            f"{case}: frozen MPI rank wrapper identity changed")
    expected_inputs = source_hashes(arm, root)
    require(len(expected_inputs) == 89 and expected_inputs.get("wrf.exe") == OLD_EXE_SHA256,
            f"{case}: historical 89-input identity is invalid")
    require(prepared.get("source_hashes") == expected_inputs,
            f"{case}: staged source inputs differ from historical control")
    staged = prepared.get("inputs", {})
    require(set(staged) == set(expected_inputs)
            and all(staged[name] == digest for name, digest in expected_inputs.items() if name != "wrf.exe"),
            f"{case}: staged non-executable input identity differs from historical control")
    require(prepared.get("build_receipt_sha256") == sha256(Path(prepared["build_receipt"])),
            f"{case}: build receipt identity changed")
    build = load(Path(prepared["build_receipt"]))
    require(build.get("status") == "PASS" and build.get("variant") == "OLD_SHAM",
            f"{case}: native build receipt is not passing OLD_SHAM")
    require(build.get("inputs_unchanged") is True and build.get("compile", {}).get("exit_code") == 0
            and build.get("link", {}).get("exit_code") == 0, f"{case}: build audit/compile/link did not pass")
    require(build.get("source", {}).get("sha256") == "d8c11bd9b3dd0fd717c14899c53ffe7ca37c4d768128c4dac750429f7fb4bf3a",
            f"{case}: OLD_SHAM target source differs from pinned original source")
    require(build.get("object", {}).get("sha256") == OLD_TARGET_OBJECT_SHA256
            and build.get("archive_member_sha256") == OLD_TARGET_OBJECT_SHA256,
            f"{case}: rebuilt target object differs from pinned original object")
    exe_hash = build.get("executable", {}).get("sha256")
    require(exe_hash and staged.get("wrf.exe") == exe_hash and run.get("inputs_after") == staged,
            f"{case}: private executable differs from passing OLD_SHAM build or changed during run")
    require(run.get("histories") and len(run["histories"]) == 7,
            f"{case}: run receipt lacks seven histories")
    baseline = history_baseline(arm, root)
    require(set(baseline) == set(HISTORY_NAMES), f"{case}: historical control lacks seven histories")
    disk_names = {path.name for path in folder.glob("wrfout*")}
    require(disk_names == set(HISTORY_NAMES), f"{case}: expected exactly seven history files")
    checked = []
    for name in HISTORY_NAMES:
        expected = baseline[name]
        observed = check_history(folder / name, expected["valid_time"])
        require(observed["sha256"] == expected["sha256"],
                f"{case}: {name} bytes differ from historical control")
        checked.append(observed)
    run_rows = {row["path"].split("/")[-1]: row for row in run["histories"]}
    require(set(run_rows) == set(HISTORY_NAMES), f"{case}: run receipt history names differ")
    for observed in checked:
        row = run_rows[observed["name"]]
        require(row.get("sha256") == observed["sha256"] and row.get("size_bytes") == observed["size_bytes"]
                and row.get("valid_utc", "").replace("T", "_").removesuffix("Z") == observed["valid_time"],
                f"{case}: run receipt does not bind {observed['name']}")
    return {"path": str(run_path), "sha256": sha256(run_path), "size_bytes": run_path.stat().st_size}, {
        "case": case, "run_receipt": str(run_path), "run_receipt_sha256": sha256(run_path),
        "prepared_sha256": sha256(prepared_path), "build_receipt": str(prepared["build_receipt"]),
        "build_receipt_sha256": prepared["build_receipt_sha256"], "input_count": len(expected_inputs),
        "historical_executable_sha256": OLD_EXE_SHA256, "private_executable_sha256": exe_hash,
        "target_object_sha256": OLD_TARGET_OBJECT_SHA256, "histories": checked,
    }


def compare(root: Path, run_root: Path, output: Path) -> dict:
    output = Path(output)
    require(not output.exists(), f"refusing to overwrite {output}")
    receipts, details = {}, {}
    for arm in ("A", "B"):
        receipts[arm], details[arm] = verify_run(arm, Path(run_root) / f"SHAM_{arm}", Path(root))
    run_a = load(Path(details["A"]["run_receipt"]))
    run_b = load(Path(details["B"]["run_receipt"]))
    prep_a = load(Path(run_root) / "SHAM_A/prepared.json")
    prep_b = load(Path(run_root) / "SHAM_B/prepared.json")
    inputs_a, inputs_b = prep_a["inputs"], prep_b["inputs"]
    require(set(inputs_a) == set(inputs_b), "A/B staged input names differ")
    require(inputs_a.get("wrf.exe") == inputs_b.get("wrf.exe")
            and prep_a.get("build_receipt_sha256") == prep_b.get("build_receipt_sha256"),
            "A/B rebuilt OLD_SHAM executable/build differs")
    require(all(inputs_a[name] == inputs_b[name] for name in inputs_a if name != "wrfinput_d01"),
            "A/B inputs other than the arm-specific initial state differ")
    require(run_a["initial_time_utc"] == run_b["initial_time_utc"]
            and run_a["end_time_utc"] == run_b["end_time_utc"], "A/B initialization bounds differ")
    require([row["valid_time"] for row in details["A"]["histories"]]
            == [row["valid_time"] for row in details["B"]["histories"]], "A/B history times differ")
    require([row["precip_fields"] for row in details["A"]["histories"]]
            == [row["precip_fields"] for row in details["B"]["histories"]], "A/B precipitation fields differ")
    require(prep_a["inputs"]["namelist.input"] == prep_b["inputs"]["namelist.input"],
            "A/B hourly-increment namelist differs")
    plan = load(Path(root) / "docs/evidence/cp02_grouped_forecast_20261105/evaluation_plan.json")
    oldsum_receipts = {}
    for arm, source_ref in (("A", "B1_oldsum_cache_receipt"), ("B", "DM065_oldsum_cache_receipt")):
        expected = plan["source_refs"][source_ref]
        path = Path(root) / expected["path"]
        identity = {"path": str(path), "sha256": sha256(path), "size_bytes": path.stat().st_size}
        require(identity["sha256"] == expected["sha256"] and identity["size_bytes"] == expected["size_bytes"],
                f"frozen {arm} oldsum cache receipt changed")
        oldsum_receipts[arm] = identity
    result = {
        "schema": "grouped_forecast_oldsum_comparability_v1", "status": "PASS",
        "oldsum_receipts": oldsum_receipts,
        "checks": {"same_initialization": True, "same_valid_time_bounds": True,
                   "same_precip_fields": True, "same_RN1_mapping": True,
                   "same_hourly_increment_definition": True},
        "verification": {"scope": "Each OLD_SHAM run independently matches its own historical 89-input control and all seven complete history files byte-for-byte.",
                         "run_details": details,
                         "shared_interpretation": "A and B retain distinct historical wrfinput_d01 fields; same_initialization means both use the same 12Z initialization time and 18Z end time, not byte-identical initial states.",
                         "RN1_mapping_basis": "The rebuilt OLD_SHAM target object and archive member are byte-identical to the pinned original object; all staged inputs other than the arm-specific wrfinput_d01 and rebuilt executable are byte-identical.",
                         "hourly_increment_basis": "Both arms use byte-identical namelist.input and the same seven hourly valid times."}
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="repository root")
    parser.add_argument("--run-root", type=Path, required=True, help="private runtime/forecasts directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.root, args.run_root, args.output)
    print(result["status"])


if __name__ == "__main__":
    main()
