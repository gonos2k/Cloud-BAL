#!/usr/bin/env python3
"""Render threshold-specific scores and paired precipitation response maps."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

LEADS = tuple(range(1, 7))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
POINTS = 3688
NEW_CASES = (
    "GATE_G50_90", "EQ_G50_90", "GATE_G75_95", "EQ_G75_95",
    "GATE_G90_99", "EQ_G90_99", "FIXED_ORIGINAL_100", "ORIGINAL_B1_100",
)
CONTEXT_CASES = ("ORIGINAL", "CONTROL_SNOW_300", "IMPROVED_BG_FIXED", "IMPROVED_SNOW_080")
CASE_ORDER = (*CONTEXT_CASES, *NEW_CASES)
SHORT_LABELS = {
    "ORIGINAL": "ORIGINAL",
    "CONTROL_SNOW_300": "CONTROL α=3",
    "IMPROVED_BG_FIXED": "B1 input + fixed exe",
    "IMPROVED_SNOW_080": "IMPROVED α=0.8",
    "GATE_G50_90": "Gate 50–90%",
    "EQ_G50_90": "Equal mass 50–90%",
    "GATE_G75_95": "Gate 75–95%",
    "EQ_G75_95": "Equal mass 75–95%",
    "GATE_G90_99": "Gate 90–99%",
    "EQ_G90_99": "Equal mass 90–99%",
    "FIXED_ORIGINAL_100": "Fixed exe / ORIGINAL input",
    "ORIGINAL_B1_100": "ORIGINAL exe / B1 input",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def verify_analysis(analysis: Path) -> tuple[dict, list[dict], list[dict]]:
    receipt_path = analysis / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("status") != "COMPLETE":
        raise ValueError("complete score receipt required")
    for name, record in receipt.get("analysis_outputs", {}).items():
        path = analysis / name
        if (path.is_symlink() or not path.is_file()
                or path.stat().st_size != record.get("size_bytes")
                or sha256(path) != record.get("sha256")):
            raise ValueError(f"analysis output hash mismatch: {name}")
    categorical = read_csv(analysis / "categorical_scores.csv")
    continuous = read_csv(analysis / "continuous_scores.csv")
    expected_cat = {(lead, case, threshold) for lead in LEADS for case in CASE_ORDER
                    for threshold in THRESHOLDS}
    cat = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): row
           for row in categorical}
    cont = {(int(row["lead_hour"]), row["case"]): row for row in continuous}
    if len(cat) != len(categorical) or set(cat) != expected_cat:
        raise ValueError("categorical table does not cover the frozen 12-case score grid")
    if len(cont) != len(continuous) or set(cont) != {(lead, case) for lead in LEADS for case in CASE_ORDER}:
        raise ValueError("continuous table does not cover the frozen score grid")
    if receipt.get("cases") != list(CASE_ORDER):
        raise ValueError("score receipt case order differs from the frozen figure design")
    for row in categorical:
        if int(row.get("valid_obs", row.get("points", -1))) != POINTS:
            raise ValueError("categorical row does not use the common paired-point count")
    return receipt, categorical, continuous


def load_arrays(analysis: Path) -> dict[int, dict[str, np.ndarray]]:
    arrays: dict[int, dict[str, np.ndarray]] = {}
    expected_keys = {"reference", *CASE_ORDER, "latitude", "longitude", "flat_index_yx"}
    for lead in LEADS:
        path = analysis / f"hour_{lead + 12}_arrays.npz"
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != expected_keys:
                raise ValueError(f"{path}: array keys differ from the frozen figure design")
            data = {key: np.asarray(archive[key]) for key in archive.files}
        if any(value.shape != (POINTS,) for value in data.values()):
            raise ValueError(f"{path}: arrays must contain {POINTS} paired points")
        if any(not np.isfinite(value).all() for key, value in data.items() if key != "flat_index_yx"):
            raise ValueError(f"{path}: non-finite array value")
        arrays[lead] = data
    first = arrays[1]
    for lead in LEADS[1:]:
        if any(not np.array_equal(first[name], arrays[lead][name])
               for name in ("latitude", "longitude", "flat_index_yx")):
            raise ValueError(f"lead +{lead}: paired points differ from lead +1")
    return arrays


def csi_algebra_matrices(analysis: Path, categorical: list[dict[str, str]],
                         threshold: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    exact_rows = read_csv(analysis / "csi_change_exact_counts.csv")
    exact = {(row["case"], int(row["lead_hour"]), float(row["threshold_mm"])): row
             for row in exact_rows}
    expected = {(case, lead, value) for case in CASE_ORDER if case != "ORIGINAL"
                for lead in LEADS for value in THRESHOLDS}
    if len(exact) != len(exact_rows) or set(exact) != expected:
        raise ValueError("exact CSI algebra table does not cover each nonbaseline case once")
    score = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): row
             for row in categorical}
    components = [np.zeros((len(CASE_ORDER), len(LEADS)), dtype=np.float64) for _ in range(3)]
    for case_index, case in enumerate(CASE_ORDER):
        for lead_index, lead in enumerate(LEADS):
            if case == "ORIGINAL":
                continue
            row = exact.get((case, lead, threshold))
            if row is None or row["csi_delta_exact_denominator"] in ("", "None"):
                for matrix in components:
                    matrix[case_index, lead_index] = np.nan
                continue
            dh = int(row["hit_delta_candidate_minus_baseline"])
            df = int(row["false_alarm_delta_candidate_minus_baseline"])
            h0 = int(row["baseline_hit"])
            d0 = int(row["baseline_CSI_denominator"])
            dc = int(row["candidate_CSI_denominator"])
            exact_numerator = d0 * dh - h0 * df
            if (exact_numerator != int(row["csi_delta_exact_numerator"])
                    or d0 * dc != int(row["csi_delta_exact_denominator"])
                    or d0 != int(row["observed_event_count"]) + int(row["baseline_false_alarm"])
                    or dc != int(row["observed_event_count"]) + int(row["candidate_false_alarm"])):
                raise ValueError(f"{case}/+{lead}/≥{threshold}: exact contingency-count identity failed")
            hit_term = dh / dc
            false_alarm_term = -h0 * df / (d0 * dc)
            total = hit_term + false_alarm_term
            baseline_csi = float(score[(lead, "ORIGINAL", threshold)]["CSI"])
            case_csi = float(score[(lead, case, threshold)]["CSI"])
            if not np.isclose(total, case_csi - baseline_csi, rtol=1e-12, atol=1e-12):
                raise ValueError(f"{case}/+{lead}/≥{threshold}: CSI algebra does not close")
            components[0][case_index, lead_index] = hit_term
            components[1][case_index, lead_index] = false_alarm_term
            components[2][case_index, lead_index] = total
    return tuple(components)


def write_png(fig, directory: Path, name: str) -> None:
    fig.savefig(directory / name, dpi=220, bbox_inches="tight", facecolor="white")


def annotation_color(image, value: float) -> str:
    red, green, blue, _ = image.cmap(image.norm(value))
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return "white" if luminance < 0.48 else "black"


def render_gate_maps(output: Path) -> dict:
    root = Path(__file__).resolve().parents[1]
    frozen = root / "docs/evidence/weak_strong_balance_20261030/runtime/frozen"
    maps_path = frozen / "initial_precip_gate_maps.npz"
    manifest_path = frozen / "gate_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256(maps_path) != manifest.get("frozen_map_sha256"):
        raise ValueError("frozen gate-map hash mismatch")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    pairs = ("G50_90", "G75_95", "G90_99")
    with np.load(maps_path, allow_pickle=False) as archive:
        expected = {"proxy", "latitude", "longitude"}
        expected.update(f"{pair}_{name}" for pair in pairs
                        for name in ("alpha", "gate_added_qsn_column_kg_m2",
                                     "eq_added_qsn_column_kg_m2"))
        if not expected.issubset(archive.files):
            raise ValueError("frozen gate map lacks dry-mass-weighted column additions")
        data = {name: np.asarray(archive[name]) for name in expected}
    lon, lat = data["longitude"], data["latitude"]
    proxy = data["proxy"]
    positive = proxy[proxy > 0]
    proxy_norm = LogNorm(vmin=max(float(positive.min()), 1e-12), vmax=float(positive.max()))
    snow_max = max(float(data[f"{pair}_{which}_qsn_column_kg_m2"].max())
                   for pair in pairs for which in ("gate_added", "eq_added"))
    snow_positive = np.concatenate([
        data[f"{pair}_{which}_qsn_column_kg_m2"].ravel()
        for pair in pairs for which in ("gate_added", "eq_added")
    ])
    snow_positive = snow_positive[snow_positive > 0]
    snow_norm = LogNorm(vmin=max(float(snow_positive.min()), 1e-8), vmax=snow_max)
    fig, axes = plt.subplots(3, 4, figsize=(15.5, 10.5), sharex=True, sharey=True,
                             layout="constrained")
    proxy_points = alpha_points = snow_points = None
    quantiles = {"G50_90": "50th–90th", "G75_95": "75th–95th", "G90_99": "90th–99th"}
    for row, pair in enumerate(pairs):
        fields = (("proxy", "Initial precipitating-water proxy (kg kg⁻¹)"),
                  (f"{pair}_alpha", "Gate multiplier α"),
                  (f"{pair}_gate_added_qsn_column_kg_m2", "Gated added QSNOW column (kg m⁻²)"),
                  (f"{pair}_eq_added_qsn_column_kg_m2", "Equal-mass added QSNOW column (kg m⁻²)"))
        for column, (field, title) in enumerate(fields):
            ax = axes[row, column]
            if column == 0:
                values = np.ma.masked_less_equal(data[field], 0.0)
                proxy_points = ax.scatter(lon, lat, c=values, cmap="viridis", norm=proxy_norm,
                                          s=2, marker="s", linewidths=0, rasterized=True)
            elif column == 1:
                alpha_points = ax.scatter(lon, lat, c=data[field], cmap="viridis", vmin=1, vmax=3,
                                          s=2, marker="s", linewidths=0, rasterized=True)
            else:
                snow_values = np.ma.masked_less_equal(data[field], 0)
                snow_points = ax.scatter(lon, lat, c=snow_values, cmap="magma", norm=snow_norm,
                                         s=2, marker="s",
                                         linewidths=0, rasterized=True)
            if row == 0:
                ax.set_title(title, fontsize=9)
            if column == 0:
                ax.set_ylabel(f"positive-X {quantiles[pair]} percentile\nLatitude (°N)")
            if row == 2:
                ax.set_xlabel("Longitude (°E)")
            ax.set_aspect(1.0 / np.cos(np.deg2rad(float(np.mean(lat)))))
            ax.grid(alpha=.15)
    fig.colorbar(proxy_points, ax=axes[:, 0], label="X (positive columns; logarithmic scale)",
                 orientation="horizontal", pad=.07, fraction=.035)
    fig.colorbar(alpha_points, ax=axes[:, 1], label="α (dimensionless)",
                 orientation="horizontal", pad=.07, fraction=.035)
    fig.colorbar(snow_points, ax=axes[:, 2:], label="Initial dry-mass-weighted added QSNOW (kg m⁻²; log scale)",
                 orientation="horizontal", pad=.07, fraction=.035)
    fig.suptitle(
        "Frozen initial-only gate and equal-mass placement controls\n"
        "ORIGINAL input only; no forecast/observation data in gate. Low-X columns retain α=1; "
        "equal-mass QSNOW totals match within 10⁻⁶ relative.", fontsize=12)
    write_png(fig, output, "initial_precip_gate_maps.png")
    plt.close(fig)
    return {"source_map_sha256": sha256(maps_path),
            "gate_manifest_sha256": sha256(manifest_path),
            "figure_sha256": sha256(output / "initial_precip_gate_maps.png")}


def render_concept_diagram(output: Path) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    fig, ax = plt.subplots(figsize=(14, 4.2))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 4.2)
    ax.axis("off")
    boxes = [
        (0.25, 2.45, 2.1, 1.0, "ORIGINAL initial column\nprecipitating-water proxy X"),
        (3.0, 2.45, 2.1, 1.0, "Positive-X percentile\ninterval and smooth gate α"),
        (5.8, 2.8, 2.1, 0.85, "Spatially gated\nQSNOW increase"),
        (5.8, 1.45, 2.1, 0.85, "Uniform increase with\nmatched initial snow mass"),
        (8.3, 2.1, 1.55, 1.0, "Paired six-hour\nWRF forecasts"),
        (10.2, 2.1, 1.35, 1.0, "Hourly total\nprecipitation"),
        (11.9, 2.1, 1.75, 1.0, "Lead × threshold\nCSI versus RN1"),
    ]
    for x, y, width, height, label in boxes:
        patch = FancyBboxPatch((x, y), width, height, boxstyle="round,pad=0.10",
                               linewidth=1.1, edgecolor="#38536d", facecolor="#f2f6fa")
        ax.add_patch(patch)
        ax.text(x + width / 2, y + height / 2, label, ha="center", va="center", fontsize=9)
    edges = [((2.35, 2.95), (3.0, 2.95)), ((5.1, 2.95), (5.8, 3.2)),
             ((5.1, 2.8), (5.8, 1.9)), ((7.9, 3.2), (8.3, 2.8)),
             ((7.9, 1.9), (8.3, 2.4)), ((9.85, 2.6), (10.2, 2.6)),
             ((11.55, 2.6), (11.9, 2.6))]
    for start, end in edges:
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=12,
                                     linewidth=1.1, color="#536b80"))
    ax.text(3.3, 1.15, "Gate is fixed from initial input only; it does not use a forecast or observation.",
            ha="center", fontsize=8.5, color="#444")
    ax.text(10.75, 1.15, "Score each lead and threshold against the same RN1 points.",
            ha="center", fontsize=8.5, color="#444")
    ax.text(6, 0.48, "The GATE − EQ score difference compares placement at matched initial QSNOW mass; it does not identify a process-level cause.",
            ha="center", fontsize=8.5, color="#444")
    fig.tight_layout()
    write_png(fig, output, "initial_gate_concept.png")
    plt.close(fig)
    return sha256(output / "initial_gate_concept.png")


def render(analysis: Path, output: Path) -> dict:
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError(f"output must be a regular directory: {output}")
    receipt, categorical, _ = verify_analysis(analysis)
    arrays = load_arrays(analysis)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    plt.rcParams.update({"font.size": 9, "svg.fonttype": "none"})
    cat = {(int(row["lead_hour"]), row["case"], float(row["threshold_mm"])): row
           for row in categorical}
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        for threshold in THRESHOLDS:
            scores = np.asarray([[float(cat[(lead, case, threshold)]["CSI"])
                                  if cat[(lead, case, threshold)]["CSI"] not in ("", "None") else np.nan
                                  for lead in LEADS] for case in CASE_ORDER])
            fig, ax = plt.subplots(figsize=(9.8, 5.2))
            for case, row in zip(CASE_ORDER, scores):
                ax.plot(LEADS, row, marker="o", markersize=3.5,
                        linewidth=1.25 if case in NEW_CASES else 1.0,
                        linestyle="-" if case in NEW_CASES else "--",
                        label=SHORT_LABELS[case])
            ax.set(xticks=LEADS, xlabel="Forecast lead (h)", ylabel="CSI",
                   ylim=(-0.03, 1.03), title=f"Hourly CSI at ≥{threshold:g} mm")
            ax.grid(True, alpha=.25)
            ax.legend(ncol=3, fontsize=7, frameon=False, loc="best")
            fig.tight_layout()
            write_png(fig, stage, f"csi_absolute_{threshold:g}mm.png")
            plt.close(fig)

            baseline = np.asarray([float(cat[(lead, "ORIGINAL", threshold)]["CSI"])
                                   for lead in LEADS])
            delta = scores - baseline[None, :]
            extent = max(0.01, float(np.nanmax(np.abs(delta))))
            norm = TwoSlopeNorm(vmin=-extent, vcenter=0, vmax=extent)
            fig, ax = plt.subplots(figsize=(9.8, 5.0))
            image = ax.imshow(delta, cmap="RdBu_r", norm=norm, aspect="auto", interpolation="nearest")
            for i in range(len(CASE_ORDER)):
                for j in range(len(LEADS)):
                    value = delta[i, j]
                    ax.text(j, i, "—" if not np.isfinite(value) else f"{value:+.5f}",
                            ha="center", va="center", fontsize=7,
                            color=annotation_color(image, value) if np.isfinite(value) else "black")
            ax.set(xticks=np.arange(6), xticklabels=[f"+{lead}" for lead in LEADS],
                   yticks=np.arange(len(CASE_ORDER)),
                   yticklabels=[SHORT_LABELS[case] for case in CASE_ORDER],
                   xlabel="Forecast lead", title=f"CSI difference at ≥{threshold:g} mm · case − ORIGINAL")
            ax.set_xticks(np.arange(-.5, 6, 1), minor=True)
            ax.set_yticks(np.arange(-.5, len(CASE_ORDER), 1), minor=True)
            ax.grid(which="minor", color="white", linewidth=.8)
            ax.tick_params(which="minor", bottom=False, left=False)
            fig.colorbar(image, ax=ax, label="ΔCSI (case − ORIGINAL)")
            fig.tight_layout()
            write_png(fig, stage, f"csi_delta_{threshold:g}mm.png")
            plt.close(fig)

        gate_rows = read_csv(analysis / "gate_equal_mass_comparison.csv")
        pair_names = ("G50_90", "G75_95", "G90_99")
        gate_delta = {(row["gate_case"], int(row["lead_hour"]), float(row["threshold_mm"])):
                      float(row["delta_CSI_gate_minus_equal_mass"])
                      for row in gate_rows if row.get("threshold_mm", "") not in ("", "None")
                      and row.get("delta_CSI_gate_minus_equal_mass") not in ("", "None")}
        required_gate_delta = {(f"GATE_{pair}", lead, threshold) for pair in pair_names
                               for lead in LEADS for threshold in THRESHOLDS}
        if set(gate_delta) != required_gate_delta:
            raise ValueError("gate/equal-mass score comparison lacks paired CSI cells")
        for threshold in THRESHOLDS:
            values = np.asarray([[gate_delta[(f"GATE_{pair}", lead, threshold)] for pair in pair_names]
                                 for lead in LEADS])
            gate_limit = max(float(np.max(np.abs(values))), 0.005)
            gate_norm = TwoSlopeNorm(vmin=-gate_limit, vcenter=0, vmax=gate_limit)
            fig, ax = plt.subplots(figsize=(8.0, 5.3))
            gate_image = ax.imshow(values, cmap="RdBu_r", norm=gate_norm, aspect="auto",
                                   interpolation="nearest")
            for row in range(6):
                for col in range(3):
                    value = float(values[row, col])
                    ax.text(col, row, f"{value:+.4f}", ha="center", va="center", fontsize=8,
                            color=annotation_color(gate_image, value))
            ax.set(xticks=np.arange(3), xticklabels=["50–90%", "75–95%", "90–99%"],
                   yticks=np.arange(6), yticklabels=[f"+{lead} h" for lead in LEADS],
                   xlabel="Positive initial-proxy percentile interval",
                   title=f"GATE − equal-mass control · CSI ≥{threshold:g} mm")
            ax.set_xticks(np.arange(-.5, 3, 1), minor=True)
            ax.set_yticks(np.arange(-.5, 6, 1), minor=True)
            ax.grid(which="minor", color="white", linewidth=.8)
            ax.tick_params(which="minor", bottom=False, left=False)
            fig.colorbar(gate_image, ax=ax, label="ΔCSI (GATE − EQ; shared zero center)")
            fig.tight_layout()
            write_png(fig, stage, f"gate_minus_equal_mass_csi_{threshold:g}mm.png")
            plt.close(fig)

        algebra_titles = ("Hit-change term · ΔH / Dcandidate",
                          "False-alarm term · −H0 ΔFA / (D0 Dcandidate)",
                          "Net change · ΔCSI")
        for threshold in THRESHOLDS:
            hit_term, false_alarm_term, net = csi_algebra_matrices(analysis, categorical, threshold)
            extent = max(0.005, *(float(np.nanmax(np.abs(values)))
                                  for values in (hit_term, false_alarm_term, net)))
            norm = TwoSlopeNorm(vmin=-extent, vcenter=0, vmax=extent)
            fig, axes = plt.subplots(1, 3, figsize=(15.0, 8.0), sharey=True,
                                     gridspec_kw={"wspace": 0.18}, layout="constrained")
            image = None
            for ax, values, title in zip(axes, (hit_term, false_alarm_term, net), algebra_titles):
                image = ax.imshow(values, cmap="RdBu_r", norm=norm, aspect="auto",
                                  interpolation="nearest")
                for row_index in range(len(CASE_ORDER)):
                    for lead_index in range(len(LEADS)):
                        value = values[row_index, lead_index]
                        ax.text(lead_index, row_index, "—" if not np.isfinite(value) else f"{value:+.3f}",
                                ha="center", va="center", fontsize=6.3,
                                color=annotation_color(image, value) if np.isfinite(value) else "black")
                ax.set(title=title, xticks=np.arange(6),
                       xticklabels=[f"+{lead}" for lead in LEADS],
                       yticks=np.arange(len(CASE_ORDER)),
                       yticklabels=[SHORT_LABELS[case] for case in CASE_ORDER])
                ax.set_xlabel("Forecast lead (h)")
                ax.set_xticks(np.arange(-.5, 6, 1), minor=True)
                ax.set_yticks(np.arange(-.5, len(CASE_ORDER), 1), minor=True)
                ax.grid(which="minor", color="white", linewidth=.8)
                ax.tick_params(which="minor", bottom=False, left=False)
            fig.colorbar(image, ax=axes, label=f"CSI algebra term (shared zero-centered range ±{extent:.3f})")
            fig.suptitle(f"Exact CSI algebra at ≥{threshold:g} mm · arithmetic decomposition, not physical attribution")
            write_png(fig, stage, f"csi_algebra_decomposition_{threshold:g}mm.png")
            plt.close(fig)

        # Each forecast map uses the identical RN1 points and shows amount plus
        # same-point difference from ORIGINAL; no interpolation fills unsampled cells.
        diff_min = min(float((arrays[lead][case] - arrays[lead]["ORIGINAL"]).min())
                       for lead in LEADS for case in CASE_ORDER)
        diff_max = max(float((arrays[lead][case] - arrays[lead]["ORIGINAL"]).max())
                       for lead in LEADS for case in CASE_ORDER)
        diff_extent = max(abs(diff_min), abs(diff_max), 0.01)
        precip_max = max(float(arrays[lead][case].max()) for lead in LEADS
                         for case in ("reference", *CASE_ORDER))
        lon, lat = arrays[1]["longitude"], arrays[1]["latitude"]
        for case in CASE_ORDER:
            fig, axes = plt.subplots(6, 3, figsize=(10.5, 14.0), sharex=True, sharey=True,
                                     layout="constrained")
            precip_points = delta_points = None
            for lead, axrow in zip(LEADS, axes):
                data = arrays[lead]
                fields = (("reference", "RN1"), (case, SHORT_LABELS[case]),
                          (case, f"{SHORT_LABELS[case]} − ORIGINAL"))
                for column, (field, title) in enumerate(fields):
                    ax = axrow[column]
                    if column == 2:
                        values = data[field] - data["ORIGINAL"]
                        delta_points = ax.scatter(lon, lat, c=values, cmap="RdBu_r",
                                                  norm=TwoSlopeNorm(vmin=-diff_extent, vcenter=0,
                                                                    vmax=diff_extent),
                                                  s=5, marker="s", linewidths=0, rasterized=True)
                    else:
                        precip_points = ax.scatter(lon, lat, c=data[field], cmap="viridis",
                                                   vmin=0, vmax=max(0.01, precip_max), s=5,
                                                   marker="s", linewidths=0, rasterized=True)
                    if lead == 1:
                        ax.set_title(title)
                    if column == 0:
                        ax.set_ylabel(f"+{lead} h\nLatitude")
                    if lead == LEADS[-1]:
                        ax.set_xlabel("Longitude (°E)")
                    ax.set_xlim(float(lon.min()), float(lon.max()))
                    ax.set_ylim(float(lat.min()), float(lat.max()))
                    ax.set_aspect(1.0 / np.cos(np.deg2rad(float(np.mean(lat)))))
                    ax.grid(alpha=.15)
            fig.colorbar(precip_points, ax=axes[:, :2], label="Hourly precipitation (mm)",
                         orientation="horizontal", pad=.035, fraction=.02)
            fig.colorbar(delta_points, ax=axes[:, 2],
                         label="Δ precipitation (mm)", orientation="horizontal", pad=.035, fraction=.02)
            fig.suptitle(f"Hourly precipitation · {SHORT_LABELS[case]}\n"
                         "Paired RN1 points only; no spatial interpolation. RN1 is processed analysis data.")
            write_png(fig, stage, f"maps_{case.lower()}.png")
            plt.close(fig)

        gate_receipt = render_gate_maps(stage)
        concept_sha256 = render_concept_diagram(stage)

        files = sorted(path for path in stage.glob("*.png"))
        manifest = {
            "schema": "weak_strong_balance_figures_v1", "status": "COMPLETE",
            "analysis_receipt_sha256": sha256(analysis / "receipt.json"),
            "renderer_sha256": sha256(Path(__file__).resolve()),
            "cases": list(CASE_ORDER), "lead_hours": list(LEADS),
            "thresholds_mm": list(THRESHOLDS), "shared_delta_precipitation_range_mm": [-diff_extent, diff_extent],
            "initial_gate_source": gate_receipt,
            "concept_diagram_sha256": concept_sha256,
            "files": {path.name: sha256(path) for path in files},
        }
        (stage / "figure_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if sha256(analysis / "receipt.json") != manifest["analysis_receipt_sha256"]:
            raise ValueError("analysis receipt changed during figure generation")
        backup_root = Path(tempfile.mkdtemp(prefix=f".{output.name}.backup-", dir=output.parent))
        backup, moved_old = backup_root / "previous-output", False
        try:
            if output.exists():
                os.replace(output, backup)
                moved_old = True
            os.replace(stage, output)
        except BaseException:
            if moved_old and not output.exists() and backup.exists():
                os.replace(backup, output)
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)
            if backup_root.exists():
                shutil.rmtree(backup_root)
        return manifest
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/evidence/weak_strong_balance_20261030/figures"))
    args = parser.parse_args()
    print(json.dumps(render(args.analysis_dir, args.output_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
