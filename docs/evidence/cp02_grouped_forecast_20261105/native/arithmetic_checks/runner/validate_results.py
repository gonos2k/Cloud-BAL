#!/usr/bin/env python3
"""Compare IFX outputs with independent exact REAL32 arithmetic references."""
from __future__ import annotations

import argparse
import csv
import json
import struct
from fractions import Fraction
from pathlib import Path

FIELDS = ('a_ph_next_hex', 'b_ph_hex', 'c_phb_next_hex', 'd_phb_hex')


def raw_bits(raw_word: str) -> int:
    return int.from_bytes(bytes.fromhex(raw_word), 'little')


def bits_fraction(bits: int) -> Fraction:
    sign = -1 if bits >> 31 else 1
    exponent = (bits >> 23) & 0xff
    significand = bits & 0x7fffff
    if exponent == 0xff:
        raise ValueError('non-finite REAL32 value')
    if exponent == 0:
        value = Fraction(significand, 1 << 149)
    else:
        significand |= 1 << 23
        power = exponent - 127 - 23
        value = Fraction(significand << power, 1) if power >= 0 else Fraction(significand, 1 << -power)
    return sign * value


def round_even(value: Fraction) -> int:
    quotient, remainder = divmod(value.numerator, value.denominator)
    doubled = 2 * remainder
    if doubled > value.denominator or (doubled == value.denominator and quotient & 1):
        quotient += 1
    return quotient


def floor_log2(value: Fraction) -> int:
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    if exponent >= 0:
        if value.numerator < (value.denominator << exponent):
            exponent -= 1
    elif (value.numerator << -exponent) < value.denominator:
        exponent -= 1
    return exponent


def round_binary32(value: Fraction) -> int:
    if value == 0:
        return 0
    sign_bit = 0x80000000 if value < 0 else 0
    magnitude = abs(value)
    exponent = floor_log2(magnitude)
    if exponent < -126:
        mantissa = round_even(magnitude * (1 << 149))
        if mantissa == 0:
            return sign_bit
        if mantissa >= (1 << 23):
            return sign_bit | 0x00800000
        return sign_bit | mantissa
    if exponent > 127:
        return sign_bit | 0x7f800000
    shift = 23 - exponent
    scaled = magnitude * (1 << shift) if shift >= 0 else magnitude / (1 << -shift)
    mantissa = round_even(scaled)
    if mantissa == (1 << 24):
        mantissa >>= 1
        exponent += 1
        if exponent > 127:
            return sign_bit | 0x7f800000
    return sign_bit | ((exponent + 127) << 23) | (mantissa - (1 << 23))


def add32(left: int, right: int, subtract: bool = False) -> int:
    a = bits_fraction(left)
    b = bits_fraction(right)
    return round_binary32(a - b if subtract else a + b)


def parse_output(path: Path) -> list[tuple[int, int, int]]:
    parsed = []
    for line_number, line in enumerate(path.read_text(encoding='ascii').splitlines(), 1):
        fields = line.split()
        if len(fields) != 3:
            raise ValueError(f'{path}:{line_number}: expected row and two bit patterns')
        parsed.append((int(fields[0]), int(fields[1], 16), int(fields[2], 16)))
    return parsed


def fraction_text(value: Fraction) -> str:
    return f'{value.numerator}/{value.denominator}'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', type=Path, required=True)
    parser.add_argument('--o0', type=Path, required=True)
    parser.add_argument('--o2', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--summary', type=Path, required=True)
    args = parser.parse_args()

    rows = json.loads(args.rows.read_text(encoding='utf-8'))
    o0 = parse_output(args.o0)
    o2 = parse_output(args.o2)
    if len(rows) != 60 or len(o0) != 60 or len(o2) != 60:
        raise SystemExit('expected exactly 60 rows in source inputs and both compiler outputs')

    indexed = {}
    results = []
    for row, out0, out2 in zip(rows, o0, o2):
        expected_index = row['row']
        if out0[0] != expected_index or out2[0] != expected_index:
            raise SystemExit(f'output row index mismatch at {expected_index}')
        a, b, c, d = (raw_bits(row[name]) for name in FIELDS)
        old_1 = add32(a, b, subtract=True)
        old_2 = add32(old_1, c)
        old_bits = add32(old_2, d, subtract=True)
        grouped_left = add32(a, b, subtract=True)
        grouped_right = add32(c, d, subtract=True)
        grouped_bits = add32(grouped_left, grouped_right)
        exact_once = round_binary32(
            bits_fraction(a) - bits_fraction(b) + bits_fraction(c) - bits_fraction(d))
        if out0[1:] != (old_bits, grouped_bits):
            raise SystemExit(f'O0 disagrees with exact sequential/grouped references at row {expected_index}')
        if out2[1:] != (old_bits, grouped_bits):
            raise SystemExit(f'O2 disagrees with exact sequential/grouped references at row {expected_index}')
        indexed[(row['target'], row['pair'], row['arm'])] = (old_bits, grouped_bits, exact_once)
        results.append({
            **row,
            'old_reference_hex': f'{old_bits:08X}',
            'grouped_reference_hex': f'{grouped_bits:08X}',
            'exact_once_hex': f'{exact_once:08X}',
            'o0_old_hex': f'{out0[1]:08X}',
            'o0_grouped_hex': f'{out0[2]:08X}',
            'o2_old_hex': f'{out2[1]:08X}',
            'o2_grouped_hex': f'{out2[2]:08X}',
        })

    pair_deltas = []
    pair_by_key = {(row['target'], row['pair']): row for row in rows}
    for target, pair in sorted(pair_by_key):
        b1_old, b1_grouped, b1_exact = indexed[(target, pair, 'B1')]
        dm_old, dm_grouped, dm_exact = indexed[(target, pair, 'DM065')]
        old_delta = bits_fraction(dm_old) - bits_fraction(b1_old)
        grouped_delta = bits_fraction(dm_grouped) - bits_fraction(b1_grouped)
        exact_once_delta = bits_fraction(dm_exact) - bits_fraction(b1_exact)
        b1_sequence = next(row['entry_sequence'] for row in rows
                           if row['target'] == target and row['pair'] == pair and row['arm'] == 'B1')
        dm_sequence = next(row['entry_sequence'] for row in rows
                           if row['target'] == target and row['pair'] == pair and row['arm'] == 'DM065')
        pair_deltas.append({
            'target': target, 'pair': pair,
            'B1_entry_sequence': b1_sequence, 'DM065_entry_sequence': dm_sequence,
            'old_interarm_delta_exact': fraction_text(old_delta),
            'grouped_interarm_delta_exact': fraction_text(grouped_delta),
            'exact_once_interarm_delta_exact': fraction_text(exact_once_delta),
            'old_interarm_delta_f64_display': format(float(old_delta), '.17g'),
            'grouped_interarm_delta_f64_display': format(float(grouped_delta), '.17g'),
        })
    pair_lookup = {(row['target'], row['pair']): row for row in pair_deltas}
    for row in results:
        delta = pair_lookup[(row['target'], row['pair'])]
        row['old_interarm_delta_exact'] = delta['old_interarm_delta_exact']
        row['grouped_interarm_delta_exact'] = delta['grouped_interarm_delta_exact']
        row['exact_once_interarm_delta_exact'] = delta['exact_once_interarm_delta_exact']

    args.results.parent.mkdir(parents=True, exist_ok=True)
    with args.results.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    summary = {
        'status': 'PASS', 'row_count': 60, 'paired_calls': 30,
        'pairs_per_target': {'p20183': 15, 'p17051': 15},
        'o0_matches_independent_binary32_references': True,
        'o2_matches_independent_binary32_references': True,
        'o0_equals_o2_for_all_rows': True,
        'old_grouped_results_differ_count': sum(r['old_reference_hex'] != r['grouped_reference_hex'] for r in results),
        'exact_once_differs_from_old_count': sum(r['old_reference_hex'] != r['exact_once_hex'] for r in results),
        'exact_once_differs_from_grouped_count': sum(r['grouped_reference_hex'] != r['exact_once_hex'] for r in results),
        'interarm_delta_pair_count': len(pair_deltas),
        'nonzero_old_interarm_delta_count': sum(row['old_interarm_delta_exact'] != '0/1' for row in pair_deltas),
        'nonzero_grouped_interarm_delta_count': sum(row['grouped_interarm_delta_exact'] != '0/1' for row in pair_deltas),
        'interarm_deltas': pair_deltas,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'interarm_deltas'}, indent=2))


if __name__ == '__main__':
    main()
