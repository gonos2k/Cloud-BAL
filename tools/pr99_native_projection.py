#!/usr/bin/env python3
"""Research projection of the additional C-H wind onto native dry-flux constraints.

The reference is HYDRO, not zero motion. Only interior faces of the predeclared
QC buffer are controls. This linear proposal requires the archived native
consumer replay and a new native tendency evaluation before any approval.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

import netCDF4
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import lsmr

import pr94_cloud_response as cloud
from pr87_native_history import _finite

ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = ROOT / "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json"


def control_faces(columns):
    columns = np.asarray(columns, dtype=bool)
    if columns.ndim != 2 or not columns.any():
        raise ValueError("empty or invalid fixed control columns")
    ny, nx = columns.shape
    u = np.zeros((ny, nx + 1), dtype=bool)
    v = np.zeros((ny + 1, nx), dtype=bool)
    u[:, 1:-1] = columns[:, :-1] & columns[:, 1:]
    v[1:-1] = columns[:-1] & columns[1:]
    return u, v


def divergence_matrix(columns, u_coeff, v_coeff):
    """Outward face flux difference; positive row factors do not alter its kernel."""
    u_mask, v_mask = control_faces(columns)
    if (u_coeff.shape != u_mask.shape or v_coeff.shape != v_mask.shape
            or not np.isfinite(u_coeff).all() or not np.isfinite(v_coeff).all()
            or np.any(u_coeff <= 0) or np.any(v_coeff <= 0)):
        raise ValueError("invalid face carrier or map geometry")
    ids = np.full(columns.shape, -1, dtype=int)
    ids[columns] = np.arange(columns.sum())
    rows, cols, values = [], [], []
    for j, i in np.argwhere(u_mask):
        n = len(values) // 2
        rows.extend((ids[j, i-1], ids[j, i]))
        cols.extend((n, n))
        values.extend((u_coeff[j, i], -u_coeff[j, i]))
    for j, i in np.argwhere(v_mask):
        n = len(values) // 2
        rows.extend((ids[j-1, i], ids[j, i]))
        cols.extend((n, n))
        values.extend((v_coeff[j, i], -v_coeff[j, i]))
    return coo_matrix((values, (rows, cols)),
                      shape=(int(columns.sum()), int(u_mask.sum()+v_mask.sum()))).tocsr()


def project_increment(matrix, increment):
    increment = np.asarray(increment, dtype=np.float64)
    if increment.shape != (matrix.shape[1],) or not np.isfinite(increment).all():
        raise ValueError("invalid additional native wind")
    rhs = matrix @ increment
    solved = lsmr(matrix, rhs, atol=1e-13, btol=1e-13, maxiter=2000)
    if solved[1] not in (0, 1, 2):
        raise ValueError(f"native projection did not converge: LSMR {solved[1]}")
    result = increment - solved[0]
    residual = float(np.linalg.norm(matrix @ result))
    # Numerical solver gate, not a relaxation of any physical state predicate.
    limit = (1e-10 * np.linalg.norm(rhs) + 64*np.finfo(float).eps
             * np.linalg.norm(matrix.data) * np.linalg.norm(increment))
    if residual > limit:
        raise ValueError("native projection leaves an unresolved flux constraint")
    return result, {"solver_stop": int(solved[1]), "iterations": int(solved[2]),
                    "initial_divergence_L2": float(np.linalg.norm(rhs)),
                    "continuous_divergence_L2": residual,
                    "continuous_solver_limit": float(limit)}


def face_coefficients(ds, k):
    """Freeze source-ordered REAL32 face mass, hybrid coefficients and metrics.

    The matrix evaluates their products in REAL64. REAL32 division/multiplication
    during calc_ww_cp remains a separate consumer check, not a linear identity.
    """
    read = lambda name: _finite(ds, name, 0).astype(np.float32)
    mu, mub = read("MU"), read("MUB")
    c1, c2 = read("C1H")[k], read("C2H")[k]
    muu = np.empty((mu.shape[0], mu.shape[1]+1), dtype=np.float32)
    muv = np.empty((mu.shape[0]+1, mu.shape[1]), dtype=np.float32)
    muu[:, 1:-1] = np.float32(.5) * (((mu[:, 1:]+mub[:, 1:])+mu[:, :-1])+mub[:, :-1])
    muv[1:-1] = np.float32(.5) * (((mu[1:]+mub[1:])+mu[:-1])+mub[:-1])
    muu[:, 0], muu[:, -1] = muu[:, 1], muu[:, -2]
    muv[0], muv[-1] = muv[1], muv[-2]
    my, mx = read("MAPFAC_UY"), read("MAPFAC_VX")
    mass_map, dnw = read("MAPFAC_MX"), read("DNW")
    rdx, rdy = float(read("RDX")), float(read("RDY"))
    if (not np.isfinite([rdx, rdy]).all() or min(rdx, rdy) <= 0
            or np.any(my <= 0) or np.any(mx <= 0) or np.any(mass_map <= 0)
            or np.any(dnw >= 0)):
        raise ValueError("invalid native map metrics")
    return ((c1*muu+c2).astype(np.float64) / my * rdx,
            (c1*muv+c2).astype(np.float64) * (np.float32(1)/mx) * rdy)


def propose(hydro, coupled, output):
    if output.exists() or output.with_suffix(".proposal.json").exists():
        raise FileExistsError(output)
    with netCDF4.Dataset(hydro) as h, netCDF4.Dataset(coupled) as c:
        h.set_auto_mask(False)
        c.set_auto_mask(False)
        if set(h.variables) != set(c.variables):
            raise ValueError("reference and treatment variable sets differ")
        for name in h.variables:
            if (h[name].dtype != c[name].dtype or h[name].dimensions != c[name].dimensions
                    or any(getattr(h[name], attr, None) != getattr(c[name], attr, None)
                           for attr in ("units", "stagger"))):
                raise ValueError(f"reference metadata differs: {name}")
            if name not in ("U", "V") and not np.array_equal(h[name][...], c[name][...]):
                raise ValueError(f"reference carrier/state differs: {name}")
        if any(c[name].dtype != np.dtype("float32") for name in ("U", "V")):
            raise ValueError("native wind proposal requires REAL32 storage")
        u0, v0 = (_finite(h, name, 0) for name in ("U", "V"))
        uc, vc = (_finite(c, name, 0) for name in ("U", "V"))
        nz, ny, nx = u0.shape[0], u0.shape[1], v0.shape[2]
        composed = json.loads(COMPOSITION.read_text())["composed_qc_vertical_influence"]
        support = cloud.make_masks(composed, (nz, ny-2, nx-2))
        columns = np.zeros((ny, nx), dtype=bool)
        columns[1:-1, 1:-1] = support["fixed_5_cell_chebyshev_buffer"].any(axis=0)
        um, vm = control_faces(columns)
        if np.any((uc-u0)[:, ~um]) or np.any((vc-v0)[:, ~vm]):
            raise ValueError("additional wind extends outside the declared free faces")
        u, v, rows = u0.astype(np.float32), v0.astype(np.float32), []
        for k in range(nz):
            matrix = divergence_matrix(columns, *face_coefficients(h, k))
            increment = np.r_[(uc-u0)[k][um], (vc-v0)[k][vm]]
            projected, row = project_increment(matrix, increment)
            base = np.r_[u0[k][um], v0[k][vm]]
            target = base + projected
            stored = target.astype(np.float32).astype(np.float64)
            # A posteriori arithmetic identity from independently known storage error.
            actual = matrix @ (stored-base)
            error = stored-target
            bound = np.abs(matrix) @ np.abs(error) + np.abs(matrix @ projected)
            row.update(k=k+1, stored_divergence_L2=float(np.linalg.norm(actual)),
                       storage_bound_L2=float(np.linalg.norm(bound)),
                       additional_wind_L2=float(np.linalg.norm(stored-base)))
            u[k][um], v[k][vm] = stored[:um.sum()], stored[um.sum():]
            rows.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(coupled, output)
    try:
        with netCDF4.Dataset(output, "r+") as ds:
            ds["U"][0], ds["V"][0] = u, v
        with netCDF4.Dataset(coupled) as source, netCDF4.Dataset(output) as ds:
            for name in source.variables:
                if name not in ("U", "V") and source[name][...].tobytes() != ds[name][...].tobytes():
                    raise ValueError(f"proposal unexpectedly changed {name}")
    except Exception:
        output.unlink()
        raise
    return {"schema": "pr99_native_uv_projection_proposal_v1",
            "status": "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_TENDENCY_VALIDATION",
            "role": "COUPLED",
            "reference": {"path": str(hydro), "sha256": cloud.sha256(hydro)},
            "parent": {"path": str(coupled), "sha256": cloud.sha256(coupled)},
            "candidate": {"path": str(output), "sha256": cloud.sha256(output)},
            "boundary": {"path": str(coupled.parent / "wrfbdy_d01"),
                         "sha256": cloud.sha256(coupled.parent / "wrfbdy_d01")},
            "generator": {"path": str(Path(__file__).resolve()),
                          "sha256": cloud.sha256(Path(__file__))},
            "composition": {"path": str(COMPOSITION), "sha256": cloud.sha256(COMPOSITION)},
            "composition_sha256": cloud.sha256(COMPOSITION),
            "controls": "U/V only, faces with both donors inside the fixed five-cell QC buffer",
            "reference_motion": "HYDRO; preserve its nonzero layer flux divergence",
            "fixed_columns": int(columns.sum()), "free_faces_per_layer": int(um.sum()+vm.sum()),
            "layers": rows, "physical_approval": "FAIL_OPEN",
            "limits": ["Frozen-carrier linear dry-flux constraint; not full momentum balance.",
                       "No omega-to-W conversion; W and every other stored variable unchanged.",
                       "REAL32 native operation order must be checked by the archived consumer.",
                       "No observation skill or complete water/energy budget is established."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hydro", required=True, type=Path)
    parser.add_argument("--coupled", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = propose(args.hydro, args.coupled, args.output)
    try:
        with args.output.with_suffix(".proposal.json").open("x") as stream:
            stream.write(json.dumps(report, indent=2, allow_nan=False)+"\n")
    except Exception:
        args.output.unlink()
        raise
