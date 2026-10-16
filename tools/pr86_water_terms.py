#!/usr/bin/env python3
"""Integrate additional saved PR85 v17 water-closure residual terms."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from pr86_water_budget import ROOT, bound_file, cell_slot, load_call_measure, sha256

PROCESS_REPORT = ROOT / "docs/evidence/pr86_process_budget_20261016.json"


class WaterTermError(ValueError):
    """Raised when a saved residual ledger is malformed or unbound."""


def remaining_after_storage_changes(initial_remainder: float,
                                    changes: list[tuple[str, float]]) -> dict[str, float]:
    """Apply R = R0 - sum(C), where positive C creates water and negative C loses it."""
    remaining = float(initial_remainder)
    snapshots = {}
    for name, storage_change in changes:
        remaining -= float(storage_change)
        snapshots[name] = remaining
    return snapshots


def _read_sedimentation(path: Path, call: dict[str, Any], kind: str) -> dict[str, Any]:
    tag = "PR85_ICE_SED" if kind == "ICE" else "PR85_G_SED"
    receipt = call["receipt"]
    expected = receipt.get("native_trace_outputs", {}).get(path.name, {}).get("sha256")
    if not expected:
        raise WaterTermError(f"run receipt does not bind {path.name}")
    identity = bound_file(path, expected)
    bounds = call["bounds"]
    rows = 0
    residual_kg = 0.0
    with path.open(encoding="ascii", errors="strict") as stream:
        header = None
        for line_number, line in enumerate(stream, 1):
            if line.startswith(f"# {tag}:"):
                header = line.rstrip("\n")
                continue
            fields = line.split()
            if not fields or fields[0] != tag:
                continue
            if len(fields) != 17:
                raise WaterTermError(f"{path.name}:{line_number}: expected 17 fields")
            try:
                i, j, _substep, _nlevels = map(int, fields[1:5])
                values = np.asarray([float(value.replace("D", "E").replace("d", "e"))
                                     for value in fields[5:]], dtype=np.float64)
            except ValueError as exc:
                raise WaterTermError(f"{path.name}:{line_number}: invalid numeric value") from exc
            if values.shape != (12,) or not np.isfinite(values).all():
                raise WaterTermError(f"{path.name}:{line_number}: invalid residual vector")
            slot = cell_slot(bounds, i, j, bounds["kts"])
            j_index, _k_index, i_index = slot
            # Source contract: residual_q = stored_delta_q + ground_approved_q,
            # in kg m-2. A positive value is net creation; integrate over area.
            residual_kg += float(values[10]) * float(call["area_ji"][j_index, i_index])
            rows += 1
        if header is None:
            raise WaterTermError(f"{path.name}: source ledger header is missing")
    if not rows:
        raise WaterTermError(f"{path.name}: no {tag} records")
    return {"rows": rows, "signed_storage_change_C_kg": residual_kg,
            "source_term": "values[10] = residual_q = stored_delta_q + ground_approved_q (kg m-2); positive is creation",
            "area_weight": "DX*DY/(MAPFAC_MX*MAPFAC_MY)", "identity": identity}


def _read_rain_freezing(path: Path, call: dict[str, Any]) -> dict[str, Any]:
    expected = call["receipt"].get("native_trace_outputs", {}).get(path.name, {}).get("sha256")
    if not expected:
        raise WaterTermError(f"run receipt does not bind {path.name}")
    identity = bound_file(path, expected)
    bounds = call["bounds"]
    rows = 0
    residual_kg = 0.0
    with path.open(encoding="ascii", errors="strict") as stream:
        header = None
        for line_number, line in enumerate(stream, 1):
            if line.startswith("# PR85_RAIN_FREEZE:"):
                header = line.rstrip("\n")
                continue
            fields = line.split()
            if not fields or fields[0] != "PR85_RAIN_FREEZE":
                continue
            if len(fields) != 34 or len(fields[5]) != 2 or any(flag not in "TF" for flag in fields[5]):
                raise WaterTermError(f"{path.name}:{line_number}: token or logical contract changed")
            try:
                i, j, k, _loop = map(int, fields[1:5])
                values = np.asarray([float(value.replace("D", "E").replace("d", "e"))
                                     for value in fields[6:]], dtype=np.float64)
            except ValueError as exc:
                raise WaterTermError(f"{path.name}:{line_number}: invalid numeric value") from exc
            if values.shape != (28,) or not np.isfinite(values).all():
                raise WaterTermError(f"{path.name}:{line_number}: invalid residual vector")
            slot = cell_slot(bounds, i, j, k)
            # The logged value is a positive loss when before > after. Convert
            # that loss to signed storage change C (negative) before summing.
            residual_kg -= float(values[22]) * float(call["volume_jki"][slot])
            rows += 1
        if header is None:
            raise WaterTermError(f"{path.name}: source ledger header is missing")
    if not rows:
        raise WaterTermError(f"{path.name}: no rain-freezing records")
    return {"rows": rows, "signed_storage_change_C_kg": residual_kg,
            "source_term": "-values[22], with values[22] = rhoDry*((QR+QG)before-(QR+QG)after) (kg m-3); positive logger value is loss",
            "volume_weight": "DELZ*map area (rhoDry already in logged kg/m3)", "identity": identity}


def analyze_arm(run_root: Path, prior_water: dict[str, Any],
                prior_process: dict[str, Any]) -> dict[str, Any]:
    call = load_call_measure(run_root)
    arm = call["arm"]
    if prior_water.get("arm") != arm or prior_process.get("arms", {}).get(arm, {}).get("arm") != arm:
        raise WaterTermError(f"saved partial budgets do not match {arm} run")
    water = prior_water
    process = prior_process["arms"][arm]
    if process["identity"]["first_call_receipt_sha256"] != call["identities"]["receipt"]["sha256"]:
        raise WaterTermError(f"process budget and run receipt differ for {arm}")

    sedimentation = {}
    for kind, basename in (("ICE", "pr85_ice_sedimentation_budget.raw"),
                           ("GRAUPEL", "pr85_graupel_sedimentation_budget.raw")):
        sedimentation[kind] = _read_sedimentation(run_root / basename, call, kind)
    rain_freezing = _read_rain_freezing(run_root / "pr85_rain_freezing_budget.raw", call)

    initial_remaining = float(water["residual_after_recorded_numerical_terms_kg"])
    process_residuals = process["stored_minus_approved_water_residuals"]
    cold = float(process_residuals["cold"]["signed_water_kg"])
    warm = float(process_residuals["warm"]["signed_water_kg"])
    remaining = remaining_after_storage_changes(initial_remaining, [("cold", cold), ("warm", warm),
                                                                    ("ice", sedimentation["ICE"]["signed_storage_change_C_kg"]),
                                                                    ("graupel", sedimentation["GRAUPEL"]["signed_storage_change_C_kg"]),
                                                                    ("rain_freeze", rain_freezing["signed_storage_change_C_kg"])])
    after_cold_warm = remaining["warm"]
    after_sedimentation = remaining["graupel"]
    after_rain_freezing = remaining["rain_freeze"]
    return {
        "arm": arm,
        "measure": water["measure"],
        "prior_remaining_after_cutoff_and_ice_transition_kg": initial_remaining,
        "balance_convention": "R = R0 - sum(C); positive C means stored water creation and negative C means storage loss",
        "additional_nonoverlap_signed_storage_changes_C_kg": {
            "cold_stored_minus_approved_Q_plus_QV": cold,
            "warm_stored_minus_approved_Q_plus_QV": warm,
            "ice_sedimentation_R32_column_term": sedimentation["ICE"]["signed_storage_change_C_kg"],
            "graupel_sedimentation_R32_column_term": sedimentation["GRAUPEL"]["signed_storage_change_C_kg"],
            "rain_freezing_pair_storage_change": rain_freezing["signed_storage_change_C_kg"],
        },
        "remaining_after_each_additive_piece_kg": {
            "after_cold_and_warm": after_cold_warm,
            "after_ice_and_graupel_sedimentation": after_sedimentation,
            "after_rain_freezing": after_rain_freezing,
        },
        "ledger_details": {"sedimentation": sedimentation, "rain_freezing": rain_freezing},
        "limitations": [
            "These saved first-call diagnostic terms are applied to the earlier fixed DEN*DELZ*map-area remainder; no new model call was run.",
            "Cold/warm, sedimentation, and rain-freezing signed storage changes are kept as separate source terms and are not folded into process proposals.",
            "This remains an open partial budget; uncaptured host hybrid mass, other process residuals, boundaries, and thermodynamic terms remain unresolved.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off-root", type=Path, required=True)
    parser.add_argument("--coupled-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    prior_process = json.loads(PROCESS_REPORT.read_text())
    arms = {}
    water_report_identities = {}
    for arm, run_root in (("OFF", args.off_root), ("COUPLED", args.coupled_root)):
        water_path = ROOT / f"docs/evidence/pr86_water_{arm}_20261016.json"
        prior_water = json.loads(water_path.read_text())
        water_report_identities[arm] = {"path": str(water_path), "sha256": sha256(water_path)}
        arms[arm] = analyze_arm(run_root.resolve(), prior_water, prior_process)
    report = {"schema": "pr86_first_call_additional_water_terms_v1",
              "arms": arms,
              "provenance": {"process_report": {"path": str(PROCESS_REPORT),
                                                     "sha256": sha256(PROCESS_REPORT)},
                             "prior_water_reports": water_report_identities}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"report": str(args.out), "sha256": sha256(args.out),
                      "remaining_after_rain_freezing_kg": {
                          arm: row["remaining_after_each_additive_piece_kg"]["after_rain_freezing"]
                          for arm, row in arms.items()}}, sort_keys=True))


if __name__ == "__main__":
    main()
