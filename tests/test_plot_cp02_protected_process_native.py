import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'plot_cp02_protected_process_native', ROOT / 'tools/plot_cp02_protected_process_native.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def synthetic_selected_rows():
    rows = []
    for point_id, point in p.POINT_SPECS.items():
        for field in ('QR', 'QV', 'TK'):
            for level in p.K_LEVELS:
                row = {
                    'point_id': point_id, 'lead_hour': str(point['lead_hour']),
                    'native_k_1based': str(level), 'field': field,
                    'units': p.EXPECTED_UNITS[field],
                    'delta_call_internal_sum': '1.0', 'delta_between_call_sum': '0.2',
                    'delta_endpoint_change': '1.2', 'ledger_residual': '0',
                    'delta_phase8_minus_phase6_sum': '0.4',
                    'delta_rain_sedimentation_sum': '0.2' if field == 'QR' else '',
                    'paired_sedimentation_calls': '180' if field == 'QR' else '',
                    'delta_condensation_substep_sum': '0.2' if field != 'QR' else '',
                    'remaining_call_internal_sum': '0.4',
                }
                rows.append(row)
    return rows


def test_renders_synthetic_six_panel_figure_in_test_directory(tmp_path):
    profiles = p.prepare_profiles(synthetic_selected_rows())
    path = tmp_path / 'synthetic-native-process.png'
    p.make_figure(profiles, path)
    assert path.is_file()
    assert path.stat().st_size > 10_000


def test_incomplete_conditional_sedimentation_stays_a_plot_gap():
    rows = synthetic_selected_rows()
    target = next(row for row in rows if row['point_id'] == 'RN1_10942'
                  and row['field'] == 'QR' and row['native_k_1based'] == '1')
    target['paired_sedimentation_calls'] = '179'
    target['delta_rain_sedimentation_sum'] = ''
    target['remaining_call_internal_sum'] = ''
    profiles = p.prepare_profiles(rows)
    assert np.isnan(profiles[('RN1_10942', 'QR')]['process_substep'][0])
    assert np.isnan(profiles[('RN1_10942', 'QR')]['remaining'][0])


def test_rejects_incomplete_or_invalid_population():
    rows = synthetic_selected_rows()
    rows.pop()
    with pytest.raises(p.NativeFigureInputError, match='incomplete'):
        p.prepare_profiles(rows)
    rows = synthetic_selected_rows()
    rows[0]['point_id'] = 'RN1_99999'
    with pytest.raises(p.NativeFigureInputError, match='unexpected point or field'):
        p.prepare_profiles(rows)


def test_rejects_null_as_zero_for_required_component():
    rows = synthetic_selected_rows()
    target = next(row for row in rows if row['point_id'] == 'RN1_12299'
                  and row['field'] == 'TK' and row['native_k_1based'] == '4')
    target['delta_condensation_substep_sum'] = ''
    with pytest.raises(p.NativeFigureInputError, match='required condensation/remaining'):
        p.prepare_profiles(rows)
