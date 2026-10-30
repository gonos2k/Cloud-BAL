"""Fine-factor scorer contract and ranking tests."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'cp02_snow_fine', ROOT / 'tools/cp02_snow_fine.py')
fine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fine)


def _selection_rows():
    categorical, continuous = [], []
    for index, case in enumerate(fine.ELIGIBLE_CASES):
        categorical.extend([
            {'lead_hour': 1, 'case': case, 'threshold_mm': 10.0,
             'CSI': 0.1 + index / 100.0, 'FAR': 0.5},
            {'lead_hour': 1, 'case': case, 'threshold_mm': 5.0,
             'CSI': 0.2 + index / 100.0, 'FAR': 0.5},
        ])
        continuous.append({'lead_hour': 1, 'case': case, 'RMSE_mm': 10.0 - index})
    return categorical, continuous


def test_fine_case_scope_is_31_contexts_and_30_eligible():
    assert len(fine.NEW_CASES) == 8
    assert len(fine.ELIGIBLE_CASES) == 30
    assert len(fine.CONTEXT_CASES) == 31
    assert fine.CONTEXT_CASES.count('CURRENT_HYDRO') == 1
    assert 'CURRENT_HYDRO' not in fine.ELIGIBLE_CASES
    assert set(fine.NEW_CASES) <= set(fine.ELIGIBLE_CASES)


def test_frozen_fine_plan_and_prior_analysis_are_hash_bound():
    record, plan = fine.check_selection_plan()
    assert record['sha256'] == fine.PLAN_SHA256
    assert plan['experiment']['factor_codes'] == ['110', '120', '130', '140']
    receipt, _, records = fine.load_prior_analysis()
    assert len(receipt['cases']) == 23
    assert len(receipt['eligible_cases']) == 22
    assert len(records) == 11


def test_selector_uses_frozen_csi_priority_and_keeps_undefined_below_zero():
    categorical, continuous = _selection_rows()
    target = 'CONTROL_SNOW_110'
    # Selection depends on first-hour CSI, not the lowest RMSE or later-lead means.
    next(row for row in categorical if row['case'] == target and row['threshold_mm'] == 10.0)['CSI'] = 0.99
    next(row for row in continuous if row['case'] == target)['RMSE_mm'] = 999.0
    rows, selection = fine.load_module('extension_for_test', fine.PRIOR_TOOL).select_case(
        categorical, continuous, fine.ELIGIBLE_CASES)
    assert rows[0]['case'] == target
    assert selection['ranking_order'][0] == 'descending +1h CSI at 10 mm'

    categorical, continuous = _selection_rows()
    undefined, defined = 'CONTROL_SNOW_110', 'CONTROL_SNOW_120'
    next(row for row in categorical if row['case'] == undefined and row['threshold_mm'] == 10.0)['CSI'] = None
    next(row for row in categorical if row['case'] == defined and row['threshold_mm'] == 10.0)['CSI'] = 0.0
    rows, _ = fine.load_module('extension_for_test_again', fine.PRIOR_TOOL).select_case(
        categorical, continuous, fine.ELIGIBLE_CASES)
    positions = {row['case']: i for i, row in enumerate(rows)}
    assert positions[defined] < positions[undefined]


def test_runtime_common_plan_rejects_incomplete_case_set(tmp_path):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    common = runtime / 'common_plan.json'
    common.write_text(json.dumps({'status': 'PASS_READY_TO_LAUNCH', 'case_records': {}}))
    with pytest.raises(ValueError, match='common plan has incomplete scope'):
        fine.check_runtime(runtime, {'sha256': 'plan-pin'}, hashlib.sha256(common.read_bytes()).hexdigest())


def test_prior_analysis_receipt_pin_rejects_altered_receipt(tmp_path, monkeypatch):
    receipt = tmp_path / 'receipt.json'
    receipt.write_text('{}\n')
    monkeypatch.setattr(fine, 'PRIOR_RECEIPT_SHA256', hashlib.sha256(receipt.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match='analysis scope is incomplete'):
        fine.load_prior_analysis(tmp_path)
