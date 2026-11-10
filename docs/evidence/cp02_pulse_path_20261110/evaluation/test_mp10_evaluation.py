import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('mp10_evaluation',Path(__file__).with_name('evaluate.py'))
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)


def arrays():
    obs=np.resize(np.array([0.,.1,.5,1.,2.5,5.,10.,11.]),3688)
    output={}
    for hour in e.HOURS:
        v={'reference':obs.copy(),'flat_index_yx':np.arange(3688),'latitude':np.arange(3688.)/1000,'longitude':np.arange(3688.)/2000}
        v.update({case:obs.copy() for case in e.CASES});output[hour]=v
    return output


def test_complete_tables_and_exact_gate_contract():
    data=arrays();data[13][e.NEW][0]=.1
    categorical,continuous,gates,transitions,bands,weak=e.score(data)
    assert [len(x) for x in (categorical,continuous,gates,transitions,bands,weak)]==[180,30,52,48,1176,60]
    assert len([r for r in gates if r['candidate']==e.NEW and r['goal']=='preserve_current_B1'])==11
    assert len([r for r in gates if r['candidate']==e.NEW and r['goal']=='recover_low_threshold_vs_ORIGINAL'])==15
    row=next(r for r in gates if r['candidate']==e.NEW and r['lead_hour']==1 and r['threshold_mm']==.1)
    assert not row['satisfied']
    transition=next(r for r in transitions if r['lead_hour']==1 and r['baseline']==e.B1 and r['observation_subset']=='dry_observed')
    assert transition['forecast_gained']==1
    assert sum(r['point_count'] for r in bands if r['lead_hour']==1 and r['baseline']==e.B1 and r['forecast_case']==e.NEW)==3688


def test_rejects_changed_cohort_and_negative_precipitation():
    data=arrays();data[14]['flat_index_yx'][0]=99
    with pytest.raises(ValueError,match='cohort'):e.score(data)
    data=arrays();data[16][e.NEW][0]=-.01
    with pytest.raises(ValueError,match='negative'):e.score(data)


def test_proof_must_pass_before_extract(tmp_path):
    proof=tmp_path/'proof.json';proof.write_text(json.dumps({'status':'FAIL','schema':'cp02_pulse_substeps_comparability_v1'}))
    with pytest.raises(ValueError,match='proof must PASS'):e.run(tmp_path,tmp_path,proof,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_symlink_destination_cannot_be_replaced(tmp_path):
    out=tmp_path/'out';out.symlink_to(tmp_path/'absent')
    with pytest.raises(FileExistsError):e.run(tmp_path,tmp_path,tmp_path/'missing',out)


def test_seven_control_histories_and_initial_are_independently_bound(tmp_path):
    previous=tmp_path/'previous';runtime=tmp_path/'runtime'
    previous.mkdir()
    for case in ('CONTROL',e.NEW):(runtime/case).mkdir(parents=True)
    names=[f'wrfout_d01_2026-08-16_{h:02d}:00:00' for h in range(12,19)]
    for name in names:
        (previous/name).write_bytes(name.encode())
        for case in ('CONTROL',e.NEW):(runtime/case/name).write_bytes(name.encode())
    for case in ('CONTROL',e.NEW):
        receipt={'status':'PASS','exit_code':0,'histories':[e.identity(runtime/case/name) for name in names]}
        (runtime/case/'run_receipt.json').write_text(json.dumps(receipt))
    pairs=[{'historical':e.identity(previous/name),'observed':e.identity(runtime/'CONTROL'/name),'byte_equal':True} for name in names]
    payload={'status':'PASS','schema':'cp02_pulse_substeps_comparability_v1','control_history_comparison':pairs,
             'candidate_initial_history':{'historical':e.identity(previous/names[0]),'observed':e.identity(runtime/e.NEW/names[0]),'byte_equal':True}}
    proof=tmp_path/'proof.json';proof.write_text(json.dumps(payload))
    assert e.verify_forecasts(runtime,previous,proof)
    (runtime/'CONTROL'/names[3]).write_bytes(b'tampered')
    with pytest.raises(ValueError,match='control proof identity mismatch'):e.verify_forecasts(runtime,previous,proof)
