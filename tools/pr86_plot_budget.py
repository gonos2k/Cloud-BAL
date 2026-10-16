#!/usr/bin/env python3
"""Plot retained first-call column budgets without changing the model."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, SymLogNorm
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off", type=Path, required=True)
    parser.add_argument("--coupled", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", choices=("water", "process"), default="water")
    args = parser.parse_args()
    fields = ("water_delta_kg", "bottom_outflow_kg", "cutoff_delta_kg")
    titles = ("Atmospheric water change", "Bottom precipitation outflow", "Numerical cutoff change")
    if args.kind == "process":
        fields = ("NG_deferred_mass_kg", "AUT_deferred_mass_kg", "G_deferred_mass_kg",
                  "rain_freeze_deferred_mass_kg")
        titles = ("Cold NG withheld", "Cold AUT withheld", "Cold G withheld", "Rain freezing withheld")
    with np.load(args.off) as off, np.load(args.coupled) as coupled:
        fig, axes = plt.subplots(2, len(fields), figsize=(4 * len(fields), 8), constrained_layout=True)
        for col, (key, title) in enumerate(zip(fields, titles)):
            limit = max(float(np.max(np.abs(off[key]))), float(np.max(np.abs(coupled[key]))), 1.)
            norm = (SymLogNorm(linthresh=1., vmin=-limit, vmax=limit) if args.kind == "water"
                    else LogNorm(vmin=max(limit * 1.e-8, 1.e-6), vmax=limit))
            for row, (label, data) in enumerate((("OFF", off), ("COUPLED", coupled))):
                values = data[key]
                if args.kind == "process":
                    values = np.ma.masked_less_equal(values, 0.)
                artist = axes[row, col].imshow(values, origin="lower", aspect="equal",
                                               extent=(1.5, values.shape[1] + 1.5,
                                                       1.5, values.shape[0] + 1.5),
                                               norm=norm, cmap="RdBu_r" if args.kind == "water" else "Reds")
                axes[row, col].set(title=f"{label}: {title}", xlabel="Native mass-grid i", ylabel="Native mass-grid j")
                scale = "symmetric log" if args.kind == "water" else "log; zero blank"
                fig.colorbar(artist, ax=axes[row, col], label=f"kg per column ({scale})", shrink=0.8)
        subtitle = ("Local dry-density × layer thickness × map-area measure; global closure OPEN"
                    if args.kind == "water" else
                    "Cold groups: half-L1 Q/QV vector activity; rain freezing: transferred mass; not gross reaction rates")
        fig.suptitle("PR85 v17 first KDM6 call, 13 UTC +20 s\n" + subtitle)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output, dpi=160)
        plt.close(fig)


if __name__ == "__main__":
    main()
