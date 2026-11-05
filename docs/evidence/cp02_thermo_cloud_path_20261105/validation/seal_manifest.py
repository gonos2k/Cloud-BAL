#!/usr/bin/env python3
"""Seal only this task's finalized artifacts; avoid recursive review hashes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
EXTRA = (
    'README.md', 'docs/CURRENT_RESEARCH_STATUS.md',
    'docs/CP02_THERMO_CLOUD_PATH_20261105.md',
    'tools/cp02_thermo_cloud_cohorts.py', 'tools/cp02_thermo_cloud_path.py',
    'tools/plot_cp02_thermo_cloud_path.py',
    'tests/test_cp02_thermo_cloud_cohorts.py', 'tests/test_cp02_thermo_cloud_path.py',
    'tests/test_plot_cp02_thermo_cloud_path.py',
    'graphify-out/graph.json', 'graphify-out/GRAPH_REPORT.md',
    'graphify-out/manifest.json',
)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    omitted = {BUNDLE / 'validation.json', BUNDLE / 'validation/final_index_review.json'}
    paths = {ROOT / name for name in EXTRA}
    paths.update(p for p in BUNDLE.rglob('*') if p.is_file())
    paths.update((ROOT / 'graphify-out/2026-11-05-thermo-cloud-path').rglob('*'))
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
    if (tests['status'] != 'PASS' or tests['test_files'] != 51
            or tests['passed'] != 327 or tests['exit_code'] != 0
            or tests['overlay_unchanged'] is not True):
        raise ValueError('clean export suite has not passed')
    receipt = {
        'schema': 'cp02_thermo_cloud_path_validation_v1',
        'status': 'PASS_SCOPED_NATIVE_DIAGNOSIS',
        'base_commit': '45de814aa346527748fcfe2d8c16e30d46726ca8',
        'pr_base_branch': 'research/b1-two-hour-process',
        'case_initial_utc': '2026-08-16T12:00:00Z',
        'new_candidates': 0, 'new_six_hour_forecasts': 0,
        'diagnostic_reintegrations': {'arms': ['B1', 'DM065'], 'hours': 2,
                                    'byte_identical_whole_histories': 6},
        'retained_configuration': 'IMPROVED_BG_FIXED', 'goal_met': False,
        'analysis': {'points': 39, 'native_cells': 123, 'levels': 39, 'steps': 360,
                     'cell_steps_per_arm': 1726920, 'RAINNC_history_word_matches': 492,
                     'lossless_array_bundles': 5},
        'tests': tests,
        'team_review': 'validation/final_team_review.json',
        'prior_evidence': {'PR147_artifacts': 161, 'additional_manifest_and_review': 2,
                           'audit': 'validation/pr147_artifact_audit.json'},
        'open_items': [
            'Incoming differences are not traced to original writers or transport fluxes.',
            'CCN activation, ice sedimentation and unassigned gaps are not fully decomposed.',
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
