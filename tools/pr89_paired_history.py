#!/usr/bin/env python3
"""Receipt-bound same-grid OFF/COUPLED WRF history comparisons."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

_SPEC = importlib.util.spec_from_file_location(
    "pr87_native_history", Path(__file__).with_name("pr87_native_history.py"))
native = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(native)

TRACERS = (*native.WATER, *native.MOMENTS, "QIB")
STATIC_GEOMETRY = ("XLAT", "XLONG", "XLAT_U", "XLONG_U", "XLAT_V", "XLONG_V",
                   "MAPFAC_M", "MAPFAC_U", "MAPFAC_V", "MAPFAC_MX", "MAPFAC_MY",
                   "MAPFAC_UX", "MAPFAC_UY", "MAPFAC_VX", "MAPFAC_VY",
                   "SINALPHA", "COSALPHA", "ZNU", "ZNW", "C1H", "C2H", "DNW")
COMPARE_FIELDS = (*TRACERS, "MU+MUB", "P+PB", "PH+PHB", "T", "U", "V", "W")


def _field(ds: netCDF4.Dataset, name: str, record: int) -> np.ndarray:
    if name == "MU+MUB":
        return native._finite(ds, "MU", record) + native._finite(ds, "MUB", record)
    if name == "P+PB":
        return native._finite(ds, "P", record) + native._finite(ds, "PB", record)
    if name == "PH+PHB":
        return native._finite(ds, "PH", record) + native._finite(ds, "PHB", record)
    return native._finite(ds, name, record)


def _pair_geometry(off: dict[str, Any], coupled: dict[str, Any]) -> None:
    if off != coupled:
        raise ValueError(f"OFF and COUPLED mass grids differ: {off} != {coupled}")


def _horizontal_mask(shape: tuple[int, ...], ny: int, nx: int,
                     interior: bool) -> np.ndarray:
    if shape == (ny, nx):
        mask = np.ones((ny, nx), dtype=bool)
    elif shape == (ny, nx + 1):
        mask = np.ones((ny, nx + 1), dtype=bool)
    elif shape == (ny + 1, nx):
        mask = np.ones((ny + 1, nx), dtype=bool)
    else:
        raise ValueError(f"field horizontal shape {shape} does not map to the mass grid {(ny, nx)}")
    if interior:
        mask = np.zeros_like(mask)
        if shape == (ny, nx + 1):
            mask[1:-1, 1:-1] = True
        elif shape == (ny + 1, nx):
            mask[1:-1, 1:-1] = True
        else:
            mask[1:-1, 1:-1] = True
    return mask


def _stats(values: np.ndarray, mask: np.ndarray) -> dict[str, Any]:
    selected = values[..., mask]
    columns = np.sum(values, axis=0, dtype=np.float64) if values.ndim >= 3 else values
    selected_columns = columns[mask]
    count = int(selected.size)
    return {"status": "ACCOUNTED" if count else "EMPTY_SCOPE",
            "selected_cell_count": count,
            "signed_total": float(np.sum(selected, dtype=np.float64)),
            "L1": float(np.sum(np.abs(selected), dtype=np.float64)),
            "max_abs_cell": float(np.max(np.abs(selected))) if count else None,
            "max_abs_column": float(np.max(np.abs(selected_columns))) if selected_columns.size else None,
            "column_L1": float(np.sum(np.abs(selected_columns), dtype=np.float64))}


def _max_abs(values: np.ndarray, mask: np.ndarray) -> float | None:
    selected = values[..., mask]
    return float(np.max(np.abs(selected))) if selected.size else None


def _decomposition(m_off: np.ndarray, r_off: np.ndarray,
                   m_coupled: np.ndarray, r_coupled: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    delta_m, delta_r = m_coupled - m_off, r_coupled - r_off
    extensive_difference = m_coupled * r_coupled - m_off * r_off
    mean_m_delta_r = 0.5 * (m_coupled + m_off) * delta_r
    mean_r_delta_m = 0.5 * (r_coupled + r_off) * delta_m
    return extensive_difference, mean_m_delta_r, mean_r_delta_m


def _records(path: Path) -> tuple[dict[datetime, int], dict[str, Any]]:
    index, grid = native._file_index([path])
    return {when: record for when, (_, record) in index.items()}, grid


def _verify_static_geometry(off_path: Path, coupled_path: Path) -> dict[str, Any]:
    matches = {}
    dx = dy = 0.0
    with netCDF4.Dataset(off_path) as off, netCDF4.Dataset(coupled_path) as coupled:
        off.set_auto_mask(False); coupled.set_auto_mask(False)
        if (float(off.DX), float(off.DY)) != (float(coupled.DX), float(coupled.DY)):
            raise ValueError("OFF and COUPLED DX/DY attributes differ")
        dx, dy = float(off.DX), float(off.DY)
        if set(off.dimensions) != set(coupled.dimensions):
            raise ValueError("OFF and COUPLED dimension names differ")
        for name in off.dimensions:
            if len(off.dimensions[name]) != len(coupled.dimensions[name]):
                raise ValueError(f"OFF and COUPLED dimension {name} lengths differ")
        for name in STATIC_GEOMETRY:
            if name not in off.variables or name not in coupled.variables:
                continue
            a = np.asarray(off.variables[name][:])
            b = np.asarray(coupled.variables[name][:])
            same = a.shape == b.shape and np.array_equal(a, b, equal_nan=True)
            matches[name] = {"shape": list(a.shape), "exact_match": bool(same)}
            if not same:
                raise ValueError(f"OFF and COUPLED static grid field {name} differs")
    return {"dx_m": dx, "dy_m": dy,
            "dimensions_exact_match": True, "static_fields": matches}


def _load_snapshot(path: Path, indices: dict[datetime, int], when: datetime,
                   grid: dict[str, Any], gravity: float) -> dict[str, np.ndarray]:
    record = indices[when]
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_mask(False)
        values = {name: _field(ds, name, record) for name in COMPARE_FIELDS}
        mass, _ = native._dry_mass(ds, record, gravity, grid["dx"], grid["dy"])
        values["DRY_MASS"] = mass
    for name, value in values.items():
        if not np.isfinite(value).all():
            raise ValueError(f"{name} contains nonfinite values")
    return values


def _face_differences(snapshot: dict[str, np.ndarray], dx: float,
                      dy: float) -> dict[str, np.ndarray]:
    return {"U_xface_difference_per_dx": np.diff(snapshot["U"], axis=-1) / dx,
            "V_yface_difference_per_dy": np.diff(snapshot["V"], axis=-2) / dy}


def _mask_for(value: np.ndarray, grid: dict[str, Any], interior: bool) -> np.ndarray:
    return _horizontal_mask(tuple(value.shape[-2:]), *grid["shape"], interior)


def _support_mask(value: np.ndarray, grid: dict[str, Any], support: np.ndarray) -> np.ndarray:
    ny, nx = grid["shape"]
    shape = tuple(value.shape[-2:])
    if shape == (ny, nx):
        return support
    if shape == (ny, nx + 1):
        faces = np.zeros((ny, nx + 1), dtype=bool)
        faces[:, 0], faces[:, -1] = support[:, 0], support[:, -1]
        faces[:, 1:-1] = support[:, :-1] | support[:, 1:]
        return faces
    if shape == (ny + 1, nx):
        faces = np.zeros((ny + 1, nx), dtype=bool)
        faces[0, :], faces[-1, :] = support[0, :], support[-1, :]
        faces[1:-1, :] = support[:-1, :] | support[1:, :]
        return faces
    raise ValueError(f"field horizontal shape {shape} does not map to the T0 support mask")


def _scopes(value: np.ndarray, grid: dict[str, Any], support: np.ndarray) -> dict[str, np.ndarray]:
    return {"same_fixed_whole_native_grid": _mask_for(value, grid, False),
            "same_fixed_interior_boundary_ring_excluded": _mask_for(value, grid, True),
            "initial_native_analysis_water_support": _support_mask(value, grid, support)}


def _compare_field(off: np.ndarray, coupled: np.ndarray, grid: dict[str, Any],
                   support: np.ndarray) -> dict[str, Any]:
    if off.shape != coupled.shape:
        raise ValueError(f"OFF and COUPLED field shapes differ: {off.shape} != {coupled.shape}")
    delta = coupled - off
    scopes = {}
    for scope, mask in _scopes(delta, grid, support).items():
        scopes[scope] = _stats(delta, mask)
    return {"shape": list(delta.shape), "scopes": scopes}


def _evolution_field(off0: np.ndarray, off60: np.ndarray,
                     coupled0: np.ndarray, coupled60: np.ndarray,
                     grid: dict[str, Any], support: np.ndarray) -> dict[str, Any]:
    initial = coupled0 - off0
    endpoint = coupled60 - off60
    change = endpoint - initial
    return {"deltaX_T0_COUPLED_minus_OFF": _compare_field(off0, coupled0, grid, support),
            "deltaX_T60_COUPLED_minus_OFF": _compare_field(off60, coupled60, grid, support),
            "delta_evolution_T60_minus_T0": {
                "shape": list(change.shape), "scopes": {
                    scope: _stats(change, mask)
                    for scope, mask in _scopes(change, grid, support).items()}}}


def _carrier_rows(off0: dict[str, np.ndarray], off60: dict[str, np.ndarray],
                  coupled0: dict[str, np.ndarray], coupled60: dict[str, np.ndarray],
                  grid: dict[str, Any], support: np.ndarray) -> dict[str, Any]:
    mass0_off, mass0_coupled = off0["DRY_MASS"], coupled0["DRY_MASS"]
    mass60_off, mass60_coupled = off60["DRY_MASS"], coupled60["DRY_MASS"]
    output = {}
    for name in TRACERS:
        endpoint_ext, carrier_term, mixing_term = _decomposition(
            mass60_off, off60[name], mass60_coupled, coupled60[name])
        residual = endpoint_ext - carrier_term - mixing_term
        off_temporal, off_carrier, off_mixing = _decomposition(
            mass0_off, off0[name], mass60_off, off60[name])
        coupled_temporal, coupled_carrier, coupled_mixing = _decomposition(
            mass0_coupled, coupled0[name], mass60_coupled, coupled60[name])
        evolution = coupled_temporal - off_temporal
        evolution_carrier = coupled_carrier - off_carrier
        evolution_mixing = coupled_mixing - off_mixing
        evolution_residual = evolution - evolution_carrier - evolution_mixing
        scopes = {}
        for scope, mask in _scopes(endpoint_ext, grid, support).items():
            scopes[scope] = {"endpoint_extensive_difference": _stats(endpoint_ext, mask),
                             "mean_dry_mass_times_mixing_ratio_difference": _stats(carrier_term, mask),
                             "mean_mixing_ratio_times_dry_mass_difference": _stats(mixing_term, mask),
                             "exact_identity_residual_max_abs": _max_abs(residual, mask),
                             "temporal_extensive_change_by_arm": {
                                 "OFF": {"extensive_change": _stats(off_temporal, mask),
                                         "mean_dry_mass_times_mixing_ratio_change": _stats(off_carrier, mask),
                                         "mean_mixing_ratio_times_dry_mass_change": _stats(off_mixing, mask)},
                                 "COUPLED": {"extensive_change": _stats(coupled_temporal, mask),
                                             "mean_dry_mass_times_mixing_ratio_change": _stats(coupled_carrier, mask),
                                             "mean_mixing_ratio_times_dry_mass_change": _stats(coupled_mixing, mask)}},
                             "delta_extensive_evolution_T60_minus_T0": {
                                 "extensive_change": _stats(evolution, mask),
                                 "mean_dry_mass_times_mixing_ratio_contribution": _stats(evolution_carrier, mask),
                                 "mean_mixing_ratio_times_dry_mass_contribution": _stats(evolution_mixing, mask),
                                 "exact_identity_residual_max_abs": _max_abs(evolution_residual, mask)}}
        output[name] = {"units": "kg species / count / m3, as applicable; carrier-weighted native quantity",
                        "identity": "m_C*r_C - m_O*r_O = mean(m)*delta(r) + mean(r)*delta(m)",
                        "scopes": scopes}
    return output


def _analyze(off_path: Path, off_receipt: Path, coupled_path: Path,
             coupled_receipt: Path, constants_receipt: Path,
             endpoint_seconds: int = 60, interval_seconds: int = 60) -> dict[str, Any]:
    gravity, constants_identity = native._constants(constants_receipt)
    off_idx, off_grid = _records(off_path)
    coupled_idx, coupled_grid = _records(coupled_path)
    _pair_geometry(off_grid, coupled_grid)
    if set(off_idx) != set(coupled_idx):
        raise ValueError("OFF and COUPLED history timestamps differ")
    times = sorted(off_idx)
    off_window = native._receipt_window(off_receipt, [off_path], times, endpoint_seconds,
                                       interval_seconds, False)
    coupled_window = native._receipt_window(coupled_receipt, [coupled_path], times, endpoint_seconds,
                                            interval_seconds, False)
    if off_window["run_start_timestamp"] != coupled_window["run_start_timestamp"]:
        raise ValueError("OFF and COUPLED receipt-derived run origins differ")
    if off_window["run_completed_timestamp"] != coupled_window["run_completed_timestamp"]:
        raise ValueError("OFF and COUPLED receipt completed timestamps differ")
    expected_times = [datetime.strptime(off_window["run_start_timestamp"], "%Y-%m-%d_%H:%M:%S")]
    expected_times.append(expected_times[0] + timedelta(seconds=endpoint_seconds))
    if times != expected_times:
        raise ValueError("paired histories must contain exactly the receipt-bound elapsed T0/T60 endpoints")
    geometry_match = _verify_static_geometry(off_path, coupled_path)
    snapshots = {"T0": (_load_snapshot(off_path, off_idx, times[0], off_grid, gravity),
                         _load_snapshot(coupled_path, coupled_idx, times[0], coupled_grid, gravity)),
                 "T60": (_load_snapshot(off_path, off_idx, times[1], off_grid, gravity),
                          _load_snapshot(coupled_path, coupled_idx, times[1], coupled_grid, gravity))}
    for label, pair in snapshots.items():
        for arm_index in (0, 1):
            pair[arm_index].update(_face_differences(pair[arm_index], off_grid["dx"], off_grid["dy"]))
    water_support = np.zeros(off_grid["shape"], dtype=bool)
    for name in native.WATER:
        water_support |= np.any(snapshots["T0"][0][name] != snapshots["T0"][1][name], axis=0)
    support_digest = hashlib.sha256(np.packbits(water_support, bitorder="little").tobytes()).hexdigest()
    locations = np.argwhere(water_support)
    support_bounds = None
    if locations.size:
        support_bounds = {"south_north_min": int(locations[:, 0].min()),
                          "south_north_max": int(locations[:, 0].max()),
                          "west_east_min": int(locations[:, 1].min()),
                          "west_east_max": int(locations[:, 1].max())}
    support_info = {"definition": "horizontal union where any T0 native water mixing ratio differs exactly between COUPLED and OFF",
                    "role": "initial_native_analysis_water_support; fixed descriptive subset, not an independent observation validation mask",
                    "shape": list(water_support.shape),
                    "selected_horizontal_columns": int(np.count_nonzero(water_support)),
                    "total_horizontal_columns": int(water_support.size),
                    "selected_fraction": float(np.mean(water_support)),
                    "bbox_zero_based_inclusive": support_bounds,
                    "packed_bitmask_sha256_little_bitorder": support_digest}
    fields = {}
    variable_names = {"MU+MUB": ("MU", "MUB"), "P+PB": ("P", "PB"),
                      "PH+PHB": ("PH", "PHB")}
    with netCDF4.Dataset(off_path) as ds, netCDF4.Dataset(coupled_path) as coupled_ds:
        descriptors = {}
        for name in (*COMPARE_FIELDS, "DRY_MASS", "U_xface_difference_per_dx", "V_yface_difference_per_dy"):
            if name.endswith("_difference_per_dx") or name.endswith("_difference_per_dy"):
                source = name[0]
                axis = "x" if name.endswith("_per_dx") else "y"
                source_names = (source,)
                extra = {"difference_axis": axis,
                         "definition": "computational-grid adjacent-face finite difference divided by DX/DY; no map-factor correction"}
            elif name == "DRY_MASS":
                source_names = ("MU", "MUB", "C1H", "C2H", "DNW", "MAPFAC_MX", "MAPFAC_MY")
                extra = {"units": "kg dry air", "derived_from": "native._dry_mass and pinned gravity"}
            else:
                source_names = variable_names.get(name, (name,))
                extra = {}
            off_vars = [{"name": var_name, "dimensions_without_time": list(ds.variables[var_name].dimensions[1:]),
                         "units": str(getattr(ds.variables[var_name], "units", ""))}
                        for var_name in source_names]
            coupled_vars = [{"name": var_name,
                             "dimensions_without_time": list(coupled_ds.variables[var_name].dimensions[1:]),
                             "units": str(getattr(coupled_ds.variables[var_name], "units", ""))}
                            for var_name in source_names]
            if off_vars != coupled_vars:
                raise ValueError(f"OFF and COUPLED field descriptors differ for {name}")
            descriptors[name] = {"source_variables": list(source_names), "variables": off_vars,
                                 "exact_match_across_arms": True, **extra}
    for name in (*COMPARE_FIELDS, "DRY_MASS", "U_xface_difference_per_dx", "V_yface_difference_per_dy"):
        row = _evolution_field(snapshots["T0"][0][name], snapshots["T60"][0][name],
                               snapshots["T0"][1][name], snapshots["T60"][1][name], off_grid, water_support)
        row["descriptor"] = descriptors[name]
        fields[name] = row
    return {"schema": "pr89_paired_history_diagnostics_v1", "status": "ACCOUNTED",
            "physical_approval": False,
            "scope": "same-grid OFF versus COUPLED native history diagnostics at elapsed T0/T60; no observation fit or process closure",
            "history_inputs": {"OFF": off_window, "COUPLED": coupled_window},
            "constants": constants_identity,
            "geometry": {"mass_grid_shape_south_north_west_east": list(off_grid["shape"]),
                         "cross_arm_exact_match": geometry_match,
                         "scope_definitions": {
                             "same_fixed_whole_native_grid": "all native horizontal cells/faces in the stored domain",
                             "same_fixed_interior_boundary_ring_excluded": "index 1:-1 on each horizontal axis; descriptive subset, not asserted to equal a model consumer or observation footprint",
                             "initial_native_analysis_water_support": support_info}},
            "field_comparisons": fields,
            "endpoint_carrier_decomposition_T60": _carrier_rows(
                snapshots["T0"][0], snapshots["T60"][0], snapshots["T0"][1], snapshots["T60"][1],
                off_grid, water_support),
            "staggered_wind_note": "U/V/W are reported on their native C-grid face arrays; no mass-point remap is used for paired differences.",
            "face_derivative_diagnostics": "computational-grid adjacent U/V face finite differences divided by DX/DY are compared on mass cells; no map-factor correction, physical divergence, full momentum equation, or continuity closure is claimed",
            "reflectivity_cloud_fraction": "not observations; no observation fit computed"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("off-history", "off-receipt", "coupled-history", "coupled-receipt",
                 "constants-receipt", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    result = _analyze(args.off_history, args.off_receipt, args.coupled_history,
                      args.coupled_receipt, args.constants_receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
