#!/usr/bin/env python3
"""Compare completed full rerun to the first pass and publish its audit tables."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
import shutil
import tempfile


def digest(path, compressed=False):
    result = hashlib.sha256()
    opener = gzip.open if compressed else open
    with opener(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            result.update(block)
    return result.hexdigest()


def verify_p01(table, arm, proof):
    weights = {(140, 79): .24629397354739388, (141, 79): .24211872650600177,
               (140, 80): .2579803287393153, (141, 80): .25360697120728903}
    totals = {first: defaultdict(float) for first in (330, 331)}
    coverage = {first: set() for first in totals}
    with gzip.open(table, 'rt', newline='') as stream:
        for row in csv.DictReader(stream):
            cell, step = (int(row['i']), int(row['j'])), int(row['step'])
            if cell not in weights or step < 330 or step > 360 or row['species'] != 'rain':
                continue
            for first in totals:
                if step < first:
                    continue
                coverage[first].add((step, cell))
                for field in ('limiter_events', 'transfer_gap', 'column_change', 'ground_fall_increment'):
                    value = float(row[field])
                    totals[first][field + '_native_sum'] += value
                    totals[first][field + '_bilinear'] += weights[cell] * value
    for first in totals:
        expected = next(row for row in proof['result'] if row['arm'] == arm and row['first_step'] == first)
        if len(coverage[first]) != (361 - first) * 4:
            raise ValueError(f'{arm}: incomplete P01 columns for {first}–360')
        for key, value in totals[first].items():
            if not math.isclose(value, expected[key], rel_tol=1e-12, abs_tol=1e-14):
                raise ValueError(f'{arm}: P01 proof mismatch for {first} {key}')
    return {'windows': [[330, 360], [331, 360]], 'all_proof_metrics_match': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--final-run', type=Path, required=True)
    parser.add_argument('--first-pass', type=Path, required=True)
    args = parser.parse_args()
    evidence = Path(__file__).resolve().parent
    final = evidence / 'full'
    if final.exists() or final.is_symlink():
        raise FileExistsError(final)
    launch_copy = evidence / 'executed_full_tool.py'
    pin = (evidence / 'full_launch_hashes.txt').read_text().splitlines()[0].split()[0]
    if digest(launch_copy) != pin or digest(args.final_run / 'executed_tool.py') != pin:
        raise ValueError('executed source differs from pre-launch pin')
    info = {}
    p01 = json.loads((evidence / 'p01_focused_proof.json').read_text())
    with tempfile.TemporaryDirectory(prefix='.full-', dir=evidence) as temporary:
        stage = Path(temporary)
        for arm in ('OLD', 'FIX'):
            source = args.final_run / arm
            attempt = args.first_pass
            summary = json.loads((source / f'{arm}_summary.json').read_text())
            old_summary = json.loads((attempt / f'{arm}_summary.json').read_text())
            if summary != old_summary:
                raise ValueError(f'{arm}: full and first-pass summaries differ')
            out = stage / arm
            out.mkdir()
            files = {}
            for suffix in ('substeps.csv.gz', 'events.csv.gz'):
                name = f'{arm}_{suffix}'
                exact = digest(source / name, compressed=True)
                if exact != digest(attempt / name, compressed=True):
                    raise ValueError(f'{arm}: first-pass and final decoded tables differ: {name}')
                shutil.copy2(source / name, out / name)
                files[name] = {'sha256': digest(out / name), 'decoded_sha256': exact}
            for suffix in ('summary.json', 'roles.csv'):
                name = f'{arm}_{suffix}'
                shutil.copy2(source / name, out / name)
                files[name] = {'sha256': digest(out / name)}
            info[arm] = {'first_pass_summary_and_decoded_tables_exact': True, 'p01': verify_p01(source / f'{arm}_substeps.csv.gz', arm, p01), 'files': files}
        (stage / 'receipt.json').write_text(json.dumps({'status': 'PASS', 'executed_tool_sha256': pin, 'arms': info}, indent=2) + '\n')
        if final.exists() or final.is_symlink():
            raise FileExistsError(final)
        stage.rename(final)

if __name__ == '__main__':
    main()
