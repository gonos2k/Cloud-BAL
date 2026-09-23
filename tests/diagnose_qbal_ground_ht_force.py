#!/usr/bin/env python3
"""Compare same-support pressure-surface forces from conditional ground HT."""
import argparse
import json
from pathlib import Path

import numpy as np

from audit_qbal_profile_domain import sha256
from diagnose_qbal_ground_reference import read_state

G0 = 9.80665
COMPONENTS = ('stage_minus_retained_ht', 'conditional_change', 'final_minus_retained_ht')


def common_triangle_support(node_support, triangles, force_support):
    """Intersect three-node support with the retained PR42 pressure support."""
    node_support = np.asarray(node_support, dtype=bool)
    triangles = np.asarray(triangles)
    force_support = np.asarray(force_support, dtype=bool)
    if node_support.ndim != 2 or triangles.ndim != 2 or triangles.shape[1] != 3:
        raise ValueError('invalid node support or triangle extent')
    if force_support.shape != (triangles.shape[0], node_support.shape[1]):
        raise ValueError('PR42 force support extent mismatch')
    if triangles.size and (triangles.min() < 0 or triangles.max() >= node_support.shape[0]):
        raise ValueError('triangle index outside the node grid')
    ground_support = node_support[triangles].all(axis=1)
    return ground_support & force_support


def triangle_pressure_force(field, support, triangles, xy, evaluation_latitude,
                            latitude0):
    """Apply PR42's P1 chart gradient and equal-area east/north metric."""
    field = np.asarray(field, dtype=np.float64)
    support = np.asarray(support, dtype=bool)
    triangles = np.asarray(triangles, dtype=np.int64)
    xy = np.asarray(xy, dtype=np.float64)
    evaluation_latitude = np.asarray(evaluation_latitude, dtype=np.float64)
    if field.ndim != 2 or support.shape != (triangles.shape[0], field.shape[1]):
        raise ValueError('field/support extent mismatch')
    if xy.shape != (2, field.shape[0]) or evaluation_latitude.shape != (triangles.shape[0],):
        raise ValueError('geometry extent mismatch')
    if not np.isfinite(latitude0) or abs(latitude0) >= 1.55:
        raise ValueError('invalid chart latitude')

    gradient = np.full((2, triangles.shape[0], field.shape[1]), np.nan)
    acceleration = np.full_like(gradient, np.nan)
    eps = np.finfo(np.float64).eps
    c0 = np.cos(latitude0)
    for triangle, levels in enumerate(support):
        active = np.flatnonzero(levels)
        if not active.size:
            continue
        indices = triangles[triangle]
        vertices = xy[:, indices]
        if not np.isfinite(vertices).all() or np.max(np.abs(vertices)) > 1.0e12:
            raise ValueError('invalid supported triangle coordinates')
        lat = evaluation_latitude[triangle]
        if not np.isfinite(lat) or abs(lat) >= 1.55:
            raise ValueError('invalid supported triangle latitude')

        dx21, dy21 = vertices[:, 1] - vertices[:, 0]
        dx31, dy31 = vertices[:, 2] - vertices[:, 0]
        determinant = dx21 * dy31 - dx31 * dy21
        scale = max(abs(dx21), abs(dy21), abs(dx31), abs(dy31))
        if (not np.isfinite(determinant) or scale <= 0.0 or
                abs(determinant) <= 64.0 * eps * scale * scale):
            raise ValueError('degenerate supported triangle')
        values = field[indices][:, active]
        if not np.isfinite(values).all():
            raise ValueError('nonfinite field value on triangle support')
        rhs21, rhs31 = values[1] - values[0], values[2] - values[0]
        gx = (rhs21 * dy31 - rhs31 * dy21) / determinant
        gy = (dx21 * rhs31 - dx31 * rhs21) / determinant
        c = np.cos(lat)
        if c <= 0.0 or c0 <= 0.0:
            raise ValueError('invalid metric latitude')
        gradient[:, triangle, active] = np.stack((gx, gy))
        acceleration[:, triangle, active] = np.stack((-c0 / c * gx, -c / c0 * gy))
    return gradient, acceleration


def triangle_force_error_bound(node_bound, component_fields, support, triangles, xy,
                               evaluation_latitude, latitude0):
    """Propagate the PR44 node closure bound through the PR42 P1 metric."""
    node_bound = np.asarray(node_bound, dtype=np.float64)
    component_fields = np.asarray(component_fields, dtype=np.float64)
    support = np.asarray(support, dtype=bool)
    triangles = np.asarray(triangles, dtype=np.int64)
    xy = np.asarray(xy, dtype=np.float64)
    evaluation_latitude = np.asarray(evaluation_latitude, dtype=np.float64)
    nt, nz = support.shape
    if node_bound.ndim != 2 or component_fields.shape[1:] != node_bound.shape:
        raise ValueError('closure-bound field extent mismatch')
    if node_bound.shape[1] != nz or triangles.shape != (nt, 3):
        raise ValueError('closure-bound support extent mismatch')
    result = np.full((2, nt, nz), np.nan)
    eps = np.finfo(np.float64).eps
    c0 = np.cos(latitude0)
    for triangle, levels in enumerate(support):
        active = np.flatnonzero(levels)
        if not active.size:
            continue
        indices = triangles[triangle]
        vertices = xy[:, indices]
        dx21, dy21 = vertices[:, 1] - vertices[:, 0]
        dx31, dy31 = vertices[:, 2] - vertices[:, 0]
        determinant = dx21 * dy31 - dx31 * dy21
        edge_size = np.max(np.abs(vertices - vertices[:, :1]))
        if edge_size <= 0.0 or determinant == 0.0:
            raise ValueError('degenerate supported triangle')
        coefficient = np.array([
            [vertices[1, 1] - vertices[1, 2], vertices[1, 2] - vertices[1, 0],
             vertices[1, 0] - vertices[1, 1]],
            [vertices[0, 2] - vertices[0, 1], vertices[0, 0] - vertices[0, 2],
             vertices[0, 1] - vertices[0, 0]],
        ]) / determinant
        lat = evaluation_latitude[triangle]
        metric_scale = np.array([-c0 / np.cos(lat), -np.cos(lat) / c0])
        force_coefficient = metric_scale[:, None] * coefficient
        propagated = np.abs(force_coefficient) @ node_bound[indices][:, active]
        condition = 1.0 + np.max(np.abs(vertices)) / edge_size
        local_scale = np.sum(np.abs(component_fields[:, indices][:, :, active]), axis=(0, 1))
        roundoff = (max(abs(metric_scale)) * np.max(np.sum(np.abs(coefficient), axis=1)) *
                    (np.max(node_bound[indices][:, active], axis=0) +
                     256.0 * eps * condition * local_scale))
        result[:, triangle, active] = propagated + roundoff[None, :]
    return result


def stats(values):
    finite = np.asarray(values)[np.isfinite(values)]
    if not finite.size:
        return {'count': 0, 'min': None, 'max': None, 'rms': None}
    return {'count': int(finite.size), 'min': float(finite.min()),
            'max': float(finite.max()), 'rms': float(np.sqrt(np.mean(finite**2)))}


def maximum_location(magnitude, triangles, pressure, support, acceleration):
    masked = np.where(support, magnitude, np.nan)
    if not np.isfinite(masked).any():
        return None
    triangle, level = np.unravel_index(np.nanargmax(masked), masked.shape)
    return {'triangle_one_based': int(triangle + 1),
            'vertices_one_based': (triangles[triangle] + 1).tolist(),
            'pressure_Pa': float(pressure[level]),
            'magnitude_m_s2': float(magnitude[triangle, level]),
            'acceleration_en_m_s2': acceleration[:, triangle, level].tolist()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ground-ht-dir', type=Path, required=True,
                        help='PR45 stage/final minus retained-HT comparison')
    parser.add_argument('--ground-dir', type=Path, required=True,
                        help='hash-bound PR43 conditional ground-reference output')
    parser.add_argument('--force-dir', type=Path, required=True,
                        help='hash-bound PR42 relative-force output')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()

    ht_dir, ground_dir, force_dir = (p.resolve() for p in
                                      (args.ground_ht_dir, args.ground_dir, args.force_dir))
    ht_report_path, ground_report_path, force_report_path = (
        ht_dir / 'report.json', ground_dir / 'report.json', force_dir / 'report.json')
    ht_arrays_path, ground_arrays_path, force_arrays_path = (
        ht_dir / 'arrays.npz', ground_dir / 'arrays.npz', force_dir / 'arrays.npz')
    input_paths = {'ground_ht_report': ht_report_path, 'ground_ht_arrays': ht_arrays_path,
                   'ground_report': ground_report_path, 'ground_arrays': ground_arrays_path,
                   'force_report': force_report_path, 'force_arrays': force_arrays_path}
    input_pins = {name: sha256(path) for name, path in input_paths.items()}
    ht_report = json.loads(ht_report_path.read_text())
    ground_report = json.loads(ground_report_path.read_text())
    force_report = json.loads(force_report_path.read_text())
    thickness_prepared = Path(ground_report['input_paths']['thickness_prepared'])
    input_paths['thickness_prepared'] = thickness_prepared
    input_pins['thickness_prepared'] = sha256(thickness_prepared)
    if ht_report['status'] != 'PASS_SCOPED / CONDITIONAL_STAGE_HT_COMPARISON':
        raise ValueError('unexpected PR44 ground-HT status')
    if ground_report['status'] != 'PASS_SCOPED / CONDITIONAL_GROUND_REFERENCE':
        raise ValueError('unexpected PR43 ground-reference status')
    if force_report['status'] != 'PASS_SCOPED / ZERO_REFERENCE_RELATIVE_PRESSURE_FORCE':
        raise ValueError('unexpected PR42 force status')
    for report, arrays_path in ((ht_report, ht_arrays_path),
                                (ground_report, ground_arrays_path),
                                (force_report, force_arrays_path)):
        if sha256(arrays_path) != report['artifact_sha256']['arrays.npz']:
            raise ValueError(f"array artifact hash mismatch: {arrays_path}")
    if ht_report['input_sha256']['ground_report'] != sha256(ground_report_path):
        raise ValueError('PR44/PR43 report lineage mismatch')
    if ht_report['input_sha256']['ground_arrays'] != sha256(ground_arrays_path):
        raise ValueError('PR44/PR43 array lineage mismatch')
    if ht_report['epoch'] != ground_report['epoch'] or ht_report['epoch'] != force_report['epoch']:
        raise ValueError('source valid times differ')
    for name in ('thickness_report', 'thickness_arrays', 'geometry_report', 'geometry_prepared'):
        if ground_report['input_sha256'][name] != force_report['input_sha256'][name]:
            raise ValueError(f'PR43/PR42 input lineage mismatch: {name}')

    with np.load(ht_arrays_path, allow_pickle=False) as stored:
        ht = {name: stored[name] for name in stored.files}
    with np.load(ground_arrays_path, allow_pickle=False) as stored:
        ground = {name: stored[name] for name in stored.files}
    with np.load(force_arrays_path, allow_pickle=False) as stored:
        force = {name: stored[name] for name in stored.files}

    if not np.isin(ground['support'], (0, 1)).all():
        raise ValueError('invalid PR43 node support')
    node_support = ground['support'].astype(bool)
    triangles = force['triangles']
    pressure = ground['pressure']
    if (not np.array_equal(ht['support'], node_support) or
            not np.array_equal(ht['pressure'], pressure) or
            not np.array_equal(force['pressure'], pressure) or
            not np.array_equal(ground['triangles'], triangles)):
        raise ValueError('PR43/PR44/PR42 grid or triangle mismatch')
    if node_support.shape != ground['before'].shape or node_support.shape != ground['after'].shape:
        raise ValueError('ground profile extent mismatch')
    if (int(node_support.any(axis=1).sum()) != ht_report['supported_nodes'] or
            int(node_support.sum()) != ht_report['supported_node_levels']):
        raise ValueError('PR44 reported node support changed')
    if ht['stage_minus_ht'].shape != node_support.shape or ht['final_minus_ht'].shape != node_support.shape:
        raise ValueError('PR44 profile extent mismatch')
    force_support = force['triangle_support'].astype(bool)
    if not np.isin(force['triangle_support'], [0, 1]).all():
        raise ValueError('invalid PR42 triangle support')
    ground_triangle_support = node_support[triangles].all(axis=1)
    if not np.array_equal(ground_triangle_support, ground['triangle_support']):
        raise ValueError('PR43 triangle support does not match its node mask')
    support = common_triangle_support(node_support, triangles, force_support)
    if not np.array_equal(support, ground_triangle_support & force_support):
        raise ValueError('common support construction mismatch')

    repo = Path(__file__).resolve().parents[1]
    source_names = ('tests/diagnose_qbal_ground_ht_force.py',
                    'tests/test_qbal_ground_ht_force.py',
                    'tests/diagnose_qbal_ground_reference.py',
                    'tests/audit_qbal_profile_domain.py',
                    'tests/qbal_relative_pressure_force.f90',
                    'tests/qbal_sloping_geometry.f90')
    source_pins = {name: sha256(repo / name) for name in source_names}
    for source in ('tests/qbal_relative_pressure_force.f90', 'tests/qbal_sloping_geometry.f90'):
        if source_pins[source] != force_report['source_sha256'][source]:
            raise ValueError(f'PR42 metric source changed: {source}')
    latitude0, _, _ = force_report['chart_parameters_lat0_lon0_radius']
    xy, evaluation_latitude = force['xy'], force['evaluation_latitude']
    if xy.shape != (2, node_support.shape[0]) or evaluation_latitude.shape != (triangles.shape[0],):
        raise ValueError('PR42 metric geometry extent mismatch')

    stage = ht['stage_minus_ht']
    final = ht['final_minus_ht']
    delta = ground['delta'][2]
    if sha256(thickness_prepared) != ground_report['input_sha256']['thickness_prepared']:
        raise ValueError('paired-state artifact hash mismatch')
    state_pressure, _, state, valid = read_state(thickness_prepared, *node_support.shape)
    if not np.array_equal(state_pressure, pressure) or np.any(node_support & (valid != 1)):
        raise ValueError('paired-state support or pressure mismatch')
    retained_height = state[:, :, 4]
    expected_stage = ground['before'] - G0 * retained_height
    expected_final = ground['after'] - G0 * retained_height
    if (not np.array_equal(stage[node_support], expected_stage[node_support]) or
            not np.array_equal(final[node_support], expected_final[node_support])):
        raise ValueError('PR44 comparison does not reproduce from retained HT')

    raw_bound = ground['bound']
    if (raw_bound.shape != node_support.shape or
            not np.isfinite(raw_bound[node_support]).all() or
            np.any(raw_bound[node_support] < 0)):
        raise ValueError('invalid supported PR43 arithmetic bound')
    arithmetic_bound = raw_bound + 32 * np.finfo(np.float64).eps * (
        np.abs(ground['before']) + np.abs(ground['after']) + 2 * G0 * np.abs(retained_height))
    closure = final - stage - delta
    if (not np.isfinite(arithmetic_bound[node_support]).all() or
            np.any(arithmetic_bound[node_support] < 0) or
            not np.isfinite(closure[node_support]).all() or
            np.any(np.abs(closure[node_support]) > arithmetic_bound[node_support])):
        raise ValueError('direct PR43 change does not close PR44 F-S within bound')

    fields = (stage, delta, final)
    gradients = []
    accelerations = []
    for field in fields:
        gradient, acceleration = triangle_pressure_force(
            field, support, triangles, xy, evaluation_latitude, latitude0)
        gradients.append(gradient)
        accelerations.append(acceleration)
    gradients = np.asarray(gradients)
    accelerations = np.asarray(accelerations)
    component_mask = np.broadcast_to(support, accelerations.shape[1:])
    acceleration_closure = accelerations[0] + accelerations[1] - accelerations[2]
    force_bound = triangle_force_error_bound(
        arithmetic_bound, np.asarray(fields), support, triangles, xy,
        evaluation_latitude, latitude0)
    if np.any(np.abs(acceleration_closure[component_mask]) >
              force_bound[component_mask]):
        raise ValueError('P1 force decomposition exceeded propagated PR44 bound')

    magnitude = np.sqrt(np.sum(accelerations**2, axis=1))
    level_results = []
    for k, p in enumerate(pressure):
        item = {'pressure_Pa': float(p), 'supported_triangles': int(support[:, k].sum()),
                'components': {}}
        for component, name in enumerate(COMPONENTS):
            field_magnitude = magnitude[component, :, k]
            item['components'][name] = {
                'acceleration_magnitude_m_s2': stats(field_magnitude[support[:, k]])}
        level_results.append(item)

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(out / 'arrays.npz', pressure=pressure, triangles=triangles,
                        triangle_support=support, stage_minus_retained_ht=stage,
                        conditional_change=delta, final_minus_retained_ht=final,
                        gradient_chart=gradients, acceleration_en=accelerations)
    report = {
        'status': 'PASS_SCOPED / SAME_SUPPORT_GROUND_HT_FORCE',
        'epoch': ht_report['epoch'],
        'units': {'potential': 'm2 s-2', 'acceleration': 'm s-2'},
        'support': {'nodes': int(node_support.any(axis=1).sum()),
                    'node_levels': int(node_support.sum()),
                    'triangles': int(support.any(axis=1).sum()),
                    'triangle_levels': int(support.sum()),
                    'within_pr42_triangle_support': True},
        'metric': 'PR42 equal-area spherical chart; P1 triangle gradient at the stored centroid latitude.',
        'chart_parameters_lat0_lon0_radius': force_report['chart_parameters_lat0_lon0_radius'],
        'components': {},
        'level_results': level_results,
        'closure': {'identity': 'F - S = direct PR43 delta[2]',
                    'maximum_node_residual_m2_s2': float(np.max(np.abs(closure[node_support]))),
                    'maximum_node_arithmetic_bound_m2_s2': float(np.max(arithmetic_bound[node_support])),
                    'maximum_force_linearity_residual_m_s2': float(np.max(np.abs(acceleration_closure[component_mask]))),
                    'maximum_propagated_force_closure_bound_m_s2': float(np.max(force_bound[component_mask]))},
        'interpretation': 'S is the conditional stage profile minus retained HT; delta is the direct conditional final-minus-stage contribution. Both gradients use the exact shared PR44/PR43 support intersected with PR42 support.',
        'limitations': ['The conditional ground reference is not an authorized physical correction.',
                        'These pressure-surface forces do not close the physical reference force, lower profile, or complete boundary transport.',
                        'The maximum-force triangle outside the PR43 selection remains unsupported.'],
        'production_authority': False,
        'input_paths': {name: str(path) for name, path in input_paths.items()},
        'input_sha256': input_pins,
        'source_sha256': source_pins,
        'artifact_sha256': {'arrays.npz': sha256(out / 'arrays.npz')},
    }
    for component, name in enumerate(COMPONENTS):
        component_magnitude = magnitude[component]
        report['components'][name] = {
            'acceleration_magnitude_m_s2': stats(component_magnitude[support]),
            'maximum_location': maximum_location(component_magnitude, triangles, pressure,
                                                  support, accelerations[component])}
    for name, path in input_paths.items():
        if sha256(path) != input_pins[name]:
            raise ValueError(f'input changed during diagnostic: {path}')
    if {name: sha256(repo / name) for name in source_names} != source_pins:
        raise ValueError('diagnostic source changed during execution')
    (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': report['status'], **report['support']}))


if __name__ == '__main__':
    main()
