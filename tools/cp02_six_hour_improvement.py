#!/usr/bin/env python3
"""Fail-closed six-hour scoring for the producer-background WRF forecast."""
import argparse
import csv
import contextlib
import hashlib
import importlib.util
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIR = ROOT / 'docs/evidence/current_forecast_paper_20261029'
SCORER = ARCHIVE_DIR / 'score_forecasts.py'
SCORER_SHA = '73d4ddd8d6b8c4c6eb7903eff000c2c1e1330a2d50a6692ee7e0eaf77d51d539'
ARCHIVED_EVALUATOR_SHA = '1cfa4965155ec273e8e1ca9f963bd79a5ece3bc47beb4ae3db4e8b8f5e21b2c0'
ARCHIVE_RECEIPT = ARCHIVE_DIR / 'scores/receipt.json'
ARCHIVE_RECEIPT_SHA = '4d6c52bb31d3a8c80732008e3d6eab0599399b7c27f2ce7dff06ae0352a9a961'
ARCHIVE_ARRAY_SHA = {
    13: '0df6e55167373751a2a9e50f10325c6d6d1e02603f1225e448c8e766184da9e4',
    14: '1228ba4d4106c151c79bcf01fb2f3a609e91a81bce4833f611da6f726283bf49',
    15: '2495bb333cb7b5b47b6b494e9d7b9ac39d48e224228b1bad06960d448c283711',
    16: '18da1d6c0e061849477030911091cee2c32d4ff7543e3684b11a991260b4c8e4',
    17: '4bf01eb3aecf5e6c7f35188b8110d42ee34c50eb670230b44b77852dc851103b',
    18: '28d298166ce100d0135ee1ce1061372602fe964606768587350d998fa22486d2',
}
ARCHIVE_CSV_SHA = {
    'categorical_scores.csv': 'f746eb6b55bc6ba6510ba27660d6086c4c7a774bcf4ddcc4caec0ccaf8daec77',
    'continuous_scores.csv': '38c7c3fc0bbfafa10d341e816d42159c845f3e2088aefeb083866705007f36bb',
    'transitions.csv': '3f2a29459f3fa7fa92b3212e7a7b174e141b056f272a1cc0e03c41bbfbc020c4',
}
PR135_ARRAYS = ROOT / 'docs/evidence/first_hour_factorial_20261030/analysis/hour_13_arrays.npz'
PR135_ARRAYS_SHA = 'f2f1a0159930527269a2c14594671c36e62a856a99c387feb6e54cdb296798f5'
PR135_RECEIPT = PR135_ARRAYS.parent / 'receipt.json'
PR135_RECEIPT_SHA = '900ee2342a434d418c67d2b86bd5519255fbb555872436ea0e219dd5d23adf56'
FIXED_EXE_SHA = '68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'
POLICY_INPUT_SHA = '9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'
BOUNDARY_SHA = '74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45'
POLICY_SOURCE_DIR = Path('/var/tmp/firsthour-runtime-plan-20261030/producer_pair/forecast/run_POLICY_BG')
RUNTIME_EVIDENCE = ROOT / 'docs/evidence/six_hour_improvement_20261030/runtime'
PREFLIGHT = RUNTIME_EVIDENCE / 'preflight.json'
PREFLIGHT_SHA = '7431b7da24a18ee3f1961d1b2048e2b32c0a4ed8661169c1bb101ec5548f1948'
RUNTIME_RECEIPT_SHA = '75a4efd06097e82980908b0c3abbb06c9cad32133cd7c3f4b4fe94e77e93722b'
ONE_HOUR_COMPARISON = RUNTIME_EVIDENCE / 'one_hour_comparison.json'
ONE_HOUR_COMPARISON_SHA = '805f9409ee932c515f7ad8c9f9c0de0357d9854e58f8de40951bf9c70067d17d'
RUNTIME_SCRIPTS = RUNTIME_EVIDENCE / 'scripts.sha256.json'
RUNTIME_SCRIPTS_SHA = '85916c5385b3f15f8023b92439ed678979f878ec9cf8895f4b5f82df69059747'
RUNTIME_SCRIPT_SHA = {
    'prepare.py': 'e5e528e9b97c35843d9ca2ffe6558171f68cf0905a992dde7b3dd8849a1f8357',
    'run.py': '71a16006fa5963c519c1295f86eee48ff00275aefe9c83a2ba328380390f48e8',
    'env.sh': '0092b662ea29b630f12bba67bafd846bbc4a1addb7a5070e04806c19428d4c40',
    'compare_one_hour.py': '91e6b7cd7f02c04bdfa121edf70f30c1a28b30fcb35524eeb798388d15f9aa22',
}
SCORING_COMMAND = RUNTIME_EVIDENCE / 'scoring_command.json'
SCORING_STDOUT = RUNTIME_EVIDENCE / 'scoring_stdout.txt'
ONE_HOUR_NAMELIST_SHA = '23f5c3cb94d44831c22d86a754fa30d242456d8d14cd70a72d89b00cdec4f3a3'
SIX_HOUR_NAMELIST_SHA = 'eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df'
CASES = ('ORIGINAL', 'CURRENT_HYDRO', 'IMPROVED_BG_FIXED')
ARCHIVED_CASES = ('ORIGINAL', 'CURRENT_OFF', 'CURRENT_HYDRO', 'CURRENT_LIQUID')
HISTORIES = [f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12, 19)]
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
HOURS = tuple(range(13, 19))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def identity(path):
    path = Path(path)
    return {'path': str(path), 'sha256': sha256(path), 'size': path.stat().st_size}


def load_scorer():
    if sha256(SCORER) != SCORER_SHA:
        raise ValueError('pinned six-hour scoring operator changed')
    spec = importlib.util.spec_from_file_location('pinned_six_hour_scorer', SCORER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if sha256(module.ARCHIVED) != ARCHIVED_EVALUATOR_SHA:
        raise ValueError('pinned archived remapping evaluator changed')
    return module


def write_csv(path, rows):
    with Path(path).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def verify_baseline_arrays(arrays):
    """Validate archived keys and paired IDs/coordinates/reference across hours."""
    keys = set(ARCHIVED_CASES) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}
    first = None
    for hour in HOURS:
        data = arrays[hour]
        if set(data) != keys:
            raise ValueError(f'{hour}: unexpected archived array keys')
        if any(np.asarray(value).shape != (3688,) for value in data.values()):
            raise ValueError(f'{hour}: archived array does not have 3688 paired points')
        if any(not np.isfinite(value).all() for value in data.values()):
            raise ValueError(f'{hour}: non-finite archived array')
        if not np.issubdtype(data['flat_index_yx'].dtype, np.integer):
            raise ValueError(f'{hour}: flat IDs must be integers')
        if len(np.unique(data['flat_index_yx'])) != 3688:
            raise ValueError(f'{hour}: duplicate archived flat IDs')
        if first is None:
            first = data
        else:
            for key in ('flat_index_yx', 'latitude', 'longitude'):
                if not np.array_equal(data[key], first[key]):
                    raise ValueError(f'{hour}: archived {key} differs across hours')
    return first


def check_runtime(run_dir, receipt_path, preflight_path=PREFLIGHT):
    """Check the actual fixed executable, candidate input, 89 staged inputs and 7 outputs."""
    run_dir, receipt_path = Path(run_dir), Path(receipt_path)
    inputs_path = run_dir / 'inputs.json'
    if not inputs_path.is_file():
        inputs_path = receipt_path.parent / 'inputs.json'
    inputs = json.loads(inputs_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    preflight_path = Path(preflight_path)
    preflight_record = identity(preflight_path)
    if preflight_record['sha256'] != PREFLIGHT_SHA:
        raise ValueError('pinned six-hour runtime preflight changed')
    preflight = json.loads(preflight_path.read_text())
    if (preflight.get('status') != 'PASS' or preflight.get('case') != 'IMPROVED_BG_FIXED'
        or Path(preflight.get('scratch_directory', '')) != run_dir
        or Path(preflight.get('source_directory', '')) != POLICY_SOURCE_DIR
        or preflight.get('declared_input_count') != 89):
        raise ValueError('six-hour runtime preflight does not bind this run')
    scripts_record = identity(RUNTIME_SCRIPTS)
    if scripts_record['sha256'] != RUNTIME_SCRIPTS_SHA:
        raise ValueError('six-hour runtime script manifest changed')
    scripts_manifest = json.loads(RUNTIME_SCRIPTS.read_text())
    if scripts_manifest != RUNTIME_SCRIPT_SHA:
        raise ValueError('six-hour runtime scripts differ from the pinned launch set')
    script_records = []
    for name, expected_sha in RUNTIME_SCRIPT_SHA.items():
        record = identity(RUNTIME_EVIDENCE / name)
        if record['sha256'] != expected_sha:
            raise ValueError(f'six-hour runtime script changed: {name}')
        script_records.append(record)
    one_hour_record = identity(ONE_HOUR_COMPARISON)
    if one_hour_record['sha256'] != ONE_HOUR_COMPARISON_SHA:
        raise ValueError('pinned one-hour history comparison changed')
    one_hour_check = json.loads(ONE_HOUR_COMPARISON.read_text())
    if (one_hour_check.get('time') != '2026-08-16_13:00:00'
        or one_hour_check.get('current_path') != str(Path(run_dir) / HISTORIES[1])
        or one_hour_check.get('prior_one_hour_path') != str(POLICY_SOURCE_DIR / HISTORIES[1])
        or one_hour_check.get('current_sha256') != one_hour_check.get('prior_one_hour_sha256')
        or one_hour_check.get('whole_file_exact') is not True
        or any(item.get('exact') is not True or item.get('unequal_values', 0) != 0
               for item in one_hour_check.get('fields', {}).values())):
        raise ValueError('one-hour runtime prefix comparison failed')
    success = (receipt.get('exit') == 0 and receipt.get('success_marker') is True
               and receipt.get('histories_exact') is True
               and receipt.get('staged_unchanged', receipt.get('staged_inputs_unchanged')) is True
               and receipt.get('source_unchanged', receipt.get('policy_source_inputs_unchanged')) is True)
    if not success:
        raise ValueError('improved runtime is incomplete or inputs changed')
    if receipt.get('histories') != HISTORIES:
        raise ValueError('improved runtime must contain the exact 12–18 UTC histories')
    if sorted(path.name for path in run_dir.glob('wrfout*')) != HISTORIES:
        raise ValueError('improved runtime history set differs from the receipt')
    staged = inputs.get('staged')
    if not isinstance(staged, dict) or len(staged) != 89:
        raise ValueError('improved runtime must bind all 89 staged inputs')
    if staged.get('wrf.exe') != FIXED_EXE_SHA or staged.get('wrfinput_d01') != POLICY_INPUT_SHA:
        raise ValueError('improved runtime executable or producer input identity mismatch')
    for required in ('wrf.exe', 'wrfinput_d01', 'wrfbdy_d01', 'namelist.input'):
        if required not in staged:
            raise ValueError(f'improved runtime missing pinned configuration input: {required}')
    source_before = inputs.get('source_before', inputs.get('source_policy_bg'))
    source_after = inputs.get('source_after', source_before)
    if not isinstance(source_before, dict) or source_before != source_after:
        raise ValueError('improved runtime source input manifest changed')
    if len(source_before) not in (88, 89):
        raise ValueError('improved runtime source manifest is incomplete')
    receipt_record = identity(receipt_path)
    if receipt_record['sha256'] != RUNTIME_RECEIPT_SHA:
        raise ValueError('frozen six-hour runtime receipt hash mismatch')
    evidence = [receipt_record, identity(inputs_path), preflight_record, scripts_record,
                one_hour_record, *script_records]
    for name, expected_sha in staged.items():
        if Path(name).name != name:
            raise ValueError('unsafe staged input path')
        record = identity(run_dir / name)
        if record['sha256'] != expected_sha:
            raise ValueError(f'staged input hash mismatch: {name}')
        evidence.append(record)
    source_dir = Path(inputs.get('source', inputs.get('source_directory', '')))
    if not str(source_dir):
        raise ValueError('improved runtime source directory is missing')
    for name, expected_sha in source_before.items():
        if Path(name).name != name:
            raise ValueError('unsafe source input path')
        record = identity(source_dir / name)
        if record['sha256'] != expected_sha:
            raise ValueError(f'source input hash mismatch: {name}')
        evidence.append(record)
    if 'source_policy_bg' in inputs:
        expected_namelist_changes = {
            'history_end_s': ['3600', '21600'],
            'run_hours': ['1', '6'],
            'end_hour': ['13', '18'],
        }
        if (inputs.get('case') != 'IMPROVED_BG_FIXED'
            or inputs.get('namelist_changes') != expected_namelist_changes
            or preflight.get('input_changes') != {'namelist.input': expected_namelist_changes}):
            raise ValueError('improved runtime preparation contract mismatch')
        for name, source_sha in source_before.items():
            if name == 'namelist.input':
                continue
            if staged.get(name) != source_sha:
                raise ValueError(f'staged input differs from policy source outside namelist time fields: {name}')
        if (inputs.get('source_directory') != str(POLICY_SOURCE_DIR)
            or inputs.get('wrfbdy_sha256') != BOUNDARY_SHA
            or staged.get('wrfbdy_d01') != BOUNDARY_SHA
            or preflight.get('boundary_sha256') != BOUNDARY_SHA):
            raise ValueError('improved runtime boundary hash differs from preparation receipt')
        if inputs.get('executable_sha256') != FIXED_EXE_SHA or inputs.get('wrfinput_sha256') != POLICY_INPUT_SHA:
            raise ValueError('improved runtime preparation receipt has wrong executable or input')
        if (staged.get('namelist.input') == source_before.get('namelist.input')
            or staged.get('namelist.input') != preflight.get('six_hour_namelist_sha256')
            or staged.get('namelist.input') != SIX_HOUR_NAMELIST_SHA
            or source_before.get('namelist.input') != preflight.get('one_hour_namelist_sha256')
            or source_before.get('namelist.input') != ONE_HOUR_NAMELIST_SHA):
            raise ValueError('six-hour namelist window edits are absent')
        if (preflight.get('staged_sha256') != staged
            or preflight.get('policy_source_sha256_before') != source_before
            or preflight.get('policy_source_sha256_after') != source_before):
            raise ValueError('runtime staged/source manifests differ from sealed preflight')
        evidence_before = preflight.get('existing_evidence_sha256_before')
        if (not isinstance(evidence_before, dict)
            or evidence_before != preflight.get('existing_evidence_sha256_after')):
            raise ValueError('producer/preflight evidence changed during preparation')
        for filename, expected_sha in evidence_before.items():
            record = identity(Path(filename))
            if record['sha256'] != expected_sha:
                raise ValueError(f'producer source evidence hash mismatch: {filename}')
            evidence.append(record)
        if (receipt.get('status') != 'SUCCESS'
            or receipt.get('case') != 'IMPROVED_BG_FIXED'
            or receipt.get('staged_sha256_after') != staged
            or receipt.get('policy_source_sha256_after') != source_before
            or receipt.get('existing_evidence_sha256_after') != evidence_before):
            raise ValueError('raw six-hour runtime receipt does not bind preflight/source postchecks')
    outputs = receipt.get('output_sha256')
    if not isinstance(outputs, dict) or set(outputs) != set(HISTORIES):
        raise ValueError('improved runtime history hashes are incomplete')
    if ('prior_one_hour_history_sha256' in preflight
        and outputs[HISTORIES[1]] != preflight['prior_one_hour_history_sha256']):
        raise ValueError('six-hour 13 UTC history differs from the pinned one-hour POLICY_BG history')
    for name in HISTORIES:
        record = identity(run_dir / name)
        if record['sha256'] != outputs[name]:
            raise ValueError(f'history hash mismatch: {name}')
        evidence.append(record)
    recorded_staged = receipt.get('input_sha256', receipt.get('staged_sha256_after'))
    if recorded_staged is not None and recorded_staged != staged:
        raise ValueError('runtime receipt staged manifest differs from inputs.json')
    if ('source_policy_sha256_after' in receipt
        and receipt['source_policy_sha256_after'] != source_before):
        raise ValueError('runtime receipt source manifest differs from preflight')
    if ('policy_source_sha256_after' in receipt
        and receipt['policy_source_sha256_after'] != source_before):
        raise ValueError('runtime receipt source manifest differs from preflight')
    return evidence


def load_archived_arrays(evidence):
    evidence.append(identity(ARCHIVE_RECEIPT))
    if sha256(ARCHIVE_RECEIPT) != ARCHIVE_RECEIPT_SHA:
        raise ValueError('pinned six-hour archive receipt changed')
    receipt = json.loads(ARCHIVE_RECEIPT.read_text())
    if (receipt.get('cases') != ['ORIGINAL', 'CURRENT_OFF', 'CURRENT_HYDRO', 'CURRENT_LIQUID']
        or receipt.get('hours_utc') != list(HOURS) or receipt.get('points_per_hour') != 3688):
        raise ValueError('archived score receipt does not describe the expected cohort')
    arrays = {}
    for hour, expected_sha in ARCHIVE_ARRAY_SHA.items():
        path = ARCHIVE_DIR / f'scores/hour_{hour}_arrays.npz'
        record = identity(path)
        if record['sha256'] != expected_sha:
            raise ValueError(f'{hour}: pinned archived arrays hash mismatch')
        evidence.append(record)
        with np.load(path, allow_pickle=False) as data:
            arrays[hour] = {key: np.array(data[key]) for key in data.files}
    first = verify_baseline_arrays(arrays)
    for filename, expected_sha in ARCHIVE_CSV_SHA.items():
        path = ARCHIVE_DIR / 'scores' / filename
        record = identity(path)
        if record['sha256'] != expected_sha:
            raise ValueError(f'pinned archived {filename} changed')
        evidence.append(record)
    return arrays, first, receipt


def load_one_hour_policy(evidence):
    for path, expected_sha in ((PR135_ARRAYS, PR135_ARRAYS_SHA),
                               (PR135_RECEIPT, PR135_RECEIPT_SHA)):
        record = identity(path)
        if record['sha256'] != expected_sha:
            raise ValueError(f'pinned PR135 one-hour artifact changed: {path.name}')
        evidence.append(record)
    receipt = json.loads(PR135_RECEIPT.read_text())
    if (receipt.get('status') != 'COMPLETE'
        or receipt.get('factor_levels') != {'H0': 'BASE_H', 'H1': 'FIX_H',
                                             'B0': 'BG_BASE', 'B1': 'POLICY_BG',
                                             'O0': 'BASE_ORIGINAL'}
        or receipt.get('analysis_outputs', {}).get('hour_13_arrays.npz', {}).get('sha256') != PR135_ARRAYS_SHA):
        raise ValueError('PR135 B1 scoring receipt does not match the expected case')
    with np.load(PR135_ARRAYS, allow_pickle=False) as data:
        result = {key: np.array(data[key]) for key in data.files}
    return result


def score_hour(hour, values, scorer):
    categorical, continuous, transitions = [], [], []
    obs = values['reference']
    time_fields = {'lead_hour': hour - 12,
                   'valid_utc': f'2026-08-16T{hour:02d}:00:00Z',
                   'window_start_utc': f'2026-08-16T{hour - 1:02d}:00:00Z',
                   'window_end_utc': f'2026-08-16T{hour:02d}:00:00Z'}
    for name in CASES:
        prediction = values[name]
        error = prediction - obs
        continuous.append({**time_fields, 'case': name, 'points': len(obs),
                           'mean_forecast_mm': float(np.mean(prediction)),
                           'mean_reference_mm': float(np.mean(obs)),
                           'mean_error_mm': float(np.mean(error)),
                           'MAE_mm': float(np.mean(np.abs(error))),
                           'RMSE_mm': float(np.sqrt(np.mean(error ** 2)))})
        for threshold in THRESHOLDS:
            categorical.append({**time_fields, 'case': name,
                                'threshold_mm': threshold, 'points': len(obs),
                                **scorer.scores(prediction, obs, threshold)})
    for baseline in ('ORIGINAL', 'CURRENT_HYDRO'):
        for threshold in THRESHOLDS:
            transitions.append({**time_fields, 'baseline': baseline,
                                'candidate': 'IMPROVED_BG_FIXED', 'threshold_mm': threshold,
                                **scorer.transitions(values[baseline], values['IMPROVED_BG_FIXED'],
                                                     obs, threshold)})
    return categorical, continuous, transitions


def csi_hour_counts(categorical):
    rows = []
    by_hour = {(int(row['lead_hour']), row['case'], float(row['threshold_mm'])): row['CSI']
               for row in categorical}
    for baseline in ('ORIGINAL', 'CURRENT_HYDRO'):
        for threshold in THRESHOLDS:
            improved = tied = worse = 0
            for lead_hour in range(1, 7):
                candidate = by_hour[(lead_hour, 'IMPROVED_BG_FIXED', threshold)]
                control = by_hour[(lead_hour, baseline, threshold)]
                if candidate is None or control is None:
                    raise ValueError('CSI undefined for an evaluated hour and threshold')
                if candidate > control:
                    improved += 1
                elif candidate < control:
                    worse += 1
                else:
                    tied += 1
            rows.append({'baseline': baseline, 'threshold_mm': threshold,
                         'improved_hours': improved, 'tied_hours': tied, 'worse_hours': worse,
                         'hours': 6})
    return rows


def run(run_dir, runtime_receipt, reference_dir, analysis, odam_dir, output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError(f'output directory already exists: {output}')
    scorer = load_scorer()
    command_record = identity(SCORING_COMMAND)
    evidence = [identity(SCORER), identity(scorer.ARCHIVED), command_record]
    evidence.extend(check_runtime(run_dir, runtime_receipt))
    archived, archive_first, archive_receipt = load_archived_arrays(evidence)
    one_hour = load_one_hour_policy(evidence)
    reference_dir, analysis, odam_dir = map(Path, (reference_dir, analysis, odam_dir))
    reference_inputs = scorer.reference_records(reference_dir, analysis)
    evidence.extend(reference_inputs.values())
    evaluator = scorer.evaluator
    inventory, mask, lat, lon, _ = evaluator.load_reference(reference_dir, analysis)
    if int(mask.sum()) != 3688:
        raise ValueError('source-bound mask does not contain 3688 points')
    if not np.array_equal(np.flatnonzero(mask), archive_first['flat_index_yx']):
        raise ValueError('archived paired flat IDs differ from source-bound RN1 mask')

    snapshots, history_records = {}, []
    source_lat = source_lon = None
    initial = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
    for hour in range(12, 19):
        path = Path(run_dir) / f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
        snapshot, record = scorer.checked_snapshot(path, initial + timedelta(hours=hour - 12), inventory)
        history_records.append(record)
        if source_lat is None:
            source_lat, source_lon = snapshot['lat'], snapshot['lon']
        elif not np.array_equal(source_lat, snapshot['lat']) or not np.array_equal(source_lon, snapshot['lon']):
            raise ValueError(f'improved runtime grid changed: {path}')
        snapshots[hour] = snapshot
    evaluator.CASES = ('IMPROVED_BG_FIXED',)
    reset_report = evaluator.check_resets({'IMPROVED_BG_FIXED': snapshots})
    x0, x1 = inventory['grid']['crop_x_inclusive']
    y0, y1 = inventory['grid']['crop_y_inclusive']
    ys, xs = slice(y0 - 2, y1), slice(x0 - 2, x1)
    mapping = evaluator.build_curvilinear_mapping(source_lat[ys, xs], source_lon[ys, xs], lat, lon, mask)
    cumulative = {}
    for hour, snapshot in snapshots.items():
        total, valid = evaluator.raw_total(snapshot)
        cumulative[hour] = evaluator.remap_field(total[ys, xs], valid[ys, xs], mapping)

    references, rn1_records = {}, []
    for hour, expected_sha in zip(HOURS, scorer.RN1_HASHES, strict=True):
        path = odam_dir / f'DFS_VSRT_GRD_KLPS_ODAM_RN1.20260816{hour:02d}00'
        record = identity(path)
        if record['sha256'] != expected_sha:
            raise ValueError(f'{hour}: canonical RN1 SHA-256 mismatch')
        references[hour] = evaluator.read_rn1(path, hour)
        rn1_records.append(record)

    arrays, categorical, continuous, transitions = {}, [], [], []
    first_hour_max_abs_diff = None
    for hour in HOURS:
        reference, reference_valid = references[hour]
        common = mask & mapping['valid'] & reference_valid
        common &= cumulative[hour - 1][1] & cumulative[hour][1]
        if int(common.sum()) != 3688:
            raise ValueError(f'{hour}: expected 3688 common points; got {common.sum()}')
        values = {key: np.array(archived[hour][key]) for key in CASES[:2]}
        values.update(reference=reference[common], latitude=lat[common], longitude=lon[common],
                      flat_index_yx=np.flatnonzero(common))
        for key in ('flat_index_yx', 'latitude', 'longitude', 'reference'):
            if not np.array_equal(values[key], archived[hour][key]):
                raise ValueError(f'{hour}: candidate paired {key} differs from pinned archive')
        diff = cumulative[hour][0] - cumulative[hour - 1][0]
        if np.any(diff[common] < -evaluator.NEGATIVE_TOLERANCE_MM):
            raise ValueError(f'{hour}: negative accumulated hourly precipitation')
        values['IMPROVED_BG_FIXED'] = np.maximum(diff[common], 0.0)
        if hour == 13:
            first_hour_max_abs_diff = float(np.max(np.abs(
                values['IMPROVED_BG_FIXED'] - one_hour['POLICY_BG'])))
            if not np.array_equal(values['IMPROVED_BG_FIXED'], one_hour['POLICY_BG']):
                raise ValueError('six-hour forecast first hour differs from PR135 POLICY_BG values')
            for key in ('reference', 'latitude', 'longitude', 'flat_index_yx'):
                if not np.array_equal(values[key], one_hour[key]):
                    raise ValueError(f'six-hour first-hour {key} differs from PR135 arrays')
        c_rows, u_rows, t_rows = score_hour(hour, values, scorer)
        categorical.extend(c_rows); continuous.extend(u_rows); transitions.extend(t_rows)
        arrays[hour] = values

    scorer.verify_records(evidence + history_records + rn1_records + list(reference_inputs.values()))
    if sha256(SCORER) != SCORER_SHA or sha256(scorer.ARCHIVED) != ARCHIVED_EVALUATOR_SHA:
        raise ValueError('scoring operator changed during evaluation')
    output.mkdir(parents=True, exist_ok=False)
    try:
        for hour, values in arrays.items():
            np.savez_compressed(output / f'hour_{hour}_arrays.npz', **values)
        write_csv(output / 'categorical_scores.csv', categorical)
        write_csv(output / 'continuous_scores.csv', continuous)
        write_csv(output / 'transitions.csv', transitions)
        output_hashes = {}
        for path in sorted(output.iterdir()):
            output_hashes[path.name] = {'sha256': sha256(path), 'size_bytes': path.stat().st_size}
        receipt = {
            'status': 'COMPLETE', 'cases': list(CASES), 'baseline_comparisons': ['ORIGINAL', 'CURRENT_HYDRO'],
            'hours_utc': list(HOURS), 'points_per_hour': 3688, 'thresholds_mm': list(THRESHOLDS),
            'row_counts': {'categorical': len(categorical), 'continuous': len(continuous),
                           'transitions': len(transitions)},
            'model': 'Hourly difference of RAINC + RAINNC; RAINSH checked zero, using the pinned archived bilinear operator.',
            'time_windows_utc': [{'lead_hour': hour - 12,
                                  'start': f'2026-08-16T{hour - 1:02d}:00:00Z',
                                  'end': f'2026-08-16T{hour:02d}:00:00Z',
                                  'valid_time': f'2026-08-16T{hour:02d}:00:00Z'}
                                 for hour in HOURS],
            'precipitation_window': 'One-hour increment between consecutive WRF histories; not a 0–lead accumulation.',
            'units': {'precipitation': 'mm per one-hour window',
                      'continuous_scores': 'mm per one-hour window', 'thresholds': 'mm per one-hour window'},
            'csi_hour_counts': csi_hour_counts(categorical),
            'first_hour_replay': {'case': 'IMPROVED_BG_FIXED', 'matched_PR135_POLICY_BG': True,
                                  'max_abs_difference_mm': first_hour_max_abs_diff,
                                  'array_sha256': PR135_ARRAYS_SHA},
            'comparison_scope': 'IMPROVED_BG_FIXED is compared with archived ORIGINAL and CURRENT_HYDRO six-hour arrays; these are combined model-version and initialization contrasts, not isolated causal effects of the new background.',
            'mapping_residual_max_deg': mapping['residual_max_deg'],
            'reset_checks': reset_report,
            'reference_limitation': 'RN1 processed analysis has no coverage bitmap; per-hour input freshness is unproven and may use previous-hour fallback. Scores are unweighted over the common 3688 points.',
            'runtime_receipt': identity(runtime_receipt),
            'sources': evidence + history_records + rn1_records + list(reference_inputs.values()),
            'analysis_outputs': output_hashes,
        }
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--runtime-receipt', type=Path, required=True)
    parser.add_argument('--reference-dir', type=Path, required=True)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--odam-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    command = {
        'argv': [str(Path(__file__).resolve()), '--run-dir', str(args.run_dir),
                 '--runtime-receipt', str(args.runtime_receipt),
                 '--reference-dir', str(args.reference_dir), '--analysis', str(args.analysis),
                 '--odam-dir', str(args.odam_dir), '--output', str(args.output)],
        'cwd': str(Path.cwd()), 'scoring_tool_sha256': sha256(Path(__file__)),
    }
    encoded = json.dumps(command, indent=2) + '\n'
    if SCORING_COMMAND.exists():
        if SCORING_COMMAND.read_text() != encoded:
            raise FileExistsError(f'refusing to replace scoring command record {SCORING_COMMAND}')
    else:
        SCORING_COMMAND.write_text(encoded, encoding='utf-8')
    with SCORING_STDOUT.open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log):
        run(args.run_dir, args.runtime_receipt, args.reference_dir, args.analysis, args.odam_dir, args.output)
        result = json.loads((args.output / 'receipt.json').read_text())
        print(json.dumps({'status': result['status'], 'row_counts': result['row_counts'],
                          'analysis_outputs': result['analysis_outputs']}, indent=2))
    result['reproduction'] = {'command': identity(SCORING_COMMAND),
                              'stdout_log': identity(SCORING_STDOUT)}
    (args.output / 'receipt.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
