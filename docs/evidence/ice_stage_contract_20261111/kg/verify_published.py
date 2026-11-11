#!/usr/bin/env python3
"""Verify published targets and preserve every previously dated snapshot."""
import json
from pathlib import Path
from capture_baseline import MAINTAINED, dated_inventory, sha256

KG = Path(__file__).resolve().parent
STAMP = '2026-11-11-ice-stage-contract'

def main():
    baseline = json.loads((KG / 'baseline.json').read_text())
    receipt = json.loads((KG / 'publish_receipt.json').read_text())
    if receipt['status'] != 'PUBLISHED_AND_READBACK_PASS':
        raise RuntimeError('publication receipt is not successful')
    counts = {}
    for label, root in [('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED / 'Cloud-BAL')]:
        old = baseline['maintained_roots'][label]['dated_snapshots']
        current = dated_inventory(root)
        if set(current) != set(old) | {STAMP}:
            raise RuntimeError(f'{label}: unexpected dated snapshot set')
        if any(current[name] != hashes for name, hashes in old.items()):
            raise RuntimeError(f'{label}: prior dated snapshot changed')
        counts[label] = len(current)
    for target in receipt['targets']:
        if sha256(Path(target['path'])) != target['sha256']:
            raise RuntimeError(f'published target changed: {target["path"]}')
    result = {'status':'PASS', 'snapshot_counts':counts, 'prior_snapshot_count':270,
              'current_snapshot_count':sum(counts.values()),
              'publish_receipt_sha256':sha256(KG / 'publish_receipt.json'),
              'scope':'Structural snapshot and file identity only; not runtime or scientific validation.'}
    with (KG / 'postpublish_review.json').open('x') as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write('\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
