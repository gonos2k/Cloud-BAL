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
from scipy.sparse.linalg import spsolve


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
        components.append(entry)
        if entry['anchored']:
            entry['compatibility'] = 'ANCHORED_NO_CONSTANT_RIGHT_NULLSPACE'
            continue
        force = rhs[selected]
        if len(selected) == 1:
            left = np.ones(1)
            residual = 0.0
        else:
            block = matrix[selected][:, selected]
            scale = np.max(np.abs(block.data))
            # A spanning-tree candidate is cheap even for the actual 3-D
            # component. Its full transpose residual is the certificate;
            # a tree alone is never evidence of compatibility.
            order, parent = breadth_first_order(block, 0, directed=False)
            child = order[1:]
            ratio = np.asarray(block[parent[child], child]).ravel() / np.asarray(
                block[child, parent[child]]).ravel()
            left = np.ones(len(selected))
            for node, edge_ratio in zip(child, ratio):
                left[node] = left[parent[node]] * edge_ratio
            left /= left.sum()
            residual = float(np.sum(np.abs(block.T @ left)) /
                             np.sum(abs(block).T @ np.abs(left)))
            if residual > 1e-12 and len(selected) <= 10000:
                # General nonreversible small blocks: solve an independently
                # assembled sparse transposed system with normalization.
                system = (block.T / scale).tolil()
                system[-1, :] = np.ones(len(selected))
                forcing = np.zeros(len(selected))
                forcing[-1] = 1
                left = spsolve(system.tocsc(), forcing)
                residual = float(np.sum(np.abs(block.T @ left)) /
                             np.sum(abs(block).T @ np.abs(left)))
        if not np.isfinite(left).all() or residual > 1e-12 or left.min() < -1e-12:
            entry['compatibility'] = 'UNRESOLVED_LEFT_NULLSPACE'
            entry['transpose_residual'] = residual
            continue
        left /= left.sum()
        defect = float(left @ force)
        rounding = float(64 * np.finfo(float).eps * (np.abs(left) @ np.abs(force)))
        entry.update(left_rhs=defect, arithmetic_bound=rounding,
                     transpose_residual=residual,
                     relative_defect=abs(defect) / max(float(np.max(np.abs(force))),
                                                     np.finfo(float).tiny),
                     compatibility='COMPATIBLE_TO_ARITHMETIC' if abs(defect) <= rounding
                     else 'INCOMPATIBLE')
    return {'source': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
            'shape': [nx, ny, nz], 'active_rows': count,
            'components': components, 'rhs_modified': False,
            'scope': 'Discrete production rows only; no accepted after-state or forecast claim'}


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
