#!/usr/bin/env python3
"""Replay unchanged ice-background common routine on covered cells for diagnostics only."""
import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import struct
from pathlib import Path
import numpy as np

GZIP_SHA='f214c97f45ba5ab5115045d8d8d9058f0907a6cdc650806aeec42b52b97d432a'
STREAM_SHA='4824a2f22cab66a45231c27345c7a21e1130ecea069ffcff80b2770337d64f50'

def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def identities(paths):
    return {name:{'path':str(path),'sha256':sha(path)} for name,path in paths.items()}


def original_stream(paths,work):
    if sha(paths['stream_gzip'])!=GZIP_SHA: raise ValueError('unrecognized original stream gzip')
    f=work/'original.bin'
    with gzip.open(paths['stream_gzip'],'rb') as src, f.open('xb') as dst: shutil.copyfileobj(src,dst,1048576)
    if sha(f)!=STREAM_SHA: raise ValueError('original stream contents differ')
    with f.open('rb') as src:
        header=src.read(340); dims=np.frombuffer(header[:12],dtype='<i4')
        if dims.tolist()!=[234,282,39] or len(header)!=340: raise ValueError('unexpected native dimensions/header')
        if struct.unpack('<q',header[12:20])[0]!=1786881600 or header[20:84].decode()!='97956ad999f5d6cf07213a9497e53d8def3372c77715813cb6b5bd88f7a80d7d': raise ValueError('unexpected valid time or grid fingerprint')
        shape=tuple(dims[::-1]); count=int(np.prod(dims)); fields=[np.fromfile(src,dtype='<f4',count=count).reshape(shape) for _ in range(6)]
        mask=np.fromfile(src,dtype='<i4',count=count).reshape(shape)
        policy=np.fromfile(src,dtype='<f8',count=19)
        if src.read(1) or len(policy)!=19 or not np.isin(mask,(0,1)).all(): raise ValueError('invalid stream trailing bytes or mask')
    with np.load(paths['mask'],allow_pickle=False) as z:
        if not np.array_equal(mask,z['valid']): raise ValueError('frozen mask differs from original stream')
    expected=json.loads(paths['policy'].read_text())
    if not np.array_equal(policy,np.array(expected['mass_threshold']+expected['lower']+expected['upper']+expected['number_cap'])): raise ValueError('stream policy mismatch')
    if int(mask.sum())!=294792: raise ValueError('unexpected frozen mask count')
    return header,shape,fields,mask.astype(bool),policy


def numpy_candidate(aqi,aqs,qi,qs,ni,den,policy,selected):
    """Independent REAL32 storage and REAL64 checks of covered-cell source conditions."""
    lo,hi,cap=policy[6],policy[11],policy[16]
    # Restrict vector computations to selected cells; NaN outside coverage remains untouched.
    q=qi[selected].astype(np.float64);s=qs[selected].astype(np.float64);n=ni[selected].astype(np.float64)
    target=aqi[selected].astype(np.float64)+aqs[selected].astype(np.float64);rho=den[selected]
    valid=np.isfinite(q)&np.isfinite(s)&np.isfinite(n)&(q>=0)&(s>=0)&(n>=0)
    valid &= ~(((q>0)&(n==0))|((q==0)&(n>0)))
    mean=np.zeros(q.shape); positive=(q>0)&(n>0)
    np.divide(q,n,out=mean,where=positive)
    valid &= (~(q>0))|((mean>=lo)&(mean<=hi))
    total=q+s;valid &= (target<=0)|(total!=0)
    f=np.zeros(q.shape);fs=np.zeros(q.shape)
    np.divide(q,total,out=f,where=total>0);np.divide(s,total,out=fs,where=total>0)
    x=f*target;y=fs*target; tiny=np.finfo(np.float32).tiny;huge=np.finfo(np.float32).max
    storable=lambda v:np.isfinite(v)&(v>=0)&(v<=huge)&((v==0)|(v>=tiny))
    valid &= storable(x)&storable(y)
    with np.errstate(over='ignore',under='ignore',invalid='ignore',divide='ignore'):
        x32=x.astype(np.float32);y32=y.astype(np.float32)
        valid &= ~((s>0)&(y32==0))&~((q>0)&(x32==0))
        num=np.zeros(q.shape);np.divide(x32.astype(np.float64),mean,out=num,where=positive)
        valid &= storable(num)
        n32=num.astype(np.float32)
        stored=x32.astype(np.float64)+y32.astype(np.float64)
        tol=np.float64(np.finfo(np.float32).eps)*np.maximum(target,stored)
        valid &= np.abs(stored-target)<=tol
        prod=n32.astype(np.float64)*rho.astype(np.float64)
        valid &= (n32==0)|((prod<=huge)&(prod>=tiny))
        vol=np.multiply(n32,rho,dtype=np.float32)
        valid &= (n32==0)|(vol.astype(np.float64)<=cap)
        ratio=np.zeros(q.shape); np.divide(x32.astype(np.float64),n32.astype(np.float64),out=ratio,where=n32>0)
        valid &= np.where(x32==0,n32==0,(n32>0)&(ratio>=lo)&(ratio<=hi))
    return valid,(x32,y32,n32)


def build(root,coverage,work):
    script='''set -euo pipefail
source "$1/tests/intel_toolchain.sh"
"$CLOUD_BAL_FC" --version > compiler_version.txt
printf '%q ' "$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" > compiler_flags.txt
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" -c "$1/src/common/cloud_bal_state.f90" "$1/src/common/cloud_bal_microphysics_initialization.f90"
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" cloud_bal_state.o cloud_bal_microphysics_initialization.o "$2/cell_driver.f90" -o cell_driver
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" cloud_bal_state.o cloud_bal_microphysics_initialization.o "$1/tools/ice_background_driver.f90" -o bulk_driver
'''
    with (work/'execution.log').open('x') as log: subprocess.run(['bash','-c',script,'replay',str(root),str(coverage)],cwd=work,stdout=log,stderr=subprocess.STDOUT,check=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,required=True);p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--snapshot-receipt',type=Path,required=True);p.add_argument('--work-root',type=Path,required=True);a=p.parse_args()
    root=a.repo_root.resolve(); snapshot=a.snapshot.resolve(); work=a.work_root.resolve(); receipt=a.snapshot_receipt.resolve();coverage=root/'docs/evidence/prior_cycle_application_20261112/coverage'
    if work==root or root in work.parents: raise ValueError('work must be outside source checkout')
    sr=json.loads(receipt.read_text())
    if sr.get('schema')!='coherent_ice_snapshot_receipt_v1' or sr.get('status')!='PASS' or sr.get('snapshot_sha256')!=sha(snapshot) or sr.get('snapshot_file')!=snapshot.name: raise ValueError('validated snapshot receipt binding required')
    paths={'state':root/'src/common/cloud_bal_state.f90','common':root/'src/common/cloud_bal_microphysics_initialization.f90','bulk_adapter':root/'tools/ice_background_driver.f90','cell_adapter':coverage/'cell_driver.f90','toolchain':root/'tests/intel_toolchain.sh','stream_gzip':coverage/'fixed.bin.gz','old_build':coverage/'build_receipt.json','mask':root/'docs/evidence/prior_cycle_application_20261112/frozen_application/mask.npz','policy':root/'docs/evidence/prior_cycle_application_20261112/frozen_application/policy.json','snapshot':snapshot,'snapshot_receipt':receipt,'script':Path(__file__).resolve()}
    before=identities(paths)
    build_receipt=json.loads(paths['old_build'].read_text())
    for name in ('state','common','bulk_adapter','cell_adapter'):
        if before[name]['sha256']!=build_receipt['artifacts'][name]['sha256']: raise ValueError('source differs from PR167 actual build: '+name)
    work.mkdir(parents=True,exist_ok=False)
    header,shape,fields,frozen,policy=original_stream(paths,work)
    with np.load(snapshot,allow_pickle=False) as z:
        observed=z['coverage']; prior=[z[n] for n in ('QI','QS','NI')]
        if observed.shape!=shape or observed.dtype!=np.bool_ or any(x.shape!=shape or x.dtype!=np.float32 for x in prior): raise ValueError('snapshot shape/type mismatch')
        if any(not np.isnan(x[~observed]).all() for x in prior): raise ValueError('uncovered background must stay NaN')
    selected = frozen & observed
    missing = frozen & ~observed
    if (int(selected.sum()), int(missing.sum())) != (288745, 6047):
        raise ValueError('unexpected frozen coverage')
    # This gate is evaluated before any common-routine call. The frozen
    # application cannot proceed; the intersection below is diagnostic only.
    full_application_status = 'STOP_UNCOVERED_BEFORE_COMMON'
    # Uncovered bytes remain NaN, and are never selected; this is not a proposal.
    with (work/'diagnostic.bin').open('xb') as f:
        f.write(header)
        for x in (fields[0],fields[1],*prior,fields[5]): np.ascontiguousarray(x,dtype='<f4').tofile(f)
        np.ascontiguousarray(selected,dtype='<i4').tofile(f);np.asarray(policy,dtype='<f8').tofile(f)
    valid,values=numpy_candidate(fields[0],fields[1],*prior,fields[5],policy,selected)
    build(root,coverage,work)
    run_files=('cell_driver','bulk_driver','diagnostic.bin')
    run_before={n:sha(work/n) for n in run_files}
    with (work/'execution.log').open('a') as log:
        command='set -euo pipefail; source "$1/tests/intel_toolchain.sh"; ./cell_driver diagnostic.bin cell.bin; ./bulk_driver diagnostic.bin bulk.bin'
        subprocess.run(['bash','-c',command,'run',str(root)],cwd=work,stdout=log,stderr=subprocess.STDOUT,check=True)
    run_after={n:sha(work/n) for n in run_files}
    if run_before!=run_after: raise ValueError('driver binary or diagnostic input changed')
    count=int(np.prod(shape))
    cell_output = work / 'cell.bin'
    if cell_output.stat().st_size != 4 * count * 4:
        raise ValueError('cell output length mismatch')
    with cell_output.open('rb') as f:
        status = np.fromfile(f, dtype='<i4', count=count).reshape(shape)
        out = np.fromfile(f, dtype='<f4', count=3 * count).reshape((3, *shape))
        if f.read(1):
            raise ValueError('trailing cell output bytes')
    if np.any(status[~selected]!=-1) or not np.array_equal(status[selected]==20,valid): raise ValueError('NumPy/common cell status mismatch')
    for idx,x in enumerate(values):
        if not np.array_equal(out[idx][selected][valid].view('u4'),x[valid].view('u4')): raise ValueError('NumPy/common accepted bits mismatch')
    bulk_output = work / 'bulk.bin'
    if bulk_output.stat().st_size < 20:
        raise ValueError('truncated bulk output')
    header_out = np.fromfile(bulk_output, dtype='<i4', count=5)
    rejected = selected & (status != 20)
    if rejected.any():
        k,j,i=np.argwhere(rejected)[0]; expected=[-10,int(i+1),int(j+1),int(k+1),2]
        if header_out.tolist() != expected or bulk_output.stat().st_size != 20:
            raise ValueError('bulk first failure or output length mismatch')
    else:
        if int(header_out[0]) != 20 or bulk_output.stat().st_size != 20 + 3 * count * 4:
            raise ValueError('bulk success header or output length mismatch')
        with bulk_output.open('rb') as f:
            f.seek(20)
            bulk_values = np.fromfile(f, dtype='<f4', count=3 * count).reshape((3, *shape))
            if f.read(1):
                raise ValueError('trailing bulk output bytes')
        if not np.array_equal(bulk_values[:, selected].view('u4'), out[:, selected].view('u4')):
            raise ValueError('bulk/cell successful values differ')
    np.savez_compressed(work/'diagnostic_only_NOT_WRF_INPUT.npz',fixed_mask=frozen,coverage=observed,covered_diagnostic_selected=selected,status=status,diagnostic_values=out)
    after=identities(paths)
    if after!=before: raise ValueError('source/input identity changed')
    result={'scope':'Covered-only common-routine numerical diagnostic; NOT proposal, initializer, authority, new applied mask, scientific confidence, or WRF input. Original frozen selection unchanged. Whole application stops before bulk because 6047 selected cells lack capture; only the explicitly diagnostic intersection is passed to the unmodified common routine.','full_application_status':full_application_status,'frozen_selected':int(frozen.sum()),'covered_diagnostic_selected':int(selected.sum()),'uncovered_selected':int(missing.sum()),'covered_common_ok':int(valid.sum()),'covered_common_failed':int((~valid).sum()),'bulk_diagnostic_header':header_out.tolist(),'numpy_status_and_accepted_bits_match':True,'inputs_unchanged':True,'identities_before':before,'identities_after':after,'run_binary_input_sha256_before':run_before,'run_binary_input_sha256_after':run_after,'compiler_version':(work/'compiler_version.txt').read_text(),'compiler_flags':(work/'compiler_flags.txt').read_text(),'binary_sha256':{n:sha(work/n) for n in ('cell_driver','bulk_driver','diagnostic.bin','cell.bin','bulk.bin','diagnostic_only_NOT_WRF_INPUT.npz','execution.log')}}
    (work/'receipt.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
