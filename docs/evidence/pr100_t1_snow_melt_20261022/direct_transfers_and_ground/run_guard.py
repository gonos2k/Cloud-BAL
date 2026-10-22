from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

manifest = Path(sys.argv[1]).resolve()
data = json.loads(manifest.read_text())
work = Path(data['cwd']).resolve()
assert Path.cwd().resolve() == work
assert manifest.parent == work
assert {p.name for p in work.iterdir()} == {'launch_manifest.json', 'kdm6_first_call_pre.raw'}
exe = Path(data['exe'])
pre = work / 'kdm6_first_call_pre.raw'
assert sha(exe) == data['exe_sha256']
assert sha(pre) == data['pre_sha256']
argv = [str(exe), str(pre)]
start = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
with (work / 'run.log').open('xb') as log:
    result = subprocess.run(argv, cwd=work, stdout=log, stderr=subprocess.STDOUT, check=False)
record = {'schema': 'pr100_root_guarded_replay_v1', 'arm': data['arm'],
          'cwd': str(work), 'argv': argv, 'start_utc': start,
          'end_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
          'returncode': result.returncode, 'launch_manifest_sha256': sha(manifest),
          'executable_sha256': sha(exe), 'pre_sha256_after': sha(pre),
          'artifacts': {p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)}
                        for p in sorted(work.iterdir()) if p.is_file()},
          'scope': data['scope']}
record['post_matches_native'] = record['artifacts'].get('replay_post.raw', {}).get('sha256') == data['post_sha256']
record['native_dump_matches'] = record['artifacts'].get('kdm6_first_call_post.raw', {}).get('sha256') == data['post_sha256']
record['completion_marker'] = b'REPLAY COMPLETED FULL ACTIVE TILE' in (work / 'run.log').read_bytes()
with (work / 'receipt.json').open('x') as out:
    json.dump(record, out, indent=2)
    out.write('\n')
print(work / 'receipt.json')
if result.returncode or not all(record[k] for k in ('post_matches_native', 'native_dump_matches', 'completion_marker')):
    raise SystemExit(1)
