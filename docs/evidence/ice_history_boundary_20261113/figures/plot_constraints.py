#!/usr/bin/env python3
"""Draw descriptive cap diagnostics; no initialization or policy changes."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def quantile_panel(axis, values, label, color, logarithmic=False):
    low, q1, median, q3, high = np.quantile(values, [.05, .25, .5, .75, .95])
    axis.plot([0, 0], [low, high], color=color, linewidth=2)
    axis.plot([0, 0], [q1, q3], color=color, linewidth=18, solid_capstyle="butt")
    axis.plot(0, median, "o", color="white", markeredgecolor="black", markersize=7)
    if logarithmic:
        axis.set_yscale("log")
    axis.set_xticks([0], [label])
    axis.set_xlim(-.6, .6)
    axis.set_title(f"Median {median:.5g}")
    axis.grid(axis="y", alpha=.2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    data_path = args.bundle / "science/cap_diagnostics.npz"
    result_path = args.bundle / "science/recount.json"
    before = {name: sha256(path) for name, path in [("cap_diagnostics.npz", data_path), ("recount.json", result_path)]}
    with np.load(data_path, allow_pickle=False) as data:
        alpha = data["alpha"]
        density_ratio = data["analysis_over_background_density"]
        empty = data["continuous_empty"]
        bad_mean = data["bad_background_mean"]
    result = json.loads(result_path.read_text())
    fig, axes = plt.subplots(1, 3, figsize=(12, 5), layout="constrained")
    quantile_panel(axes[0], alpha, "Analysis / background\nsolid-water total", "#a34f44", True)
    quantile_panel(axes[1], density_ratio, "Analysis / background\nfile density", "#318878")
    axes[0].set_ylabel("Ratio; logarithmic scale")
    axes[1].set_ylabel("Ratio; linear scale")
    labels = ["Continuous interval exists", "Continuous interval empty", "Background mean invalid"]
    counts = [int((~empty & ~bad_mean).sum()), int(empty.sum()), int(bad_mean.sum())]
    bars = axes[2].barh(labels[::-1], counts[::-1], color=["#777777", "#c4634c", "#467aa7"])
    axes[2].bar_label(bars, labels=[f"{n:,}" for n in counts[::-1]], padding=3)
    axes[2].set_xlim(0, 25000)
    axes[2].set_xlabel("Cap-flagged cells")
    axes[2].set_title("Continuous REAL64 feasibility")
    fig.suptitle("20,373 cap observations: mass scaling and density are separate diagnostics")
    fig.supxlabel("Ratio panels: thick line = IQR, thin line = 5–95%; tails omitted. Not causal attribution.")
    output = args.out / "cap_constraints.png"
    fig.savefig(output, dpi=180)
    plt.close(fig)
    assert before == {name: sha256(path) for name, path in [("cap_diagnostics.npz", data_path), ("recount.json", result_path)]}
    receipt = {"input_sha256": before, "script_sha256": sha256(Path(__file__)), "figure_sha256": sha256(output), "density_substitution_still_above": result["cap_flag"]["substitute_background_density_still_above"], "scope": "Descriptive fixed-mask calculation. Feasibility is continuous REAL64, not a native/discrete acceptance replay. No rule change."}
    (args.out / "constraints_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
