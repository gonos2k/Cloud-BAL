#!/usr/bin/env python3
"""Verify preserved PR158 artifacts after the new graph publication."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_activation_path_20261110'
PRIOR = ROOT / 'docs/evidence/cp02_mp10_process_20261110'
ALIASES = {'README.md':'README.md','docs/CURRENT_RESEARCH_STATUS.md':'CURRENT_RESEARCH_STATUS.md',
           **{f'graphify-out/{n}':f'graphify-out/{n}' for n in ('graph.json','GRAPH_REPORT.md','manifest.json')}}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    output = BUNDLE/'validation/prior_after_kg_audit.json'
    if output.exists():
        raise FileExistsError(output)
    prior_audit = json.loads((BUNDLE/'kg/prior_audit.json').read_text())
    manifest = json.loads((PRIOR/'validation.json').read_text())
    index = json.loads((PRIOR/'review/final_index_review.json').read_text())
    assert sha(PRIOR/'validation.json') == prior_audit['manifest_sha256'] == index['manifest_sha256']
    assert sha(PRIOR/'review/final_index_review.json') == prior_audit['final_index_review_sha256']
    assert prior_audit['status'] == 'PASS_PRIOR_8656_AND_INDEX_PRESERVED'
    assert manifest['artifact_count'] == len(manifest['artifacts']) == 8656
    changed=[]
    for row in manifest['artifacts']:
        name=row['path'];path=ROOT/name
        if name in ALIASES:
            preserved=BUNDLE/'kg/prior_aliases'/ALIASES[name]
            if sha(path)!=row['sha256']:changed.append(name)
        else:
            preserved=path
        assert preserved.is_file() and not preserved.is_symlink(),name
        assert preserved.stat().st_size==row['size_bytes'] and sha(preserved)==row['sha256'],name
    publication=json.loads((BUNDLE/'kg/publish_receipt.json').read_text())
    assert publication['status']=='PUBLISHED_AND_READBACK_PASS'
    assert publication['published_snapshot_count']==264
    result={'status':'PASS','artifact_count':8656,'alias_count':5,'changed_current_paths':changed,
            'prior_manifest_sha256':sha(PRIOR/'validation.json'),
            'prior_final_index_review_sha256':sha(PRIOR/'review/final_index_review.json'),
            'initial_git_blob_audit_sha256':sha(BUNDLE/'kg/prior_audit.json'),
            'publication_sha256':sha(BUNDLE/'kg/publish_receipt.json'),
            'published_snapshot_count':264,'scope':'Every prior manifest artifact and both indices preserved; five explicitly aliased current status/graph paths may differ.'}
    with output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({'status':'PASS','artifacts':8656,'aliases':5,'snapshots':264}))


if __name__=='__main__':main()
