#!/usr/bin/env python3
"""Recount archived writer and pressure-phi streams without external model files."""
import gzip
import importlib.util
import hashlib
import os
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_initial_boundaries_20261105'
sys.path.insert(0, str(ROOT / 'tools'))
import cp02_initial_phi_analysis as phi


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def resolve_json(digest):
    found = [p for p in BUNDLE.rglob('*.json') if sha(p) == digest]
    if not found:
        raise ValueError('Missing archived JSON: ' + digest)
    return sorted(found)[0]


def bound_writer(digest):
    candidates = [ROOT / 'tools/cp02_initial_writer_analysis.py']
    candidates += sorted((BUNDLE / 'prior_versions').rglob('*.py'))
    found = [p for p in candidates if sha(p) == digest]
    if not found:
        raise ValueError('Missing explicitly bound writer producer version')
    spec = importlib.util.spec_from_file_location('bound_writer_' + digest[:12], found[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    for target in ('nr20330', 'nr20330max', 'p20183', 'p17051'):
        original = BUNDLE / f'science/writer_{target}/analysis.json'
        expected = json.loads(original.read_text())
        receipts, events = {}, {}
        for arm in ('B1', 'DM065'):
            receipts[arm] = resolve_json(expected['inputs'][arm]['receipt_sha256'])
            archives = ([BUNDLE / f'native/revalidated_nr20330/{arm}_writer_rank5.jsonl.gz']
                        if target == 'nr20330' else
                        list((BUNDLE / f'native/discovery/{target}/{arm}').glob('writer_rank*.jsonl.gz')))
            if len(archives) != 1:
                raise ValueError('Archive inventory differs')
            raw = gzip.decompress(archives[0].read_bytes())
            if hashlib.sha256(raw).hexdigest() != expected['inputs'][arm]['event_sha256']:
                raise ValueError('Decompressed stream mismatch')
            events[arm] = out / f'{target}_{arm}.jsonl'
            events[arm].write_bytes(raw)
        dest = out / f'writer_{target}'
        producer = bound_writer(expected['source_sha256'])
        producer.run_analysis(target, receipts, events,
                            BUNDLE / 'baseline/results/early_selected.npz', dest,
                            resolve_json(expected['schema_sha256']),
                            resolve_json(expected['capture_closure_sha256']),
                            resolve_json(expected['capture_freeze_sha256']))
        actual = json.loads((dest / 'analysis.json').read_text())
        normalized = json.loads(json.dumps(actual))
        # Recount relocates only these two filesystem strings per arm.
        for arm in receipts:
            for key in ('receipt_path', 'event_path'):
                normalized['inputs'][arm][key] = expected['inputs'][arm][key]
        if normalized != expected:
            raise ValueError('Writer numerical replay differs: ' + target)
        rows.append({'target': target, 'kind': 'writer', 'original_sha256': sha(original),
                     'replayed_sha256': sha(dest / 'analysis.json'),
                     'producer_sha256': expected['source_sha256'],
                     'comparison': 'Explicitly bound producer version; all JSON values identical after normalizing four input path strings.'})
    for target in ('p20183', 'p17051'):
        original = BUNDLE / f'science/phi_{target}/analysis.json'
        folder = BUNDLE / f'native/phi_discovery/{target}'
        dest = out / f'phi_{target}.json'
        phi.run_analysis(target, folder / 'paired_closure.json', folder / 'phi_freeze.json',
                         BUNDLE / 'native/gdb/phi_schema.json',
                         BUNDLE / 'baseline/results/early_selected.npz', dest)
        if sha(dest) != sha(original):
            raise ValueError('Phi byte replay differs: ' + target)
        rows.append({'target': target, 'kind': 'phi', 'original_sha256': sha(original),
                     'replayed_sha256': sha(dest), 'comparison': 'Byte identical.'})
    sys.path.insert(0, str(BUNDLE / 'native/gdb'))
    os.environ['CP05_ATTEMPT'] = 'portable_numerator_replay'
    import numerator_case
    for arm in ('B1', 'DM065'):
        folder = BUNDLE / 'native/numerator_p20183' / arm
        expected = json.loads((folder / 'numerator_receipt.json').read_text())
        target = out / ('numerator_' + arm)
        (target / 'phi_capture').mkdir(parents=True)
        for name in ('numerator_rank5.jsonl', 'phi_rank5.jsonl'):
            raw = gzip.decompress((folder / (name + '.gz')).read_bytes())
            (target / 'phi_capture' / name).write_bytes(raw)
        actual = numerator_case.validate_numerator(arm, target)
        if any(expected[key] != value for key, value in actual.items()):
            raise ValueError('Numerator replay differs: ' + arm)
        rows.append({'arm': arm, 'kind': 'actual_numerator',
                     'receipt_sha256': sha(folder / 'numerator_receipt.json'),
                     'result': actual})
    result = {'status': 'PASS', 'scope': 'Six archived analysis replays and two actual numerator replays; no WRF execution or external source arrays.',
              'producer_sha256': sha(__file__), 'outputs': rows}
    (out / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
