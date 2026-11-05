#!/usr/bin/env python3
"""Independently audit actual phi/gap/prep/KDM pointer and word bridges."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
BUNDLE=ROOT/'docs/evidence/cp02_initial_boundaries_20261105'
RUNTIME=ROOT.parent/'runtime/gdb_parity'


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    result={'status':'PASS','scope':'Independent actual target pointer and raw-word bridge check, not a causal transport attribution.','targets':{}}
    for target,rank in (('p20183',5),('p17051',3)):
        arms={}
        for arm in ('B1','DM065'):
            root=RUNTIME/f'phi_{target}_01'/arm;receipt=json.loads((root/'phi_receipt.json').read_text());path=root/'phi_capture'/f'phi_rank{rank}.jsonl'
            if receipt['status']!='PASS_PHI_DISCOVERY' or sha(path)!=receipt['event_file_sha256']:raise ValueError('source receipt mismatch')
            events=[json.loads(x) for x in path.open()];gap=None;last_phi=None;last_prep=None;rows=[]
            for e in events:
                if e['event']=='gap_start':
                    if gap is not None:raise ValueError('overlapping gaps')
                    gap={'p_base':e['p_base'],'address':e['target_address'],'start':e['p_word'],'last':e['p_word'],'hits':0,'phi':None}
                elif e['event']=='gap_watch_after':
                    if gap is None or e['target_address']!=gap['address'] or e['pre_word']!=gap['last']:raise ValueError('watch continuity')
                    gap['last']=e['post_word'];gap['hits']+=1
                elif e['event']=='function_entry' and e.get('function')=='phi' and gap is not None:
                    if e['p_base']!=gap['p_base']:raise ValueError('phi base differs from watched calc P base')
                elif e['event']=='function_return' and e.get('function')=='phi' and gap is not None:
                    if e['p_base']!=gap['p_base']:raise ValueError('phi return base differs')
                    gap['phi']=e
                elif e['event']=='gap_end':
                    if gap is None or gap['phi'] is None or e['target_address']!=gap['address'] or e['initial_word']!=gap['start'] or e['final_word']!=gap['last'] or e['watch_events']!=gap['hits'] or e['last_phi_p_word']!=gap['phi']['fields']['p'] or e['last_phi_matches_prep']!=(e['last_phi_p_word']==e['final_word']):raise ValueError('gap bridge mismatch')
                    last_phi=gap['phi'];last_phi['_observed_gap_p']=e['final_word'];gap=None
                elif e['event']=='function_entry' and e.get('function')=='prep':
                    if last_phi is None or e['p_in_base']!=last_phi['p_base'] or e['fields']['p']!=last_phi['_observed_gap_p']:raise ValueError('phi/prep pointer or word mismatch')
                    last_prep={'entry':e}
                elif e['event']=='function_return' and e.get('function')=='prep':
                    if last_prep is None:raise ValueError('missing prep entry')
                    last_prep['return']=e
                elif e['event']=='function_entry' and e.get('function')=='kdm':
                    if last_prep is None or 'return' not in last_prep:raise ValueError('missing prep return')
                    a,b=last_prep['entry'],last_prep['return'];same_ptr=all(a[x]==e[y] for x,y in [('th_out_base','th_base'),('pii_out_base','pii_base'),('pf_out_base','p_base'),('qv_base','qv_base')]);same_words=all(b['fields'][x]==e['fields'][y] for x,y in [('th','th'),('pii','pii'),('pf','p')]) and a['fields']['qv']==e['fields']['qv']
                    if not same_ptr or not same_words:raise ValueError('prep/KDM pointer or word differs')
                    rows.append({'timestep':e['timestep'],'last_phi_P_matches_prep':last_phi['fields']['p']==a['fields']['p'],'prep_KDM_pointers_match':same_ptr,'prep_KDM_words_match':same_words})
                    last_phi=None;last_prep=None
            if gap is not None or [x['timestep'] for x in rows]!=[1,2,3,4]:raise ValueError('incomplete bridges')
            arms[arm]={'event_sha256':sha(path),'receipt_sha256':sha(root/'phi_receipt.json'),'bridges':rows}
        result['targets'][target]=arms
    out=BUNDLE/'native/phi_discovery/independent_bridge_audit.json';out.write_text(json.dumps(result,indent=2)+'\n');print(sha(out))


if __name__=='__main__':main()
