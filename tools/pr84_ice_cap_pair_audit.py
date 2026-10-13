#!/usr/bin/env python3
"""Read-only paired audit of the KDM6 internal ice-mass cap at same13 stages."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import netCDF4
import numpy as np

from check_native_hybrid_geometry import finite, read_geometry, digest

CAP_KG_M3 = 500.0 * math.pi * 1.0e6 / 9080.0**3
GRAVITY = 9.81
RD = 287.0
RV = 461.6
CP = 1004.5
EXPECTED_INPUTS = {
    "off_real": "6ed69cbd2bdb8d128dbd7273ac8de216fe4537748a0e4ca474213ac408060730",
    "xa_real": "dce4a2633521639a4195babc461a45427f669dc808cb7b2d99d321b153b77afb",
    "off_init": "4bac4abe8367b1e9354c448302d1ffcd621e07d838baaa490b9cd7ae07fdc708",
    "xa_init": "519b991978f2f14b925470e3f90a5bdf5f3a5ee8e3abb8f359cec6d122a345eb",
}


def source_density(al, alb):
    """Use source REAL32 AL+ALB, then REAL32 reciprocal operation order."""
    al = finite(al, "AL").astype(np.float32)
    alb = finite(alb, "ALB").astype(np.float32)
    if al.shape != alb.shape:
        raise ValueError("AL/ALB shape mismatch")
    with np.errstate(over="raise", divide="raise", invalid="raise"):
        alt = np.add(al, alb, dtype=np.float32)
        if np.any(alt <= 0):
            raise ValueError("AL+ALB must be positive")
        density = np.reciprocal(alt, dtype=np.float32)
    return finite(density, "source dry density").astype(np.float64)


def checked_field(variable, name):
    value = variable[0]
    if np.any(np.ma.getmaskarray(value)):
        raise ValueError(f"{name}: masked/fill input")
    raw = np.asarray(value)
    for attr in ("_FillValue", "missing_value"):
        if hasattr(variable, attr) and np.any(raw == getattr(variable, attr)):
            raise ValueError(f"{name}: explicit {attr} input")
    return finite(value, name)


def validate_pair_metadata(left, right):
    if left["valid_time"] != right["valid_time"]:
        raise ValueError("paired valid times differ")
    if left["qi"].shape != right["qi"].shape:
        raise ValueError("paired mass-grid shapes differ")
    for key in ("XLAT", "XLONG"):
        if not np.array_equal(left["fields"][key], right["fields"][key]):
            raise ValueError(f"paired {key} coordinates differ")
    if left["stagger_coordinates"].keys() != right["stagger_coordinates"].keys():
        raise ValueError("paired stagger-coordinate fields differ")
    for key in left["stagger_coordinates"]:
        if not np.array_equal(left["stagger_coordinates"][key], right["stagger_coordinates"][key]):
            raise ValueError(f"paired {key} coordinates differ")
    if left["staggers"] != right["staggers"]:
        raise ValueError("paired stagger dimensions differ")


def distribution(values):
    x = finite(values, "distribution")
    return {"min": float(np.min(x)), "p10": float(np.percentile(x, 10)),
            "median": float(np.median(x)), "p90": float(np.percentile(x, 90)),
            "max": float(np.max(x))}


def carrier_weighted_excess(qi, density, dry_mass):
    qi = finite(qi, "QICE")
    density = finite(density, "dry density")
    dry_mass = finite(dry_mass, "hybrid dry mass")
    if qi.shape != density.shape or qi.shape != dry_mass.shape:
        raise ValueError("QICE, density, and native dry mass shapes differ")
    if np.any(qi < 0) or np.any(density <= 0) or np.any(dry_mass <= 0):
        raise ValueError("invalid QICE/density/dry-mass values")
    excess_mix = np.maximum(qi - CAP_KG_M3 / density, 0.0)
    return float(np.sum(excess_mix * dry_mass, dtype=np.float64))


def cap_violation_mask(qi, density):
    qi = finite(qi, "QICE")
    density = finite(density, "dry density")
    if qi.shape != density.shape:
        raise ValueError("QICE and dry density shapes differ")
    if np.any(qi < 0) or np.any(density <= 0):
        raise ValueError("invalid QICE/dry-density values")
    return qi * density > CAP_KG_M3


def interior_mask(shape):
    if len(shape) != 3 or shape[0] < 1 or shape[1] < 3 or shape[2] < 3:
        raise ValueError("interior mask requires a 3-D grid with horizontal interior")
    active = np.zeros(shape, dtype=bool)
    active[:, 1:-1, 1:-1] = True
    return active


def eos_density(pressure, temperature, qv):
    """Dry carrier density from total pressure and dry-air mixing ratio."""
    return pressure / (RD * temperature * (1.0 + qv / (RD / RV)))


def eos_sensitivity_case(qi, rho, temperature, height, latitude, longitude, interior, dry_mass):
    violation = cap_violation_mask(qi, rho)
    excess_concentration = np.maximum(qi * rho - CAP_KG_M3, 0.0)
    return {
        "density_kg_m3": distribution(rho),
        "exceedances_full": int(np.count_nonzero(violation)),
        "exceedances_interior": int(np.count_nonzero(violation & interior)),
        "temperature_k_at_exceedances": distribution(temperature[violation]) if np.any(violation) else None,
        "height_m_at_exceedances": distribution(height[violation]) if np.any(violation) else None,
        "latitude_at_exceedances": distribution(latitude[np.any(violation, axis=0)]) if np.any(violation) else None,
        "longitude_at_exceedances": distribution(longitude[np.any(violation, axis=0)]) if np.any(violation) else None,
        "integrated_excess_kg_using_native_hybrid_dry_mass": float(np.sum(excess_concentration * dry_mass / rho, dtype=np.float64)),
        "dry_carrier_weighted_excess_kg": carrier_weighted_excess(qi, rho, dry_mass),
        "violation": violation, "rho": rho, "temperature": temperature, "height": height,
        "excess_concentration": excess_concentration,
    }


def summarize_stage(ds, path, gravity=GRAVITY):
    before = digest(path)
    fields = {}
    for name in ("QICE", "P", "PB", "T", "PH", "PHB", "XLAT", "XLONG"):
        if name not in ds.variables:
            raise ValueError(f"{name}: required field unavailable")
        fields[name] = checked_field(ds[name], name)
    qi = fields["QICE"]
    if qi.ndim != 3 or qi.shape[0] != len(ds.dimensions["bottom_top"]):
        raise ValueError("QICE must use the native mass grid")
    if np.any(qi < 0):
        raise ValueError("QICE contains negative mass")
    if fields["P"].shape != qi.shape or fields["PB"].shape != qi.shape or fields["T"].shape != qi.shape:
        raise ValueError("mass-grid thermodynamic field shape mismatch")
    if fields["PH"].shape[0] != qi.shape[0] + 1 or fields["PH"].shape[1:] != qi.shape[1:]:
        raise ValueError("PH/PHB stagger shape mismatch")
    for key in ("XLAT", "XLONG"):
        if fields[key].shape != qi.shape[1:]:
            raise ValueError(f"{key} shape mismatch")

    expected_dims = {
        "QICE": ("Time", "bottom_top", "south_north", "west_east"),
        "P": ("Time", "bottom_top", "south_north", "west_east"),
        "PB": ("Time", "bottom_top", "south_north", "west_east"),
        "T": ("Time", "bottom_top", "south_north", "west_east"),
        "PH": ("Time", "bottom_top_stag", "south_north", "west_east"),
        "PHB": ("Time", "bottom_top_stag", "south_north", "west_east"),
        "XLAT": ("Time", "south_north", "west_east"),
        "XLONG": ("Time", "south_north", "west_east"),
        "QVAPOR": ("Time", "bottom_top", "south_north", "west_east"),
    }
    expected_units = {
        "QICE": "kg kg-1", "P": "Pa", "PB": "Pa", "T": "K",
        "PH": "m2 s-2", "PHB": "m2 s-2", "XLAT": "degree_north",
        "XLONG": "degree_east", "QVAPOR": "kg kg-1",
    }
    for name, dimensions in expected_dims.items():
        if name not in ds.variables or ds[name].dimensions != dimensions:
            raise ValueError(f"{name}: expected native dimensions {dimensions}")
        if getattr(ds[name], "units", "").strip() != expected_units[name]:
            raise ValueError(f"{name}: expected units {expected_units[name]}")
    for name in ("XLAT_U", "XLONG_U", "XLAT_V", "XLONG_V"):
        if name in ds.variables:
            dimensions = ("Time", "south_north", "west_east_stag") if name.endswith("_U") else ("Time", "south_north_stag", "west_east")
            if ds[name].dimensions != dimensions:
                raise ValueError(f"{name}: stagger dimensions mismatch")
    if len(ds.dimensions["Time"]) != 1 or "Times" not in ds.variables:
        raise ValueError("exactly one time record and Times coordinate required")
    qv = checked_field(ds["QVAPOR"], "QVAPOR") if "QVAPOR" in ds.variables else None
    if qv is None or qv.shape != qi.shape or np.any(qv < 0):
        raise ValueError("valid QVAPOR required for thermodynamic temperature")
    use_theta_m = int(getattr(ds, "USE_THETA_M", -1))
    if use_theta_m not in (0, 1):
        raise ValueError("USE_THETA_M must be explicitly 0 or 1")
    stored_theta = fields["T"] + 300.0
    pressure = fields["P"] + fields["PB"]
    if np.any(pressure <= 0) or np.any(stored_theta <= 0):
        raise ValueError("invalid pressure or potential temperature")
    exner = (pressure / 100000.0) ** (RD / CP)
    temperature_dry_theta = stored_theta * exner
    temperature_moist_theta = stored_theta / (1.0 + (RV / RD) * qv) * exner

    source_available = "AL" in ds.variables and "ALB" in ds.variables
    if source_available:
        if ds["AL"].dimensions != ds["QICE"].dimensions or ds["ALB"].dimensions != ds["QICE"].dimensions:
            raise ValueError("AL/ALB dimensions do not match QICE")
        if any(getattr(ds[name], "units", "").strip() != "m3 kg-1" for name in ("AL", "ALB")):
            raise ValueError("AL/ALB units do not match source dry-density contract")
        rho = source_density(checked_field(ds["AL"], "AL"), checked_field(ds["ALB"], "ALB"))
        density_basis = "WRF source REAL32 reciprocal(AL+ALB)"
    else:
        rho = eos_density(pressure, temperature_dry_theta, qv)
        density_basis = "EOS dry-theta sensitivity only; source AL+ALB unavailable"
    if rho.shape != qi.shape or np.any(rho <= 0):
        raise ValueError("dry density shape/value mismatch")

    # Reuse the pinned native-hybrid checker for carrier mass; this is not rho*dz.
    _, geom = read_geometry(ds, gravity)
    dry_mass = geom["dry_mass_kg"]
    if dry_mass.shape != qi.shape:
        raise ValueError("hybrid dry mass does not align with QICE")
    interior = interior_mask(qi.shape)
    geopotential = fields["PH"] + fields["PHB"]
    height = 0.5 * (geopotential[:-1] + geopotential[1:]) / gravity
    eos_cases = {
        "stored_T_as_dry_theta": eos_sensitivity_case(
            qi, eos_density(pressure, temperature_dry_theta, qv), temperature_dry_theta,
            height, fields["XLAT"], fields["XLONG"], interior, dry_mass),
        "stored_T_as_moist_theta": eos_sensitivity_case(
            qi, eos_density(pressure, temperature_moist_theta, qv), temperature_moist_theta,
            height, fields["XLAT"], fields["XLONG"], interior, dry_mass),
    }
    eos_validation = None
    if source_available:
        eos_validation = {}
        for key, case in eos_cases.items():
            relative = np.abs(case["rho"] - rho) / rho
            eos_validation[key] = {
                "median_absolute_relative_density_error": float(np.median(relative)),
                "maximum_absolute_relative_density_error": float(np.max(relative)),
            }
    actual_violation = cap_violation_mask(qi, rho) if source_available else None
    actual_excess = np.maximum(qi * rho - CAP_KG_M3, 0.0) if source_available else None
    temperature = temperature_dry_theta
    violation = actual_violation
    stagger_coordinates = {
        name: checked_field(ds[name], name)
        for name in ("XLAT_U", "XLONG_U", "XLAT_V", "XLONG_V")
        if name in ds.variables
    }
    stage = {
        "path": str(path.resolve()), "sha256": before,
        "valid_time": b"".join(np.asarray(ds["Times"][0]).tolist()).decode("ascii").strip(),
        "shape_zyx": list(qi.shape), "density_basis": density_basis,
        "source_density_available": source_available,
        "use_theta_m": use_theta_m,
        "qi_positive_full": int(np.count_nonzero(qi > 0)),
        "qi_positive_interior": int(np.count_nonzero((qi > 0) & interior)),
        "cap_classification_assessed": source_available,
        "violations_full": int(np.count_nonzero(violation)) if source_available else None,
        "violations_interior": int(np.count_nonzero(violation & interior)) if source_available else None,
        "qi_sum_mixing_ratio_cells": float(np.sum(qi, dtype=np.float64)),
        "qi_positive_mass_density_kg_m3": float(np.sum(qi * rho, dtype=np.float64)),
        "dry_density_kg_m3": distribution(rho) if source_available else None,
        "eos_validation_against_source_density": eos_validation,
        "qi_mass_concentration_kg_m3": distribution(qi * rho) if source_available else None,
        "excess_concentration_kg_m3": distribution(actual_excess[violation]) if source_available and np.any(violation) else None,
        "temperature_k_at_violations": distribution(temperature[violation]) if source_available and np.any(violation) else None,
        "height_m_at_violations": distribution(height[violation]) if source_available and np.any(violation) else None,
        "latitude_at_violations": distribution(fields["XLAT"][np.any(violation, axis=0)]) if source_available and np.any(violation) else None,
        "longitude_at_violations": distribution(fields["XLONG"][np.any(violation, axis=0)]) if source_available and np.any(violation) else None,
        "integrated_excess_kg": float(np.sum(actual_excess * dry_mass / rho, dtype=np.float64)) if source_available else None,
        "dry_carrier_weighted_excess_kg": carrier_weighted_excess(qi, rho, dry_mass) if source_available else None,
        "eos_density_sensitivity": {key: {name: value for name, value in case.items() if name not in ("violation", "rho", "temperature", "height", "excess_concentration")} for key, case in eos_cases.items()},
        "fields": fields, "qi": qi, "rho": rho, "violation": violation,
        "interior": interior, "height": height, "temperature": temperature,
        "eos_cases": eos_cases,
        "dry_mass": dry_mass, "coordinates": (fields["XLAT"], fields["XLONG"]),
        "staggers": {key: len(ds.dimensions[key]) for key in ("bottom_top_stag", "west_east_stag", "south_north_stag")},
        "stagger_coordinates": stagger_coordinates,
    }
    if digest(path) != before:
        raise ValueError("input changed during read")
    return stage


def pair_report(left, right, left_name, right_name):
    if left["violation"] is None or right["violation"] is None:
        raise ValueError("actual cap pairing requires source AL+ALB density on both sides")
    validate_pair_metadata(left, right)
    common = left["violation"] & right["violation"]
    new = right["violation"] & ~left["violation"]
    resolved = left["violation"] & ~right["violation"]
    active = left["interior"]
    qi_delta = right["qi"] - left["qi"]
    rho_delta = right["rho"] - left["rho"]
    right_excess = np.maximum(right["qi"] * right["rho"] - CAP_KG_M3, 0.0)
    left_excess = np.maximum(left["qi"] * left["rho"] - CAP_KG_M3, 0.0)
    return {
        "left": left_name, "right": right_name,
        "common_full": int(np.count_nonzero(common)),
        "new_in_right_full": int(np.count_nonzero(new)),
        "resolved_from_left_full": int(np.count_nonzero(resolved)),
        "common_interior": int(np.count_nonzero(common & active)),
        "new_in_right_interior": int(np.count_nonzero(new & active)),
        "resolved_from_left_interior": int(np.count_nonzero(resolved & active)),
        "integrated_candidate_only_excess_kg": float(np.sum(right_excess[new] * right["dry_mass"][new] / right["rho"][new], dtype=np.float64)),
        "dry_carrier_weighted_candidate_only_excess_kg": float(np.sum(np.maximum(right["qi"][new] - CAP_KG_M3 / right["rho"][new], 0.0) * right["dry_mass"][new], dtype=np.float64)),
        "integrated_resolved_excess_kg": float(np.sum(left_excess[resolved] * left["dry_mass"][resolved] / left["rho"][resolved], dtype=np.float64)),
        "dry_carrier_weighted_resolved_excess_kg": float(np.sum(np.maximum(left["qi"][resolved] - CAP_KG_M3 / left["rho"][resolved], 0.0) * left["dry_mass"][resolved], dtype=np.float64)),
        "qi_right_minus_left": {
            "nonzero_cells": int(np.count_nonzero(qi_delta)),
            "sum": float(np.sum(qi_delta, dtype=np.float64)),
            "min": float(np.min(qi_delta)), "max": float(np.max(qi_delta)),
            "max_abs": float(np.max(np.abs(qi_delta)))},
        "density_right_minus_left": {
            "nonzero_cells": int(np.count_nonzero(rho_delta)),
            "sum": float(np.sum(rho_delta, dtype=np.float64)),
            "min": float(np.min(rho_delta)), "max": float(np.max(rho_delta)),
            "max_abs": float(np.max(np.abs(rho_delta)))},
        "delta_integrated_excess_kg": right["integrated_excess_kg"] - left["integrated_excess_kg"],
        "delta_dry_air_weighted_excess_kg": right["dry_carrier_weighted_excess_kg"] - left["dry_carrier_weighted_excess_kg"],
        "temperature_change_at_any_changed_qi": distribution((right["temperature"] - left["temperature"])[right["qi"] != left["qi"]]) if np.any(right["qi"] != left["qi"]) else None,
        "height_change_at_any_changed_qi": distribution((right["height"] - left["height"])[right["qi"] != left["qi"]]) if np.any(right["qi"] != left["qi"]) else None,
    }


def eos_pair_sensitivity(left, right, case_name):
    a, b = left["eos_cases"][case_name], right["eos_cases"][case_name]
    common = a["violation"] & b["violation"]
    new = b["violation"] & ~a["violation"]
    resolved = a["violation"] & ~b["violation"]
    qi_delta = right["qi"] - left["qi"]
    rho_delta = b["rho"] - a["rho"]
    changed_qi = qi_delta != 0
    return {
        "density_interpretation": case_name,
        "actual_post_output_cap_classification_assessed": False,
        "common_exceedances_full": int(np.count_nonzero(common)),
        "new_in_Xa_full": int(np.count_nonzero(new)),
        "resolved_from_OFF_full": int(np.count_nonzero(resolved)),
        "common_exceedances_interior": int(np.count_nonzero(common & left["interior"])),
        "new_in_Xa_interior": int(np.count_nonzero(new & left["interior"])),
        "resolved_from_OFF_interior": int(np.count_nonzero(resolved & left["interior"])),
        "candidate_only_integrated_excess_kg_using_hybrid_dry_mass": float(np.sum(b["excess_concentration"][new] * right["dry_mass"][new] / b["rho"][new], dtype=np.float64)),
        "resolved_integrated_excess_kg_using_hybrid_dry_mass": float(np.sum(a["excess_concentration"][resolved] * left["dry_mass"][resolved] / a["rho"][resolved], dtype=np.float64)),
        "candidate_only_dry_carrier_weighted_excess_kg": float(np.sum(np.maximum(right["qi"][new] - CAP_KG_M3 / b["rho"][new], 0.0) * right["dry_mass"][new], dtype=np.float64)),
        "resolved_dry_carrier_weighted_excess_kg": float(np.sum(np.maximum(left["qi"][resolved] - CAP_KG_M3 / a["rho"][resolved], 0.0) * left["dry_mass"][resolved], dtype=np.float64)),
        "qi_Xa_minus_OFF": {
            "nonzero_cells": int(np.count_nonzero(changed_qi)),
            "sum": float(np.sum(qi_delta, dtype=np.float64)),
            "min": float(np.min(qi_delta)), "max": float(np.max(qi_delta)),
            "max_abs": float(np.max(np.abs(qi_delta)))},
        "eos_density_Xa_minus_OFF": {
            "nonzero_cells": int(np.count_nonzero(rho_delta)),
            "sum": float(np.sum(rho_delta, dtype=np.float64)),
            "min": float(np.min(rho_delta)), "max": float(np.max(rho_delta)),
            "max_abs": float(np.max(np.abs(rho_delta)))},
        "temperature_change_at_changed_qi": distribution((b["temperature"] - a["temperature"])[changed_qi]) if np.any(changed_qi) else None,
        "height_change_at_changed_qi": distribution((right["height"] - left["height"])[changed_qi]) if np.any(changed_qi) else None,
        "delta_integrated_excess_kg_using_hybrid_dry_mass": b["integrated_excess_kg_using_native_hybrid_dry_mass"] - a["integrated_excess_kg_using_native_hybrid_dry_mass"],
        "delta_dry_carrier_weighted_excess_kg": b["dry_carrier_weighted_excess_kg"] - a["dry_carrier_weighted_excess_kg"],
    }


def inspect(path):
    with netCDF4.Dataset(path, "r") as ds:
        return summarize_stage(ds, path)


def full_map(stages, path):
    arrays = {}
    for label, stage in stages.items():
        arrays[f"{label}_interior"] = stage["interior"].astype(np.uint8)
        arrays[f"{label}_qi"] = stage["qi"]
        arrays[f"{label}_temperature_k"] = stage["temperature"]
        arrays[f"{label}_height_m"] = stage["height"]
        arrays[f"{label}_latitude"] = stage["fields"]["XLAT"]
        arrays[f"{label}_longitude"] = stage["fields"]["XLONG"]
        if stage["violation"] is not None:
            arrays[f"{label}_actual_violation"] = stage["violation"].astype(np.uint8)
            arrays[f"{label}_source_rho"] = stage["rho"]
            arrays[f"{label}_source_excess_kg_m3"] = np.maximum(stage["qi"] * stage["rho"] - CAP_KG_M3, 0.0)
        else:
            for case_name, case in stage["eos_cases"].items():
                arrays[f"{label}_{case_name}_sensitivity_exceedance"] = case["violation"].astype(np.uint8)
                arrays[f"{label}_{case_name}_eos_rho"] = case["rho"]
                arrays[f"{label}_{case_name}_eos_excess_kg_m3"] = case["excess_concentration"]
    np.savez_compressed(path, **arrays)
    return {"path": str(Path(path).resolve()), "sha256": digest(Path(path)),
            "format": "compressed NPZ; mass fields WRF [k,j,i], coordinates [j,i]"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off-real", type=Path, required=True)
    parser.add_argument("--xa-real", type=Path, required=True)
    parser.add_argument("--off-init", type=Path, required=True)
    parser.add_argument("--xa-init", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--full-map", type=Path, required=True)
    args = parser.parse_args()
    input_paths = [args.off_real, args.xa_real, args.off_init, args.xa_init]
    hashes_before = [digest(p) for p in input_paths]
    for key, observed in zip(EXPECTED_INPUTS, hashes_before):
        if observed != EXPECTED_INPUTS[key]:
            raise ValueError(f"{key}: SHA-256 does not match the PR83-bound artifact")
    stages = {key: inspect(path) for key, path in zip(("off_real", "xa_real", "off_init", "xa_init"), input_paths)}
    report = {
        "schema": "pr84_ice_cap_pair_audit_v1", "artifact_class": "READ_ONLY_RESEARCH_DIAGNOSTIC",
        "threshold_kg_m3": CAP_KG_M3, "formula": "500*pi*1e6/9080**3",
        "gravity_assumption_m_s2": GRAVITY,
        "binding": {
            "control_record": "docs/evidence/pr83_same13_off_control_20261013/pr83_same13_off_control_record.json",
            "control_record_sha256": digest(Path("docs/evidence/pr83_same13_off_control_20261013/pr83_same13_off_control_record.json")),
            "expected_artifact_sha256": EXPECTED_INPUTS},
        "temperature_convention_evidence": {
            "wrf_source": "Registry/Registry.EM_COMMON maps NetCDF T to th_phy_m_t0 (perturbation dry potential temperature theta-T0), and internal t to NetCDF THM; THM is option-dependent.",
            "registry_sha256": "b01855ed80569be04bbd99e43ea1672a60e35590db00145c839b8f74cfd9b07f",
            "wrf_density_source_sha256": "27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c",
            "wrf_start_source_sha256": "6be17d3a4252065cf972dcf59bf3510cd29be35f898694e38187aa525cf27ac9",
            "use_theta_m": 1,
            "real_input_density_crosscheck": "Both real inputs show the dry-theta EOS density agreeing with source REAL32 reciprocal(AL+ALB) to max relative error below 3.4e-7; the alternate moist-theta interpretation has about 3.65e-2 maximum relative error.",
            "stored_output_interpretation": "Source/registry supports T as dry theta, but no output AL/ALB carrier exists to classify post-output cap from the actual carrier. Both EOS sensitivities are retained."},
        "stages": {key: {k: v for k, v in value.items() if k not in ("fields", "qi", "rho", "violation", "interior", "height", "temperature", "dry_mass", "coordinates", "staggers", "stagger_coordinates", "eos_cases")} for key, value in stages.items()},
        "pairs": [pair_report(stages["off_real"], stages["xa_real"], "OFF real MAINT", "Xa coupled real")],
        "initial_output_eos_sensitivity_pairs": [
            eos_pair_sensitivity(stages["off_init"], stages["xa_init"], "stored_T_as_dry_theta"),
            eos_pair_sensitivity(stages["off_init"], stages["xa_init"], "stored_T_as_moist_theta")],
        "limitations": ["Initial output AL/ALB is unavailable; post-output actual carrier density and actual cap classification are NOT ASSESSED. The two EOS reconstructions are sensitivity diagnostics only; hybrid dry mass uses check_native_hybrid_geometry.",
                        "No model execution, compilation, promotion, or mutation was performed."],
    }
    report["full_map"] = full_map(stages, args.full_map)
    hashes_after = [digest(p) for p in input_paths]
    if hashes_before != hashes_after:
        raise ValueError("one or more source/product inputs changed during audit")
    report["input_hashes_before_after_identical"] = True
    report["input_hashes_before_after"] = {
        key: {"before": before, "after": after}
        for key, before, after in zip(EXPECTED_INPUTS, hashes_before, hashes_after)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"threshold_kg_m3": CAP_KG_M3,
                      "real_stage_counts": {k: {"full": stages[k]["violations_full"], "interior": stages[k]["violations_interior"]} for k in ("off_real", "xa_real")},
                      "initial_output_eos_sensitivity": report["initial_output_eos_sensitivity_pairs"],
                      "pairs": report["pairs"], "report": str(args.report), "full_map": report["full_map"]}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
