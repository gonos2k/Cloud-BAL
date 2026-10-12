#!/usr/bin/env python3
"""Verify retained CP06-A inputs and run/readback receipts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset


CASE_ID = "20260816T130000Z"
VALID_TIME = "2026-08-16T13:00:00Z"
VALID_EPOCH = 1786885200
PRODUCT_ORDER = ("lw3", "lt1", "lq3", "lwc", "lsx", "vrz", "vrt", "lcp", "lty")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array.astype(np.uint8)).tobytes()).hexdigest()


def require_pinned_file(root: Path, relative: str, expected: str) -> Path:
    path = root / relative
    lexical = Path(os.path.abspath(path))
    resolved = path.resolve(strict=True)
    if resolved != lexical or not path.is_file() or path.is_symlink():
        raise ValueError(f"retained input is missing or uses a symlink: {path}")
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"retained input hash mismatch: {path}")
    return path


def direct_products(workspace: Path) -> tuple[dict[str, Path], dict[str, str]]:
    manifest = workspace / "Cloud-BAL/config/cp06a_observation_inputs_20260816T130000Z.json"
    selection = json.loads(manifest.read_text(encoding="utf-8"))
    if selection.get("case") != "20260816T130000Z":
        raise ValueError("unexpected processed observation case")
    found = {item["product"]: item for item in selection["products"]}
    paths: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for product in PRODUCT_ORDER:
        if product not in found:
            raise ValueError(f"missing retained processed product: {product}")
        item = found[product]
        paths[product] = require_pinned_file(workspace, item["path"], item["sha256"])
        hashes[str(paths[product])] = item["sha256"]
    return paths, hashes


def native_inputs(workspace: Path, repo: Path) -> tuple[dict[str, Path], dict[str, str]]:
    manifest = repo / "tests/qbal_real_cases_20260816.tsv"
    with manifest.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    matches = [row for row in rows if row.get("case_id") == CASE_ID]
    if len(matches) != 1 or matches[0].get("valid_time_utc") != VALID_TIME:
        raise ValueError("the pinned native case row is missing or differs")
    row = matches[0]
    paths: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for name, field in (("fua", "fua"), ("fsf_center", "fsf")):
        rel = row[f"{field}_path"]
        expected = row[f"{field}_sha256"]
        paths[name] = require_pinned_file(workspace, rel, expected)
        hashes[str(paths[name])] = expected
    static = Path("ANAL/NE57/DABA/static.nest7grid")
    paths["static"] = require_pinned_file(
        workspace, str(static), "384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b"
    )
    hashes[str(paths["static"])] = "384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b"
    return paths, hashes


def build_input_receipt(workspace: Path, repo: Path) -> dict[str, object]:
    native, hashes = native_inputs(workspace, repo)
    processed, product_hashes = direct_products(workspace)
    hashes.update(product_hashes)
    authority_files = (
        workspace / "Cloud-BAL/config/cp06a_observation_inputs_20260816T130000Z.json",
        repo / "tests/qbal_real_cases_20260816.tsv",
    )
    return {
        "case_id": CASE_ID,
        "valid_time_utc": VALID_TIME,
        "valid_time_epoch": VALID_EPOCH,
        "input_selection": str(workspace / "Cloud-BAL/config/cp06a_observation_inputs_20260816T130000Z.json"),
        "authority_hashes": {str(path): sha256(path) for path in authority_files},
        "input_hashes": dict(sorted(hashes.items())),
        "native_paths": {name: str(path) for name, path in native.items()},
        "processed_paths": {name: str(path) for name, path in processed.items()},
        "driver_arguments": [
            str(native["fua"]), str(native["fsf_center"]), str(processed["lw3"]),
            str(processed["vrz"]), str(processed["vrt"]), str(native["static"]),
            *(str(processed[name]) for name in ("lt1", "lq3", "lwc", "lsx", "lcp", "lty")),
            str(VALID_EPOCH),
        ],
    }


def read_log(path: Path) -> tuple[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        fields[key] = value
        scope = key.split("_", 1)[0]
        for token in value.split(",")[1:]:
            if "=" not in token:
                continue
            subkey, subvalue = token.split("=", 1)
            subkey, subvalue = subkey.strip(), subvalue.strip()
            qualified = f"{scope}_{subkey}" if scope in {"OFF", "HYDRO", "COUPLED"} else subkey
            fields[qualified] = subvalue
    return text, fields


def variable(dataset: Dataset, name: str) -> np.ndarray:
    if name not in dataset.variables:
        raise ValueError(f"NetCDF readback is missing {name}")
    return np.asarray(dataset.variables[name][:])


def assert_same_outside(dataset: Dataset, base: str, candidate: str, support: np.ndarray) -> None:
    delta = variable(dataset, candidate) - variable(dataset, base)
    if not np.all(np.isfinite(delta)) or np.any(delta[~support] != 0):
        raise ValueError(f"{candidate} changed outside its declared support")


def masked_norm(values: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    selected = values[mask]
    if selected.size == 0 or not np.all(np.isfinite(selected)):
        raise ValueError("dry-mass closure metric has empty or nonfinite support")
    return float(np.sqrt(np.mean(selected * selected))), float(np.max(np.abs(selected)))


def represented_state_budget(dataset: Dataset, mask: np.ndarray) -> dict[str, float]:
    species_names = ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel")
    before_fields: list[np.ndarray] = []
    after_fields: list[np.ndarray] = []
    for name in species_names:
        before = variable(dataset, "background_" + name)
        after = variable(dataset, "candidate_" + name)
        for prefix, values in (("background_", before), ("candidate_", after)):
            valid_name = prefix + name + "_valid"
            quality_name = prefix + name + "_quality"
            source_name = prefix + name + "_source"
            if valid_name in dataset.variables and quality_name in dataset.variables and source_name in dataset.variables:
                valid = (variable(dataset, valid_name) != 0) & \
                    ((variable(dataset, quality_name) & 7) == 0) & (variable(dataset, source_name) > 0)
                if name == "vapor" and np.any(mask & ~valid):
                    raise ValueError("water budget has missing vapor in its declared support")
                values[~valid] = 0
        before_fields.append(before)
        after_fields.append(after)
    before_species = np.stack(before_fields)
    after_species = np.stack(after_fields)
    before_mass = variable(dataset, "dry_air_mass_measure")
    after_mass = variable(dataset, "candidate_dry_air_mass_measure")
    before_t = variable(dataset, "background_temperature")
    after_t = variable(dataset, "candidate_temperature")
    species_delta = after_mass[None, ...] * after_species - before_mass[None, ...] * before_species
    selected_delta = species_delta[:, mask]
    cp = np.asarray([1846.4, 4190.0, 2106.0, 4190.0, 2106.0, 2106.0])[:, None]
    h0 = np.asarray([2.50e6, 0.0, -3.50e5, 0.0, -3.50e5, -3.50e5])[:, None]
    def enthalpy(temperature: np.ndarray, mixture: np.ndarray) -> np.ndarray:
        return (1004.5 + np.sum(cp[:, 0, None] * mixture, axis=0)) * (temperature - 273.15) + \
            np.sum(h0[:, 0, None] * mixture, axis=0)
    before_mix = before_species[:, mask]
    after_mix = after_species[:, mask]
    before_h = enthalpy(before_t[mask], before_mix)
    after_h = enthalpy(after_t[mask], after_mix)
    h_delta = after_mass[mask] * after_h - before_mass[mask] * before_h
    mass_change = after_mass - before_mass
    geometry_change = np.zeros_like(mass_change)
    total_mass_error = float(np.sum(mass_change[mask]) + np.sum(selected_delta) - np.sum(geometry_change[mask]))
    max_cell_error = float(np.max(np.abs(mass_change[mask] + np.sum(species_delta[:, mask], axis=0) -
                                        geometry_change[mask])))
    return {
        "water_error_kg": float(np.sum(selected_delta)),
        "enthalpy_error_j": float(np.sum(h_delta)),
        "species_change_kg": float(np.sum(selected_delta)),
        "total_mass_error_kg": total_mass_error,
        "max_cell_mass_error_kg": max_cell_error,
    }


def verify_artifact(path: Path, kind: str, log: dict[str, str]) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"successful {kind} run did not write {path}")
    with Dataset(path) as data:
        for name, expected in (
            ("pressure_analysis_candidate_contract", "pressure_analysis_candidate_v1"),
            ("contract", "pressure_analysis_shadow_v1"),
            ("evidence_class", "PRESSURE_ANALYSIS_SHADOW_PROPOSAL"),
            ("supported_analysis_contract", "pressure_observation_retrieval_v1"),
        ):
            actual = getattr(data, name, None)
            if actual != expected:
                raise ValueError(f"{path}: {name}={actual!r}, expected {expected!r}")
        if int(getattr(data, "background_continuity_prior", -1)) != (kind == "coupled"):
            raise ValueError(f"{path}: wrong background prior setting")
        if int(getattr(data, "precipitation_transport_enabled", -1)) != 0:
            raise ValueError(f"{path}: retrieval ablation was not recorded")
        if getattr(data, "dry_air_flux_contract", None) != "pressure_observation_full_domain_dry_air_flux_v1":
            raise ValueError(f"{path}: full-domain background/candidate dry-flux contract is missing")
        if int(getattr(data, "dry_air_mass_tendency_assessed", -1)) != 0:
            raise ValueError(f"{path}: diagnostic flux was mislabeled as assessed mass tendency")
        for name in ("analysis_support", "geopotential_support", "thermo_support"):
            if name not in data.variables:
                raise ValueError(f"{path}: missing support variable {name}")
        analysis = variable(data, "analysis_support") != 0
        phi = variable(data, "geopotential_support") != 0
        thermo = variable(data, "thermo_support") != 0
        support_hashes = {
            "analysis": array_sha256(analysis),
            "geopotential": array_sha256(phi),
            "thermo": array_sha256(thermo),
        }
        above = variable(data, "above_ground") != 0
        if analysis.shape != above.shape or phi.shape != above.shape or thermo.shape != above.shape:
            raise ValueError(f"{path}: support/above-ground dimensions differ")
        dims = data.variables["analysis_support"].dimensions
        if not all(axis in dims for axis in ("x", "y", "z")):
            raise ValueError(f"{path}: support variable has unexpected dimensions {dims}")

        def project(mask: np.ndarray, variable_name: str) -> np.ndarray:
            variable_dims = data.variables[variable_name].dimensions
            flat = np.any(mask, axis=variable_dims.index("z"))
            remaining = [axis for axis in variable_dims if axis != "z"]
            return np.moveaxis(flat, (remaining.index("y"), remaining.index("x")), (0, 1))

        projected = project(analysis, "analysis_support")
        expected_analysis = np.zeros(projected.shape, dtype=bool)
        expected_analysis[16:19, 134:137] = True
        z_axis = dims.index("z")
        above_z = np.moveaxis(above, z_axis, 0)
        levels = np.arange(above_z.shape[0])[:, None, None]
        bottom = np.min(np.where(above_z, levels, above_z.shape[0]), axis=0)
        top = np.max(np.where(above_z, levels, -1), axis=0)
        analysis_expected_z = above_z & (levels > bottom[None, ...]) & (levels < top[None, ...]) & \
            expected_analysis[None, ...]
        analysis_expected = np.moveaxis(analysis_expected_z, 0, z_axis)
        if not np.array_equal(analysis, analysis_expected):
            raise ValueError(f"{path}: material support is not interior levels of fixed 3x3 i=135:137,j=17:19")
        phi_expected = above & np.expand_dims(expected_analysis, axis=z_axis)
        if not np.array_equal(phi, phi_expected):
            raise ValueError(f"{path}: Phi support is not full above-ground 3x3 columns")
        if np.any(analysis & ~above) or np.any(thermo & ~analysis):
            raise ValueError(f"{path}: support escapes above-ground analysis domain")
        if int(np.count_nonzero(analysis)) != int(log["analysis_support_cells"]):
            raise ValueError(f"{path}: analysis support count disagrees with preflight")
        if int(np.count_nonzero(thermo)) != int(log["thermo_active_warm_liquid_observation_cells"]):
            raise ValueError(f"{path}: thermo support count disagrees with preflight")
        if kind == "coupled":
            control = variable(data, "background_control_support") != 0
            shell = variable(data, "background_validation_shell") != 0
            support_hashes["control"] = array_sha256(control)
            support_hashes["validation_shell"] = array_sha256(shell)
            expected_control = np.zeros(project(control, "background_control_support").shape, dtype=bool)
            expected_control[15:20, 133:138] = True
            expected_shell = np.zeros(project(shell, "background_validation_shell").shape, dtype=bool)
            expected_shell[14:21, 132:139] = True
            control_expected = above & np.expand_dims(expected_control, axis=z_axis)
            shell_expected = above & np.expand_dims(expected_shell, axis=z_axis)
            if not np.array_equal(control, control_expected) or \
                    not np.array_equal(shell, shell_expected) or \
                    np.any(analysis & ~control) or np.any(control & ~shell):
                raise ValueError(f"{path}: background control/shell support differs")
            reference = variable(data, "geopotential_reference_level")
            expected_ref = np.min(np.where(above_z, np.arange(1, above_z.shape[0] + 1)[:, None, None], 99), axis=0)
            expected_ref[~project(phi, "geopotential_support")] = 0
            if not np.array_equal(reference, expected_ref):
                raise ValueError(f"{path}: lowest-level geopotential reference differs from full 3x3 Phi columns")
            if int(np.count_nonzero(shell)) != int(log["background_validation_shell_cells"]):
                raise ValueError(f"{path}: validation shell count disagrees with preflight")
            for name, expected in (
                ("dry_mass_tendency_prior", "frozen_background_minus_dry_flux_divergence_kg_s-1"),
                ("background_prior_metric", "existing_kappa_u_v_omega_not_observational_covariance"),
            ):
                if getattr(data, name, None) != expected:
                    raise ValueError(f"{path}: missing explicit prior semantics {name}")
            for name, expected in (("kappa_u", 16.0), ("kappa_v", 16.0), ("kappa_omega", 0.25)):
                if not np.isclose(float(getattr(data, name, math.nan)), expected, rtol=0, atol=0):
                    raise ValueError(f"{path}: background-prior metric differs at {name}")
        if not np.array_equal(variable(data, "omega_target"), variable(data, "original_omega_target")):
            raise ValueError(f"{path}: target omega changed during analysis")
        for suffix in ("valid", "quality", "source"):
            if not np.array_equal(variable(data, "omega_target_" + suffix),
                                  variable(data, "original_omega_target_" + suffix)):
                raise ValueError(f"{path}: omega target {suffix} metadata changed during analysis")
            if not np.array_equal(variable(data, "omega_target_sigma_" + suffix),
                                  variable(data, "original_omega_target_sigma_" + suffix)):
                raise ValueError(f"{path}: omega target sigma {suffix} metadata changed during analysis")
        if not np.array_equal(variable(data, "omega_target_sigma"),
                              variable(data, "original_omega_target_sigma")):
            raise ValueError(f"{path}: omega target sigma changed during analysis")
        if int(np.count_nonzero(variable(data, "omega_target_sigma_valid"))) != \
                int(log["omega_target_sigma_cells"]):
            raise ValueError(f"{path}: sigma validity differs from canonical reader preflight")
        if not all(log.get(prefix + "_omega_target_and_sigma_unchanged") == "T"
                   for prefix in ("HYDRO", "COUPLED")):
            raise ValueError(f"{path}: in-memory target/sigma exact preservation was not recorded")
        for candidate_name, background_name in (
            ("candidate_u", "background_u"),
            ("candidate_v", "background_v"),
            ("candidate_omega", "background_omega"),
        ):
            delta = variable(data, candidate_name) - variable(data, background_name)
            if not np.all(np.isfinite(delta)):
                raise ValueError(f"{path}: {candidate_name} increment is nonfinite")
            if kind == "hydro" and np.any(delta != 0):
                raise ValueError(f"{path}: HYDRO changed {candidate_name}")
            if kind == "coupled" and np.any(delta[~control] != 0):
                raise ValueError(f"{path}: coupled balance changed {candidate_name} outside control support")
        for species in ("cloud_water", "cloud_ice", "rain", "snow", "graupel"):
            assert_same_outside(data, "background_" + species, "candidate_" + species, analysis)
            valid_name = "candidate_" + species + "_valid"
            if valid_name in data.variables:
                values = variable(data, "candidate_" + species)
                valid = variable(data, valid_name) != 0
                if np.any(values[valid] < 0):
                    raise ValueError(f"{path}: negative candidate {species} on valid cells")
        assert_same_outside(data, "background_temperature", "candidate_temperature", thermo)
        assert_same_outside(data, "background_vapor", "candidate_vapor", thermo)
        assert_same_outside(data, "background_geopotential", "candidate_geopotential", phi)
        assert_same_outside(data, "dry_air_mass_measure", "candidate_dry_air_mass_measure", analysis)
        for name in ("pressure", "pressure_interface", "cell_dp", "pressure_mass_measure",
                     "dry_air_mass_measure", "surface_pressure", "omega_top_boundary",
                     "omega_bottom_boundary", "omega_top_boundary_valid",
                     "omega_bottom_boundary_valid", "omega_top_boundary_quality",
                     "omega_bottom_boundary_quality", "omega_top_boundary_source",
                     "omega_bottom_boundary_source"):
            if name not in data.variables:
                continue
            if not np.all(np.isfinite(variable(data, name))):
                raise ValueError(f"{path}: nonfinite fixed geometry/boundary {name}")
        for name in ("background_surface_pressure", "candidate_surface_pressure"):
            if not np.array_equal(variable(data, name), variable(data, "surface_pressure")):
                raise ValueError(f"{path}: surface pressure changed at {name}")
        for background_name, candidate_name in (
            ("background_surface_temperature", "candidate_surface_temperature"),
            ("background_surface_vapor", "candidate_surface_vapor"),
            ("background_surface_height", "candidate_surface_height"),
        ):
            if not np.array_equal(variable(data, background_name), variable(data, candidate_name)):
                raise ValueError(f"{path}: fixed surface field changed at {candidate_name}")
        flux_background = variable(data, "background_dry_air_flux_divergence")
        flux_candidate = variable(data, "candidate_dry_air_flux_divergence")
        mass = variable(data, "pressure_mass_measure")
        if np.any(mass[above] <= 0) or not np.all(np.isfinite(flux_background[above])) or \
                not np.all(np.isfinite(flux_candidate[above])):
            raise ValueError(f"{path}: invalid full-domain dry-air flux readback")
        prior_flux = -flux_background
        if kind == "coupled" and not np.any(prior_flux[shell] != 0):
            raise ValueError(f"{path}: frozen-background dry-mass tendency prior is zero on shell")
        budget = represented_state_budget(data, above)
        for name in ("analysis_total_mass_error_kg", "analysis_max_cell_mass_error_kg",
                     "analysis_enthalpy_change_j", "thermo_water_error_kg", "thermo_enthalpy_error_j"):
            if not math.isfinite(float(getattr(data, name, math.nan))):
                raise ValueError(f"{path}: nonfinite represented analysis budget {name}")
        endpoint_mass_error = float(getattr(data, "analysis_total_mass_error_kg")) + \
            float(getattr(data, "thermo_water_error_kg"))
        if not np.isclose(budget["total_mass_error_kg"], endpoint_mass_error, rtol=1e-6, atol=1e-6):
            raise ValueError(f"{path}: independently recomputed endpoint water/mass accounting differs")
        endpoint_enthalpy = float(getattr(data, "analysis_enthalpy_change_j")) + \
            float(getattr(data, "thermo_enthalpy_error_j"))
        if not np.isclose(budget["enthalpy_error_j"], endpoint_enthalpy, rtol=1e-6, atol=1e-5):
            raise ValueError(f"{path}: independently recomputed represented-enthalpy accounting differs")
        changed = int(np.count_nonzero(variable(data, "overall_changed") != 0))
        if changed <= 0:
            raise ValueError(f"{path}: candidate contains no changed cells")
        result = {
            "path": str(path),
            "sha256": sha256(path),
            "dimensions": {name: len(dim) for name, dim in data.dimensions.items()},
            "analysis_support_cells": int(np.count_nonzero(analysis)),
            "thermo_support_cells": int(np.count_nonzero(thermo)),
            "changed_cells": changed,
            "contract": str(getattr(data, "contract", "")),
            "evidence_class": str(getattr(data, "evidence_class", "")),
            "support_sha256": support_hashes,
            "represented_water_change_kg": budget["water_error_kg"],
            "represented_enthalpy_change_j": budget["enthalpy_error_j"],
            "endpoint_mass_error_kg": budget["total_mass_error_kg"],
            "independent_flux_stencil": "NOT_ASSESSED; closure recomputed from persisted full-domain BF_d arrays",
        }
        if kind == "coupled":
            initial = (variable(data, "candidate_dry_air_flux_divergence") - flux_background) / mass
            # The Coupled NetCDF holds only its endpoint. Its paired HYDRO initial state
            # is passed by verify_run below so the residual is independently rebuilt there.
            result["background_prior_nonzero_on_shell"] = bool(np.any(prior_flux[shell] != 0))
        return result


def verify_run(run_root: Path, repo: Path) -> dict[str, object]:
    inputs = json.loads((run_root / "inputs.json").read_text(encoding="utf-8"))
    spec_path = Path(inputs["experiment_spec"])
    if sha256(spec_path) != inputs["experiment_spec_sha256"] or \
            sha256(run_root / "experiment_spec.md") != inputs["experiment_spec_sha256"]:
        raise ValueError("declared v2 experiment spec changed during build/run")
    for path, expected in inputs["input_hashes"].items():
        if sha256(Path(path)) != expected:
            raise ValueError(f"pinned input changed during run: {path}")
    for path, expected in inputs["authority_hashes"].items():
        if sha256(Path(path)) != expected:
            raise ValueError(f"input-selection authority changed during run: {path}")
    profile_receipts: dict[str, object] = {}
    mask_names = ("analysis_support", "geopotential_support", "background_control_support",
                  "background_validation_shell", "thermo_support")
    preflight_hashes: dict[str, str] = {}
    for profile in ("O0", "O2"):
        build = run_root / profile
        preflight_text, preflight = read_log(build / "preflight.log")
        if preflight.get("pre_candidate_support_masks_written") != "T" or \
                "OFF_status" in preflight:
            raise ValueError(f"{profile}: candidate work occurred before the support snapshot")
        support_path = build / "pre_candidate_support.bin"
        support_hash = sha256(support_path)
        expected_support_hash = (build / "pre_candidate_support.sha256").read_text(encoding="utf-8").split()[0]
        if support_hash != expected_support_hash:
            raise ValueError(f"{profile}: pre-candidate support snapshot hash mismatch")
        raw = support_path.read_bytes()
        header = np.frombuffer(raw, dtype="<i4", count=5)
        if len(header) != 5:
            raise ValueError(f"{profile}: truncated pre-candidate support header")
        nx, ny, nz, center_i, center_j = (int(value) for value in header)
        if (center_i, center_j) != (136, 18):
            raise ValueError(f"{profile}: pre-candidate selection did not use fixed center 136,18")
        one_mask_bytes = nx * ny * nz * 4
        if len(raw) != 20 + 5 * one_mask_bytes:
            raise ValueError(f"{profile}: pre-candidate support snapshot has unexpected length")
        pre_masks: dict[str, np.ndarray] = {}
        offset = 20
        for name in mask_names:
            values = np.frombuffer(raw, dtype="<i4", count=nx * ny * nz, offset=offset)
            pre_masks[name] = values.reshape((nx, ny, nz), order="F") != 0
            offset += one_mask_bytes
        preflight_hashes[profile] = support_hash
        text, log = read_log(build / "run.log")
        for key in ("OFF_status", "HYDRO_status", "COUPLED_status"):
            status = log[key].split(",", 1)[0]
            if status != "20":
                raise ValueError(f"{profile} {key}={status}; candidate failed closed; see {build / 'run.log'}")
        if log.get("selected_center_i") != "136,j=18" or log.get("science_authority") != "NONE" or \
                log.get("case") != "CP06A-20260816T130000Z-background-prior-v2":
            raise ValueError(f"{profile}: fixed patch or authority receipt mismatch")
        if log.get("producer_decision") != "SCOPED_PRESSURE_CANDIDATE_WRITTEN" or \
                log.get("native_validation") != "NOT_RUN":
            raise ValueError(f"{profile}: failed or overclaimed producer decision")
        if int(log.get("COUPLED_solver_reason", "0")) != 1 or \
                int(log.get("COUPLED_balance_changed", "0")) <= 0:
            raise ValueError(f"{profile}: coupled run has no converged nonzero spatial balance adjustment")
        if float(log.get("COUPLED_max_wind_increment_ms", "0")) <= 0 and \
                float(log.get("COUPLED_max_omega_increment_pas", "0")) <= 0:
            raise ValueError(f"{profile}: coupled balance increments are zero")
        artifacts = {
            "hydro": verify_artifact(build / "hydro.nc", "hydro", log),
            "coupled": verify_artifact(build / "coupled.nc", "coupled", log),
        }
        for artifact_name in ("hydro", "coupled"):
            with Dataset(build / f"{artifact_name}.nc") as snapshot:
                persisted_masks = ("analysis_support", "geopotential_support", "thermo_support")
                if artifact_name == "coupled":
                    persisted_masks += ("background_control_support", "background_validation_shell")
                for name in persisted_masks:
                    if name not in snapshot.variables:
                        raise ValueError(f"{profile}/{artifact_name}: missing snapshotted support {name}")
                    dims = snapshot.variables[name].dimensions
                    axes = [("x", "y", "z").index(axis) for axis in dims]
                    expected = np.transpose(pre_masks[name], axes=axes).astype(bool)
                    if not np.array_equal(variable(snapshot, name) != 0, expected):
                        raise ValueError(f"{profile}/{artifact_name}: persisted {name} differs from pre-candidate snapshot")
        with Dataset(build / "hydro.nc") as hydro, Dataset(build / "coupled.nc") as coupled:
            for name in ("pressure", "pressure_interface", "cell_dp", "pressure_mass_measure",
                         "dry_air_mass_measure", "surface_pressure", "omega_top_boundary",
                         "omega_bottom_boundary", "omega_top_boundary_valid",
                         "omega_bottom_boundary_valid", "omega_top_boundary_quality",
                         "omega_bottom_boundary_quality", "omega_top_boundary_source",
                         "omega_bottom_boundary_source", "background_surface_pressure",
                         "candidate_surface_pressure", "candidate_dry_air_mass_measure"):
                if not np.array_equal(variable(hydro, name), variable(coupled, name)):
                    raise ValueError(f"{profile}: HYDRO/COUPLED geometry or boundary differs at {name}")
            shell = variable(coupled, "background_validation_shell") != 0
            mass = variable(coupled, "pressure_mass_measure")
            base_flux = variable(coupled, "background_dry_air_flux_divergence")
            hydro_flux = variable(hydro, "candidate_dry_air_flux_divergence")
            coupled_flux = variable(coupled, "candidate_dry_air_flux_divergence")
            initial = (hydro_flux - base_flux) / mass
            final = (coupled_flux - base_flux) / mass
            initial_rms, initial_max = masked_norm(initial, shell)
            final_rms, final_max = masked_norm(final, shell)
            expected_initial_rms = float(log["COUPLED_background_tendency_rms"])
            expected_initial_max = float(log["COUPLED_background_tendency_max"])
            expected_final_rms = float(log["COUPLED_closure_rms"])
            expected_final_max = float(log["COUPLED_closure_max"])
            for actual, expected, name in (
                (initial_rms, expected_initial_rms, "initial RMS"),
                (initial_max, expected_initial_max, "initial max"),
                (final_rms, expected_final_rms, "closure RMS"),
                (final_max, expected_final_max, "closure max"),
            ):
                if not np.isclose(actual, expected, rtol=1e-5, atol=1e-12):
                    raise ValueError(f"{profile}: independently rebuilt {name} differs from Fortran log")
            if final_rms > max(2e-3 * initial_rms, 1e-12) or \
                    final_max > max(2e-3 * initial_max, 1e-12):
                raise ValueError(f"{profile}: background-prior dry-flux closure misses frozen threshold")
            if not np.any(base_flux[shell] != 0):
                raise ValueError(f"{profile}: dry-mass tendency prior is identically zero on shell")
            artifacts["coupled"]["independent_initial_rms"] = initial_rms
            artifacts["coupled"]["independent_initial_max"] = initial_max
            artifacts["coupled"]["independent_closure_rms"] = final_rms
            artifacts["coupled"]["independent_closure_max"] = final_max
        provenance = (build / "build_provenance.txt").read_text(encoding="utf-8").splitlines()
        source_hashes = {}
        build_metadata = {}
        for line in provenance:
            if "=" in line:
                key, value = line.split("=", 1)
                build_metadata[key.strip()] = value.strip()
            fields = line.split()
            if len(fields) == 2 and len(fields[0]) == 64:
                path = Path(fields[1])
                if not path.is_file() or sha256(path) != fields[0]:
                    raise ValueError(f"{profile}: source hash changed after compilation: {path}")
                source_hashes[str(path)] = fields[0]
        profile_receipts[profile] = {
            "run_log_sha256": sha256(build / "run.log"),
            "executable_sha256": (build / "executable.sha256").read_text(encoding="utf-8").split()[0],
            "source_hashes": source_hashes,
            "build_metadata": build_metadata,
            "build_provenance_sha256": sha256(build / "build_provenance.txt"),
            "artifacts": artifacts,
            "pre_candidate_support_sha256": support_hash,
            "selected_patch": [136, 18],
            "analysis_i": [135, 137],
            "analysis_j": [17, 19],
            "control_i": [134, 138],
            "control_j": [16, 20],
            "off_status": 20,
            "hydro_status": 20,
            "coupled_status": 20,
            "science_authority": "NONE",
            "native_validation": "NOT_RUN",
        }
    for kind in ("hydro", "coupled"):
        paths = [run_root / profile / f"{kind}.nc" for profile in ("O0", "O2")]
        with Dataset(paths[0]) as first, Dataset(paths[1]) as second:
            for name in ("analysis_support", "geopotential_support", "thermo_support",
                         "background_control_support", "background_validation_shell"):
                if name in first.variables or name in second.variables:
                    if name not in first.variables or name not in second.variables or \
                            not np.array_equal(variable(first, name), variable(second, name)):
                        raise ValueError(f"O0/O2 support-mask mismatch for {kind}:{name}")
            for name in ("candidate_u", "candidate_v", "candidate_omega", "candidate_cloud_water",
                         "candidate_cloud_ice", "candidate_rain", "candidate_snow", "candidate_graupel",
                         "candidate_temperature", "candidate_vapor", "background_dry_air_flux_divergence",
                         "candidate_dry_air_flux_divergence"):
                a, b = variable(first, name), variable(second, name)
                if not np.allclose(a, b, rtol=1e-6, atol=1e-8, equal_nan=True):
                    raise ValueError(f"O0/O2 physical readback differs for {kind}:{name}")
    if profile_receipts["O0"]["source_hashes"] != profile_receipts["O2"]["source_hashes"]:
        raise ValueError("O0/O2 were not built from the same source and pinned library bytes")
    if preflight_hashes["O0"] != preflight_hashes["O2"]:
        raise ValueError("O0/O2 used different pre-candidate support masks")
    for key in ("compiler", "compiler_version", "compiler_sha256", "nf_config"):
        if profile_receipts["O0"]["build_metadata"].get(key) != \
                profile_receipts["O2"]["build_metadata"].get(key):
            raise ValueError(f"O0/O2 compiler/link configuration differs at {key}")
    receipt = {
        "case_id": CASE_ID,
        "valid_time_utc": VALID_TIME,
        "input_hashes": inputs["input_hashes"],
        "authority_hashes": inputs["authority_hashes"],
        "experiment_spec": inputs["experiment_spec"],
        "experiment_spec_sha256": inputs["experiment_spec_sha256"],
        "profiles": profile_receipts,
        "decision": "SCOPED_PRESSURE_CANDIDATE_WRITTEN",
        "authority": "research_only_no_native_or_science_authority",
    }
    output = run_root / "producer_receipt.json"
    output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify-run", type=Path)
    args = parser.parse_args()

    if args.verify_run:
        receipt = verify_run(args.verify_run.resolve(), args.repo.resolve())
        print(f"producer_receipt={args.verify_run.resolve() / 'producer_receipt.json'}")
        print(f"decision={receipt['decision']}")
    else:
        receipt = build_input_receipt(args.workspace.resolve(), args.repo.resolve())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(f"input_receipt={args.output}")
        print(f"pinned_inputs={len(receipt['input_hashes'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"CP06-A receipt error: {error}", file=sys.stderr)
        raise SystemExit(2)
