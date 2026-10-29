#!/usr/bin/env python3
"""Plot validated weighted CP02 thermodynamic and rain response profiles."""

import argparse
import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[4]
INITIAL = ROOT / "docs/evidence/cp02_kdm6_controls_20261029/inputs/selected_initial_fields.csv"
INITIAL_THERMO = ROOT / "docs/evidence/cp02_thermo_response_20261029/binary/initial_thermo.csv"
INITIAL_THERMO_RECEIPT = ROOT / "docs/evidence/cp02_thermo_response_20261029/binary/initial_thermo_receipt.json"
SELECTION = ROOT / "docs/evidence/cp02_kdm6_controls_20261029/selection.json"
DEFAULT_DIR = ROOT / "docs/evidence/cp02_thermo_response_20261029/analysis/thermo_response"
ARMS = ("OFF", "HYDRO", "LIQUID")
ARM_COLORS = {"OFF": "#4c78a8", "HYDRO": "#f58518", "LIQUID": "#54a24b"}
ENDPOINTS = ("call1_entry", "call1_return", "call2_entry", "call2_return")
LINE_STYLES = {"call1_entry": "-", "call1_return": "--",
               "call2_entry": ":", "call2_return": "-."}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_validated_profiles(directory):
    directory = Path(directory)
    summary_path, profiles_path = directory / "summary.json", directory / "profiles.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    inputs = summary["inputs"]
    if sha256(INITIAL) != inputs["initial_csv_sha256"]:
        raise ValueError("initial CSV hash differs from analyzed provenance")
    if sha256(INITIAL_THERMO) != inputs["binary_initial_csv_sha256"]:
        raise ValueError("binary initial thermodynamic CSV hash differs from analyzed provenance")
    if sha256(INITIAL_THERMO_RECEIPT) != inputs["binary_initial_receipt_sha256"]:
        raise ValueError("binary initial thermodynamic receipt hash differs from analyzed provenance")
    if sha256(SELECTION) != inputs["selection_sha256"]:
        raise ValueError("selection hash differs from analyzed provenance")
    if sha256(profiles_path) != summary["profiles"]["sha256"]:
        raise ValueError("profiles CSV hash differs from analysis summary")
    with profiles_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return summary, rows, profiles_path


def plot_groups(rows, output_dir):
    grouped = {}
    for row in rows:
        grouped.setdefault((row["arm"], row["point"], row["state"], row["field"]), []).append(
            (int(row["level_k1"]), float(row["weighted_value"])))
    created = []
    for filename, fields, title in (
        ("thermodynamic_state_profiles.png", ("q", "qc", "th", "pii", "p", "den",
                                               "T", "THM", "P", "PB"),
         "Captured argument and initial input profiles"),
        ("qr_response_profiles.png", ("qr",),
         "Captured rain argument profiles"),
    ):
        rows_count = len(fields) if len(fields) > 1 else 1
        cols_count = 2 if len(fields) > 1 else 2
        fig, axes = plt.subplots(rows_count, cols_count, figsize=(13, 3.1 * rows_count),
                                 squeeze=False, constrained_layout=True)
        for field_index, field in enumerate(fields):
            for point_index, point in enumerate(("P01", "P05")):
                ax = axes[field_index][point_index]
                for arm in ARMS:
                    state_list = ENDPOINTS
                    if field in ("q", "qc", "qr"):
                        state_list = ("initial", *ENDPOINTS)
                    elif field in ("T", "THM", "P", "PB"):
                        state_list = ("initial_wrfinput",)
                    for state in state_list:
                        key = (arm, point, state, field)
                        if key not in grouped:
                            continue
                        values = sorted(grouped[key])
                        ax.plot([item[0] for item in values], [item[1] for item in values],
                                color=ARM_COLORS[arm], linestyle=("--" if state in ("initial", "initial_wrfinput")
                                                                  else LINE_STYLES[state]),
                                linewidth=1.45, label=f"{arm} {state}")
                ax.set_title(f"{field} · {point}")
                ax.set_xlabel("model level k (1-based)")
                ax.set_ylabel("recorded numeric value (unit unassigned)")
                ax.grid(alpha=0.25)
                if field_index == 0 and point_index == 0:
                    ax.legend(fontsize=7, ncol=2, loc="best")
        if len(fields) == 1:
            axes[0][0].set_ylabel("recorded numeric value (unit unassigned)")
            axes[0][1].set_ylabel("recorded numeric value (unit unassigned)")
            axes[0][0].legend(fontsize=7, ncol=2, loc="best")
        fig.suptitle(title)
        destination = Path(output_dir) / filename
        fd, temp_name = tempfile.mkstemp(prefix=f".{filename}.", suffix=".png", dir=output_dir)
        os.close(fd)
        try:
            fig.savefig(temp_name, dpi=170)
            os.replace(temp_name, destination)
        finally:
            plt.close(fig)
            Path(temp_name).unlink(missing_ok=True)
        created.append(destination)
    return created


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    summary, rows, profiles_path = load_validated_profiles(args.analysis_dir)
    plots = plot_groups(rows, args.analysis_dir)
    metadata = {
        "schema": "cp02-thermo-response-plots-v1",
        "inputs": {"summary_sha256": sha256(args.analysis_dir / "summary.json"),
                   "profiles_sha256": sha256(profiles_path),
                   "initial_csv_sha256": summary["inputs"]["initial_csv_sha256"],
                   "binary_initial_csv_sha256": summary["inputs"]["binary_initial_csv_sha256"],
                   "binary_initial_receipt_sha256": summary["inputs"]["binary_initial_receipt_sha256"],
                   "selection_sha256": summary["inputs"]["selection_sha256"]},
        "plots": [{"path": plot.name, "sha256": sha256(plot)} for plot in plots],
        "scope": "Weighted selected-point numeric profiles; argument units remain unassigned.",
    }
    (Path(args.analysis_dir) / "plots.metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PLOTS_WRITTEN", "plots": [str(path) for path in plots]}))


if __name__ == "__main__":
    main()
