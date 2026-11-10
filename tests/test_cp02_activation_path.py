import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import cp02_activation_path as path


def test_last_substep_requires_complete_actual_sequence():
    key = lambda n:(982,154,89,1,10,n)
    records = {key(1):(2,2,{'x':1}),key(2):(2,2,{'x':2})}
    assert path.boundary(records,982,154,89,1,10,True)['x'] == 2
    del records[key(1)]
    with pytest.raises(ValueError, match='substeps'):
        path.boundary(records,982,154,89,1,10,True)
    assert path.boundary(records,982,154,89,1,11) is None


def test_source_order_rounds_and_separates_replay_from_exposure():
    rate = {f'{term}(i,k)':np.float32(0) for term in set(path.TERMS)}
    rate['pracw(i,k)'] = np.float32(1/3)
    before = {'dtcld':np.float32(3),'qrs(i,k,1)':np.float32(1)}
    after = {'qrs(i,k,1)':np.float32(2)}
    exposure, observed, residual = path.main_qr(before,after,rate)
    assert observed == 1 and residual == 0
    assert exposure['pracw'] != 1
    assert path.main_qr(None,after,rate) == ({},None,None)


def test_sum_loops_before_pairing_and_preserve_missing():
    rows = []
    for i,weight in ((1,.5),(2,.5)):
        for arm,values in (('CONTROL',[1e30]),('MP10',[1e30] if i==1 else [2,3])):
            if i==2 and arm=='CONTROL': values=[4]
            for n,v in enumerate(values,1):
                rows.append(dict(point=1,step=1,i=i,j=1,k=16,weight=weight,arm=arm,loop=n,loops=len(values),activation_nn=v))
    assert path.aggregate(rows)[0]['activation_nn'] == .5
    rows[-1]['activation_nn']=None
    assert path.aggregate(rows)[0]['activation_nn'] is None


def test_zero_weight_missing_does_not_contaminate():
    rows = [dict(point=1,step=1,i=i,j=1,k=16,weight=w,arm=arm,loop=1,loops=1,activation_nn=v)
            for i,w in ((1,1.),(2,0.)) for arm,v in (('CONTROL',1),('MP10',2 if i==1 else None))]
    assert path.aggregate(rows)[0]['activation_nn'] == 1


def test_warm_bound_includes_ice_and_rounds_outward():
    margin = path.warm_lower_bound(274.,273.15,1000.,.001,.001,.0001)
    assert margin > 0
    assert margin < 274. - float(np.float32(273.15)) - .735
    assert path.warm_lower_bound(274.,273.15,1000.,.001,.001,.001) < 0
    assert path.warm_lower_bound(274.,273.15,0.,0.,0.,0.) is None
    assert path.warm_lower_bound(274.,273.15,1000.,0.,0.,-1) is None


def test_input_mutation_is_rejected(tmp_path):
    source = tmp_path/'input'
    source.write_text('before')
    identity = path.prior.identity(source)
    path.verify_inputs([identity])
    source.write_text('after')
    with pytest.raises(ValueError,match='input changed'):
        path.verify_inputs([identity])


def test_atomic_publish_preserves_existing_and_dangling_destinations(tmp_path):
    stage = tmp_path/'stage'
    stage.mkdir()
    (stage/'payload').write_text('new')
    destination = tmp_path/'destination'
    destination.symlink_to(tmp_path/'missing')
    with pytest.raises(FileExistsError):
        path.evaluation.publish_new(stage,destination)
    assert destination.is_symlink() and (stage/'payload').read_text() == 'new'
    destination.unlink()
    path.evaluation.publish_new(stage,destination)
    assert (destination/'payload').read_text() == 'new'
    with pytest.raises(FileExistsError):
        path.run(destination)
