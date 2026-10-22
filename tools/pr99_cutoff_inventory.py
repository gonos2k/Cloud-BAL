#!/usr/bin/env python3
"""Compare source-recorded T1 cutoff removals with pre-call condensate inventory."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import pr94_cloud_response as cloud  # noqa: E402
from native_kdm6_trace import read_dump  # noqa: E402
from pr95_call_budget import _read_map_geometry  # noqa: E402
from pr98_budget import cutoff_columns  # noqa: E402

ARMS = ("OFF", "HYDRO", "COUPLED")
SPECIES = ("QC", "QI", "QR", "QS", "QG")
COMPOSITION = ROOT / "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json"
FACE_EVIDENCE = ROOT / "docs/evidence/pr98_t1_residual_20261022"
REPLAY_EVIDENCE = ROOT / "docs/evidence/pr98_t1_residual_20261022"


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sum_values(values: np.ndarray) -> float:
    return math.fsum(float(value) for value in values.flat)


def validate_pre_call_fields(density: np.ndarray, thickness: np.ndarray,
                             condensates: dict[str, np.ndarray]) -> None:
    """Validate every active geometry and condensate value before weighting."""
    if not np.isfinite(density).all() or np.any(density <= 0.0):
        raise ValueError("active DEN values must be finite and positive")
    if not np.isfinite(thickness).all() or np.any(thickness <= 0.0):
        raise ValueError("active DELZ values must be finite and positive")
    for name in SPECIES:
        values = condensates[name]
        if not np.isfinite(values).all() or np.any(values < 0.0):
            raise ValueError(f"active pre-call {name} values must be finite and nonnegative")


def weighted_removal(before: float, after: float, layer_weight: float) -> float:
    delta = before - after
    if delta < 0.0 or not math.isfinite(delta * layer_weight) or layer_weight <= 0.0:
        raise ValueError("cutoff removal and layer weight must be finite and nonnegative")
    return delta * layer_weight


def region_summary(inventory: np.ndarray, removed: np.ndarray,
                   species_events: np.ndarray, any_events: np.ndarray,
                   region: np.ndarray, event_max: np.ndarray) -> dict[str, Any]:
    """Report removal and inventory on an explicit native (k,j,i) mask."""
    if region.shape != inventory.shape[1:]:
        raise ValueError("region mask must match native (k,j,i) state")
    removal_by_species = []
    inventory_by_species = []
    ratio_by_species = []
    count_by_species = []
    voxel_count_by_species = []
    max_by_species = []
    for species_index in range(len(SPECIES)):
        removed_kg = sum_values(removed[species_index][region])
        inventory_kg = sum_values(inventory[species_index][region])
        removal_by_species.append(removed_kg)
        inventory_by_species.append(inventory_kg)
        ratio_by_species.append(removed_kg / inventory_kg if inventory_kg > 0.0 else None)
        count_by_species.append(int(np.sum(species_events[species_index][region], dtype=np.int64)))
        voxel_count_by_species.append(int(np.count_nonzero((species_events[species_index] > 0) & region)))
        max_by_species.append(float(np.max(event_max[species_index][region])) if np.any(region) else 0.0)
    total_removed = math.fsum(removal_by_species)
    total_inventory = math.fsum(inventory_by_species)
    return {
        "selected_native_cells": int(np.count_nonzero(region)),
        "removed_by_species_kg": dict(zip(SPECIES, removal_by_species, strict=True)),
        "pre_call_inventory_by_species_kg": dict(zip(SPECIES, inventory_by_species, strict=True)),
        "removed_to_pre_inventory_ratio_by_species": dict(zip(SPECIES, ratio_by_species, strict=True)),
        "total_condensate_removed_kg": total_removed,
        "total_condensate_pre_call_inventory_kg": total_inventory,
        "total_removed_to_pre_inventory_ratio": total_removed / total_inventory if total_inventory > 0.0 else None,
        "cutoff_event_rows_by_species": dict(zip(SPECIES, count_by_species, strict=True)),
        "distinct_cutoff_cells_by_species": dict(zip(SPECIES, voxel_count_by_species, strict=True)),
        "max_single_event_removal_kg_by_species": dict(zip(SPECIES, max_by_species, strict=True)),
        "signed_store_change_kg_by_species": {name: -value for name, value in zip(SPECIES, removal_by_species, strict=True)},
        "L1_removal_kg_by_species": dict(zip(SPECIES, removal_by_species, strict=True)),
        "any_species_cutoff_cells": int(np.count_nonzero(any_events & region)),
    }


def validate_manifest(arm: str, replay_path: Path, face_path: Path,
                      run_dir: Path) -> tuple[dict, dict, Path, Path, Path]:
    replay = json.loads(replay_path.read_text())
    face = json.loads(face_path.read_text())
    cutoff = run_dir / "pr85_kdm6_cutoff_budget.raw"
    pre = run_dir / "kdm6_first_call_pre.raw"
    post = run_dir / "kdm6_first_call_post.raw"
    executable = run_dir / "replay.exe"
    if replay.get("schema") != "pr98_isolated_c1_t1_replay_v1" or replay.get("returncode") != 0:
        raise ValueError(f"{arm} replay receipt is incomplete")
    if face.get("schema") != "pr98_face_replay_v1" or not face.get("completion_marker_observed"):
        raise ValueError(f"{arm} face receipt lacks the full-tile completion marker")
    if face.get("arm") != arm or not face.get("all_17_fields_and_XLAND_byte_equal"):
        raise ValueError(f"{arm} face receipt has wrong arm or changed native state")
    expected = {
        "input_pre_sha256": checksum(pre),
        "native_post_sha256": checksum(post),
        "replay_post_sha256": checksum(run_dir / "replay_post.raw"),
        "cutoff_rows_sha256": checksum(cutoff),
    }
    if any(replay.get(key) != value for key, value in expected.items()):
        raise ValueError(f"{arm} replay receipt hash mismatch")
    if checksum(executable) != replay.get("executable_before_sha256") or \
            replay.get("executable_before_sha256") != replay.get("executable_after_sha256"):
        raise ValueError(f"{arm} frozen replay executable hash mismatch")
    face_expected = {
        "pre_sha256": expected["input_pre_sha256"],
        "native_post_sha256": expected["native_post_sha256"],
        "replay_post_sha256": expected["replay_post_sha256"],
        "cutoff_rows_sha256": expected["cutoff_rows_sha256"],
    }
    if any(face.get(key) != value for key, value in face_expected.items()):
        raise ValueError(f"{arm} face receipt disagrees with replay receipt")
    if replay.get("row_counts", {}).get("cutoff_events") != sum(
            line.startswith("PR85_KDM6_CUTOFF") for line in cutoff.read_text().splitlines()):
        raise ValueError(f"{arm} cutoff row count differs from replay receipt")
    history = Path(face["history_path"])
    if checksum(history) != face.get("history_sha256"):
        raise ValueError(f"{arm} receipt-bound history changed")
    prepared_source = Path(face["prepared_source_path"])
    if checksum(prepared_source) != face.get("prepared_source_sha256"):
        raise ValueError(f"{arm} receipt-bound cutoff writer source changed")
    return replay, face, pre, cutoff, history


def analyze_arm(arm: str, replay_path: Path, face_path: Path,
                composition: dict[str, Any]) -> dict[str, Any]:
    replay = json.loads(replay_path.read_text())
    run_dir = Path(replay["scratch_directory"])
    replay, face, pre_path, cutoff_path, history = validate_manifest(
        arm, replay_path, face_path, run_dir)
    pre = read_dump(pre_path)
    bounds = pre["bounds"]
    if pre["stage"] != 1 or pre["itimestep"] != 1:
        raise ValueError(f"{arm} pre-call state is not the first KDM6 call")
    density = pre["fields"]["DEN"].astype(np.float64)
    thickness = pre["fields"]["DELZ"].astype(np.float64)
    condensates = {name: pre["fields"][name].astype(np.float64) for name in SPECIES}
    expected = (bounds["jte"] - bounds["jts"] + 1,
                bounds["kte"] - bounds["kts"] + 1,
                bounds["ite"] - bounds["its"] + 1)
    with netCDF4.Dataset(history) as dataset:
        dataset.set_auto_mask(False)
        area, _, _ = _read_map_geometry(
            dataset, slice(bounds["jts"] - 1, bounds["jte"]),
            slice(bounds["its"] - 1, bounds["ite"]))
    if density.shape != expected or thickness.shape != expected or area.shape != (expected[0], expected[2]):
        raise ValueError(f"{arm} state and map area shapes disagree")
    if any(values.shape != expected for values in condensates.values()):
        raise ValueError(f"{arm} condensate and map geometry shapes disagree")
    validate_pre_call_fields(density, thickness, condensates)
    weights = density * thickness * area[:, None, :]
    state_shape = (expected[1], expected[0], expected[2])
    support = cloud.make_masks(composition, state_shape)
    support_mask = support["original_613_native_support"]
    buffer_mask = support["fixed_5_cell_chebyshev_buffer"]
    if int(support_mask.sum()) != 613 or int(buffer_mask.any(axis=0).sum()) != 196:
        raise ValueError("source-defined QC support or five-cell buffer count changed")
    # Source records I/J/K as one-based model coordinates. Convert once into
    # the cropped active-array coordinates used by the native dump and area.
    offsets = {"i": bounds["its"], "j": bounds["jts"], "k": bounds["kts"]}
    removed = np.zeros((len(SPECIES), *state_shape), dtype=np.float64)
    event_counts = np.zeros((len(SPECIES), *state_shape), dtype=np.int32)
    event_max = np.zeros((len(SPECIES), *state_shape), dtype=np.float64)
    seen: set[tuple[int, int, int, int]] = set()
    event_rows = 0
    with cutoff_path.open(encoding="ascii") as stream:
        for line in stream:
            if not line.startswith("PR85_KDM6_CUTOFF"):
                continue
            fields = line.split()
            if len(fields) != 33:
                raise ValueError(f"invalid {arm} cutoff row width")
            i, j, k, loop, mask = map(int, fields[1:6])
            ji = (j - offsets["j"], i - offsets["i"])
            ki = (k - offsets["k"], *ji)
            if not (0 <= ki[0] < state_shape[0] and 0 <= ji[0] < expected[0] and
                    0 <= ji[1] < expected[2] and loop >= 1):
                raise ValueError(f"{arm} cutoff coordinate outside active state")
            key = (i, j, k, loop)
            if key in seen:
                raise ValueError(f"duplicate {arm} cutoff assignment row")
            seen.add(key)
            values = np.asarray(fields[6:31], dtype=np.float64)
            if not np.isfinite(values).all():
                raise ValueError(f"nonfinite {arm} cutoff operand")
            if values[0] != float(density[ji[0], ki[0], ji[1]]):
                raise ValueError(f"{arm} cutoff density differs from same-call DEN")
            qmin, qcrmin = values[1:3]
            before, after = values[3:8], values[8:13]
            expected_mask = sum(bit for bit, q, threshold in zip(
                (1, 2, 4, 8, 16), before, (qmin, qmin, qcrmin, qcrmin, qcrmin), strict=True)
                if q <= threshold)
            if mask != expected_mask:
                raise ValueError(f"{arm} cutoff threshold mask mismatch")
            for species_index, (old, new) in enumerate(zip(before, after, strict=True)):
                if old <= (qmin if species_index < 2 else qcrmin):
                    if new != 0.0:
                        raise ValueError(f"{arm} cutoff did not clear thresholded {SPECIES[species_index]}")
                elif new != old:
                    raise ValueError(f"{arm} cutoff changed above-threshold {SPECIES[species_index]}")
                delta = weighted_removal(
                    float(old), float(new), float(weights[ji[0], ki[0], ji[1]]))
                removed[(species_index, *ki)] += delta
                if delta > 0.0:
                    event_counts[(species_index, *ki)] += 1
                    event_max[(species_index, *ki)] = max(event_max[(species_index, *ki)], delta)
            event_rows += 1
    # Reuse the existing validated reducer as a separate per-column check.
    existing_cutoff_columns, _, _, _ = cutoff_columns(
        cutoff_path, bounds, density, thickness, area)
    if event_rows != replay["row_counts"]["cutoff_events"]:
        raise ValueError(f"{arm} cutoff parser row count disagrees with replay receipt")
    inventory = np.stack([condensates[name].transpose(1, 0, 2) * weights.transpose(1, 0, 2)
                          for name in SPECIES])
    species_event_masks = event_counts > 0
    any_event_mask = np.any(species_event_masks, axis=0)
    all_cells = np.ones(state_shape, dtype=bool)
    common_regions = {
        "full_active_tile": all_cells,
        "exact_613_source_composition_support": support_mask,
        "fixed5_buffer_all_39_levels_196_columns": buffer_mask,
        "union_of_cutoff_event_cells": any_event_mask,
    }
    regions = {name: region_summary(inventory, removed, event_counts,
                                    any_event_mask, mask, event_max)
               for name, mask in common_regions.items()}
    species_footprints = {}
    for species_index, species_name in enumerate(SPECIES):
        mask = species_event_masks[species_index]
        species_footprints[species_name] = {
            "selected_native_cells": int(mask.sum()),
            "removed_kg": sum_values(removed[species_index][mask]),
            "pre_call_same_species_inventory_kg": sum_values(inventory[species_index][mask]),
            "removed_to_pre_inventory_context_ratio": (
                sum_values(removed[species_index][mask]) /
                sum_values(inventory[species_index][mask])
                if sum_values(inventory[species_index][mask]) > 0.0 else None),
            "cutoff_event_rows": int(event_counts[species_index].sum()),
        }
    return {
        "arm": arm,
        "source_scope": "T1 per-level qmin/qcrmin cleanup; positive removal amounts are source-recorded Qbefore-Qafter",
        "inventory_scope": "pre-call condensates QC,QI,QR,QS,QG only; QV excluded",
        "measure": "R64 input DEN * DELZ * receipt-bound history map area; source values are Q kg/kg dry",
        "state_bounds": bounds,
        "event_rows": event_rows,
        "independent_column_reducer_crosscheck": {
            "levelwise_signed_store_change_kg": -sum_values(removed),
            "existing_PR98_column_reducer_signed_store_change_kg": sum_values(existing_cutoff_columns),
            "signed_difference_kg": -sum_values(removed) - sum_values(existing_cutoff_columns),
        },
        "regions": regions,
        "species_specific_cutoff_footprints": species_footprints,
        "bindings": {
            "replay_manifest_sha256": checksum(replay_path),
            "face_manifest_sha256": checksum(face_path),
            "pre_state_sha256": checksum(pre_path),
            "cutoff_rows_sha256": checksum(cutoff_path),
            "history_sha256": checksum(history),
            "executable_sha256": replay["executable_before_sha256"],
            "face_replay_executable_sha256": face["executable_sha256"],
            "prepared_source_sha256": face["prepared_source_sha256"],
            "prepared_source_path": face["prepared_source_path"],
            "original_diagnostic_source_sha256": face["original_pr97_diagnostic_source_sha256"],
            "observer_source_sha256": face["observer_source_sha256"],
            "replay_returncode": replay["returncode"],
            "full_tile_completion_marker_observed": face["completion_marker_observed"],
            "all_17_fields_and_XLAND_byte_equal": face["all_17_fields_and_XLAND_byte_equal"],
            "source_composition_sha256": checksum(COMPOSITION),
        },
        "interpretation": "Removal/pre-call inventory ratios are contextual ratios, not fractions of initial cloud lost; species may form, convert, replenish, or be removed repeatedly during the call.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    composition = json.loads(COMPOSITION.read_text())["composed_qc_vertical_influence"]
    arms = {}
    for arm in ARMS:
        arms[arm] = analyze_arm(
            arm,
            REPLAY_EVIDENCE / f"{arm}_replay_manifest.json",
            FACE_EVIDENCE / f"{arm}_face_replay_manifest.json",
            composition,
        )
    result = {
        "schema": "pr99_cutoff_inventory_context_v1",
        "date": "2026-10-22",
        "arms": arms,
        "scope_limits": [
            "This measures a numerical threshold cleanup in one KDM6 call; it is not a phase-change attribution.",
            "No cutoff removal is inferred where the source ledger has no threshold-assignment event.",
            "The 613-cell mask is the source-composed native QC support; the 196-column five-cell buffer includes every native level in those columns.",
            "No percentage is described as the fraction of cloud physically lost; inventories are pre-call context only.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"schema": result["schema"], "output": str(args.output),
                      "arms": {arm: {"event_rows": row["event_rows"],
                                    "full_tile": row["regions"]["full_active_tile"]["total_condensate_removed_kg"],
                                    "support": row["regions"]["exact_613_source_composition_support"]["total_condensate_removed_kg"],
                                    "buffer": row["regions"]["fixed5_buffer_all_39_levels_196_columns"]["total_condensate_removed_kg"]}
                               for arm, row in arms.items()}}, indent=2))


if __name__ == "__main__":
    main()
