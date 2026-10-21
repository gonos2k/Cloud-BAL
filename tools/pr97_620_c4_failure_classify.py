#!/usr/bin/env python3
"""Classify preserved PR94 C4 compact full-candidate failure rows."""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr94_physics_20261021/runs_on_lustre")
C4_BUILD = Path("/var/tmp/pr94_native_compact3600_20261021/pr87_native_overlay_build.json")
C4_SOURCE = Path("/var/tmp/pr94_native_compact3600_20261021/source/overrides/module_em.F")
C4_SOURCE_SHA256 = "f88708844994a30540fc458aeede7e0eda4503a04a341caf714050e52f8c18af"
C4_BUILD_SHA256 = "9ba94b0b0d4737641bd87d6237ff65e8b207bf8ae52c815521510d7d022f073d"
sys.path.insert(0, str(ROOT / "tools"))
import pr87_source_storage_failures as source_storage  # noqa: E402
import pr92_graupel_store_replay as replay  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _capture_source_module() -> str:
    build = json.loads(C4_BUILD.read_text())
    if sha256(C4_BUILD) != C4_BUILD_SHA256:
        raise ValueError("C4 source replay build receipt hash changed")
    source_pin = build["source_overrides"]["module_em.o"]["requested_sha256"]
    if source_pin != C4_SOURCE_SHA256 or sha256(C4_SOURCE) != C4_SOURCE_SHA256:
        raise ValueError("C4 store source no longer matches its build receipt")
    return C4_SOURCE.read_text().split("end module cloud_bal_joint_transport", 1)[0] + \
        "end module cloud_bal_joint_transport\n"


def _run_exact_replay(arm: str, captures: list[dict[str, Any]], core: str) -> list[dict[str, Any]]:
    statements = []
    label = 0
    for row_index, capture in enumerate(captures, 1):
        label += 1
        statements.extend([
            f"  q=transfer(int(z'{capture['q_bits']}',int64),0.0_real64)",
            f"  n=transfer(int(z'{capture['n_bits']}',int64),0.0_real64)",
            f"  rho=transfer(int(z'{capture['rho_bits']}',int32),0.0_real32)",
            "  call joint_moment_store(q,n,rho,100.0_real64,900.0_real64,.true.,sq,sn,adj,valid, &",
            "       allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true.,strict_mass_ratio=.true., &",
            "       inactive_mass_limit=0.0_real64,allow_inactive_q_quantum_adjustment=.false.,failure_stage=stage)",
            f"  write(*,'(i0,1x,l1,1x,i0)') {row_index},valid,stage",
        ])
    harness = """program pr97_620_exact_replay
use iso_fortran_env, only:int32,int64,real32,real64
use cloud_bal_joint_transport, only:joint_moment_store
implicit none
real(real64)::q,n
real(real32)::rho,sq,sn
integer::stage,adj
logical::valid
""" + "\n".join(statements) + "\nend program pr97_620_exact_replay\n"
    results = []
    for profile in ("O0", "O2"):
        run = replay.run_source_profile(profile, {"c4_core.f90": core, "probe.f90": harness})
        per_row: list[tuple[bool, int]] = []
        for line in run["stdout"].splitlines():
            fields = line.split()
            if len(fields) == 3 and fields[0].isdigit():
                per_row.append((fields[1] == "T", int(fields[2])))
        if len(per_row) != len(captures):
            raise ValueError(f"{arm} {profile}: incomplete exact replay output")
        if results and results != per_row:
            raise ValueError(f"{arm}: source replay differs between Intel profiles")
        results = per_row
    return [{"valid": valid, "failure_stage": stage} for valid, stage in results]


def _full_captures(path: Path) -> list[dict[str, Any]]:
    result = []
    lines = gzip.open(path, "rt", encoding="ascii").read().splitlines()
    for index, line in enumerate(lines):
        fields = line.split()
        if len(fields) != 21 or fields[0] != "PR92_STORE_FAIL_FULL":
            continue
        if fields[1:3] != ["32", "1"]:
            continue
        r32 = lines[index + 1].split()
        if len(r32) != 7 or r32[0] != "PR92_STORE_R32":
            raise ValueError("FULL capture is not followed by its REAL32 operand record")
        result.append({
            "timestep": int(fields[1]), "rk": int(fields[2]),
            "i": int(fields[3]), "j": int(fields[4]), "k": int(fields[5]),
            "cell": int(fields[6]), "stage": int(fields[7]),
            "q_bits": fields[8], "n_bits": fields[9], "rho_bits": r32[4],
        })
    return result


def _capture_key(capture: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (capture["timestep"], capture["rk"], capture["i"], capture["j"], capture["k"])


def _full_key(row: list[str]) -> tuple[int, int, int, int, int]:
    return (int(row[0]), int(row[1]), int(row[3]), int(row[4]), int(row[5]))


def _join_replays_to_full_rows(rows: list[list[str]], captures: list[dict[str, Any]],
                               replay_results: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if len(captures) != len(replay_results):
        raise ValueError("capture and replay result counts differ")
    replay_by_key = {}
    for capture, result in zip(captures, replay_results):
        key = _capture_key(capture)
        if key in replay_by_key:
            raise ValueError(f"duplicate capture key: {key}")
        replay_by_key[key] = (capture, result)
    row_keys = [_full_key(row) for row in rows]
    if len(set(row_keys)) != len(row_keys) or set(row_keys) != set(replay_by_key):
        raise ValueError("FULL ledger and exact-capture keys do not match uniquely")
    return [replay_by_key[key] for key in row_keys]


def classify_arm(arm: str, core: str) -> dict[str, Any]:
    run_root = RUNS / f"{arm}_3600s_c4_compact"
    receipt_path = run_root / "receipt.json"
    raw_path = run_root / "run/pr85_joint_source_failure.raw.gz"
    capture_path = run_root / "run/pr92_graupel_source_capture.raw.gz"
    receipt = json.loads(receipt_path.read_text())
    outputs = {row["compressed_path"]: row for row in receipt["compressed_outputs"]}
    output = outputs.get(raw_path.name)
    if output is None or sha256(raw_path) != output["compressed_sha256"]:
        raise ValueError(f"{arm}: source/full diagnostic is not receipt-bound")
    if receipt["candidate_build"]["receipt_sha256"] != C4_BUILD_SHA256:
        raise ValueError(f"{arm}: run receipt is not bound to the pinned PR94 compact build")
    capture_meta = next((item for item in receipt["compressed_outputs"]
                         if item["compressed_path"] == capture_path.name), None)
    if capture_meta is None or sha256(capture_path) != capture_meta["compressed_sha256"]:
        raise ValueError(f"{arm}: exact store capture is not receipt-bound")
    rows, declared = source_storage.read_full_rows(raw_path)
    captures = _full_captures(capture_path)
    replay_results = _run_exact_replay(arm, captures, core)
    joined_replays = _join_replays_to_full_rows(rows, captures, replay_results)

    classified = []
    for values, (capture, replay_result) in zip(rows, joined_replays):
        source_check = source_storage.classify_full_row(values)
        label = "runtime_source_stage_2_reject" if capture["stage"] == 2 else "runtime_source_stage_6_reject"
        classified.append({
            **source_check,
            "classification": label,
            "source_check_classification": source_check["classification"],
            "full_store_failure_stage": capture["stage"],
            "candidate_real64_bits": {"q": capture["q_bits"], "n": capture["n_bits"]},
            "runtime_store_behavior_reproduced": replay_result == {"valid": False, "failure_stage": capture["stage"]},
            "receipt_bound_source_form_exact_operand_replay": replay_result,
        })

    return {
        "arm": arm,
        "run_status": receipt["status"],
        "returncode": receipt["returncode"],
        "fatal_text": "PR87 full joint moment candidate infeasible; see source/full diagnostics",
        "receipt_path": str(receipt_path),
        "receipt_sha256": sha256(receipt_path),
        "ledger_path": str(raw_path),
        "ledger_compressed_sha256": sha256(raw_path),
        "ledger_raw_sha256": output["sha256"],
        "ledger_full_failure_count": declared,
        "source_capture_path": str(capture_path),
        "source_capture_compressed_sha256": sha256(capture_path),
        "source_capture_full_count": len(captures),
        "failures": classified,
        "interpretation_limit": (
            "PR92 captured exact candidate bits and failure stage at each per-cell FULL callback. This is "
            "not proof that any one cell alone caused grouped transaction infeasibility."
        ),
    }


def create_report() -> dict[str, Any]:
    core = _capture_source_module()
    arms = {arm: classify_arm(arm, core) for arm in ("OFF", "COUPLED")}
    return {
        "schema": "pr97_620_c4_failure_classification_v1",
        "classification_basis": {
            "continuous_check": "The source-form replay applies the actual C4 strict store call; generic 8-ULP classifications are retained only as a comparison.",
            "runtime_stage": "Exact stage captured by receipt-bound PR92_STORE_FAIL_FULL records.",
            "operand_bits": "Exact candidate REAL64 q/n bits captured by receipt-bound PR92_STORE_FAIL_FULL records.",
            "independent_replay": "Pinned Intel O0/O2 source-form replay of exact q/n bits and captured REAL32 density against the PR94 compact build's module source.",
            "store_source_path": str(C4_SOURCE),
            "store_source_sha256": sha256(C4_SOURCE),
            "build_receipt_path": str(C4_BUILD),
            "build_receipt_sha256": sha256(C4_BUILD),
            "build_profile_sha256": json.loads(C4_BUILD.read_text())["compiler_profile_sha256"],
            "build_executable_sha256": json.loads(C4_BUILD.read_text())["executable_sha256"],
        },
        "arms": arms,
    }


def main() -> None:
    output = ROOT / "docs/evidence/pr97_620_c4_failure_classification.json"
    output.write_text(json.dumps(create_report(), indent=2, sort_keys=True) + "\n")
    print(output)


if __name__ == "__main__":
    main()
