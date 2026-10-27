#!/usr/bin/env python3
"""Plot separate shadow and native level means; neither row is a water budget."""
import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def level_means(rows, level, value):
    indices = sorted({int(row[level]) for row in rows})
    return np.array(
        [
            np.mean([value(row) for row in rows if int(row[level]) == index])
            for index in indices
        ]
    )


def plot(source, output):
    if output.exists():
        raise FileExistsError(output)
    with (source / "shadow/shadow_species_profiles.csv").open() as stream:
        shadow = list(csv.DictReader(stream))
    with (source / "wrf/initial_species_profiles.csv").open() as stream:
        native = list(csv.DictReader(stream))
    fig, axes = plt.subplots(2, 2, figsize=(11, 9), constrained_layout=True)
    for column, (species, field) in enumerate((("rain", "QRAIN"), ("snow", "QSNOW"))):
        ax = axes[0, column]
        for arm, prefix, label, style in (
            ("HYDRO", "background", "Analysis background", "--"),
            ("HYDRO", "candidate", "HYDRO candidate", "-"),
            ("LIQUID_RADAR_RH1", "candidate", "LIQUID candidate", ":"),
        ):
            rows = [row for row in shadow if row["arm"] == arm]
            pressure = level_means(
                rows, "z_index", lambda r: float(r["pressure_pa"]) / 100
            )
            mixing = level_means(
                rows, "z_index", lambda r: float(r[f"{prefix}_{species}"]) * 1000
            )
            ax.plot(mixing, pressure, style, label=label)
        ax.set_title(f"Shadow analysis: {field} (22 pressure levels)")
        ax = axes[1, column]
        for arm, style in (("OFF", "--"), ("HYDRO", "-"), ("LIQUID", ":")):
            rows = [
                row
                for row in native
                if row["arm"] == arm and row["stage"] == "wrfinput"
            ]
            pressure = level_means(
                rows, "bottom_top_k", lambda r: (float(r["P"]) + float(r["PB"])) / 100
            )
            mixing = level_means(rows, "bottom_top_k", lambda r: float(r[field]) * 1000)
            ax.plot(mixing, pressure, style, label=arm)
        ax.set_title(f"Archived wrfinput: {field} (39 mass levels)")
    for ax in axes.flat:
        ax.invert_yaxis()
        ax.set_xlabel("Mixing ratio (g/kg dry air)")
        ax.set_ylabel("Pressure (hPa)")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle(
        "20 post-selected lost-hit points: unweighted level means\n"
        "Rows use different vertical grids; not a mass budget or causal decomposition"
    )
    fig.savefig(output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(args.input_dir, args.output)
