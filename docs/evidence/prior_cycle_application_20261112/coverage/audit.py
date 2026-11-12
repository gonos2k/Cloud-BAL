#!/usr/bin/env python3
"""Diagnostic counts for the predeclared mask; never produces an applied proposal."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def run_driver(exe, inp, out, cwd):
    with (out.with_suffix('.log')).open('x') as log:
        subprocess.run([str(exe),str(inp),str(out)],cwd=cwd,stdout=log,stderr=subprocess.STDOUT,check=True)

def stats(a,mask):
    x=np.asarray(a,dtype=np.float64)[mask]
    return {'count':int(x.size),'min':float(x.min()),'max':float(x.max()),'mean':float(x.mean()),'p25':float(np.percentile(x,25)),'median':float(np.median(x)),'p75':float(np.percentile(x,75))} if x.size else {'count':0}

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,required=True);p.add_argument('--driver-dir',type=Path,required=True);p.add_argument('--definition',type=Path,required=True);p.add_argument('analysis',type=Path);p.add_argument('background',type=Path);p.add_argument('mask',type=Path);p.add_argument('policy',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
    args.repo_root=args.repo_root.resolve();args.driver_dir=args.driver_dir.resolve();args.output=args.output.resolve()
    sys.path.insert(0,str(args.repo_root/'tools'))
    from propose_ice_background import native_time,grid_fingerprint,timestamp
    from initialize_model_moments import read_array,validate_kdm6_policy,STATUS_OK
    args.output.mkdir(parents=True,exist_ok=False)
    ids={k:{'path':str(getattr(args,k).resolve()),'sha256':sha(getattr(args,k))} for k in ('analysis','background','mask','policy')}
    frozen=json.loads(args.definition.read_text())
    artifacts={'script':Path(__file__).resolve(),'definition':args.definition.resolve(),'build_receipt':args.driver_dir/'build_receipt.json','state':args.repo_root/'src/common/cloud_bal_state.f90','common':args.repo_root/'src/common/cloud_bal_microphysics_initialization.f90','producer':args.repo_root/'tools/propose_ice_background.py','handoff':args.repo_root/'tools/initialize_model_moments.py','bulk_adapter':args.repo_root/'tools/ice_background_driver.f90','cell_adapter':args.driver_dir.parent/'cell_driver.f90','bulk_driver':args.driver_dir/'bulk_driver','cell_driver':args.driver_dir/'cell_driver'}
    artifact_before={k:{'path':str(v.resolve()),'sha256':sha(v)} for k,v in artifacts.items()}
    build=json.loads(artifacts['build_receipt'].read_text())
    for key in ('state','common','bulk_adapter','cell_adapter','bulk_driver','cell_driver'):
        if artifact_before[key]['sha256']!=build['artifacts'][key]['sha256']:raise ValueError(f'build identity mismatch: {key}')
    for key, expected in [('analysis',frozen['analysis']['sha256']),('mask',frozen['mask']['sha256']),('policy',frozen['policy_identity']['sha256'])]:
        if ids[key]['sha256']!=expected: raise ValueError(f'{key} differs from frozen identity')
    policy=json.loads(args.policy.read_text());validate_kdm6_policy(policy)
    with Dataset(args.analysis) as a, Dataset(args.background) as b:
        a.set_auto_maskandscale(False);b.set_auto_maskandscale(False)
        at=native_time(a);bt=native_time(b);ag=grid_fingerprint(a);bg=grid_fingerprint(b)
        if at!=bt or ag!=bg or timestamp(b.SIMULATION_START_DATE)>=timestamp(at): raise ValueError('time/grid/prior-cycle mismatch')
        if 'START_DATE' in b.ncattrs() and b.START_DATE!=b.SIMULATION_START_DATE: raise ValueError('cycle metadata mismatch')
        aqi,aqs,ani,al,alb,pressure,pbase,theta,qv=(read_array(a[n],n)[0] for n in ('QICE','QSNOW','QNICE','AL','ALB','P','PB','T','QVAPOR'))
        bqi,bqs,bni,bal,balb,bpressure,bpbase,btheta,bqv=(read_array(b[n],n)[0] for n in ('QICE','QSNOW','QNICE','AL','ALB','P','PB','T','QVAPOR'))
        cycle=b.SIMULATION_START_DATE
    with np.load(args.mask,allow_pickle=False) as m:
        mask=m['valid'];assert str(m['source_sha256'].item())==ids['analysis']['sha256']
    shape=aqi.shape
    if any(x.shape!=shape for x in (aqs,ani,al,alb,pressure,pbase,theta,qv,bqi,bqs,bni,bal,balb,bpressure,bpbase,btheta,bqv,mask)) or not np.isin(mask,(0,1)).all(): raise ValueError('invalid shapes or mask')
    selected=mask.astype(bool)
    if not selected.any():raise ValueError('empty mask')
    expected=(aqi.astype(np.float64)+aqs.astype(np.float64))>0
    if not np.array_equal(selected,expected):raise ValueError('mask differs from fixed positive analysis total')
    den=np.divide(np.float32(1),np.add(al,alb,dtype=np.float32),dtype=np.float32)
    if not np.isfinite(den).all() or np.any(den<=0):raise ValueError('invalid file density')
    dims=np.array(shape[::-1],dtype=np.int32); label=b'06 UTC CONTROL prior forecast'.ljust(256,b' ')
    def write_input(path,sel):
        with path.open('xb') as f:
            dims.tofile(f);np.array(int(timestamp(at).timestamp()),dtype=np.int64).tofile(f);f.write(ag.encode());f.write(label)
            for v in (aqi,aqs,bqi,bqs,bni,den):np.ascontiguousarray(v,dtype=np.float32).tofile(f)
            np.ascontiguousarray(sel,dtype=np.int32).tofile(f)
            for k in ('mass_threshold','lower','upper','number_cap'):np.asarray(policy[k],dtype=np.float64).tofile(f)
    inp=args.output/'fixed.bin';write_input(inp,mask)
    bulk=args.output/'bulk.bin';cell=args.output/'cell.bin'
    run_driver(args.driver_dir/'bulk_driver',inp,bulk,args.output);run_driver(args.driver_dir/'cell_driver',inp,cell,args.output)
    with bulk.open('rb') as f:
        header=np.fromfile(f,dtype=np.int32,count=5);bulk_data=np.fromfile(f,dtype=np.float32)
    with cell.open('rb') as f:
        n=mask.size;status=np.fromfile(f,dtype=np.int32,count=n).reshape(shape);values=np.fromfile(f,dtype=np.float32).reshape((3,*shape));assert not f.read(1)
    successes=selected & (status==STATUS_OK);failures=selected & ~successes
    if np.any(status[~selected]!=-1):raise ValueError('off-mask result')
    first=None
    if failures.any():
        k,j,i=np.argwhere(failures)[0];first=[int(i+1),int(j+1),int(k+1),2]
        if int(header[0])==STATUS_OK or first!=header[1:].tolist():raise ValueError('bulk first failure differs from cell diagnostic')
    elif int(header[0])!=STATUS_OK:raise ValueError('bulk rejected without cell failure')
    # A diagnostic-only subset checks kernel equivalence, never forms an application mask.
    parity=None
    if successes.any():
        subin=args.output/'diagnostic_success_subset.bin';subout=args.output/'diagnostic_success_subset_result.bin';write_input(subin,successes);run_driver(args.driver_dir/'bulk_driver',subin,subout,args.output)
        with subout.open('rb') as f:
            h=np.fromfile(f,dtype=np.int32,count=5);v=np.fromfile(f,dtype=np.float32).reshape((3,*shape))
        parity=bool(h[0]==STATUS_OK and np.array_equal(v[:,successes],values[:,successes]));
        if not parity:raise ValueError('cell and bulk successful results differ')
    if int(header[0])==STATUS_OK:
        v=bulk_data.reshape((3,*shape))
        if not np.array_equal(v[:,selected],values[:,selected]):raise ValueError('full-mask value mismatch')
    target=aqi.astype(np.float64)+aqs.astype(np.float64);bi=bqi.astype(np.float64);bs=bqs.astype(np.float64);bn=bni.astype(np.float64)
    positive=(bi>0)&(bn>0);mean=np.zeros(shape);np.divide(bi,bn,out=mean,where=positive)
    frac=np.zeros(shape);np.divide(bi,bi+bs,out=frac,where=(bi+bs)>0)
    qi=frac*target;qs=np.zeros(shape);np.divide(bs,bi+bs,out=qs,where=(bi+bs)>0);qs*=target
    f32tiny=np.finfo(np.float32).tiny;f32max=np.finfo(np.float32).max
    with np.errstate(over='ignore',under='ignore',invalid='ignore',divide='ignore'):
        qi_stored=qi.astype(np.float32).astype(np.float64)
        ni_est=np.zeros(shape);np.divide(qi_stored,mean,out=ni_est,where=positive)
        ni_stored=ni_est.astype(np.float32)
        volume_ni=np.multiply(ni_stored,den,dtype=np.float32).astype(np.float64)
    # These are overlapping observations, not assigned reasons; exact routine status is authoritative.
    cats={'background_negative_any':(bi<0)|(bs<0)|(bn<0),'background_total_zero':(bi+bs)==0,'background_ice_positive_number_zero':(bi>0)&(bn==0),'background_ice_zero_number_positive':(bi==0)&(bn>0),'background_snow_only':(bi==0)&(bs>0)&(bn==0),'background_mean_outside_policy':positive&((mean<policy['lower'][1])|(mean>policy['upper'][1])), 'computed_mass_nonzero_below_float32_normal':((qi>0)&(qi<f32tiny))|((qs>0)&(qs<f32tiny)), 'computed_mass_above_float32_max':(qi>f32max)|(qs>f32max), 'computed_ni_nonzero_below_float32_normal':(ni_est>0)&(ni_est<f32tiny), 'computed_ni_above_float32_max':ni_est>f32max, 'rounded_ni_times_density_above_policy_cap':volume_ni>policy['number_cap'][1]}
    pfull=pressure.astype(np.float64)+pbase.astype(np.float64);temp=(theta.astype(np.float64)+300)*(pfull/100000)**(287/1004.5)
    bden=np.divide(np.float32(1),np.add(bal,balb,dtype=np.float32),dtype=np.float32)
    if not np.isfinite(bden).all() or np.any(bden<=0):raise ValueError('invalid background density')
    bpfull=bpressure.astype(np.float64)+bpbase.astype(np.float64);btemp=(btheta.astype(np.float64)+300)*(bpfull/100000)**(287/1004.5)
    context={name:{k:stats(v,m) for k,m in [('selected',selected),('failed',failures),('passed',successes)]} for name,v in [('pressure_pa',pfull),('temperature_k',temp),('qv_kg_kg',qv),('file_dry_density_kg_m3',den),('background_pressure_pa',bpfull),('background_temperature_k',btemp),('background_qv_kg_kg',bqv),('background_file_dry_density_kg_m3',bden),('background_minus_analysis_pressure_pa',bpfull-pfull),('background_minus_analysis_temperature_k',btemp-temp),('background_minus_analysis_qv_kg_kg',bqv.astype(np.float64)-qv.astype(np.float64)),('background_minus_analysis_dry_density_kg_m3',bden.astype(np.float64)-den.astype(np.float64))]}
    report={'identities':ids,'analysis_time':at,'background_cycle':cycle,'grid_sha256':ag,'selected':int(selected.sum()),'off_mask':int((~selected).sum()),'accepted':int(successes.sum()),'rejected':int(failures.sum()),'rejected_fraction_of_fixed_mask':float(failures.sum()/selected.sum()),'bulk_status':int(header[0]),'bulk_first_failure_ijk_slot':header[1:].tolist(),'diagnostic_first_failure_ijk_slot':first,'success_subset_bulk_parity':parity,'category_scope':'overlapping input/value observations, not exclusive causes or exact rejection reasons','categories':{k:{'selected':int((v&selected).sum()),'failed':int((v&failures).sum())} for k,v in cats.items()},'physical_context':context,'density_scope':'file proxy float32 1/(AL+ALB), not first-use','selection_scope':'fixed analysis positive ice+snow, independent of background pass','subset_scope':'diagnostic subset only; never published or applied'}
    np.savez_compressed(args.output/'diagnostic_only.npz',status=status,selected_fixed_mask=selected,diagnostic_success_qi=values[0],diagnostic_success_qs=values[1],diagnostic_success_ni=values[2],selected_flat_indices=np.flatnonzero(selected),analysis_qi_selected=aqi[selected],analysis_qs_selected=aqs[selected],analysis_ni_selected=ani[selected],background_qi_selected=bqi[selected],background_qs_selected=bqs[selected],background_ni_selected=bni[selected],analysis_density_selected=den[selected],background_density_selected=bden[selected],analysis_temperature_selected=temp[selected],background_temperature_selected=btemp[selected],analysis_pressure_selected=pfull[selected],background_pressure_selected=bpfull[selected],analysis_qv_selected=qv[selected],background_qv_selected=bqv[selected])
    report['diagnostic_only_npz_sha256']=sha(args.output/'diagnostic_only.npz')
    report['artifact_identities_before']=artifact_before
    report['artifact_identities_after']={k:{'path':v['path'],'sha256':sha(v['path'])} for k,v in artifact_before.items()}
    report['artifact_identities_unchanged']=report['artifact_identities_before']==report['artifact_identities_after']
    if not report['artifact_identities_unchanged']:raise ValueError('source or executable changed')
    report['input_identities_unchanged']=all(sha(v['path'])==v['sha256'] for v in ids.values())
    if not report['input_identities_unchanged']:raise ValueError('input changed')
    (args.output/'coverage.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps(report,indent=2,allow_nan=False))
if __name__=='__main__':main()
