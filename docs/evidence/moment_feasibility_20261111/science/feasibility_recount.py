#!/usr/bin/env python3
"""Read-only analytical interval recount of the pinned B1 producer file."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

INPUT_SHA = '9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'
POLICY_SHA = '647126e5215acbb985d39d56564898f7c6f82adb85d05266bf0d2c4ba008a00e'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def summary(mask):
    mask = np.asarray(mask, dtype=np.uint8, order='C')
    indices = np.argwhere(mask)
    return {
        'count': int(indices.shape[0]),
        'sha256_uint8_zyx_c_order': hashlib.sha256(mask.tobytes(order='C')).hexdigest(),
        'first_ijk_1based': [int(v) + 1 for v in indices[0][::-1]] if len(indices) else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('wrfinput', type=Path)
    parser.add_argument('policy', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if sha(args.wrfinput) != INPUT_SHA or sha(args.policy) != POLICY_SHA:
        raise ValueError('unexpected input or policy hash')
    policy = json.loads(args.policy.read_text())
    with Dataset(args.wrfinput, 'r') as ds:
        ds.set_auto_maskandscale(False)
        inv = np.add(ds['AL'][0], ds['ALB'][0], dtype=np.float32)
        if not np.all(np.isfinite(inv)) or np.any(inv <= 0):
            raise ValueError('invalid inverse density')
        rho = np.divide(np.float32(1), inv, dtype=np.float32)
        masses = [np.asarray(ds[name][0], dtype=np.float32) for name in ('QCLOUD', 'QICE', 'QRAIN')]
    if any(not np.all(np.isfinite(q)) or np.any(q < 0) or q.shape != rho.shape for q in masses):
        raise ValueError('invalid mass fields')
    if policy['mass_threshold'][:3] != [0, 0, 0]:
        raise ValueError('unexpected thresholds')
    result = {
        'source_path': str(args.wrfinput.resolve()),
        'source_sha256': INPUT_SHA,
        'policy_path': str(args.policy.resolve()),
        'policy_sha256': POLICY_SHA,
        'script_sha256': sha(Path(__file__)),
        'shape_zyx': list(rho.shape),
        'density': 'float32(1/float32(AL+ALB)); file-state proxy',
        'analytical_mask': 'q>0 and q>=threshold and float64(q)/upper > min(float64(q)/lower, cap/float64(rho))',
        'scope': 'Ideal exact-real bounds evaluated in float64, not native REAL32 candidate acceptance or runtime validation.',
        'species': {},
    }
    masks = []
    for slot, (name, q) in enumerate(zip(('NC', 'NI', 'NR'), masses)):
        lower, upper, cap = policy['lower'][slot], policy['upper'][slot], policy['number_cap'][slot]
        q64 = q.astype(np.float64)
        r64 = rho.astype(np.float64)
        nmin = q64 / upper
        nmax = np.minimum(q64 / lower, cap / r64)
        mask = (q > 0) & (q64 >= policy['mass_threshold'][slot]) & (nmin > nmax)
        masks.append(mask)
        result['species'][name] = {
            'positive_mass_count': int(np.count_nonzero(q > 0)),
            'empty_interval': summary(mask),
            'maximum_q_kg_per_kg': float(np.max(q)),
            'maximum_mass_concentration_kg_per_m3': float(np.max(q64 * r64)),
            'upper_mean_mass_kg': upper,
            'number_cap_per_m3': cap,
        }
    mean_mass = np.pi * 500.0 / 6.0 * (50e-6)**3
    fixed = (masses[1] > 0) & (masses[1].astype(np.float64) * rho.astype(np.float64) / mean_mass > 1e6)
    result['ice_fixed_50um_over_cap'] = summary(fixed)
    result['ice_fixed_50um_and_empty'] = summary(fixed & masks[1])
    result['ice_fixed_50um_over_cap_not_empty'] = summary(fixed & ~masks[1])
    result['ice_fixed_50um_mean_mass_kg'] = mean_mass
    if result['ice_fixed_50um_over_cap']['count'] != 106128:
        raise ValueError('fixed-50um independent recount mismatch')
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
