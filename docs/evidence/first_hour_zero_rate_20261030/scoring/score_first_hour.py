#!/usr/bin/env python3
"""Score complete, paired one-hour WRF experiments against the pinned RN1 sample."""
import argparse
import importlib.util
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
OLD = ROOT / 'docs/evidence/current_forecast_paper_20261029'
SCORER = OLD / 'score_forecasts.py'
SCORER_SHA = '73d4ddd8d6b8c4c6eb7903eff000c2c1e1330a2d50a6692ee7e0eaf77d51d539'
ARCHIVED_SHA = '1cfa4965155ec273e8e1ca9f963bd79a5ece3bc47beb4ae3db4e8b8f5e21b2c0'
REFERENCE_SHA = '0df6e55167373751a2a9e50f10325c6d6d1e02603f1225e448c8e766184da9e4'
BUILD_RECEIPT_SHA = '50fb6bf97114cccbb170404b927aa54fc0fa83c72f64f23d2c3c107472c1afc7'
BASE_EXE_SHA = 'de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168'
FIX_EXE_SHA = '68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'
RN1_SHA = '5f435e9e7845860636b8ac6d4a982563f1d709f4340dadb7828df2f2cda8e9a1'
EXPECTED_INPUT = {'SHAM': '7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126',
                  'BASE_H': '7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126',
                  'FIX_H': '7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126',
                  'BASE_ORIGINAL': '5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc',
                  'FIX_ORIGINAL': '5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc'}
PAIRS = [('BASE_H', 'FIX_H'), ('BASE_ORIGINAL', 'FIX_ORIGINAL')]
HISTORIES = [f'wrfout_d01_2026-08-16_{h}:00:00' for h in (12, 13)]


def load_scorer():
    import hashlib
    if hashlib.sha256(SCORER.read_bytes()).hexdigest() != SCORER_SHA:
        raise ValueError('pinned scorer changed')
    spec = importlib.util.spec_from_file_location('pinned_forecast_scorer', SCORER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    if mod.evaluator.sha256(mod.ARCHIVED) != ARCHIVED_SHA:
        raise ValueError('pinned archived evaluator changed')
    return mod


def checked_run(name, directory, evaluator):
    receipt_path, inputs_path = directory / 'receipt.json', directory / 'inputs.json'
    records = [evaluator.identity(receipt_path), evaluator.identity(inputs_path)]
    receipt = json.loads(receipt_path.read_text())
    inputs = json.loads(inputs_path.read_text())
    if (receipt.get('exit') != 0 or any(receipt.get(k) is not True for k in
        ('success_marker', 'histories_exact', 'staged_unchanged', 'source_unchanged'))
        or receipt.get('histories') != HISTORIES
        or sorted(p.name for p in directory.glob('wrfout*')) != HISTORIES):
        raise ValueError(f'{name}: runtime is not complete')
    if inputs.get('source_before') != inputs.get('source_after'):
        raise ValueError(f'{name}: source input manifest changed')
    staged = inputs.get('staged')
    if not isinstance(staged, dict) or staged.get('wrfinput_d01') != EXPECTED_INPUT[name]:
        raise ValueError(f'{name}: unexpected initial input')
    for filename, expected in staged.items():
        if Path(filename).name != filename:
            raise ValueError(f'{name}: invalid staged filename')
        record = evaluator.identity(directory / filename)
        if record['sha256'] != expected:
            raise ValueError(f'{name}: staged input changed: {filename}')
        records.append(record)
    source = Path(inputs['source'])
    for filename, expected in inputs['source_before'].items():
        if Path(filename).name != filename:
            raise ValueError(f'{name}: invalid source filename')
        record = evaluator.identity(source / filename)
        if record['sha256'] != expected:
            raise ValueError(f'{name}: source input changed: {filename}')
        records.append(record)
    if set(receipt.get('output_sha256', {})) != set(HISTORIES):
        raise ValueError(f'{name}: incomplete history hash manifest')
    for filename in HISTORIES:
        record = evaluator.identity(directory / filename)
        if record['sha256'] != receipt['output_sha256'][filename]:
            raise ValueError(f'{name}: history hash mismatch: {filename}')
        records.append(record)
    return staged, records


def verify_build_receipt(path, evaluator):
    record = evaluator.identity(path)
    if record['sha256'] != BUILD_RECEIPT_SHA:
        raise ValueError('build receipt hash mismatch')
    receipt = json.loads(path.read_text())
    if (receipt.get('host_unchanged') is not True
        or receipt['arms']['BASE']['exe'] != BASE_EXE_SHA
        or receipt['arms']['FIX']['exe'] != FIX_EXE_SHA
        or any(receipt['arms'][arm][step]['exit'] != 0
               for arm in ('BASE', 'FIX') for step in ('compile', 'link'))):
        raise ValueError('build receipt does not bind the expected executables')
    return record


def verify_pair_inputs(staged):
    expected = {'SHAM': BASE_EXE_SHA, 'BASE_H': BASE_EXE_SHA,
                'BASE_ORIGINAL': BASE_EXE_SHA, 'FIX_H': FIX_EXE_SHA,
                'FIX_ORIGINAL': FIX_EXE_SHA}
    if any(staged[name].get('wrf.exe') != digest for name, digest in expected.items()):
        raise ValueError('unexpected baseline/fix executable identity')
    for baseline, candidate in [('SHAM', 'BASE_H'), *PAIRS]:
        old = {k: v for k, v in staged[baseline].items() if k != 'wrf.exe'}
        new = {k: v for k, v in staged[candidate].items() if k != 'wrf.exe'}
        if old != new:
            raise ValueError(f'{baseline}/{candidate}: staged inputs differ')


def run(cases, reference_dir, analysis, odam_dir, output, build_receipt):
    if set(cases) != set(EXPECTED_INPUT):
        raise ValueError('all five named cases are required')
    if output.exists() or output.is_symlink():
        raise ValueError('output already exists')
    old = load_scorer()
    ev = old.evaluator
    records = []
    staged = {}
    for name, directory in cases.items():
        staged[name], checked = checked_run(name, directory, ev)
        records.extend(checked)
    records.append(verify_build_receipt(build_receipt, ev))
    verify_pair_inputs(staged)
    reference_npz = OLD / 'scores/hour_13_arrays.npz'
    reference_record = ev.identity(reference_npz)
    if reference_record['sha256'] != REFERENCE_SHA:
        raise ValueError('pinned paired NPZ mismatch')
    records.append(reference_record)
    with np.load(reference_npz, allow_pickle=False) as z:
        prior = {key: np.array(z[key]) for key in ('reference', 'latitude', 'longitude', 'flat_index_yx', 'ORIGINAL', 'CURRENT_HYDRO')}
    ref_records = old.reference_records(reference_dir, analysis)
    inventory, mask, lat, lon, _ = ev.load_reference(reference_dir, analysis)
    records.extend(ref_records.values())
    rn1 = odam_dir / 'DFS_VSRT_GRD_KLPS_ODAM_RN1.202608161300'
    rn1_record = ev.identity(rn1)
    if rn1_record['sha256'] != RN1_SHA:
        raise ValueError('canonical RN1 hash mismatch')
    records.append(rn1_record)
    reference, ref_valid = ev.read_rn1(rn1, 13)
    if (int(mask.sum()) != 3688 or not np.array_equal(np.flatnonzero(mask), prior['flat_index_yx'])
        or not np.array_equal(lat[mask], prior['latitude']) or not np.array_equal(lon[mask], prior['longitude'])
        or not np.array_equal(reference[mask], prior['reference'])):
        raise ValueError('reference/mask differs from independently pinned NPZ')
    snapshots = {}
    source_lat = source_lon = None
    for name, directory in cases.items():
        snapshots[name] = {}
        for hour, filename in zip((12, 13), HISTORIES):
            item, record = old.checked_snapshot(directory / filename, datetime(2026, 8, 16, hour, tzinfo=timezone.utc), inventory)
            if record['sha256'] != next(r['sha256'] for r in records if r['path'] == str(directory / filename)):
                raise ValueError(f'{name}: history changed while reading')
            if source_lat is None:
                source_lat, source_lon = item['lat'], item['lon']
            elif not np.array_equal(source_lat, item['lat']) or not np.array_equal(source_lon, item['lon']):
                raise ValueError(f'{name}: history grid mismatch')
            snapshots[name][hour] = item
    ev.CASES = tuple(cases)
    ev.COMPARE_HOURS = (13,)
    reset_checks = ev.check_resets(snapshots)
    x0, x1 = inventory['grid']['crop_x_inclusive']; y0, y1 = inventory['grid']['crop_y_inclusive']
    ys, xs = slice(y0-2, y1), slice(x0-2, x1)
    mapping = ev.build_curvilinear_mapping(source_lat[ys, xs], source_lon[ys, xs], lat, lon, mask)
    common = mask & mapping['valid'] & ref_valid
    cumulative = {}
    for name, hours in snapshots.items():
        cumulative[name] = {}
        for hour, item in hours.items():
            total, valid = ev.raw_total(item)
            cumulative[name][hour] = ev.remap_field(total[ys, xs], valid[ys, xs], mapping)
            common &= cumulative[name][hour][1]
    if not np.array_equal(common, mask):
        raise ValueError('incomplete common validity')
    values = {k: prior[k] for k in ('reference', 'latitude', 'longitude', 'flat_index_yx')}
    continuous, categorical, transitions = [], [], []
    for name in cases:
        diff = cumulative[name][13][0] - cumulative[name][12][0]
        if np.any(diff[common] < -ev.NEGATIVE_TOLERANCE_MM):
            raise ValueError(f'{name}: negative hourly precipitation')
        values[name] = np.maximum(diff[common], 0.0)
        err = values[name] - values['reference']
        continuous.append({'case': name, 'points': len(err), 'mean_forecast_mm': float(np.mean(values[name])),
                           'mean_reference_mm': float(np.mean(values['reference'])), 'mean_error_mm': float(np.mean(err)),
                           'MAE_mm': float(np.mean(np.abs(err))), 'RMSE_mm': float(np.sqrt(np.mean(err**2)))})
        categorical.extend({'case': name, 'threshold_mm': t, 'points': len(err), **old.scores(values[name], values['reference'], t)} for t in old.THRESHOLDS)
    for baseline, candidate in PAIRS:
        transitions.extend({'baseline': baseline, 'candidate': candidate, 'threshold_mm': t,
                            **old.transitions(values[baseline], values[candidate], values['reference'], t)} for t in old.THRESHOLDS)
    comparisons = {}
    for name, archived in [('SHAM', 'CURRENT_HYDRO'), ('BASE_H', 'CURRENT_HYDRO'), ('BASE_ORIGINAL', 'ORIGINAL')]:
        difference = values[name] - prior[archived]
        comparisons[name] = {'archived_case': archived, 'equal': bool(np.array_equal(values[name], prior[archived])),
                             'changed_points': int(np.count_nonzero(difference)), 'max_abs_difference_mm': float(np.max(np.abs(difference))),
                             'mean_abs_difference_mm': float(np.mean(np.abs(difference)))}
    old.verify_records(records)
    if ev.sha256(old.ARCHIVED) != ARCHIVED_SHA or ev.sha256(SCORER) != SCORER_SHA:
        raise ValueError('pinned code changed during scoring')
    output.mkdir(parents=True, exist_ok=False)
    try:
        np.savez_compressed(output / 'hour_13_arrays.npz', **values)
        old.write_csv(output / 'categorical_scores.csv', categorical)
        old.write_csv(output / 'continuous_scores.csv', continuous)
        old.write_csv(output / 'transitions.csv', transitions)
        result = {'status': 'COMPLETE', 'points': 3688, 'cases': list(cases), 'pairs': PAIRS,
                  'comparisons_to_archived': comparisons, 'reset_checks': reset_checks,
                  'mapping_residual_max_deg': mapping['residual_max_deg'], 'sources': records,
                  'scorer_sha256': ev.sha256(Path(__file__)), 'archived_evaluator_sha256': ARCHIVED_SHA,
                  'reference_limitation': 'RN1 processed analysis lacks a coverage bitmap and may use previous-hour fallback.'}
        (output / 'receipt.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', action='append', required=True, metavar='NAME=RUN_DIRECTORY')
    parser.add_argument('--reference-dir', type=Path, required=True)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--odam-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-receipt', type=Path, required=True)
    args = parser.parse_args()
    cases = {}
    for entry in args.case:
        name, sep, directory = entry.partition('=')
        if not sep or name not in EXPECTED_INPUT or name in cases or not directory:
            parser.error(f'invalid case: {entry}')
        cases[name] = Path(directory)
    run(cases, args.reference_dir, args.analysis, args.odam_dir, args.output, args.build_receipt)


if __name__ == '__main__':
    main()
