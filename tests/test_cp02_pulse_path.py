import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import cp02_pulse_path as pulse


def test_five_minute_windows_use_fifteen_calls_and_require_no_gap():
    result=pulse.windows(np.arange(20,dtype=float)**2,np.arange(20))
    assert result[0]==(0,15,225.)
    assert result[-1]==(4,19,345.)
    with pytest.raises(ValueError,match='contiguous'):pulse.windows(np.arange(20),np.r_[np.arange(10),np.arange(11,21)])


def test_stage_differences_require_each_positive_weight_corner():
    contract={'core_delta_fields':['q(i,k)']}
    a={'core_delta':np.array([[[[1.]],[[2.]],[[3.]],[[4.]]]]),'core_valid':np.ones((1,4,1),bool)}
    b={'core_delta':np.zeros((1,4,1,1)),'core_valid':np.ones((1,4,1),bool)}
    indices=np.array([[0,1,2,3]]); weights=np.array([[.1,.2,.3,.4]])
    av,bv,diff=pulse.stage_series(a,b,'core','q(i,k)',contract,indices,weights)
    assert np.isclose(diff[0,0,0],3) and np.isclose(av[0,0,0],3) and bv[0,0,0]==0
    b['core_valid'][0,2,0]=False
    av,bv,diff=pulse.stage_series(a,b,'core','q(i,k)',contract,indices,weights)
    assert np.isnan(diff[0,0,0]) and np.isnan(av[0,0,0])
    assert pulse.stage_series(a,b,'core','absent',contract,indices,weights)==(None,None,None)


def test_window_entry_last_and_change_are_distinct_and_close():
    points=[{'flat_index_yx':'19145'}]
    entry=np.broadcast_to(np.arange(180)[:,None,None]*2.,(180,1,39)).copy()
    returned=entry+1
    stages={name:(None,None,None) for name in pulse.STAGES}
    selected={(5,'ICE_FIXED-CONSERVATIVE',19145):[{'kind':'contrast_max','start_boundary':845,'end_boundary':860}]}
    r=next(pulse.window_rows(5,'ICE_FIXED','CONSERVATIVE',points,'QR','kg kg-1',entry,returned,stages,selected))
    assert r['initial_entry_difference']==250 and r['last_return_difference']==279
    assert r['window_difference_change']==29 and r['local_difference_change_sum']==15
    assert r['between_call_difference_change_sum']==14 and r['closure_residual']==0
    assert r['core_difference_sum']==''


def test_output_symlink_is_never_overwritten(tmp_path):
    output=tmp_path/'out'; output.symlink_to(tmp_path/'missing')
    with pytest.raises(FileExistsError): pulse.run(tmp_path,tmp_path/'p',tmp_path/'s',tmp_path/'proof',output)


def test_surface_point_order_and_earliest_tie():
    points=[{'flat_index_yx':str(p)} for p in pulse.POINTS]
    trace=np.zeros((1081,3))
    for p in range(3): trace[721:,p]=np.arange(360)*(p+1)
    traces={'step':np.arange(1081),'ICE_FIXED_rain_cumulative_mm':trace,
            'CONSERVATIVE_rain_cumulative_mm':trace*.5,'FIX_rain_cumulative_mm':trace*0}
    rows,_=pulse.choose_windows(traces,points)
    chosen=[r for r in rows if r['hour']==5 and r['contrast']=='ICE_FIXED-CONSERVATIVE' and r['kind']=='upper_max']
    assert [r['point'] for r in chosen]==list(pulse.POINTS)
    assert [r['upper_counter_change_mm'] for r in chosen]==[15,30,45]
    assert all(r['start_boundary']==721 and r['end_boundary']==736 for r in chosen)


def test_wrapper_difference_is_taken_after_float64_promotion():
    contract={'entry_return_fields':['QR']}
    for name in pulse.STAGES: contract[name+'_delta_fields']=[]
    shape=(1,4,1,1)
    a={'entry':np.ones(shape,np.float32),'returned':np.ones(shape,np.float32)}
    b={'entry':np.full(shape,1e-10,np.float32),'returned':np.full(shape,1e-10,np.float32)}
    entry,returned,_=pulse.field_arrays(a,b,'QR','qrs(i,k,1)',contract,np.array([[0,1,2,3]]),np.array([[.1,.2,.3,.4]]))
    assert entry[0,0,0]<1 and entry[0,0,0]==returned[0,0,0]
