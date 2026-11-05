#!/usr/bin/env python3
"""Independently decode the actual CP04 quick captures and pin their bytes."""
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'tools'))
import cp02_thermo_cloud_path as cp

EVIDENCE = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
QUICK = ROOT.parent / 'runtime/quick'


def main():
    schema_path = EVIDENCE / 'native/schema/cp04_schema.json'
    corners_path = EVIDENCE / 'cohorts/results/point_corners.csv'
    schema = json.loads(schema_path.read_text())
    _, cells, indices, weights = cp.read_corners(corners_path)
    roots = {arm: QUICK / arm for arm in ('B1', 'DM065')}
    inputs = cp.inventory(roots)
    with tempfile.TemporaryDirectory() as tmp:
        cases = {arm: cp.analyze_arm(root, arm, tmp, schema, cells, indices, weights, 1)
                 for arm, root in roots.items()}
    cp.verify_inventory(inputs)
    record = {'status': 'PASS', 'steps': 1, 'levels': 39, 'native_cells': 123,
              'assertions': ['all actual mandatory phases and owning cores', 'all actual sedimentation substeps',
                             'conditional surface pairs and source arithmetic', 'wrapper TH*PII and P/PII call invariance',
                             'wrapper/internal density conversions and clamping', 'liquid SATDT',
                             'REAL32 QV/T process and condensation arithmetic'],
              'schema_sha256': cp.sha256(schema_path), 'corners_sha256': cp.sha256(corners_path),
              'analyzer_sha256': cp.sha256(ROOT / 'tools/cp02_thermo_cloud_path.py'),
              'script_sha256': cp.sha256(Path(__file__)), 'inputs': inputs, 'cases': cases}
    path = EVIDENCE / 'native/quick/independent_quick_gate.json'
    with path.open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print('PASS', cp.sha256(path))


if __name__ == '__main__':
    main()
