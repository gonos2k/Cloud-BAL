"""Read closed receipt identities and history Times; never compute off-time scores."""
import hashlib
import json
from pathlib import Path
import statistics
import sys
from netCDF4 import Dataset, chartostring

ROOT = Path(__file__).resolve().parent

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

cohort = json.loads((ROOT / 'cohort_closed.json').read_text())
assert cohort['all_requested_forecasts_complete'] is False
rows = []
for arm in cohort['arms']:
    assert arm['status'] == 'CLOSED' and not arm['changed_source_pins']
    copied = ROOT / (arm['arm'].lower() + '_receipt.json')
    original = Path(arm['closed_receipt']['path'])
    assert sha(copied) == sha(original) == arm['closed_receipt']['sha256']
    r = json.loads(copied.read_text())
    assert r['status'] == 'INCOMPLETE' and r['returncode'] == 1
    assert r['final_completed_step'] == 38
    assert r['snapshots']['completed_post_kdm6_timesteps'] == list(range(1, 39))
    assert r['model_timestamps'][-1]['timestamp'] == '2026-08-16_13:12:40'
    assert not r['changed_staged_inputs'] and not r['changed_original_inputs']
    assert r['executed_executable_sha256'] == r['expected_executed_executable_sha256']
    histories = [x for x in r['generated_files'] if x['path'].startswith('wrfout_')]
    assert len(histories) == 1
    item = histories[0]
    history = original.parent / 'run' / item['path']
    assert sha(history) == item['sha256']
    with Dataset(history) as ds:
        times = chartostring(ds['Times'][:]).tolist()
    assert '2026-08-16_14:00:00' not in times
    assert sha(history) == item['sha256']
    costs = [x['elapsed_seconds'] for x in r['model_timestamps']]
    rows.append(dict(arm=arm['arm'], status=r['status'], model_returncode=1,
        completed_steps=38, completed_seconds=760, requested_seconds=3600,
        last_completed_time=r['model_timestamps'][-1]['timestamp'],
        receipt_sha256=sha(copied), history_sha256=item['sha256'], history_times=times,
        history_unchanged_during_read=True, model_fields_read=False,
        wall_seconds=r['wall_seconds'], timing_sum_seconds=sum(costs),
        timing_median_seconds=statistics.median(costs),
        timing_min_seconds=min(costs), timing_max_seconds=max(costs)))
obs = json.loads((ROOT / 'observation_dispatch.json').read_text())
paired = json.loads((ROOT / 'paired_dispatch.json').read_text())
assert obs['status'] == 'SKIPPED_NONCOMPLETE_COHORT'
assert paired['status'] == 'SKIPPED_NO_COMPLETE_OBSERVATION_RESULT'
assert obs['cohort']['sha256'] == sha(ROOT / 'cohort_closed.json')
assert paired['dispatch_sha256'] == sha(ROOT / 'observation_dispatch.json')
result = dict(status='CLOSED_INCOMPLETE_CONFIRMED', arms=rows,
    observation_status=obs['status'], paired_status=paired['status'],
    timing_scope='Aggregate main-step timings, not compute/physics/I/O attribution',
    state_validation='Receipt completion only; no new full source-endpoint audit',
    physical_approval='OPEN', observation_skill='NOT_EVALUATED')
text = json.dumps(result, indent=2, allow_nan=False) + '\n'
with Path(sys.argv[1]).open('x') as out:
    out.write(text)
