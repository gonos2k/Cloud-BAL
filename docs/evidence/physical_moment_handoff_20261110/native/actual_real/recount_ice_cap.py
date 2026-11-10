#!/usr/bin/env python3
"""Independently count the immutable B1 file's fixed 50 µm ice-prior cap exceedances."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

EXPECTED = '9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('wrfinput', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if sha(args.wrfinput) != EXPECTED:
        raise ValueError('unexpected producer file hash')
    with Dataset(args.wrfinput) as ds:
        ds.set_auto_maskandscale(False)
        q = np.asarray(ds['QICE'][0], dtype=np.float32)
        inv = np.add(ds['AL'][0], ds['ALB'][0], dtype=np.float32)
        rho = np.divide(np.float32(1), inv, dtype=np.float32)
        ni = np.asarray(ds['QNICE'][0], dtype=np.float32)
    if np.any(q < 0) or np.any(inv <= 0) or np.any(ni != 0):
        raise ValueError('unexpected native fields')
    mean_mass = np.pi * 500.0 / 6.0 * (50e-6)**3
    concentration = q.astype(np.float64) * rho.astype(np.float64) / mean_mass
    mask = np.asarray((q > 0) & (concentration > 1e6), dtype=np.uint8)
    k, j, i = 12, 227, 0
    report = {
        'source_sha256': EXPECTED,
        'algorithm': 'C-order z,y,x uint8 mask: (QICE>0) and float64(QICE)*float64(float32(1/float32(AL+ALB)))/(pi*500/6*(50e-6)^3)>1e6',
        'shape_zyx': list(mask.shape),
        'mask_sha256': hashlib.sha256(mask.tobytes(order='C')).hexdigest(),
        'mask_count': int(np.count_nonzero(mask)),
        'positive_ice_count': int(np.count_nonzero(q > 0)),
        'all_native_ni_zero': bool(np.all(ni == 0)),
        'peak_implied_internal_ni_m-3': float(np.max(concentration)),
        'failed_fortran_ijk_slot': [i + 1, j + 1, k + 1, 2],
        'failed_cell_qice_kg_per_kg': float(q[k,j,i]),
        'failed_cell_file_dry_density_kg_per_m3': float(rho[k,j,i]),
        'ice_mean_mass_kg': mean_mass,
        'failed_cell_implied_ni_m-3': float(concentration[k,j,i]),
        'scope': 'prior-implied cap exceedance before background selection; file-state density proxy, not first-use density',
    }
    if report['mask_count'] != 106128 or not mask[k,j,i]:
        raise ValueError('independent recount differs')
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, sort_keys=True))

if __name__ == '__main__':
    main()
