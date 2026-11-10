#!/usr/bin/env python3
"""Bind seven six-hour histories, original inputs, candidate build and probe evidence."""
import hashlib,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
FORECAST=HERE.parent
ROOT=FORECAST.parents[3]
RUNTIME=ROOT.parent/'runtime/nn_end'
BUNDLE=FORECAST.parent
PARENT=ROOT.parent.parent/'b1_pulse_path_20261110/runtime/forecasts/MP10'

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    case=RUNTIME/'forecasts/MP10_NN_END';build=RUNTIME/'native_build/variants/MP10_NN_END/build_receipt.json';probe=RUNTIME/'probe/probe_receipt.json';prepared=case/'prepared.json';run=case/'run_receipt.json';driver=RUNTIME/'MP10_NN_END_driver_exit.json';plan=FORECAST/'launch_plan.json'
    a=json.loads(prepared.read_text());b=json.loads(build.read_text());p=json.loads(probe.read_text());r=json.loads(run.read_text());d=json.loads(driver.read_text());parent=json.loads((PARENT/'run_receipt.json').read_text());parent_prepared=json.loads((PARENT/'prepared.json').read_text());policy=FORECAST/'policy.json'
    finite=HERE/'finite_sanity.json';finite_data=json.loads(finite.read_text())
    if finite_data['status']!='PASS' or finite_data['run_receipt_sha256']!=sha(run):raise ValueError('finite audit missing or unbound')
    if any(x['status']!='PASS' for x in (b,p,r,d,parent)) or a['status']!='PREPARED':raise ValueError('run or prerequisite not passed')
    if d['plan_sha256']!=sha(plan) or not d['inputs_unchanged'] or not b['inputs_unchanged'] or r['prepared_sha256']!=sha(prepared) or a['build_receipt_sha256']!=sha(build):raise ValueError('provenance binding mismatch')
    if b['source']['sha256']!=sha(FORECAST/'source/MP10_NN_END.f90') or b['policy']['sha256']!=sha(policy):raise ValueError('source or policy differs')
    if len(a['inputs'])!=89 or a['source_hashes']!=parent_prepared['source_hashes'] or r['inputs_after']!=a['inputs'] or any(a['inputs'][n]!=v for n,v in a['source_hashes'].items() if n!='wrf.exe'):raise ValueError('private input identity differs')
    if a['inputs']['wrf.exe']!=b['executable']['sha256'] or sha(case/'wrf.exe')!=b['executable']['sha256']:raise ValueError('executable differs')
    expected=[f'wrfout_d01_2026-08-16_{h:02d}:00:00' for h in range(12,19)];histories=r['histories']
    if [Path(x['path']).name for x in histories]!=expected:raise ValueError('history schedule differs')
    for row in histories:
        path=Path(row['path'])
        if path.stat().st_size!=row['size_bytes'] or sha(path)!=row['sha256']:raise ValueError('history changed')
    initial=sha(case/expected[0]);initial_reference=sha(PARENT/expected[0]);parent_rows={Path(x['path']).name:x for x in parent['histories']}
    if initial!=initial_reference or initial_reference!=parent_rows[expected[0]]['sha256']:raise ValueError('initial history differs from MP10')
    result={'status':'PASS','schema':'cp02_nn_end_forecast_comparability_v1','candidate_source_sha256':sha(FORECAST/'source/MP10_NN_END.f90'),'parent_source_sha256':json.loads((FORECAST/'source/source_receipt.json').read_text())['parent_sha256'],'policy_sha256':sha(policy),'build_receipt_sha256':sha(build),'probe_receipt_sha256':sha(probe),'prepared_sha256':sha(prepared),'run_receipt_sha256':sha(run),'driver_receipt_sha256':sha(driver),'launch_plan_sha256':sha(plan),'parent_run_receipt_sha256':sha(PARENT/'run_receipt.json'),'parent_prepared_sha256':sha(PARENT/'prepared.json'),'build_comparison_sha256':sha(FORECAST/'proof/build_comparison.json'),'kernel_probe_sha256':sha(FORECAST/'proof/kernel_probe.json'),'finite_sanity_sha256':sha(finite),'executable_sha256':b['executable']['sha256'],'initial_history_sha256':initial,'initial_reference_sha256':initial_reference,'histories':histories,'unchanged_inputs':True,'limitation':'same-case numerical policy sensitivity; passing provenance is not scientific validation'}
    (HERE/'comparability.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
