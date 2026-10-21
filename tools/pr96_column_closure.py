#!/usr/bin/env python3
"""Reduce PR96 liquid transfer records with exact REAL32 rounding checks."""
from __future__ import annotations

import argparse
import json
import math
import struct
from collections import Counter
from fractions import Fraction
from pathlib import Path


def f32_from_bits(bits: int) -> float:
    return struct.unpack(">f", struct.pack(">I", bits))[0]


def f32_bits(value: float) -> int:
    return struct.unpack(">I", struct.pack(">f", value))[0]


def exact_fraction(value: float) -> Fraction:
    return Fraction.from_float(value)


def adjacent_f32_bits(bits: int) -> tuple[int, int]:
    if bits & 0x7FFFFFFF == 0:
        return 0x80000001, 0x00000001
    if bits & 0x80000000:
        return bits + 1, bits - 1
    return bits - 1, bits + 1


def half_ulp(bits: int) -> Fraction:
    value = exact_fraction(f32_from_bits(bits))
    gaps = [abs(exact_fraction(f32_from_bits(candidate)) - value)
            for candidate in adjacent_f32_bits(bits)
            if math.isfinite(f32_from_bits(candidate))]
    return max(gaps) / 2


def nearest_f32(exact: Fraction) -> tuple[int, Fraction, Fraction]:
    """Return nearest REAL32 bits/value and exact distance, ties to even."""
    center = f32_bits(float(exact))
    candidates = {center, *adjacent_f32_bits(center)}
    values = [(bits, exact_fraction(f32_from_bits(bits))) for bits in candidates
              if math.isfinite(f32_from_bits(bits))]
    distances = [(abs(exact - value), bits, value) for bits, value in values]
    best_distance = min(row[0] for row in distances)
    tied = [row for row in distances if row[0] == best_distance]
    # IEEE ties-to-even selects the candidate with an even least-significant bit.
    distance, bits, value = min(tied, key=lambda row: row[1] & 1)
    return bits, value, distance


def parse_trace(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split()
        if not fields:
            continue
        if len(fields) != 23:
            raise ValueError(f"{path}:{line_number}: expected 23 fields, got {len(fields)}")
        tag = fields[0]
        i, lat, k, loop = map(int, fields[1:5])
        bits = [int(value, 16) for value in fields[5:12]]
        values = list(map(float, fields[12:]))
        rate, dtcld, transfer, product64, q_before, qc_before, q_after, qc_after, *_ = values
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"{path}:{line_number}: nonfinite numeric field")
        if dtcld <= 0.0 or min(q_before, qc_before, q_after, qc_after) < 0.0:
            raise ValueError(f"{path}:{line_number}: invalid DTCLD or water state")
        if tag not in {"ACT", "COND", "CONDFULL"}:
            raise ValueError(f"{path}:{line_number}: unsupported tag {tag}")
        rows.append({
            "tag": tag, "i": i, "lat": lat, "k": k, "loop": loop,
            "bits": bits, "rate": rate, "dtcld": dtcld, "transfer": transfer,
            "product64": product64, "q_before": q_before, "qc_before": qc_before,
            "q_after": q_after, "qc_after": qc_after,
        })
    return rows


def reduce_rows(rows: list[dict], layer_weights: dict[int, float]) -> dict:
    errors = Counter()
    weighted_bounds = Counter()
    counts = Counter()
    max_half_ulp_fraction = 0.0
    transfer_minus_exact_product_kg = Counter()
    exact_event_sum = Fraction(0)
    exact_event_by_layer = Counter()
    event_counts_by_layer = Counter()
    rne_mismatches = []
    for row in rows:
        if row["k"] not in layer_weights:
            raise ValueError(f"missing cell mass weight at k={row['k']}")
        weight = layer_weights[row["k"]]
        if not math.isfinite(weight) or weight <= 0.0:
            raise ValueError(f"invalid cell mass weight at k={row['k']}")
        tag = row["tag"]
        bit_values = [row["rate"], row["dtcld"], row["transfer"],
                      row["q_before"], row["qc_before"], row["q_after"], row["qc_after"]]
        for name, value, bits in zip(("rate", "dtcld", "transfer", "q_before", "qc_before", "q_after", "qc_after"), bit_values, row["bits"]):
            if f32_bits(value) != bits:
                rne_mismatches.append({"field": name, "row": [row["i"], row["lat"], row["k"], row["loop"]], "reason": "printed REAL32 value disagrees with raw bits"})
        rate, dtcld, transfer, q_before, qc_before, q_after, qc_after = [f32_from_bits(bits) for bits in row["bits"]]
        exact_product = exact_fraction(rate) * exact_fraction(dtcld)
        if row["product64"] != rate * dtcld:
            rne_mismatches.append({"field": "product64", "row": [row["i"], row["lat"], row["k"], row["loop"]]})
        product_bits, _, _ = nearest_f32(exact_product)
        if tag != "CONDFULL" and product_bits != row["bits"][2]:
            rne_mismatches.append({"field": "transfer", "row": [row["i"], row["lat"], row["k"], row["loop"]], "reason": "transfer differs from RNE(rate*DTCLD)"})
        q_exact = exact_fraction(q_before) - exact_fraction(transfer)
        q_bits, q_rounded, q_distance = nearest_f32(q_exact)
        q_error = exact_fraction(q_after) - q_exact
        if q_bits != row["bits"][5]:
            rne_mismatches.append({"species": "Q", "row": [row["i"], row["lat"], row["k"], row["loop"]]})
        q_half_ulp = half_ulp(q_bits)
        max_half_ulp_fraction = max(max_half_ulp_fraction, float(abs(q_error) / q_half_ulp))
        exact_weight = exact_fraction(weight)
        errors["Q"] += float(q_error) * weight
        weighted_bounds["Q"] += float(q_half_ulp) * weight

        if tag == "CONDFULL":
            if transfer != -qc_before or qc_after != 0.0:
                rne_mismatches.append({"species": "QC", "row": [row["i"], row["lat"], row["k"], row["loop"]], "reason": "full evaporation extent does not exactly clear QC"})
            qc_error = Fraction(0)
        else:
            qc_exact = exact_fraction(qc_before) + exact_fraction(transfer)
            qc_bits, qc_rounded, _ = nearest_f32(qc_exact)
            qc_error = exact_fraction(qc_after) - qc_exact
            if qc_bits != row["bits"][6]:
                rne_mismatches.append({"species": "QC", "row": [row["i"], row["lat"], row["k"], row["loop"]]})
            qc_half_ulp = half_ulp(qc_bits)
            max_half_ulp_fraction = max(max_half_ulp_fraction, float(abs(qc_error) / qc_half_ulp))
            weighted_bounds["QC"] += float(qc_half_ulp) * weight
        errors["QC"] += float(qc_error) * weight
        exact_event_sum += (q_error + qc_error) * exact_weight
        exact_event_by_layer[row["k"]] += (q_error + qc_error) * exact_weight
        event_counts_by_layer[row["k"]] += 1
        transfer_minus_exact_product_kg[tag] += (transfer - row["product64"]) * weight
        counts[tag] += 1

    return {
        "events": sum(counts.values()),
        "events_by_tag": dict(sorted(counts.items())),
        "stored_minus_approved_kg": dict(errors),
        "total_stored_minus_approved_kg": math.fsum(errors.values()),
        "independent_half_ulp_bound_kg": dict(weighted_bounds),
        "actual_r32_transfer_minus_exact_operand_product_kg_by_tag": dict(transfer_minus_exact_product_kg),
        "max_store_error_fraction_of_half_ulp": max_half_ulp_fraction,
        "exact_event_sum_kg": float(exact_event_sum),
        "exact_event_by_layer_kg": {str(k): float(value) for k, value in sorted(exact_event_by_layer.items())},
        "event_count_by_layer": {str(k): count for k, count in sorted(event_counts_by_layer.items())},
        "r32_rne_mismatches": rne_mismatches,
        "r32_rne_pass": not rne_mismatches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--layer-weights", required=True, type=Path,
                        help="JSON map from Fortran k index to DEN*DELZ*cell-area kg")
    parser.add_argument("--expected-residual-kg", type=float)
    parser.add_argument("--pre-column", type=Path,
                        help="17-field, 39-level big-endian REAL32 pre-state column")
    parser.add_argument("--post-column", type=Path,
                        help="17-field, 39-level big-endian REAL32 post-state column")
    args = parser.parse_args()
    weights = {int(k): float(v) for k, v in json.loads(args.layer_weights.read_text()).items()}
    result = reduce_rows(parse_trace(args.trace), weights)
    if bool(args.pre_column) != bool(args.post_column):
        parser.error("--pre-column and --post-column must be given together")
    if args.pre_column:
        field_count = 17
        levels = sorted(weights)
        expected_bytes = field_count * len(levels) * 4
        pre_bytes = args.pre_column.read_bytes()
        post_bytes = args.post_column.read_bytes()
        if len(pre_bytes) != expected_bytes or len(post_bytes) != expected_bytes:
            parser.error(f"column states must each contain {expected_bytes} bytes")
        pre_values = struct.unpack(f">{field_count * len(levels)}f", pre_bytes)
        post_values = struct.unpack(f">{field_count * len(levels)}f", post_bytes)
        exact_per_layer = {}
        layer_rows = []
        exact_endpoint_layers = []
        exact_event_layers = []
        endpoint_events = parse_trace(args.trace)
        for layer_index, k in enumerate(levels):
            weight = exact_fraction(weights[k])
            endpoint_per_mass = Fraction(0)
            for field_index in (5, 6, 7, 8, 9, 10):
                offset = field_index * len(levels) + layer_index
                endpoint_per_mass += exact_fraction(post_values[offset]) - exact_fraction(pre_values[offset])
            endpoint_layer = endpoint_per_mass * weight
            event_layer = Fraction(0)
            for row in endpoint_events:
                if row["k"] != k:
                    continue
                transfer = exact_fraction(f32_from_bits(row["bits"][2]))
                q_error = exact_fraction(f32_from_bits(row["bits"][5])) - exact_fraction(f32_from_bits(row["bits"][3])) + transfer
                qc_error = exact_fraction(f32_from_bits(row["bits"][6])) - exact_fraction(f32_from_bits(row["bits"][4])) - transfer
                event_layer += (q_error + qc_error) * weight
            exact_per_layer[k] = endpoint_layer == event_layer
            exact_endpoint_layers.append(endpoint_layer)
            exact_event_layers.append(event_layer)
            layer_rows.append({"k": k, "event_count": result["event_count_by_layer"].get(str(k), 0),
                               "endpoint_delta_kg": float(endpoint_layer),
                               "event_store_error_kg": float(event_layer),
                               "difference_kg": float(endpoint_layer - event_layer),
                               "exact_identity_pass": endpoint_layer == event_layer})
        endpoint = sum(exact_endpoint_layers, Fraction(0))
        event_sum = sum(exact_event_layers, Fraction(0))
        signed = math.fsum(row["endpoint_delta_kg"] for row in layer_rows)
        l1 = math.fsum(abs(row["endpoint_delta_kg"]) for row in layer_rows)
        maximum = max((abs(row["endpoint_delta_kg"]) for row in layer_rows), default=0.0)
        result["exact_endpoint_phase_delta_kg"] = float(endpoint)
        result["exact_event_endpoint_identity_pass"] = endpoint == event_sum and all(exact_per_layer.values())
        result["exact_endpoint_event_difference_kg"] = float(endpoint - event_sum)
        result["per_layer_exact_identity_pass"] = all(exact_per_layer.values())
        result["per_layer"] = layer_rows
        result["endpoint_column_stats_kg"] = {"signed": signed, "l1": l1, "max_abs_layer": maximum}
    if args.expected_residual_kg is not None:
        result["expected_column_residual_kg"] = args.expected_residual_kg
        result["difference_from_column_residual_kg"] = result["total_stored_minus_approved_kg"] - args.expected_residual_kg
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
