#!/usr/bin/env python3
"""Render B1 two-hour diagnostic figures from frozen score/cohort tables.

The renderer performs no scoring and opens no native history. Process-trace
figures can be added after both OLD/FIX strict prefix gates pass.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


LEADS = tuple(range(1, 7))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
CASES = ("ORIGINAL", "ORIGINAL_B1_100", "IMPROVED_BG_FIXED")
CASE_LABELS = {
    "ORIGINAL": "규준실험 (ORIGINAL)",
    "ORIGINAL_B1_100": "기존 KDM6 (B1 OLD)",
    "IMPROVED_BG_FIXED": "0 과정률 수정 KDM6 (B1 FIX)",
}
COLORS = {"ORIGINAL": "#777777", "ORIGINAL_B1_100": "#2166ac", "IMPROVED_BG_FIXED": "#b2182b"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def load_scores(path: Path) -> dict[tuple[str, int, float], dict[str, str]]:
    rows = read_csv(path)
    required = {"lead_hour", "case", "threshold_mm", "CSI", "hit", "miss", "false_alarm"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"score table must contain columns: {', '.join(sorted(required))}")
    scores: dict[tuple[str, int, float], dict[str, str]] = {}
    for row in rows:
        case, lead, threshold = row["case"], int(row["lead_hour"]), float(row["threshold_mm"])
        key = (case, lead, threshold)
        if case in CASES:
            if key in scores:
                raise ValueError(f"duplicate selected score row: {key}")
            scores[key] = row
            expected = int(row["hit"]) / (int(row["hit"]) + int(row["miss"]) + int(row["false_alarm"]))
            if not np.isclose(float(row["CSI"]), expected, rtol=1e-12, atol=1e-15):
                raise ValueError(f"CSI inconsistent with contingency counts: {key}")
    expected_keys = {(case, lead, threshold) for case in CASES for lead in LEADS for threshold in THRESHOLDS}
    if set(scores) != expected_keys:
        missing, extra = expected_keys - set(scores), set(scores) - expected_keys
        raise ValueError(f"selected score keys incomplete (missing={len(missing)}, extra={len(extra)})")
    return scores


def draw_score_figures(scores: dict[tuple[str, int, float], dict[str, str]], out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.5), sharex=True, sharey=True, constrained_layout=True)
    for ax, threshold in zip(axes.flat, THRESHOLDS):
        for case in CASES:
            values = [float(scores[(case, lead, threshold)]["CSI"]) for lead in LEADS]
            ax.plot(LEADS, values, marker="o", linewidth=2, color=COLORS[case], label=CASE_LABELS[case])
        ax.set_title(f"≥{threshold:g} mm")
        ax.set_xticks(LEADS)
        ax.grid(alpha=0.25)
    axes[0, 0].set_ylabel("CSI")
    axes[1, 0].set_ylabel("CSI")
    for ax in axes[1, :]:
        ax.set_xlabel("Hourly forecast lead (h)")
    axes[0, 0].legend(frameon=False, fontsize=8)
    fig.suptitle("Hourly CSI by threshold — same B1 OLD/FIX pair and ORIGINAL context", fontsize=13)
    path = out / "b1_hourly_csi.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)

    delta_fix_old = np.array([
        [float(scores[("IMPROVED_BG_FIXED", lead, threshold)]["CSI"])
         - float(scores[("ORIGINAL_B1_100", lead, threshold)]["CSI"])
         for threshold in THRESHOLDS]
        for lead in LEADS
    ])
    delta_fix_original = np.array([
        [float(scores[("IMPROVED_BG_FIXED", lead, threshold)]["CSI"])
         - float(scores[("ORIGINAL", lead, threshold)]["CSI"])
         for threshold in THRESHOLDS]
        for lead in LEADS
    ])
    limit = max(abs(delta_fix_old).max(), abs(delta_fix_original).max())
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    for ax, data, title in (
        (axes[0], delta_fix_old, "FIX - OLD (same B1 input)"),
        (axes[1], delta_fix_original, "FIX - 규준실험 (ORIGINAL)"),
    ):
        image = ax.imshow(data, cmap="RdBu_r", vmin=-limit, vmax=limit, aspect="auto")
        ax.set_title(title)
        ax.set_xticks(range(len(THRESHOLDS)), [f"{t:g}" for t in THRESHOLDS])
        ax.set_yticks(range(len(LEADS)), [f"+{lead}" for lead in LEADS])
        ax.set_xlabel("One-hour precipitation threshold (mm)")
        ax.set_ylabel("Hourly lead")
        for i in range(len(LEADS)):
            for j in range(len(THRESHOLDS)):
                ax.text(j, i, f"{data[i, j]:+.4f}", ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=axes, label="ΔCSI (FIX - comparator)", shrink=0.82)
    fig.suptitle("Hourly ΔCSI; each lead and threshold remains separate", fontsize=13)
    delta_path = out / "b1_hourly_delta_csi.png"
    fig.savefig(delta_path, dpi=180)
    plt.close(fig)
    return [path, delta_path]


def draw_selected_points(path: Path, out: Path) -> Path:
    rows = read_csv(path)
    required = {"point_id", "diagnostic_group", "RN1_plus1_mm", "OLD_plus1_mm", "FIX_plus1_mm",
                "RN1_plus2_mm", "OLD_plus2_mm", "FIX_plus2_mm"}
    if len(rows) != 4 or not required.issubset(rows[0]):
        raise ValueError("selected_points.csv must contain exactly four frozen points and expected hourly fields")
    names = ("RN1", "OLD", "FIX")
    colors = ("#222222", COLORS["ORIGINAL_B1_100"], COLORS["IMPROVED_BG_FIXED"])
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for ax, row in zip(axes.flat, rows):
        for name, color in zip(names, colors):
            values = [float(row[f"{name}_plus{lead}_mm"]) for lead in (1, 2)]
            ax.plot((1, 2), values, marker="o", linewidth=2, color=color, label=name)
        max_value = max(float(row[f"{name}_plus{lead}_mm"]) for name in names for lead in (1, 2))
        ax.set_ylim(0, max(0.05, max_value * 1.15))
        ax.set_title(f"{row['point_id']} · {row['diagnostic_group'].replace('_', ' ')}")
        ax.set_xticks((1, 2), ("+1 h", "+2 h"))
        ax.set_ylabel("One-hour precipitation (mm)")
        ax.grid(alpha=0.25)
    axes[0, 0].legend(frameon=False)
    fig.suptitle("Frozen diagnostic locations: RN1 reference and same-B1 OLD/FIX\nindependent y scales by location", fontsize=13)
    output = out / "b1_selected_point_hourly_precip.png"
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return output


def csv_rows(path: Path):
    with path.open("rt", newline="", encoding="utf-8") as stream:
        yield from csv.DictReader(stream)


def process_profiles(components_path: Path) -> tuple[dict, dict, dict]:
    """Read canonical weighted local process components, keeping levels separate."""
    isolated = {arm: {name: {} for name in ("q_prevp", "t_prevp")} for arm in ("OLD", "FIX")}
    state = {arm: {name: {} for name in ("q_state", "t_state")} for arm in ("OLD", "FIX")}
    transitions = {arm: {} for arm in ("OLD", "FIX")}
    count_columns = {
        "raw_zero": "zero_raw_count",
        "negative_cap_to_applied": "zero_raw_sat_cap_negative_count",
        "cap_branch_skipped_final_zero": "zero_raw_sat_cap_absent_count",
        "sat_cap_present": "zero_raw_sat_cap_present_count",
        "final_negative": "zero_raw_final_negative_count",
        "final_positive": "zero_raw_final_positive_count",
        "final_negative_zero": "zero_raw_final_negative_zero_count",
        "final_positive_zero": "zero_raw_final_positive_zero_count",
    }
    for row in csv_rows(components_path):
        arm = row["arm"]
        point = row["point_id"]
        hour, level, weight = int(row["hour"]), int(row["k"]), float(row["weight"])
        key = (point, hour, level)
        for name, column in (("q_prevp", "delta_qv_prevp"), ("t_prevp", "delta_t_prevp")):
            isolated[arm][name][key] = isolated[arm][name].get(key, 0.0) + weight * float(row[column])
        for name, column in (("q_state", "delta_qv_state"), ("t_state", "delta_t_state")):
            state[arm][name][key] = state[arm][name].get(key, 0.0) + weight * float(row[column])
        group = (point, hour, row["corner"], level)
        counts = transitions[arm].setdefault(group, {name: 0 for name in count_columns})
        for name, column in count_columns.items():
            counts[name] += int(row[column])
    return isolated, state, transitions


def draw_vertical_profiles(isolated: dict, state: dict, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    arms = ("OLD", "FIX")
    colors = {"OLD": COLORS["ORIGINAL_B1_100"], "FIX": COLORS["IMPROVED_BG_FIXED"]}
    styles = {1: "-", 2: "--"}
    fig, axes = plt.subplots(4, 2, figsize=(13, 12), sharey=True, constrained_layout=True)
    for row_index, point in enumerate(("P01", "P02", "P03", "P04")):
        for col_index, (field, source, xlabel, title) in enumerate((
            ("q_prevp", isolated, "Δqv_PREVP (kg kg⁻¹, source mass basis)", "Rain–vapor exchange"),
            ("t_prevp", isolated, "ΔT_PREVP (K)", "Temperature contribution"),
        )):
            ax = axes[row_index, col_index]
            for arm in arms:
                for hour in (1, 2):
                    levels = sorted(k for p, h, k in source[arm][field] if p == point and h == hour)
                    values = [source[arm][field][(point, hour, level)] for level in levels]
                    arm_label = "기존 KDM6 (OLD)" if arm == "OLD" else "0 과정률 수정 KDM6 (FIX)"
                    ax.plot(values, levels, color=colors[arm], linestyle=styles[hour], linewidth=1.7,
                            label=f"{arm_label}, +{hour} h")
            ax.axvline(0.0, color="#777777", linewidth=0.7)
            ax.set_title(f"{point} · {title}")
            ax.set_ylim(1, 39)
            ax.set_xlabel(xlabel)
            ax.set_ylabel("Native model level k")
            ax.grid(alpha=0.22)
    axes[0, 0].legend(frameon=False, ncol=2, fontsize=8)
    fig.suptitle("Applied PREVP contribution by fixed native level; four corners bilinear-weighted", fontsize=13)
    path = out / "b1_prevp_qv_temperature_profiles.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)

    state_paths = []
    for field, xlabel, title in (("q_state", "Δqv at process update (kg kg⁻¹, source mass basis)", "Local process-update vapor state increment"),
                                 ("t_state", "ΔT at process update (K)", "Local process-update temperature state increment")):
        fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharey=True, constrained_layout=True)
        for ax, point in zip(axes.flat, ("P01", "P02", "P03", "P04")):
            for arm in arms:
                for hour in (1, 2):
                    levels = sorted(k for p, h, k in state[arm][field] if p == point and h == hour)
                    values = [state[arm][field][(point, hour, level)] for level in levels]
                    arm_label = "기존 KDM6 (OLD)" if arm == "OLD" else "0 과정률 수정 KDM6 (FIX)"
                    ax.plot(values, levels, color=colors[arm], linestyle=styles[hour], linewidth=1.7,
                            label=f"{arm_label}, +{hour} h")
            ax.axvline(0.0, color="#777777", linewidth=0.7)
            ax.set_title(point)
            ax.set_ylim(1, 39)
            ax.set_xlabel(xlabel)
            ax.set_ylabel("Native model level k")
            ax.grid(alpha=0.22)
        axes[0, 0].legend(frameon=False, ncol=2, fontsize=8)
        fig.suptitle(f"{title}; PRE_UPDATE to POST_STEP checkpoint, four corners bilinear-weighted", fontsize=13)
        output = out / f"b1_{field}_vertical_profiles.png"
        fig.savefig(output, dpi=180)
        plt.close(fig)
        state_paths.append(output)
    return [path, *state_paths]


def draw_zero_rate_level_corner(transitions: dict, out: Path) -> Path:
    corners = ("00", "01", "10", "11")
    fig, axes = plt.subplots(4, 2, figsize=(10, 12), sharex=True, constrained_layout=True)
    maximum = max(
        max((value["negative_cap_to_applied"] for value in transitions["OLD"].values()), default=0),
        max((value["cap_branch_skipped_final_zero"] for value in transitions["FIX"].values()), default=0),
    )
    image = None
    for row_index, point in enumerate(("P01", "P02", "P03", "P04")):
        for col_index, hour in enumerate((1, 2)):
            ax = axes[row_index, col_index]
            matrix = np.zeros((79, len(corners)))
            for corner_index, corner in enumerate(corners):
                for level in range(1, 40):
                    old = transitions["OLD"].get((point, hour, corner, level), {})
                    fix = transitions["FIX"].get((point, hour, corner, level), {})
                    matrix[level - 1, corner_index] = old.get("negative_cap_to_applied", 0)
                    matrix[40 + level - 1, corner_index] = fix.get("cap_branch_skipped_final_zero", 0)
            image = ax.imshow(matrix, origin="lower", aspect="auto", cmap="magma", vmin=0,
                              vmax=max(1, maximum), interpolation="nearest")
            ax.axhline(39.5, color="white", linewidth=1.0)
            ax.set_title(f"{point} · +{hour} h")
            ax.set_xticks(range(4), corners)
            ax.set_yticks((0, 19, 59, 78), ("1", "20", "20", "39"))
            ax.text(0.97, 0.75, "FIX", transform=ax.transAxes, va="center", ha="right", color="white",
                    fontsize=8, bbox={"facecolor": "black", "alpha": 0.55, "pad": 1})
            ax.text(0.97, 0.25, "OLD", transform=ax.transAxes, va="center", ha="right", color="white",
                    fontsize=8, bbox={"facecolor": "black", "alpha": 0.55, "pad": 1})
            ax.set_xlabel("Native corner")
    if image is not None:
        fig.colorbar(image, ax=axes, label="Zero-rate events per corner and level", shrink=0.82)
    fig.suptitle("Exact-zero PREVP_RAW: OLD negative SAT_CAP → negative final rate; FIX SAT_CAP branch absent\nlevels and native corners retained; blank SAT_CAP means branch absent, not a measured zero", fontsize=13)
    path = out / "b1_zero_rate_transitions_level_corner.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def draw_zero_rate_transitions(transitions: dict, out: Path) -> Path:
    points = ("P01", "P02", "P03", "P04")
    fig, axes = plt.subplots(1, 2, figsize=(13, 6), sharey=True, constrained_layout=True)
    width = 0.36
    x = np.arange(len(points))
    for ax, hour in zip(axes, (1, 2)):
        old_values = [sum_transition(transitions, "OLD", point, hour, "final_negative") for point in points]
        fix_values = [sum_transition(transitions, "FIX", point, hour, "final_negative") for point in points]
        old_bars = ax.bar(x - width / 2, old_values, width=width, color=COLORS["ORIGINAL_B1_100"],
                          label="OLD raw-zero → negative final rate")
        fix_bars = ax.bar(x + width / 2, fix_values, width=width, color=COLORS["IMPROVED_BG_FIXED"],
                          label="FIX raw-zero → negative final rate")
        ax.bar_label(old_bars, padding=3, fontsize=8)
        ax.bar_label(fix_bars, labels=[str(value) for value in fix_values], padding=3, fontsize=8)
        tick_labels = []
        for point in points:
            old_zero = sum_transition(transitions, "OLD", point, hour, "raw_zero")
            fix_zero = sum_transition(transitions, "FIX", point, hour, "raw_zero")
            fix_skipped = sum_transition(transitions, "FIX", point, hour, "cap_branch_skipped_final_zero")
            tick_labels.append(f"{point}\nraw0 O/F {old_zero}/{fix_zero}\nskip {fix_skipped}")
        ax.set_title(f"+{hour} h")
        ax.set_xticks(x, tick_labels)
        ax.set_ylabel("Exact-zero RAW events with negative final rate (count)")
        ax.set_xlabel("Point · raw-zero OLD/FIX · FIX cap-absent count")
        ax.grid(axis="y", alpha=0.22)
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("Same event definition for both series: PREVP_RAW = ±0 → final rate < 0\nFIX cap absence is annotated separately; an absent SAT_CAP is not a measured zero", fontsize=13)
    path = out / "b1_zero_rate_transitions.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def sum_transition(transitions: dict, arm: str, point: str, hour: int, field: str) -> int:
    return sum(values.get(field, 0) for (p, h, _corner, _level), values in transitions[arm].items()
               if p == point and h == hour)


def load_pair_summary(analysis_dir: Path, analysis_receipt: dict) -> dict:
    """Load the uniquely hash-bound pair summary, independent of its original path."""
    pair_path = analysis_dir / "pair_summary.json"
    matches = [entry for entry in analysis_receipt.get("analysis_outputs", [])
               if Path(entry.get("path", "")).name == pair_path.name]
    if (analysis_receipt.get("status") != "PASS_BOTH_ARMS" or len(matches) != 1
            or matches[0].get("sha256") != sha256(pair_path)
            or matches[0].get("bytes") != pair_path.stat().st_size):
        raise ValueError("pair_summary.json is not uniquely hash-bound by a passing analysis receipt")
    pair_summary = json.loads(pair_path.read_text(encoding="utf-8"))
    if pair_summary.get("status") != "PASS_BOTH_ARMS":
        raise ValueError("process plots require PASS_BOTH_ARMS analysis output")
    return pair_summary


def validate_inputs(args: argparse.Namespace) -> tuple[dict, list[dict[str, str]], dict, dict, dict]:
    """Validate all frozen inputs and build plot data before opening an output path."""
    scores = load_scores(args.scores)
    cohort_receipt_path = args.cohorts / "receipt.json"
    cohort_receipt = json.loads(cohort_receipt_path.read_text(encoding="utf-8"))
    selected_path = args.cohorts / "selected_points.csv"
    selected_pin = cohort_receipt.get("artifacts", {}).get("selected_points.csv", {})
    if (not selected_pin or selected_pin.get("sha256") != sha256(selected_path)
            or selected_pin.get("size_bytes") != selected_path.stat().st_size):
        raise ValueError("selected_points.csv does not match the frozen cohort receipt")
    selected_rows = read_csv(selected_path)
    required_selected = {"point_id", "diagnostic_group", "RN1_plus1_mm", "OLD_plus1_mm", "FIX_plus1_mm",
                         "RN1_plus2_mm", "OLD_plus2_mm", "FIX_plus2_mm"}
    if len(selected_rows) != 4 or not required_selected.issubset(selected_rows[0]):
        raise ValueError("selected_points.csv must contain exactly four frozen points and expected hourly fields")

    analysis_receipt = json.loads(args.analysis_receipt.read_text(encoding="utf-8"))
    pair_path = args.analysis_dir / "pair_summary.json"
    pair_summary = load_pair_summary(args.analysis_dir, analysis_receipt)

    component_receipt = json.loads(args.components_receipt.read_text(encoding="utf-8"))
    if (component_receipt.get("status") != "PASS_KEYED_LATENT_COMPONENT_DERIVATION"
            or component_receipt.get("run_receipt_sha256") != sha256(args.analysis_receipt)
            or component_receipt.get("output_sha256") != sha256(args.components)
            or component_receipt.get("output_bytes") != args.components.stat().st_size):
        raise ValueError("integrated component CSV is not bound to passing analysis and derivation receipts")
    isolated, state, transitions = process_profiles(args.components)
    old_zero = sum(values["raw_zero"] for values in transitions["OLD"].values())
    fix_zero = sum(values["raw_zero"] for values in transitions["FIX"].values())
    old_cap_negative = sum(values["negative_cap_to_applied"] for values in transitions["OLD"].values())
    old_final_negative = sum(values["final_negative"] for values in transitions["OLD"].values())
    fix_cap_absent = sum(values["cap_branch_skipped_final_zero"] for values in transitions["FIX"].values())
    fix_final_negative = sum(values["final_negative"] for values in transitions["FIX"].values())
    fix_final_zero = sum(values["final_negative_zero"] + values["final_positive_zero"]
                         for values in transitions["FIX"].values())
    if (old_zero, fix_zero, old_cap_negative, old_final_negative, fix_cap_absent, fix_final_negative) != (
        1185, 1542, 1025, 1025, 1542, 0
    ) or fix_final_zero != fix_cap_absent:
        raise ValueError("raw-zero activation counts differ from the frozen independent recount")
    return scores, selected_rows, pair_summary, (isolated, state, transitions), component_receipt


def render_figures(args: argparse.Namespace, out: Path, validated: tuple) -> dict:
    scores, selected_rows, pair_summary, process_data, component_receipt = validated
    isolated, state, transitions = process_data
    figures = draw_score_figures(scores, out)
    figures.append(draw_selected_points(args.cohorts / "selected_points.csv", out))
    figures.extend(draw_vertical_profiles(isolated, state, out))
    figures.append(draw_zero_rate_transitions(transitions, out))
    figures.append(draw_zero_rate_level_corner(transitions, out))
    inputs = {str(path.resolve()): {"sha256": sha256(path), "bytes": path.stat().st_size}
              for path in (args.scores, args.cohorts / "receipt.json", args.cohorts / "selected_points.csv",
                           args.analysis_receipt, args.components, args.components_receipt,
                           args.analysis_dir / "pair_summary.json", Path(__file__).resolve())}
    receipt = {
        "renderer": Path(__file__).name,
        "inputs": inputs,
        "analysis_status": pair_summary["status"],
        "component_run_receipt_sha256": component_receipt["run_receipt_sha256"],
        "scope": "validated compact per-arm/point/corner/level/hour components; local profiles retain each level",
        "exact_zero_raw_transitions": {
            arm: {f"{point}_hour{hour}": {
                      field: sum_transition(transitions, arm, point, hour, field)
                      for field in ("raw_zero", "negative_cap_to_applied",
                                    "cap_branch_skipped_final_zero", "sat_cap_present",
                                    "final_negative", "final_positive",
                                    "final_negative_zero", "final_positive_zero")}
                  for point in ("P01", "P02", "P03", "P04") for hour in (1, 2)}
            for arm in ("OLD", "FIX")
        },
        "figures": {path.name: {"sha256": sha256(path), "bytes": path.stat().st_size} for path in figures},
    }
    (out / "render_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohorts", type=Path, required=True, help="frozen cohort CSV directory")
    parser.add_argument("--scores", type=Path, required=True, help="unchanged full hourly categorical_scores.csv")
    parser.add_argument("--analysis-dir", type=Path, required=True, help="validated reduced OLD/FIX analysis output")
    parser.add_argument("--analysis-receipt", type=Path, required=True, help="hash-bound analyzer output receipt")
    parser.add_argument("--components", type=Path, required=True, help="key-joined weighted process components CSV")
    parser.add_argument("--components-receipt", type=Path, required=True, help="component derivation receipt")
    parser.add_argument("--out", type=Path, required=True, help="figure output directory")
    args = parser.parse_args()
    if "NanumBarunGothic" in {entry.name for entry in font_manager.fontManager.ttflist}:
        plt.rcParams["font.family"] = "NanumBarunGothic"
    plt.rcParams["axes.unicode_minus"] = False
    if args.out.exists() or args.out.is_symlink():
        raise FileExistsError(f"output path already exists; choose a fresh directory: {args.out}")
    validated = validate_inputs(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{args.out.name}.stage-", dir=args.out.parent))
    try:
        render_figures(args, stage, validated)
        os.replace(stage, args.out)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
