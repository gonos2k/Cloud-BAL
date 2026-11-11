#!/usr/bin/env python3
"""Audit the recorded source-stage conditions without changing model state."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import subprocess
from pathlib import Path
import numpy as np

VARIANTS = ('QNICE', 'NI_nominal_maximum_mass_kg-1', 'NI_fixed_50um_kg-1')
STAGES = {'WRAPPER','ENTRY','SLOPE','FINAL'} | {f'PSD{n}_{s}' for n in (1,2,3) for s in ('PRE','ACTIVE','POST')}

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def word(value):
    return np.float32(value).view(np.uint32).item()

def records(path):
    result={}
    for line in Path(path).read_text().splitlines():
        p=line.split()
        if len(p)!=9 or p[0] not in STAGES:raise ValueError('unknown or malformed stage record')
        values=[float(v) for v in p[4:]]
        if not all(np.isfinite(v) and float(np.float32(v))==v for v in values):
            raise ValueError('record is not an exact finite REAL32 value')
        row=dict(zip(('qi','ni','den','aux','temperature'),values))
        row.update(stage=p[0],loop=int(p[1]),i=int(p[2]),k=int(p[3]))
        key=(row['stage'],row['loop'],row['k'])
        if key in result or row['i']!=1 or row['qi']<0 or row['ni']<0 or row['den']<=0:
            raise ValueError('duplicate key or invalid column state')
        result[key]=row
    return result

def active(stage,row,policy):
    if stage in ('PSD1','PSD2'):
        return row['qi']>=float(np.float32(policy['psd12_qi_min']))
    if stage=='PSD3':
        return (row['qi']>=float(np.float32(policy['qmin'])) and
                row['ni']>=float(np.float32(policy['ncmin_m3'])))
    raise ValueError('unknown PSD stage')

def check_psd(stage,pre,post,selected,policy):
    for field in ('qi','den','temperature'):
        if word(pre[field])!=word(post[field]):raise ValueError('PSD changed mass or thermodynamic state')
    enabled=active(stage,pre,policy)
    if enabled != (selected is not None):raise ValueError('PSD active record disagrees with source gate')
    if enabled:
        for field in ('qi','den','temperature'):
            if word(selected[field])!=word(post[field]):raise ValueError('active PSD probe state differs')
        if not policy['lambda_min_m_inv']<=selected['aux']<=policy['lambda_max_m_inv']:
            raise ValueError('active source lambda outside bounds')
        if word(selected['ni'])!=word(post['ni']):raise ValueError('active and post number differ')
    elif word(pre['ni'])!=word(post['ni']):
        raise ValueError('inactive PSD changed number')
    # The entry cap intentionally is not applied to a later PSD state.
    return enabled

def audit_column(rows,terminal,policy,nz=39):
    expected=set()
    cap=np.float32(policy['entry_cap_m3'])
    for k in range(1,nz+1):
        for stage,loop in [('WRAPPER',0),('ENTRY',0),('SLOPE',1),('FINAL',0)]:expected.add((stage,loop,k))
        wrapper=rows[('WRAPPER',0,k)];entry=rows[('ENTRY',0,k)];slope=rows[('SLOPE',1,k)];final=rows[('FINAL',0,k)]
        clipped=np.minimum(np.maximum(np.float32(wrapper['ni']),np.float32(0)),cap)
        if word(entry['ni'])!=word(clipped):raise ValueError('entry clamp differs from source')
        if word(slope['ni'])!=word(entry['ni']) or word(slope['qi'])!=word(entry['qi']):
            raise ValueError('first slope did not consume recorded entry state')
        lower=np.float32(1)/np.float32(policy['lambda_max_m_inv'])
        upper=np.float32(1)/np.float32(policy['lambda_min_m_inv'])
        if not lower<=slope['aux']<=upper:raise ValueError('reciprocal slope outside source bounds')
        if slope['qi']<=float(np.float32(policy['qmin'])) and word(slope['aux'])!=word(lower):
            raise ValueError('first slope inactive default differs')
        if slope['qi']>float(np.float32(policy['qmin'])) and slope['ni']==0 and word(slope['aux'])!=word(upper):
            raise ValueError('first slope zero-number default differs')
        for n in (1,2,3):
            stage=f'PSD{n}'
            pre=rows[(stage+'_PRE',1,k)];post=rows[(stage+'_POST',1,k)]
            selected=rows.get((stage+'_ACTIVE',1,k))
            enabled=check_psd(stage,pre,post,selected,policy)
            expected.update([(stage+'_PRE',1,k),(stage+'_POST',1,k)])
            if enabled:expected.add((stage+'_ACTIVE',1,k))
        public=np.float32(final['ni'])/np.float32(final['den'])
        if word(terminal[9*nz+k-1])!=word(public):raise ValueError('public wrapper division differs')
        if word(terminal[4*nz+k-1])!=word(final['qi']):raise ValueError('public ice mass differs')
    if set(rows)!=expected:raise ValueError('missing or extra stage records')

def check_oracle_response(mode,actual,line,enabled):
    fields=line.split()
    if len(fields)!=4 or fields[0]!=mode or int(fields[3])!=int(enabled):
        raise ValueError('source oracle mode or active gate differs')
    if int(fields[1],16)!=word(actual['ni']) or int(fields[2],16)!=word(actual['aux']):
        raise ValueError('recorded number or slope/lambda differs from source oracle')

def audit_oracle(rows,executable,policy,nz=39):
    requests=[];expected=[]
    for k in range(1,nz+1):
        for mode in ('SLOPE','PSD1','PSD2','PSD3'):
            if mode=='SLOPE':
                row=rows[(mode,1,k)];actual=row
                enabled=row['qi']>float(np.float32(policy['qmin']))
            else:
                row=rows[(mode+'_PRE',1,k)]
                actual=dict(rows[(mode+'_POST',1,k)])
                selected=rows.get((mode+'_ACTIVE',1,k))
                enabled=selected is not None
                actual['aux']=selected['aux'] if enabled else -1.0
            requests.append(f"{mode} {row['den']:.17g} {row['qi']:.17g} {row['ni']:.17g} {policy['qmin']:.17g} {policy['ncmin_m3']:.17g}")
            expected.append((mode,actual,enabled))
    result=subprocess.run([str(executable.resolve())],input='\n'.join(requests)+'\n',text=True,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    lines=result.stdout.splitlines()
    if len(lines)!=len(expected):raise ValueError('source oracle row count differs')
    for (mode,actual,enabled),line in zip(expected,lines):
        check_oracle_response(mode,actual,line,enabled)
    return len(expected)

def check_wrapper(rows,profiles,variant):
    for k in range(1,len(profiles['QICE'])+1):
        row=rows[('WRAPPER',0,k)]
        den=np.float32(profiles['den'][k-1]);qi=np.float32(profiles['QICE'][k-1])
        ni=np.float32(profiles[variant][k-1])*den
        if word(row['den'])!=word(den) or word(row['qi'])!=word(qi) or word(row['ni'])!=word(ni):
            raise ValueError('wrapper record differs from frozen file-state input')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--oracle-o0',type=Path,required=True)
    parser.add_argument('--oracle-o2',type=Path,required=True)
    args=parser.parse_args();b=args.bundle
    policy=json.loads((b/'contract/policy.json').read_text())
    if policy['scientific_admission'] or policy['modified_input_publication']:
        raise ValueError('read-only diagnostic contract required')
    cases=json.loads((b/'cases/profiles.json').read_text())['cases']
    all_rows=[];targets=[];adjustments=[];counts={};inputs={};oracle_checks=0
    oracles={'O0':args.oracle_o0,'O2':args.oracle_o2}
    for executable in oracles.values():inputs[str(executable.resolve())]=sha(executable)
    for opt in ('O0','O2'):
        totals=Counter()
        for case_id,case in enumerate(cases):
            for variant in VARIANTS:
                name=f'case{case_id}_{variant}'
                folder=b/'native/full/results'/f'{opt}_instrumented'/name
                stagefile=folder/'stages.txt';terminalfile=folder/'terminal.bin'
                inputs[str(stagefile)]=sha(stagefile);inputs[str(terminalfile)]=sha(terminalfile)
                terminal=np.fromfile(terminalfile,dtype='<f4')
                if terminal.size!=827 or not np.isfinite(terminal).all():raise ValueError('terminal schema differs')
                ledger=records(stagefile);audit_column(ledger,terminal,policy)
                check_wrapper(ledger,case['profiles'],variant)
                oracle_checks+=audit_oracle(ledger,oracles[opt],policy)
                for k in range(1,40):
                    pairs=[('ENTRY',ledger[('WRAPPER',0,k)],ledger[('ENTRY',0,k)])]
                    pairs.extend((f'PSD{n}',ledger[(f'PSD{n}_PRE',1,k)],ledger[(f'PSD{n}_POST',1,k)]) for n in (1,2,3))
                    for operator,pre,post in pairs:
                        changed=word(pre['ni'])!=word(post['ni'])
                        totals[operator+'_changed_ni_rows']+=int(changed)
                        adjustments.append({'optimization':opt,'case':case_id,'variant':variant,'k':k,
                            'operator':operator,'ni_before_m3':pre['ni'],'ni_after_m3':post['ni'],
                            'delta_stored_ni_m3':post['ni']-pre['ni'],'changed':changed})
                for row in ledger.values():
                    stage=row['stage'];totals[stage+'_rows']+=1
                    if row['ni']>policy['entry_cap_m3']:totals[stage+'_over_entry_cap']+=1
                    normalized={'optimization':opt,'case':case_id,'role':'|'.join(case['roles']),
                                'variant':variant,**row}
                    all_rows.append(normalized)
                    if row['k']==case['fortran_ijk'][2]:targets.append(normalized)
        counts[opt]=dict(totals)
    args.output.mkdir(parents=True,exist_ok=True)
    for filename,data in [('stage_rows.csv',all_rows),('target_stages.csv',targets),('operator_adjustments.csv',adjustments)]:
        with (args.output/filename).open('x',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    result={'status':'PASS_RECORDED_STAGE_CONTRACT','contract_sha256':sha(b/'contract/policy.json'),
            'input_sha256':inputs,'counts':counts,'rows':len(all_rows),'target_rows':len(targets),'source_oracle_word_checks':oracle_checks,
            'adjustment_scope':'Float64 differences of stored REAL32 number states within each named source operator; not process rates or causal attribution across intervals.',
            'stage_semantics':'Entry cap only at ENTRY; every first slope and PSD stage matches source-extracted REAL32 oracle words; wrapper product/division match frozen inputs.',
            'scope':'Standalone local-column records; no first WRF use, initialized file publication, forecast skill or whole-domain budget.'}
    with (args.output/'summary.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'status':result['status'],'rows':len(all_rows),'counts':counts}))

if __name__=='__main__':main()
