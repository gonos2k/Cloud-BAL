#!/usr/bin/env python3
"""Persist a frozen, bounded collector job across agent conversation turns."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


p = argparse.ArgumentParser()
p.add_argument('--plan', type=Path, required=True)
p.add_argument('--arm', choices=('OLD', 'FIX'), required=True)
a = p.parse_args()
plan = json.loads(a.plan.read_text())
job = plan['arms'][a.arm]
tool = Path(plan['tool'])
receipt = Path(plan['full_launch_receipt'])
if sha(tool) != plan['tool_sha256'] or sha(receipt) != plan['full_launch_receipt_sha256']:
    raise SystemExit('frozen source/run receipt mismatch')
env = os.environ.copy()
for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    env[name] = '1'
env['PYTHONDONTWRITEBYTECODE'] = '1'
env['TMPDIR'] = job['tmpdir']
Path(env['TMPDIR']).mkdir(parents=True, exist_ok=True)
started = time.monotonic()
result = subprocess.run(job['argv'], cwd=plan['worktree'], env=env, check=False)
output_receipt = Path(job['output']) / 'capture_receipt.json'
unchanged = sha(tool) == plan['tool_sha256'] and sha(receipt) == plan['full_launch_receipt_sha256']
record = {'arm': a.arm, 'exit_code': result.returncode, 'elapsed_seconds': time.monotonic() - started,
          'source_inputs_unchanged': unchanged, 'plan_sha256': sha(a.plan),
          'driver_sha256': sha(Path(__file__)), 'tool_sha256': sha(tool), 'argv': job['argv'],
          'output_receipt_sha256': sha(output_receipt) if output_receipt.is_file() else None,
          'status': 'COMPLETED' if result.returncode == 0 and unchanged and output_receipt.is_file() else 'FAIL'}
with (a.plan.parent / f'{a.arm}_exit.json').open('x') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
raise SystemExit(0 if record['status'] == 'COMPLETED' else 1)
