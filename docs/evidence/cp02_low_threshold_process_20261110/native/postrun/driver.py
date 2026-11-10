#!/usr/bin/env python3
"""Await completed reviewed runs, then compare histories and audit captures."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

RUNTIME=Path(__file__).resolve().parent
ROOT=RUNTIME.parent/'Cloud-BAL'
BUNDLE=ROOT/'docs/evidence/cp02_low_threshold_process_20261110'
NATIVE=BUNDLE/'native'
ARMS=('FIX','CONSERVATIVE','ICE_FIXED')


def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def verify_reviewed(path):
    review=json.loads((BUNDLE/'review/launch_go.json').read_text())
    if review['sha256'].get(str(path.relative_to(ROOT))) != sha(path):
        raise ValueError('reviewed pipeline code changed: '+str(path))


def command(arm):
    log=RUNTIME/f'{arm}_postrun.log'
    with log.open('xb') as stream:
        for script in (NATIVE/'runs/compare_histories.py',NATIVE/'postrun/audited_compact.py'):
            if script.name=='compare_histories.py': verify_reviewed(script)
            result=subprocess.run([sys.executable,'-B',str(script),arm],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=False)
            if result.returncode: return {'status':'FAIL','script':str(script),'exit_code':result.returncode}
    return {'status':'PASS','audit_receipt_sha256':sha(NATIVE/f'compact/{arm}/audit_receipt.json')}


def main():
    approval=BUNDLE/'review/postrun_go.json'; review=BUNDLE/'review/launch_go.json'
    approved=json.loads(approval.read_text())
    if approved['status']!='GO_FOR_POSTRUN_AUDIT' or approved['auditor_sha256']!=sha(NATIVE/'postrun/audited_compact.py') or approved['launch_review_sha256']!=sha(review): raise ValueError('postrun approval mismatch')
    while not all((RUNTIME/f'{a}_driver_exit.json').exists() for a in ARMS):
        time.sleep(10)
    for arm in ARMS:
        if json.loads((RUNTIME/f'{arm}_driver_exit.json').read_text())['status']!='PASS': raise ValueError('native driver failed: '+arm)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        results=dict(zip(ARMS,executor.map(command,ARMS)))
    proof={'postrun_review_sha256':sha(approval),'launcher_sha256':sha(Path(__file__)),'arms':results,'status':'PASS' if all(x['status']=='PASS' for x in results.values()) else 'FAIL'}
    if proof['status']=='PASS':
        target=NATIVE/'compact/shared_flux_comparison.json'
        verify_reviewed(NATIVE/'runs/compare_shared_flux.py')
        with (RUNTIME/'shared_flux_postrun.log').open('xb') as log:
            run=subprocess.run([sys.executable,'-B',str(NATIVE/'runs/compare_shared_flux.py'),str(target)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=False)
        proof['shared_flux_exit_code']=run.returncode
        if run.returncode: proof['status']='FAIL'
        else: proof['shared_flux_comparison_sha256']=sha(target)
    with (RUNTIME/'postrun_driver_receipt.json').open('x') as f: json.dump(proof,f,indent=2);f.write('\n')


if __name__=='__main__': main()
