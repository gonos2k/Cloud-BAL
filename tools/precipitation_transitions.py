#!/usr/bin/env python3
"""Summarize paired-point precipitation changes across retained hourly arrays."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
from typing import Any

import numpy as np

ARMS = ("OFF", "HYDRO", "LIQUID")
PAIRS = (("OFF", "HYDRO"), ("OFF", "LIQUID"))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
EXPECTED_KEYS = {"reference", *ARMS, "latitude", "longitude", "flat_index_yx"}


def load_hour(path: Path) -> dict[str, np.ndarray]:
    """Load and validate one common paired sample from a retained NPZ."""
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != EXPECTED_KEYS:
            raise ValueError(f"{path}: expected NPZ keys {sorted(EXPECTED_KEYS)}")
        values = {key: np.asarray(archive[key]) for key in archive.files}
    size = values["reference"].size
    if size == 0 or any(value.shape != (size,) for value in values.values()):
        raise ValueError(f"{path}: all arrays must be nonempty vectors of equal length")
    for name, value in values.items():
        if name == "flat_index_yx":
            if not np.issubdtype(value.dtype, np.integer) or len(np.unique(value)) != size:
                raise ValueError(f"{path}: flat_index_yx must contain unique integers")
        elif not np.isfinite(value).all():
            raise ValueError(f"{path}: {name} contains non-finite values")
    if any((values[name] < 0).any() for name in ("reference", *ARMS)):
        raise ValueError(f"{path}: precipitation amounts must be nonnegative")
    if ((values["latitude"] < -90) | (values["latitude"] > 90)).any():
        raise ValueError(f"{path}: latitude must be within [-90, 90]")
    if ((values["longitude"] < -180) | (values["longitude"] > 180)).any():
        raise ValueError(f"{path}: longitude must be within [-180, 180]")
    if (values["flat_index_yx"] < 0).any():
        raise ValueError(f"{path}: flat_index_yx must be nonnegative")
    return values


def contingency(forecast: np.ndarray, reference: np.ndarray, threshold: float) -> dict[str, int]:
    fwet, owet = forecast >= threshold, reference >= threshold
    return {
        "hits": int(np.count_nonzero(fwet & owet)),
        "misses": int(np.count_nonzero(~fwet & owet)),
        "false_alarms": int(np.count_nonzero(fwet & ~owet)),
        "correct_dry": int(np.count_nonzero(~fwet & ~owet)),
    }


def summarize_hour(hour: int, fields: dict[str, np.ndarray]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    reference = fields["reference"]
    threshold_rows, continuous_rows = [], []
    for arm in (*ARMS, "REFERENCE"):
        forecast = fields["reference"] if arm == "REFERENCE" else fields[arm]
        error = forecast - reference
        wet = forecast >= 0.1
        wet_values = forecast[wet]
        quantiles = np.quantile(wet_values, (0.5, 0.9, 0.95, 0.99)) if wet_values.size else [None] * 4
        continuous_rows.append({
            "hour_utc": hour, "arm": arm, "points": reference.size,
            "mean_mm": float(np.mean(forecast)),
            "bias_mm": None if arm == "REFERENCE" else float(np.mean(error)),
            "mae_mm": None if arm == "REFERENCE" else float(np.mean(np.abs(error))),
            "rmse_mm": None if arm == "REFERENCE" else float(np.sqrt(np.mean(error**2))),
            "rain_fraction_ge_0_1": float(np.mean(wet)), "rain_points": int(wet.sum()),
            "rain_conditional_mean_mm": float(np.mean(wet_values)) if wet_values.size else None,
            "rain_max_mm": float(np.max(forecast)) if forecast.size else None,
            "rain_intensity_q50_mm": quantiles[0], "rain_intensity_q90_mm": quantiles[1],
            "rain_intensity_q95_mm": quantiles[2], "rain_intensity_q99_mm": quantiles[3],
        })
    for threshold in THRESHOLDS:
        counts = {arm: contingency(fields[arm], reference, threshold) for arm in ARMS}
        for arm in ARMS:
            threshold_rows.append({"hour_utc": hour, "threshold_mm": threshold,
                                   "arm": arm, **counts[arm]})
        for off, arm in PAIRS:
            off_hit = (fields[off] >= threshold) & (reference >= threshold)
            arm_hit = (fields[arm] >= threshold) & (reference >= threshold)
            off_fa = (fields[off] >= threshold) & (reference < threshold)
            arm_fa = (fields[arm] >= threshold) & (reference < threshold)
            threshold_rows.append({
                "hour_utc": hour, "threshold_mm": threshold, "arm": f"{off}->{arm}",
                "hit_gains": int(np.count_nonzero(~off_hit & arm_hit)),
                "hit_losses": int(np.count_nonzero(off_hit & ~arm_hit)),
                "false_alarm_gains": int(np.count_nonzero(~off_fa & arm_fa)),
                "false_alarm_losses": int(np.count_nonzero(off_fa & ~arm_fa)),
            })
    return threshold_rows, continuous_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def create_figures(out: Path, hourly: dict[int, dict[str, np.ndarray]]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    for ax, (hour, fields) in zip(axes.flat, sorted(hourly.items())):
        ref = fields["reference"]
        off_hit = (fields["OFF"] >= 5) & (ref >= 5)
        hydro_hit = (fields["HYDRO"] >= 5) & (ref >= 5)
        liquid_hit = (fields["LIQUID"] >= 5) & (ref >= 5)
        colors = np.full(ref.size, "#dddddd", dtype=object)
        colors[~off_hit & hydro_hit & liquid_hit] = "#756bb1"
        colors[~off_hit & hydro_hit & ~liquid_hit] = "#2b8cbe"
        colors[~off_hit & ~hydro_hit & liquid_hit] = "#41ab5d"
        colors[off_hit & (~hydro_hit | ~liquid_hit)] = "#d7301f"
        ax.scatter(fields["longitude"], fields["latitude"], c=colors, s=5, linewidths=0)
        ax.set_aspect(1.0 / np.cos(np.deg2rad(np.mean(fields["latitude"]))))
        ax.set_title(f"{hour:02d} UTC · OFF hit changes at ≥5 mm")
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    from matplotlib.lines import Line2D
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    fig.legend(handles=[
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#dddddd", label="No hit change", markersize=7),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#d7301f", label="OFF hit lost by an arm", markersize=7),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#2b8cbe", label="HYDRO-only gain", markersize=7),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#41ab5d", label="LIQUID-only gain", markersize=7),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#756bb1", label="Both-arm gain", markersize=7),
    ], loc="lower center", bbox_to_anchor=(0.5, 0.01), ncol=5)
    fig.savefig(out / "threshold_5mm_hit_transitions.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 4, figsize=(17, 4), constrained_layout=True)
    for ax, arm in zip(axes, ("REFERENCE", *ARMS)):
        for hour, fields in sorted(hourly.items()):
            values = fields["reference"] if arm == "REFERENCE" else fields[arm]
            wet = values[values >= 0.1]
            ax.scatter(np.full(wet.size, hour), wet, s=4, alpha=0.2)
        ax.set_yscale("symlog", linthresh=0.1)
        ax.set_title(f"{arm} wet-point amounts")
        ax.set_xlabel("Hour UTC"); ax.set_ylabel("Precipitation (mm)")
    fig.savefig(out / "rain_point_distributions.png", dpi=180)
    plt.close(fig)

    fields = hourly[13]
    ref = fields["reference"]
    off_hit = (fields["OFF"] >= 5) & (ref >= 5)
    lost = {
        arm: off_hit & ~((fields[arm] >= 5) & (ref >= 5))
        for arm in ("HYDRO", "LIQUID")
    }
    union = lost["HYDRO"] | lost["LIQUID"]
    fig, axes = plt.subplots(1, 2, figsize=(15, 7))
    lon, lat = fields["longitude"], fields["latitude"]
    xmin, xmax = lon[union].min() - 0.45, lon[union].max() + 0.45
    ymin, ymax = lat[union].min() - 0.18, lat[union].max() + 0.18
    rank_by_index = {int(i): rank + 1 for rank, i in enumerate(np.flatnonzero(union))}
    for ax, arm in zip(axes, ("HYDRO", "LIQUID")):
        colors = np.where(lost[arm], "#d7301f", "#dddddd")
        ax.scatter(lon, lat, c=colors, s=7, linewidths=0)
        midpoint = (lon[union].min() + lon[union].max()) / 2
        for side, label_x in (("left", xmin + 0.08), ("right", xmax - 0.08)):
            side_points = [int(i) for i in np.flatnonzero(union)
                           if (lon[i] <= midpoint) == (side == "left")]
            side_points.sort(key=lambda i: lat[i])
            label_ys = np.linspace(ymin + 0.06, ymax - 0.06, len(side_points))
            for i, label_y in zip(side_points, label_ys):
                ax.annotate(f"{rank_by_index[i]:02d}", xy=(lon[i], lat[i]),
                            xytext=(label_x, label_y), textcoords="data", fontsize=7,
                            ha="center", va="center",
                            arrowprops={"arrowstyle": "-", "color": "#777777", "lw": 0.5})
        ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax)
        ax.set_aspect(1.0 / np.cos(np.deg2rad(np.mean(fields["latitude"]))))
        ax.set_title(f"Hour 12–13 UTC · ≥5 mm hits · {arm}")
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    from matplotlib.lines import Line2D
    fig.tight_layout(rect=(0, 0.13, 1, 0.94))
    fig.legend(handles=[
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#d7301f",
               label="OFF hit lost by this arm", markersize=8),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#dddddd",
               label="Other points (including union points not lost by this arm)", markersize=8),
    ], loc="lower center", bbox_to_anchor=(0.5, 0.01), ncol=2)
    fig.savefig(out / "hour_13_ge5mm_lost_hit_focus.png", dpi=200)
    plt.close(fig)

    hours = sorted(hourly)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    for arm in ARMS:
        hits, fas = [], []
        for hour in hours:
            c = contingency(hourly[hour][arm], hourly[hour]["reference"], 5.0)
            hits.append(c["hits"]); fas.append(c["false_alarms"])
        axes[0].plot(hours, hits, marker="o", label=arm)
        axes[1].plot(hours, fas, marker="o", label=arm)
    for ax, label in zip(axes, ("Hits ≥5 mm", "False alarms ≥5 mm")):
        ax.set_xticks(hours); ax.set_xlabel("Hour UTC"); ax.set_ylabel("Paired points"); ax.set_title(label); ax.legend()
    fig.savefig(out / "hourly_threshold_5mm_transitions.png", dpi=180)
    plt.close(fig)


def write_results(
    output_dir: Path, hourly: dict[int, dict[str, np.ndarray]],
    threshold_rows: list[dict[str, Any]], continuous_rows: list[dict[str, Any]],
    sizes: set[int],
) -> dict[str, Any]:
    write_csv(output_dir / "threshold_counts_and_transitions.csv", threshold_rows)
    write_csv(output_dir / "continuous_metrics.csv", continuous_rows)

    first = hourly[13]
    ref = first["reference"]
    off_hit = (first["OFF"] >= 5) & (ref >= 5)
    lost_by = {arm: off_hit & ~((first[arm] >= 5) & (ref >= 5)) for arm in ("HYDRO", "LIQUID")}
    union = lost_by["HYDRO"] | lost_by["LIQUID"]
    focus_rows = []
    for i in np.flatnonzero(union):
        focus_rows.append({
            "focus_rank": int(np.searchsorted(np.flatnonzero(union), i) + 1),
            "flat_index_yx": int(first["flat_index_yx"][i]), "latitude": first["latitude"][i],
            "longitude": first["longitude"][i], "reference_mm": ref[i], "OFF_mm": first["OFF"][i],
            "HYDRO_mm": first["HYDRO"][i], "LIQUID_mm": first["LIQUID"][i],
            "OFF_hit_ge_5": int(off_hit[i]), "HYDRO_hit_ge_5": int((first["HYDRO"][i] >= 5) & (ref[i] >= 5)),
            "LIQUID_hit_ge_5": int((first["LIQUID"][i] >= 5) & (ref[i] >= 5)),
            "HYDRO_lost_hit": int(lost_by["HYDRO"][i]), "LIQUID_lost_hit": int(lost_by["LIQUID"][i]),
        })
    write_csv(output_dir / "hour_13_ge5mm_off_hit_lost_union.csv", focus_rows)
    summary = {
        "hours_utc": list(range(13, 19)), "thresholds_mm": list(THRESHOLDS),
        "paired_points_per_hour": next(iter(sizes)), "hourly_flat_index_identity": True,
        "hour_13_off_hit_lost_union_ge_5mm": len(focus_rows),
        "hour_13_hydro_lost_hits_ge_5mm": int(lost_by["HYDRO"].sum()),
        "hour_13_liquid_lost_hits_ge_5mm": int(lost_by["LIQUID"].sum()),
        "hour_13_off_hits_ge_5mm": int(off_hit.sum()),
        "hour_13_hydro_hits_ge_5mm": int(((first["HYDRO"] >= 5) & (ref >= 5)).sum()),
        "hour_13_liquid_hits_ge_5mm": int(((first["LIQUID"] >= 5) & (ref >= 5)).sum()),
        "hour_13_hydro_common_hits_ge_5mm": int((off_hit & ((first["HYDRO"] >= 5) & (ref >= 5))).sum()),
        "hour_13_liquid_common_hits_ge_5mm": int((off_hit & ((first["LIQUID"] >= 5) & (ref >= 5))).sum()),
        "scope": f"Unweighted statistics over the retained common {next(iter(sizes))}-point paired sample; no spatial coverage extrapolation.",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    create_figures(output_dir, hourly)
    return summary


def run(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise ValueError(f"output directory must not already exist: {output_dir}")
    hourly, threshold_rows, continuous_rows = {}, [], []
    for hour in range(13, 19):
        fields = load_hour(input_dir / f"hour_{hour}_arrays.npz")
        hourly[hour] = fields
        trows, crows = summarize_hour(hour, fields)
        threshold_rows.extend(trows); continuous_rows.extend(crows)
    sizes = {data["reference"].size for data in hourly.values()}
    first_indices = hourly[13]["flat_index_yx"]
    first_latitude, first_longitude = hourly[13]["latitude"], hourly[13]["longitude"]
    if len(sizes) != 1 or any(
        not np.array_equal(data["flat_index_yx"], first_indices)
        or not np.array_equal(data["latitude"], first_latitude)
        or not np.array_equal(data["longitude"], first_longitude)
        for data in list(hourly.values())[1:]
    ):
        raise ValueError("all six hours must use identical paired indices and coordinates")
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        return write_results(output_dir, hourly, threshold_rows, continuous_rows, sizes)
    except Exception:
        shutil.rmtree(output_dir)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(run(args.input_dir, args.output_dir))


if __name__ == "__main__":
    main()
