#!/usr/bin/env python3
"""Independently check raw CP04 sample arithmetic and four-corner products."""
import csv
import hashlib
import json
import struct
import sys
from pathlib import Path
import numpy as np


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def scan(root, wanted):
    out = {}
    for path in sorted(root.glob('cp04_rank*.bin')):
        with path.open('rb', buffering=1048576) as f:
            while magic := f.read(8):
                if magic != b'C4FR0001':
                    raise ValueError('bad frame marker')
                rank, call, step, j, its, ite, kts, kte = struct.unpack('>8i', f.read(32))
                if step > 1:
                    break
                f.read(40)
                while True:
                    phase, = struct.unpack('>i', f.read(4))
                    if phase == -1:
                        break
                    i, k, loop, loops, substep, mstep, nfields = struct.unpack('>7i', f.read(28))
                    if (i, j) in wanted and k in (1, 20, 39) and phase in (6, 7, 8, 11, 12):
                        data = np.frombuffer(f.read(nfields * 4), dtype='>f4').astype(np.float32)
                        key = (i, j, k, phase)
                        if key in out:
                            raise ValueError('duplicate sample')
                        out[key] = data
                    else:
                        f.seek(nfields * 4, 1)
    if len(out) != len(wanted) * 3 * 5:
        raise ValueError(f'incomplete sample: {len(out)}')
    return out


def same32(a, b):
    return np.float32(a).view(np.uint32) == np.float32(b).view(np.uint32)


def main():
    base = Path(sys.argv[1]).resolve()
    bundle = Path(sys.argv[2]).resolve()
    corners = bundle / 'cohorts/results/point_corners.csv'
    rows = list(csv.DictReader(corners.open(newline='')))
    points = list(dict.fromkeys(r['point_id'] for r in rows))
    point = 'NFA01'
    selected = [r for r in rows if r['point_id'] == point]
    cells = [(int(r['wrf_i_1based']), int(r['wrf_j_1based'])) for r in selected]
    weights = [float(r['weight']) for r in selected]
    point_index = points.index(point)
    if len(cells) != 4:
        raise ValueError('four corners required')
    report = {'status': 'PASS', 'method': 'Independent struct parsing and float32 arithmetic for four raw corners at first step and levels 1,20,39; independently recomputed weighted outputs.',
              'point': point, 'corners_sha256': sha(corners), 'arms': {}}
    for arm in ('B1', 'DM065'):
        source = base / arm
        raw = scan(source, set(cells))
        path = base / 'analysis' / (arm + '_point_timeseries.npz')
        checks = 0
        max_residual = 0.0
        with np.load(path, allow_pickle=False) as output:
            for k in (1, 20, 39):
                for cell in cells:
                    a, l, z, c, d = (raw[(*cell, k, p)] for p in (6, 7, 8, 11, 12))
                    f = np.float32
                    if not (same32(f(a[1] + f(a[16] * a[17])), z[1]) and
                            same32(f(a[2] - f(f(l[1] / l[2]) * l[3])), z[2]) and
                            same32(f(c[1] - f(c[9] * c[10])), d[1]) and
                            same32(f(c[2] + f(f(f(c[9] * c[11]) / c[12]) * c[10])), d[2])):
                        raise ValueError(f'raw arithmetic mismatch: {arm} {cell} {k}')
                    checks += 4
                for phase in (6, 7, 8, 11, 12):
                    a = np.array([raw[(*cell, k, phase)] for cell in cells], dtype=np.float64)
                    expected = np.sum(a * np.array(weights)[:, None], axis=0)
                    actual = output[f'phase_{phase}'][0, k - 1, point_index]
                    error = float(np.max(np.abs(expected - actual)))
                    max_residual = max(max_residual, error)
                    if not np.allclose(expected, actual, rtol=2e-15, atol=1e-20):
                        raise ValueError(f'weighted sample mismatch: {arm} {k} phase {phase}, {error}')
                    checks += len(expected)
                expected = sum(w * (float(raw[(*cell,k,8)][2]) - float(raw[(*cell,k,6)][2])) for cell,w in zip(cells,weights))
                if not np.isclose(expected, output['latent_temperature_change'][0,k-1,point_index],rtol=2e-15,atol=1e-20):
                    raise ValueError('latent weighted change mismatch')
                checks += 1
        report['arms'][arm] = {'raw_corner_level_samples': 12, 'individual_checks': checks,
                               'max_weighted_absolute_residual': max_residual,
                               'analysis_npz_sha256': sha(path)}
    report['analyzer_source_sha256'] = sha(Path('tools/cp02_thermo_cloud_path.py'))
    report['full_capture_receipt_sha256'] = sha(bundle / 'analysis/full_capture_receipt.json')
    dest = bundle / 'validation/native_raw_sample_review.json'
    dest.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
