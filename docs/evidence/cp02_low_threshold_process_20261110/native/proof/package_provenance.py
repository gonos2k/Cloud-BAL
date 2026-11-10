#!/usr/bin/env python3
"""Package bounded, hash-verified native execution provenance and actual frame samples."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

import netCDF4
import numpy as np

HERE=Path(__file__).resolve().parent
NATIVE=HERE.parent
ROOT=HERE.parents[4]
RUNTIME=ROOT.parent/'runtime'
INPUTS=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_grouped_forecast_20261105/runtime/native_build/inputs')
ARMS=('FIX','CONSERVATIVE','ICE_FIXED')


def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    target=HERE/'native_provenance'; target.mkdir(exist_ok=False)
    items=[]
    def retain(source,relative,compress=False):
        source=Path(source); dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        before=sha(source)
        if compress:
            with source.open('rb') as inp, dest.open('xb') as raw:
                with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=6) as out: shutil.copyfileobj(inp,out,1<<20)
            with gzip.open(dest,'rb') as f: restored=hashlib.file_digest(f,'sha256').hexdigest()
            if restored!=before: raise ValueError('gzip roundtrip mismatch: '+str(source))
        else:
            shutil.copyfile(source,dest)
            if sha(dest)!=before: raise ValueError('copy mismatch: '+str(source))
        if sha(source)!=before: raise ValueError('source changed while packaging: '+str(source))
        if dest.stat().st_size>=100*1024**2: raise ValueError('packaged file exceeds 100 MiB: '+str(dest))
        items.append({'path':str(dest.relative_to(target)),'sha256':sha(dest),'size_bytes':dest.stat().st_size,
                      'original_path':str(source),'original_sha256':before,'original_size_bytes':source.stat().st_size,
                      'encoding':'gzip' if compress else 'identity'})
    retain(INPUTS/'copy_manifest.json',Path('inputs/copy_manifest.json'))
    retain(ROOT/'tests/intel_toolchain.sh',Path('inputs/intel_toolchain.sh'))
    retain(ROOT/'docs/evidence/six_hour_improvement_20261030/runtime/inputs.json',Path('inputs/b1_inputs.json'))
    retain(RUNTIME/'driver_start.json',Path('driver_start.json'))
    retain(RUNTIME/'postrun_driver_receipt.json',Path('postrun_driver_receipt.json'))
    retain(RUNTIME/'finish_pipeline_receipt.json',Path('finish_pipeline_receipt.json'))
    for arm in ARMS:
        build=RUNTIME/'native_build/variants'/arm;run=RUNTIME/'forecasts'/arm;probe=RUNTIME/'probe'/arm
        for name in ('build_receipt.json','compile.log','link.log','ldd.txt','archive_1.log','archive_2.log','archive_3.log'):
            retain(build/name,Path(arm,'build',name))
        for name in ('prepared.json','run_receipt.json','history_comparison.json','namelist.input','launcher.log','descendants.json'):
            retain(run/name,Path(arm,'run',name))
        for name in ('probe_receipt.json','probe_validation.json','namelist.input','launcher.log'):
            retain(probe/name,Path(arm,'probe',name))
        retain(RUNTIME/f'{arm}_driver_exit.json',Path(arm,'driver_exit.json'))
        retain(RUNTIME/f'{arm}_driver.log',Path(arm,'driver.log'))
        for rank in range(8):
            retain(run/f'affinity_rank{rank}.json',Path(arm,'run',f'affinity_rank{rank}.json'))
            for kind in ('out','error'):
                name=f'rsl.{kind}.{rank:04d}'
                retain(run/name,Path(arm,'run',name))
            for stage in ('entry','return'):
                name=f'state_selected_{stage}_t000001-000003_rank{rank}.bin'
                retain(run/name,Path(arm,'sample',name+'.gz'),True)
            raw=run/f'state_calls_rank{rank}.txt'
            lines=[line for line in raw.read_text().splitlines() if int(line.split()[0])<=3]
            if {int(line.split()[0]) for line in lines}!={1,2,3}: raise ValueError('first-three call inventory missing')
            snap=target/arm/'sample'/f'state_calls_rank{rank}_first3.txt';snap.write_text('\n'.join(lines)+'\n')
            items.append({'path':str(snap.relative_to(target)),'sha256':sha(snap),'size_bytes':snap.stat().st_size,
                          'original_path':str(raw),'original_sha256':sha(raw),'original_size_bytes':raw.stat().st_size,
                          'encoding':'identity','selection':'all original rows whose timestep is 1, 2, or 3'})
        present=[]
        for rank in range(8):
            name=f'cp04_t000001-000003_rank{rank}.bin'; path=run/name
            if path.exists():
                retain(path,Path(arm,'sample',name+'.gz'),True);present.append(rank)
        if not present: raise ValueError('missing process frames')
        probe_info=json.loads((probe/'probe_validation.json').read_text())
        if probe_info['status']!='PASS': raise ValueError('probe did not pass')
        # Process files exist only for ranks owning selected columns. Zero-row
        # entry/return streams and call inventories establish all eight owners.
        manifest=target/arm/'sample/process_rank_presence.json'
        manifest.write_text(json.dumps({'present':present,'absent':[n for n in range(8) if n not in present],
            'semantics':'no selected-column process frame on absent rank in the 3-step capture'},indent=2)+'\n')
        items.append({'path':str(manifest.relative_to(target)),'sha256':sha(manifest),'size_bytes':manifest.stat().st_size,'encoding':'generated'})
    # Explicit source-vs-history endpoint evidence: actual native REAL32 bits,
    # one row for each arm/hour/native column, after aggregate proof PASS.
    proof=HERE/'comparability.json'
    if json.loads(proof.read_text())['status']!='PASS': raise ValueError('comparability proof not PASS')
    output=target/'surface_endpoint_bindings.csv'
    with output.open('x',newline='') as f:
        w=csv.writer(f);w.writerow(['arm','hour','i_1based','j_1based','source_rain_float32_hex','history_rainnc_float32_hex','history_sha256'])
        for arm in ARMS:
            with np.load(NATIVE/'compact'/arm/'surface.npz',allow_pickle=False) as data:
                ii=data['i'];jj=data['j']; rain=data['rain']; initial=data['initial_rain']
                for hour in range(7):
                    hist=RUNTIME/'forecasts'/arm/f'wrfout_d01_2026-08-16_{12+hour:02d}:00:00'; hist_sha=sha(hist)
                    with netCDF4.Dataset(hist) as ds:
                        ds.set_auto_maskandscale(False);field=ds.variables['RAINNC'][0,:,:]
                        for n,(i,j) in enumerate(zip(ii,jj)):
                            observed=np.float32(initial[n] if hour==0 else rain[hour*180-1,n]); expected=np.float32(field[j-1,i-1])
                            a=int(observed.view(np.uint32));b=int(expected.view(np.uint32))
                            if a!=b: raise ValueError('endpoint bit mismatch')
                            w.writerow((arm,hour,int(i),int(j),f'{a:08x}',f'{b:08x}',hist_sha))
    items.append({'path':str(output.relative_to(target)),'sha256':sha(output),'size_bytes':output.stat().st_size,'encoding':'generated','rows':3*7*77,'comparability_proof_sha256':sha(proof)})
    receipt={'status':'PASS','arms':list(ARMS),'file_count':len(items),'files':items,
             'total_size_bytes':sum(row['size_bytes'] for row in items),'comparability_proof_sha256':sha(proof),
             'generator_sha256':sha(Path(__file__)),'scope':'actual full-run first-three-step frames; full raw data remain external; no binaries or NetCDF copied'}
    (target/'inventory.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':'PASS','file_count':len(items),'size_bytes':receipt['total_size_bytes'],'inventory_sha256':sha(target/'inventory.json')},indent=2))


if __name__=='__main__': main()
