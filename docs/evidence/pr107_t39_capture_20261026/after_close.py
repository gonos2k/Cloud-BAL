#!/usr/bin/env python3
"""Run the two bounded diagnostics once the single HYDRO capture receipt closes."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve().parent
    receipt = args.run_root / 'receipt.json'
    deadline = time.monotonic() + 24 * 3600
    closed = None
    while time.monotonic() < deadline:
        try:
            candidate = json.loads(receipt.read_text())
            if candidate.get('status') in ('COMPLETE', 'INCOMPLETE') and isinstance(candidate.get('returncode'), int):
                closed = candidate
                break
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(30)
    result = {'schema': 'pr107_postclosure_dispatch_v1', 'model_restarted': False,
              'closed_receipt': str(receipt), 'jobs': []}
    if closed is None:
        result['status'] = 'WAIT_EXPIRED_NO_CLOSED_RECEIPT'
    else:
        result['closed_receipt_sha256'] = hashlib.sha256(receipt.read_bytes()).hexdigest()
        run = args.run_root / 'run'
        jobs = [
            ('t39_join', [sys.executable, str(here / 'postprocess_t39.py'),
             '--closed-receipt', str(receipt),
             '--group-raw', str(run / 'pr99_group_failure.raw.gz'),
             '--producer-raw', str(run / 'pr92_diffusion_producer.raw.gz'),
             '--consumer-raw', str(run / 'pr92_graupel_source_capture.raw.gz')]),
            ('prefix', [sys.executable, str(here / 'compare_prefix.py'),
             '--old-hydro', '/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr104_validtime_forecast_20261026/HYDRO',
             '--diagnostic-hydro', str(args.run_root)]),
        ]
        for name, command in jobs:
            output = args.output / (name + '.json')
            command += ['--output', str(output)]
            with (args.output / (name + '.log')).open('xb') as log:
                run_result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
            result['jobs'].append({'name': name, 'command': command,
                                   'returncode': run_result.returncode,
                                   'output': str(output),
                                   'sha256': hashlib.sha256(output.read_bytes()).hexdigest() if output.is_file() else None})
        result['status'] = ('POSTPROCESS_COMPLETE' if all(row['returncode'] == 0 for row in result['jobs'])
                            else 'POSTPROCESS_FAILED_REVIEW_LOGS')
    result['utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (args.output / 'dispatch_receipt.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
