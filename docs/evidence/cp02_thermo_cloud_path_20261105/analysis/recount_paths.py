#!/usr/bin/env python3
"""Summarize all selected-point paired CP04 stages without assigning causality."""
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
from contextlib import nullcontext

import numpy as np
from portable_arrays import load

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
CAPTURE = BUNDLE / 'analysis'
RECEIPT_SHA = 'e41105c152b55991784f1fcf0b8c8e1c75fe03fc3d33160b897160adadd33245'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    receipt_path = CAPTURE / 'full_capture_receipt.json'
    if sha(receipt_path) != RECEIPT_SHA:
        raise ValueError('full capture receipt differs')
    receipt = json.loads(receipt_path.read_text())
    pair_sha = receipt['paired_outputs']['paired_differences.npz']['sha256']
    if receipt['status'] != 'PASS_FULL_CAPTURE':
        raise ValueError('capture failed')
    points_path = BUNDLE / 'cohorts/results/selected_points.csv'
    with points_path.open(newline='') as stream:
        points = list(csv.DictReader(stream))
    if [r['point_id'] for r in points] != receipt['point_ids']:
        raise ValueError('point ordering differs')
    rows = []
    names = ['entry_difference', 'sedimentation_net_difference', 'prevp_q_difference',
             'latent_temperature_change_difference', 'condensation_q_change_difference',
             'condensation_temperature_change_difference', 'gap_post_update_to_pre_cond_q_difference',
             'gap_post_update_to_pre_cond_t_difference', 'gap_post_cond_to_return_q_difference',
             'gap_post_cond_to_return_t_difference', 'between_call_difference',
             'between_theta_difference', 'between_exner_difference', 'between_product_roundoff_difference']
    with nullcontext(load('paired_differences', pair_sha, names)) as data:
        entry = data['entry_difference']
        outputs = {
            'entry_qv_kgkg': entry[..., 1], 'entry_temperature_K': entry[..., 13],
            'entry_pressure_Pa': entry[..., 14], 'entry_cloud_water_kgkg': entry[..., 2],
            'entry_cloud_ice_kgkg': entry[..., 4], 'entry_rain_kgkg': entry[..., 3],
            'entry_rain_number_per_kg': entry[..., 10],
            'sedimentation_rain_net_kgkg': data['sedimentation_net_difference'][..., 0],
            'prevp_vapor_component_kgkg': data['prevp_q_difference'],
            'latent_temperature_change_K': data['latent_temperature_change_difference'],
            'condensation_vapor_change_kgkg': data['condensation_q_change_difference'],
            'condensation_temperature_change_K': data['condensation_temperature_change_difference'],
            'gap_post_update_to_pre_cond_q_kgkg': data['gap_post_update_to_pre_cond_q_difference'],
            'gap_post_update_to_pre_cond_t_K': data['gap_post_update_to_pre_cond_t_difference'],
            'gap_post_cond_to_return_q_kgkg': data['gap_post_cond_to_return_q_difference'],
            'gap_post_cond_to_return_t_K': data['gap_post_cond_to_return_t_difference'],
            'between_call_qv_kgkg': data['between_call_difference'][..., 1],
            'between_call_temperature_K': data['between_call_difference'][..., 13],
            'between_call_theta_term_K': data['between_theta_difference'],
            'between_call_exner_term_K': data['between_exner_difference'],
            'between_call_product_roundoff_K': data['between_product_roundoff_difference'],
        }
        for field, values in outputs.items():
            if values.shape[1:] != (39, len(points)) or not np.isfinite(values).all():
                raise ValueError(f'invalid field shape/data: {field}')
            for i, point in enumerate(points):
                sample = values[:, :, i]
                changed = np.flatnonzero(np.any(sample != 0, axis=1))
                loc = np.unravel_index(np.abs(sample).argmax(), sample.shape)
                rows.append({'point_id': point['point_id'], 'group': point['group'],
                             'flat_index_yx': point['flat_index_yx'], 'field': field,
                             'first_step': int(changed[0] + 1) if changed.size else '',
                             'max_abs': float(abs(sample[loc])), 'signed_at_max': float(sample[loc]),
                             'max_step': int(loc[0] + 1), 'max_level_1based': int(loc[1] + 1)})
    target = BUNDLE / 'analysis/point_stage_recount.csv'
    receipt_out = BUNDLE / 'analysis/point_stage_recount.json'
    if os.path.lexists(target) or os.path.lexists(receipt_out):
        raise FileExistsError('refusing to replace prior recount')
    fd, temp = tempfile.mkstemp(prefix='.recount-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        record = {'status': 'PASS', 'rows': len(rows), 'points': len(points),
                  'full_receipt_sha256': RECEIPT_SHA, 'paired_sha256': pair_sha,
                  'points_sha256': sha(points_path), 'script_sha256': sha(BUNDLE / 'attempts/portability/recount_paths.py'),
                  'csv_sha256': sha(temp),
                  'semantics': 'DM065 minus B1 weighted at native corners; first_step is the first sampled nonzero, not a causal onset. A step labels the interval ending at step*20 seconds; between-call row 1 bridges return of step 1 and entry of step 2. Phase gaps are unassigned. Sedimentation occurs before the main process update within each step.'}
        os.link(temp, target)
        with receipt_out.open('x') as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.write('\n')
    finally:
        Path(temp).unlink(missing_ok=True)
    print(json.dumps(record))


if __name__ == '__main__':
    main()
