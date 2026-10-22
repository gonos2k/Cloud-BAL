#!/usr/bin/env python3
"""Convert the captured native small-step MU change to dry-column kg/s."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import netCDF4
import numpy as np

import pr98_native_effect as native
from pr87_native_history import _constants, _finite
from pr95_call_budget import _read_map_geometry

CONSTANTS = Path("/var/tmp/pr87_history_constants_20261019/receipt.json")


def column_mass_rate(before, after, seconds, c1h, dnw, area, gravity):
    """Differentiate A/g * sum[-(C1H*MU_total+C2H)*DNW] at fixed geometry."""
    before, after, c1h, dnw, area = (
        np.asarray(x, dtype=np.float64) for x in (before, after, c1h, dnw, area))
    if (before.ndim != 2 or after.shape != before.shape or area.shape != before.shape
            or c1h.ndim != 1 or dnw.shape != c1h.shape or not c1h.size):
        raise ValueError("incompatible column geometry")
    if (not all(np.isfinite(x).all() for x in (before, after, c1h, dnw, area))
            or not np.isfinite([seconds, gravity]).all() or seconds <= 0 or gravity <= 0
            or np.any(area <= 0) or np.any(dnw >= 0) or np.any(c1h < 0)):
        raise ValueError("invalid native column measure")
    beta = float(np.sum(-c1h * dnw, dtype=np.float64))
    if beta <= 0:
        raise ValueError("nonpositive hybrid column sensitivity")
    return (after - before) / seconds * area * beta / gravity, beta


def analyze():
    evidence = native.CAPTURE_EVIDENCE
    build = json.loads((evidence / "build_provenance.json").read_text())
    noninterference = json.loads((evidence / "frozen_c1_noninterference.json").read_text())
    bindings = native.verify_capture_manifests(native.CAPTURE_RUNS, evidence, build, noninterference)
    gravity, gravity_pin = _constants(CONSTANTS)
    composition = json.loads(native.COMPOSITION.read_text())["composed_qc_vertical_influence"]
    rates, columns, rows = {}, None, {}
    for arm, root in native.CAPTURE_RUNS.items():
        initial = native.RUNS[arm] / "run/wrfinput_d01"
        if native.cloud.sha256(initial) != bindings["arms"][arm]["candidate_wrfinput_sha256"]:
            raise ValueError(f"{arm} native geometry input hash mismatch")
        with netCDF4.Dataset(initial) as ds:
            ds.set_auto_mask(False)
            area, _, _ = _read_map_geometry(ds, slice(None), slice(None))
            c1h, dnw = (_finite(ds, name, 0) for name in ("C1H", "DNW"))
        support = native.cloud.make_masks(composition, (len(c1h), area.shape[0]-2,
                                                       area.shape[1]-2))["original_613_native_support"]
        input_meta, before = native.native_capture_file(root, "pr98_mu_small_in_", 2)
        output_meta, after = native.native_capture_file(root, "pr98_mu_small_out_", 2)
        dt_meta, seconds = native.native_capture_file(root, "pr98_dts_small", 0)
        _, captured_c1h = native.native_capture_file(root, "pr98_geom_c1h", 1)
        if (input_meta["fortran_bounds"] != output_meta["fortran_bounds"]
                or not np.array_equal(captured_c1h[:len(c1h)], c1h)):
            raise ValueError(f"{arm} captured MU/hybrid geometry mismatch")
        mask = native.support_column_mask(input_meta, before.shape, support.any(axis=0))
        ims, _, jms = input_meta["fortran_bounds"][:3]
        # Capture arrays use native Fortran indices; wrfinput uses zero-based J,I.
        coords = [(int(i+ims), int(j+jms)) for i, j in np.argwhere(mask)]
        if any(not (1 <= i <= area.shape[1] and 1 <= j <= area.shape[0]) for i, j in coords):
            raise ValueError("native support lies outside input geometry")
        if columns is None:
            columns = coords
        elif columns != coords:
            raise ValueError("native support columns differ across arms")
        weights = np.ones_like(before, dtype=np.float64)
        weights[mask] = [area[j-1, i-1] for i, j in coords]
        rate, beta = column_mass_rate(before, after, float(seconds), c1h, dnw, weights, gravity)
        rates[arm] = rate[mask]
        rows[arm] = {
            "wrfinput_sha256": native.cloud.sha256(initial), "hybrid_beta": beta,
            "small_step_seconds": float(seconds),
            "capture_sha256": {"before": input_meta["sha256"], "after": output_meta["sha256"],
                               "seconds": dt_meta["sha256"]},
            "signed_kg_s": float(rates[arm].sum()),
            "L1_kg_s": float(np.abs(rates[arm]).sum()),
            "L2_kg_s": float(np.linalg.norm(rates[arm])),
            "max_abs_column_kg_s": float(np.abs(rates[arm]).max()),
            "max_abs_column_native_ij": coords[int(np.abs(rates[arm]).argmax())],
            "column_area_m2_range": [float(weights[mask].min()), float(weights[mask].max())],
        }
    return {
        "schema": "pr99_observed_native_dry_column_rate_v1", "arms": rows,
        "native_columns_ij": columns, "gravity": gravity_pin, "capture_binding": bindings,
        "composition_sha256": native.cloud.sha256(native.COMPOSITION),
        "COUPLED_minus_HYDRO": native.pair_metrics(rates["HYDRO"], rates["COUPLED"]),
        "units": "kg s-1 per native column; physical dry-mass rate, not momentum or energy",
        "measure": "A/g * sum(-C1H*DNW) * (MU_after-MU_before)/captured_dts",
        "limits": ["First captured acoustic call on the fixed 16-column QC footprint only.",
                   "C1H, DNW, map area and base mass are held fixed within this call.",
                   "This is a transformation of the observed MU update, not a separately closed face-flux budget.",
                   "Signed support change includes redistribution through its edges; it is not global dry-mass loss.",
                   "No momentum acceleration norm or observation skill is established."],
        "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = analyze()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
