from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('failure_plots', ROOT / 'tools/plot_cp02_failure_regimes.py')
plot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plot)


def test_transition_algebra_retains_four_change_classes():
    obs = np.array([1, 1, 1, 1, 0, 0, 0, 0.])
    base = np.array([1, 1, 0, 0, 1, 1, 0, 0.])
    candidate = np.array([1, 0, 1, 0, 1, 0, 1, 0.])
    row = plot.count_transitions(obs, base, candidate, .5)
    assert [row[k] for k in ('gained_hit', 'lost_hit', 'new_fa', 'removed_fa')] == [1, 1, 1, 1]
    assert (row['baseline_hit'], row['baseline_miss'], row['baseline_fa']) == (2, 2, 2)
    assert (row['comparison_hit'], row['comparison_miss'], row['comparison_fa']) == (2, 2, 2)
    assert row['baseline_CSI'] == row['comparison_CSI'] == 1 / 3


def test_real_weak_counts_and_all_108_score_transitions():
    hourly, _ = plot.read_hourly(plot.ANALYSIS)
    masks = plot.masks(hourly)
    assert [int(masks[key].sum()) for key in ('weak_gained', 'weak_lost', 'dry_new_fa', 'dry_removed_fa')] == [2, 6, 25, 17]
    rows = plot.build_counts(hourly)
    assert len(rows) == 108
    for r in rows:
        d = hourly[12 + r['lead_hour']]; obs = d['reference'] >= r['threshold_mm']; pred = d[r['comparison']] >= r['threshold_mm']
        assert (r['comparison_hit'], r['comparison_miss'], r['comparison_fa']) == (int(np.sum(obs & pred)), int(np.sum(obs & ~pred)), int(np.sum(~obs & pred)))


def test_invalid_source_does_not_change_existing_output(tmp_path):
    source = tmp_path / 'analysis'; shutil.copytree(plot.ANALYSIS, source)
    output = tmp_path / 'output'; output.mkdir(); sentinel = output / 'existing.png'; sentinel.write_bytes(b'keep')
    (source / 'hour_14_arrays.npz').write_bytes(b'altered')
    with pytest.raises(ValueError, match='differs from receipt'):
        plot.render(source, output)
    assert list(output.iterdir()) == [sentinel] and sentinel.read_bytes() == b'keep'


def test_population_summary_preserves_missing_and_full_range():
    empty = plot.summary([np.nan, np.nan])
    assert empty['n_valid'] == 0 and empty['median'] == '' and empty['maximum'] == ''
    item = plot.summary([1, 2, 3, 4, np.nan])
    assert item == {'n_valid': 4, 'minimum': 1., 'q25': 1.75, 'median': 2.5, 'q75': 3.25, 'maximum': 4.}


def test_posthoc_population_partition_and_start_times():
    hourly, _ = plot.read_hourly(plot.ANALYSIS)
    populations = plot.population_groups(hourly)
    assert [(g[0], g[1]) for g in populations] == [('weak_plus2', 1), ('fa_plus2', 1), ('weak_plus3', 2), ('fa_plus3', 2), ('heavy_plus5', 4)]
    for _, _, _, first, _, second in populations:
        assert not np.any(first & second)
    assert int(populations[0][5].sum()) == 6
    assert int(populations[1][3].sum()) == 25
    assert int(populations[1][5].sum()) == 17


def test_real_native_initial_contrast_and_corner_classification():
    hourly, _ = plot.read_hourly(plot.ANALYSIS)
    states, _ = plot.read_control_states(ROOT / 'docs/evidence/cp02_failure_regimes_20261104/state/results', hourly)
    for key in ('qrain_kgkg', 'rh_liquid', 'temperature_K'):
        np.testing.assert_array_equal(states['input'][key], states['DM_input'][key])
    initial = plot.corner_max_difference(states['input'], states['DM_input'], 'corner_qnrain_per_kg')
    masks = plot.focus_masks(hourly)
    assert [(int(np.sum(mask & (initial != 0))), int(np.sum(mask & (initial == 0)))) for _, _, _, mask in masks] == [(5, 1), (10, 15), (3, 2), (7, 2)]
    assert not states['input']['dm_valid'].any()
    assert np.isnan(states['input']['dm_mass_weighted_mm']).all()
