#!/usr/bin/env python3
"""Replay PR63 native stage masks against the public KDM6 call capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np

from native_kdm6_trace import read_dump


MASK_MAGIC = b"PR63MSK1"
MASK_HEADER_BYTES = 8 + 32 + 14 * 4 + 4


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_masks(path: Path) -> list[dict]:
    data = path.read_bytes()
    offset = 0
    records = []
    while offset < len(data):
        if len(data) - offset < MASK_HEADER_BYTES:
            raise ValueError(f"truncated mask header at byte {offset}")
        if data[offset:offset + 8] != MASK_MAGIC:
            raise ValueError(f"bad mask magic at byte {offset}")
        offset += 8
        try:
            stage = data[offset:offset + 32].decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise ValueError(f"invalid stage name at byte {offset}") from exc
        offset += 32
        values = struct.unpack_from(">14i", data, offset)
        offset += 14 * 4
        qmin = struct.unpack_from(">f", data, offset)[0]
        offset += 4
        if not math.isfinite(qmin) or qmin <= 0:
            raise ValueError(f"invalid runtime qmin in {stage}: {qmin}")
        timestep, rkstep = values[:2]
        bounds = dict(zip(
            ("ims", "ime", "jms", "jme", "kms", "kme",
             "its", "ite", "jts", "jte", "kts", "kte"),
            values[2:], strict=True))
        for axis in ("i", "j", "k"):
            if bounds[f"ims"] > bounds[f"ime"] or bounds[f"jms"] > bounds[f"jme"] or bounds[f"kms"] > bounds[f"kme"]:
                raise ValueError("invalid memory bounds")
            if bounds[f"{axis}ts"] > bounds[f"{axis}te"]:
                raise ValueError(f"inverted tile {axis} bounds")
            if (bounds[f"{axis}ts"] < bounds[f"{axis}ms"] or
                    bounds[f"{axis}te"] > bounds[f"{axis}me"]):
                raise ValueError(f"tile {axis} bounds outside memory bounds")
        shape_ijk = (bounds["ite"] - bounds["its"] + 1,
                     bounds["kte"] - bounds["kts"] + 1,
                     bounds["jte"] - bounds["jts"] + 1)
        if min(shape_ijk) <= 0:
            raise ValueError(f"invalid mask shape in {stage}: {shape_ijk}")
        count = math.prod(shape_ijk)
        nbytes = count * 4
        if offset + nbytes > len(data):
            raise ValueError(f"truncated mask values in {stage}")
        values = np.frombuffer(data, dtype=">i4", count=count, offset=offset)
        if np.any(values < 0) or np.any(values & ~7):
            raise ValueError(f"mask contains unsupported bits in {stage}")
        # Fortran writes mask(i,k,j), with i as the fastest varying index.
        mask = values.reshape((shape_ijk[2], shape_ijk[1], shape_ijk[0])).copy()
        offset += nbytes
        records.append({"stage": stage, "timestep": timestep, "rkstep": rkstep,
                        "qmin": float(qmin), "bounds": bounds, "mask": mask})
    expected = ["PRE_RK", "RK_STAGE_END", "RK_STAGE_END", "RK_STAGE_END",
                "PRE_MOIST_PREP", "POST_MOIST_PREP", "PRE_MICROPHYSICS",
                "POST_MICROPHYSICS"]
    expected_rk = [0, 1, 2, 3, 4, 4, 4, 4]
    if [record["stage"] for record in records] != expected:
        raise ValueError("unexpected, duplicate, or missing transition-stage records")
    if [record["rkstep"] for record in records] != expected_rk:
        raise ValueError("unexpected RK-stage indices")
    reference = records[0]
    if any(record["timestep"] != reference["timestep"] or
           record["bounds"] != reference["bounds"] or
           record["qmin"] != reference["qmin"] for record in records[1:]):
        raise ValueError("transition-stage headers are inconsistent")
    return records


def overlap_slices(a: dict, b: dict) -> tuple[tuple[slice, ...], tuple[slice, ...]]:
    """Return `(j,k,i)` slices over the exact global-coordinate intersection."""
    ab, bb = a["bounds"], b["bounds"]
    common = {}
    for axis in ("i", "j", "k"):
        lo = max(ab[f"{axis}ts"], bb[f"{axis}ts"])
        hi = min(ab[f"{axis}te"], bb[f"{axis}te"])
        if lo > hi:
            raise ValueError(f"mask and KDM6 trace do not overlap on {axis}")
        common[axis] = (lo, hi)
    def slices(bounds: dict) -> tuple[slice, ...]:
        return tuple(slice(common[axis][0] - bounds[f"{axis}ts"],
                           common[axis][1] - bounds[f"{axis}ts"] + 1)
                     for axis in ("j", "k", "i"))
    return slices(ab), slices(bb)


def summarize(mask_path: Path, pre_path: Path, post_path: Path) -> dict:
    masks = read_masks(mask_path)
    pre, post = read_dump(pre_path), read_dump(post_path)
    if pre["stage"] != 1 or post["stage"] != 2:
        raise ValueError("KDM6 trace stages must be pre=1 and post=2")
    if pre["bounds"] != post["bounds"] or pre["params"] != post["params"]:
        raise ValueError("KDM6 pre/post headers differ")
    if pre["itimestep"] <= 0 or post["itimestep"] != pre["itimestep"]:
        raise ValueError("KDM6 pre/post timesteps differ or are not positive")
    last = masks[-1]
    if last["timestep"] != pre["itimestep"] or post["itimestep"] != last["timestep"]:
        raise ValueError("transition and KDM6 call timesteps differ")
    for axis in ("i", "j", "k"):
        if (last["bounds"][f"{axis}ts"] > post["bounds"][f"{axis}ts"] or
                last["bounds"][f"{axis}te"] < post["bounds"][f"{axis}te"]):
            raise ValueError(f"KDM6 active {axis} window is not fully covered by host mask")
    mask_sl, trace_sl = overlap_slices(last, post)
    selected = last["mask"][mask_sl]
    pre_q, pre_n = pre["fields"]["QC"], pre["fields"]["NC"]
    q = post["fields"]["QC"][trace_sl]
    n = post["fields"]["NC"][trace_sl]
    qg = post["fields"]["QG"][trace_sl]
    bg = post["fields"]["BG"][trace_sl]
    pre_qg = pre["fields"]["QG"]
    pre_bg = pre["fields"]["BG"]
    eps = last["qmin"]
    counts = {
        "mask_full_tile": {"gap": int((last["mask"] & 1 != 0).sum()),
                           "negative_qc": int((last["mask"] & 2 != 0).sum()),
                           "qg_zero_bg_positive": int((last["mask"] & 4 != 0).sum())},
        "mask_kdm6_intersection": {"gap": int((selected & 1 != 0).sum()),
                                   "negative_qc": int((selected & 2 != 0).sum()),
                                   "qg_zero_bg_positive": int((selected & 4 != 0).sum())},
        "kdm6_return": {
            "nonfinite_qc_nc_qg_bg": int(sum(
                (~np.isfinite(values)).sum() for values in (q, n, qg, bg))),
            "qc_gt_zero_nc_zero": int(((q > 0) & (n == 0)).sum()),
            "qc_gt_runtime_epsilon_nc_zero": int(((q > eps) & (n == 0)).sum()),
            "qc_gt_1e-9_nc_zero": int(((q > 1e-9) & (n == 0)).sum()),
            "negative_qc": int((q < 0).sum()),
            "qg_zero_bg_positive": int(((qg == 0) & (bg > 0)).sum()),
        },
        "kdm6_entry": {
            "nonfinite_qc_nc_qg_bg": int(sum(
                (~np.isfinite(values)).sum() for values in
                (pre_q, pre_n, pre_qg, pre_bg))),
            "qc_gt_zero_nc_zero": int(((pre_q > 0) & (pre_n == 0)).sum()),
            "qc_gt_runtime_epsilon_nc_zero": int(((pre_q > eps) & (pre_n == 0)).sum()),
            "qc_gt_1e-9_nc_zero": int(((pre_q > 1e-9) & (pre_n == 0)).sum()),
            "negative_qc": int((pre_q < 0).sum()),
        },
        "mask_vs_kdm6": {
            "gap_predicate_mismatches": int(np.count_nonzero(
                (selected & 1 != 0) != ((q > eps) & (n == 0)))),
            "negative_predicate_mismatches": int(np.count_nonzero(
                (selected & 2 != 0) != (q < 0))),
            "graupel_volume_predicate_mismatches": int(np.count_nonzero(
                (selected & 4 != 0) != ((qg == 0) & (bg > 0)))),
        },
        "exact_global_overlap": {
            "i": [max(last["bounds"]["its"], post["bounds"]["its"]),
                  min(last["bounds"]["ite"], post["bounds"]["ite"])],
            "j": [max(last["bounds"]["jts"], post["bounds"]["jts"]),
                  min(last["bounds"]["jte"], post["bounds"]["jte"])],
            "k": [max(last["bounds"]["kts"], post["bounds"]["kts"]),
                  min(last["bounds"]["kte"], post["bounds"]["kte"])],
            "runtime_epsilon": eps,
        },
        "sha256": {"masks": sha256(mask_path), "pre": sha256(pre_path),
                   "post": sha256(post_path)},
        "stage_masks_full_tile": [
            {"stage": record["stage"], "rkstep": record["rkstep"],
             "gap": int((record["mask"] & 1 != 0).sum()),
             "negative_qc": int((record["mask"] & 2 != 0).sum()),
             "qg_zero_bg_positive": int((record["mask"] & 4 != 0).sum())}
            for record in masks],
        "stage_masks_kdm6_window": [
            {"stage": record["stage"], "rkstep": record["rkstep"],
             "gap": int((record["mask"][overlap_slices(record, post)[0]] & 1 != 0).sum()),
             "negative_qc": int((record["mask"][overlap_slices(record, post)[0]] & 2 != 0).sum()),
             "qg_zero_bg_positive": int((record["mask"][overlap_slices(record, post)[0]] & 4 != 0).sum())}
            for record in masks],
    }
    return {"schema": "pr63_transition_replay_v1", "counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("masks", type=Path)
    parser.add_argument("kdm_pre", type=Path)
    parser.add_argument("kdm_post", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = summarize(args.masks, args.kdm_pre, args.kdm_post)
    text = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
