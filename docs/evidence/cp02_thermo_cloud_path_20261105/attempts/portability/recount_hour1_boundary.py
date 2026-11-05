#!/usr/bin/env python3
"""Compare sampled step-180 wrapper values with prior +1 h WRF history."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
CAPTURE = ROOT.parent / 'runtime/full/analysis'
PRIOR = ROOT / 'docs/evidence/cp02_failure_regimes_20261104/state/protocol.json'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    receipt_path = CAPTURE / 'receipt.json'
    if sha(receipt_path) != 'e41105c152b55991784f1fcf0b8c8e1c75fe03fc3d33160b897160adadd33245' or sha(PRIOR) != '5f44ad36d60e3443f7da7bbf7253359160114e954d3015ed8cef6ca059237690':
        raise ValueError('source receipt or protocol differs')
    rec = json.loads(receipt_path.read_text())
    protocol = json.loads(PRIOR.read_text())
    cells = rec['native_cells_i_j_1based']
    indices = rec['point_corner_indices']
    rows = []
    for arm in ('B1', 'DM065'):
        history = protocol['case_time_files'][arm]['h01']
        if sha(Path(history['path'])) != history['sha256']:
            raise ValueError('history source differs')
        native = CAPTURE / f'{arm}_native_wrapper.npz'
        if sha(native) != rec['arms'][arm]['native_wrapper_sha256']:
            raise ValueError('native state differs')
        with np.load(native, allow_pickle=False) as data, Dataset(history['path']) as ds:
            end = data['returned'][179]
            for field, idx in (('QRAIN', 3), ('QNRAIN', 10)):
                values = np.stack([np.asarray(ds[field][0, :, j-1, i-1], dtype='f4') for i, j in cells], axis=1)
                for point, corners in zip(rec['point_ids'], indices):
                    a = end[:, corners, idx]
                    b = values[:, corners]
                    if not np.isfinite(a).all() or not np.isfinite(b).all():
                        raise ValueError('nonfinite state')
                    delta = a.astype('f8') - b.astype('f8')
                    rows.append({'point_id': point, 'arm': arm, 'field': field,
                                 'wrapper_and_history_bit_equal_count': int(np.count_nonzero(a.view('u4') == b.view('u4'))),
                                 'sample_count': int(a.size), 'wrapper_max_abs': float(np.max(np.abs(a))),
                                 'history_max_abs': float(np.max(np.abs(b))),
                                 'max_abs_wrapper_minus_history': float(np.max(np.abs(delta)))})
    out = BUNDLE / 'analysis/hour1_wrapper_history_comparison.csv'
    with out.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'status': 'PASS', 'rows': len(rows), 'csv_sha256': sha(out),
                      'source_sha256': sha(Path(__file__)), 'full_receipt_sha256': sha(receipt_path)}))


if __name__ == '__main__':
    main()
