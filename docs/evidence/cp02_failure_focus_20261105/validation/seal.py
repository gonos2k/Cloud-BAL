#!/usr/bin/env python3
"""Seal the reviewed B1 failure-focus evidence bundle."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_failure_focus_20261105'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(relative: str) -> dict:
    path = BUNDLE / relative
    require(path.is_file() and not path.is_symlink(), f'missing or unsafe receipt: {relative}')
    return json.loads(path.read_text(encoding='utf-8'))


def verify_output_map(owner: str, outputs: dict) -> list[Path]:
    paths = []
    for name, identity in outputs.items():
        path = Path(identity['path'])
        if not path.is_absolute():
            path = ROOT / path
        require(path.is_file() and not path.is_symlink(), f'{owner} output missing/unsafe: {name}')
        require(path.stat().st_size == identity['size_bytes'], f'{owner} output size differs: {name}')
        require(sha256(path) == identity['sha256'], f'{owner} output hash differs: {name}')
        paths.append(path)
    return paths


def verify_figure_package() -> list[Path]:
    receipt = read_json('figures/package_receipt.json')
    archive = BUNDLE / 'figures' / receipt['path']
    require(archive.is_file() and not archive.is_symlink(), 'offline gallery archive missing/unsafe')
    require(archive.stat().st_size == receipt['size_bytes'] and sha256(archive) == receipt['sha256'],
            'offline gallery archive identity differs from package receipt')
    members = receipt['members']
    expected = receipt['member_sha256']
    require(set(members) == set(expected), 'gallery member list/hash map differs')
    require(set(members) == {
        'conditional_layer_contrasts.png', 'csi_algebra_h5_5mm.png', 'gallery.md',
        'h2_transition_maps.png', 'h5_transition_maps.png', 'index.html', 'metadata.json',
        'selected_point_hourly_paths.png'}, 'gallery package member inventory differs')
    for name, expected_hash in expected.items():
        member_path = BUNDLE / 'figures' / name
        require(member_path.is_file() and not member_path.is_symlink()
                and sha256(member_path) == expected_hash, f'gallery source member hash differs: {name}')
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        require(len(names) == len(set(names)) and set(names) == set(members), 'gallery ZIP members differ')
        require(package.testzip() is None, 'gallery ZIP CRC failure')
        for name in members:
            data = package.read(name)
            require(hashlib.sha256(data).hexdigest() == expected[name], f'gallery member hash differs: {name}')
    image_paths = []
    for path in (BUNDLE / 'figures').glob('*.png'):
        require(path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n', f'invalid PNG signature: {path.name}')
        image_paths.append(path)
    require(len(image_paths) == 5, 'expected five rendered PNG figures')
    return [archive, *image_paths]


def verify_bundle() -> dict:
    required_statuses = {
        'validation/clean_export.json': 'PASS',
        'validation/figure_visual_review.json': 'PASS_VISUAL_AND_PACKAGE_REVIEW',
        'validation/reproduction.json': 'PASS',
        'validation/prior_evidence_audit.json': 'PASS',
        'review/plan_review.json': 'GO_PLAN_ONLY',
        'review/independent_target_review.json': 'PASS_TARGET_RECOUNT_AND_MATCH_REVIEW',
        'review/independent_state_review.json': 'PASS_STATE_EXTRACTION_REVIEW',
        'review/independent_context_review.json': 'PASS_CONTEXT_RECOUNT',
        'review/independent_failure_recount.json': 'PASS_ARITHMETIC_RECOUNT',
        'review/final_science_report_review.json': 'PASS_FINAL_REPORT_SCIENCE_REVIEW',
        'review/independent_kg_review.json': 'PASS_SOURCE_AND_EVIDENCE_REVIEW',
        'kg/stage_review.json': 'GO',
        'kg/publish_receipt.json': 'PUBLISHED_AND_READBACK_PASS',
        'kg/postpublish_copy_receipt.json': 'PASS_ACTIVE_WORKTREE_AND_WIKI_READBACK',
    }
    required = {name: read_json(name) for name in required_statuses}
    for name, expected in required_statuses.items():
        require(required[name].get('status') == expected,
                f'{name} status must be {expected}, got {required[name].get("status")}')

    clean = required['validation/clean_export.json']
    require(clean.get('expected_tests') == 422 and clean.get('passed') == 422
            and clean.get('exit_code') == 0 and clean.get('overlay_unchanged') is True,
            'immutable clean export does not match the expected 422-test pass')
    visual = required['validation/figure_visual_review.json']
    package = read_json('figures/package_receipt.json')
    require(visual.get('zip_sha256') == package.get('sha256')
            and visual.get('png_sha256') == {
                name: digest for name, digest in package['member_sha256'].items()
                if name.endswith('.png')}, 'visual review does not bind the current gallery assets')
    report_review = required['review/final_science_report_review.json']
    report_bindings = report_review.get('reviewed_artifacts', {})
    require('docs/CP02_B1_FAILURE_FOCUS_20261105.md' in report_bindings,
            'science review does not bind the final report')
    for name, expected_hash in report_bindings.items():
        path = ROOT / name
        require(path.is_file() and not path.is_symlink() and sha256(path) == expected_hash,
                f'science review artifact binding differs: {name}')
    prior = required['validation/prior_evidence_audit.json']
    require(prior.get('artifact_count') == 462 and len(prior.get('artifacts', [])) == 462,
            'prior PR150 artifact audit is incomplete')

    targets = read_json('targets/bundle_receipt.json')
    require(targets.get('schema') == 'cp02_failure_focus_targets_v1'
            and targets.get('status') == 'COMPLETE'
            and targets.get('exit_status') == 0
            and targets.get('unique_focus_points') == 270
            and targets.get('matched_control_pairs') == 158
            and targets.get('missing_control_pairs') == 0,
            'target bundle counts or status differ')
    state = read_json('state/extracted/receipt.json')
    expected_cases = ['ORIGINAL', 'A', 'C', 'B1_OLD_KDM6']
    expected_hours = list(range(12, 19))
    expected_pairs = {(case, hour) for case in expected_cases for hour in expected_hours}
    state_pairs = {(record['case'], record['hour_utc']) for record in state.get('records', [])}
    require(state.get('status') == 'PASS' and state_pairs == expected_pairs
            and state.get('cases') == expected_cases and state.get('hours_utc') == expected_hours
            and state.get('points') == 270 and state.get('levels') == 39
            and len(state.get('surface_score_checks', [])) == 24,
            'state extraction coverage differs')
    context = read_json('context/bundle_receipt.json')
    require(context.get('schema') == 'cp02_b1_failure_context_v1'
            and context.get('status') == 'COMPLETE'
            and context.get('exit_status') == 0
            and context.get('cases') == expected_cases and context.get('hours_utc') == expected_hours
            and context.get('focus_points') == 270 and context.get('event_rows') == 158
            and context.get('matched_control_rows') == 158,
            'context bundle counts or status differ')
    require(set(targets['outputs']) == {
        'conditional_weak_detections.csv', 'control_reuse_audit.csv', 'csi_algebra.csv',
        'event_membership.csv', 'focus_membership.csv', 'matched_controls.csv',
        'source_receipt.json', 'spatial_neighbors.csv', 'temporal_cohort_summary.csv',
        'temporal_diagnostics.csv', 'transition_counts.csv'}, 'target output inventory differs')
    require(set(context['outputs']) == {
        'cohort_physical_contrasts.csv', 'cohort_surface_context.csv',
        'cohort_surface_context_summary.csv', 'layer_features.csv', 'point_surface_paths.csv'},
        'context output inventory differs')

    output_paths = []
    output_paths += verify_output_map('targets', targets['outputs'])
    output_paths += verify_output_map('context', context['outputs'])
    output_paths += verify_figure_package()
    require(len(output_paths) == 22, 'target/context/figure output coverage differs')
    state_dir = BUNDLE / 'state/extracted'
    for record in state['records']:
        path = state_dir / record['output']
        require(path.is_file() and not path.is_symlink(), f'missing state archive: {record["output"]}')
        require(path.stat().st_size == record['output_size_bytes']
                and sha256(path) == record['output_sha256'], f'state archive hash differs: {record["output"]}')
        output_paths.append(path)
    require(len(output_paths) == 50, 'target/context/figure/state output count differs from 50')

    plan = read_json('analysis_plan.json')
    require(plan.get('status') == 'FROZEN_DIAGNOSTIC_SCOPE', 'analysis plan is not frozen')
    require(state.get('plan_sha256') == sha256(BUNDLE / 'state/extraction_plan.json'),
            'state receipt does not bind the extraction plan')
    require(context.get('state_receipt_sha256') == sha256(BUNDLE / 'state/extracted/receipt.json'),
            'context receipt does not bind the state receipt')
    require(context.get('target_receipt_sha256') == sha256(BUNDLE / 'targets/bundle_receipt.json'),
            'context receipt does not bind the target receipt')
    target_review = required['review/independent_target_review.json']
    state_review = required['review/independent_state_review.json']
    context_review = required['review/independent_context_review.json']
    require(target_review.get('bundle_receipt_sha256') == sha256(BUNDLE / 'targets/bundle_receipt.json')
            and target_review.get('analysis_plan_sha256') == sha256(BUNDLE / 'analysis_plan.json'),
            'target review does not bind the frozen target receipt and analysis plan')
    require(state_review.get('extraction_receipt_sha256') == sha256(BUNDLE / 'state/extracted/receipt.json')
            and state_review.get('target_receipt_sha256') == sha256(BUNDLE / 'targets/bundle_receipt.json')
            and state_review.get('plan_sha256') == sha256(BUNDLE / 'state/extraction_plan.json'),
            'state review does not bind the extracted state, target receipt and plan')
    require(context_review.get('context_bundle_sha256') == sha256(BUNDLE / 'context/bundle_receipt.json')
            and context_review.get('state_receipt_sha256') == sha256(BUNDLE / 'state/extracted/receipt.json')
            and context_review.get('target_receipt_sha256') == sha256(BUNDLE / 'targets/bundle_receipt.json'),
            'context review does not bind its context, state and target receipts')

    copy = required['kg/postpublish_copy_receipt.json']
    require(copy.get('publish_receipt_sha256') == sha256(BUNDLE / 'kg/publish_receipt.json'),
            'postpublish copy receipt does not bind the publish receipt')
    copied = copy.get('copied', [])
    require(len(copied) == 9, 'postpublish receipt must contain four graph targets and five wiki copies')
    for item in copied:
        path = Path(item['path'])
        if not path.is_absolute():
            path = ROOT / path
        require(path.exists() and not path.is_symlink(), f'KG readback target missing/unsafe: {path}')
        if item['kind'] == 'file':
            require(path.is_file() and sha256(path) == item['hashes'],
                    f'KG file readback differs: {path}')
        else:
            require(item['kind'] == 'directory' and path.is_dir(), f'unknown KG target kind: {item["kind"]}')
            children = list(path.iterdir())
            require(all(child.is_file() and not child.is_symlink() for child in children)
                    and {child.name for child in children} == set(item['hashes']),
                    f'KG snapshot contents differ: {path}')
            require(all(sha256(path / name) == expected for name, expected in item['hashes'].items()),
                    f'KG snapshot readback hashes differ: {path}')

    return {
        'required_statuses': required_statuses,
        'clean_export': {'passed': clean['passed'], 'expected': clean['expected_tests']},
        'target_points': targets['unique_focus_points'],
        'matched_control_pairs': targets['matched_control_pairs'],
        'state_snapshots': len(state['records']),
        'context_event_rows': context['event_rows'],
        'verified_output_count': len(output_paths),
        'prior_artifact_count': prior['artifact_count'],
    }


def artifact_paths() -> list[Path]:
    extras = [
        ROOT / 'README.md', ROOT / 'docs/CURRENT_RESEARCH_STATUS.md',
        ROOT / 'docs/CP02_B1_FAILURE_FOCUS_20261105.md',
        ROOT / 'tools/cp02_b1_failure_targets.py', ROOT / 'tools/cp02_b1_failure_state.py',
        ROOT / 'tools/cp02_b1_failure_context.py', ROOT / 'tools/plot_cp02_b1_failure_focus.py',
        ROOT / 'tools/cp02_failure_state_features.py',
    ]
    extras.extend((ROOT / 'tests').glob('*b1_failure*.py'))
    extras.extend((ROOT / 'tests').glob('*failure_focus*.py'))
    extras.extend((ROOT / 'graphify-out').glob('2026-11-05-failure-focus/*'))
    extras.extend(ROOT / 'graphify-out' / name for name in ('graph.json', 'manifest.json', 'GRAPH_REPORT.md'))
    paths = set(extras)
    paths.update(path for path in BUNDLE.rglob('*') if path.is_file())
    excluded = {BUNDLE / 'validation.json', BUNDLE / 'validation/final_index_review.json'}
    result = []
    for path in paths:
        if path in excluded or '__pycache__' in path.parts or path.suffix in ('.pyc', '.lock'):
            continue
        require(path.is_file() and not path.is_symlink(), f'unsafe/missing artifact: {path}')
        require(path.stat().st_size < 100 * 1024**2, f'artifact exceeds 100 MiB: {path}')
        result.append(path)
    return sorted(result)


def main() -> None:
    output = BUNDLE / 'validation.json'
    require(not output.exists(), 'validation.json already exists; refusing overwrite')
    checks = verify_bundle()
    rows = [
        {'path': str(path.relative_to(ROOT)), 'size_bytes': path.stat().st_size,
         'sha256': sha256(path)}
        for path in artifact_paths()
    ]
    result = {
        'schema': 'cp02_failure_focus_validation_v1',
        'status': 'PASS_COMPLETED_FAILURE_FOCUS_BATCH',
        'base_commit': 'ff1adc6328d79fc6646c23d9cd9e90208037e817',
        'analysis_scope': 'Diagnostic analysis of existing B1 histories; no new forecast, candidate, or adoption gate.',
        'checks': checks,
        'artifact_count': len(rows),
        'artifacts': rows,
        'exclusions': [
            'The validation manifest and final index review are excluded to avoid recursive hashes.',
            'Transient locks and Python bytecode are excluded; source identities and history-source pins are retained.',
        ],
        'limitations': [
            'Eulerian snapshots cannot identify evaporation, transport, tendencies, or causal mechanisms.',
            'Thermodynamic and height fields are history-derived diagnostics, not native process-call values.',
            'No column dry mass, water/energy budget, or budget closure is asserted.',
            'One case and one event window do not establish general forecast performance.',
        ],
    }
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(f'PASS: sealed {len(rows)} bounded artifacts')


if __name__ == '__main__':
    main()
