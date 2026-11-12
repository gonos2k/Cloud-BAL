#!/usr/bin/env python3
"""Seal reviewed first-call evidence and the explicit publication file set."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path('docs/evidence/first_call_water_budget_20261112')
STAMP = '2026-11-12-first-call-water-budget'
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
    assert validation['original_sha256_before'] == validation['original_sha256_after']
    assert validation['freeze_sha256_before'] == validation['freeze_sha256_after']
    bind(validation['original_sha256_after'])
    assert validation['source_sha256'] == validation['external_replay_source_sha256_before']
    assert sha(validation['external_replay_source']) == validation['external_replay_source_sha256_after'] == validation['source_sha256']
    review = read('review/source_review.json')
    assert review['status'] == 'PASS_NO_OPEN_FINDINGS' and not review['findings']
    bind(review['sha256'])
    package = read('validation/figure_package_receipt.json')
    assert package['status'] == 'PASS'
    bind(package['source_sha256'])
    assert sha(ROOT / BUNDLE / 'all_figures.zip') == package['zip_sha256']
    kg = read('kg/postpublish_review.json')
    assert kg['status'] == 'PASS' and kg['checks'] and all(kg['checks'].values())
    assert kg['prior_snapshot_count'] == 274 and kg['current_snapshot_count'] == 276
    assert sha(ROOT / BUNDLE / 'kg/publish_receipt.json') == kg['publish_receipt_sha256']
    publication = read('kg/publish_receipt.json')
    assert publication['status'] == 'PUBLISHED_AND_READBACK_PASS' and len(publication['targets']) == 28
    for item in publication['targets']:
        assert sha(item['path']) == item['sha256']
    prior = read('kg/prior_audit.json')
    assert prior['status'] == 'PASS' and prior['prior_pr_files'] == 89 and prior['commit_trees_identical']
    changed = subprocess.check_output(['git', 'diff', '--name-only', '-z', 'HEAD'], cwd=ROOT).split(b'\0')
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT).split(b'\0')
    paths = {Path(p.decode()) for p in changed + untracked if p}
    paths.update(p.relative_to(ROOT) for p in (ROOT / BUNDLE).rglob('*') if p.is_file())
    paths.update(Path('graphify-out') / STAMP / n for n in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json'))
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
                'scope': 'Same-source CONTROL first-call water accounting; no new initial partition, forecast or adoption.'}
    with (ROOT / OUTPUT).open('x') as stream:
        json.dump(manifest, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': 'PASS', 'artifacts': len(records)}))


if __name__ == '__main__':
    main()
