#!/usr/bin/env python3
"""Summarize native calc_ww_cp outputs on fixed PR98 QC support and buffer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr94_cloud_response as cloud  # noqa: E402


def read_ww(path: Path) -> np.ndarray:
    data = np.fromfile(path, dtype="<f4")
    expected = 235 * 40 * 283
    if data.size != expected:
        raise ValueError(f"unexpected native ww size in {path}: {data.size} != {expected}")
    full = data.reshape((235, 40, 283), order="F")
    # The driver computes native mass i=2..233, j=2..281 and all 40 vertical faces.
    active = full[1:233, :, 1:281].transpose(1, 2, 0).astype(np.float64)
    if not np.isfinite(active).all():
        raise ValueError(f"non-finite native ww in {path}")
    return active


def vertical_face_mask(mass_mask: np.ndarray) -> np.ndarray:
    faces = np.zeros((40, 280, 232), dtype=bool)
    faces[:39] |= mass_mask
    faces[1:] |= mass_mask
    return faces


def stats(values: np.ndarray) -> dict[str, float | int]:
    vector = np.asarray(values, dtype=np.float64).ravel()
    if vector.size == 0 or not np.isfinite(vector).all():
        raise ValueError("selected ww metric support is empty or non-finite")
    return {"n": int(vector.size), "rms_pa_s": float(np.sqrt(np.mean(vector * vector))),
            "max_abs_pa_s": float(np.max(np.abs(vector))), "mean_pa_s": float(np.mean(vector)),
            "signed_sum_pa_s": float(np.sum(vector, dtype=np.float64))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off", type=Path, required=True)
    parser.add_argument("--hydro", type=Path, required=True)
    parser.add_argument("--coupled", type=Path, required=True)
    parser.add_argument("--composition", type=Path,
                        default=ROOT / "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    support = cloud.make_masks(json.loads(args.composition.read_text())["composed_qc_vertical_influence"],
                               (39, 280, 232))
    arms = {"OFF": read_ww(args.off), "HYDRO": read_ww(args.hydro),
            "COUPLED": read_ww(args.coupled)}
    if len({array.shape for array in arms.values()}) != 1:
        raise ValueError("native ww active shapes differ between arms")
    masks = {
        "original_613_native_vertical_faces": vertical_face_mask(support["original_613_native_support"]),
        "fixed_5_cell_chebyshev_buffer_vertical_faces": vertical_face_mask(
            support["fixed_5_cell_chebyshev_buffer"]),
    }
    report = {"schema": "pr99_native_ww_fixed_support_metrics_v1",
              "units": "mass-coordinate ww in Pa/s",
              "support_identity": {"composition_path": str(args.composition),
                                   "composition_sha256": __import__("hashlib").sha256(
                                       args.composition.read_bytes()).hexdigest(),
                                   "mass_support_cells": int(support["original_613_native_support"].sum()),
                                   "mass_support_columns": int(support["original_613_native_support"].any(axis=0).sum()),
                                   "fixed5_mass_column_cells": int(support["fixed_5_cell_chebyshev_buffer"].any(axis=0).sum()),
                                   "vertical_face_mapping": "union of the two adjacent native ww faces for each supported mass level; the top face is included where adjacent"},
              "metrics": {}}
    for scope, mask in masks.items():
        selected = {arm: values[mask] for arm, values in arms.items()}
        report["metrics"][scope] = {
            "face_values": int(mask.sum()),
            "absolute_by_arm": {arm: stats(values) for arm, values in selected.items()},
            "paired_increments": {
                "HYDRO_minus_OFF": stats(selected["HYDRO"] - selected["OFF"]),
                "COUPLED_minus_HYDRO": stats(selected["COUPLED"] - selected["HYDRO"]),
                "COUPLED_minus_OFF": stats(selected["COUPLED"] - selected["OFF"]),
            },
        }
    report["inputs"] = {"OFF": str(args.off), "HYDRO": str(args.hydro), "COUPLED": str(args.coupled)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
