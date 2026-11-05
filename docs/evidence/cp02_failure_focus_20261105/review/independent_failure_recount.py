#!/usr/bin/env python3
"""Independently recount selected paired diagnostics from the six saved NPZs.

Reads the pinned scored arrays directly. It does not import production scoring,
plotting, or model code. This validates the stated count arithmetic only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
RESULTS = ROOT / 'docs/evidence/cp02_grouped_forecast_20261105/analysis'
HOURS = tuple(range(13, 19))
THRESHOLDS = (0.1, 5.0)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read_hours() -> tuple[dict, dict[int, dict[str, np.ndarray]]]:
    receipt_path = RESULTS / 'receipt.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    arrays = {}
    hashes = {'receipt.json': sha256(receipt_path)}
    for hour in HOURS:
        path = RESULTS / f'hour_{hour}_arrays.npz'
        hashes[path.name] = sha256(path)
        with np.load(path, allow_pickle=False) as archive:
            arrays[hour] = {key: np.array(archive[key], copy=True)
                            for key in ('reference', 'flat_index_yx', 'ORIGINAL', 'A', 'C')}
        if arrays[hour]['reference'].shape != (3688,):
            raise ValueError(f'{path.name}: unexpected point count')
        if len(np.unique(arrays[hour]['flat_index_yx'])) != 3688:
            raise ValueError(f'{path.name}: point keys are not unique')
    return {'receipt': receipt, 'input_sha256': hashes}, arrays


def events(values: dict[str, np.ndarray], case: str, threshold: float) -> np.ndarray:
    return values[case] >= threshold


def pair_counts(values: dict[str, np.ndarray], candidate: str, baseline: str,
                threshold: float) -> dict:
    obs, cand, base = values['reference'], events(values, candidate, threshold), events(values, baseline, threshold)
    hits_c = cand & (obs >= threshold)
    hits_b = base & (obs >= threshold)
    false_c = cand & (obs < threshold)
    false_b = base & (obs < threshold)
    return {
        'delta_hit': int(np.count_nonzero(hits_c) - np.count_nonzero(hits_b)),
        'delta_false_alarm': int(np.count_nonzero(false_c) - np.count_nonzero(false_b)),
        'hit_gains': int(np.count_nonzero(hits_c & ~hits_b)),
        'hit_losses': int(np.count_nonzero(hits_b & ~hits_c)),
        'false_alarm_gains': int(np.count_nonzero(false_c & ~false_b)),
        'false_alarm_resolutions': int(np.count_nonzero(false_b & ~false_c)),
    }


def weak_transition(values: dict[str, np.ndarray], candidate: str, baseline: str) -> dict:
    obs = values['reference']
    weak = (obs >= 0.1) & (obs < 1.0)
    cand, base = events(values, candidate, 0.1), events(values, baseline, 0.1)
    gain = weak & cand & ~base
    loss = weak & base & ~cand
    return {'weak_observed_points': int(np.count_nonzero(weak)),
            'detection_gains': int(np.count_nonzero(gain)),
            'detection_losses': int(np.count_nonzero(loss)),
            'gain_flat_indices': values['flat_index_yx'][gain].astype(int).tolist(),
            'loss_flat_indices': values['flat_index_yx'][loss].astype(int).tolist()}


def main() -> None:
    source, arrays = read_hours()
    per_hour = {}
    for hour in HOURS:
        lead = hour - 12
        values = arrays[hour]
        per_hour[str(lead)] = {
            'C_minus_A_at_5mm': pair_counts(values, 'C', 'A', 5.0),
            'A_minus_ORIGINAL_weak': weak_transition(values, 'A', 'ORIGINAL'),
            'C_minus_A_weak': weak_transition(values, 'C', 'A'),
        }

    lost_original_to_a = set(per_hour['2']['A_minus_ORIGINAL_weak']['loss_flat_indices'])
    recovered_by_c = lost_original_to_a & set(per_hour['2']['C_minus_A_weak']['gain_flat_indices'])
    remaining_losses = lost_original_to_a - recovered_by_c
    neighbors_4_to_6 = {
        'event_gains': sum(per_hour[str(lead)]['C_minus_A_weak']['detection_gains'] for lead in (4, 5, 6)),
        'event_losses': sum(per_hour[str(lead)]['C_minus_A_weak']['detection_losses'] for lead in (4, 5, 6)),
    }
    h5_loss_ids = per_hour['5']['C_minus_A_weak']['loss_flat_indices']
    amount_deltas = {}
    for flat_index in h5_loss_ids:
        accumulated = 0.0
        for lead in (4, 5, 6):
            values = arrays[lead + 12]
            position = int(np.flatnonzero(values['flat_index_yx'] == flat_index)[0])
            accumulated += float(values['C'][position] - values['A'][position])
        amount_deltas[str(flat_index)] = accumulated
    report = {
        'schema': 'cp02_failure_focus_independent_recount_v1',
        'status': 'PASS_ARITHMETIC_RECOUNT',
        'method': 'Direct paired boolean recount from six receipt-pinned NPZ arrays; no production scorer/model imports.',
        'source_receipt_status': source['receipt'].get('status'),
        'source_sha256': source['input_sha256'],
        'points_per_hour': 3688,
        'lead_hour_diagnostics': per_hour,
        'lead_2_original_to_a_lost_ids_recovered_by_c': {
            'lost_ids': sorted(lost_original_to_a),
            'recovered_ids': sorted(recovered_by_c),
            'remaining_ids': sorted(remaining_losses),
            'recovered_count': len(recovered_by_c),
            'remaining_count': len(remaining_losses),
        },
        'lead_4_to_6_weak_transition_sum_C_minus_A': neighbors_4_to_6,
        'fixed_h5_weak_loss_17_ids_amount_sum_C_minus_A_leads4_to6_mm': {
            'flat_index_amount_delta_mm': amount_deltas,
            'positive_count': sum(value > 0 for value in amount_deltas.values()),
            'negative_count': sum(value < 0 for value in amount_deltas.values()),
            'zero_count': sum(value == 0 for value in amount_deltas.values()),
        },
        'limits': [
            'Counts describe only the pinned six-hour, 3,688-point score cohort and stated thresholds.',
            'They do not establish mechanism, causality, flux, water-budget closure, or physical correctness.',
            'Flat indices are retained exactly as stored in the arrays; external ID interpretation is not inferred.',
        ],
    }
    out = Path(__file__).with_name('independent_failure_recount.json')
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'output': str(out),
                      'source_hashes': source['input_sha256']}, indent=2))


if __name__ == '__main__':
    main()
