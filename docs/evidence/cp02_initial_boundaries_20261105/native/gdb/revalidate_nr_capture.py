#!/usr/bin/env python3
"""Revalidate preserved discovery data using same-step KDM NR pointer binding."""
import hashlib
import json
import os
import sys
from pathlib import Path

os.environ['CP05_ATTEMPT']='writer_nr20330_02'
import writer_case as case

ROOT=case.base.ROOT
BUNDLE=case.base.BUNDLE
ATTEMPT=case.base.RUNTIME/'gdb_parity/writer_nr20330_02'
PRESERVED=BUNDLE/'native/attempts/writer_nr20330_02'
FAILURE_SHA='fb4f096b17b21af926a62b7259bdf97b1e44e4c0dee50b069560906779816810'
ORIGINAL_FREEZE_SHA='4711dd40a412d339ef5f1a83e9a3e29101d12c459b3a8fae6e71023745f40a08'


def main():
    sha=case.base.sha
    failure=PRESERVED/'failure_receipt.json';freeze=PRESERVED/'writer_freeze.json'
    if sha(failure)!=FAILURE_SHA or sha(freeze)!=ORIGINAL_FREEZE_SHA:
        raise ValueError('prior immutable failure or freeze differs')
    prior=json.loads(failure.read_text())
    if prior['status']!='FAILED_STRICT_COVERAGE_PRESERVED':raise ValueError('prior failure status differs')
    for item in prior['raw_runtime_files']:
        path=Path(item['path'])
        if path.stat().st_size!=item['size_bytes'] or sha(path)!=item['sha256']:
            raise ValueError('prior raw attempt changed: '+str(path))
    original=json.loads(freeze.read_text())
    replacements={str((case.HERE/'writer_case.py').resolve()):PRESERVED/'writer_case.py',
                  str((case.HERE/'test_writer_gate.py').resolve()):PRESERVED/'test_writer_gate.py'}
    for path,digest in original['sha256'].items():
        actual=replacements.get(path,Path(path))
        if sha(actual)!=digest:raise ValueError('original frozen artifact differs: '+path)
    results={}
    for arm in ('B1','DM065'):
        dest=ATTEMPT/arm;failed=dest/'writer_failed_attempt.json'
        old_failure=json.loads(failed.read_text())
        if old_failure.get('error')!='incomplete QNR RK stages':raise ValueError('unexpected original failure')
        case_receipt=json.loads((dest/'case_receipt.json').read_text())
        inputs=case_receipt['inputs'];source=case.base.B1 if arm=='B1' else case.base.DM
        if len(inputs)!=89 or any(sha(dest/n)!=digest for n,digest in inputs.items()):raise ValueError('staged inputs changed')
        if any(sha(source/n)!=digest for n,digest in case_receipt['source_hashes'].items()):raise ValueError('source inputs changed')
        profile=case.base.require_runtime_profile(dest/'wrf.exe')
        if sha(dest/'wrf.exe')!=case.base.EXE_SHA:raise ValueError('executable differs')
        logs=sorted(dest.glob('rsl.out.*'))
        if len(logs)!=8 or any('SUCCESS COMPLETE WRF' not in p.read_text(errors='replace') for p in logs):raise ValueError('rank success markers incomplete')
        debugger=dest/'writer_capture/gdb_rank5.log';text=debugger.read_text(errors='replace')
        if 'exited normally' not in text or 'Python Exception' in text or 'Error occurred in Python' in text:
            raise ValueError('debugger did not finish normally')
        history=dest/'wrfout_d01_2026-08-16_12:00:00';ref=source/history.name
        phase0=json.loads((case.PHASE0/(arm+'_parity_receipt.json')).read_text())
        if sha(history)!=phase0['h00_sha256'] or sha(ref)!=phase0['h00_sha256']:raise ValueError('h00 history differs')
        capture=case.validate_capture(arm,'nr20330',dest)
        results[arm]={'status':'PASS_DISCOVERY_CAPTURE','validation_kind':'pointer-aware revalidation of preserved first completed discovery attempt',
                      'arm':arm,'target':'nr20330','event_file_sha256':capture['event_file_sha256'],
                      'original_failure_receipt_sha256':sha(failed),'h00_sha256':sha(history),
                      'inputs_count':len(inputs),'inputs_unchanged':True,'source_inputs_unchanged':True,
                      'runtime_profile_sha256':profile,'rank_success_markers':len(logs),'gdb_log_sha256':sha(debugger),
                      'original_mpi_exit_evidence':'Frozen original runner raises its recorded RK-stage coverage error only after its MPI-return-code==0 and input-unchanged checks; all eight rank success markers and the GDB inferior normal exit were independently rechecked.',
                      **capture}
    out=BUNDLE/'native/revalidated_nr20330'
    out.mkdir(exist_ok=False)
    for arm,result in results.items():
        (out/(arm+'_receipt.json')).write_text(json.dumps(result,indent=2)+'\n')
    summary={'status':'PASS','scope':'Same-time KDM NR base pointer identifies QNR among index-6 candidates; other candidates remain explicitly unclassified.',
             'original_failure_receipt_sha256':FAILURE_SHA,'original_freeze_sha256':ORIGINAL_FREEZE_SHA,
             'validator_sha256':sha(Path(__file__)),'runner_sha256':sha(case.HERE/'writer_case.py'),
             'synthetic_test_sha256':sha(case.HERE/'test_writer_gate.py'),'synthetic_test_result':'PASS: wrong pointer, missing or duplicate matched stage, unclassified namespace, missing watch and corrupted target rejected',
             'arms':{arm:{'receipt_path':str((out/(arm+'_receipt.json')).resolve()),'receipt_sha256':sha(out/(arm+'_receipt.json'))} for arm in results}}
    (out/'revalidation_receipt.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
