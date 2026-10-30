#!/usr/bin/env python3
"""Fail-closed 2x2 first-hour WRF rainfall factorial scoring."""
import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OLD_SCRIPT = ROOT / 'docs/evidence/first_hour_zero_rate_20261030/scoring/score_first_hour.py'
OLD_SHA = '992f38bf7209eb94ee196e76e7383343a8d61872832dc605c7ea18e4bc38333c'
COMPONENT_SCRIPT = ROOT / 'docs/evidence/first_hour_background_policy_20261030/scoring/score_components.py'
COMPONENT_SHA = '48976426853745b703d497916355ec053b3ee14590d6cbf0bec071a4c9f8b26c'
PRODUCER_GATE = ROOT / 'docs/evidence/first_hour_background_policy_20261030/scoring/producer_gate.py'
PRODUCER_GATE_SHA = 'aa96a45eea76baf4f4d26238c170db7e250aaf42d8db5772a050e1b7aba460d6'
ARCHIVE = ROOT / 'docs/evidence/current_forecast_paper_20261029'
ARCHIVE_NPZ_SHA = '0df6e55167373751a2a9e50f10325c6d6d1e02603f1225e448c8e766184da9e4'
PRIOR_NPZ = ROOT / 'docs/evidence/first_hour_zero_rate_20261030/scoring/results/hour_13_arrays.npz'
PRIOR_NPZ_SHA = 'c2f7f449f265b545e88a20bcb024e7944058d34b8f31061a6281cde364281d87'
BASE_EXE_SHA = 'de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168'
FIX_EXE_SHA = '68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'
HYDRO_INPUT_SHA = '7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126'
POLICY_INPUT_SHA = '9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'
ORIGINAL_INPUT_SHA = '5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc'
HISTORIES = [f'wrfout_d01_2026-08-16_{h}:00:00' for h in (12, 13)]
CELLS = ('BASE_H', 'FIX_H', 'BG_BASE', 'POLICY_BG', 'BASE_ORIGINAL')
FACTORS = {
    'BASE_H': ('H0', BASE_EXE_SHA, HYDRO_INPUT_SHA),
    'FIX_H': ('H1', FIX_EXE_SHA, HYDRO_INPUT_SHA),
    'BG_BASE': ('B0', BASE_EXE_SHA, POLICY_INPUT_SHA),
    'POLICY_BG': ('B1', FIX_EXE_SHA, POLICY_INPUT_SHA),
    'BASE_ORIGINAL': ('O0', BASE_EXE_SHA, ORIGINAL_INPUT_SHA),
}
FACTORIAL_CONTRASTS = (
    ('guard_H1_minus_H0', 'BASE_H', 'FIX_H'),
    ('guard_B1_minus_B0', 'BG_BASE', 'POLICY_BG'),
    ('policy_B0_minus_H0', 'BASE_H', 'BG_BASE'),
    ('policy_B1_minus_H1', 'FIX_H', 'POLICY_BG'),
    ('BASE_H_to_BASE_ORIGINAL', 'BASE_H', 'BASE_ORIGINAL'),
    ('FIX_H_to_BASE_ORIGINAL', 'FIX_H', 'BASE_ORIGINAL'),
    ('BG_BASE_to_BASE_ORIGINAL', 'BG_BASE', 'BASE_ORIGINAL'),
    ('POLICY_BG_to_BASE_ORIGINAL', 'POLICY_BG', 'BASE_ORIGINAL'),
)


def load_module(path, expected_sha, name):
    import hashlib
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
        raise ValueError(f'pinned scoring helper changed: {path}')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def checked_run(name, directory, evaluator):
    """Verify complete staged/source manifests and both immutable histories."""
    receipt_path, inputs_path = directory / 'receipt.json', directory / 'inputs.json'
    receipt = json.loads(receipt_path.read_text())
    inputs = json.loads(inputs_path.read_text())
    records = [evaluator.identity(receipt_path), evaluator.identity(inputs_path)]
    if (receipt.get('exit') != 0
        or any(receipt.get(key) is not True for key in
               ('success_marker', 'histories_exact', 'staged_unchanged', 'source_unchanged'))
        or receipt.get('histories') != HISTORIES
        or sorted(path.name for path in directory.glob('wrfout*')) != HISTORIES):
        raise ValueError(f'{name}: runtime is not complete')
    staged = inputs.get('staged')
    before, after = inputs.get('source_before'), inputs.get('source_after')
    is_bg_base = name == 'BG_BASE'
    source_manifest = inputs.get('source_policy_bg') if is_bg_base else before
    if (not isinstance(staged, dict) or len(staged) != 89
        or not isinstance(source_manifest, dict)
        or (is_bg_base and len(source_manifest) != 89)
        or (not is_bg_base and (len(before) not in (88, 89) or before != after))
        or set(receipt.get('output_sha256', {})) != set(HISTORIES)):
        raise ValueError(f'{name}: input or history manifest is incomplete')
    for filename, digest in staged.items():
        if Path(filename).name != filename:
            raise ValueError(f'{name}: invalid staged filename')
        record = evaluator.identity(directory / filename)
        if record['sha256'] != digest:
            raise ValueError(f'{name}: staged input changed: {filename}')
        records.append(record)
    source_value = inputs.get('policy_source_directory') if is_bg_base else inputs.get('source', inputs.get('reference_case'))
    if not source_value:
        raise ValueError(f'{name}: source input directory is missing')
    source = Path(source_value)
    for filename, digest in source_manifest.items():
        if Path(filename).name != filename:
            raise ValueError(f'{name}: invalid source filename')
        record = evaluator.identity(source / filename)
        if record['sha256'] != digest:
            raise ValueError(f'{name}: source input changed: {filename}')
        records.append(record)
    expected_history_hashes = receipt['output_sha256']
    for filename in HISTORIES:
        record = evaluator.identity(directory / filename)
        if record['sha256'] != expected_history_hashes[filename]:
            raise ValueError(f'{name}: history hash mismatch: {filename}')
        records.append(record)
    if is_bg_base:
        if (receipt.get('staged_sha256') != staged
            or receipt.get('source_before') != source_manifest
            or receipt.get('source_after') != source_manifest):
            raise ValueError('BG_BASE: normalized postrun manifests differ from preflight')
        raw_path = Path(receipt['raw_evidence_receipt'])
        raw_record = evaluator.identity(raw_path)
        if raw_record['sha256'] != receipt.get('raw_evidence_receipt_sha256'):
            raise ValueError('BG_BASE: raw runtime receipt hash mismatch')
        copied_raw = directory / 'raw_receipt.json'
        if evaluator.identity(copied_raw)['sha256'] != raw_record['sha256']:
            raise ValueError('BG_BASE: copied raw runtime receipt differs')
        records.extend((raw_record, evaluator.identity(copied_raw)))
    evidence_before = inputs.get('evidence_before', {})
    if is_bg_base:
        if (inputs.get('factorial_cell') != 'H0xB1 (original executable x policy input)'
            or inputs.get('candidate_native_input') != POLICY_INPUT_SHA
            or inputs.get('original_executable') != BASE_EXE_SHA):
            raise ValueError('BG_BASE: original executable or producer input binding mismatch')
        executable = evaluator.identity(Path(inputs['original_executable_path']))
        if executable['sha256'] != BASE_EXE_SHA:
            raise ValueError('BG_BASE: original executable artifact mismatch')
        records.append(executable)
    if evidence_before:
        if receipt.get('evidence_unchanged') is not True or receipt.get('evidence_before') != evidence_before:
            raise ValueError(f'{name}: producer evidence changed')
        for filename, digest in evidence_before.items():
            record = evaluator.identity(Path(filename))
            if record['sha256'] != digest:
                raise ValueError(f'{name}: producer evidence hash mismatch')
            records.append(record)
    return staged, records


def verify_factorial_inputs(staged):
    for name, (_, expected_exe, expected_input) in FACTORS.items():
        if staged[name].get('wrf.exe') != expected_exe:
            raise ValueError(f'{name}: unexpected executable identity')
        if staged[name].get('wrfinput_d01') != expected_input:
            raise ValueError(f'{name}: unexpected initial input identity')
    for baseline, candidate in (('BASE_H', 'FIX_H'), ('BG_BASE', 'POLICY_BG')):
        if {key: value for key, value in staged[baseline].items() if key != 'wrf.exe'} != {
                key: value for key, value in staged[candidate].items() if key != 'wrf.exe'}:
            raise ValueError(f'{baseline}/{candidate}: staged inputs differ outside wrf.exe')
    for baseline, candidate in (('BASE_H', 'BG_BASE'), ('FIX_H', 'POLICY_BG')):
        left = {key: value for key, value in staged[baseline].items() if key != 'wrfinput_d01'}
        right = {key: value for key, value in staged[candidate].items() if key != 'wrfinput_d01'}
        if left != right:
            raise ValueError(f'{baseline}/{candidate}: staged inputs differ outside wrfinput_d01')
    if ({key: value for key, value in staged['BASE_H'].items() if key != 'wrfinput_d01'}
        != {key: value for key, value in staged['BASE_ORIGINAL'].items() if key != 'wrfinput_d01'}):
        raise ValueError('BASE_H/BASE_ORIGINAL: staged inputs differ outside wrfinput_d01')


def verify_paired_reference(mask, latitude, longitude, reference, prior):
    if (int(mask.sum()) != 3688
        or not np.array_equal(np.flatnonzero(mask), prior['flat_index_yx'])
        or not np.array_equal(latitude[mask], prior['latitude'])
        or not np.array_equal(longitude[mask], prior['longitude'])
        or not np.array_equal(reference[mask], prior['reference'])):
        raise ValueError('RN1, spatial mask, or flat IDs differ from pinned paired arrays')


def score_rows(values, scorer):
    categorical, continuous, transitions = [], [], []
    for name in CELLS:
        field = values[name]
        error = field - values['reference']
        continuous.append({
            'case': name, 'points': len(error),
            'mean_forecast_mm': float(np.mean(field)),
            'mean_reference_mm': float(np.mean(values['reference'])),
            'mean_error_mm': float(np.mean(error)),
            'MAE_mm': float(np.mean(np.abs(error))),
            'RMSE_mm': float(np.sqrt(np.mean(error ** 2))),
        })
        categorical.extend(
            {'case': name, 'threshold_mm': threshold, 'points': len(error),
             **scorer.scores(field, values['reference'], threshold)}
            for threshold in scorer.THRESHOLDS)
    for label, baseline, candidate in FACTORIAL_CONTRASTS:
        transitions.extend(
            {'contrast': label, 'baseline': baseline, 'candidate': candidate,
             'threshold_mm': threshold,
             **scorer.transitions(values[baseline], values[candidate], values['reference'], threshold)}
            for threshold in scorer.THRESHOLDS)
    return categorical, continuous, transitions


def contrast_rows(continuous):
    by_case = {row['case']: row for row in continuous}
    rows = []
    for metric in ('MAE_mm', 'RMSE_mm', 'mean_error_mm', 'mean_forecast_mm'):
        for label, baseline, candidate in FACTORIAL_CONTRASTS:
            rows.append({'metric': metric, 'threshold_mm': '', 'contrast': label,
                         'difference': by_case[candidate][metric] - by_case[baseline][metric],
                         'interpretation': 'paired score difference; not a physical causal share'})
        rows.append({'metric': metric, 'contrast': 'interaction_(B1-B0)-(H1-H0)',
                     'threshold_mm': '',
                     'difference': (by_case['POLICY_BG'][metric] - by_case['BG_BASE'][metric])
                                   - (by_case['FIX_H'][metric] - by_case['BASE_H'][metric]),
                     'interpretation': 'difference-in-differences of a score; not a physical causal share'})
    return rows


def categorical_contrast_rows(categorical):
    by_cell_threshold = {(row['case'], row['threshold_mm']): row for row in categorical}
    rows = []
    for threshold in sorted({row['threshold_mm'] for row in categorical}):
        for metric in ('CSI', 'ETS', 'POD', 'FAR', 'frequency_bias'):
            cell = lambda name: by_cell_threshold[(name, threshold)][metric]
            for label, baseline, candidate in FACTORIAL_CONTRASTS:
                old, new = cell(baseline), cell(candidate)
                rows.append({'metric': metric, 'threshold_mm': threshold, 'contrast': label,
                             'difference': None if old is None or new is None else new - old,
                             'interpretation': 'paired score difference; nonlinear metric contrasts are not physical causal shares'})
            corners = [cell(name) for name in ('BASE_H', 'FIX_H', 'BG_BASE', 'POLICY_BG')]
            difference = None if any(value is None for value in corners) else (corners[3] - corners[2]) - (corners[1] - corners[0])
            rows.append({'metric': metric, 'threshold_mm': threshold,
                         'contrast': 'interaction_(B1-B0)-(H1-H0)', 'difference': difference,
                         'interpretation': 'difference-in-differences of a nonlinear score; not a physical causal share'})
    return rows


def run(cases, reference_dir, analysis, odam_dir, output):
    if set(cases) != set(CELLS):
        raise ValueError('all five named cases are required')
    if output.exists() or output.is_symlink():
        raise ValueError('output already exists')
    old = load_module(OLD_SCRIPT, OLD_SHA, 'first_hour_scorer')
    components = load_module(COMPONENT_SCRIPT, COMPONENT_SHA, 'factorial_score_components')
    scorer = old.load_scorer()
    ev = scorer.evaluator
    records = [ev.identity(OLD_SCRIPT), ev.identity(COMPONENT_SCRIPT)]
    staged = {}
    for name in CELLS:
        staged[name], checked = checked_run(name, cases[name], ev)
        records.extend(checked)
    verify_factorial_inputs(staged)
    policy_inputs = json.loads((cases['POLICY_BG'] / 'inputs.json').read_text())
    policy_receipt = json.loads((cases['POLICY_BG'] / 'receipt.json').read_text())
    if (policy_inputs.get('input_count') != 89
        or policy_inputs.get('candidate_native_input') != str(
            Path('/var/tmp/firsthour-runtime-plan-20261030/producer_pair/native_HYDRO_BACKGROUND_PRECIP/real/wrfinput_d01'))
        or policy_receipt.get('policy') != 'HYDRO_BACKGROUND_PRECIP'):
        raise ValueError('POLICY_BG: candidate producer/native input binding mismatch')
    gate = load_module(PRODUCER_GATE, PRODUCER_GATE_SHA, 'factorial_producer_gate')
    for filename, digest in gate.validate().items():
        record = ev.identity(Path(filename))
        if record['sha256'] != digest:
            raise ValueError('POLICY_BG: producer/native source provenance changed')
        records.append(record)
    records.append(ev.identity(PRODUCER_GATE))

    prior_record = ev.identity(PRIOR_NPZ)
    archive_npz = ARCHIVE / 'scores/hour_13_arrays.npz'
    archive_record = ev.identity(archive_npz)
    if prior_record['sha256'] != PRIOR_NPZ_SHA or archive_record['sha256'] != ARCHIVE_NPZ_SHA:
        raise ValueError('pinned paired reference arrays changed')
    records.extend((prior_record, archive_record))
    with np.load(PRIOR_NPZ, allow_pickle=False) as source:
        prior = {key: np.array(source[key]) for key in
                 ('reference', 'latitude', 'longitude', 'flat_index_yx', 'FIX_H', 'FIX_ORIGINAL')}
    with np.load(archive_npz, allow_pickle=False) as source:
        archived = {key: np.array(source[key]) for key in
                    ('reference', 'latitude', 'longitude', 'flat_index_yx', 'ORIGINAL')}
    for key in ('reference', 'latitude', 'longitude', 'flat_index_yx'):
        if not np.array_equal(prior[key], archived[key]):
            raise ValueError('independently pinned paired reference arrays differ')

    ref_records = scorer.reference_records(reference_dir, analysis)
    records.extend(ref_records.values())
    inventory, mask, lat, lon, _ = ev.load_reference(reference_dir, analysis)
    rn1 = odam_dir / 'DFS_VSRT_GRD_KLPS_ODAM_RN1.202608161300'
    rn1_record = ev.identity(rn1)
    if rn1_record['sha256'] != old.RN1_SHA:
        raise ValueError('canonical RN1 hash mismatch')
    records.append(rn1_record)
    reference, valid = ev.read_rn1(rn1, 13)
    if not valid[mask].all():
        raise ValueError('RN1 reference is incomplete on the paired mask')
    verify_paired_reference(mask, lat, lon, reference, prior)

    values = {'reference': prior['reference']}
    remapped = {}
    for name in CELLS:
        result = components.remap_one_hour(cases[name], inventory, mask, lat, lon, scorer)
        for identity in result['history_identities']:
            if identity['sha256'] != next(
                record['sha256'] for record in records if record['path'] == identity['path']):
                raise ValueError(f'{name}: history changed while scoring')
        remapped[name] = result
        values[name] = result['values']
    for name in CELLS[1:]:
        if (not np.array_equal(remapped['BASE_H']['latitude'], remapped[name]['latitude'])
            or not np.array_equal(remapped['BASE_H']['longitude'], remapped[name]['longitude'])):
            raise ValueError(f'{name}: forecast grid differs')
    for name, baseline in (('FIX_H', prior['FIX_H']),
                           ('BASE_ORIGINAL', archived['ORIGINAL'])):
        if not np.array_equal(values[name], baseline):
            raise ValueError(f'{name}: forecast differs from independently pinned baseline array')

    categorical, continuous, transitions = score_rows(values, scorer)
    pointwise = []
    for label, baseline, candidate in FACTORIAL_CONTRASTS:
        delta = values[candidate] - values[baseline]
        pointwise.extend({'contrast': label, 'flat_index_yx': int(index),
                          'precipitation_difference_mm': float(value)}
                         for index, value in zip(prior['flat_index_yx'], delta, strict=True))
    interaction = ((values['POLICY_BG'] - values['BG_BASE'])
                   - (values['FIX_H'] - values['BASE_H']))
    pointwise.extend({'contrast': 'interaction_(B1-B0)-(H1-H0)',
                      'flat_index_yx': int(index), 'precipitation_difference_mm': float(value)}
                     for index, value in zip(prior['flat_index_yx'], interaction, strict=True))
    contrast_summary = contrast_rows(continuous) + categorical_contrast_rows(categorical)
    scorer.verify_records(records)
    output.mkdir(parents=True, exist_ok=False)
    try:
        np.savez_compressed(output / 'hour_13_arrays.npz', **values,
                            latitude=prior['latitude'], longitude=prior['longitude'],
                            flat_index_yx=prior['flat_index_yx'])
        scorer.write_csv(output / 'categorical_scores.csv', categorical)
        scorer.write_csv(output / 'continuous_scores.csv', continuous)
        scorer.write_csv(output / 'transitions.csv', transitions)
        scorer.write_csv(output / 'score_contrasts.csv', contrast_summary)
        scorer.write_csv(output / 'pointwise_precipitation_contrasts.csv', pointwise)
        import hashlib
        output_names = ('hour_13_arrays.npz', 'categorical_scores.csv', 'continuous_scores.csv',
                        'transitions.csv', 'score_contrasts.csv', 'pointwise_precipitation_contrasts.csv')
        analysis_outputs = {}
        for filename in output_names:
            path = output / filename
            analysis_outputs[filename] = {
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'size_bytes': path.stat().st_size,
            }
        receipt = {
            'status': 'COMPLETE', 'points': 3688, 'cases': list(CELLS),
            'factor_levels': {'H0': 'BASE_H', 'H1': 'FIX_H', 'B0': 'BG_BASE',
                              'B1': 'POLICY_BG', 'O0': 'BASE_ORIGINAL'},
            'factorial_contrasts': [label for label, _, _ in FACTORIAL_CONTRASTS],
            'interaction': '(POLICY_BG-BG_BASE)-(FIX_H-BASE_H)',
            'interaction_interpretation': 'difference-in-differences of nonlinear precipitation scores, not physical causal shares',
            'thresholds_mm': list(scorer.THRESHOLDS),
            'reset_checks': {name: result['reset'] for name, result in remapped.items()},
            'mapping_residual_max_deg': {name: result['mapping_residual_max_deg'] for name, result in remapped.items()},
            'sources': records,
            'analysis_outputs': analysis_outputs,
            'limitation': 'One forecast hour and one event. RN1 processed analysis has no coverage bitmap and may use previous-hour fallback; unweighted scores cover the retained 3688 point common sample.',
        }
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
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
    args = parser.parse_args()
    cases = {}
    for entry in args.case:
        name, sep, directory = entry.partition('=')
        if not sep or name not in CELLS or name in cases or not directory:
            parser.error(f'invalid case: {entry}')
        cases[name] = Path(directory)
    run(cases, args.reference_dir, args.analysis, args.odam_dir, args.output)


if __name__ == '__main__':
    main()
