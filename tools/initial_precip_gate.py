#!/usr/bin/env python3
"""Build frozen, input-only QSNOW gates and equal-mass scalar controls."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import netCDF4
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
GEOMETRY_PATH = ROOT / "tools/check_native_hybrid_geometry.py"
GRAVITY = 9.81
QUANTILE_PAIRS = {"G50_90": (0.50, 0.90), "G75_95": (0.75, 0.95),
                  "G90_99": (0.90, 0.99)}
CASE_TO_GATE = {f"{kind}_{name}": (kind, name)
                for name in QUANTILE_PAIRS for kind in ("GATE", "EQ")}
UNCHANGED_CASES = {"FIXED_ORIGINAL_100", "ORIGINAL_B1_100"}
EPSILON = 1e-12


def _load_geometry_module():
    spec = importlib.util.spec_from_file_location("native_hybrid_geometry", GEOMETRY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load hybrid geometry helper: {GEOMETRY_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def column_precip_proxy(dataset, gravity: float = GRAVITY):
    """Return X=Σ(qr+qs+qg)dp_d/Σdp_d and the validated hybrid geometry."""
    geometry_module = _load_geometry_module()
    _, geometry = geometry_module.read_geometry(dataset, gravity)
    species = []
    for name in ("QRAIN", "QSNOW", "QGRAUP"):
        variable = dataset.variables[name]
        if variable.dimensions != ("Time", "bottom_top", "south_north", "west_east"):
            raise ValueError(f"{name}: expected mass-level WRF field")
        if getattr(variable, "units", None) != "kg kg-1":
            raise ValueError(f"{name}: expected kg kg-1")
        values = np.asarray(variable[0], dtype=np.float64)
        if not np.all(np.isfinite(values)) or np.any(values < 0):
            raise ValueError(f"{name}: nonfinite or negative mixing ratio")
        species.append(values)
    dp = geometry["dp_pa"]
    if dp.shape != species[0].shape:
        raise ValueError("hybrid dp and hydrometeor shapes differ")
    column = np.sum((species[0] + species[1] + species[2]) * dp, axis=0,
                    dtype=np.float64) / np.sum(dp, axis=0, dtype=np.float64)
    if not np.all(np.isfinite(column)) or np.any(column < 0):
        raise ValueError("invalid initial precipitating-water proxy")
    return column, geometry


def gate_alpha(proxy, lower_quantile: float, upper_quantile: float):
    """Create a bounded smoothstep alpha field using positive input columns only."""
    values = np.asarray(proxy, dtype=np.float64)
    if values.ndim != 2 or not values.size or not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError("proxy must be a finite nonnegative 2-D field")
    if not 0 <= lower_quantile < upper_quantile <= 1:
        raise ValueError("quantiles must satisfy 0 <= lower < upper <= 1")
    positive = values[values > 0]
    if positive.size < 2:
        raise ValueError("proxy needs at least two positive columns")
    q_lower, q_upper = np.quantile(positive, [lower_quantile, upper_quantile], method="linear")
    if not np.isfinite(q_lower + q_upper) or q_lower <= 0 or q_upper <= q_lower:
        raise ValueError("positive-column quantiles must be finite, positive, and distinct")
    log_lower = np.log(q_lower + EPSILON)
    log_upper = np.log(q_upper + EPSILON)
    u = np.clip((np.log(values + EPSILON) - log_lower) / (log_upper - log_lower), 0.0, 1.0)
    weight = u * u * (3.0 - 2.0 * u)
    alpha = 1.0 + 2.0 * weight
    if not np.all(np.isfinite(alpha)) or np.any(alpha < 1.0) or np.any(alpha > 3.0):
        raise ValueError("gate alpha escaped [1, 3]")
    return alpha, {"lower_quantile": lower_quantile, "upper_quantile": upper_quantile,
                   "lower_value_kg_kg": float(q_lower), "upper_value_kg_kg": float(q_upper),
                   "positive_column_count": int(positive.size),
                   "proxy_min_kg_kg": float(values.min()), "proxy_max_kg_kg": float(values.max())}


def scaled_qsnow(source_qsnow, alpha_2d):
    """Apply one horizontal alpha at every mass level with native float32 output."""
    source = np.asarray(source_qsnow)
    alpha = np.asarray(alpha_2d, dtype=np.float64)
    if source.dtype != np.dtype("float32") or source.ndim != 3:
        raise ValueError("QSNOW must be native float32 (level, y, x)")
    if alpha.shape != source.shape[1:] or not np.all(np.isfinite(alpha)):
        raise ValueError("alpha field must match QSNOW's horizontal grid")
    if np.any(alpha < 0) or not np.all(np.isfinite(source)) or np.any(source < 0):
        raise ValueError("alpha and QSNOW must be finite and nonnegative")
    result = (source.astype(np.float64) * alpha[None, :, :]).astype(np.float32)
    if not np.all(np.isfinite(result)) or np.any(result < 0):
        raise ValueError("scaled QSNOW is invalid")
    return result


def dry_snow_mass(qsnow, dry_mass_kg):
    q = np.asarray(qsnow, dtype=np.float64)
    mass = np.asarray(dry_mass_kg, dtype=np.float64)
    if q.shape != mass.shape or not np.all(np.isfinite(q)) or np.any(q < 0):
        raise ValueError("QSNOW and hybrid dry-mass arrays must be finite and shape-matched")
    if not np.all(np.isfinite(mass)) or np.any(mass <= 0):
        raise ValueError("hybrid dry mass must be finite and positive")
    return float(np.sum(q * mass, dtype=np.float64))


def equal_mass_alpha(source_qsnow, gate_qsnow, dry_mass_kg):
    """Return uniform alpha matching the rounded gate's diagnostic initial mass."""
    source_mass = dry_snow_mass(source_qsnow, dry_mass_kg)
    gate_mass = dry_snow_mass(gate_qsnow, dry_mass_kg)
    if source_mass <= 0 or gate_mass <= 0:
        raise ValueError("source and gated QSNOW masses must be positive")
    alpha = gate_mass / source_mass
    uniform_qsnow = scaled_qsnow(source_qsnow, np.full(source_qsnow.shape[1:], alpha))
    uniform_mass = dry_snow_mass(uniform_qsnow, dry_mass_kg)
    relative_error = abs(uniform_mass - gate_mass) / gate_mass
    if relative_error > 1e-6:
        raise ValueError(f"equal-mass quantization error exceeds 1e-6: {relative_error}")
    return alpha, uniform_qsnow, {"source_diagnostic_mass_kg": source_mass,
                                  "gate_diagnostic_mass_kg": gate_mass,
                                  "uniform_diagnostic_mass_kg": uniform_mass,
                                  "gate_added_snow_kg": gate_mass - source_mass,
                                  "uniform_added_snow_kg": uniform_mass - source_mass,
                                  "relative_mass_difference": relative_error}


def case_qsnow_transform(case_id, source_qsnow, frozen_maps):
    """Resolve a candidate's QSNOW values from the frozen map or leave them exact."""
    source = np.asarray(source_qsnow)
    if case_id in UNCHANGED_CASES:
        return {"case": case_id, "gate_name": None, "kind": "UNCHANGED",
                "alpha": 1.0, "replacement": source, "write_qsnow": False,
                "transform": "no QSNOW change"}
    if case_id not in CASE_TO_GATE:
        raise ValueError(f"unknown QSNOW experiment case: {case_id}")
    kind, gate_name = CASE_TO_GATE[case_id]
    map_key = f"{gate_name}_alpha" if kind == "GATE" else f"{gate_name}_alpha_equal_mass"
    snow_key = f"{gate_name}_qsn_gated" if kind == "GATE" else f"{gate_name}_qsn_equal_mass"
    alpha = np.asarray(frozen_maps[map_key], dtype=np.float64)
    replacement = np.asarray(frozen_maps[snow_key])
    expected = scaled_qsnow(source, alpha)
    if not np.array_equal(replacement, expected):
        raise ValueError(f"{case_id}: frozen QSNOW does not match source and alpha map")
    return {"case": case_id, "gate_name": gate_name, "kind": kind,
            "alpha": alpha, "replacement": replacement, "write_qsnow": True,
            "transform": (f"spatial gate {gate_name}" if kind == "GATE"
                          else f"uniform equal-mass control for {gate_name}")}


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def freeze(input_path: Path, output_path: Path):
    input_path, output_path = Path(input_path), Path(output_path)
    input_sha = sha256(input_path)
    with netCDF4.Dataset(input_path) as dataset:
        proxy, geometry = column_precip_proxy(dataset)
        source = np.asarray(dataset.variables["QSNOW"][0])
        latitude = np.asarray(dataset.variables["XLAT"][0], dtype=np.float64)
        longitude = np.asarray(dataset.variables["XLONG"][0], dtype=np.float64)
        gates = {}
        maps = {}
        for name, (qlo, qhi) in QUANTILE_PAIRS.items():
            alpha, thresholds = gate_alpha(proxy, qlo, qhi)
            gated = scaled_qsnow(source, alpha)
            eq_alpha, equalized, mass = equal_mass_alpha(source, gated, geometry["dry_mass_kg"])
            maps[f"{name}_alpha"] = alpha
            maps[f"{name}_qsn_gated"] = gated
            maps[f"{name}_qsn_equal_mass"] = equalized
            maps[f"{name}_alpha_equal_mass"] = np.full(proxy.shape, eq_alpha, dtype=np.float64)
            gates[name] = {**thresholds, **mass, "equal_mass_alpha": eq_alpha,
                           "gate_alpha_min": float(alpha.min()), "gate_alpha_max": float(alpha.max()),
                           "gate_alpha_mean": float(alpha.mean()),
                           "gate_alpha_positive_columns_gt_one": int(np.count_nonzero(alpha > 1.0))}
            area = geometry["area_m2"]
            source_column = np.sum(source.astype(np.float64) * geometry["dry_mass_kg"], axis=0) / area
            gate_column = np.sum(gated.astype(np.float64) * geometry["dry_mass_kg"], axis=0) / area
            equal_column = np.sum(equalized.astype(np.float64) * geometry["dry_mass_kg"], axis=0) / area
            maps[f"{name}_source_qsn_column_kg_m2"] = source_column
            maps[f"{name}_gate_qsn_column_kg_m2"] = gate_column
            maps[f"{name}_eq_qsn_column_kg_m2"] = equal_column
            maps[f"{name}_gate_added_qsn_column_kg_m2"] = gate_column - source_column
            maps[f"{name}_eq_added_qsn_column_kg_m2"] = equal_column - source_column
        if sha256(input_path) != input_sha:
            raise ValueError("source wrfinput changed during gate freeze")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if latitude.shape != proxy.shape or longitude.shape != proxy.shape:
        raise ValueError("native XLAT/XLONG do not match the gate grid")
    np.savez_compressed(output_path, proxy=proxy, latitude=latitude, longitude=longitude, **maps)
    return {"schema": "initial-precip-gates-v1", "source_wrfinput": str(input_path.resolve()),
            "source_wrfinput_sha256": input_sha, "frozen_map_path": str(output_path.resolve()),
            "frozen_map_sha256": sha256(output_path), "gravity_m_s2": GRAVITY,
            "proxy": "Σ(QRAIN+QSNOW+QGRAUP)*hybrid_dp_d / Σ(hybrid_dp_d)",
            "hybrid_geometry": "tools/check_native_hybrid_geometry.py read_geometry; HYBRID_OPT=2",
            "gate": "u=clip((log(X+1e-12)-log(qL+1e-12))/(log(qU+1e-12)-log(qL+1e-12)),0,1); w=u^2(3-2u); alpha=1+2w",
            "quantile_method": "numpy linear quantiles over positive X columns only",
            "alpha_vertical_application": "same 2-D alpha at all native QSNOW mass levels; float64 multiply then float32 cast",
            "frozen_map_units": {"proxy": "kg kg-1", "alpha": "dimensionless", "qsn_*": "kg kg-1 by mass level",
                                 "*_qsn_column_kg_m2": "diagnostic dry-mass-weighted QSNOW column amount kg m-2"},
            "gate_controls": gates,
            "mass_scope": "diagnostic initial dry-mass-weighted QSNOW only; no conservation or balance claim",
            "forecast_output_or_observation_used": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = freeze(args.input, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
