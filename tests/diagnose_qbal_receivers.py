#!/usr/bin/env python3
"""Read-only receiver audit for a hypothetical pure-support omega candidate.

This computes necessary conservation bounds, not physical authority or joint
bounded feasibility. Production Fortran and the supplied RHS remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

import diagnose_qbal_boundary as boundary


def divergence(snapshot, fields, ijk):
    """The six production donors, with subtraction and division in real64."""
    i, j, k = (ijk - 1).T
    u, v, w = (np.asarray(field, dtype=np.float64) for field in fields)
    return ((u[i, j-1, k-1] - u[i-1, j-1, k-1]) / snapshot.dx[i, j].astype(float)
            + (v[i-1, j, k-1] - v[i-1, j-1, k-1]) / snapshot.dy[i, j].astype(float)
            + (w[i, j, k-1] - w[i, j, k]) / snapshot.dp[k].astype(float))


def weights(snapshot, ijk):
    i, j, k = (ijk - 1).T
    return snapshot.dx[i, j].astype(float) * snapshot.dp[k].astype(float)


def weighted_sum(values, weight):
    return math.fsum(values * weight)


def statistics(values, weight):
    return {"max_abs": float(np.max(np.abs(values), initial=0.)),
            "rms": float(np.sqrt(np.mean(values**2))) if len(values) else 0.,
            "weighted_sum": weighted_sum(values, weight)}


def necessary_bounds(demand, before_sum, weight_sum):
    """Exact active target only. Passing these bounds is not sufficient."""
    if weight_sum <= 0:
        return {"active_defect": demand, "receiver_before_sum": before_sum,
                "receiver_weight_sum": weight_sum, "required_final_sum": before_sum-demand,
                "delta_inf_lower_bound": None, "final_inf_lower_bound": None,
                "missing_receiver_for_nonzero_demand": demand != 0.}
    return {"active_defect": demand, "receiver_before_sum": before_sum,
            "receiver_weight_sum": weight_sum, "required_final_sum": before_sum-demand,
            "delta_inf_lower_bound": abs(demand)/weight_sum,
            "final_inf_lower_bound": abs(before_sum-demand)/weight_sum,
            "missing_receiver_for_nonzero_demand": False}


def receiver_inventory(snapshot, rows):
    """Reconstruct controls from geometry; never trust a supplied face mask."""
    if rows.dimensions != snapshot.dimensions or not len(rows.ijk):
        raise ValueError("empty or mismatched row geometry")
    if not np.array_equal(snapshot.dx, snapshot.dy):
        raise ValueError("only the certified dx=dy metric is supported")
    if not np.array_equal(boundary._stored_active_mask(rows),
                          boundary._expected_active_mask(snapshot)):
        raise ValueError("exported active rows differ from snapshot support")
    neighbors = boundary._neighbor_indices(rows)
    source, direction = np.where(rows.coefficients > 0.)
    if np.any(neighbors[source, direction] < 0):
        raise ValueError("positive edge has no active neighbor")
    reverse = rows.coefficients[neighbors[source, direction], boundary.OPPOSITE[direction]]
    if np.any(reverse <= 0.):
        raise ValueError("positive edge has no reverse edge")
    graph = coo_matrix((np.ones(len(source)), (source, neighbors[source, direction])),
                       shape=(len(rows.ijk), len(rows.ijk)))
    _, labels = connected_components(graph, directed=False)
    sources, directions, receivers = [], [], []
    for direction in (4, 5):
        neighbor = rows.ijk + boundary.SHIFTS[direction]
        inside = np.all((neighbor >= 2) & (neighbor <= rows.dimensions), axis=1)
        ids = np.flatnonzero(inside & (neighbors[:, direction] < 0))
        i, j, k = (neighbor[ids] - 1).T
        valid = (snapshot.beta[i, j, k] == 0.) & (snapshot.ps[i, j] >= snapshot.p[k])
        for field, offset in ((snapshot.u, (0,-1,-1)), (snapshot.u, (-1,-1,-1)),
                              (snapshot.v, (-1,0,-1)), (snapshot.v, (-1,-1,-1)),
                              (snapshot.w, (0,0,0)), (snapshot.w, (0,0,-1))):
            donor = field[i+offset[0], j+offset[1], k+offset[2]]
            valid &= np.isfinite(donor) & (donor != boundary.SENTINEL)
        ids = ids[valid]
        sources.extend(ids)
        directions.extend([direction]*len(ids))
        receivers.extend(neighbor[ids])
    source = np.asarray(sources, dtype=np.int64)
    direction = np.asarray(directions, dtype=np.int32)
    face_receiver = np.asarray(receivers, dtype=np.int32).reshape(-1, 3)
    receiver, receiver_index = np.unique(face_receiver, axis=0, return_inverse=True)
    stored = rows.ijk[source].copy()
    stored[:, 2] -= direction == 5
    if len(np.unique(stored, axis=0)) != len(stored):
        raise ValueError('duplicate hypothetical support face')
    return neighbors, labels, source, direction, stored, receiver, receiver_index


def coupled_groups(labels, source, receiver_index, receiver_count):
    """A receiver is one node, even when several active components use it."""
    count = int(labels.max()) + 1
    graph = coo_matrix((np.ones(len(source)), (labels[source], count+receiver_index)),
                       shape=(count+receiver_count, count+receiver_count))
    _, groups = connected_components(graph, directed=False)
    return groups[:count][labels], groups[count:]


def validate_candidate(snapshot, rows, candidate, stored):
    masks = [np.zeros(snapshot.dimensions, dtype=bool) for _ in range(3)]
    i, j, k = (rows.ijk-1).T
    for axis, direction in enumerate((0, 2, 4)):
        ids = np.flatnonzero(rows.coefficients[:, direction] > 0.)
        coordinates = ((i[ids], j[ids]-1, k[ids]-1) if axis == 0 else
                       (i[ids]-1, j[ids], k[ids]-1) if axis == 1 else
                       (i[ids], j[ids], k[ids]))
        masks[axis][coordinates] = True
    masks[2][tuple((stored-1).T)] = True
    counts = []
    for old, new, mask in zip((snapshot.u, snapshot.v, snapshot.w), candidate, masks):
        if new.shape != snapshot.dimensions or new.dtype.kind != 'f' or new.dtype.itemsize != 4:
            raise ValueError("candidate must contain stored float32 fields of matching shape")
        if not np.isfinite(new).all():
            raise ValueError("nonfinite candidate")
        if not np.array_equal(old == boundary.SENTINEL, new == boundary.SENTINEL):
            raise ValueError("candidate changes sentinel mask")
        changed = old.astype('=f4').view('=u4') != new.astype('=f4').view('=u4')
        if np.any(changed & ~mask):
            raise ValueError("candidate changes a face outside the hypothetical set")
        counts.append(int(np.count_nonzero(changed)))
    return masks, counts


def audit(snapshot, rows, candidate):
    neighbors, labels, source, direction, stored, receiver, receiver_index = receiver_inventory(snapshot, rows)
    masks, changed_counts = validate_candidate(snapshot, rows, candidate, stored)
    initial = (snapshot.u, snapshot.v, snapshot.w)
    active_before = divergence(snapshot, initial, rows.ijk)
    z_p = weights(snapshot, rows.ijk)
    scale = np.sum(np.abs(boundary._signed_terms(snapshot, rows)), axis=1) / z_p
    if np.any(np.abs(active_before+rows.rhs) > 32*np.finfo(float).eps*np.maximum(scale, 1.e-30)):
        raise ValueError("RHS does not reconstruct the original divergence")
    active_after = divergence(snapshot, candidate, rows.ijk)
    before = divergence(snapshot, initial, receiver)
    after = divergence(snapshot, candidate, receiver)
    delta = after-before
    z_r = weights(snapshot, receiver)
    p_group, r_group = coupled_groups(labels, source, receiver_index, len(receiver))
    groups = []
    for group in np.unique(p_group):
        p, r = p_group == group, r_group == group
        result = necessary_bounds(weighted_sum(rows.rhs[p], z_p[p]),
                                  weighted_sum(before[r], z_r[r]), math.fsum(z_r[r]))
        result.update(active_rows=int(p.sum()), receiver_rows=int(r.sum()),
                      components=np.unique(labels[p]).tolist())
        groups.append(result)
    global_bound = necessary_bounds(weighted_sum(rows.rhs, z_p), weighted_sum(before, z_r), math.fsum(z_r))
    active_change = weighted_sum(active_after-active_before, z_p)
    receiver_change = weighted_sum(delta, z_r)
    closure = active_change+receiver_change
    # Arithmetic audit only, not a physical tolerance. Sum absolute terms to
    # avoid hiding cancellation error behind the small signed total.
    roundoff = 256*np.finfo(float).eps*(weighted_sum(np.abs(active_after)+np.abs(active_before), z_p)
                                     + weighted_sum(np.abs(after)+np.abs(before), z_r))
    if abs(closure) > roundoff:
        raise ValueError("active/receiver shared-face budget does not close")
    summary = {
        "scope": "DIAGNOSED_SCOPED; hypothetical face set, no production authority or sufficient feasibility",
        "metric": "z=h*dp; discrete cancellation weight, not native mass or kg/s",
        "active_rows": len(rows.ijk), "receiver_rows": len(receiver), "support_omega_faces": len(source),
        "changed_faces_uvomega": changed_counts,
        "receiver_changed": int(np.count_nonzero(delta)),
        "improved_abs": int(np.count_nonzero(np.abs(after) < np.abs(before))),
        "worsened_abs": int(np.count_nonzero(np.abs(after) > np.abs(before))),
        "unchanged_abs": int(np.count_nonzero(np.abs(after) == np.abs(before))),
        "before": statistics(before, z_r), "delta": statistics(delta, z_r), "after": statistics(after, z_r),
        "active_after": statistics(active_after, z_p),
        "active_weighted_change": active_change, "receiver_weighted_change": receiver_change,
        "shared_face_closure": closure, "closure_arithmetic_bound": roundoff,
        "exact_active_target_bounds": global_bound, "coupled_groups": groups,
        "interval_condition": "sum(z_R*lower) <= B-d <= sum(z_R*upper); necessary only",
        "nonzero_active_residual": "replace B-d by B-d-z_P^T e_P; this is not a physical tolerance",
    }
    payload = dict(receiver_ijk=receiver, receiver_before=before, receiver_delta=delta,
                   receiver_after=after, receiver_weight=z_r, receiver_group=r_group,
                   active_ijk=rows.ijk, active_component=labels, active_group=p_group,
                   active_after=active_after, face_active_index=source, face_direction=direction,
                   face_stored_ijk=stored, face_receiver_index=receiver_index,
                   hypothetical_u_mask=masks[0], hypothetical_v_mask=masks[1], hypothetical_w_mask=masks[2])
    return summary, payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot', 'rows', 'candidate', 'output', 'arrays'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.arrays.suffix != '.npz' or args.arrays.resolve() == args.output.resolve():
        raise ValueError('arrays must use a distinct .npz output path')
    snapshot = boundary.read_snapshot(args.snapshot)
    rows = boundary.read_sparse_rows(args.rows)
    with np.load(args.candidate, allow_pickle=False) as archive:
        candidate = tuple(archive[key] for key in ('stored_u', 'stored_v', 'stored_w'))
    summary, arrays = audit(snapshot, rows, candidate)
    summary['inputs_sha256'] = {name: hashlib.sha256(getattr(args, name).read_bytes()).hexdigest()
                               for name in ('snapshot', 'rows', 'candidate')}
    for path in (args.output, args.arrays):
        if path.exists():
            raise ValueError(f'refuse to overwrite diagnostic output: {path}')
        path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.arrays, **arrays)
    summary['arrays_sha256'] = hashlib.sha256(args.arrays.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    print(f'DIAGNOSED_SCOPED: {len(rows.ijk)} active, {len(arrays["receiver_ijk"])} receivers')


if __name__ == '__main__':
    main()
