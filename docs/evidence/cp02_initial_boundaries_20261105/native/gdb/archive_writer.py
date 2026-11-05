#!/usr/bin/env python3
"""Preserve validated discovery receipts and lossless owner-rank event streams."""
import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[5]
BUNDLE=ROOT/'docs/evidence/cp02_initial_boundaries_20261105'
RUNTIME=ROOT.parent/'runtime/gdb_parity'
FREEZE_SHA='e8cf740ca1826f9f82f82fbdd74e7da9d728e127a3a9e3a9b728df116c26d12e'


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main(target,suffix):
    owner={'p20183':5,'p17051':3,'nr20330max':5}[target]
    source=RUNTIME/f'writer_{target}_{suffix}'; freeze=BUNDLE/'native/gdb/writer_freeze.json'
    if sha(freeze)!=FREEZE_SHA:raise ValueError('discovery freeze differs')
    if (source/'pair_exit.txt').read_text().strip()!=f'target={target} B1_exit=0 DM065_exit=0':raise ValueError('paired exits differ')
    target_dir=BUNDLE/'native/discovery'/target
    if os.path.lexists(target_dir):raise FileExistsError(target_dir)
    target_dir.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='.'+target+'-',dir=target_dir.parent))
    try:
        shutil.copyfile(freeze,temp/'writer_freeze.json')
        shutil.copyfile(source/'pair_exit.txt',temp/'pair_exit.txt')
        arms={}
        for arm in ('B1','DM065'):
            origin=source/arm;receipt=origin/'writer_receipt.json';d=json.loads(receipt.read_text())
            raw=origin/'writer_capture'/f'writer_rank{owner}.jsonl'
            if d['status']!='PASS_DISCOVERY_CAPTURE' or d['arm']!=arm or d['target']!=target or sha(raw)!=d['event_file_sha256']:
                raise ValueError('source capture receipt differs')
            out=temp/arm;out.mkdir()
            for p in (receipt,origin/'case_receipt.json',origin/'writer_descendants.json',origin/'writer_launcher.log',origin/'writer_capture'/f'gdb_rank{owner}.log'):
                shutil.copyfile(p,out/p.name)
            packed=out/(raw.name+'.gz')
            with raw.open('rb') as src,packed.open('xb') as dest:
                with gzip.GzipFile(filename='',fileobj=dest,mode='wb',mtime=0) as gz:shutil.copyfileobj(src,gz)
            h=hashlib.sha256()
            with gzip.open(packed,'rb') as data:
                for block in iter(lambda:data.read(1048576),b''):h.update(block)
            if h.hexdigest()!=d['event_file_sha256'] or sha(raw)!=d['event_file_sha256']:
                raise ValueError('event stream readback differs')
            arms[arm]={'receipt_path':str((target_dir/arm/'writer_receipt.json').resolve()),
                       'receipt_sha256':sha(out/'writer_receipt.json'),
                       'event_file_path':str(raw.resolve()),'event_file_sha256':d['event_file_sha256'],
                       'archived_event_path':str((target_dir/arm/packed.name).resolve()),
                       'archived_event_sha256':sha(packed),'decompressed_sha256':h.hexdigest(),
                       'raw_bytes':raw.stat().st_size,'compressed_bytes':packed.stat().st_size}
        closure={'status':'PASS','target':target,'freeze_sha256':FREEZE_SHA,
                 'pair_exit_sha256':sha(temp/'pair_exit.txt'),'arms':arms,
                 'scope':'Original executable; target boundary parity and original raw event words. GDB watch stop PCs are post-store and require separate instruction-level replay.'}
        (temp/'paired_closure.json').write_text(json.dumps(closure,indent=2)+'\n')
        if os.path.lexists(target_dir):raise FileExistsError(target_dir)
        os.rename(temp,target_dir)
    except BaseException:
        shutil.rmtree(temp,ignore_errors=True)
        raise
    print(target,sha(target_dir/'paired_closure.json'))


if __name__=='__main__':main(*sys.argv[1:])
