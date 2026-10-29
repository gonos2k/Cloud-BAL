#!/usr/bin/env python3
"""Score explicitly supplied 2026-08-16 12 UTC WRF histories against pinned RN1."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ARCHIVED = Path(__file__).resolve().parents[1] / 'precip_hourly_20261027/rn1_recovery/archived_compare_six_hour_csi.py'
ARCHIVED_SHA256 = hashlib.sha256(ARCHIVED.read_bytes()).hexdigest()
spec = importlib.util.spec_from_file_location('archived_precip_evaluator', ARCHIVED)
evaluator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = evaluator
spec.loader.exec_module(evaluator)
if evaluator.sha256(ARCHIVED) != ARCHIVED_SHA256:
    raise ValueError('archived evaluator changed during import')
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
RN1_HASHES = (
    '5f435e9e7845860636b8ac6d4a982563f1d709f4340dadb7828df2f2cda8e9a1',
    '54ba0fe609630eec8366b9f4a21fddd29baabbd1ad89e8a2ac4e769900887497',
    '00219ebc741da5bbdc79b408a1363e4a920d4f58d41118978234d2cbe089f346',
    '74f2b96af4e0686b15dc1c8a75e337f964a9e25841540a61b3d3546e22187af6',
    '77145a0b095203e452cc029cf56a97f1ff10a5485b69f76ab1d21219c15fa2d5',
    'f0b6834a27449904efb7f6242e47a6246d75ad1403d6eb24ce82c689f00557bc',
)


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def scores(forecast, reference, threshold):
    f, o = forecast >= threshold, reference >= threshold
    h = int(np.count_nonzero(f & o))
    m = int(np.count_nonzero(~f & o))
    a = int(np.count_nonzero(f & ~o))
    d = int(np.count_nonzero(~f & ~o))
    n = h + m + a + d
    random_hits = (h + m) * (h + a) / n if n else 0
    return {'hit': h, 'miss': m, 'false_alarm': a, 'correct_dry': d,
            'CSI': ratio(h, h + m + a), 'ETS': ratio(h - random_hits, h + m + a - random_hits),
            'POD': ratio(h, h + m), 'FAR': ratio(a, h + a), 'frequency_bias': ratio(h + a, h + m)}


def transitions(original, candidate, reference, threshold):
    obs = reference >= threshold
    old, new = original >= threshold, candidate >= threshold
    return {'hit_gains': int(np.count_nonzero(obs & ~old & new)),
            'hit_losses': int(np.count_nonzero(obs & old & ~new)),
            'false_alarm_gains': int(np.count_nonzero(~obs & ~old & new)),
            'false_alarm_losses': int(np.count_nonzero(~obs & old & ~new))}


def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def checked_snapshot(path, expected_time, inventory):
    before = evaluator.identity(path)
    snapshot = evaluator.read_wrf_snapshot(path, expected_time, inventory)
    if evaluator.identity(path) != before:
        raise ValueError(f'history file changed while reading: {path}')
    return snapshot, before


def reference_records(reference_dir, analysis):
    receipt_path = reference_dir / 'mask_receipt.json'
    receipt_record = evaluator.identity(receipt_path)
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if evaluator.identity(receipt_path) != receipt_record:
        raise ValueError('mask receipt changed while reading')
    mask_path = Path(receipt['artifact'])
    if not mask_path.is_absolute():
        mask_path = reference_dir / mask_path
    paths = {'inventory': reference_dir / 'inventory.json', 'mask_receipt': receipt_path,
             'mask': mask_path, 'analysis_coordinates': analysis,
             'run_contract': reference_dir.parent / 'run_contract.md',
             'one_hour_reproduction': reference_dir.parent / 'ONE_HOUR_REPRODUCTION.json'}
    records = {key: evaluator.identity(path) for key, path in paths.items()}
    if records['mask_receipt'] != receipt_record:
        raise ValueError('mask receipt changed before evaluation')
    return records


def verify_records(records):
    for record in records:
        if evaluator.identity(Path(record['path'])) != record:
            raise ValueError(f"input changed during evaluation: {record['path']}")


def transition_rows(values, cases, baseline, additional_baselines, hour):
    rows = []
    for comparison in (baseline, *additional_baselines):
        for name in cases:
            if name == comparison or (comparison != baseline and name == baseline):
                continue
            for threshold in THRESHOLDS:
                rows.append({'lead_hour': hour - 12, 'baseline': comparison, 'candidate': name,
                             'threshold_mm': threshold, **transitions(values[comparison], values[name], values['reference'], threshold)})
    return rows


def run(cases, baseline, reference_dir, analysis, odam_dir, output, additional_baselines=()):
    if baseline not in cases or len(cases) < 2:
        raise ValueError('at least two cases and a baseline case are required')
    if len(set(additional_baselines)) != len(additional_baselines) or any(name not in cases or name == baseline for name in additional_baselines):
        raise ValueError('additional baselines must be distinct cases other than the primary baseline')
    if output.exists() or output.is_symlink():
        raise ValueError(f'output directory already exists: {output}')
    reference_inputs = reference_records(reference_dir, analysis)
    inventory, mask, lat, lon, provenance = evaluator.load_reference(reference_dir, analysis)
    verify_records(reference_inputs.values())
    if int(mask.sum()) != 3688:
        raise ValueError('source-bound mask does not contain 3688 points')
    initial = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
    snapshots, records = {}, {}
    source_lat = source_lon = None
    for name, directory in cases.items():
        snapshots[name], records[name] = {}, []
        for hour in range(12, 19):
            path = directory / f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
            item, record = checked_snapshot(path, initial + timedelta(hours=hour - 12), inventory)
            if source_lat is None:
                source_lat, source_lon = item['lat'], item['lon']
            elif not np.array_equal(source_lat, item['lat']) or not np.array_equal(source_lon, item['lon']):
                raise ValueError(f'grid mismatch: {path}')
            snapshots[name][hour] = item
            records[name].append(record)
    # The archived reset checker uses this module-level list of case names.
    evaluator.CASES = tuple(cases)
    reset_report = evaluator.check_resets(snapshots)
    x0, x1 = inventory['grid']['crop_x_inclusive']
    y0, y1 = inventory['grid']['crop_y_inclusive']
    ys, xs = slice(y0 - 2, y1), slice(x0 - 2, x1)
    mapping = evaluator.build_curvilinear_mapping(source_lat[ys, xs], source_lon[ys, xs], lat, lon, mask)
    cumulative = {}
    for name, hours in snapshots.items():
        cumulative[name] = {}
        for hour, item in hours.items():
            total, valid = evaluator.raw_total(item)
            cumulative[name][hour] = evaluator.remap_field(total[ys, xs], valid[ys, xs], mapping)
    references, rn1_records = {}, []
    for hour, expected_hash in zip(range(13, 19), RN1_HASHES):
        path = odam_dir / f'DFS_VSRT_GRD_KLPS_ODAM_RN1.20260816{hour:02d}00'
        record = evaluator.identity(path)
        if record['sha256'] != expected_hash:
            raise ValueError(f'canonical RN1 hash mismatch: {path}')
        references[hour] = evaluator.read_rn1(path, hour)
        rn1_records.append(record)
    hourly, categorical, continuous, changes = {}, [], [], []
    for hour in range(13, 19):
        ref, ref_valid = references[hour]
        common = mask & mapping['valid'] & ref_valid
        for name in cases:
            common &= cumulative[name][hour - 1][1] & cumulative[name][hour][1]
        if int(common.sum()) != 3688:
            raise ValueError(f'{hour} UTC: expected all 3688 common points, got {common.sum()}')
        values = {'reference': ref[common], 'latitude': lat[common], 'longitude': lon[common],
                  'flat_index_yx': np.flatnonzero(common)}
        for name in cases:
            diff = cumulative[name][hour][0] - cumulative[name][hour - 1][0]
            if np.any(diff[common] < -evaluator.NEGATIVE_TOLERANCE_MM):
                raise ValueError(f'{name} {hour} UTC: negative hourly precipitation')
            values[name] = np.maximum(diff[common], 0.0)
            error = values[name] - values['reference']
            continuous.append({'lead_hour': hour - 12, 'case': name, 'points': len(error),
                               'mean_forecast_mm': float(np.mean(values[name])),
                               'mean_reference_mm': float(np.mean(values['reference'])),
                               'mean_error_mm': float(np.mean(error)), 'MAE_mm': float(np.mean(np.abs(error))),
                               'RMSE_mm': float(np.sqrt(np.mean(error ** 2)))})
            for threshold in THRESHOLDS:
                categorical.append({'lead_hour': hour - 12, 'case': name, 'threshold_mm': threshold,
                                    'points': len(error), **scores(values[name], values['reference'], threshold)})
        changes.extend(transition_rows(values, cases, baseline, additional_baselines, hour))
        hourly[hour] = values
    verify_records([item for entries in records.values() for item in entries] + rn1_records + list(reference_inputs.values()))
    if evaluator.sha256(ARCHIVED) != ARCHIVED_SHA256:
        raise ValueError('archived evaluator changed during evaluation')
    output.mkdir(parents=True, exist_ok=False)
    try:
        for hour, values in hourly.items():
            np.savez_compressed(output / f'hour_{hour}_arrays.npz', **values)
        write_csv(output / 'categorical_scores.csv', categorical)
        write_csv(output / 'continuous_scores.csv', continuous)
        write_csv(output / 'transitions.csv', changes)
        receipt = {'initial_time_utc': '2026-08-16T12:00:00Z', 'cases': list(cases), 'baseline': baseline,
                   'additional_baselines': list(additional_baselines),
                   'hours_utc': list(range(13, 19)), 'points_per_hour': 3688,
                   'thresholds_mm': THRESHOLDS, 'mapping_residual_max_deg': mapping['residual_max_deg'],
                   'model': 'hourly difference of RAINC + RAINNC; RAINSH checked zero',
                   'rainsh_and_bucket_contract_note': 'Historical reference contract is used only as a checker; new history attributes and fields must independently satisfy it.',
                   'reference_limitation': 'RN1 is a processed analysis with no coverage bitmap; per-hour underlying input freshness is not proven and may use previous-hour fallback.',
                   'sources': {'archived_evaluator': evaluator.identity(ARCHIVED), 'reference': reference_inputs, 'rn1': rn1_records, 'wrfout': records},
                   'reset_checks': reset_report}
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', action='append', required=True, metavar='NAME=HISTORY_DIRECTORY')
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--comparison-baseline', action='append', default=[],
                        help='additional case to use as a transition baseline (repeatable)')
    parser.add_argument('--reference-dir', type=Path, required=True)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--odam-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases = {}
    for entry in args.case:
        name, sep, directory = entry.partition('=')
        if not sep or not name.isidentifier() or name in {'reference', 'latitude', 'longitude', 'flat_index_yx'} or name in cases or not directory:
            parser.error(f'invalid or duplicate case: {entry}')
        cases[name] = Path(directory)
    run(cases, args.baseline, args.reference_dir, args.analysis, args.odam_dir, args.output, args.comparison_baseline)


if __name__ == '__main__':
    main()
