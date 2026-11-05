#!/usr/bin/env python3
"""Validate bounded actual-writer JSONL; calculate source-order float32 references."""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import struct

import numpy as np

TARGETS = {'nr20330': (5, 141, 142, 2), 'nr20330max': (5, 141, 143, 11),
           'p20183': (5, 144, 142, 4), 'p17051': (3, 140, 120, 38)}
FIELDS = {'rk': ({'scalar_current','scalar_tendency','advection_tendency','msfty','c1','c2','mu_old','mu_new','mu_base','dt'}, {'scalar_old','scalar_current'}),
          'pressure': ({'ph_k','ph_kplus1','alt','t2','t_save','c2a','mu','mut','c1h','c2h','t0','rdnw','smdiv'}, {'al','p','pm1'}),
          'prep': ({'t_new','t0','al','alb','p','p0','pb','qv','qc'}, {'rho','th','pii','pf'}),
          'kdm': (set('th qv qc qr qi qs qg nn nc ni nr bg den pii p'.split()), set('th qv qc qr qi qs qg nn nc ni nr bg den pii p'.split()))}


def word(raw):
    if not isinstance(raw,str) or re.fullmatch(r'[0-9a-f]{8}',raw) is None:
        raise ValueError('invalid little-endian REAL32 word')
    value=struct.unpack('<f',bytes.fromhex(raw))[0]
    if not math.isfinite(value):raise ValueError('nonfinite REAL32 word')
    return np.float32(value)


def finite_fields(event, required):
    fields=event.get('fields')
    if not isinstance(fields,dict) or not required.issubset(fields):raise ValueError('missing source operand')
    for value in fields.values():word(value)


def validate_events(path, target, require_operators=True):
    """Return ordered paired calls; no missing watch event is interpreted as a write."""
    rank,i,j,k=TARGETS[target];events=[]
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            e=json.loads(line)
            if not isinstance(e,dict):raise ValueError('invalid event')
            events.append(e)
    active=None; watches=[]; calls=[]; initialized_pm1=set();initialized_old=set(); completed_kdm=0
    expected_owner={'rk':'rk_update_scalar','pressure':'calc_p_rho'}
    for sequence,e in enumerate(events,1):
        if (e.get('sequence')!=sequence or e.get('rank')!=rank or e.get('target')!=target or
            (e.get('i'),e.get('j'),e.get('k'))!=(i,j,k)):
            raise ValueError('event sequence or target identity differs')
        kind=e.get('event')
        if kind=='function_entry':
            if active is not None or e.get('function') not in FIELDS:raise ValueError('unexpected nested or unknown function')
            fn=e['function'];finite_fields(e,FIELDS[fn][0]);active=e;watches=[]
            if require_operators:
                d=e.get('bounds')
                if not isinstance(d,dict):raise ValueError('missing Fortran bounds')
                for axis,index in (('i',i),('j',j),('k',k)):
                    try:
                        lo,hi=d[axis+'ts'],d[axis+'te']; ml,mh=d[axis+'ms'],d[axis+'me']; dl,dh=d[axis+'ds'],d[axis+'de']
                    except KeyError as exc:raise ValueError('incomplete Fortran bounds') from exc
                    if not all(isinstance(x,int) for x in (lo,hi,ml,mh,dl,dh)) or not (ml<=lo<=index<=hi<=mh and dl<=index<dh):raise ValueError('target outside owning bounds')
            if fn=='kdm':
                if e.get('timestep') != completed_kdm+1:raise ValueError('KDM timing differs')
                initialized_old.clear();initialized_pm1.clear()
            elif e.get('candidate_timestep') != completed_kdm+1:
                raise ValueError('candidate step differs from observed KDM sequence')
            if fn=='pressure':
                it=e.get('acoustic_iteration');p=e.get('target_pointer')
                if not isinstance(it,int) or it<0 or (it==0 and 'pm1' in e['fields']):raise ValueError('invalid pressure initialization')
                if it>0 and ('pm1' not in e['fields'] or p not in initialized_pm1):raise ValueError('unwitnessed pm1')
            if fn=='rk':
                step=e.get('rk_step');p=e.get('target_pointer')
                if step not in (1,2,3) or (step==1 and 'scalar_old' in e['fields']):raise ValueError('invalid RK initialization')
                if step>1 and ('scalar_old' not in e['fields'] or p not in initialized_old):raise ValueError('unwitnessed RK1')
        elif kind=='watch_after':
            if active is None or active['function'] not in expected_owner or e.get('owner')!=expected_owner[active['function']] or e.get('target_pointer')!=active.get('target_pointer') or e.get('watch_address')!=active.get('target_pointer'):
                raise ValueError('watchpoint outside its owning call or target')
            for key in ('candidate_timestep','rk_step','acoustic_iteration'):
                if key in active and e.get(key)!=active[key]:raise ValueError('watch metadata differs')
            post=word(e.get('post_word')); del post
            before=e.get('pre_word')
            if before is not None:word(before)
            if watches and before!=watches[-1]['post_word']:raise ValueError('watch word chain differs')
            if not watches and active['function']=='rk' and before!=active['fields']['scalar_current']:raise ValueError('first watch differs from actual RK entry')
            if not watches and active['function']=='pressure' and before is not None:raise ValueError('pressure output preword was not opaque')
            if not isinstance(e.get('reported_pc'),str) or not e.get('instruction_bytes_around_pc') or not e.get('registers'):raise ValueError('incomplete watch evidence')
            watches.append(e)
        elif kind=='function_return':
            if active is None or e.get('function')!=active['function']:raise ValueError('unpaired function return')
            fn=active['function'];finite_fields(e,FIELDS[fn][1])
            for key in ('candidate_timestep','timestep','rk_step','acoustic_iteration','target_pointer','bounds'):
                if key in active and e.get(key)!=active[key]:raise ValueError('return identity differs')
            if fn in expected_owner:
                if e.get('watch_events')!=len(watches):raise ValueError('watch event count differs')
                result=e['fields']['scalar_current' if fn=='rk' else 'p']
                if watches and watches[-1]['post_word']!=result:raise ValueError('final watched word differs from return')
                if fn=='rk' and not watches and result!=active['fields']['scalar_current']:raise ValueError('changed RK word without observed watch')
            if fn=='rk' and active['rk_step']==1:initialized_old.add(active['target_pointer'])
            if fn=='pressure' and active['acoustic_iteration']==0:initialized_pm1.add(active['target_pointer'])
            calls.append((active,e,tuple(watches)))
            if fn=='kdm':completed_kdm+=1
            active=None
        else:raise ValueError('unknown event')
    if active is not None:raise ValueError('incomplete function pair')
    kdm=[a['timestep'] for a,b,w in calls if a['function']=='kdm']
    if kdm != [1,2,3,4]:raise ValueError('KDM call coverage differs')
    if require_operators:
        operator='rk' if target.startswith('nr') else 'pressure'
        other={'rk','pressure','prep'} - ({'rk'} if operator=='rk' else {'pressure','prep'})
        if any(a['function'] in other for a,b,w in calls):raise ValueError('unexpected target operator')
        for step in range(1,5):
            ops=[a for a,b,w in calls if a['function']==operator and a['candidate_timestep']==step]
            boundary=next(a for a,b,w in calls if a['function']=='kdm' and a['timestep']==step)
            if operator=='rk':
                bound=[a for a in ops if a.get('qnr_base_pointer')==boundary.get('nr_base_pointer')]
                if [a['rk_step'] for a in bound]!=[1,2,3]:raise ValueError('incomplete pointer-bound QNR RK stages')
                for a in ops:
                    # Each identifier is captured explicitly; the probe's internal equality claim is not a substitute.
                    if not (isinstance(a.get('scs'),int) and a.get('scs')==a.get('sce')==a.get('runtime_p_qnr')==a.get('qnr_species_index')):
                        raise ValueError('runtime QNR scalar identity is missing or differs')
            else:
                if [a['acoustic_iteration'] for a in ops]!=[0,1,0,1,2,0,1,2,3,4]:raise ValueError('incomplete pressure acoustic stages')
                prep=[a for a,b,w in calls if a['function']=='prep' and a['candidate_timestep']==step]
                if len(prep)!=1:raise ValueError('missing unique preparation')
                prep=prep[0]
                if prep.get('p_in_pointer') not in {a.get('p_base_pointer') for a in ops} or any(prep.get(x)!=boundary.get(y) for x,y in (('th_out_pointer','th_base_pointer'),('pii_out_pointer','pii_base_pointer'),('pf_out_pointer','p_base_pointer'))):
                    raise ValueError('pressure/preparation/KDM pointer binding differs')
    return calls


def f(x):return np.float32(x)
def add(a,b):return f(f(a)+f(b))
def sub(a,b):return f(f(a)-f(b))
def mul(a,b):return f(f(a)*f(b))
def div(a,b):return f(f(a)/f(b))


def rk_reference(entry):
    x={k:word(v) for k,v in entry['fields'].items()};rk=entry['rk_step']
    old=x['scalar_current'] if rk==1 else x['scalar_old']
    # Valid only if target is inside both source tendency loop ranges.
    d=entry['bounds'];i,j,k=(entry[t] for t in ('i','j','k'));zone=entry['spec_zone']
    if not (d['ids']+zone<=i<=d['ide']-zone-1 and d['jds']+zone<=j<=d['jde']-zone-1 and d['kts']<=k<=min(d['kte'],d['kde']-1)):
        return None
    tendency=add(mul(x['advection_tendency'],x['msfty']),x['scalar_tendency'])
    muold=add(x['mu_old'],x['mu_base']);munew=add(x['mu_new'],x['mu_base'])
    return div(add(mul(add(mul(x['c1'],muold),x['c2']),old),mul(x['dt'],tendency)),add(mul(x['c1'],munew),x['c2']))


def pressure_reference(entry):
    x={k:word(v) for k,v in entry['fields'].items()}
    den=add(mul(x['c1h'],x['mut']),x['c2h']);cmu=mul(x['c1h'],x['mu'])
    al=mul(div(-1.,den),add(mul(x['alt'],cmu),mul(x['rdnw'],sub(x['ph_kplus1'],x['ph_k']))))
    raw=mul(x['c2a'],sub(div(mul(x['alt'],sub(x['t2'],mul(cmu,x['t_save']))),mul(den,add(x['t0'],x['t_save']))),al))
    out=raw if entry['acoustic_iteration']==0 else add(raw,mul(x['smdiv'],sub(raw,x['pm1'])))
    return al,raw,out


def prep_reference(entry):
    x={k:word(v) for k,v in entry['fields'].items()}
    p=add(x['p'],x['pb']);dry=add(x['t_new'],x['t0'])
    moist=div(dry,add(1.,mul(div(f(461.6),f(287.)),x['qv'])))
    return {'pf':p,'rho':div(1.,add(x['al'],x['alb'])),'th_dry_candidate':dry,'th_moist_candidate':moist}


def residual(actual, reference):
    """Signed observed-minus-reference, without a tolerance or equivalence claim."""
    a=float(word(actual));b=float(reference)
    return a-b if math.isfinite(b) else None


def describe_call(call):
    entry,ret,watches=call;fn=entry['function'];out={'function':fn,'entry_sequence':entry['sequence'],
        'return_sequence':ret['sequence'],'watch_events':len(watches),'entry_fields_raw':entry['fields'],
        'return_fields_raw':ret['fields'],'watch_after':[{'sequence':e['sequence'],'pre_word':e.get('pre_word'),
          'post_word':e['post_word'],'reported_pc':e['reported_pc'],'pc_symbol':e.get('pc_symbol')} for e in watches]}
    for key in ('candidate_timestep','timestep','rk_step','acoustic_iteration','scs','sce','runtime_p_qnr','qnr_species_index','spec_zone','bounds','target_pointer'):
        if key in entry:out[key]=entry[key]
    with np.errstate(all='ignore'):
        if fn=='rk':
            ref=rk_reference(entry)
            out['source_order_reference']={'reference_nr':float(ref) if ref is not None and np.isfinite(ref) else None,
                                           'return_minus_reference':residual(ret['fields']['scalar_current'],ref) if ref is not None else None}
        elif fn=='pressure':
            al,raw,calc=pressure_reference(entry)
            out['source_order_reference']={'al':float(al),'p_raw':float(raw),'p_after_damping':float(calc),
               'al_return_minus_reference':residual(ret['fields']['al'],al),
               'p_return_minus_reference':residual(ret['fields']['p'],calc),
               'pm1_return_minus_raw_reference':residual(ret['fields']['pm1'],raw)}
        elif fn=='prep':
            ref=prep_reference(entry)
            out['source_order_reference']={name:float(value) for name,value in ref.items()}
            out['source_order_reference'].update({'pf_return_minus_reference':residual(ret['fields']['pf'],ref['pf']),
                'rho_return_minus_reference':residual(ret['fields']['rho'],ref['rho']),
                'th_return_minus_dry_candidate':residual(ret['fields']['th'],ref['th_dry_candidate']),
                'th_return_minus_moist_candidate':residual(ret['fields']['th'],ref['th_moist_candidate'])})
            out['theta_branch']='unresolved: actual runtime use_theta_m/P_Qv branch not captured'
        else:
            th=word(entry['fields']['th']);pii=word(entry['fields']['pii'])
            t_return=mul(word(ret['fields']['th']),word(ret['fields']['pii']))
            t_entry=mul(th,pii)
            out['derived_TK_entry_float32']=float(t_entry);out['derived_TK_return_float32']=float(t_return)
            out['KDM_within_call_TK_change']=float(t_return)-float(t_entry)
            out['KDM_TK_semantics']='Both reconstructed TK products include the wrapper mapping; return includes within-call t/PII then TH*PII roundtrip.'
    out['reference_limitation']='Source-order float32 candidate; compiled instruction/rounding equivalence is not asserted.'
    return out


def bridges(calls,target):
    """Compare actual pointer-bound values; equality does not exclude intervening stores."""
    out=[]
    for step in range(1,5):
        entries=[(a,b) for a,b,w in calls if a['function']=='kdm' and a['timestep']==step]
        if len(entries)!=1:raise ValueError('KDM bridge target missing')
        kdm=entries[0][0]
        if target.startswith('nr'):
            rk=[(a,b) for a,b,w in calls if a['function']=='rk' and a['candidate_timestep']==step and a['qnr_base_pointer']==kdm['nr_base_pointer']]
            if not rk:raise ValueError('NR bridge missing')
            a,b=rk[-1];out.append({'step':step,'bridge':'last matching RK return to KDM entry NR',
               'producer_return_word':b['fields']['scalar_current'],'consumer_entry_word':kdm['fields']['nr'],
               'same_word':b['fields']['scalar_current']==kdm['fields']['nr'],'pointer':a['qnr_base_pointer']})
        else:
            prep=[(a,b) for a,b,w in calls if a['function']=='prep' and a['candidate_timestep']==step]
            if len(prep)!=1:raise ValueError('preparation bridge missing')
            a,b=prep[0];pressure=[(x,y) for x,y,w in calls if x['function']=='pressure' and x['candidate_timestep']==step and x['p_base_pointer']==a['p_in_pointer']]
            if not pressure:raise ValueError('pressure bridge missing')
            x,y=pressure[-1]
            out.append({'step':step,'bridge':'last matching pressure return to prep input P',
                'producer_return_word':y['fields']['p'],'consumer_entry_word':a['fields']['p'],
                'same_word':y['fields']['p']==a['fields']['p'],'pointer':a['p_in_pointer']})
            for field,consumer,pointer in (('th','th','th_out_pointer'),('pii','pii','pii_out_pointer'),('pf','p','pf_out_pointer')):
                out.append({'step':step,'bridge':f'prep {field} return to KDM entry {consumer}',
                    'producer_return_word':b['fields'][field],'consumer_entry_word':kdm['fields'][consumer],
                    'same_word':b['fields'][field]==kdm['fields'][consumer],'pointer':a[pointer]})
    return out


def verify_kdm_capture(calls, target, arm, baseline_path):
    rank,i,j,k=TARGETS[target]
    del rank
    with np.load(baseline_path,allow_pickle=False) as z:
        cells=z['native_cells_i_j_1based'];where=np.flatnonzero((cells[:,0]==i)&(cells[:,1]==j))
        if where.size!=1:raise ValueError('target not uniquely mapped in baseline')
        ci=int(where[0]);fields=[str(x) for x in z['fields']]
        if fields != ['TH','QV','QC','QR','QI','QS','QG','NN','NC','NI','NR','BG','DEN','TK','P','PII']:
            raise ValueError('baseline field order differs')
        for entry,ret,_ in calls:
            if entry['function']!='kdm':continue
            for event,boundary in ((entry,'entry'),(ret,'return')):
                expected=z[f'{arm}_{boundary}'][entry['timestep']-1,k-1,ci]
                raw=event['fields']
                for index,name in enumerate(('th','qv','qc','qr','qi','qs','qg','nn','nc','ni','nr','bg','den')):
                    if np.float32(word(raw[name])).view('u4')!=expected[index].view('u4'):raise ValueError('KDM boundary differs from selected baseline')
                if mul(word(raw['th']),word(raw['pii'])).view('u4')!=expected[13].view('u4') or word(raw['p']).view('u4')!=expected[14].view('u4') or word(raw['pii']).view('u4')!=expected[15].view('u4'):
                    raise ValueError('KDM TK/P/PII differs from selected baseline')


def paired_call_records(calls_b1,calls_dm):
    """Pair by actual source call order within each provisional model step."""
    if len(calls_b1)!=len(calls_dm):raise ValueError('arm operator counts differ')
    rows=[]
    bound={}
    for arm,calls in (('B1',calls_b1),('DM065',calls_dm)):
        bound[arm]={a['timestep']:a['nr_base_pointer'] for a,b,w in calls if a['function']=='kdm'}
    for one,two in zip(calls_b1,calls_dm):
        a,ar,_=one;b,br,_=two
        identity=lambda x:(x['function'],x.get('candidate_timestep'),x.get('timestep'),x.get('rk_step'),x.get('acoustic_iteration'))
        if identity(a)!=identity(b):raise ValueError('arm call sequences differ')
        if set(a['fields'])!=set(b['fields']) or set(ar['fields'])!=set(br['fields']):raise ValueError('arm operand inventories differ')
        delta={}
        for boundary,x,y in (('entry',a['fields'],b['fields']),('return',ar['fields'],br['fields'])):
            delta[boundary]={name:{'B1_word':x[name],'DM065_word':y[name],
                                   'DM065_minus_B1':float(word(y[name]))-float(word(x[name]))} for name in x}
        classifications={}
        if a['function']=='rk':
            for arm,event in (('B1',a),('DM065',b)):
                classifications[arm]='KDM_NR_pointer_bound' if event.get('qnr_base_pointer')==bound[arm][event['candidate_timestep']] else 'other_index6_candidate_unclassified'
        rows.append({'identity':identity(a),'classification':classifications,'B1':describe_call(one),'DM065':describe_call(two),'paired_operands':delta})
    return rows


def sha(path):
    import hashlib
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def run_analysis(target, receipts, event_paths, baseline, output, schema, closure=None, capture_freeze=None):
    """Analyze only verified successful paired actual captures; publish fresh output."""
    import os
    import shutil
    import tempfile
    output=Path(output)
    if os.path.lexists(output):raise FileExistsError(output)
    schema=Path(schema);schema_doc=json.loads(schema.read_text())
    if schema_doc.get('targets',{}).get(target,{}).get('ijk_1based')!=list(TARGETS[target][1:]):
        raise ValueError('writer schema target differs')
    if sha(baseline)!='803c398b178db89271976b941a74db7e3a9010ffe16091c94749f5d1feb5ab1c':
        raise ValueError('selected baseline differs')
    if closure is None or capture_freeze is None:
        raise ValueError('independent paired capture closure and capture freeze are required')
    closure=Path(closure);capture_freeze=Path(capture_freeze)
    closure_doc=json.loads(closure.read_text());freeze_doc=json.loads(capture_freeze.read_text())
    if closure_doc.get('status')!='PASS' or sha(capture_freeze) not in (closure_doc.get('original_freeze_sha256'),closure_doc.get('freeze_sha256')):
        raise ValueError('paired capture closure does not bind its freeze')
    schema_hashes=[value for path,value in freeze_doc['sha256'].items() if path.endswith('/writer_schema.json')]
    if len(schema_hashes)!=1 or schema_hashes[0]!=sha(schema):raise ValueError('capture freeze does not bind writer schema')
    calls={};inputs={}
    for arm in ('B1','DM065'):
        receipt_path=Path(receipts[arm]);event_path=Path(event_paths[arm]);r=json.loads(receipt_path.read_text())
        if closure_doc.get('arms',{}).get(arm,{}).get('receipt_sha256')!=sha(receipt_path):
            raise ValueError('paired closure does not bind per-arm receipt')
        if r.get('status')!='PASS_DISCOVERY_CAPTURE' or r.get('arm')!=arm or r.get('target')!=target or r.get('event_file_sha256')!=sha(event_path):
            raise ValueError('writer receipt does not bind successful target event stream')
        calls[arm]=validate_events(event_path,target)
        if r.get('event_count')!=sum(2+len(watches) for _,_,watches in calls[arm]):raise ValueError('event count differs from receipt')
        verify_kdm_capture(calls[arm],target,arm,baseline)
        inputs[arm]={'receipt_path':str(receipt_path.resolve()),'receipt_sha256':sha(receipt_path),
                     'event_path':str(event_path.resolve()),'event_sha256':sha(event_path)}
    rows=paired_call_records(calls['B1'],calls['DM065'])
    result={'status':'PASS_ACTUAL_WRITER_ANALYSIS','target':target,'target_rank_ijk_1based':TARGETS[target],
            'inputs':inputs,'schema_sha256':sha(schema),'capture_freeze_sha256':sha(capture_freeze),'capture_closure_sha256':sha(closure),'selected_baseline_sha256':sha(baseline),
            'source_sha256':sha(Path(__file__)),'paired_calls':rows,
            'bridges':{arm:bridges(calls[arm],target) for arm in ('B1','DM065')},
            'limitations':['Only actual bounded observations at this target and the first four calls.',
                'Source-order float32 references do not assert compiler-equivalent arithmetic, FMA, PC or exact writer instruction.',
                'Reported watch PC is after a changed store; absent watch events do not prove no writes.',
                'Prep dry/moist theta source branch remains unresolved until runtime configuration or instruction path is observed.',
                'Intercall changes are not a pure transport or complete budget attribution.']}
    for arm in ('B1','DM065'):
        if sha(receipts[arm])!=inputs[arm]['receipt_sha256'] or sha(event_paths[arm])!=inputs[arm]['event_sha256']:
            raise ValueError('capture changed during analysis')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.writer-analysis-',dir=output.parent))
    try:
        (stage/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        if os.path.lexists(output):raise FileExistsError(output)
        os.rename(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)
    return sha(output/'analysis.json')


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',choices=tuple(TARGETS),required=True)
    for flag in ('b1-receipt','dm065-receipt','b1-events','dm065-events','baseline','schema','closure','capture-freeze','output'):
        parser.add_argument('--'+flag,required=True)
    a=parser.parse_args()
    result=run_analysis(a.target,{'B1':a.b1_receipt,'DM065':a.dm065_receipt},
                        {'B1':a.b1_events,'DM065':a.dm065_events},a.baseline,a.output,a.schema,a.closure,a.capture_freeze)
    print('PASS_ACTUAL_WRITER_ANALYSIS',result)


if __name__=='__main__':main()
