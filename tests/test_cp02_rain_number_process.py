import importlib.util
from pathlib import Path
import struct

import numpy as np
import pytest

PATH = Path(__file__).resolve().parents[1] / 'tools/cp02_rain_number_process.py'
spec = importlib.util.spec_from_file_location('rain_process', PATH)
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)


def word(v):
    return str(struct.unpack('<i', struct.pack('<f', v))[0])


def line(phase, substep=0, mstep=0, vals=None):
    if vals is None:
        vals = [1.] * rp.FIELD_COUNTS[phase]
    header = [phase, 0, 7, 1, 1, 1, 5, 6, 1, substep, mstep, len(vals)]
    return 'CP03 ' + ' '.join(map(str, header)) + ' ' + ' '.join(map(word, vals))


def accumulator():
    return rp.ProcessAccumulator([(5, 6)], 1, 1, 1, {(1, 5, 6, 1): (0, 7)})


def add(acc, row):
    h, raw, values = next(rp.records([row]))
    acc.add(h, values, file_rank=0)


def complete(acc, mstep=2):
    for n in range(1, mstep + 1):
        for phase in (1, 2):
            vals = [float(phase)] * rp.FIELD_COUNTS[phase]
            if phase == 2:
                vals[16:21] = [3.] * 5
            add(acc, line(phase, n, mstep, vals))
    pre = [1., 2., 3., 4., 5., 6., 7., .5, .25, 4., 2.]
    post = [.875, 2.25, 3.125, 4., 5., 6., 7., .5, .25, 4., 2.]
    add(acc, line(5, vals=pre))
    add(acc, line(6, vals=post))


def test_wrapped_records_preserve_bits_and_unknown_rejected():
    row = line(5, vals=[-0.] + [1.] * 10).split()
    h, raw, values = next(rp.records([' '.join(row[:9]), ' '.join(row[9:])]))
    assert h[0] == 5 and raw[0] == -(1 << 31) and np.signbit(values[0])
    with pytest.raises(rp.TraceError, match='unknown'):
        list(rp.records(['UNRECOGNIZED 1']))
    with pytest.raises(rp.TraceError, match='truncated'):
        list(rp.records([' '.join(row[:-1])]))
    with pytest.raises(rp.TraceError, match='nonfinite'):
        list(rp.records([line(5).rsplit(' ', 1)[0] + ' 2139095040']))


def test_complete_substeps_and_absent_surface_are_distinct():
    acc = accumulator()
    complete(acc)
    result = acc.finish()
    assert result['counts'][1] == result['counts'][2] == 2
    assert result['sedimentation_delta'][0, 0, 0, 0, 4] == 2.
    assert not result['surface_mask'].any()
    assert np.isnan(result['surface']).all()
    assert all(not residual.any() for residual in rp.arithmetic_residuals(result).values())


def test_missing_last_substep_duplicate_and_wrong_owner_fail():
    acc = accumulator()
    complete(acc)
    addrow = line(1, 1, 2)
    with pytest.raises(rp.TraceError, match='duplicate'):
        add(acc, addrow)
    acc = accumulator()
    complete(acc)
    acc.bits[1, 0, 0, 0, 0, 0] &= ~np.uint64(2)
    with pytest.raises(rp.TraceError, match='substep'):
        acc.finish()
    h, _, vals = next(rp.records([line(1, 1, 1)]))
    h[2] = 8
    with pytest.raises(rp.TraceError, match='owned'):
        accumulator().add(h, vals)


def test_conditional_surface_pair_and_arithmetic():
    acc = accumulator()
    complete(acc)
    pre = [1., 0., 0., 0., 1., 0., 0., 2., 1000., 1., 4., 5.]
    post = pre.copy()
    post[10:] = [6., 7.]
    add(acc, line(3, vals=pre))
    with pytest.raises(rp.TraceError, match='surface phase pair'):
        acc.finish()
    add(acc, line(4, vals=post))
    result = acc.finish()
    assert result['surface_mask'].all()
    assert all(not residual.any() for residual in rp.arithmetic_residuals(result).values())


def test_bad_count_unknown_phase_and_noninteger_keys():
    for row in (line(5).replace('CP03 5 ', 'CP03 9 ', 1),
                line(5).replace(' 11 ', ' 12 ', 1),
                line(5).replace('CP03 5 0 ', 'CP03 5 0_0 ', 1)):
        with pytest.raises(rp.TraceError):
            list(rp.records([row]))


def test_legacy_records_keep_optional_absence_and_validate_ownership():
    acc = rp.LegacyAccumulator([(5, 6)], 1, 1, 1, {(1, 5, 6, 1): (0, 7)})
    legacy = acc.legacy
    for phase in acc.REQUIRED:
        keys, fields, kind = legacy.SCHEMAS[phase]
        key = ([0, 7, 1, 6, 5] if 'k' not in keys else
               [0, 7, 1, 0 if phase.startswith('ENTRY_') else 1, 6, 5, 1])
        row = phase + ' ' + ' '.join(map(str, key)) + ' ' + ' '.join([word(1.)] * len(fields))
        rec = next(legacy.iter_fortran_records([row], '<test>'))
        acc.add(rec, file_rank=0)
    result = acc.finish()
    assert result['counts']['PROCESS_RATES'] == 1
    assert result['counts']['PREVP_FORMULA'] == 0
    assert np.isnan(result['values']['PREVP_FORMULA']).all()
    with pytest.raises(rp.TraceError, match='duplicate'):
        acc.add(rec)


def test_paired_ledger_separates_within_and_between_call():
    corners = (np.array([[0, 1, 2, 3]]), np.array([[.25, .25, .25, .25]]))
    base = np.zeros((2, 1, 4, 1), dtype=np.float32)
    entry = base.copy()
    returned = base.copy()
    entry[0] = 1.
    returned[0] = 3.
    entry[1] = 4.
    returned[1] = 8.
    ledger = rp.call_ledger(base, base, entry, returned, corners)
    assert ledger['sum_within_call'][0, 0, 0] == 6.
    assert ledger['sum_between_call'][0, 0, 0] == 1.
    assert ledger['total'][0, 0, 0] == 7.
    assert not ledger['residual'].any()


def test_selected_binary_and_call_ownership_reject_truncation(tmp_path):
    call_file = tmp_path / 'state_calls_rank0.txt'
    call_file.write_text('1 0 7 1 3 1 3 1 2 1 2 1 2 1 1 1 2 1 2 1 1\n')
    cells = [(1, 1)]
    owners, calls = rp.read_owners([call_file], cells, 1, 1)
    state = tmp_path / 'state_selected_entry_rank0.bin'
    header = struct.pack('>8s15i', b'CBSP0001', 6, 0, 7, 1,
                         1, 2, 1, 2, 1, 1, 1, 1, 1, 14, 1)
    row = struct.pack('>3i14f', 1, 1, 1, *range(14))
    state.write_bytes(header + row)
    values = rp.read_selected_state([state], 6, cells, 1, 1, owners, calls)
    assert values[0, 0, 0, 13] == 13
    state.write_bytes(header + row[:-1])
    with pytest.raises(rp.TraceError, match='truncated'):
        rp.read_selected_state([state], 6, cells, 1, 1, owners, calls)


def test_existing_dangling_output_is_never_replaced(tmp_path):
    output = tmp_path / 'analysis'
    output.symlink_to(tmp_path / 'missing')
    with pytest.raises(rp.TraceError, match='already exists'):
        rp.analyze(tmp_path / 'missing_manifest', tmp_path / 'schema', tmp_path / 'corners', output)
    assert output.is_symlink()


def test_nonzero_number_fields_convert_with_density_and_clamp():
    state = np.zeros((1, 14), dtype=np.float32)
    state[0, 12] = 1.25
    state[0, [7, 8, 9, 10]] = [1.e8, 2.e5, 4.e5, 600.]
    raw = np.zeros((1, 15), dtype=np.float32)
    raw[0, [10, 8, 9, 11]] = np.float32(state[0, [7, 8, 9, 10]] * state[0, 12])
    clamped = raw.copy()
    clamped[0, 10] = np.clip(raw[0, 10], 1.e8, 2.e10)
    rp.check_number_conversion(state, raw, clamped)
    wrong = raw.copy()
    wrong[0, 11] = state[0, 10]
    with pytest.raises(rp.TraceError, match='density conversion'):
        rp.check_number_conversion(state, wrong, clamped)
    wrong = clamped.copy()
    wrong[0, 9] = -1
    with pytest.raises(rp.TraceError, match='clamp'):
        rp.check_number_conversion(state, raw, wrong)


def test_surface_history_crosschecks_each_native_corner_bitwise(tmp_path):
    import csv
    path = tmp_path / 'surface.csv'
    rows = []
    for arm, case in [('B1', 'IMPROVED_BG_FIXED'), ('NR_PRIOR', 'B1_RAIN_NUMBER_PRIOR')]:
        for hour in (12, 13, 14, 15):
            value = float(hour - 12)
            rows.append({'case': case, 'valid_hour_utc': hour, 'i_1based': 5, 'j_1based': 6,
                         'RAINNC_cumulative_mm': value,
                         'RAINNC_f32_le_hex': struct.pack('<f', value).hex()})
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    data = {}
    for arm in ('B1', 'NR_PRIOR'):
        surface = np.zeros((540, 1, 3), np.float32)
        surface[[179, 359, 539], 0, 1] = [1, 2, 3]
        data[arm] = {'legacy': {'values': {'SURFACE_RETURN': surface}}}
    result = rp.check_surface_history(path, data, [(5, 6)], 540)
    assert result['records'] == 8 and result['hourly_boundary_bitwise_equal']
    data['B1']['legacy']['values']['SURFACE_RETURN'][359, 0, 1] = 3
    with pytest.raises(rp.TraceError, match='differs from history'):
        rp.check_surface_history(path, data, [(5, 6)], 540)


def test_first_native_difference_detects_weighted_cancellation(tmp_path):
    import csv
    state1 = np.zeros((1, 1, 4, 14), dtype=np.float32)
    state2 = state1.copy()
    state2[0, 0, 0, 1] = 1
    state2[0, 0, 1, 1] = -1
    rates = np.zeros((1, 1, 1, 4, 16), dtype=np.float32)
    left = {'state': {'entry': state1, 'return': state1},
            'legacy': {'values': {'PROCESS_RATES': rates}}}
    right = {'state': {'entry': state2, 'return': state2},
             'legacy': {'values': {'PROCESS_RATES': rates}}}
    corners = (np.array([[0, 1, 2, 3]]), np.full((1, 4), .25))
    assert not rp.weighted_cells(state2 - state1, corners).any()
    path = tmp_path / 'first.csv'
    rp.write_first_native_differences(path, ['P'], [(1, 1), (2, 1), (1, 2), (2, 2)], corners, left, right)
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    row = next(r for r in rows if r['stage'] == 'entry' and r['field'] == 'QV' and r['comparison'] == 'numeric')
    assert row['step_1based'] == '1' and row['i_1based'] == '1'


def test_genuine_trace_missing_last_post_is_rejected():
    acc = accumulator()
    before = [1.] * rp.FIELD_COUNTS[1]
    after = [2.] * rp.FIELD_COUNTS[2]
    after[16:21] = [3.] * 5
    add(acc, line(1, 1, 2, before))
    add(acc, line(2, 1, 2, after))
    add(acc, line(1, 2, 2, before))
    add(acc, line(5))
    add(acc, line(6))
    with pytest.raises(rp.TraceError, match='PRE/POST pair'):
        acc.finish()


def test_publish_rejects_existing_directory_and_preserves_source(tmp_path):
    source = tmp_path / 'staged'
    source.mkdir()
    (source / 'result').write_text('new')
    target = tmp_path / 'analysis'
    target.mkdir()
    (target / 'result').write_text('old')
    with pytest.raises(FileExistsError):
        rp._publish_new_directory(source, target)
    assert (target / 'result').read_text() == 'old'
    assert (source / 'result').read_text() == 'new'


def test_analysis_failure_cleans_staging(tmp_path, monkeypatch):
    import json
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'format': 'CP03_PAIR_INPUT_V1', 'case_id': 'fixture',
                                    'physics': 'FIX', 'time_step_seconds': 20, 'steps': 1,
                                    'arms': {'B1': {'root': '.', 'files': {}},
                                             'NR_PRIOR': {'root': '.', 'files': {}}}}))
    monkeypatch.setattr(rp, 'check_schema', lambda path: None)
    monkeypatch.setattr(rp, 'sha256', lambda path: rp.CORNERS_SHA256)
    monkeypatch.setattr(rp, 'read_corners', lambda path: ([], [], None))
    monkeypatch.setattr(rp, 'check_inventory', lambda root, files: {})
    def fail(*args, **kwargs):
        raise rp.TraceError('synthetic input failure')
    monkeypatch.setattr(rp, 'load_arm', fail)
    with pytest.raises(rp.TraceError, match='synthetic input failure'):
        rp.analyze(manifest, tmp_path / 'schema', tmp_path / 'corners', tmp_path / 'analysis', steps=1)
    assert not (tmp_path / 'analysis').exists()
    assert not list(tmp_path.glob('.analysis.*'))
