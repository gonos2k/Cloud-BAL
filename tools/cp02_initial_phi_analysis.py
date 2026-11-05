#!/usr/bin/env python3
"""Validate bounded phi/vspow trace while preserving raw P-buffer semantics."""
from __future__ import annotations
import json
import gzip
import hashlib
import re
import struct
from pathlib import Path
import numpy as np
from cp02_initial_writer_analysis import word, add, sub, mul, div, verify_kdm_capture

CLOSURE_SHA={'p20183':'0eae5a9bfa8159fd7529c0c2bbf0258f30410bb3953d2c9890415696dd002434','p17051':'7e66ee98bd40c745bf847894ed45432d095e8288b03a2e57df47699900d3cf57'}
TARGETS={'p20183':(5,144,142,4),'p17051':(3,140,120,38)}
PHI_FIELDS=set('alb mu muts c1 c2 c3h c4h c3f c3f_next c4f c4f_next ph ph_next phb phb_next pb t p0 t0 ptop znu znw dnw rdnw rdn qv'.split())
PREP_FIELDS=set('t_new t0 al alb p p0 pb qv qc'.split())
KDM_FIELDS=set('th qv qc qr qi qs qg nn nc ni nr bg den pii p'.split())
PHI_META=('caller_pc','caller_class','p_base','al_base','moist_base','qv_base','n_moist','runtime_p_qv','param_first_scalar','hypsometric_opt','use_theta_m','non_hydrostatic','non_hydrostatic_raw_word','non_hydrostatic_branch_bit','bounds')


def fields(event, required):
    d=event.get('fields')
    if not isinstance(d,dict) or not required.issubset(d):raise ValueError('missing observed operand')
    for v in d.values():word(v)


def logical_guard(e, k):
    raw=e.get('non_hydrostatic_raw_word');logical=e.get('non_hydrostatic')
    if (not isinstance(raw,str) or re.fullmatch('[0-9a-f]{8}',raw) is None or not isinstance(logical,int) or
        struct.unpack('<i',bytes.fromhex(raw))[0]!=logical or e.get('non_hydrostatic_branch_bit')!=(logical&1) or not (logical&1)):
        raise ValueError('invalid actual nonhydrostatic logical')
    if (e.get('hypsometric_opt') not in (1,2) or not isinstance(e.get('n_moist'),int) or
        not isinstance(e.get('runtime_p_qv'),int) or not isinstance(e.get('param_first_scalar'),int) or
        not 1<=e['runtime_p_qv']<=e['n_moist'] or e['n_moist']<e['param_first_scalar'] or
        not isinstance(e.get('use_theta_m'),int) or e.get('k_plus_one')!=k+1 or not isinstance(e.get('kme'),int) or e['kme']<k+1):
        raise ValueError('invalid actual phi branch or index')


def validate_events(path,target):
    rank,i,j,k=TARGETS[target];events=[]
    with (gzip.open(path, 'rt', encoding='utf-8') if str(path).endswith('.gz') else Path(path).open(encoding='utf-8')) as stream:
        for line in stream:
            e=json.loads(line)
            if not isinstance(e,dict):raise ValueError('invalid event')
            events.append(e)
    entered=completed=0;active=None;pending_guard=None;power=None;gap=None;last_phi=None;pending_prep=None
    calls=[];powers=[];gaps=[];guards=[]
    for sequence,e in enumerate(events,1):
        if e.get('sequence')!=sequence or e.get('rank')!=rank or e.get('target')!=target or (e.get('i'),e.get('j'),e.get('k'))!=(i,j,k):
            raise ValueError('event identity or order differs')
        kind=e.get('event');fn=e.get('function')
        # The probe increments entered before KDM entry and completed before KDM return.
        if kind=='function_entry' and fn=='kdm':entered+=1
        if kind=='function_return' and fn=='kdm':completed+=1
        if (e.get('kdm_entered'),e.get('kdm_completed'))!=(entered,completed) or not 0<=completed<=entered<=4:
            raise ValueError('actual KDM chronology differs')
        if pending_guard is not None and not (kind=='function_entry' and fn=='phi'):
            raise ValueError('phi guard not immediately followed by phi entry')
        if pending_prep is not None and not (kind=='function_entry' and fn=='prep'):
            raise ValueError('gap end not immediately followed by preparation')
        if kind=='phi_guard':
            if active is not None or pending_guard is not None:raise ValueError('unexpected phi guard')
            logical_guard(e,k);pending_guard=e;guards.append(e)
        elif kind=='function_entry':
            if active is not None or fn not in ('calc_last','phi','prep','kdm'):raise ValueError('unexpected nested or unknown function')
            if fn=='calc_last':
                if e.get('acoustic_iteration')!=4 or e.get('fields')!={}:raise ValueError('invalid final calc entry')
            elif fn=='phi':
                if pending_guard is None:raise ValueError('phi without guard')
                for key in ('caller_pc','caller_class','non_hydrostatic','non_hydrostatic_raw_word','non_hydrostatic_branch_bit','hypsometric_opt','n_moist','runtime_p_qv','param_first_scalar','use_theta_m'):
                    if e.get(key)!=pending_guard.get(key):raise ValueError('phi guard metadata differs')
                if e.get('bounds',{}).get('kme')!=pending_guard['kme']:raise ValueError('phi guard bounds differ')
                d=e['bounds']; ni=d['ime']-d['ims']+1;nk=d['kme']-d['kms']+1;nj=d['jme']-d['jms']+1
                if min(ni,nj,nk)<=0 or int(e['qv_base'],16)!=int(e['moist_base'],16)+(e['runtime_p_qv']-1)*ni*nj*nk*4:
                    raise ValueError('four-dimensional moisture slice pointer differs')
                expected_class={'0x13eb579':'solve_em_RK','0x13ffdd4':'solve_em_postphysics'}.get(e['caller_pc'],'other_unclassified')
                if e['caller_class']!=expected_class:raise ValueError('caller PC class differs')
                if gap is not None:
                    target_address=int(e['p_base'],16)+4*((j-d['jms'])*nk*ni+(k-d['kms'])*ni+(i-d['ims']))
                    if target_address!=int(gap['start']['target_address'],16):raise ValueError('phi P pointer differs from gap')
                fields(e,PHI_FIELDS)
                if 'p' in e['fields'] or 'al' in e['fields']:raise ValueError('phi output was read at entry')
                pending_guard=None
            elif fn=='prep':
                if pending_prep is None:raise ValueError('prep without observed gap closure')
                fields(e,PREP_FIELDS)
                d=e['bounds'];ni=d['ime']-d['ims']+1;nk=d['kme']-d['kms']+1
                prep_address=int(e['p_in_base'],16)+4*((j-d['jms'])*nk*ni+(k-d['kms'])*ni+(i-d['ims']))
                if prep_address!=int(pending_prep['target_address'],16) or e['fields']['p']!=pending_prep['final_word']:
                    raise ValueError('prep pointer/value differs from actual gap endpoint')
                pending_prep=None
            else:
                if e.get('timestep')!=entered or completed!=entered-1:raise ValueError('KDM entry step differs')
                fields(e,KDM_FIELDS)
            active={'entry':e,'powers':[]}
        elif kind=='vspow_entry':
            if active is None or active['entry']['function']!='phi' or power is not None:raise ValueError('vspow outside phi')
            word(e.get('input_word'));word(e.get('exponent_word'))
            if not isinstance(e.get('lane_index'),int) or not isinstance(e.get('row_length'),int) or not 0<=e['lane_index']<e['row_length']:
                raise ValueError('vspow lane invalid')
            d=active['entry']['bounds'];ni=d['ime']-d['ims']+1;nk=d['kme']-d['kms']+1
            target_address=int(active['entry']['p_base'],16)+4*((j-d['jms'])*nk*ni+(k-d['kms'])*ni+(i-d['ims']))
            if int(e['output_address'],16)!=int(e['row_pointer'],16)+4*e['lane_index'] or int(e['output_address'],16)!=target_address:
                raise ValueError('vspow lane/phi P target address differs')
            power=e
        elif kind=='vspow_return':
            if power is None or active is None or active['entry']['function']!='phi':raise ValueError('unpaired vspow')
            for key in ('caller_pc','row_pointer','lane_index','row_length','output_address'):
                if e.get(key)!=power.get(key):raise ValueError('vspow identity differs')
            word(e.get('output_word'));entry=power;power=None;pair=(entry,e);powers.append(pair);active['powers'].append(pair)
        elif kind=='gap_start':
            if gap is not None or active is None or active['entry']['function']!='calc_last':raise ValueError('gap start is not final calc return')
            d=active['entry']['bounds'];ni=d['ime']-d['ims']+1;nk=d['kme']-d['kms']+1
            address=int(e['p_base'],16)+4*((j-d['jms'])*nk*ni+(k-d['kms'])*ni+(i-d['ims']))
            if address!=int(e['target_address'],16):raise ValueError('gap target address differs')
            word(e.get('p_word'));gap={'start':e,'watches':[]};last_phi=None
        elif kind=='gap_watch_after':
            if gap is None or e.get('target_address')!=gap['start']['target_address']:raise ValueError('watch outside bound gap')
            prior=gap['watches'][-1]['post_word'] if gap['watches'] else gap['start']['p_word']
            word(e.get('pre_word'));word(e.get('post_word'))
            if e['pre_word']!=prior or not e.get('reported_pc') or not e.get('instruction_bytes') or not e.get('registers'):
                raise ValueError('gap watch word/PC chain differs')
            gap['watches'].append(e)
        elif kind=='gap_end':
            if gap is None or active is not None:raise ValueError('unexpected gap end')
            previous=gap['watches'][-1]['post_word'] if gap['watches'] else gap['start']['p_word']
            if e.get('target_address')!=gap['start']['target_address'] or e.get('initial_word')!=gap['start']['p_word'] or e.get('final_word')!=previous or e.get('watch_events')!=len(gap['watches']):
                raise ValueError('gap watch endpoint differs')
            same=bool(last_phi and last_phi['p_base']==gap['start']['p_base'] and last_phi['p_word']==e['final_word'])
            if e.get('last_phi_p_word')!=(last_phi['p_word'] if last_phi and last_phi['p_base']==gap['start']['p_base'] else None) or e.get('last_phi_matches_prep')!=same:
                raise ValueError('phi-to-prep word bridge differs')
            gap['end']=e;gap['last_phi']=last_phi;gaps.append(gap);pending_prep=e;gap=None
        elif kind=='function_return':
            if active is None or fn!=active['entry']['function'] or power is not None:raise ValueError('unpaired function return')
            before=active['entry']
            if fn=='calc_last':fields(e,{'p','al'});assert_gap=(gap is not None and gap['start']['p_word']==e['fields']['p'])
            elif fn=='phi':
                fields(e,{'p','al','ph','ph_next'})
                if not active['powers']:raise ValueError('phi lacks actual target vspow')
                last_phi={'p_base':before['p_base'],'qv_base':before['qv_base'],'qv_word':before['fields']['qv'],'p_word':e['fields']['p'],'caller_pc':before['caller_pc'],'entry_sequence':before['sequence'],'return_sequence':e['sequence']}
                assert_gap=True
            elif fn=='prep':fields(e,{'rho','th','pii','pf'});assert_gap=True
            else:fields(e,KDM_FIELDS);assert_gap=(e.get('timestep')==completed)
            if not assert_gap:raise ValueError('boundary return/actual gap differs')
            for key in ('caller_pc','bounds'):
                if e.get(key)!=before.get(key):raise ValueError('return metadata differs')
            calls.append((before,e,tuple(active['powers'])));active=None
        else:raise ValueError('unknown phi event')
    if active is not None or pending_guard is not None or pending_prep is not None or power is not None or gap is not None:
        raise ValueError('incomplete phi trace')
    if entered!=4 or completed!=4 or [a['timestep'] for a,b,w in calls if a['function']=='kdm']!=[1,2,3,4]:
        raise ValueError('four KDM boundaries required')
    if len(gaps)!=4 or len([a for a,b,w in calls if a['function']=='prep'])!=4:
        raise ValueError('four gap/preparation boundaries required')
    return calls,powers,gaps,guards


def finite_or_none(value):
    value=float(value)
    return value if np.isfinite(value) else None


def phi_source_reference(entry,ret,power):
    """Source-order REAL32 candidates, not a claim about compiled instructions."""
    x={name:word(value) for name,value in entry['fields'].items()}
    with np.errstate(all='ignore'):
        if entry['hypsometric_opt']==1:
            denominator=add(mul(x['c1'],x['muts']),x['c2'])
            al=mul(div(-1.,denominator),add(mul(x['alb'],mul(x['c1'],x['mu'])),mul(x['rdnw'],sub(x['ph_next'],x['ph']))))
        else:
            pfu=add(add(mul(x['c3f_next'],x['muts']),x['c4f_next']),x['ptop'])
            pfd=add(add(mul(x['c3f'],x['muts']),x['c4f']),x['ptop'])
            phm=add(add(mul(x['c3h'],x['muts']),x['c4h']),x['ptop'])
            dz=sub(add(sub(x['ph_next'],x['ph']),x['phb_next']),x['phb'])
            al=sub(div(div(dz,phm),np.float32(np.log(div(pfd,pfu)))),x['alb'])
        numerator=mul(np.float32(287.),add(x['t0'],x['t']))
        if entry['use_theta_m']!=1:
            ratio=div(np.float32(461.6),np.float32(287.))
            numerator=mul(numerator,add(1.,mul(ratio,x['qv'])))
        eos_x=div(numerator,mul(x['p0'],add(al,x['alb'])))
        observed_x=word(power[0]['input_word']);exponent=word(power[0]['exponent_word']);observed_y=word(power[1]['output_word'])
        power_candidate=np.float32(np.power(observed_x,exponent))
        pressure_from_observed_y=sub(mul(observed_y,x['p0']),x['pb'])
        return {'al_source_order_candidate':finite_or_none(al),
                'al_observed_minus_candidate':finite_or_none(float(word(ret['fields']['al']))-float(al)),
                'eos_X_source_order_candidate':finite_or_none(eos_x),
                'vspow_X_actual':float(observed_x),'vspow_X_actual_minus_candidate':finite_or_none(float(observed_x)-float(eos_x)),
                'vspow_exponent_actual':float(exponent),'vspow_Y_actual_dimensionless':float(observed_y),
                'vspow_Y_source_power_candidate':finite_or_none(power_candidate),
                'vspow_Y_actual_minus_candidate':finite_or_none(float(observed_y)-float(power_candidate)),
                'pressure_Pa_from_actual_Y_candidate':finite_or_none(pressure_from_observed_y),
                'phi_return_pressure_Pa':float(word(ret['fields']['p'])),
                'phi_return_pressure_minus_actual_Y_candidate':finite_or_none(float(word(ret['fields']['p']))-float(pressure_from_observed_y))}


def describe(calls,powers,gaps,guards):
    output=[]
    for entry,ret,local_powers in calls:
        row={'function':entry['function'],'entry_sequence':entry['sequence'],'return_sequence':ret['sequence'],
             'kdm_entered':entry['kdm_entered'],'kdm_completed':entry['kdm_completed'],
             'caller_pc':entry.get('caller_pc'),'caller_class':entry.get('caller_class'),
             'entry_fields_raw':entry['fields'],'return_fields_raw':ret['fields']}
        if entry['function']=='phi':
            row['metadata']={k:entry.get(k) for k in PHI_META}
            row['vspow']=[{'input_word':a['input_word'],'exponent_word':a['exponent_word'],'output_word':b['output_word'],
                           'row_pointer':a['row_pointer'],'lane_index':a['lane_index'],'row_length':a['row_length'],
                           'output_address':a['output_address'],'entry_sequence':a['sequence'],'return_sequence':b['sequence']} for a,b in local_powers]
            row['source_order_reference']=phi_source_reference(entry,ret,local_powers[-1])
        elif entry['function']=='kdm':
            row['timestep']=entry['timestep'];row['TK_entry_derived']=float(mul(word(entry['fields']['th']),word(entry['fields']['pii'])))
            row['TK_return_derived']=float(mul(word(ret['fields']['th']),word(ret['fields']['pii'])))
            row['TK_within_call_change']=row['TK_return_derived']-row['TK_entry_derived']
        output.append(row)
    watches=[]
    for g in gaps:
        watches.append({'start_sequence':g['start']['sequence'],'end_sequence':g['end']['sequence'],
                        'target_address':g['start']['target_address'],'initial_P_Pa_word':g['start']['p_word'],
                        'final_P_prep_input_Pa_word':g['end']['final_word'],'last_phi_return':g['last_phi'],
                        'last_phi_return_matches_prep_P':g['end']['last_phi_matches_prep'],
                        'raw_P_buffer_watch_events':[{'sequence':x['sequence'],'pre_word':x['pre_word'],'post_word':x['post_word'],
                            'reported_pc':x['reported_pc'],'pc_symbol':x.get('pc_symbol'),
                            'units':'raw transient buffer word; may be dimensionless vspow Y, not necessarily Pa'} for x in g['watches']]})
    bridge_rows=[]
    prep_calls=[(a,b) for a,b,_ in calls if a['function']=='prep']
    for before,after in prep_calls:
        candidates=[a for a,b,_ in calls if a['function']=='kdm' and a['sequence']>after['sequence']]
        if not candidates:raise ValueError('prep has no subsequent KDM observation')
        kdm=min(candidates,key=lambda x:x['sequence'])
        gap_candidates=[g for g in gaps if g['end']['sequence']<before['sequence']]
        if not gap_candidates:raise ValueError('prep has no preceding gap')
        g=max(gap_candidates,key=lambda x:x['end']['sequence']);phi=g['last_phi']
        row={'prep_entry_sequence':before['sequence'],'kdm_entry_sequence':kdm['sequence'],'kdm_timestep':kdm['timestep'],
             'gap_end_sequence':g['end']['sequence'],'phi_to_prep_pointer_same':bool(phi and phi['p_base']==before['p_in_base']),
             'phi_return_to_prep_P_word_same':bool(phi and phi['p_word']==before['fields']['p']),
             'phi_return_P_word':phi['p_word'] if phi else None,'prep_input_P_word':before['fields']['p'],
             'phi_qv_pointer_same':bool(phi and phi['qv_base']==before['qv_base']),
             'phi_qv_to_prep_word_same':bool(phi and phi['qv_word']==before['fields']['qv']),'prep_to_KDM':{}}
        for src,dst,sp,kp in (('th','th','th_out_base','th_base'),('pii','pii','pii_out_base','pii_base'),('pf','p','pf_out_base','p_base')):
            row['prep_to_KDM'][src]={'same_pointer':before[sp]==kdm[kp],'same_word':after['fields'][src]==kdm['fields'][dst],
                                      'prep_return_word':after['fields'][src],'KDM_entry_word':kdm['fields'][dst]}
        row['prep_to_KDM']['qv']={'same_pointer':before['qv_base']==kdm['qv_base'],
                                   'same_word':before['fields']['qv']==kdm['fields']['qv'],
                                   'prep_entry_word':before['fields']['qv'],'KDM_entry_word':kdm['fields']['qv']}
        bridge_rows.append(row)
    return {'calls':output,'gap_observations':watches,'value_bridges':bridge_rows,'guard_count':len(guards),'vspow_count':len(powers)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def paired_phi(calls_b1,calls_dm):
    left=[x for x in calls_b1 if x[0]['function']=='phi']
    right=[x for x in calls_dm if x[0]['function']=='phi']
    if len(left)!=len(right):raise ValueError('cross-arm phi call count differs')
    result=[]
    for (a,b,ap),(c,d,cp) in zip(left,right):
        keys=('kdm_entered','kdm_completed','caller_pc','caller_class')
        if any(a.get(k)!=c.get(k) for k in keys) or len(ap)!=len(cp):raise ValueError('cross-arm phi chronology differs')
        if a['fields'].keys()!=c['fields'].keys() or b['fields'].keys()!=d['fields'].keys():raise ValueError('cross-arm phi operands differ')
        delta=lambda x,y:{k:float(word(y[k]))-float(word(x[k])) for k in x}
        result.append({'kdm_entered':a['kdm_entered'],'kdm_completed':a['kdm_completed'],
                       'caller_pc':a['caller_pc'],'caller_class':a['caller_class'],
                       'B1_entry_sequence':a['sequence'],'DM065_entry_sequence':c['sequence'],
                       'entry_DM065_minus_B1':delta(a['fields'],c['fields']),
                       'return_DM065_minus_B1':delta(b['fields'],d['fields']),
                       'vspow_DM065_minus_B1':[{'X':float(word(y[0]['input_word']))-float(word(x[0]['input_word'])),
                                                'exponent':float(word(y[0]['exponent_word']))-float(word(x[0]['exponent_word'])),
                                                'Y_dimensionless':float(word(y[1]['output_word']))-float(word(x[1]['output_word']))} for x,y in zip(ap,cp)]})
    return result


def run_analysis(target,closure_path,freeze_path,schema_path,baseline_path,output):
    closure=json.loads(Path(closure_path).read_text());freeze=json.loads(Path(freeze_path).read_text())
    if sha(closure_path)!=CLOSURE_SHA[target]:raise ValueError('closure pin mismatch')
    if closure.get('status')!='PASS' or closure.get('target')!=target or closure.get('freeze_sha256')!=sha(freeze_path):raise ValueError('closure/freeze mismatch')
    schema_hash=sha(schema_path)
    if [v for k,v in freeze['sha256'].items() if k.endswith('/phi_schema.json')]!=[schema_hash]:raise ValueError('schema freeze mismatch')
    if sha(baseline_path)!='803c398b178db89271976b941a74db7e3a9010ffe16091c94749f5d1feb5ab1c':raise ValueError('selected baseline mismatch')
    observed={};all_calls={};inputs={}
    for arm in ('B1','DM065'):
        identity=closure['arms'][arm];folder=Path(closure_path).parent/arm
        receipt_path=folder/'phi_receipt.json';archive=folder/Path(identity['archived_event_path']).name
        if sha(receipt_path)!=identity['receipt_sha256'] or sha(archive)!=identity['archived_event_sha256'] or archive.stat().st_size!=identity['compressed_bytes']:
            raise ValueError('receipt or archive differs from closure')
        receipt=json.loads(receipt_path.read_text());raw=gzip.decompress(archive.read_bytes());raw_sha=hashlib.sha256(raw).hexdigest()
        if (receipt.get('status')!='PASS_PHI_DISCOVERY' or receipt.get('arm')!=arm or receipt.get('target')!=target or
            receipt.get('event_file_sha256')!=raw_sha or identity['event_file_sha256']!=raw_sha or identity['decompressed_sha256']!=raw_sha or len(raw)!=identity['raw_bytes']):
            raise ValueError('raw capture identity differs')
        calls,powers,gaps,guards=validate_events(archive,target)
        verify_kdm_capture(calls,target,arm,baseline_path)
        observed[arm]=describe(calls,powers,gaps,guards);all_calls[arm]=calls
        inputs[arm]={'receipt_sha256':sha(receipt_path),'archive_sha256':sha(archive),'raw_sha256':raw_sha,'raw_bytes':len(raw)}
    result={'status':'PASS_OBSERVED_PHI_RECOUNT','target':target,'input_hashes':inputs,'closure_sha256':sha(closure_path),
            'freeze_sha256':sha(freeze_path),'schema_sha256':schema_hash,'baseline_sha256':sha(baseline_path),
            'producer_sha256':sha(__file__),'writer_helper_sha256':sha(Path(__file__).with_name('cp02_initial_writer_analysis.py')),'arms':observed,'paired_phi':paired_phi(all_calls['B1'],all_calls['DM065']),
            'limitations':['Source-order REAL32 references are candidates, not instruction-level proof.',
                           'Transient P-buffer watch values can be dimensionless vspow output; phi return and prep input are perturbation pressure in Pa; prep return PF is full pressure.',
                           'KDM counters are observed entered/completed calls, not assumed timestep labels for phi calls.',
                           'Post-watch PCs do not establish the exact store instruction or vector lane.',
                           'The source t operand may be mass coupled and is not labeled physical temperature.']}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target',choices=TARGETS)
    for name in ('closure','freeze','schema','baseline','output'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args()
    run_analysis(a.target,a.closure,a.freeze,a.schema,a.baseline,a.output)
