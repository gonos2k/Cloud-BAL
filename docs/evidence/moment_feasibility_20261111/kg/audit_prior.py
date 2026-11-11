#!/usr/bin/env python3
"""Audit PR160 sealed blobs and current files without duplicating large graphs."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
KG=Path(__file__).resolve().parent
BASE='d0366c8b45c230486d2eba36e85804de2d4f657b'
PRIOR=ROOT/'docs/evidence/physical_moment_handoff_20261110'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(1<<20),b''):h.update(data)
    return h.hexdigest()

def main():
    manifest=PRIOR/'validation.json'; index=PRIOR/'review/final_index_review.json'
    data=json.loads(manifest.read_text()); review=json.loads(index.read_text()); rows=data['artifacts']
    assert len(rows)==data['artifact_count']==104 and review['manifest_sha256']==sha(manifest)
    assert len({r['path'] for r in rows})==104
    assert subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()==BASE
    changed=[]
    with tempfile.TemporaryFile() as queries:
        for row in rows:
            path=row['path']; assert '\n' not in path and not path.startswith('-')
            queries.write(f'{BASE}:{path}\n'.encode())
        queries.seek(0)
        proc=subprocess.Popen(['git','-C',str(ROOT),'cat-file','--batch'],stdin=queries,stdout=subprocess.PIPE)
        for row in rows:
            path=row['path']; head=proc.stdout.readline().decode().split()
            assert len(head)==3 and head[1]=='blob',(path,head)
            size=int(head[2]); assert size==row['size_bytes'],path
            digest=hashlib.sha256()
            while size:
                block=proc.stdout.read(min(1<<20,size)); assert block
                digest.update(block);size-=len(block)
            assert proc.stdout.read(1)==b'\n' and digest.hexdigest()==row['sha256'],path
            current=ROOT/path
            assert current.is_file() and not current.is_symlink(),path
            if sha(current)!=row['sha256']:changed.append(path)
        assert proc.wait()==0
    for path in (manifest,index):
        rel=path.relative_to(ROOT).as_posix()
        blob=subprocess.check_output(['git','-C',str(ROOT),'show',f'{BASE}:{rel}'])
        assert hashlib.sha256(blob).hexdigest()==sha(path),rel
    previous=ROOT/'graphify-out/2026-11-10-physical-moment-handoff'
    for name in ('graph.json','GRAPH_REPORT.md','manifest.json'):
        item=next(r for r in rows if r['path']==f'graphify-out/{name}')
        assert sha(previous/name)==item['sha256'],name
    result={'status':'PASS_PRIOR_104_GIT_BLOBS_AND_INDEX','base':BASE,'manifest_sha256':sha(manifest),
      'final_index_sha256':sha(index),'artifact_count':104,'current_differences_at_capture':changed,
      'preservation':'Committed Git blobs preserve every artifact; prior dated snapshot preserves the active graph trio without duplicate graph copies.',
      'maintained_roots_written':False}
    with (KG/'prior_audit.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
