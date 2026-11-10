#!/usr/bin/env python3
"""Audit every PR158 manifest artifact against its git blob and preserved copy."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
KG = Path(__file__).resolve().parent
BASE = '8fe0892ec1a6a0c3f1ca35b23fd5cc289c400803'
PRIOR = ROOT / 'docs/evidence/cp02_mp10_process_20261110'
ALIASES = {
    'README.md': 'prior_aliases/README.md',
    'docs/CURRENT_RESEARCH_STATUS.md': 'prior_aliases/CURRENT_RESEARCH_STATUS.md',
    **{f'graphify-out/{name}': f'prior_aliases/graphify-out/{name}'
       for name in ('graph.json','GRAPH_REPORT.md','manifest.json')},
}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    manifest_path = PRIOR/'validation.json'
    review_path = PRIOR/'review/final_index_review.json'
    manifest_data = manifest_path.read_bytes()
    review = json.loads(review_path.read_bytes())
    manifest = json.loads(manifest_data)
    assert review['manifest_sha256'] == hashlib.sha256(manifest_data).hexdigest()
    rows = manifest['artifacts']
    assert manifest['artifact_count'] == len(rows) == 8656
    assert len({r['path'] for r in rows}) == len(rows)
    assert subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'], text=True).strip() == BASE
    paths = [r['path'] for r in rows] + [str(manifest_path.relative_to(ROOT)),str(review_path.relative_to(ROOT))]
    assert all('\n' not in p and '\r' not in p and not p.startswith('-') for p in paths)
    changed = []
    with tempfile.TemporaryFile() as queries:
        queries.write(''.join(f'{BASE}:{p}\n' for p in paths).encode())
        queries.seek(0)
        proc = subprocess.Popen(['git','-C',str(ROOT),'cat-file','--batch'],stdin=queries,stdout=subprocess.PIPE)
        assert proc.stdout is not None
        for idx,path in enumerate(paths):
            header = proc.stdout.readline().decode().strip().split()
            assert len(header)==3 and header[1]=='blob', (path,header)
            size = int(header[2])
            expected = rows[idx] if idx < len(rows) else None
            if expected:
                assert size == expected['size_bytes'], path
            alias = KG/ALIASES[path] if path in ALIASES else None
            if alias:
                alias.parent.mkdir(parents=True, exist_ok=True)
                temporary = tempfile.NamedTemporaryFile(dir=alias.parent,delete=False)
            else:
                temporary = None
            digest = hashlib.sha256()
            remaining = size
            while remaining:
                chunk = proc.stdout.read(min(1 << 20,remaining))
                assert chunk, f'truncated git blob: {path}'
                digest.update(chunk)
                if temporary:
                    temporary.write(chunk)
                remaining -= len(chunk)
            assert proc.stdout.read(1) == b'\n'
            if temporary:
                temporary.close()
            actual = digest.hexdigest()
            if expected:
                assert actual == expected['sha256'], f'committed blob differs: {path}'
            else:
                assert actual == sha(ROOT/path), f'prior index differs: {path}'
            if alias:
                temp_path = Path(temporary.name)
                if alias.exists():
                    assert sha(alias) == actual, f'prior alias differs: {alias}'
                    temp_path.unlink()
                else:
                    temp_path.rename(alias)
                preserved = alias
            else:
                preserved = ROOT/path
            assert preserved.stat().st_size == size and sha(preserved) == actual, f'preserved copy differs: {preserved}'
            current = ROOT/path
            if sha(current) != actual:
                assert alias, f'unapproved prior artifact changed: {path}'
                changed.append({'path':path,'preserved_at':str(alias.relative_to(ROOT)),'current_sha256':sha(current)})
        assert proc.stdout.read() == b'' and proc.wait() == 0
    publish = PRIOR/'kg/publish_receipt.json'
    receipt = json.loads(publish.read_text())
    assert receipt['status'].startswith('PUBLISHED') and receipt['published_snapshot_count'] == 262
    result = {'status':'PASS_PRIOR_8656_AND_INDEX_PRESERVED','base':BASE,
              'manifest_sha256':hashlib.sha256(manifest_data).hexdigest(),
              'final_index_review_sha256':sha(review_path), 'published_snapshot_count':262,
              'publish_receipt_sha256':sha(publish), 'artifact_count':len(rows),
              'alias_count':len(ALIASES),'changed_current_paths':changed,'maintained_roots_written':False}
    target = KG/'prior_audit.json'
    with target.open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True)
        stream.write('\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
