#!/usr/bin/env python3
"""Diagnose the PR44 cloud ON−OFF relative pressure force on one PR42 triangle."""
import argparse
import json
from pathlib import Path

import numpy as np

from audit_qbal_profile_domain import read_prepared, sha256
from diagnose_qbal_cloud_switch import paired_inputs
from diagnose_qbal_ground_ht_force import common_triangle_support, triangle_pressure_force
from diagnose_qbal_thickness_attribution import product


RD_AIR = 287.05
G0 = 9.80665
EPSILON_WATER = 0.622
ALPHA = 1.0 / EPSILON_WATER - 1.0
TARGET_TRIANGLE = 75455
TARGET_NODES = np.array([37889, 37890, 38125])
RECEIPT_TARGET_IJ = (55, 162)
RECEIPT_LAYER_RANGE_PA = (100000.0, 5000.0)


def relative_geopotential(delta_tv, pressure, valid, reference_level):
    """Integrate a shared virtual-temperature difference to a zero gauge."""
    delta_tv = np.asarray(delta_tv, dtype=np.float64)
    pressure = np.asarray(pressure, dtype=np.float64)
    valid = np.asarray(valid, dtype=bool)
    if delta_tv.ndim != 2 or valid.shape != delta_tv.shape:
        raise ValueError('temperature effect and support must be node by level arrays')
    if pressure.shape != (delta_tv.shape[1],) or not np.isfinite(pressure).all():
        raise ValueError('pressure extent or values are invalid')
    if np.any(pressure <= 0) or np.any(np.diff(pressure) >= 0):
        raise ValueError('pressure levels must be positive and descending')
    if not 0 <= reference_level < pressure.size:
        raise ValueError('reference level outside profile')
    if not np.isfinite(delta_tv[valid]).all():
        raise ValueError('nonfinite supported virtual-temperature effect')

    layer_supported = valid[:, :-1] & valid[:, 1:]
    layer_height = (
        RD_AIR / G0
        * 0.5
        * (delta_tv[:, :-1] + delta_tv[:, 1:])
        * np.log(pressure[:-1] / pressure[1:])[None, :]
    )
    layer_height[~layer_supported] = np.nan
    phi = np.full_like(delta_tv, np.nan)
    reachable = np.zeros(valid.shape, dtype=bool)
    at_reference = valid[:, reference_level]
    phi[at_reference, reference_level] = 0.0
    reachable[at_reference, reference_level] = True
    for k in range(reference_level - 1, -1, -1):
        connected = reachable[:, k + 1] & layer_supported[:, k]
        phi[connected, k] = phi[connected, k + 1] - G0 * layer_height[connected, k]
        reachable[connected, k] = True
    for k in range(reference_level + 1, pressure.size):
        connected = reachable[:, k - 1] & layer_supported[:, k - 1]
        phi[connected, k] = phi[connected, k - 1] + G0 * layer_height[connected, k - 1]
        reachable[connected, k] = True
    return phi, reachable


def _product_profile(path, variable, units, epoch, pressure, navigation=None):
    fields, masks, current_navigation = product(
        path, [(variable, units)], epoch, navigation=navigation, pressure=pressure
    )
    nx, ny, nz = fields[variable].shape
    return (
        fields[variable].reshape((nx * ny, nz), order='F'),
        masks[variable].reshape((nx * ny, nz), order='F'),
        current_navigation,
    )


def _verify_receipts(receipt_paths, pair_dir, thickness_report, thickness_prepared, retained_lq3):
    receipts = [json.loads(path.read_text()) for path in receipt_paths]
    for receipt in receipts:
        if receipt.get('status') != 'PASS_SCOPED / CLOUD_SWITCH_CAUSAL_REPLAY':
            raise ValueError('unexpected cloud replay receipt status')
        if (receipt.get('target_i_j_one_based') != list(RECEIPT_TARGET_IJ) or
                receipt.get('on_equals_retained_lq3_bytes') is not True or
                receipt['input_sha256']['on_lq3'] != receipt['input_sha256']['retained_lq3']):
            raise ValueError('cloud replay target or retained ON product differs')
    first, second = receipts
    for key in ('case_epoch', 'paired_input_files', 'paired_input_manifest_sha256',
                'on_equals_retained_lq3_bytes', 'input_sha256', 'source_sha256',
                'target_profile_kg_kg'):
        if first[key] != second[key]:
            if key == 'input_sha256':
                for stable in ('retained_lc3', 'retained_lq3', 'on_lq3', 'off_lq3',
                               'thickness_report', 'thickness_prepared'):
                    if first[key][stable] != second[key][stable]:
                        raise ValueError(f'O0/O2 replay receipts differ: {stable}')
            else:
                raise ValueError(f'O0/O2 replay receipts differ: {key}')
    count, manifest = paired_inputs(pair_dir / 'on', pair_dir / 'off')
    if count != first['paired_input_files'] or manifest != first['paired_input_manifest_sha256']:
        raise ValueError('paired producer inputs differ from the replay receipts')
    if sha256(retained_lq3) != first['input_sha256']['retained_lq3']:
        raise ValueError('retained LQ3 differs from cloud replay receipts')
    if sha256(thickness_report) != first['input_sha256']['thickness_report']:
        raise ValueError('PR41 report differs from cloud replay receipts')
    if sha256(thickness_prepared) != first['input_sha256']['thickness_prepared']:
        raise ValueError('PR41 prepared state differs from cloud replay receipts')
    expected = first['input_sha256']
    paths = {
        'on_lq3': pair_dir / 'on/lapsprd/lq3/262281300.lq3',
        'off_lq3': pair_dir / 'off/lapsprd/lq3/262281300.lq3',
        'on_lt1': pair_dir / 'on/lapsprd/lt1/262281300.lt1',
        'off_lt1': pair_dir / 'off/lapsprd/lt1/262281300.lt1',
    }
    for name in ('on_lq3', 'off_lq3'):
        if sha256(paths[name]) != expected[name]:
            raise ValueError(f'{name} differs from O0/O2 replay receipts')
    return receipts, paths


def _column_increment(delta_q, pressure, layer_supported):
    """Integrate supported regular layers only; no surface partial layer."""
    runs = []
    indices = np.flatnonzero(layer_supported)
    if not indices.size:
        return None, []
    increments = np.full(pressure.size - 1, np.nan)
    increments[indices] = (
        (pressure[:-1] - pressure[1:])[indices]
        * 0.5
        * (delta_q[:-1] + delta_q[1:])[indices]
        / G0
    )
    start = previous = int(indices[0])
    for index in map(int, indices[1:]):
        if index != previous + 1:
            runs.append((start, previous))
            start = index
        previous = index
    runs.append((start, previous))
    return float(np.sum(increments[indices])), [
        {'pressure_top_Pa': float(pressure[last + 1]),
         'pressure_bottom_Pa': float(pressure[first]),
         'layers': last - first + 1,
         'increment_kg_m2': float(np.sum(increments[first:last + 1]))}
        for first, last in runs
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--thickness-dir', type=Path, required=True, help='PR41 actual arrays/report')
    parser.add_argument('--force-dir', type=Path, required=True, help='PR42 actual arrays/report')
    parser.add_argument('--pair-dir', type=Path, required=True, help='PR44 paired ON/OFF run roots')
    parser.add_argument('--receipt-o0', type=Path, required=True)
    parser.add_argument('--receipt-o2', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--triangle', type=int, default=TARGET_TRIANGLE)
    parser.add_argument('--reference-pressure-pa', type=float, default=5000.0)
    args = parser.parse_args()
    td, fd, pair = args.thickness_dir.resolve(), args.force_dir.resolve(), args.pair_dir.resolve()
    report_path, arrays_path, prepared_path = td/'report.json', td/'arrays.npz', td/'prepared.bin'
    force_report_path, force_arrays_path, force_prepared_path = fd/'report.json', fd/'arrays.npz', fd/'prepared.bin'
    report = json.loads(report_path.read_text())
    force_report = json.loads(force_report_path.read_text())
    inputs = {
        'thickness_report': report_path, 'thickness_arrays': arrays_path,
        'thickness_prepared': prepared_path, 'force_report': force_report_path,
        'force_arrays': force_arrays_path, 'force_prepared': force_prepared_path,
        'geometry_report': Path(force_report['input_paths']['geometry_report']),
        'geometry_prepared': Path(force_report['input_paths']['geometry_prepared']),
        'retained_lt1': Path(report['input_paths']['lt1_1']),
        'retained_lq3': Path(report['input_paths']['lq3_1']),
        'receipt_o0': args.receipt_o0.resolve(), 'receipt_o2': args.receipt_o2.resolve(),
    }
    pins = {name: sha256(path) for name, path in inputs.items()}
    for artifact, input_key in (('prepared.bin', 'thickness_prepared'),
                                ('arrays.npz', 'thickness_arrays')):
        if pins[input_key] != report['artifact_sha256'][artifact]:
            raise ValueError(f'PR41 {artifact} differs from its report')
    for artifact, input_key in (('prepared.bin', 'force_prepared'),
                                ('arrays.npz', 'force_arrays')):
        if pins[input_key] != force_report['artifact_sha256'][artifact]:
            raise ValueError(f'PR42 {artifact} differs from its report')
    if report['status'] != 'PASS_SCOPED / MATCHED_LAYER_THERMODYNAMIC_ATTRIBUTION':
        raise ValueError('unexpected PR41 thermodynamic attribution status')
    if force_report['status'] != 'PASS_SCOPED / ZERO_REFERENCE_RELATIVE_PRESSURE_FORCE':
        raise ValueError('unexpected PR42 force report status')
    if force_report['input_sha256']['thickness_report'] != pins['thickness_report']:
        raise ValueError('PR42 force report does not consume this PR41 report')
    if force_report['input_sha256']['thickness_arrays'] != pins['thickness_arrays']:
        raise ValueError('PR42 force report does not consume these PR41 arrays')
    for name in ('geometry_report', 'geometry_prepared'):
        if pins[name] != force_report['input_sha256'][name]:
            raise ValueError(f'PR42 force report does not consume this {name}')
    if report['input_sha256']['source_report'] != pins['geometry_report']:
        raise ValueError('PR41 and PR42 geometry report lineage differs')
    for name, source_pin in report['source_sha256'].items():
        if sha256(Path(__file__).resolve().parents[1]/name) != source_pin:
            raise ValueError(f'PR41 source changed: {name}')
    for name, source_pin in force_report['source_sha256'].items():
        if sha256(Path(__file__).resolve().parents[1]/name) != source_pin:
            raise ValueError(f'PR42 source changed: {name}')

    receipts, replay_paths = _verify_receipts(
        [args.receipt_o0.resolve(), args.receipt_o2.resolve()], pair,
        report_path, prepared_path, inputs['retained_lq3'])
    receipt = receipts[0]
    inputs.update({name: replay_paths[name] for name in replay_paths})
    pins.update({name: sha256(path) for name, path in replay_paths.items()})
    if receipt['case_epoch'] != report['epoch']:
        raise ValueError('PR41 and cloud replay valid times differ')
    nx, ny, nz = map(int, report['grid_shape'])
    nn = nx * ny
    with np.load(arrays_path, allow_pickle=False) as saved:
        pressure = np.asarray(saved['pressure'], dtype=np.float64)
        valid_raw = np.asarray(saved['valid'])
        if not np.isin(valid_raw, (0, 1)).all():
            raise ValueError('invalid PR41 valid mask')
        valid = valid_raw.astype(bool)
        supported = np.asarray(saved['supported'], dtype=bool)
        if saved['layer'].shape != (9, nn, nz - 1):
            raise ValueError('PR41 layer array extent mismatch')
    if (pressure.shape != (nz,) or valid.shape != (nn, nz) or
            supported.shape != (nn, nz - 1) or
            not np.array_equal(supported, valid[:, :-1] & valid[:, 1:])):
        raise ValueError('PR41 pressure support mismatch')
    geom = read_prepared(inputs['geometry_prepared'])
    if geom['nn'] != nn or geom['nz'] != nz or not np.array_equal(geom['pressure'], pressure):
        raise ValueError('PR39 geometry and PR41 pressure/grid differ')
    if not np.array_equal(geom['parameters'][:3],
                          force_report['chart_parameters_lat0_lon0_radius']):
        raise ValueError('PR42 force chart parameters differ from prepared geometry')
    with np.load(force_arrays_path, allow_pickle=False) as saved:
        force_pressure = np.asarray(saved['pressure'], dtype=np.float64)
        triangles = np.asarray(saved['triangles'], dtype=np.int64)
        reachable_raw = np.asarray(saved['reachable'])
        triangle_support_raw = np.asarray(saved['triangle_support'])
        if (not np.isin(reachable_raw, (0, 1)).all() or
                not np.isin(triangle_support_raw, (0, 1)).all()):
            raise ValueError('invalid PR42 support flags')
        reachable = reachable_raw.astype(bool)
        triangle_support = triangle_support_raw.astype(bool)
        xy = np.asarray(saved['xy'], dtype=np.float64)
        evaluation_latitude = np.asarray(saved['evaluation_latitude'], dtype=np.float64)
    if (not np.array_equal(force_pressure, pressure) or
            not np.array_equal(triangles, geom['triangles']) or
            reachable.shape != valid.shape or triangle_support.shape != (geom['nt'], nz) or
            xy.shape != (2, nn) or evaluation_latitude.shape != (geom['nt'],)):
        raise ValueError('PR42 geometry, pressure, or support extent mismatch')
    if float(force_report['reference_pressure_Pa']) != args.reference_pressure_pa:
        raise ValueError('PR42 uses a different relative-pressure reference')
    ref = np.flatnonzero(pressure == args.reference_pressure_pa)
    if ref.size != 1:
        raise ValueError('reference pressure is not an exact shared knot')
    ref = int(ref[0])
    if not 1 <= args.triangle <= geom['nt']:
        raise ValueError('triangle index outside prepared mesh')
    triangle_index = args.triangle - 1
    nodes = triangles[triangle_index]
    if args.triangle == TARGET_TRIANGLE and not np.array_equal(nodes + 1, TARGET_NODES):
        raise ValueError('target triangle vertices differ from PR42 retained triangle')
    if geom['nt'] <= triangle_index:
        raise ValueError('triangle outside prepared geometry')

    on_lq3, on_mask, on_nav = _product_profile(
        replay_paths['on_lq3'], 'sh', 'kg/kg', report['epoch'], pressure)
    off_lq3, off_mask, off_nav = _product_profile(
        replay_paths['off_lq3'], 'sh', 'kg/kg', report['epoch'], pressure, on_nav)
    final_t, t_mask, _ = _product_profile(
        inputs['retained_lt1'], 't3', 'degrees Kelvin', report['epoch'], pressure, on_nav)
    expected_t_hash = report['input_sha256']['lt1_1']
    if pins['retained_lt1'] != expected_t_hash:
        raise ValueError('retained final temperature differs from PR41 source')
    for mode in ('on', 'off'):
        if sha256(replay_paths[mode+'_lt1']) != expected_t_hash:
            raise ValueError(f'{mode} replay did not retain the PR41 final LT1')
    if (np.any(valid & ~on_mask) or np.any(valid & ~off_mask) or np.any(valid & ~t_mask)):
        raise ValueError('paired products do not cover PR41 supported state')

    q_delta = on_lq3 - off_lq3
    q_delta[~valid] = np.nan
    delta_tv = ALPHA * final_t * q_delta
    delta_tv[~valid] = np.nan
    phi, node_reachable = relative_geopotential(delta_tv, pressure, valid, ref)
    if not np.array_equal(node_reachable, reachable):
        raise ValueError('cloud force support differs from PR42 node support')
    latitude0 = float(geom['parameters'][0])
    common_support = common_triangle_support(node_reachable, triangles, triangle_support)
    if not np.array_equal(common_support, triangle_support):
        raise ValueError('cloud force triangle support differs from PR42 support')
    target_force_support = common_support[triangle_index:triangle_index + 1]
    all_gradients, all_acceleration = triangle_pressure_force(
        phi, target_force_support, triangles[triangle_index:triangle_index + 1],
        xy, evaluation_latitude[triangle_index:triangle_index + 1], latitude0)
    gradient = all_gradients[:, 0]
    acceleration = all_acceleration[:, 0]
    force_supported = target_force_support[0]
    if not np.array_equal(force_supported, triangle_support[triangle_index]):
        raise ValueError('cloud force support differs from PR42 triangle support')

    target_i, target_j = RECEIPT_TARGET_IJ
    target_node = (target_j - 1) * nx + target_i - 1
    target_layer_support = supported[target_node]
    layer_range = (pressure <= RECEIPT_LAYER_RANGE_PA[0]) & (pressure >= RECEIPT_LAYER_RANGE_PA[1])
    target_layer_support = target_layer_support & layer_range[:-1] & layer_range[1:]
    target_q_delta = on_lq3[target_node] - off_lq3[target_node]
    for row in receipt['target_profile_kg_kg']:
        level = np.flatnonzero(pressure == row['pressure_Pa'])
        if level.size != 1 or not valid[target_node, level[0]]:
            raise ValueError('cloud receipt pressure is unsupported at its target node')
        k = int(level[0])
        if (on_lq3[target_node, k] != row['with_cloud'] or
                off_lq3[target_node, k] != row['without_cloud']):
            raise ValueError('loaded target profile differs from the cloud replay receipt')
    column_delta, column_segments = _column_increment(target_q_delta, pressure, target_layer_support)
    for name, path in inputs.items():
        if sha256(path) != pins[name]:
            raise ValueError(f'input changed during diagnostic: {path.name}')
    repo = Path(__file__).resolve().parents[1]
    source_paths = {
        'diagnose_qbal_cloud_force.py': Path(__file__).resolve(),
        'diagnose_qbal_cloud_switch.py': repo/'tests/diagnose_qbal_cloud_switch.py',
        'diagnose_qbal_ground_ht_force.py': repo/'tests/diagnose_qbal_ground_ht_force.py',
        'diagnose_qbal_thickness_attribution.py': repo/'tests/diagnose_qbal_thickness_attribution.py',
        'audit_qbal_profile_domain.py': repo/'tests/audit_qbal_profile_domain.py',
        'qbal_relative_pressure_force.f90': repo/'tests/qbal_relative_pressure_force.f90',
    }
    source_pins = {name: sha256(path) for name, path in source_paths.items()}
    for name, path in source_paths.items():
        if sha256(path) != source_pins[name]:
            raise ValueError(f'source changed during diagnostic: {name}')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(output/'arrays.npz', pressure=pressure, nodes=nodes + 1,
                        node_reachable=node_reachable[nodes].astype(np.int32),
                        triangle_support=force_supported.astype(np.int32),
                        delta_q_kg_kg=q_delta[nodes], delta_phi_m2_s2=phi[nodes],
                        gradient_chart_m_s2=gradient, acceleration_en_m_s2=acceleration)
    level_rows = []
    for k in np.flatnonzero(force_supported):
        level_rows.append({
            'pressure_Pa': float(pressure[k]),
            'delta_phi_vertices_m2_s2': phi[nodes, k].tolist(),
            'gradient_chart_m_s2': gradient[:, k].tolist(),
            'acceleration_en_m_s2': acceleration[:, k].tolist(),
            'magnitude_m_s2': float(np.linalg.norm(acceleration[:, k])),
        })
    report_out = {
        'status': 'PASS_SCOPED / CLOUD_ON_OFF_RELATIVE_FORCE',
        'triangle_one_based': args.triangle, 'vertices_one_based': (nodes + 1).tolist(),
        'reference_pressure_Pa': args.reference_pressure_pa, 'reference_delta_phi_m2_s2': [0.0, 0.0, 0.0],
        'fixed_temperature': 'retained PR41 final LT1, byte-identical in PR44 ON and OFF inputs',
        'moisture_effect': 'PR44 LQ3 ON−OFF; net late cloud block including subsequent QC',
        'force_metric': 'PR42 equal-area spherical chart and triangle-centroid metric; same pressure and PR42 support',
        'meteorological_correctness': 'not assessed; no physical boundary/reference force inferred',
        'supported_pressure_levels_Pa': pressure[force_supported].tolist(),
        'levels': level_rows,
        'target_node_vapor_column_increment': {
            'node_i_j_one_based': [target_i, target_j],
            'pressure_interval_Pa': list(RECEIPT_LAYER_RANGE_PA),
            'increment_kg_m2': column_delta,
            'supported_segments': column_segments,
            'surface_partial_layer_included': False,
        },
        'paired_input_manifest_sha256': receipt['paired_input_manifest_sha256'],
        'replay_receipt_sha256': {
            'O0': sha256(args.receipt_o0.resolve()), 'O2': sha256(args.receipt_o2.resolve()),
        },
        'input_paths': {name: str(path) for name, path in inputs.items()},
        'input_sha256': pins,
        'source_sha256': source_pins,
        'output_sha256': {'arrays.npz': sha256(output/'arrays.npz')},
        'production_authority': False,
    }
    (output/'report.json').write_text(json.dumps(report_out, indent=2, allow_nan=False) + '\n')
    print(json.dumps({
        'status': report_out['status'],
        'triangle_one_based': args.triangle,
        'support_levels': int(force_supported.sum()),
        '100000_Pa_acceleration_en_m_s2': next(
            row['acceleration_en_m_s2'] for row in level_rows if row['pressure_Pa'] == 100000.0),
        'target_node_vapor_column_increment_kg_m2': column_delta,
    }, allow_nan=False))


if __name__ == '__main__':
    main()
