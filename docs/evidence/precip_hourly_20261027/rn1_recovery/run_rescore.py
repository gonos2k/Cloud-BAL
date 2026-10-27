#!/usr/bin/env python3
"""Read-only extended-threshold rerun of the archived six-hour comparison."""
from __future__ import annotations
import csv
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np

BASE = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914')
OUT = Path('/var/tmp/rn1-rescore-final-20261027')
SCRIPT = BASE / 'compare_six_hour_csi.py'
THRESHOLDS_MM = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
spec = importlib.util.spec_from_file_location('archived_compare_six_hour_csi', SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
assert spec.loader is not None
spec.loader.exec_module(module)
source_hash = module.sha256(SCRIPT)
module.THRESHOLDS_MM = THRESHOLDS_MM
original_threshold_counts = module.threshold_counts
captures = {}
call_number = 0
def capture_threshold_counts(forecast, reference, valid, threshold):
    global call_number
    if threshold == THRESHOLDS_MM[0]:
        hour_index, case_index = divmod(call_number, 3)
        hour = 13 + hour_index
        case = ('OFF', 'HYDRO', 'LIQUID')[case_index]
        captures[(hour, case)] = (forecast.copy(), reference.copy(), valid.copy())
        call_number += 1
    return original_threshold_counts(forecast, reference, valid, threshold)
module.threshold_counts = capture_threshold_counts
sys.argv = [
    str(SCRIPT),
    '--root', str(BASE),
    '--reference-dir', str(BASE / 'reference'),
    '--analysis', '/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300',
    '--odam-dir', '/NHNHOME/DATA/yhlee_data/ODAM/20260816',
    '--output', str(OUT / 'RESULT_CSI_108.json'),
]
module.main()
if len(captures) != 18:
    raise RuntimeError(f'expected 18 hour/case array captures, got {len(captures)}')
_, _, target_lat, target_lon, _ = module.load_reference(
    BASE / 'reference', Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300'))
for hour in range(13, 19):
    available = {case: captures[(hour, case)][2] for case in ('OFF', 'HYDRO', 'LIQUID')}
    common = available['OFF'] & available['HYDRO'] & available['LIQUID']
    if int(np.count_nonzero(common)) != 3688:
        raise RuntimeError(f'hour {hour}: expected 3688 common cells, got {np.count_nonzero(common)}')
    iy, ix = np.nonzero(common)
    ref = captures[(hour, 'OFF')][1][common]
    if not np.array_equal(ref, captures[(hour, 'HYDRO')][1][common]) or not np.array_equal(ref, captures[(hour, 'LIQUID')][1][common]):
        raise RuntimeError(f'hour {hour}: case reference arrays differ')
    np.savez_compressed(
        OUT / f'hour_{hour:02d}_arrays.npz',
        reference=ref.astype(np.float64),
        OFF=captures[(hour, 'OFF')][0][common].astype(np.float64),
        HYDRO=captures[(hour, 'HYDRO')][0][common].astype(np.float64),
        LIQUID=captures[(hour, 'LIQUID')][0][common].astype(np.float64),
        latitude=target_lat[common].astype(np.float64),
        longitude=target_lon[common].astype(np.float64),
        flat_index_yx=np.ravel_multi_index((iy, ix), (253, 149)).astype(np.int32),
    )
result = json.loads((OUT / 'RESULT_CSI_108.json').read_text())
with (OUT / 'hourly_csi_108.csv').open('w', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(('case','lead_hour','valid_utc','threshold_mm','valid_cells','hit','miss','false_alarm','correct_dry','CSI'))
    for hour in range(13, 19):
        for threshold in THRESHOLDS_MM:
            for case in ('OFF', 'HYDRO', 'LIQUID'):
                item = result['cases'][case.lower()]['hourly'][str(hour)]
                count = item['threshold_mm'][str(threshold)]
                writer.writerow((case, hour - 12, f'2026-08-16T{hour:02d}:00:00Z', threshold, item['valid_cells'], count['hit'], count['miss'], count['false_alarm'], count['correct_dry'], count['CSI']))
receipt = {
    'runner': str(Path(__file__).resolve()),
    'source_script': str(SCRIPT),
    'source_script_sha256': source_hash,
    'runtime_threshold_override_mm': list(THRESHOLDS_MM),
    'output_json': str(OUT / 'RESULT_CSI_108.json'),
    'output_csv': str(OUT / 'hourly_csi_108.csv'),
    'array_npz': [str(OUT / f'hour_{hour:02d}_arrays.npz') for hour in range(13, 19)],
    'mode': 'import archived module, change only module.THRESHOLDS_MM and threshold_counts capture hook, invoke unchanged main()',
    'first_attempt_note': 'The preliminary unhooked output in this scratch directory was superseded by this hooked run; only this final runner, result, and input-pin pair are retained as validation evidence.',
    'array_capture': 'forecast/reference/valid passed to unchanged threshold_counts at threshold 0.1; NPZ stores common selected cells only',
}
(OUT / 'runtime_override_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
