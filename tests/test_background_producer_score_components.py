"""The producer helpers use the existing score operator with fixed paired points."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
helper=load('producer_components',ROOT/'docs/evidence/first_hour_background_policy_20261030/scoring/score_components.py')
base=load('first_hour_scorer',ROOT/'docs/evidence/first_hour_zero_rate_20261030/scoring/score_first_hour.py')


def test_scores_and_reference_transitions():
    values={name:np.zeros(3688) for name in ('PRODUCER_H','PRODUCER_BG','FIX_H','ORIGINAL','FIX_ORIGINAL','reference')}
    values['reference'][0]=1;values['PRODUCER_BG'][0]=1;values['PRODUCER_BG'][1]=1
    categorical,continuous,transitions=helper.score_arrays(values,base.load_scorer())
    row=next(r for r in categorical if r['case']=='PRODUCER_BG' and r['threshold_mm']==1)
    assert (row['hit'],row['miss'],row['false_alarm'],row['CSI'])==(1,0,1,.5)
    assert len(categorical)==30 and len(continuous)==5 and len(transitions)==24
    row=next(r for r in transitions if r['baseline']=='ORIGINAL' and r['threshold_mm']==1)
    assert row['hit_gains']==1 and row['false_alarm_gains']==1
    values['PRODUCER_BG'][3]=np.nan
    with pytest.raises(ValueError,match='invalid array'):helper.score_arrays(values,base.load_scorer())


def test_producer_gate_rejects_unpinned_build(tmp_path,monkeypatch):
    gate=load('producer_gate',ROOT/'docs/evidence/first_hour_background_policy_20261030/scoring/producer_gate.py')
    (tmp_path/'build_receipt.json').write_text('{}')
    monkeypatch.setattr(gate,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='identity mismatch'):
        gate.validate()


def test_candidate_rejects_incomplete_input_manifest(tmp_path,monkeypatch):
    scorer=load('producer_scorer',ROOT/'docs/evidence/first_hour_background_policy_20261030/scoring/score_producer.py')
    monkeypatch.setattr(scorer,'FORECAST',tmp_path)
    (tmp_path/'inputs.json').write_text('{}')
    (tmp_path/'receipt.json').write_text('{}')
    with pytest.raises(ValueError,match='candidate input preparation mismatch'):
        scorer.check_candidate(base,base.load_scorer().evaluator)
