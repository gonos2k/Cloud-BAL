import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location('summary', Path(__file__).resolve().parents[1] / 'tools/cp02_protected_process_summary.py')
summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary)


def test_contiguous_ledger_preserves_opposing_internal_and_external_changes():
    # Internal +2 and external -1 per call must remain distinct; the endpoint
    # alone would hide much of the gross response.
    entry = np.arange(180, dtype=np.float64)[:, None, None]
    returned = entry + 2
    local, external, endpoint, residual = summary.ledger(entry, returned)
    assert local.item() == 360
    assert external.item() == -179
    assert endpoint.item() == 181
    assert residual.item() == 0


def test_ledger_rejects_shortened_or_misaligned_capture():
    with pytest.raises(ValueError, match='complete contiguous'):
        summary.ledger(np.zeros((179, 39, 150)), np.zeros((179, 39, 150)))
    with pytest.raises(ValueError, match='complete contiguous'):
        summary.ledger(np.zeros((180, 39, 150)), np.zeros((180, 38, 150)))


def test_summary_rejects_capture_with_missing_frozen_cohort_pin(tmp_path):
    import json
    receipt = {
        'status': 'FULL_CAPTURE_STREAMS_VALIDATED', 'arm': 'OLD', 'mode': 'full',
        'launch_receipt_sha256': 'a' * 64, 'actual_timesteps': list(range(1, 901)),
        'process_actual_timesteps': list(range(1, 361)) + list(range(721, 901)),
        'native_columns': 381, 'levels': 39, 'surface_rows': 900 * 381,
        'tool_sha256': summary.sha(summary.ROOT / 'tools/cp02_protected_process_capture.py'),
    }
    receipt.update({key: identity[1] for key, identity in summary.PINNED.items()})
    del receipt['cohort_receipt_sha256']
    (tmp_path / 'capture_receipt.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='cohort_receipt_sha256'):
        summary.read_capture(tmp_path, 'OLD', 'a' * 64)


def test_summary_rejects_same_size_wrong_point_coordinate_scope(tmp_path):
    path = tmp_path / 'channel.npz'
    np.savez(path, actual_timestep=np.arange(181, 361), point_ids=np.array(['RN1_WRONG'] * 150),
             point_values=np.zeros((180, 39, 150)))
    receipt = {'outputs': [{'channel': 'state_entry_QR', 'actual_start': 181, 'actual_end': 360,
                           'path': path.name, 'size_bytes': path.stat().st_size,
                           'sha256': summary.sha(path)}]}
    with pytest.raises(ValueError, match='point IDs differ'):
        summary.load_channel(tmp_path, receipt, 'state_entry_QR', 2)


def test_nominal_rate_product_is_computed_before_spatial_interpolation(tmp_path):
    # A covariance term would be lost by multiplying interpolated rate and dt.
    rate = np.ones((180, 39, 381), dtype=np.float32)
    duration = np.full_like(rate, 10)
    rate[..., 1], duration[..., 1] = 3, 30
    coordinates = {'actual_timestep': np.arange(181, 361),
                   'point_ids': np.array([f'RN1_{i}' for i in range(150)]),
                   'native_column_ids': np.arange(381),
                   'point_native_corner_indices': np.tile([0, 1, 0, 1], (150, 1)),
                   'point_corner_weights': np.full((150, 4), 0.25)}
    rows = []
    for name, values in [('phase05_praut', rate), ('phase06_dtcld', duration)]:
        path = tmp_path / (name + '.npz')
        np.savez_compressed(path, native_values=values, **coordinates)
        rows.append({'channel': name, 'actual_start': 181, 'actual_end': 360, 'path': path.name,
                     'sha256': summary.sha(path), 'size_bytes': path.stat().st_size})
    result = summary.nominal_rate_integral(tmp_path, {'outputs': rows}, 'praut', 2)
    assert result.shape == (39, 150)
    assert np.all(result == 180 * 50)
    assert not np.any(result == 180 * (2 * 20))
