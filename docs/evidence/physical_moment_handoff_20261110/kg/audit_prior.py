#!/usr/bin/env python3
"""Audit all PR159 sealed artifacts against Git base and preserve five aliases."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
KG = Path(__file__).resolve().parent
BASE = 'dc68d30af29ae7fd3c3ecbf9fa9452a28b4a8d72'
PRIOR = ROOT / 'docs/evidence/cp02_activation_path_20261110'
ALIASES = {'README.md', 'docs/CURRENT_RESEARCH_STATUS.md',
           *(f'graphify-out/{n}' for n in ('graph.json','GRAPH_REPORT.md','manifest.json'))}

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    manifest_path = PRIOR / 'validation.json'
    index_path = PRIOR / 'review/final_index_review.json'
    manifest = json.loads(manifest_path.read_text())
    index = json.loads(index_path.read_text())
    assert index['manifest_sha256'] == sha(manifest_path)
    rows = manifest['artifacts']
    assert manifest['artifact_count'] == len(rows) == 3058
    assert len({row['path'] for row in rows}) == len(rows)
    assert subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip() == BASE
    assert ALIASES <= {row['path'] for row in rows}
    with tempfile.TemporaryFile() as queries:
        for row in rows:
            assert '\n' not in row['path'] and not row['path'].startswith('-')
            queries.write(f"{BASE}:{row['path']}\n".encode())
        queries.seek(0)
        process=subprocess.Popen(['git','-C',str(ROOT),'cat-file','--batch'],stdin=queries,stdout=subprocess.PIPE)
        changed=[]
        for row in rows:
            path=row['path']; header=process.stdout.readline().decode().split()
            assert len(header)==3 and header[1]=='blob', (path,header)
            size=int(header[2]); assert size==row['size_bytes'], path
            digest=hashlib.sha256(); alias=KG/'prior_aliases'/path if path in ALIASES else None
            if alias:
                alias.parent.mkdir(parents=True,exist_ok=True)
                target=alias.open('xb')
            remaining=size
            while remaining:
                chunk=process.stdout.read(min(1 << 20,remaining)); assert chunk
                digest.update(chunk)
                if alias: target.write(chunk)
                remaining-=len(chunk)
            if alias: target.close()
            assert process.stdout.read(1)==b'\n'
            assert digest.hexdigest()==row['sha256'],path
            preserved=alias if alias else ROOT/path
            assert preserved.stat().st_size==size and sha(preserved)==row['sha256'],path
            if sha(ROOT/path)!=row['sha256']:
                assert alias, f'unapproved prior artifact changed: {path}'
                changed.append(path)
        assert process.stdout.read()==b'' and process.wait()==0
    index_rel=index_path.relative_to(ROOT).as_posix()
    blob=subprocess.check_output(['git','-C',str(ROOT),'show',f'{BASE}:{index_rel}'])
    assert hashlib.sha256(blob).hexdigest()==sha(index_path)
    result={'status':'PASS_PRIOR_3058_AND_FINAL_INDEX','base':BASE,'manifest_sha256':sha(manifest_path),
            'final_index_review_sha256':sha(index_path),'artifact_count':len(rows),
            'aliases':{path:sha(KG/'prior_aliases'/path) for path in sorted(ALIASES)},
            'changed_current_paths':changed,'maintained_roots_written':False}
    with (KG/'prior_audit.json').open('x') as f:
        json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
