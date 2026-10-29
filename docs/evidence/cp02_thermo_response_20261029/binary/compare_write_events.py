#!/usr/bin/env python3
"""Recompute selected KDM62D qrs/q/qci/t write deltas from pinned captures."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAPTURES = HERE.parent / "captures"
OUTPUT_JSON = HERE / "arm_qrs_branch_comparison.json"
OUTPUT_CSV = HERE / "arm_qrs_branch_comparison.csv"
BINARY_SHA256 = "de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168"
HELPER_SHA256 = "e6b9f5395a847fb3c475e9dd9d5b648cce0b224c5bd76562278df3e23f91c38b"
SELECTION_SHA256 = "38602c67768d0836c5f911c43ff4bcced57073f6f222f1c91a63499c16956c6e"
TARGETS = {
    "P05_00": {"rank": "1", "i": 163, "j": 70, "k": 8},
    "P01_00": {"rank": "3", "i": 163, "j": 73, "k": 8},
}
CAPTURE_INPUTS = {
    ("OFF", "P05_00"): ("OFF/raw_off_first_inner_rank1_pid30347.json.gz", "edef45811030ea45efecfe7fdc8008f7f5ec0f89e1d96ed7e06afaa5c6f5319f"),
    ("OFF", "P01_00"): ("OFF/raw_off_first_inner_rank3_pid30341.json.gz", "ed4a83bc0fcb3ec1d7b826872b3dc4b72094fc2d59bcb2ef958725f4362dbfcf"),
    ("HYDRO", "P05_00"): ("HYDRO/raw_hydro_first_inner_rank1_pid29198.json.gz", "3ed97a67219678070776352c65cb6029e2df566cca3380a5e95902e46d8d6c85"),
    ("HYDRO", "P01_00"): ("HYDRO/raw_hydro_first_inner_rank3_pid29187.json.gz", "474c8dc204c3d2a95b8a84643529cff8a3170d02b8a54ae80d94bdd9bdd8e637"),
    ("LIQUID", "P05_00"): ("LIQUID/raw_liquid_first_inner_rank1_pid32018.json.gz", "7db8bab378cb4f9a898efd3e653945d1c330b3f3d21f6b732965a19ced679330"),
    ("LIQUID", "P01_00"): ("LIQUID/raw_liquid_first_inner_rank3_pid32015.json.gz", "0a7f941a3e9a1c92026bcbfb4741e204d6fd39d27b09b1c2120901ee38338e47"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def f32_from_hex(raw_hex: str) -> float:
    return struct.unpack("=f", bytes.fromhex(raw_hex))[0]


def load_capture(arm: str, target: str) -> tuple[dict, str, Path]:
    relative, expected_hash = CAPTURE_INPUTS[(arm, target)]
    path = CAPTURES / relative
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise ValueError(f"capture_hash_mismatch:{relative}:{actual_hash}")
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        record = json.load(stream)
    if record.get("status") != "all_ranks_settled":
        raise ValueError(f"capture_not_settled:{relative}:{record.get('status')}")
    if str(record.get("rank")) != TARGETS[target]["rank"]:
        raise ValueError(f"capture_rank_mismatch:{relative}")
    for key, expected in (("binary_sha256", BINARY_SHA256),
                          ("helper_sha256", HELPER_SHA256),
                          ("selection_sha256", SELECTION_SHA256)):
        if record.get(key) != expected:
            raise ValueError(f"capture_{key}_mismatch:{relative}")
    if not selected_point_present(record, target):
        raise ValueError(f"selected_point_missing:{relative}:{target}")
    return record, actual_hash, path


def selected_point_present(record: dict, target: str) -> bool:
    expected = TARGETS[target]
    return any(
        point.get("label") == target
        and (point.get("i"), point.get("j"), point.get("k"))
        == (expected["i"], expected["j"], expected["k"])
        for inner in record.get("inner", [])
        for point in inner.get("points", [])
    )


def selected_events(record: dict, target: str) -> list[dict]:
    return [event for event in record.get("write_events", [])
            if event.get("target") == target]


def event_row(arm: str, target: str, event: dict) -> dict:
    field = event["field"]
    before_hex = event["raw_before_hex"]
    after_hex = event["raw_after_hex"]
    before = f32_from_hex(before_hex)
    after = f32_from_hex(after_hex)
    return {
        "arm": arm,
        "target": target,
        "rank": str(event["rank"]),
        "ordinal": int(event["ordinal"]),
        "field": field,
        "pc_after_write": event["pc_after_write_hex"],
        "raw_before_hex": before_hex,
        "before_f32": before,
        "raw_after_hex": after_hex,
        "after_f32": after,
        "delta_f32": after - before,
    }


def event_for(events: list[dict], ordinal: int, field: str) -> dict:
    matches = [event for event in events
               if int(event["ordinal"]) == ordinal and event["field"] == field]
    if len(matches) != 1:
        raise ValueError(f"expected_one_event:{ordinal}:{field}:found={len(matches)}")
    return matches[0]


def summarize_target(arm: str, target: str, events: list[dict]) -> dict:
    first_qrs = event_for(events, 1, "qrs")
    vapor = event_for(events, 2, "q")
    branch_qrs = event_for(events, 3, "qrs")
    temp = event_for(events, 4, "t")
    for event, expected_pc in ((first_qrs, "0x25e9155"),
                               (vapor, "0x25f4dff"),
                               (branch_qrs, "0x25f4e5e"),
                               (temp, "0x25f4293")):
        if event.get("pc_after_write_hex") != expected_pc:
            raise ValueError(f"unexpected_write_pc:{arm}:{target}:{event['ordinal']}")
    q_delta = event_row(arm, target, vapor)["delta_f32"]
    qrs_delta = event_row(arm, target, branch_qrs)["delta_f32"]
    return {
        "arm": arm,
        "target": target,
        "rank": TARGETS[target]["rank"],
        "first_qrs_write": event_row(arm, target, first_qrs),
        "branch_q_write": event_row(arm, target, vapor),
        "branch_qrs_write": event_row(arm, target, branch_qrs),
        "branch_delta_q_plus_qrs": q_delta + qrs_delta,
        "post_branch_t_write": event_row(arm, target, temp),
        "all_events": [event_row(arm, target, event) for event in events],
    }


def write_csv(rows: list[dict]) -> None:
    columns = ["arm", "target", "rank", "ordinal", "field",
               "pc_after_write", "raw_before_hex", "before_f32",
               "raw_after_hex", "after_f32", "delta_f32"]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    summaries = []
    rows = []
    input_manifest = []
    for arm in ("OFF", "HYDRO", "LIQUID"):
        for target in ("P05_00", "P01_00"):
            record, capture_hash, path = load_capture(arm, target)
            events = selected_events(record, target)
            summary = summarize_target(arm, target, events)
            summaries.append(summary)
            rows.extend(summary["all_events"])
            input_manifest.append({
                "arm": arm,
                "target": target,
                "path": str(path.relative_to(CAPTURES)),
                "sha256": capture_hash,
                "status": record["status"],
                "rank": str(record["rank"]),
            })
    write_csv(rows)
    result = {
        "status": "REPRODUCED_ACCEPTED_SELECTED_WRITE_EVENTS",
        "binary_sha256": BINARY_SHA256,
        "helper_sha256": HELPER_SHA256,
        "selection_sha256": SELECTION_SHA256,
        "interpretation_scope": (
            "Selected REAL32 buffer writes only; no mass closure, physical process, "
            "or forecast-cause claim."
        ),
        "capture_inputs": input_manifest,
        "summaries": summaries,
        "event_csv": OUTPUT_CSV.name,
        "event_csv_sha256": sha256_file(OUTPUT_CSV),
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(OUTPUT_JSON)
    print(OUTPUT_CSV)
    print(result["event_csv_sha256"])


if __name__ == "__main__":
    main()
