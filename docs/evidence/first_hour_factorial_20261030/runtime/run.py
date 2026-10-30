#!/usr/bin/env python3
"""Launch and receipt the one-hour original-WRF factorial cell."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


OUT = Path(__file__).resolve().parent
DEST = Path("/var/tmp/firsthour-factorial-runtime-20261030/run_BG_BASE")
POLICY_RUN = Path("/var/tmp/firsthour-runtime-plan-20261030/producer_pair/forecast/run_POLICY_BG")
BASE_EXE = Path("/var/tmp/firsthour-runtime-plan-20261030/experiment/run_BASE_H/wrf.exe")
MPI = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun")
HISTORIES = ["wrfout_d01_2026-08-16_12:00:00", "wrfout_d01_2026-08-16_13:00:00"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    preflight = json.loads((OUT / "preflight.json").read_text())
    assert preflight["status"] == "PASS"
    assert len(preflight["staged_sha256"]) == 89
    assert preflight["only_declared_input_changed_from_POLICY_BG"] == "wrf.exe"
    frozen_scripts = json.loads((OUT / "scripts.sha256.json").read_text())
    assert {name: sha256(OUT / name) for name in frozen_scripts} == frozen_scripts
    assert not (DEST / "launcher.log").exists(), "Refusing to reuse a launched run directory"
    assert sha256(BASE_EXE) == preflight["staged_sha256"]["wrf.exe"]
    assert {name: sha256(DEST / name) for name in preflight["staged_sha256"]} == preflight["staged_sha256"]
    evidence_before = preflight["existing_evidence_sha256_before"]
    assert {path: sha256(Path(path)) for path in evidence_before} == evidence_before

    env = os.environ.copy()
    env.update(OMP_NUM_THREADS="1", OMP_DYNAMIC="FALSE")
    argv = [str(MPI), "-np", "8", str(DEST / "wrf.exe")]
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    with (DEST / "launcher.log").open("xb") as log:
        try:
            exit_code = subprocess.run(argv, cwd=DEST, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=2400).returncode
        except subprocess.TimeoutExpired:
            exit_code = "TIMEOUT"
    elapsed = time.monotonic() - started
    ended_utc = datetime.now(timezone.utc).isoformat()

    histories = sorted(path.name for path in DEST.glob("wrfout*"))
    rsl = DEST / "rsl.out.0000"
    rsl_text = rsl.read_text(errors="replace") if rsl.exists() else ""
    staged_after = {name: sha256(DEST / name) for name in preflight["staged_sha256"]}
    policy_after = {name: sha256(POLICY_RUN / name) for name in preflight["policy_source_sha256_before"]}
    evidence_after = {path: sha256(Path(path)) for path in evidence_before}
    outputs = {name: sha256(DEST / name) for name in histories}
    receipt = {
        "status": "SUCCESS" if exit_code == 0 and "SUCCESS COMPLETE WRF" in rsl_text and histories == HISTORIES else "INCOMPLETE",
        "cell": preflight["cell"],
        "start_utc": started_utc,
        "end_utc": ended_utc,
        "elapsed_seconds": elapsed,
        "argv": argv,
        "omp_num_threads": env["OMP_NUM_THREADS"],
        "omp_dynamic": env["OMP_DYNAMIC"],
        "exit": exit_code,
        "success_marker": "SUCCESS COMPLETE WRF" in rsl_text,
        "histories": histories,
        "histories_exact": histories == HISTORIES,
        "staged_inputs_unchanged": staged_after == preflight["staged_sha256"],
        "policy_source_inputs_unchanged": policy_after == preflight["policy_source_sha256_before"],
        "existing_producer_evidence_unchanged": evidence_after == evidence_before,
        "staged_sha256_after": staged_after,
        "policy_source_sha256_after": policy_after,
        "existing_evidence_sha256_after": evidence_after,
        "output_sha256": outputs,
        "scratch_directory": str(DEST),
        "preflight": str(OUT / "preflight.json"),
        "scope": "one-hour diagnostic factorial cell; runtime completion is not forecast validation",
    }
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if rsl.exists():
        (OUT / "rsl.out.0000.txt").write_text(rsl_text)
    (OUT / "launcher.log").write_bytes((DEST / "launcher.log").read_bytes())
    assert receipt["status"] == "SUCCESS", receipt
    assert receipt["staged_inputs_unchanged"] and receipt["policy_source_inputs_unchanged"], receipt
    assert receipt["existing_producer_evidence_unchanged"], receipt
    print(json.dumps({key: receipt[key] for key in (
        "status", "start_utc", "end_utc", "elapsed_seconds", "exit",
        "success_marker", "histories", "staged_inputs_unchanged",
        "policy_source_inputs_unchanged", "output_sha256",
        "existing_producer_evidence_unchanged",
    )}, indent=2))


if __name__ == "__main__":
    main()
