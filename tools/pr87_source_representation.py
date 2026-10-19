#!/usr/bin/env python3
"""Validate and summarize PR87 source-representation ledger records."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path


_TAGS = ("SOURCE_REPRESENTATION_META", "SOURCE_COLUMN", "SOURCE_TOTAL",
         "SOURCE_LATER_TOTAL")
_METRICS = ("proposal", "represented", "signed_delta", "l1_delta", "max_abs_delta")


def _records(text: str) -> list[tuple[str, list[str]]]:
    records: list[tuple[str, list[str]]] = []
    tag: str | None = None
    fields: list[str] = []
    for line in text.splitlines():
        words = line.split()
        if words and words[0] in _TAGS:
            if tag is not None:
                records.append((tag, fields))
            tag, fields = words[0], words[1:]
        elif tag is not None:
            fields.extend(words)
    if tag is not None:
        records.append((tag, fields))
    return records


def _integer(value: str, context: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{context}: expected integer, got {value!r}") from exc


def _real(value: str, context: str) -> float:
    try:
        result = float(value.replace("D", "E").replace("d", "e"))
    except ValueError as exc:
        raise ValueError(f"{context}: expected real, got {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{context}: nonfinite value {value!r}")
    return result


def _pairs(values: list[float]) -> dict[str, list[float]]:
    return {name: values[index * 2:index * 2 + 2]
            for index, name in enumerate(_METRICS)}


def _roundoff_bound(operands: list[float], operations: int) -> float:
    """Bound REAL64 accumulation/formatting error from operand scale, not delta scale."""
    scale = math.fsum(abs(value) for value in operands)
    return 64.0 * math.ulp(1.0) * max(operations, 1) * max(scale, 1.0e-300)


def _check_close(actual: float, expected: float, bound: float, context: str) -> None:
    if abs(actual - expected) > bound:
        raise ValueError(f"{context}: {actual:.17g} != {expected:.17g} within {bound:.3g}")


def _check_metrics(metrics: dict[str, list[float]], context: str,
                   arithmetic_bound: float) -> None:
    for moment, proposal, represented, delta, l1, maximum in zip(
        ("Q", "N"), metrics["proposal"], metrics["represented"],
        metrics["signed_delta"], metrics["l1_delta"], metrics["max_abs_delta"], strict=True,
    ):
        _check_close(delta, represented - proposal, arithmetic_bound,
                     f"{context} {moment} signed delta")
        if l1 + arithmetic_bound < abs(delta):
            raise ValueError(f"{context} {moment} L1 delta is smaller than signed delta")
        if maximum < 0.0 or maximum > l1 + arithmetic_bound:
            raise ValueError(f"{context} {moment} maximum absolute delta is inconsistent with L1")


def summarize_source_representation(source: str, *, source_path: str = "<memory>",
                                    source_sha256: str | None = None) -> dict:
    """Parse list-directed Fortran rows and check identity and aggregation invariants."""
    records = _records(source)
    metadata: set[tuple[int, int]] = set()
    columns: dict[tuple[int, int, int], list[dict]] = {}
    column_coordinates: dict[tuple[int, int, int], set[tuple[int, int]]] = {}
    totals: dict[tuple[int, int, int], dict] = {}
    later_totals: dict[tuple[int, int, int], dict] = {}

    for tag, fields in records:
        if tag == "SOURCE_REPRESENTATION_META":
            if len(fields) < 2:
                raise ValueError("SOURCE_REPRESENTATION_META lacks timestep/RK identity")
            identity = (_integer(fields[0], tag), _integer(fields[1], tag))
            if identity in metadata:
                raise ValueError(f"duplicate source-representation metadata for {identity}")
            metadata.add(identity)
            continue

        if tag == "SOURCE_COLUMN":
            if len(fields) != 18:
                raise ValueError(f"SOURCE_COLUMN expected 18 fields, got {len(fields)}")
            timestep, rk, pair, x, y, changed, max_k_q, max_k_n = (
                _integer(value, tag) for value in fields[:8]
            )
            key = (timestep, rk, pair)
            if pair not in (1, 2):
                raise ValueError(f"unsupported source pair identity {pair}")
            if key in totals:
                raise ValueError(f"SOURCE_COLUMN appears after a total for {key}")
            rows = columns.setdefault(key, [])
            cell_key = (x, y)
            coordinates = column_coordinates.setdefault(key, set())
            if cell_key in coordinates:
                raise ValueError(f"duplicate SOURCE_COLUMN cell {key + cell_key}")
            coordinates.add(cell_key)
            if changed <= 0 or max_k_q < 0 or max_k_n < 0:
                raise ValueError(f"invalid SOURCE_COLUMN counts/indexes for {key + cell_key}")
            values = [_real(value, tag) for value in fields[8:]]
            metrics = _pairs(values)
            rows.append({"x": x, "y": y, "changed": changed,
                         "max_k": [max_k_q, max_k_n], **metrics})
            continue

        if tag == "SOURCE_TOTAL":
            if len(fields) != 15:
                raise ValueError(f"SOURCE_TOTAL expected 15 fields, got {len(fields)}")
            timestep, rk, pair, cells, changed = (_integer(value, tag) for value in fields[:5])
            key = (timestep, rk, pair)
            if pair not in (1, 2):
                raise ValueError(f"unsupported source pair identity {pair}")
            if key in totals:
                raise ValueError(f"duplicate SOURCE_TOTAL for {key}")
            if cells <= 0 or changed < 0 or changed > cells:
                raise ValueError(f"invalid SOURCE_TOTAL counts for {key}")
            metrics = _pairs([_real(value, tag) for value in fields[5:]])
            totals[key] = {"cells": cells, "changed_cells": changed, **metrics}
            continue

        if tag == "SOURCE_LATER_TOTAL":
            if len(fields) != 7:
                raise ValueError(f"SOURCE_LATER_TOTAL expected 7 fields, got {len(fields)}")
            timestep, rk, pair = (_integer(value, tag) for value in fields[:3])
            key = (timestep, rk, pair)
            if pair not in (1, 2):
                raise ValueError(f"unsupported later-source pair identity {pair}")
            if key in later_totals:
                raise ValueError(f"duplicate SOURCE_LATER_TOTAL for {key}")
            amounts = [_real(value, tag) for value in fields[3:5]]
            residuals = [_real(value, tag) for value in fields[5:7]]
            later_totals[key] = {
                "dt_later_source_amount": amounts,
                "max_abs_r64_identity_residual": residuals,
                "aggregation_claim": False,
            }

    if not metadata or not totals:
        raise ValueError("source-representation ledger contains no complete metadata/total records")
    total_scopes = {(step, rk) for step, rk, _ in totals}
    if metadata != total_scopes:
        raise ValueError(
            "source-representation metadata scopes do not match completed total scopes: "
            f"metadata-only={sorted(metadata - total_scopes)}, totals-without-metadata={sorted(total_scopes - metadata)}"
        )
    if set(columns) - set(totals):
        raise ValueError(f"SOURCE_COLUMN groups lack totals: {sorted(set(columns) - set(totals))}")
    missing_columns = set(totals) - set(columns)
    for key in missing_columns:
        total = totals[key]
        if total["changed_cells"] != 0 or any(
            value != 0.0 for metric in ("signed_delta", "l1_delta", "max_abs_delta")
            for value in total[metric]
        ):
            raise ValueError(f"SOURCE_TOTAL group lacks changed columns: {key}")
        columns[key] = []
    if any((step, rk) not in metadata for step, rk, _ in totals):
        raise ValueError("source-representation row timestep/RK does not match metadata")
    if any((step, rk) not in metadata for step, rk, _ in columns):
        raise ValueError("source column timestep/RK does not match metadata")
    if any((step, rk) not in metadata for step, rk, _ in later_totals):
        raise ValueError("later-source timestep/RK does not match metadata")
    if set(later_totals) - set(totals):
        raise ValueError(f"SOURCE_LATER_TOTAL groups lack source totals: {sorted(set(later_totals) - set(totals))}")

    groups = []
    for key in sorted(totals):
        rows = columns[key]
        total = totals[key]
        if len(rows) > total["cells"]:
            raise ValueError(f"more SOURCE_COLUMN rows than cells for {key}")
        if sum(row["changed"] for row in rows) != total["changed_cells"]:
            raise ValueError(f"changed-cell count does not aggregate for {key}")
        operands = [value for metric in ("proposal", "represented")
                    for value in total[metric]]
        operands.extend(value for row in rows for metric in ("proposal", "represented")
                        for value in row[metric])
        arithmetic_bound = _roundoff_bound(operands, total["cells"])
        _check_metrics(total, f"SOURCE_TOTAL {key}", arithmetic_bound)
        for row in rows:
            _check_metrics(row, f"SOURCE_COLUMN {key} {(row['x'], row['y'])}", arithmetic_bound)
        for metric in ("signed_delta", "l1_delta"):
            for moment_index, moment in enumerate(("Q", "N")):
                aggregate = math.fsum(row[metric][moment_index] for row in rows)
                aggregation_bound = _roundoff_bound(
                    [total[metric][moment_index], *(row[metric][moment_index] for row in rows)],
                    total["cells"],
                )
                _check_close(total[metric][moment_index], aggregate, aggregation_bound,
                             f"SOURCE_TOTAL {key} {metric} {moment} aggregate")
        for moment_index, moment in enumerate(("Q", "N")):
            maximum = max((row["max_abs_delta"][moment_index] for row in rows), default=0.0)
            _check_close(total["max_abs_delta"][moment_index], maximum,
                         _roundoff_bound([total["max_abs_delta"][moment_index], maximum], 1),
                         f"SOURCE_TOTAL {key} max_abs_delta {moment}")
        unreported = []
        for moment_index, moment in enumerate(("Q", "N")):
            emitted_proposal = math.fsum(row["proposal"][moment_index] for row in rows)
            emitted_represented = math.fsum(row["represented"][moment_index] for row in rows)
            proposal_remainder = total["proposal"][moment_index] - emitted_proposal
            represented_remainder = total["represented"][moment_index] - emitted_represented
            roundoff_bound = _roundoff_bound(
                [total["proposal"][moment_index], total["represented"][moment_index],
                 emitted_proposal, emitted_represented], total["cells"]
            )
            if abs(proposal_remainder - represented_remainder) > roundoff_bound:
                raise ValueError(
                    f"SOURCE_TOTAL {key} unreported {moment} proposal/represented "
                    f"amounts differ by more than operand-scale roundoff"
                )
            unreported.append(proposal_remainder)
        groups.append({"timestep": key[0], "rk": key[1], "pair": key[2],
                       **total, "column_rows": len(rows),
                       "later_source": later_totals.get(key),
                       "unreported_equal_source_amount": unreported,
                       "unreported_amounts_equal_within_roundoff": True,
                       "invariants_verified": True})

    return {
        "schema": "pr87_source_representation_summary_v1",
        "status": "PASS",
        "source_ledger_path": source_path,
        "source_ledger_sha256": source_sha256,
        "quantity_basis": "pressure_carrier_amounts",
        "arithmetic_check": "REAL64 operand-scale bound: 64*epsilon*active_cells*sum(abs(proposal,represented))",
        "physical_mass_or_energy_claim": False,
        "later_source_amounts_are_separately_reported_not_aggregated": True,
        "groups": groups,
    }


def summarize_file(path: Path) -> dict:
    raw = path.read_bytes()
    decoded = gzip.decompress(raw) if path.suffix == ".gz" else raw
    source = decoded.decode("utf-8")
    return summarize_source_representation(
        source, source_path=str(path.resolve()),
        source_sha256=hashlib.sha256(raw).hexdigest(),
    ) | {
        "source_ledger_decoded_sha256": hashlib.sha256(decoded).hexdigest(),
        "source_ledger_is_gzip": path.suffix == ".gz",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, help="raw pr87_source_representation.raw ledger")
    parser.add_argument("--receipt", type=Path, help="new JSON receipt path; existing files are refused")
    args = parser.parse_args()
    if args.receipt is not None and args.receipt.exists():
        parser.error(f"receipt already exists; choose a new path: {args.receipt}")
    summary = summarize_file(args.ledger)
    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.receipt is None:
        print(rendered, end="")
    else:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(rendered, encoding="utf-8")
        print(f"{summary['status']}: {args.receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
