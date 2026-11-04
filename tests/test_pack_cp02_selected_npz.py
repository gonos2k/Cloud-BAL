import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location('parts', Path(__file__).resolve().parents[1] / 'tools/pack_cp02_selected_npz.py')
parts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parts)


def test_round_trip_chunks_and_deterministic_bytes(tmp_path):
    rng = np.random.default_rng(19)
    data = np.asfortranarray(rng.integers(0, 2**31, size=(100, 50), dtype=np.int32))
    data[0, 0] = -1
    source = tmp_path / 'selected.npz'
    np.savez_compressed(source, data=data, scalar=np.float32(-0.))
    one = parts.pack(source, tmp_path / 'one', max_bytes=5000)
    two = parts.pack(source, tmp_path / 'two', max_bytes=5000)
    decoded = parts.load_partarrays(one)
    assert np.array_equal(decoded['data'], data)
    assert decoded['data'].dtype == data.dtype
    assert decoded['data'].shape == data.shape
    assert np.signbit(decoded['scalar'])
    assert one.read_bytes() == two.read_bytes()
    for path in one.parent.glob('*.npz'):
        assert path.stat().st_size < 5000
        assert path.read_bytes() == (two.parent / path.name).read_bytes()
    assert parts.load_partarrays(one, names=['scalar']).keys() == {'scalar'}


def test_corrupt_part_and_extra_inventory_are_rejected(tmp_path):
    source = tmp_path / 'selected.npz'
    np.savez_compressed(source, a=np.arange(200, dtype=np.float32))
    manifest = parts.pack(source, tmp_path / 'parts')
    part = next(manifest.parent.glob('*.npz'))
    original = part.read_bytes()
    part.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    with pytest.raises(parts.PackError, match='SHA'):
        parts.load_partarrays(manifest)
    part.write_bytes(original)
    (manifest.parent / 'unexpected').write_text('x')
    with pytest.raises(parts.PackError, match='inventory'):
        parts.load_partarrays(manifest)


def test_existing_output_rejected_without_touching_source(tmp_path):
    source = tmp_path / 'selected.npz'
    np.savez_compressed(source, a=np.array([1.]))
    target = tmp_path / 'parts'
    target.mkdir()
    with pytest.raises(parts.PackError, match='already exists'):
        parts.pack(source, target)
    assert source.exists()
