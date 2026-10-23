#!/usr/bin/env python3
"""Validate and telescope the fixed-support PR100 QC event stream."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from native_kdm6_trace import read_dump  # noqa: E402


def _float32_bits(value: float) -> int:
    return struct.unpack(">i", struct.pack(">f", value))[0]


def _float32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def parse_event(line: str) -> dict:
    fields = line.rstrip("\n").split(",", 8)
    if len(fields) != 9 or not fields[0].startswith("QCEVENT "):
        raise ValueError("malformed event prefix")
    label = fields[0][8:]
    fixed = [int(value) for value in fields[1:8]]
    tail = fields[8].split()
    if not label or len(tail) != 20:
        raise ValueError("malformed event values")
    after_bits = int(tail[0])
    values = [float(value) for value in tail[1:]]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("nonfinite event value")
    ordinal, timestep, j, loop, i, k, before_bits = fixed
    return {"label": label, "ordinal": ordinal, "timestep": timestep,
            "j": j, "loop": loop, "i": i, "k": k,
            "before_bits": before_bits, "after_bits": after_bits,
            "before": values[0], "after": values[1], "delta": values[2],
            "proposal": values[3:7], "alpha": values[7:11],
            "approved": values[11:15], "deferred": values[15:19]}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def reduce_events(event_path: Path, mask_path: Path, pre_path: Path,
                  post_path: Path) -> dict:
    mask = [tuple(map(int, row.split())) for row in mask_path.read_text().splitlines()]
    if len(mask) != 613 or len(set(mask)) != 613:
        raise ValueError("mask must contain 613 unique i j k points")
    points = set(mask)
    pre = read_dump(pre_path)
    post = read_dump(post_path)
    if pre["fields"]["QC"].shape != post["fields"]["QC"].shape:
        raise ValueError("pre/post QC geometry differs")
    bounds = pre["bounds"]
    if bounds != post["bounds"]:
        raise ValueError("pre/post bounds differ")

    by_cell: dict[tuple[int, int, int], list[dict]] = defaultdict(list)
    ordinals = []
    labels = Counter()
    with event_path.open(encoding="ascii") as stream:
        if stream.readline().strip() != "PR100_QC_V1 613 fixed_source_support":
            raise ValueError("wrong event stream header")
        for line in stream:
            event = parse_event(line)
            ordinals.append(event["ordinal"])
            labels[event["label"]] += 1
            cell = (event["i"], event["j"], event["k"])
            if cell not in points or event["timestep"] != 1:
                raise ValueError(f"event outside fixed T1 support: {cell}")
            by_cell[cell].append(event)
    if ordinals != list(range(1, len(ordinals) + 1)):
        raise ValueError("event ordinals are not contiguous source order")
    if set(by_cell) != points:
        raise ValueError("event cells do not exactly cover mask")

    summed_delta = []
    net_change = []
    q_pre = []
    q_post = []
    packet_rows = {"cold": [], "warm": []}
    for i, j, k in mask:
        events = by_cell[(i, j, k)]
        if not events or events[0]["label"] != "ENTRY" or events[-1]["label"] != "EXIT":
            raise ValueError(f"missing endpoint event at {(i, j, k)}")
        if sum(e["label"] == "ENTRY" for e in events) != 1 or sum(
                e["label"] == "EXIT" for e in events) != 1:
            raise ValueError(f"duplicate endpoint event at {(i, j, k)}")
        for before, after in zip(events, events[1:]):
            if before["after_bits"] != after["before_bits"]:
                raise ValueError(f"broken QC write chain at {(i, j, k)}")
        for e in events:
            if _float32_bits(e["before"]) != e["before_bits"] or \
                    _float32_bits(e["after"]) != e["after_bits"]:
                raise ValueError(f"raw REAL32 bits disagree with values at {(i, j, k)}")
            if not math.isclose(e["delta"], e["after"] - e["before"],
                                rel_tol=0.0, abs_tol=1e-30):
                raise ValueError(f"event delta mismatch at {(i, j, k)}")
            if e["label"] in ("COLD_COMMIT", "WARM_COMMIT"):
                kind = "cold" if e["label"] == "COLD_COMMIT" else "warm"
                for proposal, alpha, approved, deferred in zip(
                        e["proposal"], e["alpha"], e["approved"], e["deferred"], strict=True):
                    if _float32(proposal * alpha) != _float32(approved):
                        raise ValueError(f"packet approved value fails REAL32 alpha product at {(i, j, k)}")
                    if _float32(proposal - approved) != _float32(deferred):
                        raise ValueError(f"packet deferred value fails REAL32 subtraction at {(i, j, k)}")
                packet_rows[kind].append(e)
        first, last = events[0], events[-1]
        iy, jy, ky = i - bounds["its"], j - bounds["jts"], k - bounds["kts"]
        expected_pre = float(pre["fields"]["QC"][jy, ky, iy])
        expected_post = float(post["fields"]["QC"][jy, ky, iy])
        if _float32_bits(expected_pre) != first["before_bits"]:
            raise ValueError(f"entry QC differs from source pre capture at {(i, j, k)}")
        if _float32_bits(expected_post) != last["after_bits"]:
            raise ValueError(f"exit QC differs from source post capture at {(i, j, k)}")
        endpoint_delta = last["after"] - first["before"]
        telescoped = math.fsum(e["delta"] for e in events[1:-1])
        if not math.isclose(telescoped, endpoint_delta, rel_tol=0.0, abs_tol=2e-15):
            raise ValueError(f"QC writes do not telescope at {(i, j, k)}")
        summed_delta.append(telescoped)
        net_change.append(endpoint_delta)
        q_pre.append(expected_pre)
        q_post.append(expected_post)

    return {
        "schema": "pr100_qc_process_account_v1",
        "event_sha256": sha256(event_path), "mask_sha256": sha256(mask_path),
        "pre_sha256": pre["sha256"], "post_sha256": post["sha256"],
        "mask_cells": len(points), "event_rows": len(ordinals),
        "event_labels": dict(sorted(labels.items())),
        "packet_accounting": {
            kind: {
                "commit_events": len(rows),
                "actual_single_stored_delta_sum": math.fsum(e["delta"] for e in rows),
                "component_columns": {
                    name: {
                        "proposal_signed_sum": math.fsum(e["proposal"][n] for e in rows),
                        "alpha_observed_min": min((e["alpha"][n] for e in rows), default=None),
                        "alpha_observed_max": max((e["alpha"][n] for e in rows), default=None),
                        "approved_signed_sum": math.fsum(e["approved"][n] for e in rows),
                        "binary64_product_of_observed_real32_alpha_and_proposal_signed_sum":
                            math.fsum(e["alpha"][n] * e["proposal"][n] for e in rows),
                        "binary64_product_minus_recorded_real32_approved_sum":
                            math.fsum(e["alpha"][n] * e["proposal"][n] - e["approved"][n]
                                      for e in rows),
                        "deferred_signed_sum": math.fsum(e["deferred"][n] for e in rows),
                    } for n, name in enumerate(("NG", "AUT", "G", "WARM"))
                },
                "REAL32_product_and_remainder_checks": "PASS",
                "interpretation": "packet columns are REAL32 source diagnostics; recorded approved is rounded REAL32 multiplication, not exact mathematical approval; actual QCI commit is counted once in stored delta",
            } for kind, rows in packet_rows.items()
        },
        "event_column_coverage": {
            "COLD_COMMIT": "NG/AUT/G proposal, alpha, approved and deferred values captured; one actual stored QCI delta",
            "WARM_COMMIT": "warm proposal, alpha, approved and deferred values captured; one actual stored QCI delta",
            "other_direct_write_labels": "proposal/alpha/approved/deferred arrays are zero-filled N/A sentinels, not captured zero physical process rates; before/after/delta remain observed",
            "CONDENSATION": "source tag retained; sign classification uses actual stored QCI delta; requested E/pcond is not captured",
        },
        "per_cell_chain_and_telescope": "PASS",
        "entry_exit_raw_qc_identity": "PASS",
        "total_stored_qc_change_fsum": math.fsum(net_change),
        "sum_source_write_deltas_fsum": math.fsum(summed_delta),
        "support_qc_pre_rms": math.sqrt(math.fsum(x*x for x in q_pre) / len(q_pre)),
        "support_qc_post_rms": math.sqrt(math.fsum(x*x for x in q_post) / len(q_post)),
        "scope": "613 fixed source-composed QC support cells; T1 only; observer replay, not process causality",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("mask", type=Path)
    parser.add_argument("pre", type=Path)
    parser.add_argument("post", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = reduce_events(args.events, args.mask, args.pre, args.post)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
