#!/usr/bin/env python3
"""Prepare fresh 80-second cases for native numerator capture; never launches WRF."""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
RUNTIME = ROOT.parent / 'runtime' / 'native_build' / 'operation_capture'
B1 = Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED')
DM = ROOT.parent.parent.parent / 'scratch/b1_rain_number_process_20261104/runtime/next_candidate/full'
VARIANT_ROOT = ROOT.parent / 'runtime/native_build/variants'
ARMS = {'B1': B1, 'DM065': DM}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_inventory(arm):
    source = ARMS[arm]
    receipt_name = 'receipt.json' if arm == 'B1' else 'case_receipt.json'
    receipt = json.loads((source / receipt_name).read_text())
    hashes = receipt['staged_sha256_after'] if arm == 'B1' else receipt['inputs']
    if len(hashes) != 89 or any(sha(source / name) != digest for name, digest in hashes.items()):
        raise ValueError(f'{arm}: source input inventory changed')
    expected_wrfinput = {
        'B1': '9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5',
        'DM065': 'e6ed0750f88cb36e2600fd38c05e75513e8267dca72d9ee095cd5340a24ed175',
    }[arm]
    if sha(source / 'wrfinput_d01') != expected_wrfinput:
        raise ValueError(f'{arm}: wrfinput hash differs')
    return source, hashes, expected_wrfinput


def set_control(text, key, value):
    text, count = re.subn(r'(?m)^(\s*' + re.escape(key) + r'\s*=\s*)[^,\n]+',
                          lambda match: match.group(1) + value, text)
    if count != 1:
        raise ValueError(f'namelist must contain one {key} control, found {count}')
    return text


def prepare(variant, arm, attempt):
    if variant not in ('OLD_SHAM_RETRY1', 'GROUPED') or arm not in ARMS:
        raise ValueError('unknown native variant or input arm')
    source, source_hashes, wrfinput_sha = source_inventory(arm)
    executable = VARIANT_ROOT / variant / 'wrf.exe'
    exe_sha = sha(executable)
    expected_exe = {
        'OLD_SHAM_RETRY1': 'a18b5bcacf287531b5fb9366be0ff0e2fd13911c4f44b0a739ab9e565f678308',
        'GROUPED': '4c01fd93a117a82789f564fd8557d9cab3e85ace23a400acfb84384e48eaf60f',
    }[variant]
    if exe_sha != expected_exe:
        raise ValueError(f'{variant}: executable hash differs')
    dest = RUNTIME / attempt / f'{variant}_{arm}'
    dest.mkdir(parents=True, exist_ok=False)
    for name in source_hashes:
        shutil.copy2(source / name, dest / name)
    shutil.copy2(executable, dest / 'wrf.exe')
    path = dest / 'namelist.input'
    original_namelist_sha = sha(path)
    text = path.read_text()
    for key, value in [('run_hours', '0'), ('run_minutes', '1'), ('run_seconds', '20'),
                       ('end_hour', '12'), ('end_minute', '1'), ('end_second', '20'),
                       ('history_end_s', '80')]:
        text = set_control(text, key, value)
    path.write_text(text)
    if not re.search(r'(?m)^\s*time_step\s*=\s*20\s*,?\s*$', text):
        raise ValueError('time_step does not remain 20 seconds')
    copied_before = {name: sha(dest / name) for name in source_hashes}
    expected_modified = {'namelist.input', 'wrf.exe'}
    if any(name not in expected_modified and copied_before[name] != digest
           for name, digest in source_hashes.items()):
        raise ValueError('a copied source input differs before launch')
    receipt = {
        'schema': 'cp02_grouped_operation_case_receipt_v1',
        'status': 'PREPARED_NOT_RUN',
        'variant': variant,
        'arm': arm,
        'attempt': attempt,
        'source_root': str(source),
        'source_input_count': len(source_hashes),
        'source_inputs_sha256': source_hashes,
        'source_wrfinput_sha256': wrfinput_sha,
        'source_executable': str(executable),
        'source_executable_sha256': exe_sha,
        'case_executable_sha256': sha(dest / 'wrf.exe'),
        'source_namelist_sha256': original_namelist_sha,
        'namelist_sha256': sha(path),
        'horizon_controls': {'run_hours': 0, 'run_minutes': 1, 'run_seconds': 20,
                             'end_hour': 12, 'end_minute': 1, 'end_second': 20,
                             'history_end_s': 80, 'time_step': 20},
        'case_inputs_before': copied_before,
        'case_directory': str(dest),
    }
    receipt_path = dest / 'case_receipt.json'
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'case': str(dest), 'receipt_sha256': sha(receipt_path),
                      'executable_sha256': exe_sha, 'source_input_count': len(source_hashes)},
                     sort_keys=True))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('usage: prepare_operation_cases.py VARIANT ARM ATTEMPT')
    prepare(*sys.argv[1:])
