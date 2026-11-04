#!/usr/bin/env python3
"""Publish one frozen B1 state-path KG stage after an external root GO.

This file is intentionally a prepared publisher only. It is not invoked by
the preparation or review steps. Publication requires the separately reviewed
stage receipt, validation, review, and root authorization gates below.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import uuid
from pathlib import Path

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_state_path_20261104/Cloud-BAL')
KG = ROOT / 'docs/evidence/cp02_state_path_20261104/kg'
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
STAMP = '2026-11-04-b1-state-path'
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
REVIEW_PATH = KG / 'stage_review.json'
VALIDATION_PATH = KG / 'stage_validation.json'
PUBLISH_RECEIPT = KG / 'publish_receipt.json'
COPY_RECEIPT = KG / 'postpublish_copy_receipt.json'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_json(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), f'missing or unsafe JSON receipt: {path}')
    return json.loads(path.read_text(encoding='utf-8'))


def import_prepare_helper():
    path = KG / 'prepare_kg.py'
    spec = importlib.util.spec_from_file_location('b1_state_path_prepare_kg', path)
    require(spec is not None and spec.loader is not None, f'cannot load preparation helper: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_target(path: Path, target: dict) -> None:
    require(not path.is_symlink(), f'refuse symlink target: {path}')
    if target['kind'] == 'file':
        require(path.is_file() and sha256(path) == target['hashes'], f'file hash mismatch: {path}')
        return
    require(path.is_dir(), f'missing snapshot directory: {path}')
    entries = list(path.iterdir())
    require(all(item.is_file() and not item.is_symlink() for item in entries),
            f'snapshot contains a non-file or symlink: {path}')
    files = {item.name for item in entries}
    require(files == set(target['hashes']), f'snapshot file scope mismatch: {path}')
    require(all((path / name).is_file() and not (path / name).is_symlink() and
                sha256(path / name) == expected for name, expected in target['hashes'].items()),
            f'snapshot content mismatch: {path}')


def verify_stage_and_reviews(helper, baseline: dict, lock: dict, receipt: dict,
                             validation: dict, review: dict) -> Path:
    require(review.get('status') == 'GO' and review.get('review_status') == 'GO',
            'independent staged review must be GO')
    require(review.get('stage_receipt_sha256') == sha256(KG / 'stage_receipt.json'),
            'review does not bind the current stage receipt')
    require(review.get('stage_validation_sha256') == sha256(VALIDATION_PATH),
            'review does not bind the current stage validation')
    require(review.get('selection_lock_sha256') == sha256(KG / 'selection_lock.json'),
            'review does not bind the current selection lock')
    require(receipt.get('status') == 'STAGED_ONLY_NO_MAINTAINED_WRITES',
            'stage receipt is not an isolated stage-only result')
    require(receipt.get('maintained_roots_written') is False,
            'staging receipt claims maintained-root writes')
    require(receipt.get('snapshot') == STAMP and receipt.get('dated_snapshots_preserved') == 234,
            'staging receipt has the wrong snapshot label or baseline count')
    require(receipt.get('baseline_sha256') == sha256(KG / 'baseline.json') ==
            lock.get('baseline_sha256'), 'stage/lock/baseline SHA-256 values disagree')
    require(receipt.get('selection_lock_sha256') == sha256(KG / 'selection_lock.json'),
            'stage receipt does not bind the selection lock')
    required_count = len(helper.REQUIRED_PATHS)
    require(receipt.get('source_extraction_scope') == sorted(helper.REQUIRED_PATHS) and
            receipt.get('manifest_update_scope') == sorted(helper.REQUIRED_PATHS),
            f'stage source or manifest-update scope differs from the reviewed {required_count}-path selection')
    require(set(lock.get('selected_source_sha256', {})) == helper.REQUIRED_PATHS,
            'selection lock does not name exactly the selected source paths')
    require(lock.get('source_commit') == subprocess.check_output(
        ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        'source worktree HEAD changed after freeze')
    require(validation.get('status') == 'PASS_STAGED_ONLY' and
            validation.get('maintained_roots_written') is False,
            'independent stage validation is not PASS_STAGED_ONLY')
    checks = validation.get('checks')
    require(isinstance(checks, dict) and checks and
            all(isinstance(value, dict) and value.get('pass') is True for value in checks.values()),
            'one or more independent stage validation checks failed or are missing')
    require(validation.get('baseline_sha256') == receipt['baseline_sha256'] and
            validation.get('stage_receipt_sha256') == sha256(KG / 'stage_receipt.json') and
            validation.get('selection_lock_sha256') == sha256(KG / 'selection_lock.json'),
            'stage validation does not bind the current baseline, receipt, and lock')
    require(validation.get('maintained_snapshot_count') == 234 and
            validation.get('source_pin_count') == required_count,
            'stage validation has unexpected prior snapshot or selected-source counts')
    require(review.get('baseline_sha256') == receipt['baseline_sha256'],
            'stage review baseline binding differs')
    for relative, expected in {**lock['selected_source_sha256'], **lock['hash_only_sha256']}.items():
        source = ROOT / relative
        require(source.is_file() and not source.is_symlink() and sha256(source) == expected,
                f'frozen source/hash-only pin changed: {relative}')
    require(receipt.get('hash_only_sha256') == lock.get('hash_only_sha256'),
            'stage receipt hash-only inventory differs from the frozen selection lock')
    helper.verify_baseline(baseline)
    stage = Path(receipt['stage'])
    require(stage.is_dir() and not stage.is_symlink(), f'stage directory is missing or unsafe: {stage}')
    require(review.get('stage') == str(stage) and validation.get('stage') == str(stage),
            'review/validation point to a different isolated stage')
    require(validation.get('target_count') == 13 and review.get('staged_target_count') == 13,
            'expected eight graph/snapshot targets and five wiki targets')
    return stage


def verify_wiki_old_content(helper, stage: Path, receipt: dict) -> None:
    old_wiki = MAINTAINED / 'wiki'
    new_wiki = stage / 'wiki'
    require(set(receipt['staged_wiki_sha256']) == set(helper.WIKI_FILES),
            'stage receipt does not contain exactly the five wiki mirrors')
    wiki_entries = list(new_wiki.iterdir())
    require(all(path.is_file() and not path.is_symlink() for path in wiki_entries) and
            {path.name for path in wiki_entries} == set(helper.WIKI_FILES),
            'staged wiki file set differs from the five frozen mirrors')
    for name in helper.WIKI_FILES:
        target = {'kind': 'file', 'hashes': receipt['staged_wiki_sha256'][name]}
        verify_target(new_wiki / name, target)
    require((new_wiki / 'graph-report-klaps50.md').read_bytes() ==
            (stage / 'KLAPS50/graphify-out/GRAPH_REPORT.md').read_bytes(),
            'KLAPS50 report mirror differs from staged graph report')
    require((new_wiki / 'graph-report-cloud-bal.md').read_bytes() ==
            (stage / 'Cloud-BAL/graphify-out/GRAPH_REPORT.md').read_bytes(),
            'Cloud-BAL report mirror differs from staged graph report')

    old_report = (old_wiki / 'graph-report.md').read_text(encoding='utf-8').splitlines()
    new_report = (new_wiki / 'graph-report.md').read_text(encoding='utf-8').splitlines()
    row_prefixes = ('| KLAPS50 |', '| Cloud-BAL |')
    old_rows = {prefix: [line for line in old_report if line.startswith(prefix)] for prefix in row_prefixes}
    new_rows = {prefix: [line for line in new_report if line.startswith(prefix)] for prefix in row_prefixes}
    require(all(len(old_rows[prefix]) == len(new_rows[prefix]) == 1 for prefix in row_prefixes),
            'graph report index must update one row for each maintained corpus')
    require([line for line in old_report if not line.startswith(row_prefixes)] ==
            [line for line in new_report if not line.startswith(row_prefixes)],
            'graph report index changed content outside the two corpus rows')

    old_index = (old_wiki / 'index.md').read_text(encoding='utf-8')
    new_index = (new_wiki / 'index.md').read_text(encoding='utf-8')
    marker = '## Graph snapshot'
    require(old_index.count(marker) == new_index.count(marker) == 1,
            'wiki index must contain one Graph snapshot section')

    def outside_snapshot(text: str) -> tuple[str, str]:
        start = text.index(marker)
        end = text.find('\n## ', start + len(marker))
        if end < 0:
            end = len(text)
        prefix, suffix = text[:start], text[end:]
        import re
        prefix, count = re.subn(r'(?m)^(date_modified:\s*)[^\r\n]+', r'\1<DATE>', prefix, count=1)
        require(count == 1, 'wiki index date_modified field is missing or ambiguous')
        return prefix, suffix

    require(outside_snapshot(old_index) == outside_snapshot(new_index),
            'wiki index changed content outside its dated Graph snapshot section')

    old_log = (old_wiki / 'log.md').read_bytes()
    new_log = (new_wiki / 'log.md').read_bytes()
    require(new_log.startswith(old_log), 'staged wiki log did not preserve the full old log as a byte prefix')
    suffix = new_log[len(old_log):]
    heading = f'\n## [{STAMP[:10]}] kg-update | B1 state path\n'.encode()
    require(suffix.startswith(heading) and suffix.count(heading) == 1,
            'wiki log must append exactly one B1 state-path section after the old bytes')


def make_targets(helper, stage: Path, receipt: dict) -> list[dict]:
    targets = []
    for label, destination in (('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED / 'Cloud-BAL')):
        graph = stage / label / 'graphify-out'
        hashes = receipt['corpora'][label]['snapshot_file_sha256']
        require(set(hashes) == set(GRAPH_FILES), f'{label} snapshot must contain exactly the active graph trio')
        for name in GRAPH_FILES:
            targets.append({'src': graph / name, 'dst': destination / 'graphify-out' / name,
                            'hashes': hashes[name], 'kind': 'file'})
        snapshot = graph / STAMP
        targets.append({'src': snapshot, 'dst': destination / 'graphify-out' / STAMP,
                        'hashes': hashes, 'kind': 'directory'})
    wiki = stage / 'wiki'
    for name in helper.WIKI_FILES:
        targets.append({'src': wiki / name, 'dst': MAINTAINED / 'wiki' / name,
                        'hashes': receipt['staged_wiki_sha256'][name], 'kind': 'file'})
    require(len(targets) == 13, f'expected 13 publication targets, got {len(targets)}')
    return targets


def make_source_worktree_targets(stage: Path, baseline: dict, receipt: dict) -> list[dict]:
    graph = stage / 'Cloud-BAL/graphify-out'
    hashes = receipt['corpora']['Cloud-BAL']['snapshot_file_sha256']
    expected_active = baseline['maintained_roots']['Cloud-BAL']['active_graph_trio_sha256']
    targets = []
    for name in GRAPH_FILES:
        destination = ROOT / 'graphify-out' / name
        require(destination.is_file() and not destination.is_symlink() and
                sha256(destination) == expected_active[name],
                f'source worktree active graph is not at its prepublication baseline: {destination}')
        targets.append({'src': graph / name, 'dst': destination,
                        'hashes': hashes[name], 'kind': 'file'})
    snapshot = ROOT / 'graphify-out' / STAMP
    require(not snapshot.exists() and not snapshot.is_symlink(),
            f'source worktree dated snapshot already exists: {snapshot}')
    targets.append({'src': graph / STAMP, 'dst': snapshot, 'hashes': hashes, 'kind': 'directory'})
    return targets


def unrelated_status(label: str, lines: list[str], helper) -> list[str]:
    allowed = {'graphify-out/graph.json', 'graphify-out/GRAPH_REPORT.md',
               'graphify-out/manifest.json', 'graphify-out/' + STAMP}
    if label == 'KLAPS50':
        allowed.update('wiki/' + name for name in helper.WIKI_FILES)
    result = []
    for line in lines:
        path = line[3:]
        if label == 'KLAPS50' and path.startswith('Cloud-BAL/'):
            path = path[len('Cloud-BAL/'):]
        if not any(path == target or path.startswith(target + '/') for target in allowed):
            result.append(line)
    return result


def atomic_replace(source: Path, destination: Path, kind: str) -> None:
    temporary = destination.with_name('.' + destination.name + '.b1-state-path-' + uuid.uuid4().hex)
    if kind == 'directory':
        shutil.copytree(source, temporary)
    else:
        shutil.copy2(source, temporary)
    temporary.replace(destination)


def rollback(undo: list[tuple[Path, Path, bool, str]]) -> None:
    for destination, saved, existed, kind in reversed(undo):
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        if existed:
            temporary = destination.with_name('.' + destination.name + '.rollback-' + uuid.uuid4().hex)
            if kind == 'directory':
                shutil.copytree(saved, temporary)
            else:
                shutil.copy2(saved, temporary)
            temporary.replace(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true',
                        help='required explicit root authorization after final stage review')
    args = parser.parse_args()
    require(args.publish, 'publication is disabled without explicit root --publish authorization')
    require(not PUBLISH_RECEIPT.exists() and not COPY_RECEIPT.exists(),
            'preserve any existing publication receipt; use a new audited attempt')
    helper = import_prepare_helper()
    baseline = load_json(KG / 'baseline.json')
    lock = load_json(KG / 'selection_lock.json')
    receipt = load_json(KG / 'stage_receipt.json')
    validation = load_json(VALIDATION_PATH)
    review = load_json(REVIEW_PATH)
    stage = verify_stage_and_reviews(helper, baseline, lock, receipt, validation, review)
    verify_wiki_old_content(helper, stage, receipt)
    helper.verify_baseline(baseline)
    targets = make_targets(helper, stage, receipt)
    source_targets = make_source_worktree_targets(stage, baseline, receipt)
    source_prior_inventory = helper.snapshot_inventory(ROOT)
    require(STAMP not in source_prior_inventory, 'source worktree snapshot label already exists')
    source_status_before = subprocess.check_output(
        ['git', '-C', str(ROOT), 'status', '--short'], text=True).splitlines()
    for target in targets + source_targets:
        verify_target(target['src'], target)
        require(not target['dst'].is_symlink(), f'refuse symlink destination: {target["dst"]}')
        if target['kind'] == 'directory':
            require(not target['dst'].exists(), f'refuse to overwrite existing dated snapshot: {target["dst"]}')
        else:
            require(target['dst'].is_file(), f'expected existing publication target: {target["dst"]}')

    baseline_status = {}
    for label, root in (('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED / 'Cloud-BAL')):
        raw = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain=v1', '-z'])
        expected = baseline['maintained_roots'][label]['git_state']['porcelain_v1_z_sha256']
        require(hashlib.sha256(raw).hexdigest() == expected, f'{label}: dirty-root baseline changed')
        baseline_status[label] = subprocess.check_output(
            ['git', '-C', str(root), 'status', '--short'], text=True).splitlines()

    backup = stage.parent / ('publish-backup-' + lock['freeze_id'])
    require(not backup.exists(), f'preserve existing publication backup: {backup}')
    backup.mkdir()
    undo: list[tuple[Path, Path, bool, str]] = []
    written_receipts: list[Path] = []
    wiki_evidence = KG / 'wiki'
    wiki_evidence_existed = wiki_evidence.exists()
    try:
        for index, target in enumerate(targets + source_targets):
            destination = target['dst']
            existed = destination.exists()
            saved = backup / str(index)
            undo.append((destination, saved, existed, target['kind']))
            if existed:
                if target['kind'] == 'directory':
                    shutil.copytree(destination, saved)
                else:
                    shutil.copy2(destination, saved)
            atomic_replace(target['src'], destination, target['kind'])
        for target in targets:
            verify_target(target['dst'], target)
        for label, root in (('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED / 'Cloud-BAL')):
            current = helper.snapshot_inventory(root)
            prior = baseline['maintained_roots'][label]['dated_snapshots']
            require({name: current.get(name) for name in prior} == prior,
                    f'{label}: one or more old dated snapshots changed')
            expected_count = 116 if label == 'KLAPS50' else 120
            require(len(current) == expected_count,
                    f'{label}: expected exactly {expected_count} dated snapshots after publication')
            status = subprocess.check_output(['git', '-C', str(root), 'status', '--short'], text=True).splitlines()
            require(unrelated_status(label, status, helper) ==
                    unrelated_status(label, baseline_status[label], helper),
                    f'{label}: unrelated dirty paths changed')

        source_current_inventory = helper.snapshot_inventory(ROOT)
        require({name: source_current_inventory.get(name) for name in source_prior_inventory} ==
                source_prior_inventory and len(source_current_inventory) == len(source_prior_inventory) + 1,
                'source worktree publication changed prior snapshots or added an unexpected snapshot')
        source_status_after = subprocess.check_output(
            ['git', '-C', str(ROOT), 'status', '--short'], text=True).splitlines()
        require(unrelated_status('Cloud-BAL', source_status_after, helper) ==
                unrelated_status('Cloud-BAL', source_status_before, helper),
                'Cloud-BAL source worktree unrelated dirty paths changed')

        publish = {
            'status': 'PUBLISHED_AND_READBACK_PASS',
            'snapshot': STAMP,
            'prior_snapshot_count': 234,
            'published_snapshot_count': 236,
            'stage_review_sha256': sha256(REVIEW_PATH),
            'stage_validation_sha256': sha256(VALIDATION_PATH),
            'stage_receipt_sha256': sha256(KG / 'stage_receipt.json'),
            'selection_lock_sha256': sha256(KG / 'selection_lock.json'),
            'baseline_sha256': sha256(KG / 'baseline.json'),
            'backup': str(backup),
            'targets': [{'path': str(item['dst']), 'kind': item['kind'], 'hashes': item['hashes']}
                        for item in targets],
        }
        PUBLISH_RECEIPT.write_text(json.dumps(publish, indent=2) + '\n', encoding='utf-8')
        written_receipts.append(PUBLISH_RECEIPT)
        copied = []
        for target in source_targets:
            verify_target(target['dst'], target)
            copied.append({'path': str(target['dst']), 'kind': target['kind'], 'hashes': target['hashes']})
        for name, expected in receipt['staged_wiki_sha256'].items():
            destination = wiki_evidence / name
            require(not destination.exists() and not destination.is_symlink(),
                    f'preserve existing wiki evidence copy: {destination}')
            destination.parent.mkdir(parents=True, exist_ok=True)
            written_receipts.append(destination)
            shutil.copy2(MAINTAINED / 'wiki' / name, destination)
            require(sha256(destination) == expected, f'wiki evidence readback mismatch: {destination}')
            copied.append({'path': str(destination), 'kind': 'file', 'hashes': expected})
        written_receipts.append(COPY_RECEIPT)
        COPY_RECEIPT.write_text(json.dumps({
            'status': 'PASS_ACTIVE_WORKTREE_AND_WIKI_READBACK',
            'publish_receipt_sha256': sha256(PUBLISH_RECEIPT), 'copied': copied,
        }, indent=2) + '\n', encoding='utf-8')
    except BaseException:
        for path in reversed(written_receipts):
            if path.exists():
                path.unlink()
        wiki_evidence = KG / 'wiki'
        if not wiki_evidence_existed and wiki_evidence.is_dir() and not any(wiki_evidence.iterdir()):
            wiki_evidence.rmdir()
        rollback(undo)
        raise
    print('PASS published 236 snapshots; active worktree and five wiki mirrors verified', sha256(PUBLISH_RECEIPT))


if __name__ == '__main__':
    main()
