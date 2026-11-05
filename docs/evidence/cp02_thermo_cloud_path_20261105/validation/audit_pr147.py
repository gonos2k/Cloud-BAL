#!/usr/bin/env python3
"""Check the immutable PR147 evidence using explicit preserved-path aliases."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
PRIOR = ROOT / 'docs/evidence/cp02_failure_regimes_20261104'
MANIFEST_SHA = '544a2a8be361e02fac1db4cf9d109c9ba5e7804c48a525e4e47a7d6e06008b9a'
REVIEW_SHA = 'eb88bec4ef6797c22a208cc39e6bbb8c973e1cb91a39e270522d2ad7dd9830b9'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run():
    manifest = PRIOR / 'validation.json'
    if sha(manifest) != MANIFEST_SHA:
        raise ValueError("PR147 manifest changed")
    if sha(PRIOR / 'validation/final_index_review.json') != REVIEW_SHA:
        raise ValueError('PR147 final review changed')
    records = json.loads(manifest.read_text())['artifacts']
    if len(records) != 161:
        raise ValueError("PR147 artifact scope changed")
    aliases = {
        'README.md': BUNDLE / 'prior_versions/pr147/README.md',
        'docs/CURRENT_RESEARCH_STATUS.md': BUNDLE / 'prior_versions/pr147/CURRENT_RESEARCH_STATUS.md',
    }
    for name in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json'):
        aliases[f'graphify-out/{name}'] = ROOT / 'graphify-out/2026-11-04-failure-regimes' / name
    checked = []
    for item in records:
        resolved = aliases.get(item['path'], ROOT / item['path'])
        if not resolved.is_file() or resolved.stat().st_size != item['size_bytes']:
            raise ValueError(f"PR147 missing/size mismatch: {item['path']}")
        if sha(resolved) != item['sha256']:
            raise ValueError(f"PR147 SHA mismatch: {item['path']}")
        checked.append({**item, 'resolved_path': str(resolved.relative_to(ROOT))})
    result = {'status': 'PASS', 'prior_manifest_sha256': MANIFEST_SHA,
              'prior_review_sha256': REVIEW_SHA, 'artifacts': 161,
              'additional_manifest_and_review': 2, 'source_sha256': sha(Path(__file__)),
              'checks': checked,
              'scope': 'PR147 immutable artifacts; current status and graph aliases use exact prior bytes.'}
    (BUNDLE / 'validation/pr147_artifact_audit.json').write_text(json.dumps(result, indent=2)+'\n')
    print('PASS161manifest artifacts plus2finalrecords; PR147 unchanged')


if __name__ == '__main__':
    run()
