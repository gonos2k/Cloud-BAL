#!/usr/bin/env python3
"""Bind the small reviewed follow-up to its staged file set."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
B=Path('docs/evidence/phase_preconditions_20261111')
STAMP='2026-11-11-phase-preconditions'
OUTPUT=B/'manifest.json'
FINAL=B/'review/final_index_review.json'

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def bind(mapping):
    assert mapping
    for name,digest in mapping.items():assert sha(ROOT/name)==digest,name

def main():
    validation=json.loads((ROOT/B/'validation/receipt.json').read_text())
    assert validation['status']=='PASS' and validation['exit_code']==0
    bind(validation['source_sha256'])
    assert sha(ROOT/validation['log'])==validation['log_sha256']
    review=json.loads((ROOT/B/'review/source_review.json').read_text())
    assert review['status']=='PASS' and not review['findings']
    bind(review['reviewed_sha256'])
    kg=json.loads((ROOT/B/'kg/postpublish_review.json').read_text())
    assert kg['status']=='PASS' and kg['prior_snapshots']==268 and kg['current_snapshots']==270
    assert kg['checks'] and all(kg['checks'].values())
    assert sha(ROOT/B/'kg/publish_receipt.json')==kg['publish_receipt_sha256']
    assert sha(ROOT/B/'kg/source_copy_receipt.json')==kg['source_copy_receipt_sha256']
    publication=json.loads((ROOT/B/'kg/publish_receipt.json').read_text())
    assert publication['status']=='PUBLISHED_AND_READBACK_PASS'
    for item in publication['targets']:assert sha(item['path'])==item['sha256']
    prior=json.loads((ROOT/B/'kg/prior_audit.json').read_text())
    assert prior['status']=='PASS' and prior['prior_pr_files']==80 and prior['commit_trees_identical']
    changed=subprocess.check_output(['git','diff','--name-only','-z','HEAD'],cwd=ROOT).split(b'\0')
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=ROOT).split(b'\0')
    paths={Path(p.decode()) for p in changed+untracked if p}
    paths.update(p.relative_to(ROOT) for p in (ROOT/B).rglob('*') if p.is_file())
    paths.update(Path('graphify-out')/STAMP/n for n in ('graph.json','GRAPH_REPORT.md','manifest.json'))
    paths.discard(OUTPUT);paths.discard(FINAL)
    records={}
    for name in sorted(paths):
        if '__pycache__' in name.parts or name.suffix=='.pyc':continue
        p=ROOT/name
        assert p.is_file() and not p.is_symlink(),name
        records[str(name)]={'sha256':sha(p),'bytes':p.stat().st_size,'mode':'100755' if p.stat().st_mode&0o111 else '100644'}
    receipt={'status':'PASS','base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             'artifacts':records,'excluded':[str(OUTPUT),str(FINAL)],
             'scope':'Phase preconditions only; NI policy and native first use remain open.'}
    with (ROOT/OUTPUT).open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps({'status':'PASS','artifacts':len(records)}))

if __name__=='__main__':main()
