#!/usr/bin/env python3
"""Read-only surface support and original-pressure comparison for PR47's column."""

import argparse
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from audit_qbal_profile_domain import sha256
from qbal_dry_mass_column import EPSILON, G0, RD
from qbal_surface_mass_bridge import (common_pressure_projection, gas_enthalpy,
                                      surface_support)


TARGET = (55, 162)


def read_surface(path):
    values = []
    with Dataset(path) as product:
        nx = len(product.dimensions['x'])
        for name, units in (('ps', 'pascals'), ('t', 'degrees kelvin'),
                            ('mr', 'grams/kikogram')):
            field = product.variables[name]
            if field.dimensions != ('record', 'z', 'y', 'x') or field.shape[0:2] != (1, 1):
                raise ValueError(f'{name}: unexpected surface dimensions')
            if field.units != units and not (name == 'mr' and field.units == 'grams/kilogram'):
                raise ValueError(f'{name}: unexpected units')
            value = float(field[0, 0, TARGET[1] - 1, TARGET[0] - 1])
            if not np.isfinite(value):
                raise ValueError(f'{name}: missing target surface value')
            values.append(value)
    pressure, temperature, mixing_ratio_g_kg = values
    mixing_ratio = mixing_ratio_g_kg / 1000
    if not (pressure > 0 and 150 <= temperature <= 350 and 0 <= mixing_ratio < 1):
        raise ValueError('invalid target surface state')
    return pressure, temperature, mixing_ratio, nx


def state_from_receipt(receipt):
    pressure = np.asarray(receipt['old_model_interfaces_Pa'], dtype=np.float64)
    new_pressure = np.asarray(receipt['new_model_interfaces_Pa'], dtype=np.float64)
    layers = receipt['layers']
    if (receipt['status'] != 'PASS_SCOPED / CONDITIONAL_DRY_MASS_COLUMN' or
            receipt['target_i_j_one_based'] != list(TARGET) or
            pressure.size != 20 or new_pressure.shape != pressure.shape or len(layers) != 19 or
            pressure[0] != 100000 or pressure[-1] != 5000 or
            np.any(np.diff(pressure) >= 0) or np.any(np.diff(new_pressure) >= 0)):
        raise ValueError('unexpected dry-column receipt')
    state = {'old_pressure': pressure, 'new_pressure': new_pressure}
    for output, field in (('dry_mass', 'dry_mass_kg_m2'),
                          ('old_vapor', 'old_vapor_kg_m2'),
                          ('new_vapor', 'new_vapor_kg_m2'),
                          ('layer_temperature_K', 'temperature_K'),
                          ('old_q', 'old_q_kg_kg'), ('new_q', 'new_q_kg_kg')):
        state[output] = np.asarray([row[field] for row in layers], dtype=np.float64)
    if not all(np.isfinite(value).all() for value in state.values()):
        raise ValueError('dry-column receipt is not finite')
    if (np.any((state['old_q'] < 0) | (state['old_q'] >= 1)) or
            np.any((state['new_q'] < 0) | (state['new_q'] >= 1)) or
            np.any((state['layer_temperature_K'] < 150) |
                   (state['layer_temperature_K'] > 350))):
        raise ValueError('dry-column receipt has invalid gas state')
    width = pressure[:-1] - pressure[1:]
    new_width = new_pressure[:-1] - new_pressure[1:]
    if (not np.allclose(state['dry_mass'], width * (1 - state['old_q']) / G0,
                        rtol=2e-14, atol=1e-11) or
            not np.allclose(state['old_vapor'], width * state['old_q'] / G0,
                            rtol=2e-14, atol=1e-11) or
            not np.allclose(state['new_vapor'],
                            state['dry_mass'] * state['new_q'] / (1 - state['new_q']),
                            rtol=2e-14, atol=1e-11) or
            not np.allclose(new_width / G0, state['dry_mass'] + state['new_vapor'],
                            rtol=2e-14, atol=1e-11)):
        raise ValueError('dry-column receipt mass identities changed')
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-report', type=Path, required=True)
    parser.add_argument('--cloud-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    dry_path = args.dry_report.resolve()
    cloud_path = args.cloud_report.resolve()
    dry = json.loads(dry_path.read_text())
    cloud = json.loads(cloud_path.read_text())
    if (dry['cloud_report_sha256'] != sha256(cloud_path) or
            cloud['status'] != 'PASS_SCOPED / CLOUD_ON_OFF_RELATIVE_FORCE'):
        raise ValueError('cloud and dry-column lineage differs')
    for name, digest in dry['input_sha256'].items():
        if cloud['input_sha256'][name] != digest:
            raise ValueError(f'dry-column source differs from cloud report: {name}')
    for name, digest in dry['source_sha256'].items():
        if sha256(Path(__file__).with_name(name)) != digest:
            raise ValueError(f'dry-column source changed: {name}')
    geometry_path = Path(cloud['input_paths']['geometry_report'])
    if sha256(geometry_path) != cloud['input_sha256']['geometry_report']:
        raise ValueError('geometry report changed')
    geometry = json.loads(geometry_path.read_text())
    thickness_path = Path(cloud['input_paths']['thickness_report'])
    if sha256(thickness_path) != cloud['input_sha256']['thickness_report']:
        raise ValueError('thickness report changed')
    thickness = json.loads(thickness_path.read_text())
    if geometry['times'][1] != thickness['epoch']:
        raise ValueError('surface and dry-column valid times differ')
    lsx_path = Path(geometry['input_paths']['lsx_1'])
    arrays_path = geometry_path.with_name('arrays.npz')
    if (sha256(lsx_path) != geometry['input_sha256']['lsx_1'] or
            sha256(arrays_path) != geometry['artifact_sha256']['arrays.npz']):
        raise ValueError('surface or 10 m prior input changed')

    state = state_from_receipt(dry)
    for name, values in (('old_dry_mass_kg_m2', state['dry_mass']),
                         ('new_dry_mass_kg_m2', state['dry_mass']),
                         ('old_vapor_mass_kg_m2', state['old_vapor']),
                         ('new_vapor_mass_kg_m2', state['new_vapor'])):
        if not np.isclose(dry[name], np.sum(values), rtol=2e-14, atol=1e-10):
            raise ValueError(f'dry-column total differs: {name}')
    ps, ts, rs, nx = read_surface(lsx_path)
    tv = ts * (1 + rs / EPSILON) / (1 + rs)
    p10 = ps * np.exp(-G0 * 10 / (RD * tv))
    node = (TARGET[1] - 1) * nx + TARGET[0] - 1
    with np.load(arrays_path, allow_pickle=False) as arrays:
        retained_p10 = float(arrays['p10'][1, node])
    if (not np.isclose(p10, retained_p10, rtol=0, atol=2e-9) or
            not np.isclose(ps, dry['retained_surface_pressure_Pa'], rtol=0, atol=1e-6)):
        raise ValueError('surface state differs from pinned pressure prior')

    support = surface_support(ps, p10, state['old_pressure'][0],
                              state['new_pressure'][0], rs)
    projection = common_pressure_projection(state)
    for name, original, edge, mapped in (
            ('dry', state['dry_mass'], projection['edge_dry_mass_kg_m2'],
             projection['old_pressure_cell_dry_mass_kg_m2']),
            ('vapor', state['new_vapor'], projection['edge_vapor_mass_kg_m2'],
             projection['old_pressure_cell_vapor_mass_kg_m2'])):
        if not np.isclose(np.sum(original), edge + np.sum(mapped), rtol=2e-14, atol=1e-10):
            raise ValueError(f'{name} mass missing from common-pressure comparison')
    if not np.isclose(np.sum(projection['old_pressure_cell_dry_mass_kg_m2'] +
                             projection['old_pressure_cell_vapor_mass_kg_m2']),
                      (state['old_pressure'][0] - state['old_pressure'][-1]) / G0,
                      rtol=2e-14, atol=1e-10):
        raise ValueError('common-pressure gas mass does not match its interval')
    enthalpy_before = float(np.sum(gas_enthalpy(
        state['dry_mass'], state['old_vapor'], state['layer_temperature_K'])))
    enthalpy_after = float(np.sum(gas_enthalpy(
        state['dry_mass'], state['new_vapor'], state['layer_temperature_K'])))
    if not np.isclose(projection['total_enthalpy_J_m2'], enthalpy_after,
                      rtol=2e-14, atol=1e-5):
        raise ValueError('mixture enthalpy changed during pressure repartition')
    q_error = projection['old_pressure_cell_q_kg_kg'] - state['new_q']
    t_error = projection['old_pressure_cell_temperature_K'] - state['layer_temperature_K']
    if sha256(dry_path) != sha256(args.dry_report) or sha256(lsx_path) != geometry['input_sha256']['lsx_1']:
        raise ValueError('input changed during calculation')
    result = {
        'status': 'PASS_SCOPED / SURFACE_SUPPORT_AND_COMMON_PRESSURE_COMPARISON',
        'production_authority': False,
        'target_i_j_one_based': list(TARGET),
        'pressure_basis': 'gas-only; fixed PS and LSX 0-10 m prior; old levels are modeled interfaces',
        'surface_pressure_Pa': ps,
        'surface_temperature_K': ts,
        'surface_dry_mixing_ratio_kg_kg': rs,
        'pressure_10m_Pa': float(p10),
        'surface_support': support,
        'surface_partial_complete': bool(support['old']['unsupported_span_Pa'] == 0 and
                                         support['new_if_PS_fixed']['unsupported_span_Pa'] == 0),
        'moved_edge_dry_mass_kg_m2': projection['edge_dry_mass_kg_m2'],
        'moved_edge_vapor_mass_kg_m2': projection['edge_vapor_mass_kg_m2'],
        'common_pressure_dry_mass_kg_m2': float(np.sum(projection['old_pressure_cell_dry_mass_kg_m2'])),
        'common_pressure_vapor_mass_kg_m2': float(np.sum(projection['old_pressure_cell_vapor_mass_kg_m2'])),
        'original_pressure_cell_q_difference': {
            'maximum_absolute_kg_kg': float(np.max(np.abs(q_error))),
            'rms_kg_kg': float(np.sqrt(np.mean(q_error ** 2))),
        },
        'original_pressure_cell_temperature_difference': {
            'maximum_absolute_K': float(np.max(np.abs(t_error))),
            'rms_K': float(np.sqrt(np.mean(t_error ** 2))),
        },
        'conditional_gas_mixture_enthalpy_J_m2': {
            'before': enthalpy_before, 'after': enthalpy_after,
            'change': enthalpy_after - enthalpy_before,
            'role': 'fixed-temperature state difference; not a closed energy budget',
        },
        'source_sha256': {name: sha256(Path(__file__).with_name(name)) for name in
                          ('qbal_surface_mass_bridge.py', 'diagnose_qbal_surface_mass_bridge.py')},
        'input_sha256': {'dry_report': sha256(dry_path), 'cloud_report': sha256(cloud_path),
                         'geometry_report': sha256(geometry_path), 'geometry_arrays': sha256(arrays_path),
                         'lsx': sha256(lsx_path)},
    }
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: result[key] for key in
                      ('status', 'surface_partial_complete', 'moved_edge_dry_mass_kg_m2')}))


if __name__ == '__main__':
    main()
