from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'tools/plot_cp02_initial_boundaries.py'
spec=importlib.util.spec_from_file_location('boundary_plot',SCRIPT);p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


def test_called_mask_and_first_entry_cross_counts():
    receipt,domain,_,_=p.load();called=domain['called'];initial=domain['initial_NR_changed'];entry=domain['entry_NR_changed']
    assert int((initial&called).sum())==199111
    assert int((initial&~called).sum())==1071
    assert int((entry&called&~initial).sum())==154317
    assert int((called&initial&~entry).sum())==11
    assert receipt['summary']['called_cells']==2533440


def test_native_frontier_uses_all_four_corners_and_39_levels():
    _,_,selected,_=p.load();counts=p.frontier_counts(selected);anchor=counts['NFA12']
    assert anchor.shape==(16,4)
    assert anchor[p.FIELDS.index('TH'),1]==0
    assert anchor[p.FIELDS.index('P'),1]==2
    assert anchor[p.FIELDS.index('PII'),1]==2
    assert anchor[p.FIELDS.index('TK'),1]==2
    assert all(np.max(c)<=156 for c in counts.values())


def test_bad_pin_and_existing_output_fail_without_touching(tmp_path,monkeypatch):
    monkeypatch.setitem(p.PINS,'plan','0'*64)
    with pytest.raises(ValueError,match='pinned input mismatch: plan'):p.load()
    target=tmp_path/'existing';target.mkdir();sentinel=target/'keep';sentinel.write_bytes(b'keep')
    result=subprocess.run([sys.executable,str(SCRIPT),'--output',str(target)],capture_output=True)
    assert result.returncode!=0 and sentinel.read_bytes()==b'keep'
