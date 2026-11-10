#!/usr/bin/env python3
"""Recount the published graph inventories without modifying graph or wiki files."""
import hashlib
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[4]
KG = Path(__file__).resolve().parent
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
SNAPSHOT = '2026-11-10-pulse-path'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root):
    result = {}
    for folder in sorted((root/'graphify-out').iterdir()):
        if folder.is_dir() and folder.name[:4].isdigit():
            result[folder.name] = {
                path.relative_to(folder).as_posix(): sha256(path)
                for path in sorted(folder.rglob('*'))
                if path.is_file() and not path.is_symlink()
                and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.lock')
            }
    return result


def verify_target(row):
    path = Path(row['path'])
    if path.is_symlink():
        raise ValueError(f'symlink target: {path}')
    if row['kind'] == 'file':
        if not path.is_file() or sha256(path) != row['hashes']:
            raise ValueError(f'file target differs: {path}')
    elif row['kind'] == 'directory':
        if not path.is_dir() or {p.name for p in path.iterdir()} != set(row['hashes']):
            raise ValueError(f'directory target differs: {path}')
        for name, expected in row['hashes'].items():
            child = path/name
            if child.is_symlink() or not child.is_file() or sha256(child) != expected:
                raise ValueError(f'directory member differs: {child}')
    else:
        raise ValueError(f'unknown target kind: {row["kind"]}')


def main():
    summary = KG/'publication_summary.json'
    if summary.exists() or summary.is_symlink():
        raise FileExistsError(summary)
    baseline_path = KG/'baseline.json'
    lock_path = KG/'selection_lock.json'
    receipt_path = KG/'publish_receipt.json'
    copy_path = KG/'postpublish_copy_receipt.json'
    baseline, lock, receipt, copied = [json.loads(path.read_text()) for path in
                                      (baseline_path, lock_path, receipt_path, copy_path)]
    if (receipt['status'] != 'PUBLISHED_AND_READBACK_PASS' or
        copied['status'] != 'PASS_ACTIVE_WORKTREE_AND_WIKI_READBACK' or
        copied['publish_receipt_sha256'] != sha256(receipt_path)):
        raise ValueError('original publication receipts do not match')
    if (receipt['snapshot'] != SNAPSHOT or receipt['prior_snapshot_count'] != 258 or
        receipt['published_snapshot_count'] != 258 or len(receipt['targets']) != 13 or
        len(copied['copied']) != 9):
        raise ValueError('original publication receipt scope differs')
    for row in receipt['targets'] + copied['copied']:
        verify_target(row)
    counts = {}
    for label, root in (('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED/'Cloud-BAL')):
        current = inventory(root)
        prior = baseline['maintained_roots'][label]['dated_snapshots']
        if set(current) != set(prior) | {SNAPSHOT} or any(current[name] != value for name, value in prior.items()):
            raise ValueError(f'{label} prior snapshot inventory changed')
        counts[label] = len(current)
    if counts != {'KLAPS50': 128, 'Cloud-BAL': 132}:
        raise ValueError(f'unexpected snapshot counts: {counts}')
    selected = lock['selected_source_sha256']
    hash_only = lock['hash_only_sha256']
    if len(selected) != 3 or len(hash_only) != 178 or set(selected) & set(hash_only):
        raise ValueError('frozen selection scope differs')
    for name, expected in {**selected, **hash_only}.items():
        path = SOURCE/name
        if path.is_symlink() or not path.is_file() or sha256(path) != expected:
            raise ValueError(f'frozen pin differs: {name}')
    result = {
        'status': 'PASS_CORRECTED_PUBLICATION_SUMMARY',
        'snapshot': SNAPSHOT,
        'prior_snapshot_count': 258,
        'published_snapshot_count': sum(counts.values()),
        'snapshot_counts': counts,
        'publication_targets_verified': 13,
        'worktree_and_wiki_copy_targets_verified': 9,
        'selected_source_pins_verified': len(selected),
        'hash_only_pins_verified': len(hash_only),
        'original_publish_receipt_sha256': sha256(receipt_path),
        'original_copy_receipt_sha256': sha256(copy_path),
        'baseline_sha256': sha256(baseline_path),
        'selection_lock_sha256': sha256(lock_path),
        'reconciliation_script_sha256': sha256(Path(__file__)),
        'supersedes': {'field': 'published_snapshot_count', 'original_value': 258,
                       'corrected_value': sum(counts.values()),
                       'reason': 'The original publisher mistakenly repeated the prior total after adding one snapshot per corpus.'},
        'maintained_graph_or_wiki_written': False,
    }
    with summary.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'snapshot_counts': counts,
                      'published_snapshot_count': result['published_snapshot_count']}))


if __name__ == '__main__':
    main()
