#!/usr/bin/env python3
"""Measure pressure-candidate dry-flux terms lost by WPS omega omission."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cp06a_state_force_flux import dry_fraction, get, independent_flux


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def field_stats(values: np.ndarray, mask: np.ndarray) -> dict[str, float | int]:
    selected = np.asarray(values, dtype=np.float64)[mask]
    return {
        "cells": int(selected.size),
        "rms_kg_s": float(np.sqrt(np.mean(selected * selected))),
        "max_abs_kg_s": float(np.max(np.abs(selected))),
        "l1_kg_s": float(np.sum(np.abs(selected), dtype=np.float64)),
        "signed_sum_kg_s": float(np.sum(selected, dtype=np.float64)),
    }


def measure(candidate_path: Path) -> dict[str, object]:
    with Dataset(candidate_path) as dataset:
        above = get(dataset, "above_ground") != 0
        fields = {
            f"{prefix}_{name}": get(dataset, f"{prefix}_{name}").astype(np.float64)
            for prefix, name in (
                ("background", "u"), ("background", "v"),
                ("background", "omega"), ("candidate", "u"),
                ("candidate", "v"), ("candidate", "omega"),
            )
        }
        dry = dry_fraction(dataset, "candidate", above)
        zeros = np.zeros_like(fields["candidate_omega"])
        horizontal = independent_flux(
            dataset, "candidate", dry_override=dry,
            wind_override=(fields["candidate_u"] - fields["background_u"],
                           fields["candidate_v"] - fields["background_v"]),
            omega_override=zeros,
            zero_omega_boundaries=True,
        )["divergence"]
        omega = independent_flux(
            dataset, "candidate", dry_override=dry,
            wind_override=(np.zeros_like(fields["candidate_u"]),
                           np.zeros_like(fields["candidate_v"])),
            omega_override=fields["candidate_omega"] - fields["background_omega"],
            zero_omega_boundaries=True,
        )["divergence"]
        total = horizontal + omega
        recomputed = independent_flux(
            dataset, "candidate", dry_override=dry,
            wind_override=(fields["candidate_u"] - fields["background_u"],
                           fields["candidate_v"] - fields["background_v"]),
            omega_override=fields["candidate_omega"] - fields["background_omega"],
            zero_omega_boundaries=True,
        )["divergence"]
        mask = above & np.isfinite(total) & np.isfinite(recomputed)
        if not np.any(mask):
            raise ValueError("candidate has no finite above-ground cells")
        split_error = float(np.max(np.abs(total[mask] - recomputed[mask])))
        if split_error > 1.0e-8:
            raise ValueError(f"horizontal/omega split does not reconstruct total: {split_error}")
        horizontal_stats = field_stats(horizontal, mask)
        omega_stats = field_stats(omega, mask)
        total_stats = field_stats(total, mask)
        component_l1 = horizontal_stats["l1_kg_s"] + omega_stats["l1_kg_s"]
        return {
            "schema": "pr99_pressure_transfer_diagnostic_v1",
            "input": {"path": str(candidate_path.resolve()), "sha256": sha256(candidate_path)},
            "scope": "candidate-minus-background wind correction at fixed candidate dry carrier and pressure geometry",
            "export_contract": "WPS UU/VV carry horizontal correction; pressure omega has no WPS field",
            "changed_values": {
                "u": int(np.count_nonzero(fields["candidate_u"] != fields["background_u"])),
                "v": int(np.count_nonzero(fields["candidate_v"] != fields["background_v"])),
                "omega": int(np.count_nonzero(fields["candidate_omega"] != fields["background_omega"])),
            },
            "horizontal_uv": horizontal_stats,
            "omega": omega_stats,
            "combined": total_stats,
            "component_cancellation": {
                "l1_removed_by_opposing_terms_kg_s": float(component_l1 - total_stats["l1_kg_s"]),
                "fraction_of_component_l1": float((component_l1 - total_stats["l1_kg_s"]) / component_l1)
                if component_l1 else 0.0,
            },
            "fixed_omega_wps_projection": {
                "exported_correction": horizontal_stats,
                "omitted_omega_correction": omega_stats,
                "max_split_reconstruction_error_kg_s": split_error,
                "closed_mass_wind_balance_assessed": False,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = measure(args.candidate)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
