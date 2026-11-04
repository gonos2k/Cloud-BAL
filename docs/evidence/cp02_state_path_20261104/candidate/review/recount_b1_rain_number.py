#!/usr/bin/env python3
"""Independent point-loop recount of the frozen six-hour candidate arrays."""
from __future__ import annotations

import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[5]
CANDIDATE = ROOT / "docs/evidence/cp02_state_path_20261104/candidate"
ANALYSIS = CANDIDATE / "analysis"
REVIEW = CANDIDATE / "review"
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
CASES = ("ORIGINAL", "IMPROVED_BG_FIXED", "B1_RAIN_NUMBER_PRIOR")
COHORT_INDICES = {"P01": 476, "P02": 819, "P03": 439, "P04": 544,
                  "FA01": 582, "FA02": 899, "FA03": 1870, "FA04": 1772}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pin(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path),
            "size_bytes": path.stat().st_size}


def load_arrays() -> dict[int, dict[str, np.ndarray]]:
    arrays = {}
    for hour in range(13, 19):
        with np.load(ANALYSIS / f"hour_{hour}_arrays.npz") as archive:
            values = {name: archive[name].copy() for name in archive.files}
        required = {*CASES, "reference", "flat_index_yx", "latitude", "longitude"}
        if set(values) != required or any(values[n].shape != (3688,) for n in required):
            raise ValueError(f"invalid frozen sample array at hour {hour}")
        for name in (*CASES, "reference"):
            if not np.isfinite(values[name]).all():
                raise ValueError(f"nonfinite {name} at hour {hour}")
        arrays[hour - 12] = values
    return arrays


def recount(arrays: dict[int, dict[str, np.ndarray]]) -> tuple[list[dict], list[dict], list[dict]]:
    categorical, continuous = [], []
    for lead in range(1, 7):
        values = arrays[lead]
        for case in CASES:
            obs = values["reference"]
            pred = values[case]
            hits = misses = false_alarms = 0
            errors, squares = [], []
            for i in range(3688):
                err = float(pred[i]) - float(obs[i])
                errors.append(abs(err))
                squares.append(err * err)
                hits += int(obs[i] >= 0.1 and pred[i] >= 0.1)
                misses += int(obs[i] >= 0.1 and pred[i] < 0.1)
                false_alarms += int(obs[i] < 0.1 and pred[i] >= 0.1)
            continuous.append({"lead_hour": lead, "case": case,
                               "MAE_mm": math.fsum(errors) / 3688,
                               "RMSE_mm": math.sqrt(math.fsum(squares) / 3688)})
            for threshold in THRESHOLDS:
                h = m = f = 0
                for i in range(3688):
                    observed = float(obs[i]) >= threshold
                    forecast = float(pred[i]) >= threshold
                    h += int(observed and forecast)
                    m += int(observed and not forecast)
                    f += int(not observed and forecast)
                denominator = h + m + f
                if not denominator:
                    raise ValueError(f"undefined CSI at lead {lead}, {case}, {threshold}")
                categorical.append({"lead_hour": lead, "threshold_mm": threshold,
                                    "case": case, "points": 3688, "hit": h,
                                    "miss": m, "false_alarm": f,
                                    "CSI": float(Fraction(h, denominator))})

    keyed = {(r["lead_hour"], r["threshold_mm"], r["case"]): r for r in categorical}
    constraints = []
    for lead in range(1, 7):
        for threshold in THRESHOLDS:
            protected = lead == 1 or threshold == 5.0
            recovered = lead >= 2 and threshold in (0.1, 0.5, 1.0)
            if not (protected or recovered):
                continue
            baseline = "IMPROVED_BG_FIXED" if protected else "ORIGINAL"
            candidate = keyed[lead, threshold, "B1_RAIN_NUMBER_PRIOR"]
            control = keyed[lead, threshold, baseline]
            candidate_csi = Fraction(candidate["hit"], candidate["hit"] + candidate["miss"] + candidate["false_alarm"])
            control_csi = Fraction(control["hit"], control["hit"] + control["miss"] + control["false_alarm"])
            constraints.append({"goal": "preserve_current_B1" if protected else "recover_low_threshold_vs_ORIGINAL",
                                "lead_hour": lead, "threshold_mm": threshold, "baseline": baseline,
                                "candidate_hit": candidate["hit"], "candidate_miss": candidate["miss"],
                                "candidate_false_alarm": candidate["false_alarm"],
                                "baseline_hit": control["hit"], "baseline_miss": control["miss"],
                                "baseline_false_alarm": control["false_alarm"],
                                "candidate_csi_fraction": f"{candidate_csi.numerator}/{candidate_csi.denominator}",
                                "baseline_csi_fraction": f"{control_csi.numerator}/{control_csi.denominator}",
                                "satisfied": candidate_csi >= control_csi})
    if (len(categorical), len(continuous), len(constraints)) != (108, 18, 26):
        raise AssertionError("frozen scoring scope changed")
    return categorical, continuous, constraints


def band_counts(arrays: dict[int, dict[str, np.ndarray]]) -> list[dict]:
    bands = ((0.0, 0.1, "[0,0.1)"), (0.1, 1.0, "[0.1,1)"),
             (1.0, 5.0, "[1,5)"), (5.0, math.inf, "[5,inf)"))
    rows = []
    for lead, values in arrays.items():
        for lo, hi, label in bands:
            refs = values["reference"]
            selected = [i for i in range(3688) if float(refs[i]) >= lo and float(refs[i]) < hi]
            detected_old = sum(float(values["IMPROVED_BG_FIXED"][i]) >= 0.1 for i in selected)
            detected_new = sum(float(values["B1_RAIN_NUMBER_PRIOR"][i]) >= 0.1 for i in selected)
            gained = sum(float(values["IMPROVED_BG_FIXED"][i]) < 0.1 <= float(values["B1_RAIN_NUMBER_PRIOR"][i]) for i in selected)
            lost = sum(float(values["IMPROVED_BG_FIXED"][i]) >= 0.1 > float(values["B1_RAIN_NUMBER_PRIOR"][i]) for i in selected)
            rows.append({"lead_hour": lead, "observed_band_mm": label, "points": len(selected),
                         "detection_cut_mm": 0.1, "old_detected_IMPROVED_BG_FIXED": detected_old,
                         "new_detected_candidate": detected_new, "gained": gained, "lost": lost,
                         "net_change": detected_new - detected_old})
    return rows


def transition_counts(values: dict[str, np.ndarray], threshold: float) -> dict:
    """Count forecast transitions from current B1 to the candidate."""
    counts = {"hit_gains": 0, "hit_losses": 0, "false_alarm_gains": 0, "false_alarm_losses": 0}
    for i in range(3688):
        observed = float(values["reference"][i]) >= threshold
        old = float(values["IMPROVED_BG_FIXED"][i]) >= threshold
        new = float(values["B1_RAIN_NUMBER_PRIOR"][i]) >= threshold
        if observed and not old and new:
            counts["hit_gains"] += 1
        elif observed and old and not new:
            counts["hit_losses"] += 1
        elif not observed and not old and new:
            counts["false_alarm_gains"] += 1
        elif not observed and old and not new:
            counts["false_alarm_losses"] += 1
    return counts


def cohort_values(arrays: dict[int, dict[str, np.ndarray]]) -> list[dict]:
    rows = []
    values = arrays[2]
    for point_id, sample_index in COHORT_INDICES.items():
        actual_index = int(values["flat_index_yx"][sample_index])
        rows.append({"lead_hour": 2, "point_id": point_id, "sample_index": sample_index,
                     "flat_index_yx": actual_index,
                     "reference_mm": float(values["reference"][sample_index]),
                     "ORIGINAL_mm": float(values["ORIGINAL"][sample_index]),
                     "IMPROVED_BG_FIXED_mm": float(values["IMPROVED_BG_FIXED"][sample_index]),
                     "B1_RAIN_NUMBER_PRIOR_mm": float(values["B1_RAIN_NUMBER_PRIOR"][sample_index])})
    if len({r["flat_index_yx"] for r in rows}) != 8:
        raise ValueError("the eight frozen cohort sample indices do not map uniquely")
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    REVIEW.mkdir(parents=True, exist_ok=True)
    arrays = load_arrays()
    categorical, continuous, constraints = recount(arrays)
    bands = band_counts(arrays)
    cohorts = cohort_values(arrays)
    results = {
        "categorical_recount.csv": categorical,
        "continuous_recount.csv": continuous,
        "constraints_recount.csv": constraints,
        "observed_band_detection_cut_0p1.csv": bands,
        "cohort_plus2_recount.csv": cohorts,
    }
    for name, rows in results.items():
        write_csv(REVIEW / name, rows)

    # Check independent rows against the frozen published score tables by exact
    # integer counts and tolerance only for floating point diagnostic scores.
    with (ANALYSIS / "categorical_scores.csv").open(newline="") as stream:
        published_cat = list(csv.DictReader(stream))
    with (ANALYSIS / "continuous_scores.csv").open(newline="") as stream:
        published_cont = list(csv.DictReader(stream))
    with (ANALYSIS / "admission_constraints.csv").open(newline="") as stream:
        published_constraints = list(csv.DictReader(stream))
    by_cat = {(int(r["lead_hour"]), float(r["threshold_mm"]), r["case"]): r for r in published_cat}
    for r in categorical:
        p = by_cat[r["lead_hour"], r["threshold_mm"], r["case"]]
        for k in ("hit", "miss", "false_alarm", "points"):
            if int(p[k]) != int(r[k]):
                raise AssertionError(f"category mismatch: {r} vs {p}")
        if not math.isclose(float(p["CSI"]), r["CSI"], rel_tol=0.0, abs_tol=1e-15):
            raise AssertionError("published CSI differs from exact Fraction recount")
    by_cont = {(int(r["lead_hour"]), r["case"]): r for r in published_cont}
    for r in continuous:
        p = by_cont[r["lead_hour"], r["case"]]
        for k in ("MAE_mm", "RMSE_mm"):
            if not math.isclose(float(p[k]), r[k], rel_tol=0.0, abs_tol=1e-11):
                raise AssertionError(f"continuous mismatch at {r['lead_hour']} {r['case']} {k}")
    by_constraint = {(int(r["lead_hour"]), float(r["threshold_mm"])): r for r in published_constraints}
    for r in constraints:
        p = by_constraint[r["lead_hour"], r["threshold_mm"]]
        if (p["baseline"] != r["baseline"] or p["satisfied"].lower() != str(r["satisfied"]).lower()):
            raise AssertionError("frozen constraint does not match Fraction recount")

    lead2 = {(r["threshold_mm"], r["case"]): r for r in categorical if r["lead_hour"] == 2}
    delta5 = {k: lead2[(5.0, "B1_RAIN_NUMBER_PRIOR")][k] - lead2[(5.0, "IMPROVED_BG_FIXED")][k]
              for k in ("hit", "miss", "false_alarm")}
    trans01 = transition_counts(arrays[2], 0.1)
    trans5 = transition_counts(arrays[2], 5.0)
    trans1h25 = transition_counts(arrays[1], 2.5)
    weak = next(r for r in bands if r["lead_hour"] == 2 and r["observed_band_mm"] == "[0.1,1)")
    if (trans01["hit_gains"], trans01["hit_losses"], trans01["false_alarm_gains"], trans01["false_alarm_losses"]) != (12, 7, 21, 14):
        raise AssertionError(f"unexpected lead-2 0.1 transitions: {trans01}")
    if (trans5["hit_gains"], trans5["hit_losses"], lead2[(5.0, "IMPROVED_BG_FIXED")]["false_alarm"],
            lead2[(5.0, "B1_RAIN_NUMBER_PRIOR")]["false_alarm"]) != (0, 0, 105, 106):
        raise AssertionError(f"unexpected lead-2 threshold-5 transitions: {trans5}")
    if (trans1h25["false_alarm_gains"], trans1h25["false_alarm_losses"],
            trans1h25["hit_gains"], trans1h25["hit_losses"]) != (1, 0, 0, 0):
        raise AssertionError(f"unexpected lead-1 threshold-2.5 transitions: {trans1h25}")
    summary = {
        "scope": {"leads": 6, "common_points_each_lead": 3688, "categorical_rows": len(categorical),
                  "continuous_rows": len(continuous), "constraint_rows": len(constraints),
                  "calculation": "independent explicit point loops; Fraction exact CSI/constraint comparisons"},
        "lead2_t0p1_candidate_vs_IMPROVED_BG_FIXED_transitions": trans01,
        "lead2_t0p1_candidate_minus_ORIGINAL": {
            k: lead2[(0.1, "B1_RAIN_NUMBER_PRIOR")][k] - lead2[(0.1, "ORIGINAL")][k]
            for k in ("hit", "miss", "false_alarm")},
        "lead2_t5_candidate_minus_IMPROVED_BG_FIXED": delta5,
        "lead2_t5_contingency_IMPROVED_BG_FIXED": {k: lead2[(5.0, "IMPROVED_BG_FIXED")][k] for k in ("hit", "miss", "false_alarm")},
        "lead2_t5_contingency_candidate": {k: lead2[(5.0, "B1_RAIN_NUMBER_PRIOR")][k] for k in ("hit", "miss", "false_alarm")},
        "lead2_t5_candidate_vs_IMPROVED_BG_FIXED_transitions": trans5,
        "lead2_t5_candidate_vs_FIX_F": {
            "candidate_F": 2 * lead2[(5.0, "B1_RAIN_NUMBER_PRIOR")]["hit"] /
                (2 * lead2[(5.0, "B1_RAIN_NUMBER_PRIOR")]["hit"] + lead2[(5.0, "B1_RAIN_NUMBER_PRIOR")]["miss"] + lead2[(5.0, "B1_RAIN_NUMBER_PRIOR")]["false_alarm"]),
            "FIX_F": 2 * lead2[(5.0, "IMPROVED_BG_FIXED")]["hit"] /
                (2 * lead2[(5.0, "IMPROVED_BG_FIXED")]["hit"] + lead2[(5.0, "IMPROVED_BG_FIXED")]["miss"] + lead2[(5.0, "IMPROVED_BG_FIXED")]["false_alarm"]),
        },
        "lead2_actual_weak_band_0p1_to_1mm_at_detection_cut_0p1": weak,
        "constraints_passed": sum(r["satisfied"] for r in constraints),
        "lead1_threshold2p5_sample223": {
            case: {"reference_mm": float(arrays[1]["reference"][223]),
                   "prediction_mm": float(arrays[1][case][223]),
                   "detected_at_2p5": bool(float(arrays[1][case][223]) >= 2.5)}
            for case in ("ORIGINAL", "IMPROVED_BG_FIXED", "B1_RAIN_NUMBER_PRIOR")},
        "lead1_threshold2p5_candidate_vs_IMPROVED_BG_FIXED_transitions": trans1h25,
        "cohort_values": cohorts,
    }
    (REVIEW / "recount_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    pins = [CANDIDATE / "evaluation_plan.json", CANDIDATE / "runtime_evaluation_gate.json",
            ANALYSIS / "receipt.json", ANALYSIS / "categorical_scores.csv",
            ANALYSIS / "continuous_scores.csv", ANALYSIS / "admission_constraints.csv",
            ROOT / "tools/cp02_rain_number_evaluation.py"]
    pins += [ANALYSIS / f"hour_{hour}_arrays.npz" for hour in range(13, 19)]
    receipt = {"status": "PASS", "method": "standalone Python point-loop recount with exact Fraction comparisons",
               "script": pin(Path(__file__)), "inputs": [pin(p) for p in pins],
               "outputs": {name: {"sha256": sha256(REVIEW / name),
                                  "size_bytes": (REVIEW / name).stat().st_size}
                           for name in ("categorical_recount.csv", "continuous_recount.csv",
                                        "constraints_recount.csv", "observed_band_detection_cut_0p1.csv",
                                        "cohort_plus2_recount.csv", "recount_summary.json")}}
    (REVIEW / "recount_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
