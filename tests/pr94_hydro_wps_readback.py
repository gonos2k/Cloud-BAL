#!/usr/bin/env python3
"""Verify PR94 HYDRO WPS records against the existing mapper witness."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from pr83_same13_off_wps_readback import read_inventory, field

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_baseline import read_wps


SOURCE_CANDIDATE_GENERATIONS = {
    "5e69e8b1c2f36119cead2ca4b6ca632a8898a2fa1082d9faa9dd1ea5075b7535":
        "PR78 CP06A spatial O2 HYDRO pressure-analysis product",
    "97a98c5bb05a8dc70528c2b6c025ae8cb359ed46f23b7d3c28941535f71ae9d6":
        "PR81 same13 current-generation thermo/density/Phi HYDRO producer, pinned O2",
}


def generation_for_candidate_sha(candidate_sha: str) -> str:
    try:
        return SOURCE_CANDIDATE_GENERATIONS[candidate_sha]
    except KeyError as error:
        raise ValueError("HYDRO candidate hash has no pinned generation identity") from error


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_wps(wps_path: Path, baseline_path: Path, inventory_path: Path,
              witness_path: Path, candidate_path: Path, output_path: Path) -> dict:
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError(f"refusing to overwrite receipt: {output_path}")
    wps = read_wps(wps_path)
    baseline = read_wps(baseline_path)
    mapped = read_inventory(witness_path)
    candidate_sha = sha256(candidate_path)
    generation = generation_for_candidate_sha(candidate_sha)
    if len(wps) != 235 or not baseline.keys() <= wps.keys():
        raise ValueError("HYDRO WPS inventory omits retained 13Z source records")
    units = {"TT": "K", "HGT": "m", "UU": "m s{-1}", "VV": "m s{-1}",
             "QV": "kg kg{-1}", "RH": "%", "QC": "kg kg{-1}", "QI": "kg kg{-1}",
             "QR": "kg kg{-1}", "QS": "kg kg{-1}", "QG": "kg kg{-1}",
             "SOILHGT": "m", "PSFC": "Pa", "PMSL": "Pa", "SKINTEMP": "K"}
    profiles = {"TT": "t", "HGT": "ht", "UU": "u", "VV": "v", "RH": "rh", "QV": "qv"}
    hydros = {"QC": "qc", "QI": "qi", "QR": "qr", "QS": "qs", "QG": "qg"}
    compared = 0
    for key, (unit, shape, flat, metadata) in wps.items():
        short, pressure, valid_time = key
        if (shape != (235, 283) or valid_time != "2026-08-16_13:00:00.0000"
                or units.get(short) != unit):
            raise ValueError(f"invalid HYDRO WPS record metadata: {key}")
        if short in ("UU", "VV") and not metadata.get("wind_grid_relative", False):
            raise ValueError(f"wind coordinate metadata mismatch: {key}")
        _, _, actual, _ = field(wps, short, pressure)
        expected = None
        if short in profiles:
            levels = np.asarray(mapped["p"], dtype=np.float32)
            indices = np.flatnonzero(np.isclose(levels.astype(float)*100, pressure, atol=.25, rtol=0))
            if indices.size == 1:
                expected = mapped[profiles[short]][:, :, int(indices[0])]
        elif short in hydros:
            if pressure == 200100.0:
                expected = np.zeros_like(actual)
            else:
                levels = np.asarray(mapped["p"], dtype=np.float32)[:-1]
                indices = np.flatnonzero(np.isclose(levels.astype(float)*100, pressure, atol=.25, rtol=0))
                if indices.size == 1:
                    expected = mapped[hydros[short]][:, :, int(indices[0])]
        elif short == "SOILHGT":
            expected = mapped["ht"][:, :, -1]
        elif short == "PSFC":
            expected = mapped["psfc"]
        elif short == "PMSL":
            expected = mapped["slp"]
        elif short == "SKINTEMP":
            expected = mapped["skin"]
        if expected is None or not np.array_equal(actual, expected):
            raise ValueError(f"WPS values differ from existing mapper witness: {key}")
        compared += 1
    receipt = {
        "schema": "pr94_hydro_wps_readback_v1",
        "status": "PASS_PR94_HYDRO_WPS_READBACK",
        "role": "HYDRO",
        "wps": {"path": str(wps_path.resolve()), "sha256": sha256(wps_path)},
        "candidate": {"path": str(candidate_path.resolve()), "sha256": candidate_sha},
        "baseline_wps_sha256": sha256(baseline_path),
        "lapsprep_inventory_sha256": sha256(inventory_path),
        "mapped_witness_sha256": sha256(witness_path),
        "compared_records": compared,
        "source_candidate_generation": generation,
        "scope": "Exact serialization through existing pressure-to-WPS mapper and LAPSPREP writer; no scientific promotion.",
    }
    output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    if len(sys.argv) != 7:
        raise SystemExit("usage: pr94_hydro_wps_readback.py HYDRO_WPS BASELINE_WPS INVENTORY WITNESS HYDRO_NC OUTPUT_JSON")
    result = check_wps(*map(Path, sys.argv[1:]))
    print(f"{result['status']}: {result['compared_records']} records")
