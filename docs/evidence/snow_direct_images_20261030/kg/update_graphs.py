#!/usr/bin/env python3
"""Stage and publish the frozen snow direct-image gallery graph update."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path('/var/tmp/cloudbal-snow-sensitivity')
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
HERE = Path(__file__).resolve().parent
SNAPSHOT = '2026-10-30-snow-direct-images'
STAGING = Path('/var/tmp/cloudbal_snow_direct_images_kg_20261030')
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
WIKI_FILES = ('graph-report.md', 'graph-report-klaps50.md',
              'graph-report-cloud-bal.md', 'index.md', 'log.md')
REQUIRED_PATHS = {
    'docs/evidence/snow_fine_20261030/build_report.py',
    'docs/evidence/snow_direct_images_20261030/kg/update_graphs.py',
}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load KG helper: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prior = SOURCE / 'docs/evidence/snow_sensitivity_20261030/kg'
stage = load('snow_direct_images_stage', prior / 'stage_kg.py')
publisher = load('snow_direct_images_publisher', prior / 'publish_kg.py')
stage.SOURCE = SOURCE
stage.MAINTAINED = MAINTAINED
stage.SNAPSHOT = SNAPSHOT


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def capture_baseline() -> dict:
    roots = {'KLAPS50': MAINTAINED, 'Cloud-BAL': MAINTAINED / 'Cloud-BAL'}
    records = {}
    for label, root in roots.items():
        status = stage.git(root, 'status', '--short').decode('utf-8')
        records[label] = {
            'root': str(root),
            'graph_sha256': sha256(root / 'graphify-out/graph.json'),
            'graph_report_sha256': sha256(root / 'graphify-out/GRAPH_REPORT.md'),
            'manifest_sha256': sha256(root / 'graphify-out/manifest.json'),
            'dated_snapshots': stage.snapshot_inventory(root),
            'git_status_exact': status.splitlines(),
            'git_status_raw_sha256': hashlib.sha256(status.encode('utf-8')).hexdigest(),
        }
    wiki = MAINTAINED / 'wiki'
    return {
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'maintained_roots': records,
        'dated_snapshot_count_total': sum(len(r['dated_snapshots']) for r in records.values()),
        'wiki_hashes': {name: sha256(wiki / name) for name in WIKI_FILES},
    }


def verify_baseline(baseline: dict) -> None:
    roots = {'KLAPS50': MAINTAINED, 'Cloud-BAL': MAINTAINED / 'Cloud-BAL'}
    for label, root in roots.items():
        record = baseline['maintained_roots'][label]
        for filename, key in (('graph.json', 'graph_sha256'),
                              ('GRAPH_REPORT.md', 'graph_report_sha256'),
                              ('manifest.json', 'manifest_sha256')):
            require(sha256(root / 'graphify-out' / filename) == record[key],
                    f'{label} maintained {filename} changed since baseline')
        require(stage.snapshot_inventory(root) == record['dated_snapshots'],
                f'{label} dated snapshot inventory changed since baseline')
        status = stage.git(root, 'status', '--short').decode('utf-8')
        require(status.splitlines() == record['git_status_exact'],
                f'{label} exact dirty state changed since baseline')
        require(hashlib.sha256(status.encode('utf-8')).hexdigest() ==
                record['git_status_raw_sha256'], f'{label} dirty-state bytes changed')
    require({name: sha256(MAINTAINED / 'wiki' / name) for name in WIKI_FILES} ==
            baseline['wiki_hashes'], 'maintained wiki changed since baseline')


def frozen_selection() -> dict:
    return stage.load_selection(HERE / 'selection_lock.json', REQUIRED_PATHS)


original_refresh_report = stage.refresh_staged_report


def refresh_report(stage_root: Path, extracted_paths: set[str]) -> None:
    original_refresh_report(stage_root, extracted_paths)
    report = stage_root / 'graphify-out/GRAPH_REPORT.md'
    content = report.read_text()
    content = content.replace('snow sensitivity scoped update', 'snow direct images scoped update')
    content = content.replace('snow sensitivity', 'snow direct images')
    content += ('\n- The source change only rewrites generated PNG targets as absolute raw.githubusercontent.com URLs pinned to commit 18d8b45008428644c7a85d624830b76bce597289.\n'
                '- Graph freshness does not establish browser rendering or scientific validation.\n')
    report.write_text(content)


stage.refresh_staged_report = refresh_report
original_write_wiki = stage.write_staged_wiki


def write_staged_wiki(run: Path, records: dict, lock: dict) -> dict:
    hashes = original_write_wiki(run, records, lock)
    for name in hashes:
        path = run / 'wiki' / name
        content = path.read_text().replace('snow sensitivity', 'snow direct images')
        content = content.replace('snow sensitivity scoped update', 'snow direct images scoped update')
        path.write_text(content)
    return {name: sha256(run / 'wiki' / name) for name in hashes}


stage.write_staged_wiki = write_staged_wiki


def stage_update() -> None:
    lock = frozen_selection()
    baseline = capture_baseline()
    baseline_path = HERE / 'baseline.json'
    baseline_path.write_text(json.dumps(baseline, indent=2, sort_keys=True) + '\n')
    verify_baseline(baseline)
    paths = set(lock['selected_source_sha256'])
    result = stage.stage_selected(lock, paths, paths, STAGING)
    verify_baseline(baseline)
    frozen_selection()
    result.update(
        status='STAGED_ONLY_NO_MAINTAINED_WRITES',
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        baseline_sha256=sha256(baseline_path),
        selection_lock_sha256=sha256(HERE / 'selection_lock.json'),
        dated_snapshots_preserved=baseline['dated_snapshot_count_total'],
        snapshot_counts_by_corpus={k: len(v['dated_snapshots'])
                                   for k, v in baseline['maintained_roots'].items()},
        source_extraction_scope=sorted(paths),
        manifest_update_scope=sorted(paths),
        hash_only_sha256=lock.get('hash_only_sha256', {}),
        extraction_limits=[
            'Only the two frozen Python paths are structurally extracted; other evidence is hash-bound only.',
            'Manifest updates are selected-path-only; no corpus scan or prune occurs.',
            'The absolute PNG URL presentation fix does not validate browser rendering.',
            'Graph freshness does not establish runtime or scientific validation.',
            'Fortran cross-file CALL extraction is partial.',
        ],
    )
    (HERE / 'stage_receipt.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')


def publish_update() -> None:
    baseline = json.loads((HERE / 'baseline.json').read_text())
    lock = frozen_selection()
    receipt = json.loads((HERE / 'stage_receipt.json').read_text())
    review = json.loads((HERE / 'stage_review.json').read_text())
    require(review.get('status') == 'GO' and
            review.get('stage_receipt_sha256') == sha256(HERE / 'stage_receipt.json'),
            'agent-team graph stage review must bind the exact receipt')
    require(receipt.get('status') == 'STAGED_ONLY_NO_MAINTAINED_WRITES',
            'stage is not isolated and unapplied')
    require(receipt.get('source_extraction_scope') == sorted(REQUIRED_PATHS) and
            receipt.get('manifest_update_scope') == sorted(REQUIRED_PATHS),
            'stage extraction and manifest scope must exactly match the frozen two paths')
    require(receipt.get('selection_lock_sha256') == sha256(HERE / 'selection_lock.json'),
            'frozen selection changed after staging')
    require(receipt.get('baseline_sha256') == sha256(HERE / 'baseline.json'),
            'baseline changed after staging')
    require(receipt.get('hash_only_sha256') == lock.get('hash_only_sha256', {}),
            'hash-only evidence changed after staging')
    stage_targets = []
    for label, record in baseline['maintained_roots'].items():
        root = Path(record['root'])
        staged = Path(receipt['stage']) / label / 'graphify-out'
        require(not (root / 'graphify-out' / SNAPSHOT).exists(),
                f'{label} dated snapshot already exists')
        hashes = receipt['corpora'][label]['snapshot_file_sha256']
        for name, expected in hashes.items():
            require(sha256(staged / name) == expected and
                    sha256(staged / SNAPSHOT / name) == expected,
                    f'{label} staged file changed: {name}')
            stage_targets.append(dict(source=staged / name,
                                      destination=root / 'graphify-out' / name,
                                      kind='file', sha256=expected))
        stage_targets.append(dict(source=staged / SNAPSHOT,
                                  destination=root / 'graphify-out' / SNAPSHOT,
                                  kind='directory', files=hashes))
    for name, expected in receipt['staged_wiki_sha256'].items():
        source = Path(receipt['stage']) / 'wiki' / name
        require(sha256(source) == expected, f'staged wiki changed: {name}')
        stage_targets.append(dict(source=source, destination=MAINTAINED / 'wiki' / name,
                                  kind='file', sha256=expected))
    verify_baseline(baseline)
    backup = STAGING / 'publication-backup'
    require(not backup.exists(), 'preserve any existing publication backup')
    publisher.publish(stage_targets, backup, baseline, stage, SNAPSHOT)
    (HERE / 'publish_receipt.json').write_text(json.dumps({
        'status': 'PUBLISHED_AND_READBACK_PASS',
        'stage_receipt_sha256': sha256(HERE / 'stage_receipt.json'),
        'stage_review_sha256': sha256(HERE / 'stage_review.json'),
        'prior_snapshots_preserved': baseline['dated_snapshot_count_total'],
        'snapshot_counts_by_corpus': {k: len(v['dated_snapshots'])
                                      for k, v in baseline['maintained_roots'].items()},
        'targets': [{'path': str(t['destination']), 'sha256': t.get('sha256'),
                     'files': t.get('files')} for t in stage_targets],
        'rollback_backup': str(backup),
    }, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('stage', 'publish'))
    args = parser.parse_args()
    stage_update() if args.action == 'stage' else publish_update()
