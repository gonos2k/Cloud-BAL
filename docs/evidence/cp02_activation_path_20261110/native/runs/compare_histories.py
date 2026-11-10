#!/usr/bin/env python3
"""Require exact 0–3-hour raw NetCDF data and metadata parity per capture arm."""
import argparse
import hashlib
import json
from pathlib import Path
import netCDF4
import numpy as np

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
RUNS = ROOT / 'scratch/b1_activation_path_20261110/runtime/forecasts'
REFS = {arm: ROOT / 'scratch/b1_pulse_path_20261110/runtime/forecasts' / arm for arm in ('CONTROL','MP10')}


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def signature(value):
    a = np.asarray(value)
    if a.dtype.kind == 'O':
        return a.shape, a.dtype.str, tuple((type(x).__name__, repr(x)) for x in a.flat)
    return a.shape, a.dtype.str, a.tobytes(order='C')


def compare(actual, reference):
    with netCDF4.Dataset(actual) as a, netCDF4.Dataset(reference) as b:
        a.set_auto_maskandscale(False); b.set_auto_maskandscale(False)
        if list(a.dimensions) != list(b.dimensions) or list(a.variables) != list(b.variables):
            raise ValueError('dimension or variable inventory differs')
        for name in a.dimensions:
            if (len(a.dimensions[name]), a.dimensions[name].isunlimited()) != (len(b.dimensions[name]), b.dimensions[name].isunlimited()):
                raise ValueError(f'dimension differs: {name}')
        for name in a.variables:
            x, y = a.variables[name], b.variables[name]
            if (x.dimensions, x.dtype.str, set(x.ncattrs())) != (y.dimensions, y.dtype.str, set(y.ncattrs())):
                raise ValueError(f'variable metadata differs: {name}')
            if signature(x[:]) != signature(y[:]):
                raise ValueError(f'raw variable data bits differ: {name}')
            if any(signature(x.getncattr(k)) != signature(y.getncattr(k)) for k in x.ncattrs()):
                raise ValueError(f'variable attributes differ: {name}')
        if set(a.ncattrs()) != set(b.ncattrs()) or any(signature(a.getncattr(k)) != signature(b.getncattr(k)) for k in a.ncattrs()):
            raise ValueError('global attributes differ')
    return {'actual_sha256': sha(actual), 'reference_sha256': sha(reference), 'exact': True}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('arm', choices=REFS); args = parser.parse_args()
    case = RUNS / args.arm
    run_receipt = case / 'run_receipt.json'
    if json.loads(run_receipt.read_text())['status'] != 'PASS':
        raise ValueError('run receipt not PASS')
    pins = json.loads(Path(__file__).with_name('reference_pins.json').read_text())[args.arm]
    reference_receipt = Path(pins['receipt'])
    if sha(reference_receipt) != pins['receipt_sha256']:
        raise ValueError('historical run receipt changed')
    comparisons = {}
    for hour in range(12, 16):
        name = f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
        reference = REFS[args.arm] / name
        if sha(reference) != pins['history_sha256'][name]:
            raise ValueError(f'reference history hash differs: {name}')
        if sha(case / name) != pins['history_sha256'][name]:
            raise ValueError(f'history file bytes differ: {name}')
        comparisons[name] = compare(case / name, reference)
        if sha(reference) != pins['history_sha256'][name]:
            raise ValueError(f'reference changed during comparison: {name}')
    if sha(reference_receipt) != pins['receipt_sha256']:
        raise ValueError('historical run receipt changed during comparison')
    receipt = {'reference_receipt_sha256': pins['receipt_sha256'], 'reference_pins_sha256': sha(Path(__file__).with_name('reference_pins.json')), 'status':'PASS', 'arm':args.arm, 'run_receipt_sha256':sha(run_receipt),
               'nan_policy':'raw floating data bits must match, including NaN payload and signed zero',
               'comparisons':comparisons}
    with (case / 'history_comparison.json').open('x') as f:
        json.dump(receipt, f, indent=2); f.write('\n')


if __name__ == '__main__':
    main()
