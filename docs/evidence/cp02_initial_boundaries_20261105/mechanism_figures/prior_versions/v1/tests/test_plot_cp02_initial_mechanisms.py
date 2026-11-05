from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/plot_cp02_initial_mechanisms.py'
SPEC = importlib.util.spec_from_file_location('plot_cp02_initial_mechanisms', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_pinned_writer_stages_show_nr_carry_to_first_entry():
    rows, _ = MODULE.load_writer()
    assert [row['dt'] for row in rows] == [pytest.approx(6.6666665), 10.0, 20.0]
    assert [row['nr_entry'] for row in rows] == [0.0, pytest.approx(0.0041964073), pytest.approx(0.0062302630)]
    assert [row['nr_return'] for row in rows] == [pytest.approx(0.0041964073), pytest.approx(0.0062302630), pytest.approx(0.0035873209)]


def test_pinned_phi_pair_retains_observed_deltas_and_identical_th():
    values, _ = MODULE.load_phi()
    assert values['th_B1'] == values['th_DM'] == 300.4675598144531
    assert values['p_DM'] - values['p_B1'] == -0.1328125
    assert values['pii_DM'] - values['pii_B1'] == pytest.approx(-4.172325134277344e-7)
    assert values['tk_DM'] - values['tk_B1'] == -0.0001220703125


def test_sourcepins_are_hash_verified():
    pins = MODULE.verify_sourcepins()
    assert 'module_em.f90' in pins
    assert MODULE.sha(pins['module_em.f90']) == 'e00d4b4131e179c2e59aa2cf282965bed1aef5c449202405e93b2e43e8e9e804'
