#!/usr/bin/env python3
"""Render publication figures from the validated one-hour factorial score."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np

CASES = ("BASE_H", "FIX_H", "BG_BASE", "POLICY_BG", "BASE_ORIGINAL")
CASE_IDS = {"BASE_H": "H0", "FIX_H": "H1", "BG_BASE": "B0",
            "POLICY_BG": "B1", "BASE_ORIGINAL": "O0"}
LABELS = {
    "BASE_H": "H0 · HYDRO, old WRF",
    "FIX_H": "H1 · HYDRO, zero-rate fix",
    "BG_BASE": "B0 · preserved background, old WRF",
    "POLICY_BG": "B1 · preserved background, zero-rate fix",
    "BASE_ORIGINAL": "O0 · original OFF",
}
COLORS = {
    "BASE_H": "#0072B2", "FIX_H": "#56B4E9", "BG_BASE": "#D55E00",
    "POLICY_BG": "#E69F00", "BASE_ORIGINAL": "#555555",
}
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
ARRAY_KEYS = {"reference", *CASES, "latitude", "longitude", "flat_index_yx"}
CAT_FIELDS = {"case", "threshold_mm", "points", "hit", "miss", "false_alarm",
              "correct_dry", "CSI", "ETS", "POD", "FAR", "frequency_bias"}
CONT_FIELDS = {"case", "points", "mean_forecast_mm", "mean_reference_mm",
               "mean_error_mm", "MAE_mm", "RMSE_mm"}


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
            raise ValueError(f"{path}: missing columns {sorted(required - set(reader.fieldnames or []))}")
        return list(reader)


def validate_receipt(path: Path) -> dict:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("status") != "COMPLETE" or receipt.get("points") != 3688:
        raise ValueError("score receipt is incomplete or does not bind the 3688-point sample")
    expected_levels = {"H0": "BASE_H", "H1": "FIX_H", "B0": "BG_BASE",
                       "B1": "POLICY_BG", "O0": "BASE_ORIGINAL"}
    if receipt.get("factor_levels") != expected_levels:
        raise ValueError("score receipt factor assignments do not match H0/H1/B0/B1/O0")
    if not isinstance(receipt.get("sources"), list) or not receipt["sources"]:
        raise ValueError("score receipt has no source hash records")
    for record in receipt["sources"]:
        digest = record.get("sha256")
        if (not isinstance(record.get("path"), str) or not record["path"]
                or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or not isinstance(record.get("size"), int) or record["size"] < 0):
            raise ValueError("score receipt contains a malformed source hash record")
    return receipt


def validate_analysis_outputs(analysis: Path, receipt: dict) -> list[Path]:
    expected = {"hour_13_arrays.npz", "categorical_scores.csv", "continuous_scores.csv",
                "transitions.csv", "score_contrasts.csv", "pointwise_precipitation_contrasts.csv"}
    records = receipt.get("analysis_outputs")
    if not isinstance(records, dict) or set(records) != expected:
        raise ValueError("score receipt does not bind the complete analysis output set")
    paths = []
    for name, record in records.items():
        path = analysis / name
        if (not path.is_file() or path.stat().st_size != record.get("size_bytes")
                or sha256(path) != record.get("sha256")):
            raise ValueError(f"analysis output hash mismatch: {path}")
        paths.append(path)
    return paths


def load_arrays(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != ARRAY_KEYS:
            raise ValueError(f"{path}: unexpected NPZ keys {sorted(archive.files)}")
        data = {key: np.asarray(archive[key]) for key in archive.files}
    size = data["reference"].size
    if size != 3688 or any(value.shape != (size,) for value in data.values()):
        raise ValueError("all score arrays must be vectors with exactly 3688 paired points")
    for key, values in data.items():
        if key == "flat_index_yx":
            if not np.issubdtype(values.dtype, np.integer) or np.unique(values).size != size:
                raise ValueError("flat_index_yx must contain 3688 unique integers")
        elif not np.isfinite(values).all():
            raise ValueError(f"{key} contains non-finite values")
    if any((data[key] < 0).any() for key in ("reference", *CASES)):
        raise ValueError("precipitation totals must be nonnegative")
    if ((data["latitude"] < -90) | (data["latitude"] > 90)).any():
        raise ValueError("latitude outside [-90, 90]")
    if ((data["longitude"] < -180) | (data["longitude"] > 180)).any():
        raise ValueError("longitude outside [-180, 180]")
    return data


def close(actual: float, expected: float, label: str) -> None:
    if not np.isclose(actual, expected, rtol=1e-10, atol=1e-12):
        raise ValueError(f"score table mismatch for {label}: {actual} != {expected}")


def validate_scores(analysis: Path, data: dict[str, np.ndarray]) -> tuple[list[dict], list[dict]]:
    categorical = read_csv(analysis / "categorical_scores.csv", CAT_FIELDS)
    continuous = read_csv(analysis / "continuous_scores.csv", CONT_FIELDS)
    expected_rows = {(case, threshold) for case in CASES for threshold in THRESHOLDS}
    rows = {}
    for row in categorical:
        key = (row["case"], float(row["threshold_mm"]))
        if key in rows:
            raise ValueError(f"duplicate categorical score row: {key}")
        rows[key] = row
    if set(rows) != expected_rows or len(continuous) != len(CASES):
        raise ValueError("score tables do not contain exactly five cases at six thresholds")
    continuous_by_case = {row["case"]: row for row in continuous}
    if len(continuous_by_case) != len(CASES) or set(continuous_by_case) != set(CASES):
        raise ValueError("continuous score rows have missing or duplicate cases")

    reference = data["reference"]
    for case in CASES:
        forecast = data[case]
        err = forecast - reference
        row = continuous_by_case[case]
        if int(row["points"]) != len(reference):
            raise ValueError(f"{case}: continuous point count mismatch")
        for field, value in (("mean_forecast_mm", np.mean(forecast)),
                             ("mean_reference_mm", np.mean(reference)),
                             ("mean_error_mm", np.mean(err)),
                             ("MAE_mm", np.mean(np.abs(err))),
                             ("RMSE_mm", np.sqrt(np.mean(err ** 2)))):
            close(float(row[field]), float(value), f"{case}.{field}")
        for threshold in THRESHOLDS:
            fwet, owet = forecast >= threshold, reference >= threshold
            hit = int(np.count_nonzero(fwet & owet))
            miss = int(np.count_nonzero(~fwet & owet))
            false_alarm = int(np.count_nonzero(fwet & ~owet))
            correct_dry = int(np.count_nonzero(~fwet & ~owet))
            row = rows[(case, threshold)]
            if int(row["points"]) != len(reference) or tuple(map(int, (
                row["hit"], row["miss"], row["false_alarm"], row["correct_dry"]
            ))) != (hit, miss, false_alarm, correct_dry):
                raise ValueError(f"{case} at {threshold:g} mm: contingency counts mismatch")
            csi = hit / (hit + miss + false_alarm) if hit + miss + false_alarm else 0.0
            close(float(row["CSI"]), csi, f"{case}.CSI@{threshold:g}")
    return categorical, continuous


def save_figure(fig, stage: Path, name: str) -> None:
    fig.savefig(stage / f"{name}.png", dpi=240, bbox_inches="tight", facecolor="white")
    fig.savefig(stage / f"{name}.pdf", bbox_inches="tight", facecolor="white",
                metadata={"CreationDate": None, "ModDate": None,
                          "Creator": "plot_first_hour_factorial.py"})
    fig.savefig(stage / f"{name}.svg", bbox_inches="tight", facecolor="white",
                metadata={"Date": None, "Creator": "plot_first_hour_factorial.py"})


def precipitation_figure(plt, data, stage: Path) -> None:
    from matplotlib.colors import BoundaryNorm, ListedColormap

    levels = (0.0, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 50.0, 100.0)
    colors = ("#f3f4f6", "#c6dbef", "#9ecae1", "#6baed6", "#41b6c4",
              "#1d91c0", "#225ea8", "#253494", "#4a1486")
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(levels, cmap.N, clip=True)
    lon, lat = data["longitude"], data["latitude"]
    extent = (float(lon.min()), float(lon.max()), float(lat.min()), float(lat.max()))
    figure, axes = plt.subplots(2, 2, figsize=(10.2, 7.8), sharex=True, sharey=True,
                                layout="constrained")
    fields = (("reference", "RN1 reference"), ("BASE_ORIGINAL", "O0 · original OFF"),
              ("BASE_H", "H0 · HYDRO, old WRF"), ("POLICY_BG", "B1 · preserved background, fixed WRF"))
    scatter = None
    for ax, (key, title) in zip(axes.flat, fields):
        scatter = ax.scatter(lon, lat, c=data[key], cmap=cmap, norm=norm, s=9,
                             marker="s", linewidths=0, rasterized=True)
        ax.set_title(title, loc="left", fontsize=11, fontweight="semibold")
        ax.set_xlim(extent[:2]); ax.set_ylim(extent[2:])
        ax.set_aspect(1.0 / np.cos(np.deg2rad(float(np.mean(lat)))))
        ax.grid(color="white", linewidth=0.35, alpha=0.6)
        ax.set_xlabel("Longitude (°E)"); ax.set_ylabel("Latitude (°N)")
    colorbar = figure.colorbar(scatter, ax=axes, orientation="horizontal", pad=0.08,
                               fraction=0.045, ticks=levels, extend="max")
    colorbar.set_label("Precipitation accumulated from 12 to 13 UTC (mm)")
    figure.suptitle("First-hour precipitation at the 3,688 paired RN1 locations",
                    fontsize=14, fontweight="semibold")
    figure.text(0.5, -0.01,
                "Squares mark retained paired points only; no interpolation or areal coverage is implied. "
                "RN1 is a processed analysis, not a gauge observation.",
                ha="center", va="top", fontsize=8.5, color="#444444")
    save_figure(figure, stage, "hour_12_13_paired_precipitation")
    plt.close(figure)


def metrics_figure(plt, categorical, continuous, stage: Path) -> None:
    from matplotlib.lines import Line2D

    figure, axes = plt.subplots(1, 3, figsize=(14.2, 5.6))
    for case in CASES:
        rows = sorted((row for row in categorical if row["case"] == case),
                      key=lambda row: float(row["threshold_mm"]))
        axes[0].plot([float(row["threshold_mm"]) for row in rows],
                     [float(row["CSI"]) for row in rows], marker="o", markersize=4,
                     color=COLORS[case], linewidth=1.7, label=LABELS[case])
    axes[0].set_xscale("log")
    axes[0].set_xticks(THRESHOLDS, labels=[f"{v:g}" for v in THRESHOLDS])
    axes[0].set(xlabel="1-h precipitation accumulation threshold (mm)", ylabel="CSI",
                title="Threshold skill · higher is better", ylim=(0, 1))
    for ax, field, title in ((axes[1], "MAE_mm", "MAE · lower is better"),
                             (axes[2], "RMSE_mm", "RMSE · lower is better")):
        values = {row["case"]: float(row[field]) for row in continuous}
        bars = ax.bar(np.arange(len(CASES)), [values[case] for case in CASES],
                      color=[COLORS[case] for case in CASES], width=0.7)
        ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=8, rotation=45)
        ax.set_xticks(np.arange(len(CASES)), [CASE_IDS[case] for case in CASES], fontsize=8.5,
                      rotation=22, ha="right")
        ax.set(ylabel="mm", title=title, ylim=(0, max(values.values()) * 1.22))
    axes[0].grid(axis="both", alpha=0.22)
    for ax in axes[1:]:
        ax.grid(axis="y", alpha=0.22)
        ax.set_axisbelow(True)
    handles = [Line2D([0], [0], color=COLORS[case], marker="o", linewidth=1.6,
                      label=LABELS[case]) for case in CASES]
    figure.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.995),
                  ncol=3, frameon=False, fontsize=8.3)
    figure.suptitle("One-hour paired-point verification against RN1", y=0.86,
                    fontsize=14, fontweight="semibold")
    figure.tight_layout(rect=(0.0, 0.09, 1.0, 0.79), w_pad=2.0)
    figure.text(0.5, 0.025,
                "All metrics are unweighted over the same 3,688 retained points; one spatial case and one forecast hour.",
                ha="center", fontsize=8.5, color="#444444")
    save_figure(figure, stage, "hour_12_13_skill_factorial")
    plt.close(figure)


def design_figure(plt, stage: Path) -> None:
    from matplotlib.patches import FancyBboxPatch

    figure = plt.figure(figsize=(12.4, 8.3), layout="constrained")
    grid = figure.add_gridspec(3, 1, height_ratios=(1.10, 0.50, 0.90))
    ax = figure.add_subplot(grid[0]); ax.set_axis_off()
    ax.text(0.5, 0.97, "Factorial cells: initialization policy × zero-rate guard",
            ha="center", va="top", fontsize=14, fontweight="semibold", transform=ax.transAxes)
    ax.text(0.35, 0.80, "Historical HYDRO initialization", ha="center", fontsize=10,
            transform=ax.transAxes)
    ax.text(0.78, 0.80, "Preserved background precipitation", ha="center", fontsize=10,
            transform=ax.transAxes)
    x_positions = (0.35, 0.78)
    row_y = (0.57, 0.33)
    matrix = (("H0", "BASE_H", "old WRF · guard absent"),
              ("B0", "BG_BASE", "old WRF · guard absent"),
              ("H1", "FIX_H", "fixed WRF · guard present"),
              ("B1", "POLICY_BG", "fixed WRF · guard present"))
    for (code, _, detail), x, y in zip(matrix, (x_positions[0], x_positions[1],
                                                x_positions[0], x_positions[1]),
                                        (row_y[0], row_y[0], row_y[1], row_y[1])):
        color = COLORS[dict(H0="BASE_H", H1="FIX_H", B0="BG_BASE", B1="POLICY_BG")[code]]
        box = FancyBboxPatch((x - 0.19, y - 0.085), 0.38, 0.17,
                             boxstyle="round,pad=0.014,rounding_size=0.018",
                             facecolor=color, edgecolor="white", linewidth=1.5,
                             transform=ax.transAxes)
        ax.add_patch(box)
        ax.text(x, y + 0.022, code, ha="center", va="center", color="white",
                fontsize=13, fontweight="bold", transform=ax.transAxes)
        ax.text(x, y - 0.036, detail, ha="center", va="center", color="white",
                fontsize=8, transform=ax.transAxes)
    ax.text(0.015, row_y[0], "Guard absent", ha="left", va="center", fontsize=8.7,
            transform=ax.transAxes)
    ax.text(0.015, row_y[1], "Guard present", ha="left", va="center", fontsize=8.7,
            transform=ax.transAxes)
    ax.text(0.02, 0.095, "O0 · BASE_ORIGINAL: actual original OFF forecast (external anchor)",
            ha="left", va="center", fontsize=8.7, color=COLORS["BASE_ORIGINAL"],
            fontweight="semibold", transform=ax.transAxes)

    source = figure.add_subplot(grid[1]); source.set_axis_off()
    source.text(0.02, 0.93, "What changes in the intervention", fontsize=11,
                fontweight="semibold", transform=source.transAxes)
    source.text(0.04, 0.62,
                "Preserved-background initialization changes eight coupled native fields: "
                "P, PH, AL, P_HYD, TH2, QRAIN, QSNOW, QGRAUP.",
                fontsize=9.2, transform=source.transAxes)
    source.text(0.04, 0.40,
                "Separate QR/QS swaps are prescribed species diagnostics; they do not represent the full policy intervention.",
                fontsize=9.2, transform=source.transAxes)
    source.text(0.04, 0.20,
                r"Zero-rate fix: fallback runs only when the rate $r\ne0$; exact $+0$ and $-0$ bypass it (no maximum clamp).",
                fontsize=9.2, color="#7A3E00", fontweight="semibold", transform=source.transAxes)
    source.text(0.04, 0.04,
                "Contrasts: guard H1−H0 / B1−B0; policy B0−H0 / B1−H1. "
                "Interaction is a paired score difference-in-differences, not a physical causal share.",
                fontsize=8.5, color="#444444", transform=source.transAxes)

    math = figure.add_subplot(grid[2]); math.set_axis_off()
    math.text(0.02, 0.94, "Rainfall and verification quantities", fontsize=12,
              fontweight="semibold", transform=math.transAxes)
    math.text(0.04, 0.70,
              r"$P_{12\to13}=\left(RAINC+RAINNC\right)_{13UTC}-"
              r"\left(RAINC+RAINNC\right)_{12UTC}$",
              fontsize=14, transform=math.transAxes)
    math.text(0.04, 0.52,
              "Cumulative WRF totals are differenced after reset checks; RAINSH is checked zero and excluded; tolerance-level negatives are set to zero.",
              fontsize=9, transform=math.transAxes)
    math.text(0.04, 0.29,
              r"$CSI(\tau)=H/(H+M+F),\quad H=\#(P\geq\tau,\ R\geq\tau)$",
              fontsize=14, transform=math.transAxes)
    math.text(0.04, 0.08,
              r"Each model total P and processed RN1 value R is thresholded at the same 1-h accumulation τ (mm); no interpolation or coverage extrapolation.",
              fontsize=9, transform=math.transAxes)
    figure.suptitle("Experimental structure and metric definition", fontsize=14,
                    fontweight="semibold")
    save_figure(figure, stage, "factorial_design_and_metric")
    plt.close(figure)


def publish(stage: Path, output: Path) -> None:
    backup = output.with_name(output.name + ".previous")
    moved_old = False
    try:
        if backup.exists():
            shutil.rmtree(backup)
        if output.exists():
            os.replace(output, backup)
            moved_old = True
        os.replace(stage, output)
    except BaseException:
        if moved_old and not output.exists() and backup.exists():
            os.replace(backup, output)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def run(analysis: Path, output: Path) -> dict:
    if output.is_symlink():
        raise ValueError(f"output must not be a symlink: {output}")
    receipt = validate_receipt(analysis / "receipt.json")
    input_paths = validate_analysis_outputs(analysis, receipt)
    data = load_arrays(analysis / "hour_13_arrays.npz")
    categorical, continuous = validate_scores(analysis, data)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "Noto Sans CJK JP", "font.size": 9.5,
                         "axes.titlesize": 10.5, "axes.labelsize": 9.5,
                         "svg.fonttype": "none", "svg.hashsalt": "first-hour-factorial-v1",
                         "pdf.fonttype": 42})
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        precipitation_figure(plt, data, stage)
        metrics_figure(plt, categorical, continuous, stage)
        design_figure(plt, stage)
        inputs = [*input_paths, analysis / "receipt.json"]
        manifest = {
            "schema": "first_hour_factorial_figures_v1", "status": "COMPLETE",
            "score_receipt_sha256": sha256(analysis / "receipt.json"),
            "renderer": {"path": str(Path(__file__).resolve()),
                         "sha256": sha256(Path(__file__).resolve()),
                         "size_bytes": Path(__file__).stat().st_size},
            "points": 3688, "case_keys": list(CASES), "case_labels": LABELS,
            "thresholds_mm_per_hour": list(THRESHOLDS),
            "inputs": [{"path": str(path.resolve()), "sha256": sha256(path), "size": path.stat().st_size}
                       for path in inputs],
            "precipitation_point_counts": {
                key: {"0–<0.1": int(np.count_nonzero((data[key] >= 0) & (data[key] < 0.1))),
                      "0.1–<0.5": int(np.count_nonzero((data[key] >= 0.1) & (data[key] < 0.5))),
                      "0.5–<1": int(np.count_nonzero((data[key] >= 0.5) & (data[key] < 1.0))),
                      "1–<2.5": int(np.count_nonzero((data[key] >= 1.0) & (data[key] < 2.5))),
                      "2.5–<5": int(np.count_nonzero((data[key] >= 2.5) & (data[key] < 5.0))),
                      "5–<10": int(np.count_nonzero((data[key] >= 5.0) & (data[key] < 10.0))),
                      "≥10": int(np.count_nonzero(data[key] >= 10.0))}
                for key in ("reference", "BASE_ORIGINAL", "BASE_H", "POLICY_BG")
            },
            "figures": [{"name": name, "files": [f"{name}.{suffix}" for suffix in ("png", "pdf", "svg")]}
                        for name in ("hour_12_13_paired_precipitation", "hour_12_13_skill_factorial",
                                     "factorial_design_and_metric")],
            "scope": "One forecast hour (12–13 UTC), one spatial case, unweighted paired RN1 points; RN1 is a processed analysis, not gauge truth.",
            "reference_limitation": receipt.get("reference_limitation", receipt.get("limitation", "")),
            "provenance_note": "Renderer checks receipt source-record format and sealed analysis-output hashes, then recomputes plotted scores from the paired arrays. It does not reopen original host source files; runtime/source provenance remains in the scoring receipt audit.",
            "figure_sha256": {path.name: sha256(path) for path in sorted(stage.iterdir())},
        }
        (stage / "figure_manifest.json").write_text(json.dumps(manifest, indent=2,
            ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
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
        "docs/evidence/first_hour_factorial_20261030/figures"))
    args = parser.parse_args()
    print(json.dumps(run(args.analysis_dir, args.output_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
