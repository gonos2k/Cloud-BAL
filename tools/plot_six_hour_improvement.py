#!/usr/bin/env python3
"""Render paired six-hour precipitation maps and skill summaries."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np

CASES = ("ORIGINAL", "CURRENT_HYDRO", "IMPROVED_BG_FIXED")
LABELS = {"ORIGINAL": "Original", "CURRENT_HYDRO": "Current HYDRO",
          "IMPROVED_BG_FIXED": "Improved background · fixed WRF"}
COLORS = {"ORIGINAL": "#555555", "CURRENT_HYDRO": "#0072B2",
          "IMPROVED_BG_FIXED": "#D55E00"}
HOURS = tuple(range(13, 19))
LEADS = tuple(range(1, 7))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
ARRAY_KEYS = {"reference", *CASES, "latitude", "longitude", "flat_index_yx"}
TIME_FIELDS = {"valid_utc", "window_start_utc", "window_end_utc"}
CAT_FIELDS = {"lead_hour", *TIME_FIELDS, "case", "threshold_mm", "points", "hit", "miss",
              "false_alarm", "correct_dry", "CSI", "ETS", "POD", "FAR", "frequency_bias"}
CONT_FIELDS = {"lead_hour", *TIME_FIELDS, "case", "points", "mean_forecast_mm", "mean_reference_mm",
               "mean_error_mm", "MAE_mm", "RMSE_mm"}
TRANSITION_FIELDS = {"lead_hour", *TIME_FIELDS, "baseline", "candidate", "threshold_mm",
                     "hit_gains", "hit_losses", "false_alarm_gains", "false_alarm_losses"}


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
            missing = required - set(reader.fieldnames or ())
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        return list(reader)


def validate_receipt(path: Path) -> dict:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    expected_windows = []
    for lead in LEADS:
        start = datetime(2026, 8, 16, 11 + lead, tzinfo=timezone.utc)
        end = start + timedelta(hours=1)
        expected_windows.append({"lead_hour": lead, "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 "valid_time": end.strftime("%Y-%m-%dT%H:%M:%SZ")})
    if (receipt.get("status") != "COMPLETE" or receipt.get("points_per_hour") != 3688
            or receipt.get("cases") != list(CASES) or receipt.get("hours_utc") != list(HOURS)
            or tuple(float(value) for value in receipt.get("thresholds_mm", ())) != THRESHOLDS
            or receipt.get("time_windows_utc") != expected_windows
            or receipt.get("precipitation_window")
            != "One-hour increment between consecutive WRF histories; not a 0–lead accumulation."):
        raise ValueError("score receipt is incomplete or does not match the six-hour case schema")
    sources = receipt.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("score receipt has no source hash records")
    for record in sources:
        digest = record.get("sha256")
        if (not isinstance(record.get("path"), str) or not record["path"]
                or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or not isinstance(record.get("size"), int) or record["size"] < 0):
            raise ValueError("score receipt contains a malformed source hash record")
    return receipt


def validate_analysis_outputs(analysis: Path, receipt: dict) -> list[Path]:
    expected = {*(f"hour_{hour}_arrays.npz" for hour in HOURS),
                "categorical_scores.csv", "continuous_scores.csv", "transitions.csv"}
    records = receipt.get("analysis_outputs")
    if not isinstance(records, dict) or set(records) != expected:
        raise ValueError("score receipt does not bind the complete six-hour output set")
    paths = []
    for name, record in records.items():
        path = analysis / name
        if (not path.is_file() or path.stat().st_size != record.get("size_bytes")
                or sha256(path) != record.get("sha256")):
            raise ValueError(f"analysis output hash mismatch: {path}")
        paths.append(path)
    return paths


def load_hour(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != ARRAY_KEYS:
            raise ValueError(f"{path}: unexpected NPZ keys {sorted(archive.files)}")
        data = {key: np.asarray(archive[key]) for key in archive.files}
    if any(value.shape != (3688,) for value in data.values()):
        raise ValueError(f"{path}: all arrays must be vectors of exactly 3688 paired points")
    for name, values in data.items():
        if name == "flat_index_yx":
            if not np.issubdtype(values.dtype, np.integer) or np.unique(values).size != 3688:
                raise ValueError(f"{path}: flat_index_yx must contain unique integers")
        elif not np.isfinite(values).all():
            raise ValueError(f"{path}: {name} contains non-finite values")
    if any((data[name] < 0).any() for name in ("reference", *CASES)):
        raise ValueError(f"{path}: precipitation must be nonnegative")
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


def validate_window(row: dict[str, str], lead: int) -> None:
    start = datetime(2026, 8, 16, 11 + lead, tzinfo=timezone.utc)
    expected = {"valid_utc": start + timedelta(hours=1),
                "window_start_utc": start, "window_end_utc": start + timedelta(hours=1)}
    for field, value in expected.items():
        try:
            actual = datetime.fromisoformat(row[field].replace("Z", "+00:00"))
        except (ValueError, AttributeError) as error:
            raise ValueError(f"invalid {field} timestamp for lead +{lead}") from error
        if actual.tzinfo is None or actual.astimezone(timezone.utc) != value:
            raise ValueError(f"{field} does not match lead +{lead}'s one-hour UTC window")


def validate_scores(analysis: Path, hours: dict[int, dict[str, np.ndarray]]) -> tuple[list, list, list]:
    categorical = read_csv(analysis / "categorical_scores.csv", CAT_FIELDS)
    continuous = read_csv(analysis / "continuous_scores.csv", CONT_FIELDS)
    transitions = read_csv(analysis / "transitions.csv", TRANSITION_FIELDS)
    expected_categorical = {(lead, case, threshold) for lead in LEADS
                            for case in CASES for threshold in THRESHOLDS}
    cat_by_key = {}
    for row in categorical:
        key = (int(row["lead_hour"]), row["case"], float(row["threshold_mm"]))
        validate_window(row, key[0])
        if key in cat_by_key:
            raise ValueError(f"duplicate categorical score row: {key}")
        cat_by_key[key] = row
    if set(cat_by_key) != expected_categorical:
        raise ValueError("categorical table does not contain exactly 108 expected rows")
    cont_by_key = {}
    for row in continuous:
        key = (int(row["lead_hour"]), row["case"])
        validate_window(row, key[0])
        if key in cont_by_key:
            raise ValueError(f"duplicate continuous score row: {key}")
        cont_by_key[key] = row
    expected_continuous = {(lead, case) for lead in LEADS for case in CASES}
    if set(cont_by_key) != expected_continuous:
        raise ValueError("continuous table does not contain exactly 18 expected rows")

    expected_transitions = {(lead, baseline, "IMPROVED_BG_FIXED", threshold)
                            for lead in LEADS for baseline in ("ORIGINAL", "CURRENT_HYDRO")
                            for threshold in THRESHOLDS}
    trans_by_key = {}
    for row in transitions:
        key = (int(row["lead_hour"]), row["baseline"], row["candidate"],
               float(row["threshold_mm"]))
        validate_window(row, key[0])
        if key in trans_by_key:
            raise ValueError(f"duplicate transition row: {key}")
        trans_by_key[key] = row
    if set(trans_by_key) != expected_transitions:
        raise ValueError("transition table does not contain exactly 72 expected rows")

    for lead in LEADS:
        values = hours[lead + 12]
        reference = values["reference"]
        for case in CASES:
            forecast = values[case]
            error = forecast - reference
            cont = cont_by_key[(lead, case)]
            if int(cont["points"]) != 3688:
                raise ValueError(f"{case} lead +{lead}: continuous point count mismatch")
            for field, value in (("mean_forecast_mm", np.mean(forecast)),
                                 ("mean_reference_mm", np.mean(reference)),
                                 ("mean_error_mm", np.mean(error)),
                                 ("MAE_mm", np.mean(np.abs(error))),
                                 ("RMSE_mm", np.sqrt(np.mean(error ** 2)))):
                close(float(cont[field]), float(value), f"{case} lead +{lead}.{field}")
            for threshold in THRESHOLDS:
                hits, misses, false_alarms, dry = contingency(forecast, reference, threshold)
                row = cat_by_key[(lead, case, threshold)]
                counts = tuple(int(row[name]) for name in ("hit", "miss", "false_alarm", "correct_dry"))
                expected_counts = tuple(int(np.count_nonzero(mask))
                                        for mask in (hits, misses, false_alarms, dry))
                if int(row["points"]) != 3688 or counts != expected_counts:
                    raise ValueError(f"{case} lead +{lead} at {threshold:g} mm: contingency mismatch")
                denom = sum(expected_counts[:3])
                csi = expected_counts[0] / denom if denom else 0.0
                close(float(row["CSI"]), csi, f"{case} lead +{lead}.CSI@{threshold:g}")

        for baseline in ("ORIGINAL", "CURRENT_HYDRO"):
            for threshold in THRESHOLDS:
                base_hit, _, base_fa, _ = contingency(values[baseline], reference, threshold)
                new_hit, _, new_fa, _ = contingency(values["IMPROVED_BG_FIXED"], reference, threshold)
                row = trans_by_key[(lead, baseline, "IMPROVED_BG_FIXED", threshold)]
                expected = (int(np.count_nonzero(~base_hit & new_hit)),
                            int(np.count_nonzero(base_hit & ~new_hit)),
                            int(np.count_nonzero(~base_fa & new_fa)),
                            int(np.count_nonzero(base_fa & ~new_fa)))
                actual = tuple(int(row[name]) for name in (
                    "hit_gains", "hit_losses", "false_alarm_gains", "false_alarm_losses"))
                if actual != expected:
                    raise ValueError(f"transition count mismatch: lead +{lead}, {baseline}, {threshold:g} mm")
    return categorical, continuous, transitions


def save_figure(figure, stage: Path, name: str) -> None:
    figure.savefig(stage / f"{name}.png", dpi=240, bbox_inches="tight", facecolor="white")
    figure.savefig(stage / f"{name}.pdf", bbox_inches="tight", facecolor="white",
                   metadata={"CreationDate": None, "ModDate": None,
                             "Creator": "plot_six_hour_improvement.py"})
    figure.savefig(stage / f"{name}.svg", bbox_inches="tight", facecolor="white",
                   metadata={"Date": None, "Creator": "plot_six_hour_improvement.py"})


def map_figure(plt, hours: dict[int, dict[str, np.ndarray]], leads: tuple[int, ...],
               extent: tuple[float, float, float, float], stage: Path) -> None:
    from matplotlib.colors import BoundaryNorm, ListedColormap

    levels = (0, 0.1, 0.5, 1, 2.5, 5, 10, 20, 50, 100)
    colors = ("#f3f4f6", "#c6dbef", "#9ecae1", "#6baed6", "#41b6c4",
              "#1d91c0", "#225ea8", "#253494", "#4a1486")
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(levels, cmap.N, clip=True)
    figure, axes = plt.subplots(len(leads), 4, figsize=(15.0, 3.25 * len(leads)),
                                sharex=True, sharey=True, layout="constrained")
    keys = ("reference", *CASES)
    labels = ("RN1 · processed analysis", *[LABELS[case] for case in CASES])
    scatter = None
    for row_index, lead in enumerate(leads):
        hour = lead + 12
        values = hours[hour]
        lon, lat = values["longitude"], values["latitude"]
        for column, (key, label) in enumerate(zip(keys, labels)):
            ax = axes[row_index, column]
            scatter = ax.scatter(lon, lat, c=values[key], cmap=cmap, norm=norm,
                                s=7.5, marker="s", linewidths=0, rasterized=True)
            if row_index == 0:
                ax.set_title(label, loc="left", fontsize=9.5, fontweight="semibold")
            if column == 0:
                ax.set_ylabel(f"+{lead} h\nLatitude (°N)")
            if row_index == len(leads) - 1:
                ax.set_xlabel("Longitude (°E)")
            ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
            ax.set_aspect(1.0 / np.cos(np.deg2rad(float(np.mean(lat)))))
            ax.grid(color="white", linewidth=0.3, alpha=0.55)
    colorbar = figure.colorbar(scatter, ax=axes, orientation="horizontal", pad=0.065,
                               fraction=0.035, ticks=levels, extend="max")
    colorbar.set_label("One-hour precipitation accumulation (mm)")
    start_hour = leads[0] + 11
    end_hour = leads[-1] + 12
    figure.suptitle(f"Paired precipitation fields · leads +{leads[0]}–+{leads[-1]} h · "
                    f"{start_hour:02d}:00–{end_hour:02d}:00 UTC",
                    fontsize=13, fontweight="semibold")
    figure.text(0.5, -0.005,
                "Each marker is a retained paired point; maps do not interpolate between points or imply full spatial coverage. "
                "RN1 is a processed analysis, not gauge truth.",
                ha="center", va="top", fontsize=8, color="#444444")
    name = f"precipitation_maps_leads_{leads[0]}_{leads[-1]}"
    save_figure(figure, stage, name)
    plt.close(figure)


def skill_figure(plt, categorical: list[dict], continuous: list[dict],
                 hours: dict[int, dict[str, np.ndarray]], stage: Path) -> None:
    from matplotlib.colors import TwoSlopeNorm
    from matplotlib.lines import Line2D

    cat = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): float(row["CSI"])
           for row in categorical}
    cont = {(int(row["lead_hour"]), row["case"]): row for row in continuous}
    csi_matrices = {case: np.asarray([[cat[(lead, case, threshold)] for threshold in THRESHOLDS]
                                      for lead in LEADS]) for case in CASES}
    delta = csi_matrices["IMPROVED_BG_FIXED"] - csi_matrices["ORIGINAL"]
    delta_limit = max(0.05, np.ceil(np.max(np.abs(delta)) / 0.05) * 0.05)
    figure = plt.figure(figsize=(15.5, 9.5))
    grid = figure.add_gridspec(2, 4, height_ratios=(1.16, 0.84), hspace=0.4, wspace=0.35,
                               left=0.055, right=0.96, bottom=0.12, top=0.88)
    csi_axes = [figure.add_subplot(grid[0, index]) for index in range(4)]
    heatmaps = [*(csi_matrices[case] for case in CASES), delta]
    titles = ("ORIGINAL", "CURRENT_HYDRO", "IMPROVED_BG_FIXED", "ΔCSI · improved − original")
    csi_cmap = plt.get_cmap("YlGnBu")
    delta_cmap = plt.get_cmap("RdBu_r")
    for index, (ax, matrix, title) in enumerate(zip(csi_axes, heatmaps, titles)):
        if index < 3:
            image = ax.imshow(matrix, origin="upper", aspect="auto", cmap=csi_cmap,
                              vmin=0, vmax=1, interpolation="nearest")
            for y in range(6):
                for x in range(6):
                    ax.text(x, y, f"{matrix[y, x]:.2f}", ha="center", va="center",
                            fontsize=7, color="#17212b" if matrix[y, x] < 0.62 else "white")
        else:
            image = ax.imshow(matrix, origin="upper", aspect="auto", cmap=delta_cmap,
                              norm=TwoSlopeNorm(vmin=-delta_limit, vcenter=0, vmax=delta_limit),
                              interpolation="nearest")
            for y in range(6):
                for x in range(6):
                    ax.text(x, y, f"{matrix[y, x]:+.2f}", ha="center", va="center",
                            fontsize=7, color="#17212b" if abs(matrix[y, x]) < 0.62 * delta_limit else "white")
        ax.set_title(title, fontsize=9, fontweight="semibold")
        ax.set_xticks(range(6), [f"{threshold:g}" for threshold in THRESHOLDS], fontsize=7.5)
        ax.set_yticks(range(6), [f"+{lead}" for lead in LEADS], fontsize=7.5)
        ax.set_xlabel("1-h precipitation threshold (mm)", fontsize=8)
        ax.set_ylabel("Forecast lead (h)", fontsize=8)
        ax.set_xticks(np.arange(-0.5, 6, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, 6, 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=1.2)
        ax.tick_params(which="minor", bottom=False, left=False)
        colorbar = figure.colorbar(image, ax=ax, fraction=0.05, pad=0.03)
        colorbar.ax.tick_params(labelsize=7)
        colorbar.set_label("ΔCSI" if index == 3 else "CSI", fontsize=8)

    metrics = (("MAE_mm", "MAE · lower is better"), ("RMSE_mm", "RMSE · lower is better"))
    for column, (field, title) in enumerate(metrics):
        ax = figure.add_subplot(grid[1, column * 2:column * 2 + 2])
        for case in CASES:
            values = [float(cont[(lead, case)][field]) for lead in LEADS]
            ax.plot(LEADS, values, color=COLORS[case], marker="o", markersize=4,
                    linewidth=1.8, label=LABELS[case])
        ax.set(title=title, xlabel="Forecast lead (h)", ylabel="mm", xticks=LEADS)
        ax.grid(alpha=0.24)
        ax.set_axisbelow(True)
    handles = [Line2D([0], [0], color=COLORS[case], marker="o", linewidth=1.7,
                      label=LABELS[case]) for case in CASES]
    figure.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.985),
                  ncol=3, frameon=False, fontsize=8.5)
    figure.suptitle("Six-hour paired-point precipitation skill against RN1", y=1.02,
                    fontsize=14, fontweight="semibold")
    figure.text(0.5, 0.01,
                "Each score uses one-hour accumulation windows and 3,688 paired points; leads are not cumulative totals. "
                "ΔCSI is a paired score difference, not physical causal attribution; one event and one spatial case only.",
                ha="center", fontsize=8, color="#444444")
    save_figure(figure, stage, "six_hour_skill_summary")
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
    receipt = validate_receipt(analysis / "receipt.json")
    receipt_digest = sha256(analysis / "receipt.json")
    input_paths = validate_analysis_outputs(analysis, receipt)
    renderer_path = Path(__file__).resolve()
    renderer_digest = sha256(renderer_path)
    hours = {hour: load_hour(analysis / f"hour_{hour}_arrays.npz") for hour in HOURS}
    first = hours[HOURS[0]]
    for hour in HOURS[1:]:
        current = hours[hour]
        for name in ("flat_index_yx", "latitude", "longitude"):
            if not np.array_equal(first[name], current[name]):
                raise ValueError(f"hour {hour}: paired grid identity differs for {name}")
    categorical, continuous, transitions = validate_scores(analysis, hours)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "Noto Sans CJK JP", "font.size": 9,
                         "axes.titlesize": 10, "axes.labelsize": 9,
                         "svg.fonttype": "none", "svg.hashsalt": "six-hour-improvement-v1",
                         "pdf.fonttype": 42})
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        lon, lat = first["longitude"], first["latitude"]
        extent = (float(lon.min()), float(lon.max()), float(lat.min()), float(lat.max()))
        map_figure(plt, hours, (1, 2, 3), extent, stage)
        map_figure(plt, hours, (4, 5, 6), extent, stage)
        skill_figure(plt, categorical, continuous, hours, stage)
        if (sha256(analysis / "receipt.json") != receipt_digest
                or sha256(renderer_path) != renderer_digest):
            raise ValueError("score receipt or renderer changed during figure generation")
        validate_analysis_outputs(analysis, receipt)
        all_inputs = [*input_paths, analysis / "receipt.json"]
        manifest = {
            "schema": "six_hour_improvement_figures_v1", "status": "COMPLETE",
            "renderer": {"path": str(renderer_path), "sha256": renderer_digest,
                         "size_bytes": renderer_path.stat().st_size},
            "receipt_sha256": receipt_digest,
            "cases": list(CASES), "hours_utc": list(HOURS), "lead_hours": list(LEADS),
            "thresholds_mm": list(THRESHOLDS), "paired_points_per_hour": 3688,
            "accumulation_definition": "Each forecast value and score is a one-hour increment over its valid window, not a 0-to-lead cumulative total.",
            "inputs": [{"path": str(path.resolve()), "sha256": sha256(path),
                        "size_bytes": path.stat().st_size} for path in all_inputs],
            "point_counts_by_hour": {str(hour): 3688 for hour in HOURS},
            "rain_points_ge_threshold_by_hour": {
                str(hour): {
                    name: {f"{threshold:g} mm": int(np.count_nonzero(hours[hour][name] >= threshold))
                           for threshold in THRESHOLDS}
                    for name in ("reference", *CASES)
                }
                for hour in HOURS
            },
            "reference_limitation": receipt.get("reference_limitation", ""),
            "provenance_note": "Renderer validates the scoring receipt schema and sealed analysis-output hashes, then recomputes categorical, continuous, and transition scores from the paired arrays. It does not reopen original host source files; runtime/source provenance remains in the scoring receipt audit.",
            "scope": "Six hourly accumulations, one spatial case, 3,688 unweighted paired points per hour; RN1 is a processed analysis, not gauge truth.",
            "figures": ["precipitation_maps_leads_1_3", "precipitation_maps_leads_4_6",
                        "six_hour_skill_summary"],
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
        "docs/evidence/six_hour_improvement_20261030/figures"))
    args = parser.parse_args()
    print(json.dumps(run(args.analysis_dir, args.output_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
