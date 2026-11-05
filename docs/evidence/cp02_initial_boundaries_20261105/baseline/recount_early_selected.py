#!/usr/bin/env python3
"""Preserve PR148's first four selected-cell boundaries without a new run."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
from pack_cp02_selected_npz import load_partarrays
from cp02_thermo_cloud_path import weighted

PRIOR = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
BUNDLE = ROOT / 'docs/evidence/cp02_initial_boundaries_20261105'
PINS = {
    'docs/evidence/cp02_thermo_cloud_path_20261105/native/schema/cp04_schema.json': '64496e9f19ec0042762a7b8fa7d4f8006ea617a45433434242706c223db2210c',
    'tools/pack_cp02_selected_npz.py': '3c929e783856119daebf5b35487a0b10330d368db201024e5e57e7b37c34fb4d',
    'tools/cp02_thermo_cloud_path.py': 'a1b0d5ac6a418d5bcd679eaa4a8fdb9e3e8cb1bb63a8cebb6268c849b9efad8d',
    'docs/evidence/cp02_thermo_cloud_path_20261105/analysis/full_capture_receipt.json': 'e41105c152b55991784f1fcf0b8c8e1c75fe03fc3d33160b897160adadd33245',
}
PARTS = {
    'B1': '2d6a6fb716de26f7abb4428d85137c92b33a242e7d35b1e83c796e21163dff09',
    'DM065': '5bc658ead82af6b75984c7c5af365ecb0c3fad80afcdd0209b51c0ff44b209fd',
}
FIELDS = ('TH', 'QV', 'QC', 'QR', 'QI', 'QS', 'QG', 'NN', 'NC', 'NI', 'NR', 'BG', 'DEN', 'TK', 'P', 'PII')
FOCUS = {'NFA05': 17051, 'NFA12': 20183, 'RFA08': 16454, 'RFA11': 20330}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(output):
    if os.path.lexists(output):
        raise FileExistsError(output)
    for name, expected in PINS.items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'prior source or receipt changed: {name}')
    schema = json.loads((PRIOR / 'native/schema/cp04_schema.json').read_text())
    if tuple(x.replace('TK=TH*PII', 'TK') for x in schema['wrapper_selected']['fields']) != FIELDS:
        raise ValueError('wrapper field order changed')
    rec = json.loads((PRIOR / 'analysis/full_capture_receipt.json').read_text())
    cells = np.asarray(rec['native_cells_i_j_1based'], dtype='i4')
    indices = np.asarray(rec['point_corner_indices'], dtype='i4')
    weights = np.asarray(rec['point_corner_weights'], dtype='f8')
    arrays = {}
    part_pins = {}
    for arm, expected in PARTS.items():
        path = PRIOR / f'analysis/{arm}_native_wrapper_parts/{arm}_native_wrapper.parts.json'
        if sha(path) != expected or json.loads(path.read_text())['source_sha256'] != rec['arms'][arm]['native_wrapper_sha256']:
            raise ValueError(f'prior array manifest changed: {arm}')
        part_pins[str(path.relative_to(ROOT))] = expected
        full = load_partarrays(path, names=['entry', 'returned'])
        for boundary, name in [('entry', 'entry'), ('return', 'returned')]:
            a = full[name]
            if a.shape != (360, 39, 123, 16) or a.dtype.kind != 'f' or a.dtype.itemsize != 4:
                raise ValueError(f'prior wrapper layout changed: {arm}/{boundary}')
            arrays[f'{arm}_{boundary}'] = a[:4].copy()
        del full
    for name, a in arrays.items():
        if not np.isfinite(a).all() or not np.array_equal(a[..., 13].view('u4'), (a[..., 0] * a[..., 15]).view('u4')):
            raise ValueError(f'nonfinite value or TK product mismatch: {name}')
    delta = arrays['DM065_entry'].astype('f8') - arrays['B1_entry'].astype('f8')
    wd = weighted(arrays['DM065_entry'], indices, weights) - weighted(arrays['B1_entry'], indices, weights)
    rows = []
    for pid, flat in FOCUS.items():
        point = rec['point_ids'].index(pid)
        for field in ('NR', 'QV', 'QC', 'TH', 'TK', 'P', 'PII', 'QR'):
            f = FIELDS.index(field)
            for mode, a in [('native', delta[:, :, indices[point], f]), ('weighted', wd[:, :, point, f])]:
                hits = np.flatnonzero(np.any(a != 0, axis=tuple(range(1, a.ndim))))
                first = int(hits[0]) if len(hits) else None
                level = corner = None
                value = ''
                if first is not None:
                    at = np.unravel_index(np.argmax(np.abs(a[first])), a[first].shape)
                    level = int(at[0]) + 1
                    corner = int(at[1]) if mode == 'native' else None
                    value = float(a[first][at])
                cell = cells[indices[point, corner]] if corner is not None else ('', '')
                rows.append({'point_id': pid, 'flat_index_yx': flat, 'field': field, 'mode': mode,
                             'first_sample_step_within_1_to_4': first + 1 if first is not None else '',
                             'representative_k_1based': level or '', 'native_i_1based': cell[0],
                             'native_j_1based': cell[1], 'difference_at_first_step_max_abs': value,
                             'window_max_abs': float(np.max(np.abs(a)))})
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.early-selected-', dir=output.parent))
    try:
        np.savez_compressed(stage / 'early_selected.npz', **arrays, native_cells_i_j_1based=cells,
                            point_corner_indices=indices, point_corner_weights=weights,
                            point_ids=np.asarray(rec['point_ids']), fields=np.asarray(FIELDS))
        with (stage / 'entry_frontier.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        result = {'status': 'PASS', 'pins': {**PINS, **part_pins}, 'script_sha256': sha(Path(__file__)),
                  'steps': [1, 2, 3, 4], 'native_cells': 123, 'levels': 39, 'fields': list(FIELDS),
                  'table_rows': len(rows), 'TK_float32_product_checks': 2 * 2 * 4 * 39 * 123,
                  'semantics': 'Existing PR148 selected Eulerian boundary data; numerical nonzero, not physical onset. Native columns follow receipt coordinate order, not GC labels. Table is ENTRY only. Returned TK already includes t/pii then TH*pii mapping within KDM6; intercall net starts after this boundary.',
                  'outputs': {n: sha(stage / n) for n in ['early_selected.npz', 'entry_frontier.csv']}}
        (stage / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
        if os.path.lexists(output):
            raise FileExistsError(output)
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print('PASS: first four calls, 64 frontier rows and 76,752 TK product checks')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=BUNDLE / 'baseline/results')
    run(parser.parse_args().output)
