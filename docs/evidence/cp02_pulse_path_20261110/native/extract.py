#!/usr/bin/env python3
"""Extract exact CP04 records for selected native cells and calls; verify inventory."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import struct

OLD = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_low_threshold_process_20261110')
PRIOR = OLD / 'Cloud-BAL/docs/evidence/cp02_low_threshold_process_20261110/native'
OUT = Path(__file__).resolve().parent
ARMS = ('FIX', 'CONSERVATIVE', 'ICE_FIXED')
CELLS = {(i, j) for i in (147, 148, 149) for j in (134, 135)} | {(i, j) for i in (148, 149) for j in (125, 126)}
STEPS = {831, 839} | set(range(844, 863))


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def verify_inventory(arm):
    folder = OLD / 'runtime/forecasts' / arm
    entries = json.loads((PRIOR / 'compact' / arm / 'raw_inventory.json').read_text())
    for entry in entries:
        f = folder / entry['name']
        if not f.is_file() or f.stat().st_size != entry['size_bytes'] or sha(f) != entry['sha256']:
            raise ValueError(f'inventory mismatch: {f}')
    return {'files': len(entries), 'bytes': sum(e['size_bytes'] for e in entries),
            'inventory_sha256': sha(PRIOR / 'compact' / arm / 'raw_inventory.json')}


def exact(f, n):
    b = f.read(n)
    if len(b) != n:
        raise ValueError('truncated frame')
    return b


def extract_arm(arm):
    schema = json.loads((PRIOR / 'schema/schema.json').read_text())
    counts = {int(k): len(v['fields']) for k, v in schema['phases'].items()}
    override = schema['arm_overrides']['FIX' if arm == 'FIX' else 'CONSERVATIVE and ICE_FIXED']
    for phase in override['absent_phases']:
        del counts[phase]
    if arm != 'FIX':
        counts[10] = len(override['phase_10_fields'])
    folder = OLD / 'runtime/forecasts' / arm
    output = OUT / f'{arm}_selected.bin.gz'
    sources, seen, covered, records = {}, set(), set(), 0
    inventory = {e['name']: e for e in json.loads((PRIOR / 'compact' / arm / 'raw_inventory.json').read_text())}
    with output.open('xb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as dst:
        for path in sorted(folder.glob('cp04_t*.bin')):
            match = re.fullmatch(r'cp04_t(\d+)-(\d+)_rank\d+\.bin', path.name)
            if not match or not any(int(match[1]) <= s <= int(match[2]) for s in STEPS):
                continue
            sources[path.name] = sha(path)
            if path.name not in inventory or sources[path.name] != inventory[path.name]['sha256']:
                raise ValueError('selected source is not inventory-bound')
            with path.open('rb') as f:
                while magic := f.read(8):
                    if magic != b'C4FR0001':
                        raise ValueError('frame magic')
                    head = exact(f, 72)
                    rank, call, step, j, its, ite, kts, kte = struct.unpack('>8i', head[:32])
                    selected = []
                    while True:
                        raw_phase = exact(f, 4)
                        phase = struct.unpack('>i', raw_phase)[0]
                        if phase == -1:
                            break
                        raw_key = exact(f, 28)
                        i, k, loop, loops, sub, mstep, n = struct.unpack('>7i', raw_key)
                        if phase not in counts or n != counts[phase]:
                            raise ValueError('phase schema mismatch')
                        payload = exact(f, n * (8 if phase in (18, 22) else 4))
                        if step in STEPS and (i, j) in CELLS:
                            selected.append(raw_phase + raw_key + payload)
                            covered.add((step, i, j))
                    if selected:
                        key = (rank, call, step, j)
                        if key in seen:
                            raise ValueError('duplicate frame')
                        seen.add(key)
                        dst.write(magic + head + b''.join(selected) + struct.pack('>i', -1))
                        records += len(selected)
    if covered != {(step, i, j) for step in STEPS for i, j in CELLS}:
        raise ValueError('missing selected step/cell coverage')
    return {'sources': sources, 'frames': len(seen), 'records': records,
            'output': output.name, 'output_sha256': sha(output)}


def main():
    before = {arm: verify_inventory(arm) for arm in ARMS}
    result = {arm: extract_arm(arm) for arm in ARMS}
    after = {arm: verify_inventory(arm) for arm in ARMS}
    if before != after:
        raise ValueError('inventory changed')
    pins = [PRIOR / 'schema/schema.json', PRIOR / 'runs/read_frames.py', PRIOR / 'source/columns.csv']
    pins += [PRIOR / 'source' / f'module_mp_kdm6_{arm}.f90' for arm in ARMS]
    receipt = {'status': 'PASS', 'steps': sorted(STEPS), 'cells_i_j': sorted(CELLS),
               'inventory_verified_before_after': before, 'source_pins': {str(p): sha(p) for p in pins},
               'extractor_sha256': sha(Path(__file__)), 'arms': result}
    (OUT / 'extract_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
