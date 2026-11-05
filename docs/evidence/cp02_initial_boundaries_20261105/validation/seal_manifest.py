#!/usr/bin/env python3
"""Seal only this task's finalized artifacts; avoid recursive review hashes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_initial_boundaries_20261105'
EXTRA = (
    'README.md', 'docs/CURRENT_RESEARCH_STATUS.md', 'docs/CP02_INITIAL_BOUNDARIES_20261105.md',
    'tools/cp02_initial_boundaries.py', 'tools/cp02_initial_writer_analysis.py',
    'tools/cp02_initial_phi_analysis.py', 'tools/plot_cp02_initial_boundaries.py',
    'tools/plot_cp02_initial_mechanisms.py',
    'tests/test_cp02_initial_boundaries.py', 'tests/test_cp02_initial_writer_analysis.py',
    'tests/test_cp02_initial_phi_analysis.py', 'tests/test_plot_cp02_initial_boundaries.py',
    'tests/test_plot_cp02_initial_mechanisms.py',
    'graphify-out/graph.json', 'graphify-out/GRAPH_REPORT.md', 'graphify-out/manifest.json',
)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require_reviews():
    required = {
        'validation/clean_export_suite.json': 'PASS',
        'validation/independent_global_reader_review.json': 'GO',
        'validation/independent_numerator_raw_review.json': 'PASS_INDEPENDENT_RAW_NUMERATOR_REVIEW',
        'validation/final_science_report_review.json': 'PASS',
        'validation/portable_analysis_replay.json': 'PASS',
        'validation/pr148_artifact_audit.json': 'PASS',
        'mechanism_figures/receipt.json': 'PASS',
        'gallery/receipt.json': 'PASS',
    }
    team_path = BUNDLE / 'validation/final_team_review.json'
    if not team_path.is_file() or team_path.is_symlink():
        raise ValueError('final team review is required before sealing')
    team = json.loads(team_path.read_text())
    if team.get('status') != 'GO':
        raise ValueError('final team review has not passed')
    bound = team.get('artifact_sha256', {})
    expected = {str((BUNDLE / name).relative_to(ROOT)) for name in required}
    expected.update(name for name in EXTRA if not name.startswith('graphify-out/'))
    expected.add(str(Path(__file__).relative_to(ROOT)))
    if not expected.issubset(bound):
        raise ValueError('final team review omits a required source, report or validation receipt')
    for name, digest in bound.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe reviewed artifact path')
        path = ROOT / relative
        if path.is_symlink() or not path.is_file() or sha(path) != digest:
            raise ValueError('reviewed artifact changed: ' + name)
    for name, status in required.items():
        if json.loads((BUNDLE / name).read_text()).get('status') != status:
            raise ValueError('required validation is not complete: ' + name)
    for name, status in {
        'kg/publish_receipt.json': 'PUBLISHED_AND_READBACK_PASS',
        'kg/postpublish_copy_receipt.json': 'PASS_ACTIVE_WORKTREE_AND_WIKI_READBACK',
    }.items():
        path = BUNDLE / name
        if not path.is_file() or json.loads(path.read_text()).get('status') != status:
            raise ValueError('KG publication/readback is not complete: ' + name)


def main():
    require_reviews()
    omitted = {BUNDLE / 'validation.json', BUNDLE / 'validation/final_index_review.json'}
    paths = {ROOT / name for name in EXTRA}
    paths.update(p for p in BUNDLE.rglob('*') if p.is_file())
    paths.update((ROOT / 'graphify-out/2026-11-05-initial-boundaries').rglob('*'))
    artifacts = []
    for path in sorted(paths):
        if path in omitted or path.is_dir() or '__pycache__' in path.parts or path.suffix in ('.pyc', '.lock'):
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'not a regular artifact: {path}')
        size = path.stat().st_size
        if size >= 100 * 1024**2:
            raise ValueError(f'unsplit artifact: {path}')
        artifacts.append({'path': str(path.relative_to(ROOT)), 'size_bytes': size, 'sha256': sha(path)})
    tests = json.loads((BUNDLE / 'validation/clean_export_suite.json').read_text())
    if (tests['status'] != 'PASS' or tests['test_files'] != 56
            or tests['passed'] != tests['expected_tests'] or tests['passed'] < 353 or tests['exit_code'] != 0
            or tests['overlay_unchanged'] is not True):
        raise ValueError('clean export suite has not passed')
    receipt = {
        'schema': 'cp02_initial_boundaries_validation_v1',
        'status': 'PASS_SCOPED_NATIVE_DIAGNOSIS',
        'base_commit': '4e193057538840c47631761ac22e70169fbfc0c3',
        'pr_base_branch': 'research/b1-two-hour-process',
        'pr_head_branch': 'research/b1-initial-boundaries',
        'case_initial_utc': '2026-08-16T12:00:00Z',
        'new_candidates': 0, 'new_six_hour_forecasts': 0,
        'diagnostic_reintegrations': {
            'arms': ['B1', 'DM065'], 'per_run_seconds': 80,
            'mode': 'Original FIX executable with GDB boundary/operand observations; no model source or state-policy change.',
            'scope': 'Actual calls and selected words with parity gates; no new one-hour/six-hour forecast.'},
        'retained_configuration': 'IMPROVED_BG_FIXED', 'goal_met': False,
        'analysis': {'called_native_cells': 2533440, 'uncalled_cells': 40092,
                     'initial_same_entry_NR_different_cells': 154317,
                     'selected_native_columns': 123, 'levels': 39, 'selected_steps': 4},
        'tests': tests,
        'team_review': 'validation/final_team_review.json',
        'prior_evidence': {'PR148_artifacts': 357, 'additional_manifest_and_review': 2,
                           'audit': 'validation/pr148_artifact_audit.json'},
        'open_items': [
            'Selected NR writer and final pressure producer are traced; a full flux attribution and later precipitation causal path remain open.',
            'Local arithmetic regrouping is not an adopted model correction or a forecast performance result.',
            'Same-time mass basis and domain water/energy budgets remain open.',
            'RN1 upstream time/coverage/QC and independent cases remain unverified.',
            'Separate C2 T39 and H/A/N one-hour completion remain unfinished.',
        ],
        'exclusions': ['Self manifest and final_index_review.json avoid recursive hashes.',
                       'Transient locks, Python caches and external runtime files are excluded.'],
        'artifact_count': len(artifacts), 'artifacts': artifacts,
    }
    (BUNDLE / 'validation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'PASS: {len(artifacts)} bounded artifacts')


if __name__ == '__main__':
    main()
