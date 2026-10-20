#!/usr/bin/env python3
"""Verify the byte-bound PR83 WPS-to-real QC support chain."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED = {
    "met_em": "5c896259727e224658434b7896b1c04187cd903190d87b8fc790a75dda856e02",
    "laps": "f6e54602dea6fa6c867cbf226efd969d70f1f18526962f4b3dcb13a3189f9da1",
    "klbg": "180e75c16ac2d299e4826324abd71aee530288d2c2c86079355ff1c4c9800e08",
    "wrfinput": "6ed69cbd2bdb8d128dbd7273ac8de216fe4537748a0e4ca474213ac408060730",
}
FG_ORDER = ["SOIT", "SOIM", "KLBG", "LAPS", "RCHA"]
QC_TABLE = {
    "interp_option": "four_pt+average_4pt",
    "fill_missing": "0.",
    "fill_lev": "200100:const(0.)",
    "flag_in_output": "FLAG_QC",
    "qc_specific_interpolation_mask": False,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def horizontal_summary(replay: dict[str, Any]) -> dict[str, Any]:
    rows = replay["comparison_rows"]
    horizontal_cells = len(replay["inverse_support"])
    pressure_source_levels = len(replay["source_levels_k0"])
    matched = sum(row["prediction_hex"] == row["met_em_qc_hex"] for row in rows)
    targets = {(row["target_i0"], row["target_j0"]) for row in rows}
    levels = {row["pressure_pa"] for row in rows}
    if len(rows) != 288 or len(targets) != 16 or len(levels) != 18:
        raise ValueError("expected the fixed 16-target × 18-level WPS replay")
    if matched != len(rows):
        raise ValueError(f"WPS source replay has {len(rows) - matched} QC mismatches")
    return {"source_support_pressure_cells": horizontal_cells * pressure_source_levels,
            "unique_horizontal_source_cells": horizontal_cells,
            "target_metgrid_columns": len(targets), "pressure_levels": len(levels),
            "comparisons": len(rows), "bitwise_matches": matched}


def build_report(met_em: Path, laps: Path, wrfinput: Path, replay_json: Path,
                 composition_json: Path, vertical_probe_json: Path, klbg: Path,
                 klbg_output: Path) -> dict[str, Any]:
    bound_files = {"met_em": met_em, "laps": laps, "klbg": klbg, "wrfinput": wrfinput}
    hashes = {name: sha256(path) for name, path in bound_files.items()}
    for name, expected in EXPECTED.items():
        if hashes[name] != expected:
            raise ValueError(f"{name} SHA-256 does not match the archived PR83 identity")

    horizontal = json.loads(replay_json.read_text())
    composition = json.loads(composition_json.read_text())
    vertical_probe = json.loads(vertical_probe_json.read_text())
    horizontal_result = horizontal_summary(horizontal)
    klbg_rows = [line.split() for line in klbg_output.read_text().splitlines()]
    if len(klbg_rows) != 288:
        raise ValueError(f"expected 288 KLBG control rows, got {len(klbg_rows)}")
    klbg_matches = sum(row[5] == row[6] for row in klbg_rows)
    klbg_vs_laps = sum(row[5] == expected["prediction_hex"]
                       for row, expected in zip(klbg_rows, horizontal["comparison_rows"]))
    totals = composition["composed_qc_vertical_influence"]["totals"]
    probe_result = vertical_probe["result"]
    if (vertical_probe["input_bindings"]["met_em_sha256"] != hashes["met_em"] or
            vertical_probe["input_bindings"]["wrfinput_sha256"] != hashes["wrfinput"]):
        raise ValueError("vertical source-form probe is bound to different initializer inputs")
    if (probe_result["compared_points"] != 624 or probe_result["mismatches"] != 0 or
            not probe_result["o0_o2_bitwise_identical"]):
        raise ValueError("source-form native QC vertical probe is not the expected exact 624-point result")
    return {
        "schema": "pr93_pr83_same_met_em_qc_chain_v1",
        "input_bindings": {name: {"path": str(path), "sha256": hashes[name]}
                           for name, path in bound_files.items()},
        "metgrid_reproduction": {
            "metgrid_executable_sha256": "f96632837016bda00946e0a5cfeaaac3372eba972e4e9451e0e4e88ee8399c37",
            "metgrid_table_sha256": "44f1a43af35441957d0bef3a6220831aad1cf56ebc765d64d08e20f439a63b44",
            "forecast_source_order": FG_ORDER,
            "qc_table": QC_TABLE,
            "reproduced_met_em_sha256_matches_pr83": True,
        },
        "horizontal_qc_replay": horizontal_result,
        "source_priority_control": {
            "source_order": FG_ORDER,
            "klbg_qc_input_present": True,
            "klbg_only_matches_final_met_em_rows": klbg_matches,
            "klbg_only_matches_laps_replay_rows": klbg_vs_laps,
            "interpretation": "KLBG is listed before LAPS in fg_name and contains QC. Its standalone WPS replay matches final QC at only the counted rows; the exact LAPS replay matches all 288 rows. This is evidence for the retained support rows and this product, not a general priority rule.",
        },
        "native_qc_influence": {
            "native_target_levels": totals["native_target_levels"],
            "levels_with_nonzero_qc_support": totals["levels_with_qc_support"],
            "composed_source_links": totals["composed_nonzero_links"],
            "unique_horizontal_source_cells": totals["unique_horizontal_source_cells"],
            "source_form_qcloud_bitwise_matches": probe_result["qcloud_exact_bit_matches"],
            "source_form_mismatches": probe_result["mismatches"],
            "optimization_results_bitwise_identical": probe_result["o0_o2_bitwise_identical"],
        },
        "interpretation_limit": (
            "The preserved source-form real.exe QC vertical expressions match the initialized QCLOUD "
            "at the 16 WPS-touched columns and 39 eta levels. This is a bounded source-form replay, "
            "not a full real.exe execution. Other WPS variables and their masks/fallback behavior are outside scope."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--met-em", type=Path, required=True)
    parser.add_argument("--laps", type=Path, required=True)
    parser.add_argument("--wrfinput", type=Path, required=True)
    parser.add_argument("--horizontal-replay", type=Path, required=True)
    parser.add_argument("--vertical-composition", type=Path, required=True)
    parser.add_argument("--vertical-probe", type=Path, required=True)
    parser.add_argument("--klbg", type=Path, required=True)
    parser.add_argument("--klbg-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    report = build_report(args.met_em, args.laps, args.wrfinput, args.horizontal_replay,
                          args.vertical_composition, args.vertical_probe,
                          args.klbg, args.klbg_output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
