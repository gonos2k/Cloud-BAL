#!/usr/bin/env python3
"""Bind both complete forecasts to their PR154 bytewise control reference."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
RUNTIME=ROOT.parent/'runtime/forecasts'
PRIOR=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_ice_velocity_20261109/runtime/forecasts/ICE_FIXED')
NAMES=[f'wrfout_d01_2026-08-16_{h:02d}:00:00' for h in range(12,19)]


def identity(path):
    with path.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'path':str(path.resolve()),'sha256':digest,'size_bytes':path.stat().st_size}


def pair(a,b):
    x,y=identity(a),identity(b)
    return {'historical':x,'observed':y,'byte_equal':(x['sha256'],x['size_bytes'])==(y['sha256'],y['size_bytes'])}


def main():
    plan=json.loads((HERE/'launch_plan.json').read_text())
    for case in ('CONTROL','MP10'):
        run=json.loads((RUNTIME/case/'run_receipt.json').read_text())
        if run['status']!='PASS' or run['exit_code']!=0 or {Path(x['path']).name for x in run['histories']}!=set(NAMES): raise ValueError('incomplete '+case)
        for item in run['histories']:
            actual=identity(Path(item['path']))
            if any(item[key]!=actual[key] for key in ('sha256','size_bytes')): raise ValueError('history changed')
        driver=json.loads((RUNTIME.parent/f'{case}_driver_exit.json').read_text())
        if driver['status']!='PASS' or driver['plan_sha256']!=identity(HERE/'launch_plan.json')['sha256']: raise ValueError('driver or plan mismatch')
        prep=identity(RUNTIME/case/'prepared.json')
        if prep['sha256']!=plan['prepared_sha256'][case]: raise ValueError('prepared mismatch')
    old=json.loads((PRIOR/'run_receipt.json').read_text())
    if old['status']!='PASS' or old['exit_code']!=0 or {Path(x['path']).name for x in old['histories']}!=set(NAMES): raise ValueError('prior not passed')
    for item in old['histories']:
        actual=identity(PRIOR/Path(item['path']).name)
        if any(item[key]!=actual[key] for key in ('sha256','size_bytes')): raise ValueError('prior changed')
    control=[pair(PRIOR/name,RUNTIME/'CONTROL'/name) for name in NAMES]
    initial=pair(PRIOR/NAMES[0],RUNTIME/'MP10'/NAMES[0])
    if not all(r['byte_equal'] for r in control) or not initial['byte_equal']: raise ValueError('history mismatch')
    prepared={c:json.loads((RUNTIME/c/'prepared.json').read_text()) for c in ('CONTROL','MP10')}
    if any(prepared['CONTROL']['inputs'][k]!=v for k,v in prepared['MP10']['inputs'].items() if k!='wrf.exe'): raise ValueError('non-executable inputs differ')
    result={'schema':'cp02_pulse_substeps_comparability_v1','status':'PASS','plan':identity(HERE/'launch_plan.json'),
            'policy':identity(HERE.parent/'experiment_policy.json'),'prior_run_receipt':identity(PRIOR/'run_receipt.json'),
            'run_receipts':{c:identity(RUNTIME/c/'run_receipt.json') for c in prepared},
            'prepared_receipts':{c:identity(RUNTIME/c/'prepared.json') for c in prepared},
            'control_history_comparison':control,'candidate_initial_history':initial,
            'scope':'Bytewise control and initial history reproducibility, not scientific validation.'}
    dest=HERE/'proof/comparability.json';dest.parent.mkdir(exist_ok=True)
    with dest.open('x') as f: json.dump(result,f,indent=2);f.write('\n')


if __name__=='__main__': main()
