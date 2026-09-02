#!/usr/bin/env python3
"""Validate one test-only balance solve on the real NE57 geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


def read_metrics(path: Path) -> dict[str, str]:
    metrics: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.startswith("ERROR STOP"):
            continue
        key, value = line.split("=", 1)
        if key in metrics:
            raise ValueError(f"duplicate metric: {key}")
        metrics[key] = value.strip()
    return metrics


def number(metrics: dict[str, str], name: str) -> float:
    if name not in metrics:
        raise ValueError(f"missing metric: {name}")
    value = float(metrics[name])
    if not np.isfinite(value):
        raise ValueError(f"non-finite metric: {name}")
    return value


def validate(diagnostic: Path, log: Path) -> dict[str, object]:
    metrics = read_metrics(log)
    if metrics.get("evidence_authority") != "NUMERICAL_REAL_GEOMETRY_ONLY":
        raise ValueError("invalid evidence authority")
    if metrics.get("science_authority") != "NONE":
        raise ValueError("manufactured test claimed science authority")
    if metrics.get("balance_scope") != "TARGET_INCREMENT_PROJECTION_ONLY":
        raise ValueError("numerical test overstated its balance scope")
    if metrics.get("target_kind") != "MANUFACTURED_TEST":
        raise ValueError("invalid target kind")
    if metrics.get("boundary_authority") != "MANUFACTURED_TEST_ONLY":
        raise ValueError("invalid boundary authority")
    if metrics.get("boundary_driver") != "MODEL_FSF_PS_TENDENCY_ADVECTION":
        raise ValueError("invalid boundary driver")
    if metrics.get("surface_wind_frame") != "UNRESOLVED_NATIVE":
        raise ValueError("surface wind frame was overstated")
    if metrics.get("operational_state_unchanged") != "T":
        raise ValueError("operational input changed")
    expected_configuration = {
        "target_amplitude_pas": 0.02,
        "kappa_omega": 0.1,
        "minimum_beta": 0.001,
        "solver_residual_fraction": 0.05,
        "minimum_target_response_ratio": 0.01,
        "maximum_target_response_failure_fraction": 0.50,
    }
    for name, expected in expected_configuration.items():
        if abs(number(metrics, name) - expected) > 1.0e-12:
            raise ValueError(f"unexpected numerical-test configuration: {name}")

    required_integer = {
        "seed_i": (1, None),
        "seed_j": (1, None),
        "target_cells": (1, None),
        "beta_cells": (1, None),
        "bottom_boundary_nonzero_cells": (1, None),
        "balance_status": (20, 20),
        "balance_reason": (0, 0),
        "solver_reason": (1, 1),
        "solver_iterations": (1, 1200),
        "acceptance_failures": (0, 0),
        "changed_cells": (1, None),
        "outside_support_changed_cells": (0, 0),
    }
    integer_metrics: dict[str, int] = {}
    for name, (minimum, maximum) in required_integer.items():
        raw_value = number(metrics, name)
        value = int(raw_value)
        if raw_value != value:
            raise ValueError(f"non-integer metric: {name}={raw_value}")
        if value < minimum or (maximum is not None and value > maximum):
            raise ValueError(f"metric outside contract: {name}={value}")
        integer_metrics[name] = value

    proposed = number(metrics, "continuity_proposed_rms")
    projected = number(metrics, "continuity_projected_rms")
    background = number(metrics, "continuity_background_rms")
    candidate = number(metrics, "continuity_candidate_rms")
    proposed_max = number(metrics, "continuity_proposed_max")
    projected_max = number(metrics, "continuity_projected_max")
    background_max = number(metrics, "continuity_background_max")
    candidate_max = number(metrics, "continuity_candidate_max")
    max_wind = number(metrics, "max_wind_increment_ms")
    max_omega = number(metrics, "max_omega_increment_pas")
    identity = number(metrics, "operator_identity_max")
    response_failure = number(metrics, "target_response_failure_fraction")
    trust = number(metrics, "trust_region_fraction")
    geo_background = number(metrics, "geostrophic_background_rms")
    geo_candidate = number(metrics, "geostrophic_candidate_rms")
    divergent = number(metrics, "divergent_increment_rms")
    rotational = number(metrics, "rotational_increment_rms")
    if min(
        proposed,
        projected,
        background,
        candidate,
        proposed_max,
        projected_max,
        background_max,
        candidate_max,
        max_wind,
        max_omega,
        identity,
        geo_background,
        geo_candidate,
        divergent,
        rotational,
    ) < 0.0:
        raise ValueError("a norm or error metric is negative")
    if not 0.0 <= response_failure <= 1.0 or not 0.0 <= trust <= 1.0:
        raise ValueError("a fraction metric is outside [0, 1]")
    if proposed <= 0.0 or projected > 0.25 * proposed:
        raise ValueError("target-induced continuity reduction failed")
    if candidate > background + 1.0e-7:
        raise ValueError("full-state continuity residual worsened")
    if not (0.0 < max_wind <= 0.5 and 1.0e-3 <= max_omega <= 0.05):
        raise ValueError("dynamic increment is outside the numerical-test bounds")
    if identity > 1.0e-12 or \
            response_failure > expected_configuration[
                "maximum_target_response_failure_fraction"
            ] or trust < 0.25:
        raise ValueError("operator, response, or trust-region gate failed")
    if geo_candidate > 1.05 * geo_background + 0.01:
        raise ValueError("geostrophic residual gate failed")

    with Dataset(diagnostic) as dataset:
        if getattr(dataset, "evidence_authority", "") != "NUMERICAL_REAL_GEOMETRY_ONLY":
            raise ValueError("diagnostic authority differs from log")
        if getattr(dataset, "science_authority", "") != "NONE":
            raise ValueError("diagnostic claims science authority")
        if getattr(dataset, "balance_scope", "") != "TARGET_INCREMENT_PROJECTION_ONLY":
            raise ValueError("diagnostic overstated its balance scope")
        if getattr(dataset, "target_kind", "") != "MANUFACTURED_TEST":
            raise ValueError("diagnostic target kind differs from log")
        if getattr(dataset, "boundary_authority", "") != "MANUFACTURED_TEST_ONLY":
            raise ValueError("diagnostic boundary authority differs from log")
        if getattr(dataset, "boundary_driver", "") != "MODEL_FSF_PS_TENDENCY_ADVECTION":
            raise ValueError("diagnostic boundary driver differs from log")
        if getattr(dataset, "surface_wind_frame", "") != "UNRESOLVED_NATIVE":
            raise ValueError("diagnostic surface wind frame was overstated")
        if getattr(dataset, "wave_proxy_scope", "") != \
                "NEIGHBOR_JUMP_ENGINEERING_GUARD_ONLY":
            raise ValueError("diagnostic wave proxy scope mismatch")
        if int(getattr(dataset, "forecast_wave_response_assessed", -1)) != 0:
            raise ValueError("diagnostic overstated forecast-wave evidence")
        if int(getattr(dataset, "target_source_bits", -1)) != 5120 or \
                int(getattr(dataset, "target_quality_bits", -1)) != 0:
            raise ValueError("diagnostic target provenance mismatch")
        if int(getattr(dataset, "boundary_source_bits", -1)) != 6144 or \
                int(getattr(dataset, "boundary_quality_bits", -1)) != 0:
            raise ValueError("diagnostic boundary provenance mismatch")
        if int(getattr(dataset, "balance_status", -1)) != integer_metrics["balance_status"]:
            raise ValueError("diagnostic balance status differs from log")
        if int(getattr(dataset, "solver_iterations", -1)) != \
                integer_metrics["solver_iterations"]:
            raise ValueError("diagnostic solver iterations differ from log")
        if int(getattr(dataset, "acceptance_failures", -1)) != 0:
            raise ValueError("diagnostic acceptance result differs from log")
        for name, expected in expected_configuration.items():
            if abs(float(getattr(dataset, name)) - expected) > 1.0e-12:
                raise ValueError(f"diagnostic configuration differs: {name}")
        background_u = np.asarray(dataset["background_u"][:], dtype=np.float64)
        background_v = np.asarray(dataset["background_v"][:], dtype=np.float64)
        background_omega = np.asarray(dataset["background_omega"][:], dtype=np.float64)
        candidate_u = np.asarray(dataset["candidate_u"][:], dtype=np.float64)
        candidate_v = np.asarray(dataset["candidate_v"][:], dtype=np.float64)
        candidate_omega = np.asarray(dataset["candidate_omega"][:], dtype=np.float64)
        beta = np.asarray(dataset["balance_beta"][:], dtype=np.float64)
        raw_changed = np.asarray(dataset["changed"][:], dtype=np.int64)
        raw_above_ground = np.asarray(dataset["above_ground"][:], dtype=np.int64)
        raw_target_valid = np.asarray(dataset["omega_target_valid"][:], dtype=np.int64)
        hydro_support = np.asarray(dataset["hydro_support"][:], dtype=np.int64)
        target_source = np.asarray(dataset["omega_target_source"][:], dtype=np.int64)
        omega_target = np.asarray(dataset["omega_target"][:], dtype=np.float64)
        original_hydro = np.asarray(
            dataset["original_total_hydrometeor"][:], dtype=np.float64
        )
        proposal_hydro = np.asarray(
            dataset["proposal_total_hydrometeor"][:], dtype=np.float64
        )
        original_dry_mass = np.asarray(
            dataset["original_dry_air_mass"][:], dtype=np.float64
        )
        proposal_dry_mass = np.asarray(
            dataset["proposal_dry_air_mass"][:], dtype=np.float64
        )
        radar = np.asarray(dataset["radar_dbz"][:], dtype=np.float64)
        residual_background = np.asarray(
            dataset["continuity_background"][:], dtype=np.float64
        )
        residual_candidate = np.asarray(
            dataset["continuity_candidate"][:], dtype=np.float64
        )
        residual_proposed = np.asarray(
            dataset["continuity_proposed_increment"][:], dtype=np.float64
        )
        residual_projected = np.asarray(
            dataset["continuity_projected_increment"][:], dtype=np.float64
        )
        latitude = np.asarray(dataset["latitude"][:], dtype=np.float64)
        longitude = np.asarray(dataset["longitude"][:], dtype=np.float64)
        pressure = np.asarray(dataset["pressure"][:], dtype=np.float64)
        top_boundary = np.asarray(dataset["omega_top_boundary"][:], dtype=np.float64)
        boundary = np.asarray(dataset["omega_bottom_boundary"][:], dtype=np.float64)

    for name, raw_mask in {
        "changed": raw_changed,
        "above_ground": raw_above_ground,
        "omega_target_valid": raw_target_valid,
    }.items():
        if not np.all((raw_mask == 0) | (raw_mask == 1)):
            raise ValueError(f"{name} is not a binary mask")
    changed = raw_changed.astype(bool)
    above_ground = raw_above_ground.astype(bool)
    target_valid = raw_target_valid.astype(bool)

    arrays = (
        background_u,
        background_v,
        background_omega,
        candidate_u,
        candidate_v,
        candidate_omega,
        beta,
        omega_target,
        original_hydro,
        proposal_hydro,
        original_dry_mass,
        proposal_dry_mass,
        radar,
        residual_background,
        residual_candidate,
        residual_proposed,
        residual_projected,
        latitude,
        longitude,
        pressure,
        top_boundary,
        boundary,
    )
    if any(np.any(~np.isfinite(array)) for array in arrays):
        raise ValueError("diagnostic contains a non-finite value")
    if not np.all(np.diff(pressure) < 0.0):
        raise ValueError("pressure is not canonical bottom-to-top")
    field_shape = background_u.shape
    if any(array.shape != field_shape for array in (
        background_v, background_omega, candidate_u, candidate_v, candidate_omega,
        beta, omega_target, original_hydro, proposal_hydro, original_dry_mass,
        proposal_dry_mass, radar, raw_changed, raw_above_ground, raw_target_valid,
        hydro_support, target_source, residual_background, residual_candidate,
        residual_proposed, residual_projected,
    )):
        raise ValueError("diagnostic field shapes differ")
    if latitude.shape != field_shape[1:] or longitude.shape != field_shape[1:] or \
            top_boundary.shape != field_shape[1:] or \
            boundary.shape != field_shape[1:] or pressure.shape != (field_shape[0],):
        raise ValueError("diagnostic coordinate shapes differ")
    if np.any(top_boundary != 0.0):
        raise ValueError("manufactured top boundary is not exact zero")
    if np.any((beta < 0.0) | (beta > 1.0)) or \
            not np.all((hydro_support == 0) | (hydro_support == 1)):
        raise ValueError("support arrays are outside their contract")
    if np.any(target_valid & (~above_ground | (beta <= 0.0))):
        raise ValueError("manufactured target escaped the active domain/support")
    if np.any(target_source[target_valid] != 5120) or \
            np.any(target_source[~target_valid] != 0):
        raise ValueError("target source bits differ from the valid mask")
    if np.any(original_hydro < 0.0) or np.any(proposal_hydro < 0.0) or \
            np.any(original_dry_mass < 0.0) or np.any(proposal_dry_mass < 0.0):
        raise ValueError("hydrometeor or dry-air mass is negative")
    if np.any(~above_ground & (
        (beta != 0.0) | target_valid | changed | (hydro_support != 0)
    )):
        raise ValueError("a support/change marker exists below ground")
    active = above_ground & (beta > expected_configuration["minimum_beta"])
    if not np.any(active):
        raise ValueError("balance active mask is empty")

    nz, ny, nx = field_shape
    seed_i = integer_metrics["seed_i"]
    seed_j = integer_metrics["seed_j"]
    if not 6 <= seed_i <= nx - 5 or not 6 <= seed_j <= ny - 5:
        raise ValueError("manufactured seed is outside the interior contract")
    center_i = (nx + 1) // 2
    center_j = (ny + 1) // 2
    expected_seed = min(
        (
            (i - center_i) ** 2 + (j - center_j) ** 2,
            j,
            i,
        )
        for j in range(6, ny - 4)
        for i in range(6, nx - 4)
        if np.any(hydro_support[:, j - 1, i - 1] != 0)
        and np.count_nonzero(above_ground[:, j - 1, i - 1]) >= 6
    )
    if (seed_i, seed_j) != (expected_seed[2], expected_seed[1]):
        raise ValueError("manufactured seed is not the deterministic support seed")

    expected_beta = np.zeros_like(beta)
    for j in range(max(1, seed_j - 5), min(ny, seed_j + 5) + 1):
        for i in range(max(1, seed_i - 5), min(nx, seed_i + 5) + 1):
            radius = np.hypot(i - seed_i, j - seed_j) / 5.0
            if radius >= 1.0:
                continue
            weight = np.float32((1.0 - radius) ** 4 * (1.0 + 4.0 * radius))
            expected_beta[:, j - 1, i - 1] = np.where(
                above_ground[:, j - 1, i - 1], weight, np.float32(0.0)
            )
    expected_target_valid = np.zeros_like(target_valid)
    expected_target = background_omega.astype(np.float32)
    column = above_ground[:, seed_j - 1, seed_i - 1]
    active_levels = np.flatnonzero(column)
    if active_levels.size < 2:
        raise ValueError("manufactured target column is too shallow")
    bottom = int(active_levels[0])
    for k in active_levels:
        vertical_weight = np.sin(
            np.pi * (float(k - bottom) + 0.5) / float(active_levels.size)
        )
        if vertical_weight < 0.25:
            continue
        expected_target_valid[k, seed_j - 1, seed_i - 1] = True
        expected_target[k, seed_j - 1, seed_i - 1] = np.float32(
            background_omega[k, seed_j - 1, seed_i - 1]
            + expected_configuration["target_amplitude_pas"] * vertical_weight
        )
        expected_beta[k, seed_j - 1, seed_i - 1] = 1.0
    if not np.array_equal(target_valid, expected_target_valid) or \
            not np.array_equal(omega_target.astype(np.float32), expected_target):
        raise ValueError("manufactured target differs from the fixed single-column sine fixture")
    if not np.array_equal(beta.astype(np.float32), expected_beta.astype(np.float32)):
        raise ValueError("manufactured localization differs from the fixed Wendland fixture")

    def active_rms(values: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(values[active]))))

    residual_contract = {
        "continuity_background_rms": (residual_background, background, background_max),
        "continuity_candidate_rms": (residual_candidate, candidate, candidate_max),
        "continuity_proposed_rms": (residual_proposed, proposed, proposed_max),
        "continuity_projected_rms": (residual_projected, projected, projected_max),
    }
    for name, (values, logged, logged_max) in residual_contract.items():
        recomputed = active_rms(values)
        tolerance = max(1.0e-12, 5.0e-6 * max(abs(recomputed), abs(logged)))
        if abs(recomputed - logged) > tolerance:
            raise ValueError(f"persisted residual differs from logged norm: {name}")
        recomputed_max = float(np.max(np.abs(values[active])))
        max_tolerance = max(
            1.0e-12, 5.0e-6 * max(abs(recomputed_max), abs(logged_max))
        )
        if abs(recomputed_max - logged_max) > max_tolerance:
            raise ValueError(f"persisted residual differs from logged maximum: {name}")
        if np.any(values[~active] != 0.0):
            raise ValueError(f"residual is nonzero outside the active mask: {name}")
    linearity_error = float(np.max(np.abs(
        residual_candidate - residual_background - residual_projected
    )))
    if linearity_error > 1.0e-9:
        raise ValueError("candidate/background residuals do not close with the increment")
    du = candidate_u - background_u
    dv = candidate_v - background_v
    domega = candidate_omega - background_omega
    expected_changed = (du != 0.0) | (dv != 0.0) | (domega != 0.0)
    if not np.array_equal(changed, expected_changed):
        raise ValueError("persisted changed mask differs from the fields")
    if np.any(expected_changed & ~active):
        raise ValueError("a dynamic change escaped localization support")
    if np.any((domega != 0.0) & ~target_valid):
        raise ValueError("an omega correction escaped target authority")
    hydro_changed = proposal_hydro != original_hydro
    if np.any(hydro_changed & (hydro_support == 0)):
        raise ValueError("a hydrometeor proposal escaped hydrometeor support")
    recomputed_counts = {
        "target_cells": int(np.count_nonzero(target_valid)),
        "beta_cells": int(np.count_nonzero(beta > 0.0)),
        "bottom_boundary_nonzero_cells": int(np.count_nonzero(np.abs(boundary) > 0.1)),
        "changed_cells": int(np.count_nonzero(changed)),
        "outside_support_changed_cells": int(np.count_nonzero(changed & (beta <= 0.0))),
    }
    for name, value in recomputed_counts.items():
        if integer_metrics[name] != value:
            raise ValueError(f"logged count differs from diagnostic: {name}")
    calculated_wind = float(np.max(np.hypot(du, dv)))
    calculated_omega = float(np.max(np.abs(domega)))
    if abs(calculated_wind - max_wind) > 2.0e-7:
        raise ValueError("persisted wind increment differs from the gate")
    if abs(calculated_omega - max_omega) > 2.0e-7:
        raise ValueError("persisted omega increment differs from the gate")

    wind_jump = max(
        float(np.max(np.abs(np.diff(du, axis=2)))),
        float(np.max(np.abs(np.diff(du, axis=1)))),
        float(np.max(np.abs(np.diff(du, axis=0)))),
        float(np.max(np.abs(np.diff(dv, axis=2)))),
        float(np.max(np.abs(np.diff(dv, axis=1)))),
        float(np.max(np.abs(np.diff(dv, axis=0)))),
    )
    omega_jump = max(
        float(np.max(np.abs(np.diff(domega, axis=2)))),
        float(np.max(np.abs(np.diff(domega, axis=1)))),
        float(np.max(np.abs(np.diff(domega, axis=0)))),
    )
    # These are predeclared engineering guards for this 0.02 Pa/s numerical
    # perturbation, not evidence that a forecast will be free of waves.
    if wind_jump > 0.10 or omega_jump > 0.02:
        raise ValueError("neighbor-jump wave proxy exceeded the numerical-test guard")
    boundary_jump = max(
        float(np.max(np.abs(np.diff(boundary, axis=1)))),
        float(np.max(np.abs(np.diff(boundary, axis=0)))),
    )
    if np.any(~np.any(above_ground, axis=0)):
        raise ValueError("a column has no above-ground level")
    bottom_index = np.argmax(above_ground, axis=0)
    bottom_background = np.take_along_axis(
        background_omega, bottom_index[None, :, :], axis=0
    )[0]
    bottom_candidate = np.take_along_axis(
        candidate_omega, bottom_index[None, :, :], axis=0
    )[0]

    def maximum_neighbor_jump(values: np.ndarray) -> float:
        return max(float(np.max(np.abs(np.diff(values, axis=axis)))) for axis in range(3))

    background_omega_jump = maximum_neighbor_jump(background_omega)
    candidate_omega_jump = maximum_neighbor_jump(candidate_omega)
    background_wind_jump = max(
        maximum_neighbor_jump(background_u), maximum_neighbor_jump(background_v)
    )
    candidate_wind_jump = max(
        maximum_neighbor_jump(candidate_u), maximum_neighbor_jump(candidate_v)
    )
    original_hydro_mass = float(np.sum(original_hydro * original_dry_mass))
    proposal_hydro_mass = float(np.sum(proposal_hydro * proposal_dry_mass))
    hydro_delta = np.abs(proposal_hydro - original_hydro)[hydro_changed]
    hydro_quantiles = (
        np.quantile(hydro_delta, [0.5, 0.9, 0.99, 1.0]).tolist()
        if hydro_delta.size
        else [0.0, 0.0, 0.0, 0.0]
    )
    return {
        "schema": 1,
        "decision": "NUMERICAL_REAL_GEOMETRY_PASS",
        "science_authority": "NONE",
        "algorithm_target_science_assessed": False,
        "artifacts": {
            "diagnostic_sha256": hashlib.sha256(diagnostic.read_bytes()).hexdigest(),
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        },
        "metrics": {
            **integer_metrics,
            "continuity_reduction_ratio": projected / proposed,
            "continuity_background_rms": background,
            "continuity_candidate_rms": candidate,
            "continuity_residual_linearity_error": linearity_error,
            "max_wind_increment_ms": calculated_wind,
            "max_omega_increment_pas": calculated_omega,
            "max_neighbor_wind_component_jump_ms": wind_jump,
            "max_neighbor_omega_jump_pas": omega_jump,
            "neighbor_jump_wave_proxy_passed": True,
            "bottom_boundary_min_pas": float(np.min(boundary)),
            "bottom_boundary_max_pas": float(np.max(boundary)),
            "max_neighbor_bottom_boundary_jump_pas": boundary_jump,
            "max_background_top_boundary_jump_pas": float(
                np.max(np.abs(background_omega[-1] - top_boundary))
            ),
            "max_candidate_top_boundary_jump_pas": float(
                np.max(np.abs(candidate_omega[-1] - top_boundary))
            ),
            "max_background_bottom_boundary_jump_pas": float(
                np.max(np.abs(bottom_background - boundary))
            ),
            "max_candidate_bottom_boundary_jump_pas": float(
                np.max(np.abs(bottom_candidate - boundary))
            ),
            "max_neighbor_background_omega_jump_pas": background_omega_jump,
            "max_neighbor_candidate_omega_jump_pas": candidate_omega_jump,
            "max_neighbor_background_wind_component_jump_ms": background_wind_jump,
            "max_neighbor_candidate_wind_component_jump_ms": candidate_wind_jump,
            "original_hydrometeor_mass_kg": original_hydro_mass,
            "proposal_hydrometeor_mass_kg": proposal_hydro_mass,
            "hydrometeor_mass_change_kg": proposal_hydro_mass - original_hydro_mass,
            "hydrometeor_absolute_delta_quantiles_kgkg": hydro_quantiles,
            "target_response_failure_fraction": response_failure,
            "trust_region_fraction": trust,
            "operator_identity_max": identity,
            "geostrophic_background_rms": geo_background,
            "geostrophic_candidate_rms": geo_candidate,
            "divergent_increment_rms": divergent,
            "rotational_increment_rms": rotational,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("diagnostic", type=Path)
    parser.add_argument("log", type=Path)
    parser.add_argument("--json", required=True, type=Path)
    args = parser.parse_args()
    report = validate(args.diagnostic, args.log)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(report["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
