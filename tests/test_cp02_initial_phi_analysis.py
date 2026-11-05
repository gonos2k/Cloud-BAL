import json
from pathlib import Path
import struct
import sys
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import cp02_initial_phi_analysis as a


def hx(x):return struct.pack('<f',x).hex()


def test_nonhydro_logic_word_is_integer_lowbit_not_float():
    e={'non_hydrostatic_raw_word':'ffffffff','non_hydrostatic':-1,'non_hydrostatic_branch_bit':1,
       'hypsometric_opt':2,'n_moist':6,'runtime_p_qv':2,'param_first_scalar':2,'use_theta_m':1,'k_plus_one':5,'kme':40}
    a.logical_guard(e,4)
    e['non_hydrostatic_branch_bit']=0
    with pytest.raises(ValueError,match='logical'):a.logical_guard(e,4)


def test_hypso2_and_vspow_are_separate_dimensionless_and_pressure_candidates():
    names=a.PHI_FIELDS;f={k:hx(1) for k in names}
    f.update({'ph':hx(1),'ph_next':hx(2),'phb':hx(1),'phb_next':hx(2),'c3f':hx(2),'c3f_next':hx(1),'muts':hx(1),'p0':hx(100000),'pb':hx(90000),'t0':hx(300),'t':hx(1),'qv':hx(.01)})
    entry={'fields':f,'hypsometric_opt':2,'use_theta_m':1};ret={'fields':{'al':hx(0),'p':hx(100)}}
    powentry={'input_word':hx(1.001),'exponent_word':hx(1.4)};powreturn={'output_word':hx(1.01)}
    x=a.phi_source_reference(entry,ret,(powentry,powreturn))
    assert x['vspow_Y_actual_dimensionless']==pytest.approx(np.float32(1.01))
    assert x['pressure_Pa_from_actual_Y_candidate']>1000
    assert 'al_observed_minus_candidate' in x


def test_phi_reader_rejects_unknown_event_and_counter_discontinuity(tmp_path):
    common={'rank':5,'target':'p20183','i':144,'j':142,'k':4,'kdm_entered':0,'kdm_completed':0}
    p=tmp_path/'phi.jsonl';p.write_text(json.dumps({**common,'sequence':1,'event':'unknown'})+'\n')
    with pytest.raises(ValueError,match='unknown'):a.validate_events(p,'p20183')
    p.write_text(json.dumps({**common,'sequence':1,'event':'unknown','kdm_completed':1})+'\n')
    with pytest.raises(ValueError,match='chronology'):a.validate_events(p,'p20183')


def make_complete_trace():
    common={'rank':5,'target':'p20183','i':144,'j':142,'k':4}
    d={'ids':1,'ide':235,'jds':1,'jde':283,'kds':1,'kde':40,
       'ims':1,'ime':234,'jms':1,'jme':282,'kms':1,'kme':40,
       'its':1,'ite':233,'jts':1,'jte':281,'kts':1,'kte':39}
    pbase=0x100000;moist=0x10000000;ni=234;nk=40;nj=282
    target=pbase+4*((142-1)*nk*ni+(4-1)*ni+(144-1));addr=hex(target)
    events=[]
    def put(kind,n,**kw):events.append({**common,'event':kind,'kdm_entered':n,'kdm_completed':n,**kw})
    for n in range(4):
        calc={'caller_pc':'0x3','bounds':d,'p_base':hex(pbase),'acoustic_iteration':4}
        put('function_entry',n,function='calc_last',fields={},**calc)
        put('gap_start',n,target_address=addr,p_word=hx(100),**calc)
        put('function_return',n,function='calc_last',fields={'p':hx(100),'al':hx(1)},**calc)
        guard={'caller_pc':'0x13eb579','caller_class':'solve_em_RK','non_hydrostatic':-1,'non_hydrostatic_raw_word':'ffffffff',
               'non_hydrostatic_branch_bit':1,'hypsometric_opt':2,'n_moist':3,'runtime_p_qv':2,'param_first_scalar':2,
               'use_theta_m':1,'k_plus_one':5,'kme':40}
        put('phi_guard',n,**guard)
        meta={key:value for key,value in guard.items() if key not in ('k_plus_one','kme')}
        meta.update({'p_base':hex(pbase),'al_base':'0x200000','moist_base':hex(moist),'qv_base':hex(moist+ni*nk*nj*4),'bounds':d})
        put('function_entry',n,function='phi',fields={x:hx(1) for x in a.PHI_FIELDS},**meta)
        power={'caller_pc':'0x44','row_pointer':hex(target-4*143),'lane_index':143,'row_length':233,'output_address':addr}
        put('vspow_entry',n,input_word=hx(1),exponent_word=hx(1.4),**power)
        put('gap_watch_after',n,target_address=addr,pre_word=hx(100),post_word=hx(1.01),reported_pc='0x7',instruction_bytes='bytes',registers='registers')
        put('vspow_return',n,output_word=hx(1.01),**power)
        put('gap_watch_after',n,target_address=addr,pre_word=hx(1.01),post_word=hx(10),reported_pc='0x8',instruction_bytes='bytes',registers='registers')
        put('function_return',n,function='phi',fields={'p':hx(10),'al':hx(1),'ph':hx(1),'ph_next':hx(1)},**meta)
        put('gap_end',n,target_address=addr,initial_word=hx(100),final_word=hx(10),watch_events=2,last_phi_p_word=hx(10),last_phi_matches_prep=True)
        prep={'caller_pc':'0x66','bounds':d,'p_in_base':hex(pbase),'th_out_base':'0x300','pii_out_base':'0x400','pf_out_base':'0x500','qv_base':'0x600'}
        inputs={x:hx(1) for x in a.PREP_FIELDS};inputs['p']=hx(10)
        put('function_entry',n,function='prep',fields=inputs,**prep)
        put('function_return',n,function='prep',fields={'rho':hx(1),'th':hx(300),'pii':hx(1),'pf':hx(10)},**prep)
        km={'caller_pc':'0x88','bounds':d,'timestep':n+1,'th_base':'0x300','qv_base':'0x600','pii_base':'0x400','p_base':'0x500'}
        fs={x:hx(1) for x in a.KDM_FIELDS};events.append({**common,'event':'function_entry','kdm_entered':n+1,'kdm_completed':n,'function':'kdm','fields':fs,**km})
        events.append({**common,'event':'function_return','kdm_entered':n+1,'kdm_completed':n+1,'function':'kdm','fields':fs,**km})
    for n,e in enumerate(events,1):e['sequence']=n
    return events


def write_events(path,events):path.write_text(''.join(json.dumps(e)+'\n' for e in events))


def test_complete_nested_phi_vspow_and_dimensionless_watch(tmp_path):
    path=tmp_path/'phi.jsonl';events=make_complete_trace();write_events(path,events)
    calls,powers,gaps,guards=a.validate_events(path,'p20183')
    assert (len(calls),len(powers),len(gaps),len(guards))==(16,4,4,4)
    assert gaps[0]['watches'][0]['post_word']==hx(1.01)
    info=a.describe(calls,powers,gaps,guards)
    assert 'dimensionless' in info['gap_observations'][0]['raw_P_buffer_watch_events'][0]['units']
    events[6]['pre_word']=hx(99);write_events(path,events)
    with pytest.raises(ValueError,match='watch word'):a.validate_events(path,'p20183')


def test_gap_and_phi_must_target_same_buffer_cell(tmp_path):
    events=make_complete_trace();events[4]['p_base']='0x100004'
    path=tmp_path/'bad.jsonl';write_events(path,events)
    with pytest.raises(ValueError,match='phi P pointer'):a.validate_events(path,'p20183')


def test_phi_pairing_rejects_cross_arm_chronology(tmp_path):
    path=tmp_path/'events.jsonl';write_events(path,make_complete_trace())
    calls,_,_,_=a.validate_events(path,'p20183')
    other=[(dict(x),y,z) for x,y,z in calls]
    next(x for x,y,z in other if x['function']=='phi')['kdm_completed']=99
    with pytest.raises(ValueError,match='chronology'):a.paired_phi(calls,other)
