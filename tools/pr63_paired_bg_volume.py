#!/usr/bin/env python3
"""Replay the mapped BG descriptor difference from a matched PR63 run pair."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from native_kdm6_call_geometry import _bound_header_match, parse_geometry
from native_kdm6_trace import read_dump


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(control_geometry: Path, paired_geometry: Path,
           control_post: Path, paired_post: Path) -> dict:
    control_geo_bytes = control_geometry.read_bytes()
    paired_geo_bytes = paired_geometry.read_bytes()
    if control_geo_bytes != paired_geo_bytes:
        raise ValueError("control and paired same-call geometry differ")
    geometry = parse_geometry(control_geo_bytes)[0]
    control = read_dump(control_post)
    paired = read_dump(paired_post)
    if control["stage"] != 2 or paired["stage"] != 2:
        raise ValueError("both KDM6 captures must be post-call records")
    if (control["bounds"] != paired["bounds"] or
            control["itimestep"] != paired["itimestep"] or
            control["params"] != paired["params"]):
        raise ValueError("control and paired KDM6 headers differ")
    if control["itimestep"] != geometry["timestep"]:
        raise ValueError("geometry and KDM6 timestep differ")
    _bound_header_match(geometry, control)
    _bound_header_match(geometry, paired)
    for name in control["fields"]:
        if (not np.isfinite(control["fields"][name]).all() or
                not np.isfinite(paired["fields"][name]).all()):
            raise ValueError(f"nonfinite KDM6 field: {name}")
        if name == "BG":
            continue
        if not np.array_equal(control["fields"][name], paired["fields"][name], equal_nan=True):
            raise ValueError(f"non-BG KDM6 field differs: {name}")

    qg = control["fields"]["QG"]
    bg_control = control["fields"]["BG"].astype(np.float64)
    bg_paired = paired["fields"]["BG"].astype(np.float64)
    mask = (bg_control > 0.0) & (bg_paired == 0.0)
    if not np.any(mask):
        raise ValueError("no positive-to-zero BG cells in paired run")
    if np.any((qg[mask] > 1.0e-9) | (qg[mask] < 0.0)):
        raise ValueError("BG cleanup mask includes graupel above qcrmin or negative QG")
    if np.any((qg <= 1.0e-9) & (bg_control > 0.0) & (bg_paired != 0.0)):
        raise ValueError("paired run leaves BG where QG is under the existing cutoff")

    b = geometry["bounds"]
    kb = control["bounds"]
    arrays = geometry["arrays"]
    i0, i1 = kb["its"] - b["ims"], kb["ite"] - b["ims"] + 1
    j0, j1 = kb["jts"] - b["jms"], kb["jte"] - b["jms"] + 1
    mu = arrays["mu2"][i0:i1, j0:j1].T
    mub = arrays["mub"][i0:i1, j0:j1].T
    msftx = arrays["msftx"][i0:i1, j0:j1].T
    msfty = arrays["msfty"][i0:i1, j0:j1].T
    area = geometry["dx_m"] * geometry["dy_m"] / (msftx * msfty)
    if not np.isfinite(area).all() or np.any(area <= 0.0):
        raise ValueError("mapped cell area is nonpositive or nonfinite")
    layers = np.arange(kb["kts"], kb["kte"] + 1) - b["kms"]
    dp = -(arrays["c1h"][layers, None, None] * (mu[None] + mub[None])
           + arrays["c2h"][layers, None, None]) * arrays["dnw"][layers, None, None]
    md = (dp * area[None] / geometry["gravity_m_s2"]).transpose(1, 0, 2)
    if not np.isfinite(dp).all() or np.any(dp <= 0.0):
        raise ValueError("hybrid layer mass thickness is nonpositive or nonfinite")
    if not np.isfinite(md).all() or np.any(md <= 0.0):
        raise ValueError("mapped dry-mass measure is nonpositive or nonfinite")
    delta = bg_control - bg_paired
    changed = delta != 0.0
    if not np.array_equal(changed, mask):
        raise ValueError("BG changes are not exactly the positive-to-zero mask")
    weighted_volume = float(np.sum(delta * md, dtype=np.float64))
    unweighted_delta = float(np.sum(delta, dtype=np.float64))
    if not np.isfinite(delta).all() or not np.isfinite(weighted_volume) or weighted_volume <= 0.0:
        raise ValueError("mapped BG difference or weighted total is nonpositive/nonfinite")
    if not np.isfinite(unweighted_delta) or unweighted_delta <= 0.0:
        raise ValueError("unweighted BG difference total is nonpositive/nonfinite")
    return {
        "schema": "pr63_paired_bg_volume_replay_v1",
        "scope": "mapped bulk-volume descriptor difference; not a water or energy budget closure",
        "timestep": control["itimestep"],
        "changed_cells": int(mask.sum()),
        "max_bg_delta_m3_per_kg_dry": float(np.max(delta[mask])),
        "unweighted_delta_sum_m3_per_kg_dry": unweighted_delta,
        "hybrid_carrier_weighted_delta_m3": weighted_volume,
        "hybrid_mass_formula": "dp=-(C1H*(MU2+MUB)+C2H)*DNW; md=dp*DX*DY/(MSFTX*MSFTY*g)",
        "hashes": {
            "geometry": sha256(control_geometry),
            "control_post": sha256(control_post),
            "paired_post": sha256(paired_post),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control_geometry", type=Path)
    parser.add_argument("paired_geometry", type=Path)
    parser.add_argument("control_post", type=Path)
    parser.add_argument("paired_post", type=Path)
    args = parser.parse_args()
    result = replay(args.control_geometry, args.paired_geometry,
                    args.control_post, args.paired_post)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
