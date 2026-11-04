"""Reconstruct selected hourly RAINC/RAINNC using the frozen WRF corners."""
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_rain_number_process_20261104'
CORNERS = BUNDLE / 'newcohorts/point_corners.csv'
CORNER_SHA = 'aa5da1ef6cdb8773addb139ef4cc385d3ea9e2b9d490368f79fd77086bca4b1b'
SOURCE = ROOT / 'docs/evidence/cp02_state_path_20261104/candidate/analysis'
RUNS = {
    'IMPROVED_BG_FIXED': Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED'),
    'B1_RAIN_NUMBER_PRIOR': Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_state_path_20261104/runtime/B1_RAIN_NUMBER_PRIOR_6H'),
}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run():
    assert sha(CORNERS) == CORNER_SHA
    corners = list(csv.DictReader(CORNERS.open()))
    point_ids = list(dict.fromkeys(row['point_id'] for row in corners))
    grouped = {point: [row for row in corners if row['point_id'] == point] for point in point_ids}
    assert len(point_ids) == 9 and all(len(rows) == 4 for rows in grouped.values())
    inputs, cumulative, descriptions, surface_rows = {}, {}, {}, []
    for case, directory in RUNS.items():
        for hour in range(12, 19):
            path = directory / f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
            inputs[str(path)] = {'sha256': sha(path), 'size_bytes': path.stat().st_size}
            with Dataset(path) as ds:
                assert tuple(ds['RAINC'].shape[1:]) == (282, 234)
                fields = {name: np.asarray(ds[name][0], dtype=np.float64) for name in ('RAINC', 'RAINNC')}
                if hour <= 15:
                    for row in corners:
                        j, i = int(row['native_j_zero_based']), int(row['native_i_zero_based'])
                        record = {'case': case, 'valid_hour_utc': hour,
                                  'point_id': row['point_id'], 'corner': row['corner'],
                                  'i_1based': i + 1, 'j_1based': j + 1}
                        for name, field in fields.items():
                            value = np.float32(field[j, i])
                            record[name + '_cumulative_mm'] = float(value)
                            record[name + '_f32_le_hex'] = value.astype('<f4').tobytes().hex()
                        surface_rows.append(record)
                for name in fields:
                    assert ds[name].units == 'mm'
                    descriptions[name] = ds[name].description
                    for point, rows in grouped.items():
                        terms = [float(row['weight']) * float(fields[name][int(row['native_j_zero_based']), int(row['native_i_zero_based'])]) for row in rows]
                        assert all(math.isfinite(value) for value in terms)
                        cumulative[case, hour, point, name] = math.fsum(terms)
    rows = []
    unit_roundoff = np.finfo(np.float64).eps / 2
    gamma32 = 32 * unit_roundoff / (1 - 32 * unit_roundoff)
    for hour in range(13, 19):
        canonical = SOURCE / f'hour_{hour}_arrays.npz'
        inputs[str(canonical.relative_to(ROOT))] = {'sha256': sha(canonical), 'size_bytes': canonical.stat().st_size}
        with np.load(canonical, allow_pickle=False) as arrays:
            for point in point_ids:
                index = int(grouped[point][0]['rn1_sample_index_zero_based'])
                for case in RUNS:
                    values = {name: cumulative[case, hour, point, name] - cumulative[case, hour - 1, point, name] for name in ('RAINC', 'RAINNC')}
                    total = math.fsum(values.values())
                    expected = float(arrays[case][index])
                    scale = math.fsum(abs(cumulative[case, hh, point, name]) for hh in (hour - 1, hour) for name in values)
                    bound = gamma32 * scale
                    residual = total - expected
                    assert abs(residual) <= bound, (point, hour, case, residual, bound)
                    rows.append({'point_id': point, 'lead_hour': hour - 12, 'valid_hour_utc': hour, 'case': case,
                                 'RAINC_hour_mm': values['RAINC'], 'RAINNC_hour_mm': values['RAINNC'],
                                 'total_hour_mm': total, 'canonical_total_hour_mm': expected,
                                 'total_reconstruction_residual_mm': residual, 'roundoff_bound_mm': bound})
    assert len(rows) == 108
    output = BUNDLE / 'science/precipitation_components.csv'
    with output.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    assert len(surface_rows) == 288
    surface_output = BUNDLE / 'science/native_surface_reference.csv'
    with surface_output.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(surface_rows[0]))
        writer.writeheader()
        writer.writerows(surface_rows)
    receipt = {'status': 'PASS_COMPONENT_RECONSTRUCTION', 'rows': len(rows), 'cases': list(RUNS),
               'source_sha256': sha(Path(__file__)), 'corners_sha256': CORNER_SHA, 'input_files': inputs,
               'output_sha256': sha(output), 'descriptions_from_history': descriptions,
               'native_surface_reference': {'rows': len(surface_rows), 'sha256': sha(surface_output),
                                            'scope': 'Original history values at 36 distinct native corners; each f32 word is preserved for a direct native RAINNC-return check. This is extraction, not a new integration.'},
               'max_absolute_residual_mm': max(abs(row['total_reconstruction_residual_mm']) for row in rows),
               'scope': 'RAINC and RAINNC increments at the frozen points; KDM6 native surface records concern RAINNC, not total. External original histories required to replay this component split. Canonical total arrays remain repository-replayable. No cumulative reset or negative increment correction.',
               'roundoff': 'gamma32 times sum of absolute four cumulative component values; IEEE binary64 bookkeeping bound, not a physical tolerance.'}
    (BUNDLE / 'science/precipitation_components_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: receipt[key] for key in ('status', 'rows', 'max_absolute_residual_mm')}))


if __name__ == '__main__':
    run()
