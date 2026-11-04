#!/usr/bin/env python3
"""Extract paired Eulerian state snapshots using frozen native-corner physics."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from netCDF4 import Dataset

PROTOCOL_SHA256 = '5f44ad36d60e3443f7da7bbf7253359160114e954d3015ed8cef6ca059237690'
NPOINTS, NLEVELS = 3688, 39
RD, RV, CP = 287.0, 461.6, 1004.5
QMIN = 1e-15


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def corners(mapping, flat_indices):
    flat_indices = np.asarray(flat_indices)
    if flat_indices.shape != (NPOINTS,) or len(np.unique(flat_indices)) != NPOINTS:
        raise ValueError('expected 3688 unique canonical points')
    y, x = np.divmod(flat_indices, 149)
    if np.any(y < 0) or np.any(y >= 253) or not mapping['valid'][y, x].all():
        raise ValueError('canonical point outside valid mapping')
    j, i = mapping['j0'][y, x] + 5, mapping['i0'][y, x] + 74
    u, v = mapping['u'][y, x], mapping['v'][y, x]
    jj = np.stack((j, j, j + 1, j + 1), axis=-1)
    ii = np.stack((i, i + 1, i, i + 1), axis=-1)
    weights = np.stack(((1-u)*(1-v), u*(1-v), (1-u)*v, u*v), axis=-1)
    if (np.any(jj < 0) or np.any(jj >= 282) or np.any(ii < 0) or np.any(ii >= 234)
        or not np.isfinite(weights).all() or np.any(weights < 0)
        or not np.allclose(weights.sum(axis=-1), 1, rtol=0, atol=1e-12)):
        raise ValueError('invalid source corner/weight')
    return jj, ii, weights


def temperature_from_history(theta_perturbation, pressure):
    """History T is dry potential-temperature perturbation, not THM."""
    if not np.isfinite(theta_perturbation).all() or not np.isfinite(pressure).all() or np.any(pressure <= 0):
        raise ValueError('invalid temperature or pressure input')
    return (theta_perturbation + 300.0) * (pressure / 100000.0) ** (RD / CP)


def humidity(qv, temperature, pressure, *, ice_or_water=False):
    """KDM6 saturation formula at snapshots; REAL64 diagnostic, not bit-exact."""
    if (not np.isfinite(qv).all() or not np.isfinite(temperature).all()
        or not np.isfinite(pressure).all() or np.any(temperature <= 0) or np.any(pressure <= 0)):
        raise ValueError('invalid thermodynamic input')
    tr = 273.16 / temperature
    liquid_a = -(4 * RV - 4190.0) / RV
    liquid_b = liquid_a + 2.5e6 / (RV * 273.16)
    if ice_or_water:
        ice_a = -(4 * RV - 2106.0) / RV
        ice_b = ice_a + 2.85e6 / (RV * 273.16)
        a = np.where(temperature < 273.16, ice_a, liquid_a)
        b = np.where(temperature < 273.16, ice_b, liquid_b)
    else:
        a, b = liquid_a, liquid_b
    es = np.minimum(610.78 * np.exp(np.log(tr) * a) * np.exp(b * (1 - tr)), 0.99 * pressure)
    qs = np.maximum((RD / RV) * es / (pressure - es), QMIN)
    return np.maximum(qv / qs, QMIN)


def diameter(qrain, qnrain):
    """Unclamped shared-basis gamma mass-weighted mean diameter in mm."""
    valid = (qrain > 0) & (qnrain > 0)
    out = np.full(qrain.shape, np.nan, dtype=np.float64)
    out[valid] = 5000.0 / np.cbrt(4000.0 * np.pi * qnrain[valid] / qrain[valid])
    if not np.isfinite(out[valid]).all():
        raise ValueError('nonfinite valid diameter')
    return out, valid


def weighted(values, weights, valid=None):
    """No renormalization: all positive-weight native corners must be valid."""
    weights = np.asarray(weights)[:, None, :]
    if valid is None:
        valid = np.isfinite(values)
    required = weights > 0
    allowed = np.all(valid | ~required, axis=-1)
    valid_weight = np.sum(np.where(valid, weights, 0.0), axis=-1)
    result = np.sum(np.where(valid, values, 0.0) * weights, axis=-1)
    return np.where(allowed, result, np.nan), valid_weight, allowed


def layer_mean(values, height, low, high):
    """Unweighted native model-level mean per corner, without mass inference."""
    selected = (height >= low) & (height < high)
    count = selected.sum(axis=1)
    sums = np.sum(np.where(selected, values, 0.0), axis=1)
    mean = np.full(count.shape, np.nan, dtype=np.float64)
    np.divide(sums, count, out=mean, where=count > 0)
    return mean[:, None, :], count


def extract_snapshot(path, jj, ii, weights, expected_coordinates):
    with Dataset(path) as ds:
        if getattr(ds, 'USE_THETA_M', None) != 1:
            raise ValueError('USE_THETA_M differs from frozen case')
        def read(name):
            variable = ds.variables[name]
            variable.set_auto_maskandscale(False)
            values = np.asarray(variable[0], dtype=np.float64)
            if values.shape != (NLEVELS, 282, 234):
                raise ValueError(f'{name}: unexpected dimensions')
            result = values[:, jj, ii].transpose(1, 0, 2)
            if not np.isfinite(result).all():
                raise ValueError(f'{name}: nonfinite corner value')
            return result
        qrain, qnrain, qv = read('QRAIN'), read('QNRAIN'), read('QVAPOR')
        theta, theta_m, pressure = read('T'), read('THM'), read('P') + read('PB')
        dry_error = np.abs(theta + 300 - (theta_m + 300) / (1 + (RV / RD) * qv))
        if np.max(dry_error) > 6.0e-5 or np.any(pressure <= 0):
            raise ValueError('dry/moist theta consistency or pressure failed')
        temperature = temperature_from_history(theta, pressure)
        rh_liquid = humidity(qv, temperature, pressure)
        rh_phase = humidity(qv, temperature, pressure, ice_or_water=True)
        dm, dm_valid = diameter(qrain, qnrain)
        ph = np.asarray(ds.variables['PH'][0], dtype=np.float64)
        phb = np.asarray(ds.variables['PHB'][0], dtype=np.float64)
        terrain = np.asarray(ds.variables['HGT'][0], dtype=np.float64)
        if ph.shape != (40, 282, 234) or phb.shape != ph.shape or terrain.shape != (282, 234):
            raise ValueError('invalid geopotential/terrain dimensions')
        geop = (ph + phb)[:, jj, ii].transpose(1, 0, 2)
        height = (geop[:, :-1] + geop[:, 1:]) / (2 * 9.81) - terrain[jj, ii][:, None, :]
        if not np.isfinite(height).all():
            raise ValueError('nonfinite geometric height')
        lat = np.asarray(ds.variables['XLAT'][0], dtype=np.float64)[jj, ii]
        lon = np.asarray(ds.variables['XLONG'][0], dtype=np.float64)[jj, ii]
        mapped = (np.sum(lat * weights, axis=1), np.sum(lon * weights, axis=1))
        if any(not np.allclose(a, b, rtol=0, atol=1e-9) for a, b in zip(mapped, expected_coordinates)):
            raise ValueError('native mapped coordinates differ from paired reference')
    fields = {'qrain_kgkg': qrain, 'qnrain_per_kg': qnrain, 'qvapor_kgkg': qv,
              'temperature_K': temperature, 'pressure_Pa': pressure, 'rh_liquid': rh_liquid,
              'rh_ice_or_water': rh_phase, 'height_agl_m': height}
    output = {name: weighted(value, weights)[0].astype(np.float32) for name, value in fields.items()}
    output['dm_mass_weighted_mm'], output['dm_valid_weight'], output['dm_valid'] = weighted(dm, weights, dm_valid)
    output['dm_mass_weighted_mm'] = output['dm_mass_weighted_mm'].astype(np.float32)
    output['dm_valid_weight'] = output['dm_valid_weight'].astype(np.float32)
    output.update(corner_qrain_kgkg=qrain.astype(np.float32), corner_qnrain_per_kg=qnrain.astype(np.float32),
                  corner_rh_liquid=rh_liquid.astype(np.float32), corner_dm_mass_weighted_mm=dm.astype(np.float32),
                  corner_dm_valid=dm_valid)
    for label, low, high in (('0to1km', 0, 1000), ('1to3km', 1000, 3000)):
        for name, value in (('rh_liquid', rh_liquid), ('temperature_K', temperature)):
            mean, count = layer_mean(value, height, low, high)
            result, coverage, valid = weighted(mean, weights, count[:, None, :] > 0)
            output[f'layer_{label}_{name}_level_mean'] = result[:, 0].astype(np.float32)
            output[f'layer_{label}_{name}_valid_weight'] = coverage[:, 0].astype(np.float32)
            output[f'layer_{label}_{name}_valid'] = valid[:, 0]
        output[f'layer_{label}_corner_level_count'] = count.astype(np.int16)
    return output, float(np.max(dry_error))


def run(protocol_path, output_dir):
    protocol_path, output_dir = Path(protocol_path), Path(output_dir)
    if sha256(protocol_path) != PROTOCOL_SHA256:
        raise ValueError('frozen state protocol differs')
    protocol = json.loads(protocol_path.read_text())
    if protocol['status'] != 'FROZEN_BEFORE_FEATURE_EXTRACTION':
        raise ValueError('state protocol is not frozen')
    transition_path = protocol_path.parent.parent / 'transitions/protocol.json'
    source_hashes = protocol['thermodynamic_sources']
    def verify_sources():
        if (sha256(transition_path) != protocol['transition_protocol_sha256']
            or any(sha256(Path(path)) != digest for path, digest in source_hashes.items())):
            raise ValueError('frozen source or transition protocol changed')
    verify_sources()
    mapping_info = protocol['mapping']
    mapping_path, samples_path = Path(mapping_info['path']), Path(mapping_info['target_samples_path'])
    if sha256(mapping_path) != mapping_info['sha256'] or sha256(samples_path) != mapping_info['target_samples_sha256']:
        raise ValueError('mapping or sample input changed')
    with np.load(samples_path, allow_pickle=False) as samples, np.load(mapping_path, allow_pickle=False) as mapping:
        flat = np.asarray(samples['flat_index_yx'], dtype=np.int64)
        lat, lon = np.asarray(samples['latitude']), np.asarray(samples['longitude'])
        jj, ii, weights = corners(mapping, flat)
    if os.path.lexists(output_dir):
        raise FileExistsError(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.' + output_dir.name + '.', dir=output_dir.parent))
    try:
        records = []
        for case in ('B1', 'NR_PRIOR', 'DM065'):
            for tag in ('input', 'h00', 'h01', 'h02', 'h03', 'h04', 'h05', 'h06'):
                source = protocol['case_time_files'][case][tag]
                path = Path(source['path'])
                if path.stat().st_size != source['size_bytes'] or sha256(path) != source['sha256']:
                    raise ValueError(f'{case}/{tag}: source hash differs')
                values, theta_error = extract_snapshot(path, jj, ii, weights, (lat, lon))
                values.update(flat_index_yx=flat, latitude=lat, longitude=lon,
                              native_j_zero_based=jj, native_i_zero_based=ii,
                              corner_weights=weights, model_level_1based=np.arange(1, 40, dtype=np.int16))
                dest = temporary / f'{case}_{tag}.npz'
                np.savez_compressed(dest, **values)
                if dest.stat().st_size >= 100 * 1024 * 1024:
                    raise ValueError('derived file exceeds 100 MiB')
                if sha256(path) != source['sha256']:
                    raise ValueError(f'{case}/{tag}: source changed while reading')
                records.append({'case': case, 'time': tag, 'input_sha256': source['sha256'],
                                'name': dest.name, 'sha256': sha256(dest), 'size_bytes': dest.stat().st_size,
                                'dry_theta_max_error_K': theta_error,
                                'dm_valid_point_levels': int(values['dm_valid'].sum())})
                print(case, tag, 'done', flush=True)
        if sha256(protocol_path) != PROTOCOL_SHA256 or sha256(mapping_path) != mapping_info['sha256'] or sha256(samples_path) != mapping_info['target_samples_sha256']:
            raise ValueError('frozen inputs changed during extraction')
        verify_sources()
        receipt = {'status': 'PASS', 'protocol_sha256': PROTOCOL_SHA256,
                   'precision': 'Native-corner thermodynamic calculations use float64 and output profiles are rounded to float32; not bit-identical to KDM6 internal operations.',
                   'points': NPOINTS, 'levels': NLEVELS, 'cases': 3, 'times': 8,
                   'records': records, 'scope': 'Eulerian snapshots; physical derived quantities at native corners prior to interpolation; no mass closure or trajectories.'}
        (temporary / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        lock_path = output_dir.parent / '.state_publish.lock'
        with lock_path.open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if os.path.lexists(output_dir):
                raise FileExistsError(output_dir)
            os.rename(temporary, output_dir)
        return receipt
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.protocol, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
