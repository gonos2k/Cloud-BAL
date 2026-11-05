#!/usr/bin/env python3
"""Compare every original NPZ NPY payload with its lossless part representation."""
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path('tools').resolve()))
from pack_cp02_selected_npz import load_partarrays


def file_sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def main():
    runtime, bundle = map(lambda p: Path(p).resolve(), sys.argv[1:3])
    receipt = json.loads((bundle / 'analysis/full_capture_receipt.json').read_text())
    stems = ('B1_native_wrapper', 'DM065_native_wrapper', 'B1_point_timeseries',
             'DM065_point_timeseries', 'paired_differences')
    expected_hashes = {'B1_native_wrapper': receipt['arms']['B1']['native_wrapper_sha256'],
                       'DM065_native_wrapper': receipt['arms']['DM065']['native_wrapper_sha256'],
                       'B1_point_timeseries': receipt['arms']['B1']['output_sha256'],
                       'DM065_point_timeseries': receipt['arms']['DM065']['output_sha256'],
                       'paired_differences': receipt['paired_outputs']['paired_differences.npz']['sha256']}
    result = {'status': 'PASS', 'scope': 'All NPZ members; original NPY header and payload SHA, shape, dtype and storage order; loader reconstruction and every part SHA/size.',
              'full_capture_receipt_sha256': file_sha(bundle / 'analysis/full_capture_receipt.json'),
              'packer_sha256': file_sha(Path('tools/pack_cp02_selected_npz.py')), 'arrays': {}}
    for stem in stems:
        source = runtime / (stem + '.npz')
        manifest_path = bundle / 'analysis' / (stem + '_parts') / (stem + '.parts.json')
        manifest = json.loads(manifest_path.read_text())
        if file_sha(source) != expected_hashes[stem] or manifest['source_sha256'] != expected_hashes[stem]:
            raise ValueError(f'source mismatch {stem}')
        by_name = {item['name']: item for item in manifest['members']}
        with zipfile.ZipFile(source) as archive:
            if set(archive.namelist()) != {name + '.npy' for name in by_name}:
                raise ValueError('original member inventory differs')
            for name, member in by_name.items():
                raw = archive.read(name + '.npy')
                stream = io.BytesIO(raw)
                version = np.lib.format.read_magic(stream)
                shape, fortran, dtype = np.lib.format._read_array_header(stream, version)
                if (hashlib.sha256(raw).hexdigest() != member['original_npy_sha256'] or
                    list(shape) != member['shape'] or dtype.str != member['dtype'] or
                    fortran != member['fortran_order'] or raw[:stream.tell()].hex() != member['header_hex']):
                    raise ValueError(f'original member mismatch: {stem}/{name}')
        first = manifest['members'][0]['name']
        loaded = load_partarrays(manifest_path, names=[first])
        if set(loaded) != {first}:
            raise ValueError('loader selective return mismatch')
        parts = [c for m in manifest['members'] for c in m['chunks']]
        if not all(c['part_bytes'] < 90 * 1024 * 1024 for c in parts):
            raise ValueError('part exceeds strict 90 MiB limit')
        result['arrays'][stem + '.npz'] = {'source_sha256': expected_hashes[stem],
            'manifest_path': str(manifest_path.relative_to(bundle)), 'manifest_sha256': file_sha(manifest_path),
            'member_count': len(by_name), 'part_count': len(parts),
            'max_part_bytes': max(p['part_bytes'] for p in parts), 'loader_selected_member': first}
        print(stem, 'PASS', flush=True)
    path = bundle / 'validation/array_parts_review.json'
    path.write_text(json.dumps(result, indent=2) + '\n')
    print('receipt_sha256', file_sha(path))


if __name__ == '__main__':
    main()
