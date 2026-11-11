#!/usr/bin/env python3
"""Select fixed B1 ice cases and export their unchanged file-state columns."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from netCDF4 import Dataset

EXPECTED = '9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'
FIELDS = ('QICE', 'QNICE', 'AL', 'ALB', 'T', 'P', 'PB', 'QVAPOR', 'QCLOUD',
          'QRAIN', 'QSNOW', 'QGRAUP', 'QNCLOUD', 'QNRAIN', 'QIB', 'QNCCN')

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def density(al, alb):
    return np.divide(np.float32(1), np.add(al, alb, dtype=np.float32), dtype=np.float32)

def dry_temperature(t, p, pb):
    pressure = np.add(p, pb, dtype=np.float32)
    exner = np.power(pressure / np.float32(100000), np.float32(287.0) / np.float32(1004.5))
    return np.multiply(np.add(t, np.float32(300), dtype=np.float32), exner, dtype=np.float32)

def nearest(values, mask, target):
    if values.shape != mask.shape or not np.any(mask):
        raise ValueError('selection mask empty or shape mismatch')
    distance = np.where(mask, np.abs(values - target), np.inf)
    # argmin on C-order flat array resolves ties lexicographically in z,y,x.
    return tuple(int(x) for x in np.unravel_index(np.argmin(distance), values.shape))

def select_cases(q, rho, cap, maximum_mass):
    if q.shape != rho.shape or q.ndim != 3:
        raise ValueError('expected matching z,y,x fields')
    if not np.all(np.isfinite(q)) or not np.all(np.isfinite(rho)) or np.any(q < 0) or np.any(rho <= 0):
        raise ValueError('invalid ice or density')
    ratio = q.astype(np.float64) * rho.astype(np.float64) / (cap * maximum_mass)
    positive = q > 0
    return {
        'interior_half_boundary': nearest(ratio, positive, 0.5),
        'closest_below_boundary': nearest(ratio, positive & (ratio < 1), 1),
        'closest_above_boundary': nearest(ratio, positive & (ratio > 1), 1),
        'first_infeasible_lexicographic': tuple(int(x) for x in np.argwhere(ratio > 1)[0]),
        'maximum_ice_water_content': tuple(int(x) for x in np.unravel_index(np.argmax(q.astype(np.float64) * rho.astype(np.float64)), q.shape)),
    }, ratio

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('policy', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    before = sha(args.input)
    if before != EXPECTED:
        raise ValueError('unexpected immutable B1 hash')
    policy = json.loads(args.policy.read_text())
    cap, max_mass = policy['number_cap'][1], policy['upper'][1]
    fixed_mass = np.pi * 500.0 / 6.0 * (50e-6)**3
    with Dataset(args.input) as ds:
        ds.set_auto_maskandscale(False)
        for field in FIELDS:
            if field not in ds.variables:
                raise ValueError(f'missing required source field {field}')
        q = np.asarray(ds['QICE'][0], dtype=np.float32)
        rho = density(np.asarray(ds['AL'][0], dtype=np.float32), np.asarray(ds['ALB'][0], dtype=np.float32))
        selected, ratio = select_cases(q, rho, cap, max_mass)
        if (selected['maximum_ice_water_content'] != (25, 71, 191)
                or selected['first_infeasible_lexicographic'] != (16, 93, 208)
                or ds['QNICE'][0, 16, 93, 208] != 0):
            raise ValueError('fixed case assumptions failed')
        units = {name: getattr(ds[name], 'units', '') for name in FIELDS}
        for name in ('PH', 'PHB', 'XLAND'):
            if name not in ds.variables:
                raise ValueError(f'missing required source field {name}')
            units[name] = getattr(ds[name], 'units', '')
        # Roles may overlap; each selected point appears once with all memberships.
        points = {}
        for role, point in selected.items():
            points.setdefault(point, []).append(role)
        cases = []
        for (k, j, i), roles in points.items():
            profiles = {name: np.asarray(ds[name][0, :, j, i], dtype=np.float32) for name in FIELDS}
            den = density(profiles['AL'], profiles['ALB'])
            temp = dry_temperature(profiles['T'], profiles['P'], profiles['PB'])
            qi = profiles['QICE'].astype(np.float64)
            # Public number is kg^-1; multiply by den for concentration m^-3.
            ph = np.asarray(ds['PH'][0, :, j, i], dtype=np.float32)
            phb = np.asarray(ds['PHB'][0, :, j, i], dtype=np.float32)
            geopotential = np.add(ph, phb, dtype=np.float32)
            profiles['PH_staggered'] = ph
            profiles['PHB_staggered'] = phb
            profiles['DELZ'] = np.diff(geopotential) / np.float32(9.81)
            profiles['den'] = den
            profiles['dry_tk'] = temp
            profiles['NI_nominal_maximum_mass_kg-1'] = qi / max_mass
            profiles['NI_fixed_50um_kg-1'] = qi / fixed_mass
            cases.append({'roles': roles, 'selected_zyx': [k, j, i],
                          'fortran_ijk': [i + 1, j + 1, k + 1],
                          'boundary_ratio': float(ratio[k, j, i]),
                          'XLAND': float(ds['XLAND'][0, j, i]),
                          'profiles': {name: value.tolist() for name, value in profiles.items()}})
    after = sha(args.input)
    if after != before:
        raise ValueError('input changed while reading')
    payload = {
        'source_file': str(args.input.resolve()), 'source_sha256_before': before, 'source_sha256_after': after,
        'policy_file': str(args.policy), 'policy_sha256': sha(args.policy),
        'generator_sha256': sha(__file__), 'shape_zyx': list(q.shape),
        'field_map': {name: {'source': name, 'units': units[name]} for name in (*FIELDS, 'PH', 'PHB', 'XLAND')},
        'selection': {'quantity': 'float64(QICE)*float64(den)/(nominal ice cap*nominal maximum ice mean mass)',
                      'nominal_ice_cap_m-3': cap, 'nominal_maximum_mean_mass_kg': max_mass,
                      'first_infeasible': 'first lexicographic z,y,x with ratio > 1; QNICE is zero at the selected B1 cell, while QICE is positive',
                      'maximum_ice_water_content': 'argmax(float64(QICE)*float64(den)), ties lexicographic z,y,x',
                      'positive_mask': 'QICE > 0', 'boundary_masks': 'strictly below or above 1',
                      'tie_break': 'lexicographic z,y,x', 'roles_may_overlap': True},
        'source_base_commit': 'aa526e672e3aba8a34c9014da618521d975db23e',
        'temperature_constants_source': 'docs/evidence/cp02_activation_path_20261110/reference/module_model_constants.F',
        'temperature_constants_source_sha256': sha('docs/evidence/cp02_activation_path_20261110/reference/module_model_constants.F'),
        'derived': {'DELZ': 'diff(float32(PH+PHB))/float32(9.81 m s-2); file-state layer thickness m; 40 staggered geopotential values retained',
                    'den': 'float32(1 / float32(AL + ALB)); kg m-3, file-state dry density proxy',
                    'dry_tk': 'float32(T+300) * (float32(P+PB)/100000)**(float32(287.0)/float32(1004.5)); K, dry Exner file-state proxy',
                    'NI_nominal_maximum_mass_kg-1': 'QICE / policy.upper[1]; nominal lambda_min maximum-mass candidate, can exceed entry cap',
                    'NI_fixed_50um_kg-1': 'QICE / (pi*500/6*(50e-6)**3); fixed 50 micrometre, 500 kg m-3 ice sphere',
                    'native_constants': 'nominal policy values are not source-real32 native constants; native replay must seed with its own pinned constants'},
        'scope': 'File-state inputs and proxies, not established first-use microphysics state. No input NetCDF modified.',
        'cases': cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.cases-', dir=args.output.parent))
    try:
        (tmp / 'profiles.json').write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n')
        os.rename(tmp, args.output)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    print(json.dumps({role: list(point) for role, point in selected.items()}, sort_keys=True))

if __name__ == '__main__':
    main()
