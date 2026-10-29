#!/usr/bin/env python3
"""Check or publish the frozen CP02 WRF-first-call KG stage."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path('/var/tmp/cloudbal-cp02-wrf-first-call')
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
KG = SOURCE / 'docs/evidence/cp02_wrf_first_call_20261029/kg'
BASELINE = KG / 'baseline.json'
SELECTION = KG / 'selection_lock.json'
STAGE_RECEIPT = KG / 'stage_receipt.json'
ROOT_GO = KG / 'root_go.json'
OUT = Path('/var/tmp/cp02_wrf_first_call_kg_20261029')
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
WIKI_FILES = ('graph-report.md', 'graph-report-klaps50.md', 'graph-report-cloud-bal.md', 'index.md', 'log.md')
EXPECTED_SELECTED_PATHS = {
    'tools/cp02_wrf_first_call.py',
    'tests/test_cp02_wrf_first_call.py',
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def git_status(root: Path) -> list[str]:
    return subprocess.check_output(['git', '-C', str(root), 'status', '--short'], text=True).splitlines()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def snapshot_inventory(root: Path) -> dict:
    result = {}
    for folder in sorted((root / 'graphify-out').iterdir()):
        if folder.is_dir() and folder.name[:4].isdigit():
            result[folder.name] = {
                path.name: sha256(path)
                for path in sorted(folder.iterdir())
                if path.is_file()
            }
    return result


def relative_status_path(line: str) -> str:
    return line[3:].rstrip('/') if len(line) >= 4 else line


def status_without_publication_targets(lines: list[str], snapshot: str) -> list[str]:
    graph_paths = {f'graphify-out/{name}' for name in GRAPH_FILES}
    wiki_paths = {f'wiki/{name}' for name in WIKI_FILES}
    snapshot_path = f'graphify-out/{snapshot}'
    return [line for line in lines if relative_status_path(line) not in graph_paths | wiki_paths | {snapshot_path}]


def graph_stats(graph: dict) -> dict:
    return {
        'nodes': len(graph.get('nodes', [])),
        'edges': len(graph.get('links', graph.get('edges', []))),
        'communities': len({node.get('community') for node in graph.get('nodes', [])
                            if node.get('community') is not None}),
    }


def verify_receipts() -> tuple[dict, dict, Path]:
    require(subprocess.check_output(['graphify', '--version'], text=True).strip() == 'graphify 0.9.53',
            'publisher requires Graphify 0.9.53')
    require(BASELINE.is_file() and SELECTION.is_file() and STAGE_RECEIPT.is_file(),
            'baseline, frozen selection, or stage receipt is missing')
    baseline = json.loads(BASELINE.read_text())
    selection = json.loads(SELECTION.read_text())
    receipt = json.loads(STAGE_RECEIPT.read_text())
    require(baseline.get('dated_snapshot_count_total') == 190, 'prepared KG baseline must contain 190 snapshots')
    require(selection.get('status') == 'FROZEN' and selection.get('review_status') == 'GO',
            'source selection must be frozen and independently reviewed GO')
    require(set(selection.get('selected_source_sha256', {})) == EXPECTED_SELECTED_PATHS,
            'selection must contain exactly the two reviewed WRF-first-call Python paths')
    require(receipt.get('status') == 'STAGED_ONLY_NO_MAINTAINED_WRITES', 'stage is not publishable')
    require(receipt.get('graphify_version') == 'graphify 0.9.53', 'stage Graphify version mismatch')
    require(receipt.get('source_commit') == selection.get('source_commit'), 'stage/source commit mismatch')
    require(receipt.get('freeze_id') == selection.get('freeze_id'), 'stage/freeze ID mismatch')
    require(receipt.get('selected_source_sha256') == selection.get('selected_source_sha256'),
            'staged selected hashes differ from the frozen selection')
    require(receipt.get('baseline_sha256') == sha256(BASELINE), 'stage receipt does not bind this maintained-root baseline')
    require(receipt.get('selection_lock_sha256') == sha256(SELECTION), 'stage receipt does not bind this lock')
    require(receipt.get('maintained_roots_verified_unchanged') is True,
            'stage did not verify unchanged maintained roots')
    snapshot = receipt.get('snapshot')
    require(isinstance(snapshot, str) and snapshot.startswith('2026-10-29-cp02-wrf-first-call'),
            'unexpected frozen snapshot name')
    for path, expected in selection['selected_source_sha256'].items():
        source = SOURCE / path
        require(source.is_file() and not source.is_symlink() and sha256(source) == expected,
                f'frozen source hash changed: {path}')

    content = dict(receipt)
    stage_fingerprint = content.pop('stage_sha256', None)
    require(stage_fingerprint == canonical_sha256(content), 'stage receipt fingerprint mismatch')
    raw_run = Path(receipt['staging_directory'])
    require(not raw_run.is_symlink(), 'staging directory is symlinked')
    run = raw_run.resolve()
    require(run.parent == OUT.resolve() and run.is_dir(),
            'staging directory is outside the assigned temporary root or unsafe')
    wiki_hashes = receipt.get('staged_wiki_sha256', {})
    require(set(wiki_hashes) == set(WIKI_FILES), 'stage receipt wiki hash set is incomplete')
    for name, expected in wiki_hashes.items():
        require(sha256(run / 'wiki' / name) == expected, f'staged wiki file hash mismatch: {name}')

    for label in ('KLAPS50', 'Cloud-BAL'):
        record = receipt.get('corpora', {}).get(label)
        require(record is not None, f'missing staged corpus receipt: {label}')
        require(set(record.get('snapshot_file_hashes', {})) == set(GRAPH_FILES),
                f'{label} dated snapshot hash set is incomplete')
        stage_graph = run / label / 'graphify-out'
        for filename in GRAPH_FILES:
            expected = record['snapshot_file_hashes'][filename]
            require(sha256(stage_graph / filename) == expected, f'{label} staged graph artifact mismatch: {filename}')
            require(sha256(stage_graph / snapshot / filename) == expected,
                    f'{label} dated snapshot artifact mismatch: {filename}')
        graph = json.loads((stage_graph / 'graph.json').read_text())
        require(graph_stats(graph) == record.get('stats'), f'{label} staged graph counts differ from receipt')
    return baseline, receipt, run


def verify_maintained_before(baseline: dict, snapshot: str) -> None:
    require(snapshot_inventory(MAINTAINED) == baseline['maintained_roots']['KLAPS50']['dated_snapshots'],
            'KLAPS50 pre-publication snapshot inventory changed')
    require(snapshot_inventory(MAINTAINED / 'Cloud-BAL') == baseline['maintained_roots']['Cloud-BAL']['dated_snapshots'],
            'Cloud-BAL pre-publication snapshot inventory changed')
    require(sum(baseline['maintained_roots'][name]['dated_snapshot_count'] for name in ('KLAPS50', 'Cloud-BAL')) == 190,
            'baseline corpus snapshot counts do not sum to 190')
    for label, root in (('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED / 'Cloud-BAL')):
        prior = baseline['maintained_roots'][label]
        require(sha256(root / 'graphify-out/graph.json') == prior['graph_sha256'],
                f'{label} active graph changed since baseline capture')
        current_files = {path.name: sha256(path) for path in sorted((root / 'graphify-out').iterdir()) if path.is_file()}
        require(current_files == prior['graphify_top_level_file_sha256'],
                f'{label} Graphify top-level artifact state changed since baseline capture')
        require(git_status(root) == prior['git_status_exact'],
                f'{label} unrelated dirty state changed since baseline capture')
        require(not (root / 'graphify-out' / snapshot).exists(), f'{label} target dated snapshot already exists')
    for name, expected in baseline['wiki_sha256'].items():
        require(sha256(MAINTAINED / 'wiki' / name) == expected, f'maintained wiki changed since baseline capture: {name}')


def publication_targets(receipt: dict, run: Path) -> list[dict]:
    snapshot = receipt['snapshot']
    targets = []
    for label, root in (('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED / 'Cloud-BAL')):
        record = receipt['corpora'][label]
        stage_graph = run / label / 'graphify-out'
        for name in GRAPH_FILES:
            targets.append({
                'kind': 'file',
                'source': stage_graph / name,
                'destination': root / 'graphify-out' / name,
                'sha256': record['snapshot_file_hashes'][name],
            })
        targets.append({
            'kind': 'directory',
            'source': stage_graph / snapshot,
            'destination': root / 'graphify-out' / snapshot,
            'files': record['snapshot_file_hashes'],
        })
    for name, expected in receipt['staged_wiki_sha256'].items():
        targets.append({
            'kind': 'file',
            'source': run / 'wiki' / name,
            'destination': MAINTAINED / 'wiki' / name,
            'sha256': expected,
        })
    return targets


def verify_readback(baseline: dict, receipt: dict, run: Path) -> dict:
    snapshot = receipt['snapshot']
    readback = {}
    for label, root in (('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED / 'Cloud-BAL')):
        record = receipt['corpora'][label]
        graph_dir = root / 'graphify-out'
        graph = json.loads((graph_dir / 'graph.json').read_text())
        require(graph_stats(graph) == record['stats'], f'{label} published graph stats differ from stage')
        for name in GRAPH_FILES:
            expected = record['snapshot_file_hashes'][name]
            require(sha256(graph_dir / name) == expected, f'{label} active {name} readback mismatch')
            require(sha256(graph_dir / snapshot / name) == expected, f'{label} snapshot {name} readback mismatch')
        inventory = snapshot_inventory(root)
        old = baseline['maintained_roots'][label]['dated_snapshots']
        require(set(inventory) == set(old) | {snapshot}, f'{label} dated snapshot names changed unexpectedly')
        require({name: inventory[name] for name in old} == old, f'{label} prior dated snapshot was altered')
        require(inventory[snapshot] == record['snapshot_file_hashes'], f'{label} new dated snapshot differs from stage')
        readback[label] = {
            **record['stats'],
            'graph_sha256': sha256(graph_dir / 'graph.json'),
            'prior_snapshots_preserved': len(old),
            'dated_snapshots_after': len(inventory),
            'new_snapshot': snapshot,
            'snapshot_files': inventory[snapshot],
        }
    for name, expected in receipt['staged_wiki_sha256'].items():
        require(sha256(MAINTAINED / 'wiki' / name) == expected, f'published wiki readback mismatch: {name}')
    for label, root in (('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED / 'Cloud-BAL')):
        expected_status = status_without_publication_targets(
            baseline['maintained_roots'][label]['git_status_exact'], snapshot)
        actual_status = status_without_publication_targets(git_status(root), snapshot)
        require(actual_status == expected_status, f'{label} unrelated dirty state changed during publication')
    return readback


def atomic_copy(source: Path, destination: Path, temporary_suffix: str) -> None:
    temporary = destination.with_name(destination.name + temporary_suffix)
    require(not temporary.exists(), f'publication temporary path already exists: {temporary}')
    try:
        shutil.copy2(source, temporary)
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def apply_publication(targets: list[dict], receipt: dict, baseline: dict,
                      run: Path, root_go: dict, stage_receipt_sha: str) -> dict:
    backup = OUT / f'publish-backup-{receipt["freeze_id"]}'
    require(not backup.exists(), f'publication backup already exists: {backup}')
    backup.mkdir()
    files_to_restore = []
    new_directories = []
    for index, target in enumerate(targets):
        if target['kind'] == 'file':
            destination = target['destination']
            backup_file = backup / f'{index:02d}-{destination.name}'
            shutil.copy2(destination, backup_file)
            files_to_restore.append((backup_file, destination))

    try:
        for index, target in enumerate(targets):
            source, destination = target['source'], target['destination']
            if target['kind'] == 'file':
                atomic_copy(source, destination, f'.cp02-wrf-{index}.tmp')
            else:
                temporary = destination.with_name(destination.name + '.cp02-wrf.tmp')
                require(not temporary.exists(), f'snapshot temporary path already exists: {temporary}')
                shutil.copytree(source, temporary)
                os.replace(temporary, destination)
                new_directories.append(destination)
        readback = verify_readback(baseline, receipt, run)
        apply_receipt = {
            'schema': 'cp02_wrf_first_call_kg_apply_receipt_v1',
            'status': 'PUBLISHED_AND_READBACK_PASSED',
            'root_go': root_go['go'],
            'root_go_stage_receipt_sha256': root_go['stage_receipt_sha256'],
            'stage_receipt_sha256': stage_receipt_sha,
            'selection_lock_sha256': receipt['selection_lock_sha256'],
            'freeze_id': receipt['freeze_id'],
            'source_commit': receipt['source_commit'],
            'snapshot': receipt['snapshot'],
            'applied_at_utc': datetime.now(timezone.utc).isoformat(),
            'corpora': readback,
            'wiki_sha256': receipt['staged_wiki_sha256'],
            'preservation': {
                'prior_dated_snapshots_total': 190,
                'KLAPS50_prior_snapshots_preserved': 93,
                'Cloud-BAL_prior_snapshots_preserved': 97,
                'new_dated_snapshot_count_total': 192,
                'unrelated_dirty_state': 'preserved by exact filtered git-status readback',
            },
            'extraction_limits': receipt['extraction_limits'],
            'runtime_or_science_validation': 'not established by graph freshness',
        }
        receipt_path = KG / 'apply_receipt.json'
        require(not receipt_path.exists(), 'apply receipt already exists; refusing repeat publication')
        temporary_receipt = receipt_path.with_name(receipt_path.name + '.tmp')
        temporary_receipt.write_text(json.dumps(apply_receipt, indent=2, sort_keys=True) + '\n')
        os.replace(temporary_receipt, receipt_path)
        return apply_receipt
    except Exception:
        for directory in reversed(new_directories):
            if directory.exists():
                shutil.rmtree(directory)
        for backup_file, destination in reversed(files_to_restore):
            atomic_copy(backup_file, destination, '.rollback.tmp')
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-only', action='store_true')
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--root-go', type=Path)
    args = parser.parse_args()
    require((args.root_go is not None) == args.apply,
            '--apply requires --root-go; --check-only forbids --root-go')

    baseline, receipt, run = verify_receipts()
    verify_maintained_before(baseline, receipt['snapshot'])
    require(not (MAINTAINED / 'graphify-out' / receipt['snapshot']).exists()
            and not (MAINTAINED / 'Cloud-BAL/graphify-out' / receipt['snapshot']).exists(),
            'target dated snapshot already exists')
    targets = publication_targets(receipt, run)
    require(len(targets) == 13, 'publication target set must be exactly 13 files/directories')
    stage_sha = sha256(STAGE_RECEIPT)

    if args.check_only:
        print(json.dumps({
            'status': 'CHECK_ONLY_PASS_NO_WRITES',
            'source_commit': receipt['source_commit'],
            'freeze_id': receipt['freeze_id'],
            'stage_receipt_sha256': stage_sha,
            'baseline_dated_snapshot_count': 190,
            'expected_after_dated_snapshot_count': 192,
            'snapshot': receipt['snapshot'],
            'publication_targets': len(targets),
            'maintained_graphs_and_snapshots_match_baseline': True,
            'staged_artifacts_and_wiki_match_receipt': True,
            'writes_performed': False,
        }, indent=2))
        return

    root_go_path = args.root_go.resolve()
    require(root_go_path.is_file() and not root_go_path.is_symlink(), 'root GO record missing or unsafe')
    root_go = json.loads(root_go_path.read_text())
    require(root_go.get('go') == 'GO', 'root GO decision is not GO')
    require(root_go.get('stage_receipt_sha256') == stage_sha == sha256(STAGE_RECEIPT),
            'root GO is not bound to the exact current stage receipt hash')
    require(root_go.get('freeze_id') == receipt['freeze_id'], 'root GO freeze ID mismatch')
    if 'snapshot' in root_go:
        require(root_go['snapshot'] == receipt['snapshot'], 'root GO snapshot mismatch')
    require(isinstance(root_go.get('review'), str) and root_go['review'].strip(),
            'root GO review evidence is missing')
    readback = apply_publication(targets, receipt, baseline, run, root_go, stage_sha)
    print(json.dumps(readback, indent=2))


if __name__ == '__main__':
    main()
