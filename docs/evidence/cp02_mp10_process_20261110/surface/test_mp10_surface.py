import csv
import importlib.util
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('mp10_surface_extract', HERE / 'extract.py')
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)


def test_frozen_mapping_projection_and_invalid_anchor():
    with (HERE.parent / 'cohorts/selected_points.csv').open() as stream:
        points = list(csv.DictReader(stream))
    with np.load(extract.RESULTS / 'bilinear_mapping.npz', allow_pickle=False) as data:
        mapping = {key: data[key].copy() for key in data.files}
    ids, j, i, u, v = extract.geometry(points, mapping)
    assert len(ids) == 30
    y, x = np.unravel_index(ids, mapping['valid'].shape)
    assert np.array_equal(j, mapping['j0'][y, x] + 5)
    assert np.array_equal(i, mapping['i0'][y, x] + 74)
    assert np.all((u >= 0) & (u <= 1) & (v >= 0) & (v <= 1))
    points[0]['native_i0_fortran_one_based'] = '1'
    with pytest.raises(ValueError, match='geometry'):
        extract.geometry(points, mapping)


def test_component_replay_and_reset_guard():
    corners = np.zeros((1, 7, 2, 4), dtype=np.float32)
    corners[:, :, 0, :] = np.arange(7)[None, :, None]
    corners[:, :, 1, :] = 2 * np.arange(7)[None, :, None]
    components, total = extract.surface.replay(corners, np.array([.25]), np.array([.75]), 1e-6)
    assert np.all(components[:, :, 0] == 1)
    assert np.all(components[:, :, 1] == 2)
    assert np.all(total == 3)
    corners[0, 4, 1, 0] = -1
    with pytest.raises(ValueError, match='invalid cumulative'):
        extract.surface.replay(corners, np.array([.25]), np.array([.75]), 1e-6)
