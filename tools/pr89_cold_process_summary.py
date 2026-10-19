#!/usr/bin/env python3
"""Compact, source-bound summary for current KDM6 cold-process requests."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any


TAG = "PR89_KDM6_COLD_SUMMARY"
SUMMARY_HEADER = (
    "# PR89_KDM6_COLD_SUMMARY v1 step,lat,loops,cell_transactions,raw_cell_rows,"
    "unrecorded_transactions; group-major NG,AUT,G; stage-major proposed,applied,deferred; "
    "each stage signed,half-L1; units kg m-2 SUM_COLUMNS; weight=DEN*DELZ; "
    "half-L1=0.5*sum(abs(Q(5)),abs(QV))*DEN*DELZ; diagnostic request activity, "
    "not reaction throughput; no grid-area/global kg"
)
RAW_HEADER = "# PR85_KDM6_COLD fields:"
GROUPS = ("NG", "AUT", "G")
STAGES = ("proposed", "applied", "deferred")
METRICS = ("signed_kg_m2", "half_l1_kg_m2")


class SummaryError(ValueError):
    """Raised when a cold-process trace violates its declared row contract."""


def _open_text(path: Path) -> AbstractContextManager[Any]:
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def add_cold_summary(source: str, expected_sha256: str) -> str:
    """Add a compact per-KDM62D-call accumulator to a precisely bound source."""
    actual = hashlib.sha256(source.encode()).hexdigest()
    if actual != expected_sha256:
        raise SummaryError(f"unexpected KDM6 source hash: {actual}")
    if "PR89_KDM6_COLD_SUMMARY" in source:
        raise SummaryError("cold summary instrumentation already present")

    declaration_anchor = "   integer                            :: pr85_cold_unit,pr85_cold_ios\n"
    declarations = (
        "   integer :: pr89_cold_unit,pr89_cold_ios,pr89_cold_transactions\n"
        "   integer :: pr89_cold_group,pr89_cold_stage\n"
        "   real(kind=8) :: pr89_cold_water(2,3,3),pr89_cold_weight\n"
        "   real(kind=8) :: pr89_cold_q(5),pr89_cold_qv,pr89_cold_alpha,pr89_cold_scale\n"
        "   real(kind=8) :: pr89_cold_signed,pr89_cold_half_l1\n"
    )
    if source.count(declaration_anchor) != 1:
        raise SummaryError("KDM62D cold-ledger declaration anchor missing or ambiguous")
    source = source.replace(declaration_anchor, declaration_anchor + declarations, 1)

    init_anchor = "   if(delt.le.dtcldcr) dtcld = delt\n"
    init = """   pr89_cold_water=0.0d0
   pr89_cold_transactions=0
   open(newunit=pr89_cold_unit,file='pr89_kdm6_cold_summary.raw', &
        form='formatted',status='unknown',position='append',action='write', &
        iostat=pr89_cold_ios)
   if (pr89_cold_ios.ne.0) error stop 'PR89 cold summary open failed'
   write(pr89_cold_unit,'(a)',iostat=pr89_cold_ios) &
        '# PR89_KDM6_COLD_SUMMARY v1 step,lat,loops,cell_transactions,raw_cell_rows,unrecorded_transactions; '// &
        'group-major NG,AUT,G; stage-major proposed,applied,deferred; each stage signed,half-L1; '// &
        'units kg m-2 SUM_COLUMNS; weight=DEN*DELZ; half-L1=0.5*sum(abs(Q(5)),abs(QV))*DEN*DELZ; '// &
        'diagnostic request activity, not reaction throughput; no grid-area/global kg'
   if (pr89_cold_ios.ne.0) error stop 'PR89 cold summary header failed'
"""
    if source.count(init_anchor) != 1:
        raise SummaryError("KDM62D timestep setup anchor missing or ambiguous")
    source = source.replace(init_anchor, init_anchor + init, 1)

    row_anchor = """            if (.false.) then
            write(pr85_cold_unit,'(a,8i8,1x,l1,1p,*(1x,e24.16))',iostat=pr85_cold_ios) &
                 'PR85_KDM6_COLD',i,lat,k,loop,rain_ng_search_status, &
"""
    collector = """            ! PR89: same-call column water measure, DEN*DELZ (kg m-2).
            ! KDM62D has no horizontal area argument; do not claim grid-area totals.
            pr89_cold_weight=DBLE(dry_carrier_density(i,k))*DBLE(delz(i,k))
            pr89_cold_transactions=pr89_cold_transactions+1
            do pr89_cold_group=1,3
              select case(pr89_cold_group)
              case(1)
                pr89_cold_q=DBLE(rain_ng_q_process)
                pr89_cold_qv=DBLE(rain_ng_qv_process)
                pr89_cold_alpha=DBLE(rain_ng_alpha)
              case(2)
                pr89_cold_q=DBLE(rain_aut_q_process)
                pr89_cold_qv=0.0d0
                pr89_cold_alpha=DBLE(rain_aut_alpha)
              case(3)
                pr89_cold_q=DBLE(rain_q_process_request)
                pr89_cold_qv=DBLE(rain_g_qv_process)
                pr89_cold_alpha=DBLE(rain_process_alpha)
              end select
              do pr89_cold_stage=1,3
                select case(pr89_cold_stage)
                case(1)
                  pr89_cold_scale=1.0d0
                case(2)
                  pr89_cold_scale=pr89_cold_alpha
                case(3)
                  pr89_cold_scale=1.0d0-pr89_cold_alpha
                end select
                pr89_cold_signed=(SUM(pr89_cold_q)+pr89_cold_qv)*pr89_cold_scale
                pr89_cold_half_l1=0.5d0*(SUM(ABS(pr89_cold_q))+ABS(pr89_cold_qv))* &
                     ABS(pr89_cold_scale)
                pr89_cold_water(1,pr89_cold_stage,pr89_cold_group)= &
                     pr89_cold_water(1,pr89_cold_stage,pr89_cold_group)+ &
                     pr89_cold_signed*pr89_cold_weight
                pr89_cold_water(2,pr89_cold_stage,pr89_cold_group)= &
                     pr89_cold_water(2,pr89_cold_stage,pr89_cold_group)+ &
                     pr89_cold_half_l1*pr89_cold_weight
              enddo
            enddo
"""
    if source.count(row_anchor) != 1:
        raise SummaryError("cold-process row anchor missing or ambiguous")
    source = source.replace(row_anchor, collector + row_anchor, 1)

    close_anchor = """   if (pr67_trace_this_call) then
     close(pr85_psd_unit,iostat=pr85_psd_ios)
"""
    output = """   write(pr89_cold_unit,'(a,6i10,1p,*(1x,e24.16))',iostat=pr89_cold_ios) &
        'PR89_KDM6_COLD_SUMMARY',pr87_model_timestep,lat,loops, &
        pr89_cold_transactions,0,pr89_cold_transactions,pr89_cold_water
   if (pr89_cold_ios.ne.0) error stop 'PR89 cold summary write failed'
   close(pr89_cold_unit,iostat=pr89_cold_ios)
   if (pr89_cold_ios.ne.0) error stop 'PR89 cold summary close failed'
"""
    if source.count(close_anchor) != 1:
        raise SummaryError("KDM62D post-loop summary anchor missing or ambiguous")
    return source.replace(close_anchor, output + close_anchor, 1)


def _finite_floats(fields: list[str], line_number: int) -> list[float]:
    try:
        values = [float(item.replace("D", "E").replace("d", "e")) for item in fields]
    except ValueError as exc:
        raise SummaryError(f"line {line_number}: invalid summary number") from exc
    if not all(math.isfinite(value) for value in values):
        raise SummaryError(f"line {line_number}: nonfinite summary number")
    return values


def parse_summary(path: Path) -> dict[str, Any]:
    """Read compact summary rows and validate count and schema consistency."""
    if path.is_symlink() or not path.is_file():
        raise SummaryError(f"summary is not a regular file: {path}")
    headers = 0
    rows: list[dict[str, Any]] = []
    seen_calls: set[tuple[int, int]] = set()
    try:
        with _open_text(path) as stream:
            for line_number, line in enumerate(stream, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    if stripped == SUMMARY_HEADER:
                        headers += 1
                    continue
                fields = stripped.split()
                if fields[0] != TAG or len(fields) != 25:
                    raise SummaryError(f"line {line_number}: malformed {TAG} record")
                try:
                    step, lat, loops, transactions, raw_rows, unrecorded = map(int, fields[1:7])
                except ValueError as exc:
                    raise SummaryError(f"line {line_number}: invalid summary count") from exc
                if step < 0 or loops < 1 or min(transactions, raw_rows, unrecorded) < 0:
                    raise SummaryError(f"line {line_number}: negative or invalid count")
                if raw_rows > transactions or unrecorded != transactions - raw_rows:
                    raise SummaryError(f"line {line_number}: row and unrecorded counts disagree")
                key = (step, lat)
                if key in seen_calls:
                    raise SummaryError(f"line {line_number}: duplicate timestep/latitude call {key}")
                seen_calls.add(key)
                values = _finite_floats(fields[7:], line_number)
                metrics: dict[str, dict[str, dict[str, float]]] = {}
                offset = 0
                for group in GROUPS:
                    metrics[group] = {}
                    for stage in STAGES:
                        metrics[group][stage] = {
                            METRICS[0]: values[offset], METRICS[1]: values[offset + 1]
                        }
                        offset += 2
                rows.append({"timestep": step, "lat": lat, "loops": loops,
                             "cell_transactions": transactions, "raw_cell_rows": raw_rows,
                             "unrecorded_transactions": unrecorded, "groups": metrics})
    except (OSError, EOFError, UnicodeError) as exc:
        raise SummaryError(f"cannot read summary text: {path}") from exc
    if headers == 0:
        raise SummaryError("summary header is missing")
    if len(rows) != headers:
        raise SummaryError("summary header/data record counts disagree")
    totals: dict[str, dict[str, dict[str, float]]] = {
        group: {stage: {metric: 0.0 for metric in METRICS} for stage in STAGES}
        for group in GROUPS
    }
    for row in rows:
        for group in GROUPS:
            for stage in STAGES:
                for metric in METRICS:
                    totals[group][stage][metric] += row["groups"][group][stage][metric]
    return {"status": "EVALUATED" if rows else "NOT_EVALUATED",
            "summary_header_records": headers, "summary_data_records": len(rows),
            "call_records": len(rows), "timesteps": sorted({r["timestep"] for r in rows}),
            "cell_transactions": sum(r["cell_transactions"] for r in rows),
            "raw_cell_rows": sum(r["raw_cell_rows"] for r in rows),
            "unrecorded_transactions": sum(r["unrecorded_transactions"] for r in rows),
            "weight_units": "kg m-2 SUM_COLUMNS; no grid-area/global kg",
            "definition": "signed=sum(Q(5)+QV); half-L1=0.5*sum(abs(Q(5)),abs(QV)); per stage",
            "groups": totals, "calls": rows}


def inspect_current_ledger(path: Path) -> dict[str, Any]:
    """Report coverage of the current verbose cell ledger without old replay data."""
    if path.is_symlink() or not path.is_file():
        raise SummaryError(f"cold ledger is not a regular file: {path}")
    headers = 0
    data_records = 0
    try:
        with _open_text(path) as stream:
            for line_number, line in enumerate(stream, 1):
                stripped = line.strip()
                if stripped.startswith(RAW_HEADER):
                    headers += 1
                elif stripped.startswith("PR85_KDM6_COLD"):
                    fields = stripped.split()
                    if len(fields) != 217:
                        raise SummaryError(f"line {line_number}: malformed cold cell record")
                    if fields[9] not in ("T", "F"):
                        raise SummaryError(f"line {line_number}: malformed stored-noop flag")
                    _finite_floats(fields[10:], line_number)
                    data_records += 1
    except (OSError, EOFError, UnicodeError) as exc:
        raise SummaryError(f"cannot read cold ledger text: {path}") from exc
    if data_records and not headers:
        raise SummaryError("cold cell records exist without a recognized header")
    return {"status": "NOT_EVALUATED" if data_records == 0 else "CELL_RECORDS_PRESENT",
            "ledger_header_records": headers, "ledger_data_records": data_records,
            "call_records": 0, "source": "current supplied ledger only"}


def summarize(ledger_path: Path, summary_path: Path | None = None) -> dict[str, Any]:
    """Prefer current compact rows; otherwise report the supplied raw-ledger coverage."""
    if summary_path is not None and summary_path.exists():
        result = parse_summary(summary_path)
        result["source"] = str(summary_path)
        return result
    result = inspect_current_ledger(ledger_path)
    result["source"] = str(ledger_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, help="current pr85_kdm6_cold_budget.raw")
    parser.add_argument("--summary", type=Path, help="compact PR89 summary file")
    parser.add_argument("--output", type=Path, help="write JSON instead of stdout")
    args = parser.parse_args()
    result = summarize(args.ledger, args.summary)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
