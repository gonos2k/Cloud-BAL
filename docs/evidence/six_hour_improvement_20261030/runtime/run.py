#!/usr/bin/env python3
"""Run the six-hour improved B1 forecast and seal its output hashes."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRATCH = Path("/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED")
SOURCE = Path("/var/tmp/firsthour-runtime-plan-20261030/producer_pair/forecast/run_POLICY_BG")
MPI = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun")
HISTORIES = [f"wrfout_d01_2026-08-16_{hour:02d}:00:00" for hour in range(12, 19)]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    preflight = json.loads((HERE / "preflight.json").read_text())
    assert preflight["status"] == "PASS"
    script_manifest = json.loads((HERE / "scripts.sha256.json").read_text())
    assert {name: sha256(HERE / name) for name in script_manifest} == script_manifest
    staged_before = preflight["staged_sha256"]
    source_before = preflight["policy_source_sha256_before"]
    assert {name: sha256(SCRATCH / name) for name in staged_before} == staged_before
    assert {name: sha256(SOURCE / name) for name in source_before} == source_before
    evidence_before = preflight["existing_evidence_sha256_before"]
    assert {path: sha256(Path(path)) for path in evidence_before} == evidence_before
    assert not (SCRATCH / "launcher.log").exists(), "Refusing to reuse a launched run directory"

    environment = os.environ.copy()
    environment.update(OMP_NUM_THREADS="1", OMP_DYNAMIC="FALSE")
    argv = [str(MPI), "-np", "8", str(SCRATCH / "wrf.exe")]
    start_utc = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    with (SCRATCH / "launcher.log").open("xb") as log:
        try:
            exit_code = subprocess.run(argv, cwd=SCRATCH, env=environment, stdout=log,
                                       stderr=subprocess.STDOUT, timeout=5400).returncode
        except subprocess.TimeoutExpired:
            exit_code = "TIMEOUT"
    elapsed = time.monotonic() - start
    end_utc = datetime.now(timezone.utc).isoformat()

    histories = sorted(path.name for path in SCRATCH.glob("wrfout*"))
    rsl = SCRATCH / "rsl.out.0000"
    rsl_text = rsl.read_text(errors="replace") if rsl.exists() else ""
    staged_after = {name: sha256(SCRATCH / name) for name in staged_before}
    source_after = {name: sha256(SOURCE / name) for name in source_before}
    evidence_after = {path: sha256(Path(path)) for path in evidence_before}
    output_sha = {name: sha256(SCRATCH / name) for name in histories}
    receipt = {
        "status": "SUCCESS" if exit_code == 0 and "SUCCESS COMPLETE WRF" in rsl_text and histories == HISTORIES else "INCOMPLETE",
        "case": "IMPROVED_BG_FIXED",
        "start_utc": start_utc,
        "end_utc": end_utc,
        "elapsed_seconds": elapsed,
        "argv": argv,
        "omp_num_threads": environment["OMP_NUM_THREADS"],
        "omp_dynamic": environment["OMP_DYNAMIC"],
        "exit": exit_code,
        "success_marker": "SUCCESS COMPLETE WRF" in rsl_text,
        "histories": histories,
        "histories_exact": histories == HISTORIES,
        "staged_inputs_unchanged": staged_after == staged_before,
        "policy_source_inputs_unchanged": source_after == source_before,
        "existing_evidence_unchanged": evidence_after == evidence_before,
        "staged_sha256_after": staged_after,
        "policy_source_sha256_after": source_after,
        "existing_evidence_sha256_after": evidence_after,
        "output_sha256": output_sha,
        "scratch_directory": str(SCRATCH),
        "scope": "six-hour diagnostic B1 forecast; completion is not forecast validation",
    }
    (HERE / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if rsl.exists():
        (HERE / "rsl.out.0000.txt").write_text(rsl_text)
    (HERE / "launcher.log").write_bytes((SCRATCH / "launcher.log").read_bytes())
    assert receipt["status"] == "SUCCESS", receipt
    assert receipt["staged_inputs_unchanged"] and receipt["policy_source_inputs_unchanged"] and receipt["existing_evidence_unchanged"], receipt
    print(json.dumps({key: receipt[key] for key in (
        "status", "start_utc", "end_utc", "elapsed_seconds", "exit",
        "success_marker", "histories", "staged_inputs_unchanged",
        "policy_source_inputs_unchanged", "existing_evidence_unchanged", "output_sha256",
    )}, indent=2))


if __name__ == "__main__":
    main()
