#!/usr/bin/env python3
"""Stage and publish only the reviewed extension's structural graph additions."""
import argparse
import importlib.util
import json
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
SNAPSHOT = '2026-10-30-snow-inline-gallery'
STAGING = Path('/var/tmp/cloudbal_snow_inline_gallery_kg_20261030')
PRIOR = ROOT / 'docs/evidence/snow_sensitivity_20261030/kg'
REQUIRED_PATHS = {
    'docs/evidence/snow_fine_20261030/build_report.py',
    'docs/evidence/snow_inline_gallery_20261030/kg/update_graphs.py',
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
ACTIVE_STAGE_ROOT = None
_original_stage_require = stage.require


def scoped_graph_require(condition, message):
    if condition:
        return _original_stage_require(condition, message)
    if 'graph update removed prior node IDs' in message and ACTIVE_STAGE_ROOT is not None:
        label = message.split(' ', 1)[0]
        maintained_root = stage.MAINTAINED if label == 'KLAPS50' else stage.MAINTAINED / 'Cloud-BAL'
        staged_graph = ACTIVE_STAGE_ROOT / label / 'graphify-out/graph.json'
        old_graph = json.loads((maintained_root / 'graphify-out/graph.json').read_text())
        new_graph = json.loads(staged_graph.read_text())
        old_nodes = {node['id']: node for node in old_graph.get('nodes', []) if 'id' in node}
        new_nodes = {node['id']: node for node in new_graph.get('nodes', []) if 'id' in node}
        expected_id = ('cloud_bal_docs_evidence_snow_fine_20261030_build_report_link'
                       if label == 'KLAPS50' else
                       'docs_evidence_snow_fine_20261030_build_report_link')
        removed = set(old_nodes) - set(new_nodes)
        source_prefix = 'Cloud-BAL/' if label == 'KLAPS50' else ''
        source_file = source_prefix + 'docs/evidence/snow_fine_20261030/build_report.py'
        replacement_id = expected_id.removesuffix('_link') + '_inline_image'
        valid = (removed == {expected_id} and
                 old_nodes[expected_id].get('label') == 'link()' and
                 old_nodes[expected_id].get('source_file') == source_file and
                 replacement_id in new_nodes and
                 new_nodes[replacement_id].get('label') == 'inline_image()' and
                 new_nodes[replacement_id].get('source_file') == source_file)
        if valid:
            return
        return _original_stage_require(False, f'{message}; unexpected source-backed removal: {sorted(removed)}')
    return _original_stage_require(condition, message)


stage.require = scoped_graph_require
original_write_staged_wiki = stage.write_staged_wiki


def write_staged_wiki(run, records, lock):
    hashes = original_write_staged_wiki(run, records, lock)
    for name in hashes:
        path = run / 'wiki' / name
        content = path.read_text()
        content = content.replace('snow sensitivity', 'inline PNG gallery')
        path.write_text(content)
    return {name: hashlib.sha256((run / 'wiki' / name).read_bytes()).hexdigest()
            for name in hashes}


stage.write_staged_wiki = write_staged_wiki


def refresh_staged_report(stage_root, extracted_paths):
    subprocess.run(
        ['graphify', 'cluster-only', str(stage_root), '--no-viz', '--no-label',
         '--graph', str(stage_root / 'graphify-out/graph.json')],
        cwd=stage_root, check=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    report = stage_root / 'graphify-out/GRAPH_REPORT.md'
    with report.open('a') as stream:
        stream.write('\n## inline PNG gallery scoped update\n')
        stream.write(f'- Only {len(extracted_paths)} frozen Python paths are structurally extracted.\n')
        stream.write('- Gallery Markdown, preserved prior versions, and review receipts are hash-bound only; document semantics are not extracted.\n')
        stream.write('- Graph freshness does not establish runtime or scientific validity.\n')
        stream.write('- The old `link()` node is replaced by `inline_image()` in the builder; no other prior node is removed.\n')
        stream.write('- Fortran cross-file CALL extraction is partial.\n')


stage.refresh_staged_report = refresh_staged_report
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
    global ACTIVE_STAGE_ROOT
    baseline, lock = read('baseline.json'), frozen_selection()
    verify_baseline(baseline)
    paths = set(lock['selected_source_sha256'])
    ACTIVE_STAGE_ROOT = STAGING / f"stage-{lock['freeze_id']}"
    result = stage.stage_selected(lock, paths, paths, STAGING)
    for label, record in result['corpora'].items():
        maintained_root = stage.MAINTAINED if label == 'KLAPS50' else stage.MAINTAINED / 'Cloud-BAL'
        old_graph = json.loads((maintained_root / 'graphify-out/graph.json').read_text())
        staged_graph = json.loads((ACTIVE_STAGE_ROOT / label / 'graphify-out/graph.json').read_text())
        old_ids = {node['id'] for node in old_graph.get('nodes', []) if 'id' in node}
        staged_ids = {node['id'] for node in staged_graph.get('nodes', []) if 'id' in node}
        removed_ids = sorted(old_ids - staged_ids)
        record['prior_node_ids_preserved'] = len(old_ids & staged_ids)
        record['prior_node_ids_removed'] = removed_ids
    result['source_backed_node_removals'] = [
        {'corpus': 'KLAPS50', 'id': 'cloud_bal_docs_evidence_snow_fine_20261030_build_report_link',
         'old': 'link()', 'replacement': 'inline_image()',
         'source': 'docs/evidence/snow_fine_20261030/build_report.py'},
        {'corpus': 'Cloud-BAL', 'id': 'docs_evidence_snow_fine_20261030_build_report_link',
         'old': 'link()', 'replacement': 'inline_image()',
         'source': 'docs/evidence/snow_fine_20261030/build_report.py'},
    ]
    verify_baseline(baseline)
    frozen_selection()
    result.update(status='STAGED_ONLY_NO_MAINTAINED_WRITES',
                  baseline_sha256=sha256(HERE / 'baseline.json'),
                  selection_lock_sha256=sha256(HERE / 'selection_lock.json'),
                  source_extraction_scope=sorted(paths),
                  hash_only_sha256=lock['hash_only_sha256'],
                  extraction_limits=['Selected Python AST only; other evidence hash-bound only.',
                                     'Only the obsolete build_report.link() node was removed, after verifying inline_image() in the same selected source file.',
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
