"""Locate retained raw momentum responses; no new model or normalization."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import netCDF4

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr99_native_contract_20261022/Cloud-BAL')
sys.path.insert(0, str(ROOT / 'tools'))
import pr98_native_effect as native
from pr87_native_history import _finite


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


report_path = ROOT / 'docs/evidence/pr99_native_projection_20261022/response.json'
report = json.loads(report_path.read_text())
receipts = {'P': report['receipt'], **{
    arm: {'path': report['frozen_capture_binding']['arms'][name]['receipt_path'],
          'sha256': report['frozen_capture_binding']['arms'][name]['receipt_sha256']}
    for arm, name in (('H', 'HYDRO'), ('C', 'COUPLED'))}}
roots, pins, inputs = {}, {}, {}
for arm, binding in receipts.items():
    path = Path(binding['path'])
    assert sha(path) == binding['sha256']
    receipt = json.loads(path.read_text())
    assert receipt['status'] == 'COMPLETE' and receipt['returncode'] == 0
    roots[arm] = path.parent / 'run'
    pins[arm] = {row['path']: row['sha256'] for row in receipt['generated_files']}
    input_path = roots[arm] / 'wrfinput_d01'
    assert sha(input_path) == receipt['candidate_wrfinput_sha256']
    with netCDF4.Dataset(input_path) as ds:
        ds.set_auto_mask(False)
        inputs[arm] = {name: _finite(ds, name, 0) for name in ('U', 'V')}

composition = json.loads(native.COMPOSITION.read_text())['composed_qc_vertical_influence']
support = native.cloud.make_masks(composition, (39, 280, 232))['original_613_native_support']


def read(arm, prefix):
    paths = list(roots[arm].glob(prefix + '*.bin'))
    assert len(paths) == 1
    path = paths[0]
    expected = pins[arm][path.name]
    assert sha(path) == expected
    meta, array = native.native_capture_file(roots[arm], prefix, 3)
    assert sha(path) == expected
    return meta, array.astype(np.float64)


def curvature(array, k, j, i):
    if not (0 <= k < array.shape[0] and 0 < j < array.shape[1]-1 and 0 < i < array.shape[2]-1):
        return None
    return float(array[k,j,i-1] + array[k,j,i+1] + array[k,j-1,i] + array[k,j+1,i] - 4*array[k,j,i])


rows = {}
for field, wind, axis, packet in (
    ('advu_ru_tend', 'U', 'i', True), ('advv_rv_tend', 'V', 'j', True),
    ('hdifu_ru_tendf', 'U', 'i', True), ('hdifv_rv_tendf', 'V', 'j', True),
    ('assembled_ru_tend_out_', 'U', 'i', False), ('assembled_rv_tend_out_', 'V', 'j', False)):
    arrays, metas = {}, {}
    for arm in roots:
        prefix = 'pr98_' + field
        if packet:
            before_meta, before = read(arm, prefix + '_in')
            meta, after = read(arm, prefix + '_out')
            assert before_meta['fortran_bounds'] == meta['fortran_bounds']
            arrays[arm] = after - before
        else:
            meta, arrays[arm] = read(arm, prefix)
        metas[arm] = meta
    assert all(meta['fortran_bounds'] == metas['H']['fortran_bounds'] for meta in metas.values())
    meta = metas['H']
    mask = native.support_native_mask(meta, arrays['H'].shape, support, axis)
    d = {name: arrays[a] - arrays[b] for name, a, b in (('P-H','P','H'), ('C-H','C','H'), ('P-C','P','C'))}
    coords = np.argwhere(mask)
    order = np.argsort(np.abs(d['P-H'][mask]))[::-1]
    ims, _, kms, _, jms, _ = meta['fortran_bounds'][:6]
    top = []
    for index in order[:8]:
        i0, k0, j0 = (int(v) for v in coords[index])
        i, k, j = i0+ims, k0+kms, j0+jms
        item = {'native_face_ikj': [i,k,j], 'source_differences': {
            name: float(array[i0,k0,j0]) for name,array in d.items()}}
        item['initial_face_wind_increment_m_s'] = {
            name: float((inputs[a][wind] - inputs[b][wind])[k-1,j-1,i-1])
            for name,a,b in (('P-H','P','H'), ('C-H','C','H'))}
        item['computational_grid_curvature_m_s_per_grid_step_squared'] = {
            name: curvature(inputs[a][wind] - inputs[b][wind], k-1,j-1,i-1)
            for name,a,b in (('P-H','P','H'), ('C-H','C','H'))}
        top.append(item)
    profiles = []
    for k0 in range(mask.shape[1]):
        level_mask = mask[:,k0,:]
        if level_mask.any():
            profiles.append({'native_k': k0+kms, 'faces': int(level_mask.sum()), **{
                name: float(np.linalg.norm(array[:,k0,:][level_mask])) for name,array in d.items()}})
    rows[field] = {'faces': int(mask.sum()), 'bounds': meta['fortran_bounds'],
        'L2': {name: float(np.linalg.norm(array[mask])) for name,array in d.items()},
        'top_eight_P_minus_H': top, 'level_L2': profiles,
        'top_eight_squared_norm_fraction': float(np.sum(d['P-H'][mask][order[:8]]**2) / np.sum(d['P-H'][mask]**2))}

result = {'schema': 'pr100_closed_raw_momentum_locality_v1',
    'source_report': {'path': str(report_path), 'sha256': sha(report_path)},
    'script_sha256': sha(Path(__file__)), 'receipt_bindings': receipts, 'rows': rows,
    'limits': ['Only receipt-closed original C1 H/C and projected P20; no C2 outputs.',
               'Separate native source-array differences, not acceleration or energy and not a complete momentum decomposition.',
               'Native k is a level index, not a geometric height.',
               'Wind curvature is an unweighted computational-grid diagnostic, not the native diffusion operator or physical Laplacian.',
               'Top locations describe retained fixed support, not a newly selected verification region.',
               'Spatial colocation does not establish causality; no wind or physics changes made.'],
    'physical_approval': 'FAIL_OPEN', 'observation_skill': 'NOT_EVALUATED'}
out = Path('/var/tmp/pr100_momentum_locality_20261022.json')
with out.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
    stream.write('\n')
print(out, sha(out))
