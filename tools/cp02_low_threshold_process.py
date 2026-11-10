#!/usr/bin/env python3
"""Compare same-column three-arm captures without mixing state and number units."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'docs/evidence/cp02_low_threshold_process_20261110'
SELECTED_POINTS_SHA256='fa729899d1af5abb23d8e6cd7fe0b3b151de512b4c3674864b1d70206df53d92'
ARMS=('FIX','CONSERVATIVE','ICE_FIXED')
HOURS=(1,5,6)
PAIRS=(('ICE_FIXED','CONSERVATIVE'),('CONSERVATIVE','FIX'),('ICE_FIXED','FIX'))
FIELDS={'QV':('q(i,k)','kg kg-1'),'QC':('qci(i,k,1)','kg kg-1'),'QR':('qrs(i,k,1)','kg kg-1'),'QI':('qci(i,k,2)','kg kg-1'),'QS':('qrs(i,k,2)','kg kg-1'),'QG':('qrs(i,k,3)','kg kg-1'),'TK':('t(i,k)','K')}


def identity(path):
    path=Path(path)
    with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(path.resolve()),'sha256':digest,'size_bytes':path.stat().st_size}


def ledger(entry,returned):
    """A contiguous window, fixed native levels; no unobserved gap is bridged."""
    entry,returned=np.asarray(entry,dtype=np.float64),np.asarray(returned,dtype=np.float64)
    if entry.shape!=returned.shape or entry.ndim<2 or len(entry)!=180 or not np.isfinite(entry).all() or not np.isfinite(returned).all():raise ValueError('complete contiguous 180-call arrays required')
    local=(returned-entry).sum(axis=0,dtype=np.float64)
    external=(entry[1:]-returned[:-1]).sum(axis=0,dtype=np.float64)
    endpoint=returned[-1]-entry[0]
    return local,external,endpoint,endpoint-local-external


def weighted(values,indices,weights,valid=None):
    """All positive-weight native corners are required; no renormalization."""
    values=np.asarray(values,dtype=np.float64);indices=np.asarray(indices);weights=np.asarray(weights,dtype=np.float64)
    if values.ndim!=3 or indices.ndim!=2 or indices.shape[1]!=4 or weights.shape!=indices.shape or np.any(indices<0) or np.any(indices>=values.shape[1]):raise ValueError('invalid time,column,k mapping')
    if not np.isfinite(weights).all() or np.any(weights<0) or not np.allclose(weights.sum(axis=1),1,rtol=0,atol=1e-12):raise ValueError('invalid bilinear weights')
    selected=values[:,indices,:]
    allowed=np.isfinite(selected)
    if valid is not None:
        valid=np.asarray(valid,dtype=bool)
        if valid.shape!=values.shape:raise ValueError('validity shape differs')
        allowed &= valid[:,indices,:]
    needed=weights[None,:,:,None]>0
    complete=np.all(allowed|~needed,axis=2)
    result=np.sum(np.where(allowed,selected,0.)*weights[None,:,:,None],axis=2)
    return np.where(complete,result,np.nan),complete


def geometry(rows,i,j):
    lookup={(int(x),int(y)):n for n,(x,y) in enumerate(zip(i,j))}
    if len(lookup)!=len(i):raise ValueError('duplicate native column')
    indices=[];weights=[]
    for r in rows:
        x,y=int(r['native_i0_fortran_one_based']),int(r['native_j0_fortran_one_based'])
        try:indices.append([lookup[x,y],lookup[x+1,y],lookup[x,y+1],lookup[x+1,y+1]])
        except KeyError as error:raise ValueError('selected point has an uncaptured corner') from error
        weights.append([float(r[k]) for k in ('weight_j0_i0','weight_j0_i1','weight_j1_i0','weight_j1_i1')])
    return np.asarray(indices),np.asarray(weights)


def read_capture(folder,arm,schema,proof_arm):
    rp=folder/'capture_receipt.json';r=json.loads(rp.read_text())
    if r['status']!='COMPLETE' or r['arm']!=arm or r['coverage_hours']!=[1,5,6] or r['surface_steps']!=[1,1080] or r['columns']!=77 or r['levels']!=39:raise ValueError('incomplete capture '+arm)
    if proof_arm['capture_receipt_sha256']!=identity(rp)['sha256'] or proof_arm['outputs']!=r['outputs'] or proof_arm['source_sha256']!=r['source_sha256'] or proof_arm['run_receipt_sha256']!=r['run_receipt_sha256'] or proof_arm['history_comparison_sha256']!=r['history_comparison_sha256']:raise ValueError('proof does not bind this capture')
    ap=folder/'audit_receipt.json';audit=json.loads(ap.read_text())
    if audit['status']!='PASS' or audit['arm']!=arm or audit['capture_receipt_sha256']!=identity(rp)['sha256'] or not audit['all_raw_inputs_unchanged'] or not audit['all_history_files_byte_exact']:raise ValueError('audited compact identity or closure missing')
    if proof_arm['audit_receipt_sha256']!=identity(ap)['sha256']:raise ValueError('proof does not bind this audit')
    records=[identity(rp),identity(ap)]
    for name,expected in r['outputs'].items():
        p=folder/name
        if p.is_symlink() or not p.is_file():raise ValueError('unsafe compact input')
        actual=identity(p)
        if any(actual[k]!=expected[k] for k in ('sha256','size_bytes')):raise ValueError('compact hash mismatch '+name)
        records.append(actual)
    if r['schema_sha256']!=identity(schema)['sha256']:raise ValueError('capture schema differs')
    return r,records


def load_hour(folder,hour,contract):
    with np.load(folder/f'h{hour:02d}.npz',allow_pickle=False) as f:a={k:f[k].copy() for k in f.files}
    start=(hour-1)*180+1
    if not np.array_equal(a['step'],np.arange(start,start+180)) or not np.array_equal(a['k'],np.arange(1,40)):raise ValueError('missing or displaced call/level axis')
    if a['i'].ndim!=1 or a['j'].shape!=a['i'].shape or len(a['i'])!=77:raise ValueError('native column scope differs')
    shape=(180,77,39)
    if not np.array_equal(a['entry_fields'],np.asarray(contract['entry_return_fields'])):raise ValueError('wrapper field labels differ')
    for name in ('entry','returned'):
        if a[name].dtype!=np.float32 or a[name].shape!=(*shape,len(contract['entry_return_fields'])):raise ValueError('native wrapper dtype/shape differs')
        mask=a['entry_valid' if name=='entry' else 'return_valid']
        if mask.dtype!=np.bool_ or mask.shape!=shape or not mask.all() or not np.isfinite(a[name]).all():raise ValueError('incomplete wrapper state')
    for name in ('entry','returned'):
        fields=contract['entry_return_fields'];theta=a[name][...,fields.index('TH')];pii=a[name][...,fields.index('PII')];tk=a[name][...,fields.index('TK=TH*PII')]
        if not np.array_equal((theta*pii).view(np.uint32),tk.view(np.uint32)):raise ValueError('native temperature product differs')
    for name in ('core','cond','sed_rsg','sed_ice'):
        key=name+'_delta'
        if a[key].dtype!=np.float64 or a[key].shape!=(*shape,len(contract[key+'_fields'])):raise ValueError('diagnostic delta precision/shape differs: '+key)
        if a[name+'_valid'].dtype!=np.bool_ or a[name+'_valid'].shape!=shape:raise ValueError('delta mask shape differs')
        if not np.array_equal(a[name+'_fields'],np.asarray(contract[key+'_fields'])):raise ValueError('phase field labels differ')
        if not np.isfinite(a[key][a[name+'_valid']]).all():raise ValueError('nonfinite recorded delta')
    return a


def write_csv(path,rows):
    if not rows:raise ValueError('refuse empty table')
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def compare_hour(payloads,hour,points,contract):
    reference=payloads['FIX'];indices,weights=geometry(points,reference['i'],reference['j'])
    for a in payloads.values():
        if any(not np.array_equal(a[k],reference[k]) for k in ('step','i','j','k')):raise ValueError('arm coordinate/time axes differ')
    records=[]
    for upper,lower in PAIRS:
        a,b=payloads[upper],payloads[lower]
        for field,(expression,units) in FIELDS.items():
            wi=contract['entry_return_fields'].index('TK=TH*PII' if field=='TK' else field)
            entry,_=weighted(a['entry'][...,wi].astype(np.float64)-b['entry'][...,wi].astype(np.float64),indices,weights)
            returned,_=weighted(a['returned'][...,wi].astype(np.float64)-b['returned'][...,wi].astype(np.float64),indices,weights)
            local,external,end,residual=ledger(entry,returned)
            stages={}
            for name in ('core','cond','sed_rsg','sed_ice'):
                names=contract[name+'_delta_fields']
                if expression not in names:stages[name]=(None,None);continue
                fi=names.index(expression);valid=a[name+'_valid'] & b[name+'_valid']
                mapped,complete=weighted(a[name+'_delta'][...,fi]-b[name+'_delta'][...,fi],indices,weights,valid)
                stages[name]=(mapped.sum(axis=0,dtype=np.float64),complete.all(axis=0))
            for p,row in enumerate(points):
                for k in range(39):
                    record={'lead_hour':hour,'contrast':upper+'-'+lower,'flat_index_yx':int(row['flat_index_yx']),'cohort':row['cohort'],'native_k_1based':k+1,'field':field,'units':units,'entry_delta':entry[0,p,k],'return_delta':returned[-1,p,k],'local_sum':local[p,k],'external_sum':external[p,k],'endpoint_change':end[p,k],'ledger_residual':residual[p,k]}
                    measured=[]
                    for name,(values,complete) in stages.items():
                        available=values is not None and bool(complete[p,k]);value=float(values[p,k]) if available else None
                        record[name+'_available']=available;record[name+'_sum']=value
                        if available:measured.append(value)
                    record['measured_stage_sum']=sum(measured)
                    record['remaining_internal']=record['local_sum']-record['measured_stage_sum']
                    records.append(record)
    return records




def number_tables(payloads,hour,points,contract):
    base=payloads['FIX'];indices,weights=geometry(points,base['i'],base['j']);public=[];internal=[]
    for field,expression in (('NR','nrs(i,k,1)'),('NI','nci(i,k,2)')):
        index=contract['entry_return_fields'].index(field)
        for upper,lower in PAIRS:
            a,b=payloads[upper],payloads[lower]
            entry,_=weighted(a['entry'][...,index].astype(np.float64)-b['entry'][...,index].astype(np.float64),indices,weights)
            returned,_=weighted(a['returned'][...,index].astype(np.float64)-b['returned'][...,index].astype(np.float64),indices,weights)
            local,external,end,residual=ledger(entry,returned)
            for n,row in enumerate(points):
                for k in range(39):public.append({'lead_hour':hour,'contrast':upper+'-'+lower,'flat_index_yx':int(row['flat_index_yx']),'cohort':row['cohort'],'native_k_1based':k+1,'field':field,'units':'source public kg-1','entry_delta':entry[0,n,k],'return_delta':returned[-1,n,k],'local_sum':local[n,k],'external_sum':external[n,k],'endpoint_change':end[n,k],'ledger_residual':residual[n,k]})
        for arm,a in payloads.items():
            stages={}
            for name in ('core','cond','sed_rsg','sed_ice'):
                fields=contract[name+'_delta_fields']
                if expression not in fields:stages[name]=(None,None);continue
                mapped,complete=weighted(a[name+'_delta'][...,fields.index(expression)],indices,weights,a[name+'_valid'])
                stages[name]=(mapped.sum(axis=0,dtype=np.float64),complete.all(axis=0))
            for n,row in enumerate(points):
                for k in range(39):
                    r={'lead_hour':hour,'arm':arm,'flat_index_yx':int(row['flat_index_yx']),'cohort':row['cohort'],'native_k_1based':k+1,'field':expression,'units':'source internal m-3; temporal sum, not column particle budget'}
                    for name,(values,valid) in stages.items():r[name+'_sum']=float(values[n,k]) if values is not None and valid[n,k] else None
                    internal.append(r)
    return public,internal

def surface_tables(compact,points):
    reference_path=ROOT/'docs/evidence/cp02_ice_false_alarm_20261109/surface/native/hourly_points.csv'
    reference_receipt=reference_path.parent/'receipt.json';ref=json.loads(reference_receipt.read_text())
    if identity(reference_path)['sha256']!=ref['outputs'][reference_path.name]:raise ValueError('frozen surface reference differs')
    with reference_path.open(newline='') as f:
        lookup={(int(r['lead_hour']),r['case'],int(r['flat_index_yx'])):float(r['rainnc_mm']) for r in csv.DictReader(f)}
    case_names={'FIX':'IMPROVED_BG_FIXED','CONSERVATIVE':'CONSERVATIVE_SEDIMENTATION','ICE_FIXED':'FIRST_ICE_VELOCITY'}
    rows=[];traces={'point_ids':np.asarray([int(r['flat_index_yx']) for r in points],np.int32),'step':np.arange(0,1081,dtype=np.int32)}
    for arm in ARMS:
        with np.load(compact/arm/'surface.npz',allow_pickle=False) as f:a={k:f[k].copy() for k in f.files}
        if not np.array_equal(a['step'],np.arange(1,1081)) or a['rain'].dtype!=np.float32 or a['rain'].shape!=(1080,77) or a['valid'].dtype!=np.bool_ or a['valid'].shape!=(1080,77) or not a['valid'].all():raise ValueError('surface call coverage differs')
        if a['initial_rain'].dtype!=np.float32 or a['initial_rain'].shape!=(77,) or not np.isfinite(a['initial_rain']).all():raise ValueError('initial surface values missing')
        indices,weights=geometry(points,a['i'],a['j'])
        full=np.concatenate((a['initial_rain'][None,:],a['rain']),axis=0).astype(np.float64)
        mapped,valid=weighted(full[:,:,None],indices,weights)
        rate,rv=weighted(a['rainncv'][:,:,None],indices,weights)
        if not valid.all() or not rv.all():raise ValueError('missing selected surface value')
        traces[arm+'_rain_cumulative_mm']=mapped[:,:,0]
        traces[arm+'_rainncv_mm']=rate[:,:,0]
        for hour in range(1,7):
            lo,hi=(hour-1)*180,hour*180
            value,_=weighted((full[hi]-full[lo])[None,:,None],indices,weights)
            for q,r in enumerate(points):
                expected=lookup[hour,case_names[arm],int(r['flat_index_yx'])];actual=float(value[0,q,0]);residual=actual-expected
                if abs(residual)>1e-10:raise ValueError('selected source rain does not reproduce stored RAINNC')
                nominal=float(rate[lo:hi,q,0].sum(dtype=np.float64))
                rows.append({'arm':arm,'lead_hour':hour,'flat_index_yx':int(r['flat_index_yx']),'cohort':r['cohort'],'rainnc_counter_hour_mm':actual,'reference_rainnc_hour_mm':expected,'counter_reference_residual_mm':residual,'rainncv_step_sum_mm':nominal,'rainncv_sum_minus_counter_mm':nominal-actual})
    return rows,traces,[identity(reference_path),identity(reference_receipt)]

def run(compact,points_path,schema_path,proof_path,output):
    if os.path.lexists(output):raise FileExistsError(output)
    proof=json.loads(proof_path.read_text())
    if proof['status']!='PASS' or set(proof['arms'])!=set(ARMS) or proof['schema_sha256']!=identity(schema_path)['sha256']:raise ValueError('three-arm comparability proof required')
    if identity(points_path)['sha256']!=SELECTED_POINTS_SHA256:raise ValueError('points differ from the pre-capture selection')
    cohort_receipt=points_path.parent/'receipt.json';cr=json.loads(cohort_receipt.read_text())
    if cr['status']!='COMPLETE' or cr['outputs'][points_path.name]!=SELECTED_POINTS_SHA256:raise ValueError('selection receipt differs')
    source_receipt=BUNDLE/'native/source/source_receipt.json';launch_review=BUNDLE/'review/launch_go.json'
    if proof['source_receipt_sha256']!=identity(source_receipt)['sha256'] or proof['launch_review_sha256']!=identity(launch_review)['sha256']:raise ValueError('source/launch proof differs')
    schema=json.loads(schema_path.read_text());contract=schema['compact_contract']
    with points_path.open(newline='') as f:points=list(csv.DictReader(f))
    if len(points)!=21 or len({r['flat_index_yx'] for r in points})!=21:raise ValueError('frozen representative scope differs')
    inputs=[identity(points_path),identity(cohort_receipt),identity(source_receipt),identity(launch_review),identity(schema_path),identity(proof_path)];receipts={}
    for arm in ARMS:
        receipts[arm],items=read_capture(compact/arm,arm,schema_path,proof['arms'][arm]);inputs+=items
    surface_rows,traces,surface_inputs=surface_tables(compact,points);inputs+=surface_inputs
    rows=[];public_numbers=[];internal_numbers=[]
    for hour in HOURS:
        payloads={arm:load_hour(compact/arm,hour,contract) for arm in ARMS}
        rows+=compare_hour(payloads,hour,points,contract)
        a,b=number_tables(payloads,hour,points,contract);public_numbers+=a;internal_numbers+=b
    if len(rows)!=51597:raise ValueError('paired fixed-level table coverage differs')
    output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.low-process-',dir=output.parent))
    try:
        write_csv(stage/'paired_process_ledger.csv',rows)
        write_csv(stage/'point_surface_hourly.csv',surface_rows)
        write_csv(stage/'public_number_ledger.csv',public_numbers)
        write_csv(stage/'internal_number_stage_sums.csv',internal_numbers)
        np.savez_compressed(stage/'point_surface_traces.npz',**traces)
        limits=['Three-arm differences are coupled forecast responses, not independent physical contributions.','Substep ordinal is not paired across arms with different durations.','Between-call changes include all external operations, not pure transport.','Remaining internal change includes unmeasured stages and temperature conversion/rounding; it is not a full process budget.','Temporal sums at native k are not vertical mass integrals.','Public number-per-mass and internal number-per-volume are not added.']
        summary={'contrasts':[a+'-'+b for a,b in PAIRS],'hours':list(HOURS),'points':21,'levels':39,'rows':len(rows),'surface_rows':len(surface_rows),'public_number_rows':len(public_numbers),'internal_number_rows':len(internal_numbers),'maximum_abs_surface_reference_residual_mm':max(abs(r['counter_reference_residual_mm']) for r in surface_rows),'maximum_abs_ledger_residual_by_field':{f:max(abs(float(r['ledger_residual'])) for r in rows if r['field']==f) for f in FIELDS},'new_forecast_candidate':False,'admission':'21/26; current B1 retained','limits':limits}
        (stage/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        for r in inputs:
            if identity(r['path'])!=r:raise ValueError('input changed while analyzing')
        receipt={'status':'COMPLETE','inputs':inputs,'source':identity(__file__),'outputs':{p.name:identity(p)['sha256'] for p in stage.iterdir()}}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        import cp02_ice_false_alarm as prior
        prior.evaluation.publish_new(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compact',type=Path,required=True);p.add_argument('--points',type=Path,required=True);p.add_argument('--schema',type=Path,required=True);p.add_argument('--proof',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.compact,a.points,a.schema,a.proof,a.output)
