#!/usr/bin/env python3
"""Read PR101 call-boundary records and replay the pinned U/V stencil."""

from __future__ import annotations

import argparse
import copy
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import numpy as np


MAGIC = 0x50573130
VERSION = 1
# The capture OPEN explicitly requests BIG_ENDIAN, matching the C2 WRF compile
# receipt's -convert big_endian setting. Keep this format fixed in the reader.
HEADER = struct.Struct(">29i")
FLAGS = struct.Struct(">8i")
SCALARS = struct.Struct(">3f")
PAIR = struct.Struct(">2f")
FLOAT = struct.Struct(">f")
METRIC = struct.Struct(">2i8f")


@dataclass
class Record:
    component: str
    phase: int
    rk_step: int
    time_step: int
    face_i: int
    face_j: int
    bounds: dict[str, int]
    diff_opt: int
    km_opt: int
    diff_6th_opt: int
    flags: dict[str, bool]
    khdif: np.float32
    rdx: np.float32
    rdy: np.float32
    c1: dict[int, np.float32] = field(default_factory=dict)
    c2: dict[int, np.float32] = field(default_factory=dict)
    values: dict[tuple[int, int, int], np.float32] = field(default_factory=dict)
    xkmhd: dict[tuple[int, int, int], np.float32] = field(default_factory=dict)
    tendency: dict[int, np.float32] = field(default_factory=dict)
    metrics: dict[tuple[int, int], dict[str, np.float32]] = field(default_factory=dict)


def _exact(stream: BinaryIO, fmt: struct.Struct) -> tuple:
    data = stream.read(fmt.size)
    if len(data) != fmt.size:
        raise ValueError("truncated PR101 capture record")
    return fmt.unpack(data)


def read_records(path: Path) -> list[Record]:
    records: list[Record] = []
    with path.open("rb") as stream:
        while True:
            raw = stream.read(HEADER.size)
            if not raw:
                break
            if len(raw) != HEADER.size:
                raise ValueError("truncated PR101 capture header")
            h = HEADER.unpack(raw)
            if h[0] != MAGIC or h[1] != VERSION or h[2] not in (1, 2) or h[3] not in (1, 2):
                raise ValueError("unexpected PR101 capture header")
            if h[4] < 0 or h[5] < 0 or h[6:8] != ((136, 16) if h[2] == 1 else (135, 17)):
                raise ValueError("unexpected PR101 event or target face")
            names = ("ids", "ide", "jds", "jde", "kds", "kde", "ims", "ime", "jms", "jme",
                     "kms", "kme", "its", "ite", "jts", "jte", "kts", "kte")
            bounds = dict(zip(names, h[8:26]))
            options = (h[26], h[27], h[28])
            flag_values = _exact(stream, FLAGS)
            if any(value not in (0, 1) for value in flag_values):
                raise ValueError("PR101 capture flags must be encoded as zero or one")
            flag_names = ("open_xs", "open_xe", "open_ys", "open_ye", "specified", "nested", "periodic_x", "polar")
            khdif, rdx, rdy = _exact(stream, SCALARS)
            rec = Record("u" if h[2] == 1 else "v", h[3], h[4], h[5], h[6], h[7], bounds,
                         *options, dict(zip(flag_names, (bool(v) for v in flag_values))),
                         np.float32(khdif), np.float32(rdx), np.float32(rdy))
            if bounds["kts"] > 37 or min(bounds["kte"], bounds["kde"] - 1) < 39:
                raise ValueError("capture bounds do not include active levels 37..39")
            if not (bounds["ims"] <= rec.face_i - 1 <= rec.face_i + 1 <= bounds["ime"]
                    and bounds["jms"] <= rec.face_j - 1 <= rec.face_j + 1 <= bounds["jme"]):
                raise ValueError("capture bounds do not contain the target face stencil")
            for k in (37, 38, 39):
                rec.c1[k], rec.c2[k] = map(np.float32, _exact(stream, PAIR))
                for j in range(rec.face_j - 1, rec.face_j + 2):
                    for i in range(rec.face_i - 1, rec.face_i + 2):
                        value, xk = _exact(stream, PAIR)
                        rec.values[i, k, j] = np.float32(value)
                        rec.xkmhd[i, k, j] = np.float32(xk)
                rec.tendency[k] = np.float32(_exact(stream, FLOAT)[0])
            for _ in range(9):
                i, j, mut, *metric_values = _exact(stream, METRIC)
                metric_names = ("mut", "msfux", "msfuy", "msfvx", "msfvx_inv", "msfvy", "msftx", "msfty")
                rec.metrics[i, j] = dict(zip(metric_names, map(np.float32, (mut, *metric_values))))
            numeric = [rec.khdif, rec.rdx, rec.rdy, *rec.c1.values(), *rec.c2.values(),
                       *rec.values.values(), *rec.xkmhd.values(), *rec.tendency.values()]
            numeric.extend(value for row in rec.metrics.values() for value in row.values())
            if not np.isfinite(np.asarray(numeric, dtype=np.float64)).all():
                raise ValueError("non-finite operand in PR101 capture record")
            records.append(rec)
    return records


def _f(x: float) -> np.float32:
    return np.float32(x)


def _add(a: float, b: float) -> np.float32:
    return _f(_f(a) + _f(b))


def _sub(a: float, b: float) -> np.float32:
    return _f(_f(a) - _f(b))


def _mul(a: float, b: float) -> np.float32:
    return _f(_f(a) * _f(b))


def _div(a: float, b: float) -> np.float32:
    return _f(_f(a) / _f(b))


def _weighted(mut: float, c1: float, c2: float) -> np.float32:
    return _add(_mul(c1, mut), c2)


def _sum(values: list[float]) -> np.float32:
    out = _f(values[0])
    for value in values[1:]:
        out = _add(out, value)
    return out


def _active(rec: Record) -> bool:
    b, f = rec.bounds, rec.flags
    if b["kts"] > 37 or min(b["kte"], b["kde"] - 1) < 39:
        return False
    specified = f["specified"] or f["nested"]
    its, ite, jts, jte = b["its"], b["ite"], b["jts"], b["jte"]
    ids, ide, jds, jde = b["ids"], b["ide"], b["jds"], b["jde"]
    if rec.component == "u":
        i_start, i_end = its, ite
        j_start, j_end = jts, min(jte, jde - 1)
        if f["open_xs"] or specified:
            i_start = max(ids + 1, its)
        if f["open_xe"] or specified:
            i_end = min(ide - 1, ite)
        if f["open_ys"] or specified:
            j_start = max(jds + 1, jts)
        if f["open_ye"] or specified:
            j_end = min(jde - 2, jte)
        if f["periodic_x"]:
            i_start, i_end = its, ite
    else:
        i_start, i_end = its, min(ite, ide - 1)
        j_start, j_end = jts, jte
        if f["open_xs"] or specified:
            i_start = max(ids + 1, its)
        if f["open_xe"] or specified:
            i_end = min(ide - 2, ite)
        if f["open_ys"] or specified:
            j_start = max(jds + 1, jts)
        if f["open_ye"] or specified:
            j_end = min(jde - 1, jte)
        if f["periodic_x"]:
            i_start, i_end = its, min(ite, ide - 1)
        if f["polar"]:
            j_start, j_end = max(jds + 1, jts), min(jde - 1, jte)
    return i_start <= rec.face_i <= i_end and j_start <= rec.face_j <= j_end


def replay_face(rec: Record, start_tendency: float) -> dict[int, np.float32]:
    """Apply the source expression for the selected U/V face at k=37..39."""
    if not _active(rec):
        raise ValueError(f"{rec.component} face is outside the native diffusion loop bounds")
    i, j = rec.face_i, rec.face_j
    m = rec.metrics

    def metric(ii: int, jj: int, name: str) -> np.float32:
        return m[ii, jj][name]

    result = {}
    for k in (37, 38, 39):
        c1, c2 = rec.c1[k], rec.c2[k]
        if rec.component == "u":
            km = _mul(_mul(_mul(_div(metric(i-1,j,"msftx"),metric(i-1,j,"msfty")),
                                _weighted(metric(i-1,j,"mut"),c1,c2)),
                           rec.xkmhd[i-1,k,j]),rec.rdx)
            kp = _mul(_mul(_mul(_div(metric(i,j,"msftx"),metric(i,j,"msfty")),
                                _weighted(metric(i,j,"mut"),c1,c2)),
                           rec.xkmhd[i,k,j]),rec.rdx)
            mr = _mul(_mul(metric(i,j,"msfux"),metric(i,j,"msfuy")),rec.rdx)
            yratio_m = _div(_add(metric(i,j,"msfuy"),metric(i,j-1,"msfuy")),
                            _add(metric(i,j,"msfux"),metric(i,j-1,"msfux")))
            ym_terms = [_weighted(metric(ii,jj,"mut"),c1,c2)
                        for ii,jj in ((i,j),(i,j-1),(i-1,j-1),(i-1,j))]
            ym_xk = _sum([rec.xkmhd[ii,k,jj] for ii,jj in ((i,j),(i,j-1),(i-1,j-1),(i-1,j))])
            mkm = _mul(_mul(_mul(_mul(_mul(yratio_m,_f(0.25)),_sum(ym_terms)),
                                  _f(0.25)),ym_xk),rec.rdy)
            yratio_p = _div(_add(metric(i,j,"msfuy"),metric(i,j+1,"msfuy")),
                            _add(metric(i,j,"msfux"),metric(i,j+1,"msfux")))
            yp_terms = [_weighted(metric(ii,jj,"mut"),c1,c2)
                        for ii,jj in ((i,j),(i,j+1),(i-1,j+1),(i-1,j))]
            yp_xk = _sum([rec.xkmhd[ii,k,jj] for ii,jj in ((i,j),(i,j+1),(i-1,j+1),(i-1,j))])
            mkp = _mul(_mul(_mul(_mul(_mul(yratio_p,_f(0.25)),_sum(yp_terms)),
                                  _f(0.25)),yp_xk),rec.rdy)
            my = _mul(_mul(metric(i,j,"msfux"),metric(i,j,"msfuy")),rec.rdy)
        else:
            xm_ratio = _div(_add(metric(i,j,"msfvx"),metric(i-1,j,"msfvx")),
                            _add(metric(i,j,"msfvy"),metric(i-1,j,"msfvy")))
            xm_terms = [_weighted(metric(ii,jj,"mut"),c1,c2)
                        for ii,jj in ((i,j),(i,j-1),(i-1,j-1),(i-1,j))]
            xm_xk = _sum([rec.xkmhd[ii,k,jj] for ii,jj in ((i,j),(i,j-1),(i-1,j-1),(i-1,j))])
            km = _mul(_mul(_mul(_mul(_mul(xm_ratio,_f(0.25)),_sum(xm_terms)),
                                 _f(0.25)),xm_xk),rec.rdx)
            xp_ratio = _div(_add(metric(i,j,"msfvx"),metric(i+1,j,"msfvx")),
                            _add(metric(i,j,"msfvy"),metric(i+1,j,"msfvy")))
            xp_terms = [_weighted(metric(ii,jj,"mut"),c1,c2)
                        for ii,jj in ((i,j),(i,j-1),(i+1,j-1),(i+1,j))]
            xp_xk = _sum([rec.xkmhd[ii,k,jj] for ii,jj in ((i,j),(i,j-1),(i+1,j-1),(i+1,j))])
            kp = _mul(_mul(_mul(_mul(_mul(xp_ratio,_f(0.25)),_sum(xp_terms)),
                                 _f(0.25)),xp_xk),rec.rdx)
            mr = _mul(_mul(metric(i,j,"msfvx"),metric(i,j,"msfvy")),rec.rdx)
            mkm = _mul(_mul(_div(metric(i,j-1,"msfty"),metric(i,j-1,"msftx")),
                            rec.xkmhd[i,k,j-1]),rec.rdy)
            mkp = _mul(_mul(_div(metric(i,j,"msfty"),metric(i,j,"msftx")),
                            rec.xkmhd[i,k,j]),rec.rdy)
            my = _mul(_mul(metric(i,j,"msfvx"),metric(i,j,"msfvy")),rec.rdy)

        fip = rec.values[i+1,k,j]; fi = rec.values[i,k,j]; fim = rec.values[i-1,k,j]
        fjp = rec.values[i,k,j+1]; fj = rec.values[i,k,j]; fjm = rec.values[i,k,j-1]
        xpart = _sub(_mul(kp,_sub(fip,fi)),_mul(km,_sub(fi,fim)))
        ypart = _sub(_mul(mkp,_sub(fjp,fj)),_mul(mkm,_sub(fj,fjm)))
        tendency_delta = _add(_mul(mr,xpart),_mul(my,ypart))
        result[k] = _add(start_tendency,tendency_delta)
    return result


def compare(path: Path) -> dict:
    records = read_records(path)
    grouped: dict[tuple[str,int,int,int,int], dict[int,Record]] = {}
    for rec in records:
        key = rec.component, rec.face_i, rec.face_j, rec.time_step, rec.rk_step
        if rec.phase in grouped.setdefault(key, {}):
            raise ValueError(f"duplicate {rec.component} phase {rec.phase} for event {key}")
        grouped[key][rec.phase] = rec
    results = []
    for key, phases in sorted(grouped.items()):
        if set(phases) != {1,2}:
            raise ValueError(f"incomplete before/after capture for event {key}")
        before, after = phases[1], phases[2]
        if before.diff_opt != 1 or after.diff_opt != 1:
            raise ValueError("capture occurred with diff_opt other than 1")
        if before.bounds != after.bounds or before.flags != after.flags:
            raise ValueError("call bounds or flags changed across the operator")
        if (before.rk_step, before.time_step) != (after.rk_step, after.time_step):
            raise ValueError("time-step or RK event changed across the operator")
        krows = []
        if (before.c1 != after.c1 or before.c2 != after.c2 or before.values != after.values
                or before.xkmhd != after.xkmhd or before.metrics != after.metrics
                or before.khdif != after.khdif or before.rdx != after.rdx or before.rdy != after.rdy
                or (before.diff_opt, before.km_opt, before.diff_6th_opt) !=
                   (after.diff_opt, after.km_opt, after.diff_6th_opt)):
            raise ValueError("input operands or options changed across horizontal_diffusion")
        for k in (37, 38, 39):
            predicted = replay_face(before, before.tendency[k])[k]
            observed = after.tendency[k]
            krows.append({"k": k, "before": float(before.tendency[k]), "after": float(observed),
                          "predicted_after": float(predicted),
                          "residual": float(np.float32(predicted-observed)),
                          "observed_increment": float(np.float32(observed-before.tendency[k]))})
        results.append({"component": before.component.upper(), "face_ij": [before.face_i,before.face_j],
                        "native_time_step_seconds": before.time_step,
                        "rk_step": before.rk_step, "levels": krows})
    if not results:
        raise ValueError("no complete U/V capture pairs found")
    targets = sorted({(row["component"], *row["face_ij"]) for row in results})
    expected = [("U", 136, 16), ("V", 135, 17)]
    return {"schema":"pr101_upper_wind_replay_v1", "capture":str(path), "records":len(records),
            "capture_coverage":{"expected_faces":[list(x) for x in expected],
                                "observed_faces":[list(x) for x in targets],
                                "complete_for_both_target_faces":targets == expected},
            "faces":results}


def _pre_records(path: Path) -> dict[tuple[str,int,int,int,int], Record]:
    records = {}
    for rec in read_records(path):
        if rec.phase != 1:
            continue
        key = rec.component, rec.face_i, rec.face_j, rec.time_step, rec.rk_step
        if key in records:
            raise ValueError(f"duplicate PRE capture for {key}")
        records[key] = rec
    if not records:
        raise ValueError(f"no PRE operands in {path}")
    return records


def factor_separation(projected_path: Path, hydro_path: Path) -> dict:
    """Split the source stencil response into field and coefficient effects."""
    projected_check, hydro_check = compare(projected_path), compare(hydro_path)
    projected, hydro = _pre_records(projected_path), _pre_records(hydro_path)
    if projected.keys() != hydro.keys():
        raise ValueError("projected and HYDRO captures have different target faces")

    def increment(rec: Record) -> dict[int, float]:
        return {k: float(replay_face(rec, 0.0)[k]) for k in (37,38,39)}

    faces = []
    for key in sorted(projected):
        p, h = projected[key], hydro[key]
        if p.component != h.component or p.bounds != h.bounds or p.flags != h.flags:
            raise ValueError("paired source capture bounds/options differ")
        if (p.diff_opt, p.km_opt, p.diff_6th_opt, p.time_step, p.rk_step) != \
           (h.diff_opt, h.km_opt, h.diff_6th_opt, h.time_step, h.rk_step):
            raise ValueError("paired source capture event or diffusion option differs")
        pp = increment(p)
        ph = copy.deepcopy(h); ph.values = p.values
        hp = copy.deepcopy(p); hp.values = h.values
        p_h = increment(ph)
        h_p = increment(hp)
        hh = increment(h)
        rows = []
        for k in (37,38,39):
            field_effect = p_h[k] - hh[k]
            coefficient_effect = h_p[k] - hh[k]
            interaction = pp[k] - p_h[k] - h_p[k] + hh[k]
            rows.append({"k":k, "P_field_P_coeff":pp[k], "P_field_H_coeff":p_h[k],
                         "H_field_P_coeff":h_p[k], "H_field_H_coeff":hh[k],
                         "field_effect_at_H_coeff":field_effect,
                         "coefficient_effect_at_H_field":coefficient_effect,
                         "field_coefficient_interaction":interaction,
                         "total_P_minus_H":pp[k]-hh[k]})
        faces.append({"component":p.component.upper(), "face_ij":[p.face_i,p.face_j],
                      "native_time_step_seconds":p.time_step,
                      "rk_step":p.rk_step, "levels":rows})
    return {"schema":"pr101_upper_wind_factor_separation_v1",
            "projected_capture":str(projected_path), "hydro_capture":str(hydro_path),
            "capture_coverage":{"projected_complete_for_both_target_faces":
                                    projected_check["capture_coverage"]["complete_for_both_target_faces"],
                                "hydro_complete_for_both_target_faces":
                                    hydro_check["capture_coverage"]["complete_for_both_target_faces"]},
            "faces":faces,
            "coefficient_fields":["MUT","xkmhd","c1","c2","map_metrics","rdx","rdy"],
            "captured_but_not_read_by_horizontal_diffusion":["khdif"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--compare-hydro", type=Path,
                        help="also split projected-versus-HYDRO diffusion increments by field/coefficient inputs")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(args.capture)
    if args.compare_hydro:
        result["factor_separation"] = factor_separation(args.capture, args.compare_hydro)
    encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
