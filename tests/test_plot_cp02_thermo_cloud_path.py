from __future__ import annotations

import importlib.util
from pathlib import Path
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cp04_plot',ROOT/'tools/plot_cp02_thermo_cloud_path.py');plot=importlib.util.module_from_spec(spec);spec.loader.exec_module(plot)


def test_point_surface_anchor_and_first_sample_semantics():
    points=plot.read_csv(plot.BUNDLE/'cohorts/results/selected_points.csv');ids={int(r['flat_index_yx']):r['point_id'] for r in points}
    assert [ids[i] for i in (17051,16454,20183,20330)]==['NFA05','RFA08','NFA12','RFA11']
    surface=plot.read_csv(plot.BUNDLE/'science/surface_reference/point_components.csv');by={(r['point_id'],r['arm'],int(r['lead_hour'])):r for r in surface}
    assert .0028<float(by['NFA12','B1',1]['RAINC_hour_mm'])<.0031
    assert all(float(by[pid,arm,2]['RAINC_hour_mm'])==0 for pid in [r['point_id'] for r in points] for arm in ('B1','DM065'))
    rows=plot.read_csv(plot.ANALYSIS/'rain_presence_recount.csv');q={(r['point_id'],r['stage'],r['field'],r['arm_or_difference']):r for r in rows}
    assert int(q['NFA12','wrapper_entry','QR','B1']['first_sample_step'])==23
    assert int(q['NFA12','wrapper_return','QR','B1']['first_sample_step'])==276
    assert int(q['NFA05','wrapper_return','QR','B1']['first_sample_step'])==234
    assert int(q['NFA05','wrapper_return','QR','DM065']['first_sample_step'])==287


def test_amplitude_and_no_zero_substitution():
    data=np.array([[[np.nan,2]],[[np.nan,-3]]],dtype=float)
    assert np.isnan(plot.amplitude(data,0)) and plot.amplitude(data,1)==3


def test_pinned_input_failure_and_existing_output_preserved(tmp_path,monkeypatch):
    target=tmp_path/'existing';target.mkdir();sentinel=target/'keep';sentinel.write_bytes(b'unchanged')
    with pytest.raises(FileExistsError):plot.render(target)
    assert sentinel.read_bytes()==b'unchanged'
    monkeypatch.setitem(plot.PINS,'capture','0'*64)
    fresh=tmp_path/'fresh'
    with pytest.raises(ValueError,match='pinned input mismatch'):plot.render(fresh)
    assert not fresh.exists()
    monkeypatch.setitem(plot.PINS,'capture',plot.sha(plot.ANALYSIS/'full_capture_receipt.json'))
    monkeypatch.setitem(plot.PINS,'schema','0'*64)
    with pytest.raises(ValueError,match='pinned input mismatch: schema'):plot.render(fresh)
    assert not fresh.exists()


def test_group_delta_labels_and_units():
    assert plot.GROUPS==('new_fa_initial_nr_unchanged','removed_fa_initial_nr_unchanged','weak_lost','weak_retained_nearest_control')
    assert plot.PAIRED_KEYS.count('within_call_difference')==1 and plot.PAIRED_KEYS.count('between_call_difference')==1


def test_geographic_comparators_are_nearest_removed():
    points=plot.read_csv(plot.BUNDLE/'cohorts/results/selected_points.csv')
    plot.verify_anchor_controls(points)
    for r in points:
        if r['point_id']=='RFA08': r['latitude']='0'
    with pytest.raises(ValueError,match='geographic comparator'):
        plot.verify_anchor_controls(points)


def test_receipt_write_failure_rolls_back_fresh_output(tmp_path,monkeypatch):
    data=tmp_path/'input';data.write_bytes(b'input')
    monkeypatch.setattr(plot,'load_verified',lambda:([{}],[],{}, {'fixture':data}))
    monkeypatch.setattr(plot,'configure_font',lambda:None)
    def draw(*args): args[-1].write_bytes(b'image')
    for name in ('draw_source_order','draw_surface','draw_anchor','draw_thermo','draw_first_rain'):monkeypatch.setattr(plot,name,draw)
    def groups(points,arrays,path):
        path.write_bytes(b'image');return [{'point_id':'one','max_abs':0}]
    monkeypatch.setattr(plot,'draw_groups',groups)
    original=Path.write_text
    def fail(path,*args,**kwargs):
        if path.name=='receipt.json':raise OSError('injected receipt failure')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'write_text',fail)
    target=tmp_path/'fresh'
    with pytest.raises(OSError,match='injected receipt failure'):plot.render(target)
    assert not target.exists() and not list(tmp_path.glob('.cp04-figures-*'))
