import importlib.util
from pathlib import Path
import numpy as np
import pytest

PATH = Path(__file__).with_name('evaluate.py')
spec = importlib.util.spec_from_file_location('sed_evaluate', PATH)
evalmod = importlib.util.module_from_spec(spec); spec.loader.exec_module(evalmod)


def sample():
    # Include every threshold and exact observed weak/dry boundaries.
    obs = np.resize(np.array([0., .099, .1, .5, .999, 1., 5., 10.]), 3688)
    original = obs.copy(); b1 = obs.copy(); candidate = obs.copy()
    # Weak hit lost at 0.1, dry new false alarm, strong hit lost.
    candidate[:8] = [0., .1, 0., .5, .999, 1., 4.9, 10.]
    return {h:{'reference':obs.copy(),'ORIGINAL':original.copy(),
               evalmod.CURRENT:b1.copy(),evalmod.CANDIDATE:candidate.copy()} for h in range(13,19)}


def test_fixed_scope_and_no_threshold_aggregation():
    _, score = evalmod.pinned_modules()
    categorical, continuous, conditions = score.compare_scores(sample())
    assert (len(categorical),len(continuous),len(conditions)) == (108,18,26)
    assert sum(r['goal']=='preserve_current_B1' for r in conditions)==11
    assert sum(r['goal']=='recover_low_threshold_vs_ORIGINAL' for r in conditions)==15
    assert not next(r for r in conditions if r['lead_hour']==1 and r['threshold_mm']==.1)['satisfied']
    assert next(r for r in conditions if r['lead_hour']==1 and r['threshold_mm']==10)['satisfied']
    assert {r['baseline'] for r in conditions if r['goal']=='preserve_current_B1'} == {evalmod.CURRENT}
    assert {r['baseline'] for r in conditions if r['goal']=='recover_low_threshold_vs_ORIGINAL'} == {'ORIGINAL'}


def test_observation_boundaries_and_transitions():
    rows = evalmod.transitions(sample())
    weak = next(r for r in rows if r['lead_hour']==1 and r['baseline']=='ORIGINAL' and r['observation_subset']=='weak_observed')
    dry = next(r for r in rows if r['lead_hour']==1 and r['baseline']=='ORIGINAL' and r['observation_subset']=='dry_observed')
    strong = next(r for r in rows if r['lead_hour']==1 and r['baseline']=='ORIGINAL' and r['observation_subset']=='strong_observed')
    assert weak['forecast_lost']==1 and dry['forecast_gained']==1 and strong['forecast_lost']==1
    assert weak['n_observed_subset']==3*(3688//8)
    for r in rows:
        assert r['n_observed_subset']==sum(r[k] for k in ('forecast_both_below','forecast_gained','forecast_lost','forecast_both_at_or_above'))


def test_scorer_rejects_incomplete_or_nonfinite():
    _, score=evalmod.pinned_modules(); arrays=sample(); arrays[13][evalmod.CANDIDATE][0]=np.nan
    with pytest.raises(ValueError): score.compare_scores(arrays)
    del arrays[18]
    with pytest.raises(ValueError): score.compare_scores(arrays)


def test_proof_rejects_missing_hour_and_changed_history(tmp_path, monkeypatch):
    import json
    runtime = tmp_path/'runtime'; historical = tmp_path/'historical'; historical.mkdir()
    monkeypatch.setattr(evalmod, 'RUNTIME', runtime); monkeypatch.setattr(evalmod, 'HISTORICAL', historical)
    plan_id = {'path':'plan','size_bytes':1,'sha256':'a'}
    cases = {}
    for case in ('CONTROL', 'CONSERVATIVE'):
        d=runtime/'forecasts'/case; d.mkdir(parents=True)
        for name in ('prepared.json','run_receipt.json'): (d/name).write_text('{}')
        driver=runtime/f'{case}_driver_exit.json'; driver.write_text('{}')
        cases[case]={'prepared':evalmod.identity(d/'prepared.json'),'run':evalmod.identity(d/'run_receipt.json'),
                     'driver':evalmod.identity(driver),'all_89_source_hashes_match_base':True,
                     'non_executable_staged_inputs_match_base':True,'input_after_matches_staged':True,
                     'rank_success_count':8,'finite_history_count':7}
    rows=[]
    for hour in range(12,19):
        name=f'wrfout_d01_2026-08-16_{hour:02d}:00:00'; (historical/name).write_text(name)
        for case in ('CONTROL','CONSERVATIVE'): (runtime/'forecasts'/case/name).write_text(name)
        old=evalmod.identity(historical/name); new=evalmod.identity(runtime/'forecasts/CONTROL'/name)
        rows.append({'filename':name,'historical':old,'observed':new,'byte_equal':True,
                     'historical_sha256':old['sha256'],'control_sha256':new['sha256']})
    first=rows[0]; initial=dict(first); initial['observed']=evalmod.identity(runtime/'forecasts/CONSERVATIVE'/first['filename'])
    initial['conservative_sha256']=initial['observed']['sha256']
    proof={'schema':'cp02_sedimentation_forecast_comparability_v1','status':'PASS','plan':plan_id,
           'cases':cases,'control_history_comparison':rows,'candidate_initial_history':initial}
    path=tmp_path/'proof.json'; path.write_text(json.dumps(proof))
    evalmod.verify_proof(path,plan_id)
    proof['control_history_comparison']=rows[:-1]; path.write_text(json.dumps(proof))
    with pytest.raises(ValueError,match='seven histories'): evalmod.verify_proof(path,plan_id)
    proof['control_history_comparison']=rows; path.write_text(json.dumps(proof))
    (runtime/'forecasts/CONTROL'/rows[4]['filename']).write_text('tampered')
    with pytest.raises(ValueError,match='identity differs'): evalmod.verify_proof(path,plan_id)
