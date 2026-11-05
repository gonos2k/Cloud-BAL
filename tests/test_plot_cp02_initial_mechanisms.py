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
    numerator, paths = MODULE.load_numerator(values)
    assert values['th_B1'] == values['th_DM'] == 300.4675598144531
    assert values['p_DM'] - values['p_B1'] == -0.1328125
    assert values['pii_DM'] - values['pii_B1'] == pytest.approx(-4.172325134277344e-7)
    assert values['tk_DM'] - values['tk_B1'] == -0.0001220703125
    assert numerator['numerator_B1'] == 1024.7392578125
    assert numerator['numerator_DM065'] == 1024.740234375
    assert numerator['delta_numerator'] == 0.0009765625
    assert numerator['al_B1'] == pytest.approx(0.04034990072250366)
    assert numerator['al_DM065'] == pytest.approx(0.04035085439682007)
    assert MODULE.sha(paths['closure']) == MODULE.NUMERATOR_PINS['closure']


def test_sourcepins_are_hash_verified():
    pins = MODULE.verify_sourcepins()
    assert 'module_em.f90' in pins
    assert MODULE.sha(pins['module_em.f90']) == 'e00d4b4131e179c2e59aa2cf282965bed1aef5c449202405e93b2e43e8e9e804'
    receipt = MODULE.read_json(MODULE.OUT / 'receipt.json')
    assert receipt['status'] == 'PASS'
    assert receipt['renderer_sha256'] == MODULE.sha(SCRIPT)
    assert receipt['font_sha256'] == MODULE.sha(MODULE.FONT)
    assert receipt['outputs_sha256']['offline_gallery.zip'] == MODULE.sha(MODULE.OUT / 'offline_gallery.zip')
    assert receipt['inputs_sha256']['closure'] == MODULE.NUMERATOR_PINS['closure']


def test_build_rejects_corrupt_pinned_analysis_before_output(tmp_path, monkeypatch):
    copied_science = tmp_path / 'science'
    copied_writer = copied_science / 'writer_nr20330' / 'analysis.json'
    copied_writer.parent.mkdir(parents=True)
    copied_writer.write_bytes((MODULE.SCIENCE / 'writer_nr20330/analysis.json').read_bytes() + b' ')
    monkeypatch.setattr(MODULE, 'SCIENCE', copied_science)
    output = tmp_path / 'render'
    with pytest.raises(ValueError, match='pinned input mismatch: writer analysis'):
        MODULE.build(output)
    assert not output.exists()
