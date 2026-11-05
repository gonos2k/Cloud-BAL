#!/usr/bin/env python3
"""Losslessly stage closed selected diagnostic streams in sub-90-MiB parts."""
import concurrent.futures
import hashlib
import json
import subprocess
import sys
from pathlib import Path

CHUNK = 85 * 1024 * 1024


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def stage(source, destination):
    destination.mkdir(parents=True, exist_ok=False)
    before = digest(source)
    producer = subprocess.Popen(['gzip', '-n', '-c', str(source)], stdout=subprocess.PIPE)
    splitter = subprocess.run(['split', '-b', str(CHUNK), '-d', '-a', '4', '-', str(destination / 'part_')], stdin=producer.stdout, check=False)
    producer.stdout.close()
    if producer.wait() or splitter.returncode:
        raise RuntimeError(f'compression failed: {source}')
    parts = sorted(destination.glob('part_*'))
    if not parts or any(p.stat().st_size > CHUNK for p in parts):
        raise RuntimeError(f'invalid parts: {source}')
    concatenate = subprocess.Popen(['cat', *map(str, parts)], stdout=subprocess.PIPE)
    decompressor = subprocess.Popen(['gzip', '-dc'], stdin=concatenate.stdout, stdout=subprocess.PIPE)
    concatenate.stdout.close()
    observed = hashlib.sha256()
    for block in iter(lambda: decompressor.stdout.read(1024 * 1024), b''):
        observed.update(block)
    decompressor.stdout.close()
    if decompressor.wait() or concatenate.wait() or observed.hexdigest() != before or digest(source) != before:
        raise RuntimeError(f'lossless readback failed: {source}')
    return {'source': str(source), 'source_sha256': before, 'source_bytes': source.stat().st_size,
            'parts': [{'name': p.name, 'sha256': digest(p), 'bytes': p.stat().st_size} for p in parts],
            'decompressed_sha256': observed.hexdigest()}


def main():
    runtime = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    patterns = ('state_calls_rank*.txt', 'state_selected_entry_rank*.bin', 'state_selected_return_rank*.bin',
                'cp04_rank*.bin', 'surface_cp04_rank*.bin')
    jobs = []
    for arm in ('B1', 'DM065'):
        source = runtime / 'full' / arm
        receipt = json.loads((source / 'launch_receipt.json').read_text())
        if receipt['status'] != 'PASS' or not receipt['history_byte_parity']:
            raise RuntimeError(f'forecast gate failed: {arm}')
        for pattern in patterns:
            paths = sorted(source.glob(pattern))
            if not paths:
                raise RuntimeError(f'missing {arm} {pattern}')
            jobs.extend((p, output / arm / p.name) for p in paths)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda pair: stage(*pair), jobs))
    receipt = {'status': 'STAGED_NOT_PUBLISHED', 'chunk_limit_bytes': CHUNK,
               'streams': records, 'compressed_bytes': sum(p['bytes'] for r in records for p in r['parts'])}
    (output / 'staging_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'streams': len(records), 'compressed_bytes': receipt['compressed_bytes']}))


if __name__ == '__main__':
    main()
