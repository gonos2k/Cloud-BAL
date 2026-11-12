#!/usr/bin/env python3
"""Seal reviewed background-proposal source and evidence for explicit staging."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path('docs/evidence/ice_background_prior_20261112')
STAMP = '2026-11-12-ice-background-prior'
OUTPUT = BUNDLE / 'manifest.json'
FINAL = BUNDLE / 'review/final_index_review.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(name):
    return json.loads((ROOT / BUNDLE / name).read_text())


def bind(mapping):
    assert mapping
    for name, digest in mapping.items():
        assert sha(ROOT / name) == digest, name


def main():
    validation = read('validation/receipt.json')
    assert validation['status'] == 'PASS'
    assert validation['source_sha256_before'] == validation['source_sha256_after'] == validation['freeze_sha256_after']
    bind(validation['source_sha256_after'])
    for command in validation['commands']:
        assert command['exit_code'] == 0
        assert sha(ROOT / BUNDLE / 'validation' / command['log']) == command['log_sha256']
    review = read('review/source_review.json')
    assert review['status'] == 'PASS_NO_OPEN_FINDINGS' and not review['findings']
    bind(review['sha256'])
    kg = read('kg/postpublish_review.json')
    assert kg['status'] == 'PASS' and kg['checks'] and all(kg['checks'].values())
    assert kg['prior_snapshot_count'] == 276 and kg['current_snapshot_count'] == 278
    assert sha(ROOT / BUNDLE / 'kg/publish_receipt.json') == kg['publish_receipt_sha256']
    publication = read('kg/publish_receipt.json')
    assert publication['status'] == 'PUBLISHED_AND_READBACK_PASS' and len(publication['targets']) == 28
    for item in publication['targets']:
        assert sha(item['path']) == item['sha256']
    prior = read('kg/prior_audit.json')
    assert prior['status'] == 'PASS' and prior['prior_pr_files'] == 93 and prior['commit_trees_identical']
    changed = subprocess.check_output(['git', 'diff', '--name-only', '-z', 'HEAD'], cwd=ROOT).split(b'\0')
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT).split(b'\0')
    paths = {Path(p.decode()) for p in changed + untracked if p}
    paths.update(p.relative_to(ROOT) for p in (ROOT / BUNDLE).rglob('*') if p.is_file())
    paths.update(Path('graphify-out') / STAMP / name for name in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json'))
    paths.difference_update((OUTPUT, FINAL))
    records = {}
    for name in sorted(paths):
        if '__pycache__' in name.parts or name.suffix == '.pyc':
            continue
        path = ROOT / name
        assert path.is_file() and not path.is_symlink(), name
        records[str(name)] = {'sha256': sha(path), 'bytes': path.stat().st_size,
                              'mode': '100755' if path.stat().st_mode & 0o111 else '100644'}
    manifest = {'status': 'PASS', 'base': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'artifacts': records, 'excluded': [str(OUTPUT), str(FINAL)],
                'scope': 'Synthetic background proposal implementation; independent real NI unavailable; no actual initialization or forecast adoption.'}
    with (ROOT / OUTPUT).open('x') as stream:
        json.dump(manifest, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': 'PASS', 'artifacts': len(records)}))


if __name__ == '__main__':
    main()
