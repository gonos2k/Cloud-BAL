#!/usr/bin/env python3
"""Replay the retained actual fixed-mask stream; output is diagnostic only."""
import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identities(paths):
    return {name: {'path': str(path), 'sha256': sha(path)} for name, path in paths.items()}


def unpack_stream(compressed, output, export):
    with gzip.open(compressed, 'rb') as source, output.open('xb') as target:
        shutil.copyfileobj(source, target, 1024 * 1024)
    if sha(output) != export['uncompressed_sha256'] or output.stat().st_size != export['uncompressed_size_bytes']:
        raise ValueError('stream integrity mismatch')
    with output.open('rb') as stream:
        dims = np.fromfile(stream, dtype=np.int32, count=3)
        if dims.size != 3 or np.any(dims <= 0) or dims[2] < 2:
            raise ValueError('invalid stream dimensions')
        count = int(np.prod(dims, dtype=np.int64))
        # Header, six float32 fields, mask, and 19 REAL64 policy values.
        if output.stat().st_size != 340 + 7 * count * 4 + 19 * 8:
            raise ValueError('stream length does not match dimensions')
        stream.seek(340 + 6 * count * 4)
        raw_mask = np.fromfile(stream, dtype=np.int32, count=count)
        if raw_mask.size != count or not np.isin(raw_mask, (0, 1)).all():
            raise ValueError('invalid stream selection mask')
    return tuple(dims[::-1]), raw_mask.reshape(tuple(dims[::-1])).astype(bool)


def build_and_run(root, coverage, work):
    script = '''set -euo pipefail
source "$1/tests/intel_toolchain.sh"
"$CLOUD_BAL_FC" --version > compiler_version.txt
printf '%q ' "$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" > compiler_flags.txt
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" -c "$1/src/common/cloud_bal_state.f90" "$1/src/common/cloud_bal_microphysics_initialization.f90"
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" cloud_bal_state.o cloud_bal_microphysics_initialization.o "$2/cell_driver.f90" -o cell_driver
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" cloud_bal_state.o cloud_bal_microphysics_initialization.o "$1/tools/ice_background_driver.f90" -o bulk_driver
./bulk_driver fixed.bin bulk.bin
./cell_driver fixed.bin cell.bin
'''
    with (work / 'execution.log').open('x') as log:
        subprocess.run(['bash', '-c', script, 'replay', str(root), str(coverage)],
                       cwd=work, stdout=log, stderr=subprocess.STDOUT, check=True)


def compare_results(work, paths, shape, mask):
    bulk = work / 'bulk.bin'
    if bulk.read_bytes() != paths['expected_bulk'].read_bytes():
        raise ValueError('bulk stream differs')
    header = np.fromfile(bulk, dtype=np.int32)
    if header.tolist() != [-10, 150, 228, 11, 2]:
        raise ValueError('unexpected full transaction result')
    count = int(np.prod(shape, dtype=np.int64))
    output = work / 'cell.bin'
    if output.stat().st_size != 4 * count * 4:
        raise ValueError('cell output length mismatch')
    with output.open('rb') as stream:
        status = np.fromfile(stream, dtype=np.int32, count=count).reshape(shape)
        values = np.fromfile(stream, dtype=np.float32, count=3 * count).reshape((3, *shape))
    with np.load(paths['expected_diagnostic'], allow_pickle=False) as reference:
        if not np.array_equal(status, reference['status']) or not np.array_equal(mask, reference['selected_fixed_mask']):
            raise ValueError('status or fixed mask mismatch')
        passed = mask & (status == 20)
        for index, name in enumerate(('diagnostic_success_qi', 'diagnostic_success_qs', 'diagnostic_success_ni')):
            actual_bits = values[index][passed].view(np.uint32)
            expected_bits = reference[name][passed].view(np.uint32)
            if not np.array_equal(actual_bits, expected_bits):
                raise ValueError(name + ' bits differ')
    return header.tolist(), passed, status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--work-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    work = args.work_root.resolve()
    coverage = root / 'docs/evidence/prior_cycle_application_20261112/coverage'
    if work == root or root in work.parents:
        raise ValueError('work directory must be outside source checkout')
    work.mkdir(parents=True, exist_ok=False)
    paths = {
        'state': root / 'src/common/cloud_bal_state.f90',
        'common': root / 'src/common/cloud_bal_microphysics_initialization.f90',
        'bulk_adapter': root / 'tools/ice_background_driver.f90',
        'cell_adapter': coverage / 'cell_driver.f90',
        'toolchain': root / 'tests/intel_toolchain.sh',
        'stream_gzip': coverage / 'fixed.bin.gz',
        'expected_bulk': coverage / 'bulk.bin',
        'expected_diagnostic': coverage / 'diagnostic_only.npz',
        'export_receipt': coverage / 'export_receipt.json',
        'build_receipt': coverage / 'build_receipt.json',
        'replay': Path(__file__).resolve(),
    }
    before = identities(paths)
    original = json.loads(paths['build_receipt'].read_text())
    for name in ('state', 'common', 'bulk_adapter', 'cell_adapter'):
        if before[name]['sha256'] != original['artifacts'][name]['sha256']:
            raise ValueError('source differs from actual build: ' + name)
    export = json.loads(paths['export_receipt'].read_text())
    stream = work / 'fixed.bin'
    shape, mask = unpack_stream(paths['stream_gzip'], stream, export)
    build_and_run(root, coverage, work)
    header, passed, status = compare_results(work, paths, shape, mask)
    after = identities(paths)
    if before != after:
        raise ValueError('source changed during replay')
    result = {
        'replay_status': 'PASS', 'application_status': 'REJECTED',
        'selected': int(mask.sum()), 'pass': int(passed.sum()),
        'reject': int((mask & (status != 20)).sum()), 'bulk_header': header,
        'all_cell_status_and_success_arrays_match_bits': True,
        'full_bulk_bytes_match': True, 'inputs_unchanged': True,
        'identities_before': before, 'identities_after': after,
        'stream_sha256': sha(stream), 'stream_size': stream.stat().st_size,
        'execution_log_sha256': sha(work / 'execution.log'),
        'compiler_version': (work / 'compiler_version.txt').read_text(),
        'compiler_flags': (work / 'compiler_flags.txt').read_text(),
        'bulk_exe_sha256': sha(work / 'bulk_driver'),
        'cell_exe_sha256': sha(work / 'cell_driver'),
    }
    (work / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
