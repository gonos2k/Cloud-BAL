"""Sparse cloud traces must reproduce source arithmetic and reject gaps."""
import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from pr87_cloud_diffusion_replay import replay
from pr87_rain_diffusion_replay import _VALUE_NAMES

VALUES = runpy.run_path(str(ROOT / 'tests/test_pr87_rain_diffusion_replay.py'))['VALUES']


def record(phase, moist, tendency):
    values = dict(VALUES, tendency=tendency)
    numbers = ' '.join(f'{values[name]:.17E}' for name in _VALUE_NAMES)
    return f'PR87_CLOUD_DIFFUSION_{phase} 1 {2 if moist else 3} 90 14 11 {"T" if moist else "F"} F {numbers}'


def test_dyadic_source_replay_and_two_separate_call_ordinals(tmp_path):
    lines = [record(phase, moist, value) for moist in (True, False)
             for phase, value in [('PRE', 1.0), ('POST', 2.0)]]
    path = tmp_path / 'stdout'
    path.write_text('\n'.join(lines + lines) + '\n')
    result = replay(path)
    assert len(result['calls']) == 2
    assert result['all_post_r32_bits_match']
    for call in result['calls']:
        for moment in call['moments'].values():
            assert moment['replayed_post_r64'] == 2.0
            assert moment['correction_rate_r64'] == 0.0
    path.write_text('\n'.join(lines[:-1]))
    with pytest.raises(ValueError, match='incomplete'):
        replay(path)


def test_changed_stencil_operand_is_not_a_valid_call_pair(tmp_path):
    lines = [record('PRE', True, 1.0), record('POST', True, 2.0)]
    tokens = lines[1].split()
    tokens[8 + _VALUE_NAMES.index('mut_center')] = '2.0'
    lines[1] = ' '.join(tokens)
    path = tmp_path / 'stdout'
    path.write_text('\n'.join(lines))
    with pytest.raises(ValueError, match='operand changed'):
        replay(path)


def test_graupel_uses_specific_bulk_volume_contract(tmp_path):
    lines = []
    # Same numeric registry can mean another species in the other mode.
    # Include those overlapping records and require the replay to exclude them.
    for moist, registry in ((True, 7), (False, 5), (True, 5), (False, 7)):
        for phase, tendency in [('PRE', 1.0), ('POST', 2.0)]:
            values = dict(VALUES, tendency=tendency)
            if moist:
                for name in list(values):
                    if name.startswith('field_') or name == 'tendency':
                        values[name] *= 400.0
            numbers = ' '.join(f'{values[name]:.17E}' for name in _VALUE_NAMES)
            lines.append(f'PR87_G_DIFFUSION_{phase} 1 {registry} 8 205 16 {"T" if moist else "F"} F {numbers}')
    path = tmp_path / 'stdout'
    path.write_text('\n'.join(lines) + '\n')
    result = replay(path, graupel=True)
    assert result['species'] == ['QG', 'BG']
    assert result['moment_kind'] == 'specific_bulk_volume'
    assert result['source_mass_bounds'] == [100.0, 900.0]
    assert result['excluded_registry_records'] == [
        {'moist_mode': False, 'registry_index': 7,
         'reason': 'registry does not identify QG/BG in this mode', 'record_count': 2},
        {'moist_mode': True, 'registry_index': 5,
         'reason': 'registry does not identify QG/BG in this mode', 'record_count': 2},
    ]
    assert result['all_post_r32_bits_match']
    assert result['calls'][0]['ratios']['replayed_post_r64']['q_over_moment'] == 400.0
    assert result['calls'][0]['moments']['QG']['registry_index'] == 7
    assert result['calls'][0]['moments']['BG']['registry_index'] == 5
