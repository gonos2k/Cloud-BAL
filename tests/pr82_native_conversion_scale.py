#!/usr/bin/env python3
"""Summarize REAL32 number-basis conversion risk from one captured KDM6 tile."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from native_kdm6_trace import read_dump

MASS_PAIRS = {"NC": "QC", "NI": "QI", "NR": "QR", "NN": None}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_new_json(path: Path, value: dict) -> None:
    output = Path(os.path.abspath(path))
    for component in reversed((output, *output.parents)):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"output path contains a symlink: {component}")
        if component == output:
            raise FileExistsError(f"refusing to overwrite existing output: {output}")
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"output parent is not a directory: {component}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def summarize(path: Path) -> dict:
    before = sha256(path)
    dump = read_dump(path)
    fields = dump["fields"]
    density_total = np.asarray(fields["DEN"], dtype=np.float32)
    vapor = np.asarray(fields["Q"], dtype=np.float32)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore", under="ignore"):
        denominator = np.add(np.float32(1), vapor, dtype=np.float32)
        dry_density = np.divide(density_total, denominator, dtype=np.float32)
    minimum_subnormal = np.nextafter(np.float32(0), np.float32(1), dtype=np.float32)
    half_minimum = float(minimum_subnormal) / 2.0
    counts = {}
    for species, field in MASS_PAIRS.items():
        value = np.asarray(fields[species], dtype=np.float32)
        finite_value = np.isfinite(value)
        finite_density = np.isfinite(dry_density)
        valid_base = finite_value & finite_density & (value >= 0) & (dry_density > 0)
        exact_product = value.astype(np.float64) * dry_density.astype(np.float64)
        overflow_guard = valid_base & (dry_density > 1) & (
            value.astype(np.float64) > float(np.finfo(np.float32).max) / dry_density.astype(np.float64))
        result = np.zeros(value.shape, dtype=np.float32)
        with np.errstate(over="ignore", invalid="ignore", under="ignore"):
            result[valid_base & ~overflow_guard] = exact_product[valid_base & ~overflow_guard].astype(np.float32)
        classes = {
            "NONFINITE_INPUT": int((~finite_value).sum()),
            "NONFINITE_DENSITY": int((finite_value & ~finite_density).sum()),
            "NEGATIVE_INPUT": int((finite_value & finite_density & (value < 0)).sum()),
            "NONPOSITIVE_DENSITY": int((finite_value & finite_density & (value >= 0) & (dry_density <= 0)).sum()),
            "OVERFLOW_GUARD": int(overflow_guard.sum()),
            "NONFINITE_RESULT": int((valid_base & ~overflow_guard & ~np.isfinite(result)).sum()),
            "POSITIVE_TO_ZERO": int((valid_base & ~overflow_guard & (value > 0) & (result == 0)).sum()),
        }
        species_counts = {
            "public_number_positive": int((value > 0).sum()),
            "conversion_error_class_counts": classes,
            "independent_float64_product_at_or_below_half_minimum": int((valid_base & (value > 0) & (exact_product <= half_minimum)).sum()),
        }
        if field is None:
            species_counts["mass_pair"] = None
            species_counts["mass_pair_note"] = (
                "ambient CCN reservoir initialized from ccn0 and qnn factors; "
                "no condensate mass counterpart"
            )
        else:
            mass = np.asarray(fields[field], dtype=np.float32)
            species_counts["mass_pair"] = field
            species_counts["positive_mass_zero_number"] = int(((mass > 0) & (value == 0)).sum())
            species_counts["positive_number_zero_mass"] = int(((value > 0) & (mass == 0)).sum())
        counts[species] = species_counts
    after = sha256(path)
    if before != after:
        raise RuntimeError("KDM6 pre-call snapshot changed during offline aggregation")
    return {
        "schema": "pr82_native_conversion_scale_v2",
        "scope": "offline REAL32 representability estimate over the captured KDM6 active tile; no model rerun",
        "input_path": str(path), "input_sha256_before": before, "input_sha256_after": after,
        "stage": dump["stage"], "timestep": dump["itimestep"],
        "bounds": dump["bounds"], "active_cell_count": int(density_total.size),
        "density_formula": "REAL32 DEN / (REAL32(1) + REAL32 Q)",
        "product_threshold": {"smallest_positive_subnormal": float(minimum_subnormal),
                              "half_minimum_round_to_zero": half_minimum},
        "mass_pair_source_semantics": {
            "NN": "ambient CCN reservoir initialized from ccn0 and qnn_land_mult/qnn_sea_mult; QS is not its mass pair",
            "NC": "QC", "NI": "QI", "NR": "QR",
        },
        "species": counts,
    }


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: pr82_native_conversion_scale.py KDM6_PRE_TRACE OUTPUT_JSON")
    report = summarize(Path(sys.argv[1]))
    write_new_json(Path(sys.argv[2]), report)
    print(sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
