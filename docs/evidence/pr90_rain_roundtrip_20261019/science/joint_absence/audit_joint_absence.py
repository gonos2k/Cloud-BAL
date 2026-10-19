#!/usr/bin/env python3
"""Read-only mass reconstruction for paired STORED_PAIR joint-absence events."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
EXPECTED_GRAVITY_RECEIPT_SHA256 = "7b6cc54597b1d67c35ec112decab192cae3d1d5035ec03f5fb418a081df38670"
EXPECTED_GRAVITY = Decimal("9.81000041961669921875")
EVENT_TAGS = ("JOINT_STORAGE", "STORAGE_DELTA_PRESSURE_Q", "STORAGE_DELTA_PRESSURE_MOMENT", "STORED_PAIR")
EXPECTED_FIELDS = 18


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def print_interval(token: str) -> tuple[Decimal, Decimal, Decimal]:
    center = Decimal(token.replace("D", "E").replace("d", "e"))
    exponent = center.as_tuple().exponent
    radius = Decimal(5).scaleb(exponent - 1)
    return center, center - radius, center + radius


def stored_pair_rows(path: Path):
    """Read wrapped Fortran list-directed rows without loading the whole ledger."""
    pending: list[str] | None = None
    with gzip.open(path, "rt", encoding="ascii") as stream:
        for line in stream:
            fields = line.split()
            if not fields:
                continue
            tag = fields[0]
            if tag in EVENT_TAGS:
                if pending is not None:
                    raise ValueError(f"truncated STORED_PAIR row ({len(pending)} fields)")
                if tag == "STORED_PAIR":
                    pending = fields[1:]
                    if len(pending) > EXPECTED_FIELDS:
                        raise ValueError("oversized STORED_PAIR row")
                    if len(pending) == EXPECTED_FIELDS:
                        yield pending
                        pending = None
                continue
            if pending is not None:
                pending.extend(fields)
                if len(pending) > EXPECTED_FIELDS:
                    raise ValueError("oversized STORED_PAIR continuation")
                if len(pending) == EXPECTED_FIELDS:
                    yield pending
                    pending = None
        if pending is not None:
            raise ValueError(f"truncated final STORED_PAIR row ({len(pending)} fields)")


def load_run(run_root: Path, gravity: Decimal) -> dict[str, Any]:
    receipt_path = run_root / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get("status") != "COMPLETE" or receipt.get("timestep_count") != 6
            or receipt.get("final_completed_step") != 6):
        raise ValueError(f"expected complete six-step receipt: {receipt_path}")
    preflight_path = run_root / "preflight.json"
    preflight = json.loads(preflight_path.read_text())
    if (preflight.get("arm") != receipt.get("arm") or preflight.get("duration_seconds") != 120
            or preflight.get("timestep_seconds") != 20):
        raise ValueError(f"receipt/preflight are not the requested 120 s run: {run_root}")
    artifact = next((row for row in receipt.get("compressed_outputs", [])
                     if row.get("path") == "pr87_joint_storage.raw"), None)
    if artifact is None:
        raise ValueError("run receipt lacks pr87_joint_storage.raw binding")
    ledger = run_root / "run" / artifact["compressed_path"]
    if sha256(ledger) != artifact["compressed_sha256"]:
        raise ValueError(f"compressed ledger hash differs from receipt: {ledger}")
    raw_digest = hashlib.sha256()
    raw_bytes = 0
    with gzip.open(ledger, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            raw_digest.update(chunk)
            raw_bytes += len(chunk)
    if raw_digest.hexdigest() != artifact["sha256"] or raw_bytes != artifact["bytes"]:
        raise ValueError("decompressed joint storage ledger hash/size differs from receipt")
    if not any(row.get("path") == artifact["compressed_path"]
               and row.get("sha256") == artifact["compressed_sha256"]
               for row in receipt.get("generated_files", [])):
        raise ValueError("generated_files does not bind compressed joint storage ledger")

    build_ref = receipt.get("candidate_build", {})
    build_path = Path(build_ref.get("receipt_path", ""))
    if sha256(build_path) != build_ref.get("receipt_sha256"):
        raise ValueError("candidate build receipt hash does not match run receipt")
    build = json.loads(build_path.read_text())
    if build.get("status") != "PASS_OVERLAY_BUILD":
        raise ValueError("candidate build receipt is not a passed overlay build")
    executable = Path(build["executable_path"])
    if sha256(executable) != receipt.get("executed_executable_sha256"):
        raise ValueError("executed executable hash mismatch")
    module = build["source_overrides"]["module_em.o"]
    module_path = Path(module["staged_path"])
    module_hash = sha256(module_path)
    if module_hash != module["requested_sha256"] or module_hash != module["staged_sha256"]:
        raise ValueError("compiled module_em source is not hash-bound")
    source = module_path.read_text(errors="replace")
    required = (
        "newcarrier(cell)=c1(k)*(munew(i,j)+mub(i,j))+c2(k)",
        "'STORED_PAIR',itimestep,rk,p,i,j,k,oldcarrier(cell),newcarrier(cell),",
        "rdnw(k),msftx(i,j),msfty(i,j),rdx,rdy",
    )
    normalized = re.sub(r"\s+", "", source.lower())
    for needle in required:
        if re.sub(r"\s+", "", needle.lower()) not in normalized:
            raise ValueError(f"compiled module_em source lacks expected pair formula/ledger field: {needle}")
    if "real(real32),allocatable::oldcarrier(:),newcarrier(:),drydensity(:)" not in normalized:
        raise ValueError("carrier and dry-density declarations are not the expected REAL32")
    if "real(real64)::outflow,cfl,maxcfl,source_candidate(2)" not in normalized:
        raise ValueError("pair candidate is not declared REAL64")
    caller_ref = build["source_overrides"]["solve_em.o"]
    caller_path = Path(caller_ref["staged_path"])
    caller_hash = sha256(caller_path)
    if caller_hash != caller_ref["requested_sha256"] or caller_hash != caller_ref["staged_sha256"]:
        raise ValueError("compiled solve_em caller source is not hash-bound")
    caller = re.sub(r"\s+", "", caller_path.read_text(errors="replace").lower())
    if "(/p_qc,p_qi,p_qr,p_qg/)" not in caller or "(/p_qnc,p_qni,p_qnr,p_qib/)" not in caller:
        raise ValueError("compiled solve_em pair map does not identify pair 4 as QG/QIB")
    if ("qibisrime-volumemixingratio(m3kg-dry-1),notanumbermoment." not in normalized
            or "minmass=[" not in normalized or "100.0_real64]" not in normalized
            or "maxmass=[" not in normalized or "900.0_real64]" not in normalized):
        raise ValueError("compiled module_em source does not pin QIB volume units and graupel density limits")

    groups: dict[tuple[int, int, int], dict[str, Any]] = {}
    ledger_rows_scanned = 0
    for fields in stored_pair_rows(ledger):
        ledger_rows_scanned += 1
        step, rk, pair, i, j, k = map(int, fields[:6])
        values = [print_interval(token) for token in fields[6:]]
        if len(values) != 12:
            raise ValueError("STORED_PAIR numeric field count mismatch")
        oldcarrier, newcarrier, qcandidate, ncandidate, qstored, nstored = values[:6]
        if not (qstored[0] == 0 and nstored[0] == 0
                and qcandidate[0] > 0 and ncandidate[0] > 0):
            continue
        # md = newcarrier * (-1/rdnw) / (g*rdx*rdy*msftx*msfty),
        # evaluated using same-event list-directed values and pinned gravity.
        density, rdnw, msftx, msfty, rdx, rdy = values[6:12]
        if not (newcarrier[1] > 0 and rdnw[2] < 0 and msftx[1] > 0
                and msfty[1] > 0 and rdx[1] > 0 and rdy[1] > 0):
            raise ValueError("unexpected sign/zero in same-event geometry values")
        def weight(newc: Decimal, rd: Decimal, mx: Decimal, my: Decimal,
                   dx: Decimal, dy: Decimal) -> Decimal:
            return newc * (-Decimal(1) / rd) / (gravity * dx * dy * mx * my)

        with localcontext() as ctx:
            ctx.prec = 80
            md_center = weight(newcarrier[0], rdnw[0], msftx[0], msfty[0], rdx[0], rdy[0])
        with localcontext() as ctx:
            ctx.prec = 80
            ctx.rounding = ROUND_FLOOR
            factor_low = -Decimal(1) / rdnw[1]
            numerator_low = newcarrier[1] * factor_low
            denominator_high = gravity * rdx[2] * rdy[2] * msftx[2] * msfty[2]
            md_low = numerator_low / denominator_high
        with localcontext() as ctx:
            ctx.prec = 80
            ctx.rounding = ROUND_CEILING
            factor_high = -Decimal(1) / rdnw[2]
            numerator_high = newcarrier[2] * factor_high
            denominator_low = gravity * rdx[1] * rdy[1] * msftx[1] * msfty[1]
            md_high = numerator_high / denominator_low
        with localcontext() as ctx:
            ctx.prec = 80
            ctx.rounding = ROUND_FLOOR
            q_low = -(qcandidate[2] * md_high)
            n_low = -(ncandidate[2] * md_high)
            v_low = -(ncandidate[2] * md_high)
        with localcontext() as ctx:
            ctx.prec = 80
            ctx.rounding = ROUND_CEILING
            q_high = -(qcandidate[1] * md_low)
            n_high = -(ncandidate[1] * md_low)
            v_high = -(ncandidate[1] * md_low)
        with localcontext() as ctx:
            ctx.prec = 80
            q_values = (-qcandidate[0] * md_center, q_low, q_high)
            n_values = (-ncandidate[0] * md_center, n_low, n_high)
            v_values = (-ncandidate[0] * md_center, v_low, v_high)
        key = (step, rk, pair)
        moment_name = "signed_bulk_volume_m3" if pair == 4 else "signed_n_count"
        row = groups.setdefault(key, {
            "step": step, "rk": rk, "pair": pair, "event_count": 0,
            "signed_q_kg_center": Decimal(0), "signed_q_kg_low": Decimal(0),
            "signed_q_kg_high": Decimal(0),
            f"{moment_name}_center": Decimal(0), f"{moment_name}_low": Decimal(0),
            f"{moment_name}_high": Decimal(0),
        })
        row["event_count"] += 1
        for name, value in (("signed_q_kg", q_values),
                            (("signed_bulk_volume_m3" if pair == 4 else "signed_n_count"),
                             (v_values if pair == 4 else n_values))):
            with localcontext() as ctx:
                ctx.prec = 80
                row[f"{name}_center"] += value[0]
            with localcontext() as ctx:
                ctx.prec = 80
                ctx.rounding = ROUND_FLOOR
                row[f"{name}_low"] += value[1]
            with localcontext() as ctx:
                ctx.prec = 80
                ctx.rounding = ROUND_CEILING
                row[f"{name}_high"] += value[2]

    def dec(value: Decimal, bound: bool = False) -> str:
        return str(value) if bound else format(value, ".16E")

    return {
        "run_root": str(run_root), "receipt_path": str(receipt_path),
        "receipt_sha256": sha256(receipt_path), "arm": receipt["arm"],
        "preflight_path": str(preflight_path), "preflight_sha256": sha256(preflight_path),
        "duration_seconds": preflight["duration_seconds"],
        "status": receipt["status"], "candidate_executable_sha256": receipt["executed_executable_sha256"],
        "candidate_wrfinput_sha256": receipt.get("candidate_wrfinput_sha256"),
        "candidate_wrfbdy_sha256": receipt.get("candidate_wrfbdy_sha256"),
        "source_receipt_sha256": receipt.get("source_receipt_sha256"),
        "joint_storage_ledger": str(ledger),
        "ledger_compressed_sha256": artifact["compressed_sha256"],
        "ledger_compressed_bytes": artifact["compressed_bytes"],
        "ledger_raw_sha256": artifact["sha256"], "ledger_raw_bytes": artifact["bytes"],
        "candidate_build_receipt_path": str(build_path),
        "candidate_build_receipt_sha256": sha256(build_path),
        "module_em_source_path": str(module_path), "module_em_source_sha256": module_hash,
        "solve_em_source_path": str(caller_path), "solve_em_source_sha256": caller_hash,
        "ledger_rows_scanned": ledger_rows_scanned,
        "joint_absence_group_count": len(groups),
        "joint_absence_event_count": sum(row["event_count"] for row in groups.values()),
        "pair4_joint_absence_event_count": sum(row["event_count"] for row in groups.values()
                                                if row["pair"] == 4),
        "pair4_bulk_volume_assessment": {
            "status": "NO_MATCHED_PAIR4_EVENTS",
            "event_set_contribution_m3": "0" if not any(key[2] == 4 for key in groups) else None,
            "unit_basis": "QIB is rime-volume mixing ratio in m3/kg-dry; pair-4 signed volume is -candidate_QIB * md directly. Source limits graupel bulk density to 100..900 kg/m3.",
        },
        "groups": [{key: (dec(value, key.endswith("_low") or key.endswith("_high"))
                            if isinstance(value, Decimal) else value)
                    for key, value in row.items()} for _, row in sorted(groups.items())],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off", type=Path, required=True)
    parser.add_argument("--coupled", type=Path, required=True)
    parser.add_argument("--constants", type=Path, default=Path("/var/tmp/pr87_history_constants_20261019/receipt.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sha256(args.constants) != EXPECTED_GRAVITY_RECEIPT_SHA256:
        raise SystemExit("gravity receipt SHA-256 differs from pr87_native_history pin")
    gravity_receipt = json.loads(args.constants.read_text())
    gravity = Decimal.from_float(float(gravity_receipt["constants_real32_promoted_to_real64"]["g"]))
    if gravity != EXPECTED_GRAVITY:
        raise SystemExit("gravity value differs from pr87_native_history pin")
    results = [load_run(args.off, gravity), load_run(args.coupled, gravity)]
    if [row["arm"] for row in results] != ["OFF", "COUPLED"]:
        raise SystemExit("expected OFF and COUPLED receipts")
    result = {
        "schema": "pr90_joint_absence_mass_audit_v1",
        "audit_script_path": str(Path(__file__).resolve()),
        "audit_script_sha256": sha256(Path(__file__).resolve()),
        "reproduction_command": "python3 docs/evidence/pr90_rain_roundtrip_20261019/science/joint_absence/audit_joint_absence.py --off /var/tmp/pr89_OFF_120s_c5_20261019 --coupled /var/tmp/pr89_COUPLED_120s_c5_20261019 --output docs/evidence/pr90_rain_roundtrip_20261019/science/joint_absence/result.json",
        "scope": "C5 OFF/COUPLED 120 s only; joint-absence events where stored Q=N=0 and both same-event candidate moments are positive.",
        "gravity": {"receipt_path": str(args.constants), "receipt_sha256": sha256(args.constants),
                    "g_m_s2_promoted_real32": str(gravity)},
        "mass_conversion": "md = newcarrier * (-1/rdnw) / (g*rdx*rdy*msftx*msfty), from same STORED_PAIR event fields.",
        "signed_change": "stored minus candidate; Q kg = -candidate_Q * md; pairs 1-3 N count = -candidate_N * md; pair 4 QIB volume m3 = -candidate_QIB * md.",
        "rounding_bounds": "Each default-WRITE decimal is treated as a nearest-rounded value with a half-last-printed-digit interval. 80-digit Decimal interval operations round lows toward -Infinity and highs toward +Infinity through the event weight, products, grouped sums, and exact decimal endpoint serialization.",
        "limitations": ["These are approximate totals reconstructed from decimal-rounded ledger fields, not exact binary values.",
                        "Bounds cover decimal print rounding only; they do not cover ordinary REAL32 candidate/storage rounding or other source/transport residuals.",
                        "No sum over RK substages is presented as a final budget.",
                        "Pair 4 maps to QG/QIB. Source identifies QIB as rime-volume mixing ratio (m3/kg-dry) and bounds graupel bulk density to 100..900 kg/m3; multiplying QIB by md gives m3 directly. Neither run has a matched pair-4 event."],
        "runs": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "off_joint_absence_events": results[0]["joint_absence_event_count"],
                      "coupled_joint_absence_events": results[1]["joint_absence_event_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
