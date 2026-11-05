#!/usr/bin/env python3
"""Publish losslessly staged capture only after an exact full-analysis gate."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    stage, analysis, target = map(lambda x: Path(x).resolve(), sys.argv[1:4])
    if os.path.lexists(target):
        raise FileExistsError(target)
    staged = json.loads((stage / 'staging_receipt.json').read_text())
    manifest = json.loads((analysis / 'input_manifest.json').read_text())
    receipt = json.loads((analysis / 'receipt.json').read_text())
    if (staged['status'] != 'STAGED_NOT_PUBLISHED' or receipt['status'] != 'PASS_FULL_CAPTURE'
            or receipt['manifest_sha256'] != sha(analysis / 'input_manifest.json')
            or receipt['steps'] != 360 or receipt['levels'] != 39 or receipt['unique_native_cells'] != 123):
        raise ValueError('invalid full-capture gate')
    expected = {item['path']: (item['sha256'], item['size_bytes'])
                for items in manifest['arms'].values() for item in items
                if Path(item['path']).name != 'launch_receipt.json'}
    actual = {item['source']: (item['source_sha256'], item['source_bytes']) for item in staged['streams']}
    if len(actual) != len(staged['streams']) or actual != expected:
        raise ValueError('staged streams differ from analyzed input inventory')
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.capture-', dir=target.parent))
    try:
        for item in staged['streams']:
            source = Path(item['source'])
            arm = source.parent.name
            if arm not in ('B1', 'DM065') or sha(source) != item['source_sha256']:
                raise ValueError(f'source identity changed: {source}')
            for part in item['parts']:
                src = stage / arm / source.name / part['name']
                if src.stat().st_size != part['bytes'] or sha(src) != part['sha256']:
                    raise ValueError(f'staged part changed: {src}')
                dest = temp / arm / source.name / part['name']
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
                if sha(dest) != part['sha256']:
                    raise ValueError(f'published part readback failed: {dest}')
        publication = {'status': 'PASS_PUBLISHED', 'analysis_receipt_sha256': sha(analysis / 'receipt.json'),
                       'analysis_manifest_sha256': sha(analysis / 'input_manifest.json'),
                       'staging_receipt_sha256': sha(stage / 'staging_receipt.json'),
                       'stream_count': len(actual), 'compressed_bytes': staged['compressed_bytes'],
                       'max_chunk_bytes': staged['chunk_limit_bytes'], 'streams': staged['streams'],
                       'full_global_streams': 'External hash-only inventory; not part of this selected-stream capture.'}
        (temp / 'publication_receipt.json').write_text(json.dumps(publication, indent=2) + '\n')
        if os.path.lexists(target):
            raise FileExistsError(target)
        os.rename(temp, target)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    print(json.dumps({'status': publication['status'], 'streams': publication['stream_count'],
                      'compressed_bytes': publication['compressed_bytes']}))


if __name__ == '__main__':
    main()
