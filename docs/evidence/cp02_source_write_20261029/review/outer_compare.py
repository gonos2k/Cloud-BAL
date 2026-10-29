"""Independently compare selected first-outer-call captures with PR129."""
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent.parent
PRIOR = ROOT / 'docs/evidence/cp02_xmm6_producer_20261029/captures'
CORE = ('th q qc qr qi qs qg nn nc ni nr bg diag_rhog den pii p delz xland rain '
        'rainncv snow snowncv sr graupel graupelncv').split()
OPTIONAL = ('refl_10cm', 're_cloud', 're_ice', 're_snow')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_arm(base, arm):
    files = sorted((base / arm).glob('raw_*.json.gz'))
    assert len(files) == 8
    records = [json.loads(gzip.decompress(p.read_bytes())) for p in files]
    assert {str(r['rank']) for r in records} == set(map(str, range(8)))
    samples = {}
    for r in records:
        assert r['status'] == 'all_ranks_settled'
        for endpoint in ('entry', 'return'):
            for s in r['outer'][endpoint]['samples']:
                if s['status'] != 'owned_tile':
                    continue
                key = (endpoint, s['i'], s['j'], s['k'])
                assert key not in samples
                samples[key] = (r['rank'], s['values'])
    assert len(samples) == 1248
    return samples, {p.name: sha(p) for p in files}

def main():
    arms = {}
    for arm in ('OFF', 'HYDRO', 'LIQUID'):
        new, new_hashes = read_arm(HERE / 'captures', arm)
        old, old_hashes = read_arm(PRIOR, arm)
        assert new.keys() == old.keys()
        core_count = 0
        optional = {}
        for key in sorted(new):
            rank, nv = new[key]
            prior_rank, ov = old[key]
            assert str(rank) == str(prior_rank)
            for field in CORE:
                assert nv[field]['finite'] and ov[field]['finite']
                assert nv[field]['raw_hex'] == ov[field]['raw_hex'], (arm, key, field)
                core_count += 1
            for field in OPTIONAL:
                stat = optional.setdefault(key[0] + ':' + field, {'compared': 0, 'different': 0, 'new_nonfinite': 0, 'prior_nonfinite': 0})
                stat['compared'] += 1
                stat['different'] += nv[field]['raw_hex'] != ov[field]['raw_hex']
                stat['new_nonfinite'] += not nv[field]['finite']
                stat['prior_nonfinite'] += not ov[field]['finite']
        assert core_count == 31200
        arms[arm] = {'core_equal_values': core_count, 'optional': optional, 'new_capture_sha256': new_hashes, 'pr129_capture_sha256': old_hashes}
    output = {'scope': 'Selected owned outer entry and return samples versus PR129, not whole-domain noninterference or scientific validation', 'core_fields': CORE, 'optional_fields': list(OPTIONAL), 'core_equal_values_total': sum(x['core_equal_values'] for x in arms.values()), 'arms': arms, 'script_sha256': sha(Path(__file__))}
    (HERE / 'validation/outer_scope.json').write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print('Compared', output['core_equal_values_total'], 'equal core values')

if __name__ == '__main__':
    main()
