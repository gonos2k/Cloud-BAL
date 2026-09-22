#!/usr/bin/env python3
"""Attribute same-case humidity changes with a paired cloud-switch replay."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from audit_qbal_profile_domain import sha256
from diagnose_qbal_ground_reference import read_state
from diagnose_qbal_thickness_attribution import product


def paired_inputs(on, off):
    """Check copied producer inputs; LQ3/LH3/LH4 are generated outputs."""
    excluded = {'lq3', 'lh3', 'lh4'}
    def paths(root):
        names = set()
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            name = path.relative_to(root)
            if len(name.parts) > 1 and name.parts[0] == 'lapsprd' and name.parts[1] in excluded:
                continue
            if name.parts[0] == 'replay' and name.suffix == '.log':
                continue
            names.add(name)
        return names
    names = paths(on)
    if names != paths(off):
        raise ValueError('paired input file sets differ')
    switch = Path('static/moisture_switch.nl')
    before = (on/switch).read_text()
    if before.count('CLOUD_SWITCH = 1,') != 1:
        raise ValueError('ON cloud switch is not unique')
    if (off/switch).read_text() != before.replace('CLOUD_SWITCH = 1,', 'CLOUD_SWITCH = 0,'):
        raise ValueError('cloud switch is not the only configuration change')
    digest = hashlib.sha256()
    for name in sorted(names):
        if name == switch:
            continue
        left, right = sha256(on/name), sha256(off/name)
        if left != right:
            raise ValueError(f'paired input differs: {name}')
        digest.update(f'{name}\0{left}\n'.encode())
    return len(names), digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair-dir', type=Path, required=True)
    parser.add_argument('--thickness-report', type=Path, required=True)
    parser.add_argument('--retained-lc3', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--i', type=int, default=55)
    parser.add_argument('--j', type=int, default=162)
    args = parser.parse_args()
    pair = args.pair_dir.resolve()
    on, off = pair/'on', pair/'off'
    count, input_hash = paired_inputs(on, off)
    lc3_hash = sha256(args.retained_lc3)
    if sha256(on/'lapsprd/lc3/262281300.lc3') != lc3_hash:
        raise ValueError('LC3 source differs from retained input')
    for mode in ('on', 'off'):
        if 'LQ3_PRODUCER_SUCCESS' not in (pair/f'{mode}.log').read_text():
            raise ValueError(f'{mode} producer did not finish successfully')
    build = args.build_dir.resolve()
    if not (build/'run_verified.sh').is_file():
        raise ValueError('verified humidity launcher missing')

    source = json.loads(args.thickness_report.read_text())
    if source['status'] != 'PASS_SCOPED / MATCHED_LAYER_THERMODYNAMIC_ATTRIBUTION':
        raise ValueError('unexpected thickness-attribution status')
    retained = Path(source['input_paths']['lq3_1'])
    if sha256(retained) != source['input_sha256']['lq3_1']:
        raise ValueError('retained LQ3 changed')
    prepared = args.thickness_report.parent/'prepared.bin'
    if sha256(prepared) != source['artifact_sha256']['prepared.bin']:
        raise ValueError('paired-state stream changed')
    nx, ny, nz = source['grid_shape']
    nn = nx*ny
    pressure, _, state, valid = read_state(prepared, nn, nz)
    files = {mode: pair/mode/'lapsprd/lq3/262281300.lq3' for mode in ('on', 'off')}
    if sha256(files['on']) != sha256(retained):
        raise ValueError('ON output does not reproduce retained LQ3 bytes')
    values, masks, navigation = {}, {}, {}
    for mode, path in files.items():
        data, mask, nav = product(path, [('sh', 'kg/kg')], source['epoch'], pressure=pressure)
        values[mode] = data['sh'].reshape((nn, nz), order='F')
        masks[mode] = mask['sh'].reshape((nn, nz), order='F')
        navigation[mode] = nav
    if navigation['on'] != navigation['off'] or not np.array_equal(masks['on'], masks['off']):
        raise ValueError('paired output geometry or support differs')
    if not (1 <= args.i <= nx and 1 <= args.j <= ny):
        raise ValueError('target node outside grid')
    node = (args.j-1)*nx + args.i-1
    rows = []
    for k, p in enumerate(pressure):
        if valid[node, k] != 1 or not masks['on'][node, k]:
            continue
        stage = float(state[node, k, 1])
        without = float(values['off'][node, k])
        with_cloud = float(values['on'][node, k])
        rows.append({'pressure_Pa': float(p), 'stage': stage, 'without_cloud': without,
                     'with_cloud': with_cloud, 'cloud_effect': with_cloud-without,
                     'other_analysis_change': without-stage,
                     'total_analysis_change': with_cloud-stage})
    active = masks['on'] & (values['on'] != values['off'])
    if not active.any():
        raise ValueError('cloud switch changed no valid LQ3 value')
    repo = Path(__file__).resolve().parents[1]
    names = ('diagnose_qbal_cloud_switch.py', 'diagnose_qbal_ground_reference.py',
             'audit_qbal_profile_domain.py', 'diagnose_qbal_thickness_attribution.py',
             'diagnose_qbal_sloping_faces.py', 'diagnose_qbal_boundary.py')
    report = {
        'status': 'PASS_SCOPED / CLOUD_SWITCH_CAUSAL_REPLAY',
        'case_epoch': source['epoch'], 'target_i_j_one_based': [args.i, args.j],
        'paired_input_files': count, 'paired_input_manifest_sha256': input_hash,
        'on_equals_retained_lq3_bytes': True,
        'changed_valid_node_levels': int(active.sum()),
        'negative_cloud_effect_node_levels': int(np.count_nonzero(
            masks['on'] & (values['on'] < values['off']))),
        'max_cloud_effect_kg_kg': float(np.max((values['on']-values['off'])[active])),
        'target_profile_kg_kg': rows,
        'input_sha256': {'retained_lc3': lc3_hash, 'retained_lq3': sha256(retained),
                         'on_lq3': sha256(files['on']), 'off_lq3': sha256(files['off']),
                         'thickness_report': sha256(args.thickness_report),
                         'thickness_prepared': sha256(prepared),
                         'humidity_executable': sha256(build/'klps_anal_humd.exe'),
                         'verified_launcher': sha256(build/'run_verified.sh'),
                         'build_inputs': sha256(build/'inputs.sha256'),
                         'build_runtime': sha256(build/'runtime.sha256'),
                         'on_log': sha256(pair/'on.log'),
                         'off_log': sha256(pair/'off.log')},
        'source_sha256': {name: sha256(repo/'tests'/name) for name in names},
        'interpretation': 'ON-OFF is the net late cloud-moistening-block effect, including subsequent QC; stage-to-ON also includes earlier humidity analysis steps.',
        'production_authority': False,
    }
    with args.output.open('x') as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({key: report[key] for key in ('status', 'changed_valid_node_levels')}))


if __name__ == '__main__':
    main()
