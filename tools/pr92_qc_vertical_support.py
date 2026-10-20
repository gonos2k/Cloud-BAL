#!/usr/bin/env python3
"""Reconstruct WRF real.exe QC pressure-to-eta support for archived targets."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ROOT / "docs/evidence/pr91_science_sources_20261020/horizontal_replay/laps_qc_horizontal_rows.json"
SOURCE_PRESSURES = tuple(range(95_000, 9_999, -5_000))
G = 9.81
RD = 287.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dry_mixing_ratio(rh: np.ndarray, temperature: np.ndarray,
                     pressure: np.ndarray) -> np.ndarray:
    """Source-equivalent real.exe rh_to_mxrat1 liquid-water branch."""
    rh = np.clip(rh.astype(np.float64), 0.0, 100.0)
    t_c = temperature.astype(np.float64) - 273.16
    es = 0.6112 * 10.0 * np.exp(17.67 * (temperature - 273.15) /
                                (temperature - 29.65))
    vapor_hpa = es * rh * 0.01
    total_hpa = pressure.astype(np.float64) / 100.0
    vapor_hpa = np.minimum(vapor_hpa, total_hpa)
    q = np.where(vapor_hpa >= total_hpa, 1.0e-6,
                 np.maximum(0.622 * vapor_hpa / (total_hpa - vapor_hpa), 1.0e-6))
    q = np.where((pressure < 10_000.0) & (q > 1.0e-5), 3.0e-6, q)
    q = np.where((pressure < 110_000.0) & (q < 1.0e-6), 1.0e-6, q)
    return q


def source_dry_pressure(pressure: np.ndarray, q: np.ndarray, temperature: np.ndarray,
                        height: np.ndarray) -> tuple[np.ndarray, float]:
    """Port the metgrid-column branch of real.exe integ_moist."""
    intq = 0.0
    dry = np.zeros_like(pressure, dtype=np.float64)
    dry[-1] = pressure[-1]
    for k in range(len(pressure) - 2, 0, -1):
        rho_bar = (pressure[k] / (RD * temperature[k]) +
                   pressure[k + 1] / (RD * temperature[k + 1])) * 0.5
        q_bar = (q[k] + q[k + 1]) * 0.5
        intq += G * q_bar * rho_bar / (1.0 + q_bar) * (height[k + 1] - height[k])
        dry[k] = pressure[k] - intq

    level_above_surface = next((k for k in range(1, len(pressure) - 1)
                                if pressure[k] < pressure[0]), None)
    if level_above_surface is None:
        raise ValueError("real.exe integ_moist could not find the first source level above the surface")
    k = level_above_surface
    surface_pressure = pressure[0]
    if pressure[k - 1] >= surface_pressure and pressure[k] < surface_pressure:
        p1, p2 = surface_pressure, pressure[k]
        t1, t2 = temperature[0], temperature[k]
        q1, q2 = q[0], q[k]
        z1, z2 = height[0], height[k]
        rho_bar = (p1 / (RD * t1) + p2 / (RD * t2)) * 0.5
        q_bar = (q1 + q2) * 0.5
        dz = z2 - z1
        if dz > 0.1:
            intq += G * q_bar * rho_bar / (1.0 + q_bar) * dz
        for level in range(k - 1, 0, -1):
            dry[level] = pressure[level] - intq
    dry[0] = pressure[0] - intq
    return dry, intq


def interpolation_levels(source_pressure: np.ndarray, target_pressure: np.ndarray,
                         zap_close_pa: float = 500.0,
                         interp_type: int = 2) -> tuple[list[dict[str, Any]], list[int]]:
    """Apply real.exe level selection and first-order pressure/log-pressure weights."""
    pressure = source_pressure.astype(np.float64)
    if pressure[1] < pressure[-1]:
        pressure = np.concatenate((pressure[:1], pressure[:0:-1]))
        original_indices = np.concatenate((np.array([0]), np.arange(len(pressure) - 1, 0, -1)))
    else:
        original_indices = np.arange(len(pressure))

    # For this 21-level met_em input the lowest input level is the surface (ko_above_sfc=2).
    ordered: list[tuple[int, float]] = [(int(original_indices[0]), float(pressure[0]))]
    zapped: list[int] = []
    for idx in range(1, len(pressure)):
        delta = ordered[-1][1] - float(pressure[idx])
        if delta < zap_close_pa and idx < len(pressure) - 1:
            zapped.append(int(original_indices[idx]))
            continue
        ordered.append((int(original_indices[idx]), float(pressure[idx])))

    rows: list[dict[str, Any]] = []
    for target in target_pressure.astype(np.float64):
        coordinate = np.log if interp_type == 2 else (lambda x: x)
        if target > ordered[0][1]:
            # Source lagrange_setup's var_type='Q', extrap_type=1 branch uses levels 2 and 3.
            left, right = ordered[1], ordered[2]
            x1, x2, xt = coordinate(left[1]), coordinate(right[1]), coordinate(target)
            w1 = float((xt - x2) / (x1 - x2))
            w2 = float((x1 - xt) / (x1 - x2))
            coefficients = [(left[0], w1), (right[0], w2)]
            mode = "below_ground_log_pressure_extrapolation" if interp_type == 2 else "below_ground_pressure_extrapolation"
        else:
            pair = None
            for left, right in zip(ordered[:-1], ordered[1:]):
                if (target - left[1]) * (target - right[1]) <= 0.0:
                    pair = (left, right)
                    break
            if pair is None:
                raise ValueError(f"eta pressure {target:.3f} Pa lies outside source pressure range")
            left, right = pair
            x_left, x_right, x_target = coordinate(left[1]), coordinate(right[1]), coordinate(target)
            span = x_left - x_right
            w_left = (x_target - x_right) / span
            w_right = (x_left - x_target) / span
            coefficients = [(left[0], float(w_left)), (right[0], float(w_right))]
            mode = "linear_log_pressure_interpolation" if interp_type == 2 else "linear_pressure_interpolation"
        coeff = [{"met_em_pressure_index0": int(index), "pressure_pa": float(source_pressure[index]),
                  "input_pressure_pa": float(pressure[index]), "weight": float(weight)}
                 for index, weight in coefficients if abs(weight) > 1.0e-12]
        rows.append({"target_pressure_pa": float(target), "mode": mode,
                     "vertical_coefficients": coeff})
    return rows, zapped


def compose_horizontal(horizontal: dict[str, Any], targets: list[dict[str, Any]],
                       rows_by_target: dict[tuple[int, int], list[dict[str, Any]]]) -> dict[str, Any]:
    target_links: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for source in horizontal["links_by_source_cell"]:
        for link in source["links"]:
            key = (int(link["target_i0"]), int(link["target_j0"]))
            target_links.setdefault(key, []).append({
                "source_i0": int(source["source_i0"]), "source_j0": int(source["source_j0"]),
                "coefficient": float(link["coefficient_f32"])})
    totals = {"native_target_levels": 0, "levels_with_qc_support": 0,
              "composed_nonzero_links": 0, "unique_horizontal_source_cells": set()}
    target_records = []
    candidate_k0_by_met_em_index = {index: index + 1 for index in range(2, 20)}
    for target in targets:
        key = (int(target["target_i0"]), int(target["target_j0"]))
        horizontal_rows = target_links.get(key, [])
        vertical = rows_by_target[key]
        levels = []
        for eta_level0, row in enumerate(vertical):
            source_weights = []
            for source_coeff in row["vertical_coefficients"]:
                pressure_index = source_coeff["met_em_pressure_index0"]
                if pressure_index not in candidate_k0_by_met_em_index:
                    continue
                candidates = [item for item in horizontal_rows
                              if candidate_k0_by_met_em_index[pressure_index] in horizontal["candidate_source_k0"]]
                for item in candidates:
                    source_weights.append({**item, "met_em_pressure_index0": pressure_index,
                                           "input_pressure_pa": source_coeff["input_pressure_pa"],
                                           "dry_pressure_pa": source_coeff["pressure_pa"],
                                           "vertical_weight": source_coeff["weight"],
                                           "composed_weight": item["coefficient"] * source_coeff["weight"]})
            nonzero = [item for item in source_weights if abs(item["composed_weight"]) > 1.0e-12]
            totals["native_target_levels"] += 1
            totals["composed_nonzero_links"] += len(nonzero)
            if nonzero:
                totals["levels_with_qc_support"] += 1
                totals["unique_horizontal_source_cells"].update((x["source_i0"], x["source_j0"]) for x in nonzero)
            levels.append({"native_eta_level0": eta_level0, "mode": row["mode"],
                           "vertical_coefficients": row["vertical_coefficients"],
                           "composed_qc_source_links": nonzero})
        target_records.append({"target_i0": key[0], "target_j0": key[1], "native_levels": levels})
    totals["unique_horizontal_source_cells"] = len(totals["unique_horizontal_source_cells"])
    return {"totals": totals, "targets": target_records}


def analyze(met_em_path: Path, wrfinput_path: Path, horizontal_path: Path) -> dict[str, Any]:
    horizontal = json.loads(horizontal_path.read_text())
    targets = horizontal["union_target_cells"]
    rows_by_target: dict[tuple[int, int], list[dict[str, Any]]] = {}
    mu_residuals = []
    qcloud_residuals = []
    worst_qcloud = []
    source_columns = []
    with netCDF4.Dataset(met_em_path) as met, netCDF4.Dataset(wrfinput_path) as native:
        met.set_auto_mask(False); native.set_auto_mask(False)
        plev = np.asarray(met.variables["PRES"][0], dtype=np.float64)
        qc = np.asarray(met.variables["QC"][0], dtype=np.float64)
        source_pressures = plev[:, 0, 0]
        ptop = float(native.variables["P_TOP"][0])
        mu_total = (np.asarray(native.variables["MU"][0], dtype=np.float64) +
                    np.asarray(native.variables["MUB"][0], dtype=np.float64))
        c3h = np.asarray(native.variables["C3H"][0], dtype=np.float64)
        c4h = np.asarray(native.variables["C4H"][0], dtype=np.float64)
        qc_initial = np.asarray(native.variables["QCLOUD"][0], dtype=np.float64)
        for target in targets:
            i, j = int(target["target_i0"]), int(target["target_j0"])
            p = np.asarray(met.variables["PRES"][0, :, j, i], dtype=np.float64)
            rh = np.asarray(met.variables["RH"][0, :, j, i], dtype=np.float64)
            t = np.asarray(met.variables["TT"][0, :, j, i], dtype=np.float64)
            z = np.asarray(met.variables["GHT"][0, :, j, i], dtype=np.float64)
            if "QV" in met.variables:
                q = np.asarray(met.variables["QV"][0, :, j, i], dtype=np.float64)
                humidity_branch = "direct_QV_met_em"
            else:
                q = dry_mixing_ratio(rh, t, p)
                humidity_branch = "RH_to_QV_liquid"
            terrain = float(met.variables["HGT_M"][0, j, i])
            psfc_input = float(met.variables["PSFC"][0, j, i])
            tavgsfc = float(met.variables["TAVGSFC"][0, j, i])
            psfc = psfc_input * math.exp(G * (z[0] - terrain) /
                                         (RD * tavgsfc * (1.0 + 0.608 * q[0])))
            pd_gc, intq = source_dry_pressure(p, q, t, z)
            mu0 = psfc - intq - ptop
            mu_residuals.append(mu0 - mu_total[j, i])
            pnew = c3h * mu0 + c4h + ptop
            interp_rows, zapped = interpolation_levels(pd_gc, pnew, interp_type=2)
            rows_by_target[(i, j)] = interp_rows
            # Independently apply the source first-order operator to the met_em QC column.
            out = np.zeros(len(pnew), dtype=np.float64)
            for k, row in enumerate(interp_rows):
                for coeff in row["vertical_coefficients"]:
                    out[k] += qc[coeff["met_em_pressure_index0"], j, i] * coeff["weight"]
            observed = qc_initial[:, j, i]
            residual = out - observed
            qcloud_residuals.extend(residual.tolist())
            worst_level = int(np.argmax(np.abs(residual)))
            worst_qcloud.append({"target_i0": i, "target_j0": j,
                                 "native_eta_level0": worst_level,
                                 "reconstructed_qcloud": float(out[worst_level]),
                                 "initialized_qcloud": float(observed[worst_level]),
                                 "difference": float(residual[worst_level]),
                                 "vertical_row": interp_rows[worst_level]})
            source_columns.append({"target_i0": i, "target_j0": j,
                                   "surface_pressure_input_pa": psfc_input,
                                   "surface_pressure_real_source_formula_pa": psfc,
                                   "surface_temperature_real_source_formula_k": tavgsfc,
                                   "humidity_branch": humidity_branch,
                                   "integrated_vapor_pressure_pa": intq,
                                   "mu0_real_source_formula_pa": mu0,
                                   "mu0_minus_wrfinput_mu_plus_mub_pa": mu0 - mu_total[j, i],
                                   "close_levels_zapped_met_em_pressure_indices0": zapped,
                                   "source_dry_pressure_pa": pd_gc.tolist(),
                                   "target_eta_dry_pressure_pa": pnew.tolist(),
                                   "eta_qc_vs_wrfinput_qcloud": {
                                       "max_abs_difference": float(np.max(np.abs(out - observed))),
                                       "mean_abs_difference": float(np.mean(np.abs(out - observed))),
                                       "native_qc_initial_max": float(np.max(np.abs(observed)))}})
    horizontal["candidate_source_k0"] = list(range(3, 21))
    composed = compose_horizontal(horizontal, targets, rows_by_target)
    return {"schema": "pr92_real_qc_vertical_support_v1",
            "method": "Source-form reconstruction of real.exe `integ_moist`, `p_dts`, `p_dry`, and first-order log-pressure QC `vert_interp`; composed only with preserved QC WPS horizontal links.",
            "input_bindings": {"met_em_path": str(met_em_path), "met_em_sha256": sha256(met_em_path),
                               "wrfinput_path": str(wrfinput_path), "wrfinput_sha256": sha256(wrfinput_path),
                               "horizontal_rows_path": str(horizontal_path), "horizontal_rows_sha256": sha256(horizontal_path)},
            "operator_configuration": {"interp_type": 2, "interp_coordinate": "natural log of dry pressure in Pa",
                                       "lagrange_order": 1, "extrap_type": 1,
                                       "use_surface": True, "use_levels_below_ground": True,
                                       "force_sfc_in_vinterp": 0, "zap_close_levels_pa": 500.0,
                                       "pressure_target": "C3H*mu0 + C4H + P_TOP; mu0=PSFC-integrated_vapor-P_TOP",
            "humidity_branch": "direct QV when met_em contains QV; otherwise rh_to_mxrat1 liquid-water branch",
                                       "var_type": "Q"},
            "source_bindings": {"module_initialize_real.F_sha256": "a4bb2497d0c70588f45da06fe9754b56597245033fec7b4bb51beba05901ce2c",
                                "qc_vert_interp_call_lines": "1884-1905", "integ_moist_lines": "6953-7145",
                                "p_dts_lines": "6750-6784", "p_dry_lines": "6696-6746",
                                "lagrange_setup_lines": "6331-6528", "wrf_registry_defaults": "Registry/Registry.EM_COMMON lines 2311-2325"},
            "source_pressure_columns": source_columns,
            "validation": {"selected_target_count": len(targets),
                           "mu0_vs_wrfinput_mu_plus_mub_max_abs_pa": float(np.max(np.abs(mu_residuals))),
                           "initial_qcloud_vs_reconstructed_vert_interp_max_abs": float(np.max(np.abs(qcloud_residuals))),
                           "initial_qcloud_vs_reconstructed_vert_interp_mean_abs": float(np.mean(np.abs(qcloud_residuals))),
                           "worst_qcloud_target_level": max(worst_qcloud, key=lambda row: abs(row["difference"])),
                           "qcloud_comparison_note": "Same met_em QC is vertically replayed at each selected target, then compared with initialized wrfinput QCLOUD; this readback check does not prove executable identity."},
            "composed_qc_vertical_influence": composed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--met-em", type=Path, required=True)
    parser.add_argument("--wrfinput", type=Path, required=True)
    parser.add_argument("--horizontal-rows", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    result = analyze(args.met_em, args.wrfinput, args.horizontal_rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
