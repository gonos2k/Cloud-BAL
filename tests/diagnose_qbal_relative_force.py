#!/usr/bin/env python3
"""Read-only common-reference geopotential and pressure-force attribution."""
import argparse
import json
from pathlib import Path
import subprocess

import numpy as np

from audit_qbal_profile_domain import read_prepared, sha256
from diagnose_qbal_thickness_attribution import stats


def read_output(path, nn, nz, nt):
    shapes = [('reachable', '<i4', (nn, nz)), ('triangle_support', '<i4', (nt, nz)),
              ('xy', '<f8', (2, nn)), ('evaluation_latitude', '<f8', (nt,)),
              ('phi', '<f8', (3, nn, nz)), ('phi_bound', '<f8', (nn, nz)),
              ('gradient_chart', '<f8', (2, 3, nt, nz)),
              ('acceleration_en', '<f8', (2, 3, nt, nz)), ('force_bound', '<f8', (nt, nz))]
    result = {}
    with path.open('rb') as stream:
        for name, dtype, shape in shapes:
            x = np.fromfile(stream, dtype, int(np.prod(shape)))
            if x.size != np.prod(shape):
                raise ValueError(f'truncated output: {name}')
            result[name] = x.reshape(shape, order='F')
        if stream.read(1):
            raise ValueError('unexpected output suffix')
    for name in ('reachable', 'triangle_support'):
        if not np.isin(result[name], [0, 1]).all():
            raise ValueError('invalid support flag')
    if not np.isfinite(result['xy']).all() or not np.isfinite(result['evaluation_latitude']).all():
        raise ValueError('invalid output geometry')
    for name, support in [('phi', 'reachable'), ('phi_bound', 'reachable'),
                          ('gradient_chart', 'triangle_support'),
                          ('acceleration_en', 'triangle_support'), ('force_bound', 'triangle_support')]:
        a, mask = result[name], result[support].astype(bool)
        if not np.isfinite(a[..., mask]).all() or not np.isnan(a[..., ~mask]).all():
            raise ValueError(f'output support/NaN mismatch: {name}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--thickness-dir', type=Path, required=True)
    parser.add_argument('--geometry-dir', type=Path, required=True, help='PR39 prepared replay')
    parser.add_argument('--reference-pressure-pa', type=float, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    td, gd = args.thickness_dir.resolve(), args.geometry_dir.resolve()
    inputs = {'thickness_report': td/'report.json', 'thickness_arrays': td/'arrays.npz',
              'geometry_report': gd/'report.json', 'geometry_prepared': gd/'prepared.bin'}
    pins = {n: sha256(p) for n, p in inputs.items()}
    tr = json.loads(inputs['thickness_report'].read_text())
    gr = json.loads(inputs['geometry_report'].read_text())
    if pins['thickness_arrays'] != tr['artifact_sha256']['arrays.npz']:
        raise ValueError('thickness artifact hash mismatch')
    if pins['geometry_prepared'] != gr['artifact_sha256']['prepared.bin']:
        raise ValueError('geometry artifact hash mismatch')
    if pins['geometry_report'] != tr['input_sha256']['source_report']:
        raise ValueError('thickness/geometry source lineage mismatch')
    if tr['epoch'] != gr['times'][1]:
        raise ValueError('source valid times differ')
    if tr['field_order'][2:6] != ['temperature', 'moisture', 'total', 'arithmetic_bound']:
        raise ValueError('thickness field contract mismatch')
    case = read_prepared(inputs['geometry_prepared'])
    if not np.array_equal(case['times'], gr['times']):
        raise ValueError('prepared geometry times differ from receipt')
    a = np.load(inputs['thickness_arrays'], allow_pickle=False)
    nn, nz, nt = case['nn'], case['nz'], case['nt']
    p = a['pressure']
    if (not np.array_equal(p, case['pressure']) or
            not np.array_equal(a['ps'].ravel(order='F'), case['ps'][1]) or
            int(np.prod(a['grid_shape'])) != nn):
        raise ValueError('pressure/grid/PS mismatch')
    if a['valid'].shape != (nn, nz) or a['supported'].shape != (nn, nz-1):
        raise ValueError('support extent mismatch')
    if not np.isin(a['valid'], [0, 1]).all() or not np.isin(a['supported'], [0, 1]).all():
        raise ValueError('invalid source support')
    if not np.array_equal(a['supported'], a['valid'][:, :-1]*a['valid'][:, 1:]):
        raise ValueError('source layer mask mismatch')
    ref = np.flatnonzero(p == args.reference_pressure_pa)
    if len(ref) != 1:
        raise ValueError('reference must be an exact shared pressure level')
    ref = int(ref[0])
    layers = a['layer'][[2, 3, 4, 5]]
    if layers.shape != (4, nn, nz-1):
        raise ValueError('thickness extent mismatch')
    mask = a['supported'].astype(bool)
    if not np.isfinite(layers[:, mask]).all() or not np.isnan(layers[:, ~mask]).all():
        raise ValueError('thickness NaN/support mismatch')
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with (out/'prepared.bin').open('wb') as stream:
        np.array([nn, nz, nt, ref+1], '<i4').tofile(stream)
        for x in (case['parameters'][:3], p, case['lat'], case['lon'], case['ps'][1], layers):
            np.asarray(x, '<f8').ravel(order='F').tofile(stream)
        for x in (a['valid'], a['supported'], case['triangles'].T+1):
            np.asarray(x, '<i4').ravel(order='F').tofile(stream)
    repo = Path(__file__).resolve().parents[1]
    modules = ['qbal_physical_boundary.f90', 'qbal_pressure_flux.f90', 'qbal_sloping_geometry.f90',
               'qbal_relative_pressure_force.f90', 'diagnose_qbal_relative_force.f90']
    sources = ['tests/'+n for n in modules]+['tests/diagnose_qbal_relative_force.py',
        'tests/audit_qbal_profile_domain.py', 'tests/diagnose_qbal_thickness_attribution.py', 'tests/intel_toolchain.sh']
    source_pins = {n: sha256(repo/n) for n in sources}
    script = out/'run.sh'
    script.write_text('''#!/usr/bin/env bash
set -euo pipefail
repo=$1
out=$2
. "$repo/tests/intel_toolchain.sh"
for level in O0 O2; do
 mkdir "$out/$level"
 if [[ $level == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
 (
 cd "$out/$level"
 "$CLOUD_BAL_FC" "${flags[@]}" -convert little_endian '''+
    ' '.join('"$repo/tests/'+n+'"' for n in modules)+''' -o diagnose
 ./diagnose "$out/prepared.bin" result.bin
 )
done
''')
    with (out/'intel.log').open('w') as log:
        subprocess.run(['bash', str(script), str(repo), str(out)], stdout=log, stderr=subprocess.STDOUT, check=True)
    x, y = [read_output(out/level/'result.bin', nn, nz, nt) for level in ('O0', 'O2')]
    # Independently derive connectivity to the common reference from source masks.
    connected = np.zeros((nn, nz), bool)
    connected[:, ref] = a['valid'][:, ref].astype(bool)
    for k in range(ref-1, -1, -1): connected[:, k] = connected[:, k+1] & mask[:, k]
    for k in range(ref+1, nz): connected[:, k] = connected[:, k-1] & mask[:, k-1]
    expected = connected[case['triangles']].all(axis=1)
    if not np.array_equal(x['reachable'], connected) or not np.array_equal(x['triangle_support'], expected):
        raise ValueError('reference-connected support mismatch')
    for name in ('reachable', 'triangle_support'):
        if not np.array_equal(x[name], y[name]): raise ValueError('O0/O2 support differs')
    for name, bound in [('phi', 'phi_bound'), ('acceleration_en', 'force_bound')]:
        if np.any(np.abs(x[name]-y[name]) > x[bound]+y[bound]):
            raise ValueError(f'O0/O2 arithmetic difference: {name}')
    if np.any(np.abs(x['phi'][0]+x['phi'][1]-x['phi'][2]) > x['phi_bound']):
        raise ValueError('relative geopotential attribution failed')
    if np.any(np.abs(x['acceleration_en'][:, 0]+x['acceleration_en'][:, 1]-x['acceleration_en'][:, 2]) > x['force_bound']):
        raise ValueError('force attribution failed')
    np.savez_compressed(out/'arrays.npz', pressure=p, triangles=case['triangles'], **x)
    names = ('temperature', 'moisture', 'total')
    summary = []
    for k, pressure in enumerate(p):
        record = {'pressure_Pa': float(pressure), 'supported_nodes': int(connected[:, k].sum()),
                  'supported_triangles': int(expected[:, k].sum()), 'components': {}}
        for c, name in enumerate(names):
            acceleration = x['acceleration_en'][:, c, :, k]
            magnitude = np.sqrt(np.sum(acceleration**2, axis=0))
            entry = {'phi_m2_s2': stats(x['phi'][c, :, k]), 'acceleration_magnitude_m_s2': stats(magnitude)}
            if np.isfinite(magnitude).any():
                t = int(np.nanargmax(magnitude))
                entry['maximum_location'] = {'triangle_one_based': t+1,
                    'vertices_one_based': (case['triangles'][t]+1).tolist(),
                    'evaluation_latitude_rad': float(x['evaluation_latitude'][t]),
                    'colocated_acceleration_en_m_s2': x['acceleration_en'][:, :, t, k].tolist()}
            record['components'][name] = entry
        summary.append(record)
    phi_error = np.abs(x['phi'][0]+x['phi'][1]-x['phi'][2])
    force_error = np.max(np.abs(x['acceleration_en'][:, 0]+x['acceleration_en'][:, 1]-x['acceleration_en'][:, 2]), axis=0)
    phi_nonzero = np.isfinite(x['phi_bound']) & (x['phi_bound'] > 0)
    force_nonzero = np.isfinite(x['force_bound']) & (x['force_bound'] > 0)
    arithmetic = {
        'maximum_phi_closure_ratio': float(np.max(phi_error[phi_nonzero]/x['phi_bound'][phi_nonzero])) if phi_nonzero.any() else None,
        'maximum_force_closure_ratio': float(np.max(force_error[force_nonzero]/x['force_bound'][force_nonzero])) if force_nonzero.any() else None,
        'maximum_O0_O2_phi_difference_m2_s2': stats(np.abs(x['phi']-y['phi']))['max'],
        'maximum_O0_O2_force_difference_m_s2': stats(np.abs(x['acceleration_en']-y['acceleration_en']))['max'],
    }
    report = {'status': 'PASS_SCOPED / ZERO_REFERENCE_RELATIVE_PRESSURE_FORCE', 'epoch': tr['epoch'],
              'connected_node_levels': int(connected.sum()), 'supported_triangle_levels': int(expected.sum()),
              'arithmetic': arithmetic, 'reference_pressure_Pa': float(p[ref]), 'reference_delta_phi_m2_s2': 0.0,
              'unknown_reference_force': 'Physical acceleration also includes -grad_p(deltaPhi_reference); not inferred here.',
              'metric': 'Equal-area spherical chart; P1 triangle gradient converted to physical east/north at chart centroid.',
              'chart_parameters_lat0_lon0_radius': case['parameters'][:3].tolist(),
              'level_results': summary, 'input_paths': {n: str(v) for n, v in inputs.items()},
              'input_sha256': pins, 'source_sha256': source_pins,
              'physical_pressure_gradient_force': None, 'height_or_wind_modified': False,
              'production_authority': False, 'time_contract': 'Single retained 13 UTC state difference, not time tendency.'}
    for name, path in inputs.items():
        if sha256(path) != pins[name]: raise ValueError('input changed during diagnostic')
    for name, pin in source_pins.items():
        if sha256(repo/name) != pin: raise ValueError('source changed during diagnostic')
    report['artifact_sha256'] = {n: sha256(out/n) for n in ('prepared.bin', 'arrays.npz')}
    (out/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print('PASS:', int(connected.sum()), 'node-levels;', int(expected.sum()), 'triangle-levels; reference', p[ref])


if __name__ == '__main__':
    main()
