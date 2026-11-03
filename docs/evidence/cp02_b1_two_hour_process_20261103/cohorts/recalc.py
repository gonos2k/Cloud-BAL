#!/usr/bin/env python3
"""Recompute the B1 +1/+2 paired probe and map four diagnostic RN1 cohorts."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset

BASE = Path('/var/tmp/cloudbal-recount-contract')
ANALYSIS_DIR = BASE / 'docs/evidence/weak_strong_balance_20261030/analysis'
ARCHIVED_MAPPER = BASE / 'docs/evidence/precip_hourly_20261027/rn1_recovery/archived_compare_six_hour_csi.py'
CONTROL_TOOL = BASE / 'tools/cp02_precip_control_mapping.py'
ANALYSIS_COORDS = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300')
RUNTIME = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030')
CASES = {'OLD': RUNTIME / 'ORIGINAL_B1_100',
         'FIX': Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED')}
THRESHOLDS = (0.1, 0.5, 1.0, 5.0)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def csi_counts(obs: np.ndarray, fcst: np.ndarray, threshold: float) -> dict[str, int | float]:
    o, f = obs >= threshold, fcst >= threshold
    hit = int(np.count_nonzero(o & f))
    miss = int(np.count_nonzero(o & ~f))
    false_alarm = int(np.count_nonzero(~o & f))
    denominator = hit + miss + false_alarm
    return {'hit': hit, 'miss': miss, 'false_alarm': false_alarm,
            'CSI': hit / denominator if denominator else float('nan')}


def select(arrays: np.lib.npyio.NpzFile) -> list[dict[str, Any]]:
    obs, old, fix = arrays['reference'], arrays['ORIGINAL_B1_100'], arrays['IMPROVED_BG_FIXED']
    masks = {
        'weak_hit_lost': (obs >= .1) & (obs < 1) & (old >= .1) & (fix < .1),
        'weak_new_false_alarm': (obs < .1) & (old < .1) & (fix >= .1) & (fix < 1),
        'weak_stable_hit': (obs >= .1) & (obs < 1) & (old >= .1) & (old < 1) & (fix >= .1) & (fix < 1),
        'strong_hit_gain': (obs >= 5) & (old < 5) & (fix >= 5),
        'strong_stable_hit_fallback': (obs >= 5) & (old >= 5) & (fix >= 5),
    }
    counts = {name: int(np.count_nonzero(mask)) for name, mask in masks.items()}
    chosen = []
    for role in ('weak_hit_lost', 'weak_new_false_alarm', 'weak_stable_hit'):
        eligible = np.flatnonzero(masks[role])
        if not eligible.size:
            raise RuntimeError(f'empty required diagnostic group: {role}')
        i = min(eligible, key=lambda ix: (-abs(float(fix[ix] - old[ix])), int(arrays['flat_index_yx'][ix])))
        chosen.append((role, int(i), role))
    if counts['strong_hit_gain']:
        eligible = np.flatnonzero(masks['strong_hit_gain'])
        role = 'strong_hit_gain'
        selection_note = 'threshold-5 hit-gain cohort available'
    else:
        eligible = np.flatnonzero(masks['strong_stable_hit_fallback'])
        role = 'strong_stable_hit_fallback'
        selection_note = 'predeclared fallback: threshold-5 hit-gain cohort empty'
    if not eligible.size:
        raise RuntimeError('strong hit-gain and stable-hit fallback cohorts are both empty')
    ix = min(eligible, key=lambda n: (-abs(float(fix[n] - old[n])), int(arrays['flat_index_yx'][n])))
    chosen.append((role, int(ix), selection_note))
    rows = []
    for n, (role, i, note) in enumerate(chosen, 1):
        row = {'point_id': f'P{n:02d}', 'diagnostic_group': role,
               'selection_note': note, 'rn1_sample_index_zero_based': i,
               'target_flat_index_yx': int(arrays['flat_index_yx'][i]),
               'latitude': float(arrays['latitude'][i]), 'longitude': float(arrays['longitude'][i]),
               'reference_plus2_mm': float(obs[i]), 'OLD_plus2_mm': float(old[i]),
               'FIX_plus2_mm': float(fix[i]), 'delta_P_plus2_mm': float(fix[i] - old[i]),
               'selection_rule': 'within the declared group, maximize abs(FIX−OLD) one-hour precipitation at +2; tie-break smallest target_flat_index_yx; posthoc diagnostic, not performance holdout or physics/input mask'}
        for lead in (1, 2):
            a = np.load(ANALYSIS_DIR / f'hour_{12 + lead}_arrays.npz')
            r, o, f = float(a['reference'][i]), float(a['ORIGINAL_B1_100'][i]), float(a['IMPROVED_BG_FIXED'][i])
            row.update({f'RN1_plus{lead}_mm': r, f'OLD_plus{lead}_mm': o, f'FIX_plus{lead}_mm': f,
                        f'OLD_plus{lead}_t0p1_hit': bool(r >= .1 and o >= .1),
                        f'FIX_plus{lead}_t0p1_hit': bool(r >= .1 and f >= .1),
                        f'OLD_plus{lead}_t0p1_FA': bool(r < .1 and o >= .1),
                        f'FIX_plus{lead}_t0p1_FA': bool(r < .1 and f >= .1),
                        f'OLD_plus{lead}_t5_hit': bool(r >= 5 and o >= 5),
                        f'FIX_plus{lead}_t5_hit': bool(r >= 5 and f >= 5)})
        row['eligible_group_counts'] = counts
        rows.append(row)
    return rows


def mapping(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tool = load_module(CONTROL_TOOL, 'control_map_tool')
    mapper = tool.load_archived_mapper()  # verifies the mapper's pinned SHA-256
    with Dataset(ANALYSIS_COORDS) as ds:
        lat = np.asarray(ds['lat'][6:259, 75:224], dtype=np.float64)
        lon = np.asarray(ds['lon'][6:259, 75:224], dtype=np.float64)
    if lat.shape != (253, 149) or lon.shape != lat.shape:
        raise RuntimeError(f'ODAM analysis crop shape mismatch: {lat.shape}/{lon.shape}')
    history = RUNTIME / 'ORIGINAL_B1_100' / 'wrfout_d01_2026-08-16_12:00:00'
    with Dataset(history) as ds:
        source_lat = np.asarray(ds['XLAT'][0], dtype=np.float64)
        source_lon = np.asarray(ds['XLONG'][0], dtype=np.float64)
    # Same inclusive crop convention in cp02_precip_control_mapping.py: [7,259]y,[76,224]x.
    jbase, ibase = 5, 74
    corners_lat = source_lat[jbase:259, ibase:224]
    corners_lon = source_lon[jbase:259, ibase:224]
    mask = np.zeros(lat.shape, dtype=bool)
    positions = {}
    for row in rows:
        y, x = divmod(int(row['target_flat_index_yx']), 149)
        if not (0 <= y < 253 and 0 <= x < 149):
            raise RuntimeError(f"bad RN1 target flat index: {row['target_flat_index_yx']}")
        if float(row['latitude']) != float(lat[y, x]) or float(row['longitude']) != float(lon[y, x]):
            raise RuntimeError(f"RN1/ODAM coordinate mismatch for {row['point_id']}")
        mask[y, x] = True
        positions[row['point_id']] = (y, x)
    mapped = mapper.build_curvilinear_mapping(corners_lat, corners_lon, lat, lon, mask)
    out = []
    for row in rows:
        y, x = positions[row['point_id']]
        j0, i0 = int(mapped['j0'][y, x]) + jbase, int(mapped['i0'][y, x]) + ibase
        u, v = float(mapped['u'][y, x]), float(mapped['v'][y, x])
        w = ((1-u)*(1-v), u*(1-v), (1-u)*v, u*v)
        cells = ((j0, i0), (j0, i0+1), (j0+1, i0), (j0+1, i0+1))
        reconstruction_lat = sum(ww * source_lat[jj, ii] for (jj, ii), ww in zip(cells, w))
        reconstruction_lon = sum(ww * source_lon[jj, ii] for (jj, ii), ww in zip(cells, w))
        if abs(sum(w) - 1.0) > 1e-12:
            raise RuntimeError(f"weights do not sum to one for {row['point_id']}")
        if max(abs(reconstruction_lat - row['latitude']), abs(reconstruction_lon - row['longitude'])) > 1e-6:
            raise RuntimeError(f"canonical bilinear coordinate reconstruction failed for {row['point_id']}")
        for label, (jj, ii), weight in zip(('00','10','01','11'), cells, w):
            out.append({'point_id': row['point_id'], 'diagnostic_group': row['diagnostic_group'],
                        'corner': label, 'native_j_zero_based': jj, 'native_i_zero_based': ii,
                        'wrf_j_1based': jj + 1, 'wrf_i_1based': ii + 1, 'weight': weight,
                        'bilinear_u': u, 'bilinear_v': v,
                        'target_y_zero_based': y, 'target_x_zero_based': x,
                        'coordinate_residual_max_deg': float(mapped['residual_max_deg']),
                        'reconstructed_latitude': reconstruction_lat,
                        'reconstructed_longitude': reconstruction_lon,
                        'weight_sum': sum(w), 'coordinate_source': str(history)})
    identity = {'control_mapping_tool': str(CONTROL_TOOL), 'control_mapping_tool_sha256': sha256(CONTROL_TOOL),
                'canonical_archived_mapper': str(ARCHIVED_MAPPER), 'canonical_archived_mapper_sha256': sha256(ARCHIVED_MAPPER),
                'old_b1_time0_history': str(history), 'old_b1_time0_history_sha256': sha256(history),
                'analysis_coordinate_file': str(ANALYSIS_COORDS), 'analysis_coordinate_sha256': sha256(ANALYSIS_COORDS),
                'analysis_crop': {'shape_yx': [253,149], 'source_slice': '[6:259,75:224]',
                                  'native_coordinate_crop': '[j=5:259,i=74:224]'},
                'mapping_function': 'existing archived_compare_six_hour_csi.build_curvilinear_mapping loaded through cp02_precip_control_mapping.load_archived_mapper()',
                'max_mapping_residual_deg': float(mapped['residual_max_deg'])}
    return out, identity, mapped, mapper


def native_precip_reconstruction(rows: list[dict[str, Any]], arrays_by_lead: dict[int, Any],
                                 mapped: dict[str, Any], mapper: Any) -> list[dict[str, Any]]:
    inventory = {'bucket_contract': {'BUCKET_MM': -1.0, 'PREC_ACC_DT': 0.0},
                 'rainsh': {'policy': 'exclude_zero', 'source': mapper.RAINSH_SOURCE,
                            'model_driver': mapper.RAINSH_DRIVER,
                            'zero_tolerance_mm': mapper.NEGATIVE_TOLERANCE_MM}}
    jbase, ibase = 5, 74
    ys, xs = slice(jbase, 259), slice(ibase, 224)
    source_grid = None
    result = []
    for case_label, (case_dir, array_key) in {'OLD': ('ORIGINAL_B1_100', 'ORIGINAL_B1_100'),
                                               'FIX': ('IMPROVED_BG_FIXED', 'IMPROVED_BG_FIXED')}.items():
        root = CASES[case_label]
        cumulative = {}
        for hour in (12,13,14):
            path = root / f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
            snapshot = mapper.read_wrf_snapshot(path, datetime(2026,8,16,hour,tzinfo=timezone.utc), inventory)
            if source_grid is None:
                source_grid = (snapshot['lat'].copy(), snapshot['lon'].copy())
            elif not np.array_equal(source_grid[0], snapshot['lat']) or not np.array_equal(source_grid[1], snapshot['lon']):
                raise RuntimeError(f'{case_label} history grid changed at {hour}Z')
            total, valid = mapper.raw_total(snapshot)
            cumulative[hour] = mapper.remap_field(total[ys,xs], valid[ys,xs], mapped)
        for point in rows:
            y,x = divmod(int(point['target_flat_index_yx']),149)
            for lead, end_hour in ((1,13),(2,14)):
                previous, previous_valid = cumulative[end_hour-1]
                current, current_valid = cumulative[end_hour]
                if not (previous_valid[y,x] and current_valid[y,x]):
                    raise RuntimeError(f'{case_label} remap lacks valid point {point["point_id"]} at +{lead}')
                reconstructed = max(0.0, float(current[y,x] - previous[y,x]))
                canonical = float(arrays_by_lead[lead][array_key][int(point['rn1_sample_index_zero_based'])])
                difference = reconstructed - canonical
                result.append({'case':case_label,'point_id':point['point_id'],'lead_hour':lead,
                               'native_reconstructed_mm':reconstructed,'canonical_array_mm':canonical,
                               'difference_mm':difference,'within_1e-6_mm':abs(difference)<=1e-6,
                               'rainsh_policy':'checked zero and excluded from RAINC+RAINNC total',
                               'mapping':'archived mapper remap_field on cumulative RAINC+RAINNC, then hourly difference'})
    return result


def history_samples(corners: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # AL/ALB exist in the B1 initial wrfinput only; histories at +1/+2 omit these variables.
    unique = {(r['point_id'], r['wrf_j_1based'], r['wrf_i_1based'], r['weight']) for r in corners}
    rows, files = [], {}
    for case_label, root in CASES.items():
        input_path = root / 'wrfinput_d01'
        with Dataset(input_path) as ds:
            for point_id, j1, i1, weight in sorted(unique):
                for k in range(39):
                    for field in ('AL', 'ALB', 'QVAPOR'):
                        if field not in ds.variables:
                            raise RuntimeError(f'{field} missing from {input_path}')
                        rows.append({'case': case_label, 'valid_hour': 0, 'point_id': point_id,
                                     'wrf_j_1based': j1, 'wrf_i_1based': i1, 'k_zero_based': k,
                                     'field': field, 'value': float(ds[field][0,k,j1-1,i1-1]),
                                     'availability': 'present_in_B1_wrfinput'})
        files[f'{case_label}_wrfinput'] = {'path': str(input_path), 'sha256': sha256(input_path)}
        for hour in (1, 2):
            history = root / f'wrfout_d01_2026-08-16_{12+hour:02d}:00:00'
            with Dataset(history) as ds:
                for point_id, j1, i1, weight in sorted(unique):
                    for k in range(39):
                        for field in ('AL', 'ALB', 'QVAPOR'):
                            present = field in ds.variables
                            rows.append({'case': case_label, 'valid_hour': hour, 'point_id': point_id,
                                         'wrf_j_1based': j1, 'wrf_i_1based': i1, 'k_zero_based': k,
                                         'field': field,
                                         'value': float(ds[field][0,k,j1-1,i1-1]) if present else '',
                                         'availability': 'present_in_wrfout_history' if present else 'not_written_to_history'})
            files[f'{case_label}_wrfout_hour{hour}'] = {'path': str(history), 'sha256': sha256(history)}
    return rows, files


def runtime_receipts() -> dict[str, dict[str, str]]:
    paths = {
        'OLD_case_receipt': BASE / 'docs/evidence/weak_strong_balance_20261030/runtime/cases/ORIGINAL_B1_100/receipt.json',
        'OLD_final_receipt': BASE / 'docs/evidence/weak_strong_balance_20261030/runtime/final_receipt.json',
        'OLD_history_validation': BASE / 'docs/evidence/weak_strong_balance_20261030/runtime/history_validation.json',
        'FIX_normalized_receipt': BASE / 'docs/evidence/six_hour_improvement_20261030/runtime/normalized_receipt.json',
        'FIX_history_validation': BASE / 'docs/evidence/six_hour_improvement_20261030/runtime/history_validation.json',
        'FIX_one_hour_comparison': BASE / 'docs/evidence/six_hour_improvement_20261030/runtime/one_hour_comparison.json',
    }
    receipts = {name: {'path': str(path), 'sha256': sha256(path)} for name,path in paths.items()}
    old_case = json.loads(paths['OLD_case_receipt'].read_text())
    fix_case = json.loads(paths['FIX_normalized_receipt'].read_text())
    expected_input = sha256(CASES['OLD'] / 'wrfinput_d01')
    if old_case['status'] != 'SUCCESS' or old_case['staged_sha256_after'].get('wrfinput_d01') != expected_input:
        raise RuntimeError('OLD runtime receipt does not bind the selected B1 input')
    if fix_case['status'] != 'SUCCESS' or fix_case['staged_sha256_after'].get('wrfinput_d01') != expected_input:
        raise RuntimeError('FIX runtime receipt does not bind the same selected B1 input')
    old_hist = json.loads(paths['OLD_history_validation'].read_text())['cases']['ORIGINAL_B1_100']['histories']
    old_hist_hashes = {r['file']: r['sha256'] for r in old_hist}
    fix_hist = json.loads(paths['FIX_history_validation'].read_text())['histories']
    fix_hist_hashes = {r['name']: r['sha256'] for r in fix_hist}
    for hour in (0,1,2):
        name = f'wrfout_d01_2026-08-16_{12+hour:02d}:00:00'
        old_path = CASES['OLD'] / name
        fix_path = CASES['FIX'] / name
        if old_hist_hashes.get(name) != sha256(old_path):
            raise RuntimeError(f'OLD history hash is not bound by validation receipt: {name}')
        if fix_hist_hashes.get(name) != sha256(fix_path) or fix_case['output_sha256'].get(name) != sha256(fix_path):
            raise RuntimeError(f'FIX history hash is not bound by runtime/history receipt: {name}')
    return receipts


def main(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    source_hashes = {}
    pair_scores = []
    arrays_by_lead = {}
    for lead in range(1, 7):
        path = ANALYSIS_DIR / f'hour_{12+lead}_arrays.npz'
        source_hashes[path.name] = sha256(path)
        a = np.load(path, allow_pickle=False)
        arrays_by_lead[lead] = a
        obs = a['reference']
        for name, oldkey, fixkey in (('original_input', 'ORIGINAL', 'FIXED_ORIGINAL_100'),
                                     ('B1_input', 'ORIGINAL_B1_100', 'IMPROVED_BG_FIXED')):
            for threshold in THRESHOLDS:
                old, fix = csi_counts(obs, a[oldkey], threshold), csi_counts(obs, a[fixkey], threshold)
                pair_scores.append({'lead_hour': lead, 'input_pair': name, 'OLD_case': oldkey,
                                    'FIX_case': fixkey, 'threshold_mm': threshold,
                                    **{f'OLD_{k}': v for k,v in old.items()},
                                    **{f'FIX_{k}': v for k,v in fix.items()},
                                    'delta_CSI_FIX_minus_OLD': fix['CSI'] - old['CSI'],
                                    'delta_hit_FIX_minus_OLD': fix['hit'] - old['hit'],
                                    'delta_false_alarm_FIX_minus_OLD': fix['false_alarm'] - old['false_alarm']})
    a2 = arrays_by_lead[2]
    rows = select(a2)
    corner_rows, map_info, mapped, mapper = mapping(rows)
    reconstruction = native_precip_reconstruction(rows, arrays_by_lead, mapped, mapper)
    timeseries, runtime_hashes = history_samples(corner_rows)
    # Preserve superseded, unrestricted preliminary candidates and their rule in audit metadata.
    preselected = {
        'selection_rule': 'unrestricted first pass: one point from each binary transition/stable category, max abs delta then flat-index tie-break; replaced after weak-observed focus was specified',
        'hit_lost': {'sample_index': 305, 'flat_index_yx': 10201, 'observed_plus2_mm': 11.2,
                     'OLD_plus2_mm': .3164687734142179, 'FIX_plus2_mm': .0321117358418741,
                     'latitude': 34.90729904174805, 'longitude': 127.50761413574219},
        'new_false_alarm': {'sample_index': 514, 'flat_index_yx': 11082, 'observed_plus2_mm': 0.0,
                            'OLD_plus2_mm': .0004008733247453883, 'FIX_plus2_mm': 1.1176509935011945,
                            'latitude': 35.19065475463867, 'longitude': 126.78507995605469},
        'stable_hit': {'sample_index': 201, 'flat_index_yx': 9614, 'observed_plus2_mm': .5,
                       'OLD_plus2_mm': 16.22711137544967, 'FIX_plus2_mm': 13.789640728532676,
                       'latitude': 34.71521759033203, 'longitude': 128.00437927246094},
        'threshold5_hit_gain': {'eligible_count': 0},
        'strong_stable_fallback': {'sample_index': 544, 'flat_index_yx': 11112, 'observed_plus2_mm': 9.4,
                                   'OLD_plus2_mm': 60.44618882247576, 'FIX_plus2_mm': 62.83795731256127,
                                   'latitude': 35.16273880004883, 'longitude': 128.46669006347656}}
    package = {'schema': 'b1-two-hour-cohort-probe-v1',
               'status': 'FROZEN_DIAGNOSTIC_SELECTION',
               'base_commit': '83804668a02e20eeac686d00ff5b2ff6b9a71154',
               'base_pull_request': 142,
               'recalc_script_sha256': sha256(Path(__file__).resolve()),
               'common_sample_size': 3688,
               'lead_definition': '+1/+2 each denotes a separate 1-hour accumulation window ending 13Z/14Z',
               'paired_comparison': {'OLD': 'ORIGINAL_B1_100 (ORIGINAL executable, B1 input)',
                                     'FIX': 'IMPROVED_BG_FIXED (FIX executable, same B1 input)',
                                     'input_identity_check': 'exact wrfinput_d01 SHA-256 equality verified'},
               'selection_group_counts': rows[0]['eligible_group_counts'],
               'selection_design': {'threshold_mm': .1, 'weak_observed_band_mm': '[0.1,1.0)',
                                    'weak_forecast_band_mm': '[0.1,1.0)',
                                    'rule': 'maximum absolute FIX−OLD one-hour precipitation difference within each group; tie-break by smallest RN1 target flat index; diagnostic posthoc selection, not performance holdout or physics/input mask',
                                    'strong_control_fallback': 'use stable observed>=5 mm and OLD,FIX>=5 mm if threshold-5 hit-gain group is empty',
                                    'superseded_unrestricted_selection_audit': preselected},
               'mapping': map_info, 'points': rows,
               'source_hashes_sha256': source_hashes,
               'runtime_files_sha256': runtime_hashes,
               'runtime_receipt_sha256': runtime_receipts(),
               'native_precip_reconstruction': {'rows': len(reconstruction),
                   'all_within_1e-6_mm': all(r['within_1e-6_mm'] for r in reconstruction),
                   'max_abs_difference_mm': max(abs(r['difference_mm']) for r in reconstruction),
                   'method': 'canonical RAINC+RAINNC cumulative remap then hourly differencing; RAINSH checked/excluded'}}
    (outdir/'selection.json').write_text(json.dumps(package, indent=2, sort_keys=True)+'\n')
    for name, data in [('corners.csv', corner_rows), ('paired_scores.csv', pair_scores),
                       ('selected_points.csv', rows), ('history_samples.csv', timeseries),
                       ('native_precip_reconstruction.csv', reconstruction)]:
        with (outdir/name).open('w', newline='') as stream:
            if not data: continue
            writer = csv.DictWriter(stream, fieldnames=list(data[0]))
            writer.writeheader(); writer.writerows(data)
    print(json.dumps({'output': str(outdir), 'selected_points': [r['point_id'] for r in rows],
                      'corners': len(corner_rows), 'history_samples': len(timeseries),
                      'paired_score_rows': len(pair_scores), 'mapping_residual_deg': map_info['max_mapping_residual_deg']}, indent=2))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', type=Path, default=Path(__file__).resolve().parent)
    main(parser.parse_args().out_dir)
