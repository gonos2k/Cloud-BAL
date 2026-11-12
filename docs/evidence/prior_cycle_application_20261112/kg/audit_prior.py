#!/usr/bin/env python3
"""Record prior PR file identities from immutable Git trees."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TIP = 'd31cf5f40ad3bc8b4f88bbd3ba9e1760b46e10e3'
BASE = '817f27af88fc07230f0671ac9c8e0d90cdc8f0f7'

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

def main():
    tip_tree = git('rev-parse', TIP + '^{tree}').decode().strip()
    base_tree = git('rev-parse', BASE + '^{tree}').decode().strip()
    if tip_tree != base_tree:
        raise RuntimeError('Prior tip and merge base trees differ')
    paths = git('diff-tree', '--no-commit-id', '--name-only', '-r', '-z', TIP).split(b'\0')
    rows = []
    for raw in filter(None, paths):
        path = raw.decode('utf-8')
        tip_blob = git('rev-parse', TIP + ':' + path).decode().strip()
        base_blob = git('rev-parse', BASE + ':' + path).decode().strip()
        if tip_blob != base_blob:
            raise RuntimeError(f'blob mismatch: {path}')
        rows.append({'path': path, 'git_blob': tip_blob})
    result = {'status':'PASS', 'prior_pr':166, 'prior_tip':TIP, 'base_commit':BASE,
              'tree':tip_tree, 'commit_trees_identical':True, 'prior_pr_files':len(rows),
              'artifacts':rows, 'scope':'Immutable Git objects; no historical proof bundle edited.'}
    target = Path(__file__).parent / 'prior_audit.json'
    with target.open('x') as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write('\n')
    print(f'PASS: {len(rows)} prior PR file blob identities; tree {tip_tree}')

if __name__ == '__main__':
    main()
