#!/usr/bin/env python3
"""Check PR149 evidence, resolving only explicitly preserved document/graph versions."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
BUNDLE=ROOT/'docs/evidence/cp02_grouped_forecast_20261105'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    manifest=ROOT/'docs/evidence/cp02_initial_boundaries_20261105/validation.json'
    data=json.loads(manifest.read_text())
    aliases={row['current_path']:row['preserved_path'] for row in json.loads((BUNDLE/'prior_versions/reconciliation.json').read_text())['files']}
    for name in ('GRAPH_REPORT.md','graph.json','manifest.json'):
        aliases['graphify-out/'+name]='graphify-out/2026-11-05-initial-boundaries/'+name
    checked=[]
    for row in data['artifacts']:
        actual=ROOT/row['path'];preserved=False
        if not actual.is_file() or sha(actual)!=row['sha256']:
            actual=ROOT/aliases.get(row['path'],row['path']);preserved=True
        if not actual.is_file() or sha(actual)!=row['sha256'] or actual.stat().st_size!=row['size_bytes']:
            raise ValueError('prior artifact mismatch: '+row['path'])
        checked.append({'original_path':row['path'],'verified_path':str(actual.relative_to(ROOT)),'preserved_version_used':preserved,'sha256':row['sha256']})
    if len(checked)!=data['artifact_count'] or len(checked)!=414:
        raise ValueError('PR149 evidence scope differs')
    out={'status':'PASS','source_manifest_sha256':sha(manifest),'artifact_count':len(checked),'artifacts':checked}
    with (BUNDLE/'validation/pr149_artifact_audit.json').open('x') as stream:
        json.dump(out,stream,indent=2);stream.write('\n')
    print('PASS:',len(checked),'prior artifacts')


if __name__=='__main__':main()
