#!/usr/bin/env python3
"""Compare completed fresh paired arrays with the retained historical sample."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

PAIRS = (('ORIGINAL', 'OFF'), ('CURRENT_HYDRO', 'HYDRO'), ('CURRENT_LIQUID', 'LIQUID'))
COMMON = ('reference', 'latitude', 'longitude', 'flat_index_yx')


def identity(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return {'path': str(path.resolve()), 'sha256': digest.hexdigest(), 'size': path.stat().st_size}


def compare(a, b):
    if a.shape != (3688,) or b.shape != (3688,) or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('all compared fields must contain 3688 finite values')
    equal = a == b
    # Bitwise equality also requires identical dtype, including byte order.
    same_bits = a.dtype == b.dtype and np.array_equal(a.view(np.uint8), b.view(np.uint8))
    return {'fresh_dtype': str(a.dtype), 'archived_dtype': str(b.dtype),
            'exact_values_equal': bool(equal.all()), 'bitwise_equal': bool(same_bits),
            'changed_count': int(np.count_nonzero(~equal)),
            'max_absolute_difference': float(np.max(np.abs(a.astype(np.float64) - b.astype(np.float64))))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fresh', type=Path, required=True)
    parser.add_argument('--archived', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(args.output)
    inputs = [directory / f'hour_{hour}_arrays.npz' for hour in range(13, 19)
              for directory in (args.fresh, args.archived)]
    records = [identity(path) for path in inputs]
    script = Path(__file__).resolve()
    script_record = identity(script)
    hourly = {}
    for hour in range(13, 19):
        with np.load(args.fresh / f'hour_{hour}_arrays.npz', allow_pickle=False) as fresh, \
             np.load(args.archived / f'hour_{hour}_arrays.npz', allow_pickle=False) as archived:
            checks = {key: compare(fresh[key], archived[key]) for key in COMMON}
            checks.update({f'{a}_vs_{b}': compare(fresh[a], archived[b]) for a, b in PAIRS})
            hourly[str(hour - 12)] = checks
    if [identity(path) for path in inputs] != records or identity(script) != script_record:
        raise ValueError('input or comparison script changed while reading')
    result = {'scope': 'Paired point values only; one historical case. CURRENT_OFF is deliberately not compared with historical OFF because its initialization differs.',
              'fields': list(COMMON), 'forecast_pairs': [list(pair) for pair in PAIRS],
              'inputs': records, 'script': script_record, 'hourly': hourly}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
