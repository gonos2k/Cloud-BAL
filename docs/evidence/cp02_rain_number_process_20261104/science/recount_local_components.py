"""Separate evaporation/condensation terms at each native layer; never pool layers."""
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
from pack_cp02_selected_npz import load_partarrays

OUT = Path(__file__).resolve().parent
ANALYSIS = OUT.parent / 'analysis'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    history_path = ANALYSIS / 'point_history.npz'
    with np.load(history_path, allow_pickle=False) as h:
        points, indices, weights = h['points'].tolist(), h['corner_indices'], h['corner_weights']
    rows, inputs = [], {str(history_path.relative_to(ROOT)): sha(history_path)}
    for case in ('B1', 'NR_PRIOR'):
        manifest = ANALYSIS / f'selected_{case}_parts/selected_{case}.parts.json'
        inputs[str(manifest.relative_to(ROOT))] = sha(manifest)
        arrays = load_partarrays(manifest, names=['PROCESS_RATES', 'PRE_UPDATE', 'final_cond', 'sedimentation_delta'])
        rates = arrays['PROCESS_RATES'][:, 0]
        pre = arrays['PRE_UPDATE'][:, 0]
        cond = arrays['final_cond'][0, :, 0]
        dt = pre[..., 16]
        terms = {
            'PREVP_evaporation_qv_kgkg': np.multiply(np.maximum(-rates[..., 2], 0), dt, dtype=np.float32),
            'PREVP_condensation_qv_kgkg': np.multiply(-np.maximum(rates[..., 2], 0), dt, dtype=np.float32),
            'FINALCOND_evaporation_qv_kgkg': np.multiply(np.maximum(-cond[..., 7], 0), cond[..., 8], dtype=np.float32),
            'FINALCOND_condensation_qv_kgkg': np.multiply(-np.maximum(cond[..., 7], 0), cond[..., 8], dtype=np.float32),
            'RSG_sedimentation_QR_increment_kgkg': arrays['sedimentation_delta'][:, 0, ..., 4],
        }
        for j, point in enumerate(points):
            cc, ww = indices[j], weights[j]
            for lead in (1, 2, 3):
                ts = range(180 * (lead - 1), 180 * lead)
                for k in range(39):
                    row = {'case': case, 'point_id': point, 'lead_hour': lead, 'level_1based': k + 1}
                    for name, a in terms.items():
                        row[name] = math.fsum(float(ww[c]) * float(a[t, k, cc[c]]) for t in ts for c in range(4))
                    rows.append(row)
    assert len(rows) == 2106 and len({(x['case'], x['point_id'], x['lead_hour'], x['level_1based']) for x in rows}) == 2106
    output = OUT / 'local_process_components.csv'
    with output.open('w', newline='') as stream:
        w = csv.DictWriter(stream, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    receipt = {'status': 'PASS_LAYERWISE_RECOUNT', 'rows': len(rows), 'inputs': inputs,
               'source_sha256': sha(Path(__file__)), 'verified_loader_sha256': sha(ROOT / 'tools/pack_cp02_selected_npz.py'),
               'output_sha256': sha(output),
               'scope': 'Each row preserves one case, point, hour and native level. REAL32 vapor component products precede four-corner weighting and math.fsum temporal integration. Not a column mass, actual hourly qv/temperature change, or causal contribution fraction; no layer/case averaging.'}
    (OUT / 'local_process_components_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    for point in ('P01', 'H3_L05', 'FA03', 'H3_FA01'):
        for case in ('B1', 'NR_PRIOR'):
            print(next(x for x in rows if x['point_id'] == point and x['case'] == case and x['lead_hour'] == 2 and x['level_1based'] == 12))


if __name__ == '__main__':
    run()
