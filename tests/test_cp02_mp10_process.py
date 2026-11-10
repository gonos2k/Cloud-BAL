import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import cp02_mp10_process as process


def states(loops=2):
    shape=(1,1,2,loops,len(process.FIELDS))
    value=np.zeros(shape,np.float32)
    return {phase:value.copy() for phase in (30,32,33,34)}


def test_carry_compares_native_bits_including_signed_zero():
    values=states()
    process.loop_metrics(values)
    values[34][0,0,0,0,3]=np.float32(-0.)
    assert values[34][0,0,0,0,3] == values[30][0,0,0,1,3]
    with pytest.raises(ValueError,match='carry'):process.loop_metrics(values)


def test_psd_block_cannot_silently_change_water_or_temperature():
    values=states(1)
    values[34][0,0,0,0,0]=np.float32(1e-6)
    with pytest.raises(ValueError,match='mass/temperature'):process.loop_metrics(values)


def test_source_carrier_mass_and_number_area_use_different_density_factors():
    before=np.zeros((1,1,2,2,18),np.float32)
    before[...,2]=280;before[...,3]=2;before[...,4]=100;before[...,6]=2e-9
    zero=before.copy();zero[...,6]=0
    end=zero.copy();end[...,11]=3
    removed,number=process.cleanup_columns({32:before,33:zero,34:end})
    assert np.isclose(removed[0,0],4*float(before[0,0,0,0,6])*2*100)
    assert number[0,0,0] == 4*3*100
    before[...,3]=4;zero[...,3]=4;end[...,3]=4
    doubled,same_number=process.cleanup_columns({32:before,33:zero,34:end})
    assert np.array_equal(doubled,removed*2)
    assert np.array_equal(same_number,number)


def test_paired_native_subtraction_precedes_weighting():
    a=np.array([[[1e30],[1],[0],[0]]],np.float32)
    b=np.array([[[1e30],[0],[0],[0]]],np.float32)
    ix=np.array([[0,1,2,3]]);weights=np.array([[.5,.5,0.,0.]])
    assert process.paired(a,b,ix,weights)[0,0,0] == .5
    assert (process.weighted(a.astype(float),ix,weights)-process.weighted(b.astype(float),ix,weights))[0,0,0] == 0
    a[0,1,0]=np.nan
    assert np.isnan(process.paired(a,b,ix,weights)[0,0,0])


def test_public_ledger_separates_local_between_and_endpoint_change():
    entry=np.array([0.,3.,4.])[:,None]
    returned=np.array([1.,2.,7.])[:,None]
    local,between,change,residual=process.ledger(entry,returned)
    assert (local[0],between[0],change[0],residual[0]) == (3,4,7,0)
    assert returned[-1,0] != change[0]+2


def test_dense_records_require_full_unique_native_positions():
    keys=np.array([[1,0,4,1,1,k,l,2,0,0,30,18] for k in range(1,40) for l in (1,2)],np.int32)
    bits=np.zeros((len(keys),18),np.uint32)
    result=process.dense_phase((keys,bits),30,(1,),((1,1),),2,tuple(range(18)))
    assert result.shape == (1,1,39,2,18)
    keys[1]=keys[0]
    with pytest.raises(ValueError,match='duplicate'):process.dense_phase((keys,bits),30,(1,),((1,1),),2,tuple(range(18)))


def test_actual_sediment_substeps_are_paired_then_summed_with_missing_preserved():
    keys=np.array([[1,0,4,1,1,1,1,1,n,2,phase,1] for phase in (9,10) for n in (1,2)],np.int32)
    bits=np.array([[1.],[2.],[2.],[3.]],np.float32).view(np.uint32)
    schema={'phases':{'9':{'fields':['q(i,k)']},'10':{'fields':['q(i,k)']}},
            'arm_overrides':{'CONTROL and MP10':{'phase_10_fields':['q(i,k)']}}}
    actual=process.source_stage((keys,bits),9,10,(1,),((1,1),),1,schema)
    assert actual[0,0,0,0,0] == 2
    assert np.isnan(actual[0,0,0,0,3]) and np.isnan(actual[0,0,1,0,0])
    with pytest.raises(ValueError,match='keys differ'):process.source_stage((keys[:-1],bits[:-1]),9,10,(1,),((1,1),),1,schema)


def test_dtype_and_destination_guards_reject_incomplete_inputs(tmp_path):
    keys=np.array([[1,0,4,1,1,1,1,1,1,1,18,1]],np.int32)
    np.savez_compressed(tmp_path/'faces_000001_000.npz',keys=keys,bits=np.zeros((1,1),np.uint32))
    with pytest.raises(ValueError,match='bit payload'):process.load_group(tmp_path,['faces_000001_000.npz'],'faces',1)
    out=tmp_path/'out';out.symlink_to(tmp_path/'absent')
    with pytest.raises(FileExistsError):process.run(tmp_path,tmp_path/'p',tmp_path/'s',tmp_path/'proof',out)
    proof=tmp_path/'proof';proof.write_text(json.dumps({'status':'FAIL'}))
    with pytest.raises(ValueError,match='incomplete receipt'):process.run(tmp_path,tmp_path/'p',tmp_path/'s',proof,tmp_path/'new')
    assert not (tmp_path/'new').exists()


def test_core_arithmetic_rounds_each_source_operation_not_just_final_result():
    keys=[];values=[]
    q=np.float32(1);work=np.float32(-1/3);dt=np.float32(3)
    q_after=np.add(q,np.multiply(work,dt,dtype=np.float32),dtype=np.float32)
    assert q_after==0 and np.float32(float(q)+float(work)*float(dt))!=q_after
    for phase in (6,7,8):
        for k in range(1,40):
            row=np.zeros(6,np.float32)
            if phase in (6,8):row[1]=q if phase==6 else q_after;row[2]=10
            else:row[:6]=[work,0,1004,dt,2.5e6,3.3e5]
            keys.append([1,0,4,1,1,k,1,1,0,0,phase,6]);values.append(row)
    keys=np.array(keys,np.int32);bits=np.array(values,np.float32).view(np.uint32)
    assert process.validate_core_arithmetic((keys,bits),(1,),((1,1),),1)==39
    bits[keys[:,10]==8,1]=np.float32(1e-8).view(np.uint32)
    with pytest.raises(ValueError,match='vapor update'):process.validate_core_arithmetic((keys,bits),(1,),((1,1),),1)
