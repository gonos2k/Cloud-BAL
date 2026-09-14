#!/usr/bin/env python3
"""Discover compiler inputs, pin their bytes, then verify a fresh Intel build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / 'tools/build_upstream_producer.sh'
PINNER = REPO / 'tools/pin_compiler_inputs.py'
TRACER_SHA256 = '28f957c227012de0b18d1bd7fff2d396cb693ea60ed8013be68de071e84b5001'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path):
    return {'path': str(path), 'sha256': digest(path)}


def run_build(work, phase, args, manifest=None):
    phase_root = work / phase
    phase_root.mkdir()
    trace_dir = phase_root / 'trace'
    trace_dir.mkdir()
    env = os.environ.copy()
    env.pop('CLOUD_BAL_COMPILER_INPUTS_MANIFEST', None)
    env.update(TMPDIR=str(work / 'tmp'), PYTHONDONTWRITEBYTECODE='1',
               PYTHONPYCACHEPREFIX=str(work / 'empty_cache'))
    if manifest is not None:
        env['CLOUD_BAL_COMPILER_INPUTS_MANIFEST'] = str(manifest)
    command = [str(args.tracer), '-ff', '-yy', '-s', '4096', '-o',
               str(trace_dir / 'events'), '-e',
               'trace=execve,execveat,open,openat,openat2',
               '/bin/bash', str(BUILDER), args.producer, args.optimization]
    log = phase_root / 'build.log'
    with log.open('xb') as stream:
        result = subprocess.run(command, cwd=phase_root, env=env,
                                stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'{phase} build exited {result.returncode}; see {log}')
    build = Path(log.read_text().splitlines()[0])
    if not build.is_absolute() or build.resolve(strict=True) != build or \
            build.parent != REPO / 'scratch' or \
            not build.name.startswith(f'upstream_{args.producer}_build.'):
        raise RuntimeError(f'unexpected build directory: {build}')
    if 'BUILD_AND_LINK_PASS;' not in (build / 'build.log').read_text():
        raise RuntimeError(f'{phase} build completion marker is missing')
    return build, trace_dir, log


def pin_trace(trace_dir, generated_roots, manifest, receipt, tracer, verify=False):
    command = [sys.executable, str(PINNER), '--trace-dir', str(trace_dir),
               '--manifest', str(manifest), '--receipt', str(receipt),
               '--tracer', str(tracer)]
    for root in generated_roots:
        command += ['--build-root', str(root)]
    if verify:
        command.append('--verify')
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('producer', choices=('derived', 'balance', 'lapsprep'))
    parser.add_argument('optimization', choices=('O0', 'O2'))
    parser.add_argument('--tracer', type=Path, required=True)
    args = parser.parse_args()
    args.tracer = args.tracer.resolve(strict=True)
    if digest(args.tracer) != TRACER_SHA256:
        parser.error('tracer bytes do not match the reviewed tracing tool')
    work = Path(tempfile.mkdtemp(prefix='compiler_audited_build.', dir=REPO / 'scratch'))
    for name in ('tmp', 'empty_cache'):
        (work / name).mkdir()
    print(work, flush=True)
    sources = {str(p): digest(p) for p in (Path(__file__).resolve(), BUILDER, PINNER)}
    manifest = work / 'compiler_inputs.sha256'
    discovery, trace, discovery_log = run_build(work, 'discovery', args)
    pin_trace(trace, [work, discovery], manifest, work / 'discovery_receipt.json', args.tracer)
    final, trace, final_log = run_build(work, 'final', args, manifest)
    if final == discovery:
        raise RuntimeError('accepted build must have a fresh working directory')
    pin_trace(trace, [work, discovery, final], manifest, work / 'final_receipt.json', args.tracer, True)
    if (final / 'compiler_inputs.sha256').read_bytes() != manifest.read_bytes():
        raise RuntimeError('accepted build did not retain the precompile compiler pins')
    if any(digest(Path(path)) != value for path, value in sources.items()):
        raise RuntimeError('build audit sources changed during execution')
    receipt = {
        'status': 'PASS_COMPILER_INPUTS_PINNED_BEFORE_FRESH_BUILD',
        'producer': args.producer, 'optimization': args.optimization,
        'discovery_build': str(discovery), 'accepted_build': str(final),
        'sources': sources, 'tracer': record(args.tracer),
        'evidence': [record(p) for p in (manifest, work / 'discovery_receipt.json',
                     work / 'final_receipt.json', discovery_log, final_log,
                     final / 'inputs.sha256', final / 'executable.sha256')],
        'scope': 'Observed regular compiler/build inputs and executed tools; '
                 'owned generated files and kernel virtual state classified separately. '
                 'No producer execution, native acceptance or physical durability claim.',
    }
    (work / 'RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'accepted_build': str(final), 'receipt': str(work / 'RECEIPT.json')}))


if __name__ == '__main__':
    main()
