#!/usr/bin/env python3
"""Score only fully verified C/D grouped histories into a new cache."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'docs/evidence/cp02_grouped_forecast_20261105'
CANONICAL_SCORER = ROOT / 'docs/evidence/current_forecast_paper_20261029/score_forecasts.py'
CANONICAL_SCORER_SHA256 = '73d4ddd8d6b8c4c6eb7903eff000c2c1e1330a2d50a6692ee7e0eaf77d51d539'
REFERENCE_RECEIPT = ROOT / 'docs/evidence/current_forecast_paper_20261029/scores/receipt.json'
REFERENCE_RECEIPT_SHA256 = '4d6c52bb31d3a8c80732008e3d6eab0599399b7c27f2ce7dff06ae0352a9a961'
GROUPED_EXECUTABLE_SHA256 = '4c01fd93a117a82789f564fd8557d9cab3e85ace23a400acfb84384e48eaf60f'
GROUPED_BUILD_RECEIPT_SHA256 = 'a210478d6a06b393d2687421ccdb6fd13806536b70c4e0ff9feaf3e2af405e92'
INITIAL_INPUT_SHA256 = {
    'A': '9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5',
    'B': 'e6ed0750f88cb36e2600fd38c05e75513e8267dca72d9ee095cd5340a24ed175',
}
HISTORY_NAMES = tuple(f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12, 19))
RUN_TIMES = ('2026-08-16T12:00:00Z', '2026-08-16T18:00:00Z')


def sha256(path: Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(path: Path) -> dict:
    path = Path(path)
    return {'path': str(path), 'sha256': sha256(path), 'size_bytes': path.stat().st_size}


def checked_json(path: Path) -> tuple[dict, dict]:
    record = identity(path)
    value = json.loads(path.read_text(encoding='utf-8'))
    if identity(path) != record:
        raise ValueError(f'file changed while reading: {path}')
    return value, record


def verify_identity(record: dict, label: str) -> Path:
    path = Path(record['path'])
    if not path.is_file() or path.is_symlink():
        raise ValueError(f'{label} is missing or not a regular file: {path}')
    actual = identity(path)
    expected_size = record.get('size_bytes', record.get('size'))
    if actual['sha256'] != record['sha256'] or actual['size_bytes'] != expected_size:
        raise ValueError(f'{label} identity differs: {path}')
    return path


def load_reference_inputs() -> tuple[Path, Path, Path, dict]:
    if sha256(REFERENCE_RECEIPT) != REFERENCE_RECEIPT_SHA256:
        raise ValueError('pinned legacy score receipt changed')
    receipt = json.loads(REFERENCE_RECEIPT.read_text(encoding='utf-8'))
    sources = receipt['sources']
    references = sources['reference']
    if len(sources['rn1']) != 6:
        raise ValueError('legacy score receipt must pin six RN1 files')
    for name, record in references.items():
        verify_identity(record, f'legacy reference {name}')
    for index, record in enumerate(sources['rn1'], start=1):
        verify_identity(record, f'canonical RN1 hour {index}')
    reference_dir = Path(references['inventory']['path']).parent
    analysis = Path(references['analysis_coordinates']['path'])
    odam_dir = Path(sources['rn1'][0]['path']).parent
    return reference_dir, analysis, odam_dir, {
        'legacy_score_receipt': identity(REFERENCE_RECEIPT),
        'reference': references,
        'rn1': sources['rn1'],
    }


def validate_histories(case: str, run_dir: Path, receipt: dict) -> list[dict]:
    if receipt.get('schema') != 'cp02_grouped_six_hour_run_v1' or receipt.get('status') != 'PASS':
        raise ValueError(f'{case} run receipt is not a passing grouped six-hour run')
    if receipt.get('case') != case or receipt.get('variant') != 'GROUPED':
        raise ValueError(f'{case} run case or variant differs')
    arm = 'A' if case == 'C' else 'B'
    if receipt.get('initialization') != arm:
        raise ValueError(f'{case} initialization arm differs')
    if (receipt.get('initial_time_utc'), receipt.get('end_time_utc')) != RUN_TIMES:
        raise ValueError(f'{case} run time interval differs')
    rows = receipt.get('histories')
    if not isinstance(rows, list) or len(rows) != len(HISTORY_NAMES):
        raise ValueError(f'{case} must have exactly seven histories')
    by_name = {}
    for row in rows:
        path = Path(row.get('path', ''))
        if path.name in by_name:
            raise ValueError(f'{case} duplicate history: {path.name}')
        by_name[path.name] = row
    if set(by_name) != set(HISTORY_NAMES):
        raise ValueError(f'{case} must cover every history from 12 through 18 UTC')
    checked = []
    for hour, name in zip(range(12, 19), HISTORY_NAMES):
        row = by_name[name]
        path = Path(row['path'])
        if path.parent.resolve() != run_dir.resolve():
            raise ValueError(f'{case} history is outside its run directory: {path}')
        valid = (datetime(2026, 8, 16, hour, tzinfo=timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')
        if row.get('valid_utc') != valid:
            raise ValueError(f'{case} {name} valid time differs')
        actual = identity(path)
        if actual['sha256'] != row.get('sha256') or actual['size_bytes'] != row.get('size_bytes'):
            raise ValueError(f'{case} {name} identity differs from run receipt')
        checked.append(actual | {'valid_utc': valid})
    return checked


def validate_run(case: str, run_dir: Path) -> dict:
    run_dir = Path(run_dir).resolve()
    run_receipt_path = run_dir / 'run_receipt.json'
    run, run_record = checked_json(run_receipt_path)
    prepared_path = run_dir / 'prepared.json'
    prepared, prepared_record = checked_json(prepared_path)
    if prepared.get('status') != 'PREPARED' or prepared.get('case') != case:
        raise ValueError(f'{case} prepared receipt is missing or mismatched')
    if prepared.get('variant') != 'GROUPED':
        raise ValueError(f'{case} was not prepared with the GROUPED build')
    if prepared.get('initial_time_utc') != RUN_TIMES[0] or prepared.get('end_time_utc') != RUN_TIMES[1]:
        raise ValueError(f'{case} prepared interval differs')
    if run.get('prepared_sha256') != prepared_record['sha256']:
        raise ValueError(f'{case} run receipt does not bind prepared receipt')
    if run.get('runner_sha256') != prepared.get('runner_sha256'):
        raise ValueError(f'{case} runner identity differs from preparation')
    if run.get('inputs_after') != prepared.get('inputs'):
        raise ValueError(f'{case} final runtime inputs differ from prepared inputs')
    source_hashes = prepared.get('source_hashes', {})
    staged_hashes = prepared.get('inputs', {})
    if not source_hashes or set(source_hashes) != set(staged_hashes):
        raise ValueError(f'{case} prepared input inventory is incomplete')
    source_dir = Path(prepared.get('source', ''))
    for name, expected in source_hashes.items():
        source_path = source_dir / name
        runtime_path = run_dir / name
        if not source_path.is_file() or sha256(source_path) != expected:
            raise ValueError(f'{case} frozen source input changed: {name}')
        if not runtime_path.is_file() or sha256(runtime_path) != staged_hashes[name]:
            raise ValueError(f'{case} staged runtime input changed: {name}')
        if name != 'wrf.exe' and staged_hashes[name] != expected:
            raise ValueError(f'{case} non-executable staged input differs from frozen source: {name}')
    arm = 'A' if case == 'C' else 'B'
    input_hash = run.get('inputs_after', {}).get('wrfinput_d01')
    if input_hash != INITIAL_INPUT_SHA256[arm]:
        raise ValueError(f'{case} initial boundary is not the pinned {arm} input')
    build_path = Path(prepared['build_receipt'])
    build, build_record = checked_json(build_path)
    if prepared.get('build_receipt_sha256') != build_record['sha256']:
        raise ValueError(f'{case} prepared build receipt identity differs')
    if build_record['sha256'] != GROUPED_BUILD_RECEIPT_SHA256:
        raise ValueError(f'{case} grouped build receipt is not the pinned build')
    if build.get('status') != 'PASS' or build.get('variant') != 'GROUPED':
        raise ValueError(f'{case} grouped build has not passed')
    executable = build.get('executable', {})
    executable_path = Path(executable.get('path', ''))
    if not executable_path.is_file() or sha256(executable_path) != executable.get('sha256'):
        raise ValueError(f'{case} grouped executable identity differs')
    if executable['sha256'] != GROUPED_EXECUTABLE_SHA256:
        raise ValueError(f'{case} grouped executable is not the pinned build')
    histories = validate_histories(case, run_dir, run)
    return {
        'run_receipt': run_record,
        'prepared_receipt': prepared_record,
        'build_receipt': build_record,
        'executable': identity(executable_path),
        'initial_input_sha256': input_hash,
        'histories': histories,
    }


def load_scorer():
    if sha256(CANONICAL_SCORER) != CANONICAL_SCORER_SHA256:
        raise ValueError('pinned canonical scorer changed')
    spec = importlib.util.spec_from_file_location('cp02_canonical_grouped_scorer', CANONICAL_SCORER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def publish_score_cache(c_run_dir: Path, d_run_dir: Path, output: Path) -> dict:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError(f'refuse to overwrite score cache: {output}')
    c_run = validate_run('C', c_run_dir)
    d_run = validate_run('D', d_run_dir)
    reference_dir, analysis, odam_dir, reference_records = load_reference_inputs()
    scorer = load_scorer()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f'.{output.name}.pending-', dir=output.parent))
    canonical_output = temp / 'canonical'
    try:
        scorer.run({'C': Path(c_run_dir).resolve(), 'D': Path(d_run_dir).resolve()}, 'C',
                   reference_dir, analysis, odam_dir, canonical_output)
        raw_receipt = canonical_output / 'receipt.json'
        raw_bytes = raw_receipt.read_bytes()
        raw = json.loads(raw_bytes)
        if raw.get('cases') != ['C', 'D'] or raw.get('baseline') != 'C':
            raise ValueError('canonical scorer produced an unexpected case contract')
        if raw.get('hours_utc') != list(range(13, 19)) or raw.get('points_per_hour') != 3688:
            raise ValueError('canonical scorer output has incomplete lead or point coverage')
        scored_histories = raw.get('sources', {}).get('wrfout', {})
        for case, validated in (('C', c_run), ('D', d_run)):
            scored = scored_histories.get(case, [])
            expected = validated['histories']
            scored_ids = [(row.get('path'), row.get('sha256'), row.get('size_bytes', row.get('size')))
                          for row in scored]
            expected_ids = [(row.get('path'), row.get('sha256'), row.get('size_bytes', row.get('size')))
                            for row in expected]
            if len(scored) != 7 or scored_ids != expected_ids:
                raise ValueError(f'canonical scorer histories do not match validated {case} run receipt')
        (canonical_output / 'canonical_receipt.json').write_bytes(raw_bytes)
        raw_receipt.unlink()
        files = sorted(path for path in canonical_output.iterdir() if path.is_file())
        required = {f'hour_{hour}_arrays.npz' for hour in range(13, 19)} | {
            'categorical_scores.csv', 'continuous_scores.csv', 'transitions.csv', 'canonical_receipt.json'}
        if {path.name for path in files} != required:
            raise ValueError('canonical scorer output set is incomplete or unexpected')
        outputs = {path.name: identity(path) for path in files}
        for record in outputs.values():
            record.pop('path')
        augmented = dict(raw)
        augmented.update({
            'schema': 'cp02_grouped_score_cache_v1', 'status': 'COMPLETE',
            'canonical_receipt_sha256': hashlib.sha256(raw_bytes).hexdigest(),
            'canonical_scorer': identity(CANONICAL_SCORER),
            'legacy_reference_receipt': reference_records['legacy_score_receipt'],
            'reference_inputs': reference_records,
            'runs': {'C': c_run, 'D': d_run},
            'outputs': outputs,
        })
        (canonical_output / 'receipt.json').write_text(json.dumps(augmented, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        os.replace(canonical_output, output)
        return augmented
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--c-run-dir', type=Path, required=True)
    parser.add_argument('--d-run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    receipt = publish_score_cache(args.c_run_dir, args.d_run_dir, args.output)
    print(f"{receipt['status']}: {args.output}")


if __name__ == '__main__':
    main()
