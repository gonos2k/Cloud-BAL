#!/usr/bin/env python3
"""Seal reviewed paired diagnostics, keeping validation and forecast claims separate."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
B = ROOT / 'docs/evidence/cp02_low_threshold_process_20261110'
SOURCES = (
    'tools/cp02_low_threshold_cohorts.py', 'tools/cp02_low_threshold_process.py',
    'tools/plot_cp02_low_threshold_process.py', 'tests/test_cp02_low_threshold_cohorts.py',
    'tests/test_cp02_low_threshold_process.py', 'tests/test_cp02_low_threshold_native_source.py',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(name, status):
    path = B / name
    require(path.is_file() and not path.is_symlink(), 'missing receipt: ' + name)
    result = json.loads(path.read_text())
    require(result.get('status') == status, 'incomplete receipt: ' + name)
    return result


def bind(name, expected):
    path = Path(name)
    if not path.is_absolute():
        require('..' not in path.parts, 'unsafe artifact name')
        path = ROOT / path
    require(path.is_file() and not path.is_symlink() and sha(path) == expected,
            'changed artifact: ' + str(name))


def outputs(folder):
    receipt = read(folder + '/receipt.json', 'COMPLETE')
    for name, expected in receipt['outputs'].items():
        bind(B / folder / name, expected)
    return receipt


def verify():
    clean = read('validation/clean_export.json', 'PASS')
    require(clean['passed'] == clean['expected_tests'] == 503 and clean['exit_code'] == 0
            and clean['source_inputs_unchanged'], 'related503-test suite required')
    for name in SOURCES:
        bind(name, clean['overlay_sha256'][name])
    for name, expected in clean['guarded_source_input_sha256'].items():
        bind(name, expected)
    for folder in ('cohorts/results', 'analysis', 'figures'):
        outputs(folder)
    require(json.loads((B / 'cohorts/results/summary.json').read_text())['capture_points'] == 21,
            'selection scope differs')
    proof = read('native/proof/comparability.json', 'PASS')
    require(set(proof['arms']) == {'FIX', 'CONSERVATIVE', 'ICE_FIXED'}, 'arm scope differs')
    for arm, evidence in proof['arms'].items():
        folder = 'native/compact/' + arm
        audit = read(folder + '/audit_receipt.json', 'PASS')
        require(audit['all_raw_inputs_unchanged'] and audit['all_history_files_byte_exact'],
                'raw/history proof incomplete')
        bind(B / folder / 'audit_receipt.json', evidence['audit_receipt_sha256'])
        bind(B / folder / 'capture_receipt.json', evidence['capture_receipt_sha256'])
        for name, expected in audit['artifact_hashes'].items():
            bind(name, expected)
        require(len(evidence['surface_history_binding']) == 7 and
                all(row['all_77_columns_bitwise_equal'] for row in evidence['surface_history_binding']),
                'surface endpoint proof incomplete')
        require(set(evidence['outputs']) == {'h01.npz', 'h05.npz', 'h06.npz', 'surface.npz'},
                'compact scope differs')
        for name, item in evidence['outputs'].items():
            path = B / folder / name
            bind(path, item['sha256'])
            require(path.stat().st_size == item['size_bytes'], 'compact size differs')
        read('science/full/' + arm + '/receipt.json', 'PASS')
    read('science/h6_review/receipt.json', 'PASS')
    read('native/proof/provenance_verification.json', 'PASS')
    for name in ('analysis_review', 'figures_review', 'provenance_review', 'gallery_review',
                 'report_review'):
        read('review/' + name + '.json', 'PASS')
    report_review = read('review/report_review.json', 'PASS')
    bind('docs/CP02_LOW_THRESHOLD_PROCESS_20261110.md', report_review['report_sha256'])
    for name, expected in report_review['evidence_sha256'].items():
        bind(name, expected)
    gallery = read('gallery_receipt.json', 'PASS')
    require(gallery['figure_count'] == 27, 'gallery scope differs')
    bind(B / 'all_figures.zip', gallery['archive_sha256'])
    bind(B / 'FIGURES.md', gallery['gallery_sha256'])
    # The tree replay has a separately reviewed exact scope. The original full
    # raw streams remain external and are never implied by its PASS status.
    replay = read('validation/tree_replay_receipt.json', 'PASS')
    require(replay['focused_tests_passed'] == 15 and replay['native_sample']['sample_steps'] == [1, 2, 3],
            'tree replay scope incomplete')
    require({key: len(value) for key, value in replay['byte_identical_outputs'].items()} ==
            {'cohort': 5, 'analysis': 6, 'figures': 27}, 'replay output count differs')
    for name, expected in replay['overlay_files'].items():
        bind(name, expected['sha256'])
        require((ROOT / name).stat().st_size == expected['size_bytes'], 'replay input size differs')
    prior = read('kg/prior_audit.json', 'PASS_PRIOR_73_AND_INDEX_PRESERVED')
    require(prior['artifact_count'] == 73, 'prior evidence audit incomplete')
    read('kg/stage_review.json', 'GO')
    read('kg/publish_receipt.json', 'PUBLISHED_AND_READBACK_PASS')
    read('kg/postpublish_copy_receipt.json', 'PASS_ACTIVE_WORKTREE_AND_WIKI_READBACK')
    return {'related_tests': 503, 'new_tests': 15, 'paired_native_arms': 3,
            'history_files_byte_identical': 21, 'source_surface_endpoints_bitwise_equal': 1617,
            'selected_points': 21, 'native_columns': 77, 'native_levels': 39,
            'detailed_steps': [list(range(1, 181)), list(range(721, 1081))],
            'figures': 27, 'new_physics_candidate': False, 'new_forecast_skill_result': False,
            'candidate_admission': {'passed': 21, 'required': 26}, 'retained_configuration': 'B1',
            'portable_replay_scope': replay.get('scope'),
            'full_raw_streams_external': True}


def artifacts():
    paths = {ROOT / name for name in SOURCES}
    paths.update(ROOT / name for name in ('README.md', 'docs/CURRENT_RESEARCH_STATUS.md',
                                         'docs/CP02_LOW_THRESHOLD_PROCESS_20261110.md'))
    paths.update(p for p in B.rglob('*') if p.is_file() or p.is_symlink())
    paths.update((ROOT / 'graphify-out/2026-11-10-low-threshold-process').glob('*'))
    paths.update(ROOT / 'graphify-out' / name for name in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json'))
    excluded = {B / 'validation.json', B / 'review/final_index_review.json'}
    rows = []
    for path in sorted(paths):
        if path in excluded or '__pycache__' in path.parts or path.suffix in ('.pyc', '.lock'):
            continue
        require(path.is_file() and not path.is_symlink(), 'unsafe artifact: ' + str(path))
        require(path.stat().st_size < 100 * 1024 ** 2, 'artifact exceeds100MiB')
        with path.open('rb') as stream:
            require(stream.read(4) != b'\x7fELF', 'ELF must remain external')
        rows.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path),
                     'size_bytes': path.stat().st_size})
    return rows


if __name__ == '__main__':
    destination = B / 'validation.json'
    require(not destination.exists() and not destination.is_symlink(), 'preserve existing manifest')
    checks = verify()
    rows = artifacts()
    destination.write_text(json.dumps({'status': 'PASS', 'schema': 'cp02_low_threshold_process_validation_v1',
                                      'checks': checks, 'artifact_count': len(rows), 'artifacts': rows,
                                      'excluded_self_referential': ['validation.json', 'review/final_index_review.json']},
                                     indent=2) + '\n')
    print(json.dumps({'status': 'PASS', 'artifact_count': len(rows)}))
