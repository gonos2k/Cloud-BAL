#!/usr/bin/env python3
"""Independently read back KG publication and the PR160 preservation baseline."""
import base64,hashlib,json,subprocess,tempfile
from pathlib import Path
from capture_baseline import dated_inventory,sha256,MAINTAINED
ROOT=Path(__file__).resolve().parents[4]
KG=Path(__file__).resolve().parent
STAMP='2026-11-11-moment-feasibility'

def main():
    baseline=json.loads((KG/'baseline.json').read_text())
    pub=json.loads((KG/'publish_receipt.json').read_text()); copy=json.loads((KG/'source_copy_receipt.json').read_text())
    lock=json.loads((KG/'selection_lock.json').read_text());stage=json.loads((KG/'stage_receipt.json').read_text())
    assert pub['status']=='PUBLISHED_AND_READBACK_PASS' and copy['status']=='COPIED_AND_READBACK_PASS'
    assert copy['publish_receipt_sha256']==sha256(KG/'publish_receipt.json')
    assert pub['selection_lock_sha256']==sha256(KG/'selection_lock.json')
    targets={x['path']:x['sha256'] for x in pub['targets']};copies={x['path']:x['sha256'] for x in copy['targets']}
    assert len(targets)==28 and len(copies)==11 and all(targets.get(k)==v for k,v in copies.items())
    for path,digest in targets.items():
        p=Path(path);assert p.is_file() and not p.is_symlink() and sha256(p)==digest,path
    for key in ('selected_source_sha256','hash_only_sha256'):
        for path,digest in lock[key].items():assert sha256(ROOT/path)==digest,path
    counts={}
    for label,root in [('KLAPS50',MAINTAINED),('Cloud-BAL',MAINTAINED/'Cloud-BAL')]:
        old=baseline['maintained_roots'][label]; state=old['git_state']
        assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()==state['head']
        status=subprocess.check_output(['git','-C',str(root),'status','--porcelain=v1','-z'])
        if label=='Cloud-BAL':status=status.replace(f'?? graphify-out/{STAMP}/\0'.encode(),b'')
        assert status==base64.b64decode(state['status_porcelain_v1_z_base64']),label+' unrelated NUL status changed'
        inventory=dated_inventory(root);new=inventory.pop(STAMP)
        assert inventory==old['dated_snapshots'] and len(new)==3,label+' snapshot inventory'
        assert new==stage['corpora'][label]['snapshot_file_sha256'],label+' snapshot hashes'
        counts[label]=len(inventory)+1
    assert sum(counts.values())==268 and sha256(MAINTAINED/'AGENTS.md')==baseline['agents_sha256']
    previous=ROOT/'docs/evidence/physical_moment_handoff_20261110'; manifest=previous/'validation.json';idx=previous/'review/final_index_review.json'
    prior=json.loads((KG/'prior_audit.json').read_text());m=json.loads(manifest.read_text())
    assert prior['artifact_count']==len(m['artifacts'])==104
    assert sha256(manifest)==prior['manifest_sha256'] and sha256(idx)==prior['final_index_sha256']
    base=prior['base']
    with tempfile.TemporaryFile() as q:
        for item in m['artifacts']:q.write(f"{base}:{item['path']}\n".encode())
        q.seek(0);p=subprocess.Popen(['git','-C',str(ROOT),'cat-file','--batch'],stdin=q,stdout=subprocess.PIPE)
        for item in m['artifacts']:
            header=p.stdout.readline().decode().split();assert len(header)==3 and header[1]=='blob'
            remaining=int(header[2]);assert remaining==item['size_bytes'];h=hashlib.sha256()
            while remaining:
                chunk=p.stdout.read(min(remaining,1048576));assert chunk;h.update(chunk);remaining-=len(chunk)
            assert p.stdout.read(1)==b'\n' and h.hexdigest()==item['sha256'],item['path']
        assert p.wait()==0
    for name in ('graph.json','GRAPH_REPORT.md','manifest.json'):
        prior_row=next(x for x in m['artifacts'] if x['path']==f'graphify-out/{name}')
        assert sha256(ROOT/'graphify-out/2026-11-10-physical-moment-handoff'/name)==prior_row['sha256']
    result={'status':'GO','prior_snapshot_count':266,'current_snapshot_count':268,
       'current_snapshot_counts':counts,'prior_artifact_count':104,'selected_source_count':len(lock['selected_source_sha256']),
       'hash_only_count':len(lock['hash_only_sha256']), 'maintained_file_targets':17,'worktree_copy_targets':11,
       'publish_receipt_sha256':sha256(KG/'publish_receipt.json'),'source_copy_receipt_sha256':sha256(KG/'source_copy_receipt.json'),
       'selection_lock_sha256':sha256(KG/'selection_lock.json'),'checks':{
        'all_28_target_hashes':True,'all_11_source_copy_hashes':True,'all_266_prior_snapshots':True,
        'separate_new_snapshot_trios':True,'both_heads_and_unrelated_NUL_status':True,'agents_unchanged':True,
        'all_frozen_pins':True,'prior_104_committed_blobs':True,'prior_manifest_and_index':True,
        'prior_graph_trio_in_existing_snapshot':True},
       'scope':'Independent postpublication readback; graph freshness is not runtime or scientific validation.'}
    with (KG/'postpublish_independent_review.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print('PASS postpublication; SHA256',sha256(KG/'postpublish_independent_review.json'))
if __name__=='__main__':main()
