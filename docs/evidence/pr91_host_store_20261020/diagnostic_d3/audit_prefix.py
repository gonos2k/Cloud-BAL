#!/usr/bin/env python3
"""Bounded, read-only byte audit of a live PR85 stage trace against C7 gzip."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import os
import struct
from pathlib import Path

MAGIC_FIELDS = {
    b"PR85QND2": ("DEN", "Q", "QC", "QI", "QR", "QS", "QG", "NN", "NC", "NI", "NR", "BG"),
    b"PR85QNB1": ("DEN", "Q", "QC", "QI", "QR", "QS", "QG", "NN", "NC", "NI", "NR", "BG"),
    b"PR85PLB1": ("QV_TEND", "QC_TEND", "QI_TEND", "QNC_TEND", "QNI_TEND"),
}
HEADER_BYTES = 8 + 32 + 15 * 4

class BoundedReader:
    def __init__(self, stream, limit: int):
        self.stream = stream
        self.limit = limit
        self.read_bytes = 0
        self.digest = hashlib.sha256()

    def exact(self, count: int, *, update_hash: bool = True) -> bytes:
        if count > self.limit - self.read_bytes:
            raise EOFError("fixed live snapshot boundary reached")
        out = bytearray()
        while len(out) < count:
            chunk = self.stream.read(min(1024 * 1024, count - len(out)))
            if not chunk:
                raise EOFError("incomplete final record in stream")
            out.extend(chunk)
        self.read_bytes += count
        if update_hash:
            self.digest.update(out)
        return bytes(out)

def stat_identity(path: Path) -> dict:
    st = path.stat()
    return {"path": str(path), "size_bytes": st.st_size, "mtime_ns": st.st_mtime_ns,
            "inode": st.st_ino, "device": st.st_dev}

def read_record(reader: BoundedReader) -> tuple[bytes, list[tuple[str, bytes]], dict]:
    header = reader.exact(HEADER_BYTES)
    magic = header[:8]
    if magic not in MAGIC_FIELDS:
        raise ValueError(f"unknown trace magic {magic!r} at byte {reader.read_bytes - HEADER_BYTES}")
    label = header[8:40].decode("ascii").strip()
    values = struct.unpack(">15i", header[40:])
    kind, timestep, rk, *bounds = values
    expected_kind = 2 if magic == b"PR85PLB1" else 1
    if kind != expected_kind:
        raise ValueError(f"kind/magic mismatch at {label}: {kind}/{magic!r}")
    ims, ime, jms, jme, kms, kme, its, ite, jts, jte, kts, kte = bounds
    dims = (ite - its + 1, jte - jts + 1, kte - kts + 1)
    if min(dims) <= 0:
        raise ValueError(f"invalid bounds at {label}: {bounds}")
    cells = dims[0] * dims[1] * dims[2]
    fields = []
    for name in MAGIC_FIELDS[magic]:
        fields.append((name, reader.exact(cells * 4)))
    info = {"magic": magic.decode("ascii"), "stage": label, "kind": kind,
            "timestep": timestep, "rk": rk, "cells": cells,
            "bounds_memory_and_active": bounds,
            "record_bytes": HEADER_BYTES + cells * 4 * len(fields),
            "field_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in fields}}
    return header, fields, info

def audit(live_path: Path, baseline_path: Path, stop_step: int) -> dict:
    fixed = stat_identity(live_path)
    baseline_before = stat_identity(baseline_path)
    digest = hashlib.sha256()
    records = []
    target = None
    with live_path.open("rb", buffering=0) as lf, gzip.open(baseline_path, "rb") as bf:
        left = BoundedReader(lf, fixed["size_bytes"])
        right = BoundedReader(bf, 1 << 63)
        while True:
            try:
                lh, lfields, li = read_record(left)
            except EOFError as exc:
                return {"status": "INCOMPLETE_BEFORE_TARGET", "stop_reason": str(exc),
                        "live_snapshot": fixed, "live_after": stat_identity(live_path),
                        "baseline_before": baseline_before, "baseline_after": stat_identity(baseline_path),
                        "live_bytes_compared": left.read_bytes, "records": records,
                        "prefix_sha256": digest.hexdigest()}
            rh, rfields, ri = read_record(right)
            if lh != rh or li["stage"] != ri["stage"] or li["timestep"] != ri["timestep"] or li["rk"] != ri["rk"]:
                raise ValueError(f"record header mismatch at record {len(records)+1}: {li} vs {ri}")
            if len(lfields) != len(rfields):
                raise ValueError(f"field count mismatch at record {len(records)+1}")
            digest.update(lh)
            for (ln, lb), (rn, rb) in zip(lfields, rfields, strict=True):
                if ln != rn or lb != rb:
                    raise ValueError(f"field bytes differ at record {len(records)+1} {ln}")
                digest.update(lb)
            li["exact_header_match"] = True
            li["all_field_bytes_match"] = True
            records.append(li)
            if li["stage"] == "POST_KDM6" and li["timestep"] == stop_step:
                target = li
                break
    live_after = stat_identity(live_path)
    baseline_after = stat_identity(baseline_path)
    return {"status": "PASS_EXACT_PREFIX", "comparison": "full record headers and every field payload byte-by-byte",
            "stop_after": {"stage": target["stage"], "timestep": target["timestep"], "rk": target["rk"]},
            "live_snapshot": fixed, "live_after": live_after,
            "live_grew_after_snapshot": live_after["size_bytes"] > fixed["size_bytes"],
            "baseline_before": baseline_before, "baseline_after": baseline_after,
            "baseline_metadata_unchanged": baseline_before == baseline_after,
            "live_bytes_compared": sum(r["record_bytes"] for r in records),
            "unparsed_bytes_in_fixed_live_snapshot": fixed["size_bytes"] - sum(r["record_bytes"] for r in records),
            "complete_records": len(records), "prefix_sha256": digest.hexdigest(), "records": records,
            "bitwise_statement": "Every original REAL32 field payload in the listed records matched the C7 baseline byte-for-byte."}

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--live", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--stop-step", type=int, default=1)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = audit(a.live, a.baseline, a.stop_step)
    result["command"] = ["python3", str(Path(__file__).resolve()), "--live", str(a.live),
                         "--baseline", str(a.baseline), "--stop-step", str(a.stop_step),
                         "--output", str(a.output)]
    result["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    a.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "stop_after", "complete_records", "live_bytes_compared", "prefix_sha256", "live_snapshot", "live_after", "baseline_metadata_unchanged") if k in result}, indent=2))
    if result["status"] != "PASS_EXACT_PREFIX":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
