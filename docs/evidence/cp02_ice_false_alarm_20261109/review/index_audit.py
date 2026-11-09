#!/usr/bin/env python3
"""Stream and audit the exact staged manifest set against Git blobs and working files."""
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
manifest_name = 'docs/evidence/cp02_ice_false_alarm_20261109/validation.json'
review_name = 'docs/evidence/cp02_ice_false_alarm_20261109/review/final_index_review.json'
manifest_path = root / manifest_name
manifest = json.loads(manifest_path.read_bytes())
if manifest.get('status') != 'PASS':
    raise ValueError('manifest status is not PASS')
rows = manifest['artifacts']
expected = {}
for row in rows:
    name = row['path']
    p = Path(name)
    if p.is_absolute() or '..' in p.parts or name in expected or name in (manifest_name, review_name):
        raise ValueError(f'unsafe or duplicate manifest path: {name}')
    expected[name] = (row['sha256'], row['size_bytes'])
if len(rows) != manifest['artifact_count']:
    raise ValueError('manifest count differs')
manifest_bytes = manifest_path.read_bytes()
expected[manifest_name] = (hashlib.sha256(manifest_bytes).hexdigest(), len(manifest_bytes))
raw = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '-z'])
paths = [p.decode() for p in raw.split(b'\0') if p]
if len(paths) != len(set(paths)) or set(paths) != set(expected):
    raise ValueError(f'staged path mismatch: missing={sorted(set(expected)-set(paths))}; extra={sorted(set(paths)-set(expected))}')
if subprocess.check_output(['git', 'diff', '--cached', '--name-only', '--diff-filter=D', '-z']):
    raise ValueError('staged deletion found')
if subprocess.check_output(['git', 'ls-files', '--unmerged', '-z']):
    raise ValueError('unmerged index entries found')
entries = subprocess.check_output(['git', 'ls-files', '--stage', '-z', '--', *paths]).split(b'\0')
process = subprocess.Popen(['git', 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
results = []
try:
    for entry in entries:
        if not entry:
            continue
        meta, raw_path = entry.split(b'\t', 1)
        mode, oid, stage = meta.split()
        path = raw_path.decode()
        if stage != b'0' or mode not in (b'100644', b'100755') or path not in expected:
            raise ValueError(f'unsupported index entry: {path}')
        work_path = root / path
        if work_path.is_symlink() or not work_path.is_file():
            raise ValueError(f'unsafe or missing working file: {path}')
        process.stdin.write(oid + b'\n'); process.stdin.flush()
        actual_oid, kind, size = process.stdout.readline().rstrip(b'\n').split()
        size = int(size)
        if actual_oid != oid or kind != b'blob' or size != expected[path][1]:
            raise ValueError(f'blob header or size mismatch: {path}')
        remaining = size
        staged = hashlib.sha256()
        with work_path.open('rb') as stream:
            while remaining:
                chunk = process.stdout.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError(f'truncated blob: {path}')
                remaining -= len(chunk); staged.update(chunk)
                if stream.read(len(chunk)) != chunk:
                    raise ValueError(f'working file differs from staged blob: {path}')
            if stream.read(1):
                raise ValueError(f'working file longer than staged blob: {path}')
        if process.stdout.read(1) != b'\n' or staged.hexdigest() != expected[path][0]:
            raise ValueError(f'blob delimiter or manifest SHA mismatch: {path}')
        results.append({'path': path, 'git_oid': oid.decode(), 'bytes': size, 'sha256': staged.hexdigest()})
except BaseException:
    process.kill(); process.wait()
    raise
else:
    process.stdin.close()
    status = process.wait()
    if status:
        raise RuntimeError(f'git cat-file failed: {status}')
if len(results) != len(expected) or {r['path'] for r in results} != set(expected):
    raise ValueError('staged paths and index entries differ')
print(json.dumps({'status': 'PASS', 'manifest_sha256': expected[manifest_name][0],
                  'manifest_artifacts': len(rows), 'staged_blobs': len(results),
                  'bytes': sum(r['bytes'] for r in results), 'files': results}, indent=2))
