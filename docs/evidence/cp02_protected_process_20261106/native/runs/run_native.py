#!/usr/bin/env python3
"""Prepare, launch, and gate protected-process OLD/FIX native runs."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import time
import shutil
from typing import Any
import netCDF4
import numpy as np

CLOUD_BAL = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_protected_process_20261106/Cloud-BAL")
EVIDENCE = CLOUD_BAL / "docs/evidence/cp02_protected_process_20261106/native"
WORK = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_protected_process_20261106/runtime/native")
COHORT = CLOUD_BAL / "docs/evidence/cp02_protected_process_20261106/cohorts/unique_global_corners.csv"
SOURCE_RECEIPT = EVIDENCE / "source/source_generation_receipt.json"
QUICK_PLAN = EVIDENCE / "plans/quick_gate_plan.json"
RUNNER_WRAPPER = EVIDENCE / "runs/run_native.sh"
BUILD_RECEIPT = WORK / "build/build_receipt.json"
EXECUTED_BUILD_SCRIPT = EVIDENCE / "build/build_pair.py"
COMPILE_REVIEW = CLOUD_BAL / "docs/evidence/cp02_protected_process_20261106/review/final_compile_provenance_review.json"
STAGE = Path("/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED")
STAGE_RECEIPT = STAGE / "receipt.json"
OLD_REF = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100")
FIX_REF = STAGE
REFS = {"OLD": OLD_REF, "FIX": FIX_REF}
CPUS = {"OLD": list(range(32, 40)), "FIX": list(range(40, 48))}
MPI = "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun"
MPI_ENV = "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh"
CHUNK_LIMIT = 90 * 1024 * 1024
DIAGNOSTIC_LIMIT = 32 * 1024**3


def sha(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def require_gates(plan_path: Path, review_path: Path | None) -> tuple[dict, dict, dict | None]:
    if Path(__file__).resolve().parent != EVIDENCE / "runs":
        raise ValueError("run the reviewed runner from its evidence location")
    if WORK == CLOUD_BAL or CLOUD_BAL in WORK.parents or not str(WORK).endswith("/runtime/native"):
        raise ValueError("runs, TMPDIR, and diagnostics must remain under external runtime/native scratch")
    stack_limits = resource.getrlimit(resource.RLIMIT_STACK)
    if stack_limits[0] != resource.RLIM_INFINITY:
        raise ValueError(f"stack soft limit must be unlimited, got {stack_limits}")
    expected_netcdf = "/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel"
    if os.environ.get("NETCDF") != expected_netcdf or not os.environ.get("LD_LIBRARY_PATH", "").startswith(expected_netcdf + "/lib:"):
        raise ValueError("runtime environment does not match the pinned NetCDF profile")
    quick_plan = json.loads(plan_path.read_text())
    plan_sha = sha(plan_path)
    launch_review = json.loads(review_path.read_text()) if review_path else None
    if launch_review is not None:
        if launch_review.get("status") != "GO_FOR_ONE_STEP_CAPTURE":
            raise ValueError("independent one-step prelaunch review is not GO")
        if launch_review.get("plan_sha256") != plan_sha:
            raise ValueError("prelaunch review does not bind this plan")
        if launch_review.get("runner_sha256") != sha(Path(__file__)):
            raise ValueError("prelaunch review does not bind this runner")
        if launch_review.get("wrapper_sha256") != sha(RUNNER_WRAPPER):
            raise ValueError("prelaunch review does not bind this launch wrapper")
    if quick_plan.get("status") != "FROZEN_QUICK_GATE_PLAN":
        raise ValueError("quick-gate plan is not frozen")
    if sha(CLOUD_BAL / "tests/intel_toolchain.sh") != quick_plan["pins"]["toolchain_profile_sha256"]:
        raise ValueError("pinned Intel toolchain profile changed")
    if sha(Path(MPI_ENV)) != quick_plan["pins"]["mpi_environment_sha256"]:
        raise ValueError("pinned MPI environment script changed")
    if sha(Path(MPI)) != quick_plan["pins"]["mpi_launcher_sha256"]:
        raise ValueError("pinned MPI launcher changed")
    if sha(EXECUTED_BUILD_SCRIPT) != quick_plan["pins"]["build_script_executed_sha256"]:
        raise ValueError("executed build helper differs from sealed provenance")
    if sha(COMPILE_REVIEW) != quick_plan["pins"]["compile_review_sha256"]:
        raise ValueError("independent compile review differs from sealed plan")
    compile_review = json.loads(COMPILE_REVIEW.read_text())
    if compile_review.get("status") != "PASS_COMPILE_PROVENANCE_WITH_WARNING":
        raise ValueError("independent compile provenance review is not PASS")
    generation = json.loads(SOURCE_RECEIPT.read_text())
    if sha(SOURCE_RECEIPT) != quick_plan["pins"]["source_generation_receipt_sha256"]:
        raise ValueError("source-generation receipt differs from frozen quick plan")
    if generation["generator_sha256"] != quick_plan["pins"]["generator_sha256"]:
        raise ValueError("source generator differs from frozen quick plan")
    if sha(EVIDENCE / "plans/capture_plan.md") != generation["plan_sha256"]:
        raise ValueError("frozen capture plan changed")
    if generation["plan_sha256"] != quick_plan["pins"]["capture_plan_sha256"]:
        raise ValueError("capture plan differs from frozen quick plan")
    if sha(EVIDENCE / "plans/plan_freeze.json") != quick_plan["pins"]["plan_freeze_sha256"]:
        raise ValueError("plan freeze receipt differs from frozen quick plan")
    if sha(EVIDENCE / "schema/cp05_schema.json") != generation["schema_sha256"]:
        raise ValueError("process schema changed")
    if generation["schema_sha256"] != quick_plan["pins"]["schema_sha256"]:
        raise ValueError("process schema differs from frozen quick plan")
    cohort_receipt = CLOUD_BAL / "docs/evidence/cp02_protected_process_20261106/cohorts/receipt.json"
    if sha(cohort_receipt) != generation["cohort_receipt_sha256"]:
        raise ValueError("frozen cohort receipt changed")
    if not BUILD_RECEIPT.is_file():
        raise ValueError("paired IFX build receipt missing")
    build = json.loads(BUILD_RECEIPT.read_text())
    if build.get("status") != "PASS":
        raise ValueError("paired IFX build is not PASS")
    if build.get("source_generation_receipt_sha256") != quick_plan["pins"]["source_generation_receipt_sha256"]:
        raise ValueError("build was made from a different source-generation receipt")
    if build.get("build_script_sha256") != quick_plan["pins"]["build_script_executed_sha256"]:
        raise ValueError("build receipt is not bound to the executed safe build helper")
    if compile_review.get("build_receipt_sha256") != sha(BUILD_RECEIPT):
        raise ValueError("independent compile review does not bind the paired build receipt")
    if sha(BUILD_RECEIPT) != quick_plan["pins"]["build_receipt_sha256"]:
        raise ValueError("paired build receipt differs from sealed quick plan")
    if sha(COHORT) != quick_plan["cohort"]["selector_sha256"]:
        raise ValueError("selected-column selector differs from quick plan")
    if sha(cohort_receipt) != quick_plan["cohort"]["receipt_sha256"]:
        raise ValueError("cohort receipt differs from frozen quick plan")
    if sha(STAGE_RECEIPT) != quick_plan["pins"]["stage_receipt_sha256"]:
        raise ValueError("B1 stage receipt differs from quick plan")
    if build.get("link_inputs_before") != build.get("link_inputs_after"):
        raise ValueError("pinned host link inputs changed during build")
    if build.get("profile", {}).get("profile_sha256") != quick_plan["pins"]["toolchain_profile_sha256"]:
        raise ValueError("paired build did not use the pinned Intel profile")
    for arm in ("OLD", "FIX"):
        source_sha = next(row["sha256"] for row in generation["arms"] if row["arm"] == arm)
        if build["arms"][arm]["source_sha256"] != source_sha:
            raise ValueError(f"{arm} executable was not built from reviewed source")
        if build["arms"][arm]["object_sha256"] != build["arms"][arm]["archive_member_sha256"]:
            raise ValueError(f"{arm} linked archive member differs from compiled object")
    return build, quick_plan, launch_review


def history_path(root: Path, hour: int) -> Path:
    return root / f"wrfout_d01_2026-08-16_{hour:02d}:00:00"


def value_signature(value: Any) -> tuple:
    arr = np.asarray(value)
    if arr.dtype.kind in "biufc":
        native = arr.astype(arr.dtype.newbyteorder("="), copy=False)
        return ("numeric", arr.dtype.str, arr.shape, native.tobytes(order="C"))
    if arr.dtype.kind == "O":
        return ("object", arr.shape, tuple((type(x).__name__, repr(x)) for x in arr.flat))
    return ("other", arr.dtype.str, arr.shape, arr.tobytes())


def canonical_array(variable) -> tuple:
    arr = np.ma.asarray(variable[:])
    return (value_signature(np.asarray(arr.data)), np.ma.getmaskarray(arr).tobytes())


def compare_history(actual: Path, reference: Path) -> dict:
    if not actual.is_file() or not reference.is_file():
        raise FileNotFoundError(f"history file missing: {actual} or {reference}")
    with netCDF4.Dataset(actual) as a, netCDF4.Dataset(reference) as b:
        if list(a.dimensions) != list(b.dimensions):
            raise ValueError("history dimension inventory differs")
        for name in a.dimensions:
            da, db = a.dimensions[name], b.dimensions[name]
            if (len(da), da.isunlimited()) != (len(db), db.isunlimited()):
                raise ValueError(f"history dimension differs: {name}")
        if list(a.variables) != list(b.variables):
            raise ValueError("history variable inventory differs")
        for name in a.variables:
            va, vb = a.variables[name], b.variables[name]
            if (va.dimensions, va.dtype.str, set(va.ncattrs())) != (vb.dimensions, vb.dtype.str, set(vb.ncattrs())):
                raise ValueError(f"history variable metadata differs: {name}")
            if canonical_array(va) != canonical_array(vb):
                raise ValueError(f"history variable bytes differ: {name}")
            for attr in va.ncattrs():
                if value_signature(va.getncattr(attr)) != value_signature(vb.getncattr(attr)):
                    raise ValueError(f"history variable attribute differs: {name}/{attr}")
        if set(a.ncattrs()) != set(b.ncattrs()):
            raise ValueError("history global attribute inventory differs")
        for attr in a.ncattrs():
            if value_signature(a.getncattr(attr)) != value_signature(b.getncattr(attr)):
                raise ValueError(f"history global attribute differs: {attr}")
    return {"actual": str(actual), "reference": str(reference), "actual_sha256": sha(actual),
            "reference_sha256": sha(reference), "all_variables_coordinates_attributes_exact": True}


def prepare_case(stage: str, arm: str, duration: int) -> Path:
    if sha(STAGE_RECEIPT) != "00eddd6ac26a3a4857ea40e294256d2b32c9c9e6a2998f112000c39d5281bf5e":
        raise ValueError("B1 stage receipt pin changed")
    stage_receipt = json.loads(STAGE_RECEIPT.read_text())
    staged = stage_receipt["staged_sha256_after"]
    if len(staged) != 89 or staged["wrfinput_d01"] != "9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5" or staged["wrfbdy_d01"] != "74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45":
        raise ValueError("B1 inputs do not match frozen initial and boundary fields")
    case = WORK / "cases" / stage / arm
    case.parent.mkdir(parents=True, exist_ok=True)
    case.mkdir(exist_ok=False)
    for name, expected in staged.items():
        source = WORK / "build" / arm / "wrf.exe" if name == "wrf.exe" else STAGE / name
        if sha(source) != expected and name != "wrf.exe":
            raise ValueError(f"stage input differs before copy: {name}")
        if name == "wrf.exe" and sha(STAGE / name) != expected:
            raise ValueError("historical stage executable differs from its receipt")
        shutil.copy2(source, case / name)
    namelist = case / "namelist.input"
    original = namelist.read_text()
    controls = ([('run_hours', '0'), ('end_hour', '12'), ('history_end_s', '20'),
                 ('run_minutes', '0'), ('run_seconds', '20'), ('end_minute', '0'), ('end_second', '20')]
                if duration == 20 else [('run_hours', str(duration // 3600)),
                                        ('end_hour', str(12 + duration // 3600)),
                                        ('history_end_s', str(duration))])
    updated = original
    for key, value in controls:
        updated, count = re.subn(r'(?m)^(\s*' + re.escape(key) + r'\s*=\s*)[^,\n]+',
                                 lambda match: match.group(1) + value, updated)
        if count != 1:
            raise ValueError(f"expected one namelist control {key}, found {count}")
    if not re.search(r'(?m)^\s*time_step\s*=\s*20\s*,?\s*$', updated):
        raise ValueError("staged timestep is not 20 seconds")
    namelist.write_text(updated)
    receipt = {"stage": stage, "arm": arm, "source_stage": str(STAGE), "source_stage_receipt_sha256": sha(STAGE_RECEIPT),
               "inputs_before": {name: sha(case / name) for name in staged},
               "controls": controls, "namelist_sha256": sha(namelist),
               "executable_sha256": sha(case / "wrf.exe"), "expected_history_hours": list(range(12, 13 + duration // 3600))}
    (case / "case_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return case


def diagnostic_size(case: Path) -> tuple[int, list[Path]]:
    patterns = ("cp04_t*_rank*.bin", "state_selected_*_t*_rank*.bin", "state_entry_rank*.bin",
                "state_pre_update_rank*.bin", "state_post_process_rank*.bin",
                "state_kdm62d_return_rank*.bin", "state_wrapper_return_rank*.bin",
                "surface_cp04_rank*.bin")
    paths = [p for pattern in patterns for p in case.glob(pattern)]
    for path in paths:
        if (path.name.startswith("cp04_t") or path.name.startswith("state_selected_")) and path.stat().st_size > CHUNK_LIMIT:
            raise OverflowError(f"per-chunk output cap exceeded: {path}")
    return sum(p.stat().st_size for p in paths), paths


def run_pair(stage: str, duration: int, plan_path: Path, review_path: Path) -> dict:
    build, quick_plan, launch_review = require_gates(plan_path, review_path)
    cases = {arm: prepare_case(stage, arm, duration) for arm in ("OLD", "FIX")}
    processes = {}
    logs = {}
    envs = {}
    commands = {}
    starts = {}
    for arm, case in cases.items():
        cpus = CPUS[arm]
        tmpdir = case / "tmp"
        tmpdir.mkdir()
        env = os.environ.copy()
        cpu_list = ",".join(str(x) for x in cpus)
        env.update(OMP_NUM_THREADS="1", OMP_DYNAMIC="FALSE", I_MPI_PIN="1",
                   I_MPI_PIN_DOMAIN="core", I_MPI_PIN_RESPECT_CPUSET="1",
                   I_MPI_PIN_PROCESSOR_LIST=cpu_list, TMPDIR=str(tmpdir))
        command = ["taskset", "-c", cpu_list, MPI, "-np", "8", "./wrf.exe"]
        log_path = case / "launcher.log"
        log = log_path.open("xb")
        process = subprocess.Popen(command, cwd=case, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        processes[arm], logs[arm], envs[arm], commands[arm], starts[arm] = process, log, env, command, time.time()
    cap_failures = {}
    while any(process.poll() is None for process in processes.values()):
        for arm, process in processes.items():
            if process.poll() is not None:
                continue
            try:
                size, _ = diagnostic_size(cases[arm])
                if size > DIAGNOSTIC_LIMIT:
                    cap_failures[arm] = "aggregate diagnostic cap exceeded"
                    os.killpg(process.pid, signal.SIGTERM)
            except OverflowError as error:
                cap_failures[arm] = str(error)
                os.killpg(process.pid, signal.SIGTERM)
        time.sleep(2)
    for log in logs.values():
        log.close()
    wanted_hours = list(range(12, 13 + duration // 3600))
    results = {}
    for arm, case in cases.items():
        code = processes[arm].wait()
        outputs = sorted(case.glob("wrfout_d01_2026-08-16_*"))
        expected_names = [history_path(case, h).name for h in wanted_hours]
        actual_names = [p.name for p in outputs]
        logs_text = "".join(p.read_text(errors="replace") for p in case.glob("rsl.out.*"))
        history = {}
        if code == 0 and not cap_failures.get(arm) and actual_names == expected_names:
            for hour in wanted_hours:
                history[f"{hour:02d}"] = compare_history(history_path(case, hour), history_path(REFS[arm], hour))
        before = json.loads((case / "case_receipt.json").read_text())["inputs_before"]
        after = {name: sha(case / name) for name in before}
        history_ok = len(history) == len(wanted_hours)
        raw_status = code == 0 and arm not in cap_failures and history_ok and after == before and "SUCCESS COMPLETE WRF" in logs_text
        result = {"status": ("RAW_PROBE_COMPLETED_AWAITING_CAPTURE_GATE" if stage == "quick" and raw_status else
                             "PASS" if raw_status else "FAIL"),
                  "arm": arm, "stage": stage, "exit_code": code, "argv": commands[arm],
                  "cpu_set": CPUS[arm], "omp_threads": 1, "elapsed_seconds": time.time() - starts[arm],
                  "success_marker": "SUCCESS COMPLETE WRF" in logs_text,
                  "history_files": actual_names, "expected_history_files": expected_names,
                  "history_comparisons": history, "inputs_before": before, "inputs_after": after,
                  "diagnostic_bytes": diagnostic_size(case)[0], "cap_failure": cap_failures.get(arm),
                  "environment": {key: envs[arm].get(key) for key in
                                  ("OMP_NUM_THREADS", "OMP_DYNAMIC", "I_MPI_PIN", "I_MPI_PIN_DOMAIN",
                                   "I_MPI_PIN_RESPECT_CPUSET", "I_MPI_PIN_PROCESSOR_LIST", "TMPDIR",
                                   "PATH", "LD_LIBRARY_PATH", "NETCDF")},
                  "stack_rlimit_bytes": resource.getrlimit(resource.RLIMIT_STACK),
                  "mpi_environment_script": {"path": MPI_ENV, "sha256": sha(Path(MPI_ENV))},
                  "launcher_log_sha256": sha(case / "launcher.log"),
                  "call_manifest_files": sorted(p.name for p in case.glob("state_calls_rank*.txt")),
                  "case_path": str(case)}
        results[arm] = result
        (case / "launch_receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    aggregate_statuses = {v["status"] for v in results.values()}
    aggregate_status = ("RAW_PROBE_COMPLETED_AWAITING_CAPTURE_GATE" if stage == "quick" and
                        aggregate_statuses == {"RAW_PROBE_COMPLETED_AWAITING_CAPTURE_GATE"} else
                        "PASS" if stage == "full" and aggregate_statuses == {"PASS"} else "FAIL")
    aggregate = {"stage": stage, "status": aggregate_status,
                 "duration_seconds": duration, "build_receipt_sha256": sha(BUILD_RECEIPT),
                 "prelaunch_review_sha256": sha(review_path), "quick_plan_sha256": sha(plan_path),
                 "runner_sha256": sha(Path(__file__)), "wrapper_sha256": sha(RUNNER_WRAPPER), "arms": results}
    out = WORK / ("quick_gate.json" if stage == "quick" else "full_run_receipt.json")
    out.write_text(json.dumps(aggregate, indent=2) + "\n")
    return aggregate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("stage", choices=("quick", "full"), nargs="?")
    args = parser.parse_args()
    if args.preflight:
        build, plan, _ = require_gates(args.plan, None)
        print(json.dumps({"status": "PURE_GATE_PASS", "build_receipt_sha256": sha(BUILD_RECEIPT),
                          "plan_sha256": sha(args.plan), "profile_sha256": build["profile"]["profile_sha256"],
                          "stack_rlimit_bytes": resource.getrlimit(resource.RLIMIT_STACK),
                          "selected_columns": plan["cohort"]["native_columns"]}, indent=2))
        return
    if args.review is None or args.stage is None:
        parser.error("--review and stage are required for a model run")
    if args.stage == "full":
        quick = json.loads((WORK / "quick_gate.json").read_text())
        if (quick.get("status") != "PASS" or quick.get("quick_plan_sha256") != sha(args.plan) or
                quick.get("stage") != "quick"):
            raise ValueError("full run blocked: strict paired one-step capture/history gate is not PASS")
        receipt = run_pair("full", 18000, args.plan, args.review)
    else:
        receipt = run_pair("quick", 20, args.plan, args.review)
    print(json.dumps(receipt, indent=2))
    if receipt["status"] not in {"PASS", "RAW_PROBE_COMPLETED_AWAITING_CAPTURE_GATE"}:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
