#!/usr/bin/env python3
"""Compare the conditional ground profile with unchanged, retained LT1 HT."""
import argparse
import json
from pathlib import Path

import numpy as np

from audit_qbal_profile_domain import sha256
from diagnose_qbal_ground_reference import read_state
from diagnose_qbal_thickness_attribution import product, stats

G0 = 9.80665


def compare(ground, height):
    support = ground['support']
    before, after = ground['before'], ground['after']
    delta, bound = ground['delta'], ground['bound']
    if delta.ndim != support.ndim + 1 or delta.shape != (3,) + support.shape:
        raise ValueError('ground delta shape mismatch')
    change = delta[2]
    if height.shape != support.shape or not np.isfinite(height[support]).all():
        raise ValueError('retained HT support mismatch')
    arrays = (before, after, change, bound)
    if any(values.shape != support.shape for values in arrays):
        raise ValueError('ground comparison shape mismatch')
    if any(not np.isfinite(values[support]).all() for values in arrays):
        raise ValueError('nonfinite supported comparison input')
    if np.any(bound[support] < 0):
        raise ValueError('negative supported bound')
    stage = before - G0 * height
    final = after - G0 * height
    error = final - stage - change
    scale = bound + 32*np.finfo(np.float64).eps * (
        np.abs(before) + np.abs(after) + 2*G0*np.abs(height))
    if (not np.isfinite(stage[support]).all() or
            not np.isfinite(final[support]).all() or
            not np.isfinite(error[support]).all() or
            not np.isfinite(scale[support]).all()):
        raise ValueError('nonfinite supported defect')
    if np.any(np.abs(error[support]) > scale[support]):
        raise ValueError('HT/change closure failed')
    for values in (stage, final):
        values[~support] = np.nan
    return stage, final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ground-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    directory = args.ground_dir.resolve()
    repo = Path(__file__).resolve().parents[1]
    source_names = ('diagnose_qbal_ground_ht.py', 'diagnose_qbal_ground_reference.py',
                    'audit_qbal_profile_domain.py', 'diagnose_qbal_thickness_attribution.py',
                    'diagnose_qbal_sloping_faces.py', 'diagnose_qbal_boundary.py')
    source_pins = {name: sha256(repo/'tests'/name) for name in source_names}
    source = json.loads((directory/'report.json').read_text())
    if source['status'] != 'PASS_SCOPED / CONDITIONAL_GROUND_REFERENCE':
        raise ValueError('unexpected ground-reference status')
    inputs = {key: Path(value) for key, value in source['input_paths'].items()}
    for key, path in inputs.items():
        if sha256(path) != source['input_sha256'][key]:
            raise ValueError(f'changed ground input: {key}')
    for name in ('arrays.npz', 'prepared.bin'):
        if sha256(directory/name) != source['artifact_sha256'][name]:
            raise ValueError(f'changed ground artifact: {name}')
    thickness = json.loads(inputs['thickness_report'].read_text())
    retained = Path(thickness['input_paths']['lt1_1'])
    if sha256(retained) != thickness['input_sha256']['lt1_1']:
        raise ValueError('retained LT1 changed')

    with np.load(directory/'arrays.npz', allow_pickle=False) as stored:
        ground = {key: stored[key] for key in stored.files}
    nn, nz = ground['support'].shape
    pressure, _, state, valid = read_state(inputs['thickness_prepared'], nn, nz)
    if not np.array_equal(pressure, ground['pressure']):
        raise ValueError('pressure mismatch')
    original, _, _ = product(retained, [('ht', 'meters')], source['epoch'], pressure=pressure)
    original_ht = original['ht'].reshape((nn, nz), order='F')
    if not np.array_equal(state[:, :, 4], original_ht):
        raise ValueError('paired-state HT differs from retained LT1')
    if np.any(ground['support'] & (valid != 1)):
        raise ValueError('unsupported HT level')
    stage, final = compare(ground, state[:, :, 4])
    support = ground['support']
    if np.count_nonzero(np.any(support, axis=1)) != source['eligible_nodes']:
        raise ValueError('eligible node count changed')

    nx = thickness['grid_shape'][0]
    node, level = np.unravel_index(np.nanargmax(np.abs(stage)), stage.shape)
    largest_stage = {
        'i_j_one_based': [int(node % nx + 1), int(node // nx + 1)],
        'pressure_Pa': float(pressure[level]),
        'stage_minus_retained_ht': float(stage[node, level]),
        'final_minus_retained_ht': float(final[node, level]),
        'change': float(ground['delta'][2, node, level]),
    }

    if {name: sha256(repo/'tests'/name) for name in source_names} != source_pins:
        raise ValueError('diagnostic source changed during execution')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(output/'arrays.npz', stage_minus_ht=stage,
                        final_minus_ht=final, support=support,
                        pressure=pressure)
    report = {
        'status': 'PASS_SCOPED / CONDITIONAL_STAGE_HT_COMPARISON',
        'epoch': source['epoch'], 'supported_nodes': source['eligible_nodes'],
        'supported_node_levels': int(support.sum()),
        'units': 'm2 s-2',
        'paired_state_ht_equals_retained_lt1': True,
        'stage_minus_retained_ht': stats(stage),
        'final_minus_retained_ht': stats(final),
        'change': stats(ground['delta'][2]),
        'per_pressure': [{'pressure_Pa': float(p), 'stage_minus_retained_ht': stats(stage[:, k]),
                          'final_minus_retained_ht': stats(final[:, k])}
                         for k, p in enumerate(pressure)],
        'largest_absolute_stage_defect': largest_stage,
        'identity': '(final - retained HT) - (stage - retained HT) = conditional T/q change',
        'interpretation': 'The stage defect includes producer operator and datum differences; it is not an observed height error or an authorized correction.',
        'input_sha256': {'ground_report': sha256(directory/'report.json'),
                         'ground_arrays': sha256(directory/'arrays.npz'),
                         'thickness_prepared': sha256(inputs['thickness_prepared']),
                         'retained_lt1': sha256(retained)},
        'source_sha256': source_pins,
        'artifact_sha256': {'arrays.npz': sha256(output/'arrays.npz')},
        'production_authority': False,
    }
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'status': report['status'], 'supported_nodes': report['supported_nodes']}))


if __name__ == '__main__':
    main()
