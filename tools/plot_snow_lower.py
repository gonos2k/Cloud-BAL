#!/usr/bin/env python3
"""Render lower-factor QSNOW sensitivity scores and hourly maps."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

PLAN_SHA256 = "8d30f3f7a3d82a34332013334d5f0d6c66f1a1576198db228b98b1a89c950cf2"
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
HOURS = tuple(range(13, 19))
LEADS = tuple(range(1, 7))
POINTS = 3688
PRECIPITATION_LEVELS = (0, 0.1, 0.5, 1, 2.5, 5, 10, 20, 50, 100)
FAMILIES = ("CONTROL", "IMPROVED")
FACTORS = (0, 25, 50, 60, 70, 75, 80, 90, 110, 120, 125, 130, 140, 150, 175, 200, 250, 300)
VARIANTS = tuple(f"{family}_SNOW_{factor:03d}" for family in FAMILIES for factor in FACTORS)
NEW_FACTORS = (110, 120, 130, 140)
NEW_CASES = tuple(f"{family}_SNOW_{factor:03d}" for family in FAMILIES for factor in NEW_FACTORS)
FOCUSED_CASES = ("ORIGINAL", *(f"{family}_SNOW_{factor:03d}"
                                  for factor in (50, 60, 70, 80, 90)
                                  for family in FAMILIES))
ALL_CASES = ("ORIGINAL", "CURRENT_HYDRO", "IMPROVED_BG_FIXED", *VARIANTS)
BASE_CASES = ("ORIGINAL", "CURRENT_HYDRO", "IMPROVED_BG_FIXED",
              *(f"{family}_SNOW_{factor:03d}" for family in FAMILIES for factor in FACTORS[:6]))
ELIGIBLE = tuple(case for case in ALL_CASES if case != "CURRENT_HYDRO")
ARRAY_KEYS = {"reference", *ALL_CASES, "latitude", "longitude", "flat_index_yx"}
LABELS = {"ORIGINAL": "규준 실험 α=1.0", "CURRENT_HYDRO": "기존 HYDRO (참고)",
          "IMPROVED_BG_FIXED": "기존 개선안 B1 (α=1.0)"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def display_case(case: str) -> str:
    if case in LABELS:
        return LABELS[case]
    family, _, suffix = case.split("_")
    family_label = "규준 계열" if family == "CONTROL" else "개선 계열"
    return f"{family_label} α={int(suffix) / 100:g}"


def axis_case_label(case: str, focused: bool = False) -> str:
    if case == "ORIGINAL":
        return "α=1.0"
    if case == "IMPROVED_BG_FIXED":
        return "B1 α=1.0"
    if case == "CURRENT_HYDRO":
        return "HYDRO"
    family, _, suffix = case.split("_")
    factor = f"{int(suffix) / 100:g}"
    return f"{'C' if family == 'CONTROL' else 'I'}{factor}" if focused else f"α={factor}"


def delta_csi(candidate: float, control: float) -> float:
    """Return candidate CSI minus control CSI for one threshold and lead."""
    return float(candidate) - float(control)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def validate_window(row: dict, lead: int) -> None:
    end = datetime(2026, 8, 16, 12 + lead, tzinfo=timezone.utc)
    expected = {"valid_utc": end, "window_start_utc": end - timedelta(hours=1),
                "window_end_utc": end}
    if int(row["valid_obs"]) != POINTS:
        raise ValueError("score row does not use the frozen paired-point count")
    for field, target in expected.items():
        try:
            actual = datetime.fromisoformat(row[field].replace("Z", "+00:00"))
        except (ValueError, AttributeError) as error:
            raise ValueError(f"invalid {field} timestamp for lead +{lead}") from error
        if actual.tzinfo is None or actual.astimezone(timezone.utc) != target:
            raise ValueError(f"{field} does not match lead +{lead}'s one-hour UTC window")


def verify_analysis(analysis: Path) -> tuple[dict, list[dict], list[dict], list[dict], tuple[str, ...]]:
    receipt_path = analysis / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("status") not in ("COMPLETE", "PARTIAL"):
        raise ValueError("lower-sensitivity score receipt has no usable complete score tables")
    outputs = receipt.get("analysis_outputs")
    if not isinstance(outputs, dict):
        raise ValueError("score receipt has no analysis output hashes")
    for name, record in outputs.items():
        path = analysis / name
        if (path.is_symlink() or not path.is_file()
                or path.stat().st_size != record.get("size_bytes")
                or sha256(path) != record.get("sha256")):
            raise ValueError(f"analysis output hash mismatch: {name}")
    plan_path = analysis.parent / "selection_plan.json"
    if sha256(plan_path) != PLAN_SHA256:
        raise ValueError("frozen lower-sensitivity selection plan hash mismatch")
    cat = read_csv(analysis / "categorical_scores.csv")
    cont = read_csv(analysis / "continuous_scores.csv")
    for row in (*cat, *cont):
        validate_window(row, int(row["lead_hour"]))
    selection_rows = read_csv(analysis / "selection_scores.csv")
    cases = tuple(receipt.get("cases", ()))
    eligible = tuple(case for case in cases if case != "CURRENT_HYDRO")
    if (not set(BASE_CASES).issubset(cases) or set(cases) != set(ALL_CASES)
            or len(cases) != len(ALL_CASES) or len(set(cases)) != len(cases)):
        raise ValueError("score receipt does not contain the complete 39-case grid")
    if len(cat) != len(cases) * len(LEADS) * len(THRESHOLDS) or len(cont) != len(cases) * len(LEADS):
        raise ValueError("score tables do not cover every scored case and lead hour")
    cat_keys = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])) for row in cat}
    cont_keys = {(int(row["lead_hour"]), row["case"]) for row in cont}
    expected_cat = {(lead, case, threshold) for lead in LEADS for case in cases for threshold in THRESHOLDS}
    expected_cont = {(lead, case) for lead in LEADS for case in cases}
    if cat_keys != expected_cat or cont_keys != expected_cont:
        raise ValueError("score table coverage or keys do not match the frozen design")
    if len({row["case"] for row in selection_rows}) != len(selection_rows):
        raise ValueError("selection table contains duplicate case rows")
    if not set(eligible).issubset({row["case"] for row in selection_rows}):
        raise ValueError("selection table omits a scored eligible case")
    return receipt, cat, cont, selection_rows, cases


def rank_cases(categorical: list[dict], continuous: list[dict],
               cases: tuple[str, ...] | None = None) -> list[str]:
    cat = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): row
           for row in categorical}
    cont = {(int(row["lead_hour"]), row["case"]): row for row in continuous}
    ranked = []
    def metric(row: dict, field: str) -> float | None:
        value = row.get(field)
        return None if value in (None, "", "None") else float(value)

    eligible_cases = cases or tuple(case for case in ALL_CASES if case != "CURRENT_HYDRO")
    for case in eligible_cases:
        csi10 = metric(cat[(1, case, 10.0)], "CSI")
        csi5 = metric(cat[(1, case, 5.0)], "CSI")
        far10 = metric(cat[(1, case, 10.0)], "FAR")
        suffix = case.rsplit("_", 1)[-1]
        factor_code = int(suffix) if case in VARIANTS else 100
        ranked.append((case, csi10, csi5, far10,
                       metric(cont[(1, case)], "RMSE_mm"), abs(factor_code - 100)))
    ranked.sort(key=lambda item: (
        item[1] is None, 0 if item[1] is None else -item[1],
        item[2] is None, 0 if item[2] is None else -item[2],
        item[3] is None, 0 if item[3] is None else item[3],
        item[4] is None, 0 if item[4] is None else item[4], item[5], item[0]))
    return [item[0] for item in ranked]


def selected_case(selection: dict, eligible: tuple[str, ...] = ELIGIBLE) -> str:
    case = selection.get("selected_case")
    if case not in eligible:
        raise ValueError(f"selected case is ineligible or unknown: {case!r}")
    return case


def map_fields(case: str) -> tuple[tuple[str, str], ...]:
    if case not in ALL_CASES:
        raise ValueError(f"unknown experiment: {case}")
    return ("reference", "RN1 분석"), (case, display_case(case))


def expected_coverage(cases: tuple[str, ...]) -> tuple[set[tuple], set[tuple]]:
    score_keys = {(lead, case, threshold) for lead in LEADS for case in cases
                  for threshold in THRESHOLDS}
    map_keys = {(case, lead) for case in cases for lead in LEADS}
    return score_keys, map_keys


def validate_figure_coverage(manifest: dict, cases: tuple[str, ...], selected: str) -> None:
    groups = case_groups(cases)
    expected_groups = {name: list(group) for name, group in groups}
    expected_heatmaps = {
        f"delta_csi/{group_name}/delta_csi_t{threshold_slug(threshold)}.png"
        for threshold in THRESHOLDS for group_name, _ in groups
    }
    expected_csi_heatmaps = {
        f"csi/{group_name}/csi_t{threshold_slug(threshold)}.png"
        for threshold in THRESHOLDS for group_name, _ in groups
    }
    expected_focused_csi = {
        f"focused/low_factor_csi_t{threshold_slug(threshold)}.png" for threshold in THRESHOLDS
    }
    expected_focused_delta = {
        f"focused/low_factor_delta_csi_t{threshold_slug(threshold)}.png" for threshold in THRESHOLDS
    }
    heatmaps = manifest.get("delta_csi_heatmaps", {})
    csi_heatmaps = manifest.get("csi_heatmaps", {})
    focused_csi = manifest.get("focused_csi_heatmaps", {})
    focused_delta = manifest.get("focused_delta_csi_heatmaps", {})
    maps = manifest.get("hourly_precipitation_maps", {})
    heatmap_coverage = manifest.get("heatmap_coverage", {})
    map_coverage = manifest.get("map_coverage", {})
    limits = heatmap_coverage.get("shared_color_limits")
    difference = manifest.get("pointwise_precipitation_difference", {})
    difference_limits = difference.get("shared_color_limits_mm")
    if (manifest.get("selected_case") != selected
            or manifest.get("context_only_cases") != ["CURRENT_HYDRO"]
            or set(heatmaps) != expected_heatmaps or set(csi_heatmaps) != expected_csi_heatmaps
            or set(focused_csi) != expected_focused_csi or set(focused_delta) != expected_focused_delta
            or set(maps) != set(cases)
            or heatmap_coverage.get("cases_per_page_groups") != expected_groups
            or set(heatmap_coverage.get("cases", ())) != set(cases)
            or heatmap_coverage.get("lead_hours") != list(LEADS)
            or heatmap_coverage.get("thresholds_mm") != list(THRESHOLDS)
            or heatmap_coverage.get("delta_cell_count") != len(cases) * len(LEADS) * len(THRESHOLDS)
            or heatmap_coverage.get("csi_cell_count") != len(cases) * len(LEADS) * len(THRESHOLDS)
            or heatmap_coverage.get("focused_delta_cell_count") != len(FOCUSED_CASES) * len(LEADS) * len(THRESHOLDS)
            or heatmap_coverage.get("focused_csi_cell_count") != len(FOCUSED_CASES) * len(LEADS) * len(THRESHOLDS)
            or set(map_coverage.get("cases", ())) != set(cases)
            or map_coverage.get("lead_hours") != list(LEADS)
            or map_coverage.get("case_lead_count") != len(cases) * len(LEADS)
            or difference.get("definition") != "P_case - P_ORIGINAL at the same lead and paired grid point"
            or difference.get("baseline_case") != "ORIGINAL"
            or difference.get("units") != "mm"
            or difference.get("point_count_per_lead") != POINTS
            or difference.get("cases") != list(cases)
            or difference.get("lead_hours") != list(LEADS)
            or difference.get("ORIGINAL_is_zero") is not True
            or not np.isfinite(difference.get("observed_min_mm", np.nan))
            or not np.isfinite(difference.get("observed_max_mm", np.nan))
            or not isinstance(difference_limits, list) or len(difference_limits) != 2
            or difference_limits[0] >= 0 or difference_limits[1] <= 0
            or difference_limits[0] != -difference_limits[1]
            or difference_limits[0] > difference.get("observed_min_mm", 0)
            or difference_limits[1] < difference.get("observed_max_mm", 0)
            or set(difference.get("source_sha256", {})) != {
                f"hour_{lead + 12}_difference_vs_original.npz" for lead in LEADS}
            or set(difference.get("source_size_bytes", {})) != {
                f"hour_{lead + 12}_difference_vs_original.npz" for lead in LEADS}
            or any(len(value) != 64 for value in difference.get("source_sha256", {}).values())
            or any(not isinstance(value, int) or value <= 0
                   for value in difference.get("source_size_bytes", {}).values())
            or not isinstance(limits, list) or len(limits) != 2 or limits[0] != -limits[1]):
        raise ValueError("figure manifest does not cover the full symmetric CSI and hourly-map grids")
    for threshold in THRESHOLDS:
        for group_name, group_cases in groups:
            name = f"delta_csi/{group_name}/delta_csi_t{threshold_slug(threshold)}.png"
            item = heatmaps[name]
            if (item.get("threshold_mm") != threshold or item.get("group") != group_name
                    or item.get("cases") != list(group_cases)
                    or item.get("lead_hours") != list(LEADS)
                    or item.get("color_limits") != limits
                    or item.get("delta_definition") != "CSI(experiment) - CSI(ORIGINAL; 규준 실험 α=1.0)"):
                raise ValueError(f"{name}: incorrect threshold, case group, leads, or shared scale")
            csi_name = f"csi/{group_name}/csi_t{threshold_slug(threshold)}.png"
            csi_item = csi_heatmaps[csi_name]
            if (csi_item.get("threshold_mm") != threshold or csi_item.get("group") != group_name
                    or csi_item.get("cases") != list(group_cases)
                    or csi_item.get("lead_hours") != list(LEADS)
                    or csi_item.get("color_limits") != [0.0, 1.0]):
                raise ValueError(f"{csi_name}: incorrect threshold, case group, leads, or scale")
        focused_csi_name = f"focused/low_factor_csi_t{threshold_slug(threshold)}.png"
        focused_delta_name = f"focused/low_factor_delta_csi_t{threshold_slug(threshold)}.png"
        for name, items, limits in (
                (focused_csi_name, focused_csi, [0.0, 1.0]),
                (focused_delta_name, focused_delta, heatmap_coverage.get("shared_color_limits"))):
            item = items[name]
            if (item.get("threshold_mm") != threshold or item.get("cases") != list(FOCUSED_CASES)
                    or item.get("lead_hours") != list(LEADS)
                    or item.get("color_limits") != limits):
                raise ValueError(f"{name}: incorrect focused case list, threshold, leads, or scale")
    bins = map_coverage.get("common_precipitation_bins_mm")
    if bins != list(PRECIPITATION_LEVELS):
        raise ValueError("hourly precipitation maps must use the frozen common color bins")
    for case, item in maps.items():
        if (item.get("lead_hours") != list(LEADS)
                or item.get("panels_per_lead") != ["reference", case, "case_minus_ORIGINAL"]
                or item.get("precipitation_bins_mm") != bins):
            raise ValueError(f"{case}: hourly map does not use shared bins and paired RN1 coverage")
        if item.get("difference_color_limits_mm") != difference_limits:
            raise ValueError(f"{case}: hourly difference map does not use the common scale")
    required_assets = set()
    for name in (*expected_heatmaps, *(item["figure"] for item in maps.values())):
        stem = name[:-4]
        required_assets.add(f"{stem}.png")
    required_assets.update(csi_heatmaps)
    required_assets.update(focused_csi)
    required_assets.update(focused_delta)
    if not required_assets.issubset(manifest.get("figure_sha256", {})):
        raise ValueError("figure hashes omit one or more linked PNG assets")


def case_groups(cases: tuple[str, ...]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    control = tuple(sorted((case for case in cases if case.startswith("CONTROL_SNOW_")),
                           key=lambda case: int(case.rsplit("_", 1)[-1])))
    improved = tuple(sorted((case for case in cases if case.startswith("IMPROVED_SNOW_")),
                            key=lambda case: int(case.rsplit("_", 1)[-1])))
    groups = (
        ("control", ("ORIGINAL", *control)),
        ("improved", ("IMPROVED_BG_FIXED", *improved)),
        ("context", tuple(case for case in cases if case == "CURRENT_HYDRO")),
    )
    flattened = tuple(case for _, group in groups for case in group)
    if len(flattened) != len(cases) or set(flattened) != set(cases):
        raise ValueError("case groups must partition all scored experiments exactly once")
    return groups


def threshold_slug(threshold: float) -> str:
    return format(threshold, "g").replace(".", "p")


def load_arrays(analysis: Path, cases: tuple[str, ...]) -> dict[int, dict[str, np.ndarray]]:
    array_keys = {"reference", *cases, "latitude", "longitude", "flat_index_yx"}
    hours = {}
    for hour in HOURS:
        path = analysis / f"hour_{hour}_arrays.npz"
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != array_keys:
                raise ValueError(f"{path}: array fields differ from expected cases")
            data = {key: np.asarray(archive[key]) for key in archive.files}
        if any(values.shape != (POINTS,) for values in data.values()):
            raise ValueError(f"{path}: expected {POINTS} paired values per field")
        for key, values in data.items():
            if key == "flat_index_yx":
                if not np.issubdtype(values.dtype, np.integer) or np.unique(values).size != POINTS:
                    raise ValueError(f"{path}: paired indices must be unique integers")
            elif not np.isfinite(values).all():
                raise ValueError(f"{path}: {key} contains non-finite values")
        if any((data[key] < 0).any() for key in ("reference", *cases)):
            raise ValueError(f"{path}: precipitation values must be nonnegative")
        hours[hour] = data
    first = hours[HOURS[0]]
    for hour in HOURS[1:]:
        if any(not np.array_equal(first[key], hours[hour][key])
               for key in ("flat_index_yx", "latitude", "longitude")):
            raise ValueError(f"hour {hour}: paired grid differs")
    return hours


def load_precipitation_differences(
        analysis: Path, cases: tuple[str, ...], hours: dict[int, dict[str, np.ndarray]]) -> tuple[
            dict[int, dict[str, np.ndarray]], dict[str, str], dict[str, int]]:
    keys = {"reference", "flat_index_yx", "latitude", "longitude", *cases}
    differences = {}
    source_hashes = {}
    source_sizes = {}
    for hour in HOURS:
        path = analysis / f"hour_{hour}_difference_vs_original.npz"
        source_hashes[path.name] = sha256(path)
        source_sizes[path.name] = path.stat().st_size
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != keys:
                raise ValueError(f"{path}: difference fields differ from expected cases")
            values = {key: np.asarray(archive[key]) for key in archive.files}
        if any(value.shape != (POINTS,) for value in values.values()):
            raise ValueError(f"{path}: expected {POINTS} paired differences per field")
        source = hours[hour]
        for key in ("flat_index_yx", "latitude", "longitude", "reference"):
            if not np.array_equal(values[key], source[key]):
                raise ValueError(f"{path}: paired-grid metadata differs from source arrays")
        for case in cases:
            expected = source[case].astype(np.float64) - source["ORIGINAL"].astype(np.float64)
            if not np.isfinite(values[case]).all() or not np.array_equal(values[case], expected):
                raise ValueError(f"{path}: {case} differences do not equal same-point P_case − P_ORIGINAL")
        if not np.array_equal(values["ORIGINAL"], np.zeros(POINTS, dtype=values["ORIGINAL"].dtype)):
            raise ValueError(f"{path}: ORIGINAL difference must be exactly zero")
        differences[hour] = values
    return differences, source_hashes, source_sizes


def precipitation_difference_color_scale(
        differences: dict[int, dict[str, np.ndarray]], cases: tuple[str, ...]) -> tuple[float, float, list[float]]:
    values = np.concatenate([differences[hour][case] for hour in HOURS for case in cases])
    if not np.isfinite(values).all():
        raise ValueError("pointwise precipitation differences contain non-finite values")
    observed_min, observed_max = float(values.min()), float(values.max())
    limit = max(0.1, float(np.ceil(max(abs(observed_min), abs(observed_max)) * 10) / 10))
    return observed_min, observed_max, [-limit, limit]


def save_figure(fig, stage: Path, name: str) -> None:
    base = stage / name
    base.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(base.with_suffix(".png"), dpi=240, bbox_inches="tight", facecolor="white")


def render(analysis: Path, output: Path) -> dict:
    if output.is_symlink() or output.exists() and not output.is_dir():
        raise ValueError(f"figure output must be a regular directory path: {output}")
    receipt, categorical, continuous, selection_rows, cases = verify_analysis(analysis)
    receipt_digest = sha256(analysis / "receipt.json")
    renderer_digest = sha256(Path(__file__).resolve())
    eligible = tuple(case for case in cases if case != "CURRENT_HYDRO")
    selection = json.loads((analysis / "selection.json").read_text(encoding="utf-8"))
    order = rank_cases(categorical, continuous, eligible)
    if selection.get("selection_order") != order:
        raise ValueError("selection order does not match the frozen metric ranking")
    best = selected_case(selection, eligible)
    if order[0] != best:
        raise ValueError("selected case is not the top ranked eligible experiment")
    hours = load_arrays(analysis, cases)
    differences, difference_hashes, difference_sizes = load_precipitation_differences(
        analysis, cases, hours)
    difference_min, difference_max, difference_limits = precipitation_difference_color_scale(
        differences, cases)
    difference_limit = difference_limits[1]
    from matplotlib.colors import TwoSlopeNorm as DifferenceNorm
    difference_norm = DifferenceNorm(vmin=-difference_limit, vcenter=0.0, vmax=difference_limit)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    plt.rcParams.update({"font.family": "Noto Sans CJK JP", "font.size": 9})
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    cat = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): row
           for row in categorical}
    groups = case_groups(cases)
    delta_by_key = {}
    delta_values = []
    for threshold in THRESHOLDS:
        for lead in LEADS:
            for case in cases:
                candidate = cat[(lead, case, threshold)]["CSI"]
                control = cat[(lead, "ORIGINAL", threshold)]["CSI"]
                value = (np.nan if candidate in ("", "None") or control in ("", "None")
                         else delta_csi(float(candidate), float(control)))
                delta_by_key[(lead, case, threshold)] = value
                if np.isfinite(value):
                    delta_values.append(abs(value))
    max_delta = max(delta_values) if delta_values else 0.0
    limit = max(0.02, float(np.ceil(max_delta / 0.02) * 0.02))
    from matplotlib.colors import TwoSlopeNorm
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    group_titles = {"control": "규준 계열", "improved": "개선 계열", "context": "참고 실험"}
    heatmap_manifest = {}
    csi_manifest = {}
    focused_csi_manifest = {}
    focused_delta_manifest = {}
    for threshold in THRESHOLDS:
        for group_name, group_cases in groups:
            matrix = np.asarray([
                [delta_by_key[(lead, case, threshold)] for case in group_cases]
                for lead in LEADS
            ], dtype=np.float64)
            fig_width = max(6.6, len(group_cases) * 0.86)
            fig, ax = plt.subplots(figsize=(fig_width, 5.6), layout="constrained")
            image = ax.imshow(matrix, cmap="RdBu_r", norm=norm, aspect="auto",
                              interpolation="nearest")
            for row in range(len(LEADS)):
                for col in range(len(group_cases)):
                    value = matrix[row, col]
                    ax.text(col, row, "—" if np.isnan(value) else f"{value:+.4f}",
                            ha="center", va="center", fontsize=7,
                            color="#17212b" if np.isnan(value) or abs(value) < 0.58 * limit else "white")
            ax.set_title(f"규준 실험 α=1.0 대비 CSI 차이 ≥{threshold:g} mm · {group_titles[group_name]}")
            ax.set_xticks(range(len(group_cases)), [axis_case_label(case) for case in group_cases],
                          rotation=48, ha="right", fontsize=7.5)
            ax.set_yticks(range(len(LEADS)), [f"+{lead} h" for lead in LEADS])
            ax.set_xlabel("실험")
            ax.set_ylabel("예측시간")
            ax.set_xticks(np.arange(-0.5, len(group_cases), 1), minor=True)
            ax.set_yticks(np.arange(-0.5, len(LEADS), 1), minor=True)
            ax.grid(which="minor", color="white", linewidth=1.0)
            ax.tick_params(which="minor", bottom=False, left=False)
            fig.colorbar(image, ax=ax, label=f"ΔCSI = 실험 − 규준 실험 α=1.0 (공통 범위 ±{limit:.3f})")
            fig.suptitle(f"강수 임계값 ≥{threshold:g} mm · lead별 CSI 차이")
            name = f"delta_csi/{group_name}/delta_csi_t{threshold_slug(threshold)}"
            save_figure(fig, stage, name)
            plt.close(fig)
            heatmap_manifest[f"{name}.png"] = {
                "threshold_mm": threshold, "group": group_name,
                "cases": list(group_cases), "lead_hours": list(LEADS),
                "delta_definition": "CSI(experiment) - CSI(ORIGINAL; 규준 실험 α=1.0)",
                "color_limits": [-limit, limit],
            }
            csi_matrix = np.asarray([
                [float(cat[(lead, case, threshold)]["CSI"])
                 if cat[(lead, case, threshold)]["CSI"] not in ("", "None") else np.nan
                 for case in group_cases]
                for lead in LEADS
            ], dtype=np.float64)
            fig, ax = plt.subplots(figsize=(fig_width, 5.6), layout="constrained")
            image = ax.imshow(csi_matrix, cmap="viridis", vmin=0.0, vmax=1.0,
                              aspect="auto", interpolation="nearest")
            for row in range(len(LEADS)):
                for col in range(len(group_cases)):
                    value = csi_matrix[row, col]
                    ax.text(col, row, "—" if np.isnan(value) else f"{value:.4f}",
                            ha="center", va="center", fontsize=7,
                            color="white" if np.isfinite(value) and value < 0.45 else "#17212b")
            ax.set_title(f"CSI ≥{threshold:g} mm · {group_titles[group_name]}")
            ax.set_xticks(range(len(group_cases)), [axis_case_label(case) for case in group_cases],
                          rotation=48, ha="right", fontsize=7.5)
            ax.set_yticks(range(len(LEADS)), [f"+{lead} h" for lead in LEADS])
            ax.set_xlabel("실험")
            ax.set_ylabel("예측시간")
            ax.set_xticks(np.arange(-0.5, len(group_cases), 1), minor=True)
            ax.set_yticks(np.arange(-0.5, len(LEADS), 1), minor=True)
            ax.grid(which="minor", color="white", linewidth=1.0)
            ax.tick_params(which="minor", bottom=False, left=False)
            fig.colorbar(image, ax=ax, label="CSI (0–1)")
            fig.suptitle(f"강수 임계값 ≥{threshold:g} mm · lead별 CSI")
            csi_name = f"csi/{group_name}/csi_t{threshold_slug(threshold)}"
            save_figure(fig, stage, csi_name)
            plt.close(fig)
            csi_manifest[f"{csi_name}.png"] = {
                "threshold_mm": threshold, "group": group_name,
                "cases": list(group_cases), "lead_hours": list(LEADS),
                "color_limits": [0.0, 1.0],
            }

    focus_width = max(7.2, len(FOCUSED_CASES) * 0.9)
    focus_delta_limit = [-limit, limit]
    for threshold in THRESHOLDS:
        for metric, manifest, folder, limits, cmap in (
                ("CSI", focused_csi_manifest, "low_factor_csi", [0.0, 1.0], "viridis"),
                ("ΔCSI", focused_delta_manifest, "low_factor_delta_csi", focus_delta_limit, "RdBu_r")):
            matrix = np.asarray([
                [delta_by_key[(lead, case, threshold)] if metric == "ΔCSI"
                 else (float(cat[(lead, case, threshold)]["CSI"])
                       if cat[(lead, case, threshold)]["CSI"] not in ("", "None") else np.nan)
                 for case in FOCUSED_CASES]
                for lead in LEADS
            ], dtype=np.float64)
            fig, ax = plt.subplots(figsize=(focus_width, 5.6), layout="constrained")
            image = ax.imshow(matrix, cmap=cmap, vmin=limits[0], vmax=limits[1],
                              aspect="auto", interpolation="nearest")
            for row in range(len(LEADS)):
                for col in range(len(FOCUSED_CASES)):
                    value = matrix[row, col]
                    color = ("white" if metric == "ΔCSI" and np.isfinite(value)
                             and abs(value) >= 0.58 * limit else
                             "white" if metric == "CSI" and np.isfinite(value) and value < 0.45
                             else "#17212b")
                    text = "—" if np.isnan(value) else (f"{value:+.4f}" if metric == "ΔCSI" else f"{value:.4f}")
                    ax.text(col, row, text, ha="center", va="center", fontsize=7, color=color)
            ax.set_xticks(range(len(FOCUSED_CASES)),
                          [axis_case_label(case, focused=True) for case in FOCUSED_CASES],
                          rotation=48, ha="right", fontsize=7.5)
            ax.set_yticks(range(len(LEADS)), [f"+{lead} h" for lead in LEADS])
            ax.set_xlabel("초기 QSNOW 배율 α")
            ax.set_ylabel("예측시간")
            ax.set_xticks(np.arange(-0.5, len(FOCUSED_CASES), 1), minor=True)
            ax.set_yticks(np.arange(-0.5, len(LEADS), 1), minor=True)
            ax.grid(which="minor", color="white", linewidth=1.0)
            ax.tick_params(which="minor", bottom=False, left=False)
            if metric == "CSI":
                label = "CSI (0–1)"
                title = "절대 CSI"
            else:
                label = f"ΔCSI = 실험 − 규준 실험 α=1.0 (공통 범위 ±{limit:.3f})"
                title = "규준 실험 α=1.0 대비 ΔCSI"
            fig.colorbar(image, ax=ax, label=label)
            fig.suptitle(f"초기 QSNOW 비교 · C=CONTROL, I=IMPROVED · ≥{threshold:g} mm · {title}")
            name = f"focused/{folder}_t{threshold_slug(threshold)}"
            save_figure(fig, stage, name)
            plt.close(fig)
            manifest[f"{name}.png"] = {
                "threshold_mm": threshold, "cases": list(FOCUSED_CASES),
                "lead_hours": list(LEADS), "color_limits": limits,
            }

    levels = PRECIPITATION_LEVELS
    colors = ("#f3f4f6", "#c6dbef", "#9ecae1", "#6baed6", "#41b6c4",
              "#1d91c0", "#225ea8", "#253494", "#4a1486")
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(levels, cmap.N, clip=True)
    lon, lat = hours[HOURS[0]]["longitude"], hours[HOURS[0]]["latitude"]
    extent = (float(lon.min()), float(lon.max()), float(lat.min()), float(lat.max()))
    map_manifest = {}
    for case in cases:
        fields = map_fields(case)
        fig, axes = plt.subplots(len(LEADS), 3, figsize=(12.6, 16.5),
                                 sharex=True, sharey=True, layout="constrained")
        for row, lead in enumerate(LEADS):
            data = hours[lead + 12]
            for col, (field, label) in enumerate(fields):
                ax = axes[row, col]
                points = ax.scatter(data["longitude"], data["latitude"], c=data[field], cmap=cmap,
                                    norm=norm, s=7.5, marker="s", linewidths=0, rasterized=True)
                if row == 0:
                    ax.set_title(label, loc="left", fontsize=9.5)
                if col == 0:
                    ax.set_ylabel(f"+{lead} h\n위도 (°N)")
                if row == len(LEADS) - 1:
                    ax.set_xlabel("경도 (°E)")
                ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
                ax.set_aspect(1.0 / np.cos(np.deg2rad(float(np.mean(lat)))))
                ax.grid(color="white", linewidth=0.3, alpha=0.55)
            diff_ax = axes[row, 2]
            delta_points = diff_ax.scatter(data["longitude"], data["latitude"],
                                           c=differences[lead + 12][case], cmap="RdBu_r",
                                           norm=difference_norm, s=7.5, marker="s",
                                           linewidths=0, rasterized=True)
            if row == 0:
                diff_ax.set_title("ΔP = 실험 − 규준 실험 α=1.0", loc="left", fontsize=9.5)
            diff_ax.set_ylabel(f"+{lead} h\n위도 (°N)")
            if row == len(LEADS) - 1:
                diff_ax.set_xlabel("경도 (°E)")
            diff_ax.set_xlim(extent[0], extent[1]); diff_ax.set_ylim(extent[2], extent[3])
            diff_ax.set_aspect(1.0 / np.cos(np.deg2rad(float(np.mean(lat)))))
            diff_ax.grid(color="white", linewidth=0.3, alpha=0.55)
        bar = fig.colorbar(points, ax=axes[:, :2], orientation="horizontal", pad=0.065,
                           fraction=0.035, ticks=levels, extend="max")
        bar.set_label("한 시간 지상 총강수 (mm)")
        diff_bar = fig.colorbar(delta_points, ax=axes[:, 2], orientation="horizontal", pad=0.065,
                                fraction=0.035)
        diff_bar.set_label(f"ΔP = 실험 − 규준 실험 α=1.0 (mm; 공통 범위 ±{difference_limit:.1f})")
        fig.suptitle(f"{display_case(case)} · 시간별 총강수와 규준 실험 α=1.0 대비 차이", fontsize=13)
        fig.text(0.5, -0.005, "모든 패널은 3,688개 공통 RN1 paired point만 표시. ΔP는 같은 lead·격자점에서 계산하며 관측오차가 아님; 추가 보간·coverage 외삽 없음.",
                 ha="center", fontsize=8, color="#444444")
        group_name = ("control" if case == "ORIGINAL" or case.startswith("CONTROL_SNOW_")
                      else "improved" if case == "IMPROVED_BG_FIXED" or case.startswith("IMPROVED_SNOW_")
                      else "context")
        name = f"hourly_maps/{group_name}/hourly_total_precip_{case}"
        save_figure(fig, stage, name)
        plt.close(fig)
        map_manifest[case] = {"figure": f"{name}.png", "lead_hours": list(LEADS),
                              "panels_per_lead": ["reference", case, "case_minus_ORIGINAL"],
                              "precipitation_bins_mm": list(levels),
                              "difference_color_limits_mm": difference_limits}

    figures = sorted(path for path in stage.rglob("*") if path.is_file())
    expected_score_keys, expected_map_keys = expected_coverage(cases)
    manifest = {"schema": "snow_lower_figures_v1", "status": "COMPLETE",
                "renderer_sha256": sha256(Path(__file__).resolve()),
                "receipt_sha256": sha256(analysis / "receipt.json"),
                "selection_plan_sha256": PLAN_SHA256, "selected_case": best,
                "ranking": order, "thresholds_mm": list(THRESHOLDS), "lead_hours": list(LEADS),
                "eligible_cases": list(eligible), "unranked_cases": selection.get("failed_or_incomplete_cases_unranked", []),
                "context_only_cases": ["CURRENT_HYDRO"],
                "figure_sha256": {path.relative_to(stage).as_posix(): sha256(path) for path in figures},
                "delta_csi_heatmaps": heatmap_manifest,
                "csi_heatmaps": csi_manifest,
                "focused_csi_heatmaps": focused_csi_manifest,
                "focused_delta_csi_heatmaps": focused_delta_manifest,
                "heatmap_coverage": {
                    "cases": list(cases), "lead_hours": list(LEADS),
                    "thresholds_mm": list(THRESHOLDS),
                    "delta_cell_count": len(expected_score_keys),
                "csi_cell_count": len(expected_score_keys),
                "focused_delta_cell_count": len(FOCUSED_CASES) * len(LEADS) * len(THRESHOLDS),
                "focused_csi_cell_count": len(FOCUSED_CASES) * len(LEADS) * len(THRESHOLDS),
                    "cases_per_page_groups": {name: list(group) for name, group in groups},
                    "shared_color_limits": [-limit, limit],
                },
                "hourly_precipitation_maps": map_manifest,
                "map_coverage": {
                    "cases": list(cases), "lead_hours": list(LEADS),
                    "case_lead_count": len(expected_map_keys),
                    "common_precipitation_bins_mm": list(levels),
                },
                "pointwise_precipitation_difference": {
                    "definition": "P_case - P_ORIGINAL at the same lead and paired grid point",
                    "baseline_case": "ORIGINAL", "units": "mm",
                    "point_count_per_lead": POINTS, "cases": list(cases),
                    "lead_hours": list(LEADS), "ORIGINAL_is_zero": True,
                    "observed_min_mm": difference_min, "observed_max_mm": difference_max,
                    "shared_color_limits_mm": difference_limits,
                    "source_sha256": difference_hashes,
                    "source_size_bytes": difference_sizes,
                }}
    validate_figure_coverage(manifest, cases, best)
    (stage / "figure_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    verify_analysis(analysis)
    if (sha256(analysis / "receipt.json") != receipt_digest
            or sha256(Path(__file__).resolve()) != renderer_digest):
        raise ValueError("score receipt or renderer changed during figure generation")
    backup_root = Path(tempfile.mkdtemp(prefix=f".{output.name}.backup-", dir=output.parent))
    backup = backup_root / "previous-output"
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
        if backup_root.exists():
            shutil.rmtree(backup_root)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if backup_root.exists() and not backup.exists():
            shutil.rmtree(backup_root)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/evidence/snow_lower_20261030/figures"))
    args = parser.parse_args()
    print(json.dumps(render(args.analysis_dir, args.output_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
