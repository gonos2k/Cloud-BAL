#!/usr/bin/env python3
"""Replay PR91 failure-only store records through the pinned shared core."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "docs/evidence/pr91_host_store_20261020/validation/final_i/cloud_bal_joint_transport.f90"
CORE_SHA256 = "9cfc20a3724b9a71b0be912d7f6746cd3ae5f17128dd743539a34ddadfd862a6"
HEX = re.compile(r"^[0-9A-Fa-f]{16}$")


def _fortran_bool(value: bool) -> str:
    return ".true." if value else ".false."


@dataclass(frozen=True)
class Record:
    run_id: str
    attempt: int
    timestep: int
    rk: int
    pair: int
    i: int
    j: int
    k: int
    scale: str
    candidate_q: str
    candidate_n: str
    source_q: str
    source_n: str
    transport_q: str
    transport_n: str
    dry_density: str
    carrier_old: str
    carrier_new: str
    base_q: str
    base_n: str
    dt: str
    min_mass: str
    max_mass: str
    number_min: str
    number_max: str
    stored_q: str
    stored_n: str
    stage: int
    adjustment: int
    allow_subnormal: bool
    normal_adjust: bool
    quantum_absence: bool
    strict_mass: bool
    inactive_present: bool
    volume_present: bool
    number_pair_bounds: bool
    strict_number_pair: bool


def _bool(token: str) -> bool:
    if token.upper() in {"T", ".TRUE."}:
        return True
    if token.upper() in {"F", ".FALSE."}:
        return False
    raise ValueError(f"invalid Fortran logical: {token}")


def _as_f32(bits: str) -> float:
    return struct.unpack(">f", bytes.fromhex(bits))[0]


def _as_f64(bits: str) -> float:
    return struct.unpack(">d", bytes.fromhex(bits))[0]


def _fraction(value: float) -> Fraction:
    return Fraction.from_float(value)


def _volume_margins(row: Record) -> dict | None:
    if not row.volume_present:
        return None
    q, n = _as_f64(row.candidate_q), _as_f64(row.candidate_n)
    rho = _as_f32(row.dry_density)
    lower, upper = _as_f64(row.number_min), _as_f64(row.number_max)
    # Match the core's separately rounded REAL64 products, then express their
    # differences as exact rationals of the resulting IEEE values.
    number64 = n * float(rho)
    lower64 = lower * q
    upper64 = upper * q
    number32 = struct.unpack(">f", struct.pack(">f", number64))[0]
    def margin(left: float, right: float) -> dict:
        exact = _fraction(left) - _fraction(right)
        return {"decimal": float(exact), "exact_fraction": str(exact)}
    return {
        "definition": "M64=N64*rho32, L64=volume_min*Q64, U64=volume_max*Q64 with REAL64 rounding as in the core; stored check compares REAL32-rounded M32 to the same L64/U64.",
        "M64": number64, "M32": number32, "L64": lower64, "U64": upper64,
        "continuous_lower_margin_M64_minus_L64": margin(number64, lower64),
        "continuous_upper_margin_U64_minus_M64": margin(upper64, number64),
        "stored_lower_margin_M32_minus_L64": margin(number32, lower64),
        "stored_upper_margin_U64_minus_M32": margin(upper64, number32),
    }


def _strict_mass_margins(row: Record) -> dict | None:
    if not row.strict_mass:
        return None
    q, n = _as_f64(row.candidate_q), _as_f64(row.candidate_n)
    minimum, maximum = _as_f64(row.min_mass), _as_f64(row.max_mass)
    ratio = q / n
    lower_margin = _fraction(ratio) - _fraction(minimum)
    upper_margin = _fraction(maximum) - _fraction(ratio)
    return {
        "definition": "ratio=Q64/N64 with REAL64 division as in strict_mass_ratio_valid64; margins are exact rationals of that rounded ratio and the exact REAL64 bounds.",
        "ratio_real64": ratio,
        "lower_margin_ratio_minus_minimum": {"decimal": float(lower_margin), "exact_fraction": str(lower_margin)},
        "upper_margin_maximum_minus_ratio": {"decimal": float(upper_margin), "exact_fraction": str(upper_margin)},
    }


def parse_trace(path: Path, *, expected_run_id: str | None = None) -> list[Record]:
    failures = []
    current_run = ""
    first_run = ""
    options: dict[tuple[str, int, int, int, int, int, int, int], list[str]] = {}
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
      lines = stream.read().splitlines()
    for lineno, raw in enumerate(lines, 1):
        fields = raw.split()
        if not fields:
            continue
        if fields[0] == "PR91_HOST_STORE_TRACE_V1":
            if len(fields) != 2:
                raise ValueError(f"line {lineno}: malformed trace header")
            current_run = fields[1]
        elif fields[0].startswith("PR91_HOST_STORE_TRACE_V1"):
            current_run = fields[0][len("PR91_HOST_STORE_TRACE_V1"):]
            if len(fields) != 1 or not current_run:
                raise ValueError(f"line {lineno}: malformed concatenated trace header")
        elif fields[0] == "ACTUAL_STORE_OPTIONS":
            if len(fields) != 18:
                raise ValueError(f"line {lineno}: expected 18 option fields, got {len(fields)}")
            if not current_run or fields[1] != current_run:
                raise ValueError(f"line {lineno}: option run ID differs from trace header")
            attempt = {"BASELINE": 0, "SOURCE_FIRST_FALLBACK": 1}.get(fields[2])
            if attempt is None:
                raise ValueError(f"line {lineno}: unknown attempt name {fields[2]}")
            key = (fields[1], attempt, *(int(x) for x in fields[3:9]))
            if key in options:
                raise ValueError(f"line {lineno}: duplicate ACTUAL_STORE_OPTIONS {key}")
            options[key] = fields[9:]
        elif fields[0] == "ACTUAL_STORE_FAILURE":
            # The exact hexadecimal payload is authoritative; printed decimal
            # values are intentionally ignored because ES26.17 is rounded text.
            if len(fields) != 48:
                raise ValueError(f"line {lineno}: expected 48 failure fields, got {len(fields)}")
            run_id = fields[1]
            if not current_run or run_id != current_run:
                raise ValueError(f"line {lineno}: failure run ID differs from trace header")
            ints = [int(x) for x in fields[2:9]]
            h64 = fields[28:38]
            h32 = fields[38:46]
            if not all(HEX.fullmatch(x) for x in h64):
                raise ValueError(f"line {lineno}: malformed HEX64 value")
            if not all(re.fullmatch(r"[0-9A-Fa-f]{8}", x) for x in h32):
                raise ValueError(f"line {lineno}: malformed HEX32 value")
            stage, adjustment = int(fields[46]), int(fields[47])
            failures.append((lineno, run_id, ints, fields[9], h64, h32, stage, adjustment))
        if current_run:
            if first_run and current_run != first_run:
                raise ValueError(f"line {lineno}: multiple run IDs in one trace")
            if expected_run_id is not None and current_run != expected_run_id:
                raise ValueError(f"line {lineno}: trace run ID differs from closed diagnostic")
            first_run = current_run
    if not current_run and failures:
        raise ValueError("failure records lack a trace header")
    if expected_run_id is not None and not first_run:
        raise ValueError("closed diagnostic trace lacks a run header")
    records = []
    for lineno, run_id, ints, scale, h64, h32, stage, adjustment in failures:
        key = (run_id, *ints)
        opt = options.pop(key, None)
        if opt is None:
            raise ValueError(f"line {lineno}: missing matching ACTUAL_STORE_OPTIONS {key}")
        # options payload: eight logicals, inactive limit
        if len(opt) != 9:
            raise ValueError(f"line {lineno}: malformed option payload")
        records.append(Record(
            run_id, *ints, scale, h64[0], h64[1], h64[2], h64[3], h64[4], h64[5],
            h32[2], h32[3], h32[4], h32[5], h32[6], h32[7],
            h64[6], h64[7], h64[8], h64[9],
            h32[0], h32[1], stage, adjustment,
            *(_bool(x) for x in opt[:8])))
    if options:
        raise ValueError(f"orphan ACTUAL_STORE_OPTIONS records: {sorted(options)}")
    return records


def trace_metadata(path: Path) -> tuple[dict, str | None, int | None]:
    """Bind optional sidecar assertions to these exact trace bytes and identity."""
    artifact = path.read_bytes()
    payload = gzip.decompress(artifact) if path.suffix == ".gz" else artifact
    raw_sha = hashlib.sha256(payload).hexdigest()
    artifact_sha = hashlib.sha256(artifact).hexdigest()
    capture_path = path.parent / "capture.json"
    closed_path = path.parent / "closed_run.json"
    capture = json.loads(capture_path.read_text()) if capture_path.is_file() else None
    closed = json.loads(closed_path.read_text()) if closed_path.is_file() else None
    expected_count = None
    expected_id = None
    if capture is not None:
        if capture.get("trace_sha256") != raw_sha or capture.get("bytes") != len(payload):
            raise ValueError("capture metadata does not match uncompressed trace")
        expected_count = capture.get("selected_failure_records")
        if type(expected_count) is not int or expected_count < 0:
            raise ValueError("capture metadata lacks a valid failure-record count")
    if closed is not None:
        expected_id = closed.get("identity")
        if not isinstance(expected_id, str) or not expected_id:
            raise ValueError("closed diagnostic lacks a run identity")
        if closed.get("raw_failure_trace_sha256") != raw_sha:
            raise ValueError("closed diagnostic does not match uncompressed trace")
        if path.suffix == ".gz" and closed.get("compressed_failure_trace_sha256") != artifact_sha:
            raise ValueError("closed diagnostic does not match compressed trace")
        if capture is not None and capture.get("run_root") != closed.get("source_run_root"):
            raise ValueError("capture and closed diagnostic identify different source runs")
    return {
        "trace_artifact_sha256": artifact_sha,
        "trace_artifact_bytes": len(artifact),
        "trace_uncompressed_sha256": raw_sha,
        "trace_uncompressed_bytes": len(payload),
        "capture_metadata": capture,
        "closed_run_metadata": closed,
        "provenance_scope": (
            "Trace hashes and declared run ID bound to closed diagnostic; external runtime assertions are not revalidated here."
            if closed is not None else
            "Capture trace hash/count bound; no closed diagnostic binding."
            if capture is not None else
            "Trace identity only; no run receipt or sidecar binding."
        ),
    }, expected_id, expected_count


def _call(record: Record, idx: int) -> str:
    scale = float(record.scale)
    if not (scale == scale and abs(scale) != float("inf")):
        raise ValueError(f"non-finite scale for record {idx}")
    scale_literal = f"{scale:.17g}_real64"
    opt = []
    if record.allow_subnormal:
        opt.append("allow_subnormal=.true.")
    # allow_subnormal is required positionally, so passed in the common call.
    opt = [f"allow_normal_q_adjustment={_fortran_bool(record.normal_adjust)}",
           f"allow_joint_quantum_absence={_fortran_bool(record.quantum_absence)}"]
    if record.volume_present:
        opt.append("volume_number_bounds=bounds")
    if record.strict_mass:
        opt.append("strict_mass_ratio=.true.")
    if record.inactive_present:
        opt.append("inactive_mass_limit=inactive")
    args = ", &\n    ".join(opt)
    return f'''  q=transfer(int(z'{record.candidate_q}',int64),0.0_real64)
  n=transfer(int(z'{record.candidate_n}',int64),0.0_real64)
  source_q=transfer(int(z'{record.source_q}',int64),0.0_real64)
  source_n=transfer(int(z'{record.source_n}',int64),0.0_real64)
  transport_q=transfer(int(z'{record.transport_q}',int64),0.0_real64)
  transport_n=transfer(int(z'{record.transport_n}',int64),0.0_real64)
  rho=transfer(int(z'{record.dry_density}',int32),0.0_real32)
  carrier_old=transfer(int(z'{record.carrier_old}',int32),0.0_real32)
  carrier_new=transfer(int(z'{record.carrier_new}',int32),0.0_real32)
  base_q=transfer(int(z'{record.base_q}',int32),0.0_real32)
  base_n=transfer(int(z'{record.base_n}',int32),0.0_real32)
  dt=transfer(int(z'{record.dt}',int32),0.0_real32)
  qcalc=(real(carrier_old,real64)*real(base_q,real64)+real(dt,real64)* &
    (source_q+{scale_literal}*transport_q))/real(carrier_new,real64)
  ncalc=(real(carrier_old,real64)*real(base_n,real64)+real(dt,real64)* &
    (source_n+{scale_literal}*transport_n))/real(carrier_new,real64)
  candidate_match=transfer(qcalc,0_int64)==transfer(q,0_int64).and. &
    transfer(ncalc,0_int64)==transfer(n,0_int64)
  bounds=[transfer(int(z'{record.number_min}',int64),0.0_real64), &
          transfer(int(z'{record.number_max}',int64),0.0_real64)]
  lo=transfer(int(z'{record.min_mass}',int64),0.0_real64)
  hi=transfer(int(z'{record.max_mass}',int64),0.0_real64)
  inactive=0.0_real64
  if ({_fortran_bool(record.inactive_present)}) inactive=real(nearest(1.e-14,-1.0),real64)
  call joint_moment_store(q,n,rho,lo,hi,{_fortran_bool(record.allow_subnormal)},sq,sn,adj,ok, &
    {args},failure_stage=stage)
  call joint_moment_store(real(sq,real64),real(sn,real64),rho,lo,hi, &
    {_fortran_bool(record.allow_subnormal)},rq,rn,readj,read_ok, {args},failure_stage=rstage)
  consumed=ok.and.read_ok.and.transfer(rq,0_int32)==transfer(sq,0_int32).and. &
    transfer(rn,0_int32)==transfer(sn,0_int32)
  write(*,'(a,1x,i0,1x,i0,1x,l1,1x,l1,1x,l1,1x,i0,1x,z8.8,1x,z8.8)') &
    'REPLAY', {idx}, stage, ok, consumed, candidate_match, adj, &
    transfer(sq,0_int32), transfer(sn,0_int32)
'''


def replay(records: list[Record], optimization: str, scratch: Path | None = None) -> dict:
    core_hash = hashlib.sha256(CORE.read_bytes()).hexdigest()
    if core_hash != CORE_SHA256:
        raise ValueError(f"shared core hash mismatch: {core_hash}")
    if not records:
        return {"status": "NO_FAILURE_RECORDS", "records": 0, "results": [],
                "core_sha256": core_hash}
    if shutil.which("bash") is None:
        raise RuntimeError("bash is required for the pinned Intel profile")
    with tempfile.TemporaryDirectory(prefix=f"pr91_replay_{optimization}_", dir=scratch) as temp:
        work = Path(temp)
        source = work / "replay.f90"
        calls = "\n".join(_call(row, i) for i, row in enumerate(records, 1))
        source.write_text(f'''program pr91_replay
 use iso_fortran_env, only: real32,real64,int32,int64
 use cloud_bal_joint_transport, only: joint_moment_store
 implicit none
 real(real64) :: q,n,lo,hi,bounds(2),inactive,source_q,source_n,transport_q,transport_n,qcalc,ncalc
 real(real32) :: rho,sq,sn,rq,rn,carrier_old,carrier_new,base_q,base_n,dt
 integer :: adj,stage,readj,rstage
 logical :: ok,consumed,read_ok,candidate_match
{calls}
end program pr91_replay
''')
        profile = "CLOUD_BAL_FREE_FLAGS" if optimization == "O0" else "CLOUD_BAL_REPRO_FLAGS"
        cmd = f'''set -euo pipefail
source "{ROOT / 'tests/intel_toolchain.sh'}"
"$CLOUD_BAL_FC" "${{{profile}[@]}}" "{CORE}" "{source}" -o "{work / 'replay'}"
"{work / 'replay'}"'''
        proc = subprocess.run(["bash", "-c", cmd], cwd=work, text=True, capture_output=True)
        if proc.returncode:
            raise RuntimeError(f"pinned Intel replay failed ({optimization}):\n{proc.stdout}{proc.stderr}")
        results = []
        for line in proc.stdout.splitlines():
            fields = line.split()
            if fields and fields[0] == "REPLAY":
                results.append({"index": int(fields[1]), "stage": int(fields[2]),
                    "valid": _bool(fields[3]), "reconsumed": _bool(fields[4]),
                    "candidate_bits_match": _bool(fields[5]), "adjustment": int(fields[6]),
                    "stored_q_hex": fields[7], "stored_n_hex": fields[8]})
        if len(results) != len(records):
            raise RuntimeError(f"expected {len(records)} replay results, got {len(results)}; output={proc.stdout}")
        for row, result in zip(records, results):
            result.update({"run_id": row.run_id, "attempt": row.attempt,
                "timestep": row.timestep, "rk": row.rk, "pair": row.pair,
                "i": row.i, "j": row.j, "k": row.k,
                "trace_stage": row.stage, "trace_adjustment": row.adjustment,
                "scale_printed_r64": row.scale,
                "candidate_q_hex": row.candidate_q, "candidate_n_hex": row.candidate_n,
                "source_q_hex": row.source_q, "source_n_hex": row.source_n,
                "transport_q_hex": row.transport_q, "transport_n_hex": row.transport_n,
                "carrier_old_hex": row.carrier_old, "carrier_new_hex": row.carrier_new,
                "base_q_hex": row.base_q, "base_n_hex": row.base_n, "dt_hex": row.dt,
                "dry_density_hex": row.dry_density, "mass_min_hex": row.min_mass,
                "mass_max_hex": row.max_mass, "volume_min_hex": row.number_min,
                "volume_max_hex": row.number_max,
                "volume_margins": _volume_margins(row),
                "strict_mass_margins": _strict_mass_margins(row),
                "trace_stored_q_hex": row.stored_q, "trace_stored_n_hex": row.stored_n})
            result["store_trace_match"] = (
                result["stage"] == row.stage and result["adjustment"] == row.adjustment and
                result["stored_q_hex"].upper() == row.stored_q.upper() and
                result["stored_n_hex"].upper() == row.stored_n.upper())
            reconsumed = result.pop("reconsumed")
            result["stored_pair_idempotence"] = reconsumed if result["valid"] else None
            result["reproduced_failure"] = (
                result["candidate_bits_match"] and result["store_trace_match"] and not result["valid"])
            result["classification"] = (
                "REPRODUCED_FAILURE" if result["reproduced_failure"] else "REPLAY_MISMATCH")
        return {"records": len(records), "results": results, "core_sha256": core_hash,
                "optimization": optimization}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--optimization", choices=("O0", "O2", "both"), default="both")
    parser.add_argument("--scratch", type=Path, default=Path("/var/tmp"))
    args = parser.parse_args()
    metadata, expected_id, expected_count = trace_metadata(args.trace)
    records = parse_trace(args.trace, expected_run_id=expected_id)
    if hashlib.sha256(args.trace.read_bytes()).hexdigest() != metadata["trace_artifact_sha256"]:
        raise ValueError("trace changed while reading provenance and records")
    if expected_count is not None and len(records) != expected_count:
        raise ValueError("capture failure-record count differs from parsed trace")
    outputs = ([replay(records, opt, args.scratch)
                for opt in (("O0", "O2") if args.optimization == "both" else (args.optimization,))]
               if records else [])
    status = "REPLAYED" if records else "NO_FAILURE_RECORDS"
    print(json.dumps({"status": status, "trace": str(args.trace),
                      **metadata,
                      "record_count": len(records), "runs": outputs}, indent=2))
    if any(not row["reproduced_failure"] for run in outputs for row in run["results"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
