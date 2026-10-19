#!/usr/bin/env python3
"""Summarize captured PR87 state changes without inventing physical geometry."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import netCDF4

from native_kdm6_trace import read_dump
from pr67_kdm6_process_budget import parse_process_capture


FIELDS = ("DEN", "Q", "QC", "QI", "QR", "QS", "QG", "NN", "NC", "NI", "NR", "BG")
WATER_FIELDS = ("Q", "QC", "QI", "QR", "QS", "QG")
NUMBER_FIELDS = ("NN", "NC", "NI", "NR")
STATE_MAGIC = b"PR85QND2"
PBL_MAGIC = b"PR85PLB1"
PBL_FIELDS = ("QV_TEND", "QC_TEND", "QI_TEND", "QNC_TEND", "QNI_TEND")
SELECTED = {"PRE_RK", "POST_KDM6"}
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = {
    "OFF": Path("/var/tmp/pr87_joint_OFF_40s_v42_20261016/run"),
    "COUPLED": Path("/var/tmp/pr87_joint_COUPLED_40s_v42_20261016/run"),
}
DEFAULT_OUT = ROOT / "docs/evidence/pr87_followup_20261019/budget"
DEFAULT_COLUMN_MAPS = Path("/var/tmp/pr87_followup_budget_20261019")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _change_stats(before: np.ndarray, after: np.ndarray) -> dict[str, float]:
    delta = after.astype(np.float64) - before.astype(np.float64)
    column_delta = np.sum(delta, axis=1, dtype=np.float64)
    return {
        "signed_field_sum": float(np.sum(delta, dtype=np.float64)),
        "l1_field_sum": float(np.sum(np.abs(delta), dtype=np.float64)),
        "max_abs_cell_delta": float(np.max(np.abs(delta))),
        "max_abs_column_sum": float(np.max(np.abs(column_delta))),
    }


def _group_stats(fields: dict[str, dict[str, float]], names: tuple[str, ...]) -> dict[str, float]:
    rows = [fields[name] for name in names]
    return {
        "signed_field_sum": sum(row["signed_field_sum"] for row in rows),
        "l1_field_sum": sum(row["l1_field_sum"] for row in rows),
        "max_abs_cell_delta": max(row["max_abs_cell_delta"] for row in rows),
        "max_abs_column_sum": max(row["max_abs_column_sum"] for row in rows),
    }


def _history_summary(path: Path) -> dict[str, Any]:
    required = ("P", "PB", "PH", "PHB", "U", "V", "W", "MAPFAC_MX", "MAPFAC_MY",
                "XLAT", "XLONG")
    with netCDF4.Dataset(path) as dataset:
        dataset.set_auto_mask(False)
        missing = [name for name in required if name not in dataset.variables]
        if missing:
            raise ValueError(f"initial history missing expected variables: {missing}")
        times = [b"".join(row).decode("ascii").strip()
                 for row in np.asarray(dataset.variables["Times"][:])]
        mx = np.asarray(dataset.variables["MAPFAC_MX"][0], dtype=np.float64)
        my = np.asarray(dataset.variables["MAPFAC_MY"][0], dtype=np.float64)
        area = float(dataset.DX) * float(dataset.DY) / (mx * my)
        if not np.isfinite(area).all() or np.any(area <= 0.0):
            raise ValueError("invalid initial map area")
        return {"model_times": times, "records": len(times),
                "available_initial_fields": list(required),
                "dx_m": float(dataset.DX), "dy_m": float(dataset.DY),
                "map_area_m2_min": float(area.min()), "map_area_m2_max": float(area.max())}


def _weighted_stats(delta: np.ndarray) -> dict[str, float]:
    column_delta = np.sum(delta, axis=1, dtype=np.float64)
    return {"signed": float(np.sum(delta, dtype=np.float64)),
            "l1": float(np.sum(np.abs(delta), dtype=np.float64)),
            "max_abs_cell": float(np.max(np.abs(delta))),
            "max_abs_column": float(np.max(np.abs(column_delta)))}


def _inventory_delta(before: np.ndarray, after: np.ndarray, dry_mass: np.ndarray) -> np.ndarray:
    """Convert a mixing-ratio endpoint change to extensive cell inventory."""
    if before.shape != after.shape or before.shape != dry_mass.shape:
        raise ValueError("state endpoints and dry-mass geometry must have matching shapes")
    return ((after.astype(np.float64) - before.astype(np.float64)) *
            dry_mass.astype(np.float64))


def _sum_species_delta(deltas: list[np.ndarray]) -> tuple[np.ndarray, dict[str, float]]:
    """Sum species changes cellwise before computing total-water L1 and maxima."""
    if not deltas or any(delta.shape != deltas[0].shape for delta in deltas):
        raise ValueError("species deltas must be a nonempty set of matching arrays")
    total = np.sum(np.stack(deltas), axis=0, dtype=np.float64)
    return total, _weighted_stats(total)


def _horizontal_stats(values: np.ndarray) -> dict[str, float]:
    return {"signed": float(np.sum(values, dtype=np.float64)),
            "l1": float(np.sum(np.abs(values), dtype=np.float64)),
            "max_abs_cell": float(np.max(np.abs(values))),
            "max_abs_column": float(np.max(np.abs(values)))}


def _expand_bound(run_root: Path, receipt: dict, name: str, temp_dir: Path) -> tuple[Path, dict]:
    bindings = {row["compressed_path"]: row for row in receipt["compressed_outputs"]}
    binding = bindings.get(name)
    source = run_root / name
    if not binding or sha256(source) != binding["compressed_sha256"]:
        raise ValueError(f"missing or unbound compressed output: {source}")
    expanded = temp_dir / name.removesuffix(".gz")
    with gzip.open(source, "rb") as compressed, expanded.open("wb") as output:
        while block := compressed.read(8 * 1024 * 1024):
            output.write(block)
    if sha256(expanded) != binding["sha256"] or sha256(source) != binding["compressed_sha256"]:
        raise ValueError(f"compressed output hash mismatch: {source}")
    return expanded, {"compressed_path": str(source), "compressed_sha256": binding["compressed_sha256"],
                      "expanded_sha256": binding["sha256"], "expanded_bytes": expanded.stat().st_size}


def _bottom_flux(run_root: Path, receipt: dict, pre: dict, area: np.ndarray,
                 temp_dir: Path) -> tuple[dict[str, Any], np.ndarray, np.ndarray, dict]:
    path, identity = _expand_bound(run_root, receipt, "pr67_kdm6_process.raw.gz", temp_dir)
    records = parse_process_capture(path)
    b = pre["bounds"]
    rows = [row for row in records if row["stage"] == 2]
    if len(rows) != b["jte"] - b["jts"] + 1:
        raise ValueError("KDM6 process capture does not cover the first-call j rows")
    bottom_by_species = np.zeros((4, area.shape[0], area.shape[1]), dtype=np.float64)
    accumulator_by_column = np.zeros((area.shape[0], area.shape[1]), dtype=np.float64)
    species_names = ("rain", "snow", "graupel", "ice")
    for row in rows:
        j = row["lat"] - b["jts"]
        if (row["its"], row["ite"], row["kts"], row["kte"]) != (
                b["its"], b["ite"], b["kts"], b["kte"]):
            raise ValueError("KDM6 process geometry differs from first-call capture")
        # Same KDM6 call: verify its saved per-cell geometry against PRE.
        source_row = next((item for item in records if item["stage"] == 0 and item["lat"] == row["lat"]), None)
        if source_row is None or not np.array_equal(source_row["density"], pre["fields"]["DEN"][j]) or \
                not np.array_equal(source_row["delz"], pre["fields"]["DELZ"][j]):
            raise ValueError(f"process geometry differs from PRE capture in row {row['lat']}")
        # Native rainncv conversion, kept in the same form as the source budget:
        # fall*DELZ/DENR*dt -> mm, then water density and map area -> kg.
        depth_mm = row["fall"] * row["delz"][None, :] / row["denr"] * row["dtcld"] * 1000.0
        if not np.allclose(np.sum(depth_mm, axis=0), row["rainncv"], rtol=2.0e-6, atol=1.0e-5):
            raise ValueError(f"saved rainncv disagrees with summed phase falls at row {row['lat']}")
        bottom_by_species[:, j, :] = depth_mm * (row["denr"] / 1000.0) * area[j][None, :]
        accumulator_by_column[j, :] = row["rainncv"] * area[j]
    species_totals = {name: float(np.sum(bottom_by_species[index], dtype=np.float64))
                      for index, name in enumerate(species_names)}
    total_map = np.sum(bottom_by_species, axis=0, dtype=np.float64)
    accumulator_total = float(np.sum(accumulator_by_column, dtype=np.float64))
    if not np.isclose(accumulator_total, float(np.sum(total_map, dtype=np.float64)), rtol=2.0e-6, atol=1.0e-5):
        raise ValueError("mapped rainncv increment does not match mapped phase outflow")
    return ({"unit": "kg", "species_outflow_kg": species_totals,
             "total_outflow_kg": float(np.sum(total_map, dtype=np.float64)),
             "rainncv_accumulator_increment_kg": accumulator_total,
             "signed_l1_max_column": _weighted_stats(total_map[:, None, :]),
             "records": len(records), "stage2_rows": len(rows)}, total_map,
            bottom_by_species, identity)


def _rain_ground_comparison(run_root: Path, receipt: dict, bounds: dict,
                            area: np.ndarray, rain_fall_map: np.ndarray) -> tuple[dict[str, Any], dict, np.ndarray]:
    path = run_root / "pr87_rain_sedimentation_budget.raw.gz"
    binding = {row["compressed_path"]: row for row in receipt["compressed_outputs"]}.get(path.name)
    if not binding or sha256(path) != binding["compressed_sha256"]:
        raise ValueError("rain sedimentation ledger missing or receipt hash mismatch")
    ground_map = np.zeros_like(area, dtype=np.float64)
    selected_rows = 0
    call_rows = 0
    current_step: int | None = None
    current_j: int | None = None
    helper_residual = 0.0
    for line in gzip.open(path, "rt", encoding="ascii"):
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "PR87_RAIN_CALL":
            if len(fields) != 4:
                raise ValueError("rain call marker contract changed")
            current_step, current_j = int(fields[1]), int(fields[2])
            if current_step == 1:
                call_rows += 1
                if current_j != bounds["jts"] + call_rows - 1 or float(fields[3]) != 20.0:
                    raise ValueError("rain call markers do not cover first-step rows at 20 s")
            continue
        if fields[0] != "PR87_RAIN_SED" or current_step != 1:
            continue
        if len(fields) != 17 or current_j is None:
            raise ValueError("rain sedimentation row contract changed")
        i, j, _substep, nlevels = map(int, fields[1:5])
        values = np.asarray(fields[5:], dtype=np.float64)
        if not np.isfinite(values).all() or j != current_j or nlevels != bounds["kte"] - bounds["kts"] + 1:
            raise ValueError("rain sedimentation row has invalid values or geometry")
        ji = (j - bounds["jts"], i - bounds["its"])
        if not (0 <= ji[0] < area.shape[0] and 0 <= ji[1] < area.shape[1]):
            raise ValueError("rain sedimentation row is outside the active map")
        ground_map[ji] += float(values[6]) * area[ji[0], ji[1]]
        helper_residual += float(values[10]) * area[ji[0], ji[1]]
        selected_rows += 1
    if call_rows != area.shape[0] or selected_rows == 0:
        raise ValueError("rain sedimentation ledger does not cover timestep 1")
    if sha256(path) != binding["compressed_sha256"]:
        raise ValueError("rain sedimentation ledger changed during analysis")
    difference = ground_map - rain_fall_map
    return ({"comparison": "helper ground-approved rain Q versus captured public fall phase 1 mapped through rainncv",
             "helper_ground_approved_rain_Q_kg": float(np.sum(ground_map, dtype=np.float64)),
             "captured_public_fall_phase1_rain_kg": float(np.sum(rain_fall_map, dtype=np.float64)),
             "helper_minus_public_rain_difference_kg": _horizontal_stats(difference),
             "helper_ground_approved_map": _horizontal_stats(ground_map),
             "captured_public_rain_map": _horizontal_stats(rain_fall_map),
             "helper_internal_column_residual_mapped_kg": helper_residual,
             "timestep": 1, "call_marker_rows": call_rows, "selected_sedimentation_rows": selected_rows,
             "unit_basis": "ground_approved_q is kg m-2 per call times actual map area; public fall phase 1 uses source fall*DELZ/DENR*DTCLD*1000 mm times water density/1000 and map area",
            "interpretation": "The helper ledger and public output accumulator disagree; ground-approved process Q is not substituted for emitted precipitation."},
            {"path": str(path), "sha256": binding["compressed_sha256"]}, difference)


def _save_column_maps(arm: str, bounds: dict, output_dir: Path, *, area: np.ndarray,
                      water_delta: np.ndarray, bottom_map: np.ndarray,
                      residual_before: np.ndarray, residual_after: np.ndarray,
                      rain_difference: np.ndarray, number_delta: np.ndarray,
                      bg_delta: np.ndarray) -> dict[str, Any]:
    """Save a compact, hash-bound archive of 2D column maps only."""
    output_dir.mkdir(parents=True, exist_ok=True)
    j_offset, i_offset = np.indices(area.shape)
    arrays = {
        "total_water_delta_kg_per_column": water_delta,
        "public_bottom_outflow_kg_per_column": bottom_map,
        "water_residual_before_cleanup_kg_per_column": residual_before,
        "water_residual_after_recorded_cleanup_kg_per_column": residual_after,
        "helper_minus_public_rain_kg_per_column": rain_difference,
        "number_category_sum_delta_count_per_column_not_conserved": number_delta,
        "BG_volume_delta_m3_per_column": bg_delta,
        "cell_area_m2": area,
        "i_index": i_offset + bounds["its"],
        "j_index": j_offset + bounds["jts"],
    }
    shapes = {name: list(np.asarray(value).shape) for name, value in arrays.items()}
    if any(len(shape) != 2 or shape != list(area.shape) for shape in shapes.values()):
        raise ValueError("column archive must contain only matching 2D maps")
    path = output_dir / f"{arm}_firstcall_columns.npz"
    np.savez_compressed(path, **arrays)
    if path.stat().st_size >= 5 * 1024 * 1024:
        path.unlink()
        raise ValueError("column-map archive exceeds 5 MiB limit")
    units = {
        "total_water_delta_kg_per_column": "kg",
        "public_bottom_outflow_kg_per_column": "kg",
        "water_residual_before_cleanup_kg_per_column": "kg",
        "water_residual_after_recorded_cleanup_kg_per_column": "kg",
        "helper_minus_public_rain_kg_per_column": "kg",
        "number_category_sum_delta_count_per_column_not_conserved": "count",
        "BG_volume_delta_m3_per_column": "m3",
        "cell_area_m2": "m2",
        "i_index": "1-based active-domain WRF i index",
        "j_index": "1-based active-domain WRF j index",
    }
    return {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size,
            "format": "compressed NumPy NPZ; 2D maps only; no interpolation",
            "shape_j_i": list(area.shape), "arrays": list(arrays), "units": units,
            "array_shapes": shapes}


def _recorded_numerical_terms(run_root: Path, receipt: dict, pre: dict,
                              dry_mass: np.ndarray, *,
                              allow_single_cutoff_sweep: bool = False) -> tuple[dict[str, Any], np.ndarray, np.ndarray, dict]:
    b = pre["bounds"]
    cutoff_map = np.zeros(dry_mass.shape, dtype=np.float64)
    cutoff_path = run_root / "pr85_kdm6_cutoff_budget.raw.gz"
    bindings = {row["compressed_path"]: row for row in receipt["compressed_outputs"]}
    cutoff_binding = bindings.get(cutoff_path.name)
    if not cutoff_binding or sha256(cutoff_path) != cutoff_binding["compressed_sha256"]:
        raise ValueError("cutoff ledger missing or receipt hash mismatch")
    sweep = 0
    previous_j: int | None = None
    first_sweep_j: list[int] = []
    second_sweep_j: list[int] = []
    cutoff_rows = 0
    first_geometry_mismatches = 0
    second_geometry_mismatches = 0
    for line in gzip.open(cutoff_path, "rt", encoding="ascii"):
        fields = line.split()
        if not fields or fields[0] != "PR85_KDM6_CUTOFF":
            continue
        if len(fields) != 33:
            raise ValueError("cutoff ledger field contract changed")
        i, j, k = map(int, fields[1:4])
        if previous_j is not None and j < previous_j:
            sweep += 1
            if sweep > 1:
                raise ValueError("cutoff ledger contains more than two j sweeps")
        previous_j = j
        if sweep == 0:
            first_sweep_j.append(j)
        else:
            second_sweep_j.append(j)
        slot = (j - b["jts"], k - b["kts"], i - b["its"])
        values = np.asarray(fields[6:-2], dtype=np.float64)
        if not np.isfinite(values).all():
            raise ValueError(f"cutoff row contains nonfinite values at {(i, j, k)}")
        matches_pre = values[0] == float(pre["fields"]["DEN"][slot])
        if sweep == 0 and not matches_pre:
            first_geometry_mismatches += 1
        if sweep == 1 and not matches_pre:
            second_geometry_mismatches += 1
        if sweep == 1:
            continue
        # Qbefore(5) and Qafter(5); remove only their signed stored water delta.
        delta_q = float(np.sum(values[8:13] - values[3:8], dtype=np.float64))
        cutoff_map[slot] += delta_q * dry_mass[slot]
        cutoff_rows += 1
    expected_lat = list(range(b["jts"], b["jte"] + 1))
    first_sweep_complete = list(dict.fromkeys(first_sweep_j)) == expected_lat
    second_sweep_complete = list(dict.fromkeys(second_sweep_j)) == expected_lat
    if not first_sweep_complete or (not second_sweep_complete and not allow_single_cutoff_sweep):
        raise ValueError("cutoff ledger lacks the required complete ordered call sweep(s)")
    if first_geometry_mismatches or (not allow_single_cutoff_sweep and second_geometry_mismatches == 0):
        raise ValueError("cutoff sweep cannot be uniquely assigned to the captured first KDM6 call")
    if sha256(cutoff_path) != cutoff_binding["compressed_sha256"]:
        raise ValueError("cutoff ledger changed during analysis")

    transition_map = np.zeros(dry_mass.shape, dtype=np.float64)
    transition_path = run_root / "pr85_ice_transition_branch.raw.gz"
    transition_binding = bindings.get(transition_path.name)
    if not transition_binding or sha256(transition_path) != transition_binding["compressed_sha256"]:
        raise ValueError("transition ledger missing or receipt hash mismatch")
    current_step: int | None = None
    current_j: int | None = None
    transition_rows = 0
    for line in gzip.open(transition_path, "rt", encoding="ascii"):
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "PR85_ICE_TRANSITION_LOOP":
            if len(fields) != 8:
                raise ValueError("transition loop marker contract changed")
            current_step, current_j = int(fields[1]), int(fields[2])
            continue
        if fields[0] != "PR85_ICE_TRANSITION":
            continue
        if len(fields) != 18 or current_step is None or current_j is None:
            raise ValueError("transition event lacks its call marker")
        i, j, k = map(int, fields[1:4])
        if j != current_j:
            raise ValueError("transition event does not match its marker latitude")
        if current_step != 1:
            continue
        values = np.asarray(fields[5:], dtype=np.float64)
        if not np.isfinite(values).all():
            raise ValueError("nonfinite transition event")
        slot = (j - b["jts"], k - b["kts"], i - b["its"])
        delta_q = float((values[10] - values[4]) + (values[11] - values[5]))
        transition_map[slot] += delta_q * dry_mass[slot]
        transition_rows += 1
    if sha256(transition_path) != transition_binding["compressed_sha256"]:
        raise ValueError("transition ledger changed during analysis")
    cutoff_assignment = (
        "first full ordered j sweep; all rows rhoDry match first-call PRE; only one complete sweep is captured"
        if allow_single_cutoff_sweep and not second_sweep_j else
        "first full ordered j sweep; every row rhoDry matches first-call PRE capture and second sweep has changed rhoDry rows")
    return ({"cutoff_water_delta_kg": _weighted_stats(cutoff_map),
             "cutoff_rows_first_sweep": cutoff_rows,
             "cutoff_rows_second_sweep_geometry_mismatches": second_geometry_mismatches,
             "cutoff_sweep_assignment": cutoff_assignment,
             "ice_snow_transition_water_delta_kg": _weighted_stats(transition_map),
             "ice_snow_transition_rows_step1": transition_rows,
             "transition_step_assignment": "explicit PR85_ICE_TRANSITION_LOOP timestep marker equals 1"},
            cutoff_map, transition_map,
            {"cutoff": {"path": str(cutoff_path), "sha256": cutoff_binding["compressed_sha256"]},
             "transition": {"path": str(transition_path), "sha256": transition_binding["compressed_sha256"]}})


def first_call_budget(arm: str, receipt: dict, *, run_root: Path | None = None,
                      column_output_dir: Path | None = None,
                      allow_single_cutoff_sweep: bool = False) -> dict[str, Any]:
    """Compute the exact first KDM6 call ledger with its captured rhoDry and DELZ."""
    run_root = DEFAULT_RUNS[arm] if run_root is None else Path(run_root)
    column_output_dir = DEFAULT_COLUMN_MAPS if column_output_dir is None else Path(column_output_dir)
    with tempfile.TemporaryDirectory(prefix=f"pr87_v42_{arm.lower()}_budget_") as temp:
        temp_dir = Path(temp)
        pre_path, pre_identity = _expand_bound(run_root, receipt, "kdm6_first_call_pre.raw.gz", temp_dir)
        post_path, post_identity = _expand_bound(run_root, receipt, "kdm6_first_call_post.raw.gz", temp_dir)
        pre, post = read_dump(pre_path), read_dump(post_path)
        if (pre["stage"], post["stage"], pre["itimestep"], post["itimestep"]) != (1, 2, 1, 1):
            raise ValueError("expected the first PRE/POST KDM6 call")
        if pre["bounds"] != post["bounds"] or pre["params"] != post["params"]:
            raise ValueError("first-call PRE/POST headers differ")
        for name in ("DEN", "DELZ"):
            if not np.array_equal(pre["fields"][name], post["fields"][name]):
                raise ValueError(f"same-call {name} changed across KDM6 endpoints")
        b = pre["bounds"]
        wrfout = run_root / "wrfout_d01_2026-08-16_13:00:00"
        with netCDF4.Dataset(wrfout) as dataset:
            dataset.set_auto_mask(False)
            ys, xs = slice(b["jts"] - 1, b["jte"]), slice(b["its"] - 1, b["ite"])
            mx = np.asarray(dataset.variables["MAPFAC_MX"][0, ys, xs], dtype=np.float64)
            my = np.asarray(dataset.variables["MAPFAC_MY"][0, ys, xs], dtype=np.float64)
            area = float(dataset.DX) * float(dataset.DY) / (mx * my)
        rho = pre["fields"]["DEN"].astype(np.float64)
        delz = pre["fields"]["DELZ"].astype(np.float64)
        if area.shape != (rho.shape[0], rho.shape[2]) or not np.isfinite(area).all() or np.any(area <= 0.0):
            raise ValueError("invalid first-call map area")
        dry_mass = rho * delz * area[:, None, :]
        water_names = ("Q", "QC", "QI", "QR", "QS", "QG")
        number_names = ("NN", "NC", "NI", "NR")
        delta_maps: dict[str, np.ndarray] = {}
        inventories: dict[str, dict[str, Any]] = {}
        for name in (*water_names, *number_names, "BG"):
            before = pre["fields"][name].astype(np.float64) * dry_mass
            after = post["fields"][name].astype(np.float64) * dry_mass
            delta = _inventory_delta(pre["fields"][name], post["fields"][name], dry_mass)
            delta_maps[name] = delta
            inventories[name] = {"before": float(np.sum(before, dtype=np.float64)),
                                 "after": float(np.sum(after, dtype=np.float64)),
                                 "change": _weighted_stats(delta)}
        water_delta, water_stats = _sum_species_delta([delta_maps[name] for name in water_names])
        number_delta, number_stats = _sum_species_delta([delta_maps[name] for name in number_names])
        water_column_delta = np.sum(water_delta, axis=1, dtype=np.float64)
        bottom, bottom_map, bottom_by_species, process_identity = _bottom_flux(
            run_root, receipt, pre, area, temp_dir)
        rain_ground, rain_ground_identity, rain_difference = _rain_ground_comparison(
            run_root, receipt, pre["bounds"], area, bottom_by_species[0])
        numerical, cutoff_map, transition_map, numerical_identities = _recorded_numerical_terms(
            run_root, receipt, pre, dry_mass,
            allow_single_cutoff_sweep=allow_single_cutoff_sweep)
        residual_column = water_column_delta + bottom_map
        adjusted_residual_column = (residual_column -
                                    np.sum(cutoff_map, axis=1, dtype=np.float64) -
                                    np.sum(transition_map, axis=1, dtype=np.float64))
        residual = {"interpretation": "water-state change + bottom outflow before recorded cleanup/phase-storage corrections",
                    "unit": "kg per column",
                    "signed": float(np.sum(residual_column, dtype=np.float64)),
                    "l1": float(np.sum(np.abs(residual_column), dtype=np.float64)),
                    "max_abs_column": float(np.max(np.abs(residual_column))),
                    "water_change_kg": float(np.sum(water_delta, dtype=np.float64)),
                    "bottom_outflow_kg": bottom["total_outflow_kg"]}
        recorded_adjusted_residual = {
            "interpretation": "water-state change + bottom outflow - recorded cutoff water delta - recorded ice/snow storage delta",
            "unit": "kg per column",
            "signed": float(np.sum(adjusted_residual_column, dtype=np.float64)),
            "l1": float(np.sum(np.abs(adjusted_residual_column), dtype=np.float64)),
            "max_abs_column": float(np.max(np.abs(adjusted_residual_column))),
            "not_closed": True,
        }
        column_maps = _save_column_maps(
            arm, b, column_output_dir, area=area,
            water_delta=water_column_delta,
            bottom_map=bottom_map,
            residual_before=residual_column,
            residual_after=adjusted_residual_column,
            rain_difference=rain_difference,
            number_delta=np.sum(number_delta, axis=1, dtype=np.float64),
            bg_delta=np.sum(delta_maps["BG"], axis=1, dtype=np.float64))
        return {
            "status": "FIRST_KDM6_CALL_ACCOUNTED_PARTIAL_BUDGET_OPEN",
            "timestep": 1, "call_seconds": pre["params"]["dt_s"],
            "measure": "same-call DEN * DELZ * DX*DY/(MAPFAC_MX*MAPFAC_MY)",
            "active_shape_jki": list(dry_mass.shape),
            "inventory_by_field": inventories,
            "water_total": {"fields": list(water_names), "change": water_stats,
                            "sum_of_separate_field_l1": float(sum(inventories[name]["change"]["l1"]
                                                                   for name in water_names))},
            "number_category_sum_change_not_a_conservation_residual": {
                "fields": list(number_names), "change": number_stats,
                "sum_of_separate_field_l1": float(sum(inventories[name]["change"]["l1"]
                                                       for name in number_names))},
            "BG_volume": {"unit": "m3", "change": _weighted_stats(delta_maps["BG"])},
            "bottom_outflow": bottom,
            "rain_ground_comparison": rain_ground,
            "unadjusted_water_residual": residual,
            "recorded_numerical_terms": numerical,
            "residual_after_recorded_numerical_terms": recorded_adjusted_residual,
            "column_maps": column_maps,
            "coverage_limits": ["unadjusted residual precedes cutoff and ice/snow transition corrections; adjusted residual subtracts only those two recorded terms",
                                "both residuals omit stored-rounding and other numerical terms",
                                "same-call host hybrid dry-mass and boundary reconciliation are not captured",
                                "not a closed whole-model water or thermodynamic budget"],
            "identities": {"pre": pre_identity, "post": post_identity,
                           "process": process_identity,
                           "rain_ground_ledger": rain_ground_identity,
                           "numerical_ledgers": numerical_identities,
                           "initial_history_sha256": sha256(wrfout)},
        }


def read_step_changes(path: Path, expected_sha256: str) -> dict[str, Any]:
    """Stream the trace and keep only each step's PRE_RK and POST_KDM6 states."""
    actual_sha256 = sha256(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(f"stage trace hash mismatch: {path}")
    records = 0
    step_changes: dict[str, Any] = {}
    pre_state: dict[str, np.ndarray] | None = None
    pre_step: int | None = None
    active_bounds: tuple[int, ...] | None = None
    with gzip.open(path, "rb") as stream:
        while magic := stream.read(8):
            if len(magic) != 8:
                raise ValueError("truncated stage-trace magic")
            label_raw, header = stream.read(32), stream.read(60)
            if len(label_raw) != 32 or len(header) != 60:
                raise ValueError("truncated stage-trace header")
            label = label_raw.decode("ascii").strip()
            values = struct.unpack(">15i", header)
            kind, timestep, _rkstep = values[:3]
            bounds = values[3:]
            if magic not in (STATE_MAGIC, PBL_MAGIC) or timestep <= 0:
                raise ValueError(f"unexpected trace record {label!r} at step {timestep}")
            names = FIELDS if magic == STATE_MAGIC and kind == 1 else PBL_FIELDS
            if (magic == STATE_MAGIC and kind != 1) or (magic == PBL_MAGIC and kind != 2):
                raise ValueError(f"bad record kind for {label!r} at step {timestep}")
            cells = ((bounds[11] - bounds[10] + 1) *
                     (bounds[9] - bounds[8] + 1) *
                     (bounds[7] - bounds[6] + 1))
            if cells <= 0:
                raise ValueError("invalid active state bounds")
            this_active_bounds = tuple(bounds[6:])
            if magic == STATE_MAGIC:
                if active_bounds is None:
                    active_bounds = this_active_bounds
                elif active_bounds != this_active_bounds:
                    raise ValueError("active stage-trace state bounds changed")
            keep = magic == STATE_MAGIC and label in SELECTED
            fields: dict[str, np.ndarray] = {}
            for name in names:
                raw = stream.read(cells * 4)
                if len(raw) != cells * 4:
                    raise ValueError(f"truncated {label} {name} at step {timestep}")
                if keep:
                    fields[name] = np.frombuffer(raw, dtype=">f4").reshape(
                        bounds[11] - bounds[10] + 1,
                        bounds[9] - bounds[8] + 1,
                        bounds[7] - bounds[6] + 1,
                    ).copy()
            records += 1
            if label == "PRE_RK":
                if pre_state is not None:
                    raise ValueError("PRE_RK occurred before prior POST_KDM6")
                pre_state, pre_step = fields, timestep
            elif label == "POST_KDM6":
                if pre_state is None or pre_step != timestep:
                    raise ValueError(f"POST_KDM6 lacks matching PRE_RK at step {timestep}")
                if set(pre_state) != set(FIELDS) or set(fields) != set(FIELDS):
                    raise ValueError("incomplete state fields")
                field_changes = {name: _change_stats(pre_state[name], fields[name])
                                 for name in FIELDS if name != "DEN"}
                step_changes[str(timestep)] = {
                    "model_seconds": timestep * 20,
                    "active_shape_jki": list(fields["DEN"].shape),
                    "fields": field_changes,
                    "field_groups": {
                        "water_Q_QC_QI_QR_QS_QG": _group_stats(field_changes, WATER_FIELDS),
                        "number_NN_NC_NI_NR": _group_stats(field_changes, NUMBER_FIELDS),
                        "graupel_B_BG": field_changes["BG"],
                    },
                    "rhoDry": {
                        "pre_min": float(np.min(pre_state["DEN"])),
                        "pre_max": float(np.max(pre_state["DEN"])),
                        "post_min": float(np.min(fields["DEN"])),
                        "post_max": float(np.max(fields["DEN"])),
                    },
                }
                pre_state, pre_step = None, None
    if records == 0 or pre_state is not None or set(step_changes) != {"1", "2"}:
        raise ValueError("expected completed PRE_RK/POST_KDM6 pairs for steps 1 and 2")
    if sha256(path) != actual_sha256:
        raise ValueError("stage trace changed during analysis")
    return {"path": str(path), "sha256": actual_sha256, "records": records,
            "active_bounds_ims_ime_jms_jme_kms_kme_its_ite_jts_jte_kts_kte": active_bounds,
            "step_changes": step_changes}


def analyze_arm(arm: str) -> dict[str, Any]:
    run_root = DEFAULT_RUNS[arm]
    receipt_path = run_root.parent / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("status") != "COMPLETE" or receipt.get("timestep_count") != 2:
        raise ValueError(f"{arm}: expected successful two-step receipt")
    trace_name = "pr85_joint_moment_stages.raw.gz"
    compressed = {row["compressed_path"]: row for row in receipt["compressed_outputs"]}
    trace_binding = compressed.get(trace_name)
    if not trace_binding:
        raise ValueError(f"{arm}: receipt does not bind {trace_name}")
    trace = read_step_changes(run_root / trace_name, trace_binding["compressed_sha256"])
    output_file = run_root / "wrfout_d01_2026-08-16_13:00:00"
    input_inventory = {
        name: {"path": str(run_root / name), "sha256": compressed.get(name, {}).get("compressed_sha256")}
        for name in (trace_name, "kdm6_first_call_pre.raw.gz", "kdm6_first_call_post.raw.gz")
    }
    # The WRF history is a single initialization record; it has static map factors
    # and initial P/PB, PH/PHB, U/V/W, but no post-step output or observations.
    history = {"path": str(output_file), "sha256": sha256(output_file),
               **_history_summary(output_file),
               "post_step_pressure_phi_wind_or_observation_signal": False,
               "observation_or_echo_fields": []}
    return {
        "status": "STATE_CHANGES_ONLY_PHYSICAL_INVENTORY_OPEN",
        "arm": arm,
        "receipt": {"path": str(receipt_path), "sha256": sha256(receipt_path),
                    "run_status": receipt["status"], "timesteps": receipt["timestep_count"],
                    "model_timestamps": [x["timestamp"] for x in receipt["model_timestamps"]]},
        "first_kdm6_call_budget": first_call_budget(arm, receipt),
        "stage_trace": trace,
        "geometry_availability": {
            "rhoDry": "captured at every PRE_RK/POST_KDM6 state as DEN",
            "DELZ": "captured in first-call KDM6 PRE/POST files only; not alongside per-step PRE_RK/POST_KDM6 stage states",
            "area": "static map area derivable from initial MAPFAC_MX/MAPFAC_MY and DX*DY",
            "exact_two_step_inventory_changes": False,
            "reason": "endpoint DELZ is absent from the full stage trace, so rhoDry*DELZ*area cannot be applied to both state endpoints without assuming fixed layer thickness",
            "units_of_reported_changes": "native Q/B mixing or moment state units; not kg, particles, or column inventory",
        },
        "observation_signal": history,
        "bound_inputs": input_inventory,
    }


def _first_call_only_result(manifest_path: Path, build_path: Path, runs_path: Path,
                            column_output_dir: Path,
                            allow_incomplete_window: bool = False) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    build = json.loads(build_path.read_text())
    if build.get("status") != "PASS_OVERLAY_BUILD" or not build.get("executable_sha256"):
        raise ValueError("candidate build receipt is missing a passing executable identity")
    candidate_sha = manifest.get("candidate_source_sha256")
    transform_sha = manifest.get("rain_transform", {}).get("output_sha256")
    if transform_sha is not None and candidate_sha != transform_sha:
        raise ValueError("source manifest candidate differs from its rain transform output")
    build_sha = sha256(build_path)
    run_roots = json.loads(runs_path.read_text())
    if set(run_roots) != {"OFF", "COUPLED"}:
        raise ValueError("run map must bind exactly OFF and COUPLED")
    validated: dict[str, tuple[Path, Path, dict[str, Any], dict[str, Any]]] = {}
    for arm, run_value in run_roots.items():
        run_root = Path(run_value)
        receipt_path = run_root.parent / "receipt.json"
        preflight_path = run_root.parent / "preflight.json"
        if not receipt_path.is_file() or not preflight_path.is_file():
            raise ValueError(f"{arm}: expected a completed run receipt and preflight")
        receipt = json.loads(receipt_path.read_text())
        preflight = json.loads(preflight_path.read_text())
        complete = receipt.get("status") == "COMPLETE" and receipt.get("returncode") == 0
        incomplete_with_first_call = (
            receipt.get("status") == "INCOMPLETE" and allow_incomplete_window and
            receipt.get("final_completed_step", 0) >= 1)
        if not complete and not incomplete_with_first_call:
            raise ValueError(f"{arm}: run is incomplete; use the explicit incomplete-window flag for a first-call-only budget")
        if receipt.get("timestep_count", 0) < 1 or receipt.get("final_completed_step", 0) < 1:
            raise ValueError(f"{arm}: receipt contains no completed timesteps")
        preflight_build = preflight.get("candidate_build", {})
        if (preflight_build.get("receipt_sha256") != build_sha or
                preflight_build.get("executable_sha256") != build["executable_sha256"]):
            raise ValueError(f"{arm}: preflight build identity differs from the candidate build receipt")
        receipt_build = receipt.get("candidate_build", {})
        if receipt_build and receipt_build.get("receipt_sha256") != build_sha:
            raise ValueError(f"{arm}: run receipt build identity differs from candidate build receipt")
        for key in ("executed_executable_sha256", "expected_executed_executable_sha256"):
            if receipt.get(key) != build["executable_sha256"]:
                raise ValueError(f"{arm}: run receipt {key} differs from candidate executable")
        if receipt.get("candidate_build_unchanged") is not True:
            raise ValueError(f"{arm}: run did not preserve its candidate build")
        validated[arm] = (run_root, receipt_path, receipt, preflight_path)

    arms: dict[str, Any] = {}
    for arm, (run_root, receipt_path, receipt, preflight_path) in validated.items():
        arms[arm] = {
            "run_root": str(run_root),
            "run_receipt": {"path": str(receipt_path), "sha256": sha256(receipt_path),
                            "status": receipt["status"], "returncode": receipt["returncode"],
                            "timestep_count": receipt["timestep_count"],
                            "final_completed_step": receipt["final_completed_step"],
                            "earliest_fatal": receipt.get("earliest_fatal"),
                            "model_timestamps": receipt.get("model_timestamps", []),
                            "frozen_executable_sha256": receipt.get("frozen_executable_sha256"),
                            "executed_executable_sha256": receipt.get("executed_executable_sha256"),
                            "candidate_build_unchanged": receipt.get("candidate_build_unchanged")},
            "preflight": {"path": str(preflight_path), "sha256": sha256(preflight_path)},
            "first_call_budget": first_call_budget(
                arm, receipt, run_root=run_root, column_output_dir=column_output_dir,
                allow_single_cutoff_sweep=(receipt.get("status") != "COMPLETE")),
        }
    return {
        "schema": "pr87_candidate_first_call_budget_v1",
        "status": ("FIRST_KDM6_CALL_ACCOUNTED_PARTIAL_BUDGET_OPEN" if
                   all(x[2].get("status") == "COMPLETE" for x in validated.values()) else
                   "FIRST_KDM6_CALL_ACCOUNTED_FROM_INCOMPLETE_RUN_WINDOW"),
        "complete_run_window": all(x[2].get("status") == "COMPLETE" for x in validated.values()),
        "source_manifest": {"path": str(manifest_path), "sha256": sha256(manifest_path),
                            "identity": manifest.get("identity"),
                            "candidate_source_sha256": candidate_sha,
                            "rain_transform": manifest.get("rain_transform")},
        "build": {"path": str(build_path), "sha256": build_sha,
                  "status": build["status"], "identity": build.get("identity"),
                  "executable_path": build.get("executable_path"),
                  "executable_sha256": build["executable_sha256"],
                  "compiler_profile_path": build.get("profile_path"),
                  "compiler_profile_sha256": build.get("profile_sha256")},
        "arms": arms,
        "science_status": "OPEN; first-call partial budget only, not a closed whole-model budget",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--first-call-only", action="store_true",
                        help="write only a receipt-bound first-call comparison for explicit candidate runs")
    parser.add_argument("--source-manifest", type=Path,
                        help="candidate source manifest for --first-call-only")
    parser.add_argument("--candidate-build", type=Path,
                        help="passing build receipt for --first-call-only")
    parser.add_argument("--runs-json", type=Path,
                        help="JSON object mapping OFF and COUPLED to explicit run directories")
    parser.add_argument("--column-output-dir", type=Path,
                        help="separate directory for compressed 2D column maps")
    parser.add_argument("--allow-incomplete-window-for-first-call", action="store_true",
                        help="permit first-call accounting from receipt-bound captures when the full model window failed")
    args = parser.parse_args()
    if args.first_call_only:
        required = (args.source_manifest, args.candidate_build, args.runs_json, args.column_output_dir)
        if any(value is None for value in required):
            parser.error("--first-call-only requires --source-manifest, --candidate-build, --runs-json, and --column-output-dir")
        result = _first_call_only_result(args.source_manifest, args.candidate_build,
                                         args.runs_json, args.column_output_dir,
                                         args.allow_incomplete_window_for_first_call)
        output = args.output
        if output.suffix.lower() != ".json":
            output = output / "candidate_first_call_budget.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(output)
        return
    args.output.mkdir(parents=True, exist_ok=True)
    result = {"schema": "pr87_v42_state_budget_availability_v1",
              "source_manifest": "/var/tmp/pr87_joint_cycle_sources_20261016_v42/sources.json",
              "source_manifest_sha256": sha256(Path("/var/tmp/pr87_joint_cycle_sources_20261016_v42/sources.json")),
              "arms": {arm: analyze_arm(arm) for arm in ("OFF", "COUPLED")}}
    output = args.output / "v42_two_step_budget.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(output)


if __name__ == "__main__":
    main()
