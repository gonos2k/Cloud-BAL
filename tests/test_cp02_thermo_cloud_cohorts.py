from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('thermo_cohort',ROOT/'tools/cp02_thermo_cloud_cohorts.py');cohort=importlib.util.module_from_spec(spec);spec.loader.exec_module(cohort)


def test_real_selection_classes_initial_native_and_stencils():
    values,mapping,b1,dm=cohort.inputs();groups,jj,ii,weights=cohort.select(values,mapping,b1,dm)
    assert len(groups)==39 and len({g[2] for g in groups})==39
    assert [sum(g[1]==name for g in groups) for name in ('new_fa_initial_nr_unchanged','removed_fa_initial_nr_unchanged','weak_lost','weak_retained_nearest_control')]==[15,12,6,6]
    initial_equal=np.all((b1['corner_qnrain_per_kg']==dm['corner_qnrain_per_kg']) | (weights[:,None,:]==0),axis=(1,2))
    assert all(initial_equal[g[2]] for g in groups[:27])
    assert {17051,20183}.issubset({int(values['flat_index_yx'][g[2]]) for g in groups[:15]})
    assert np.allclose(weights.sum(axis=1),1,rtol=0,atol=1e-12)
    assert len({(int(jj[g[2],c]),int(ii[g[2],c])) for g in groups for c in range(4)})==123


def test_nearest_controls_greedy_no_reuse_and_flat_tie():
    values={'flat_index_yx':np.array([100,200,9,3,10]),'latitude':np.zeros(5),'longitude':np.array([0.,10.,1.,-1.,11.])}
    lost=np.array([True,True,False,False,False]);retained=np.array([False,False,True,True,True]);pairs=cohort.choose_controls(values,lost,retained)
    assert [(a,b) for a,b,_ in pairs]==[(0,3),(1,4)]
    assert all(distance>0 for _,_,distance in pairs)
    with pytest.raises(ValueError,match='not enough'):
        cohort.choose_controls(values,lost,np.array([False,False,False,True,False]))


def test_outputs_replay_and_existing_target_preserved(tmp_path):
    output=tmp_path/'results';receipt=cohort.run(output)
    canonical=cohort.COHORTS/'results'
    for name in ('selected_points.csv','point_corners.csv','unique_global_corners.csv'):
        assert (output/name).read_bytes()==(canonical/name).read_bytes()
    assert receipt['point_corner_rows']==156 and receipt['unique_global_cells']==123
    with pytest.raises(FileExistsError):cohort.run(output)
    assert len(list(csv.DictReader((output/'selected_points.csv').open())))==39
