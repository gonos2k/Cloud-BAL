#!/usr/bin/env python3
"""Bind all three audited captures and exact histories into one analysis proof."""
import hashlib
import json
from pathlib import Path
import sys
import netCDF4
import numpy as np

NATIVE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[5]
RUNTIME=ROOT.parent/'runtime'
ARMS=('FIX','CONSERVATIVE','ICE_FIXED')


def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    launch=ROOT/'docs/evidence/cp02_low_threshold_process_20261110/review/launch_go.json'
    approval=ROOT/'docs/evidence/cp02_low_threshold_process_20261110/review/postrun_go.json'
    post=RUNTIME/'postrun_driver_receipt.json'; postobj=json.loads(post.read_text()); launch_sha=sha(launch)
    if postobj['status']!='PASS' or postobj['postrun_review_sha256']!=sha(approval): raise ValueError('postrun pipeline did not pass under reviewed auditor')
    approved=json.loads(approval.read_text())
    if approved['launch_review_sha256']!=launch_sha: raise ValueError('postrun review does not bind launch review')
    if postobj['launcher_sha256']!=sha(RUNTIME/'postrun_driver.py') or postobj['shared_flux_comparison_sha256']!=sha(NATIVE/'compact/shared_flux_comparison.json'):
        raise ValueError('postrun driver or shared flux output changed')
    schema=NATIVE/'schema/schema.json'; source=NATIVE/'source/source_receipt.json'; sourceobj=json.loads(source.read_text()); results={}
    for arm in ARMS:
        out=NATIVE/'compact'/arm; case=RUNTIME/'forecasts'/arm
        cap=out/'capture_receipt.json'; audit=out/'audit_receipt.json'; history=case/'history_comparison.json'; run=case/'run_receipt.json'
        c=json.loads(cap.read_text());a=json.loads(audit.read_text());h=json.loads(history.read_text());r=json.loads(run.read_text())
        if (c['status']!='COMPLETE' or a['status']!='PASS' or h['status']!='PASS' or r['status']!='PASS' or
            a['review_sha256']!=launch_sha or a['auditor_sha256']!=approved['auditor_sha256'] or
            a['capture_receipt_sha256']!=sha(cap) or a['run_receipt_sha256']!=sha(run) or a['history_comparison_sha256']!=sha(history) or
            c['schema_sha256']!=sha(schema) or c['source_sha256']!=sourceobj['arms'][arm]['source_sha256'] or
            postobj['arms'][arm]['audit_receipt_sha256']!=sha(audit)):
            raise ValueError('capture/run/review proof mismatch: '+arm)
        for name,identity in c['outputs'].items():
            if sha(out/name)!=identity['sha256'] or (out/name).stat().st_size!=identity['size_bytes']: raise ValueError('compact data changed: '+name)
        surface=out/'surface.npz'
        with np.load(surface,allow_pickle=False) as data:
            i=data['i'];j=data['j'];values=data['rain'];initial=data['initial_rain'];valid=data['valid']
            if values.shape!=(1080,77) or not valid.all() or initial.shape!=(77,) or not np.array_equal(data['step'],np.arange(1,1081)):
                raise ValueError('surface coverage differs')
            surface_checks=[]
            for hour in range(7):
                name=f'wrfout_d01_2026-08-16_{12+hour:02d}:00:00'; path=case/name
                row=h['comparisons'][name]
                if sha(path)!=row['actual_sha256'] or row['actual_sha256']!=row['reference_sha256']: raise ValueError('history bytes changed')
                with netCDF4.Dataset(path) as ds:
                    ds.set_auto_maskandscale(False); field=ds.variables['RAINNC'][0,:,:]
                    expected=np.asarray([field[jj-1,ii-1] for ii,jj in zip(i,j)],dtype=np.float32)
                observed=initial if hour==0 else values[hour*180-1,:]
                exact=np.array_equal(expected.view(np.uint32),observed.view(np.uint32))
                if not exact: raise ValueError(f'surface RAINNC differs at {arm} hour {hour}')
                surface_checks.append({'hour':hour,'history_sha256':sha(path),'all_77_columns_bitwise_equal':True})
        results[arm]={'source_sha256':c['source_sha256'],'run_receipt_sha256':sha(run),'history_comparison_sha256':sha(history),'capture_receipt_sha256':sha(cap),'audit_receipt_sha256':sha(audit),'outputs':c['outputs'],'surface_history_binding':surface_checks}
    proof={'status':'PASS','arms':results,'schema_sha256':sha(schema),'source_receipt_sha256':sha(source),'launch_review_sha256':launch_sha,'postrun_review_sha256':sha(approval),'postrun_driver_receipt_sha256':sha(post),'shared_flux_comparison_sha256':postobj['shared_flux_comparison_sha256'],'proof_script_sha256':sha(Path(__file__)),'surface_semantics':'rain is compared to cumulative RAINNC; rainncv remains separate per-call increment'}
    output=NATIVE/'proof/comparability.json';output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as f: json.dump(proof,f,indent=2);f.write('\n')


if __name__=='__main__': main()
