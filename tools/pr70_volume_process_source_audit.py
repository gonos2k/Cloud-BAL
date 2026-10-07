#!/usr/bin/env python3
"""Create a source-bound audit of the PR69 graupel-volume rejection."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

EXPECTED_SOURCE_SHA256 = "ee688498b32b7a1ccaf69858f62f4e457f7153df4fb8b965acfd069d8eefb425"
EXPECTED_NATIVE_RECEIPT_SHA256 = "3b39e94f4d2249717d242526ab17066f0293b2d7eba8390bbfaecbfde960db9c"

ANCHORS = {
    "rhox_initialization": "rhox(i,k) =0.",
    "prog_b_threshold": "if (qrs(i,k,3).gt. qcrmin .or. brs(i,k).gt. brs_min) then",
    "prog_b_density": "rhox(i,k) = qrs(i,k,3)/brs(i,k)",
    "prog_b_definition": "SUBROUTINE ProgB_param(",
    "prog_b_rhox_intent": "REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: rhox",
    "prog_b_end": "END subroutine ProgB_param",
    "pgdep_threshold": "if(qrs(i,k,3).gt.0. .and. ifsat.ne.1) then",
    "pgdep_formula": "pgdep(i,k) =(rh(i,k,2)-1.)*",
    "pgdep_mass_cap": "pgdep(i,k) = max(pgdep(i,k),-(qrs(i,k,3))/dtcld)",
    "volume_consumer": "call kdm6_mass_volume_rate(pgdep(i,k),rhox(i,k),",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locate_once(lines: list[str], anchor: str) -> int:
    matches = [index + 1 for index, line in enumerate(lines) if anchor in line]
    if len(matches) != 1:
        raise ValueError(f"Expected one source match for {anchor!r}, found {matches}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--native-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_hash = sha256(args.source)
    if source_hash != EXPECTED_SOURCE_SHA256:
        raise SystemExit(f"selected source hash mismatch: {source_hash}")
    native_hash = sha256(args.native_receipt)
    if EXPECTED_NATIVE_RECEIPT_SHA256 and native_hash != EXPECTED_NATIVE_RECEIPT_SHA256:
        raise SystemExit(f"native receipt hash mismatch: {native_hash}")

    lines = args.source.read_text(encoding="utf-8").splitlines()
    locations = {name: locate_once(lines, anchor) for name, anchor in ANCHORS.items()}
    pgdep_line = locations["pgdep_threshold"]
    progb_calls = [
        index + 1 for index, line in enumerate(lines)
        if "call ProgB_param(" in line and index + 1 < pgdep_line
    ]
    if not progb_calls:
        raise SystemExit("no ProgB_param call found before pgdep")
    locations["prog_b_calls_before_pgdep"] = progb_calls
    locations["last_prog_b_call_before_pgdep"] = progb_calls[-1]
    if not (
        locations["rhox_initialization"] < locations["last_prog_b_call_before_pgdep"]
        < locations["pgdep_threshold"] < locations["pgdep_formula"]
        < locations["pgdep_mass_cap"] < locations["volume_consumer"]
    ):
        raise SystemExit(f"unexpected source order: {locations}")

    subroutine_lines = lines[locations["prog_b_definition"] - 1 : locations["prog_b_end"]]
    out_names: list[str] = []
    for index, line in enumerate(subroutine_lines):
        if "INTENT(OUT)" not in line.upper() or "::" not in line:
            continue
        declaration = line.split("::", 1)[1].strip()
        continuation = index + 1
        while declaration.rstrip().endswith("&"):
            declaration = declaration.rstrip()[:-1] + subroutine_lines[continuation].strip()
            continuation += 1
        out_names.extend(name.strip().lower() for name in declaration.split(",") if name.strip())
    out_assignment_lines = {
        name: [
            index + 1 for index, line in enumerate(subroutine_lines, locations["prog_b_definition"] - 1)
            if re.search(rf"\b{re.escape(name)}\s*\(i,k\)\s*=", line, re.IGNORECASE)
        ]
        for name in out_names
    }
    if not out_names or any(not positions for positions in out_assignment_lines.values()):
        raise SystemExit(f"missing output assignments in ProgB_param: {out_assignment_lines}")

    receipt = json.loads(args.native_receipt.read_text(encoding="utf-8"))
    actual = receipt["run"]["actual_rejection_reason"]
    result = {
        "schema": "pr70_volume_process_source_audit_v1",
        "source": {
            "path": str(args.source),
            "sha256": source_hash,
            "line_anchors": locations,
            "intent_out_names": out_names,
            "intent_out_assignment_lines": out_assignment_lines,
            "all_outputs_assigned_on_every_control_path": False,
            "branch_audit": {
                "density_gate_false": "No rhox or other INTENT(OUT) assignments; outputs undefined on return",
                "density_gate_true": "rhox set to qg/brs and clamped to 100..900; cmg and pidn0g assigned if the range check passes",
                "cmg_positive": "Gamma-law parameters assigned only inside the 100..900 table intervals or exact 900 endpoint",
            },
            "thresholds": {"qcrmin": 1.0e-9, "brs_min": 1.0e-15},
            "logic": {
                "density_setup_gate": "qg > qcrmin OR brs > brs_min",
                "tendency_gate": "qg > 0 AND ifsat != 1",
                "negative_tendency": "pgdep is multiplied by (rh_ice - 1); available graupel mass caps negative pgdep",
                "skipped_density_gate": "rhox has INTENT(OUT); if the ProgB_param gate is false the source makes no assignment, so rhox is undefined by Fortran semantics on return",
            },
        },
        "native_receipt": {
            "path": str(args.native_receipt),
            "sha256": native_hash,
            "status": receipt["status"],
            "actual_rejection_operand": actual["operand"],
            "cell": receipt["run"]["location"],
            "observed_operands": {
                "pgdep": receipt["run"]["diagnostic"]["bg_input"]["pgdep"],
                "rhox": receipt["run"]["diagnostic"]["bg_input"]["rhox"],
                "brs": receipt["run"]["diagnostic"]["bg_input"]["brs"],
                "printed_final_qg_component": receipt["run"]["diagnostic"]["q_fixed"][4],
            },
            "qg_at_pgdep_line": "NOT_CAPTURED",
            "endpoint_qg_caveat": "printed Qfixed qg is a projected endpoint, not a checkpoint at the pgdep tendency line",
        },
        "finding": "The source admits positive qg into pgdep below the qcrmin PSD setup threshold, while ProgB_param has no rhox assignment when its density gate is false. Because rhox is INTENT(OUT), that path leaves the output undefined by the language; the retained ifx run observed zero. The source does not define a density-based graupel bulk-volume rate in this unsupported state.",
        "scope": "Source and retained-receipt audit only; no runtime rerun or physical closure claim.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "source_sha256": source_hash, "native_receipt_sha256": native_hash, "line_anchors": locations}, indent=2))


if __name__ == "__main__":
    main()
