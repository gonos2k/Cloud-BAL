import json
from pathlib import Path
import struct
import sys
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import cp02_initial_writer_analysis as w


def hx(x):return struct.pack('<f',x).hex()


def kdm_events():
    output=[]
    for step in range(1,5):
        for event in ('function_entry','function_return'):
            output.append({'event':event,'rank':5,'target':'nr20330','i':141,'j':142,'k':2,
                           'function':'kdm','timestep':step,'bounds':{},'fields':{k:hx(1) for k in w.FIELDS['kdm'][0]}})
    return output


def save(path,events):
    for i,event in enumerate(events,1):event['sequence']=i
    path.write_text(''.join(json.dumps(e)+'\n' for e in events))


def test_strict_paired_order_and_unknown_events(tmp_path):
    path=tmp_path/'writer.jsonl';events=kdm_events();save(path,events)
    assert len(w.validate_events(path,'nr20330',require_operators=False))==4
    broken=kdm_events();broken[1]['function']='rk';save(path,broken)
    with pytest.raises(ValueError,match='unpaired'):w.validate_events(path,'nr20330',require_operators=False)
    broken=kdm_events();broken.insert(1,{'event':'unknown','rank':5,'target':'nr20330','i':141,'j':142,'k':2});save(path,broken)
    with pytest.raises(ValueError,match='unknown event'):w.validate_events(path,'nr20330',require_operators=False)


def test_rk_reference_uses_rk1_current_not_uninitialized_old():
    event={'rk_step':1,'i':5,'j':5,'k':2,'spec_zone':1,
           'bounds':{'ids':1,'ide':20,'jds':1,'jde':20,'kts':1,'kte':10,'kde':11},
           'fields':{k:hx(v) for k,v in {'scalar_current':2,'scalar_tendency':.5,'advection_tendency':.25,'msfty':2,'c1':1,'c2':0,'mu_old':1,'mu_new':1,'mu_base':0,'dt':2}.items()}}
    assert w.rk_reference(event)==np.float32(4)
    event['rk_step']=2;event['fields']['scalar_old']=hx(5)
    assert w.rk_reference(event)==np.float32(7)


def test_pressure_step_zero_never_requires_or_reads_pm1():
    fields={'ph_k':1,'ph_kplus1':2,'alt':1,'t2':5,'t_save':1,'c2a':2,'mu':1,'mut':2,'c1h':1,'c2h':1,'t0':300,'rdnw':1,'smdiv':.1}
    e={'fields':{k:hx(v) for k,v in fields.items()},'acoustic_iteration':0}
    al,raw,out=w.pressure_reference(e)
    assert np.isfinite([al,raw,out]).all() and raw==out
    e['acoustic_iteration']=1;e['fields']['pm1']=hx(3)
    al,raw,out=w.pressure_reference(e);assert out==w.add(raw,w.mul(np.float32(.1),w.sub(raw,np.float32(3))))


def test_word_validation_rejects_nan_and_bad_hex():
    with pytest.raises(ValueError,match='nonfinite'):w.word('0000c07f')
    with pytest.raises(ValueError,match='invalid'):w.word('abc')


def test_changed_rk_word_requires_matching_watch_chain(tmp_path):
    common={'rank':5,'target':'nr20330','i':141,'j':142,'k':2}
    fields={k:hx(1) for k in w.FIELDS['rk'][0]}
    entry={**common,'event':'function_entry','function':'rk','candidate_timestep':1,'rk_step':1,'target_pointer':'0x123','fields':fields}
    ret={**common,'event':'function_return','function':'rk','candidate_timestep':1,'rk_step':1,'target_pointer':'0x123','fields':{'scalar_old':hx(1),'scalar_current':hx(2)},'watch_events':0}
    path=tmp_path/'writer.jsonl';events=[entry,ret]+kdm_events();save(path,events)
    with pytest.raises(ValueError,match='without observed watch'):w.validate_events(path,'nr20330',require_operators=False)
    watch={**common,'event':'watch_after','owner':'rk_update_scalar','candidate_timestep':1,'rk_step':1,'target_pointer':'0x123','watch_address':'0x123','pre_word':hx(1),'post_word':hx(2),'reported_pc':'0x4','instruction_bytes_around_pc':'bytes','registers':'registers'}
    ret['watch_events']=1;save(path,[entry,watch,ret]+kdm_events());assert len(w.validate_events(path,'nr20330',require_operators=False))==5
    watch['pre_word']=hx(3);save(path,[entry,watch,ret]+kdm_events())
    with pytest.raises(ValueError,match='first watch'):w.validate_events(path,'nr20330',require_operators=False)


def test_strict_reader_requires_actual_operator_coverage(tmp_path):
    path=tmp_path/'writer.jsonl';save(path,kdm_events())
    with pytest.raises(ValueError,match='bounds|RK stages'):w.validate_events(path,'nr20330')


def test_independent_binding_selects_only_actual_kdm_scalar_pointer(tmp_path):
    common={'rank':5,'target':'nr20330','i':141,'j':142,'k':2}
    bounds={'ids':1,'ide':234,'jds':1,'jde':282,'kds':1,'kde':40,
            'ims':1,'ime':234,'jms':1,'jme':282,'kms':1,'kme':40,
            'its':1,'ite':233,'jts':1,'jte':281,'kts':1,'kte':39}
    events=[]
    for step in range(1,5):
        for rk in (1,2,3):
            for pointer in ('0x111','0x222'):
                fields={k:hx(1) for k in w.FIELDS['rk'][0]}
                if rk>1:fields['scalar_old']=hx(1)
                meta={**common,'candidate_timestep':step,'rk_step':rk,'target_pointer':pointer,'qnr_base_pointer':pointer,
                      'scs':6,'sce':6,'runtime_p_qnr':6,'qnr_species_index':6,'bounds':bounds}
                events.append({**meta,'event':'function_entry','function':'rk','fields':fields})
                events.append({**meta,'event':'function_return','function':'rk','fields':{'scalar_old':hx(1),'scalar_current':hx(1)},'watch_events':0})
        fields={k:hx(1) for k in w.FIELDS['kdm'][0]}
        meta={**common,'timestep':step,'nr_base_pointer':'0x222','bounds':bounds}
        events.append({**meta,'event':'function_entry','function':'kdm','fields':fields})
        events.append({**meta,'event':'function_return','function':'kdm','fields':fields})
    path=tmp_path/'writer.jsonl';save(path,events)
    assert len(w.validate_events(path,'nr20330'))==28
    events[0]['runtime_p_qnr']=7;save(path,events)
    with pytest.raises(ValueError,match='scalar identity'):w.validate_events(path,'nr20330')


def test_failed_capture_receipt_never_enters_numerical_analysis(tmp_path):
    schema=tmp_path/'schema.json';schema.write_text(json.dumps({'targets':{'nr20330':{'ijk_1based':[141,142,2]}}}))
    # A rejected or absent capture cannot create a fresh analysis directory.
    output=tmp_path/'out';baseline=tmp_path/'baseline.npz';baseline.write_bytes(b'not-the-pinned-baseline')
    with pytest.raises(ValueError,match='baseline differs'):
        w.run_analysis('nr20330',{'B1':'missing','DM065':'missing'},{'B1':'missing','DM065':'missing'},baseline,output,schema)
    assert not output.exists()


def test_pressure_logical_low_bit_accepts_negative_true_and_rejects_even(tmp_path):
    common={'rank':5,'target':'p20183','i':144,'j':142,'k':4}
    fields={key:hx(1) for key in w.FIELDS['pressure'][0]}
    p={**common,'event':'function_entry','function':'pressure','candidate_timestep':1,'acoustic_iteration':0,'target_pointer':'0x123','non_hydrostatic':-1,'non_hydrostatic_raw_word':'ffffffff','non_hydrostatic_branch_bit':1,'fields':fields,'bounds':{'kme':40}}
    guard={**common,'event':'pressure_guard','candidate_timestep':1,'acoustic_iteration':0,'non_hydrostatic':-1,'non_hydrostatic_raw_word':'ffffffff','non_hydrostatic_branch_bit':1,'k_plus_one':5,'kme':40}
    q={**common,'event':'function_return','function':'pressure','candidate_timestep':1,'acoustic_iteration':0,'target_pointer':'0x123','fields':{k:hx(1) for k in w.FIELDS['pressure'][1]},'watch_events':0,'bounds':{'kme':40}}
    events=[guard,p,q]
    for step in range(1,5):
        meta={**common,'function':'kdm','timestep':step,'bounds':{},'fields':{k:hx(1) for k in w.FIELDS['kdm'][0]}}
        events.extend([{**meta,'event':'function_entry'},{**meta,'event':'function_return'}])
    path=tmp_path/'pressure.jsonl';save(path,events)
    assert len(w.validate_events(path,'p20183',require_operators=False))==5
    p['non_hydrostatic']=-2;p['non_hydrostatic_raw_word']='feffffff';p['non_hydrostatic_branch_bit']=0;guard['non_hydrostatic']=-2;guard['non_hydrostatic_raw_word']='feffffff';guard['non_hydrostatic_branch_bit']=0;save(path,events)
    with pytest.raises(ValueError,match='low bit'):w.validate_events(path,'p20183',require_operators=False)


def test_pressure_guard_must_immediately_match_entry(tmp_path):
    common={'rank':5,'target':'p20183','i':144,'j':142,'k':4}
    guard={**common,'event':'pressure_guard','candidate_timestep':1,'acoustic_iteration':0,'non_hydrostatic':-1,'non_hydrostatic_raw_word':'ffffffff','non_hydrostatic_branch_bit':1,'k_plus_one':5,'kme':40}
    fields={k:hx(1) for k in w.FIELDS['pressure'][0]}
    entry={**common,'event':'function_entry','function':'pressure','candidate_timestep':1,'acoustic_iteration':1,'target_pointer':'0x123','non_hydrostatic':-1,'non_hydrostatic_raw_word':'ffffffff','non_hydrostatic_branch_bit':1,'fields':fields,'bounds':{'kme':40}}
    path=tmp_path/'bad.jsonl';save(path,[guard,entry])
    with pytest.raises(ValueError,match='preceding guard'):w.validate_events(path,'p20183',require_operators=False)


def test_paired_candidates_reject_different_pointer_classification(monkeypatch):
    def event(fn,step,pointer):
        return {'function':fn,'candidate_timestep':step if fn=='rk' else None,'timestep':step if fn=='kdm' else None,
                'rk_step':1 if fn=='rk' else None,'acoustic_iteration':None,'fields':{'value':hx(1)},
                'qnr_base_pointer':pointer,'nr_base_pointer':'bound'}
    # Check cross-arm candidate identity before any scientific delta can be reported.
    monkeypatch.setattr(w,'describe_call',lambda call:{})
    a=event('rk',1,'bound');b=event('rk',1,'other');ka=event('kdm',1,'bound');kb=event('kdm',1,'bound')
    calls_a=[(a,{'fields':{'value':hx(1)}},()),(ka,{'fields':{'value':hx(1)}},())]
    calls_b=[(b,{'fields':{'value':hx(1)}},()),(kb,{'fields':{'value':hx(1)}},())]
    with pytest.raises(ValueError,match='different namespaces'):w.paired_call_records(calls_a,calls_b)
