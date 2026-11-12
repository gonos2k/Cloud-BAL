#!/usr/bin/env python3
"""Publish a separately reviewed graph stage with rollback on failure."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from verify_baseline import verify

ROOT = Path(__file__).resolve().parents[4]
KG = Path(__file__).resolve().parent
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
STAMP = '2026-11-12-prior-cycle-application'
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
WIKI_FILES = ('graph-report.md','graph-report-klaps50.md','graph-report-cloud-bal.md','index.md','log.md')

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20),b''):
            digest.update(block)
    return digest.hexdigest()

def require(condition, message):
    if not condition: raise RuntimeError(message)

def publish():
    lock_path=KG/'selection_lock.json'; receipt_path=KG/'stage_receipt.json'
    lock=json.loads(lock_path.read_text()); receipt=json.loads(receipt_path.read_text())
    review=json.loads((KG/'stage_review.json').read_text())
    require(review['status']=='GO' and all(review['checks'].values()), 'independent stage GO required')
    require(review['stage_receipt_sha256']==sha(receipt_path) and review['selection_lock_sha256']==sha(lock_path), 'stage review pins changed')
    require(receipt['status']=='STAGED_ONLY_NO_MAINTAINED_WRITES' and receipt['snapshot']==STAMP, 'invalid stage receipt')
    require(json.loads((KG/'prior_audit.json').read_text())['status']=='PASS', 'prior audit missing')
    for name, digest in {**lock['selected_source_sha256'],**lock['hash_only_sha256']}.items():
        require(sha(ROOT/name)==digest, f'frozen pin changed: {name}')
    verify()
    stage=Path(receipt['stage'])
    targets=[]
    for label, root in (('KLAPS50',MAINTAINED),('Cloud-BAL',MAINTAINED/'Cloud-BAL')):
        for name in GRAPH_FILES:
            source=stage/label/'graphify-out'/name
            require(sha(source)==receipt['corpora'][label]['snapshot_file_sha256'][name], f'stage graph changed: {label}/{name}')
            targets.append((source,root/'graphify-out'/name,True))
            targets.append((source,root/'graphify-out'/STAMP/name,False))
    for name in WIKI_FILES:
        source=stage/'wiki'/name
        require(sha(source)==receipt['staged_wiki_sha256'][name], f'stage wiki changed: {name}')
        targets.append((source,MAINTAINED/'wiki'/name,True))
        targets.append((source,KG/'wiki'/name,False))
    # Source worktree mirrors the maintained Cloud-BAL graph and gets its own dated snapshot.
    for name in GRAPH_FILES:
        source=stage/'Cloud-BAL/graphify-out'/name
        targets.append((source,ROOT/'graphify-out'/name,True))
        targets.append((source,ROOT/'graphify-out'/STAMP/name,False))
    destinations=[dst for _,dst,_ in targets]
    require(len(set(destinations))==len(destinations),'duplicate destinations')
    for src,dst,exists in targets:
        require(src.is_file() and not src.is_symlink() and not dst.is_symlink(), f'unsafe path: {dst}')
        require(dst.is_file() if exists else not dst.exists(), f'unexpected destination: {dst}')
    created_dirs=[]; undo=[]; copied=[]; receipts=[]
    try:
        for src,dst,existed in targets:
            if not dst.parent.exists():
                dst.parent.mkdir(); created_dirs.append(dst.parent)
            backup=None
            if existed:
                with tempfile.NamedTemporaryFile(dir=dst.parent,delete=False) as f: backup=Path(f.name)
                try: shutil.copy2(dst,backup)
                except BaseException:
                    backup.unlink(missing_ok=True)
                    raise
            try:
                with tempfile.NamedTemporaryFile(dir=dst.parent,delete=False) as f: temporary=Path(f.name)
            except BaseException:
                if backup: backup.unlink(missing_ok=True)
                raise
            try:
                shutil.copy2(src,temporary)
                require(sha(temporary)==sha(src), f'temporary copy mismatch: {dst}')
                os.replace(temporary,dst)
            except BaseException:
                if backup: backup.unlink(missing_ok=True)
                raise
            finally:
                temporary.unlink(missing_ok=True)
            undo.append((dst,backup,existed))
            require(sha(dst)==sha(src), f'readback mismatch: {dst}')
            copied.append({'path':str(dst),'sha256':sha(dst)})
        require(not (KG/'publish_receipt.json').exists() and not (KG/'source_copy_receipt.json').exists(), 'receipts already exist')
        with (KG/'publish_receipt.json').open('x') as f:
            receipts.append(KG/'publish_receipt.json')
            json.dump({'status':'PUBLISHED_AND_READBACK_PASS','snapshot':STAMP,
                       'stage_review_sha256':sha(KG/'stage_review.json'),
                       'selection_lock_sha256':sha(lock_path),'targets':copied,
                       'prior_snapshot_count':json.loads((KG/'baseline.json').read_text())['dated_snapshot_count_total'],
                       'new_maintained_snapshot_count':json.loads((KG/'baseline.json').read_text())['dated_snapshot_count_total'] + 2},f,indent=2,sort_keys=True)
            f.write('\n')
        with (KG/'source_copy_receipt.json').open('x') as f:
            receipts.append(KG/'source_copy_receipt.json')
            local=[row for row in copied if row['path'].startswith(str(ROOT)+'/')]
            json.dump({'status':'COPIED_AND_READBACK_PASS','snapshot':STAMP,
                       'publish_receipt_sha256':sha(KG/'publish_receipt.json'), 'targets':local},
                      f,indent=2,sort_keys=True)
            f.write('\n')
    except BaseException:
        for path in receipts: path.unlink(missing_ok=True)
        for dst,backup,existed in reversed(undo):
            if existed: os.replace(backup,dst)
            else: dst.unlink(missing_ok=True)
        for directory in reversed(created_dirs): directory.rmdir()
        raise
    finally:
        for _,backup,_ in undo:
            if backup: backup.unlink(missing_ok=True)
    print('PASS: two maintained dated snapshots, graph trios, five wiki files and worktree copies published')

if __name__=='__main__':
    if sys.argv[1:] != ['--publish']: raise SystemExit('explicit root GO and --publish required')
    publish()
