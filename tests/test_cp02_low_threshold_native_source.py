"""Check paired process diagnostics retain physical source and native flux kinds."""
import difflib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'docs/evidence/cp02_low_threshold_process_20261110/native'
spec = importlib.util.spec_from_file_location('low_trace', NATIVE / 'source/instrument.py')
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


def test_three_generated_sources_preserve_physics_and_flux_semantics():
    schema = json.loads((NATIVE / 'schema/schema.json').read_text())
    for arm, (parent, digest) in trace.PARENTS.items():
        assert trace.sha(parent) == digest
        original = parent.read_text().splitlines(keepends=True)
        observed = (NATIVE / f'source/module_mp_kdm6_{arm}.f90').read_text().splitlines(keepends=True)
        assert all(op[0] in ('equal', 'insert') for op in difflib.SequenceMatcher(None, original, observed, autojunk=False).get_opcodes())
        source = ''.join(observed)
        assert source.count('process_unit,20,i,k') == (2 if arm == 'FIX' else 1)
        assert source.count('process_unit,21,i,k') == (2 if arm == 'FIX' else 1)
        assert ('process_unit,23,i,k' in source) == (arm == 'FIX')
        assert ('process_unit,22,i,k' in source) == (arm != 'FIX')
        if arm != 'FIX':
            post = source.split('process_unit,10,i,k', 1)[1].split('/))', 1)[0]
            assert 'falk' not in post
    assert schema['phases']['18']['payload_kind'] == 'IEEE REAL64'
    assert schema['phases']['22']['payload_kind'] == 'IEEE REAL64'
    assert schema['phase_window_steps'] == [1, 180, 721, 1080]


def test_frame_decoder_preserves_real64_and_rejects_truncation(tmp_path):
    import struct
    import numpy as np
    import pytest
    path = NATIVE / 'runs/read_frames.py'
    reader_spec = importlib.util.spec_from_file_location('low_reader', path)
    reader = importlib.util.module_from_spec(reader_spec)
    reader_spec.loader.exec_module(reader)
    sample = tmp_path / 'frame.bin'
    values = (1.0000000000000002, 1e-200)
    frame = (b'C4FR0001' + struct.pack('>8i', 0,1,1,1,1,1,1,39) +
             struct.pack('>10f', *([1.0] * 10)) + struct.pack('>8i', 18,1,1,1,1,1,1,2) +
             struct.pack('>2d', *values) + struct.pack('>i', -1))
    sample.write_bytes(frame)
    rows = list(reader.frames(sample, {18:2}))
    assert rows[0][1][0][-1].dtype.itemsize == 8
    assert tuple(rows[0][1][0][-1]) == values
    for broken in (frame[:-1], frame[:-4], frame[:20]):
        sample.write_bytes(broken)
        with pytest.raises(ValueError): list(reader.frames(sample, {18:2}))
    sample.write_bytes(frame)
    with pytest.raises(ValueError): list(reader.frames(sample, {18:3}))
