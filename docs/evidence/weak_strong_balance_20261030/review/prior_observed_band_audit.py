#!/usr/bin/env python3
"""Separate prior low-threshold score changes by observed intensity, for verification only."""
import csv
import hashlib
import io
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / 'docs/evidence/snow_lower_20261030/analysis'
RECEIPT_SHA = 'a9b8fa97e12d85bd49ce91b42f5126c8fc727ef0846eba1eeddc6a552a044602'
CASES = ('CONTROL_SNOW_300', 'IMPROVED_BG_FIXED', 'IMPROVED_SNOW_080')
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
BANDS = (('dry<0.1', 0.0, 0.1), ('light[0.1,1)', 0.1, 1.0),
         ('moderate[1,5)', 1.0, 5.0), ('strong[5,10)', 5.0, 10.0),
         ('very_strong>=10', 10.0, np.inf))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_exact(path, data):
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f'refusing to replace differing audit: {path}')
    path.write_bytes(data)


def run():
    receipt_path = SOURCE / 'receipt.json'
    if digest(receipt_path) != RECEIPT_SHA:
        raise ValueError('prior paired-array receipt changed')
    receipt = json.loads(receipt_path.read_text())
    rows, inputs = [], []
    for lead in range(1, 7):
        path = SOURCE / f'hour_{lead + 12}_arrays.npz'
        if digest(path) != receipt['analysis_outputs'][path.name]['sha256']:
            raise ValueError(f'prior array hash changed: {path}')
        inputs.append({'path': str(path.relative_to(ROOT)), 'sha256': digest(path)})
        with np.load(path, allow_pickle=False) as values:
            observed, baseline = values['reference'], values['ORIGINAL']
            if observed.shape != (3688,) or not np.isfinite(observed).all() or np.any(observed < 0):
                raise ValueError('invalid prior observations')
            for case in CASES:
                candidate = values[case]
                if candidate.shape != observed.shape or not np.isfinite(candidate).all():
                    raise ValueError('invalid prior candidate')
                for threshold in THRESHOLDS:
                    event, before, after = observed >= threshold, baseline >= threshold, candidate >= threshold
                    for name, lower, upper in BANDS:
                        mask = (observed >= lower) & (observed < upper)
                        count = lambda condition: int(np.count_nonzero(mask & condition))
                        rows.append({'case': case, 'lead_hour': lead, 'threshold_mm': threshold,
                                     'observed_band': name, 'points': int(mask.sum()),
                                     'baseline_hits': count(event & before), 'candidate_hits': count(event & after),
                                     'hits_lost': count(event & before & ~after),
                                     'hits_gained': count(event & ~before & after),
                                     'baseline_false_alarms': count(~event & before),
                                     'candidate_false_alarms': count(~event & after),
                                     'new_false_alarms': count(~event & ~before & after),
                                     'removed_false_alarms': count(~event & before & ~after),
                                     'baseline_misses': count(event & ~before),
                                     'candidate_misses': count(event & ~after)})
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    output = HERE / 'prior_observed_band.csv'
    save_exact(output, stream.getvalue().encode())
    record = {'status': 'PASS', 'scope': 'Verification-only prior observed intensity bins; never used to construct initialization gates.',
              'rows': len(rows), 'paired_points_per_lead': 3688, 'cases': list(CASES),
              'source_receipt_sha256': RECEIPT_SHA, 'source_arrays': inputs,
              'script_sha256': digest(__file__), 'csv_sha256': digest(output)}
    save_exact(HERE / 'prior_observed_band_receipt.json', (json.dumps(record, indent=2) + '\n').encode())
    print(json.dumps(record))


if __name__ == '__main__':
    run()
