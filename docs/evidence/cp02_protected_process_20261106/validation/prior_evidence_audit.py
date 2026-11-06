#!/usr/bin/env python3
"""Verify all 225 artifacts sealed by the immediately prior failure-focus batch."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_protected_process_20261106'
PRIOR_MANIFEST = ROOT / 'docs/evidence/cp02_failure_focus_20261105/validation.json'
PRIOR_MANIFEST_SHA256 = '89bafb3a1a11f27c96ed63ca56fe395b36671a18dbb90f6dd9419749be3e4fae'
EXPECTED_ARTIFACTS = 225


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def preserved_aliases() -> dict[str, str]:
    aliases = {
        'README.md': 'docs/evidence/cp02_protected_process_20261106/prior_versions/README_before_protected_process.md',
        'docs/CURRENT_RESEARCH_STATUS.md': (
            'docs/evidence/cp02_protected_process_20261106/prior_versions/'
            'CURRENT_RESEARCH_STATUS_before_protected_process.md'),
    }
    aliases['tools/cp02_b1_failure_context.py'] = 'docs/evidence/cp02_protected_process_20261106/residual_fix/prior_versions/cp02_b1_failure_context.py'
    aliases['tests/test_cp02_b1_failure_context.py'] = 'docs/evidence/cp02_protected_process_20261106/residual_fix/prior_versions/test_cp02_b1_failure_context.py'
    snapshot = 'graphify-out/2026-11-05-failure-focus/'
    for name in ('GRAPH_REPORT.md', 'manifest.json', 'graph.json'):
        aliases[f'graphify-out/{name}'] = snapshot + name
    return aliases


def audit() -> dict:
    if not PRIOR_MANIFEST.is_file() or sha256(PRIOR_MANIFEST) != PRIOR_MANIFEST_SHA256:
        raise ValueError('PR151 grouped-forecast validation manifest changed')
    manifest = json.loads(PRIOR_MANIFEST.read_text(encoding='utf-8'))
    rows = manifest.get('artifacts', [])
    if (manifest.get('schema') != 'cp02_failure_focus_validation_v1'
            or manifest.get('artifact_count') != EXPECTED_ARTIFACTS
            or len(rows) != EXPECTED_ARTIFACTS):
        raise ValueError('prior PR151 artifact inventory differs from 225')
    aliases = preserved_aliases()
    checked = []
    seen = set()
    for row in rows:
        original = row['path']
        if original in seen:
            raise ValueError(f'duplicate path in prior manifest: {original}')
        seen.add(original)
        path = ROOT / original
        preserved = False
        if (not path.is_file() or path.is_symlink()
                or path.stat().st_size != row['size_bytes']
                or sha256(path) != row['sha256']):
            alias = aliases.get(original)
            if alias is None:
                raise ValueError(f'prior artifact changed without a declared preservation path: {original}')
            path = ROOT / alias
            preserved = True
        if (not path.is_file() or path.is_symlink()
                or path.stat().st_size != row['size_bytes']
                or sha256(path) != row['sha256']):
            raise ValueError(f'prior artifact bytes differ: {original}')
        checked.append({'original_path': original,
                        'verified_path': str(path.relative_to(ROOT)),
                        'preserved_version_used': preserved,
                        'size_bytes': row['size_bytes'],
                        'sha256': row['sha256']})
    if len(checked) != EXPECTED_ARTIFACTS:
        raise ValueError('prior artifact readback is incomplete')
    return {'schema': 'cp02_protected_process_prior_evidence_audit_v1',
            'status': 'PASS',
            'source_manifest_path': str(PRIOR_MANIFEST.relative_to(ROOT)),
            'source_manifest_sha256': PRIOR_MANIFEST_SHA256,
            'artifact_count': len(checked),
            'preserved_version_count': sum(row['preserved_version_used'] for row in checked),
            'artifacts': checked}


def main():
    output = BUNDLE / 'validation/prior_evidence_audit.json'
    if output.exists():
        raise FileExistsError(output)
    result = audit()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(f"PASS: {result['artifact_count']} prior artifacts; "
          f"{result['preserved_version_count']} resolved from preserved versions")


if __name__ == '__main__':
    main()
