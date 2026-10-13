#!/usr/bin/env python3
"""Validate a declared PR83 Q/N/B candidate and compare paired native states."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from native_kdm6_trace import read_dump


TIME = "2026-08-16_13:00:00"
MOMENTS = {
    "QCLOUD": ("QNCLOUD", "number", "kg-1"),
    "QICE": ("QNICE", "number", "kg-1"),
    "QRAIN": ("QNRAIN", "number", "kg-1"),
    "QGRAUP": ("QIB", "volume", "m3 kg-1"),
}
PRESERVED = ("QVAPOR", "T")
PAIR_FIELDS = (
    "QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP", "T",
    "P", "PB", "PH", "PHB", "U", "V", "W", "QNCLOUD", "QNICE",
    "QNRAIN", "QIB", "XLAT", "XLONG", "XLAT_U", "XLONG_U", "XLAT_V", "XLONG_V",
)
COORDINATE_FIELDS = {
    "XLAT": (("Time", "south_north", "west_east"), "degree_north"),
    "XLONG": (("Time", "south_north", "west_east"), "degree_east"),
    "XLAT_U": (("Time", "south_north", "west_east_stag"), "degree_north"),
    "XLONG_U": (("Time", "south_north", "west_east_stag"), "degree_east"),
    "XLAT_V": (("Time", "south_north_stag", "west_east"), "degree_north"),
    "XLONG_V": (("Time", "south_north_stag", "west_east"), "degree_east"),
}
EXPECTED_UNITS = {
    "QVAPOR": "kg kg-1", "QCLOUD": "kg kg-1", "QICE": "kg kg-1",
    "QRAIN": "kg kg-1", "QSNOW": "kg kg-1", "QGRAUP": "kg kg-1",
    "QNCLOUD": "kg-1", "QNICE": "kg-1", "QNRAIN": "kg-1",
    "QIB": "m3 kg-1", "T": "K", "P": "Pa", "PB": "Pa",
    "PH": "m2 s-2", "PHB": "m2 s-2", "U": "m s-1",
    "V": "m s-1", "W": "m s-1",
}
GRID_ATTRIBUTES = (
    "DX", "DY", "MAP_PROJ", "CEN_LAT", "CEN_LON", "TRUELAT1",
    "TRUELAT2", "STAND_LON",
)
EXPECTED_POLICY_SHA256 = "dde8df58f840d2fb11579876450749964ea2a54e36a68856c92bc979f46bae2a"
EXPECTED_PR84_POLICY_SHA256 = "7f0176742d736c9dbe2be127f43eb00ed35ebda89f0b792a51220efb7d4d7e92"
PR84_POLICY_SCHEMA = "pr84_same13_native_moment_policy_v2"
PR84_QICE_PIDNI_F32 = 1570.79638671875
PR84_QICE_PIDNI_F32_HEX = "44c4597c"
PR84_QICE_LAMBDA_MIN_M1 = 9080.0
PR84_QICE_DMI = 3.0
PR84_SOURCE_INPUTS = {
    "OFF": "6ed69cbd2bdb8d128dbd7273ac8de216fe4537748a0e4ca474213ac408060730",
    "COUPLED": "dce4a2633521639a4195babc461a45427f669dc808cb7b2d99d321b153b77afb",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def values(variable: netCDF4.Variable) -> np.ndarray:
    raw = variable[:]
    if np.any(np.ma.getmaskarray(raw)):
        raise ValueError(f"{variable.name}: masked values are forbidden")
    result = np.asarray(raw)
    for attribute in ("_FillValue", "missing_value"):
        if hasattr(variable, attribute) and np.any(result == np.asarray(getattr(variable, attribute))):
            raise ValueError(f"{variable.name}: explicit {attribute} value is forbidden")
    if result.dtype.kind in "iuf" and not np.isfinite(result).all():
        raise ValueError(f"{variable.name}: non-finite values are forbidden")
    return result


def normalize_units(units: str | None) -> str | None:
    if units is None:
        return None
    compact = " ".join(units.strip().split()).lower()
    aliases = {
        "kg(-1)": "kg-1", "kg^(-1)": "kg-1", "kg**-1": "kg-1",
        "m(3) kg(-1)": "m3 kg-1", "m^3 kg^(-1)": "m3 kg-1",
        "m**3 kg**-1": "m3 kg-1", "kg kg(-1)": "kg kg-1",
        "kg kg^(-1)": "kg kg-1", "m s(-1)": "m s-1",
        "m s^(-1)": "m s-1", "m2 s(-2)": "m2 s-2",
        "m2 s^(-2)": "m2 s-2",
    }
    return aliases.get(compact, compact)


def valid_time(dataset: netCDF4.Dataset) -> str:
    if "Time" not in dataset.dimensions or len(dataset.dimensions["Time"]) != 1:
        raise ValueError("expected exactly one native time record")
    if "Times" not in dataset.variables:
        raise ValueError("native file has no Times variable")
    return b"".join(dataset.variables["Times"][0].tolist()).decode("ascii")


def require_field(dataset: netCDF4.Dataset, name: str, *, dimensions: tuple[str, ...] | None = None,
                  units: str | None = None) -> tuple[netCDF4.Variable, np.ndarray]:
    if name not in dataset.variables:
        raise ValueError(f"required native field missing: {name}")
    variable = dataset.variables[name]
    if dimensions is not None and variable.dimensions != dimensions:
        raise ValueError(f"{name}: dimensions {variable.dimensions} != {dimensions}")
    actual_units = getattr(variable, "units", None)
    if units is not None and normalize_units(actual_units) != normalize_units(units):
        raise ValueError(f"{name}: units {actual_units!r} != {units!r}")
    data = values(variable)
    return variable, data


def _record_delta(before: np.ndarray, after: np.ndarray) -> dict[str, Any]:
    if before.shape != after.shape:
        raise ValueError(f"native field shape mismatch: {before.shape} != {after.shape}")
    delta = after.astype(np.float64) - before.astype(np.float64)
    return {
        "shape": list(before.shape),
        "changed_cells": int(np.count_nonzero(before != after)),
        "max_abs_difference": float(np.abs(delta).max(initial=0.0)),
        "before_sha256_f32_le": hashlib.sha256(before.astype("<f4", copy=False).tobytes()).hexdigest(),
        "after_sha256_f32_le": hashlib.sha256(after.astype("<f4", copy=False).tobytes()).hexdigest(),
    }


def _validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("schema") == PR84_POLICY_SCHEMA:
        _validate_pr84_policy(policy)
        return
    if policy.get("schema") != "pr83_same13_native_moment_policy_v1":
        raise ValueError("unsupported PR83 moment policy schema")
    if policy.get("declared_before_experiment") is not True:
        raise ValueError("moment policy was not declared before the candidate")
    if policy.get("status") != "RESEARCH_PRIOR_NOT_OPERATIONAL_OR_SCIENCE_APPROVAL":
        raise ValueError("moment policy authority status changed")
    for name, (moment, kind, units) in MOMENTS.items():
        declaration = policy.get("species", {}).get(name)
        if not isinstance(declaration, dict) or declaration.get("target_moment") != moment:
            raise ValueError(f"policy target moment mismatch for {name}")
        if kind == "number":
            if policy["prior"]["number_units"] != units:
                raise ValueError(f"policy number units mismatch for {moment}")
        elif policy["prior"]["volume_units"] != units:
            raise ValueError(f"policy bulk-volume units mismatch for {moment}")
    if policy.get("species", {}).get("QSNOW", {}).get("target_moment") is not None:
        raise ValueError("policy must retain QSNOW as mass-only")


def _validate_pr84_policy(policy: dict[str, Any]) -> None:
    if (policy.get("policy_id") != "SAME13_KDM6_NATIVE_MOMENT_PRIOR_20261013_V2"
            or policy.get("declared_before_experiment") is not True):
        raise ValueError("unsupported or undeclared PR84 v2 policy")
    if policy.get("status") != "RESEARCH_PRIOR_NOT_OPERATIONAL_OR_SCIENCE_APPROVAL":
        raise ValueError("PR84 v2 policy authority status changed")
    if policy.get("prior", {}).get("active_domain_mode") != "FULL_NATIVE_HORIZONTAL":
        raise ValueError("PR84 v2 requires the full native horizontal domain")
    ice = policy.get("species", {}).get("QICE", {})
    if ice.get("internal_number_cap_mode") != "SOURCE_PSD_COMPATIBLE_ENTRY_GUARD":
        raise ValueError("PR84 v2 QICE cap mode mismatch")
    authorized = policy.get("preflight", {}).get("authorized_source_inputs")
    observed = {entry.get("role"): entry.get("sha256") for entry in authorized or []
                if isinstance(entry, dict)}
    if not isinstance(authorized, list) or len(authorized) != 2 or observed != PR84_SOURCE_INPUTS:
        raise ValueError("PR84 v2 authorized source input pair mismatch")
    if (policy.get("preflight", {}).get("expected_source_valid_time") != TIME
            or policy["preflight"].get(
                "expected_input_spatial_shape_bottom_top_south_north_west_east") != [39, 282, 234]):
        raise ValueError("PR84 v2 input identity mismatch")
    pidni = ice.get("source_pidni_binary32_value")
    pidni_hex = ice.get("source_pidni_binary32_hex")
    lambda_min = ice.get("lambda_min_m-1")
    if (pidni is None or pidni_hex is None or lambda_min is None
            or ice.get("shape_exponent_d") != PR84_QICE_DMI):
        raise ValueError("PR84 v2 QICE source constants are missing")
    actual_hex = f"{int(np.asarray(np.float32(pidni)).view(np.uint32)):08x}"
    if (str(pidni_hex).lower().removeprefix("0x") != actual_hex
            or actual_hex != PR84_QICE_PIDNI_F32_HEX
            or float(pidni) != PR84_QICE_PIDNI_F32
            or float(lambda_min) != PR84_QICE_LAMBDA_MIN_M1):
        raise ValueError("PR84 v2 QICE PIDNI value/hex mismatch")


def _active_slices(dataset: netCDF4.Dataset, policy: dict[str, Any]) -> tuple[slice, ...]:
    if (policy.get("schema") == PR84_POLICY_SCHEMA
            and policy["prior"].get("active_domain_mode") == "FULL_NATIVE_HORIZONTAL"):
        return (slice(None),) * 4
    if (dataset.variables["QCLOUD"].shape[-2] > 2
            and dataset.variables["QCLOUD"].shape[-1] > 2):
        return (slice(None), slice(None), slice(1, -1), slice(1, -1))
    return (slice(None),) * 4


def _float32_ceiling(bounds: np.ndarray) -> np.ndarray:
    """Least finite float32 values not below nonnegative float64 bounds."""
    bounds = np.asarray(bounds, dtype=np.float64)
    if not np.isfinite(bounds).all() or np.any(bounds < 0.0):
        raise ValueError("PR84 QICE number floor is invalid")
    with np.errstate(over="ignore", invalid="ignore"):
        rounded = bounds.astype(np.float32)
    low = rounded.astype(np.float64) < bounds
    rounded[low] = np.nextafter(rounded[low], np.float32(np.inf), dtype=np.float32)
    if not np.isfinite(rounded).all():
        raise ValueError("PR84 QICE number floor overflows float32")
    return rounded


def _mean_particle_mass_bounds(policy: dict[str, Any], mass_name: str,
                               declaration: dict[str, Any]) -> list[float]:
    if mass_name == "QICE" and policy.get("schema") == PR84_POLICY_SCHEMA:
        pidni = float(np.float32(declaration["source_pidni_binary32_value"]))
        exponent = float(declaration["shape_exponent_d"])
        lambda_min = float(declaration["lambda_min_m-1"])
        lambda_max = float(declaration["lambda_max_m-1"])
        return [pidni / lambda_max**exponent, pidni / lambda_min**exponent]
    return declaration["particle_mean_mass_bounds_kg"]


def _check_metadata(dataset: netCDF4.Dataset, policy: dict[str, Any], label: str,
                    *, require_density_fields: bool = False) -> None:
    time = valid_time(dataset)
    if time != policy["preflight"]["expected_source_valid_time"]:
        raise ValueError(f"{label}: valid time mismatch: {time}")
    if int(getattr(dataset, "MP_PHYSICS", -1)) != 37:
        raise ValueError(f"{label}: MP_PHYSICS must be 37")
    mass_dims = ("Time", "bottom_top", "south_north", "west_east")
    for name in ("QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP",
                 "QNCLOUD", "QNICE", "QNRAIN", "QIB", "T"):
        unit = EXPECTED_UNITS[name]
        require_field(dataset, name, dimensions=mass_dims, units=unit)
    for name in ("P", "PB"):
        require_field(dataset, name, dimensions=mass_dims, units=EXPECTED_UNITS[name])
    for name in ("PH", "PHB", "W"):
        require_field(dataset, name,
                      dimensions=("Time", "bottom_top_stag", "south_north", "west_east"),
                      units=EXPECTED_UNITS[name])
    require_field(dataset, "U",
                  dimensions=("Time", "bottom_top", "south_north", "west_east_stag"),
                  units=EXPECTED_UNITS["U"])
    require_field(dataset, "V",
                  dimensions=("Time", "bottom_top", "south_north_stag", "west_east"),
                  units=EXPECTED_UNITS["V"])
    for name, (dimensions, units) in COORDINATE_FIELDS.items():
        require_field(dataset, name, dimensions=dimensions, units=units)
    mass_shape = dataset.variables["QCLOUD"].shape
    expected_spatial = tuple(policy["preflight"]["expected_input_spatial_shape_bottom_top_south_north_west_east"])
    if mass_shape != (1, *expected_spatial):
        raise ValueError(f"{label}: wrong same13 native mass-grid shape: {mass_shape}")
    for name in ("QNCLOUD", "QNICE", "QNRAIN", "QIB"):
        if dataset.variables[name].shape != mass_shape:
            raise ValueError(f"{label}: {name} does not use the mass grid")
    if require_density_fields:
        for name in ("AL", "ALB"):
            require_field(dataset, name, dimensions=mass_dims, units="m3 kg-1")


def _validate_moments(dataset: netCDF4.Dataset, policy: dict[str, Any]) -> dict[str, Any]:
    report: dict[str, Any] = {
        "active_domain_mode": ("FULL_NATIVE_HORIZONTAL"
                               if policy.get("schema") == PR84_POLICY_SCHEMA
                               else "NATIVE_INTERIOR_HORIZONTAL")
    }
    active = _active_slices(dataset, policy)
    inverse_density = np.add(values(dataset.variables["AL"]).astype(np.float32),
                             values(dataset.variables["ALB"]).astype(np.float32),
                             dtype=np.float32)[active]
    dry_density = np.divide(np.float32(1.0), inverse_density, dtype=np.float32)
    if not np.isfinite(dry_density).all() or np.any(dry_density <= 0.0):
        raise ValueError("source dry density from float32 reciprocal(AL+ALB) is invalid")
    for mass_name, (moment_name, kind, _) in MOMENTS.items():
        mass = values(dataset.variables[mass_name]).astype(np.float64)[active]
        moment = values(dataset.variables[moment_name]).astype(np.float64)[active]
        if np.any(mass < 0.0) or np.any(moment < 0.0):
            raise ValueError(f"{mass_name}/{moment_name}: negative mass or moment")
        if np.any((mass == 0.0) & (moment != 0.0)):
            raise ValueError(f"{moment_name}: nonzero moment exists at exact zero mass")
        unresolved = (mass > 0.0) & (moment == 0.0)
        valid = (mass > 0.0) & (moment > 0.0)
        if np.any(unresolved):
            raise ValueError(f"{moment_name}: positive-mass support has unresolved zero moments")
        declaration = policy["species"][mass_name]
        if kind == "number":
            bounds = _mean_particle_mass_bounds(policy, mass_name, declaration)
            ratio = mass[valid] / moment[valid]
            bad = (ratio < bounds[0]) | (ratio > bounds[1])
            if np.any(bad):
                raise ValueError(f"{moment_name}: mean particle mass outside source bounds")
            rho = dry_density[valid]
            internal_number = np.multiply(moment[valid].astype(np.float32), rho, dtype=np.float32)
            if not np.isfinite(internal_number).all() or np.any(internal_number <= 0.0):
                raise ValueError(f"{moment_name}: native number underflows or is non-finite")
            if mass_name == "QICE" and policy.get("schema") == PR84_POLICY_SCHEMA:
                pidni = float(np.float32(declaration["source_pidni_binary32_value"]))
                lambda_min = float(declaration["lambda_min_m-1"])
                density_valid = dry_density[valid]
                public_min64 = mass[valid] * (lambda_min ** PR84_QICE_DMI) / pidni
                internal_min64 = density_valid.astype(np.float64) * public_min64
                internal_floor = _float32_ceiling(internal_min64)
                public_floor = _float32_ceiling(public_min64)
                while True:
                    roundtrip = np.multiply(public_floor, density_valid, dtype=np.float32)
                    needs_step = roundtrip < internal_floor
                    if not np.any(needs_step):
                        break
                    public_floor[needs_step] = np.nextafter(
                        public_floor[needs_step], np.float32(np.inf), dtype=np.float32
                    )
                    if not np.isfinite(public_floor).all():
                        raise ValueError("QNICE source-compatible floor overflows float32")
                while True:
                    predecessor = np.nextafter(
                        public_floor, np.float32(-np.inf), dtype=np.float32
                    )
                    predecessor_roundtrip = np.multiply(
                        predecessor, density_valid, dtype=np.float32
                    )
                    can_step_down = ((predecessor.astype(np.float64) >= public_min64)
                                     & (predecessor_roundtrip >= internal_floor))
                    if not np.any(can_step_down):
                        break
                    public_floor[can_step_down] = predecessor[can_step_down]
                if np.any(moment[valid].astype(np.float64) < public_min64):
                    raise ValueError("QNICE: public number is below the source PSD floor")
                if np.any(moment[valid].astype(np.float32) < public_floor):
                    raise ValueError("QNICE: public number is below the source PSD floor")
                cap_values = np.maximum(
                    np.float32(1.0e6),
                    np.multiply(public_floor, density_valid, dtype=np.float32),
                )
                cap = float(cap_values.max(initial=np.float32(0.0)))
                over_cap = internal_number > cap_values
            else:
                cap = declaration["internal_number_cap_number_m-3"]
                over_cap = internal_number.astype(np.float64) > cap
            if np.any(over_cap):
                raise ValueError(f"{moment_name}: native internal number exceeds source cap")
            physical = {
                "mean_particle_mass_bounds_kg": bounds,
                "internal_number_cap_number_m-3": cap,
                "internal_number_cap_mode": declaration.get("internal_number_cap_mode", "FIXED_SOURCE_CAP"),
                "maximum_native_internal_number_m-3": float(internal_number.max(initial=0.0)),
                "validated_cells": int(np.count_nonzero(valid)),
            }
            if mass_name == "QICE" and policy.get("schema") == PR84_POLICY_SCHEMA:
                physical["derived_cap_min_number_m-3"] = float(cap_values.min())
                physical["derived_cap_max_number_m-3"] = float(cap_values.max())
                physical["derived_cap_formula"] = (
                    "max(1e6, float32(minimal_QNICE_float32 * dry_density_float32))"
                )
            if mass_name == "QICE" and policy.get("schema") == PR84_POLICY_SCHEMA:
                physical["derived_cap_min_number_m-3"] = float(cap_values.min(initial=np.float32(0.0)))
                physical["derived_cap_max_number_m-3"] = float(cap_values.max(initial=np.float32(0.0)))
        else:
            density = mass[valid] / moment[valid]
            if np.any((density < declaration["bulk_density_min_kg_m-3"]) |
                      (density > declaration["bulk_density_max_kg_m-3"])):
                raise ValueError("QGRAUP/QIB density outside source bounds")
            physical = {
                "bulk_density_bounds_kg_m-3": [declaration["bulk_density_min_kg_m-3"],
                                                declaration["bulk_density_max_kg_m-3"]],
                "validated_cells": int(np.count_nonzero(valid)),
            }
        report[moment_name] = {
            "positive_mass_cells": int(np.count_nonzero(mass > 0.0)),
            "positive_moment_cells": int(np.count_nonzero(moment > 0.0)),
            "positive_mass_zero_moment_cells": int(np.count_nonzero(unresolved)),
            **physical,
        }
    snow = values(dataset.variables["QSNOW"]).astype(np.float64)
    report["QSNOW"] = {
        "positive_mass_cells": int(np.count_nonzero(snow > 0.0)),
        "treatment": policy["species"]["QSNOW"]["treatment"],
        "native_snow_number_moment": "NOT_DECLARED",
    }
    return report


def compare_native_initial_outputs(candidate_native: Path, off_native: Path) -> dict[str, Any]:
    """Compare two same-time native starts without assuming shared field values."""
    result: dict[str, Any] = {}
    with netCDF4.Dataset(candidate_native) as xa, netCDF4.Dataset(off_native) as xb:
        if valid_time(xa) != valid_time(xb) or valid_time(xa) != TIME:
            raise ValueError("paired native initial outputs do not share exact 13 UTC time")
        for attribute in GRID_ATTRIBUTES:
            if hasattr(xa, attribute) != hasattr(xb, attribute):
                raise ValueError(f"paired native grid metadata differs: {attribute}")
            if hasattr(xa, attribute) and getattr(xa, attribute) != getattr(xb, attribute):
                raise ValueError(f"paired native grid metadata differs: {attribute}")
        if int(getattr(xa, "MP_PHYSICS", -1)) != 37 or int(getattr(xb, "MP_PHYSICS", -1)) != 37:
            raise ValueError("paired native initial outputs must both declare MP_PHYSICS=37")
        for name in PAIR_FIELDS:
            if name not in xa.variables or name not in xb.variables:
                raise ValueError(f"paired native field missing: {name}")
            dimensions, units = (COORDINATE_FIELDS[name] if name in COORDINATE_FIELDS
                                 else (None, EXPECTED_UNITS[name]))
            avar, aval = require_field(xa, name, dimensions=dimensions, units=units)
            bvar, bval = require_field(xb, name, dimensions=dimensions, units=units)
            if avar.dimensions != bvar.dimensions or aval.shape != bval.shape:
                raise ValueError(f"paired native staggering/shape differs: {name}")
            if name in COORDINATE_FIELDS and not np.array_equal(aval, bval):
                raise ValueError(f"paired native coordinates differ: {name}")
            result[name] = _record_delta(bval, aval)
        for name, (expected_dims, expected_units) in {
            **{field: (("Time", "bottom_top", "south_north", "west_east"), EXPECTED_UNITS[field])
               for field in ("QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP",
                             "QNCLOUD", "QNICE", "QNRAIN", "QIB", "T", "P", "PB")},
            "PH": (("Time", "bottom_top_stag", "south_north", "west_east"), "m2 s-2"),
            "PHB": (("Time", "bottom_top_stag", "south_north", "west_east"), "m2 s-2"),
            "W": (("Time", "bottom_top_stag", "south_north", "west_east"), "m s-1"),
            "U": (("Time", "bottom_top", "south_north", "west_east_stag"), "m s-1"),
            "V": (("Time", "bottom_top", "south_north_stag", "west_east"), "m s-1"),
            **COORDINATE_FIELDS,
        }.items():
            for dataset, label in ((xa, "Xa"), (xb, "Xb")):
                if name not in dataset.variables:
                    continue
                require_field(dataset, name, dimensions=expected_dims, units=expected_units)
        pressure: dict[str, dict[str, float]] = {}
        for label, dataset in (("Xa", xa), ("Xb", xb)):
            physical_pressure = values(dataset.variables["P"]).astype(np.float64) + \
                values(dataset.variables["PB"]).astype(np.float64)
            if not np.isfinite(physical_pressure).all() or np.any(physical_pressure <= 0.0):
                raise ValueError(f"{label} native initial P+PB is not positive and finite")
            pressure[label] = {"min_pa": float(physical_pressure.min()),
                               "max_pa": float(physical_pressure.max())}
    return {
        "definition": "M(Xa)-M(Xb) on same-time native initial wrfout fields",
        "Xa_candidate_native_initial_wrfo": str(candidate_native),
        "Xb_off_native_initial_wrfo": str(off_native),
        "native_field_deltas": result,
        "positive_finite_physical_pressure_P_plus_PB": pressure,
        "same_carrier_grid_fields": "validated on matching native dimensions/stagger, units, grid, and time; field values may differ under M(Xa)-M(Xb)",
    }


def validate_candidate_input(source_path: Path, candidate_path: Path,
                             receipt_path: Path, policy_path: Path) -> dict[str, Any]:
    """Verify a successful same13 prior before the candidate enters WRF."""
    source_path, candidate_path = (p.resolve(strict=True) for p in
                                   (source_path, candidate_path))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    _validate_policy(policy)
    is_pr84 = policy.get("schema") == PR84_POLICY_SCHEMA
    expected_policy_hash = (EXPECTED_PR84_POLICY_SHA256 if is_pr84
                            else EXPECTED_POLICY_SHA256)
    if expected_policy_hash is None or sha256(policy_path) != expected_policy_hash:
        raise ValueError("same13 moment policy bytes differ from the frozen declaration")
    if receipt.get("schema") != "pr83_same13_native_moment_prior_receipt_v1":
        raise ValueError("candidate receipt schema is not PR83 same13")
    if receipt.get("status") != "RESEARCH_PRIOR_CREATED":
        raise ValueError("candidate receipt does not report a complete prior")
    if receipt.get("policy_id") != policy.get("policy_id"):
        raise ValueError("candidate receipt policy does not match declared policy")
    if receipt.get("policy_sha256") != sha256(policy_path):
        raise ValueError("candidate receipt policy hash mismatch")
    initializer = ROOT / "tools/initialize_native_moments.py"
    if receipt.get("initializer_sha256") != sha256(initializer):
        raise ValueError("candidate receipt initializer hash mismatch")
    expected_source = policy.get("preflight", {}).get("expected_source_input_sha256")
    if is_pr84:
        source_role = receipt.get("source_input_role")
        expected_source = PR84_SOURCE_INPUTS.get(source_role)
        if receipt.get("policy_schema") != PR84_POLICY_SCHEMA:
            raise ValueError("PR84 prior receipt does not bind the v2 policy schema")
        if expected_source is None:
            raise ValueError("PR84 prior receipt has an unauthorized source role")
    if expected_source != sha256(source_path):
        raise ValueError("source wrfinput does not match the declared same13 identity")
    if receipt.get("source_input_sha256") != sha256(source_path):
        raise ValueError("candidate receipt source hash mismatch")
    if receipt.get("output_input_sha256") != sha256(candidate_path):
        raise ValueError("candidate receipt candidate hash mismatch")
    if receipt.get("all_other_variables_unchanged") is not True:
        raise ValueError("candidate receipt does not attest unchanged nonmoment fields")

    with netCDF4.Dataset(source_path) as source, netCDF4.Dataset(candidate_path) as candidate:
        _check_metadata(source, policy, "source wrfinput", require_density_fields=True)
        _check_metadata(candidate, policy, "candidate wrfinput", require_density_fields=True)
        if valid_time(source) != valid_time(candidate):
            raise ValueError("source/candidate valid times differ")
        for attribute in GRID_ATTRIBUTES:
            present = [hasattr(dataset, attribute) for dataset in (source, candidate)]
            if len(set(present)) != 1:
                raise ValueError(f"source/candidate grid metadata presence differs: {attribute}")
            if all(present) and getattr(source, attribute) != getattr(candidate, attribute):
                raise ValueError(f"source/candidate grid metadata differs: {attribute}")
        targets = {moment for moment, _, _ in MOMENTS.values()}
        if set(source.variables) != set(candidate.variables):
            raise ValueError("candidate changed the NetCDF variable inventory")
        moment_changes: dict[str, Any] = {}
        for name in source.variables:
            before_var, after_var = source.variables[name], candidate.variables[name]
            if before_var.dimensions != after_var.dimensions:
                raise ValueError(f"candidate changed shape/staggering for {name}")
            before, after = values(before_var), values(after_var)
            if before.shape != after.shape:
                raise ValueError(f"candidate changed shape for {name}")
            if name in targets:
                moment_changes[name] = _record_delta(before, after)
            elif not np.array_equal(before, after):
                raise ValueError(f"candidate changed undeclared source field: {name}")
        for name in PRESERVED:
            if not np.array_equal(values(source.variables[name]), values(candidate.variables[name])):
                raise ValueError(f"prior changed Q/Tq carrier field: {name}")
        moment_validity = _validate_moments(candidate, policy)
    return {
        "source_wrfinput_sha256": sha256(source_path),
        "candidate_wrfinput_sha256": sha256(candidate_path),
        "moment_prior_policy_schema": policy["schema"],
        "source_input_role": receipt.get("source_input_role"),
        "time": TIME,
        "candidate_target_moment_deltas": moment_changes,
        "candidate_moment_validity": moment_validity,
        "source_candidate_nonmoment_identity": "PASS",
        "science_authority": "NONE",
        "operational_authority": "NONE",
    }


def build_report(source_path: Path, candidate_path: Path, native_path: Path,
                 receipt_path: Path, policy_path: Path, *, trace_pre: Path | None = None,
                 paired_off_native: Path | None = None,
                 paired_off_trace_pre: Path | None = None) -> dict[str, Any]:
    source_path, candidate_path, native_path = (p.resolve(strict=True) for p in
                                                (source_path, candidate_path, native_path))
    candidate_input_report = validate_candidate_input(
        source_path, candidate_path, receipt_path, policy_path
    )
    policy = json.loads(policy_path.read_text(encoding="utf-8"))

    with netCDF4.Dataset(source_path) as source, netCDF4.Dataset(candidate_path) as candidate, \
            netCDF4.Dataset(native_path) as native:
        _check_metadata(source, policy, "source wrfinput", require_density_fields=True)
        _check_metadata(candidate, policy, "candidate wrfinput", require_density_fields=True)
        _check_metadata(native, policy, "native initial wrfout")
        if valid_time(source) != valid_time(candidate) or valid_time(source) != valid_time(native):
            raise ValueError("candidate and native output valid times differ")
        for attribute in GRID_ATTRIBUTES:
            present = [hasattr(dataset, attribute) for dataset in (source, candidate, native)]
            if len(set(present)) != 1:
                raise ValueError(f"source/candidate/native grid metadata presence differs: {attribute}")
            if all(present):
                values_by_file = [getattr(dataset, attribute) for dataset in
                                  (source, candidate, native)]
                if not values_by_file[0] == values_by_file[1] == values_by_file[2]:
                    raise ValueError(f"source/candidate/native grid metadata differs: {attribute}")
        moment_changes: dict[str, Any] = {}
        targets = {moment for moment, _, _ in MOMENTS.values()}
        for name in source.variables:
            if name not in candidate.variables:
                raise ValueError(f"candidate dropped source field: {name}")
            before, after = values(source.variables[name]), values(candidate.variables[name])
            if before.shape != after.shape or source.variables[name].dimensions != candidate.variables[name].dimensions:
                raise ValueError(f"candidate changed shape/staggering for {name}")
            if name in targets:
                moment_changes[name] = _record_delta(before, after)
            elif not np.array_equal(before, after):
                raise ValueError(f"candidate changed undeclared source field: {name}")
        for name in targets:
            if name not in candidate.variables or name not in native.variables:
                raise ValueError(f"candidate/native output lacks declared moment: {name}")
            if not np.array_equal(values(candidate.variables[name]), values(native.variables[name])):
                raise ValueError(f"native initialization changed candidate moment: {name}")
        for name in (*PRESERVED, "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP",
                     *COORDINATE_FIELDS):
            if not np.array_equal(values(source.variables[name]), values(candidate.variables[name])):
                raise ValueError(f"prior changed preserved carrier/thermodynamic field: {name}")
            if not np.array_equal(values(candidate.variables[name]), values(native.variables[name])):
                raise ValueError(f"native initial wrfout changed preserved field: {name}")
        if getattr(native.variables["T"], "description", None) != \
                "perturbation potential temperature theta-t0":
            raise ValueError("native initial T lacks perturbation-potential-temperature semantics")
        physical_pressure = values(native.variables["P"]).astype(np.float64) + \
            values(native.variables["PB"]).astype(np.float64)
        if not np.isfinite(physical_pressure).all() or np.any(physical_pressure <= 0.0):
            raise ValueError("native initial physical P+PB must be positive and finite")

    trace_summary = None
    if trace_pre is not None:
        trace = read_dump(trace_pre)
        if trace["stage"] != 1 or trace["itimestep"] <= 0:
            raise ValueError("candidate trace is not a first-call pre capture")
        trace_summary = {
            "path": str(trace_pre), "sha256": trace["sha256"],
            "stage": trace["stage"], "itimestep": trace["itimestep"],
            "bounds": trace["bounds"], "active_shape_xyz": trace["active_shape_xyz"],
            "fields": {
                name: {
                    "positive": int(np.count_nonzero(trace["fields"][name] > 0.0)),
                    "zero": int(np.count_nonzero(trace["fields"][name] == 0.0)),
                    "negative": int(np.count_nonzero(trace["fields"][name] < 0.0)),
                    "nonfinite": int(np.count_nonzero(~np.isfinite(trace["fields"][name]))),
                }
                for name in ("Q", "QC", "QI", "QR", "QS", "QG", "NC", "NI", "NR", "BG")
            },
            "post_call_trace": "NOT_AVAILABLE; no pre-to-post inference made",
            "QIB_post_call": "NOT_ASSESSED; the retained trace has no post-call QIB capture",
        }
    paired = None
    if paired_off_native is not None:
        paired = compare_native_initial_outputs(native_path, paired_off_native.resolve(strict=True))
    if paired_off_trace_pre is not None:
        if trace_pre is None:
            raise ValueError("paired OFF trace requires candidate first-call pre trace")
        xa, xb = read_dump(trace_pre), read_dump(paired_off_trace_pre)
        if xa["stage"] != 1 or xb["stage"] != 1 or xa["itimestep"] != xb["itimestep"]:
            raise ValueError("paired first-call pre traces differ in stage/timestep")
        if xa["bounds"] != xb["bounds"] or xa["params"] != xb["params"]:
            raise ValueError("paired first-call pre traces differ in domain/call parameters")
        paired_trace: dict[str, Any] = {}
        for name in ("Q", "QC", "QI", "QR", "QS", "QG", "NC", "NI", "NR", "BG"):
            left, right = xa["fields"][name], xb["fields"][name]
            paired_trace[name] = _record_delta(right, left)
        if paired is None:
            paired = {}
        paired["first_call_pre_trace_deltas"] = {
            "definition": "M(Xa)-M(Xb) on same-stage/timestep KDM6 pre-call native fields",
            "field_deltas": paired_trace,
            "same_carrier_fields": "same named native Q fields, stage, timestep, bounds, and parameters; deltas are allowed and reported",
            "post_call_trace": "NOT_AVAILABLE; no pre-to-post inference made",
        }

    return {
        "schema": "pr83_moment_candidate_native_readback_v1",
        "status": "PASS_SCOPED_MOMENT_CANDIDATE_READBACK",
        "science_authority": "NONE",
        "operational_authority": "NONE",
        "time": TIME,
        "source_wrfinput_sha256": sha256(source_path),
        "candidate_wrfinput_sha256": sha256(candidate_path),
        "native_initial_wrfo_sha256": sha256(native_path),
        "moment_prior_policy_schema": policy["schema"],
        "source_input_role": candidate_input_report["source_input_role"],
        "candidate_target_moment_deltas": moment_changes,
        "candidate_moment_validity": candidate_input_report["candidate_moment_validity"],
        "preserved_Q_and_Tq_fields": ["QVAPOR", "T", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP"],
        "physical_pressure_p_plus_pb": {
            "positive_finite": True,
            "min_pa": float(physical_pressure.min()),
            "max_pa": float(physical_pressure.max()),
        },
        "candidate_first_call_pre_trace": trace_summary,
        "paired_native_comparison": paired,
        "QSNOW_treatment": policy["species"]["QSNOW"]["treatment"],
        "candidate_promoted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_wrfinput", type=Path)
    parser.add_argument("candidate_wrfinput", type=Path)
    parser.add_argument("native_initial_wrfo", type=Path)
    parser.add_argument("candidate_receipt", type=Path)
    parser.add_argument("policy", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--trace-pre", type=Path)
    parser.add_argument("--paired-off-native-wrfo", type=Path)
    parser.add_argument("--paired-off-trace-pre", type=Path)
    args = parser.parse_args()
    if args.output_json.exists() or args.output_json.is_symlink():
        parser.error(f"readback receipt path already exists: {args.output_json}")
    try:
        report = build_report(
            args.source_wrfinput, args.candidate_wrfinput, args.native_initial_wrfo,
            args.candidate_receipt, args.policy, trace_pre=args.trace_pre,
            paired_off_native=args.paired_off_native_wrfo,
            paired_off_trace_pre=args.paired_off_trace_pre,
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    with args.output_json.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "time": report["time"],
                      "report": str(args.output_json)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
