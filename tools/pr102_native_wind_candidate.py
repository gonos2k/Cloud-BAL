#!/usr/bin/env python3
"""Build a receipt-bound PR102 native-grid wind candidate (never launch it here)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import sys

import netCDF4
import numpy as np
import scipy
from scipy.sparse import block_diag, coo_matrix, csr_matrix

import pr94_cloud_response as cloud
import pr99_native_projection as projection
import pr87_native_history as history
from pr102_native_uv_smoother import solve_smooth_increment


ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = ROOT / "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json"
POLICY = ROOT / "docs/evidence/pr102_wind_structure_20261025/policy.json"
POLICY_SHA256 = "9ab0d468b9d46cce00fb9cc66162fa995beeda714f93cedba8c65d6e1891200d"
ROUGHNESS_FACTOR = 1.0
EXPECTED_NATIVE_LEVELS = 39
EXPECTED_SUPPORT_LEVELS = 613
EXPECTED_SUPPORT_COLUMNS = 16
EXPECTED_BUFFER_COLUMNS = 196
EXPECTED_FREE_FACES_PER_LAYER = 364


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _attributes_equal(left, right) -> bool:
    if set(left.ncattrs()) != set(right.ncattrs()):
        return False
    return all(np.array_equal(np.asarray(left.getncattr(name)),
                              np.asarray(right.getncattr(name)))
               for name in left.ncattrs())


def verify_only_wind_changed(candidate: Path, original_p: Path) -> None:
    """Require exact NetCDF structure and byte equality outside U/V."""
    with netCDF4.Dataset(candidate) as new, netCDF4.Dataset(original_p) as old:
        new.set_auto_mask(False)
        old.set_auto_mask(False)
        if set(new.dimensions) != set(old.dimensions):
            raise ValueError("candidate NetCDF dimensions differ from original_p")
        for name in old.dimensions:
            if (len(new.dimensions[name]) != len(old.dimensions[name]) or
                    new.dimensions[name].isunlimited() != old.dimensions[name].isunlimited()):
                raise ValueError(f"candidate dimension differs from original_p: {name}")
        if not _attributes_equal(new, old):
            raise ValueError("candidate global attributes differ from original_p")
        if set(new.variables) != set(old.variables):
            raise ValueError("candidate variables differ from original_p")
        for name in old.variables:
            before, after = old[name], new[name]
            if (before.dtype != after.dtype or before.dimensions != after.dimensions or
                    not _attributes_equal(before, after)):
                raise ValueError(f"candidate variable metadata differs from original_p: {name}")
            prior_values, candidate_values = before[...], after[...]
            if name not in {"U", "V"} and prior_values.tobytes() != candidate_values.tobytes():
                raise ValueError(f"candidate unexpectedly changed non-wind variable {name}")
            if name in {"U", "V"}:
                if candidate_values.dtype != np.dtype("float32"):
                    raise ValueError(f"candidate {name} must be finite REAL32")
                history._finite(new, name, 0)


def _read(ds, name: str) -> np.ndarray:
    return history._finite(ds, name, 0)


def _geometry(ds, free_u: np.ndarray, free_v: np.ndarray, gravity: float) -> dict:
    u_shape = free_u.shape
    v_shape = free_v.shape
    nz, ny, nxu = u_shape
    if v_shape != (nz, ny + 1, nxu - 1):
        raise ValueError("U/V free-face geometries have inconsistent native shapes")
    expected_dimensions = {
        "U": ("Time", "bottom_top", "south_north", "west_east_stag"),
        "V": ("Time", "bottom_top", "south_north_stag", "west_east"),
        "PH": ("Time", "bottom_top_stag", "south_north", "west_east"),
        "PHB": ("Time", "bottom_top_stag", "south_north", "west_east"),
        "MAPFAC_UX": ("Time", "south_north", "west_east_stag"),
        "MAPFAC_UY": ("Time", "south_north", "west_east_stag"),
        "MAPFAC_VX": ("Time", "south_north_stag", "west_east"),
        "MAPFAC_VY": ("Time", "south_north_stag", "west_east"),
    }
    for name, dimensions in expected_dimensions.items():
        if name not in ds.variables or ds[name].dimensions != dimensions:
            raise ValueError(f"{name} does not follow the pinned WRF native dimension contract")
    history._check_unit(ds, "U", ("m s-1", "m s^-1"))
    history._check_unit(ds, "V", ("m s-1", "m s^-1"))
    history._check_unit(ds, "PH", ("m2 s-2", "m^2 s^-2"))
    history._check_unit(ds, "PHB", ("m2 s-2", "m^2 s^-2"))
    for name in ("MAPFAC_UX", "MAPFAC_UY", "MAPFAC_VX", "MAPFAC_VY"):
        if str(getattr(ds[name], "units", "")).strip() != "":
            raise ValueError(f"{name} must use the pinned dimensionless WRF units metadata")
    ph, phb = _read(ds, "PH"), _read(ds, "PHB")
    if ph.shape != (nz + 1, ny, nxu - 1) or phb.shape != ph.shape:
        raise ValueError("PH/PHB do not match staggered native wind dimensions")
    interfaces = (ph + phb) / gravity
    layer_depth = np.diff(interfaces, axis=0)
    if not np.isfinite(interfaces).all() or np.any(layer_depth <= 0):
        raise ValueError("native geopotential interfaces must be finite and strictly increasing")
    mass_height = 0.5 * (interfaces[:-1] + interfaces[1:])
    dx, dy = float(ds.DX), float(ds.DY)
    if not np.isfinite([dx, dy]).all() or min(dx, dy) <= 0:
        raise ValueError("DX and DY must be finite and positive")

    map_u_x, map_u_y = _read(ds, "MAPFAC_UX"), _read(ds, "MAPFAC_UY")
    map_v_x, map_v_y = _read(ds, "MAPFAC_VX"), _read(ds, "MAPFAC_VY")
    expected = {"MAPFAC_UX": (ny, nxu), "MAPFAC_UY": (ny, nxu),
                "MAPFAC_VX": (ny + 1, nxu - 1), "MAPFAC_VY": (ny + 1, nxu - 1)}
    for name, value in (("MAPFAC_UX", map_u_x), ("MAPFAC_UY", map_u_y),
                        ("MAPFAC_VX", map_v_x), ("MAPFAC_VY", map_v_y)):
        if value.shape != expected[name] or not np.isfinite(value).all() or np.any(value <= 0):
            raise ValueError(f"{name} must have native shape and positive finite metrics")

    mass_dz = layer_depth
    u_height = np.empty(u_shape, dtype=np.float64)
    u_depth = np.empty(u_shape, dtype=np.float64)
    u_height[:, :, 1:-1] = 0.5 * (mass_height[:, :, :-1] + mass_height[:, :, 1:])
    u_depth[:, :, 1:-1] = 0.5 * (mass_dz[:, :, :-1] + mass_dz[:, :, 1:])
    u_height[:, :, 0], u_height[:, :, -1] = mass_height[:, :, 0], mass_height[:, :, -1]
    u_depth[:, :, 0], u_depth[:, :, -1] = mass_dz[:, :, 0], mass_dz[:, :, -1]
    v_height = np.empty(v_shape, dtype=np.float64)
    v_depth = np.empty(v_shape, dtype=np.float64)
    v_height[:, 1:-1, :] = 0.5 * (mass_height[:, :-1, :] + mass_height[:, 1:, :])
    v_depth[:, 1:-1, :] = 0.5 * (mass_dz[:, :-1, :] + mass_dz[:, 1:, :])
    v_height[:, 0, :], v_height[:, -1, :] = mass_height[:, 0, :], mass_height[:, -1, :]
    v_depth[:, 0, :], v_depth[:, -1, :] = mass_dz[:, 0, :], mass_dz[:, -1, :]

    u_area = dx * dy / (map_u_x * map_u_y)
    v_area = dx * dy / (map_v_x * map_v_y)
    u_volume = u_depth * u_area[None, :, :]
    v_volume = v_depth * v_area[None, :, :]
    if (not np.isfinite(u_volume).all() or not np.isfinite(v_volume).all()
            or np.any(u_volume <= 0) or np.any(v_volume <= 0)):
        raise ValueError("native U/V dual volumes must be finite and positive")
    return {"dx": dx, "dy": dy, "u_map_x": map_u_x, "u_map_y": map_u_y,
            "v_map_x": map_v_x, "v_map_y": map_v_y,
            "u_height": u_height, "v_height": v_height,
            "u_volume": u_volume, "v_volume": v_volume}


def _roughness_matrix(free_u: np.ndarray, free_v: np.ndarray, geometry: dict):
    """Build component-grid derivative rows, including fixed-zero neighbors."""
    nz = free_u.shape[0]
    u_ids = np.full(free_u.shape, -1, dtype=np.int64)
    v_ids = np.full(free_v.shape, -1, dtype=np.int64)
    per_layer = int(free_u[0].sum() + free_v[0].sum())
    if per_layer == 0 or not np.all(free_u == free_u[0]) or not np.all(free_v == free_v[0]):
        raise ValueError("free native U/V controls must be nonempty and fixed across levels")
    for k in range(nz):
        offset = k * per_layer
        u_ids[k][free_u[k]] = offset + np.arange(free_u[k].sum())
        v_ids[k][free_v[k]] = offset + int(free_u[k].sum()) + np.arange(free_v[k].sum())

    rows, cols, values, edge_groups = [], [], [], []
    row = 0
    component_data = (
        (free_u, u_ids, geometry["u_height"], geometry["u_volume"],
         geometry["u_map_x"], geometry["u_map_y"]),
        (free_v, v_ids, geometry["v_height"], geometry["v_volume"],
         geometry["v_map_x"], geometry["v_map_y"]),
    )
    for component_name, (mask, ids, heights, volumes, map_x, map_y) in zip(("U", "V"), component_data):
        nz0, ny, nx = mask.shape
        for k, j, i in np.argwhere(mask):
            here = int(ids[k, j, i])
            for axis, delta, map_factor in (
                (2, geometry["dx"], map_x),
                (1, geometry["dy"], map_y),
                (0, None, None),
            ):
                for sign in (-1, 1):
                    neighbor = [int(k), int(j), int(i)]
                    neighbor[axis] += sign
                    if not 0 <= neighbor[axis] < mask.shape[axis]:
                        if axis == 0:
                            continue
                        raise ValueError("free face touches a native horizontal boundary")
                    kk, jj, ii = neighbor
                    other_free = bool(mask[kk, jj, ii])
                    if other_free and sign < 0:
                        continue
                    if axis == 0:
                        distance = abs(float(heights[kk, jj, ii] - heights[k, j, i]))
                    elif axis == 2:
                        distance = delta / (0.5 * (map_factor[j, i] + map_factor[j, ii]))
                    else:
                        distance = delta / (0.5 * (map_factor[j, i] + map_factor[jj, i]))
                    if not np.isfinite(distance) or distance <= 0:
                        raise ValueError("native roughness edge has invalid physical distance")
                    dual_volume = 0.5 * (volumes[k, j, i] + volumes[kk, jj, ii])
                    weight = dual_volume / distance**2
                    coefficient = float(np.sqrt(weight * ROUGHNESS_FACTOR))
                    if not np.isfinite(coefficient) or coefficient <= 0:
                        raise ValueError("native roughness edge has invalid volume weight")
                    rows.append(row); cols.append(here); values.append(coefficient)
                    if other_free:
                        rows.append(row); cols.append(int(ids[kk, jj, ii])); values.append(-coefficient)
                    edge_groups.append((component_name, "vertical" if axis == 0 else "horizontal", int(k)))
                    row += 1
    return coo_matrix((values, (rows, cols)),
                      shape=(row, nz * per_layer)).tocsr(), u_ids, v_ids, edge_groups


def _roughness_report(matrix, vector, edge_groups) -> dict:
    edge_energy = np.square(matrix @ vector)
    result = {"total": float(edge_energy.sum())}
    for component in ("U", "V"):
        for direction in ("horizontal", "vertical"):
            selection = np.array([c == component and axis == direction
                                  for c, axis, _ in edge_groups], dtype=bool)
            result[f"{component}_{direction}"] = float(edge_energy[selection].sum())
    return result


def _upper_positive_product(left: float, right: float) -> float:
    """Return a binary64 upper bound for an exact nonnegative product."""
    if left < 0.0 or right < 0.0 or not np.isfinite(left) or not np.isfinite(right):
        raise ValueError("upper-product operands must be finite and nonnegative")
    product = float(np.float64(left) * np.float64(right))
    if not np.isfinite(product):
        raise ValueError("stored-flux arithmetic product overflowed binary64")
    # A positive exact product can round to zero or downward, including
    # into the subnormal range. One outward step (eta for zero) encloses it.
    return float(np.nextafter(np.float64(product), np.float64(np.inf)))


def _stored_flux_arithmetic_bound(matrix, continuous: np.ndarray,
                                  stored: np.ndarray) -> dict:
    """Bound observed A·stored from binary64 dot/subtraction rounding operands."""
    a = csr_matrix(matrix, dtype=np.float64)
    c = np.asarray(continuous, dtype=np.float64)
    s = np.asarray(stored, dtype=np.float64)
    if (c.shape != (a.shape[1],) or s.shape != c.shape or
            not np.isfinite(c).all() or not np.isfinite(s).all()):
        raise ValueError("stored-flux arithmetic inputs have invalid shape or values")
    residual = np.asarray(a @ s).ravel()
    continuous_residual = np.asarray(a @ c).ravel()
    error = np.subtract(s, c)
    absolute_a = abs(a).tocsr()
    absolute_error_dot = np.asarray(absolute_a @ np.abs(error)).ravel()
    if (not np.isfinite(residual).all() or not np.isfinite(continuous_residual).all()
            or not np.isfinite(absolute_error_dot).all()):
        raise ValueError("stored-flux dot product overflowed binary64")
    eps = np.finfo(np.float64).eps
    unit_roundoff = eps / 2.0
    smallest_subnormal = float(np.nextafter(0.0, 1.0))

    def outward(value: float) -> float:
        return float(np.nextafter(np.float64(value), np.float64(np.inf)))

    def upper_positive_sum(products: list[float]) -> float:
        total = math.fsum(products)
        if not np.isfinite(total):
            raise ValueError("stored-flux arithmetic sum overflowed binary64")
        return outward(total)

    rows = []
    limits = np.zeros(a.shape[0], dtype=np.float64)
    for row_index in range(a.shape[0]):
        start, stop = a.indptr[row_index], a.indptr[row_index + 1]
        columns = a.indices[start:stop]
        coefficients = a.data[start:stop]
        n = len(columns)
        if n == 0 or n > 4:
            raise ValueError("native dry-flux row must have one to four face terms")
        gamma = outward((2.0 * n * unit_roundoff) /
                        (1.0 - 2.0 * n * unit_roundoff))
        abs_coefficients = np.abs(coefficients)
        c_values, s_values, e_values = c[columns], s[columns], error[columns]

        def dot_error(values: np.ndarray) -> tuple[float, float]:
            magnitude = upper_positive_sum([
                _upper_positive_product(float(abs_coefficients[q]), abs(float(values[q])))
                for q in range(n)
            ])
            bound = upper_positive_sum([
                _upper_positive_product(gamma, magnitude), 2.0 * n * smallest_subnormal
            ])
            return magnitude, bound

        _, delta_dot_c = dot_error(c_values)
        _, delta_dot_s = dot_error(s_values)
        absolute_error_dot_upper, delta_dot_abs_e = dot_error(e_values)
        subtraction_errors = []
        for left, right in zip(s_values, c_values):
            operand_sum = upper_positive_sum([abs(float(left)), abs(float(right))])
            product_bound = _upper_positive_product(unit_roundoff, operand_sum)
            subtraction_errors.append(upper_positive_sum(
                [product_bound, smallest_subnormal]))
        abs_a_subtraction = upper_positive_sum([
            _upper_positive_product(float(abs_coefficients[q]), subtraction_errors[q])
            for q in range(n)
        ])
        delta_a_subtraction = upper_positive_sum([
            _upper_positive_product(outward(1.0 + gamma), abs_a_subtraction),
            2.0 * n * smallest_subnormal,
        ])
        terms = {
            "observed_continuous_dot": abs(float(continuous_residual[row_index])),
            "observed_abs_error_dot": float(absolute_error_dot[row_index]),
            "absolute_error_dot_upper": absolute_error_dot_upper,
            "delta_dot_continuous": delta_dot_c,
            "delta_dot_stored": delta_dot_s,
            "delta_dot_abs_error": delta_dot_abs_e,
            "delta_subtraction_to_flux": delta_a_subtraction,
        }
        if not all(np.isfinite(value) for value in terms.values()):
            raise ValueError("stored-flux arithmetic error bound overflowed binary64")
        limit = upper_positive_sum(list(terms.values()))
        if not np.isfinite(limit):
            raise ValueError("stored-flux arithmetic error bound is not finite")
        limits[row_index] = limit
        rows.append({"row": row_index, "nnz": n, "gamma_2n": gamma,
                     "columns": columns.tolist(), "coefficients": coefficients.tolist(),
                     "continuous_operands": c_values.tolist(),
                     "stored_operands": s_values.tolist(), "subtraction_operands": e_values.tolist(),
                     "continuous_bits": [int(np.float64(x).view(np.uint64)) for x in c_values],
                     "stored_bits": [int(np.float64(x).view(np.uint64)) for x in s_values],
                     "observed_continuous_dot": float(continuous_residual[row_index]),
                     "observed_stored_dot": float(residual[row_index]),
                     "continuous_dot_bits": int(np.float64(continuous_residual[row_index]).view(np.uint64)),
                     "stored_dot_bits": int(np.float64(residual[row_index]).view(np.uint64)),
                     "subtraction_error_bounds": subtraction_errors,
                     "terms": terms, "limit": limit})
    return {"observed_residual": residual, "continuous_residual": continuous_residual,
            "limits": limits, "rows": rows,
            "unit_roundoff": unit_roundoff,
            "smallest_subnormal": smallest_subnormal}


def _storage_margin(hydro_free, projected, delta: float) -> float:
    """Euclidean half-ULP envelope for the declared H+P±Δ REAL32 box."""
    if hydro_free.shape != projected.shape:
        raise ValueError("storage-margin wind vectors differ from projection size")
    target = hydro_free.astype(np.float64) + projected
    endpoints = np.stack((target - delta, target + delta)).astype(np.float32)
    if not np.isfinite(endpoints).all():
        raise ValueError("REAL32 storage target box overflows")
    above = np.nextafter(endpoints, np.float32(np.inf), dtype=np.float32)
    below = np.nextafter(endpoints, np.float32(-np.inf), dtype=np.float32)
    ulp = np.maximum(np.abs(above.astype(np.float64) - endpoints),
                     np.abs(endpoints.astype(np.float64) - below.astype(np.float64)))
    if not np.isfinite(ulp).all():
        raise ValueError("REAL32 storage ULP bound is not finite")
    half_ulp = 0.5 * np.max(ulp, axis=0)
    return float(np.linalg.norm(half_ulp))


def _artifact(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256(path)}


def _verify_pr99_receipt(receipt_path: Path, hydro: Path, coupled: Path,
                         original_p: Path, boundary: Path) -> dict:
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get("schema") != "pr99_native_uv_projection_proposal_v1" or
            receipt.get("status") != "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_TENDENCY_VALIDATION" or
            receipt.get("role") != "COUPLED"):
        raise ValueError("expected original PR99 COUPLED projection receipt")
    expected = {"reference": hydro, "parent": coupled, "candidate": original_p,
                "boundary": boundary}
    for name, path in expected.items():
        row = receipt.get(name, {})
        if (Path(row.get("path", "")).resolve() != path.resolve() or
                not path.is_file() or sha256(path) != row.get("sha256")):
            raise ValueError(f"PR99 {name} artifact does not bind the declared input")
    composition_row = receipt.get("composition", {})
    original_composition = Path(composition_row.get("path", "")).resolve()
    expected_composition_sha = composition_row.get("sha256")
    if (not original_composition.is_file() or
            sha256(original_composition) != expected_composition_sha or
            receipt.get("composition_sha256") != expected_composition_sha):
        raise ValueError("original PR99 composition path/hash does not verify")
    if not COMPOSITION.is_file() or sha256(COMPOSITION) != expected_composition_sha:
        raise ValueError("current PR102 composition mirror is not byte-identical to PR99 source")
    for name in ("generator",):
        row = receipt.get(name, {})
        path = Path(row.get("path", ""))
        if not path.is_file() or sha256(path) != row.get("sha256"):
            raise ValueError(f"PR99 {name} artifact changed or is unavailable")
    return {**receipt, "_composition_source_binding": {
        "path": str(original_composition), "sha256": expected_composition_sha}}


def propose(hydro: Path, coupled: Path, original_p: Path, pr99_receipt: Path,
            boundary: Path, constants_receipt: Path, output: Path) -> dict:
    """Build a candidate only when explicitly called; caller must separately authorize it."""
    sidecar = output.with_suffix(".proposal.json")
    if output.exists() or sidecar.exists():
        raise FileExistsError(output)
    if not POLICY_SHA256 or not POLICY.is_file() or sha256(POLICY) != POLICY_SHA256:
        raise ValueError("frozen PR102 policy artifact is absent or has the wrong hash")
    policy = json.loads(POLICY.read_text())
    if policy.get("schema") != "pr102_native_wind_structure_policy_v1":
        raise ValueError("unsupported frozen PR102 policy schema")
    pr99 = _verify_pr99_receipt(pr99_receipt, hydro, coupled, original_p, boundary)
    gravity, gravity_identity = history._constants(constants_receipt)
    composition = json.loads(COMPOSITION.read_text())
    composed = composition["composed_qc_vertical_influence"]

    pinned_inputs = [hydro, coupled, original_p, boundary, pr99_receipt,
                     constants_receipt, POLICY, COMPOSITION,
                     Path(pr99["_composition_source_binding"]["path"]),
                     Path(__file__).resolve(), Path(projection.__file__),
                     Path(cloud.__file__),
                     Path(history.__file__), Path(solve_smooth_increment.__code__.co_filename)]
    input_hashes = {str(path.resolve()): sha256(path) for path in pinned_inputs}

    with netCDF4.Dataset(hydro) as h, netCDF4.Dataset(coupled) as c, netCDF4.Dataset(original_p) as p:
        for ds in (h, c, p):
            ds.set_auto_mask(False)
        verify_only_wind_changed(original_p, hydro)
        verify_only_wind_changed(coupled, original_p)
        for name in ("U", "V"):
            if h[name].dtype != np.dtype("float32"):
                raise ValueError("native wind candidates require REAL32 U/V")
        hu, hv = (_read(h, name) for name in ("U", "V"))
        cu, cv = (_read(c, name) for name in ("U", "V"))
        pu, pv = (_read(p, name) for name in ("U", "V"))
        nz, ny, nx = hu.shape[0], hu.shape[1], hv.shape[2]
        if (cu.shape != hu.shape or pv.shape != hv.shape or cv.shape != hv.shape or
                pu.shape != hu.shape):
            raise ValueError("source U/V native shapes differ")
        if nz != EXPECTED_NATIVE_LEVELS:
            raise ValueError("native level count differs from the frozen 39-level support")
        support = cloud.make_masks(composed, (nz, ny - 2, nx - 2))
        native_support = support["original_613_native_support"]
        columns = np.zeros((ny, nx), dtype=bool)
        columns[1:-1, 1:-1] = support["fixed_5_cell_chebyshev_buffer"].any(axis=0)
        u2, v2 = projection.control_faces(columns)
        if (native_support.sum() != EXPECTED_SUPPORT_LEVELS or
                native_support.any(axis=0).sum() != EXPECTED_SUPPORT_COLUMNS or
                columns.sum() != EXPECTED_BUFFER_COLUMNS or
                u2.sum() + v2.sum() != EXPECTED_FREE_FACES_PER_LAYER or
                pr99.get("fixed_columns") != int(columns.sum()) or
                pr99.get("free_faces_per_layer") != int(u2.sum() + v2.sum()) or
                len(pr99.get("layers", [])) != nz):
            raise ValueError("derived support differs from the receipt-bound PR99 control")
        free_u, free_v = np.broadcast_to(u2, hu.shape).copy(), np.broadcast_to(v2, hv.shape).copy()
        if (pu[:, ~u2].tobytes() != hu[:, ~u2].tobytes() or
                pv[:, ~v2].tobytes() != hv[:, ~v2].tobytes()):
            raise ValueError("original_p contains stored wind changes outside the PR99 free faces")
        raw_u, raw_v = cu - hu, cv - hv
        if np.any(raw_u[:, ~u2]) or np.any(raw_v[:, ~v2]):
            raise ValueError("raw COUPLED−HYDRO wind differs outside free faces")
        geometry = _geometry(h, free_u, free_v, gravity)
        layer_matrices = []
        raw_parts, projected_parts, hydro_parts = [], [], []
        projection_reports = []
        for k in range(nz):
            matrix = projection.divergence_matrix(columns, *projection.face_coefficients(h, k))
            increment = np.r_[raw_u[k][u2], raw_v[k][v2]]
            projected, report = projection.project_increment(matrix, increment)
            base = np.r_[hu[k][u2], hv[k][v2]]
            reconstructed_p = (base + projected).astype(np.float32)
            expected_p = np.r_[pu[k][u2], pv[k][v2]].astype(np.float32)
            if reconstructed_p.tobytes() != expected_p.tobytes():
                raise ValueError("recomputed PR99 stored increment does not match original_p bytes")
            layer_matrices.append(matrix)
            raw_parts.append(increment)
            projected_parts.append(projected)
            hydro_parts.append(base)
            projection_reports.append(report)
        raw = np.concatenate(raw_parts)
        projected = np.concatenate(projected_parts)
        hydro_free = np.concatenate(hydro_parts)
        delta = float(np.linalg.norm(raw - projected))
        if not delta < np.linalg.norm(projected):
            raise ValueError("PR99 displacement budget does not exclude zero")
        margin = _storage_margin(hydro_free, projected, delta)
        radius = delta - margin
        if not np.isfinite(radius) or radius <= 0:
            raise ValueError("REAL32 storage margin consumes the PR99 displacement budget")
        A = block_diag(layer_matrices, format="csr")
        G, u_ids, v_ids, edge_groups = _roughness_matrix(free_u, free_v, geometry)
        solution = solve_smooth_increment(A, G, raw, projected, radius=radius)
        candidate_increment = solution.increment
        if candidate_increment.shape != raw.shape or not np.isfinite(candidate_increment).all():
            raise ValueError("solver returned an invalid candidate shape")
        if not np.isfinite(solution.displacement) or solution.displacement > radius:
            raise ValueError("continuous candidate exceeds the strict global PR99 distance budget")
        continuous_layer_residuals = []
        stride = int(u2.sum() + v2.sum())
        for k, matrix in enumerate(layer_matrices):
            residual = float(np.linalg.norm(matrix @
                            candidate_increment[k * stride:(k + 1) * stride]))
            limit = float(projection_reports[k]["continuous_solver_limit"])
            if not np.isfinite(residual) or residual > limit:
                raise ValueError("continuous candidate exceeds the original PR99 layer residual gate")
            continuous_layer_residuals.append({"l2": residual, "pr99_solver_limit": limit})
        candidate_u, candidate_v = hu.astype(np.float32).copy(), hv.astype(np.float32).copy()
        for k in range(nz):
            base = np.r_[hu[k][u2], hv[k][v2]]
            section = candidate_increment[k * len(base):(k + 1) * len(base)]
            stored = (base + section).astype(np.float32).astype(np.float64)
            candidate_u[k][u2] = stored[:int(u2.sum())]
            candidate_v[k][v2] = stored[int(u2.sum()):]
        stored_increment = np.concatenate([
            np.r_[(candidate_u[k] - hu[k])[u2], (candidate_v[k] - hv[k])[v2]]
            for k in range(nz)
        ])
        stored_distance = float(np.linalg.norm(stored_increment - projected))
        if not stored_distance <= delta:
            raise ValueError("stored REAL32 candidate exceeds the global PR99 distance budget")
        if np.linalg.norm(stored_increment) == 0:
            raise ValueError("stored candidate increment collapsed to zero")
        stride = int(u2.sum() + v2.sum())
        stored_A_residuals, storage_A_bounds = [], []
        storage_roundoff_terms = []
        for k, matrix in enumerate(layer_matrices):
            section = stored_increment[k * stride:(k + 1) * stride]
            continuous_section = candidate_increment[k * stride:(k + 1) * stride]
            arithmetic = _stored_flux_arithmetic_bound(matrix, continuous_section, section)
            residual = arithmetic["observed_residual"]
            bound = arithmetic["limits"]
            failed = np.flatnonzero(np.abs(residual) > bound)
            if failed.size:
                detail = arithmetic["rows"][int(failed[0])]
                raise ValueError("stored dry-flux arithmetic bound failed: " +
                                 json.dumps(detail, sort_keys=True, allow_nan=False))
            stored_A_residuals.append({"l2": float(np.linalg.norm(residual)),
                                       "linf": float(np.max(np.abs(residual))),
                                       "cellwise": residual.tolist()})
            storage_A_bounds.append({"l2": float(np.linalg.norm(bound)),
                                     "linf": float(np.max(bound)),
                                     "cellwise": bound.tolist()})
            rows = arithmetic["rows"]
            storage_roundoff_terms.append({
                "unit_roundoff": arithmetic["unit_roundoff"],
                "smallest_subnormal": arithmetic["smallest_subnormal"],
                "real32_quantization_contribution": [
                    row["terms"]["observed_abs_error_dot"] for row in rows],
                "fp64_rounding_terms": {
                    name: [row["terms"][name] for row in rows]
                    for name in ("delta_dot_continuous", "delta_dot_stored",
                                 "delta_dot_abs_error", "delta_subtraction_to_flux")},
                "total_arithmetic_limit": bound.tolist(),
            })

    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original_p, output)
    try:
        with netCDF4.Dataset(output, "r+") as ds:
            ds["U"][0], ds["V"][0] = candidate_u, candidate_v
        verify_only_wind_changed(output, original_p)
        with netCDF4.Dataset(output) as ds:
            ds.set_auto_mask(False)
            stored_u, stored_v = _read(ds, "U"), _read(ds, "V")
            if (stored_u.astype(np.float32).tobytes() != candidate_u.tobytes() or
                    stored_v.astype(np.float32).tobytes() != candidate_v.tobytes()):
                raise ValueError("candidate U/V readback differs from the intended REAL32 arrays")
            actual_stored = np.concatenate([
                np.r_[(stored_u[k] - hu[k])[u2], (stored_v[k] - hv[k])[v2]]
                for k in range(nz)
            ])
            actual_distance = float(np.linalg.norm(actual_stored - projected))
            if not actual_distance <= delta:
                raise ValueError("readback REAL32 candidate exceeds the original PR99 distance budget")
    except Exception:
        output.unlink(missing_ok=True)
        raise
    for path_text, digest in input_hashes.items():
        if sha256(Path(path_text)) != digest:
            output.unlink(missing_ok=True)
            raise ValueError(f"source artifact changed during candidate construction: {path_text}")
    roughness_before = _roughness_report(G, projected, edge_groups)
    roughness_raw = _roughness_report(G, raw, edge_groups)
    roughness_after = _roughness_report(G, candidate_increment, edge_groups)
    roughness_stored = _roughness_report(G, actual_stored, edge_groups)
    return {"schema": "pr102_wind_structure_proposal_v1",
            "status": "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_SOURCE_CAPTURE",
            "role": "COUPLED", "parent_sha256": sha256(original_p),
            "candidate": _artifact(output), "original_p": _artifact(original_p),
            "reference_hydro": _artifact(hydro), "reference_coupled": _artifact(coupled),
            "boundary": _artifact(boundary), "generator": _artifact(Path(__file__).resolve()),
            "policy": _artifact(POLICY), "composition": _artifact(COMPOSITION),
            "pr99_projection_receipt": _artifact(pr99_receipt),
            "pr99_composition_source": pr99["_composition_source_binding"],
            "current_composition_mirror": _artifact(COMPOSITION),
            "solver_core": _artifact(Path(solve_smooth_increment.__code__.co_filename)),
            "projection_helper": _artifact(Path(projection.__file__)),
            "runtime_dependencies": [_artifact(Path(cloud.__file__)),
                                      _artifact(Path(history.__file__))],
            "source_pin_hashes": input_hashes,
            "python_environment": {"executable": sys.executable,
                                   "version": sys.version,
                                   "platform": platform.platform(),
                                   "numpy": np.__version__,
                                   "scipy": scipy.__version__,
                                   "netCDF4": netCDF4.__version__},
            "change_contract": {"changed_variables": ["U", "V"],
                                "non_target_variables_identical": True},
            "composition_sha256": sha256(COMPOSITION), "gravity": gravity_identity,
            "control": {"horizontal_columns": int(columns.sum()),
                        "free_u_faces_per_layer": int(u2.sum()),
                        "free_v_faces_per_layer": int(v2.sum()), "layers": int(nz)},
            "policy_metrics": {"schema": policy["schema"], "trust_radius": radius,
                       "pr99_adjustment_delta": delta, "storage_margin": margin,
                       "continuous_distance_to_projection": solution.displacement,
                       "continuous_distance_to_projection_limit": radius,
                       "continuous_distance_gate_slack": radius - solution.displacement,
                       "stored_distance_to_projection": actual_distance,
                       "continuous_layer_constraint_residuals": continuous_layer_residuals,
                       "continuous_constraint_residual": solution.equality_residual,
                       "normalized_kkt_residual": solution.stationarity_residual_scaled,
                       "roughness_before": roughness_before,
                       "roughness_raw": roughness_raw,
                       "roughness_continuous": roughness_after,
                       "roughness_stored": roughness_stored,
                       "roughness_squared": solution.roughness_squared,
                       "roughness_factor": ROUGHNESS_FACTOR,
                       "roughness_units": "m^3 s^-2",
                       "stored_layer_divergence_l2": stored_A_residuals,
                       "stored_layer_storage_divergence_bound_l2": storage_A_bounds,
                       "stored_layer_roundoff_terms": storage_roundoff_terms,
                       "projection_layers": projection_reports,
                       "native_geometry": {"dx_m": geometry["dx"], "dy_m": geometry["dy"],
                                           "gravity_m_s2": gravity}},
            "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hydro", type=Path, required=True)
    parser.add_argument("--coupled", type=Path, required=True)
    parser.add_argument("--original-p", type=Path, required=True)
    parser.add_argument("--pr99-receipt", type=Path, required=True)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--constants-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = propose(args.hydro, args.coupled, args.original_p, args.pr99_receipt,
                     args.boundary, args.constants_receipt, args.output)
    try:
        with args.output.with_suffix(".proposal.json").open("x") as stream:
            stream.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    except Exception:
        args.output.unlink(missing_ok=True)
        raise
    print(json.dumps({"status": report["status"], "candidate_sha256": report["candidate"]["sha256"],
                      "delta": report["policy_metrics"]["pr99_adjustment_delta"],
                      "stored_distance": report["policy_metrics"]["stored_distance_to_projection"]}, indent=2))


if __name__ == "__main__":
    main()
