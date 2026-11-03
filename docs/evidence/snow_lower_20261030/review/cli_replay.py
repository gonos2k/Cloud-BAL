#!/usr/bin/env python3
"""Run the scorer CLI into scratch and verify byte-identical artifacts."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/cp02_snow_lower.py'
PRIMARY = BUNDLE / 'analysis'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replay():
    with tempfile.TemporaryDirectory(prefix='snow-lower-cli-replay-') as temp:
        output = Path(temp) / 'analysis'
        command = [sys.executable, str(TOOL), '--output', str(output)]
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        record = {
            'status': 'PASS_BYTE_IDENTICAL' if run.returncode == 0 else 'FAIL',
            'returncode': run.returncode,
            'command': command,
            'stdout': run.stdout,
            'stderr': run.stderr,
            'scoring_tool_sha256': sha256(TOOL),
            'analysis_receipt_sha256': sha256(PRIMARY / 'receipt.json'),
        }
        if run.returncode != 0:
            raise RuntimeError(json.dumps(record, indent=2))
        expected = sorted(path.name for path in PRIMARY.iterdir())
        actual = sorted(path.name for path in output.iterdir())
        if actual != expected:
            raise ValueError('CLI replay artifact names differ from the primary analysis')
        files = []
        for name in expected:
            same = (PRIMARY / name).read_bytes() == (output / name).read_bytes()
            files.append({'name': name, 'same_bytes': same,
                          'size_bytes': (PRIMARY / name).stat().st_size,
                          'sha256': sha256(PRIMARY / name),
                          'replay_sha256': sha256(output / name)})
        record['file_count'] = len(files)
        record['all_files_byte_identical'] = all(item['same_bytes'] for item in files)
        record['files'] = files
        if not record['all_files_byte_identical']:
            record['status'] = 'FAIL_NOT_BYTE_IDENTICAL'
            raise ValueError(json.dumps(record, indent=2))
        return record


if __name__ == '__main__':
    result = replay()
    destination = BUNDLE / 'review/cli_replay.json'
    destination.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
