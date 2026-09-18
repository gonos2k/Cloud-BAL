#!/usr/bin/env python3
"""Diagnose the exported production D G rows; never alter RHS or state.

The Fortran audit writes little-endian stream records: four int32 header
values (nx, ny, nz, nrow), then i/j/k int32, RHS float64, six float64
coefficients in E/W/N/S/upper/lower order for every active row.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import breadth_first_order, connected_components


RESIDUAL_TOLERANCE = 1e-10
DETAILED_BALANCE_TOLERANCE = 4096 * np.finfo(float).eps


def diagnose(path: Path) -> dict:
    raw = path.read_bytes()
    nx, ny, nz, count = np.frombuffer(raw, dtype='<i4', count=4).tolist()
    dtype = np.dtype([('ijk', '<i4', (3,)), ('rhs', '<f8'), ('c', '<f8', (6,))])
    if min(nx, ny, nz) < 2 or count < 0 or len(raw) != 16 + count * dtype.itemsize:
        raise ValueError('invalid operator record length or dimensions')
    rows = np.frombuffer(raw, dtype=dtype, offset=16, count=count)
    ijk, rhs, coeff = rows['ijk'], rows['rhs'], rows['c']
    if not np.isfinite(rhs).all() or not np.isfinite(coeff).all() or (coeff < 0).any():
        raise ValueError('nonfinite RHS or invalid face coefficient')
    shape = (nx + 2, ny + 2, nz + 2)
    if (ijk < 2).any() or (ijk > np.array([nx, ny, nz])).any():
        raise ValueError('active row outside continuity domain')
    ids = np.ravel_multi_index(ijk.T, shape)
    if len(np.unique(ids)) != count:
        raise ValueError('duplicate active row')
    lookup = np.full(np.prod(shape), -1, dtype=np.int32)
    lookup[ids] = np.arange(count)
    sources, targets, values = [], [], []
    anchored = np.zeros(count, dtype=bool)
    for direction, shift in enumerate(((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                                        (0, -1, 0), (0, 0, 1), (0, 0, -1))):
        neighbor = lookup[np.ravel_multi_index((ijk + shift).T, shape)]
        positive = coeff[:, direction] > 0
        anchored |= positive & (neighbor < 0)
        present = positive & (neighbor >= 0)
        sources.append(np.flatnonzero(present))
        targets.append(neighbor[present])
        values.append(coeff[present, direction])
    off = coo_matrix((np.concatenate(values),
                      (np.concatenate(sources), np.concatenate(targets))),
                     shape=(count, count)).tocsr()
    ncomponent, labels = connected_components(off, directed=False)
    matrix = off.copy()
    matrix.setdiag(-coeff.sum(axis=1))
    components = []
    grouped = np.argsort(labels, kind='stable')
    offsets = np.concatenate(([0], np.cumsum(np.bincount(labels))))
    for component in range(ncomponent):
        selected = grouped[offsets[component]:offsets[component + 1]]
        entry = {'id': component, 'rows': len(selected),
                 'first_cell': ijk[selected[0]].tolist(),
                 'anchored': bool(anchored[selected].any())}
        positive_diagonal = coeff[selected].sum(axis=1)
        diagonal_min = float(np.min(positive_diagonal))
        diagonal_max = float(np.max(positive_diagonal))
        entry.update(
            positive_diagonal_min=diagonal_min,
            positive_diagonal_max=diagonal_max,
            positive_diagonal_ratio=(diagonal_max / diagonal_min
                                      if diagonal_min > 0 else None),
        )
        components.append(entry)
        if entry['anchored']:
            entry['compatibility'] = 'ANCHORED_NO_CONSTANT_RIGHT_NULLSPACE'
            continue
        force = rhs[selected]
        block = matrix[selected][:, selected]
        edge_block = off[selected][:, selected]
        tree_valid = True
        if len(selected) == 1:
            left = np.ones(1)
            residual = 0.0
        else:
            # A spanning-tree candidate is cheap even for the actual 3-D
            # component. Both edge detailed balance and the full transpose
            # residual are required; a tree alone is not a certificate.
            order, parent = breadth_first_order(block, 0, directed=False)
            child = order[1:]
            if len(order) != len(selected):
                tree_valid = False
            else:
                tree_forward = np.asarray(
                    block[parent[child], child]).ravel()
                tree_reverse = np.asarray(
                    block[child, parent[child]]).ravel()
                tree_valid = bool(
                    np.isfinite(tree_forward).all() and
                    np.isfinite(tree_reverse).all() and
                    (tree_forward > 0).all() and (tree_reverse > 0).all())
            if tree_valid:
                ratio = tree_forward / tree_reverse
                left = np.ones(len(selected))
                for node, edge_ratio in zip(child, ratio):
                    left[node] = left[parent[node]] * edge_ratio
                left /= left.sum()
                residual = float(np.sum(np.abs(block.T @ left)) /
                                 np.sum(abs(block).T @ np.abs(left)))
            else:
                left = np.full(len(selected), np.nan)
                residual = float('inf')
        edge_max_relative = None
        edge_count = edge_block.nnz
        unresolved_edges = 0
        missing_reverse = not tree_valid
        if edge_count == 0 and tree_valid:
            edge_max_relative = 0.0
        if edge_count and np.isfinite(left).all() and left.min() > 0:
            edges = edge_block.tocoo()
            reverse = np.asarray(edge_block[edges.col, edges.row]).ravel()
            lhs = left[edges.row] * edges.data
            rhs_edge = left[edges.col] * reverse
            edge_scale = np.maximum(np.abs(lhs), np.abs(rhs_edge))
            valid = (np.isfinite(lhs) & np.isfinite(rhs_edge) &
                     (edge_scale > 0) & (reverse > 0))
            missing_reverse = bool((reverse <= 0).any())
            relative = np.ones(edge_count)
            forward_scaled = lhs[valid] / edge_scale[valid]
            reverse_scaled = rhs_edge[valid] / edge_scale[valid]
            relative[valid] = np.abs(forward_scaled - reverse_scaled) / (
                np.abs(forward_scaled) + np.abs(reverse_scaled))
            edge_max_relative = float(relative.max(initial=0.0))
            unresolved_edges = int(np.count_nonzero(
                ~valid | (relative > DETAILED_BALANCE_TOLERANCE)))
        entry.update(edge_count=edge_count,
                     edge_max_relative_defect=edge_max_relative,
                     edge_tolerance=DETAILED_BALANCE_TOLERANCE)
        if (not np.isfinite(left).all() or not np.isfinite(residual) or
                residual > DETAILED_BALANCE_TOLERANCE or
                left.min() <= 0 or unresolved_edges):
            entry['compatibility'] = 'UNRESOLVED_LEFT_NULLSPACE'
            entry['transpose_residual'] = (float(residual)
                                           if np.isfinite(residual) else None)
            if missing_reverse:
                entry['unresolved_reason'] = 'MISSING_REVERSE_EDGE'
            elif unresolved_edges:
                entry['unresolved_reason'] = 'DETAILED_BALANCE_EDGE'
            continue
        left /= left.sum()
        defect = float(left @ force)
        rounding = float(64 * np.finfo(float).eps * (np.abs(left) @ np.abs(force)))
        left_norm2 = float(np.linalg.norm(left, ord=2))
        rhs_norm2 = float(np.linalg.norm(force, ord=2))
        rhs_norm_inf = float(np.linalg.norm(force, ord=np.inf))
        obstruction_inf = float(abs(defect) / np.sum(np.abs(left)))
        obstruction_2 = float(abs(defect) / left_norm2)
        entry.update(left_rhs=defect, arithmetic_bound=rounding,
                     transpose_residual=residual,
                     transpose_residual_l1=float(np.sum(np.abs(block.T @ left))),
                     left_norm2=left_norm2,
                     rhs_norm2=rhs_norm2,
                     rhs_norm_inf=rhs_norm_inf,
                     obstruction_inf=obstruction_inf,
                     obstruction_2=obstruction_2,
                     fixed_tolerance=RESIDUAL_TOLERANCE,
                     fixed_tolerance_infeasible=bool(obstruction_inf > RESIDUAL_TOLERANCE),
                     relative_defect=abs(defect) / max(float(np.max(np.abs(force))),
                                                     np.finfo(float).tiny),
                     obstruction_interpretation=(
                         'conditional_diagnostic; not a rigorous lower bound'),
                     compatibility='COMPATIBLE_TO_ARITHMETIC' if abs(defect) <= rounding
                     else 'INCOMPATIBLE')
    return {'source': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
            'shape': [nx, ny, nz], 'active_rows': count,
            'components': components, 'rhs_modified': False,
            'scope': 'Discrete production rows only; no accepted after-state or forecast claim',
            'diagnostic_note': (
                'The edge test requires a numerically validated, sum-normalized '
                'detailed-balance certificate. Obstruction values are conditional '
                'diagnostics from that certificate, not rigorous lower bounds or '
                'interval bounds. The fixed 1e-10 tolerance is diagnostic only; '
                'the positive diagonal ratio is coefficient contrast, not a '
                'condition number. No independent left-null solve is used to '
                'accept a nonreversible component. For approximate z, subtract '
                '||A^T z||1 * ||lambda||inf from |z^T b| (floored at zero) '
                'before dividing by ||z||1 for an infinity residual bound.')}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rows', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = diagnose(args.rows)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    counts = {}
    for entry in result['components']:
        key = entry['compatibility']
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({'active_rows': result['active_rows'], 'components': counts}))


if __name__ == '__main__':
    main()
