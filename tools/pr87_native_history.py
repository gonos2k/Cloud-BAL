#!/usr/bin/env python3
"""Receipt-bound endpoint inventory and native-state summaries from WRF history."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

EXPECTED_PROFILE_SHA256 = "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4"
EXPECTED_CONSTANTS_MOD_SHA256 = "262c94bfd198c60701a4fdceb8e85f30ae40c4a167fc5918cc7e73530d8bbe65"
EXPECTED_CONSTANTS_RECEIPT_SHA256 = "7b6cc54597b1d67c35ec112decab192cae3d1d5035ec03f5fb418a081df38670"
EXPECTED_GRAVITY_M_S2 = 9.81000041961669922
WATER = {"QVAPOR": "kg kg-1", "QCLOUD": "kg kg-1", "QICE": "kg kg-1",
         "QRAIN": "kg kg-1", "QSNOW": "kg kg-1", "QGRAUP": "kg kg-1"}
MOMENTS = {"QNCCN": "count kg-1 dry air", "QNCLOUD": "count kg-1 dry air",
           "QNICE": "count kg-1 dry air", "QNRAIN": "count kg-1 dry air"}
STATE = ("P", "PB", "PH", "PHB", "T", "U", "V", "W")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def _constants(receipt_path: Path) -> tuple[float, dict[str, Any]]:
    if _sha(receipt_path) != EXPECTED_CONSTANTS_RECEIPT_SHA256:
        raise ValueError("constants receipt hash does not match the pinned gravity probe")
    r = _load_json(receipt_path)
    profile = Path(r.get("profile", ""))
    module = Path(r.get("module_interface", ""))
    if r.get("returncode") != 0 or r.get("profile_sha256") != EXPECTED_PROFILE_SHA256 or \
            r.get("module_interface_sha256") != EXPECTED_CONSTANTS_MOD_SHA256:
        raise ValueError("constants receipt is not from the pinned Intel profile/module interface")
    if not profile.is_file() or _sha(profile) != EXPECTED_PROFILE_SHA256:
        raise ValueError("pinned Intel profile path/hash does not verify")
    if not module.is_file() or _sha(module) != EXPECTED_CONSTANTS_MOD_SHA256:
        raise ValueError("pinned module_model_constants.mod path/hash does not verify")
    constants = r.get("constants_real32_promoted_to_real64", {})
    try:
        gravity = float(constants["g"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("constants receipt lacks promoted REAL32 gravity g") from exc
    if not np.isfinite(gravity) or gravity != EXPECTED_GRAVITY_M_S2:
        raise ValueError("constants receipt gravity differs from the pinned promoted REAL32 value")
    if not _valid_hash(r.get("source_sha256")) or not _valid_hash(r.get("executable_sha256")):
        raise ValueError("constants probe source/executable hashes are missing")
    return gravity, {"path": str(receipt_path), "sha256": _sha(receipt_path),
                     "profile_sha256": r["profile_sha256"],
                     "module_interface_sha256": r["module_interface_sha256"],
                     "probe_source_sha256": r["source_sha256"],
                     "probe_executable_sha256": r["executable_sha256"], "g_m_s2": gravity}


def _receipt_history_hashes(receipt: dict[str, Any]) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for key in ("generated_files", "compressed_outputs", "history_files", "history_outputs"):
        for row in receipt.get(key, []):
            if not isinstance(row, dict):
                continue
            name = Path(row.get("path", row.get("compressed_path", ""))).name
            digest = row.get("sha256", row.get("expanded_sha256"))
            if name and _valid_hash(digest):
                bindings[name] = digest
    return bindings


def _receipt_window(receipt_path: Path, history_paths: list[Path], observed: list[datetime],
                    endpoint_seconds: int, interval_seconds: int, allow_incomplete: bool) -> dict[str, Any]:
    r = _load_json(receipt_path)
    status = r.get("status")
    complete = status == "COMPLETE" and r.get("returncode") == 0
    incomplete = status == "INCOMPLETE" and allow_incomplete
    if not complete and not incomplete:
        raise ValueError("run receipt must be COMPLETE with returncode 0, or use explicit incomplete-window mode")
    if len(observed) < 2:
        raise ValueError("history must include elapsed 0 and at least one completed later timestamp")
    expected_text = r.get("expected_model_timestamps", [])
    if len(expected_text) < 2:
        raise ValueError("run receipt lacks expected model timestamps to verify the history origin")
    expected = [datetime.strptime(value, "%Y-%m-%d_%H:%M:%S") for value in expected_text]
    step_seconds = int((expected[1] - expected[0]).total_seconds())
    if step_seconds <= 0 or any((b - a).total_seconds() != step_seconds
                                for a, b in zip(expected, expected[1:])):
        raise ValueError("receipt expected model timestamps must be a strictly increasing uniform step schedule")
    run_start = expected[0] - timedelta(seconds=step_seconds)
    if observed[0] != run_start:
        raise ValueError("history origin does not match the receipt-derived model start")
    elapsed = [(t - run_start).total_seconds() for t in observed]
    if elapsed[0] != 0 or any(x % interval_seconds for x in elapsed):
        raise ValueError("history timestamps must start at 0 and follow the declared output interval")
    if any(b - a != interval_seconds for a, b in zip(elapsed, elapsed[1:])):
        raise ValueError("history timestamps are not a contiguous output window")
    if interval_seconds % step_seconds:
        raise ValueError("history output interval must be an integer number of model steps")
    if endpoint_seconds % interval_seconds:
        raise ValueError("requested endpoint must be an integer number of history intervals")
    requested_end = run_start + timedelta(seconds=endpoint_seconds)
    if requested_end not in expected:
        raise ValueError("requested endpoint is absent from the receipt's expected timestamps")
    expected_history = [run_start + timedelta(seconds=value)
                        for value in range(0, endpoint_seconds + 1, interval_seconds)]
    if observed != expected_history[:len(observed)]:
        raise ValueError("available history timestamps do not match expected model times at the declared interval")
    if complete and elapsed[-1] != endpoint_seconds:
        raise ValueError("complete history does not reach the requested endpoint")
    if not complete and elapsed[-1] > endpoint_seconds:
        raise ValueError("incomplete history extends beyond the requested endpoint")
    actual_rows = r.get("model_timestamps", [])
    actual_text = [row.get("timestamp") for row in actual_rows if isinstance(row, dict)]
    if len(actual_text) != len(actual_rows) or not actual_text:
        raise ValueError("run receipt lacks a completed model timestamp")
    actual_times = [datetime.strptime(value, "%Y-%m-%d_%H:%M:%S") for value in actual_text]
    if actual_times != expected[:len(actual_times)]:
        raise ValueError("completed model timestamps do not match the receipt's expected step schedule")
    actual_end = actual_times[-1]
    actual_end_text = actual_text[-1]
    if observed[-1] > actual_end:
        raise ValueError("history contains a timestamp beyond the run receipt's completed output")
    bindings = _receipt_history_hashes(r)
    if not bindings:
        raise ValueError("run receipt does not bind any history output hashes")
    identities = []
    for path in history_paths:
        expected_hash = bindings.get(path.name)
        if not expected_hash or _sha(path) != expected_hash:
            raise ValueError(f"history file is not hash-bound by run receipt: {path}")
        identities.append({"path": str(path), "sha256": expected_hash})
    return {"path": str(receipt_path), "sha256": _sha(receipt_path), "status": status,
            "complete_run_window": complete, "run_start_timestamp": run_start.strftime("%Y-%m-%d_%H:%M:%S"),
            "runner_timestep_seconds": step_seconds,
            "run_start_derivation": "first expected model timestamp minus uniform expected model-step interval",
            "run_completed_timestamp": actual_end_text, "history_outputs": identities,
            "observed_endpoint_seconds": int(elapsed[-1]), "requested_endpoint_seconds": endpoint_seconds}


def _times(dataset: netCDF4.Dataset) -> list[datetime]:
    if "Times" not in dataset.variables:
        raise ValueError("wrfout is missing Times")
    rows = np.asarray(dataset.variables["Times"][:])
    return [datetime.strptime(b"".join(row).decode("ascii").strip(), "%Y-%m-%d_%H:%M:%S") for row in rows]


def _finite(dataset: netCDF4.Dataset, name: str, record: int) -> np.ndarray:
    if name not in dataset.variables:
        raise ValueError(f"wrfout is missing required variable {name}")
    value = np.asarray(dataset.variables[name][record], dtype=np.float64)
    if not np.isfinite(value).all():
        raise ValueError(f"{name} contains nonfinite history values")
    variable = dataset.variables[name]
    for attribute in ("_FillValue", "missing_value"):
        if hasattr(variable, attribute):
            sentinels = np.asarray(getattr(variable, attribute)).reshape(-1)
            if np.isfinite(sentinels).any() and np.isin(value, sentinels[np.isfinite(sentinels)]).any():
                raise ValueError(f"{name} contains declared {attribute} sentinel values")
    return value


def _check_unit(dataset: netCDF4.Dataset, name: str, expected: tuple[str, ...]) -> None:
    actual = str(getattr(dataset.variables[name], "units", "")).strip().lower().replace(" ", "")
    allowed = {x.lower().replace(" ", "") for x in expected}
    if actual not in allowed:
        raise ValueError(f"{name} units {actual!r} are not in {sorted(allowed)}")


def _file_index(paths: list[Path]) -> tuple[dict[datetime, tuple[Path, int]], dict[str, Any]]:
    index: dict[datetime, tuple[Path, int]] = {}
    geometry: dict[str, Any] | None = None
    required = set(WATER) | set(MOMENTS) | set(STATE) | {"MU", "MUB", "DNW", "C1H", "C2H",
               "MAPFAC_MX", "MAPFAC_MY", "QIB", "Times"}
    for path in paths:
        with netCDF4.Dataset(path) as ds:
            ds.set_auto_mask(False)
            missing = sorted(required - set(ds.variables))
            if missing:
                raise ValueError(f"{path} is missing required history variables: {missing}")
            times = _times(ds)
            for r, when in enumerate(times):
                if when in index:
                    raise ValueError(f"duplicate history timestamp {when}")
                index[when] = (path, r)
            dx, dy = float(ds.DX), float(ds.DY)
            shape = tuple(ds.variables["MU"].shape[-2:])
            if len(shape) != 2 or min(shape) < 3 or not np.isfinite((dx, dy)).all() or dx <= 0 or dy <= 0:
                raise ValueError("invalid native history mass grid or DX/DY")
            current = {"dx": dx, "dy": dy, "shape": shape}
            if geometry is not None and current != geometry:
                raise ValueError("history files differ in grid shape or DX/DY")
            geometry = current
            for name in ("MU", "MUB", "C2H", "P", "PB"):
                _check_unit(ds, name, ("Pa",))
            _check_unit(ds, "C1H", ("dimensionless", "1", ""))
            _check_unit(ds, "DNW", ("dimensionless", "1", ""))
            for name in WATER:
                _check_unit(ds, name, ("kg kg-1", "kg/kg"))
            _check_unit(ds, "QIB", ("m(3) kg(-1)", "m3 kg-1", "m^3 kg-1"))
            for name in MOMENTS:
                _check_unit(ds, name, ("# kg(-1)", "kg(-1)", "kg-1", "1/kg"))
            for name in ("PH", "PHB"):
                _check_unit(ds, name, ("m2 s-2", "m^2 s^-2"))
            _check_unit(ds, "T", ("K",))
            for name in ("U", "V", "W"):
                _check_unit(ds, name, ("m s-1", "m s^-1"))
    return index, geometry or {}


def _dry_mass(ds: netCDF4.Dataset, record: int, gravity: float, dx: float, dy: float) -> tuple[np.ndarray, dict]:
    mu_base, mub = _finite(ds, "MU", record), _finite(ds, "MUB", record)
    if mu_base.shape != mub.shape:
        raise ValueError("MU and MUB dimensions differ")
    mu = mu_base + mub
    c1, c2, dnw = (_finite(ds, name, record) for name in ("C1H", "C2H", "DNW"))
    mx, my = _finite(ds, "MAPFAC_MX", record), _finite(ds, "MAPFAC_MY", record)
    if (mx.shape != mu.shape or my.shape != mu.shape or c1.ndim != 1 or
            c2.shape != c1.shape or dnw.shape != c1.shape):
        raise ValueError("hybrid coefficients or mass map factors have incompatible dimensions")
    carrier = c1[:, None, None] * mu[None, :, :] + c2[:, None, None]
    if np.any(mu <= 0) or np.any(mx <= 0) or np.any(my <= 0):
        raise ValueError("MU+MUB and each map factor must be positive")
    if np.any(dnw >= 0) or np.any(carrier <= 0):
        raise ValueError("DNW must be negative and hybrid pressure carrier positive")
    dp = -carrier * dnw[:, None, None]
    area = dx * dy / (mx * my)
    mass = area[None, :, :] * dp / gravity
    if not np.isfinite(mass).all() or np.any(mass <= 0):
        raise ValueError("native dry hybrid layer mass is nonpositive or nonfinite")
    return mass, {"layer_pressure_thickness_pa_min": float(dp.min()),
                  "layer_pressure_thickness_pa_max": float(dp.max()),
                  "dry_mass_kg_min": float(mass.min()), "dry_mass_kg_max": float(mass.max())}


def _state_fields(ds: netCDF4.Dataset, record: int) -> dict[str, np.ndarray]:
    pressure = _finite(ds, "P", record) + _finite(ds, "PB", record)
    geopotential_interface = _finite(ds, "PH", record) + _finite(ds, "PHB", record)
    geopotential = 0.5 * (geopotential_interface[:-1, ...] + geopotential_interface[1:, ...])
    theta_perturb = _finite(ds, "T", record)
    u = _finite(ds, "U", record); v = _finite(ds, "V", record); w = _finite(ds, "W", record)
    if (u.ndim != 3 or v.ndim != 3 or w.ndim != 3 or
            u.shape[-1] < 2 or v.shape[-2] < 2 or w.shape[0] < 2):
        raise ValueError("staggered U/V/W dimensions cannot map to mass levels")
    result = {"P+PB": pressure, "PH+PHB": geopotential, "T_perturb_potential": theta_perturb,
              "U_mass_point": 0.5 * (u[..., :-1] + u[..., 1:]),
              "V_mass_point": 0.5 * (v[..., :-1, :] + v[..., 1:, :]),
              "W_mass_point": 0.5 * (w[:-1, ...] + w[1:, ...])}
    if any(value.shape != theta_perturb.shape for value in result.values()):
        raise ValueError("native state fields do not map to a common mass-grid shape")
    if any(not np.isfinite(value).all() for value in result.values()):
        raise ValueError("derived native state contains nonfinite values")
    return result


def _delta_stats(delta: np.ndarray) -> dict[str, float]:
    return {"mean": float(np.mean(delta, dtype=np.float64)),
            "mean_abs": float(np.mean(np.abs(delta), dtype=np.float64)),
            "max_abs": float(np.max(np.abs(delta))), "min": float(np.min(delta)),
            "max": float(np.max(delta))}


def _extensive_change(delta: np.ndarray, mask: np.ndarray) -> dict[str, float]:
    cells = delta[:, mask]
    columns = np.sum(delta, axis=0, dtype=np.float64)[mask]
    return {"signed_total": float(np.sum(cells, dtype=np.float64)),
            "L1": float(np.sum(np.abs(cells), dtype=np.float64)),
            "max_abs_cell": float(np.max(np.abs(cells))),
            "max_abs_column": float(np.max(np.abs(columns))),
            "column_L1": float(np.sum(np.abs(columns), dtype=np.float64))}


def _analyze(paths: list[Path], run_receipt: Path, constants_receipt: Path,
             endpoint_seconds: int, interval_seconds: int, allow_incomplete: bool) -> dict[str, Any]:
    gravity, constants_identity = _constants(constants_receipt)
    index, grid = _file_index(paths)
    times = sorted(index)
    run_identity = _receipt_window(run_receipt, paths, times, endpoint_seconds, interval_seconds, allow_incomplete)
    if not times:
        raise ValueError("history contains no timestamps")
    elapsed = [(t - times[0]).total_seconds() for t in times]
    expected = list(range(0, int(elapsed[-1]) + 1, interval_seconds))
    if elapsed != expected:
        raise ValueError("history does not contain the exact elapsed 0, interval, ..., endpoint sequence")
    full_mask = np.ones(grid["shape"], dtype=bool)
    interior_mask = np.zeros(grid["shape"], dtype=bool); interior_mask[1:-1, 1:-1] = True
    masks = {"all_native_mass_cells": full_mask, "interior_excluding_boundary_ring": interior_mask}
    inventory_rows = []
    baseline_inventory: dict[str, dict[str, Any]] | None = None
    baseline_extensive: dict[str, np.ndarray] | None = None
    baseline_state: dict[str, np.ndarray] | None = None
    for when in times:
        path, record = index[when]
        with netCDF4.Dataset(path) as ds:
            ds.set_auto_mask(False)
            mass, geometry = _dry_mass(ds, record, gravity, grid["dx"], grid["dy"])
            water_fields = {name: _finite(ds, name, record) for name in WATER}
            number_fields = {name: _finite(ds, name, record) for name in MOMENTS}
            bg = _finite(ds, "QIB", record)
            for name, field in {**water_fields, **number_fields, "QIB": bg}.items():
                if field.shape != mass.shape:
                    raise ValueError(f"{name} shape differs from hybrid dry mass")
            water_extensive = {name: field * mass for name, field in water_fields.items()}
            number_extensive = {name: field * mass for name, field in number_fields.items()}
            extensive = {"total_water": sum(water_extensive.values()),
                         "BG_rime_volume": bg * mass,
                         **{f"moment:{name}": value for name, value in number_extensive.items()}}
            if any(not np.isfinite(value).all() for value in extensive.values()):
                raise ValueError("extensive endpoint inventories overflowed or became nonfinite")
            domain_inventory = {}
            for scope, mask in masks.items():
                water_by_species = {name: float(np.sum(field[:, mask], dtype=np.float64))
                                    for name, field in water_extensive.items()}
                number_by_species = {name: float(np.sum(field[:, mask], dtype=np.float64))
                                     for name, field in number_extensive.items()}
                domain_inventory[scope] = {
                    "mass_cell_count": int(np.count_nonzero(mask) * mass.shape[0]),
                    "dry_mass_kg": float(np.sum(mass[:, mask], dtype=np.float64)),
                    "water_species_kg": water_by_species,
                    "water_total_kg": float(sum(water_by_species.values())),
                    "moment_inventory_count": number_by_species,
                    "BG_rime_volume_m3": float(np.sum(extensive["BG_rime_volume"][:, mask], dtype=np.float64)),
                }
            if baseline_inventory is None:
                baseline_inventory = domain_inventory
                baseline_extensive = {name: value.copy() for name, value in extensive.items()}
                inventory_delta = {scope: {"dry_mass_kg": 0.0,
                    "water_species_kg": {name: 0.0 for name in WATER},
                    "water_total_kg": 0.0, "moment_inventory_count": {name: 0.0 for name in MOMENTS},
                    "BG_rime_volume_m3": 0.0} for scope in masks}
                physical_change = {scope: {name: _extensive_change(np.zeros_like(value), mask)
                                           for name, value in extensive.items()}
                                   for scope, mask in masks.items()}
            else:
                inventory_delta = {}
                for scope in masks:
                    initial = baseline_inventory[scope]
                    current = domain_inventory[scope]
                    inventory_delta[scope] = {
                        "dry_mass_kg": current["dry_mass_kg"] - initial["dry_mass_kg"],
                        "water_species_kg": {name: current["water_species_kg"][name] - initial["water_species_kg"][name]
                                              for name in WATER},
                        "water_total_kg": current["water_total_kg"] - initial["water_total_kg"],
                        "moment_inventory_count": {name: current["moment_inventory_count"][name] - initial["moment_inventory_count"][name]
                                                   for name in MOMENTS},
                        "BG_rime_volume_m3": current["BG_rime_volume_m3"] - initial["BG_rime_volume_m3"],
                    }
                physical_change = {scope: {name: _extensive_change(value - baseline_extensive[name], mask)
                                           for name, value in extensive.items()}
                                   for scope, mask in masks.items()}
            state = _state_fields(ds, record)
            state_delta = {}
            if baseline_state is None:
                baseline_state = {name: value.copy() for name, value in state.items()}
            else:
                for name, value in state.items():
                    if value.shape != baseline_state[name].shape:
                        raise ValueError(f"{name} field shape changed between endpoints")
                    state_delta[name] = _delta_stats(value - baseline_state[name])
            inventory_rows.append({"timestamp": when.strftime("%Y-%m-%d_%H:%M:%S"),
                "elapsed_seconds": int((when - times[0]).total_seconds()),
                "hybrid_geometry": geometry, "inventory": domain_inventory,
                "inventory_delta_from_elapsed_zero": inventory_delta,
                "physical_change_metrics_from_elapsed_zero": physical_change,
                "native_state_delta_from_elapsed_zero": state_delta})
    return {"schema": "pr87_native_history_endpoint_inventory_v1", "status": "ACCOUNTED",
            "scoped_data_status": "PASS_SCOPED_DATA", "physical_approval": False,
            "state_and_observation_evaluations": "NOT_EVALUATED",
            "scope": "native endpoint state inventory and state deltas; not a timestep or whole-model closure",
            "source_contract": {"dry_layer_pressure_thickness": "-(C1H*(MU+MUB)+C2H)*DNW",
                "cell_dry_mass": "DX*DY/(MAPFAC_MX*MAPFAC_MY)*dp_dry/g",
                "gravity_source": constants_identity, "horizontal_scope": list(masks),
                "interior_scope_note": "index 1:-1 on each mass-grid horizontal axis, descriptive only; not asserted to equal the KDM6 consumer footprint",
                "stagger_note": "U/V/W are averaged over adjacent faces to mass points for state-delta summaries only; no face-flux closure is computed",
                "thermal_note": "T is perturbation potential temperature; report only its change, whose 300 K offset cancels",
                "pressure_note": "P+PB is total EOS pressure and is not used as the dry mass coordinate"},
            "window": run_identity, "history_times": [t.strftime("%Y-%m-%d_%H:%M:%S") for t in times],
            "history_interval_seconds": interval_seconds, "dx_m": grid["dx"], "dy_m": grid["dy"],
            "grid_shape_south_north_west_east": list(grid["shape"]), "records": inventory_rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, nargs="+", required=True)
    parser.add_argument("--run-receipt", type=Path, required=True)
    parser.add_argument("--constants-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint-seconds", type=int, default=60)
    parser.add_argument("--history-interval-seconds", type=int, default=60)
    parser.add_argument("--allow-incomplete-window", action="store_true")
    args = parser.parse_args()
    if args.endpoint_seconds <= 0 or args.history_interval_seconds <= 0:
        parser.error("endpoint and history interval must be positive seconds")
    result = _analyze(args.history, args.run_receipt, args.constants_receipt,
                      args.endpoint_seconds, args.history_interval_seconds,
                      args.allow_incomplete_window)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
