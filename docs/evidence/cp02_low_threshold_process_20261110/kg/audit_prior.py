#!/usr/bin/env python3
"""Verify every previous manifest artifact, including explicit mutable-file aliases."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
KG = Path(__file__).resolve().parent
BASE = '95a433ac5925ecd283bfdb8d2a02df257441821c'
PRIOR = ROOT / 'docs/evidence/cp02_ice_false_alarm_20261109'
ALIASES = {
    'README.md': KG / 'prior_aliases/README.md',
    'docs/CURRENT_RESEARCH_STATUS.md': KG / 'prior_aliases/CURRENT_RESEARCH_STATUS.md',
    **{f'graphify-out/{name}': ROOT / 'graphify-out/2026-11-09-ice-false-alarm' / name
       for name in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')},
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    manifest_path = PRIOR / 'validation.json'
    manifest_data = manifest_path.read_bytes()
    review_data = (PRIOR / 'review/final_index_review.json').read_bytes()
    review = json.loads(review_data)
    assert review['manifest_sha256'] == digest(manifest_data)
    manifest = json.loads(manifest_data)
    assert manifest['artifact_count'] == len(manifest['artifacts']) == 73
    assert len({a['path'] for a in manifest['artifacts']}) == 73
    head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    assert head == BASE, f'unexpected source HEAD {head}'
    changes = []
    for row in manifest['artifacts']:
        path = row['path']
        expected = row['sha256']
        # The prior committed object and the preserved current artifact must both match.
        original = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{BASE}:{path}'])
        assert len(original) == row['size_bytes'] and digest(original) == expected, path
        preserved_path = ALIASES.get(path, ROOT / path)
        preserved = preserved_path.read_bytes()
        assert len(preserved) == row['size_bytes'] and digest(preserved) == expected, str(preserved_path)
        current = (ROOT / path).read_bytes()
        if digest(current) != expected:
            assert path in ALIASES, f'unapproved previous artifact changed: {path}'
            changes.append({'path': path, 'current_sha256': digest(current),
                            'preserved_at': str(preserved_path.relative_to(ROOT))})
    for path, data in [(manifest_path, manifest_data), (PRIOR / 'review/final_index_review.json', review_data)]:
        original = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{BASE}:{path.relative_to(ROOT)}'])
        assert data == original, f'prior index changed: {path}'
    result = {'status': 'PASS_PRIOR_73_AND_INDEX_PRESERVED', 'base': BASE,
              'manifest_sha256': digest(manifest_data), 'final_index_review_sha256': digest(review_data),
              'artifact_count': 73, 'alias_count': len(ALIASES), 'changed_current_paths': changes,
              'maintained_roots_written': False}
    print(json.dumps(result, indent=2, sort_keys=True))

if __name__ == '__main__':
    main()
