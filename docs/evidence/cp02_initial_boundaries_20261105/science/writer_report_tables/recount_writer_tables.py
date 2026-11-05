#!/usr/bin/env python3
"""Tabulate actual paired writer operands, references and boundary bridges."""
import csv,hashlib,json,math,os,struct
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
SCIENCE=HERE.parent
PINS={'nr20330':'81136f351c4804be078761cbfc57a715ccd58bf24ffd1537cb4c180a1b3d475b',
      'nr20330max':'ae60a061371e6fae99ff352a61d4ae3f541e7d73422d2b81ee9853b4f7d58735',
      'p20183':'cd31c0400f17d7cdd94e9c4e91767f75ef25ed6bbab6959891cda767cc9576cd',
      'p17051':'c98855bfa798a6ed9e2cb007921f0a01f961dda12ab49caded34b65b395fa462'}

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def f32word(value):return struct.unpack('<f',bytes.fromhex(value))[0]

def write_csv(path,rows):
    names=list(dict.fromkeys(key for row in rows for key in row))
    with path.open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=names,lineterminator='\n');w.writeheader();w.writerows(rows)

def main():
    paths={target:SCIENCE/f'writer_{target}/analysis.json' for target in PINS}
    for t,p in paths.items():
        if sha(p)!=PINS[t]:raise ValueError('closed analysis differs: '+t)
    calls=[];bridges=[];first=[]
    for target,path in paths.items():
        data=json.loads(path.read_text())
        if data['status']!='PASS_ACTUAL_WRITER_ANALYSIS' or data['target']!=target:raise ValueError('analysis scope differs')
        seen={}
        for pair in data['paired_calls']:
            fn=pair['identity'][0]
            if fn not in ('rk','pressure','prep'):continue
            step=pair['identity'][1];key=(fn,step);seen[key]=seen.get(key,0)+1
            if fn!='rk' or pair['classification']['B1']=='KDM_NR_pointer_bound':
                changed={stage:[n for n,x in pair['paired_operands'][stage].items() if x['DM065_minus_B1']!=0] for stage in ('entry','return')}
                if any(changed.values()) and not any(r['target']==target and r['function']==fn for r in first):
                    first.append({'target':target,'function':fn,'candidate_timestep':step,'occurrence_within_step':seen[key],
                                  'rk_step':pair['identity'][3] if pair['identity'][3] is not None else '',
                                  'acoustic_iteration':pair['identity'][4] if pair['identity'][4] is not None else '',
                                  'differing_entry_operands':','.join(changed['entry']),'differing_return_operands':','.join(changed['return'])})
            for arm in ('B1','DM065'):
                item=pair[arm];row={'target':target,'arm':arm,'function':fn,'candidate_timestep':step,'occurrence_within_step':seen[key],
                    'classification':pair['classification'].get(arm,'not_applicable'),'rk_step':item.get('rk_step',''),
                    'acoustic_iteration':item.get('acoustic_iteration',''),'watch_events':item['watch_events'],
                    'non_hydrostatic_raw_word':item.get('non_hydrostatic_raw_word',''),
                    'non_hydrostatic_signed':item.get('non_hydrostatic',''),'non_hydrostatic_branch_bit':item.get('non_hydrostatic_branch_bit','')}
                for boundary in ('entry','return'):
                    for name,word in item[boundary+'_fields_raw'].items():row[boundary+'_'+name]=f32word(word);row[boundary+'_'+name+'_f32_le_hex']=word
                for name,val in item['source_order_reference'].items():row['source_reference_'+name]=val
                if fn=='prep':
                    x=item['entry_fields_raw'];pf=np.float32(np.float32(f32word(x['p']))+np.float32(f32word(x['pb'])));p0=np.float32(f32word(x['p0']));rd=np.float32(287.);cp=np.float32(np.float32(7.)*rd/np.float32(2.));rcp=np.float32(rd/cp)
                    with np.errstate(all='ignore'):pii=np.float32(np.power(np.float32(pf/p0),rcp))
                    row['source_reference_PII_candidate']=float(pii) if np.isfinite(pii) else '';row['observed_PII_minus_reference']=float(f32word(item['return_fields_raw']['pii'])-pii) if np.isfinite(pii) else ''
                    row['theta_branch']='unresolved_runtime_branch'
                calls.append(row)
        for arm,values in data['bridges'].items():
            for item in values:bridges.append({'target':target,'arm':arm,**item})
    output=HERE/'results'
    if os.path.lexists(output):raise FileExistsError('output exists')
    output.mkdir()
    try:
        for name,rows in [('producer_calls.csv',calls),('pointer_value_bridges.csv',bridges),('first_sampled_operator_differences.csv',first)]:write_csv(output/name,rows)
        rec={'status':'PASS','analysis_pins':PINS,'source_sha256':sha(Path(__file__)),'rows':{'producer_calls':len(calls),'bridges':len(bridges),'first_differences':len(first)},
             'outputs':{p.name:sha(p) for p in output.iterdir()},'limitations':['All records are bounded same-target sampled events, not a complete budget.','Source-order float32 candidates and signed residuals do not establish compiled instruction or rounding equivalence.','The prep runtime theta branch remains unresolved; t_new is a captured model input, not labeled physical temperature.','Same pointer may carry changed values between producer return and consumer entry; compare words, never infer continuity from pointer alone.','Other index-6 namespaces are unclassified. Watch PCs are post-store; no event does not prove no write.']}
        (output/'receipt.json').write_text(json.dumps(rec,indent=2)+'\n')
    except BaseException:
        import shutil;shutil.rmtree(output);raise
    print('PASS',sha(output/'receipt.json'))

if __name__=='__main__':main()
