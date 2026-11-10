from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import cp02_weak_activation as weak


def test_activation_observes_state_and_rejects_changed_constants_or_inactive_updates():
    pre=np.zeros((2,12),np.float32);pre[:,0]=[1,0];pre[:,6:]=1
    post=pre.copy();post[0,1]=3;post[0,2]=-3
    delta=weak.activation_changes(pre,post)
    assert tuple(delta[0,:2]) == (3,-3)
    bad=post.copy();bad[0,9]=2
    with pytest.raises(ValueError,match='constants'):weak.activation_changes(pre,bad)
    bad=post.copy();bad[1,3]=1
    with pytest.raises(ValueError,match='inactive'):weak.activation_changes(pre,bad)


def test_reservoir_lower_restoration_and_upper_removal_are_separate():
    pre=np.array([0,1e8,2e8,3e10],np.float32)
    post=np.minimum(np.maximum(pre,np.float32(1e8)),np.float32(2e10))
    lower,upper=weak.reservoir_limits(pre,post)
    assert np.array_equal(lower,[1e8,0,0,0])
    assert upper[-1] == float(pre[-1])-float(post[-1]) and np.count_nonzero(upper)==1
    post[0]=0
    with pytest.raises(ValueError,match='NN limit'):weak.reservoir_limits(pre,post)


def test_surface_end_uses_last_actual_inner_loop_and_rejects_missing_or_duplicate():
    keys=np.array([[step,0,1,2,1,1,loop,2,0,0,43,2]
                   for step in (361,362,363) for loop in (1,2)],np.int32)
    values=np.column_stack((np.arange(6,dtype=np.float32),np.zeros(6,np.float32))).view(np.uint32)
    result=weak.surface_end((keys,values),(361,362,363),[(1,2)],2,['rain','rainncv'])
    assert np.array_equal(result[:,0],[1,3,5])
    with pytest.raises(ValueError,match='coverage'):weak.surface_end((keys[:-1],values[:-1]),(361,362,363),[(1,2)],2,['rain','rainncv'])
    keys[-1]=keys[-2]
    with pytest.raises(ValueError,match='duplicate'):weak.surface_end((keys,values),(361,362,363),[(1,2)],2,['rain','rainncv'])


def test_pairing_sums_loops_before_native_differencing_and_weighting():
    control=np.array([[[[2.,1.]],[[4.,0.]],[[0.,0.]],[[0.,0.]]]],np.float32)
    candidate=np.repeat(control/2,2,axis=2)
    candidate[0,0,1,0]+=1
    ix=np.array([[0,1,2,3]]);w=np.array([[.5,.5,0,0]])
    paired=weak.prior.paired(candidate.sum(axis=2),control.sum(axis=2),ix,w)
    assert np.array_equal(paired,[[[.5,0]]])


def test_existing_or_dangling_output_is_never_overwritten(tmp_path):
    out=tmp_path/'out';out.symlink_to(tmp_path/'missing')
    with pytest.raises(FileExistsError):weak.run(out)
    assert out.is_symlink()
