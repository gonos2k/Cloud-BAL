#!/usr/bin/env python3
"""Plot the hash-bound B1 OLD/FIX score and actual-state diagnostics."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def bound_rows(folder: Path, receipt: dict, name: str) -> list[dict[str, str]]:
    path = folder / name
    bound = receipt["outputs"][name]
    if path.stat().st_size != bound["size_bytes"] or digest(path) != bound["sha256"]:
        raise ValueError(f"cohort artifact differs from receipt: {name}")
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def score_figure(rows: list[dict[str, str]], out: Path) -> None:
    keyed = {(int(r["lead_hour"]), float(r["threshold_mm"])): r for r in rows}
    if len(rows) != 12 or set(keyed) != {(h, t) for h in (1, 2) for t in THRESHOLDS}:
        raise ValueError("expected 2 leads by 6 thresholds")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for ax, h in zip(axes, (1, 2)):
        selected = [keyed[h, t] for t in THRESHOLDS]
        for arm, color in (("OLD", "#2166ac"), ("FIX", "#b2182b")):
            values = [float(r[f"{arm}_CSI"]) for r in selected]
            ax.plot(range(6), values, "o-", label=arm, color=color)
        for x, row in enumerate(selected):
            delta = float(row["FIX_CSI"]) - float(row["OLD_CSI"])
            ax.annotate(f"{delta:+.4f}", (x, max(float(row['OLD_CSI']), float(row['FIX_CSI']))),
                        xytext=(0, 7), textcoords="offset points", ha="center", fontsize=8)
        ax.set(title=f"+{h} h: one-hour precipitation", xticks=range(6),
               xticklabels=[f"{t:g}" for t in THRESHOLDS], xlabel="Threshold (mm)", ylabel="CSI")
        ax.grid(alpha=.25)
        ax.legend(frameon=False)
    fig.suptitle("Same B1 initial state: OLD / FIX (3,688 samples; labels = FIX minus OLD)")
    fig.savefig(out / "paired_csi.png", dpi=180)
    plt.close(fig)


def amplitude_figure(rows: list[dict[str, str]], out: Path) -> None:
    rows = [r for r in rows if r["point_id"] == "P01"]
    if len(rows) != 190 or any(float(r["q_change"]) or float(r["t_change_k"]) for r in rows):
        raise ValueError("P01 actual-state scope differs from the preserved 190 events")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), constrained_layout=True)
    for h, color in ((1, "#2166ac"), (2, "#b2182b")):
        subset = [r for r in rows if int(r["hour"]) == h]
        axes[0].scatter([int(r["itimestep"]) * 20 / 60 for r in subset],
                        [float(r["increment_abs_over_q_ulp"]) for r in subset],
                        s=16, alpha=.6, label=f"hour {h}: {len(subset)} events", color=color)
    axes[0].set(xlabel="Timestep × 20 s (min)", ylabel="|PREVP term × dt| / ULP(q PRE)",
                title="P01: term amplitude relative to stored REAL32 q")
    axes[0].set_yscale("log")
    axes[0].axhline(.5, color="black", ls="--", lw=1, label="0.5 ULP reference")
    axes[0].legend(fontsize=8, frameon=False)
    axes[1].bar(["events", "q changed", "T changed"], [190, 0, 0], color=["#777777", "#2166ac", "#b2182b"])
    axes[1].set(ylabel="Count", title="Actual PRE_UPDATE to local POST_PROCESS values")
    axes[1].text(.65, .60, "No stored q or T change\nin these 190 events.\n\nTerm size alone does not\nprove rounding or causality.",
                 transform=axes[1].transAxes, ha="center", fontsize=9)
    fig.savefig(out / "p01_event_amplitude.png", dpi=180)
    plt.close(fig)


def false_alarm_figure(rows: list[dict[str, str]], scores: list[dict[str, str]], out: Path) -> None:
    points = {r["point_id"]: r for r in rows}
    if set(points) != {"P01", "P02", "P03", "P04", "FA01", "FA02", "FA03", "FA04"}:
        raise ValueError("expected original four cohorts and four false-alarm transitions")
    ids = [f"FA{i:02d}" for i in range(1, 5)]
    score = next(r for r in scores if int(r["lead_hour"]) == 2 and float(r["threshold_mm"]) == 5)
    if (int(score["OLD_hit"]) != int(score["FIX_hit"])
            or int(score["OLD_miss"]) != int(score["FIX_miss"])
            or int(score["FIX_false_alarm"]) - int(score["OLD_false_alarm"]) != -2):
        raise ValueError("5 mm contingency no longer supports unchanged H and F minus 2")
    for pid in ids:
        row = points[pid]
        observed, old, fixed = (float(row[k]) for k in ("reference_plus2_mm", "OLD_plus2_mm", "FIX_plus2_mm"))
        if not observed < 5 or (pid != "FA04" and not old >= 5 > fixed) or (pid == "FA04" and not fixed >= 5 > old):
            raise ValueError(f"false-alarm transition differs from the declared role: {pid}")
    x = np.arange(4)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), constrained_layout=True)
    for shift, key, label, color in ((-.25, "reference_plus2_mm", "RN1 reference", "#555555"),
                                   (0, "OLD_plus2_mm", "OLD", "#2166ac"),
                                   (.25, "FIX_plus2_mm", "FIX", "#b2182b")):
        axes[0].bar(x + shift, [float(points[p][key]) for p in ids], width=.23, label=label, color=color)
    axes[0].axhline(5, color="black", ls="--", lw=1)
    axes[0].set(xticks=x, xticklabels=ids, ylabel="One-hour precipitation (mm)", title="+2 h: actual 5 mm false-alarm transitions")
    axes[0].legend(frameon=False, fontsize=8)
    for arm, color, shift in (("OLD", "#2166ac", -.19), ("FIX", "#b2182b", .19)):
        h, m, f = (int(score[f"{arm}_{key}"]) for key in ("hit", "miss", "false_alarm"))
        bars = axes[1].bar(np.arange(3) + shift, [h, m, f], width=.36,
                           label=f"{arm}: CSI = {h/(h+m+f):.6f}", color=color)
        axes[1].bar_label(bars, padding=3, fontsize=9)
    axes[1].set(xticks=[0, 1, 2], xticklabels=["Hit", "Miss", "False alarm"], ylabel="Sample count",
                title="Full 3,688-point contingency: H unchanged, F −2")
    axes[1].legend(frameon=False, fontsize=8)
    fig.savefig(out / "false_alarm_transitions.png", dpi=180)
    plt.close(fig)


def render(folder: Path, output: Path) -> dict:
    if os.path.lexists(output):
        raise FileExistsError(output)
    receipt_path = folder / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    scores = bound_rows(folder, receipt, "paired_scores.csv")
    events = bound_rows(folder, receipt, "zero_rate_state_paths.csv")
    points = bound_rows(folder, receipt, "selected_points.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".state-path-figures-", dir=output.parent))
    try:
        score_figure(scores, temp)
        amplitude_figure(events, temp)
        false_alarm_figure(points, scores, temp)
        metadata = {"scope": "Existing paired B1 evidence, no new forecast skill claim", "inputs": {
            name: receipt["outputs"][name] for name in ("paired_scores.csv", "zero_rate_state_paths.csv", "selected_points.csv")},
            "cohort_receipt_sha256": digest(receipt_path), "renderer_sha256": digest(Path(__file__)),
            "outputs": {p.name: {"sha256": digest(p), "size_bytes": p.stat().st_size} for p in sorted(temp.glob("*.png"))}}
        (temp / "render_receipt.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        temp.rename(output)
        return metadata
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohorts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.cohorts, args.output)


if __name__ == "__main__":
    main()
