#!/usr/bin/env python3
"""Bind final test evidence and replace only the provisional staged wiki log entry."""
import hashlib,json,os,tempfile
from pathlib import Path
from verify_baseline import verify
ROOT=Path(__file__).resolve().parents[4]
K=Path(__file__).resolve().parent
B=K.parent
MAINTAINED=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    verify()
    lock=json.loads((K/'selection_lock.json').read_text())
    stage_receipt=K/'stage_receipt.json'; stage=json.loads(stage_receipt.read_text())
    validation=B/'validation/validation_receipt.json'; results=json.loads(validation.read_text())
    review=K/'source_review.json';source=json.loads(review.read_text())
    assert results['status']=='PASS' and source['status']=='PASS_SOURCE_REVIEW_WITH_BROAD_VALIDATION_PENDING'
    assert stage['selection_lock_sha256']==source['selection_lock_sha256']==sha(K/'selection_lock.json')
    assert stage['selected_source_sha256']==source['source_sha256']==lock['selected_source_sha256']
    for path,digest in {**lock['selected_source_sha256'],**lock['hash_only_sha256']}.items():
        assert sha(ROOT/path)==digest,path
    for path,digest in lock['selected_source_sha256'].items():
        assert results['source_sha256'].get(path)==digest,path
    assert set(results['commands'])=={'unit','boundary','figures'}
    for item in results['commands'].values():
        assert item['exit_code']==0 and sha(ROOT/item['log'])==item['log_sha256']
    folder=Path(stage['stage']); staged_log=folder/'wiki/log.md'
    baseline_log=(MAINTAINED/'wiki/log.md').read_bytes(); old=staged_log.read_bytes()
    assert old.startswith(baseline_log) and b'kg-update | moment feasibility' in old[len(baseline_log):]
    entry='\n## [2026-11-11] kg-update | moment feasibility\n'
    entry+=f"- Source base `{lock['source_commit']}`; selected Fortran/Python AST extraction, no corpus scan or prune.\n"
    for name in ('KLAPS50','Cloud-BAL'):
        d=stage['corpora'][name];before=d['before'];after=d['after']
        entry+=f"- {name}: 2026-11-11-moment-feasibility; {after['nodes']} nodes / {after['edges']} edges / {after['communities']} communities; delta nodes={after['nodes']-before['nodes']}, edges={after['edges']-before['edges']}, communities={after['communities']-before['communities']}.\n"
    entry+='- 11 reviewed source paths structurally extracted; supporting evidence hash-bound, document semantics not extracted.\n'
    entry+='- Validation: fixed-source pinned Intel full unit, boundary and analytical figure/data reproduction passed; independent source review passed.\n'
    entry+='- Open items: analytical intervals do not establish REAL32 feasibility or first-use behavior; native first use, forecast, full domain water/energy closure and independent cases remain open.\n'
    entry+='- Fortran cross-file calls and external imports may be incomplete; graph freshness does not establish runtime or scientific validation.\n'
    provisional=K/'attempts/corrected_provisional_stage_receipt.json'
    with provisional.open('xb') as f:f.write(stage_receipt.read_bytes())
    try:
        staged_log.write_bytes(baseline_log+entry.encode())
        stage['staged_wiki_sha256']['log.md']=sha(staged_log)
        stage['final_validation_sha256']=sha(validation)
        stage['source_review_sha256']=sha(review)
        stage['provisional_stage_receipt_sha256']=sha(provisional)
        stage['finalization']='Final tested-source hashes and completed validation replace only provisional appended wiki entry; no maintained writes.'
        fd,tmp=tempfile.mkstemp(dir=K,prefix='.stage-receipt-')
        with os.fdopen(fd,'w') as f:json.dump(stage,f,indent=2,sort_keys=True);f.write('\n')
        os.replace(tmp,stage_receipt)
    except BaseException:
        staged_log.write_bytes(old)
        raise
    verify()
    print('PASS finalized isolated stage',sha(stage_receipt))
if __name__=='__main__':main()
