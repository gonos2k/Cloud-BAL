#!/usr/bin/env python3
"""Plot the retained fixed-domain application; never create an initialization mask."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def plot_coverage(bundle, out):
    coverage = json.loads((bundle / "coverage/coverage.json").read_text())
    bins = json.loads((bundle / "science/supplemental_recount/significance.json").read_text())["mass_bins"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    x = np.arange(len(bins))
    passed = np.array([item["accepted"] for item in bins])
    failed = np.array([item["rejected"] for item in bins])
    axes[0].bar(x, passed / 1000, label="Accepted", color="#318878")
    axes[0].bar(x, failed / 1000, bottom=passed / 1000, label="Rejected", color="#c4634c")
    axes[0].set_xticks(x, ["(0, 1e-12)", "[1e-12, 1e-9)", "[1e-9, 1e-6)", "[1e-6, inf)"])
    axes[0].tick_params(axis="x", labelsize=8)
    axes[0].set(xlabel="Stored analysis QICE + QSNOW (kg/kg)", ylabel="Selected cells (thousands)", title="Frozen selection, descriptive mass bins")
    axes[0].legend()
    names = ["background_total_zero", "background_ice_zero_number_positive", "rounded_ni_times_density_above_policy_cap", "background_mean_outside_policy", "background_negative_any", "background_ice_positive_number_zero"]
    labels = ["No background ice or snow", "Background QI=0, NI>0", "Computed target volume number > cap", "Background mean outside bounds", "Negative background field", "Background QI>0, NI=0"]
    counts = [coverage["categories"][name]["failed"] for name in names]
    bars = axes[1].barh(labels[::-1], np.array(counts[::-1]) / 1000, color="#a34f44")
    axes[1].bar_label(bars, labels=[f"{n:,}" for n in counts[::-1]], padding=3, fontsize=9)
    axes[1].set(xlabel="Rejected cells with observation (thousands)", title="Overlapping observations: do not add")
    axes[1].set_xlim(0, 96)
    fig.suptitle("06 UTC prior valid at 12 UTC: 129,878 / 294,792 cells rejected (44.06%)")
    fig.savefig(out / "coverage.png", dpi=180)
    plt.close(fig)


def plot_context(bundle, out):
    with np.load(bundle / "coverage/diagnostic_only.npz", allow_pickle=False) as data:
        selected = data["selected_fixed_mask"].astype(bool)
        rejected = selected & (data["status"] != 20)
        selected_count = selected.sum(axis=0)
        fraction = np.divide(rejected.sum(axis=0), selected_count, out=np.full(selected_count.shape, np.nan), where=selected_count > 0)
        delta_t = data["background_temperature_selected"] - data["analysis_temperature_selected"]
        failed_selected = data["status"][selected] != 20
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    ny, nx = fraction.shape
    im = axes[0].imshow(fraction, origin="lower", extent=(.5, nx + .5, .5, ny + .5), vmin=0, vmax=1, cmap="magma", interpolation="nearest")
    axes[0].plot(150, 228, "c+", markersize=10, label="First transaction failure")
    axes[0].legend(fontsize=8, loc="lower left")
    axes[0].set(xlabel="Fortran i (1-based)", ylabel="Fortran j (1-based)", title="Rejected / selected layers per column")
    fig.colorbar(im, ax=axes[0], label="Cell fraction; blank = no selected layers")
    edges = np.linspace(-4, 4, 65)
    axes[1].hist(delta_t[~failed_selected], bins=edges, density=True, histtype="step", linewidth=2, label="Accepted cells", color="#318878")
    axes[1].hist(delta_t[failed_selected], bins=edges, density=True, histtype="step", linewidth=2, label="Rejected cells", color="#c4634c")
    axes[1].set(xlabel="Background minus analysis file-derived temperature (K)", ylabel="Density", title="Paired context, not a causal temperature threshold")
    axes[1].legend()
    fig.suptitle("Frozen application domain; cells are spatially dependent")
    fig.savefig(out / "context.png", dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    inputs = [args.bundle / name for name in ("coverage/coverage.json", "coverage/diagnostic_only.npz", "science/supplemental_recount/significance.json")]
    before = {str(path.relative_to(args.bundle)): digest(path) for path in inputs}
    plot_coverage(args.bundle, args.out)
    plot_context(args.bundle, args.out)
    assert before == {str(path.relative_to(args.bundle)): digest(path) for path in inputs}
    receipt = {"input_sha256": before, "script_sha256": digest(Path(__file__)), "outputs": {name: digest(args.out / name) for name in ("coverage.png", "context.png")}, "scope": "Diagnostic only. No policy, rule or selection change."}
    (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
