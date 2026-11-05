import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import cp02_thermo_cloud_path as cp


def make_frame(missing=None, duplicate=None):
    out = bytearray(b'C4FR0001' + struct.pack('>8i10f', 3, 4, 1, 9, 1, 10, 1, 1, *([1.] * 10)))
    records = [(1, 0, 0), (2, 0, 0)]
    records += [(p, 1, 0) for p in (3, 4, 5, 6, 7, 8, 11, 12)]
    records += [(p, 1, n) for n in (1, 2) for p in (9, 10)]
    if missing:
        records.remove(missing)
    if duplicate:
        records.append(duplicate)
    for phase, loop, step in records:
        out += struct.pack('>8if', phase, 7, 1, loop, loop, step, 2 if step else 0, 1, float(phase))
    out += struct.pack('>i', -1)
    return out


def parse(tmp_path, payload):
    path = tmp_path / 'capture.bin'
    path.write_bytes(payload)
    return list(cp.iter_frames(path, {p: 1 for p in range(1, 18)}, 3))


def test_complete_frame_and_exact_last_substep(tmp_path):
    frame, records = parse(tmp_path, make_frame())[0]
    assert frame.constants == (1.,) * 10
    cp.validate_frame(frame, records, [7])
    frame, records = parse(tmp_path, make_frame(missing=(10, 1, 2)))[0]
    with pytest.raises(ValueError, match='missing sedimentation'):
        cp.validate_frame(frame, records, [7])


def test_duplicate_missing_unknown_and_truncated(tmp_path):
    frame, records = parse(tmp_path, make_frame(duplicate=(3, 1, 0)))[0]
    with pytest.raises(ValueError, match='duplicate'):
        cp.validate_frame(frame, records, [7])
    frame, records = parse(tmp_path, make_frame(missing=(6, 1, 0)))[0]
    with pytest.raises(ValueError, match='missing mandatory'):
        cp.validate_frame(frame, records, [7])
    bad = make_frame()
    bad[80:84] = struct.pack('>i', 18)
    with pytest.raises(ValueError, match='unknown'):
        parse(tmp_path, bad)
    with pytest.raises(ValueError, match='truncated'):
        parse(tmp_path, make_frame()[:-5])


def test_nonfinite_and_field_count(tmp_path):
    bad = make_frame()
    bad[112:116] = struct.pack('>f', float('nan'))
    with pytest.raises(ValueError, match='nonfinite'):
        parse(tmp_path, bad)
    bad = make_frame()
    bad[108:112] = struct.pack('>i', 2)
    with pytest.raises(ValueError, match='field count'):
        parse(tmp_path, bad)


def test_exner_decomposition_reconstructs_actual_float32_product():
    a, b, c, d = [np.array([x], dtype=np.float32) for x in (300.13, .91, 300.19, .909)]
    theta, exner, residual = cp.exner_decomposition(a, b, c, d)
    actual = (c*d).astype('f8') - (a*b).astype('f8')
    np.testing.assert_allclose(theta + exner + residual, actual, atol=0, rtol=0)


def test_source_arithmetic_uses_actual_recorded_values():
    v = {6: np.zeros((1, 18), 'f4'), 8: np.zeros((1, 16), 'f4'),
         7: np.zeros((1, 6), 'f4'), 5: np.zeros((1, 41), 'f4'),
         11: np.zeros((1, 13), 'f4'), 12: np.zeros((1, 13), 'f4')}
    v[6][0, [1, 2, 16, 17]] = [.01, 280, .0001, 20]
    v[7][0, [1, 2, 3]] = [2., 1000., 20.]
    v[5][0, 2] = -.00002
    v[8][0, 1] = np.float32(v[6][0, 1] + np.float32(v[6][0, 16] * v[6][0, 17]))
    v[8][0, 2] = np.float32(v[6][0, 2] - np.float32(np.float32(2. / 1000.) * 20.))
    v[11][0, [1, 2, 9, 10, 11, 12]] = [.02, 280., .0001, 20., 2., 1000.]
    v[12][0, 1] = np.float32(v[11][0, 1] - np.float32(v[11][0, 9] * v[11][0, 10]))
    v[12][0, 2] = np.float32(v[11][0, 2] + np.float32(np.float32(np.float32(v[11][0, 9] * v[11][0, 11]) / v[11][0, 12]) * v[11][0, 10]))
    result = cp.process_arithmetic(v)
    assert result['prevp_q'][0] == np.float32(-np.float32(v[5][0, 2] * 20.))
    v[12][0, 1] += np.float32(.001)
    with pytest.raises(ValueError, match='source update'):
        cp.process_arithmetic(v)


def test_wrapper_number_density_conversion_and_pressure_guard():
    entry = np.zeros((1, 16), dtype='f4')
    entry[0, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15]] = [300, .01, .001, .002, .003, .004, .005, 100, 20, 30, 40, 2, 1.25, 90000, .9]
    entry[0, 13] = np.float32(entry[0, 0] * entry[0, 15])
    raw = np.zeros((1, 16), dtype='f4')
    for a, b in ((14, 0), (1, 1), (13, 2), (12, 3), (2, 4), (4, 5), (3, 6), (5, 7), (6, 8), (11, 15)):
        raw[0, b] = entry[0, a]
    for a, b in ((8, 9), (9, 10), (7, 11), (10, 12)):
        raw[0, b] = np.float32(entry[0, a] * entry[0, 12])
    clamped = raw.copy()
    clamped[0, 11] = 1.e8
    cp.validate_wrapper_binding(entry, entry.copy(), raw, clamped)
    bad = raw.copy()
    bad[0, 12] = entry[0, 10]
    with pytest.raises(ValueError, match='density conversion'):
        cp.validate_wrapper_binding(entry, entry, bad, clamped)
    returned = entry.copy()
    returned[0, 14] += 1
    with pytest.raises(ValueError, match='pressure or Exner'):
        cp.validate_wrapper_binding(entry, returned, raw, clamped)


def test_conditional_surface_absence_stays_nan_and_present_update_is_checked():
    surface = np.full((2, 1, 2, 12), np.nan, dtype='f4')
    pre = np.array([1, 0, 0, 0, 1, 0, 0, 2, 1000, 20, 3, 4], dtype='f4')
    post = pre.copy()
    increment = np.float32(np.float32(np.float32(np.float32(pre[4] * pre[7]) / pre[8]) * pre[9]) * 1000)
    post[10] = np.float32(pre[10] + increment)
    post[11] = np.float32(pre[11] + increment)
    surface[0, 0, 0] = pre
    surface[1, 0, 0] = post
    returned = np.zeros((1, 2, 3), dtype='f4')
    returned[0, 0, 1] = post[10]
    cp.validate_surface(surface, returned)
    assert np.isnan(surface[:, 0, 1]).all()
    surface[1, 0, 0, 11] += 1
    with pytest.raises(ValueError, match='surface accumulation'):
        cp.validate_surface(surface, returned)


def test_reference_surface_word_matches_and_corruption_fails(tmp_path):
    import csv
    import json
    path = tmp_path / 'native_surface.csv'
    with path.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('arm', 'hour', 'wrf_i_1based', 'wrf_j_1based', 'RAINNC_float32_le_hex'))
        for h, value in enumerate((0., 1.25, 2.5)):
            writer.writerow(('B1', h, 7, 9, struct.pack('<f', value).hex()))
    receipt = tmp_path / 'receipt.json'
    receipt.write_text(json.dumps({'status': 'PASS', 'cohort_sha256': {'point_corners.csv': 'b5d4de1d9209048e6e157ec8d5fe801f8464ee0b9fe307f5656cff32e09923fa'}, 'outputs': {'native_surface.csv': {'sha256': cp.sha256(path)}}}))
    returned = np.zeros((360, 1, 3), dtype='f4')
    returned[179, 0, 1], returned[359, 0, 1] = 1.25, 2.5
    assert cp.validate_surface_reference(path, receipt, 'B1', [(7, 9)], returned, 360) == 2
    returned[359, 0, 1] = 2.5001
    with pytest.raises(ValueError, match='history word'):
        cp.validate_surface_reference(path, receipt, 'B1', [(7, 9)], returned, 360)
