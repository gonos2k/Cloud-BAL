"""Verify all 450 PR145 artifacts through explicit immutable aliases."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BUNDLE = ROOT / 'docs/evidence/cp02_rain_number_process_20261104'
MANIFEST = ROOT / 'docs/evidence/cp02_state_path_20261104/validation.json'
MANIFEST_SHA = '38086a0cd1baaf8516f54fcacbedeeeb9f5d91ad25eb0bf1e4e805fac195df8c'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def run():
    assert sha(MANIFEST) == MANIFEST_SHA
    data = json.loads(MANIFEST.read_text())
    records = data['artifacts']
    assert data['artifact_count'] == len(records) == 450
    aliases = {
        'tools/initialize_b1_rain_psd_prior.py': BUNDLE / 'prior_versions/initialize_b1_rain_psd_prior.py',
        'tests/test_initialize_b1_rain_psd_prior.py': BUNDLE / 'prior_versions/test_initialize_b1_rain_psd_prior.py',
        'README.md': BUNDLE / 'prior_versions/pr145/README.md',
        'docs/CURRENT_RESEARCH_STATUS.md': BUNDLE / 'prior_versions/pr145/CURRENT_RESEARCH_STATUS.md',
    }
    for name in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json'):
        aliases[f'graphify-out/{name}'] = ROOT / 'graphify-out/2026-11-04-b1-state-path' / name
    checks = []
    for record in records:
        path = aliases.get(record['path'], ROOT / record['path'])
        assert path.is_file() and path.stat().st_size == record['size_bytes'], record['path']
        assert sha(path) == record['sha256'], record['path']
        checks.append({'original_path': record['path'], 'resolved_path': str(path.relative_to(ROOT)),
                       'size_bytes': record['size_bytes'], 'sha256': record['sha256']})
    result = {'status': 'PASS', 'prior_manifest_sha256': MANIFEST_SHA, 'artifacts': len(checks),
              'source_sha256': sha(Path(__file__)), 'checks': checks,
              'scope': 'Original PR145 manifest remains unchanged; updated source and current-graph paths resolve only to explicit preserved bytes.'}
    (HERE / 'pr145_artifact_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS 450 PR145 artifacts; manifest unchanged')


if __name__ == '__main__':
    run()
