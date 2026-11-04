"""Audit immutable immediate prior manifests through explicit preserved versions."""
from pathlib import Path
import hashlib
import json
ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
CACHE = {}
def sha(path):
    if path not in CACHE:
        with path.open('rb') as stream:
            CACHE[path] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return CACHE[path]
prior_dirs = [ROOT/'docs/evidence/cp02_state_path_20261104/prior_versions',
              ROOT/'docs/evidence/cp02_b1_two_hour_process_20261103/prior_versions']
preserved = [p for d in prior_dirs for p in d.rglob('*') if p.is_file()]
checks = []
for label, key in [('recount_contract_20261103','indexed_files'),('cp02_b1_two_hour_process_20261103','artifacts')]:
    manifest = ROOT/'docs/evidence'/label/'validation.json'
    rows = json.loads(manifest.read_text())[key]
    assert len(rows) == {'recount_contract_20261103':58,'cp02_b1_two_hour_process_20261103':247}[label]
    for row in rows:
        path = ROOT/row['path']
        if row['path'] in {'graphify-out/graph.json','graphify-out/GRAPH_REPORT.md','graphify-out/manifest.json'}:
            candidates = [ROOT/'graphify-out'/date/path.name for date in ('2026-11-03-recount-contract','2026-11-03-b1-two-hour')]
        else:
            candidates = [path, *preserved]
        matches = [p for p in candidates if p.is_file() and p.stat().st_size == row['bytes'] and sha(p) == row['sha256']]
        assert matches, (label,row['path'])
        resolved = matches[0]
        checks.append({'manifest':str(manifest.relative_to(ROOT)),'original_path':row['path'],
                       'resolved_path':str(resolved.relative_to(ROOT)), 'sha256':row['sha256'],'size_bytes':row['bytes']})
result={'status':'PASS','prior_entries':len(checks),'checks':checks,'source_sha256':sha(Path(__file__))}
(HERE/'prior_manifest_audit.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print('PASS',len(checks),'prior artifacts; no prior manifest modified')
