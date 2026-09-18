#!/usr/bin/env python3
"""Audit signed boundary defects from the actual QBAL sparse rows.

The sparse export is the production ``D G`` operator written by the prior
read-only audit.  The snapshot is the matching big-endian raw iteration
snapshot.  No RHS, state, or support mask is changed here.

The audited quantity is the stored continuity right-hand side
``z.T @ b = -z.T @ D(y)``.  It uses the pressure-coordinate metric
``z(i,j,k) = h(i,j) * dp(k)`` with ``h=dx=dy`` for this actual snapshot.  A
shared internal face is paired once; its two signed contributions are kept as
an ``internal_pair`` roundoff check and are never added to a boundary bucket.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


BOUNDARY_NAMES = ("outer", "topbottom", "support", "terrain-sentinel")
SHIFTS = np.asarray(
    ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)),
    dtype=np.int32,
)
OPPOSITE = np.asarray((1, 0, 3, 2, 5, 4), dtype=np.int32)
SENTINEL = np.float32(1.0e-30)
DETAIL_BALANCE_RELATIVE_TOLERANCE = 1.0e-12
RHS_RECONSTRUCTION_ROUNDING_ULPS = 32.0


@dataclass(frozen=True)
class Snapshot:
    """Arrays written by ``qbalpe_snapshot.f`` after the failed LEIBP3 call."""

    dimensions: tuple[int, int, int]
    relaxation_tolerance: float
    multiplier: np.ndarray
    legacy_rhs: np.ndarray
    erru: np.ndarray
    beta: np.ndarray
    tau: np.ndarray
    dx: np.ndarray
    dy: np.ndarray
    ps: np.ndarray
    p: np.ndarray
    dp: np.ndarray
    u: np.ndarray
    v: np.ndarray
    w: np.ndarray
    raw_sha256: str


@dataclass(frozen=True)
class SparseRows:
    dimensions: tuple[int, int, int]
    ijk: np.ndarray
    rhs: np.ndarray
    coefficients: np.ndarray
    raw_sha256: str


@dataclass(frozen=True)
class BackgroundTelemetry:
    """Background triplet from the agreed initial-LEIB_SUB telemetry.

    Binary telemetry is big-endian ``int32 nx,ny,nz`` followed by Fortran
    ``real32`` arrays ``ub,vb,omb``.  An ``npz`` with those three names is also
    accepted for conversion and inspection convenience.
    """

    dimensions: tuple[int, int, int]
    ub: np.ndarray
    vb: np.ndarray
    omb: np.ndarray
    raw_sha256: str


def _read_fortran_real32(raw: bytes, offset: int, shape: tuple[int, ...]) -> tuple[np.ndarray, int]:
    count = int(np.prod(shape))
    end = offset + 4 * count
    if end > len(raw):
        raise ValueError("snapshot ends before a declared array")
    values = np.frombuffer(raw, dtype=">f4", count=count, offset=offset)
    return values.reshape(shape, order="F"), end


def read_snapshot(path: Path) -> Snapshot:
    raw = path.read_bytes()
    if len(raw) < 16:
        raise ValueError("snapshot is shorter than its header")
    nx, ny, nz = np.frombuffer(raw, dtype=">i4", count=3).tolist()
    tolerance = float(np.frombuffer(raw, dtype=">f4", count=1, offset=12)[0])
    if min(nx, ny, nz) < 2 or not np.isfinite(tolerance):
        raise ValueError("invalid snapshot dimensions or tolerance")
    cell_shape = (nx, ny, nz)
    corner_shape = (nx + 1, ny + 1, nz + 1)
    plane_shape = (nx, ny)
    offset = 16
    arrays: list[np.ndarray] = []
    for shape in (corner_shape, corner_shape, cell_shape, cell_shape,
                  plane_shape, plane_shape, plane_shape, plane_shape,
                  (nz,), (nz,), cell_shape, cell_shape, cell_shape):
        value, offset = _read_fortran_real32(raw, offset, shape)
        arrays.append(value)
    if offset != len(raw):
        raise ValueError(f"snapshot has {len(raw) - offset} trailing bytes")
    if any(not np.isfinite(value).all() for value in arrays):
        raise ValueError("snapshot contains nonfinite values")
    if (arrays[2] <= 0.0).any() or (arrays[4] <= 0.0).any() or \
            (arrays[5] <= 0.0).any() or (arrays[6] <= 0.0).any() or \
            (arrays[9] <= 0.0).any():
        raise ValueError("snapshot contains nonpositive operator geometry")
    if (arrays[3] < 0.0).any() or (arrays[3] > 1.0).any():
        raise ValueError("snapshot contains influence outside [0, 1]")
    return Snapshot(
        (nx, ny, nz), tolerance, arrays[0], arrays[1], arrays[2], arrays[3],
        arrays[4], arrays[5], arrays[6], arrays[7], arrays[8], arrays[9],
        arrays[10], arrays[11], arrays[12], hashlib.sha256(raw).hexdigest(),
    )


def read_sparse_rows(path: Path) -> SparseRows:
    raw = path.read_bytes()
    if len(raw) < 16:
        raise ValueError("sparse export is shorter than its header")
    nx, ny, nz, count = np.frombuffer(raw, dtype="<i4", count=4).tolist()
    record = np.dtype([("ijk", "<i4", (3,)), ("rhs", "<f8"), ("c", "<f8", (6,))])
    expected = 16 + count * record.itemsize
    if min(nx, ny, nz) < 2 or count < 0 or expected != len(raw):
        raise ValueError("invalid sparse export dimensions or record length")
    rows = np.frombuffer(raw, dtype=record, count=count, offset=16)
    ijk = rows["ijk"].copy()
    rhs = rows["rhs"].copy()
    coefficients = rows["c"].copy()
    limits = np.asarray((nx, ny, nz), dtype=np.int32)
    if (ijk < 2).any() or (ijk > limits).any():
        raise ValueError("sparse row lies outside the physical continuity domain")
    ids = np.ravel_multi_index(ijk.T, (nx + 2, ny + 2, nz + 2))
    if len(np.unique(ids)) != count:
        raise ValueError("sparse export contains duplicate rows")
    if not np.isfinite(rhs).all() or not np.isfinite(coefficients).all():
        raise ValueError("sparse export contains nonfinite values")
    if (coefficients < 0).any():
        raise ValueError("sparse export contains a negative face coefficient")
    return SparseRows((nx, ny, nz), ijk, rhs, coefficients,
                      hashlib.sha256(raw).hexdigest())


def read_background_telemetry(path: Path, snapshot: Snapshot) -> BackgroundTelemetry:
    """Read only the background triplet; the proposed triplet stays snapshot-pinned."""
    raw = path.read_bytes()
    shape = snapshot.dimensions
    if path.suffix.lower() == ".npz":
        with np.load(path) as archive:
            missing = {name for name in ("ub", "vb", "omb") if name not in archive}
            if missing:
                raise ValueError(f"background telemetry missing arrays: {sorted(missing)}")
            arrays = tuple(np.asarray(archive[name], dtype=np.float32)
                           for name in ("ub", "vb", "omb"))
    else:
        if len(raw) < 12:
            raise ValueError("background telemetry is shorter than its header")
        dimensions = tuple(np.frombuffer(raw, dtype=">i4", count=3).tolist())
        if dimensions != shape:
            raise ValueError("background telemetry dimensions differ from snapshot")
        count = int(np.prod(shape))
        expected = 12 + 3 * 4 * count
        if len(raw) != expected:
            raise ValueError("background telemetry has an unexpected byte length")
        arrays = []
        offset = 12
        for _ in range(3):
            values = np.frombuffer(raw, dtype=">f4", count=count, offset=offset)
            arrays.append(values.reshape(shape, order="F"))
            offset += 4 * count
        arrays = tuple(arrays)
    if any(value.shape != snapshot.u.shape for value in arrays):
        raise ValueError("background telemetry array shape differs from snapshot")
    if any(not np.isfinite(value).all() for value in arrays):
        raise ValueError("background telemetry contains nonfinite values")
    return BackgroundTelemetry(shape, *arrays, hashlib.sha256(raw).hexdigest())


def _neighbor_indices(rows: SparseRows) -> np.ndarray:
    nx, ny, nz = rows.dimensions
    table_shape = (nx + 2, ny + 2, nz + 2)
    table = np.full(int(np.prod(table_shape)), -1, dtype=np.int64)
    row_ids = np.ravel_multi_index(rows.ijk.T, table_shape)
    table[row_ids] = np.arange(len(rows.ijk))
    neighbors = np.full((len(rows.ijk), 6), -1, dtype=np.int64)
    limits = np.asarray(rows.dimensions, dtype=np.int32)
    for direction, shift in enumerate(SHIFTS):
        candidate = rows.ijk + shift
        valid = np.all((candidate >= 2) & (candidate <= limits), axis=1)
        neighbors[valid, direction] = table[
            np.ravel_multi_index(candidate[valid].T, table_shape)
        ]
    return neighbors


def _sentinel_row(snapshot: Snapshot, cell: np.ndarray) -> bool:
    """Return whether a physical cell has a sentinel in its six continuity faces."""
    i, j, k = (cell - 1).tolist()
    return bool(
        snapshot.u[i, j - 1, k - 1] == SENTINEL
        or snapshot.u[i - 1, j - 1, k - 1] == SENTINEL
        or snapshot.v[i - 1, j, k - 1] == SENTINEL
        or snapshot.v[i - 1, j - 1, k - 1] == SENTINEL
        or snapshot.w[i, j, k - 1] == SENTINEL
        or snapshot.w[i, j, k] == SENTINEL
    )


def _stored_active_mask(rows: SparseRows) -> np.ndarray:
    nx, ny, nz = rows.dimensions
    active = np.zeros((nx - 1, ny - 1, nz - 1), dtype=bool)
    active[rows.ijk[:, 0] - 2, rows.ijk[:, 1] - 2, rows.ijk[:, 2] - 2] = True
    return active


def _expected_active_mask(snapshot: Snapshot) -> np.ndarray:
    nx, ny, nz = snapshot.dimensions
    sentinels = (
        (snapshot.u[1:nx, :ny - 1, :nz - 1] == SENTINEL)
        | (snapshot.u[:nx - 1, :ny - 1, :nz - 1] == SENTINEL)
        | (snapshot.v[:nx - 1, 1:ny, :nz - 1] == SENTINEL)
        | (snapshot.v[:nx - 1, :ny - 1, :nz - 1] == SENTINEL)
        | (snapshot.w[1:nx, 1:ny, :nz - 1] == SENTINEL)
        | (snapshot.w[1:nx, 1:ny, 1:nz] == SENTINEL)
    )
    support = snapshot.beta[1:nx, 1:ny, 1:nz] > 0.0
    above_ground = snapshot.ps[1:nx, 1:ny, None] >= snapshot.p[1:nz]
    return support & above_ground & ~sentinels


def _classify_missing_face(
    rows: SparseRows,
    snapshot: Snapshot,
    row_number: int,
    direction: int,
    neighbors: np.ndarray,
) -> str:
    """Classify exactly one non-operator face of an active row."""
    i, j, k = rows.ijk[row_number].tolist()
    if direction == 0 and i == rows.dimensions[0]:
        return "outer"
    if direction == 1 and i == 2:
        return "outer"
    if direction == 2 and j == rows.dimensions[1]:
        return "outer"
    if direction == 3 and j == 2:
        return "outer"
    if direction == 4 and k == rows.dimensions[2]:
        return "topbottom"
    if direction == 5 and k == 2:
        return "topbottom"

    candidate = rows.ijk[row_number] + SHIFTS[direction]
    if neighbors[row_number, direction] >= 0:
        raise ValueError("positive-coefficient face was classified as missing")
    ci, cj, ck = (candidate - 1).tolist()
    beta = float(snapshot.beta[ci, cj, ck])
    above_ground = float(snapshot.ps[ci, cj]) >= float(snapshot.p[ck])
    sentinel = _sentinel_row(snapshot, candidate)
    if (not above_ground) or sentinel:
        return "terrain-sentinel"
    if beta <= 0.0:
        return "support"
    raise ValueError("active row has an unexplained missing positive-support neighbor")


def _signed_terms(
    snapshot: Snapshot,
    rows: SparseRows,
    state: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
) -> np.ndarray:
    """Return six signed RHS flux terms, already multiplied by z=h*dp."""
    if state is None:
        u, v, w = snapshot.u, snapshot.v, snapshot.w
    else:
        u, v, w = state
        if any(value.shape != snapshot.u.shape for value in state):
            raise ValueError("state array shape differs from snapshot")
        if any(not np.isfinite(value).all() for value in state):
            raise ValueError("state array contains nonfinite values")
    ri, rj, rk = (rows.ijk - 1).T
    z = (snapshot.dx[ri, rj].astype(np.float64)
         * snapshot.dp[rk].astype(np.float64))
    dx = snapshot.dx[ri, rj].astype(np.float64)
    dy = snapshot.dy[ri, rj].astype(np.float64)
    dp = snapshot.dp[rk].astype(np.float64)
    return np.column_stack((
        -z * u[ri, rj - 1, rk - 1] / dx,
        z * u[ri - 1, rj - 1, rk - 1] / dx,
        -z * v[ri - 1, rj, rk - 1] / dy,
        z * v[ri - 1, rj - 1, rk - 1] / dy,
        z * w[ri, rj, rk] / dp,
        -z * w[ri, rj, rk - 1] / dp,
    ))


def _state_has_active_sentinel(
    rows: SparseRows,
    state: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> bool:
    u, v, w = state
    ri, rj, rk = (rows.ijk - 1).T
    return bool(np.any(
        (u[ri, rj - 1, rk - 1] == SENTINEL)
        | (u[ri - 1, rj - 1, rk - 1] == SENTINEL)
        | (v[ri - 1, rj, rk - 1] == SENTINEL)
        | (v[ri - 1, rj - 1, rk - 1] == SENTINEL)
        | (w[ri, rj, rk - 1] == SENTINEL)
        | (w[ri, rj, rk] == SENTINEL)
    ))


def _relabel_stably(labels: np.ndarray) -> np.ndarray:
    first = np.full(int(labels.max()) + 1, len(labels), dtype=np.int64)
    for index, label in enumerate(labels):
        first[label] = min(first[label], index)
    order = np.argsort(first, kind="stable")
    remap = np.empty_like(order)
    remap[order] = np.arange(len(order))
    return remap[labels]


def _decompose_components(
    rows: SparseRows,
    snapshot: Snapshot,
    neighbors: np.ndarray,
    positive: np.ndarray,
    labels: np.ndarray,
    z: np.ndarray,
    signed_terms: np.ndarray,
    row_metric_rhs: np.ndarray,
    state_label: str,
) -> list[dict]:
    """Partition one state with the fixed proposed active graph and labels."""
    component_count = int(labels.max()) + 1 if len(labels) else 0
    components: list[dict] = []
    for component in range(component_count):
        selected = np.flatnonzero(labels == component)
        weight_sum = math.fsum(float(value) for value in z[selected])
        if not math.isfinite(weight_sum) or weight_sum <= 0.0:
            raise ValueError("component has a nonpositive analytic metric weight sum")
        boundary_values = {name: [] for name in BOUNDARY_NAMES}
        boundary_counts = {name: 0 for name in BOUNDARY_NAMES}
        internal_sum = 0.0
        internal_compensation = 0.0
        internal_max = 0.0
        internal_count = 0
        selected_set = set(selected.tolist())
        for row_number in selected:
            for direction in range(6):
                neighbor = int(neighbors[row_number, direction])
                if positive[row_number, direction] and neighbor >= 0:
                    if row_number < neighbor and neighbor in selected_set:
                        pair = float(signed_terms[row_number, direction]
                                     + signed_terms[neighbor, OPPOSITE[direction]])
                        corrected = pair - internal_compensation
                        updated = internal_sum + corrected
                        internal_compensation = (updated - internal_sum) - corrected
                        internal_sum = updated
                        internal_max = max(internal_max, abs(pair))
                        internal_count += 1
                    continue
                name = _classify_missing_face(rows, snapshot, row_number,
                                              direction, neighbors)
                boundary_values[name].append(float(signed_terms[row_number, direction]))
                boundary_counts[name] += 1
        if sum(boundary_counts.values()) + 2 * internal_count != 6 * len(selected):
            raise ValueError("boundary partition double-counted or omitted a face")
        boundary = {name: math.fsum(values)
                    for name, values in boundary_values.items()}
        weighted_rhs = math.fsum(float(value) for value in row_metric_rhs[selected])
        axis_signed = {
            "u": math.fsum(float(value) for value in signed_terms[selected, :2].ravel()),
            "v": math.fsum(float(value) for value in signed_terms[selected, 2:4].ravel()),
            "omega": math.fsum(float(value) for value in signed_terms[selected, 4:6].ravel()),
        }
        normalized = {name: value / weight_sum for name, value in boundary.items()}
        components.append({
            "id": component,
            "state": state_label,
            "rows": int(len(selected)),
            "first_cell": rows.ijk[selected[0]].tolist(),
            "metric_weight_sum": weight_sum,
            "weighted_rhs": weighted_rhs,
            "normalized_left_rhs": weighted_rhs / weight_sum,
            "boundary_signed": boundary,
            "boundary_normalized": normalized,
            "axis_signed": axis_signed,
            "boundary_face_counts": boundary_counts,
            "boundary_signed_sum": float(math.fsum(boundary.values())),
            "internal_pair_count": internal_count,
            "internal_pair_signed_sum": internal_sum,
            "internal_pair_max_abs": internal_max,
            "closure_error": float(math.fsum(boundary.values())
                                    + internal_sum - weighted_rhs),
        })
    return components


def _state_summary(components: list[dict]) -> dict:
    """Aggregate a fixed-label state without changing its partition."""
    boundary_signed = {
        name: math.fsum(component["boundary_signed"][name]
                        for component in components)
        for name in BOUNDARY_NAMES
    }
    boundary_face_counts = {
        name: sum(component["boundary_face_counts"][name]
                  for component in components)
        for name in BOUNDARY_NAMES
    }
    internal_signed = math.fsum(
        component["internal_pair_signed_sum"] for component in components
    )
    axis_signed = {
        axis: math.fsum(component["axis_signed"][axis] for component in components)
        for axis in ("u", "v", "omega")
    }
    weighted_rhs = math.fsum(component["weighted_rhs"] for component in components)
    boundary_sum = math.fsum(boundary_signed.values())
    return {
        "boundary_signed": boundary_signed,
        "boundary_face_counts": boundary_face_counts,
        "boundary_signed_sum": boundary_sum,
        "axis_signed": axis_signed,
        "internal_pair_count": sum(
            component["internal_pair_count"] for component in components
        ),
        "internal_pair_signed_sum": internal_signed,
        "weighted_rhs": weighted_rhs,
        "closure_error": boundary_sum + internal_signed - weighted_rhs,
    }


def diagnose(
    rows_path: Path,
    snapshot_path: Path,
    background_path: Path | None = None,
) -> dict:
    rows = read_sparse_rows(rows_path)
    snapshot = read_snapshot(snapshot_path)
    telemetry = (read_background_telemetry(background_path, snapshot)
                 if background_path is not None else None)
    if rows.dimensions != snapshot.dimensions:
        raise ValueError("sparse rows and snapshot dimensions differ")
    if np.max(np.abs(snapshot.dx - snapshot.dy)) != 0.0:
        raise ValueError("analytic z=h*dp requires the actual dx=dy metric")
    if not np.array_equal(_stored_active_mask(rows), _expected_active_mask(snapshot)):
        raise ValueError("sparse active rows do not match snapshot support/terrain/sentinel mask")

    neighbors = _neighbor_indices(rows)
    positive = rows.coefficients > 0.0
    if np.any(positive & (neighbors < 0)):
        raise ValueError("positive coefficient has no paired active face")
    edge_rows: list[np.ndarray] = []
    edge_columns: list[np.ndarray] = []
    for direction in (0, 2, 4):
        present = positive[:, direction] & (neighbors[:, direction] >= 0)
        edge_rows.append(np.flatnonzero(present))
        edge_columns.append(neighbors[present, direction])
    if edge_rows:
        source = np.concatenate(edge_rows)
        target = np.concatenate(edge_columns)
        graph = coo_matrix((np.ones(len(source)), (source, target)),
                           shape=(len(rows.ijk), len(rows.ijk)))
    else:
        graph = coo_matrix((len(rows.ijk), len(rows.ijk)))
    _, labels = connected_components(graph + graph.T, directed=False)
    labels = _relabel_stably(labels)
    component_count = int(labels.max()) + 1 if len(labels) else 0

    ri, rj, rk = (rows.ijk - 1).T
    z = (snapshot.dx[ri, rj].astype(np.float64)
         * snapshot.dp[rk].astype(np.float64))
    signed_terms = _signed_terms(snapshot, rows)
    row_metric_rhs = z * rows.rhs
    row_term_error = signed_terms.sum(axis=1) - row_metric_rhs

    detail_abs: list[float] = []
    detail_rel: list[float] = []
    detail_count = 0
    transpose = -z * rows.coefficients.sum(axis=1)
    transpose_scale = float(2.0 * np.sum(np.abs(transpose)))
    for direction in range(6):
        present = positive[:, direction] & (neighbors[:, direction] >= 0)
        source = np.flatnonzero(present)
        target = neighbors[present, direction]
        lhs = z[source] * rows.coefficients[source, direction]
        rhs = z[target] * rows.coefficients[target, OPPOSITE[direction]]
        np.add.at(transpose, target, lhs)
        difference = lhs - rhs
        denominator = np.abs(lhs) + np.abs(rhs)
        if (denominator <= 0.0).any():
            raise ValueError("positive internal face has zero metric balance denominator")
        detail_abs.extend(np.abs(difference).tolist())
        detail_rel.extend((np.abs(difference) / denominator).tolist())
        detail_count += len(source)

    transpose_l1 = float(np.sum(np.abs(transpose)))
    transpose_relative = transpose_l1 / transpose_scale if transpose_scale else 0.0
    if (not math.isfinite(transpose_relative)
            or transpose_relative > DETAIL_BALANCE_RELATIVE_TOLERANCE):
        raise ValueError("analytic detail balance fails full transpose residual check")
    detail_max_abs = float(max(detail_abs, default=0.0))
    detail_max_relative = float(max(detail_rel, default=0.0))
    if (not math.isfinite(detail_max_abs)
            or not math.isfinite(detail_max_relative)
            or detail_max_relative > DETAIL_BALANCE_RELATIVE_TOLERANCE):
        raise ValueError(
            "sparse operator fails analytic per-edge detail balance: "
            f"abs={detail_max_abs:g}, rel={detail_max_relative:g}"
        )
    reconstruction_scale = np.sum(np.abs(signed_terms), axis=1)
    reconstruction_bound = (
        RHS_RECONSTRUCTION_ROUNDING_ULPS
        * np.finfo(np.float64).eps
        * reconstruction_scale
    )
    reconstruction_ratio = np.divide(
        np.abs(row_term_error), reconstruction_bound,
        out=np.zeros_like(row_term_error), where=reconstruction_bound > 0.0,
    )
    reconstruction_max_abs = float(np.max(np.abs(row_term_error)))
    reconstruction_max_ratio = float(np.max(reconstruction_ratio))
    zero_scale_error = (reconstruction_scale == 0.0) & (row_term_error != 0.0)
    if (not np.isfinite(reconstruction_scale).all()
            or not np.isfinite(reconstruction_ratio).all()
            or zero_scale_error.any()
            or reconstruction_max_ratio > 1.0):
        raise ValueError(
            "sparse RHS does not reconstruct from the stored float64 continuity "
            f"faces within {RHS_RECONSTRUCTION_ROUNDING_ULPS:g} float64 ulps: "
            f"max={reconstruction_max_abs:g}, ratio={reconstruction_max_ratio:g}"
        )

    components = _decompose_components(
        rows, snapshot, neighbors, positive, labels, z, signed_terms,
        row_metric_rhs, "proposal",
    )
    state_decompositions = {"proposal": components}
    if telemetry is not None:
        background_state = (telemetry.ub, telemetry.vb, telemetry.omb)
        if _state_has_active_sentinel(rows, background_state):
            raise ValueError("background telemetry has a sentinel on a proposed active face")
        background_terms = _signed_terms(snapshot, rows, background_state)
        background_rhs = background_terms.sum(axis=1)
        state_decompositions["background"] = _decompose_components(
            rows, snapshot, neighbors, positive, labels, z, background_terms,
            background_rhs, "background",
        )
        delta_state = tuple(
            proposed.astype(np.float64) - background.astype(np.float64)
            for proposed, background in zip(
                (snapshot.u, snapshot.v, snapshot.w), background_state
            )
        )
        delta_terms = _signed_terms(snapshot, rows, delta_state)
        delta_rhs = delta_terms.sum(axis=1)
        state_decompositions["proposal_delta"] = _decompose_components(
            rows, snapshot, neighbors, positive, labels, z, delta_terms,
            delta_rhs, "proposal_delta",
        )

    attribution = {
        "feasible_from_snapshot": telemetry is not None,
        "stored_triplet": "uo,vo,omo pre-correction proposed triplet",
        "missing_arrays": [] if telemetry is not None else ["ub", "vb", "omb"],
        "background_telemetry": (
            str(background_path.resolve()) if background_path is not None else None
        ),
        "background_telemetry_sha256": (
            telemetry.raw_sha256 if telemetry is not None else None
        ),
        "reason": (
            "Background and proposal_delta use the fixed proposed active labels, "
            "faces, and metric weights from the pinned snapshot."
            if telemetry is not None else
            "The pinned snapshot already stores uo,vo,omo as the proposed "
            "pre-correction triplet, but not ub,vb,omb. Capture the background "
            "triplet at initial LEIB_SUB to attribute source terms without inference."
        ),
    }

    state_summaries = {
        state: _state_summary(decomposition)
        for state, decomposition in state_decompositions.items()
    }
    return {
        "source": {
            "rows": str(rows_path.resolve()),
            "rows_sha256": rows.raw_sha256,
            "snapshot": str(snapshot_path.resolve()),
            "snapshot_sha256": snapshot.raw_sha256,
            "dimensions": list(rows.dimensions),
            "active_rows": int(len(rows.ijk)),
        },
        "metric": {
            "formula": "z(i,j,k)=h(i,j)*dp(k), h=dx=dy",
            "signed_quantity": "z^T b = -z^T D(y)",
            "face_signs": "east=-z*u/dx, west=+z*u/dx, north=-z*v/dy, "
                          "south=+z*v/dy, upper=+z*w/dp, lower=-z*w/dp",
            "axis_contribution_scope": (
                "signed six-face sums grouped as u, v, omega; no COM causality claim"
            ),
            "dx_equals_dy_max_abs": float(np.max(np.abs(snapshot.dx - snapshot.dy))),
            "z_min": float(z.min()),
            "z_max": float(z.max()),
            "z_dtype": "float64",
            "analytic_transpose_l1": transpose_l1,
            "analytic_transpose_relative": transpose_relative,
            "peredge_detailbalance_directed_count": detail_count,
            "peredge_detailbalance_unique_count": detail_count // 2,
            "peredge_detailbalance_max_abs": detail_max_abs,
            "peredge_detailbalance_rms_abs": float(np.sqrt(np.mean(np.square(detail_abs)))
                                                       if detail_abs else 0.0),
            "peredge_detailbalance_max_relative": detail_max_relative,
            "peredge_detailbalance_relative_denominator": "abs(lhs)+abs(rhs)",
            "peredge_detailbalance_checks_all_positive_interfaces": True,
            "weighted_rhs_sum": math.fsum(float(value) for value in row_metric_rhs),
            "unweighted_rhs_sum": math.fsum(float(value) for value in rows.rhs),
            "row_flux_reconstruction_max_abs": reconstruction_max_abs,
            "row_flux_reconstruction_max_roundoff_ratio": reconstruction_max_ratio,
            "row_flux_reconstruction_roundoff_ulps": RHS_RECONSTRUCTION_ROUNDING_ULPS,
            "row_flux_reconstruction_rms": float(np.sqrt(np.mean(np.square(row_term_error)))),
        },
        "components": components,
        "state_decompositions": state_decompositions,
        "state_summaries": state_summaries,
        "component_count": component_count,
        "boundary_groups": list(BOUNDARY_NAMES),
        "no_doublecount_contract": (
            "Each positive internal face is paired once by row index. Boundary terms "
            "are assigned once to outer, topbottom, support, or terrain-sentinel."
        ),
        "background_proposal_attribution": attribution,
        "scope": "actual stored operator/state only; no after-state or production edit",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rows", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--background-telemetry", type=Path)
    args = parser.parse_args()
    result = diagnose(args.rows, args.snapshot, args.background_telemetry)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "active_rows": result["source"]["active_rows"],
        "components": result["component_count"],
        "weighted_rhs_sum": result["metric"]["weighted_rhs_sum"],
        "detailbalance_max_abs": result["metric"]["peredge_detailbalance_max_abs"],
    }))


if __name__ == "__main__":
    main()
