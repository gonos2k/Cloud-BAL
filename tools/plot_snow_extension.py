#!/usr/bin/env python3
"""Render extension score comparisons and six-hour precipitation maps."""
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

PLAN_SHA256 = "36e094ac84d698351cdc477ec0bb58fd7580e0676e9ed830236a7d52b0818642"
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
HOURS = tuple(range(13, 19))
LEADS = tuple(range(1, 7))
POINTS = 3688
FAMILIES = ("CONTROL", "IMPROVED")
FACTORS = (0, 25, 50, 75, 125, 150, 175, 200, 250, 300)
VARIANTS = tuple(f"{family}_SNOW_{factor:03d}" for family in FAMILIES for factor in FACTORS)
NEW_FACTORS = FACTORS[6:]
NEW_CASES = tuple(f"{family}_SNOW_{factor:03d}" for family in FAMILIES for factor in NEW_FACTORS)
ALL_CASES = ("ORIGINAL", "CURRENT_HYDRO", "IMPROVED_BG_FIXED", *VARIANTS)
BASE_CASES = ("ORIGINAL", "CURRENT_HYDRO", "IMPROVED_BG_FIXED",
              *(f"{family}_SNOW_{factor:03d}" for family in FAMILIES for factor in FACTORS[:6]))
ELIGIBLE = tuple(case for case in ALL_CASES if case != "CURRENT_HYDRO")
BASELINES = ("ORIGINAL", "IMPROVED_BG_FIXED")
ARRAY_KEYS = {"reference", *ALL_CASES, "latitude", "longitude", "flat_index_yx"}
LABELS = {"ORIGINAL": "규준 실험", "CURRENT_HYDRO": "기존 HYDRO",
          "IMPROVED_BG_FIXED": "기존 개선안 B1"}


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
        raise ValueError("extension score receipt has no usable complete score tables")
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
        raise ValueError("frozen extension selection plan hash mismatch")
    cat = read_csv(analysis / "categorical_scores.csv")
    cont = read_csv(analysis / "continuous_scores.csv")
    for row in (*cat, *cont):
        validate_window(row, int(row["lead_hour"]))
    selection_rows = read_csv(analysis / "selection_scores.csv")
    cases = tuple(case for case in ALL_CASES if any(row["case"] == case for row in cont))
    eligible = tuple(case for case in cases if case != "CURRENT_HYDRO")
    if not set(BASE_CASES).issubset(cases) or len(cases) > len(ALL_CASES):
        raise ValueError("baseline or prior sensitivity cases are missing from scored tables")
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
        alpha = int(suffix) / 100 if case in VARIANTS else 1.0
        ranked.append((case, csi10, csi5, far10,
                       float(cont[(1, case)]["RMSE_mm"]), abs(alpha - 1), alpha))
    ranked.sort(key=lambda item: (
        item[1] is None, 0 if item[1] is None else -item[1],
        item[2] is None, 0 if item[2] is None else -item[2],
        item[3] is None, 0 if item[3] is None else item[3],
        item[4], item[5], item[0]))
    return [item[0] for item in ranked]


def selected_case(selection: dict, eligible: tuple[str, ...] = ELIGIBLE) -> str:
    case = selection.get("selected_case")
    if case not in eligible:
        raise ValueError(f"selected case is ineligible or unknown: {case!r}")
    return case


def map_fields(selected: str) -> tuple[tuple[str, str], ...]:
    if selected not in ALL_CASES:
        raise ValueError(f"selected case is unknown: {selected}")
    fields = [("reference", "RN1 분석"), ("ORIGINAL", LABELS["ORIGINAL"]),
              ("IMPROVED_BG_FIXED", LABELS["IMPROVED_BG_FIXED"])]
    if selected not in {field for field, _ in fields}:
        fields.append((selected, f"선정 실험 · {display_case(selected)}"))
    return tuple(fields)


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


def save_figure(fig, stage: Path, name: str) -> None:
    fig.savefig(stage / f"{name}.png", dpi=240, bbox_inches="tight", facecolor="white")
    fig.savefig(stage / f"{name}.pdf", bbox_inches="tight", facecolor="white",
                metadata={"CreationDate": None, "ModDate": None, "Creator": "plot_snow_extension.py"})
    fig.savefig(stage / f"{name}.svg", bbox_inches="tight", facecolor="white",
                metadata={"Date": None, "Creator": "plot_snow_extension.py"})


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
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Rectangle
    plt.rcParams.update({"font.family": "Noto Sans CJK JP", "font.size": 9,
                         "svg.fonttype": "none", "svg.hashsalt": "snow-extension-v1", "pdf.fonttype": 42})
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    cat = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): row
           for row in categorical}
    def score_matrix(matrix_cases: tuple[str, ...], leads: tuple[int, ...], thresholds: tuple[float, ...]) -> np.ndarray:
        rows = []
        for lead in leads:
            values = []
            for case in matrix_cases:
                for threshold in thresholds:
                    value = cat[(lead, case, threshold)]["CSI"]
                    values.append(np.nan if value in ("", "None") else float(value))
            rows.append(values)
        return np.asarray(rows, dtype=np.float64)

    # Threshold-specific 10-mm CSI across lead hours: no threshold or lead averaging.
    values = score_matrix(eligible, LEADS, (10.0,))
    fig, ax = plt.subplots(figsize=(15.2, 5.6))
    image = ax.imshow(values, cmap="YlGnBu", vmin=0, vmax=1, aspect="auto", interpolation="nearest")
    for row in range(len(LEADS)):
        for col in range(len(eligible)):
            value = values[row, col]
            ax.text(col, row, "—" if np.isnan(value) else f"{value:.3f}",
                    ha="center", va="center", fontsize=5.7,
                    color="#17212b" if np.isnan(value) or value < 0.62 else "white")
    ax.set_xticks(range(len(eligible)), [display_case(case) for case in eligible], rotation=55, ha="right")
    ax.set_yticks(range(6), [f"+{lead} h" for lead in LEADS])
    ax.set_xlabel("Eligible experiment")
    ax.set_ylabel("Forecast lead")
    ax.set_title("Hourly CSI at the study strong precipitation threshold (≥10 mm)")
    ax.add_patch(Rectangle((eligible.index(best) - 0.5, -0.5), 1, len(LEADS),
                           fill=False, edgecolor="#d62728", linewidth=2.0))
    fig.colorbar(image, ax=ax, label="CSI")
    fig.text(0.5, -0.04, "All scores use 3,688 paired points per hour; 10 mm per one-hour window is a study threshold, not an official warning class.",
             ha="center", fontsize=8)
    fig.tight_layout()
    save_figure(fig, stage, "strong_precipitation_csi")
    plt.close(fig)

    # Selected case and baselines retain threshold-specific CSI and every contingency count.
    display_cases = list(dict.fromkeys((*BASELINES, best)))
    fig, axes = plt.subplots(1, len(display_cases), figsize=(5.1 * len(display_cases), 5.0), squeeze=False)
    for ax, case in zip(axes.flat, display_cases):
        matrix = score_matrix((case,), LEADS, THRESHOLDS)
        image = ax.imshow(matrix, cmap="YlGnBu", vmin=0, vmax=1, aspect="auto", interpolation="nearest")
        for row in range(len(LEADS)):
            for col in range(len(THRESHOLDS)):
                value = matrix[row, col]
                ax.text(col, row, "—" if np.isnan(value) else f"{value:.3f}",
                        ha="center", va="center", fontsize=7,
                        color="#17212b" if np.isnan(value) or value < 0.62 else "white")
        ax.set_title("선정 · " + display_case(case) if case == best else display_case(case))
        ax.set_xticks(range(6), [f"{threshold:g}" for threshold in THRESHOLDS])
        ax.set_yticks(range(6), [f"+{lead}" for lead in LEADS])
        ax.set_xlabel("1시간 강수 임계값 (mm)")
        ax.set_ylabel("예측시간 (h)")
        fig.colorbar(image, ax=ax, label="CSI")
    fig.suptitle("임계값별 CSI · 각 칸은 개별 임계값 점수", y=1.02)
    fig.tight_layout()
    save_figure(fig, stage, "selected_threshold_csi")
    plt.close(fig)

    delta_values = []
    for threshold in (5.0, 10.0):
        delta_values.append(np.asarray([
            [delta_csi(float(cat[(lead, case, threshold)]["CSI"]),
                       float(cat[(lead, "ORIGINAL", threshold)]["CSI"]))
             for case in NEW_CASES]
            for lead in LEADS], dtype=np.float64))
    limit = max(0.02, float(np.ceil(np.max(np.abs(delta_values)) / 0.02) * 0.02))
    from matplotlib.colors import TwoSlopeNorm
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    fig, axes = plt.subplots(1, 2, figsize=(12.0, 5.3), squeeze=False,
                             gridspec_kw={"wspace": 0.28}, layout="constrained")
    short_labels = [display_case(case).replace(" 계열", "") for case in NEW_CASES]
    for ax, threshold, matrix in zip(axes.flat, (5.0, 10.0), delta_values):
        image = ax.imshow(matrix, cmap="RdBu_r", norm=norm, aspect="auto", interpolation="nearest")
        for row in range(len(LEADS)):
            for col in range(len(NEW_CASES)):
                value = matrix[row, col]
                ax.text(col, row, f"{value:+.4f}", ha="center", va="center", fontsize=7.6,
                        color="#17212b" if abs(value) < 0.58 * limit else "white")
        ax.set_title(f"CSI 차이 ≥{threshold:g} mm · 신규 실험 − 규준")
        ax.set_xticks(range(len(NEW_CASES)), short_labels, rotation=38, ha="right", fontsize=8)
        ax.set_yticks(range(len(LEADS)), [f"+{lead} h" for lead in LEADS])
        ax.set_xlabel("새 실험 · snow α")
        ax.set_ylabel("예측시간")
        ax.set_xticks(np.arange(-0.5, len(NEW_CASES), 1), minor=True)
        ax.set_yticks(np.arange(-0.5, len(LEADS), 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=1.0)
        ax.tick_params(which="minor", bottom=False, left=False)
    fig.colorbar(image, ax=axes, orientation="horizontal", pad=0.14, fraction=0.06,
                 label=f"ΔCSI = new case − ORIGINAL (shared range ±{limit:.2f})")
    fig.suptitle("새 고배율 실험과 규준 실험 비교 · lead별 ΔCSI (새 실험 − 규준)")
    save_figure(fig, stage, "new_cases_vs_control_csi")
    plt.close(fig)

    levels = (0, 0.1, 0.5, 1, 2.5, 5, 10, 20, 50, 100)
    colors = ("#f3f4f6", "#c6dbef", "#9ecae1", "#6baed6", "#41b6c4",
              "#1d91c0", "#225ea8", "#253494", "#4a1486")
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(levels, cmap.N, clip=True)
    fields = map_fields(best)
    lon, lat = hours[HOURS[0]]["longitude"], hours[HOURS[0]]["latitude"]
    extent = (float(lon.min()), float(lon.max()), float(lat.min()), float(lat.max()))
    for leads in ((1, 2, 3), (4, 5, 6)):
        fig, axes = plt.subplots(3, len(fields), figsize=(2.6 * len(fields), 9.6),
                                 sharex=True, sharey=True, layout="constrained")
        for row, lead in enumerate(leads):
            data = hours[lead + 12]
            for col, (field, label) in enumerate(fields):
                ax = axes[row, col]
                points = ax.scatter(data["longitude"], data["latitude"], c=data[field], cmap=cmap,
                                    norm=norm, s=7.5, marker="s", linewidths=0, rasterized=True)
                if row == 0:
                    ax.set_title(label, loc="left", fontsize=9.5)
                if col == 0:
                    ax.set_ylabel(f"+{lead} h\n위도 (°N)")
                if row == 2:
                    ax.set_xlabel("경도 (°E)")
                ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
                ax.set_aspect(1.0 / np.cos(np.deg2rad(float(np.mean(lat)))))
                ax.grid(color="white", linewidth=0.3, alpha=0.55)
        bar = fig.colorbar(points, ax=axes, orientation="horizontal", pad=0.065,
                           fraction=0.035, ticks=levels, extend="max")
        bar.set_label("한 시간 지상 총강수 (mm)")
        fig.suptitle(f"선정 실험 {display_case(best)} · +{leads[0]}–+{leads[-1]}시간", fontsize=13)
        fig.text(0.5, -0.005, "공통 RN1 평가점만 표시하며 추가 보간·coverage 외삽은 하지 않음. RN1은 처리된 분석자료임.",
                 ha="center", fontsize=8, color="#444444")
        save_figure(fig, stage, f"snow_extension_maps_leads_{leads[0]}_{leads[-1]}")
        plt.close(fig)

    figures = sorted(path for path in stage.iterdir() if path.is_file())
    manifest = {"schema": "snow_extension_figures_v1", "status": "COMPLETE",
                "renderer_sha256": sha256(Path(__file__).resolve()),
                "receipt_sha256": sha256(analysis / "receipt.json"),
                "selection_plan_sha256": PLAN_SHA256, "selected_case": best,
                "ranking": order, "thresholds_mm": list(THRESHOLDS), "lead_hours": list(LEADS),
                "eligible_cases": list(eligible), "unranked_cases": selection.get("failed_or_incomplete_cases_unranked", []),
                "context_only_cases": ["CURRENT_HYDRO"],
                "figure_sha256": {path.name: sha256(path) for path in figures}}
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
    parser.add_argument("--output-dir", type=Path, default=Path("docs/evidence/snow_extension_20261030/figures"))
    args = parser.parse_args()
    print(json.dumps(render(args.analysis_dir, args.output_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
