#!/usr/bin/env python3
"""Integrate same-call KDM6 species changes on the captured hybrid carrier.

This is a research audit, not a budget-closure validator. It binds its three
binary captures to a successful isolated-run receipt and keeps the DEN*DELZ
volume-style diagnostic separate from the hybrid dry-air mass measure.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


def _load_tool(name: str, filename: str) -> Any:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_GEOMETRY = _load_tool("pr65_samecall_geometry", "native_kdm6_call_geometry.py")
_TRACE = _load_tool("pr65_samecall_trace", "native_kdm6_trace.py")
SPECIES = ("Q", "QC", "QR", "QI", "QS", "QG")


def _sum_mass(mixing_ratio: np.ndarray, dry_mass: np.ndarray) -> float:
    value = float(np.sum(mixing_ratio.astype(np.float64) * dry_mass, dtype=np.float64))
    if not math.isfinite(value):
        raise ValueError("nonfinite integrated species mass")
    return value


def _relative_delta(delta: float, baseline: float) -> float | None:
    if not math.isfinite(delta) or not math.isfinite(baseline):
        raise ValueError("relative-change operands must be finite")
    if baseline == 0.0:
        return None
    result = delta / baseline
    if not math.isfinite(result):
        raise ValueError("relative change is nonfinite")
    return result


def _stats(values: np.ndarray) -> dict[str, float | int]:
    finite = np.isfinite(values)
    if not finite.all():
        raise ValueError("nonfinite diagnostic field")
    return {
        "count": int(values.size),
        "changed_count": int(np.count_nonzero(values != 0.0)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
        "max_abs": float(np.max(np.abs(values))),
    }


def audit(geometry_path: Path, pre_path: Path, post_path: Path,
          receipt_path: Path, expected_executable_sha256: str) -> dict[str, Any]:
    geometry_report = _GEOMETRY.audit(
        geometry_path, pre_path, post_path, receipt_path,
        expected_executable_sha256=expected_executable_sha256,
    )
    records = _GEOMETRY.parse_geometry(geometry_path.read_bytes())
    geometry = records[0]
    geometry_equal = {
        name: bool(np.array_equal(records[0]["arrays"][name], records[1]["arrays"][name]))
        for name in _GEOMETRY.ARRAY_NAMES
    }
    if not all(geometry_equal.values()):
        raise ValueError("fixed-carrier budget requires identical pre/post geometry arrays")
    pre, post = _TRACE.read_dump(pre_path), _TRACE.read_dump(post_path)

    measure = _GEOMETRY.active_geometry_measure(geometry, pre)
    area = measure["area"]
    dry_mass = np.transpose(measure["dry_mass"], (1, 0, 2))
    if dry_mass.shape != pre["fields"]["Q"].shape:
        raise ValueError("hybrid dry-mass weights do not align with KDM6 fields")
    if not np.isfinite(dry_mass).all() or np.any(dry_mass <= 0.0):
        raise ValueError("hybrid dry-mass weights are nonpositive or nonfinite")

    component_changes = {}
    water_pre = 0.0
    water_post = 0.0
    for name in SPECIES:
        before = pre["fields"][name].astype(np.float64)
        after = post["fields"][name].astype(np.float64)
        component_changes[name] = {
            "pre_mass_kg": _sum_mass(before, dry_mass),
            "post_mass_kg": _sum_mass(after, dry_mass),
            "delta_mass_kg": _sum_mass(after - before, dry_mass),
            "delta_mixing_ratio": _stats(after - before),
        }
        water_pre += component_changes[name]["pre_mass_kg"]
        water_post += component_changes[name]["post_mass_kg"]
    if not math.isfinite(water_pre) or not math.isfinite(water_post):
        raise ValueError("aggregate total-water storage must be finite")

    qc_pre = pre["fields"]["QC"].astype(np.float64)
    negative_qc = qc_pre < 0.0
    negative_qc_clip_mass = float(np.sum(-qc_pre[negative_qc] * dry_mass[negative_qc], dtype=np.float64))
    if not math.isfinite(negative_qc_clip_mass):
        raise ValueError("nonfinite negative-QC cleanup estimate")

    temperatures = {}
    for label, state in (("pre", pre), ("post", post)):
        # Reconstruct temperature in float64 from the captured REAL*4 operands.
        temperature = (state["fields"]["TH"].astype(np.float64)
                       * state["fields"]["PII"].astype(np.float64))
        temperatures[label] = temperature
    temp_change = temperatures["post"] - temperatures["pre"]
    dry_mass_total = float(np.sum(dry_mass, dtype=np.float64))
    weighted_temp_change = float(np.sum(temp_change.astype(np.float64) * dry_mass, dtype=np.float64))
    if not math.isfinite(dry_mass_total) or dry_mass_total <= 0.0:
        raise ValueError("hybrid dry-mass total must be finite and positive")
    weighted_temp_change_mean = weighted_temp_change / dry_mass_total
    if not math.isfinite(weighted_temp_change) or not math.isfinite(weighted_temp_change_mean):
        raise ValueError("nonfinite weighted temperature diagnostic")

    den_delz = {}
    for label, state in (("pre", pre), ("post", post)):
        # Promote the stored REAL*4 operands before the diagnostic product and
        # reduce in float64; the legacy geometry audit's REAL*4 product is
        # retained separately below for an apples-to-apples provenance link.
        den = state["fields"]["DEN"].astype(np.float64)
        delz = state["fields"]["DELZ"].astype(np.float64)
        if (not np.isfinite(den).all() or not np.isfinite(delz).all()
                or np.any(den <= 0.0) or np.any(delz <= 0.0)):
            raise ValueError(f"{label} DEN and DELZ must be finite and positive")
        diagnostic = den * delz * area[:, None, :]
        total = float(np.sum(diagnostic, dtype=np.float64))
        if not np.isfinite(diagnostic).all() or not math.isfinite(total) or total <= 0.0:
            raise ValueError("invalid DEN*DELZ area diagnostic")
        den_delz[label] = {
            "total_kg_diagnostic": total,
            "arithmetic": "DEN and DELZ promoted to float64 before multiplication; area scaling and reduction in float64",
            "relative_difference_from_hybrid_dry_mass": total / float(np.sum(dry_mass)) - 1.0,
        }
    legacy_den_delz = float(geometry_report["DEN_DELZ_area_mass_diagnostic_kg"])
    promoted_den_delz = den_delz["pre"]["total_kg_diagnostic"]
    if not math.isfinite(legacy_den_delz):
        raise ValueError("nonfinite legacy DEN*DELZ comparison")
    den_delz_precision_comparison = {
        "legacy_geometry_audit_float32_product_kg": legacy_den_delz,
        "promoted_float64_product_kg": promoted_den_delz,
        "difference_kg": promoted_den_delz - legacy_den_delz,
        "relative_difference_to_hybrid_mass": (promoted_den_delz - legacy_den_delz)
            / float(np.sum(dry_mass)),
        "interpretation": "Both are volume-style diagnostics from the same stored DEN/DELZ values and same area. Their small difference is arithmetic-order sensitivity, not a physical tolerance or closure result.",
    }
    if not all(math.isfinite(value) for value in (
            den_delz_precision_comparison["difference_kg"],
            den_delz_precision_comparison["relative_difference_to_hybrid_mass"])):
        raise ValueError("nonfinite DEN*DELZ arithmetic-order comparison")

    water_delta = water_post - water_pre
    if not math.isfinite(water_delta):
        raise ValueError("nonfinite total-water endpoint difference")
    return {
        "schema": "pr65_samecall_kdm6_water_budget_audit_v1",
        "execution_scope": "same-call KDM6 pre/post fields, first timestep, one-rank/one-tile research observer",
        "geometry_audit": geometry_report,
        "integrated_measures": {
            "hybrid_dry_air_mass_kg": float(np.sum(dry_mass, dtype=np.float64)),
            "formula": "sum(dp_k * DX*DY/(MSFTX*MSFTY) / g), dp_k=-[C1H_k*(MU2+MUB)+C2H_k]*DNW_k",
            "species_mixing_ratio_basis": "KDM6 Q, QC, QR, QI, QS, QG are treated as kg species per kg dry air",
            "DEN_DELZ_diagnostic": den_delz,
            "DEN_DELZ_precision_comparison": den_delz_precision_comparison,
        },
        "species_mass_changes": component_changes,
        "total_water": {
            "species": list(SPECIES),
            "pre_kg": water_pre,
            "post_kg": water_post,
            "delta_kg": water_delta,
            "relative_delta": _relative_delta(water_delta, water_pre),
            "closure": "OPEN: same-call precipitation accumulation/bottom sedimentation flux is not captured; the net storage change cannot be closed or attributed.",
        },
        "negative_qc_cleanup": {
            "pre_negative_cell_count": int(np.count_nonzero(negative_qc)),
            "pre_negative_qc_hybrid_mass_correction_kg_if_clipped_to_zero": negative_qc_clip_mass,
            "post_negative_cell_count": int(np.count_nonzero(post["fields"]["QC"] < 0.0)),
            "interpretation": "The model microphysics source clips input QC to nonnegative at call entry. This estimate is not a complete decomposition of QC change and is not a new model floor proposal.",
        },
        "temperature_change_diagnostic": {
            "formula": "T=TH*PII reconstructed in float64 from captured REAL*4 operands; report only, not an energy measure",
            "delta_temperature_k": _stats(temp_change),
            "dry_mass_weighted_delta_temperature_kg_k": weighted_temp_change,
            "dry_mass_weighted_mean_delta_temperature_k": weighted_temp_change_mean,
            "energy_closure": "OPEN: the same-call thermodynamic tendency/enthalpy ledger and precipitation enthalpy export are not captured. A broader whole-model energy budget would additionally require pressure-work and kinetic-energy terms.",
        },
        "missing_budget_terms": [
            "same-call rainncv/snowncv/graupelncv or equivalent bottom sedimentation flux increments",
            "per-process phase and cleanup tendency ledger to separate internal transfers from nonconservative edits",
            "same-call thermodynamic tendency/enthalpy ledger and precipitation enthalpy export",
            "pressure-work and kinetic-energy terms only if asserting a broader whole-model energy budget",
        ],
        "capture_hashes": geometry_report["capture_hashes"],
        "receipt_sha256": geometry_report["receipt_sha256"],
        "diagnostic_limits": [
            "The hybrid dry-air measure uses the exact same-call host geometry and is fixed across the KDM6 call in this capture.",
            "DEN*DELZ*area is reported as a separate volume-style diagnostic and is not substituted for hybrid dry-air mass.",
            "The integrated changes are endpoint storage diagnostics; they are not mass or energy closure because source and boundary fluxes are incomplete.",
            "Float32 state fields are reduced in float64; no formal aggregate summation error bound is claimed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry", type=Path)
    parser.add_argument("pre", type=Path)
    parser.add_argument("post", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--expected-executable-sha256", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.geometry, args.pre, args.post, args.receipt,
                   args.expected_executable_sha256)
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
