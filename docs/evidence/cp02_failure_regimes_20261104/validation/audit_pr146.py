#!/usr/bin/env python3
"""Check the immutable PR146 evidence using explicit preserved-path aliases."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_failure_regimes_20261104'
PRIOR = ROOT / 'docs/evidence/cp02_rain_number_process_20261104'
MANIFEST_SHA = '005e5aa2049c3ad3088698389840db90efb59a58d8a9a3254f590ef61e4010e4'
REVIEW_SHA = '85f4bad3662588ac9cb8665c734506e32b298cf9b10621286b48d866c43c78fd'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run():
    manifest = PRIOR / 'validation.json'
    if sha(manifest) != MANIFEST_SHA:
        raise ValueError("PR146 manifest changed")
    if sha(PRIOR / 'validation/final_index_review.json') != REVIEW_SHA:
        raise ValueError('PR146 final review changed')
    records = json.loads(manifest.read_text())['artifacts']
    if len(records) != 456:
        raise ValueError("PR146 artifact scope changed")
    aliases = {
        'README.md': BUNDLE / 'prior_versions/pr146/README.md',
        'docs/CURRENT_RESEARCH_STATUS.md': BUNDLE / 'prior_versions/pr146/CURRENT_RESEARCH_STATUS.md',
    }
    for name in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json'):
        aliases[f'graphify-out/{name}'] = ROOT / 'graphify-out/2026-11-04-rain-number-process' / name
    checked = []
    for item in records:
        resolved = aliases.get(item['path'], ROOT / item['path'])
        if not resolved.is_file() or resolved.stat().st_size != item['size_bytes']:
            raise ValueError(f"PR146 missing/size mismatch: {item['path']}")
        if sha(resolved) != item['sha256']:
            raise ValueError(f"PR146 SHA mismatch: {item['path']}")
        checked.append({**item, 'resolved_path': str(resolved.relative_to(ROOT))})
    result = {'status': 'PASS', 'prior_manifest_sha256': MANIFEST_SHA,
              'prior_review_sha256': REVIEW_SHA, 'artifacts': 456,
              'additional_manifest_and_review': 2, 'source_sha256': sha(Path(__file__)),
              'checks': checked,
              'scope': 'PR146 immutable artifacts; current status and graph aliases use exact prior bytes.'}
    (BUNDLE / 'validation/pr146_artifact_audit.json').write_text(json.dumps(result, indent=2)+'\n')
    print('PASS456manifest artifacts plus2finalrecords; PR146 unchanged')


if __name__ == '__main__':
    run()
