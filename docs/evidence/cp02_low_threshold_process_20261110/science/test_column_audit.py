"""Tests for pairing, missing surface records and REAL32 source carriers."""
import numpy as np
import pytest
import column_audit as audit


def records(surface=True):
    result = []
    for k in range(1, 40):
        pre = np.zeros(22, dtype=np.float32)
        pre[5:8] = 2
        pre[10:13] = (1, 2, 1)
        post = pre.copy()
        if k == 1:
            post[5] = 1
        result.extend([(9, 4, k, 1, 1, 1, 1, pre), (10, 4, k, 1, 1, 1, 1, post)])
    if surface:
        v = np.zeros(12, dtype=np.float32)
        v[:5] = (1, 0, 0, 0, 1)
        v[7:10] = (2, 1000, 1)
        result.extend([(13, 4, 1, 1, 1, 0, 0, v), (14, 4, 1, 1, 1, 0, 0, v.copy())])
    return result


def test_complete_and_unavailable():
    header = (0, 4, 1, 7, 1, 10, 1, 39)
    row = audit.audit_frame('CONSERVATIVE', header, records())[0]
    assert row['state_complete'] == row['surface_complete'] == 1
    assert row['state_change_kg_m2'] == -2
    assert row['executed_export_kg_m2'] == 2
    assert row['residual_kg_m2'] == 0
    row = audit.audit_frame('CONSERVATIVE', header, records(False))[0]
    assert row['surface_complete'] == 0
    assert row['executed_export_kg_m2'] == row['residual_kg_m2'] == ''


def test_incomplete_pairs_and_duplicate():
    header = (0, 4, 1, 7, 1, 10, 1, 39)
    data = records()
    missing = [r for r in data if not (r[0] == 10 and r[2] == 39)]
    row = audit.audit_frame('CONSERVATIVE', header, missing)[0]
    assert row['state_complete'] == 0
    assert row['state_change_kg_m2'] == row['residual_kg_m2'] == ''
    with pytest.raises(ValueError, match='duplicate'):
        audit.audit_frame('CONSERVATIVE', header, data + [data[0]])


def test_guard_existing_destination_and_unapproved_full(tmp_path):
    existing = tmp_path / 'existing'
    existing.mkdir()
    with pytest.raises(FileExistsError):
        audit.run('FIX', tmp_path, existing, 'probe')
    proof = tmp_path / 'bad_proof.json'
    proof.write_text('{"status":"PENDING"}')
    with pytest.raises(ValueError, match='requires PASS'):
        audit.run('FIX', tmp_path, tmp_path / 'new', 'full', proof)
    assert not (tmp_path / 'new').exists()


def test_spans_use_last_actual_substep_and_match_fields():
    def rec(phase, sub, mstep, values):
        return (phase, 4, 2, 1, 1, sub, mstep, np.array(values, dtype=np.float32))
    warm = np.arange(22, dtype=np.float32)
    ice = np.arange(10, dtype=np.float32) + 10
    core = np.arange(18, dtype=np.float32) + 20
    post = np.arange(16, dtype=np.float32) + 30
    cond = np.arange(13, dtype=np.float32) + 40
    entries = [rec(10, 1, 2, warm + 100), rec(10, 2, 2, warm), rec(21, 1, 1, ice),
               rec(6, 0, 0, core), rec(8, 0, 0, post), rec(11, 0, 0, cond)]
    vals = {field: value for _, _, field, value in audit.span_frame(entries)}
    assert len(vals) == 11
    assert vals[0] == core[4] - warm[3]
    assert vals[3] == core[8] - warm[7]
    assert vals[4] == core[1] - ice[1]
    assert vals[6] == core[5] - ice[3]
    assert vals[10] == cond[5] - post[5]
    assert len(audit.span_frame(entries[:-1])) == 7
