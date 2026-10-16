#!/usr/bin/env python3
"""Summarize recorded PR85 v17 cold-process admission and backtracking.

The output separates the per-process feasibility fraction from the shared
composite factor. These are source-recorded stages, not individual failed
moment constraints or primitive reaction gross rates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from pr86_process_budget import COLD_SLICES, LedgerError, _cold_stage, _record_values
from pr86_water_budget import cell_slot, load_call_measure

ARMS = {
    "OFF": Path("/var/tmp/pr85_same13_OFF_joint_v17_20261015a"),
    "COUPLED": Path("/var/tmp/pr85_same13_COUPLED_joint_v17_20261015a"),
}
GROUPS = ("NG", "AUT", "G")
FRACTION_EDGES = (0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0000001)
STATUS_NAMES = {0: "FEASIBLE_SEARCH", 1: "NO_FEASIBLE_STEP", 2: "SEARCH_FAILURE_OR_UNSUPPORTED_G_VOLUME"}


def _bin_index(fraction: float) -> int:
    if not math.isfinite(fraction) or fraction < -1e-6 or fraction > 1.000001:
        raise LedgerError(f"invalid approval fraction: {fraction}")
    return next(i for i, upper in enumerate(FRACTION_EDGES[1:])
                if fraction <= upper + 1e-7)


def _new_group() -> dict[str, Any]:
    return {
        "records": 0,
        "proposing_records": 0,
        "proposal_mass_activity_kg": 0.0,
        "approved_mass_activity_kg": 0.0,
        "withheld_mass_activity_kg": 0.0,
        "fraction_bins": [{"lower": FRACTION_EDGES[i],
                           "upper": min(1.0, FRACTION_EDGES[i + 1]),
                           "records": 0, "proposal_mass_activity_kg": 0.0}
                          for i in range(len(FRACTION_EDGES) - 1)],
        "search_status": {},
        "composite_gamma": {},
        "cause_split": {"process_limiter_withheld_kg": 0.0,
                        "composite_backtracking_withheld_kg": 0.0,
                        "unresolved_when_gamma_zero_kg": 0.0},
    }


def analyze_arm(run_root: Path) -> dict[str, Any]:
    """Read one cold ledger once, checking its receipt hash and call geometry."""
    call = load_call_measure(run_root)
    path = run_root / "pr85_kdm6_cold_budget.raw"
    if path.is_symlink() or not path.is_file():
        raise LedgerError(f"cold ledger is not a regular file: {path}")
    expected = call["receipt"].get("native_trace_outputs", {}).get(path.name, {}).get("sha256")
    if not expected:
        raise LedgerError(f"run receipt does not bind {path.name}")

    groups = {name: _new_group() for name in GROUPS}
    digest = hashlib.sha256()
    rows = 0
    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            digest.update(raw_line)
            line = raw_line.decode("ascii").rstrip("\n")
            if not line.startswith("PR85_KDM6_COLD"):
                continue
            ids, data = _record_values(line, "PR85_KDM6_COLD", 217, line_number)
            i, j, k = ids[:3]
            slot = cell_slot(call["bounds"], i, j, k)
            if data[1] != float(call["rho_dry_jki"][slot]):
                raise LedgerError(f"cold rhoDry differs from same-cell call at {(i, j, k)}")
            dry_mass = float(call["dry_mass_jki"][slot])
            volume = float(call["volume_jki"][slot])
            gamma = data[2]
            if not 0.0 <= gamma <= 1.0:
                raise LedgerError(f"invalid composite gamma at {(i, j, k)}: {gamma}")
            statuses = ids[4:7]
            for group_index, group in enumerate(GROUPS):
                acc = groups[group]
                proposal = _cold_stage(group, data[COLD_SLICES[group]], 0, dry_mass, volume)["mass_kg"]
                approved = _cold_stage(group, data[COLD_SLICES[group]], 1, dry_mass, volume)["mass_kg"]
                withheld = _cold_stage(group, data[COLD_SLICES[group]], 2, dry_mass, volume)["mass_kg"]
                alpha = data[44 + group_index]
                status = statuses[group_index]
                if status not in STATUS_NAMES:
                    raise LedgerError(f"unknown {group} search status {status} at {(i,j,k)}")
                if abs((approved + withheld) - proposal) > max(1e-12, proposal * 2e-6):
                    raise LedgerError(f"{group} proposal split fails at {(i,j,k)}")
                acc["records"] += 1
                if proposal > 0.0:
                    acc["proposing_records"] += 1
                    acc["proposal_mass_activity_kg"] += proposal
                    acc["approved_mass_activity_kg"] += approved
                    acc["withheld_mass_activity_kg"] += withheld
                    fraction = approved / proposal
                    b = acc["fraction_bins"][_bin_index(fraction)]
                    b["records"] += 1
                    b["proposal_mass_activity_kg"] += proposal
                    if gamma > 0.0:
                        initial_alpha = alpha / gamma
                        if not -1e-5 <= initial_alpha <= 1.00001:
                            raise LedgerError(f"{group} alpha/gamma outside [0,1] at {(i,j,k)}")
                        initial_alpha = min(1.0, max(0.0, initial_alpha))
                        acc["cause_split"]["process_limiter_withheld_kg"] += proposal * (1.0 - initial_alpha)
                        acc["cause_split"]["composite_backtracking_withheld_kg"] += proposal * initial_alpha * (1.0 - gamma)
                    else:
                        acc["cause_split"]["unresolved_when_gamma_zero_kg"] += withheld
                    status_key = f"{status}:{STATUS_NAMES[status]}"
                    status_row = acc["search_status"].setdefault(
                        status_key, {"records": 0, "proposal_mass_activity_kg": 0.0})
                    status_row["records"] += 1
                    status_row["proposal_mass_activity_kg"] += proposal
                    gamma_key = f"{gamma:.9g}"
                    gamma_row = acc["composite_gamma"].setdefault(
                        gamma_key, {"records": 0, "proposal_mass_activity_kg": 0.0})
                    gamma_row["records"] += 1
                    gamma_row["proposal_mass_activity_kg"] += proposal
            rows += 1
    actual = digest.hexdigest()
    if actual != expected:
        raise LedgerError(f"run receipt hash mismatch for {path.name}")

    for group, acc in groups.items():
        proposed = acc["proposal_mass_activity_kg"]
        acc["applied_over_proposed"] = acc["approved_mass_activity_kg"] / proposed if proposed else None
        acc["withheld_over_proposed"] = acc["withheld_mass_activity_kg"] / proposed if proposed else None
        acc["cause_split"]["process_limiter_fraction_of_proposal"] = (
            acc["cause_split"]["process_limiter_withheld_kg"] / proposed if proposed else None)
        acc["cause_split"]["composite_fraction_of_proposal"] = (
            acc["cause_split"]["composite_backtracking_withheld_kg"] / proposed if proposed else None)
        acc["cause_split"]["unresolved_fraction_of_proposal"] = (
            acc["cause_split"]["unresolved_when_gamma_zero_kg"] / proposed if proposed else None)
    return {
        "arm": call["arm"],
        "ledger": {"path": str(path), "sha256": actual, "bytes": path.stat().st_size,
                   "first_call_receipt_sha256": call["identities"]["receipt"]["sha256"]},
        "rows": rows,
        "approval_fraction_bins": "proposal-mass-activity weighted; each record's applied/proposed vector activity; bins are right-closed, with zero included in the first bin",
        "cause_method": "per-process proposal withholding from alpha-before-gamma, plus incremental common composite gamma; gamma=0 has irrecoverable pre-gamma alpha",
        "groups": groups,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=("OFF", "COUPLED", "both"), default="both")
    args = parser.parse_args()
    arms = ARMS if args.arm == "both" else {args.arm: ARMS[args.arm]}
    result = {"schema": "pr87_cold_reasons_v1",
              "source": "/var/tmp/pr85_native_joint_candidate_20261015v17/source/phys/module_mp_kdm6.F",
              "limitations": [
                  "Mass is the PR86 half-L1 Q plus QV vector-activity proxy; it is not primitive gross reaction transfer.",
                  "Search status records feasibility-search outcome, not the individual state constraint that bounded alpha.",
                  "G status 2 combines search failure with unsupported graupel volume-rate cases in the source assignment.",
                  "Composite gamma records shared endpoint backtracking; it does not identify the failed endpoint moment.",
                  "Rows with gamma zero have no saved pre-composite alpha, so their suppression cannot be split between the per-process limiter and composite backtracking.",
              ],
              "arms": {name: analyze_arm(root) for name, root in arms.items()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({name: {group: {
        "proposed_kg": values["proposal_mass_activity_kg"],
        "approved_fraction": values["applied_over_proposed"],
        "withheld_kg": values["withheld_mass_activity_kg"],
        "cause_split": values["cause_split"],
    } for group, values in arm["groups"].items()} for name, arm in result["arms"].items()}, indent=2))


if __name__ == "__main__":
    main()
