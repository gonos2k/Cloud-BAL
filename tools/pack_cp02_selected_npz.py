#!/usr/bin/env python3
"""Losslessly split selected diagnostic NPZ members into deterministic NPZ parts."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import numpy as np

MAX_PART_BYTES = 90 * 1024 * 1024
CHUNK_BYTES = 80 * 1024 * 1024


class PackError(ValueError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_npy(raw):
    stream = io.BytesIO(raw)
    version = np.lib.format.read_magic(stream)
    shape, order, dtype = np.lib.format._read_array_header(stream, version)
    header = raw[:stream.tell()]
    if dtype.hasobject:
        raise PackError('object arrays are not supported')
    array = np.load(io.BytesIO(raw), allow_pickle=False)
    if array.shape != shape or array.dtype != dtype:
        raise PackError('NPY header mismatch')
    return array, header, order


def encode_npy(array):
    stream = io.BytesIO()
    np.save(stream, array, allow_pickle=False)
    return stream.getvalue()


def write_part(path, key, raw):
    info = zipfile.ZipInfo(key + '.npy', date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o600 << 16
    with zipfile.ZipFile(path, 'w', allowZip64=True, compresslevel=6) as archive:
        archive.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)


def pack(source, destination, max_bytes=MAX_PART_BYTES):
    """Create parts in a fresh destination; verify exact arrays before publishing."""
    source, destination = Path(source), Path(destination)
    if os.path.lexists(destination):
        raise PackError('destination already exists')
    if max_bytes <= 1024:
        raise PackError('part limit too small')
    source_hash = file_sha(source)
    temp = Path(tempfile.mkdtemp(prefix='.' + destination.name + '.', dir=destination.parent))
    try:
        members = []
        with zipfile.ZipFile(source) as original:
            infos = original.infolist()
            if not infos or len({x.filename for x in infos}) != len(infos):
                raise PackError('empty or duplicate NPZ member inventory')
            for info in sorted(infos, key=lambda value: value.filename):
                if not info.filename.endswith('.npy') or '/' in info.filename:
                    raise PackError('unexpected NPZ member name')
                key = info.filename[:-4]
                raw = original.read(info)
                array, header, fortran = read_npy(raw)
                chunks = []
                if info.compress_size + 512 < max_bytes:
                    slices = [(0, array.shape[0] if array.ndim else 1, raw)]
                else:
                    if not array.ndim or array.shape[0] == 0:
                        raise PackError(f'{key}: cannot split oversized scalar/empty array')
                    row_bytes = max(1, array.nbytes // array.shape[0])
                    target = min(CHUNK_BYTES, max_bytes - 1024)
                    rows = max(1, target // row_bytes)
                    slices = [(start, min(start + rows, array.shape[0]),
                               encode_npy(array[start:min(start + rows, array.shape[0])]))
                              for start in range(0, array.shape[0], rows)]
                for start, stop, chunk in slices:
                    name = f'{source.stem}.part{sum(len(m["chunks"]) for m in members) + len(chunks) + 1:03d}.npz'
                    path = temp / name
                    write_part(path, key, chunk)
                    if path.stat().st_size >= max_bytes:
                        raise PackError(f'{key}: individual leading-axis chunk exceeds part size limit')
                    chunks.append({'part': name, 'part_sha256': file_sha(path), 'part_bytes': path.stat().st_size,
                                   'start': start, 'stop': stop, 'npy_sha256': sha(chunk)})
                members.append({'name': key, 'dtype': array.dtype.str, 'shape': list(array.shape),
                                'fortran_order': fortran, 'header_hex': header.hex(),
                                'original_npy_sha256': sha(raw), 'chunks': chunks})
        manifest = {'format': 'CP02_SELECTED_PARTS_V1', 'source_name': source.name,
                    'source_sha256': source_hash, 'source_bytes': source.stat().st_size,
                    'max_part_bytes_exclusive': max_bytes, 'members': members}
        manifest_path = temp / (source.stem + '.parts.json')
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        load_partarrays(manifest_path, names=[])
        if file_sha(source) != source_hash:
            raise PackError('source changed while packing')
        os.rename(temp, destination)
        return destination / manifest_path.name
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def load_partarrays(manifest_path, names=None):
    """Verify all part inventories and NPY hashes; return requested logical arrays."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('format') != 'CP02_SELECTED_PARTS_V1':
        raise PackError('unsupported part manifest')
    members = manifest.get('members', [])
    keys = [item['name'] for item in members]
    if not keys or len(set(keys)) != len(keys):
        raise PackError('empty or duplicate logical member inventory')
    requested = set(keys if names is None else names)
    if requested - set(keys):
        raise PackError('requested logical member is absent')
    part_names = [chunk['part'] for item in members for chunk in item['chunks']]
    if len(set(part_names)) != len(part_names) or any(Path(n).name != n for n in part_names):
        raise PackError('duplicate or invalid part filename')
    expected_files = set(part_names) | {manifest_path.name}
    if {p.name for p in manifest_path.parent.iterdir()} != expected_files:
        raise PackError('part directory inventory mismatch')
    result = {}
    for item in members:
        key, pieces, next_start = item['name'], [], 0
        for chunk in item['chunks']:
            path = manifest_path.parent / chunk['part']
            if path.stat().st_size != chunk['part_bytes'] or file_sha(path) != chunk['part_sha256']:
                raise PackError(f'{path}: part size or SHA mismatch')
            with zipfile.ZipFile(path) as archive:
                if archive.namelist() != [key + '.npy']:
                    raise PackError(f'{path}: member inventory mismatch')
                raw = archive.read(key + '.npy')
            if sha(raw) != chunk['npy_sha256']:
                raise PackError(f'{path}: NPY SHA mismatch')
            array, _, _ = read_npy(raw)
            if chunk['start'] != next_start or chunk['stop'] < next_start:
                raise PackError(f'{key}: incomplete or overlapping chunk ranges')
            next_start = chunk['stop']
            pieces.append(array)
        shape = tuple(item['shape'])
        if not pieces or next_start != (shape[0] if shape else 1):
            raise PackError(f'{key}: incomplete chunks')
        array = pieces[0] if len(pieces) == 1 else np.concatenate(pieces, axis=0)
        if array.shape != shape or array.dtype.str != item['dtype']:
            raise PackError(f'{key}: reconstructed dtype/shape mismatch')
        payload = array.tobytes(order='F' if item['fortran_order'] else 'C')
        if sha(bytes.fromhex(item['header_hex']) + payload) != item['original_npy_sha256']:
            raise PackError(f'{key}: reconstructed original NPY bytes differ')
        if key in requested:
            result[key] = array
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(pack(args.source, args.destination))


if __name__ == '__main__':
    main()
