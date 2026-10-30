"""The single-species scorer rejects nonselected fields and unpinned inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
from netCDF4 import Dataset

ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'docs/evidence/first_hour_zero_rate_20261030/species_scoring/score_species.py'
spec=importlib.util.spec_from_file_location('species_scorer',p)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


def create(path,rain,snow,pressure=1.):
    with Dataset(path,'w') as d:
        d.createDimension('x',2);d.description='fixture'
        for k,v in [('QRAIN',rain),('QSNOW',snow),('P',pressure)]:
            x=d.createVariable(k,'f4',('x',));x.units='test';x[:]=v


def test_single_field_diff():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        base,donor,candidate=[Path(tmp)/x for x in ('base','donor','candidate')]
        create(base,1,2);create(donor,3,4);create(candidate,3,2)
        common=mod.load_common();mod.verify_single_field(base,donor,candidate,'QRAIN',common)
        create(candidate,3,4)
        with pytest.raises(ValueError,match='unexpected native field difference: QSNOW'):
            mod.verify_single_field(base,donor,candidate,'QRAIN',common)


def test_unpinned_input_gate_before_output(tmp_path,monkeypatch):
    common=mod.load_common();old=common.load_base();_,base,donor=common.PARENTS['H_ORIGINAL_QRQS']
    prep={'schema':'initial_qrain_qsnow_single_species_v1','parent_before':{},'parent_after':{},'parent_unchanged':True,'cases':{}}
    for name,(field,_) in mod.CASES.items():
        prep['cases'][name]={'base_sha256':base,'donor_sha256':donor,'changed_variables':[field],
            'other_variable_values_and_all_metadata_unchanged':True,'prior_case_hashes_before_after_equal':True,
            'all_staged_input_hashes':{'wrfinput_d01':'wrong','wrf.exe':old.FIX_EXE_SHA}}
    f=tmp_path/'prep.json';f.write_text(json.dumps(prep));monkeypatch.setattr(mod,'PREP_SHA',hashlib.sha256(f.read_bytes()).hexdigest())
    cases={k:tmp_path/k for k in mod.CASES}
    for d in cases.values():d.mkdir()
    output=tmp_path/'out'
    with pytest.raises(ValueError,match='incorrect input identity'):
        mod.run(cases,f,tmp_path,tmp_path,tmp_path,output)
    assert not output.exists()
