#!/usr/bin/env python3
"""Summarize isolated native QNCCN RK-stage captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

from native_kdm6_trace import read_dump


STAGE_MAGIC = b"CCNSTG1 "
UPDATE_MAGIC = b"CCNUPD1 "
PD_BUDGET_MAGIC = b"CCNPDB1 "


class TraceError(ValueError):
    """Raised when a QNCCN stage capture is incomplete or inconsistent."""


def _stats(values: np.ndarray) -> dict:
    finite = np.isfinite(values)
    finite_values = values[finite]
    return {
        "size": int(values.size),
        "finite": int(finite.sum()),
        "nonfinite": int((~finite).sum()),
        "positive": int((values > 0).sum()),
        "zero": int((values == 0).sum()),
        "negative": int((values < 0).sum()),
        "min": float(finite_values.min()) if finite_values.size else None,
        "max": float(finite_values.max()) if finite_values.size else None,
    }


def _read_f32(view: memoryview, offset: int, count: int, label: str) -> tuple[np.ndarray, int]:
    end = offset + count * 4
    if end > len(view):
        raise TraceError(f"truncated {label}")
    return np.frombuffer(view[offset:end], dtype=np.dtype(">f4")), end


def _active_slices(bounds: dict, ims: int, jms: int, kms: int,
                   its: int, ite: int, jts: int, jte: int,
                   kts: int, kte: int) -> tuple[slice, slice, slice]:
    i0, i1 = bounds["its"], bounds["ite"] + 1
    j0, j1 = bounds["jts"], bounds["jte"] + 1
    k0, k1 = bounds["kts"], bounds["kte"] + 1
    if (i0 < its or i1 - 1 > ite or j0 < jts or j1 - 1 > jte or
            k0 < kts or k1 - 1 > kte):
        raise TraceError("KDM6 active bounds are outside the capture bounds")
    return (slice(j0 - jms, j1 - jms),
            slice(k0 - kms, k1 - kms),
            slice(i0 - its, i1 - its))


def _read_stage(path: Path, call_bounds: dict, expected_stage: int,
                expected_rk: int) -> dict:
    raw = path.read_bytes()
    if len(raw) < 80:
        raise TraceError(f"truncated stage header in {path}")
    view = memoryview(raw)
    if view[:8].tobytes() != STAGE_MAGIC:
        raise TraceError(f"wrong stage magic in {path}")
    stage, rk_step, ids, ide, jds, jde, kds, kde = struct.unpack_from(">8i", view, 8)
    ims, ime, jms, jme, kms, kme, its, ite, kts, kte = struct.unpack_from(">10i", view, 40)
    if (stage, rk_step) != (expected_stage, expected_rk):
        raise TraceError(f"stage header mismatch for {path.name}")
    for start, end, label in (("ids", "ide", "i"), ("jds", "jde", "j"), ("kds", "kde", "k"),
                              ("ims", "ime", "i"), ("jms", "jme", "j"), ("kms", "kme", "k")):
        if locals()[start] > locals()[end]:
            raise TraceError(f"empty or inverted {label} capture bounds in {path}")
    expected_domain = (call_bounds["ids"], call_bounds["ide"], call_bounds["jds"],
                       call_bounds["jde"], call_bounds["kds"], call_bounds["kde"])
    if (ids, ide, jds, jde, kds, kde) != expected_domain:
        raise TraceError(f"domain bounds mismatch in {path}")
    expected_memory = (call_bounds["ims"], call_bounds["ime"], call_bounds["jms"],
                       call_bounds["jme"], call_bounds["kms"], call_bounds["kme"])
    if (ims, ime, jms, jme, kms, kme) != expected_memory:
        raise TraceError(f"memory bounds mismatch in {path}")
    nx, ny, nz = ite - its + 1, jme - jms + 1, kte - kts + 1
    if min(nx, ny, nz) <= 0 or nx * ny * nz > (1 << 29):
        raise TraceError(f"invalid capture shape in {path}")
    if its < ims or ite > ime or kts < kms or kte > kme:
        raise TraceError(f"stage capture bounds fall outside memory in {path}")
    expected_bytes = 80 + nx * ny * nz * 8
    if len(raw) != expected_bytes:
        raise TraceError(f"stage payload size mismatch in {path}: expected {expected_bytes}, got {len(raw)}")
    if (its > call_bounds["its"] or ite < call_bounds["ite"] or
            kts > call_bounds["kts"] or kte < call_bounds["kte"]):
        raise TraceError(f"active bounds fall outside stage capture in {path}")
    active = _active_slices(call_bounds, its, jms, kts, its, ite,
                            jms, jme, kts, kte)
    count = nx * ny * nz
    state, offset = _read_f32(view, 80, count, "state")
    tendency, offset = _read_f32(view, offset, count, "tendency")
    state = state.reshape(ny, nz, nx)[active]
    tendency = tendency.reshape(ny, nz, nx)[active]
    return {
        "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw), "stage": stage, "rk_step": rk_step,
        "active_shape_xyz": [state.shape[2], state.shape[0], state.shape[1]],
        "state": state, "tendency": tendency,
    }


def _read_update(path: Path, call_bounds: dict) -> dict:
    raw = path.read_bytes()
    view = memoryview(raw)
    if len(raw) < 60:
        raise TraceError(f"truncated update header in {path}")
    if view[:8].tobytes() != UPDATE_MAGIC:
        raise TraceError(f"wrong update magic in {path}")
    ims, ime, jms, jme, kms, kme, its, ite, jts, jte, kts, kte = struct.unpack_from(">12i", view, 8)
    dt = struct.unpack_from(">f", view, 56)[0]
    nx, ny, nz = ite - its + 1, jte - jts + 1, kte - kts + 1
    if min(nx, ny, nz) <= 0 or nx * ny * nz > (1 << 29):
        raise TraceError("invalid update capture shape")
    n3, n2 = nx * ny * nz, nx * ny
    expected_bytes = 60 + (4 * n3 + 4 * n2 + 2 * nz) * 4
    if len(raw) != expected_bytes:
        raise TraceError(f"update payload size mismatch: expected {expected_bytes}, got {len(raw)}")
    if not np.isfinite(dt) or dt <= 0:
        raise TraceError("update dt must be finite and positive")
    expected_memory = (call_bounds["ims"], call_bounds["ime"], call_bounds["jms"],
                       call_bounds["jme"], call_bounds["kms"], call_bounds["kme"])
    if (ims, ime, jms, jme, kms, kme) != expected_memory:
        raise TraceError("memory bounds mismatch in update capture")
    if its < ims or ite > ime or jts < jms or jte > jme or kts < kms or kte > kme:
        raise TraceError("update capture bounds fall outside memory")
    if (its > call_bounds["its"] or ite < call_bounds["ite"] or
            jts > call_bounds["jts"] or jte < call_bounds["jte"] or
            kts > call_bounds["kts"] or kte < call_bounds["kte"]):
        raise TraceError("active bounds fall outside update capture")
    active = _active_slices(call_bounds, its, jts, kts, its, ite,
                            jts, jte, kts, kte)
    offset = 60
    arrays = []
    for count, label in ((n3, "scalar_old"), (n3, "scalar"),
                         (n3, "scalar_tend"), (n3, "advect_tend"),
                         (n2, "msfty"), (n2, "mu_old"),
                         (n2, "mu_new"), (n2, "mu_base"),
                         (nz, "c1"), (nz, "c2")):
        values, offset = _read_f32(view, offset, count, label)
        arrays.append(values)
    if offset != len(view):
        raise TraceError(f"unexpected trailing bytes in {path}")

    scalar_old, scalar, scalar_tend, advect_tend, msfty, mu_old, mu_new, mu_base, c1, c2 = arrays
    scalar_shape = (ny, nz, nx)
    plane_shape = (ny, nx)
    scalar_old = scalar_old.reshape(scalar_shape)[active]
    scalar = scalar.reshape(scalar_shape)[active]
    scalar_tend = scalar_tend.reshape(scalar_shape)[active]
    advect_tend = advect_tend.reshape(scalar_shape)[active]
    plane_active = (active[0], active[2])
    msfty = msfty.reshape(plane_shape)[plane_active]
    mu_old = mu_old.reshape(plane_shape)[plane_active]
    mu_new = mu_new.reshape(plane_shape)[plane_active]
    mu_base = mu_base.reshape(plane_shape)[plane_active]
    vertical_active = slice(call_bounds["kts"] - kts, call_bounds["kte"] - kts + 1)
    c1, c2 = c1[vertical_active], c2[vertical_active]

    tendency32 = (advect_tend * msfty[:, None, :]).astype(np.float32) + scalar_tend
    old_mass32 = (mu_old + mu_base).astype(np.float32)
    new_mass32 = (mu_new + mu_base).astype(np.float32)
    old_factor32 = (c1[None, :, None] * old_mass32[:, None, :]).astype(np.float32) + c2[None, :, None]
    new_factor32 = (c1[None, :, None] * new_mass32[:, None, :]).astype(np.float32) + c2[None, :, None]
    numerator32 = (old_factor32 * scalar_old).astype(np.float32) + (np.float32(dt) * tendency32).astype(np.float32)
    if (not np.isfinite(old_factor32).all() or not np.isfinite(new_factor32).all() or
            np.any(old_factor32 <= 0) or np.any(new_factor32 <= 0)):
        raise TraceError("update mass factors must be finite and positive")
    predicted32 = (numerator32 / new_factor32).astype(np.float32)

    old_mass64 = mu_old.astype(np.float64) + mu_base.astype(np.float64)
    new_mass64 = mu_new.astype(np.float64) + mu_base.astype(np.float64)
    tendency64 = advect_tend.astype(np.float64) * msfty.astype(np.float64)[:, None, :] + scalar_tend.astype(np.float64)
    predicted64 = (
        (c1.astype(np.float64)[None, :, None] * old_mass64[:, None, :] + c2.astype(np.float64)[None, :, None])
        * scalar_old.astype(np.float64) + float(dt) * tendency64
    ) / (
        c1.astype(np.float64)[None, :, None] * new_mass64[:, None, :] + c2.astype(np.float64)[None, :, None]
    )
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "dt_s": float(dt),
        "scalar_old": scalar_old,
        "scalar": scalar,
        "scalar_tend": scalar_tend,
        "advect_tend": advect_tend,
        "predicted_float32": predicted32,
        "predicted_float64_from_saved_inputs": predicted64,
    }



def _read_pd_budget(path: Path, call_bounds: dict, final_nn: np.ndarray) -> dict:
    raw = path.read_bytes()
    if len(raw) < 68:
        raise TraceError(f"truncated PD budget header in {path}")
    view = memoryview(raw)
    if view[:8].tobytes() != PD_BUDGET_MAGIC:
        raise TraceError(f"wrong PD budget magic in {path}")
    ims, ime, jms, jme, kms, kme, its, ite, jts, jte, kts, kte = struct.unpack_from(">12i", view, 8)
    dt, rdx, rdy = struct.unpack_from(">3f", view, 56)
    nx, ny, nz = ite - its + 1, jte - jts + 1, kte - kts + 1
    if min(nx, ny, nz) <= 0 or nx * ny * nz > (1 << 29):
        raise TraceError(f"invalid PD budget capture shape in {path}")
    if not all(np.isfinite(value) and value > 0 for value in (dt, rdx, rdy)):
        raise TraceError(f"PD budget parameters must be finite and positive in {path}")
    expected_memory = (call_bounds["ims"], call_bounds["ime"], call_bounds["jms"],
                       call_bounds["jme"], call_bounds["kms"], call_bounds["kme"])
    if (ims, ime, jms, jme, kms, kme) != expected_memory:
        raise TraceError(f"PD budget memory bounds mismatch in {path}")
    if (its < ims or ite > ime or jts < jms or jte > jme or kts < kms or kte > kme):
        raise TraceError(f"PD budget capture bounds fall outside memory in {path}")
    if (its > call_bounds["its"] or ite < call_bounds["ite"] or
            jts > call_bounds["jts"] or jte < call_bounds["jte"] or
            kts > call_bounds["kts"] or kte < call_bounds["kte"]):
        raise TraceError(f"active bounds fall outside PD budget capture in {path}")
    n3, n2 = nx * ny * nz, nx * ny
    nxface, nyface, nzface = (nx + 2) * ny * nz, nx * (ny + 2) * nz, nx * ny * (nz + 1)
    expected_bytes = 68 + (5 * n3 + 2 * nxface + 2 * nyface + 2 * nzface + 2 * n2 + nz) * 4
    if len(raw) != expected_bytes:
        raise TraceError(f"PD budget payload size mismatch in {path}: expected {expected_bytes}, got {len(raw)}")
    active = _active_slices(call_bounds, its, jts, kts, its, ite, jts, jte, kts, kte)
    offset = 68
    arrays = []
    for count, label in ((n3, "field_old"), (n3, "tendency"), (n3, "ph_low"),
                         (n3, "flux_out"), (n3, "scale"),
                         (nxface, "fqx"), (nyface, "fqy"), (nzface, "fqz"),
                         (nxface, "fqxl"), (nyface, "fqyl"), (nzface, "fqzl"),
                         (n2, "msftx"), (n2, "msfty"), (nz, "rdzw")):
        values, offset = _read_f32(view, offset, count, label)
        arrays.append(values)
    field_old, tendency, ph_low, flux_out, scale, fqx, fqy, fqz, fqxl, fqyl, fqzl, msftx, msfty, rdzw = arrays
    shape = (ny, nz, nx)
    active_field = lambda array: array.reshape(shape)[active]
    ph_low = active_field(ph_low)
    flux_out = active_field(flux_out)
    scale = active_field(scale)
    plane_active = (active[0], active[2])
    msftx = msftx.reshape(ny, nx)[plane_active]
    msfty = msfty.reshape(ny, nx)[plane_active]
    vertical = slice(call_bounds["kts"] - kts, call_bounds["kte"] - kts + 1)
    rdzw = rdzw[vertical]
    fqx = fqx.reshape(ny, nz, nx + 2)
    fqy = fqy.reshape(ny + 2, nz, nx)
    fqz = fqz.reshape(ny, nz + 1, nx)
    negative = final_nn < 0
    residuals = []
    for y, z, x in np.argwhere(negative):
        i = call_bounds["its"] + int(x)
        j = call_bounds["jts"] + int(y)
        k = call_bounds["kts"] + int(z)
        ix, jy, kz = i - its, j - jts, k - kts
        outx = np.float32(np.float32(max(0.0, float(fqx[jy, kz, ix + 2]))) -
                          np.float32(min(0.0, float(fqx[jy, kz, ix + 1]))))
        outy = np.float32(np.float32(max(0.0, float(fqy[jy + 2, kz, ix]))) -
                          np.float32(min(0.0, float(fqy[jy + 1, kz, ix]))))
        outz = np.float32(np.float32(min(0.0, float(fqz[jy, kz + 1, ix]))) -
                          np.float32(max(0.0, float(fqz[jy, kz, ix]))))
        horizontal = np.float32(np.float32(rdx) * outx + np.float32(rdy) * outy)
        horizontal = np.float32(np.float32(msftx[y, x] * msfty[y, x]) * horizontal)
        vertical_term = np.float32(np.float32(msfty[y, x] * rdzw[z]) * outz)
        outgoing = np.float32(np.float32(dt) * np.float32(horizontal + vertical_term))
        residuals.append(float(np.float32(ph_low[y, z, x] - outgoing)))
    residuals = np.asarray(residuals, dtype=np.float64)
    return {
        "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
        "dt_s": float(dt), "rdx": float(rdx), "rdy": float(rdy),
        "ph_low": _stats(ph_low), "flux_out": _stats(flux_out), "scale": _stats(scale),
        "negative_ph_low_cells": int((ph_low < 0).sum()),
        "active_limiter_cells": int((scale < 1).sum()),
        "negative_call_cells": int(negative.sum()),
        "negative_call_cells_with_positive_ph_low": int(((ph_low > 0) & negative).sum()),
        "negative_call_cells_with_active_limiter": int(((scale < 1) & negative).sum()),
        "negative_call_cells_postscale_budget_overshoot": int((residuals < 0).sum()),
        "negative_call_cells_postscale_budget_zero": int((residuals == 0).sum()),
        "negative_call_cells_postscale_budget_positive": int((residuals > 0).sum()),
        "postscale_budget_residual_min": float(residuals.min()) if residuals.size else None,
        "postscale_budget_residual_max": float(residuals.max()) if residuals.size else None,
        "residual_method": "Replays source max/min outgoing-face split and flux_out grouping in float32 from post-limit shared face values.",
    }

def summarize(run_dir: Path, kdm_pre_path: Path) -> dict:
    kdm_pre = read_dump(kdm_pre_path)
    bounds = kdm_pre["bounds"]
    stages = []
    retained = {}
    for rk_step in (1, 2, 3):
        for stage in (1, 2, 3):
            path = run_dir / f"pr61_qnn_stage_{stage}_rk{rk_step}.raw"
            record = _read_stage(path, bounds, expected_stage=stage, expected_rk=rk_step)
            stages.append({key: value for key, value in record.items() if key not in ("state", "tendency")}
                          | {"state": _stats(record["state"]), "tendency": _stats(record["tendency"])})
            if stage in (2, 3):
                retained[(stage, rk_step)] = record["state"]
    boundary_delta = {}
    for rk in (1, 2, 3):
        after_update = retained[(2, rk)]
        after_boundary = retained[(3, rk)]
        boundary_delta[str(rk)] = {
            "changed_cells": int((after_update != after_boundary).sum()),
            "max_abs_change": float(np.max(np.abs(after_update - after_boundary))),
        }
    final = retained[(3, 3)]
    call_nn = kdm_pre["fields"]["NN"]
    call_match = bool(np.array_equal(final, call_nn))
    update = _read_update(run_dir / "pr61_qnn_update_rkfinal.raw", bounds)
    negative = call_nn < 0
    pd_budget_path = run_dir / "pr61_qnn_pd_budget_rk3.raw"
    pd_budget = _read_pd_budget(pd_budget_path, bounds, call_nn) if pd_budget_path.exists() else None
    return {
        "schema": "native_ccn_stage_trace_v1",
        "execution_scope": "one-rank, one-tile, first 20-second physics call",
        "kdm_pre": {"path": str(kdm_pre_path), "sha256": kdm_pre["sha256"],
                    "bytes": kdm_pre["bytes"], "NN": _stats(call_nn)},
        "stages": stages,
        "post_update_to_post_boundary": boundary_delta,
        "pd_limiter_budget": pd_budget,
        "final_rk3_after_boundary_matches_kdm_pre_NN": call_match,
        "final_rk3_update_replay": {
            "path": update["path"], "sha256": update["sha256"],
            "bytes": update["bytes"], "dt_s": update["dt_s"],
            "negative_cells": int(negative.sum()),
            "negative_cells_with_nonnegative_rk_old_state": int((update["scalar_old"][negative] >= 0).sum()),
            "negative_cells_with_zero_scalar_tend": int((update["scalar_tend"][negative] == 0).sum()),
            "float32_replay_exact_matches": int((update["predicted_float32"][negative] == call_nn[negative]).sum()),
            "float64_replay_negative": int((update["predicted_float64_from_saved_inputs"][negative] < 0).sum()),
            "float64_replay_positive": int((update["predicted_float64_from_saved_inputs"][negative] > 0).sum()),
            "float64_replay_zero": int((update["predicted_float64_from_saved_inputs"][negative] == 0).sum()),
            "scope_note": "Float64 replay uses already-rounded float32 operands and does not test precision inside the flux limiter or tendency generation.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("kdm_pre", type=Path, help="KDM6 pre-call stream for exact active bounds")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = summarize(args.run_dir, args.kdm_pre)
    except (OSError, TraceError, ValueError, struct.error) as exc:
        parser.error(str(exc))
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
