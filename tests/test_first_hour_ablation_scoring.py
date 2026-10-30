"""Ablation scoring rejects non-intervention changes and unpinned input identities."""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT/'docs/evidence/first_hour_zero_rate_20261030/ablation_scoring/score_ablation.py'
spec=importlib.util.spec_from_file_location('score_ablation',PATH)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


def make_file(path, rain, snow, vapor=1., pressure=900.):
    with Dataset(path,'w') as d:
        d.createDimension('x',2);d.test='metadata'
        for name,value in [('QRAIN',rain),('QSNOW',snow),('QVAPOR',vapor),('P',pressure)]:
            v=d.createVariable(name,'f4',('x',));v.units='test';v[:]=value


def test_native_field_swap_detects_unexpected_change(tmp_path):
    base,donor,candidate=(tmp_path/s for s in ('base','donor','candidate'))
    make_file(base,1.,2.);make_file(donor,3.,4.,vapor=5.);make_file(candidate,3.,4.)
    mod.verify_native_intervention(base,donor,candidate)
    make_file(candidate,3.,4.,pressure=901.)
    with pytest.raises(ValueError,match='unexpected native field difference: P'):
        mod.verify_native_intervention(base,donor,candidate)
    make_file(candidate,3.,2.)
    with pytest.raises(ValueError,match='unexpected native field difference: QSNOW'):
        mod.verify_native_intervention(base,donor,candidate)


def test_unpinned_candidate_fails_before_output(tmp_path,monkeypatch):
    cases={k:tmp_path/k for k in mod.CANDIDATES}
    for d in cases.values():d.mkdir()
    prep={'schema':'initial_qrain_qsnow_reciprocal_v1','parent_unchanged':True,'parent_before':{},'parent_after':{},'cases':{}}
    for name,(_,base,donor) in mod.PARENTS.items():
        prep['cases'][name]={'base_sha256':base,'donor_sha256':donor,'changed_variables':['QRAIN','QSNOW'],
          'other_variable_values_and_all_metadata_unchanged':True,'prior_case_hashes_before_after_equal':True,
          'all_staged_input_hashes':{'wrfinput_d01':'arbitrary','wrf.exe':mod.load_base().FIX_EXE_SHA}}
    p=tmp_path/'prep.json';p.write_text(json.dumps(prep));monkeypatch.setattr(mod,'PREPARATION_SHA',hashlib.sha256(p.read_bytes()).hexdigest())
    out=tmp_path/'output'
    with pytest.raises(ValueError,match='invalid preparation identity'):
        mod.run(cases,p,tmp_path,tmp_path,tmp_path,out)
    assert not out.exists()


def test_unexpected_field_change_fails_before_output(tmp_path,monkeypatch):
    ev=mod.load_base().load_scorer().evaluator
    old=mod.load_base();monkeypatch.setattr(mod,'load_base',lambda:old)
    name='H_ORIGINAL_QRQS';base,donor,candidate=(tmp_path/s for s in ('base','donor','candidate'))
    make_file(base,1.,2.);make_file(donor,3.,4.);make_file(candidate,3.,4.,pressure=901.)
    directory=tmp_path/name;directory.mkdir();(directory/'wrfinput_d01').write_bytes(candidate.read_bytes())
    (directory/'wrf.exe').write_bytes(b'fixture executable')
    exe=ev.sha256(directory/'wrf.exe');monkeypatch.setattr(old,'FIX_EXE_SHA',exe)
    hashes={'wrfinput_d01':ev.sha256(directory/'wrfinput_d01'),'wrf.exe':exe}
    monkeypatch.setitem(mod.CANDIDATES,name,hashes['wrfinput_d01'])
    monkeypatch.setitem(mod.PARENTS,name,('FIX_H',ev.sha256(base),ev.sha256(donor)))
    prior=tmp_path/'prior';prior.mkdir()
    monkeypatch.setattr(old,'checked_run',lambda *args: ({'wrfinput_d01':ev.sha256(base),'wrf.exe':exe},[]))
    entry={'base':str(base),'donor':str(donor),'base_sha256':ev.sha256(base),'donor_sha256':ev.sha256(donor),
           'changed_variables':['QRAIN','QSNOW'],'other_variable_values_and_all_metadata_unchanged':True,
           'prior_case_hashes_before_after_equal':True,'prior_case':str(prior),'all_staged_input_hashes':hashes}
    (directory/'inputs.json').write_text(json.dumps(entry))
    prep={'schema':'initial_qrain_qsnow_reciprocal_v1','parent_unchanged':True,'parent_before':{},'parent_after':{},'cases':{name:entry}}
    p=tmp_path/'prep.json';p.write_text(json.dumps(prep));monkeypatch.setattr(mod,'PREPARATION_SHA',ev.sha256(p))
    other=tmp_path/'other';other.mkdir();out=tmp_path/'output'
    with pytest.raises(ValueError,match='unexpected native field difference: P'):
        mod.run({name:directory,'ORIGINAL_H_QRQS':other},p,tmp_path,tmp_path,tmp_path,out)
    assert not out.exists()
