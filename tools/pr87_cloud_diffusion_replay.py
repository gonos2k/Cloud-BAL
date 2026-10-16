"""Replay sparse cloud or graupel traces using the reviewed scalar arithmetic.

This binds actual PRE/POST operands to a source-equation replay; it does not
attribute every cloud failure to diffusion or certify a model timestep.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

from pr87_rain_diffusion_replay import (
    _VALUE_NAMES, _add32, _bits32, _f32, _stencil32, _stencil64,
)

MIN_MASS = 523.59881591796875 / 500000.0**3
MAX_MASS = 523.59881591796875 / 12000.0**3


def replay(path: Path, *, graupel: bool = False) -> dict:
    prefix = "PR87_G_DIFFUSION" if graupel else "PR87_CLOUD_DIFFUSION"
    tags = {prefix + "_PRE", prefix + "_POST"}
    mass_bounds = (100.0, 900.0) if graupel else (MIN_MASS, MAX_MASS)
    species = ("QG", "BG") if graupel else ("QC", "QNC")
    opener = gzip.open if path.suffix == ".gz" else open
    pending = {}
    pairs = []
    excluded_registry_records = {}
    with opener(path, "rt", encoding="utf-8", errors="strict") as stream:
        for line_number, line in enumerate(stream, 1):
            tokens = line.split()
            if not tokens or tokens[0] not in tags:
                continue
            if len(tokens) != 8 + len(_VALUE_NAMES):
                raise ValueError(f"wrong cloud probe width at line {line_number}")
            tag = tokens[0]
            rk, registry_index, i, j, k = map(int, tokens[1:6])
            if any(value not in {"T", "F"} for value in tokens[6:8]):
                raise ValueError("invalid cloud probe logical field")
            moist, disabled = (value == "T" for value in tokens[6:8])
            if disabled or rk != 1:
                raise ValueError("cloud probe is not active RK1 diffusion")
            if graupel and registry_index != (7 if moist else 5):
                key_excluded = (moist, registry_index)
                excluded_registry_records[key_excluded] = excluded_registry_records.get(key_excluded, 0) + 1
                continue
            values = dict(zip(_VALUE_NAMES, (_f32(float(x.replace("D", "E")))
                                             for x in tokens[8:]), strict=True))
            if not all(math.isfinite(value) for value in values.values()):
                raise ValueError("nonfinite cloud stencil operand")
            key = (registry_index, i, j, k, moist)
            if tag.endswith("_PRE"):
                if key in pending:
                    raise ValueError("duplicate cloud PRE before POST")
                pending[key] = (values, line_number)
                continue
            if key not in pending:
                raise ValueError("cloud POST has no PRE")
            before, pre_line = pending.pop(key)
            for name in _VALUE_NAMES:
                if name != "tendency" and _bits32(before[name]) != _bits32(values[name]):
                    raise ValueError(f"diffusion operand changed across call: {name}")
            post32 = _add32(before["tendency"], _stencil32(before))
            post64 = before["tendency"] + _stencil64(before)
            pairs.append({"species": species[0] if moist else species[1], "registry_index": registry_index,
                          "coordinate_i_j_k": [i, j, k], "line_pre": pre_line,
                          "line_post": line_number, "source_values": before,
                          "logged_post_r32": values["tendency"],
                          "replayed_post_r32": post32,
                          "post_bits_match": _bits32(post32) == _bits32(values["tendency"]),
                          "replayed_post_r64": post64,
                          "correction_rate_r64": post64 - values["tendency"]})
    if pending or not pairs or len(pairs) % 2:
        raise ValueError("incomplete cloud stencil trace")
    calls = []
    for index in range(0, len(pairs), 2):
        members = {p["species"]: p for p in pairs[index:index + 2]}
        if set(members) != set(species):
            raise ValueError("cloud call lacks one moment")
        q, n = members[species[0]], members[species[1]]
        if q["coordinate_i_j_k"] != n["coordinate_i_j_k"]:
            raise ValueError("cloud moments captured at different coordinates")
        ratios = {}
        for label in ("logged_post_r32", "replayed_post_r64"):
            qv, nv = q[label], n[label]
            ratios[label] = {"q_over_moment": qv / nv if nv > 0 else None,
                             "positive_source_pair": qv > 0 and nv > 0,
                             "within_source_mass_bounds":
                             qv > 0 and nv > 0 and mass_bounds[0] * nv <= qv <= mass_bounds[1] * nv}
        calls.append({"capture_ordinal": len(calls) + 1, "moments": members, "ratios": ratios})
    return {"schema": "pr87_sparse_moment_diffusion_replay_v2", "input": str(path),
            "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "species": list(species), "moment_kind": "specific_bulk_volume" if graupel else "specific_number",
            "source_mass_bounds": list(mass_bounds), "calls": calls,
            "excluded_registry_records": [
                {"moist_mode": moist, "registry_index": registry,
                 "reason": "registry does not identify QG/BG in this mode",
                 "record_count": count}
                for (moist, registry), count in sorted(excluded_registry_records.items())
            ],
            "all_post_r32_bits_match": all(p["post_bits_match"] for p in pairs),
            "scope": "one fixed stencil per captured call; ordinal is not a timestep identity; source tendency ratio is not full-state PSD or a physical-time budget"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stdout", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--graupel", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists")
    result = replay(args.stdout, graupel=args.graupel)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"calls": len(result["calls"]),
                      "all_post_r32_bits_match": result["all_post_r32_bits_match"]}))
