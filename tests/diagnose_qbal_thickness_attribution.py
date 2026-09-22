#!/usr/bin/env python3
"""Matched-layer temperature/moisture thickness attribution from retained HT states."""
import argparse
import json
from pathlib import Path
import subprocess

import numpy as np
from netCDF4 import Dataset
from diagnose_qbal_sloping_faces import nav, sha, validate_product_time

FIELDS = ('before', 'after', 'temperature', 'moisture', 'total', 'arithmetic_bound',
          'stage_height_defect', 'final_height_defect', 'closure_error')


def capture(path):
    with path.open('rb') as stream:
        shape = np.fromfile(stream, '>i4', 3)
        if shape.size != 3 or np.any(shape <= 0):
            raise ValueError('invalid capture header')
        values = np.fromfile(stream, '>f4')
    if values.size != np.prod(shape):
        raise ValueError('invalid capture extent')
    return values.reshape(tuple(shape), order='F').astype(np.float64)


def product(path, variables, epoch, navigation=None, pressure=None):
    result, masks = {}, {}
    with Dataset(path) as nc:
        nc.set_auto_maskandscale(False)
        validate_product_time(nc, epoch, path.suffix)
        current_nav = nav(nc)
        if navigation is not None and current_nav != navigation:
            raise ValueError('navigation mismatch')
        if pressure is not None:
            if nc['level'].units != 'hectopascals':
                raise ValueError('pressure units mismatch')
            if not np.array_equal(np.asarray(nc['level'][:])[::-1] * 100, pressure):
                raise ValueError('pressure levels mismatch')
        for key, units in variables:
            var = nc[key]
            if var.units != units or var.dimensions != ('record', 'z', 'y', 'x'):
                raise ValueError(f'{key}: units or dimensions mismatch')
            values = np.asarray(var[0], dtype=np.float64).transpose(2, 1, 0)[:, :, ::-1]
            valid = np.isfinite(values)
            for attribute in ('_FillValue', 'missing_value'):
                if attribute in var.ncattrs():
                    for missing in np.asarray(var.getncattr(attribute)).ravel():
                        valid &= values != missing
            # HT's below-sea-level values remain diagnostic evidence; its
            # declared nonnegative valid_range is not an altitude datum test.
            if key != 'ht' and 'valid_range' in var.ncattrs():
                lo, hi = var.valid_range
                valid &= (values >= lo) & (values <= hi)
            result[key], masks[key] = values, valid
    return result, masks, current_nav


def stats(values):
    good = np.isfinite(values)
    if not good.any():
        return {'count': 0, 'min': None, 'max': None, 'mean': None, 'rms': None}
    x = values[good]
    return {'count': int(good.sum()), 'min': float(x.min()), 'max': float(x.max()),
            'mean': float(x.mean()), 'rms': float(np.sqrt(np.mean(x*x)))}


def read_result(path, nn, nz):
    with path.open('rb') as stream:
        mask = np.fromfile(stream, '<i4', nn*(nz-1)).reshape(nn, nz-1, order='F')
        layer = np.fromfile(stream, '<f8', 9*nn*(nz-1)).reshape(9, nn, nz-1, order='F')
        column = np.fromfile(stream, '<f8', 9*nn).reshape(9, nn, order='F')
        if stream.read(1):
            raise ValueError('unexpected output suffix')
    if np.any((mask != 0) & (mask != 1)):
        raise ValueError('invalid output support')
    if not np.isfinite(layer[:, mask == 1]).all() or not np.isnan(layer[:, mask == 0]).all():
        raise ValueError('layer NaN/support mismatch')
    present = np.any(mask == 1, axis=1)
    if not np.isfinite(column[:, present]).all() or not np.isnan(column[:, ~present]).all():
        raise ValueError('column NaN/support mismatch')
    return mask, layer, column


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-report', type=Path, required=True, help='PR39 thermodynamic replay report')
    parser.add_argument('--ht-dir', type=Path, required=True, help='PR40 scratch HT capture directory')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    prior = json.loads(args.source_report.read_text())
    ht_dir = args.ht_dir.resolve()
    receipt = json.loads((ht_dir / 'comparison.json').read_text())
    epoch = prior['times'][1]
    if not np.isfinite(epoch) or epoch != round(epoch):
        raise ValueError('invalid reference epoch')
    epoch = int(epoch)
    inputs = {name: Path(prior['input_paths'][name]) for name in ('lsx_1', 'lt1_1', 'lq3_1')}
    for name, path in inputs.items():
        if sha(path) != prior['input_sha256'][name]:
            raise ValueError(f'prior source hash mismatch: {name}')
    if sha(inputs['lt1_1']) != receipt['retained_lt1_sha256']:
        raise ValueError('HT capture and final LT1 lineage differ')
    inputs.update({'source_report': args.source_report.resolve(), 'capture_receipt': ht_dir / 'comparison.json'})
    names = {'ta': 'temp_after_insert_tobs', 'qa': 'sh_before_hydrostatic',
             'p': 'pres3d_before_hydrostatic', 'ht': 'ht_after_hydrostatic'}
    for name, suffix in names.items():
        inputs[name] = ht_dir / 'replay/instrumented_unlimited' / f'pr40_{suffix}.bin'
    pins = {name: sha(path) for name, path in inputs.items()}
    data = {name: capture(inputs[name]) for name in names}
    shape = data['p'].shape
    if any(value.shape != shape for value in data.values()):
        raise ValueError('capture shapes differ')
    p = data['p'][0, 0, :]
    if (not np.isfinite(p).all() or np.any(p < 100) or np.any(p > 120000)
            or np.any(np.diff(p) >= 0) or not np.all(data['p'] == p)):
        raise ValueError('capture pressure not a shared descending grid')
    nx, ny, nz = shape
    nn = nx*ny
    final, final_mask, navigation = product(inputs['lt1_1'], [('t3', 'degrees Kelvin'), ('ht', 'meters')], epoch, pressure=p)
    moist, moist_mask, _ = product(inputs['lq3_1'], [('sh', 'kg/kg')], epoch, navigation, p)
    surface, surface_mask, _ = product(inputs['lsx_1'], [('ps', 'pascals')], epoch, navigation)
    if final['t3'].shape != shape or moist['sh'].shape != shape or surface['ps'].shape != (nx, ny, 1):
        raise ValueError('source shapes differ')
    if not np.array_equal(final['ht'].astype('f4').view('u4'), data['ht'].astype('f4').view('u4')):
        raise ValueError('captured same-stage HT no longer matches retained HT')
    if not surface_mask['ps'].all():
        raise ValueError('invalid ground pressure')
    ps = surface['ps'][:, :, 0]
    common = final_mask['t3'] & moist_mask['sh'] & final_mask['ht']
    for value in data.values():
        common &= np.isfinite(value)
    common &= (p[None, None, :] <= ps[:, :, None])
    numerical = ((data['ta'] >= 100) & (data['ta'] <= 500)
                 & (final['t3'] >= 100) & (final['t3'] <= 500)
                 & (data['qa'] >= 0) & (data['qa'] < 1)
                 & (moist['sh'] >= 0) & (moist['sh'] < 1))
    if np.any(common & ~numerical):
        raise ValueError('supported thermodynamic state outside numerical range')
    state = np.stack((data['ta'], data['qa'], final['t3'], moist['sh'], data['ht']), axis=-1)
    state = state.reshape(nn, nz, 5, order='F')
    valid = common.reshape(nn, nz, order='F').astype('<i4')
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with (out / 'prepared.bin').open('wb') as stream:
        np.array([nn, nz], '<i4').tofile(stream)
        for values in (p, ps.ravel(order='F'), state):
            np.asarray(values, dtype='<f8').ravel(order='F').tofile(stream)
        valid.ravel(order='F').tofile(stream)

    repo = Path(__file__).resolve().parents[1]
    source_names = ['tests/qbal_thickness_attribution.f90', 'tests/diagnose_qbal_thickness_attribution.f90',
                    'tests/diagnose_qbal_thickness_attribution.py', 'tests/diagnose_qbal_sloping_faces.py',
                    'tests/intel_toolchain.sh']
    source_pins = {name: sha(repo / name) for name in source_names}
    script = out / 'run.sh'
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
 "$CLOUD_BAL_FC" "${flags[@]}" -convert little_endian "$repo/tests/qbal_thickness_attribution.f90" "$repo/tests/diagnose_qbal_thickness_attribution.f90" -o diagnose
 ./diagnose "$out/prepared.bin" result.bin
 )
done
''')
    with (out / 'intel.log').open('w') as log:
        subprocess.run(['bash', str(script), str(repo), str(out)], stdout=log, stderr=subprocess.STDOUT, check=True)
    a, b = [read_result(out / level / 'result.bin', nn, nz) for level in ('O0', 'O2')]
    expected_mask = valid[:, :-1] * valid[:, 1:]
    if not np.array_equal(a[0], expected_mask) or not np.array_equal(a[0], b[0]):
        raise ValueError('matched layer support mismatch')
    for index in (1, 2):
        bound = a[index][5] + b[index][5]
        if np.any(np.abs(a[index]-b[index]) > bound[None, ...]):
            raise ValueError('O0/O2 difference exceeds arithmetic bound')
    mask, layer, column = a
    if not np.any(mask):
        raise ValueError('no matched above-ground layers')
    for values in (layer, column):
        if np.any(np.abs(values[2]+values[3]-values[4]) > values[5]):
            raise ValueError('attribution closure failed')
    np.savez_compressed(out / 'arrays.npz', pressure=p, ps=ps, valid=valid, supported=mask,
                        layer=layer, matched_column=column, grid_shape=np.array([nx, ny]))
    locations = {}
    for index in (2, 3, 4):
        node, level = np.unravel_index(np.nanargmax(np.abs(layer[index])), layer[index].shape)
        locations[FIELDS[index]] = {
            'i_j_one_based': [int(node % nx + 1), int(node // nx + 1)],
            'bottom_top_pressure_Pa': [float(p[level]), float(p[level+1])],
            'colocated_values_m': {name: float(layer[j, node, level]) for j, name in enumerate(FIELDS)},
        }
    node = int(np.nanargmax(np.abs(column[4])))
    levels = np.flatnonzero(mask[node])
    column_location = {
        'i_j_one_based': [node % nx + 1, node // nx + 1],
        'matched_layer_indices_zero_based': levels.tolist(),
        'lowest_highest_matched_pressure_Pa': [float(p[levels[0]]), float(p[levels[-1]+1])],
        'colocated_values_m': {name: float(column[j, node]) for j, name in enumerate(FIELDS)},
    }
    report = {
        'status': 'PASS_SCOPED / MATCHED_LAYER_THERMODYNAMIC_ATTRIBUTION', 'epoch': epoch,
        'grid_shape': [nx, ny, nz], 'field_order': FIELDS,
        'layer_count': int(mask.sum()), 'matched_columns': int(np.any(mask, axis=1).sum()),
        'per_pressure_layer_count': mask.sum(axis=0).tolist(),
        'below_ground_level_count': int(np.count_nonzero(p[None, None, :] > ps[:, :, None])),
        'source_invalid_above_ground_level_count': int(np.count_nonzero((~common) & (p[None, None, :] <= ps[:, :, None]))),
        'extreme_layer_locations': locations,
        'max_absolute_matched_column_change_location': column_location,
        'layer_statistics_m': {name: stats(layer[i]) for i, name in enumerate(FIELDS)},
        'matched_column_statistics_m': {name: stats(column[i]) for i, name in enumerate(FIELDS)},
        'closure_ratio_max': float(np.nanmax(np.abs(layer[8])/layer[5])),
        'input_paths': {name: str(path) for name, path in inputs.items()}, 'input_sha256': pins,
        'source_sha256': source_pins,
        'contract': 'Specific humidity; gas-only Tv; identical endpoint trapezoid in ln(p); common finite source support with p<=PS; no surface partial layer or gap filling.',
        'producer_identity': 'Conditional retained-binary capture from PR40; this diagnostic quadrature is not the historical producer algorithm.',
        'height_contract': 'HT used unchanged for layer-difference diagnostics; no absolute height datum or ground offset corrected.',
        'full_column_thickness': None, 'physical_flux_residual': None, 'production_authority': False,
    }
    for name, path in inputs.items():
        if sha(path) != pins[name]: raise ValueError(f'input changed: {name}')
    for name, pin in source_pins.items():
        if sha(repo / name) != pin: raise ValueError(f'source changed: {name}')
    report['artifact_sha256'] = {name: sha(out / name) for name in ('prepared.bin', 'arrays.npz')}
    (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
