#!/usr/bin/env python3
"""Plot weighted four-corner KDM6 entry/return profiles from archived GDB captures."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


ROLES = ("P01", "P05", "P09", "P13")
FIELDS = (
    ("qr", "Rain candidate", "tab:blue"),
    ("qs", "Snow candidate", "tab:orange"),
    ("qc", "Cloud candidate", "tab:green"),
    ("qi", "Ice candidate", "tab:red"),
)
PHASES = ("entry", "return")
LEVELS = tuple(range(1, 40))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def load_captures(capture_dir: Path) -> dict:
    captures = {}
    paths = sorted(capture_dir.glob("capture_rank*_pid*.json.gz"))
    if len(paths) != 8:
        raise ValueError(f"expected 8 archived rank captures, found {len(paths)}")
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            record = json.load(stream)
        if record.get("status") != "return_captured":
            raise ValueError(f"capture is incomplete: {path}")
        rank = int(record["entry"]["rank"])
        if rank in captures:
            raise ValueError(f"duplicate capture for rank {rank}")
        if record["entry"]["scalar_raw4"]["itimestep"]["decoded"] != 1:
            raise ValueError(f"unexpected itimestep in rank {rank}")
        if not math.isclose(record["entry"]["scalar_raw4"]["delt"]["decoded"], 20.0, abs_tol=1e-5):
            raise ValueError(f"unexpected delt in rank {rank}")
        captures[rank] = record
    if set(captures) != set(range(8)):
        raise ValueError(f"expected ranks 0..7, found {sorted(captures)}")
    return captures


def load_selection(selection_path: Path) -> dict[tuple[str, int], dict]:
    points = read_json(selection_path)["points"]
    selection = {}
    for point in points:
        label = point["label"]
        key = (label, int(point["k"]))
        if key in selection:
            raise ValueError(f"duplicate selected point {key}")
        selection[key] = point
    if len(selection) != 4 * 4 * len(LEVELS):
        raise ValueError(f"expected 624 unique selected corner-level points, found {len(selection)}")
    for role in ROLES:
        labels = sorted({label for label, _ in selection if label.startswith(role + "_")})
        if len(labels) != 4:
            raise ValueError(f"{role} must have four selected corners; found {labels}")
        for k in LEVELS:
            points_k = [selection[(label, k)] for label in labels]
            if not math.isclose(sum(float(p["weight"]) for p in points_k), 1.0, abs_tol=1e-12):
                raise ValueError(f"{role} corner weights do not sum to one at k={k}")
    return selection


def collect_owned_samples(captures: dict) -> dict[tuple[str, str, int], dict]:
    owned = {}
    for rank, capture in captures.items():
        for phase in PHASES:
            for sample in capture[phase]["samples"]:
                if sample["status"] != "owned_tile":
                    continue
                key = (phase, sample["label"], int(sample["k"]))
                if key in owned:
                    raise ValueError(f"sample has multiple owning ranks: {key}")
                owned[key] = sample
    return owned


def weighted_profiles(selection: dict, owned: dict) -> dict:
    profiles = {}
    for role in ROLES:
        labels = sorted({label for label, _ in selection if label.startswith(role + "_")})
        for phase in PHASES:
            for field, _, _ in FIELDS:
                values = []
                for k in LEVELS:
                    total = 0.0
                    for label in labels:
                        sample = owned.get((phase, label, k))
                        if sample is None:
                            raise ValueError(f"missing owning sample: {phase}/{label}/k={k}")
                        point = selection[(label, k)]
                        if int(sample["i"]) != int(point["i"]) or int(sample["j"]) != int(point["j"]):
                            raise ValueError(f"capture coordinate mismatch for {phase}/{label}/k={k}")
                        value = float(sample["values"][field]["value_f32"])
                        if not math.isfinite(value):
                            raise ValueError(f"non-finite {field} sample at {phase}/{label}/k={k}")
                        total += float(point["weight"]) * value
                    values.append(1000.0 * total)  # kg/kg to g/kg
                profiles[(role, phase, field)] = values
    return profiles


def role_descriptions(manifest: dict) -> dict[str, str]:
    role_map = manifest.get("point_roles", {})
    return {role: str(role_map.get(role, "role unavailable")) for role in ROLES}


def make_plot(profiles: dict, descriptions: dict[str, str], output_path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharey=True, constrained_layout=False)
    for ax, role in zip(axes.flat, ROLES):
        for field, label, color in FIELDS:
            for phase in PHASES:
                ax.plot(
                    profiles[(role, phase, field)],
                    LEVELS,
                    color=color,
                    linestyle="-" if phase == "entry" else "--",
                    linewidth=1.8,
                )
        ax.set_title(f"{role}: {descriptions[role]}")
        ax.set_xlabel("Candidate mixing ratio (g kg$^{-1}$)")
        ax.set_ylim(1, 39)
        ax.set_yticks((1, 5, 10, 15, 20, 25, 30, 35, 39))
        ax.grid(True, alpha=0.28)
    axes[0, 0].set_ylabel("WRF native mass-level index k")
    axes[1, 0].set_ylabel("WRF native mass-level index k")
    species_legend = [Line2D([0], [0], color=color, lw=2, label=label) for _, label, color in FIELDS]
    phase_legend = [
        Line2D([0], [0], color="black", lw=2, linestyle="-", label="PRE: KDM6 entry"),
        Line2D([0], [0], color="black", lw=2, linestyle="--", label="POST: KDM6 return"),
    ]
    fig.legend(
        handles=species_legend + phase_legend,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.045),
        ncol=3,
        frameon=False,
    )
    fig.suptitle(
        "HYDRO first KDM6 call · step 1 · dt = 20 s\n"
        "Four-corner weighted profiles; ABI field labels are provisional",
        fontsize=13,
    )
    fig.text(
        0.5,
        0.008,
        "Captured state profiles only; no integrated mass or forecast claim. PRE/POST denote the call boundary.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.14, 1, 0.91))
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="CP02 evidence directory (defaults to this script's directory)",
    )
    args = parser.parse_args()
    evidence_dir = args.evidence_dir.resolve()
    capture_dir = evidence_dir / "capture"
    captures = load_captures(capture_dir)
    selection_path = capture_dir / "selection.json"
    selection = load_selection(selection_path)
    owned = collect_owned_samples(captures)
    profiles = weighted_profiles(selection, owned)
    manifest_path = evidence_dir / "inputs" / "manifest.json"
    manifest = read_json(manifest_path)
    descriptions = role_descriptions(manifest)
    png_path = evidence_dir / "first_call_weighted_profiles.png"
    make_plot(profiles, descriptions, png_path)

    input_paths = [selection_path, evidence_dir / "capture" / "receipt.json"]
    input_paths.extend(sorted(capture_dir.glob("capture_rank*_pid*.json.gz")))
    metadata = {
        "purpose": "weighted PRE/POST profiles at first HYDRO KDM6 call; not a forecast or integrated mass analysis",
        "step": 1,
        "delt_seconds": 20.0,
        "vertical_index": "native WRF mass-level k=1..39",
        "fields": {field: {"label": label, "abi_name_status": "provisional candidate", "plot_units": "g kg-1"} for field, label, _ in FIELDS},
        "aggregation": "recorded four-corner bilinear weights; exactly one owning rank required per corner, level, and phase",
        "inputs": {str(path.relative_to(evidence_dir)): sha256(path) for path in input_paths},
        "role_descriptions_source": "inputs/manifest.json point_roles mapping",
        "role_descriptions_sha256": hashlib.sha256(json.dumps(manifest.get("point_roles", {}), sort_keys=True).encode()).hexdigest(),
        "plot_script_sha256": sha256(Path(__file__).resolve()),
        "plot_png_sha256": sha256(png_path),
        "role_descriptions": descriptions,
    }
    (evidence_dir / "first_call_weighted_profiles.metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {png_path}")
    print(f"wrote {evidence_dir / 'first_call_weighted_profiles.metadata.json'}")


if __name__ == "__main__":
    main()
