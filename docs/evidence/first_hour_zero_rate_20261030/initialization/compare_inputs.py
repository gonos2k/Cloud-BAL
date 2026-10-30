#!/usr/bin/env python3
"""Read-only full-array comparison of the two pinned native initial states."""
import hashlib
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
PATHS = {'ORIGINAL': ROOT / 'scratch/current_forecast_paper_20261029/run.PomEr8/original/wrfinput_d01',
         'HYDRO': ROOT / 'Cloud-BAL/scratch/cp02_six_hour_20260914/hydro/run/wrfinput_d01'}
HASHES = {'ORIGINAL': '5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc',
          'HYDRO': '7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126'}
FIELDS = ('QVAPOR', 'QCLOUD', 'QICE', 'QRAIN', 'QSNOW', 'QGRAUP', 'T', 'THM', 'P', 'PB',
          'MU', 'MUB', 'PH', 'PHB', 'U', 'V', 'QNCCN', 'QNCLOUD', 'QNICE', 'QNRAIN', 'QIB')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def compare(a, b):
    if a.dimensions != b.dimensions or a.shape != b.shape or a.dtype != b.dtype:
        raise ValueError('field dimensions, shape or dtype differ')
    x = a[:]; y = b[:]
    if np.any(np.ma.getmaskarray(x)) or np.any(np.ma.getmaskarray(y)):
        raise ValueError('masked input values')
    x = np.asarray(x); y = np.asarray(y)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('nonfinite input values')
    delta = y.astype(np.float64) - x.astype(np.float64)
    attrs_a = {k: str(a.getncattr(k)) for k in a.ncattrs()}
    attrs_b = {k: str(b.getncattr(k)) for k in b.ncattrs()}
    return {'dimensions': list(a.dimensions), 'shape': list(a.shape), 'dtype': str(a.dtype),
            'units': attrs_a.get('units'), 'metadata_equal': attrs_a == attrs_b,
            'metadata_differences': {k: [attrs_a.get(k), attrs_b.get(k)] for k in sorted(set(attrs_a) | set(attrs_b)) if attrs_a.get(k) != attrs_b.get(k)},
            'count': x.size, 'changed_count': int(np.count_nonzero(x != y)),
            'increased_count': int(np.count_nonzero(delta > 0)), 'decreased_count': int(np.count_nonzero(delta < 0)),
            'original_positive_count': int(np.count_nonzero(x > 0)), 'hydro_positive_count': int(np.count_nonzero(y > 0)),
            'max_abs_difference': float(np.max(np.abs(delta))), 'mean_signed_difference': float(np.mean(delta)),
            'sum_signed_unweighted_difference': float(np.sum(delta)),
            'original_min_max': [float(np.min(x)), float(np.max(x))], 'hydro_min_max': [float(np.min(y)), float(np.max(y))]}


def main():
    if {k: sha(v) for k, v in PATHS.items()} != HASHES: raise ValueError('input hash mismatch')
    with Dataset(PATHS['ORIGINAL']) as original, Dataset(PATHS['HYDRO']) as hydro:
        fields = {name: compare(original[name], hydro[name]) for name in FIELDS}
        attrs = {k: [str(original.getncattr(k)) if k in original.ncattrs() else None,
                     str(hydro.getncattr(k)) if k in hydro.ncattrs() else None]
                 for k in sorted(set(original.ncattrs()) | set(hydro.ncattrs()))
                 if (str(original.getncattr(k)) if k in original.ncattrs() else None) !=
                    (str(hydro.getncattr(k)) if k in hydro.ncattrs() else None)}
    if {k: sha(v) for k, v in PATHS.items()} != HASHES: raise ValueError('input changed during read')
    result = {'status': 'PASS', 'paths': {k: str(v) for k, v in PATHS.items()}, 'sha256_before_after': HASHES,
              'comparison': 'HYDRO minus ORIGINAL; all array elements, including outside verification mask',
              'unweighted_sum_limitation': 'Mixing-ratio sums are not a mass budget; require cell dry-air mass and area weights.',
              'fields': fields, 'global_attribute_differences': attrs}
    output = Path(__file__).with_name('input_comparison.json')
    with output.open('x') as f: json.dump(result, f, indent=2, allow_nan=False); f.write('\n')


if __name__ == '__main__': main()
