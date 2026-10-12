#!/usr/bin/env python3
"""Independent CP06-A pressure-force and dry-flux calculation from state fields."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


GRAVITY = 9.80665
QUALITY_EXCLUDED = 0b111


def get(dataset: Dataset, name: str) -> np.ndarray:
    value = dataset.variables[name][:]
    if np.ma.isMaskedArray(value):
        fill = np.nan if np.issubdtype(value.dtype, np.floating) else 0
        value = value.filled(fill)
    return np.asarray(value)


def cell_usable(dataset: Dataset, prefix: str, name: str) -> np.ndarray:
    valid_name = f"{prefix}_{name}_valid"
    if valid_name not in dataset.variables:
        return np.isfinite(get(dataset, f"{prefix}_{name}"))
    valid = get(dataset, f"{prefix}_{name}_valid") != 0
    quality = get(dataset, f"{prefix}_{name}_quality")
    source = get(dataset, f"{prefix}_{name}_source")
    return valid & ((quality & QUALITY_EXCLUDED) == 0) & (source > 0)


def face_segments(left: np.ndarray, right: np.ndarray):
    """Yield exact overlap segments from cloud_bal_grid_geometry partitioning."""
    i = j = 0
    while i < left.size - 1 and j < right.size - 1:
        thickness = min(left[i], right[j]) - max(left[i + 1], right[j + 1])
        if thickness > 0.0:
            yield i, j, thickness
        if left[i + 1] > right[j + 1]:
            i += 1
        elif right[j + 1] > left[i + 1]:
            j += 1
        else:
            i += 1
            j += 1


def composition_dry_fraction(dataset: Dataset, prefix: str, above: np.ndarray) -> np.ndarray:
    shape = get(dataset, f"{prefix}_vapor").shape
    water = np.zeros(shape, dtype=np.float64)
    for species in ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel"):
        values = get(dataset, f"{prefix}_{species}").astype(np.float64)
        usable = cell_usable(dataset, prefix, species)
        water[usable] += values[usable]
    fraction = np.zeros_like(water)
    fraction[above] = 1.0 / (1.0 + water[above])
    return fraction


def dry_fraction(dataset: Dataset, prefix: str, above: np.ndarray) -> np.ndarray:
    dry_measure_name = ("candidate_dry_air_mass_measure" if prefix == "candidate"
                        else "dry_air_mass_measure")
    if dry_measure_name not in dataset.variables:
        return composition_dry_fraction(dataset, prefix, above)
    pressure_measure = get(dataset, "pressure_mass_measure").astype(np.float64)
    dry_measure = get(dataset, dry_measure_name).astype(np.float64)
    fraction = np.zeros_like(pressure_measure)
    fraction[above] = dry_measure[above] / pressure_measure[above]
    return fraction


def independent_flux(dataset: Dataset, prefix: str,
                     dry_override: np.ndarray | None = None,
                     wind_override: tuple[np.ndarray, np.ndarray] | None = None
                     ) -> dict[str, np.ndarray | float]:
    """Build dry-air face flux divergence without operator/divergence readbacks."""
    above = get(dataset, "above_ground") != 0
    u, v, omega = (get(dataset, f"{prefix}_{field}").astype(np.float64)
                   for field in ("u", "v", "omega"))
    if wind_override is not None:
        u, v = (np.asarray(value, dtype=np.float64) for value in wind_override)
    # NetCDF stores (z,y,x); the Fortran operator is indexed (x,y,z).
    dz, ny, nx = u.shape
    pressure_i = get(dataset, "pressure_interface").astype(np.float64)
    volume = get(dataset, "pressure_mass_measure").astype(np.float64)
    dry = dry_fraction(dataset, prefix, above) if dry_override is None else dry_override
    cell = above & np.isfinite(u) & np.isfinite(v) & np.isfinite(omega)
    dx = float(dataset.getncattr("grid_dx_m"))
    dy = float(dataset.getncattr("grid_dy_m"))
    cell_dp = get(dataset, "cell_dp").astype(np.float64)
    divergence = np.zeros_like(volume)
    internal_lateral = np.zeros(2, dtype=np.float64)
    internal_vertical = np.zeros(2, dtype=np.float64)
    boundary = np.zeros(4, dtype=np.float64)  # x-min, x-max, y-min, y-max
    for y in range(ny):
        for x in range(nx - 1):
            left_i = pressure_i[:, y, x]
            right_i = pressure_i[:, y, x + 1]
            for kl, kr, dp in face_segments(left_i, right_i):
                if not (cell[kl, y, x] and cell[kr, y, x + 1]):
                    continue
                wl = dx / (dx + dx)
                wr = 1.0 - wl
                area = dy * dp / GRAVITY
                flux = area * (wl * u[kl, y, x] * dry[kl, y, x] +
                               wr * u[kr, y, x + 1] * dry[kr, y, x + 1])
                divergence[kl, y, x] += flux
                divergence[kr, y, x + 1] -= flux
                internal_lateral += (flux, -flux)
    for y in range(ny - 1):
        for x in range(nx):
            south_i = pressure_i[:, y, x]
            north_i = pressure_i[:, y + 1, x]
            for ks, kn, dp in face_segments(south_i, north_i):
                if not (cell[ks, y, x] and cell[kn, y + 1, x]):
                    continue
                area = dx * dp / GRAVITY
                flux = area * (0.5 * v[ks, y, x] * dry[ks, y, x] +
                               0.5 * v[kn, y + 1, x] * dry[kn, y + 1, x])
                divergence[ks, y, x] += flux
                divergence[kn, y + 1, x] -= flux
                internal_lateral += (flux, -flux)

    # Pressure-center interpolation matches the source's pressure interface.
    pressure = get(dataset, "pressure").astype(np.float64)
    for k in range(dz - 1):
        denominator = pressure[k] - pressure[k + 1]
        left_weight = (pressure_i[k + 1] - pressure[k + 1]) / denominator
        right_weight = 1.0 - left_weight
        face = cell[k] & cell[k + 1]
        flux = (dx * dy / GRAVITY) * (
            left_weight * omega[k] * dry[k] + right_weight * omega[k + 1] * dry[k + 1])
        divergence[k] -= np.where(face, flux, 0.0)
        divergence[k + 1] += np.where(face, flux, 0.0)
        internal_vertical += (float(np.sum(np.where(face, -flux, 0.0))),
                              float(np.sum(np.where(face, flux, 0.0))))

    # Zero-gradient horizontal perimeter flux: use the adjacent cell's dry fraction.
    for k in range(dz):
        for y in range(ny):
            if cell[k, y, 0]:
                flux = -dy * cell_dp[k, y, 0] / GRAVITY * \
                    u[k, y, 0] * dry[k, y, 0]
                divergence[k, y, 0] += flux
                boundary[0] += flux
            if cell[k, y, nx - 1]:
                flux = dy * cell_dp[k, y, nx - 1] / GRAVITY * \
                    u[k, y, nx - 1] * dry[k, y, nx - 1]
                divergence[k, y, nx - 1] += flux
                boundary[1] += flux
        for x in range(nx):
            if cell[k, 0, x]:
                flux = -dx * cell_dp[k, 0, x] / GRAVITY * \
                    v[k, 0, x] * dry[k, 0, x]
                divergence[k, 0, x] += flux
                boundary[2] += flux
            if cell[k, ny - 1, x]:
                flux = dx * cell_dp[k, ny - 1, x] / GRAVITY * \
                    v[k, ny - 1, x] * dry[k, ny - 1, x]
                divergence[k, ny - 1, x] += flux
                boundary[3] += flux

    top = get(dataset, "omega_top_boundary").astype(np.float64)
    bottom = get(dataset, "omega_bottom_boundary").astype(np.float64)
    top_valid = get(dataset, "omega_top_boundary_valid") != 0
    bottom_valid = get(dataset, "omega_bottom_boundary_valid") != 0
    vertical_boundary = np.zeros(2, dtype=np.float64)
    for y in range(ny):
        for x in range(nx):
            levels = np.flatnonzero(cell[:, y, x])
            if not levels.size:
                continue
            kb, kt = levels[0], levels[-1]
            area = dx * dy / GRAVITY
            if top_valid[y, x]:
                flux = -area * top[y, x] * dry[kt, y, x]
                divergence[kt, y, x] += flux
                vertical_boundary[0] += flux
            if bottom_valid[y, x]:
                flux = area * bottom[y, x] * dry[kb, y, x]
                divergence[kb, y, x] += flux
                vertical_boundary[1] += flux
    return {"divergence": divergence, "cell": cell, "dry_fraction": dry,
            "internal_lateral_face_pair_sum": float(np.sum(internal_lateral)),
            "internal_vertical_face_pair_sum": float(np.sum(internal_vertical)),
            "lateral_boundary_flux": boundary, "vertical_boundary_flux": vertical_boundary,
            "global_flux_sum": float(np.sum(divergence))}


def independent_flux_adjoint(dataset: Dataset, prefix: str, dual: np.ndarray,
                             dry_override: np.ndarray | None = None
                             ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Apply the transpose of the state-wind-to-cell-flux map from the same geometry.

    Top/bottom boundary omega values are fixed affine data, not cell omega controls;
    the returned third array is the adjoint for cell-centered omega only.
    """
    above = get(dataset, "above_ground") != 0
    u, v, omega = (get(dataset, f"{prefix}_{field}").astype(np.float64)
                   for field in ("u", "v", "omega"))
    if np.shape(dual) != np.shape(u):
        raise ValueError("dual must have the state (z,y,x) shape")
    pressure_i = get(dataset, "pressure_interface").astype(np.float64)
    pressure = get(dataset, "pressure").astype(np.float64)
    dry = dry_fraction(dataset, prefix, above) if dry_override is None else dry_override
    cell = above & np.isfinite(u) & np.isfinite(v) & np.isfinite(omega)
    nz, ny, nx = u.shape
    dx, dy = float(dataset.getncattr("grid_dx_m")), float(dataset.getncattr("grid_dy_m"))
    cell_dp = get(dataset, "cell_dp").astype(np.float64)
    adj_u, adj_v, adj_omega = (np.zeros_like(u) for _ in range(3))

    for y in range(ny):
        for x in range(nx - 1):
            for kl, kr, dp in face_segments(pressure_i[:, y, x], pressure_i[:, y, x + 1]):
                if not (cell[kl, y, x] and cell[kr, y, x + 1]):
                    continue
                factor = dy * dp / GRAVITY * 0.5 * (dual[kl, y, x] - dual[kr, y, x + 1])
                adj_u[kl, y, x] += factor * dry[kl, y, x]
                adj_u[kr, y, x + 1] += factor * dry[kr, y, x + 1]
    for y in range(ny - 1):
        for x in range(nx):
            for ks, kn, dp in face_segments(pressure_i[:, y, x], pressure_i[:, y + 1, x]):
                if not (cell[ks, y, x] and cell[kn, y + 1, x]):
                    continue
                factor = dx * dp / GRAVITY * 0.5 * (dual[ks, y, x] - dual[kn, y + 1, x])
                adj_v[ks, y, x] += factor * dry[ks, y, x]
                adj_v[kn, y + 1, x] += factor * dry[kn, y + 1, x + 0]

    area = dx * dy / GRAVITY
    for k in range(nz - 1):
        denom = pressure[k] - pressure[k + 1]
        left_weight = (pressure_i[k + 1] - pressure[k + 1]) / denom
        right_weight = 1.0 - left_weight
        face = cell[k] & cell[k + 1]
        factor = area * (dual[k + 1] - dual[k])
        adj_omega[k] += np.where(face, factor * left_weight * dry[k], 0.0)
        adj_omega[k + 1] += np.where(face, factor * right_weight * dry[k + 1], 0.0)

    for k in range(nz):
        adj_u[k, :, 0] += np.where(cell[k, :, 0],
                                    -dy * cell_dp[k, :, 0] / GRAVITY * dry[k, :, 0] * dual[k, :, 0], 0.0)
        adj_u[k, :, -1] += np.where(cell[k, :, -1],
                                     dy * cell_dp[k, :, -1] / GRAVITY * dry[k, :, -1] * dual[k, :, -1], 0.0)
        adj_v[k, 0, :] += np.where(cell[k, 0, :],
                                    -dx * cell_dp[k, 0, :] / GRAVITY * dry[k, 0, :] * dual[k, 0, :], 0.0)
        adj_v[k, -1, :] += np.where(cell[k, -1, :],
                                     dx * cell_dp[k, -1, :] / GRAVITY * dry[k, -1, :] * dual[k, -1, :], 0.0)
    return adj_u, adj_v, adj_omega


def pressure_force(dataset: Dataset, shared_mask: np.ndarray,
                   candidate_wind_override: tuple[np.ndarray, np.ndarray] | None = None
                   ) -> dict[str, np.ndarray | float]:
    """Evaluate source geostrophic stencil and exactly split pressure/Coriolis changes."""
    u0, v0 = get(dataset, "background_u").astype(np.float64), get(dataset, "background_v").astype(np.float64)
    u1, v1 = get(dataset, "candidate_u").astype(np.float64), get(dataset, "candidate_v").astype(np.float64)
    if candidate_wind_override is not None:
        u1, v1 = (np.asarray(value, dtype=np.float64) for value in candidate_wind_override)
    phi0 = get(dataset, "background_geopotential").astype(np.float64)
    phi1 = get(dataset, "candidate_geopotential").astype(np.float64)
    lat = np.deg2rad(get(dataset, "latitude").astype(np.float64))
    dy = float(dataset.getncattr("grid_dy_m")); dx = float(dataset.getncattr("grid_dx_m"))
    f = 1.458423e-4 * np.sin(lat)[None, :, :]
    dphi = phi1 - phi0
    gx = np.zeros_like(phi0); gy = np.zeros_like(phi0)
    direct_delta_ru = np.zeros_like(phi0); direct_delta_rv = np.zeros_like(phi0)
    phi_edge_stencil = np.zeros_like(shared_mask)
    phi_internal_stencil = np.zeros_like(shared_mask)
    above = get(dataset, "above_ground") != 0
    pressure = get(dataset, "pressure")
    usable = above & np.isfinite(u0) & np.isfinite(v0) & np.isfinite(u1) & np.isfinite(v1)
    phi_usable = {}
    for prefix in ("background", "candidate"):
        q = get(dataset, f"{prefix}_geopotential_quality")
        src = get(dataset, f"{prefix}_geopotential_source")
        valid = get(dataset, f"{prefix}_geopotential_valid") != 0
        phi_usable[prefix] = valid & ((q & QUALITY_EXCLUDED) == 0) & (src > 0)
    for k, y, x in zip(*np.where(shared_mask)):
        if x + 1 < phi0.shape[2] and usable[k, y, x + 1]:
            xn, sign_x = x + 1, 1.0
        elif x > 0 and usable[k, y, x - 1]:
            xn, sign_x = x - 1, -1.0
        else:
            continue
        if y + 1 < phi0.shape[1] and usable[k, y + 1, x]:
            yn, sign_y = y + 1, 1.0
        elif y > 0 and usable[k, y - 1, x]:
            yn, sign_y = y - 1, -1.0
        else:
            continue
        if not (phi_usable["background"][k,y,x] and phi_usable["background"][k,y,xn] and
                phi_usable["background"][k,y+int(np.sign(yn-y)),x] and
                phi_usable["candidate"][k,y,x] and phi_usable["candidate"][k,y,xn] and
                phi_usable["candidate"][k,y+int(np.sign(yn-y)),x]):
            continue
        xdistance = abs(xn - x) * 0.5 * (dx + dx)
        ydistance = abs(yn - y) * 0.5 * (dy + dy)
        gx[k, y, x] = sign_x * (dphi[k, y, xn] - dphi[k, y, x]) / xdistance
        gy[k, y, x] = sign_y * (dphi[k, yn, x] - dphi[k, y, x]) / ydistance
        grad0x = sign_x * (phi0[k, y, xn] - phi0[k, y, x]) / xdistance
        grad1x = sign_x * (phi1[k, y, xn] - phi1[k, y, x]) / xdistance
        grad0y = sign_y * (phi0[k, yn, x] - phi0[k, y, x]) / ydistance
        grad1y = sign_y * (phi1[k, yn, x] - phi1[k, y, x]) / ydistance
        direct_delta_ru[k, y, x] = (-f[0, y, x] * v1[k, y, x] + grad1x) - \
            (-f[0, y, x] * v0[k, y, x] + grad0x)
        direct_delta_rv[k, y, x] = (f[0, y, x] * u1[k, y, x] + grad1y) - \
            (f[0, y, x] * u0[k, y, x] + grad0y)
        x_change = (dphi[k, y, xn] != 0.0, dphi[k, y, x] != 0.0)
        y_change = (dphi[k, yn, x] != 0.0, dphi[k, y, x] != 0.0)
        phi_edge_stencil[k, y, x] = (x_change[0] != x_change[1] or
                                     y_change[0] != y_change[1])
        phi_internal_stencil[k, y, x] = all(x_change) and all(y_change)
    du, dv = u1 - u0, v1 - v0
    coriolis_u, coriolis_v = -f * dv, f * du
    total_u, total_v = gx + coriolis_u, gy + coriolis_v
    # The discrete decomposition is linear: ΔR = ∇δΦ + (-fδv, fδu).
    sq = lambda x: float(np.mean(np.square(x[shared_mask])))
    return {"pressure_gradient_x": gx, "pressure_gradient_y": gy,
            "phi_edge_stencil": phi_edge_stencil,
            "phi_internal_stencil": phi_internal_stencil,
            "coriolis_u": coriolis_u, "coriolis_v": coriolis_v,
            "total_u": total_u, "total_v": total_v,
            "shared_cells": int(np.count_nonzero(shared_mask)),
            "pressure_gradient_rms": float(np.sqrt(0.5 * (sq(gx) + sq(gy)))),
            "coriolis_rms": float(np.sqrt(0.5 * (sq(coriolis_u) + sq(coriolis_v)))),
            "total_force_rms": float(np.sqrt(0.5 * (sq(total_u) + sq(total_v)))),
            "cross_term_mean": float(np.mean((gx[shared_mask] * coriolis_u[shared_mask]) +
                                              (gy[shared_mask] * coriolis_v[shared_mask]))),
            "reconstruction_max": float(max(np.max(np.abs(direct_delta_ru[shared_mask] - total_u[shared_mask])),
                                             np.max(np.abs(direct_delta_rv[shared_mask] - total_v[shared_mask]))))}


def geostrophic_rms(dataset: Dataset, prefix: str, mask: np.ndarray,
                    wind_override: tuple[np.ndarray, np.ndarray] | None = None
                    ) -> tuple[float, int]:
    """Reproduce geostrophic_residual on an externally fixed evaluation mask."""
    u = get(dataset, f"{prefix}_u").astype(np.float64)
    v = get(dataset, f"{prefix}_v").astype(np.float64)
    if wind_override is not None:
        u, v = (np.asarray(value, dtype=np.float64) for value in wind_override)
    phi = get(dataset, f"{prefix}_geopotential").astype(np.float64)
    above = get(dataset, "above_ground") != 0
    pressure = get(dataset, "pressure")
    usable = above & np.isfinite(u) & np.isfinite(v) & np.isfinite(pressure)[:, None, None]
    q = get(dataset, f"{prefix}_geopotential_quality")
    src = get(dataset, f"{prefix}_geopotential_source")
    valid = get(dataset, f"{prefix}_geopotential_valid") != 0
    phi_usable = valid & ((q & QUALITY_EXCLUDED) == 0) & (src > 0) & np.isfinite(phi)
    lat = np.deg2rad(get(dataset, "latitude").astype(np.float64))
    dx = float(dataset.getncattr("grid_dx_m")); dy = float(dataset.getncattr("grid_dy_m"))
    pi_f = 1.458423e-4 * np.sin(lat)
    residual_sq = []
    missing = 0
    for k, y, x in zip(*np.where(mask)):
        ix = x + 1 if x + 1 < u.shape[2] and usable[k, y, x+1] else (
            x - 1 if x > 0 and usable[k, y, x-1] else -1)
        jy = y + 1 if y + 1 < u.shape[1] and usable[k, y+1, x] else (
            y - 1 if y > 0 and usable[k, y-1, x] else -1)
        if ix < 0 or jy < 0 or not (phi_usable[k,y,x] and phi_usable[k,y,ix] and phi_usable[k,jy,x]):
            missing += 1
            continue
        gx = (phi[k,y,ix] - phi[k,y,x]) / ((ix-x) * dx)
        gy = (phi[k,jy,x] - phi[k,y,x]) / ((jy-y) * dy)
        ru = -pi_f[y,x] * v[k,y,x] + gx
        rv = pi_f[y,x] * u[k,y,x] + gy
        residual_sq.append(ru * ru + rv * rv)
    if missing:
        raise ValueError(f"{prefix}: {missing}/{np.count_nonzero(mask)} fixed-mask cells lack geostrophic stencil coverage")
    if not residual_sq:
        raise ValueError(f"{prefix}: fixed geostrophic mask is empty")
    return float(np.sqrt(np.sum(residual_sq) / (2 * len(residual_sq)))), len(residual_sq)


def force_summary(force: dict[str, np.ndarray | float], mask: np.ndarray) -> dict[str, float | int]:
    gx, gy = force["pressure_gradient_x"], force["pressure_gradient_y"]
    cu, cv = force["coriolis_u"], force["coriolis_v"]
    ru, rv = force["total_u"], force["total_v"]
    count = int(np.count_nonzero(mask))
    if not count:
        return {"cells": 0}
    return {"cells": count,
            "pressure_gradient_x_mean": float(np.mean(gx[mask])),
            "pressure_gradient_y_mean": float(np.mean(gy[mask])),
            "coriolis_u_mean": float(np.mean(cu[mask])),
            "coriolis_v_mean": float(np.mean(cv[mask])),
            "total_u_mean": float(np.mean(ru[mask])),
            "total_v_mean": float(np.mean(rv[mask])),
            "pressure_gradient_rms": float(np.sqrt(np.mean(gx[mask]**2 + gy[mask]**2) / 2)),
            "coriolis_rms": float(np.sqrt(np.mean(cu[mask]**2 + cv[mask]**2) / 2)),
            "total_force_rms": float(np.sqrt(np.mean(ru[mask]**2 + rv[mask]**2) / 2)),
            "cross_term_mean": float(np.mean(gx[mask]*cu[mask] + gy[mask]*cv[mask])),
            "reconstruction_max": float(max(np.max(np.abs(ru[mask]-gx[mask]-cu[mask])),
                                             np.max(np.abs(rv[mask]-gy[mask]-cv[mask]))))}


def state_report(path: Path, shared: np.ndarray) -> dict[str, object]:
    with Dataset(path) as ds:
        force = pressure_force(ds, shared)
        background_flux = independent_flux(ds, "background")
        flux = independent_flux(ds, "candidate")
        above = get(ds, "above_ground") != 0
        composition_fraction = composition_dry_fraction(ds, "candidate", above)
        composition_flux = independent_flux(ds, "candidate", composition_fraction)
        mask_edge = np.zeros_like(shared)
        mask_edge[:, :, 0] = shared[:, :, 0]
        mask_edge[:, :, -1] |= shared[:, :, -1]
        mask_edge[:, 0, :] |= shared[:, 0, :]
        mask_edge[:, -1, :] |= shared[:, -1, :]
        for shift in (1, -1):
            mask_edge |= shared & ~np.roll(shared, shift, axis=1)
            mask_edge |= shared & ~np.roll(shared, shift, axis=2)
        interior = shared & ~mask_edge
        phi_edge = shared & force["phi_edge_stencil"]
        phi_internal = shared & force["phi_internal_stencil"]
        phi_support = get(ds, "geopotential_support") != 0
        phi_changed = (get(ds, "candidate_geopotential") != get(ds, "background_geopotential")) & shared
        target = get(ds, "candidate_dry_air_flux_divergence")
        background_target = get(ds, "background_dry_air_flux_divergence")
        calc = flux["divergence"]
        background_calc = background_flux["divergence"]
        composition_calc = composition_flux["divergence"]
        pressure_mass = get(ds, "pressure_mass_measure").astype(np.float64)
        state_fraction = np.zeros_like(pressure_mass)
        state_fraction[above] = get(ds, "candidate_dry_air_mass_measure")[above] / pressure_mass[above]
        fraction_delta = composition_fraction[above] - state_fraction[above]
        expected_dry_mass = composition_fraction[above] * pressure_mass[above]
        state_dry_mass = get(ds, "candidate_dry_air_mass_measure")[above]
        consistency_tolerance = 2.0e-7 * np.maximum(expected_dry_mass, 1.0)
        usable = flux["cell"]
        def flux_summary(item: dict[str, np.ndarray | float]) -> dict[str, object]:
            boundary_total = float(np.sum(item["lateral_boundary_flux"]) +
                                   np.sum(item["vertical_boundary_flux"]))
            return {"global_sum_kg_s": item["global_flux_sum"],
                    "boundary_sum_kg_s": boundary_total,
                    "global_boundary_closure_kg_s": float(item["global_flux_sum"] - boundary_total),
                    "internal_lateral_face_pair_sum_kg_s": item["internal_lateral_face_pair_sum"],
                    "internal_vertical_face_pair_sum_kg_s": item["internal_vertical_face_pair_sum"],
                    "lateral_boundary_kg_s": np.asarray(item["lateral_boundary_flux"]).tolist(),
                    "top_bottom_boundary_kg_s": np.asarray(item["vertical_boundary_flux"]).tolist(),
                    "usable_cells": int(np.count_nonzero(item["cell"]))}

        report = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "shared_mask_cells": force["shared_cells"],
                  "source_geostrophic_rms": {
                      "OFF_background": {"all": geostrophic_rms(ds, "background", shared),
                                         "interior": geostrophic_rms(ds, "background", interior),
                                         "validation_support_boundary": geostrophic_rms(ds, "background", mask_edge)},
                      "candidate": {"all": geostrophic_rms(ds, "candidate", shared),
                                    "interior": geostrophic_rms(ds, "candidate", interior),
                                    "validation_support_boundary": geostrophic_rms(ds, "candidate", mask_edge)}},
                  "force": {"all": force_summary(force, shared),
                            "interior": force_summary(force, interior),
                            "validation_support_boundary": force_summary(force, mask_edge),
                            "phi_support_edge_stencils": force_summary(force, phi_edge),
                            "phi_internal_stencils": force_summary(force, phi_internal),
                            "phi_support_cells": int(np.count_nonzero(phi_support)),
                            "phi_changed_cells_on_fixed_support": int(np.count_nonzero(phi_changed))},
                  "independent_flux": {"OFF_background": flux_summary(background_flux),
                      "candidate": flux_summary(flux),
                      "OFF_persisted_divergence_max_abs_difference_kg_s": float(np.max(np.abs(background_calc[usable] - background_target[usable]))),
                      "OFF_persisted_divergence_rms_difference_kg_s": float(np.sqrt(np.mean(np.square(background_calc[usable] - background_target[usable])))),
                      "persisted_divergence_max_abs_difference_kg_s": float(np.max(np.abs(calc[usable] - target[usable]))),
                      "persisted_divergence_rms_difference_kg_s": float(np.sqrt(np.mean(np.square(calc[usable] - target[usable])))),
                      "composition_reconstruction": {
                          "dry_fraction_max_abs_difference": float(np.max(np.abs(fraction_delta))),
                          "dry_fraction_rms_difference": float(np.sqrt(np.mean(fraction_delta**2))),
                          "dry_fraction_max_relative_difference": float(np.max(np.abs(fraction_delta) / np.maximum(np.abs(state_fraction[above]), 1e-300))),
                          "dry_mass_error_max_over_source_consistency_tolerance": float(np.max(np.abs(state_dry_mass - expected_dry_mass) / consistency_tolerance)),
                          "divergence_max_abs_difference_kg_s": float(np.max(np.abs(composition_calc[usable] - calc[usable]))),
                          "divergence_rms_difference_kg_s": float(np.sqrt(np.mean(np.square(composition_calc[usable] - calc[usable])))),
                          "divergence_max_relative_to_state_max": float(np.max(np.abs(composition_calc[usable] - calc[usable])) / max(float(np.max(np.abs(calc[usable]))), 1e-300)),
                          "divergence_rms_relative_to_state_rms": float(np.sqrt(np.mean(np.square(composition_calc[usable] - calc[usable]))) / max(float(np.sqrt(np.mean(calc[usable]**2))), 1e-300)),
                      },
                  }}
        return report


WIND_DIAGNOSTIC_NAMES = (
    "input_objective", "candidate_objective", "input_force_rms", "candidate_force_rms",
    "input_normalized_force_rms", "candidate_normalized_force_rms",
    "continuity_candidate_rms", "continuity_candidate_max", "maximum_wind_increment",
    "projected_increment_rms", "projected_increment_max",
)


def read_wind_artifact(path: Path, shape: tuple[int, int, int]
                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Read and strictly validate the retained-wind stream-v1 binary contract."""
    raw = np.fromfile(path, dtype=np.uint8)
    expected_cells = int(np.prod(shape))
    expected_size = 4 * 4 + 2 * expected_cells * 4 + len(WIND_DIAGNOSTIC_NAMES) * 8
    if raw.size != expected_size:
        raise ValueError(f"wind artifact size {raw.size} != schema-v1 expected {expected_size}")
    header = np.frombuffer(raw[:16], dtype="<i4")
    expected_header = np.array([1, shape[2], shape[1], shape[0]], dtype=np.int32)
    if not np.array_equal(header, expected_header):
        raise ValueError(f"wind artifact header {header.tolist()} != {expected_header.tolist()}")
    offset = 16
    field_bytes = expected_cells * 4
    u = np.frombuffer(raw[offset:offset + field_bytes], dtype="<f4").astype(np.float64)
    offset += field_bytes
    v = np.frombuffer(raw[offset:offset + field_bytes], dtype="<f4").astype(np.float64)
    offset += field_bytes
    diagnostics = np.frombuffer(raw[offset:], dtype="<f8").copy()
    if not np.all(np.isfinite(u)) or not np.all(np.isfinite(v)) or not np.all(np.isfinite(diagnostics)):
        raise ValueError("wind artifact contains nonfinite values")
    # NetCDF's (z,y,x) shape in C order has the same x-fastest linear stream
    # layout as the producer's Fortran (x,y,z) arrays.
    winds = (u.reshape(shape, order="C"), v.reshape(shape, order="C"))
    return winds[0], winds[1], diagnostics


def dry_flux_norm(divergence: np.ndarray, volume: np.ndarray,
                  mask: np.ndarray) -> tuple[float, float, int]:
    if divergence.shape != volume.shape or mask.shape != volume.shape:
        raise ValueError("flux, mass measure, and mask shapes must match")
    if not np.any(mask) or np.any(volume[mask] <= 0.0):
        raise ValueError("dry flux diagnostic mask is empty or has nonpositive mass measure")
    values = divergence[mask] / volume[mask]
    return float(np.sqrt(np.mean(values * values))), float(np.max(np.abs(values))), int(np.count_nonzero(mask))


def evaluate_wind_artifact(netcdf_path: Path, artifact_path: Path) -> dict[str, object]:
    """Evaluate a wind-only artifact on the retained file's unchanged masks/geometry."""
    with Dataset(netcdf_path) as ds:
        force_mask = get(ds, "geostrophic_validation_support") != 0
        shell = get(ds, "background_validation_shell") != 0
        control = get(ds, "background_control_support") != 0
        shape = get(ds, "candidate_u").shape
        if (np.count_nonzero(force_mask), np.count_nonzero(control), np.count_nonzero(shell)) != (900, 500, 980):
            raise ValueError("retained force/control/shell masks do not match pinned 900/500/980 contract")
        refined_u, refined_v, diagnostics = read_wind_artifact(artifact_path, shape)
        before_geo, before_count = geostrophic_rms(ds, "candidate", force_mask)
        after_geo, refined_count = geostrophic_rms(ds, "candidate", force_mask, (refined_u, refined_v))
        if before_count != 900 or refined_count != 900:
            raise ValueError("force evaluation lost required fixed-mask coverage")
        background_flux = independent_flux(ds, "background")
        before_flux = independent_flux(ds, "candidate")
        after_flux = independent_flux(ds, "candidate", wind_override=(refined_u, refined_v))
        volume = get(ds, "pressure_mass_measure").astype(np.float64)
        masks = {"force_900": force_mask, "control_500": control, "validation_shell_980": shell}
        flux_metrics = {}
        for name, mask in masks.items():
            before_rms, before_max, count = dry_flux_norm(before_flux["divergence"], volume, mask)
            after_rms, after_max, after_count = dry_flux_norm(after_flux["divergence"], volume, mask)
            delta_rms, delta_max, delta_count = dry_flux_norm(
                after_flux["divergence"] - before_flux["divergence"], volume, mask)
            before_prior_rms, before_prior_max, _ = dry_flux_norm(
                before_flux["divergence"] - background_flux["divergence"], volume, mask)
            after_prior_rms, after_prior_max, _ = dry_flux_norm(
                after_flux["divergence"] - background_flux["divergence"], volume, mask)
            flux_metrics[name] = {"cells": count, "refined_cells": after_count, "increment_cells": delta_count,
                                  "before_rms_s-1": before_rms, "after_rms_s-1": after_rms,
                                  "increment_rms_s-1": delta_rms,
                                  "before_max_abs_s-1": before_max, "after_max_abs_s-1": after_max,
                                  "increment_max_abs_s-1": delta_max,
                                  "before_minus_OFF_rms_s-1": before_prior_rms,
                                  "after_minus_OFF_rms_s-1": after_prior_rms,
                                  "before_minus_OFF_max_abs_s-1": before_prior_max,
                                  "after_minus_OFF_max_abs_s-1": after_prior_max}
        force_delta = pressure_force(ds, force_mask, (refined_u, refined_v))
        baseline_delta = pressure_force(ds, force_mask)
        source_summary = lambda result: {"rms_m_s-2": result[0], "cells": result[1]}
        return {
            "input": {"path": str(netcdf_path), "sha256": hashlib.sha256(netcdf_path.read_bytes()).hexdigest()},
            "wind_artifact": {"path": str(artifact_path), "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                              "schema": "stream-v1 little-endian int32[version,nx,ny,nz], float32 absolute U,V in Fortran order, 11 float64 diagnostics",
                              "diagnostics": dict(zip(WIND_DIAGNOSTIC_NAMES, map(float, diagnostics)))},
            "fixed_masks": {"geostrophic_validation_support": 900, "background_control_support": 500,
                            "background_validation_shell": 980},
            "source_geostrophic_rms": {"input": source_summary((before_geo, before_count)),
                                        "refined_wind": source_summary((after_geo, refined_count))},
            "force_increment": {"input_candidate": force_summary(baseline_delta, force_mask),
                                "refined_candidate": force_summary(force_delta, force_mask)},
            "dry_flux_divergence": flux_metrics,
            "global_flux_integral_kg_s": {"input": float(before_flux["global_flux_sum"]),
                                          "refined_wind": float(after_flux["global_flux_sum"]),
                                          "boundary_change": float(after_flux["global_flux_sum"] - before_flux["global_flux_sum"])},
            "authority": "wind-only diagnostic evaluation; observation fit and scientific acceptance are not assessed",
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evaluate-wind-artifact", type=Path)
    args = parser.parse_args()
    if args.evaluate_wind_artifact:
        if len(args.files) != 1:
            parser.error("wind artifact evaluation takes exactly one retained NetCDF file")
        result = evaluate_wind_artifact(args.files[0], args.evaluate_wind_artifact)
        text = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
        print(text)
        return
    mask_source = next((path for path in args.files if path.stem.lower() == "coupled"), args.files[0])
    with Dataset(mask_source) as ds:
        shared = get(ds, "geostrophic_validation_support") != 0
    result = {path.stem.upper(): state_report(path, shared) for path in args.files}
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
