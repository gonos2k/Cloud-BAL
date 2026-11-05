#!/usr/bin/env python3
"""Check the immutable PR148 evidence using explicit preserved-path aliases."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_initial_boundaries_20261105'
PRIOR = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
MANIFEST_SHA = '2656c0cf58008b6f32bddb1c575a3273c169e164ff41fd06b732dc4eb5012f0b'
REVIEW_SHA = '8e9b836c2700383f3ca8012b73504564be8443fa460bf7ca4da8802e2f58a87c'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run():
    manifest = PRIOR / 'validation.json'
    if sha(manifest) != MANIFEST_SHA:
        raise ValueError("PR148 manifest changed")
    if sha(PRIOR / 'validation/final_index_review.json') != REVIEW_SHA:
        raise ValueError('PR148 final review changed')
    records = json.loads(manifest.read_text())['artifacts']
    if len(records) != 357:
        raise ValueError("PR148 artifact scope changed")
    aliases = {
        'README.md': BUNDLE / 'prior_versions/pr148/README.md',
        'docs/CURRENT_RESEARCH_STATUS.md': BUNDLE / 'prior_versions/pr148/CURRENT_RESEARCH_STATUS.md',
    }
    for name in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json'):
        aliases[f'graphify-out/{name}'] = ROOT / 'graphify-out/2026-11-05-thermo-cloud-path' / name
    checked = []
    for item in records:
        resolved = aliases.get(item['path'], ROOT / item['path'])
        if not resolved.is_file() or resolved.stat().st_size != item['size_bytes']:
            raise ValueError(f"PR148 missing/size mismatch: {item['path']}")
        if sha(resolved) != item['sha256']:
            raise ValueError(f"PR148 SHA mismatch: {item['path']}")
        checked.append({**item, 'resolved_path': str(resolved.relative_to(ROOT))})
    result = {'status': 'PASS', 'prior_manifest_sha256': MANIFEST_SHA,
              'prior_review_sha256': REVIEW_SHA, 'artifacts': 357,
              'additional_manifest_and_review': 2, 'source_sha256': sha(Path(__file__)),
              'checks': checked,
              'scope': 'PR148 immutable artifacts; current status and graph aliases use exact prior bytes.'}
    (BUNDLE / 'validation/pr148_artifact_audit.json').write_text(json.dumps(result, indent=2)+'\n')
    print('PASS357manifest artifacts plus2finalrecords; PR148 unchanged')


if __name__ == '__main__':
    run()
