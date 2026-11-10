#!/usr/bin/env python3
"""Replay a completed MP10 figure package and compare every output byte."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
import plot_cp02_mp10_process as plots


def run(expected, output, analysis=None, scratch=None):
    if os.path.lexists(output):
        raise FileExistsError(output)
    original = {p.name: plots.E.identity(p) for p in expected.iterdir() if p.is_file()}
    if 'receipt.json' not in original:
        raise ValueError('missing figure receipt')
    manifest = json.loads((expected / 'receipt.json').read_text())
    if manifest.get('status') != 'COMPLETE' or set(manifest['outputs']) != set(original) - {'receipt.json'}:
        raise ValueError('incomplete figure package')
    for name, expected_hash in manifest['outputs'].items():
        if original[name]['sha256'] != expected_hash:
            raise ValueError('figure package hash mismatch: ' + name)
    with tempfile.TemporaryDirectory(prefix='mp10-figure-replay-', dir=scratch) as temp:
        replay = Path(temp) / 'figures'
        plots.run(replay, analysis)
        actual = {p.name: plots.E.identity(p) for p in replay.iterdir() if p.is_file()}
        if set(actual) != set(original):
            raise ValueError('replayed figure inventory differs')
        for name, record in original.items():
            if actual[name]['sha256'] != record['sha256']:
                raise ValueError('replayed figure differs: ' + name)
        for record in original.values():
            if plots.E.identity(record['path']) != record:
                raise ValueError('expected figure changed during replay')
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {'status': 'PASS', 'expected_receipt': original['receipt.json'],
              'replay_source': plots.E.identity(__file__), 'figures': len(original),
              'sha256': {name: record['sha256'] for name, record in sorted(original.items())}}
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--analysis', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scratch', type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.expected, args.output, args.analysis, args.scratch), indent=2))
