#!/usr/bin/env python3
"""Render paired six-hour QSNOW dose-response and selected-case figures."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np

BASELINE_CASES = ("ORIGINAL", "CURRENT_HYDRO", "IMPROVED_BG_FIXED")
ALPHA_SUFFIXES = ("000", "025", "050", "075", "125", "150")
ALPHA_VALUES = {"000": 0.0, "025": 0.25, "050": 0.5,
                "075": 0.75, "125": 1.25, "150": 1.5}
FAMILIES = ("CONTROL", "IMPROVED")
SENSITIVITY_CASES = tuple(f"{family}_SNOW_{suffix}"
                          for family in FAMILIES for suffix in ALPHA_SUFFIXES)
CASES = (*BASELINE_CASES, *SENSITIVITY_CASES)
CASE_ALPHA = {f"{family}_SNOW_{suffix}": ALPHA_VALUES[suffix]
              for family in FAMILIES for suffix in ALPHA_SUFFIXES}
CASE_FAMILY = {case: family for family in FAMILIES for case in SENSITIVITY_CASES
               if case.startswith(family + "_")}
CASE_LABELS = {"ORIGINAL": "규준 실험", "CURRENT_HYDRO": "기존 HYDRO",
               "IMPROVED_BG_FIXED": "기존 개선안"}
FAMILY_LABELS = {"CONTROL": "규준 계열 snow α", "IMPROVED": "개선 계열 snow α"}
CASE_COLORS = {"ORIGINAL": "#555555", "CURRENT_HYDRO": "#0072B2",
               "IMPROVED_BG_FIXED": "#D55E00", "CONTROL": "#0072B2", "IMPROVED": "#D55E00"}
HOURS = tuple(range(13, 19))
LEADS = tuple(range(1, 7))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
ALPHA_TICKS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5)
POINTS = 3688
EQUALITY_TOLERANCE = 1e-12
SELECTION_PLAN_SHA256 = "1a5e236793f276ba9781664980ad37f79efa565038b17e0e90aa916fe953d6ef"
ARRAY_KEYS = {"reference", *CASES, "latitude", "longitude", "flat_index_yx"}
TIME_FIELDS = {"valid_utc", "window_start_utc", "window_end_utc"}
CAT_FIELDS = {"lead_hour", *TIME_FIELDS, "case", "threshold_mm", "points", "hit", "miss",
              "false_alarm", "correct_dry", "CSI", "ETS", "POD", "FAR", "frequency_bias"}
CONT_FIELDS = {"lead_hour", *TIME_FIELDS, "case", "points", "mean_forecast_mm",
               "mean_reference_mm", "mean_error_mm", "MAE_mm", "RMSE_mm"}
TRANS_FIELDS = {"lead_hour", *TIME_FIELDS, "baseline", "candidate", "threshold_mm",
                "hit_gains", "hit_losses", "false_alarm_gains", "false_alarm_losses"}
SELECTION_FIELDS = {
    "case", "arm", "alpha", "first_hour_mean_CSI_6_thresholds", "first_hour_CSI_at_5mm",
    "first_hour_MAE_mm", "first_hour_RMSE_mm", "pooled_MAE_mm", "pooled_RMSE_mm", "feasible",
    "criterion_first_hour_CSI_at_5mm_at_least_alpha1", "criterion_first_hour_RMSE_at_most_alpha1",
    "criterion_pooled_6h_MAE_at_most_alpha1", "criterion_pooled_6h_RMSE_at_most_alpha1",
    "rank_all_cases", "rank_feasible_cases",
}
ELIGIBLE_CASES = ("ORIGINAL", "IMPROVED_BG_FIXED", *SENSITIVITY_CASES)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path}: missing columns {sorted(required - set(reader.fieldnames or ())) }")
        return list(reader)


def validate_window(row: dict[str, str], lead: int) -> None:
    start = datetime(2026, 8, 16, 11 + lead, tzinfo=timezone.utc)
    expected = {"valid_utc": start + timedelta(hours=1),
                "window_start_utc": start, "window_end_utc": start + timedelta(hours=1)}
    for field, target in expected.items():
        try:
            actual = datetime.fromisoformat(row[field].replace("Z", "+00:00"))
        except (ValueError, AttributeError) as error:
            raise ValueError(f"invalid {field} timestamp for lead +{lead}") from error
        if actual.tzinfo is None or actual.astimezone(timezone.utc) != target:
            raise ValueError(f"{field} does not match lead +{lead}'s one-hour UTC window")


def validate_receipt(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"scoring receipt must be a regular local file: {path}")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if (receipt.get("status") != "COMPLETE" or receipt.get("points_per_hour") != POINTS
            or receipt.get("cases") != list(CASES) or receipt.get("hours_utc") != list(HOURS)
            or tuple(float(value) for value in receipt.get("thresholds_mm", ())) != THRESHOLDS
            or receipt.get("precipitation_window")
            != "Hourly differences between consecutive WRF histories; not 0–lead accumulation."):
        raise ValueError("scoring receipt is incomplete or does not match the frozen 15-case design")
    sources = receipt.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("scoring receipt has no source hash records")
    for record in sources:
        digest = record.get("sha256")
        if (not isinstance(record.get("path"), str) or not record["path"]
                or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or not isinstance(record.get("size"), int) or record["size"] < 0):
            raise ValueError("scoring receipt contains a malformed source hash record")
    return receipt


def validate_analysis_outputs(analysis: Path, receipt: dict) -> list[Path]:
    expected = {*(f"hour_{hour}_arrays.npz" for hour in HOURS), "categorical_scores.csv",
                "continuous_scores.csv", "transitions.csv", "selection_scores.csv", "selection.json"}
    records = receipt.get("analysis_outputs")
    if not isinstance(records, dict) or set(records) != expected:
        raise ValueError("scoring receipt does not bind the complete snow-sensitivity outputs")
    paths = []
    for name, record in records.items():
        path = analysis / name
        digest = record.get("sha256") if isinstance(record, dict) else None
        size = record.get("size_bytes") if isinstance(record, dict) else None
        if (path.is_symlink() or not path.is_file() or not isinstance(size, int) or size < 0
                or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or path.stat().st_size != size
                or sha256(path) != digest):
            raise ValueError(f"analysis output hash mismatch: {path}")
        paths.append(path)
    return paths


def load_hour(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != ARRAY_KEYS:
            raise ValueError(f"{path}: unexpected NPZ keys {sorted(archive.files)}")
        data = {name: np.asarray(archive[name]) for name in archive.files}
    if any(value.shape != (POINTS,) for value in data.values()):
        raise ValueError(f"{path}: all arrays must contain exactly {POINTS} paired points")
    for name, values in data.items():
        if name == "flat_index_yx":
            if not np.issubdtype(values.dtype, np.integer) or np.unique(values).size != POINTS:
                raise ValueError(f"{path}: flat_index_yx must contain unique integers")
        elif not np.isfinite(values).all():
            raise ValueError(f"{path}: {name} contains non-finite values")
    if any((data[name] < 0).any() for name in ("reference", *CASES)):
        raise ValueError(f"{path}: precipitation totals must be nonnegative")
    if ((data["latitude"] < -90) | (data["latitude"] > 90)).any():
        raise ValueError(f"{path}: latitude outside [-90, 90]")
    if ((data["longitude"] < -180) | (data["longitude"] > 180)).any():
        raise ValueError(f"{path}: longitude outside [-180, 180]")
    return data


def close(actual: float, expected: float, label: str) -> None:
    if not np.isclose(actual, expected, rtol=1e-10, atol=1e-12):
        raise ValueError(f"score table mismatch for {label}: {actual} != {expected}")


def contingency(forecast: np.ndarray, reference: np.ndarray, threshold: float) -> tuple[np.ndarray, ...]:
    fwet, rwet = forecast >= threshold, reference >= threshold
    return fwet & rwet, ~fwet & rwet, fwet & ~rwet, ~fwet & ~rwet


def validate_selection(categorical: list[dict], continuous: list[dict], pooled: dict[str, dict],
                       rows: list[dict], selection: dict) -> str:
    row_by_case = {row["case"]: row for row in rows}
    if len(row_by_case) != len(ELIGIBLE_CASES) or set(row_by_case) != set(ELIGIBLE_CASES):
        raise ValueError("selection score table must contain all 14 eligible cases once")
    cat = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): row
           for row in categorical}
    cont = {(int(row["lead_hour"]), row["case"]): row for row in continuous}
    baseline = "IMPROVED_BG_FIXED"
    b_csi = float(cat[(1, baseline, 5.0)]["CSI"])
    b_rmse = float(cont[(1, baseline)]["RMSE_mm"])
    b_mae6 = float(pooled[baseline]["pooled_MAE_mm"])
    b_rmse6 = float(pooled[baseline]["pooled_RMSE_mm"])
    eligible_rows = []
    for case in ELIGIBLE_CASES:
        row = row_by_case[case]
        alpha = 1.0 if case in BASELINE_CASES else CASE_ALPHA[case]
        arm = "CONTROL" if case == "ORIGINAL" or CASE_FAMILY.get(case) == "CONTROL" else "IMPROVED"
        first_csi = np.asarray([float(cat[(1, case, threshold)]["CSI"])
                                for threshold in THRESHOLDS], dtype=np.float64)
        first_mae = float(cont[(1, case)]["MAE_mm"])
        first_rmse = float(cont[(1, case)]["RMSE_mm"])
        case_pool = pooled[case]
        criteria = {
            "first_hour_CSI_at_5mm_at_least_alpha1": float(cat[(1, case, 5.0)]["CSI"]) >= b_csi - EQUALITY_TOLERANCE,
            "first_hour_RMSE_at_most_alpha1": first_rmse <= b_rmse + EQUALITY_TOLERANCE,
            "pooled_6h_MAE_at_most_alpha1": float(case_pool["pooled_MAE_mm"]) <= b_mae6 + EQUALITY_TOLERANCE,
            "pooled_6h_RMSE_at_most_alpha1": float(case_pool["pooled_RMSE_mm"]) <= b_rmse6 + EQUALITY_TOLERANCE,
        }
        expected_values = {
            "arm": arm, "alpha": alpha,
            "first_hour_mean_CSI_6_thresholds": float(np.mean(first_csi)),
            "first_hour_CSI_at_5mm": float(cat[(1, case, 5.0)]["CSI"]),
            "first_hour_MAE_mm": first_mae, "first_hour_RMSE_mm": first_rmse,
            "pooled_MAE_mm": float(case_pool["pooled_MAE_mm"]),
            "pooled_RMSE_mm": float(case_pool["pooled_RMSE_mm"]),
        }
        for field, value in expected_values.items():
            if field == "arm":
                if row[field] != value:
                    raise ValueError(f"selection.{case}.arm does not match its case family")
            else:
                close(float(row[field]), float(value), f"selection.{case}.{field}")
        if any(_bool(row[f"criterion_{name}"]) != value for name, value in criteria.items()):
            raise ValueError(f"{case}: selection criterion flags do not match recomputed gates")
        feasible = all(criteria.values())
        if _bool(row["feasible"]) != feasible:
            raise ValueError(f"{case}: feasible flag does not match recomputed gates")
        eligible_rows.append({**expected_values, "case": case, "arm": arm, "feasible": feasible})
    rank = lambda item: (-item["first_hour_mean_CSI_6_thresholds"], item["first_hour_MAE_mm"],
                         item["first_hour_RMSE_mm"], abs(item["alpha"] - 1.0), item["case"])
    ranked = sorted(eligible_rows, key=rank)
    feasible_ranked = [item for item in ranked if item["feasible"]]
    all_ranks = {item["case"]: index for index, item in enumerate(ranked, 1)}
    feasible_ranks = {item["case"]: index for index, item in enumerate(feasible_ranked, 1)}
    failures = {}
    criteria_fields = (
        "criterion_first_hour_CSI_at_5mm_at_least_alpha1",
        "criterion_first_hour_RMSE_at_most_alpha1",
        "criterion_pooled_6h_MAE_at_most_alpha1",
        "criterion_pooled_6h_RMSE_at_most_alpha1",
    )
    for case in ELIGIBLE_CASES:
        row = row_by_case[case]
        if int(row["rank_all_cases"]) != all_ranks[case]:
            raise ValueError(f"{case}: all-case rank does not match the frozen ordering")
        expected_rank = feasible_ranks.get(case)
        actual_rank = row["rank_feasible_cases"]
        if (expected_rank is None and actual_rank not in ("", None)
                or expected_rank is not None and int(actual_rank) != expected_rank):
            raise ValueError(f"{case}: feasible rank does not match the frozen ordering")
        failed = [field.removeprefix("criterion_") for field in criteria_fields
                  if not _bool(row[field])]
        if failed:
            failures[case] = failed
    best_overall = feasible_ranked[0] if feasible_ranked else None
    best_improved = next((item for item in feasible_ranked if item["arm"] == "IMPROVED"), None)
    expected_overall = best_overall["case"] if best_overall else baseline
    expected_improved = best_improved["case"] if best_improved else baseline
    if (selection.get("best_eligible_overall_case") != expected_overall
            or float(selection.get("best_eligible_overall_alpha")) !=
            (best_overall["alpha"] if best_overall else 1.0)
            or selection.get("best_eligible_improved_case") != expected_improved
            or float(selection.get("best_eligible_improved_alpha")) !=
            (best_improved["alpha"] if best_improved else 1.0)
            or selection.get("ranking_all_eligible_cases") != [item["case"] for item in ranked]
            or selection.get("ranking_feasible_cases") != [item["case"] for item in feasible_ranked]
            or selection.get("feasibility_failures") != failures
            or selection.get("overall_fallback_used") != (best_overall is None or expected_overall == baseline)
            or selection.get("improved_fallback_used") != (best_improved is None or expected_improved == baseline)):
        raise ValueError("selection.json does not match the frozen eligibility, gates, and ranking")
    if selected_overall_case(selection) != expected_overall:
        raise ValueError("selection overall case is not the validated frozen winner")
    return expected_overall


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise ValueError(f"invalid boolean in selection table: {value!r}")


def selected_overall_case(selection: dict) -> str:
    """Resolve the frozen overall choice, including the alpha=1 fallback."""
    case = selection.get("best_eligible_overall_case")
    if case not in ELIGIBLE_CASES:
        raise ValueError(f"selection names an ineligible or unknown case: {case!r}")
    if case == "IMPROVED_BG_FIXED" and float(selection.get("best_eligible_overall_alpha")) != 1.0:
        raise ValueError("B1 fallback must retain its alpha=1 identity")
    return case


def display_case(case: str) -> str:
    if case in CASE_LABELS:
        return CASE_LABELS[case]
    if case not in CASE_ALPHA:
        raise ValueError(f"unknown snow sensitivity case: {case}")
    return f"{FAMILY_LABELS[CASE_FAMILY[case]]} (α={CASE_ALPHA[case]:g})"


def exploratory_label(case: str, selection: dict) -> str:
    failures = selection.get("feasibility_failures", {}).get(case, [])
    reason = "선정 조건 미통과" if failures else "선정 결과와 별도 탐색"
    if "first_hour_RMSE_at_most_alpha1" in failures:
        reason = "+1 h RMSE 기준 미통과"
    return f"탐색 비교 · 미선정 ({display_case(case)}; {reason})"


def validate_scores(analysis: Path, hours: dict[int, dict[str, np.ndarray]]) -> tuple[list, list, list, list, dict, dict]:
    categorical = read_csv(analysis / "categorical_scores.csv", CAT_FIELDS)
    continuous = read_csv(analysis / "continuous_scores.csv", CONT_FIELDS)
    transitions = read_csv(analysis / "transitions.csv", TRANS_FIELDS)
    selection_rows = read_csv(analysis / "selection_scores.csv", SELECTION_FIELDS)
    selection = json.loads((analysis / "selection.json").read_text(encoding="utf-8"))
    cat_by_key, cont_by_key, trans_by_key = {}, {}, {}
    for row in categorical:
        lead = int(row["lead_hour"]); validate_window(row, lead)
        key = (lead, row["case"], float(row["threshold_mm"]))
        if key in cat_by_key:
            raise ValueError(f"duplicate categorical row: {key}")
        cat_by_key[key] = row
    expected_cat = {(lead, case, threshold) for lead in LEADS for case in CASES for threshold in THRESHOLDS}
    if set(cat_by_key) != expected_cat:
        raise ValueError("categorical table must have exactly 540 case/hour/threshold rows")
    for row in continuous:
        lead = int(row["lead_hour"]); validate_window(row, lead)
        key = (lead, row["case"])
        if key in cont_by_key:
            raise ValueError(f"duplicate continuous row: {key}")
        cont_by_key[key] = row
    expected_cont = {(lead, case) for lead in LEADS for case in CASES}
    if set(cont_by_key) != expected_cont:
        raise ValueError("continuous table must have exactly 90 case/hour rows")
    for row in transitions:
        lead = int(row["lead_hour"]); validate_window(row, lead)
        key = (lead, row["baseline"], row["candidate"], float(row["threshold_mm"]))
        if key in trans_by_key:
            raise ValueError(f"duplicate transition row: {key}")
        trans_by_key[key] = row
    expected_trans = {(lead, baseline, case, threshold) for lead in LEADS
                      for baseline in ("ORIGINAL", "IMPROVED_BG_FIXED")
                      for case in SENSITIVITY_CASES for threshold in THRESHOLDS}
    if set(trans_by_key) != expected_trans:
        raise ValueError("transition table must have exactly 864 expected rows")

    for lead in LEADS:
        values = hours[lead + 12]
        reference = values["reference"]
        for case in CASES:
            forecast = values[case]
            error = forecast - reference
            row = cont_by_key[(lead, case)]
            if int(row["points"]) != POINTS:
                raise ValueError(f"{case} lead +{lead}: continuous point count mismatch")
            for field, value in (("mean_forecast_mm", np.mean(forecast)),
                                 ("mean_reference_mm", np.mean(reference)),
                                 ("mean_error_mm", np.mean(error)),
                                 ("MAE_mm", np.mean(np.abs(error))),
                                 ("RMSE_mm", np.sqrt(np.mean(error ** 2)))):
                close(float(row[field]), float(value), f"{case} lead +{lead}.{field}")
            for threshold in THRESHOLDS:
                hit, miss, false_alarm, correct_dry = contingency(forecast, reference, threshold)
                row = cat_by_key[(lead, case, threshold)]
                actual_counts = tuple(int(row[field]) for field in ("hit", "miss", "false_alarm", "correct_dry"))
                expected_counts = tuple(int(np.count_nonzero(mask))
                                         for mask in (hit, miss, false_alarm, correct_dry))
                if int(row["points"]) != POINTS or actual_counts != expected_counts:
                    raise ValueError(f"{case} lead +{lead} at {threshold:g} mm: contingency mismatch")
                denom = sum(expected_counts[:3])
                csi = expected_counts[0] / denom if denom else 0.0
                close(float(row["CSI"]), csi, f"{case} lead +{lead}.CSI@{threshold:g}")
        for baseline in ("ORIGINAL", "IMPROVED_BG_FIXED"):
            for case in SENSITIVITY_CASES:
                for threshold in THRESHOLDS:
                    base_hit, _, base_fa, _ = contingency(values[baseline], reference, threshold)
                    new_hit, _, new_fa, _ = contingency(values[case], reference, threshold)
                    row = trans_by_key[(lead, baseline, case, threshold)]
                    expected = (int(np.count_nonzero(~base_hit & new_hit)),
                                int(np.count_nonzero(base_hit & ~new_hit)),
                                int(np.count_nonzero(~base_fa & new_fa)),
                                int(np.count_nonzero(base_fa & ~new_fa)))
                    actual = tuple(int(row[field]) for field in (
                        "hit_gains", "hit_losses", "false_alarm_gains", "false_alarm_losses"))
                    if actual != expected:
                        raise ValueError(f"transition counts mismatch for {case} lead +{lead} {threshold:g} mm")

    pooled = {}
    for case in CASES:
        reference = np.concatenate([hours[hour]["reference"].astype(np.float64) for hour in HOURS])
        forecast = np.concatenate([hours[hour][case].astype(np.float64) for hour in HOURS])
        error = forecast - reference
        pooled[case] = {"pooled_MAE_mm": float(np.mean(np.abs(error))),
                        "pooled_RMSE_mm": float(np.sqrt(np.mean(error ** 2)))}
    best_case = validate_selection(categorical, continuous, pooled, selection_rows, selection)
    exploratory_case = selection["ranking_all_eligible_cases"][0]
    if exploratory_case not in ELIGIBLE_CASES:
        raise ValueError("unfiltered ranking starts with an ineligible case")
    return (categorical, continuous, transitions, selection_rows, selection, pooled,
            best_case, exploratory_case)


def map_fields(hour_data: dict[str, np.ndarray], selected_case: str,
               exploratory_case: str | None = None,
               selection: dict | None = None) -> tuple[tuple[str, str], ...]:
    if selected_case not in CASES:
        raise ValueError(f"selected case is absent from the snow-sweep design: {selected_case}")
    fields = (("reference", "RN1 분석"), ("ORIGINAL", CASE_LABELS["ORIGINAL"]),
              ("IMPROVED_BG_FIXED", CASE_LABELS["IMPROVED_BG_FIXED"]))
    result = list(fields)
    if selected_case not in BASELINE_CASES:
        result.append((selected_case, f"선택 결과 · {display_case(selected_case)}"))
    if exploratory_case is not None:
        if exploratory_case not in ELIGIBLE_CASES:
            raise ValueError(f"exploratory case is ineligible or unknown: {exploratory_case}")
        if exploratory_case not in {field for field, _ in result}:
            label = exploratory_label(exploratory_case, selection or {})
            result.append((exploratory_case, label))
    return tuple(result)


def save_figure(figure, stage: Path, name: str) -> None:
    figure.savefig(stage / f"{name}.png", dpi=240, bbox_inches="tight", facecolor="white")
    figure.savefig(stage / f"{name}.pdf", bbox_inches="tight", facecolor="white",
                   metadata={"CreationDate": None, "ModDate": None,
                             "Creator": "plot_snow_sensitivity.py"})
    figure.savefig(stage / f"{name}.svg", bbox_inches="tight", facecolor="white",
                   metadata={"Date": None, "Creator": "plot_snow_sensitivity.py"})


def dose_response_figure(plt, selection_rows: list[dict], best_case: str,
                        exploratory_case: str, selection: dict, stage: Path) -> None:
    from matplotlib.lines import Line2D

    rows = {row["case"]: row for row in selection_rows}
    fig, axes = plt.subplots(2, 2, figsize=(13.2, 8.2))
    metrics = (("first_hour_mean_CSI_6_thresholds", "First-hour mean CSI · six thresholds", True),
               ("first_hour_CSI_at_5mm", "First-hour CSI · 5-mm threshold", True),
               ("pooled_MAE_mm", "Pooled six-hour MAE", False),
               ("pooled_RMSE_mm", "Pooled six-hour RMSE", False))
    alpha_x = np.asarray([ALPHA_VALUES[suffix] for suffix in ALPHA_SUFFIXES])
    for ax, (field, title, higher_better) in zip(axes.flat, metrics):
        for family in FAMILIES:
            case_order = [f"{family}_SNOW_{suffix}" for suffix in ALPHA_SUFFIXES]
            values = [float(rows[case][field]) for case in case_order]
            ax.plot(alpha_x, values, color=CASE_COLORS[family], marker="o",
                    markersize=4.5, linewidth=1.8, label=FAMILY_LABELS[family])
            if exploratory_case in case_order:
                exploratory_index = case_order.index(exploratory_case)
                ax.scatter(alpha_x[exploratory_index], values[exploratory_index], marker="*", s=105,
                           facecolor="white", edgecolor="#111111", linewidth=0.9, zorder=5)
        if best_case in BASELINE_CASES:
            ax.scatter(1.0, float(rows[best_case][field]), marker="D", s=35,
                       color=CASE_COLORS[best_case], edgecolor="#111111", linewidth=0.55,
                       zorder=5)
        if field == "first_hour_mean_CSI_6_thresholds":
            ax.axhline(float(rows["IMPROVED_BG_FIXED"][field]), color=CASE_COLORS["IMPROVED_BG_FIXED"],
                       linestyle="--", linewidth=1.3, label="기존 개선안 · B1")
            ax.axhline(float(rows["ORIGINAL"][field]), color=CASE_COLORS["ORIGINAL"],
                       linestyle=":", linewidth=1.3, label="규준 실험")
        elif field == "first_hour_CSI_at_5mm":
            ax.axhline(float(rows["IMPROVED_BG_FIXED"][field]), color=CASE_COLORS["IMPROVED_BG_FIXED"],
                       linestyle="--", linewidth=1.3, label="기존 개선안 · B1")
            ax.axhline(float(rows["ORIGINAL"][field]), color=CASE_COLORS["ORIGINAL"],
                       linestyle=":", linewidth=1.3, label="규준 실험")
        else:
            ax.axhline(float(rows["IMPROVED_BG_FIXED"][field]), color=CASE_COLORS["IMPROVED_BG_FIXED"],
                       linestyle="--", linewidth=1.3, label="기존 개선안 · B1")
            ax.axhline(float(rows["ORIGINAL"][field]), color=CASE_COLORS["ORIGINAL"],
                       linestyle=":", linewidth=1.3, label="규준 실험")
        ax.set(title=title + (" · higher is better" if higher_better else " · lower is better"),
               xlabel="QSNOW scaling factor α", xticks=ALPHA_TICKS)
        ax.set_ylabel("CSI" if "CSI" in field else "mm")
        ax.grid(alpha=0.24)
    handles = [Line2D([0], [0], color=CASE_COLORS[family], marker="o", linewidth=1.8,
                      label=FAMILY_LABELS[family]) for family in FAMILIES]
    handles += [Line2D([0], [0], color=CASE_COLORS["ORIGINAL"], linestyle=":",
                       linewidth=1.3, label="규준 실험"),
                Line2D([0], [0], color=CASE_COLORS["IMPROVED_BG_FIXED"], linestyle="--",
                       linewidth=1.3, label="기존 개선안 · B1")]
    if best_case in BASELINE_CASES:
        handles.append(Line2D([0], [0], marker="D", color="#111111", linestyle="none",
                              label=f"선정 결과 · {display_case(best_case)} (α=1)", markersize=6))
    if exploratory_case in SENSITIVITY_CASES:
        handles.append(Line2D([0], [0], marker="*", color="none", markerfacecolor="white",
                              markeredgecolor="#111111",
                              label=exploratory_label(exploratory_case, selection), markersize=9))
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.99),
               ncol=4, frameon=False, fontsize=8.5)
    fig.suptitle("QSNOW alpha 민감도: 첫 시간 CSI와 6시간 pooled error",
                 y=1.035, fontsize=14, fontweight="semibold")
    fig.tight_layout(rect=(0, 0.02, 1, 0.9), w_pad=2.2, h_pad=2.0)
    fig.text(0.5, 0.0,
             "한 사례의 여섯 개 1시간 누적자료(각 3,688개 paired 지점)에서 계산. "
             "Pooled 오차는 6개 시간창 표본의 평균이며 6시간 누적강수가 아님. "
             "민감도 진단으로 독립 검증이나 운영 적합성 판정이 아님.",
             ha="center", fontsize=8, color="#444444")
    save_figure(fig, stage, "snow_alpha_dose_response")
    plt.close(fig)


def csi_comparison_figure(plt, categorical: list[dict], best_case: str,
                          exploratory_case: str, selection: dict, stage: Path) -> None:
    from matplotlib.colors import TwoSlopeNorm

    csi = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): float(row["CSI"])
           for row in categorical}
    def matrix(case):
        return np.asarray([[csi[(lead, case, threshold)] for threshold in THRESHOLDS]
                           for lead in LEADS])
    control = matrix("ORIGINAL")
    b1 = matrix("IMPROVED_BG_FIXED")
    selected = matrix(best_case)
    exploratory = matrix(exploratory_case)
    absolute_cases = list(dict.fromkeys(("ORIGINAL", "IMPROVED_BG_FIXED", best_case,
                                         exploratory_case)))
    def absolute_title(case: str) -> str:
        if case == best_case:
            return f"선정 결과 · {display_case(case)}"
        if case == exploratory_case:
            return exploratory_label(case, selection)
        return CASE_LABELS.get(case, display_case(case))

    panels = [(matrix(case), absolute_title(case), False) for case in absolute_cases]
    differences = []
    if best_case != "ORIGINAL":
        differences.append((selected - control, "ΔCSI · 선정 − 규준 실험"))
    if best_case != "IMPROVED_BG_FIXED":
        differences.append((selected - b1, "ΔCSI · 선정 − 기존 개선안"))
    if exploratory_case != "ORIGINAL":
        differences.append((exploratory - control, "ΔCSI · 탐색 − 규준 실험"))
    if exploratory_case != "IMPROVED_BG_FIXED":
        differences.append((exploratory - b1, "ΔCSI · 탐색 − 기존 개선안"))
    panels.extend((values, title, True) for values, title in differences)
    diff_limit = max(0.05, math.ceil(max(float(np.max(np.abs(values)))
                                         for values, _, is_delta in panels if is_delta) / 0.05) * 0.05)
    fig, axes_grid = plt.subplots(2, 3, figsize=(16.0, 9.0), squeeze=False,
                                  gridspec_kw={"hspace": 0.5, "wspace": 0.38})
    axes = list(axes_grid.flat)
    for ax in axes[len(panels):]:
        ax.set_visible(False)
    for index, (ax, (values, title, is_delta)) in enumerate(zip(axes, panels)):
        if is_delta:
            norm = TwoSlopeNorm(vmin=-diff_limit, vcenter=0, vmax=diff_limit)
            image = ax.imshow(values, origin="upper", aspect="auto", cmap="RdBu_r",
                              norm=norm, interpolation="nearest")
        else:
            image = ax.imshow(values, origin="upper", aspect="auto", cmap="YlGnBu",
                              vmin=0, vmax=1, interpolation="nearest")
        for y in range(6):
            for x in range(6):
                value = values[y, x]
                text = f"{value:+.4f}" if is_delta else f"{value:.3f}"
                dark = (abs(value) < 0.62 * diff_limit) if is_delta else (value < 0.62)
                ax.text(x, y, text, ha="center", va="center", fontsize=7.5,
                        color="#17212b" if dark else "white")
        ax.set_title(title, fontsize=9, fontweight="semibold")
        ax.set_xticks(range(6), [f"{value:g}" for value in THRESHOLDS], fontsize=7.5)
        ax.set_yticks(range(6), [f"+{lead}" for lead in LEADS], fontsize=7.5)
        ax.set_xlabel("1-h accumulation threshold (mm)", fontsize=8)
        ax.set_ylabel("Lead (h)", fontsize=8)
        ax.set_xticks(np.arange(-0.5, 6, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, 6, 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=1.2)
        ax.tick_params(which="minor", bottom=False, left=False)
        colorbar = fig.colorbar(image, ax=ax, fraction=0.05, pad=0.03)
        colorbar.set_label("ΔCSI" if is_delta else "CSI", fontsize=8)
        colorbar.ax.tick_params(labelsize=7)
    fig.suptitle("Selected and exploratory QSNOW comparisons across leads and thresholds",
                 y=0.99, fontsize=14, fontweight="semibold")
    failed_gates = selection.get("feasibility_failures", {}).get(exploratory_case, [])
    reason = ("+1 h RMSE guard failed" if "first_hour_RMSE_at_most_alpha1" in failed_gates
              else "not selected under the frozen guardrails")
    fig.text(0.5, 0.015,
             f"Exploratory comparison: {display_case(exploratory_case)}; {reason}. "
             "Cells use the same 3,688 paired points; ΔCSI is a score contrast, not physical attribution.",
             ha="center", fontsize=8.5, color="#444444")
    save_figure(fig, stage, "selected_case_csi_comparison")
    plt.close(fig)


def error_figure(plt, continuous: list[dict], best_case: str,
                 exploratory_case: str, selection: dict, stage: Path) -> None:
    values = {(int(row["lead_hour"]), row["case"]): row for row in continuous}
    cases = tuple(dict.fromkeys(("ORIGINAL", "IMPROVED_BG_FIXED", best_case, exploratory_case)))
    labels = {case: CASE_LABELS.get(case, display_case(case)) for case in cases}
    labels[best_case] = f"선정 결과 · {display_case(best_case)}"
    labels[exploratory_case] = exploratory_label(exploratory_case, selection)
    if exploratory_case == best_case:
        labels[exploratory_case] = f"선정 결과 · {display_case(best_case)}"
    unique_cases = cases
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.4))
    for ax, field, title in zip(axes, ("MAE_mm", "RMSE_mm"),
                                ("MAE · lower is better", "RMSE · lower is better")):
        for case in unique_cases:
            color = ("#7A3E9D" if case == exploratory_case else
                     CASE_COLORS[case] if case in CASE_COLORS else CASE_COLORS[CASE_FAMILY[case]])
            marker = "o"
            linestyle = "-"
            markersize = 4.3
            if case == best_case and best_case in BASELINE_CASES:
                marker, linestyle, markersize = "D", "--", 4.8
            elif case == exploratory_case:
                marker, markersize = "*", 6.0
            ax.plot(LEADS, [float(values[(lead, case)][field]) for lead in LEADS],
                    color=color,
                    marker=marker, markersize=markersize, linestyle=linestyle,
                    linewidth=1.7, label=labels[case])
        ax.set(title=title, xlabel="Forecast lead (h)", ylabel="mm per 1-h window", xticks=LEADS)
        ax.grid(alpha=0.24); ax.set_axisbelow(True)
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", bbox_to_anchor=(0.5, 1.0),
               ncol=3, frameon=False, fontsize=8.7)
    fig.suptitle("Six one-hour error scores: selected and exploratory comparison",
                 y=1.08, fontsize=13.5, fontweight="semibold")
    fig.tight_layout(rect=(0, 0.02, 1, 0.82), w_pad=1.8)
    failed_gates = selection.get("feasibility_failures", {}).get(exploratory_case, [])
    reason = ("+1 h RMSE guard failed" if "first_hour_RMSE_at_most_alpha1" in failed_gates
              else "not selected under the frozen guardrails")
    fig.text(0.5, -0.005,
             f"Six-hour pooled error is in the dose-response panel. Exploratory {display_case(exploratory_case)}: "
             f"{reason}; per-hour scores remain visible here.",
             ha="center", fontsize=8, color="#444444")
    save_figure(fig, stage, "selected_case_hourly_errors")
    plt.close(fig)


def map_figure(plt, hours: dict[int, dict[str, np.ndarray]], leads: tuple[int, ...],
               extent: tuple[float, float, float, float], best_case: str,
               exploratory_case: str, selection: dict, stage: Path) -> None:
    from matplotlib.colors import BoundaryNorm, ListedColormap

    levels = (0, 0.1, 0.5, 1, 2.5, 5, 10, 20, 50, 100)
    colors = ("#f3f4f6", "#c6dbef", "#9ecae1", "#6baed6", "#41b6c4",
              "#1d91c0", "#225ea8", "#253494", "#4a1486")
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(levels, cmap.N, clip=True)
    first_fields = map_fields(hours[leads[0] + 12], best_case, exploratory_case, selection)
    columns = len(first_fields)
    figure, axes = plt.subplots(len(leads), columns,
                                figsize=(4.0 * columns, 3.25 * len(leads)),
                                sharex=True, sharey=True, layout="constrained")
    scatter = None
    for row, lead in enumerate(leads):
        hour = lead + 12
        values = hours[hour]
        fields = map_fields(values, best_case, exploratory_case, selection)
        lon, lat = values["longitude"], values["latitude"]
        for column, (field, label) in enumerate(fields):
            ax = axes[row, column]
            scatter = ax.scatter(lon, lat, c=values[field], cmap=cmap, norm=norm,
                                s=7.5, marker="s", linewidths=0, rasterized=True)
            if row == 0:
                ax.set_title(label, loc="left", fontsize=9.5, fontweight="semibold")
            if column == 0:
                ax.set_ylabel(f"+{lead} h\nLatitude (°N)")
            if row == len(leads) - 1:
                ax.set_xlabel("Longitude (°E)")
            ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
            ax.set_aspect(1.0 / np.cos(np.deg2rad(float(np.mean(lat)))))
            ax.grid(color="white", linewidth=0.3, alpha=0.55)
    colorbar = figure.colorbar(scatter, ax=axes, orientation="horizontal", pad=0.065,
                               fraction=0.035, ticks=levels, extend="max")
    colorbar.set_label("One-hour precipitation accumulation (mm)")
    start_hour = leads[0] + 11
    end_hour = leads[-1] + 12
    figure.suptitle(f"눈 민감도 · +{leads[0]}–+{leads[-1]} h · "
                    f"{start_hour:02d}:00–{end_hour:02d}:00 UTC · 선정: {display_case(best_case)} · "
                    f"탐색: {display_case(exploratory_case)}",
                    fontsize=13, fontweight="semibold")
    figure.text(0.5, -0.005,
                "Markers show retained paired points only; no interpolation or coverage extrapolation. "
                "RN1 is a processed analysis, not gauge truth. 탐색 비교는 선정 결과가 아님.",
                ha="center", va="top", fontsize=8, color="#444444")
    name = f"snow_sensitivity_maps_leads_{leads[0]}_{leads[-1]}"
    save_figure(figure, stage, name)
    plt.close(figure)


def publish(stage: Path, output: Path) -> None:
    backup_root = Path(tempfile.mkdtemp(prefix=f".{output.name}.backup-", dir=output.parent))
    backup = backup_root / "existing-output"
    moved_old = False
    try:
        if output.exists():
            os.replace(output, backup)
            moved_old = True
        os.replace(stage, output)
    except BaseException:
        if moved_old and not output.exists() and backup.exists():
            os.replace(backup, output)
        raise
    else:
        shutil.rmtree(backup_root)
    finally:
        if backup_root.exists() and not backup.exists():
            shutil.rmtree(backup_root)


def run(analysis: Path, output: Path) -> dict:
    if output.is_symlink():
        raise ValueError(f"output must not be a symlink: {output}")
    if output.exists() and not output.is_dir():
        raise ValueError(f"output exists and is not a directory: {output}")
    receipt_path = analysis / "receipt.json"
    receipt = validate_receipt(receipt_path)
    receipt_digest = sha256(receipt_path)
    input_paths = validate_analysis_outputs(analysis, receipt)
    selection_plan = analysis.parent / "selection_plan.json"
    if sha256(selection_plan) != SELECTION_PLAN_SHA256:
        raise ValueError("frozen snow selection plan hash mismatch")
    renderer_path = Path(__file__).resolve()
    renderer_digest = sha256(renderer_path)
    hours = {hour: load_hour(analysis / f"hour_{hour}_arrays.npz") for hour in HOURS}
    first = hours[HOURS[0]]
    for hour in HOURS[1:]:
        for name in ("flat_index_yx", "latitude", "longitude"):
            if not np.array_equal(first[name], hours[hour][name]):
                raise ValueError(f"hour {hour}: paired grid identity differs for {name}")
    (categorical, continuous, transitions, selection_rows, selection, pooled,
     best_case, exploratory_case) = validate_scores(analysis, hours)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "Noto Sans CJK JP", "font.size": 9,
                         "axes.titlesize": 10, "axes.labelsize": 9,
                         "svg.fonttype": "none", "svg.hashsalt": "snow-sensitivity-v1",
                         "pdf.fonttype": 42})
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        dose_response_figure(plt, selection_rows, best_case, exploratory_case, selection, stage)
        csi_comparison_figure(plt, categorical, best_case, exploratory_case, selection, stage)
        error_figure(plt, continuous, best_case, exploratory_case, selection, stage)
        lon, lat = first["longitude"], first["latitude"]
        extent = (float(lon.min()), float(lon.max()), float(lat.min()), float(lat.max()))
        map_figure(plt, hours, (1, 2, 3), extent, best_case, exploratory_case, selection, stage)
        map_figure(plt, hours, (4, 5, 6), extent, best_case, exploratory_case, selection, stage)
        if (sha256(receipt_path) != receipt_digest or sha256(renderer_path) != renderer_digest
                or sha256(selection_plan) != SELECTION_PLAN_SHA256):
            raise ValueError("score receipt, frozen plan, or renderer changed during figure generation")
        validate_analysis_outputs(analysis, receipt)
        inputs = [*input_paths, receipt_path]
        manifest = {
            "schema": "snow_sensitivity_figures_v1", "status": "COMPLETE",
            "renderer": {"path": str(renderer_path), "sha256": renderer_digest,
                         "size_bytes": renderer_path.stat().st_size},
            "receipt_sha256": receipt_digest,
            "cases": list(CASES), "hours_utc": list(HOURS), "lead_hours": list(LEADS),
            "thresholds_mm": list(THRESHOLDS), "paired_points_per_hour": POINTS,
            "display_labels": CASE_LABELS.copy(),
            "selected_best_case": best_case,
            "exploratory_comparison_case": exploratory_case,
            "exploratory_comparison_selected": exploratory_case == best_case,
            "exploratory_comparison_rank_all_eligible_cases":
                selection.get("ranking_all_eligible_cases", []).index(exploratory_case) + 1,
            "exploratory_comparison_failed_gates": selection.get("feasibility_failures", {}).get(
                exploratory_case, []),
            "exploratory_comparison_interpretation":
                ("Top unfiltered rank is shown as an exploratory comparison; it was not selected."
                 if exploratory_case != best_case else
                 "Top unfiltered rank and selected case are the same eligible experiment."),
            "selection_plan_sha256": SELECTION_PLAN_SHA256,
            "selected_best_alpha": selection.get("best_eligible_overall_alpha"),
            "selected_best_improved_case": selection.get("best_eligible_improved_case"),
            "selected_best_improved_alpha": selection.get("best_eligible_improved_alpha"),
            "selection_basis": "Frozen eligible-case ranking with four B1 guardrails; B1 fallback when no eligible case outranks it.",
            "selection_feasible_cases": selection.get("ranking_feasible_cases", []),
            "selection_rule": "Eligible: ORIGINAL, IMPROVED_BG_FIXED, and 12 QSNOW variants. Gates: CSI@5mm first hour ≥ B1; first-hour RMSE and pooled 6-hour MAE/RMSE ≤ B1 within 1e-12. Rank by first-hour mean CSI, first-hour MAE/RMSE, |alpha−1|, then case ID; B1 fallback.",
            "accumulation_definition": "Each forecast value/score is a one-hour increment over its valid window, not a 0-to-lead cumulative total.",
            "inputs": [{"path": str(path.resolve()), "sha256": sha256(path),
                        "size_bytes": path.stat().st_size} for path in [*inputs, selection_plan]],
            "reference_limitation": receipt.get("reference_limitation", ""),
            "provenance_note": "Renderer verifies receipt schema and sealed analysis-output hashes, then recomputes categorical, continuous, transition, pooled-error, and selection results from the paired arrays. It does not reopen original host files; runtime/source provenance remains in the scorer receipt audit.",
            "scope": "QSNOW alpha diagnostics across two experiment families; one spatial case, six one-hour windows, 3,688 unweighted paired points per hour. Not a balanced or operational initialization.",
            "rain_points_ge_threshold_by_hour": {
                str(hour): {name: {f"{threshold:g} mm": int(np.count_nonzero(hours[hour][name] >= threshold))
                                   for threshold in THRESHOLDS}
                            for name in ("reference", "ORIGINAL", "IMPROVED_BG_FIXED", best_case)}
                for hour in HOURS
            },
            "figures": ["snow_alpha_dose_response", "selected_case_csi_comparison",
                        "selected_case_hourly_errors", "snow_sensitivity_maps_leads_1_3",
                        "snow_sensitivity_maps_leads_4_6"],
            "figure_sha256": {path.name: sha256(path) for path in sorted(stage.iterdir())},
        }
        (stage / "figure_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8")
        publish(stage, output)
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return json.loads((output / "figure_manifest.json").read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(
        "docs/evidence/snow_sensitivity_20261030/figures"))
    args = parser.parse_args()
    print(json.dumps(run(args.analysis_dir, args.output_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
