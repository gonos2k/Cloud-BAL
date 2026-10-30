#!/usr/bin/env python3
"""Recount the sealed 39-case snow-lower archive against ORIGINAL."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / "docs/evidence/weak_strong_balance_20261030"
SOURCE = ROOT / "docs/evidence/snow_lower_20261030/analysis"
EXPECTED_RECEIPT_SHA256 = "a9b8fa97e12d85bd49ce91b42f5126c8fc727ef0846eba1eeddc6a552a044602"
EXPECTED_INPUTS = {
    "categorical_scores.csv": "3dcab1e1ca19b3bce65611a3196eeaa93ae0c23560f00145ccfbd6b0fd170c7b",
    "hour_13_arrays.npz": "db3c69de36fe7d82ff3223dc92f849031fe5bb68bb7118592526e65fa6501048",
    "hour_14_arrays.npz": "5b3411c6b03fc1a9fdad78dd05fa04d5181b18e28adb8de6f96a11a220e3a983",
    "hour_15_arrays.npz": "2dcbd2c0960c75fc18b1932e37187ad1b53079ca245ad2e225b0c0157ce44bba",
    "hour_16_arrays.npz": "902b55a65837f64a1ae78fab0d8a59f3ce40906e82fa0aa0eab7c88d115765e5",
    "hour_17_arrays.npz": "f48d9b98e6cdf6acb48466bb9e3669739ecdc148bc751a64e2ecc2f1af3222e7",
    "hour_18_arrays.npz": "91732db992aa3936946d789dae7445f5d9b29c10ee8da03dcb72d922b5841130",
}
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
WEAK_THRESHOLDS = (0.1, 0.5, 1.0)
LEADS = tuple(range(1, 7))
CONTEXT_CASE = "CURRENT_HYDRO"
BASELINE_CASE = "ORIGINAL"

ROW_FIELDS = (
    "scope", "case", "lead_hour", "valid_utc", "threshold_mm",
    "baseline_hit", "baseline_miss", "baseline_false_alarm", "baseline_correct_dry",
    "case_hit", "case_miss", "case_false_alarm", "case_correct_dry",
    "delta_hit", "delta_miss", "delta_false_alarm", "delta_correct_dry",
    "hits_lost", "hits_gained", "false_alarms_removed", "false_alarms_new",
    "baseline_CSI", "case_CSI", "delta_CSI", "baseline_FAR", "case_FAR", "delta_FAR",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def counts(forecast: np.ndarray, reference: np.ndarray, threshold: float) -> dict[str, int | float]:
    forecast_event = forecast >= threshold
    reference_event = reference >= threshold
    hit = int(np.count_nonzero(forecast_event & reference_event))
    miss = int(np.count_nonzero(~forecast_event & reference_event))
    false_alarm = int(np.count_nonzero(forecast_event & ~reference_event))
    correct_dry = int(np.count_nonzero(~forecast_event & ~reference_event))
    denominator = hit + miss + false_alarm
    return {
        "hit": hit,
        "miss": miss,
        "false_alarm": false_alarm,
        "correct_dry": correct_dry,
        "CSI": hit / denominator if denominator else float("nan"),
        "FAR": false_alarm / (hit + false_alarm) if hit + false_alarm else float("nan"),
    }


def transition_counts(baseline: np.ndarray, candidate: np.ndarray,
                      reference: np.ndarray, threshold: float) -> dict[str, int]:
    base_event, case_event, observed_event = (
        baseline >= threshold, candidate >= threshold, reference >= threshold
    )
    return {
        "hits_lost": int(np.count_nonzero(base_event & observed_event & ~case_event)),
        "hits_gained": int(np.count_nonzero(~base_event & observed_event & case_event)),
        "false_alarms_removed": int(np.count_nonzero(base_event & ~observed_event & ~case_event)),
        "false_alarms_new": int(np.count_nonzero(~base_event & ~observed_event & case_event)),
    }


def score_row(scope: str, case: str, lead: int, threshold: float,
              baseline: np.ndarray, candidate: np.ndarray,
              reference: np.ndarray) -> dict[str, int | float | str]:
    base_score = counts(baseline, reference, threshold)
    case_score = counts(candidate, reference, threshold)
    transitions = transition_counts(baseline, candidate, reference, threshold)
    delta = {
        "hit": case_score["hit"] - base_score["hit"],
        "miss": case_score["miss"] - base_score["miss"],
        "false_alarm": case_score["false_alarm"] - base_score["false_alarm"],
        "correct_dry": case_score["correct_dry"] - base_score["correct_dry"],
    }
    if (delta["hit"] != transitions["hits_gained"] - transitions["hits_lost"]
            or delta["miss"] != -delta["hit"]
            or delta["false_alarm"] != transitions["false_alarms_new"] - transitions["false_alarms_removed"]
            or delta["correct_dry"] != -delta["false_alarm"]):
        raise ValueError(f"{case}/lead{lead}/threshold{threshold}: transitions do not reconcile")
    return {
        "scope": scope,
        "case": case,
        "lead_hour": lead,
        "valid_utc": f"2026-08-16T{lead + 12:02d}:00:00Z",
        "threshold_mm": threshold,
        "baseline_hit": base_score["hit"],
        "baseline_miss": base_score["miss"],
        "baseline_false_alarm": base_score["false_alarm"],
        "baseline_correct_dry": base_score["correct_dry"],
        "case_hit": case_score["hit"],
        "case_miss": case_score["miss"],
        "case_false_alarm": case_score["false_alarm"],
        "case_correct_dry": case_score["correct_dry"],
        "delta_hit": delta["hit"],
        "delta_miss": delta["miss"],
        "delta_false_alarm": delta["false_alarm"],
        "delta_correct_dry": delta["correct_dry"],
        **transitions,
        "baseline_CSI": base_score["CSI"],
        "case_CSI": case_score["CSI"],
        "delta_CSI": case_score["CSI"] - base_score["CSI"],
        "baseline_FAR": base_score["FAR"],
        "case_FAR": case_score["FAR"],
        "delta_FAR": case_score["FAR"] - base_score["FAR"],
    }


def main() -> int:
    review = BUNDLE / "review"
    review.mkdir(parents=True, exist_ok=True)
    receipt_path = SOURCE / "receipt.json"
    if sha256(receipt_path) != EXPECTED_RECEIPT_SHA256:
        raise ValueError("prior lower-sensitivity receipt hash mismatch")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (receipt.get("status") != "COMPLETE" or receipt.get("cases") is None
            or len(receipt["cases"]) != 39 or receipt.get("points_per_hour") != 3688
            or receipt.get("thresholds_mm") != list(THRESHOLDS)
            or receipt.get("hours_utc") != list(range(13, 19))):
        raise ValueError("prior receipt does not describe the complete 39-case grid")
    input_hashes = {name: sha256(SOURCE / name) for name in EXPECTED_INPUTS}
    if input_hashes != EXPECTED_INPUTS:
        raise ValueError("prior CSV or one of six hourly-array hashes changed")
    if receipt.get("analysis_outputs", {}).get("categorical_scores.csv", {}).get("sha256") != EXPECTED_INPUTS["categorical_scores.csv"]:
        raise ValueError("receipt does not bind categorical CSV hash")
    for name in EXPECTED_INPUTS:
        if name == "categorical_scores.csv":
            continue
        if receipt.get("analysis_outputs", {}).get(name, {}).get("sha256") != EXPECTED_INPUTS[name]:
            raise ValueError(f"receipt does not bind {name}")

    csv_rows = read_csv(SOURCE / "categorical_scores.csv")
    expected_cases = set(receipt["cases"])
    if expected_cases != {row["case"] for row in csv_rows}:
        raise ValueError("CSV case set differs from sealed receipt")
    candidate_cases = sorted(expected_cases - {BASELINE_CASE, CONTEXT_CASE})
    if len(candidate_cases) != 37 or len(expected_cases) != 39:
        raise ValueError("expected 37 eligible contrasts, one baseline, and one context-only case")
    csv_index = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): row
                 for row in csv_rows}
    if len(csv_index) != len(csv_rows) or len(csv_rows) != 39 * 6 * 6:
        raise ValueError("categorical score grid is incomplete or duplicated")

    rows: list[dict[str, int | float | str]] = []
    fail_rows: list[dict[str, int | float | str]] = []
    candidate_summaries = []
    context_rows: list[dict[str, int | float | str]] = []
    named_case_cells = {}
    floor_failure_cells = {}

    for lead in LEADS:
        with np.load(SOURCE / f"hour_{lead + 12}_arrays.npz", allow_pickle=False) as data:
            arrays = {name: np.asarray(data[name]) for name in data.files}
        if set(arrays) != expected_cases | {"reference", "latitude", "longitude", "flat_index_yx"}:
            raise ValueError(f"lead {lead}: point-array case/coordinate keys mismatch")
        if any(arrays[name].shape != (3688,) or not np.isfinite(arrays[name]).all()
               for name in expected_cases | {"reference"}):
            raise ValueError(f"lead {lead}: point array has wrong shape or nonfinite values")
        baseline = arrays[BASELINE_CASE]
        reference = arrays["reference"]
        for case in [*candidate_cases, CONTEXT_CASE]:
            scope = "ELIGIBLE_CANDIDATE" if case in candidate_cases else "CONTEXT_ONLY"
            candidate = arrays[case]
            for threshold in THRESHOLDS:
                row = score_row(scope, case, lead, threshold, baseline, candidate, reference)
                archived = csv_index[(lead, case, threshold)]
                for field in ("hit", "miss", "false_alarm", "correct_dry"):
                    if int(archived[field]) != row[f"case_{field}"]:
                        raise ValueError(f"archived {case}/lead{lead}/{threshold}/{field} differs from arrays")
                if float(archived["CSI"]) != row["case_CSI"] or float(archived["FAR"]) != row["case_FAR"]:
                    raise ValueError(f"archived {case}/lead{lead}/{threshold} CSI/FAR differs from arrays")
                rows.append(row)
                if scope == "CONTEXT_ONLY":
                    context_rows.append(row)
                if case in {"CONTROL_SNOW_300", "IMPROVED_SNOW_080", "IMPROVED_BG_FIXED"}:
                    named_case_cells[f"{case}|L{lead}|T{threshold:g}"] = row

                if case in candidate_cases and threshold in WEAK_THRESHOLDS:
                    base_csi = counts(baseline, reference, threshold)["CSI"]
                    candidate_csi = counts(candidate, reference, threshold)["CSI"]
                    if candidate_csi < base_csi:
                        failure = {
                            "case": case, "lead_hour": lead, "threshold_mm": threshold,
                            "baseline_CSI": base_csi, "candidate_CSI": candidate_csi,
                            "delta_CSI": candidate_csi - base_csi,
                            "cell_rule": "candidate CSI < ORIGINAL CSI (zero tolerance)",
                        }
                        fail_rows.append(failure)
                        floor_failure_cells.setdefault(case, []).append(f"L{lead}@{threshold:g}")

    for case in candidate_cases:
        case_rows = [row for row in rows if row["case"] == case]
        failures = floor_failure_cells.get(case, [])
        strong = csv_index[(1, case, 10.0)]
        baseline_strong = csv_index[(1, BASELINE_CASE, 10.0)]
        strong_pass = float(strong["CSI"]) > float(baseline_strong["CSI"])
        candidate_summaries.append({
            "case": case,
            "weak_floor_cells_passed": 18 - len(failures),
            "weak_floor_cells_failed": len(failures),
            "weak_floor_failure_cells": failures,
            "lead1_CSI10_strictly_above_ORIGINAL": strong_pass,
            "qualified": len(failures) == 0 and strong_pass,
            "rows_compared": len(case_rows),
        })

    if len(rows) != 38 * 36 or len(context_rows) != 36 or len(named_case_cells) != 3 * 36:
        raise ValueError("derived comparison grid has wrong cardinality")
    if len(fail_rows) != sum(len(cells) for cells in floor_failure_cells.values()):
        raise ValueError("weak-floor failure list and case map differ")

    results = {
        "schema": "prior-weak-strong-tradeoff-audit-v1",
        "status": "PASS",
        "baseline_case": BASELINE_CASE,
        "eligible_case_count": len(candidate_cases),
        "context_only_case": CONTEXT_CASE,
        "context_only_rows": len(context_rows),
        "cases_total_in_source": len(expected_cases),
        "points_per_lead": 3688,
        "leads_hours": list(LEADS),
        "thresholds_mm": list(THRESHOLDS),
        "weak_floor": {"thresholds_mm": list(WEAK_THRESHOLDS), "cells_per_candidate": 18,
                       "rule": "CSI(candidate) >= CSI(ORIGINAL) with zero tolerance for every lead and weak threshold",
                       "qualified_candidates": [row["case"] for row in candidate_summaries if row["qualified"]],
                       "failure_cell_count": len(fail_rows)},
        "strong_gate": {"cell": "lead1_CSI10", "rule": "CSI(candidate) > CSI(ORIGINAL), strict, zero tolerance"},
        "candidate_summaries": candidate_summaries,
        "named_case_details": named_case_cells,
        "transition_definitions": {
            "hits_lost": "ORIGINAL forecast >= threshold, reference >= threshold, candidate forecast < threshold",
            "hits_gained": "ORIGINAL forecast < threshold, reference >= threshold, candidate forecast >= threshold",
            "false_alarms_removed": "ORIGINAL forecast >= threshold, reference < threshold, candidate forecast < threshold",
            "false_alarms_new": "ORIGINAL forecast < threshold, reference < threshold, candidate forecast >= threshold",
            "sign_check": "delta_hit=hits_gained-hits_lost; delta_miss=-delta_hit; delta_FA=false_alarms_new-false_alarms_removed; delta_CN=-delta_FA",
        },
        "source_bindings": {
            "source_receipt": {"path": str(receipt_path.relative_to(ROOT)), "sha256": EXPECTED_RECEIPT_SHA256},
            "source_hashes": input_hashes,
        },
        "calculated_metrics": "Per lead and threshold only. No means, averages, or cross-lead/threshold aggregation.",
        "review_source_sha256": sha256(Path(__file__)),
    }

    results_path = review / "results.json"
    rows_path = review / "results.csv"
    context_path = review / "current_hydro_context.csv"
    failures_path = review / "weak_floor_failures.csv"
    with rows_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=ROW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with context_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=ROW_FIELDS)
        writer.writeheader()
        writer.writerows(context_rows)
    with failures_path.open("w", newline="", encoding="utf-8") as stream:
        fields = ("case", "lead_hour", "threshold_mm", "baseline_CSI", "candidate_CSI", "delta_CSI", "cell_rule")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(fail_rows)
    results["audit_outputs"] = {
        "results_csv": {"path": str(rows_path.relative_to(ROOT)), "sha256": sha256(rows_path), "rows": len(rows)},
        "current_hydro_context_csv": {"path": str(context_path.relative_to(ROOT)),
                                      "sha256": sha256(context_path), "rows": len(context_rows)},
        "weak_floor_failures_csv": {"path": str(failures_path.relative_to(ROOT)),
                                    "sha256": sha256(failures_path), "rows": len(fail_rows)},
    }
    results_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "eligible_cases": len(candidate_cases),
                      "eligible_rows": len(rows) - len(context_rows),
                      "context_rows": len(context_rows), "weak_floor_failures": len(fail_rows),
                      "qualified_candidates": results["weak_floor"]["qualified_candidates"],
                      "source_sha256": results["review_source_sha256"],
                      "results_json_sha256": sha256(results_path),
                      "results_csv_sha256": sha256(rows_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
