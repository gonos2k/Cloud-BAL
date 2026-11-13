#!/usr/bin/env python3
"""Check saved debugger and history words without reading NetCDF files."""
import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path

EVENTS = (
    'kdm_entry', 'kdm_return', 'zero_b_entry', 'zero_b_return',
    'zero_a_entry', 'zero_a_return',
)
FIELDS = ('qi', 'ni')


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def index_cells(rows):
    indexed = {tuple(row['cell']): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError('duplicate cell in a capture event or history sample')
    return indexed


def read_inputs(args):
    records = [json.loads(line) for line in args.capture.read_text().splitlines()]
    baseline = index_cells(json.loads(args.baseline.read_text())['cells'])
    replayed = index_cells(json.loads(args.replayed.read_text())['cells'])
    events = [record['event'] for record in records]
    if len(set(events)) != len(events):
        raise ValueError('duplicate capture event')
    captured = {record['event']: index_cells(record.get('rows', [])) for record in records}
    return records, baseline, replayed, events, captured


def valid_words(rows):
    return all(
        struct.pack('<f', row[field]).hex() == row[field + '_le']
        for row in rows for field in FIELDS
    )


def same_words(left, right, cells, field):
    return all(
        cell in left and cell in right
        and left[cell][field + '_le'] == right[cell][field + '_le']
        for cell in cells
    )


def check_words(records, baseline, replayed, events, captured):
    cells = baseline.keys()
    checks = {
        'exact_six_event_sequence': tuple(events) == EVENTS,
        'nine_cells_baseline_and_replay': len(baseline) == len(replayed) == 9
        and cells == replayed.keys(),
        'nine_matching_rows_per_event': len(records) == 6
        and all(len(table) == 9 and table.keys() == cells for table in captured.values()),
        'capture_word_encodings_valid': valid_words(
            row for record in records for row in record.get('rows', [])
        ),
        'history_word_encodings_valid': valid_words(baseline.values())
        and valid_words(replayed.values()),
    }
    for first, second in (('kdm_return', 'zero_b_entry'),
                          ('zero_b_return', 'zero_a_entry')):
        checks[first + '_to_' + second] = all(
            same_words(captured.get(first, {}), captured.get(second, {}), cells, field)
            for field in FIELDS
        )
    for field in FIELDS:
        checks['zero_a_return_' + field + '_equals_replayed_history'] = same_words(
            captured.get('zero_a_return', {}), replayed, cells, field
        )
        checks['baseline_equals_replayed_history_' + field] = same_words(
            baseline, replayed, cells, field
        )
    return checks


def write_csv(path, records, baseline, replayed):
    with path.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['i', 'j', 'k', 'event', 'qi', 'ni', 'qi_hex_le', 'ni_hex_le'])
        for record in records:
            for row in record.get('rows', []):
                writer.writerow([*row['cell'], record['event'], row['qi'], row['ni'],
                                 row['qi_le'], row['ni_le']])
        for label, table in (('baseline_history', baseline), ('replayed_history', replayed)):
            for cell, row in table.items():
                writer.writerow([*cell, label, row['qi'], row['ni'], row['qi_le'], row['ni_le']])


def main():
    parser = argparse.ArgumentParser()
    for name in ('capture', 'baseline', 'replayed', 'inputsreceipt', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    records, baseline, replayed, events, captured = read_inputs(args)
    checks = check_words(records, baseline, replayed, events, captured)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / 'boundary_values.csv', records, baseline, replayed)
    result = {
        'status': 'PASS' if all(checks.values()) else 'INCOMPLETE_OR_MISMATCH',
        'checks': checks,
        'events': events,
        'file_sha256': {name: sha256(getattr(args, name))
                        for name in ('capture', 'baseline', 'replayed', 'inputsreceipt')},
        'scope': 'Offline validation of 54 recorded event-cell records plus 18 saved '
                 'history-cell pairs; it does not independently read or hash NetCDF inputs or outputs.',
    }
    (args.out / 'offline_word_validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
