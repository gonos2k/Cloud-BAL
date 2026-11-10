import importlib.util
from pathlib import Path
import numpy as np
import pytest

P=Path(__file__).resolve().parents[1]/'tools/cp02_low_threshold_process.py'
s=importlib.util.spec_from_file_location('low_process',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def test_ledger_counts_external_change_and_does_not_bridge_gaps():
    entry=np.arange(180,dtype=float)[:,None]*.25
    returned=entry+.125
    local,external,end,residual=m.ledger(entry,returned)
    assert local[0]==22.5 and external[0]==22.375
    assert end[0]==44.875 and residual[0]==0
    with pytest.raises(ValueError,match='180-call'):m.ledger(entry[:-1],returned[:-1])


def test_positive_weight_missing_is_missing_and_no_renormalization():
    v=np.array([[[2.],[4.],[6.],[8.]]]);index=np.array([[0,1,2,3]]);w=np.array([[.1,.2,.3,.4]])
    got,valid=m.weighted(v,index,w);assert got[0,0,0]==6 and valid.all()
    v[0,2,0]=np.nan;got,valid=m.weighted(v,index,w);assert np.isnan(got[0,0,0]) and not valid.any()
    w=np.array([[.25,.25,0,.5]]);got,valid=m.weighted(v,index,w);assert got[0,0,0]==5.5 and valid.all()
    with pytest.raises(ValueError,match='weights'):m.weighted(v,index,w*.5)


def test_geometry_retains_all_four_fortran_corners():
    row={'native_i0_fortran_one_based':'137','native_j0_fortran_one_based':'72','weight_j0_i0':'.1','weight_j0_i1':'.2','weight_j1_i0':'.3','weight_j1_i1':'.4'}
    idx,w=m.geometry([row],np.array([138,137,138,137]),np.array([73,72,72,73]))
    assert idx.tolist()==[[1,2,3,0]] and np.allclose(w,[[.1,.2,.3,.4]])
    with pytest.raises(ValueError,match='uncaptured'):m.geometry([row],np.array([137]),np.array([72]))


def test_native_float32_difference_is_taken_in_float64():
    import json
    contract=json.loads((P.parents[1]/'docs/evidence/cp02_low_threshold_process_20261110/native/schema/schema.json').read_text())['compact_contract']
    shape=(180,4,39);payloads={}
    for arm in m.ARMS:
        a={'step':np.arange(1,181),'i':np.array([137,138,137,138]),'j':np.array([72,72,73,73]),'k':np.arange(1,40)}
        for name in ('entry','returned'):a[name]=np.zeros(shape+(16,),np.float32)
        for name in ('core','cond','sed_rsg','sed_ice'):
            a[name+'_delta']=np.zeros(shape+(len(contract[name+'_delta_fields']),),np.float64);a[name+'_valid']=np.ones(shape,bool)
        payloads[arm]=a
    payloads['ICE_FIXED']['returned'][...,1]=1.
    payloads['CONSERVATIVE']['returned'][...,1]=np.float32(1e-10)
    row={'flat_index_yx':'1','cohort':'test','native_i0_fortran_one_based':'137','native_j0_fortran_one_based':'72','weight_j0_i0':'.1','weight_j0_i1':'.2','weight_j1_i0':'.3','weight_j1_i1':'.4'}
    records=m.compare_hour(payloads,1,[row],contract)
    result=next(r for r in records if r['contrast']=='ICE_FIXED-CONSERVATIVE' and r['field']=='QV' and r['native_k_1based']==1)
    assert .9999999<result['return_delta']<1.
    assert result['local_sum']<180.


def test_capture_proof_must_bind_audit_and_data(tmp_path):
    import json
    schema=tmp_path/'schema.json';schema.write_text('{}')
    data=tmp_path/'h01.npz';data.write_bytes(b'compact')
    cap={'status':'COMPLETE','arm':'FIX','coverage_hours':[1,5,6],'surface_steps':[1,1080],'columns':77,'levels':39,'source_sha256':'s','run_receipt_sha256':'r','history_comparison_sha256':'h','schema_sha256':m.identity(schema)['sha256'],'outputs':{'h01.npz':{k:v for k,v in m.identity(data).items() if k!='path'}}}
    rp=tmp_path/'capture_receipt.json';rp.write_text(json.dumps(cap))
    ap=tmp_path/'audit_receipt.json';ap.write_text(json.dumps({'status':'PASS','arm':'FIX','capture_receipt_sha256':m.identity(rp)['sha256'],'all_raw_inputs_unchanged':True,'all_history_files_byte_exact':True}))
    proof={k:cap[k] for k in ('source_sha256','run_receipt_sha256','history_comparison_sha256','outputs')};proof.update(capture_receipt_sha256=m.identity(rp)['sha256'],audit_receipt_sha256=m.identity(ap)['sha256'])
    assert m.read_capture(tmp_path,'FIX',schema,proof)[0]==cap
    bad={**proof,'audit_receipt_sha256':'0'*64}
    with pytest.raises(ValueError,match='this audit'):m.read_capture(tmp_path,'FIX',schema,bad)
    data.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):m.read_capture(tmp_path,'FIX',schema,proof)


def test_points_are_bound_to_pre_capture_selection(tmp_path):
    import json
    schema=tmp_path/'schema.json';schema.write_text('{}')
    points=tmp_path/'points.csv';points.write_text('changed but twenty-one rows could still pass a count check')
    proof=tmp_path/'proof.json';proof.write_text(json.dumps({'status':'PASS','arms':dict.fromkeys(m.ARMS,{}),'schema_sha256':m.identity(schema)['sha256']}))
    with pytest.raises(ValueError,match='pre-capture selection'):m.run(tmp_path,points,schema,proof,tmp_path/'output')
    assert not (tmp_path/'output').exists()
