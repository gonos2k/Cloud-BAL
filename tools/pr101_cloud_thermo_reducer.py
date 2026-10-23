#!/usr/bin/env python3
"""Validate source-observed KDM6 liquid saturation/evaporation records."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

VALUE_NAMES = (
    "t_before", "pressure", "qv_before", "qc_before", "es_liquid", "qs_liquid",
    "work1", "pcond", "dtcld", "xl", "cpm", "cpm_basis_q", "xl_basis_t",
    "psat", "ttp", "xa", "xb", "ep2", "qmin", "es_initial", "qs_initial",
    "es_after", "qs_after", "rh_initial", "rh_branch", "rh_after",
    "unbounded_evaporation", "bounded_evaporation",
    "source_extent", "qv_after", "qc_after", "t_after", "stored_dqv",
    "stored_dqc", "stored_dt",
)


def parse_row(line: str) -> dict:
    head, *tail = line.rstrip("\n").split(maxsplit=1)
    fields = head.split(",")
    if fields[0] != "PR101THERMO_LIQUID" or len(fields) != 8 or len(tail) != 1:
        raise ValueError("malformed PR101 thermodynamic row")
    meta = [int(x) for x in fields[1:]]
    values = [float(x) for x in tail[0].split()]
    if len(values) != len(VALUE_NAMES) or not all(map(math.isfinite, values)):
        raise ValueError("malformed or nonfinite PR101 values")
    timestep, j, loop, i, k, full, t_before_bits = meta
    if (timestep != 1 or loop < 1 or min(j, i, k) < 1 or full not in (0, 1)):
        raise ValueError("invalid timestep, loop, coordinates, or full-evaporation flag")
    row = dict(zip(VALUE_NAMES, values, strict=True))
    row.update(timestep=timestep, j=j, loop=loop, i=i, k=k,
               full_evaporation=bool(full), t_before_bits=t_before_bits)
    if _bits(row["t_before"]) != t_before_bits:
        raise ValueError("T-before REAL32 bits disagree with serialized T")
    return row


def _f32(value: float) -> float:
    return struct.unpack("=f", struct.pack("=f", value))[0]


def _bits(value: float) -> int:
    return struct.unpack("=I", struct.pack("=f", _f32(value)))[0]


def _within_ulps(actual: float, expected: float, limit: int = 1) -> bool:
    return _f32(actual) >= 0 and _f32(expected) >= 0 and abs(_bits(actual) - _bits(expected)) <= limit


def source_liquid_qs(temp: float, p: float, psat: float, ttp: float,
                    xa: float, xb: float, ep2: float, qmin: float) -> tuple[float, float]:
    tr = _f32(_f32(ttp) / _f32(temp))
    first_exp = _f32(math.exp(_f32(_f32(math.log(tr)) * _f32(xa))))
    second_arg = _f32(_f32(xb) * _f32(_f32(1.0) - tr))
    second_exp = _f32(math.exp(second_arg))
    es = _f32(_f32(_f32(psat) * first_exp) * second_exp)
    capped = min(es, _f32(_f32(0.99) * _f32(p)))
    numerator = _f32(_f32(ep2) * _f32(capped))
    denominator = _f32(_f32(p) - capped)
    qs = max(_f32(numerator / denominator), _f32(qmin))
    return es, qs


def validate_row(row: dict) -> None:
    if (row["pressure"] <= 0 or row["dtcld"] <= 0 or row["cpm"] <= 0
            or row["psat"] <= 0 or row["ttp"] <= 0 or row["ep2"] <= 0 or row["qmin"] < 0):
        raise ValueError("invalid thermodynamic constant, pressure, timestep, or heat capacity")
    expected_unbounded = max(-row["work1"], 0.0)
    expected_bounded = _f32(max(_f32(-_f32(row["pcond"] * row["dtcld"])), 0.0))
    if (row["unbounded_evaporation"] != expected_unbounded
            or _f32(row["bounded_evaporation"]) != expected_bounded):
        raise ValueError("unbounded or pcond-bounded evaporation differs from source expression")
    for temp, es_name, qs_name in (
            (row["xl_basis_t"], "es_initial", "qs_initial"),
            (row["t_before"], "es_liquid", "qs_liquid"),
            (row["t_after"], "es_after", "qs_after")):
        es, qs = source_liquid_qs(temp, row["pressure"], row["psat"], row["ttp"],
                                  row["xa"], row["xb"], row["ep2"], row["qmin"])
        row.setdefault("saturation_oracle_ulp_differences", {})[es_name] = abs(_bits(row[es_name]) - _bits(es))
        row["saturation_oracle_ulp_differences"][qs_name] = abs(_bits(row[qs_name]) - _bits(qs))
    for name, numerator, denominator in (
            ("rh_initial", row["cpm_basis_q"], row["qs_initial"]),
            ("rh_branch", row["qv_before"], row["qs_liquid"]),
            ("rh_after", row["qv_after"], row["qs_after"])):
        expected = _f32(max(_f32(_f32(numerator) / _f32(denominator)), _f32(row["qmin"])))
        if _f32(row[name]) != expected:
            raise ValueError(f"{name} differs from source-style relative humidity")
    if row["full_evaporation"]:
        if _f32(row["source_extent"]) != _f32(row["qc_before"]):
            raise ValueError("full-evaporation source extent differs from cloud water")
        expected_qv = _f32(row["qv_before"] + row["source_extent"])
        expected_qc = 0.0
        expected_t = _f32(row["t_before"] - _f32(
            _f32(row["source_extent"] * row["xl"]) / row["cpm"]))
    else:
        expected_extent = _f32(-_f32(row["pcond"] * row["dtcld"]))
        if _f32(row["source_extent"]) != expected_extent:
            raise ValueError("partial/general source extent differs from pcond*dtcld")
        vapor_change = _f32(row["pcond"] * row["dtcld"])
        expected_qv = _f32(row["qv_before"] - vapor_change)
        expected_qc = _f32(max(_f32(row["qc_before"] + vapor_change), 0.0))
        thermal = _f32(_f32(_f32(row["pcond"] * row["xl"]) / row["cpm"]) * row["dtcld"])
        expected_t = _f32(row["t_before"] + thermal)
    if any(_f32(row[name]) != expected for name, expected in (
            ("qv_after", expected_qv), ("qc_after", expected_qc), ("t_after", expected_t))):
        raise ValueError("stored qv/qc/T differs from source branch arithmetic")
    for delta, after, before in (("stored_dqv", "qv_after", "qv_before"),
                                 ("stored_dqc", "qc_after", "qc_before"),
                                 ("stored_dt", "t_after", "t_before")):
        if not math.isclose(row[delta], row[after] - row[before], rel_tol=0.0, abs_tol=1e-25):
            raise ValueError(f"{delta} differs from stored state endpoints")


def read_stream(path: Path) -> list[dict]:
    rows = []
    keys = set()
    with path.open(encoding="ascii") as stream:
        if stream.readline().strip() != "PR101_CLOUD_THERMO_V1":
            raise ValueError("wrong PR101 stream header")
        for line in stream:
            row = parse_row(line)
            validate_row(row)
            key = (row["timestep"], row["loop"], row["i"], row["j"], row["k"])
            if key in keys:
                raise ValueError(f"duplicate thermodynamic event key: {key}")
            keys.add(key)
            rows.append(row)
    if not rows:
        raise ValueError("thermodynamic stream is empty")
    return rows


def summarize(path: Path) -> dict:
    rows = read_stream(path)
    ulp_differences = [difference for row in rows
                       for difference in row["saturation_oracle_ulp_differences"].values()]
    return {
        "schema": "pr101_cloud_thermo_arm_v1",
        "stream_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": len(rows),
        "support_cells": len({(r["i"], r["j"], r["k"]) for r in rows}),
        "full_evaporation_rows": sum(r["full_evaporation"] for r in rows),
        "liquid_saturation_phase": "source formula, including cold temperatures",
        "source_arithmetic_checks": "PASS",
        "python_saturation_oracle": {
            "disposition": "advisory only; source-computed Fortran values are authoritative",
            "max_ulp_difference": max(ulp_differences, default=0),
            "over_one_ulp_comparisons": sum(value > 1 for value in ulp_differences),
        },
        "rows_data": rows,
    }


def contrast(current: list[dict], reference: list[dict]) -> dict:
    key = lambda r: (r["timestep"], r["loop"], r["i"], r["j"], r["k"])
    left, right = {}, {}
    for rows, mapping in ((current, left), (reference, right)):
        for row in rows:
            identity = key(row)
            if identity in mapping:
                raise ValueError(f"duplicate thermodynamic event key: {identity}")
            mapping[identity] = row
    if left.keys() != right.keys():
        raise ValueError("arm thermodynamic event keys differ")
    fields = ("t_before", "pressure", "qv_before", "qc_before", "es_liquid",
              "qs_liquid", "work1", "pcond", "unbounded_evaporation",
              "bounded_evaporation", "source_extent", "cpm", "xl",
              "cpm_basis_q", "xl_basis_t", "es_initial", "qs_initial",
              "es_after", "qs_after", "rh_initial", "rh_branch", "rh_after",
              "qv_after", "qc_after", "t_after", "stored_dqv", "stored_dqc", "stored_dt")
    return {"schema": "pr101_cloud_thermo_contrast_v1", "reference": "OFF",
            "row_count": len(left), "field_signed_differences": {
                name: math.fsum(left[k][name] - right[k][name] for k in left)
                for name in fields},
            "contrast_semantics": "same timestep/loop/cell source records; arm absolutes remain separately retained"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stream", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--off", type=Path, help="optional OFF stream for aligned contrast")
    args = parser.parse_args()
    result = summarize(args.stream)
    if args.off:
        result["contrast_to_OFF"] = contrast(read_stream(args.stream), read_stream(args.off))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows_data"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
