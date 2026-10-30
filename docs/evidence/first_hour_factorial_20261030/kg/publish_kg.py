#!/usr/bin/env python3
"""Publish a reviewed first-hour factorial graph stage with rollback on write failure."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import uuid
from pathlib import Path

EVIDENCE = Path('/var/tmp/cloudbal-first-hour-factorial/docs/evidence/first_hour_factorial_20261030/kg')
BASELINE = EVIDENCE / 'baseline.json'
SELECTION = EVIDENCE / 'selection_lock.json'
STAGE_RECEIPT = EVIDENCE / 'stage_receipt.json'
STAGE_VALIDATION = EVIDENCE / 'stage_validation.json'
PUBLISH_GO = EVIDENCE / 'publish_go.json'
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
CORPORA = {'KLAPS50': MAINTAINED, 'Cloud-BAL': MAINTAINED / 'Cloud-BAL'}
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
WIKI_FILES = ('graph-report.md', 'graph-report-klaps50.md',
              'graph-report-cloud-bal.md', 'index.md', 'log.md')
SNAPSHOT = '2026-10-30-first-hour-factorial'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_stage_module():
    script = EVIDENCE / 'stage_kg.py'
    spec = importlib.util.spec_from_file_location('first_hour_factorial_stage', script)
    require(spec is not None and spec.loader is not None, 'cannot load stage verifier')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def status_path(line: str) -> str:
    return line[3:] if len(line) >= 4 else line


def unrelated_status(label: str, lines: list[str], snapshot: str) -> list[str]:
    allowed = {
        'graphify-out/graph.json',
        'graphify-out/GRAPH_REPORT.md',
        'graphify-out/manifest.json',
        f'graphify-out/{snapshot}',
    }
    if label == 'KLAPS50':
        allowed.update(f'wiki/{name}' for name in WIKI_FILES)
    prefix = 'Cloud-BAL/' if label == 'KLAPS50' else ''
    result = []
    for line in lines:
        path = status_path(line)
        relative = path[len(prefix):] if prefix and path.startswith(prefix) else path
        if relative not in allowed and not any(relative.startswith(item + '/') for item in allowed):
            result.append(line)
    return result


def stage_targets(receipt: dict) -> list[dict]:
    run = Path(receipt['stage'])
    snapshot = '2026-10-30-first-hour-factorial'
    targets = []
    for label, root in CORPORA.items():
        stage_graph = run / label / 'graphify-out'
        snapshot_dir = stage_graph / snapshot
        for name in GRAPH_FILES:
            targets.append({
                'source': stage_graph / name,
                'destination': root / 'graphify-out' / name,
                'sha256': receipt['corpora'][label]['snapshot_file_sha256'][name],
                'kind': 'file',
            })
        targets.append({
            'source': snapshot_dir,
            'destination': root / 'graphify-out' / snapshot,
            'files': receipt['corpora'][label]['snapshot_file_sha256'],
            'kind': 'directory',
        })
    for name in WIKI_FILES:
        targets.append({
            'source': run / 'wiki' / name,
            'destination': MAINTAINED / 'wiki' / name,
            'sha256': receipt['staged_wiki_sha256'][name],
            'kind': 'file',
        })
    return targets


def verify_stage(receipt: dict, validation: dict, selection: dict,
                 approval: dict, targets: list[dict]) -> None:
    require(receipt.get('status') == 'STAGED_ONLY_NO_MAINTAINED_WRITES',
            'stage is not an unapplied isolated stage')
    require(validation.get('status') == 'PASS_STAGED_ONLY', 'stage validation did not pass')
    require(approval.get('status') == 'GO' and approval.get('review_status') == 'GO',
            'publication requires an explicit GO approval file')
    require(approval.get('stage_receipt_sha256') == sha256(STAGE_RECEIPT),
            'publication GO does not bind the current stage receipt')
    require(approval.get('stage_validation_sha256') == sha256(STAGE_VALIDATION),
            'publication GO does not bind the current stage validation')
    require(selection.get('status') == 'FROZEN' and selection.get('review_status') == 'GO',
            'source selection is not frozen with review GO')
    require(selection.get('selected_source_sha256') == receipt['corpora']['KLAPS50']['selected_source_sha256'],
            'source selection differs from staged source hashes')
    require(receipt.get('source_extraction_scope') == sorted(selection['selected_source_sha256']),
            'stage extraction scope differs from exact frozen selection')
    require(set(receipt.get('manifest_update_scope', [])) ==
            set(selection['selected_source_sha256']),
            'stage manifest scope differs from frozen selection')
    for relative, expected in selection.get('hash_only_sha256', {}).items():
        source = Path('/var/tmp/cloudbal-first-hour-factorial') / relative
        require(source.is_file() and sha256(source) == expected,
                f'hash-only evidence changed after staging: {relative}')
    for target in targets:
        if target['kind'] == 'file':
            require(sha256(target['source']) == target['sha256'],
                    f'staged file hash mismatch: {target["source"]}')
        else:
            for name, expected in target['files'].items():
                require(sha256(target['source'] / name) == expected,
                        f'staged snapshot hash mismatch: {target["source"] / name}')


def publish(targets: list[dict], backup_root: Path, baseline: dict, stage,
            snapshot_name: str) -> None:
    backup_root.mkdir(parents=True)
    backups = []
    try:
        for index, target in enumerate(targets):
            source, destination = target['source'], target['destination']
            require(not destination.is_symlink(), f'refuse symlink destination: {destination}')
            destination.parent.mkdir(parents=True, exist_ok=True)
            existed = destination.exists()
            backup = backup_root / f'{index:02d}-{destination.name}'
            if existed:
                if target['kind'] == 'directory':
                    shutil.copytree(destination, backup)
                else:
                    shutil.copy2(destination, backup)
            backups.append((destination, backup, existed, target['kind']))
            temporary = destination.with_name(f'.{destination.name}.zero-candidate-{uuid.uuid4().hex}.tmp')
            if target['kind'] == 'directory':
                shutil.copytree(source, temporary)
            else:
                shutil.copy2(source, temporary)
            temporary.replace(destination)
        for target in targets:
            if target['kind'] == 'file':
                require(sha256(target['destination']) == target['sha256'],
                        f'published file readback mismatch: {target["destination"]}')
            else:
                for name, expected in target['files'].items():
                    require(sha256(target['destination'] / name) == expected,
                            f'published snapshot readback mismatch: {target["destination"] / name}')
        for label, root in CORPORA.items():
            current = stage.snapshot_inventory(root)
            prior = baseline['maintained_roots'][label]['dated_snapshots']
            require({name: current[name] for name in prior} == prior,
                    f'{label} prior dated snapshots changed during publication')
            before_status = baseline['maintained_roots'][label]['git_status_exact']
            after_status = stage.git(root, 'status', '--short').decode('utf-8').splitlines()
            require(unrelated_status(label, after_status, snapshot_name) ==
                    unrelated_status(label, before_status, snapshot_name),
                    f'{label} unrelated dirty status changed during publication')
    except Exception:
        for destination, backup, existed, kind in reversed(backups):
            if destination.exists():
                if destination.is_dir():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            if existed:
                temporary = destination.with_name(f'.{destination.name}.rollback-{uuid.uuid4().hex}.tmp')
                if kind == 'directory':
                    shutil.copytree(backup, temporary)
                else:
                    shutil.copy2(backup, temporary)
                temporary.replace(destination)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true', help='publish only with a bound publish_go.json')
    parser.add_argument('--go-file', type=Path, default=PUBLISH_GO)
    args = parser.parse_args()
    require(args.publish, 'no maintained files written; pass --publish only after root GO')

    baseline = json.loads(BASELINE.read_text())
    receipt = json.loads(STAGE_RECEIPT.read_text())
    validation = json.loads(STAGE_VALIDATION.read_text())
    selection = json.loads(SELECTION.read_text())
    approval = json.loads(args.go_file.read_text())
    targets = stage_targets(receipt)
    verify_stage(receipt, validation, selection, approval, targets)

    stage = load_stage_module()
    stage.load_selection(SELECTION, stage.REQUIRED_PATHS)
    stage.verify_baseline(baseline)
    snapshot_name = SNAPSHOT
    for root in CORPORA.values():
        require(not (root / 'graphify-out' / snapshot_name).exists(),
                f'target snapshot already exists: {root / "graphify-out" / snapshot_name}')

    backup_root = Path('/var/tmp/cloudbal_first_hour_factorial_kg_20261030') / 'final-publish-backup'
    require(not backup_root.exists(), f'preserve existing backup directory: {backup_root}')
    publish(targets, backup_root, baseline, stage, snapshot_name)
    result = {
        'status': 'PUBLISHED_AND_READBACK_PASS',
        'approval_sha256': sha256(args.go_file),
        'stage_receipt_sha256': sha256(STAGE_RECEIPT),
        'stage_validation_sha256': sha256(STAGE_VALIDATION),
        'published_targets': [
            {'path': str(t['destination']), 'kind': t['kind'],
             'sha256': t.get('sha256'), 'files': t.get('files')}
            for t in targets
        ],
        'prior_dated_snapshots_preserved': baseline['dated_snapshot_count_total'],
        'rollback_backup': str(backup_root),
    }
    output = EVIDENCE / 'publish_receipt.json'
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
