#!/usr/bin/env python3
"""Prepare, launch, and gate protected-process OLD/FIX native runs."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import time
from typing import Any
import netCDF4
import numpy as np

WORK = Path(__file__).resolve().parent
CLOUD_BAL = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_protected_process_20261106/Cloud-BAL")
EVIDENCE = CLOUD_BAL / "docs/evidence/cp02_protected_process_20261106/native"
COHORT = CLOUD_BAL / "docs/evidence/cp02_protected_process_20261106/cohorts/unique_global_corners.csv"
SOURCE_RECEIPT = EVIDENCE / "source/source_generation_receipt.json"
REVIEW = CLOUD_BAL / "docs/evidence/cp02_protected_process_20261106/review/native_source_plan_review.json"
BUILD_RECEIPT = WORK / "build/build_receipt.json"
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


def require_gates() -> dict:
    review = json.loads(REVIEW.read_text())
    if review.get("status") != "GO_FOR_COMPILE_STATIC_REVIEW":
        raise ValueError("independent static review is not GO")
    generation = json.loads(SOURCE_RECEIPT.read_text())
    if review["generated_source"]["receipt_sha256"] != sha(SOURCE_RECEIPT):
        raise ValueError("source-generation receipt differs from review")
    if review["plan"]["sha256"] != generation["plan_sha256"]:
        raise ValueError("plan differs from review")
    if not BUILD_RECEIPT.is_file():
        raise ValueError("paired IFX build receipt missing")
    build = json.loads(BUILD_RECEIPT.read_text())
    if build.get("status") != "PASS":
        raise ValueError("paired IFX build is not PASS")
    for arm in ("OLD", "FIX"):
        source_sha = next(row["sha256"] for row in generation["arms"] if row["arm"] == arm)
        if build["arms"][arm]["source_sha256"] != source_sha:
            raise ValueError(f"{arm} executable was not built from reviewed source")
    return build


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


def selected_cells() -> set[tuple[int, int]]:
    rows = list(__import__("csv").DictReader((CLOUD_BAL / "docs/evidence/cp02_protected_process_20261106/cohorts/unique_global_corners.csv").open(newline="")))
    cells = {(int(row["wrf_i_1based"]), int(row["wrf_j_1based"])) for row in rows}
    if len(cells) != 381:
        raise ValueError("final native selector count is not 381")
    return cells


def parse_calls(case: Path) -> dict:
    calls = {}
    for path in case.glob("state_calls_rank*.txt"):
        rank_match = re.fullmatch(r"state_calls_rank(\d+)\.txt", path.name)
        rank = int(rank_match.group(1))
        for line in path.read_text().splitlines():
            values = tuple(int(x) for x in line.split())
            if len(values) != 21:
                raise ValueError("call inventory row is not 21 integers")
            step, fr, call = values[:3]
            if fr != rank or not 1 <= step <= 1:
                raise ValueError("quick call inventory has invalid rank or timestep")
            key = (step, rank, call)
            if key in calls:
                raise ValueError("duplicate call inventory key")
            calls[key] = values[15:21]
    if not calls:
        raise ValueError("quick call inventory is empty")
    return calls


def quick_capture_gate(case: Path) -> dict:
    cells = selected_cells()
    calls = parse_calls(case)
    owner = {}
    for (step, rank, call), bounds in calls.items():
        its, ite, jts, jte, kts, kte = bounds
        for i, j in cells:
            if its <= i <= ite and jts <= j <= jte:
                for k in range(kts, kte + 1):
                    key = (step, i, j, k)
                    if key in owner:
                        raise ValueError("duplicate selected level owner in quick run")
                    owner[key] = (rank, call)
    expected = {(1, i, j, k) for i, j in cells for k in range(1, 40)}
    if set(owner) != expected:
        raise ValueError(f"quick owner coverage differs: expected={len(expected)} observed={len(owner)}")

    state_seen = {6: set(), 7: set()}
    header = struct.Struct(">8s15i")
    row = struct.Struct(">3i16f")
    for path in case.glob("state_selected_*_t*_rank*.bin"):
        match = re.fullmatch(r"state_selected_(entry|return)_t\d{6}-\d{6}_rank(\d+)\.bin", path.name)
        if not match:
            raise ValueError("selected-state chunk has an unexpected name")
        stage_id = 6 if match.group(1) == "entry" else 7
        rank = int(match.group(2))
        with path.open("rb") as stream:
            while block := stream.read(header.size):
                if len(block) != header.size:
                    raise ValueError("truncated selected-state header")
                magic, sid, fr, call, step, ilo, ihi, jlo, jhi, klo, khi, si, sj, sk, fields, count = header.unpack(block)
                if (magic != b"CBSP0001" or sid != stage_id or fr != rank or step != 1 or
                        (si, sj, sk, fields) != (1, 1, 1, 16) or count < 0):
                    raise ValueError("invalid selected-state frame header")
                for _ in range(count):
                    raw = stream.read(row.size)
                    if len(raw) != row.size:
                        raise ValueError("truncated selected-state row")
                    i, j, k, *values = row.unpack(raw)
                    if owner.get((1, i, j, k)) != (rank, call) or not all(math.isfinite(v) for v in values):
                        raise ValueError("selected-state row ownership or finiteness failed")
                    state_seen[stage_id].add((i, j, k))
                    tk = np.float32(np.float32(values[0]) * np.float32(values[15]))
                    if tk.view(np.uint32) != np.float32(values[13]).view(np.uint32):
                        raise ValueError("selected wrapper TK is not TH*PII in REAL32")
    wanted_levels = {(i, j, k) for i, j in cells for k in range(1, 40)}
    if any(state_seen[stage] != wanted_levels for stage in (6, 7)):
        raise ValueError("quick wrapper entry/return coverage is incomplete")

    process_seen = {phase: set() for phase in (1, 2, 6, 8)}
    frame_count = 0
    phase_counts = {}
    fixed_int = struct.Struct(">i")
    frame_head = struct.Struct(">8i")
    record_head = struct.Struct(">7i")
    for path in case.glob("cp04_t*_rank*.bin"):
        match = re.fullmatch(r"cp04_t\d{6}-\d{6}_rank(\d+)\.bin", path.name)
        if not match:
            raise ValueError("process chunk has an unexpected name")
        rank_from_name = int(match.group(1))
        with path.open("rb") as stream:
            while magic := stream.read(8):
                if magic != b"C4FR0001":
                    raise ValueError("invalid CP04 frame marker")
                header_values = frame_head.unpack(stream.read(frame_head.size))
                rank, call, step, j, its, ite, kts, kte = header_values
                constants = stream.read(40)
                if len(constants) != 40 or rank != rank_from_name or step != 1 or (kts, kte) != (1, 39):
                    raise ValueError("invalid CP04 frame header")
                frame_count += 1
                selected_i = {i for i, jj in cells if jj == j and its <= i <= ite}
                if not selected_i:
                    raise ValueError("unexpected CP04 frame without selected cells")
                while True:
                    raw_phase = stream.read(4)
                    if len(raw_phase) != 4:
                        raise ValueError("truncated CP04 record stream")
                    phase = fixed_int.unpack(raw_phase)[0]
                    if phase == -1:
                        break
                    if phase not in range(1, 18):
                        raise ValueError("unknown CP04 phase")
                    record = stream.read(record_head.size)
                    if len(record) != record_head.size:
                        raise ValueError("truncated CP04 record header")
                    i, k, loop, loops, substep, mstep, nfields = record_head.unpack(record)
                    payload = stream.read(nfields * 4)
                    if len(payload) != nfields * 4 or not i in selected_i or not 1 <= k <= 39:
                        raise ValueError("invalid CP04 record payload or selected cell")
                    vals = np.frombuffer(payload, dtype=">f4")
                    if not np.isfinite(vals).all():
                        raise ValueError("nonfinite CP04 source field")
                    phase_counts[phase] = phase_counts.get(phase, 0) + 1
                    if phase in process_seen:
                        process_seen[phase].add((i, j, k))
                    if phase in (9, 10) and not 1 <= substep <= mstep:
                        raise ValueError("sedimentation record lacks actual substep")
    if frame_count == 0:
        raise ValueError("quick process frames are missing")
    for phase in (1, 2, 6, 8):
        if process_seen[phase] != wanted_levels:
            raise ValueError(f"quick mandatory process phase {phase} coverage incomplete")

    surface_seen = set()
    surface_row = struct.Struct(">8s5i3f")
    for path in case.glob("surface_cp04_rank*.bin"):
        rank = int(re.fullmatch(r"surface_cp04_rank(\d+)\.bin", path.name).group(1))
        with path.open("rb") as stream:
            while raw := stream.read(surface_row.size):
                if len(raw) != surface_row.size:
                    raise ValueError("truncated surface return")
                magic, fr, call, step, j, i, rainncv, rain, sr = surface_row.unpack(raw)
                if (magic != b"C4SR0001" or fr != rank or step != 1 or (i, j) not in cells or
                        owner.get((step, i, j, 1)) != (rank, call) or
                        not all(math.isfinite(v) for v in (rainncv, rain, sr))):
                    raise ValueError("invalid quick surface return")
                surface_seen.add((i, j))
    if surface_seen != cells:
        raise ValueError("quick surface return coverage incomplete")
    return {"status": "PASS", "selected_columns": len(cells), "levels": 39,
            "owner_rows": len(owner), "wrapper_entry_rows": len(state_seen[6]),
            "wrapper_return_rows": len(state_seen[7]), "cp04_frame_count": frame_count,
            "phase_counts": phase_counts, "surface_return_rows": len(surface_seen)}


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


def run_pair(stage: str, duration: int) -> dict:
    build = require_gates()
    cases = {arm: prepare_case(stage, arm, duration) for arm in ("OLD", "FIX")}
    processes = {}
    logs = {}
    envs = {}
    commands = {}
    starts = {}
    for arm, case in cases.items():
        cpus = CPUS[arm]
        env = os.environ.copy()
        cpu_list = ",".join(str(x) for x in cpus)
        env.update(OMP_NUM_THREADS="1", OMP_DYNAMIC="FALSE", I_MPI_PIN="1",
                   I_MPI_PIN_DOMAIN="core", I_MPI_PIN_RESPECT_CPUSET="1",
                   I_MPI_PIN_PROCESSOR_LIST=cpu_list)
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
        result = {"status": "PASS" if code == 0 and arm not in cap_failures and history_ok and after == before and "SUCCESS COMPLETE WRF" in logs_text else "FAIL",
                  "arm": arm, "stage": stage, "exit_code": code, "argv": commands[arm],
                  "cpu_set": CPUS[arm], "omp_threads": 1, "elapsed_seconds": time.time() - starts[arm],
                  "success_marker": "SUCCESS COMPLETE WRF" in logs_text,
                  "history_files": actual_names, "expected_history_files": expected_names,
                  "history_comparisons": history, "inputs_before": before, "inputs_after": after,
                  "diagnostic_bytes": diagnostic_size(case)[0], "cap_failure": cap_failures.get(arm),
                  "launcher_log_sha256": sha(case / "launcher.log"),
                  "call_manifest_files": sorted(p.name for p in case.glob("state_calls_rank*.txt")),
                  "case_path": str(case)}
        if stage == "quick" and result["status"] == "PASS":
            try:
                result["quick_capture_gate"] = quick_capture_gate(case)
                result["status"] = "PASS"
            except Exception as error:
                result["status"] = "FAIL"
                result["quick_capture_error"] = repr(error)
        results[arm] = result
        (case / "launch_receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    aggregate = {"stage": stage, "status": "PASS" if all(v["status"] == "PASS" for v in results.values()) else "FAIL",
                 "duration_seconds": duration, "build_receipt_sha256": sha(BUILD_RECEIPT),
                 "review_receipt_sha256": sha(REVIEW), "arms": results}
    out = WORK / ("quick_gate.json" if stage == "quick" else "full_run_receipt.json")
    out.write_text(json.dumps(aggregate, indent=2) + "\n")
    return aggregate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("quick", "full"))
    args = parser.parse_args()
    if args.stage == "full":
        quick = json.loads((WORK / "quick_gate.json").read_text())
        if quick.get("status") != "PASS":
            raise ValueError("full run blocked: paired 20-second source/coverage/history gate is not PASS")
        receipt = run_pair("full", 18000)
    else:
        receipt = run_pair("quick", 20)
    print(json.dumps(receipt, indent=2))
    if receipt["status"] != "PASS":
        raise SystemExit(1)

if __name__ == "__main__":
    import shutil
    main()
