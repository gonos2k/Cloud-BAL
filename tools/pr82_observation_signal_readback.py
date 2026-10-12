#!/usr/bin/env python3
"""Read back PR81 cloud-water signal against the retained analyzed LWC input."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset

from cp06a_thermo_density_readback import preprior_condensate_fields


RD_AIR = 287.05
EPSILON_WATER = 0.622
SPECIES = ("cloud_water", "cloud_ice", "rain", "snow", "graupel")
LWC_UNITS = "kg m-3"
PRESSURE_UNITS = ("Pa",)
TEMPERATURE_UNITS = ("K",)
MIXING_RATIO_UNITS = ("kg kg-1 dryair",)
DRY_AIR_MASS_UNITS = ("kg dryair",)
# The pre-density vector is a saved cell mass, unlike the per-grid-cell
# candidate measure whose metadata explicitly identifies dry-air mass.
PREPRIOR_DRY_MASS_UNITS = ("kg",)
MODELED_UNIT_CONTRACT = {
    "pressure": "Pa; required on every opened candidate before EOS",
    "temperature": "K; required on the selected background/candidate/pre-density state",
    "vapor_and_five_condensates": "kg kg-1 dryair",
    "candidate_dry_air_mass_measure": "kg dryair",
    "pre_density_dry_mass_vector": "kg; explicit exception because this saved vector stores absolute cell mass",
}
LWC_OPERATOR = {
    "name": "direct_dry_air_cloud_water_to_volumetric_LWC",
    "equation": "H(x)=rho_d(p,T,qv)*qc; rho_d=p/[287.05*T*(1+qv/0.622)]",
    "units": {"H": LWC_UNITS, "y": LWC_UNITS, "residual": LWC_UNITS},
    "source": "src/common/cloud_bal_real_netcdf.f90 read_real_shadow_state/read_and_assign_hydrometeor/dry_density",
    "source_lines": "499-503, 4021-4056, 4371-4378",
    "observation_product": "processed LWC analysis product, not independent raw observation",
    "fit_scope": "unweighted raw-unit consistency residual only; no R, covariance, or independent observation-fit claim",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_new_output_path(path: Path) -> Path:
    output = Path(os.path.abspath(path))
    for component in reversed((output, *output.parents)):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"output path contains a symlink: {component}")
        if component == output:
            raise FileExistsError(f"refusing to overwrite existing output: {output}")
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"output parent is not a directory: {component}")
    return output


def write_new_json(path: Path, value: dict[str, Any]) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    output = _validate_new_output_path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Check again after creating the directory tree and let exclusive creation
    # close the leaf-level race without replacing an existing receipt.
    output = _validate_new_output_path(output)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(payload)


def read_array(dataset: Dataset, name: str) -> np.ndarray:
    value = dataset.variables[name][:]
    if np.ma.isMaskedArray(value):
        value = value.filled(np.nan if np.issubdtype(value.dtype, np.floating) else 0)
    return np.asarray(value)


def read_binary_mask(dataset: Dataset, name: str) -> np.ndarray:
    """Read a strict 0/1 mask without converting missing/fill values to false."""
    variable = dataset.variables[name]
    raw = variable[:]
    if np.ma.isMaskedArray(raw):
        if np.any(np.ma.getmaskarray(raw)):
            raise ValueError(f"{name} contains masked/fill values")
        raw = raw.data
    values = np.asarray(raw)
    if not np.all(np.isfinite(values)) or not np.all((values == 0) | (values == 1)):
        raise ValueError(f"{name} must contain only finite binary 0/1 values")
    return values.astype(bool)


def require_units(dataset: Dataset, name: str, accepted: tuple[str, ...],
                  physical_quantity: str) -> None:
    variable = dataset.variables[name]
    actual = " ".join(str(getattr(variable, "units", "")).lower().split())
    expected = {" ".join(unit.lower().split()) for unit in accepted}
    if not actual or actual not in expected:
        allowed = ", ".join(repr(unit) for unit in accepted)
        raise ValueError(
            f"{name} has missing or unsupported units {actual!r} for {physical_quantity}; "
            f"accepted: {allowed}"
        )


def validate_mask_set(label: str, masks: dict[str, np.ndarray],
                      above_ground: np.ndarray) -> None:
    for name, mask in masks.items():
        if mask.shape != above_ground.shape:
            raise ValueError(f"{label} {name} shape differs from above-ground mask")
    support = masks["analysis_support"]
    if np.any(support & ~above_ground):
        raise ValueError(f"{label} analysis support is not a subset of above-ground")
    radar_echo = masks["radar_valid"]
    radar_no_echo = masks["radar_no_echo"]
    radar_missing = masks["radar_missing"]
    if np.any(radar_echo & radar_no_echo) or np.any((radar_echo | radar_no_echo) & radar_missing):
        raise ValueError(f"{label} radar signal masks overlap")
    if not np.array_equal(radar_echo | radar_no_echo | radar_missing, above_ground):
        raise ValueError(f"{label} radar signal masks do not partition above-ground")


def validate_fixed_common_masks(reference: dict[str, np.ndarray],
                               candidate: dict[str, np.ndarray], label: str) -> None:
    for name, reference_mask in reference.items():
        if name not in candidate or not np.array_equal(reference_mask, candidate[name]):
            raise ValueError(f"{label} changed common mask {name}")


def dry_air_density(pressure: np.ndarray, temperature: np.ndarray,
                    vapor: np.ndarray,
                    valid_mask: np.ndarray | None = None) -> np.ndarray:
    """Mirror cloud_bal_real_netcdf::dry_density in kg dry air per m3."""
    pressure, temperature, vapor = np.broadcast_arrays(pressure, temperature, vapor)
    domain = np.ones(pressure.shape, dtype=bool) if valid_mask is None else np.broadcast_to(valid_mask, pressure.shape)
    physical = (np.isfinite(pressure) & np.isfinite(temperature) & np.isfinite(vapor) &
                (pressure > 0.0) & (temperature > 0.0) & (vapor >= 0.0))
    if np.any(domain & ~physical):
        raise ValueError("pressure, temperature, and vapor must be finite and physical before EOS")
    density = np.zeros(pressure.shape, dtype=np.float64)
    denominator = RD_AIR * temperature * (1.0 + vapor / EPSILON_WATER)
    np.divide(pressure, denominator, out=density, where=domain)
    return density


def validate_state_fields(label: str, pressure: np.ndarray, temperature: np.ndarray,
                          vapor: np.ndarray, condensates: dict[str, np.ndarray],
                          dry_mass: np.ndarray, above_ground: np.ndarray) -> None:
    """Reject invalid modeled thermodynamics on the physical domain only."""
    if set(condensates) != set(SPECIES):
        raise ValueError(f"{label} does not contain exactly the five condensate species")
    fields = {"pressure": pressure, "temperature": temperature, "vapor": vapor,
              "dry_air_mass_measure": dry_mass, **condensates}
    for name, values in fields.items():
        if values.shape != above_ground.shape:
            raise ValueError(f"{label} {name} shape differs from above-ground mask")
        selected = values[above_ground]
        if not np.all(np.isfinite(selected)):
            raise ValueError(f"{label} {name} is non-finite above ground")
        if name in {"pressure", "temperature", "dry_air_mass_measure"}:
            if np.any(selected <= 0.0):
                raise ValueError(f"{label} {name} must be positive above ground")
        elif np.any(selected < 0.0):
            raise ValueError(f"{label} {name} must be nonnegative above ground")


def residual_summary(residual: np.ndarray, mask: np.ndarray) -> dict[str, Any]:
    values = np.asarray(residual, dtype=np.float64)[mask]
    if not values.size:
        raise ValueError("observation footprint is empty")
    absolute = np.abs(values)
    return {
        "count": int(values.size),
        "bias": float(np.mean(values)),
        "mae": float(np.mean(absolute)),
        "rmse": float(np.sqrt(np.mean(values * values))),
        "max_abs": float(np.max(absolute)),
        "p95_abs": float(np.percentile(absolute, 95)),
        "p99_abs": float(np.percentile(absolute, 99)),
        "p99_9_abs": float(np.percentile(absolute, 99.9)),
        "count_abs_gt_1e-6": int(np.count_nonzero(absolute > 1.0e-6)),
    }


def source_input(input_json: Path) -> tuple[dict[str, Any], Path, str]:
    declaration = json.loads(input_json.read_text(encoding="utf-8"))
    raw_path = Path(declaration["processed_paths"]["lwc"])
    expected_hash = declaration["input_hashes"].get(str(raw_path))
    if expected_hash is None:
        raise ValueError("input manifest does not pin the processed LWC product")
    actual_hash = sha256(raw_path)
    if actual_hash != expected_hash:
        raise ValueError(f"LWC product SHA-256 mismatch: {actual_hash} != {expected_hash}")
    return declaration, raw_path, actual_hash


def load_lwc(raw_path: Path, shape: tuple[int, ...], expected_time: int) -> tuple[np.ndarray, np.ndarray]:
    with Dataset(raw_path) as dataset:
        if tuple(len(dataset.dimensions[name]) for name in ("z", "y", "x")) != shape:
            raise ValueError("LWC dimensions differ from the candidate grid")
        units = getattr(dataset.variables["lwc"], "units", "")
        if units.strip().lower() not in {"kg/meter**3", "kg/m**3"}:
            raise ValueError(f"unsupported LWC units: {units!r}")
        valid_time = int(np.asarray(dataset.variables["valtime"][:]).reshape(-1)[0])
        if valid_time != expected_time:
            raise ValueError("LWC valid time differs from retained candidate")
        raw = read_array(dataset, "lwc")[0, ::-1, :, :].astype(np.float64)
    valid = np.isfinite(raw) & (np.abs(raw) < 1.0e30) & (raw >= 0.0)
    return np.where(valid, raw, 0.0), valid


def summary_state(dataset: Dataset, label: str,
                  observation: np.ndarray, obs_mask: np.ndarray,
                  echo_mask: np.ndarray, no_echo_mask: np.ndarray,
                  mode: str = "candidate",
                  analysis_support: np.ndarray | None = None) -> dict[str, Any]:
    above_ground = read_binary_mask(dataset, "above_ground")
    pressure = read_array(dataset, "pressure").astype(np.float64)
    if pressure.ndim == 1:
        pressure = np.broadcast_to(pressure[:, None, None], above_ground.shape)

    def field(name: str) -> np.ndarray:
        return read_array(dataset, name).astype(np.float64)

    def state_field(name: str, units: tuple[str, ...], quantity: str) -> np.ndarray:
        require_units(dataset, name, units, quantity)
        return field(name)

    if mode == "background":
        temperature = state_field("background_temperature", TEMPERATURE_UNITS, "temperature")
        vapor = state_field("background_vapor", MIXING_RATIO_UNITS, "water-vapor mixing ratio")
        condensates = {name: state_field(f"background_{name}", MIXING_RATIO_UNITS,
                                         f"{name} mixing ratio") for name in SPECIES}
        dry_mass = state_field("dry_air_mass_measure", DRY_AIR_MASS_UNITS, "dry-air cell mass")
    elif mode == "pre_density":
        temperature = state_field("thermo_preprior_temperature", TEMPERATURE_UNITS,
                                  "pre-density temperature")
        vapor = state_field("thermo_preprior_vapor", MIXING_RATIO_UNITS,
                            "pre-density water-vapor mixing ratio")
        support = read_binary_mask(dataset, "analysis_support")
        final_condensates = tuple(state_field(f"candidate_{name}", MIXING_RATIO_UNITS,
                                              f"{name} mixing ratio") for name in SPECIES)
        pre_condensates = preprior_condensate_fields(dataset, support, final_condensates)
        condensates = dict(zip(SPECIES, pre_condensates))
        indices = list(zip(*np.where(support)))
        dry_mass = state_field("candidate_dry_air_mass_measure", DRY_AIR_MASS_UNITS,
                               "candidate dry-air cell mass")
        require_units(dataset, "thermo_preprior_dry_air_mass_measure",
                      PREPRIOR_DRY_MASS_UNITS, "saved pre-density cell mass")
        pre_mass = field("thermo_preprior_dry_air_mass_measure")
        if pre_mass.shape != (len(indices),):
            raise ValueError("saved pre-density dry-mass vector has the wrong shape")
        for mass, index in zip(pre_mass, indices):
            dry_mass[index] = mass
    else:
        temperature = state_field("candidate_temperature", TEMPERATURE_UNITS, "temperature")
        vapor = state_field("candidate_vapor", MIXING_RATIO_UNITS, "water-vapor mixing ratio")
        condensates = {name: state_field(f"candidate_{name}", MIXING_RATIO_UNITS,
                                         f"{name} mixing ratio") for name in SPECIES}
        dry_mass = state_field("candidate_dry_air_mass_measure", DRY_AIR_MASS_UNITS,
                               "dry-air cell mass")

    validate_state_fields(label, pressure, temperature, vapor, condensates,
                          dry_mass, above_ground)
    density = dry_air_density(pressure, temperature, vapor, above_ground)
    cell_volume = np.divide(dry_mass, density, out=np.zeros_like(dry_mass), where=density > 0)
    state_lwc = density * condensates["cloud_water"]
    if not np.all(np.isfinite(state_lwc[obs_mask])):
        raise ValueError(f"{label} has non-finite cloud-water signal on the common footprint")

    masks = {
        "domain": above_ground,
        "lwc_product": obs_mask,
        "radar_echo": echo_mask,
        "radar_no_echo": no_echo_mask,
    }
    masses: dict[str, np.ndarray] = {
        **condensates,
        "vapor": vapor,
        "liquid_total": condensates["cloud_water"] + condensates["rain"],
        "ice_total": condensates["cloud_ice"] + condensates["snow"] + condensates["graupel"],
    }
    masses["total_water"] = masses["vapor"] + masses["liquid_total"] + masses["ice_total"]
    residual = state_lwc - observation
    residual_groups = {
        "all_valid_above_ground": obs_mask,
        "positive_lwc_only": obs_mask & (observation > 0.0),
    }
    if analysis_support is not None:
        residual_groups["analysis_support"] = obs_mask & analysis_support
        residual_groups["outside_analysis_support"] = obs_mask & ~analysis_support
    result: dict[str, Any] = {
        "label": label,
        "lwc_analysis_product_residual_kg_m3": {
            **{name: residual_summary(residual, mask) for name, mask in residual_groups.items()},
            "interpretation": "source-linked direct state consistency against an analyzed LWC input product; not independent observation fit",
        },
        "hydrometeor_and_vapor": {},
        "dry_air_and_total_moist_mass_kg": {},
    }
    for name, mixing_ratio in masses.items():
        concentration = density * mixing_ratio
        result["hydrometeor_and_vapor"][name] = {
            mask_name: {
                "cells": int(np.count_nonzero(mask)),
                "mass_kg": float(np.sum(mixing_ratio[mask] * dry_mass[mask], dtype=np.float64)),
                "volume_mean_concentration_kg_m3": float(
                    np.sum(concentration[mask] * cell_volume[mask], dtype=np.float64) /
                    np.sum(cell_volume[mask], dtype=np.float64)) if np.any(mask) else None,
            }
            for mask_name, mask in masks.items()
        }
    for mask_name, mask in masks.items():
        dry_air_mass = float(np.sum(dry_mass[mask], dtype=np.float64))
        total_water_mass = float(np.sum(masses["total_water"][mask] * dry_mass[mask], dtype=np.float64))
        result["dry_air_and_total_moist_mass_kg"][mask_name] = {
            "dry_air_mass": dry_air_mass,
            "total_water_mass": total_water_mass,
            "total_moist_air_mass": dry_air_mass + total_water_mass,
        }
    return result


def analyze(paths: dict[str, Path], input_json: Path) -> dict[str, Any]:
    input_declaration_hash = sha256(input_json)
    declaration, lwc_path, lwc_hash = source_input(input_json)
    datasets: dict[str, Dataset] = {}
    hashes: dict[str, str] = {}
    try:
        for label, path in paths.items():
            if not path.is_file():
                raise ValueError(f"missing retained candidate: {path}")
            hashes[label] = sha256(path)
            datasets[label] = Dataset(path)

        reference = datasets["pr81_final"]
        shape = tuple(len(reference.dimensions[name]) for name in ("z", "y", "x"))
        expected_time = int(reference.getncattr("valid_time_epoch"))
        if expected_time != int(declaration["valid_time_epoch"]):
            raise ValueError("retained candidate time differs from input declaration")
        reference_masks = {
            name: read_binary_mask(reference, name)
            for name in ("above_ground", "analysis_support", "radar_valid", "radar_no_echo", "radar_missing")
        }
        above_ground = reference_masks["above_ground"]
        analysis_support = reference_masks["analysis_support"]
        validate_mask_set("reference", reference_masks, above_ground)
        for label, dataset in datasets.items():
            if tuple(len(dataset.dimensions[name]) for name in ("z", "y", "x")) != shape:
                raise ValueError(f"{label} grid dimensions differ")
            if int(dataset.getncattr("valid_time_epoch")) != expected_time:
                raise ValueError(f"{label} valid time differs")
            candidate_masks = {
                name: read_binary_mask(dataset, name)
                for name in reference_masks
            }
            validate_mask_set(label, candidate_masks, above_ground)
            validate_fixed_common_masks(reference_masks, candidate_masks, label)
            require_units(dataset, "pressure", PRESSURE_UNITS, "pressure")
            for name in ("pressure", "radar_dbz"):
                if not np.array_equal(read_array(reference, name), read_array(dataset, name)):
                    raise ValueError(f"{label} changed common observation/grid field {name}")

        above_ground = reference_masks["above_ground"]
        analysis_support = reference_masks["analysis_support"]
        radar_dbz = read_array(reference, "radar_dbz").astype(np.float64)
        radar_valid = reference_masks["radar_valid"]
        radar_no_echo = reference_masks["radar_no_echo"]
        radar_missing = reference_masks["radar_missing"]
        observation, raw_valid = load_lwc(lwc_path, shape, expected_time)
        lwc_mask = above_ground & raw_valid
        if not np.any(lwc_mask):
            raise ValueError("source LWC has no valid above-ground cells")
        # Freeze the shared support and observation classification before state diagnostics.
        frozen = {
            "grid_kji": list(shape),
            "valid_time_epoch": expected_time,
            "above_ground_sha256": hashlib.sha256(np.ascontiguousarray(above_ground).tobytes()).hexdigest(),
            "lwc_valid_sha256": hashlib.sha256(np.ascontiguousarray(lwc_mask).tobytes()).hexdigest(),
            "lwc_value_sha256": hashlib.sha256(np.ascontiguousarray(observation).tobytes()).hexdigest(),
            "analysis_support_sha256": hashlib.sha256(np.ascontiguousarray(analysis_support).tobytes()).hexdigest(),
            "analysis_support_cells": int(np.count_nonzero(analysis_support)),
            "radar_echo_mask_sha256": hashlib.sha256(np.ascontiguousarray(radar_valid).tobytes()).hexdigest(),
            "radar_no_echo_mask_sha256": hashlib.sha256(np.ascontiguousarray(radar_no_echo).tobytes()).hexdigest(),
            "lwc_operator_sha256": hashlib.sha256(
                json.dumps(LWC_OPERATOR, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "lwc_valid_above_ground_cells": int(np.count_nonzero(lwc_mask)),
            "lwc_positive_cells": int(np.count_nonzero(lwc_mask & (observation > 0.0))),
            "lwc_zero_cells": int(np.count_nonzero(lwc_mask & (observation == 0.0))),
            "lwc_observed_min_mean_max_kg_m3": [float(np.min(observation[lwc_mask])),
                                                 float(np.mean(observation[lwc_mask])),
                                                 float(np.max(observation[lwc_mask]))],
            "radar_echo_cells": int(np.count_nonzero(radar_valid)),
            "radar_no_echo_cells": int(np.count_nonzero(radar_no_echo)),
            "radar_missing_cells": int(np.count_nonzero(radar_missing)),
            "radar_echo_dbz_minmax": [float(np.min(radar_dbz[radar_valid])), float(np.max(radar_dbz[radar_valid]))],
        }

        state_results = [summary_state(reference, "Xbackground", observation, lwc_mask,
                                       radar_valid, radar_no_echo, "background",
                                       analysis_support),
                         summary_state(reference, "Xpre-density", observation, lwc_mask,
                                       radar_valid, radar_no_echo, "pre_density",
                                       analysis_support)]
        state_results.extend(summary_state(datasets[label], label, observation, lwc_mask,
                                           radar_valid, radar_no_echo,
                                           analysis_support=analysis_support)
                             for label in paths if label != "pr81_final")
        state_results.append(summary_state(reference, "Xfinal", observation, lwc_mask,
                                           radar_valid, radar_no_echo,
                                           analysis_support=analysis_support))
        changed_candidates = [str(path) for label, path in paths.items()
                              if sha256(path) != hashes[label]]
        if changed_candidates:
            raise ValueError("candidate files changed during readback: " + ", ".join(changed_candidates))
        if sha256(lwc_path) != lwc_hash:
            raise ValueError("processed LWC product changed during readback")
        if sha256(input_json) != input_declaration_hash:
            raise ValueError("input declaration changed during readback")
        return {
            "schema": "pr82_observation_signal_readback_v2",
            "case_id": declaration["case_id"],
            "source_operator": {
                **LWC_OPERATOR,
            },
            "modeled_unit_contract": MODELED_UNIT_CONTRACT,
            "inputs": {
                "input_declaration": str(input_json),
                "input_declaration_sha256": input_declaration_hash,
                "lwc_path": str(lwc_path),
                "lwc_sha256": lwc_hash,
                "readback_tool": {
                    "path": str(Path(__file__).resolve()),
                    "sha256": sha256(Path(__file__).resolve()),
                },
                "candidate_files": {label: {"path": str(path), "sha256": hashes[label]} for label, path in paths.items()},
            },
            "frozen_common_footprint_and_signal": frozen,
            "radar_fit": {
                "status": "not_computed",
                "reason": "No candidate-state-to-dBZ forward operator or radar LOS observation table is declared in retained inputs; echo/no-echo summaries below are signal-stratified state diagnostics only.",
            },
            "states": state_results,
        }
    finally:
        for dataset in datasets.values():
            dataset.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--pr81-final", type=Path, required=True)
    parser.add_argument("--pr78-o0-hydro", type=Path, required=True)
    parser.add_argument("--pr78-o0-coupled", type=Path, required=True)
    parser.add_argument("--pr78-o2-hydro", type=Path, required=True)
    parser.add_argument("--pr78-o2-coupled", type=Path, required=True)
    parser.add_argument("--pr80-o0", type=Path, required=True)
    parser.add_argument("--pr80-o2", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        "pr78_o0_hydro": args.pr78_o0_hydro,
        "pr78_o0_coupled": args.pr78_o0_coupled,
        "pr78_o2_hydro": args.pr78_o2_hydro,
        "oldcoupled_pr78_o2": args.pr78_o2_coupled,
        "pr80_o0_retained": args.pr80_o0,
        "pr80_o2_retained": args.pr80_o2,
        "pr81_final": args.pr81_final,
    }
    report = analyze(paths, args.input_json)
    write_new_json(args.output, report)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
