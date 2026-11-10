import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('nn_frequency_evaluation', Path(__file__).with_name('evaluate.py'))
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)

def data():
    obs = np.resize(np.array([0., .1, .3, .5, .8, 1., 2.5, 5., 10., 11.]), e.POINTS)
    return {h: {'reference':obs.copy(), 'flat_index_yx':np.arange(e.POINTS),
                'latitude':np.arange(e.POINTS)/1000., 'longitude':np.arange(e.POINTS)/2000.,
                **{case:obs.copy() for case in e.CASES}} for h in e.HOURS}

def test_frozen_gate_contract_and_false_alarm():
    p=e.load_policy(); d=data(); d[13][e.NEW][0]=.1
    categorical,continuous,gates,weak,transitions=e.score(d,p)
    assert [len(x) for x in (categorical,continuous,gates,weak,transitions)] == [216,36,26,108,72]
    assert sum(g['goal']=='protection' for g in gates)==11
    assert sum(g['goal']=='recovery' for g in gates)==15
    assert not next(g for g in gates if (g['lead_hour'],g['threshold_mm'])==(1,.1))['satisfied']
    assert next(r for r in transitions if (r['lead_hour'],r['baseline'],r['threshold_mm'])==(1,e.MP10,.1))['false_alarm_created']==1
    assert all(g['satisfied'] for g in gates if (g['lead_hour'],g['threshold_mm'])!=(1,.1))

def test_missing_nonfinite_and_empty_bands_rejected():
    p=e.load_policy(); d=data(); del d[18]
    with pytest.raises(ValueError,match='six hours'): e.score(d,p)
    d=data();d[13][e.NEW][0]=np.nan
    with pytest.raises(ValueError,match='finite'): e.score(d,p)
    d=data();d[13]['reference'][:]=0.
    with pytest.raises(ValueError,match='empty observed weak band'): e.score(d,p)

def test_undefined_threshold_cannot_be_omitted():
    p=e.load_policy();d=data()
    for v in d.values():
        v['reference'][:]=.5
        for case in e.CASES: v[case][:]=.5
    with pytest.raises(ValueError,match='undefined CSI'):e.score(d,p)

def test_sealed_previous_results_unchanged():
    p=e.load_policy();d=e.frozen_arrays(p)
    for v in d.values():v[e.NEW]=v[e.MP10].copy()
    cat,cont,*_=e.score(d,p)
    e.compare_prior(cat,cont)
