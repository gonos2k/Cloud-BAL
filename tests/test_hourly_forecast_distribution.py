import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCORES = ROOT / 'docs/evidence/current_forecast_paper_20261029/scores'
spec = importlib.util.spec_from_file_location('hourly_distribution', ROOT / 'tools/plot_hourly_forecast_distribution.py')
plot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plot)


def test_archived_inputs_have_matching_grid():
    _, hashes, points = plot.load_inputs(SCORES)
    assert hashes == plot.EXPECTED
    assert len(points) == 6
    assert points[13]['latitude'].shape == (3688,)


def test_missing_and_mutated_hour_rejected(tmp_path):
    for hour in plot.HOURS:
        shutil.copy(SCORES / f'hour_{hour:02d}_arrays.npz', tmp_path)
    target = tmp_path / 'hour_15_arrays.npz'
    target.unlink()
    with pytest.raises(FileNotFoundError):
        plot.load_inputs(tmp_path)
    target.write_bytes(b'mutated')
    with pytest.raises(ValueError, match='SHA-256'):
        plot.load_inputs(tmp_path)


def test_invalid_coordinates_rejected(tmp_path):
    with np.load(SCORES / 'hour_13_arrays.npz') as data:
        fields = {name: data[name] for name in data.files}
    fields['latitude'][0] = 91
    path = tmp_path / 'bad.npz'
    np.savez(path, **fields)
    with pytest.raises(ValueError, match='invalid latitude'):
        plot.read_points(path)


def test_full_render_and_existing_destination(tmp_path):
    output = tmp_path / 'figures'
    plot.render(SCORES, output)
    manifest = json.loads((output / 'figure_manifest.json').read_text())
    assert len(manifest['outputs']) == 13
    assert len(manifest['inputs']) == 6
    assert all(item['sha256_before'] == item['sha256_after'] for item in manifest['inputs'])
    assert all(plot.sha256(output / item['path']) == item['sha256'] for item in manifest['outputs'])
    with pytest.raises(FileExistsError):
        plot.render(SCORES, output)
