#!/usr/bin/env python3
"""Validate and summarize diagnostic KDM6 first-call stream dumps."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np


MAGIC = b"KDM6TRC1"
BOUNDS = ("ids", "ide", "jds", "jde", "kds", "kde", "ims", "ime",
          "jms", "jme", "kms", "kme", "its", "ite", "jts", "jte",
          "kts", "kte")
FIELDS_3D = ("TH", "PII", "DEN", "P", "DELZ", "Q", "QC", "QR", "QI",
             "QS", "QG", "NN", "NC", "NI", "NR", "BG", "DIAGRHOG")
FIELDS_2D = ("XLAND",)


class TraceError(ValueError):
    """The stream is incomplete or does not match the expected first call."""


def _read_exact(data: memoryview, offset: int, size: int, label: str) -> tuple[memoryview, int]:
    end = offset + size
    if end > len(data):
        raise TraceError(f"truncated {label}: need {size} bytes at offset {offset}")
    return data[offset:end], end


def read_dump(path: Path) -> dict:
    raw = path.read_bytes()
    view = memoryview(raw)
    offset = 0
    magic, offset = _read_exact(view, offset, 8, "magic")
    if magic != MAGIC:
        raise TraceError(f"wrong trace magic: {magic!r}")
    header, offset = _read_exact(view, offset, 20 * 4, "header")
    header_values = struct.unpack(">20i", header)
    stage, timestep, *bound_values = header_values
    bounds = dict(zip(BOUNDS, bound_values, strict=True))
    params_bytes, offset = _read_exact(view, offset, 5 * 4, "parameters")
    dt, ccn, scale_h, land_mult, sea_mult = struct.unpack(">5f", params_bytes)
    params = (dt, ccn, scale_h, land_mult, sea_mult)
    if not all(np.isfinite(value) for value in params) or min(params) <= 0:
        raise TraceError("call parameters must be finite and positive")
    nx = bounds["ime"] - bounds["ims"] + 1
    ny = bounds["jme"] - bounds["jms"] + 1
    nz = bounds["kme"] - bounds["kms"] + 1
    if min(nx, ny, nz) <= 0 or nx * ny * nz > len(view) // 4:
        raise TraceError(f"invalid memory bounds: {bounds}")
    for start, end, label in (("its", "ite", "i"), ("jts", "jte", "j"),
                              ("kts", "kte", "k")):
        if bounds[start] > bounds[end]:
            raise TraceError(f"empty or inverted active {label} tile")
    active = (slice(bounds["jts"] - bounds["jms"], bounds["jte"] - bounds["jms"] + 1),
              slice(bounds["kts"] - bounds["kms"], bounds["kte"] - bounds["kms"] + 1),
              slice(bounds["its"] - bounds["ims"], bounds["ite"] - bounds["ims"] + 1))
    if any(s.start < 0 or s.stop > n for s, n in zip(active, (ny, nz, nx), strict=True)):
        raise TraceError("active tile is outside the memory bounds")

    fields = {}
    for name in FIELDS_3D + FIELDS_2D:
        field_name, offset = _read_exact(view, offset, 8, f"{name} name")
        try:
            decoded_name = field_name.tobytes().decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise TraceError(f"invalid ASCII field name for {name}") from exc
        if decoded_name != name:
            raise TraceError(f"expected field {name}, got {field_name.tobytes()!r}")
        shape = (ny, nz, nx) if name in FIELDS_3D else (ny, nx)
        size = int(np.prod(shape)) * 4
        field_bytes, offset = _read_exact(view, offset, size, f"{name} data")
        values = np.frombuffer(field_bytes, dtype=np.dtype(">f4"))
        fields[name] = values.reshape(shape)[active] if name in FIELDS_3D else values.reshape(shape)[active[0], active[2]]
    if offset != len(view):
        raise TraceError(f"unexpected trailing bytes: {len(view) - offset}")
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "stage": stage, "itimestep": timestep, "bounds": bounds,
            "active_shape_xyz": [bounds["ite"] - bounds["its"] + 1,
                                 bounds["jte"] - bounds["jts"] + 1,
                                 bounds["kte"] - bounds["kts"] + 1],
            "params": {"dt_s": dt, "ccn_number_m3": ccn, "scale_h_m": scale_h,
                       "qnccn_land_mult": land_mult, "qnccn_sea_mult": sea_mult},
            "fields": fields}


def _stats(values: np.ndarray) -> dict:
    finite = np.isfinite(values)
    finite_values = values[finite]
    return {"size": int(values.size), "finite": int(finite.sum()),
            "nonfinite": int((~finite).sum()), "positive": int((values > 0).sum()),
            "zero": int((values == 0).sum()), "negative": int((values < 0).sum()),
            "min": float(finite_values.min()) if finite_values.size else None,
            "max": float(finite_values.max()) if finite_values.size else None}


def summarize_pair(pre_path: Path, post_path: Path, expected_timestep: int | None = None) -> dict:
    pre, post = read_dump(pre_path), read_dump(post_path)
    if pre["stage"] != 1 or post["stage"] != 2:
        raise TraceError("trace stages must be pre=1 and post=2")
    if pre["itimestep"] != post["itimestep"]:
        raise TraceError("pre/post timestep mismatch")
    if expected_timestep is not None and pre["itimestep"] != expected_timestep:
        raise TraceError(f"wrong timestep: expected {expected_timestep}, got {pre['itimestep']}")
    if pre["itimestep"] <= 0:
        raise TraceError("first-call timestep must be positive")
    if pre["bounds"] != post["bounds"] or pre["params"] != post["params"]:
        raise TraceError("pre/post call header mismatch")
    fields = {}
    changed = {}
    for name in FIELDS_3D + FIELDS_2D:
        a, b = pre["fields"][name], post["fields"][name]
        if a.shape != b.shape:
            raise TraceError(f"pre/post shape mismatch for {name}")
        fields[name] = {"pre": _stats(a), "post": _stats(b)}
        delta = np.abs(b - a)
        finite_delta = delta[np.isfinite(delta)]
        changed[name] = {"changed_cells": int((b != a).sum()),
                         "max_abs_change": float(finite_delta.max()) if finite_delta.size else None,
                         "pre_nonfinite": int((~np.isfinite(a)).sum()),
                         "post_nonfinite": int((~np.isfinite(b)).sum())}
    temperature_pre = pre["fields"]["TH"] * pre["fields"]["PII"]
    temperature_post = post["fields"]["TH"] * post["fields"]["PII"]
    fields["T_K"] = {"pre": _stats(temperature_pre), "post": _stats(temperature_post)}
    temperature_delta = np.abs(temperature_post - temperature_pre)
    finite_temperature_delta = temperature_delta[np.isfinite(temperature_delta)]
    changed["T_K"] = {
        "changed_cells": int((temperature_post != temperature_pre).sum()),
        "max_abs_change": float(finite_temperature_delta.max()) if finite_temperature_delta.size else None,
        "pre_nonfinite": int((~np.isfinite(temperature_pre)).sum()),
        "post_nonfinite": int((~np.isfinite(temperature_post)).sum()),
    }
    pairs = {"QC": "NC", "QI": "NI", "QR": "NR", "QG": "BG"}
    gaps = {mass: {"positive_mass": int((pre["fields"][mass] > 0).sum()),
                   "positive_mass_zero_moment": int(((pre["fields"][mass] > 0) &
                                                      (pre["fields"][moment] == 0)).sum())}
            for mass, moment in pairs.items()}
    gaps_post = {mass: {"positive_mass": int((post["fields"][mass] > 0).sum()),
                        "positive_mass_zero_moment": int(((post["fields"][mass] > 0) &
                                                           (post["fields"][moment] == 0)).sum())}
                 for mass, moment in pairs.items()}
    return {"schema": "kdm6_first_call_raw_trace_summary_v1",
            "execution_scope": "diagnostic capture around one public kdm6 call",
            "pre": {k: v for k, v in pre.items() if k != "fields"},
            "post": {k: v for k, v in post.items() if k != "fields"},
            "fields": fields, "pre_positive_mass_zero_moment": gaps,
            "post_positive_mass_zero_moment": gaps_post, "pre_to_post": changed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pre", type=Path)
    parser.add_argument("post", type=Path)
    parser.add_argument("--expected-timestep", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        summary = summarize_pair(args.pre, args.post, args.expected_timestep)
    except (OSError, TraceError) as exc:
        parser.error(str(exc))
    encoded = json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
