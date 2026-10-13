#!/usr/bin/env python3
"""Compare paired same-time PR83/MODE_OFF native initial states."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pr83_moment_candidate_readback import compare_native_initial_outputs
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_native_hybrid_geometry import compare as compare_hybrid_water

NATIVE_GRAVITY_M_S2 = 9.81


def native_transfer_inventory(xa: Path, xb: Path) -> dict:
    """Compute Xa-Xb dry-mass and water deltas on matched native grids."""
    inventory = compare_hybrid_water(xb, xa, NATIVE_GRAVITY_M_S2)
    inventory["interpretation"] = (
        "same-grid native initial-state transfer/composition diagnostic; not physical-time closure; "
        "boundary flux and energy closure remain open")
    inventory["field_delta_direction"] = "Xa minus Xb"
    inventory["gravity_source"] = "pinned native module_model_constants G value: 9.81 m s-2"
    return inventory


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: pr83_same13_native_pair_readback.py XA_INITIAL_WRFO XB_OFF_INITIAL_WRFO OUTPUT_JSON")
    xa, xb, output = map(Path, sys.argv[1:])
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"refusing to overwrite paired readback: {output}")
    report = compare_native_initial_outputs(xa.resolve(strict=True), xb.resolve(strict=True))
    report["dry_mass_six_water_inventory"] = native_transfer_inventory(
        xa.resolve(strict=True), xb.resolve(strict=True))
    report.update({
        "schema": "pr83_same13_native_mode_off_pair_readback_v1",
        "status": "PASS_SCOPED_SAME13_NATIVE_MODE_OFF_PAIR_READBACK",
        "comparison": "M(Xa)-M(Xb) on matched 13 UTC native initial fields",
        "science_authority": "NONE",
        "operational_authority": "NONE",
        "candidate_promoted": False,
    })
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "output": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
