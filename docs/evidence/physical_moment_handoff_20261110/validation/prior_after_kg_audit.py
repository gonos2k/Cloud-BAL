#!/usr/bin/env python3
"""Recheck all prior sealed artifacts after the derived graph update."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
B=ROOT/'docs/evidence/physical_moment_handoff_20261110'
P=ROOT/'docs/evidence/cp02_activation_path_20261110'
ALIASES={'README.md':'README.md','docs/CURRENT_RESEARCH_STATUS.md':'docs/CURRENT_RESEARCH_STATUS.md',
         **{f'graphify-out/{n}':f'graphify-out/{n}' for n in ('graph.json','GRAPH_REPORT.md','manifest.json')}}


def sha(p):
    with Path(p).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    output=B/'validation/prior_after_kg_audit.json'
    if output.exists():raise FileExistsError(output)
    original=json.loads((B/'kg/prior_audit.json').read_text())
    manifest=json.loads((P/'validation.json').read_text())
    assert original['status']=='PASS_PRIOR_3058_AND_FINAL_INDEX'
    assert manifest['artifact_count']==len(manifest['artifacts'])==3058
    assert sha(P/'validation.json')==original['manifest_sha256']
    assert sha(P/'review/final_index_review.json')==original['final_index_review_sha256']
    changed=[]
    for row in manifest['artifacts']:
        name=row['path'];p=ROOT/name
        if name in ALIASES:
            preserved=B/'kg/prior_aliases'/ALIASES[name]
            if sha(p)!=row['sha256']:changed.append(name)
        else:preserved=p
        assert preserved.is_file() and not preserved.is_symlink(),name
        assert preserved.stat().st_size==row['size_bytes'] and sha(preserved)==row['sha256'],name
    publication=json.loads((B/'kg/publish_receipt.json').read_text())
    assert publication['status']=='PUBLISHED_AND_READBACK_PASS'
    assert publication['new_maintained_snapshot_count']==266
    result={'status':'PASS','artifact_count':3058,'alias_count':5,'new_snapshot_count':266,
            'changed_current_paths':changed,'prior_manifest_sha256':sha(P/'validation.json'),
            'prior_final_index_review_sha256':sha(P/'review/final_index_review.json'),
            'prior_audit_sha256':sha(B/'kg/prior_audit.json'),
            'publish_receipt_sha256':sha(B/'kg/publish_receipt.json')}
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':'PASS','artifacts':3058,'aliases':5,'snapshots':266}))


if __name__=='__main__':main()
