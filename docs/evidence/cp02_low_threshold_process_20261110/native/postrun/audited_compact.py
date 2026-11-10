#!/usr/bin/env python3
"""Audit immutable run, history and raw capture inputs around the reviewed compact collector."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

NATIVE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[5]
RUNTIME=ROOT.parent/'runtime'


def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def raw_files(case):
    return sorted([*case.glob('cp04_t*.bin'),*case.glob('state_selected_*_t*.bin'),*case.glob('surface_cp04_rank*.bin'),*case.glob('state_calls_rank*.txt')])


def inventory(paths):
    return {p.name:{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in paths}


def main():
    arm=sys.argv[1]
    if arm not in ('FIX','CONSERVATIVE','ICE_FIXED'): raise ValueError('invalid arm')
    case=RUNTIME/'forecasts'/arm; review=ROOT/'docs/evidence/cp02_low_threshold_process_20261110/review/launch_go.json'
    reviewed=json.loads(review.read_text()); files=reviewed['sha256']
    artifacts=[NATIVE/'runs/compact.py',NATIVE/'runs/read_frames.py',NATIVE/'schema/schema.json',NATIVE/'source/source_receipt.json',NATIVE/'source/columns.csv',ROOT/'docs/evidence/cp02_protected_process_20261106/native/provenance/collector_v5/cp02_protected_process_capture.py']
    for path in artifacts:
        if files.get(str(path.relative_to(ROOT)))!=sha(path): raise ValueError('reviewed artifact changed: '+str(path))
    run=case/'run_receipt.json'; comparison=case/'history_comparison.json'; runobj=json.loads(run.read_text()); comp=json.loads(comparison.read_text())
    if runobj['status']!='PASS' or comp['status']!='PASS' or comp['run_receipt_sha256']!=sha(run): raise ValueError('history comparison is not bound to the passed run')
    source=json.loads((NATIVE/'source/source_receipt.json').read_text()); build=RUNTIME/f'native_build/variants/{arm}/build_receipt.json'
    buildobj=json.loads(build.read_text()); prepared=json.loads((case/'prepared.json').read_text())
    if reviewed['build_receipt_sha256'][arm]!=sha(build) or prepared['build_receipt_sha256']!=sha(build) or buildobj['source']['sha256']!=source['arms'][arm]['source_sha256']:
        raise ValueError('run build/source identity mismatch')
    if runobj['prepared_sha256']!=sha(case/'prepared.json'): raise ValueError('run prepared receipt mismatch')
    expected_names={f'wrfout_d01_2026-08-16_{h:02d}:00:00' for h in range(12,19)}
    if {Path(row['path']).name for row in runobj['histories']} != expected_names or set(comp['comparisons']) != expected_names:
        raise ValueError('history names differ from the seven expected hourly files')
    for row in runobj['histories']:
        path=Path(row['path']); name=path.name; comparison_row=comp['comparisons'][name]
        if not comparison_row['exact'] or sha(path)!=row['sha256'] or sha(path)!=comparison_row['actual_sha256'] or comparison_row['actual_sha256']!=comparison_row['reference_sha256']:
            raise ValueError('seven-hour exact history changed: '+name)
    if len(runobj['histories'])!=7 or len(comp['comparisons'])!=7: raise ValueError('seven histories required')
    before=inventory(raw_files(case))
    if not before: raise ValueError('missing raw files')
    source_hashes={str(p.relative_to(ROOT)):sha(p) for p in artifacts}; run_hash=sha(run); comp_hash=sha(comparison); review_hash=sha(review)
    result=subprocess.run([sys.executable,'-B',str(NATIVE/'runs/compact.py'),arm],cwd=ROOT,check=False)
    if result.returncode: raise RuntimeError('compact collector failed')
    after=inventory(raw_files(case))
    if before!=after or sha(run)!=run_hash or sha(comparison)!=comp_hash or sha(review)!=review_hash or any(sha(ROOT/name)!=h for name,h in source_hashes.items()): raise ValueError('audited input changed during compaction')
    for row in runobj['histories']:
        if sha(Path(row['path']))!=row['sha256']: raise ValueError('history changed during compaction')
    output=NATIVE/'compact'/arm; capture=output/'capture_receipt.json'; captured=json.loads(capture.read_text())
    if captured['status']!='COMPLETE' or captured['run_receipt_sha256']!=run_hash or captured['history_comparison_sha256']!=comp_hash: raise ValueError('compact receipt mismatches run')
    if sha(output/'raw_inventory.json')!=captured['raw_inventory_sha256']:
        raise ValueError('compact raw inventory hash differs from receipt')
    captured_raw={r['name']:{'sha256':r['sha256'],'size_bytes':r['size_bytes']} for r in json.loads((output/'raw_inventory.json').read_text())}
    if captured_raw!=before: raise ValueError('compact raw inventory differs from audited raw')
    for name,identity in captured['outputs'].items():
        if sha(output/name)!=identity['sha256'] or (output/name).stat().st_size!=identity['size_bytes']: raise ValueError('compact output mismatch')
    proof={'status':'PASS','arm':arm,'review_sha256':review_hash,'auditor_sha256':sha(Path(__file__)),'run_receipt_sha256':run_hash,'history_comparison_sha256':comp_hash,'capture_receipt_sha256':sha(capture),'raw_inventory_sha256':captured['raw_inventory_sha256'],'artifact_hashes':source_hashes,'raw_input_count':len(before),'all_raw_inputs_unchanged':True,'all_history_files_byte_exact':True}
    with (output/'audit_receipt.json').open('x') as f: json.dump(proof,f,indent=2);f.write('\n')


if __name__=='__main__': main()
