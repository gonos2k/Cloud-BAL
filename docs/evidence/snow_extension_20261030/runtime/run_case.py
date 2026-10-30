#!/usr/bin/env python3
"""Run one frozen snow-sensitivity case and write its raw receipt."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "common_plan.json"
MPI = "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun"
EXPECTED_HOURS = [f"wrfout_d01_2026-08-16_{hour:02d}:00:00" for hour in range(12, 19)]
SOURCE_B1 = Path("/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED")
SOURCE_ORIGINAL = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8/original")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def proc_table() -> dict[int, tuple[int, str]]:
    result = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
            closing = stat.rfind(")")
            fields = stat[closing + 2:].split()
            parent = int(fields[1])
            command = (entry / "cmdline").read_bytes().split(b"\0", 1)[0].decode(errors="replace")
            result[int(entry.name)] = (parent, command)
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
            continue
    return result


def descendants(root_pid: int) -> dict[int, str]:
    table = proc_table()
    found = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (parent, _) in table.items():
            if parent in found and pid not in found:
                found.add(pid)
                changed = True
    return {pid: table.get(pid, (0, ""))[1] for pid in found}


def source_hashes(group: str, plan: dict) -> tuple[dict, dict]:
    b1 = plan["source_b1_input_sha256_before"]
    original = plan["original_source_sha256_before"]
    paths = plan["source_evidence_sha256_before"]
    return {"B1": b1, "ORIGINAL": original, "evidence": paths}, {
        "B1": {name: sha256(SOURCE_B1 / name) for name in b1},
        "ORIGINAL": {name: sha256(SOURCE_ORIGINAL / name) for name in original},
        "evidence": {path: sha256(Path(path)) for path in paths},
    }


def main() -> int:
    case_id = sys.argv[1]
    plan_bytes = PLAN_PATH.read_bytes()
    plan = json.loads(plan_bytes)
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    assert plan["status"] == "PASS_READY_TO_LAUNCH"
    launch_scripts = json.loads((HERE / "launch_scripts.sha256.json").read_text())
    assert all(sha256(HERE / name) == digest for name, digest in launch_scripts.items())
    case = plan["case_records"][case_id]
    scratch = Path(case["scratch_directory"])
    evidence_dir = HERE / "cases" / case_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    input_before = case["staged_sha256"]
    assert {name: sha256(scratch / name) for name in input_before} == input_before

    source_before_expected, source_before_actual = source_hashes(case["group"], plan)
    assert source_before_actual == source_before_expected
    cpus = case["cpu_set"]
    cpu_list = ",".join(str(cpu) for cpu in cpus)
    env = os.environ.copy()
    env.update({
        "OMP_NUM_THREADS": "1",
        "OMP_DYNAMIC": "FALSE",
        "I_MPI_PIN": "1",
        "I_MPI_PIN_DOMAIN": "core",
        "I_MPI_PIN_ORDER": "compact",
        "I_MPI_PIN_RESPECT_CPUSET": "1",
        "I_MPI_PIN_PROCESSOR_LIST": cpu_list,
        "I_MPI_DEBUG": "4",
    })
    argv = ["taskset", "--cpu-list", cpu_list, MPI, "-np", "8", str(scratch / "wrf.exe")]
    assert not (scratch / "launcher.log").exists(), f"Refusing to relaunch {case_id}"
    start_utc = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    exit_code = None
    observed_affinities: dict[str, list[int]] = {}
    affinity_outside_set = False
    try:
        with (scratch / "launcher.log").open("xb") as log:
            proc = subprocess.Popen(argv, cwd=scratch, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                while proc.poll() is None:
                    for pid, command in descendants(proc.pid).items():
                        if pid == proc.pid or "wrf.exe" not in command:
                            continue
                        try:
                            affinity = sorted(os.sched_getaffinity(pid))
                        except (ProcessLookupError, PermissionError):
                            continue
                        observed_affinities[str(pid)] = affinity
                        if not set(affinity).issubset(set(cpus)):
                            affinity_outside_set = True
                    time.sleep(1.0)
                exit_code = proc.returncode
            except BaseException:
                proc.terminate()
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise
    except BaseException as error:
        exit_code = "LAUNCH_EXCEPTION"
        launch_error = repr(error)
    else:
        launch_error = None
    elapsed = time.monotonic() - start
    end_utc = datetime.now(timezone.utc).isoformat()

    histories = sorted(path.name for path in scratch.glob("wrfout*"))
    rsl_path = scratch / "rsl.out.0000"
    rsl = rsl_path.read_text(errors="replace") if rsl_path.exists() else ""
    success_marker = "SUCCESS COMPLETE WRF" in rsl
    output_sha = {name: sha256(scratch / name) for name in histories}
    input_after = {name: sha256(scratch / name) for name in input_before}
    source_after_expected, source_after_actual = source_hashes(case["group"], plan)
    assert source_after_expected == source_before_expected
    plan_unchanged = sha256(PLAN_PATH) == plan_sha
    staged_unchanged = input_after == input_before
    source_unchanged = source_after_actual == source_before_actual
    case_status = "SUCCESS" if (
        exit_code == 0 and success_marker and histories == EXPECTED_HOURS
        and staged_unchanged and source_unchanged and plan_unchanged and not affinity_outside_set
    ) else "INCOMPLETE"
    receipt = {
        "status": case_status,
        "case": case_id,
        "group": case["group"],
        "display_label": case["display_label"],
        "alpha": case["alpha"],
        "common_plan_sha256": plan_sha,
        "selection_plan_sha256": plan["selection_plan_sha256"],
        "launch_scripts_sha256": launch_scripts,
        "scratch_directory": str(scratch),
        "preflight_case_sha256": input_before,
        "staged_sha256_after": input_after,
        "staged_inputs_unchanged": staged_unchanged,
        "source_sha256_before": source_before_actual,
        "source_sha256_after": source_after_actual,
        "source_unchanged": source_unchanged,
        "cpu_slot": case["slot"],
        "cpu_set": cpus,
        "mpi_ranks": 8,
        "omp_threads": 1,
        "i_mpi_pin": env["I_MPI_PIN"],
        "i_mpi_pin_domain": env["I_MPI_PIN_DOMAIN"],
        "i_mpi_pin_respect_cpuset": env["I_MPI_PIN_RESPECT_CPUSET"],
        "i_mpi_pin_processor_list": env["I_MPI_PIN_PROCESSOR_LIST"],
        "observed_rank_process_affinities": observed_affinities,
        "affinity_outside_assigned_set": affinity_outside_set,
        "argv": argv,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "elapsed_seconds": elapsed,
        "exit": exit_code,
        "common_plan_unchanged_after_run": plan_unchanged,
        "launch_error": launch_error,
        "success_marker": success_marker,
        "histories": histories,
        "histories_exact": histories == EXPECTED_HOURS,
        "output_sha256": output_sha,
        "qsnow_audit": case["qsnow_audit"],
        "scope": "direct native QSNOW scaling sensitivity; no balance or operational claim",
    }
    receipt_path = evidence_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    if rsl_path.exists():
        (evidence_dir / "rsl.out.0000.txt").write_text(rsl)
    if (scratch / "launcher.log").exists():
        (evidence_dir / "launcher.txt").write_bytes((scratch / "launcher.log").read_bytes())
    print(json.dumps({"case": case_id, "status": receipt["status"], "exit": exit_code,
                      "history_count": len(histories), "cpu_set": cpus,
                      "staged_inputs_unchanged": receipt["staged_inputs_unchanged"],
                      "source_unchanged": receipt["source_unchanged"]}, sort_keys=True))
    return 0 if receipt["status"] == "SUCCESS" and receipt["staged_inputs_unchanged"] and receipt["source_unchanged"] and not affinity_outside_set else 1


if __name__ == "__main__":
    raise SystemExit(main())
