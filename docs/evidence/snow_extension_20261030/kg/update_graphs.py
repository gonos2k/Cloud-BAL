#!/usr/bin/env python3
"""Stage and publish only the reviewed extension's structural graph additions."""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
SNAPSHOT = '2026-10-30-snow-heavy-extension'
STAGING = Path('/var/tmp/cloudbal_snow_extension_kg_20261030')
PRIOR = ROOT / 'docs/evidence/snow_sensitivity_20261030/kg'
REQUIRED_PATHS = {
    'tools/cp02_snow_extension.py',
    'tools/plot_snow_extension.py',
    'tests/test_cp02_snow_extension.py',
    'tests/test_plot_snow_extension.py',
    'docs/evidence/snow_extension_20261030/build_report.py',
    'docs/evidence/snow_extension_20261030/build_full_score_tables.py',
    'docs/evidence/snow_extension_20261030/kg/update_graphs.py',
    'docs/evidence/snow_extension_20261030/runtime/prepare_cases.py',
    'docs/evidence/snow_extension_20261030/runtime/run_case.py',
    'docs/evidence/snow_extension_20261030/runtime/run_all.py',
    'docs/evidence/snow_extension_20261030/runtime/finalize_batch.py',
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage = load('previous_scoped_graph_stage', PRIOR / 'stage_kg.py')
publisher = load('previous_scoped_graph_publisher', PRIOR / 'publish_kg.py')
stage.SOURCE = ROOT
stage.SNAPSHOT = SNAPSHOT
sha256 = stage.sha256
require = stage.require


def read(name):
    return json.loads((HERE / name).read_text())


def write(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def verify_baseline(baseline):
    for label, record in baseline['maintained_roots'].items():
        root = Path(record['root'])
        for filename, key in [('graph.json', 'graph_sha256'),
                              ('GRAPH_REPORT.md', 'graph_report_sha256'),
                              ('manifest.json', 'manifest_sha256')]:
            require(sha256(root / 'graphify-out' / filename) == record[key],
                    f'{label}: maintained {filename} changed')
        require(stage.snapshot_inventory(root) == record['dated_snapshots'],
                f'{label}: dated snapshots changed')
        require(stage.git(root, 'status', '--short').decode().splitlines() == record['git_status_exact'],
                f'{label}: unrelated working-tree status changed')
    for name, expected in baseline['wiki_hashes'].items():
        require(sha256(stage.MAINTAINED / 'wiki' / name) == expected,
                f'maintained wiki changed: {name}')


def frozen_selection():
    return stage.load_selection(HERE / 'selection_lock.json', REQUIRED_PATHS)


def stage_update():
    baseline, lock = read('baseline.json'), frozen_selection()
    verify_baseline(baseline)
    paths = set(lock['selected_source_sha256'])
    result = stage.stage_selected(lock, paths, paths, STAGING)
    verify_baseline(baseline)
    frozen_selection()
    result.update(status='STAGED_ONLY_NO_MAINTAINED_WRITES',
                  baseline_sha256=sha256(HERE / 'baseline.json'),
                  selection_lock_sha256=sha256(HERE / 'selection_lock.json'),
                  source_extraction_scope=sorted(paths),
                  extraction_limits=['Selected Python AST only; other evidence hash-bound only.',
                                     'Fortran cross-file CALL extraction is partial.',
                                     'Graph freshness is not runtime or scientific validation.'])
    write('stage_receipt.json', result)


def publish_update():
    baseline, lock = read('baseline.json'), frozen_selection()
    receipt, review = read('stage_receipt.json'), read('stage_review.json')
    require(review.get('status') == 'GO' and
            review.get('stage_receipt_sha256') == sha256(HERE / 'stage_receipt.json'),
            'agent-team graph stage review must bind the exact receipt')
    require(receipt['baseline_sha256'] == sha256(HERE / 'baseline.json') and
            receipt['selection_lock_sha256'] == sha256(HERE / 'selection_lock.json'),
            'stage baseline or selection changed')
    require(receipt.get('status') == 'STAGED_ONLY_NO_MAINTAINED_WRITES' and
            receipt.get('source_extraction_scope') == sorted(REQUIRED_PATHS),
            'graph stage status or extraction scope is invalid')
    targets = []
    for label, root_record in baseline['maintained_roots'].items():
        root, source = Path(root_record['root']), Path(receipt['stage']) / label / 'graphify-out'
        hashes = receipt['corpora'][label]['snapshot_file_sha256']
        require(receipt['corpora'][label]['selected_source_sha256'] == lock['selected_source_sha256'],
                'stage source hashes changed')
        require(not (root / 'graphify-out' / SNAPSHOT).exists(), 'dated snapshot already exists')
        for name, expected in hashes.items():
            require(sha256(source / name) == expected and sha256(source / SNAPSHOT / name) == expected,
                    f'{label}: staged file changed: {name}')
            targets.append(dict(source=source / name, destination=root / 'graphify-out' / name,
                                kind='file', sha256=expected))
        targets.append(dict(source=source / SNAPSHOT, destination=root / 'graphify-out' / SNAPSHOT,
                            kind='directory', files=hashes))
    for name, expected in receipt['staged_wiki_sha256'].items():
        source = Path(receipt['stage']) / 'wiki' / name
        require(sha256(source) == expected, f'staged wiki changed: {name}')
        targets.append(dict(source=source, destination=stage.MAINTAINED / 'wiki' / name,
                            kind='file', sha256=expected))
    verify_baseline(baseline)
    backup = STAGING / 'publication-backup'
    require(not backup.exists(), 'preserve prior publication backup')
    publisher.publish(targets, backup, baseline, stage, SNAPSHOT)
    write('publish_receipt.json', dict(status='PUBLISHED_AND_READBACK_PASS',
          stage_receipt_sha256=sha256(HERE / 'stage_receipt.json'),
          stage_review_sha256=sha256(HERE / 'stage_review.json'),
          prior_snapshots_preserved=baseline['dated_snapshot_count_total'],
          targets=[dict(path=str(t['destination']), sha256=t.get('sha256'), files=t.get('files'))
                   for t in targets], rollback_backup=str(backup)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['stage', 'publish'])
    args = parser.parse_args()
    (stage_update if args.action == 'stage' else publish_update)()
