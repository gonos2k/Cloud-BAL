#!/usr/bin/env python3
"""Plot same-level C1 C-H wind increments and their saved early response."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from pr98_native_effect import COMPOSITION, EXECUTABLE_SHA256, RUNS, cloud
from pr86_compare_response import load_history
from pr94_hydro_response import validate_receipt_triplet


def render(output: Path, native_level: int = 16) -> dict:
    """Keep the grid level and original QC footprint fixed across panels."""
    identities, receipts, histories = {}, {}, {}
    for arm, root in RUNS.items():
        histories[arm], receipts[arm], identities[arm] = cloud.verify_run(arm, root)
    validate_receipt_triplet(receipts, expected_executable_sha256=EXECUTABLE_SHA256)
    fields = {}
    for second, frame in ((0, 0), (60, 1)):
        fields[second] = {}
        for arm in ("HYDRO", "COUPLED"):
            timestamp, values, _ = load_history(histories[arm], frame)
            expected = f"2026-08-16_13:{second // 60:02d}:00"
            if timestamp != expected:
                raise ValueError(f"unexpected {arm} saved time: {timestamp}")
            fields[second][arm] = values
    shape = fields[0]["HYDRO"]["U"].shape
    if shape != (39, 280, 232) or not 1 <= native_level <= shape[0]:
        raise ValueError("unexpected C1 active grid or native level")
    composition = json.loads(COMPOSITION.read_text())["composed_qc_vertical_influence"]
    masks = cloud.make_masks(composition, shape)
    mask = masks["original_613_native_support"]
    if int(mask.sum()) != 613:
        raise ValueError("original QC support changed")
    columns = np.any(mask, axis=0)
    level = native_level - 1

    def delta(second: int, name: str) -> np.ndarray:
        return (fields[second]["COUPLED"][name] - fields[second]["HYDRO"][name])[level]

    du, dv = delta(0, "U"), delta(0, "V")
    magnitude = np.hypot(du, dv)
    peak_j, peak_i = np.unravel_index(int(np.argmax(magnitude)), magnitude.shape)
    peak = (int(peak_i + 2), int(peak_j + 2))
    panels = (
        ("Initial U increment", du, "m s-1", True),
        ("Initial V increment", dv, "m s-1", True),
        ("Initial wind-increment magnitude", magnitude, "m s-1", False),
        ("60 s pressure difference", delta(60, "pressure"), "Pa", True),
        ("60 s geopotential difference", delta(60, "geopotential"), "m2 s-2", True),
        ("60 s W difference", delta(60, "W"), "m s-1", True),
    )
    output.mkdir(parents=True, exist_ok=False)
    coordinates = (np.arange(2, 234), np.arange(2, 282))
    buffer_rows, buffer_cols = np.nonzero(masks["fixed_5_cell_chebyshev_buffer"].any(axis=0))
    zoom = (float(buffer_cols.min() + 1.5), float(buffer_cols.max() + 2.5),
            float(buffer_rows.min() + 1.5), float(buffer_rows.max() + 2.5))
    summaries = []
    for title, values, unit, _ in panels:
        if not np.isfinite(values).all():
            raise ValueError(f"nonfinite panel: {title}")
        summaries.append({"title": title, "minimum": float(values.min()),
                          "maximum": float(values.max()), "units": unit})
    for basename, bounds, view in (("same_level_response", zoom, "fixed five-cell QC buffer"),
                                   ("full_domain_response", None, "full active grid")):
        figure, axes = plt.subplots(2, 3, figsize=(13, 10), constrained_layout=True)
        for axis, (title, values, unit, signed) in zip(axes.flat, panels, strict=True):
            limit = float(np.max(np.abs(values))) or 1.0
            image = axis.imshow(values, origin="lower", extent=(1.5, 233.5, 1.5, 281.5),
                                vmin=-limit if signed else 0, vmax=limit,
                                cmap="RdBu_r" if signed else "viridis")
            axis.contour(*coordinates, columns.astype(int), levels=[0.5], colors="0.4", linewidths=0.8)
            axis.scatter(*peak, marker="x", c="black", s=25, linewidths=1)
            if bounds is not None:
                axis.set(xlim=bounds[:2], ylim=bounds[2:])
            axis.set(title=title, xlabel="native mass i (1-based)", ylabel="native mass j (1-based)")
            figure.colorbar(image, ax=axis, shrink=0.75, label=unit)
        figure.suptitle(
            f"C1 COUPLED-HYDRO, native level {native_level}; {view}\n"
            "Mass-point saved states. Gray: original QC columns; x: initial wind peak.\n"
            "Descriptive comparison; force, continuity and observation skill remain unassessed by these maps.",
            fontsize=11,
        )
        for suffix in ("png", "svg"):
            figure.savefig(output / f"{basename}.{suffix}", dpi=160)
        plt.close(figure)
    result = {
        "schema": "pr98_same_level_native_maps_v1", "native_level_1based": native_level,
        "mass_grid_1based": {"i": [2, 233], "j": [2, 281]},
        "original_qc_points": 613, "projected_qc_columns": int(columns.sum()),
        "zoom_native_bounds": list(zoom), "zoom_selection": "Original fixed five-cell QC buffer, independent of response values",
        "initial_mass_point_wind_increment_peak": {"i": peak[0], "j": peak[1],
                                                   "magnitude_m_s": float(magnitude[peak_j, peak_i])},
        "histories": identities,
        "composition": {"path": str(COMPOSITION), "sha256": cloud.sha256(COMPOSITION)},
        "panels": summaries,
        "artifacts": {path.name: cloud.sha256(path) for path in output.iterdir()},
        "script_sha256": cloud.sha256(Path(__file__)),
        "physical_approval": "FAIL_OPEN", "skill": "NOT_EVALUATED",
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-level", type=int, default=16)
    args = parser.parse_args()
    print(json.dumps(render(args.output, args.native_level), indent=2))


if __name__ == "__main__":
    main()
