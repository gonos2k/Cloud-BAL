#!/usr/bin/env python3
"""Read-only dry-mass-fixed gas column from the retained cloud OFF/ON pair."""

import argparse
import json
from pathlib import Path

import numpy as np

from audit_qbal_profile_domain import sha256
from diagnose_qbal_thickness_attribution import product
from qbal_dry_mass_column import G0, dry_mass_column, remap_component_masses


TARGET_IJ = (55, 162)


def read_target(path, variable, units, epoch, pressure, node, navigation=None):
    fields, masks, navigation = product(
        path, [(variable, units)], epoch, navigation=navigation, pressure=pressure)
    values = fields[variable].reshape((-1, pressure.size), order='F')[node]
    valid = masks[variable].reshape((-1, pressure.size), order='F')[node]
    return values, valid, navigation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cloud-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report_path = args.cloud_report.resolve()
    report = json.loads(report_path.read_text())
    if (report.get('status') != 'PASS_SCOPED / CLOUD_ON_OFF_RELATIVE_FORCE' or
            report['target_node_vapor_column_increment']['node_i_j_one_based'] != list(TARGET_IJ) or
            report['target_node_vapor_column_increment']['pressure_interval_Pa'] != [100000.0, 5000.0]):
        raise ValueError('cloud report has a different target or support')
    names = ('thickness_report', 'thickness_arrays', 'on_lq3', 'off_lq3',
             'retained_lt1', 'receipt_o0')
    inputs = {name: Path(report['input_paths'][name]) for name in names}
    for name, path in inputs.items():
        if sha256(path) != report['input_sha256'][name]:
            raise ValueError(f'cloud report input changed: {name}')
    thickness = json.loads(inputs['thickness_report'].read_text())
    receipt = json.loads(inputs['receipt_o0'].read_text())
    supported_pressure = np.asarray(
        [row['pressure_Pa'] for row in receipt['target_profile_kg_kg']], dtype=np.float64)
    if (receipt['target_i_j_one_based'] != list(TARGET_IJ) or
            supported_pressure.shape != (20,) or supported_pressure[0] != 100000 or
            supported_pressure[-1] != 5000 or
            not np.array_equal(supported_pressure,
                               np.asarray(report['supported_pressure_levels_Pa']))):
        raise ValueError('target pressure profile differs from retained support')
    nx, ny, nz = map(int, thickness['grid_shape'])
    node = (TARGET_IJ[1] - 1) * nx + TARGET_IJ[0] - 1
    if not (0 <= node < nx * ny):
        raise ValueError('target node outside retained grid')
    with np.load(inputs['thickness_arrays'], allow_pickle=False) as arrays:
        full_pressure = np.asarray(arrays['pressure'], dtype=np.float64)
        valid = np.asarray(arrays['valid'][node])
        surface_pressure = float(arrays['ps'][TARGET_IJ[0] - 1, TARGET_IJ[1] - 1])
    if (full_pressure.shape != (nz,) or valid.shape != (nz,) or
            not np.isin(valid, (0, 1)).all() or
            not np.isfinite(surface_pressure) or surface_pressure < 100000):
        raise ValueError('invalid PR41 target support')
    indices = np.flatnonzero(valid)
    if (indices.size != 20 or not np.array_equal(indices, np.arange(indices[0], nz)) or
            not np.array_equal(full_pressure[indices], supported_pressure)):
        raise ValueError('target is not the same continuous 19-layer pressure column')
    epoch = int(thickness['epoch'])
    if (receipt.get('status') != 'PASS_SCOPED / CLOUD_SWITCH_CAUSAL_REPLAY' or
            receipt['case_epoch'] != epoch or
            receipt['input_sha256']['on_lq3'] != report['input_sha256']['on_lq3'] or
            receipt['input_sha256']['off_lq3'] != report['input_sha256']['off_lq3'] or
            receipt['on_equals_retained_lq3_bytes'] is not True):
        raise ValueError('cloud replay lineage or valid time differs')
    q1, on_valid, nav = read_target(inputs['on_lq3'], 'sh', 'kg/kg', epoch,
                                   full_pressure, node)
    q0, off_valid, _ = read_target(inputs['off_lq3'], 'sh', 'kg/kg', epoch,
                                  full_pressure, node, nav)
    temperature, t_valid, _ = read_target(
        inputs['retained_lt1'], 't3', 'degrees Kelvin', epoch, full_pressure, node, nav)
    if not (on_valid[indices].all() and off_valid[indices].all() and
            t_valid[indices].all()):
        raise ValueError('a supported target level is missing in the paired products')
    q0, q1, temperature = q0[indices], q1[indices], temperature[indices]
    pressure = full_pressure[indices]
    for k, row in enumerate(receipt['target_profile_kg_kg']):
        if q0[k] != row['without_cloud'] or q1[k] != row['with_cloud']:
            raise ValueError('cloud replay profile differs from receipt')

    state = dry_mass_column(pressure, q0, q1, temperature)
    if state['new_pressure'][0] > surface_pressure:
        raise ValueError('new lower model interface exceeds retained surface pressure')
    dry = state['dry_mass']
    old_vapor = state['old_vapor']
    new_vapor = state['new_vapor']
    new_width = np.diff(state['new_pressure']) * -1
    if (not np.allclose(new_width / G0, dry + new_vapor, rtol=2e-14, atol=1e-11) or
            not np.isclose((state['new_pressure'][0] - pressure[0]) / G0,
                           np.sum(new_vapor - old_vapor), rtol=2e-14, atol=1e-11)):
        raise ValueError('dry-mass pressure and vapor budgets do not close')
    fixed_pressure_vapor = float(np.sum((pressure[:-1] - pressure[1:]) *
                                        (state['new_q'] - state['old_q']) / G0))
    expected = report['target_node_vapor_column_increment']['increment_kg_m2']
    if not np.isclose(fixed_pressure_vapor, expected, rtol=0, atol=2e-11):
        raise ValueError('fixed-pressure reference vapor increment differs')
    # Repartition only the new column, including its moved lower edge.
    interior = pressure[(pressure < state['new_pressure'][0]) &
                        (pressure > state['new_pressure'][-1])]
    target = np.r_[state['new_pressure'][0], interior, state['new_pressure'][-1]]
    mapped_dry, mapped_vapor = remap_component_masses(
        state['new_pressure'], state['dry_mass'], state['new_vapor'], target)
    for original, mapped in ((state['dry_mass'], mapped_dry),
                             (state['new_vapor'], mapped_vapor)):
        if not np.isclose(np.sum(original), np.sum(mapped), rtol=2e-14, atol=1e-11):
            raise ValueError('component mass changed in comparison-grid remap')
    mapped_q = mapped_vapor / (mapped_dry + mapped_vapor)
    if not np.isfinite(mapped_q).all() or np.any((mapped_q < 0) | (mapped_q >= 1)):
        raise ValueError('remapped gas composition is invalid')
    for name, path in inputs.items():
        if sha256(path) != report['input_sha256'][name]:
            raise ValueError(f'input changed during calculation: {name}')

    repo = Path(__file__).resolve().parents[1]
    source_names = ('qbal_dry_mass_column.py', 'diagnose_qbal_dry_mass_column.py',
                    'diagnose_qbal_thickness_attribution.py', 'audit_qbal_profile_domain.py')
    source_hashes = {name: sha256(repo / 'tests' / name) for name in source_names}
    result = {
        'status': 'PASS_SCOPED / CONDITIONAL_DRY_MASS_COLUMN',
        'production_authority': False,
        'target_i_j_one_based': list(TARGET_IJ),
        'gas_model': 'dry air + vapor only; condensate, surface partial layer and energy response unsupported',
        'temperature': 'retained final LT1; pressure-cell endpoint mean held fixed',
        'humidity': 'cloud OFF/ON LQ3 gas specific humidity; endpoint mean attached to each dry-mass cell',
        'pressure_anchor': '5000 Pa upper interface fixed; 100000 Pa is not surface pressure',
        'pressure_coordinate_role': 'source pressure levels used as model integration interfaces, not native faces',
        'height_datum': 'none; only layer thicknesses are calculated',
        'retained_surface_pressure_Pa': surface_pressure,
        'old_omitted_surface_span_Pa': surface_pressure - pressure[0],
        'new_omitted_surface_span_Pa_if_PS_fixed': surface_pressure - state['new_pressure'][0],
        'old_model_interfaces_Pa': pressure.tolist(),
        'new_model_interfaces_Pa': state['new_pressure'].tolist(),
        'old_bottom_pressure_Pa': float(pressure[0]),
        'new_bottom_pressure_Pa': float(state['new_pressure'][0]),
        'old_dry_mass_kg_m2': float(np.sum(dry)),
        'new_dry_mass_kg_m2': float(np.sum(dry)),
        'old_vapor_mass_kg_m2': float(np.sum(old_vapor)),
        'new_vapor_mass_kg_m2': float(np.sum(new_vapor)),
        'fixed_pressure_vapor_increment_kg_m2': fixed_pressure_vapor,
        'fixed_dry_vapor_increment_kg_m2': float(np.sum(new_vapor - old_vapor)),
        'pressure_change_Pa': float(state['new_pressure'][0] - pressure[0]),
        'old_supported_thickness_m': float(np.sum(state['old_thickness'])),
        'new_supported_thickness_m': float(np.sum(state['new_thickness'])),
        'layers': [{
            'old_bottom_top_Pa': [float(pressure[k]), float(pressure[k + 1])],
            'new_bottom_top_Pa': [float(state['new_pressure'][k]),
                                  float(state['new_pressure'][k + 1])],
            'old_q_kg_kg': float(state['old_q'][k]),
            'new_q_kg_kg': float(state['new_q'][k]),
            'temperature_K': float(state['layer_temperature_K'][k]),
            'dry_mass_kg_m2': float(dry[k]),
            'old_vapor_kg_m2': float(old_vapor[k]),
            'new_vapor_kg_m2': float(new_vapor[k]),
            'old_thickness_m': float(state['old_thickness'][k]),
            'new_thickness_m': float(state['new_thickness'][k]),
        } for k in range(pressure.size - 1)],
        'post_repartition_target_interfaces_Pa': target.tolist(),
        'post_repartition_dry_mass_kg_m2': float(np.sum(mapped_dry)),
        'post_repartition_vapor_mass_kg_m2': float(np.sum(mapped_vapor)),
        'post_repartition_q_kg_kg': mapped_q.tolist(),
        'post_repartition_includes_moved_edge': True,
        'cloud_report_sha256': sha256(report_path),
        'input_sha256': {name: report['input_sha256'][name] for name in names},
        'source_sha256': source_hashes,
    }
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: result[key] for key in (
        'status', 'new_bottom_pressure_Pa', 'fixed_pressure_vapor_increment_kg_m2',
        'fixed_dry_vapor_increment_kg_m2')}, allow_nan=False))


if __name__ == '__main__':
    main()
