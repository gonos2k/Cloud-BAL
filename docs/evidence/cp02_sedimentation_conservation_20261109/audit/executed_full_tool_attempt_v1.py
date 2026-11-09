#!/usr/bin/env python3
"""Replay CP05 sedimentation substeps and audit their native column budgets."""
from __future__ import annotations
import argparse
import csv
import gzip
import json
import tempfile
from collections import defaultdict
from pathlib import Path
import numpy as np
import cp02_protected_process_capture as cap

F = np.float32
SPECIES = (("rain", 5, 17, 22, True), ("snow", 6, 18, 23, True),
           ("graupel", 7, 19, 24, True), ("rain_number", 8, 20, 25, False))
STEPS = tuple(range(1, 361)) + tuple(range(721, 901))
LAUNCH_SHA = "41a1d6e8dd2b0821dc03bdc6927465513c31e877981497eb795ad349284201e5"
CAPTURE_SHA = {"OLD": "3778e4db7e661eb3f502235a9f5328e7b90254a80a11bd0ec0f93ed210510cd9",
               "FIX": "9d852d396c037d633b1c000c94170516ed290eb7a56592335c1f3df423294914"}


def replay(pre, post, state, fall, flux, mass):
    """Evaluate the exact source order using recorded fluxes and updated upper states."""
    q = pre[:, state]
    rho = pre[:, 10] if mass else np.ones(len(pre), dtype=np.float32)
    dz, dt = pre[:, 11], pre[:, 12]
    f = post[:, flux]
    if (np.any(q < 0) or np.any(rho <= 0) or np.any(dz <= 0) or
            np.any(dt <= 0) or np.any(f < 0) or not np.isfinite(pre).all() or not np.isfinite(post).all()):
        raise ValueError("invalid sedimentation state, geometry, or flux")
    out = np.minimum(F(f * dt) / rho, q)
    incoming_raw = F(F(F(f[1:] * dz[1:]) / dz[:-1]) * dt[:-1]) / rho[:-1]
    incoming = np.minimum(incoming_raw, post[1:, state])
    expected = np.maximum(F(F(q[:-1] - out[:-1]) + incoming), F(0))
    top = np.maximum(F(q[-1] - F(F(f[-1] * dt[-1]) / rho[-1])), F(0))
    expected = np.append(expected, top).astype(np.float32)
    if not np.array_equal(expected.view(np.uint32), post[:, state].view(np.uint32)):
        bad = np.flatnonzero(expected.view(np.uint32) != post[:, state].view(np.uint32))
        raise ValueError(f"POST replay mismatch at levels {(bad + 1).tolist()[:8]}; expected {expected[bad[0]]}, got {post[bad[0], state]}")
    if not np.array_equal(F(pre[:, fall] + f).view(np.uint32), post[:, fall].view(np.uint32)):
        raise ValueError("fall accumulation mismatch")
    # The source limits each receipt by the upper POST state, in the receiver's units.
    removal = out[1:].astype(np.float64) * rho[1:].astype(np.float64) * dz[1:].astype(np.float64)
    receipt = incoming.astype(np.float64) * rho[:-1].astype(np.float64) * dz[:-1].astype(np.float64)
    stored = np.sum((post[:, state].astype(np.float64) - q.astype(np.float64)) * rho.astype(np.float64) * dz.astype(np.float64))
    boundary = float(F(F(post[0, fall] - pre[0, fall]) * dz[0]) * dt[0])
    nominal_boundary = float(f[0]) * float(dz[0]) * float(dt[0])
    gap = removal - receipt
    actual_bottom = float(out[0]) * float(rho[0]) * float(dz[0])
    rounding = stored + actual_bottom + float(np.sum(gap))
    scale = float(np.sum((np.abs(q.astype(np.float64)) + np.abs(post[:, state].astype(np.float64))) * rho.astype(np.float64) * dz.astype(np.float64))) + abs(actual_bottom) + float(np.sum(np.abs(gap)))
    tolerance = 32 * np.finfo(np.float32).eps * scale + 1e-30
    if abs(rounding) > tolerance:
        raise ValueError(f"column storage rounding exceeds tolerance: {rounding} > {tolerance}")
    return incoming_raw, incoming, removal, receipt, stored, boundary, nominal_boundary, gap, rounding


def audit_frame(frame, records, cohort, inventory, writer, events, totals, only=None):
    selected = cap._frame_selected_cells(frame, cohort.cells)
    ci = {cell: ix for ix, cell in enumerate(cohort.cells)}
    pairs = defaultdict(dict)
    for r in records:
        if r.phase not in (9, 10):
            continue
        cell = (r.i, frame.j)
        if cell not in ci or cell not in selected:
            raise ValueError("unselected sedimentation record")
        owner = (frame.timestep - 1, r.k - 1, ci[cell])
        if (inventory.owners_rank[owner], inventory.owners_call[owner]) != (frame.rank, frame.call_id):
            raise ValueError("sedimentation record owner mismatch")
        key = (r.i, r.substep, r.k, r.phase)
        if key in pairs:
            raise ValueError("duplicate sedimentation record")
        pairs[key] = (r.mstep, r.values)
    for i, j in selected:
        if only is not None and (i, j) not in only:
            continue
        keys = [key for key in pairs if key[0] == i]
        msteps = {pairs[key][0] for key in keys}
        if len(msteps) != 1:
            raise ValueError("missing or inconsistent mstep")
        mstep = msteps.pop()
        if set(keys) != {(i, n, k, phase) for n in range(1, mstep + 1) for k in range(1, 40) for phase in (9, 10)}:
            raise ValueError("incomplete sedimentation PRE/POST/level/substep coverage")
        for n in range(1, mstep + 1):
            pre = np.stack([pairs[i, n, k, 9][1] for k in range(1, 40)])
            post = np.stack([pairs[i, n, k, 10][1] for k in range(1, 40)])
            if not np.array_equal(pre[:, [10, 11, 12]], post[:, [10, 11, 12]]):
                raise ValueError("geometry changed inside sedimentation substep")
            for name, state, fall, flux, mass in SPECIES:
                raw, incoming, removal, receipt, stored, boundary, nominal, gap, rounding = replay(pre, post, state, fall, flux, mass)
                firing = raw > post[1:, state]
                unit = "kg_m-2" if mass else "number_m-2"
                writer.writerow((frame.timestep, frame.rank, frame.call_id, i, j, n, mstep, name, unit, int(firing.sum()), float(gap.sum()), stored, boundary, nominal, rounding))
                for k in np.flatnonzero(firing):
                    events.writerow((frame.timestep, frame.rank, frame.call_id, i, j, n, name, int(k + 2), float(raw[k]), float(post[k + 1, state]), float(removal[k]), float(receipt[k]), float(gap[k])))
                agg = totals[name]
                agg["substeps"] += 1
                agg["limiter_events"] += int(firing.sum())
                for label, value in (("transfer_gap", gap.sum()), ("column_change", stored), ("ground_fall_increment", boundary), ("rounding_residual", rounding)):
                    agg[label] += float(value)
                agg["max_abs_rounding_residual"] = max(agg["max_abs_rounding_residual"], abs(rounding))


def _run(case, arm, launch, output):
    schema, cohort, _ = cap.load_contract()
    contract = cap.load_mode_contract("full", launch, LAUNCH_SHA)
    files = cap.validate_case_file_inventory(case, contract)
    inventory = cap.read_call_inventory(files["calls"], cohort.cells, steps=900, expected_ranks=contract.ranks)
    files = cap.validate_case_file_inventory(case, contract, inventory)
    receipt_path = cap.EVIDENCE / "native/compact" / arm / "capture_receipt.json"
    if cap.sha256(receipt_path) != CAPTURE_SHA[arm]:
        raise ValueError("prior capture receipt SHA mismatch")
    receipt = json.loads(receipt_path.read_text())
    raw = {Path(row["path"]).name: row for row in receipt["raw_stream_files"]}
    actual = {p.name: p for paths in files.values() for p in paths}
    if set(raw) != set(actual):
        raise ValueError("raw inventory filenames differ")
    for name, p in actual.items():
        if p.stat().st_size != raw[name]["size_bytes"] or cap.sha256(p) != raw[name]["sha256"]:
            raise ValueError(f"raw inventory mismatch: {name}")
    expected = cap._expected_frame_keys(inventory, cohort.cells, STEPS)
    seen = set()
    counts = {int(p): len(x["fields"]) for p, x in schema["phases"].items()}
    totals = defaultdict(lambda: defaultdict(float))
    output.mkdir(parents=True, exist_ok=True)
    with gzip.open(output / f"{arm}_substeps.csv.gz", "wt", newline="") as sub, gzip.open(output / f"{arm}_events.csv.gz", "wt", newline="") as ev:
        writer, events = csv.writer(sub), csv.writer(ev)
        writer.writerow(("step", "rank", "call", "i", "j", "substep", "mstep", "species", "unit", "limiter_events", "transfer_gap", "column_change", "ground_fall_increment", "nominal_ground_flux", "rounding_residual"))
        events.writerow(("step", "rank", "call", "i", "j", "substep", "species", "upper_level", "incoming_raw", "upper_post", "upper_removal", "lower_receipt", "gap"))
        for p in files["process"]:
            rank = cap.parse_chunk_filename(p, "cp04")[2]
            for frame, records in cap.iter_process_frames(p, counts, rank):
                key = (frame.timestep, rank, frame.call_id, frame.j, frame.its, frame.ite, frame.kts, frame.kte)
                if key not in expected or key in seen:
                    raise ValueError("unexpected or duplicate process frame")
                seen.add(key)
                audit_frame(frame, records, cohort, inventory, writer, events, totals)
    if seen != expected:
        raise ValueError(f"missing process frames: {len(expected-seen)}")
    (output / f"{arm}_summary.json").write_text(json.dumps({"arm": arm, "frames": len(seen), "raw_files_hashed": len(raw), "species": totals}, indent=2) + "\n")


def summarize_roles(substeps, cohort, destination):
    """Aggregate each role's unique native columns; roles may overlap each other."""
    membership = defaultdict(set)
    points_by_cell = defaultdict(list)
    for pi, point in enumerate(cohort.point_ids):
        roles = set(cohort.role_rows.get(point, []))
        for ci, weight in zip(cohort.point_cells[pi], cohort.point_weights[pi]):
            cell = cohort.cells[int(ci)]
            membership[cell].update(roles)
            points_by_cell[cell].append((point, float(weight), roles))
    groups = defaultdict(lambda: defaultdict(float))
    with gzip.open(substeps, "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            cell = (int(row["i"]), int(row["j"]))
            step = int(row["step"])
            labels = {"all_unique_columns"} | membership[cell]
            if step >= 721:
                labels |= {"h5/" + label for label in labels}
            if cell in {(140, 79), (141, 79), (140, 80), (141, 80)} and 330 <= step <= 360:
                labels.add("P01_final_31_calls_four_unique_columns")
            weighted_labels = [(label, 1.0) for label in labels]
            for point, weight, roles in points_by_cell[cell]:
                point_labels = {"point/" + point} | {"role_point_sum/" + role for role in roles}
                if step >= 721:
                    point_labels |= {"h5/" + label for label in point_labels}
                weighted_labels.extend((label, weight) for label in point_labels)
            for label, weight in weighted_labels:
                target = groups[(label, row["species"], row["unit"])]
                target["substeps"] += weight
                for field in ("limiter_events", "transfer_gap", "column_change", "ground_fall_increment", "nominal_ground_flux", "rounding_residual"):
                    target[field] += weight * float(row[field])
                bottom = float(row["rounding_residual"]) - float(row["column_change"]) - float(row["transfer_gap"])
                target["actual_bottom_removal"] += weight * bottom
                target["ground_boundary_minus_bottom"] += weight * (float(row["ground_fall_increment"]) - bottom)
    fields = ("substeps", "limiter_events", "transfer_gap", "column_change", "ground_fall_increment", "nominal_ground_flux", "rounding_residual", "actual_bottom_removal", "ground_boundary_minus_bottom")
    with destination.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("group", "species", "unit", *fields))
        for (label, species, unit), values in sorted(groups.items()):
            writer.writerow((label, species, unit, *(values[field] for field in fields)))


def run(case, arm, launch, output):
    """Publish a complete arm atomically; retain any existing result on failure."""
    output.mkdir(parents=True, exist_ok=True)
    final = output / arm
    if final.exists() or final.is_symlink():
        raise FileExistsError(f"audit output already exists: {final}")
    with tempfile.TemporaryDirectory(prefix=f".{arm}-", dir=output) as temporary:
        stage = Path(temporary)
        _run(case, arm, launch, stage)
        _, cohort, _ = cap.load_contract()
        summarize_roles(stage / f"{arm}_substeps.csv.gz", cohort, stage / f"{arm}_roles.csv")
        if final.exists() or final.is_symlink():
            raise FileExistsError(f"audit output already exists: {final}")
        stage.rename(final)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--arm", choices=("OLD", "FIX"), required=True)
    parser.add_argument("--launch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    run(a.case, a.arm, a.launch, a.output)

if __name__ == "__main__":
    main()
