#!/usr/bin/env python3
"""Evaluate a conditional ground reference on hash-bound, thin-layer support."""
import argparse
import json
from pathlib import Path
import subprocess

import numpy as np

from audit_qbal_profile_domain import read_prepared, sha256
from diagnose_qbal_thickness_attribution import stats


def read_state(path, nn, nz):
    """Read the existing PR41 paired-state stream without changing its mask."""
    expected = 8 + 8 * (nz + nn + 5 * nn * nz) + 4 * nn * nz
    if path.stat().st_size != expected:
        raise ValueError('paired-state extent mismatch')
    with path.open('rb') as stream:
        if np.fromfile(stream, '<i4', 2).tolist() != [nn, nz]:
            raise ValueError('paired-state dimensions mismatch')
        pressure = np.fromfile(stream, '<f8', nz)
        ps = np.fromfile(stream, '<f8', nn)
        state = np.fromfile(stream, '<f8', 5*nn*nz).reshape((nn, nz, 5), order='F')
        valid = np.fromfile(stream, '<i4', nn*nz).reshape((nn, nz), order='F')
    return pressure, ps, state, valid


def read_output(path, nn, nz):
    fields = [('first', '<i4', (nn,)), ('eligible', '<i4', (nn,)),
              ('before', '<f8', (nn, nz)), ('after', '<f8', (nn, nz)),
              ('delta', '<f8', (3, nn, nz)), ('bound', '<f8', (nn, nz))]
    result = {}
    with path.open('rb') as stream:
        for name, dtype, shape in fields:
            count = int(np.prod(shape))
            values = np.fromfile(stream, dtype, count)
            if values.size != count:
                raise ValueError(f'truncated output: {name}')
            result[name] = values.reshape(shape, order='F')
        if stream.read(1):
            raise ValueError('unexpected output suffix')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--thickness-dir', type=Path, required=True)
    parser.add_argument('--geometry-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    td, gd = args.thickness_dir.resolve(), args.geometry_dir.resolve()
    inputs = {'thickness_report': td/'report.json', 'thickness_prepared': td/'prepared.bin',
              'thickness_arrays': td/'arrays.npz', 'geometry_report': gd/'report.json',
              'geometry_prepared': gd/'prepared.bin', 'geometry_arrays': gd/'arrays.npz'}
    pins = {name: sha256(path) for name, path in inputs.items()}
    tr = json.loads(inputs['thickness_report'].read_text())
    gr = json.loads(inputs['geometry_report'].read_text())
    for prefix, report in [('thickness', tr), ('geometry', gr)]:
        for field, filename in [('prepared', 'prepared.bin'), ('arrays', 'arrays.npz')]:
            if pins[prefix+'_'+field] != report['artifact_sha256'][filename]:
                raise ValueError(f'{prefix} {field} hash mismatch')
    if tr['input_sha256']['source_report'] != pins['geometry_report']:
        raise ValueError('paired-state/prior source lineage mismatch')
    if tr['epoch'] != gr['times'][1]:
        raise ValueError('source valid times differ')
    if not gr['status'].startswith('THERMODYNAMIC_10M_PRIOR /'):
        raise ValueError('the thermodynamic 10 m prior is required')
    case = read_prepared(inputs['geometry_prepared'])
    nn, nz = case['nn'], case['nz']
    pressure, ps, state, valid = read_state(inputs['thickness_prepared'], nn, nz)
    with np.load(inputs['thickness_arrays'], allow_pickle=False) as layers:
        if (not np.array_equal(pressure, layers['pressure']) or
                not np.array_equal(ps, layers['ps'].ravel(order='F')) or
                not np.array_equal(valid, layers['valid'])):
            raise ValueError('paired-state stream/array mismatch')
    with np.load(inputs['geometry_arrays'], allow_pickle=False) as prior:
        if prior['p10'].shape != (3, nn) or prior['thermo'].shape != (3, nn, 5):
            raise ValueError('prior extent mismatch')
        if prior['mapped'].shape != (3, nn) or not np.all(prior['mapped'][1] == 1):
            raise ValueError('central-time prior is not fully available')
        if not np.array_equal(prior['triangles'], case['triangles']):
            raise ValueError('prior mesh mismatch')
        p10, tv = prior['p10'][1], prior['thermo'][1, :, 0]
    if (not np.array_equal(pressure, case['pressure']) or
            not np.array_equal(ps, case['ps'][1]) or
            not np.array_equal(case['times'], gr['times'])):
        raise ValueError('pressure/PS/time alignment mismatch')
    if not np.isin(valid, [0, 1]).all():
        raise ValueError('invalid source mask')

    # Freeze support using inputs alone, before evaluating any geopotential.
    above = pressure[None, :] <= ps[:, None]
    first = np.argmax(above, axis=1)
    eligible = above.any(axis=1) & (p10 <= pressure[first])
    for node, k in enumerate(first):
        eligible[node] &= bool(valid[node, k:].all())
    support = eligible[:, None] & (np.arange(nz)[None, :] >= first[:, None])
    triangle_support = support[case['triangles']].all(axis=1)

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with (out/'prepared.bin').open('wb') as stream:
        np.array([nn, nz], '<i4').tofile(stream)
        for values in (pressure, ps, p10, tv, case['terrain'], state[:, :, :4]):
            np.asarray(values, '<f8').ravel(order='F').tofile(stream)
        np.asarray(valid, '<i4').ravel(order='F').tofile(stream)
    repo = Path(__file__).resolve().parents[1]
    modules = ['qbal_thickness_attribution.f90', 'qbal_ground_reference.f90',
               'diagnose_qbal_ground_reference.f90']
    sources = ['tests/'+name for name in modules] + [
        'tests/diagnose_qbal_ground_reference.py', 'tests/intel_toolchain.sh',
        'tests/audit_qbal_profile_domain.py', 'tests/diagnose_qbal_thickness_attribution.py']
    source_pins = {name: sha256(repo/name) for name in sources}
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
 "$CLOUD_BAL_FC" "${flags[@]}" -convert little_endian ''' +
        ' '.join('"$repo/tests/'+name+'"' for name in modules) + ''' -o diagnose
 ./diagnose "$out/prepared.bin" result.bin
 )
done
''')
    with (out/'intel.log').open('w') as log:
        subprocess.run(['bash', str(script), str(repo), str(out)],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    results = [read_output(out/level/'result.bin', nn, nz) for level in ('O0', 'O2')]
    for result in results:
        if (not np.array_equal(result['eligible'], eligible.astype(np.int32)) or
                not np.array_equal(result['first'], np.where(eligible, first+1, 0))):
            raise ValueError('Fortran/input support mismatch')
        for name in ('before', 'after', 'delta', 'bound'):
            values = result[name]
            if not np.isfinite(values[..., support]).all() or not np.isnan(values[..., ~support]).all():
                raise ValueError(f'output support/NaN mismatch: {name}')
        if np.any(result['bound'][support] < 0):
            raise ValueError('negative arithmetic bound')
        if np.any(np.abs(result['after']-result['before']-result['delta'][2])[support] > result['bound'][support]):
            raise ValueError('absolute/change closure failed')
        if np.any(np.abs(result['delta'][0]+result['delta'][1]-result['delta'][2])[support] > result['bound'][support]):
            raise ValueError('temperature/moisture closure failed')
    x, y = results
    for name in ('before', 'after', 'delta'):
        if np.any(np.abs(x[name]-y[name])[..., support] > (x['bound']+y['bound'])[support]):
            raise ValueError(f'O0/O2 arithmetic mismatch: {name}')
    if {name: sha256(path) for name, path in inputs.items()} != pins:
        raise ValueError('inputs changed during execution')
    if {name: sha256(repo/name) for name in sources} != source_pins:
        raise ValueError('sources changed during execution')
    np.savez_compressed(out/'arrays.npz', pressure=pressure, support=support,
                        triangle_support=triangle_support, triangles=case['triangles'], **x)
    report = {
        'status': 'PASS_SCOPED / CONDITIONAL_GROUND_REFERENCE', 'epoch': tr['epoch'],
        'eligible_nodes': int(eligible.sum()),
        'eligible_triangles': int(triangle_support.any(axis=1).sum()),
        'reference_pressure_Pa': float(pressure[-1]),
        'reference_change_m2_s2': {name: stats(x['delta'][i, :, -1])
                                 for i, name in enumerate(('temperature', 'moisture', 'total'))},
        'bitwise_equal_O0_O2': sha256(out/'O0/result.bin') == sha256(out/'O2/result.bin'),
        'contract': 'Shared g0*AVG datum and constant LSX Tv partial layer only inside p10..PS; '
                    'contiguous endpoint-Tv regular layers. Common partial cancels from change; '
                    'junction Tv may jump. Constructed stage is not retained HT.',
        'physical_reference_authority': False, 'production_authority': False,
        'physical_flux_residual': None,
        'limitations': ['Ground datum and partial-layer representation remain conditional.',
                        'No lower wind, 0-10 m transport or full column balance is constructed.',
                        'This consumes PR39 geometry and PR41 states, not PR42 force arrays.'],
        'input_paths': {name: str(path) for name, path in inputs.items()},
        'input_sha256': pins, 'source_sha256': source_pins,
        'artifact_sha256': {name: sha256(out/name) for name in ('prepared.bin', 'arrays.npz')},
    }
    (out/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({name: report[name] for name in ('status', 'eligible_nodes', 'eligible_triangles')}))


if __name__ == '__main__':
    main()
