#!/usr/bin/env python3
"""Freeze source, evaluation, probe, build and privately staged input identities."""
import hashlib,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
RUNTIME=ROOT.parent/'runtime/nn_end'
BUNDLE=HERE.parent

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    build=RUNTIME/'native_build/variants/MP10_NN_END/build_receipt.json';probe_build=RUNTIME/'native_build/variants/MP10_NN_END_PROBE/build_receipt.json';probe=RUNTIME/'probe/probe_receipt.json';prepared=RUNTIME/'forecasts/MP10_NN_END/prepared.json'
    freeze=BUNDLE/'evaluation/freeze.json';evaluation=BUNDLE/'evaluation/evaluate.py';test=BUNDLE/'evaluation/test_nn_frequency_evaluation.py';review=BUNDLE/'evaluation/preflight_review.json'
    f=json.loads(freeze.read_text());r=json.loads(review.read_text());policy=HERE/'policy.json';run=json.loads(prepared.read_text());b=json.loads(build.read_text());pb=json.loads(probe_build.read_text());pr=json.loads(probe.read_text());kernel=json.loads((HERE/'proof/kernel_probe.json').read_text());compare=json.loads((HERE/'proof/build_comparison.json').read_text())
    if f['status']!='FROZEN_BEFORE_FORECAST_EVALUATION' or f['candidate_data_inspected'] or f['policy_sha256']!=sha(policy) or f['evaluation_sha256']!=sha(evaluation) or f['test_sha256']!=sha(test) or r['status']!='PASS_PREFORECAST_REVIEW':raise ValueError('evaluation preflight not frozen')
    if any(x['status']!='PASS' for x in (b,pb,pr,kernel,compare)) or run['status']!='PREPARED':raise ValueError('build/probe/prepared incomplete')
    if run['build_receipt_sha256']!=sha(build) or pr['build_receipt_sha256']!=sha(probe_build) or compare['candidate_build_receipt_sha256']!=sha(build):raise ValueError('build receipt bindings differ')
    source=HERE/'source/MP10_NN_END.f90';exe=Path(b['executable']['path'])
    if b['source']['sha256']!=sha(source) or sha(exe)!=b['executable']['sha256']:raise ValueError('build source or executable changed')
    paths=[Path(__file__),HERE/'launch.py',HERE/'forecast.py',HERE/'rank_wrapper.sh',HERE/'build.py',HERE/'build_probe.py',HERE/'probe.py',HERE/'kernel_probe.py',HERE/'compare_builds.py',policy,source,HERE/'source/source_receipt.json',HERE/'source/generate.py',HERE/'source/MP10_NN_END_PROBE.f90',HERE/'source/probe_source_receipt.json',HERE/'source/generate_probe.py',HERE/'proof/kernel_probe.json',HERE/'proof/build_comparison.json',ROOT/'tests/intel_toolchain.sh',freeze,evaluation,test,review,build,probe_build,probe,prepared,exe,BUNDLE/'native/proof/comparability.json',ROOT/'docs/evidence/cp02_pulse_path_20261110/evaluation/results/receipt.json']
    plan={'status':'FROZEN_PRELAUNCH','schema':'cp02_nn_end_forecast_launch_plan_v1','candidate':'MP10_NN_END','duration_hours':6,'outer_step_seconds':20,'candidate_microphysics_step_seconds':10,'cpu_cores':run['cpus'],'physical_change':'per-loop aerosol NN lower floor applied only on final inner loop; entry floor and each-loop upper cap retained','candidate_evaluation_inspected':False,'admission':'all 26 fixed exact CSI gates individually; no average','inputs_sha256':{str(p.resolve()):sha(p) for p in paths},'prepared_input_count':len(run['inputs']),'prepared_nonexecutable_inputs':'exact copies of the frozen 89-file B1 source set except replacement executable','requirements':['independent launch review','explicit root launch GO','seven history files and initial byte identity to MP10 parent','frozen evaluator only after comparability proof']}
    path=HERE/'launch_plan.json'
    with path.open('x') as stream:json.dump(plan,stream,indent=2);stream.write('\n')
    print('FROZEN',sha(path))
if __name__=='__main__':main()
