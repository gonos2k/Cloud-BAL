#!/usr/bin/env python3
"""Close native capture coverage and emit bounded per-hour selected process arrays."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import numpy as np
import netCDF4
from read_frames import frames

NATIVE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[5]
RUNTIME=ROOT.parent/'runtime/forecasts'
MANDATORY=(1,2,3,4,5,6,7,8,11,12)


def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def load_prior():
    path=ROOT/'docs/evidence/cp02_protected_process_20261106/native/provenance/collector_v5/cp02_protected_process_capture.py'
    spec=importlib.util.spec_from_file_location('prior_capture',path); m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    def parse(path,prefix):
        match=re.fullmatch(rf'{re.escape(prefix)}_t(\d{{6}})-(\d{{6}})_rank(\d+)\.bin',Path(path).name)
        if not match: raise ValueError('bad chunk name')
        first,last,rank=map(int,match.groups())
        if first<1 or first%3!=1 or last!=min(first+2,1080): raise ValueError('bad chunk extent')
        return first,last,rank
    m.parse_chunk_filename=parse
    return m,path


def write_npz(path, **arrays):
    with path.open('xb') as f: np.savez_compressed(f,**arrays)


def process_hour(case, arm, hour, steps, cells, inventory, prior, schema, output):
    paths=lambda stem:[p for p in case.glob(stem+'_t*.bin') if prior.parse_chunk_filename(p,stem)[0] in steps]
    cohort=prior.Cohort(cells,[],[],np.empty((0,4)),np.empty((0,4)),{})
    entry,_=prior.read_state_chunks(paths('state_selected_entry'),6,cohort,inventory,steps)
    returned,_=prior.read_state_chunks(paths('state_selected_return'),7,cohort,inventory,steps)
    # Existing reader uses step, k, column, field. Emit documented step, column, k, field.
    entry=entry.transpose(0,2,1,3); returned=returned.transpose(0,2,1,3)
    shape=(len(steps),len(cells),39); ci={cell:n for n,cell in enumerate(cells)}; si={s:n for n,s in enumerate(steps)}
    masks={p:np.zeros(shape,bool) for p in MANDATORY}
    raw={p:np.full(shape+(n,),np.nan,np.float32) for p,n in ((5,39),(6,18),(8,16),(11,13),(12,13))}
    sed={9:np.zeros(shape+(22,),np.float64),20:np.zeros(shape+(10,),np.float64)}
    sediment_count={9:np.zeros(shape,np.int32),20:np.zeros(shape,np.int32)}
    counts={int(k):len(v['fields']) for k,v in schema['phases'].items()}
    absent=schema['arm_overrides']['FIX']['absent_phases'] if arm=='FIX' else schema['arm_overrides']['CONSERVATIVE and ICE_FIXED']['absent_phases']
    for p in absent: counts.pop(p)
    if arm!='FIX': counts[10]=len(schema['arm_overrides']['CONSERVATIVE and ICE_FIXED']['phase_10_fields'])
    framekeys=set(); faces={18:0,22:0,23:0}; max_residual={'rain_mass_kg_m2':0.0,'snow_mass_kg_m2':0.0,'graupel_mass_kg_m2':0.0,'rain_number_m2':0.0,'graupel_volume_m':0.0,'ice_mass_kg_m2':0.0,'ice_number_m2':0.0}
    for path in sorted(paths('cp04')):
        _,_,file_rank=prior.parse_chunk_filename(path,'cp04')
        for header,records in frames(path,counts):
            rank,call,step,j,its,ite,kts,kte=header
            if step not in si or rank!=file_rank or (step,rank,call) not in inventory.calls: raise ValueError('unknown frame owner')
            a,b,c,d,e,f=inventory.calls[(step,rank,call)]
            if (its,ite,kts,kte)!=(a,b,e,f) or not c<=j<=d: raise ValueError('frame bounds differ')
            fk=(step,rank,call,j,its,ite,kts,kte)
            if fk in framekeys: raise ValueError('duplicate frame')
            framekeys.add(fk); local={}
            for phase,i,k,loop,loops,sub,mstep,values in records:
                if (i,j) not in ci or not its<=i<=ite or not kts<=k<=kte: raise ValueError('record outside selected tile')
                ix=(si[step],ci[(i,j)],k-1); key=(i,k,loop,sub,mstep)
                if (phase,key) in local: raise ValueError('duplicate record')
                local[(phase,key)]=values
                if phase in masks:
                    if masks[phase][ix]: raise ValueError('duplicate mandatory phase')
                    masks[phase][ix]=True
                if phase in raw: raw[phase][ix]=values[:raw[phase].shape[-1]]
                if phase in faces: faces[phase]+=1
            for pre,post in ((9,10),(20,21)):
                starts={key for p,key in local if p==pre}; ends={key for p,key in local if p==post}
                if starts!=ends: raise ValueError('unpaired sedimentation')
                expected={(i,k) for i,jj in cells if jj==j and its<=i<=ite for k in range(kts,kte+1)}
                groups={}
                for i,k,loop,sub,mstep in starts: groups.setdefault((i,k),set()).add((sub,mstep))
                if set(groups)!=expected: raise ValueError('missing sediment cell/level')
                for group in groups.values():
                    totals={m for _,m in group}
                    if len(totals)!=1 or {n for n,_ in group}!=set(range(1,next(iter(totals))+1)): raise ValueError('incomplete substeps')
                face=23 if arm=='FIX' and pre==20 else 18 if pre==9 else 22
                if (arm!='FIX' or pre==20) and {key for phase,key in local if phase==face} != starts:
                    raise ValueError('extra or missing native transfer records')
                by_column={}
                for i,k,loop,sub,mstep in starts: by_column.setdefault(i,set()).add(mstep)
                if any(len(ms)!=1 for ms in by_column.values()): raise ValueError('mstep differs across levels of a column')
                for key in sorted(starts):
                    i,k,loop,sub,mstep=key; ix=(si[step],ci[(i,j)],k-1)
                    if sub<1 or sub>mstep: raise ValueError('bad substep')
                    face=23 if arm=='FIX' and pre==20 else 18 if pre==9 else 22
                    if (arm!='FIX' or pre==20) and (face,key) not in local: raise ValueError('missing actual face record')
                    before=local[(pre,key)].astype(np.float64); after=local[(post,key)][:len(before)].astype(np.float64)
                    sed[pre][ix]+=after-before; sediment_count[pre][ix]+=1
                    if arm!='FIX':
                        flux=local[(face,key)].astype(np.float64)
                        if pre==9:
                            # Column mass/number residuals, before float32 state storage rounding.
                            dz=before[11]; rho=before[10]
                            for name,state,lo,hi,scale in (('rain_mass_kg_m2',5,0,1,rho*dz),('snow_mass_kg_m2',6,2,3,rho*dz),('graupel_mass_kg_m2',7,4,5,rho*dz),('rain_number_m2',8,6,7,dz),('graupel_volume_m',13,8,9,rho*dz)):
                                residual=(after[state]-before[state])*scale+flux[lo]-flux[hi]
                                max_residual[name]=max(max_residual[name],abs(float(residual)))
                        else:
                            dz=before[6]; rho=before[5]
                            for name,state,lo,hi,scale in (('ice_mass_kg_m2',3,0,1,rho*dz),('ice_number_m2',4,2,3,dz)):
                                residual=(after[state]-before[state])*scale+flux[lo]-flux[hi]
                                max_residual[name]=max(max_residual[name],abs(float(residual)))
    if framekeys!=prior._expected_frame_keys(inventory,cells,steps): raise ValueError('process frame coverage mismatch')
    if any(not mask.all() for mask in masks.values()): raise ValueError('mandatory process coverage missing')
    if any(not (x>0).all() for x in sediment_count.values()): raise ValueError('sediment coverage missing')
    write_npz(output,step=np.asarray(steps,np.int32),i=np.asarray([x[0] for x in cells],np.int32),j=np.asarray([x[1] for x in cells],np.int32),k=np.arange(1,40,dtype=np.int32),entry=entry,returned=returned,entry_valid=np.ones(shape,bool),return_valid=np.ones(shape,bool),entry_fields=np.asarray(schema['compact_contract']['entry_return_fields']),core_delta=raw[8].astype(np.float64)-raw[6][...,:16].astype(np.float64),core_valid=masks[6]&masks[8],core_fields=np.asarray(schema['compact_contract']['core_delta_fields']),hourly_rate_integral=np.sum(raw[5].astype(np.float64)*raw[6][...,17,None].astype(np.float64),axis=0),rate_fields=np.asarray(schema['phases']['5']['fields'][:39]),cond_delta=raw[12].astype(np.float64)-raw[11].astype(np.float64),cond_valid=masks[11]&masks[12],cond_fields=np.asarray(schema['compact_contract']['cond_delta_fields']),sed_rsg_delta=sed[9],sed_rsg_count=sediment_count[9],sed_rsg_valid=sediment_count[9]>0,sed_rsg_fields=np.asarray(schema['compact_contract']['sed_rsg_delta_fields']),sed_ice_delta=sed[20],sed_ice_count=sediment_count[20],sed_ice_valid=sediment_count[20]>0,sed_ice_fields=np.asarray(schema['compact_contract']['sed_ice_delta_fields']))
    return {'frames':len(framekeys),'face_counts':faces,'max_abs_storage_residual':max_residual if arm!='FIX' else None}


def main():
    arm=sys.argv[1]
    if arm not in ('FIX','CONSERVATIVE','ICE_FIXED'): raise ValueError('invalid arm')
    case=RUNTIME/arm; hist=case/'history_comparison.json'; run=case/'run_receipt.json'
    if json.loads(hist.read_text())['status']!='PASS' or json.loads(run.read_text())['status']!='PASS': raise ValueError('run/history gate failed')
    schema_path=NATIVE/'schema/schema.json'; schema=json.loads(schema_path.read_text())
    rows=list(csv.DictReader((NATIVE/'source/columns.csv').open()));cells=[(int(r['wrf_i_1based']),int(r['wrf_j_1based'])) for r in rows]
    prior,prior_path=load_prior(); inventory=prior.read_call_inventory(case.glob('state_calls_rank*.txt'),cells,steps=1080)
    out=NATIVE/'compact'/arm; out.mkdir(parents=True,exist_ok=False)
    audits={}
    for h in (1,5,6): audits[str(h)]=process_hour(case,arm,h,tuple(range((h-1)*180+1,h*180+1)),cells,inventory,prior,schema,out/f'h{h:02d}.npz')
    cohort=prior.Cohort(cells,[],[],np.empty((0,4)),np.empty((0,4)),{})
    surface=prior.read_surface(case.glob('surface_cp04_rank*.bin'),cohort,inventory,range(1,1081))
    h0=case/'wrfout_d01_2026-08-16_12:00:00'
    with netCDF4.Dataset(h0) as ds:
        ds.set_auto_maskandscale(False); arr=ds.variables['RAINNC'][0,:,:]
        initial=np.asarray([arr[j-1,i-1] for i,j in cells],dtype=np.float32)
    write_npz(out/'surface.npz',step=np.arange(1,1081,dtype=np.int32),i=np.asarray([x[0] for x in cells],np.int32),j=np.asarray([x[1] for x in cells],np.int32),rainncv=surface[:,:,0],rain=surface[:,:,1],sr=surface[:,:,2],valid=np.ones(surface.shape[:2],bool),initial_rain=initial,initial_history_sha256=np.asarray(sha(h0)))
    rawpaths=sorted([*case.glob('cp04_t*.bin'),*case.glob('state_selected_*_t*.bin'),*case.glob('surface_cp04_rank*.bin'),*case.glob('state_calls_rank*.txt')])
    raw=[{'name':p.name,'sha256':sha(p),'size_bytes':p.stat().st_size} for p in rawpaths]
    rawfile=out/'raw_inventory.json'; rawfile.write_text(json.dumps(raw,indent=2)+'\n')
    files={p.name:{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in sorted(out.glob('*.npz'))}
    generated=json.loads((NATIVE/'source/source_receipt.json').read_text())
    receipt={'status':'COMPLETE','arm':arm,'coverage_hours':[1,5,6],'surface_steps':[1,1080],'columns':len(cells),'levels':39,'schema_sha256':sha(schema_path),'source_sha256':generated['arms'][arm]['source_sha256'],'run_receipt_sha256':sha(run),'history_comparison_sha256':sha(hist),'raw_inventory_sha256':sha(rawfile),'prior_collector_sha256':sha(prior_path),'outputs':files,'audit':audits,'residual_policy':'float64 storage residual includes float32 state rounding; no conservation tolerance claimed'}
    (out/'capture_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__': main()
