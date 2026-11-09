#!/usr/bin/env python3
"""Seal completed sedimentation diagnostics, forecast evaluation and reviewed evidence."""
import hashlib
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_sedimentation_conservation_20261109'
SOURCES = ('tools/cp02_sedimentation_conservation.py', 'tools/cp02_sedimentation_focus.py',
           'tests/test_cp02_sedimentation_conservation.py', 'tests/test_cp02_sedimentation_raw_audit.py',
           'tests/test_cp02_sedimentation_focus.py')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(name, status=None):
    path = BUNDLE / name
    require(path.is_file() and not path.is_symlink(), f'missing/unsafe receipt: {name}')
    result = json.loads(path.read_text())
    require(status is None or result.get('status') == status, f'receipt status differs: {name}')
    return result


def binding(name, expected):
    path = Path(name)
    require(not path.is_absolute() and '..' not in path.parts, f'unsafe artifact path: {name}')
    path = ROOT / path
    require(path.is_file() and not path.is_symlink() and sha(path) == expected,
            f'reviewed artifact changed: {name}')


def verify():
    clean = read('validation/clean_export.json', 'PASS')
    require(clean.get('passed') == clean.get('expected_tests') == 474
            and clean.get('exit_code') == 0 and clean.get('source_inputs_unchanged') is True,
            'related 474-test validation must pass')
    guarded = clean['guarded_source_input_sha256']
    require(set(SOURCES) <= set(guarded), 'related suite lacks one of the five maintained sources')
    for name, expected in guarded.items():
        binding(name, expected)
    for name in ('review/final_science_report_review.json', 'review/final_figure_gallery_review.json'):
        review = read(name)
        require(review['status'] in ('PASS', 'PASS_FINAL_REPORT_SCIENCE_REVIEW'), 'final review is not GO')
        pins = review.get('reviewed_artifacts', review.get('bound_artifacts', {}))
        require(bool(pins), 'final review lacks artifact identities')
        for path, expected in pins.items():
            if name.endswith('final_figure_gallery_review.json'):
                path = str((BUNDLE / path).relative_to(ROOT))
            binding(path, expected)
    raw = read('audit/full/receipt.json', 'PASS')
    require(raw['executed_tool_sha256'] == sha(ROOT / SOURCES[0]), 'raw audit tool changed after execution')
    require(set(raw['arms']) == {'OLD', 'FIX'}, 'full audit requires both arms')
    for arm, record in raw['arms'].items():
        for name, identity in record['files'].items():
            path = BUNDLE / 'audit/full' / arm / name
            binding(str(path.relative_to(ROOT)), identity['sha256'])
            if 'decoded_sha256' in identity:
                with gzip.open(path, 'rb') as stream:
                    require(hashlib.file_digest(stream, 'sha256').hexdigest() == identity['decoded_sha256'],
                            f'decoded full audit table differs: {path}')
    compare = read('forecast/proof/comparability.json', 'PASS')
    require(compare['plan']['sha256'] == sha(BUNDLE / 'forecast/launch_plan.json'), 'forecast plan identity differs')
    plan = read('forecast/launch_plan.json', 'FROZEN_CONTROLLED_SIX_HOUR_PLAN')
    for name, expected in plan['source_sha256'].items():
        binding(name, expected)
    score = read('evaluation/results/receipt.json', 'COMPLETE')
    require(score['rows'] == {'categorical': 108, 'continuous': 18, 'constraints': 26, 'transitions': 48},
            'evaluation table coverage differs')
    require(score['scorer']['sha256'] == sha(BUNDLE / 'evaluation/evaluate.py'), 'scorer changed after evaluation')
    for name, expected in score['outputs'].items():
        binding(str((BUNDLE / 'evaluation/results' / name).relative_to(ROOT)), expected)
    verdict = read('evaluation/results/verdict.json')
    require(verdict['passed_constraints'] == 19 and verdict['required_constraints'] == 26
            and verdict['qualified'] is False, 'candidate decision differs from the reviewed 19/26 result')
    reproduction = read('validation/reproduction.json', 'PASS')
    require(reproduction.get('byte_identical_count') == 24 and reproduction.get('portable_tests_passed') == 18,
            'portable replay scope is incomplete')
    require(reproduction.get('reproducer_sha256') == sha(BUNDLE / 'validation/reproduce.py'), 'reproducer changed')
    maps = read('evaluation/maps_metadata.json')
    require(maps['renderer_sha256'] == sha(BUNDLE / 'evaluation/plot_maps.py'), 'map renderer changed')
    require(len(reproduction['artifacts']) == len({r['path'] for r in reproduction['artifacts']}) == 24,
            'portable artifact inventory differs')
    for row in reproduction['artifacts']:
        binding(row['path'], row['sha256'])
        require((ROOT / row['path']).stat().st_size == row['size_bytes'], 'portable artifact size differs')
    prior = read('validation/prior_after_kg_audit.json', 'PASS_PRIOR_414_AND_INDEX_PRESERVED')
    require(prior['artifact_count'] == 414, 'prior evidence audit incomplete')
    read('kg/stage_review.json', 'GO')
    read('kg/publish_receipt.json', 'PUBLISHED_AND_READBACK_PASS')
    read('kg/postpublish_copy_receipt.json', 'PASS_ACTIVE_WORKTREE_AND_WIKI_READBACK')
    return {'related_tests': 474, 'portable_tests': 18, 'portable_byte_identical_artifacts': 24,
            'categorical_rows': 108, 'constraints': 26, 'candidate_passed': 19,
            'figures': 13, 'prior_artifacts': 414, 'retained_configuration': 'B1'}


def artifacts():
    paths = {ROOT / name for name in SOURCES}
    paths.update(ROOT / name for name in ('README.md', 'docs/CURRENT_RESEARCH_STATUS.md',
                 'docs/CP02_SEDIMENTATION_CONSERVATION_20261109.md', 'patches/kdm6_conservative_sedimentation.patch'))
    paths.update(p for p in BUNDLE.rglob('*') if p.is_file() or p.is_symlink())
    paths.update((ROOT / 'graphify-out/2026-11-09-sedimentation-conservation').glob('*'))
    paths.update(ROOT / 'graphify-out' / name for name in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json'))
    excluded = {BUNDLE / 'validation.json', BUNDLE / 'validation/final_index_review.json'}
    result = []
    for path in sorted(paths):
        if path in excluded or '__pycache__' in path.parts or path.suffix in ('.pyc', '.lock'):
            continue
        require(path.is_file() and not path.is_symlink(), f'unsafe artifact: {path}')
        require(path.stat().st_size < 100 * 1024**2, f'artifact exceeds 100 MiB: {path}')
        with path.open('rb') as stream:
            require(stream.read(4) != b'\x7fELF', f'executable must remain external: {path}')
        result.append(path)
    return result


if __name__ == '__main__':
    output = BUNDLE / 'validation.json'
    require(not output.exists() and not output.is_symlink(), 'preserve the existing manifest before resealing')
    checks = verify()
    rows = [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p), 'size_bytes': p.stat().st_size} for p in artifacts()]
    output.write_text(json.dumps({'schema': 'cp02_sedimentation_conservation_validation_v1',
        'status': 'PASS_COMPLETED_REVIEWED_BATCH', 'base_commit': '8e65810352d2103dc1d14c89f256070dec061b59',
        'checks': checks, 'artifact_count': len(rows), 'artifacts': rows,
        'exclusions': ['This manifest and final index review avoid recursive hashes.',
                       'Transient locks/bytecode; full raw streams, WRF histories, ELF and archives remain external.'],
        'limits': ['Kernel conservation is not full-model water/energy closure or forecast skill.',
                   'The conservative candidate is unqualified at 19/26; current B1 remains retained.',
                   'RN1 upstream conventions, independent cases and separate C2 remain open.']}, indent=2, sort_keys=True) + '\n')
    print(f'PASS sealed {len(rows)} artifacts')
