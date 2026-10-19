#!/usr/bin/env python3
"""Correct and validate the D2 T7 packet against raw producer artifacts."""
from __future__ import annotations

import argparse
import decimal
import gzip
import hashlib
import json
import math
import struct
from pathlib import Path

DECIMAL = decimal.Decimal
TRACE_TO_LEDGER = {
    "rho": ("parameters", "rho_dry"), "T": ("bulk_before", "T"),
    "Qc": ("q_before", "Qc"), "Nc": ("n_before", "Nc"),
    "Qi": ("q_before", "Qi"), "Ni": ("n_before", "Ni"),
    "Qr": ("q_before", "Qr"), "Nr": ("n_before", "Nr"),
    "Qs": ("q_before", "Qs"), "Qg": ("q_before", "Qg"),
    "Nccn": ("bulk_before", "CCN3"), "Bg": ("bulk_before", "BG"),
    "Qv": ("bulk_before", "QV"),
}
TRACE_AFTER_TO_LEDGER = {
    **{key: value for key, value in TRACE_TO_LEDGER.items() if key != "rho"},
    "rho": ("parameters", "rho_dry"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def value(printed: str, kind: str) -> dict[str, str]:
    result = {"printed": printed, "source_type": kind}
    if kind == "REAL32":
        rounded = struct.unpack(">f", struct.pack(">f", float(printed)))[0]
        result["hex32"] = struct.pack(">f", rounded).hex().upper()
    return result


def ledger_row(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="ascii") as stream:
        rows = [line.split() for line in stream
                if line.startswith("WARM ") and line.split()[1:4] == ["193", "222", "4"]]
    if len(rows) != 1:
        raise ValueError(f"expected one target warm row, found {len(rows)}")
    row = rows[0]
    if len(row) != 116:
        raise ValueError(f"target warm row has {len(row)} tokens, expected 116")
    return row


def trace_rows(path: Path) -> dict[str, dict[str, str]]:
    wanted = {"WARM_BEFORE_COMMIT", "WARM_AFTER_COMMIT"}
    found: dict[str, dict[str, str]] = {}
    with gzip.open(path, "rt", encoding="ascii") as stream:
        for line in stream:
            fields = line.split()
            if len(fields) != 21 or fields[0] != "PR90_T7_PRODUCER":
                continue
            stage = fields[1]
            if stage in wanted:
                found[stage] = dict(zip(
                    ("rho", "T", "Qc", "Nc", "Qi", "Ni", "Qr", "Nr", "Qs", "Qg", "Nccn", "Bg", "Qv"),
                    fields[7:20], strict=True))
    if set(found) != wanted:
        raise ValueError(f"missing target warm trace states: {sorted(wanted - found.keys())}")
    return found


def verify_decimal_interval(item: dict[str, str]) -> None:
    """Require the E24.16 decimal rounding interval to select one source float."""
    printed = DECIMAL(item["printed"])
    exponent = int(item["printed"].split("E")[1])
    half_unit = DECIMAL(5).scaleb(exponent - 17)
    lower, upper = printed - half_unit, printed + half_unit
    kind = item["source_type"]
    if kind == "REAL32":
        bits = int(item["hex32"], 16)
        center = DECIMAL.from_float(struct.unpack(">f", struct.pack(">I", bits))[0])
        if bits == 0:
            prev_bits, next_bits = 0x80000001, 1
        elif bits == 0x80000000:
            prev_bits, next_bits = 0x80000001, 1
        else:
            prev_bits = bits + 1 if bits & 0x80000000 else bits - 1
            next_bits = bits - 1 if bits & 0x80000000 else bits + 1
        prev = DECIMAL.from_float(struct.unpack(">f", struct.pack(">I", prev_bits))[0])
        nxt = DECIMAL.from_float(struct.unpack(">f", struct.pack(">I", next_bits))[0])
        lo, hi = sorted((prev, center)), sorted((center, nxt))
        cell_low, cell_high = (lo[0] + lo[1]) / 2, (hi[0] + hi[1]) / 2
    else:
        center_float = float(printed)
        center = DECIMAL.from_float(center_float)
        prev = DECIMAL.from_float(math.nextafter(center_float, -math.inf))
        nxt = DECIMAL.from_float(math.nextafter(center_float, math.inf))
        cell_low, cell_high = (prev + center) / 2, (center + nxt) / 2
    if printed == 0 and center == 0:
        if lower < 0 < upper:
            return
    if not (cell_low < lower <= upper < cell_high):
        raise ValueError(f"E24.16 interval does not uniquely identify {kind} value {item}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="initial target packet JSON")
    parser.add_argument("warm_ledger_gz", type=Path)
    parser.add_argument("producer_trace_gz", type=Path)
    parser.add_argument("build_receipt", type=Path)
    parser.add_argument("run_receipt", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    packet = json.loads(args.packet.read_text())
    row = ledger_row(args.warm_ledger_gz)
    fields = packet["warm_fields"]
    # Source column order is BGbefore,BGafter,Tbefore,Tafter,QVbefore,QVafter,
    # CCN3before,CCN3after (tokens 64 through 71); these values are interleaved.
    bulk_before = dict(zip(("BG", "T", "QV", "CCN3"), (row[64], row[66], row[68], row[70]), strict=True))
    bulk_after = dict(zip(("BG", "T", "QV", "CCN3"), (row[65], row[67], row[69], row[71]), strict=True))
    fields["bulk_before"] = {name: value(text, "REAL32") for name, text in bulk_before.items()}
    fields["bulk_after"] = {name: value(text, "REAL32") for name, text in bulk_after.items()}

    trace = trace_rows(args.producer_trace_gz)
    for stage, mapping in (("WARM_BEFORE_COMMIT", TRACE_TO_LEDGER),
                           ("WARM_AFTER_COMMIT", TRACE_AFTER_TO_LEDGER)):
        is_after = stage == "WARM_AFTER_COMMIT"
        for trace_name, (group, field) in mapping.items():
            if group == "q_before" and is_after:
                group = "q_after"
            elif group == "n_before" and is_after:
                group = "n_after"
            elif group == "bulk_before" and is_after:
                group = "bulk_after"
            actual = fields[group][field]["hex32"]
            if actual != trace[stage][trace_name]:
                raise ValueError(f"{stage} {trace_name}: ledger {actual} != trace {trace[stage][trace_name]}")

    decimal_items = []
    def visit(node: object) -> None:
        if isinstance(node, dict):
            if "printed" in node and "source_type" in node:
                decimal_items.append(node)
            else:
                for child in node.values():
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(fields)
    for item in decimal_items:
        verify_decimal_interval(item)

    build = json.loads(args.build_receipt.read_text())
    run_receipt = json.loads(args.run_receipt.read_text())
    compiled = build["source_overrides"]["module_mp_kdm6.o"]["requested_sha256"]
    packet["parent_physical_source_sha256"] = packet.pop("source_sha256")
    packet["compiled_kdm_source_sha256"] = compiled
    packet["build_receipt_sha256"] = sha256(args.build_receipt)
    packet["candidate_executable_sha256"] = build["executable_sha256"]
    packet["decimal_interval_proof"] = {
        "format": "Fortran E24.16",
        "checked_fields": len(decimal_items),
        "REAL32_fields": sum(item["source_type"] == "REAL32" for item in decimal_items),
        "REAL64_fields": sum(item["source_type"] == "REAL64" for item in decimal_items),
        "criterion": "Each decimal rounding interval is strictly inside the source value's nearest-representable rounding cell.",
    }
    packet["field_type_scope"] = {
        "REAL32": "Q, N, BG, T, QV, CCN3, physical parameters, primitive rates, requested states, and admitted alpha fields",
        "REAL64": "stored deltas and stored-minus-admitted residuals only",
        "source": "The warm ledger writer uses default REAL for state/rate fields and explicitly REAL(...,8) for stored deltas and residuals.",
    }
    packet["trace_ledger_crosscheck"] = {
        "events": ["WARM_BEFORE_COMMIT", "WARM_AFTER_COMMIT"],
        "fields_per_event": 13,
        "status": "PASS",
    }
    packet["artifacts"]["warm_ledger"]["path"] = "warm_ledger.raw.gz"
    packet["artifacts"]["producer_trace"]["path"] = "producer_trace.raw.gz"
    packet["artifacts"]["warm_ledger"]["sha256"] = sha256(args.warm_ledger_gz)
    packet["artifacts"]["producer_trace"]["sha256"] = sha256(args.producer_trace_gz)
    packet["run_receipt_sha256"] = sha256(args.run_receipt)
    packet["run_receipt_status"] = run_receipt.get("status")
    args.output.write_text(json.dumps(packet, indent=2) + "\n")


if __name__ == "__main__":
    main()
