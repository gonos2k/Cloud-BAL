#!/usr/bin/env python3
"""Archive verified original-executable phi event streams and paired receipts."""
import gzip,hashlib,json,os,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
BUNDLE=ROOT/'docs/evidence/cp02_initial_boundaries_20261105'
RUNTIME=ROOT.parent/'runtime/gdb_parity'
FREEZE_SHA='6ea99937103482991ad6c166f509bbf4efe5d24848366d60f2a3c5347aa3a860'


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main(target):
    owner={'p20183':5,'p17051':3}[target];source=RUNTIME/f'phi_{target}_01';freeze=BUNDLE/'native/gdb/phi_freeze.json'
    if sha(freeze)!=FREEZE_SHA:raise ValueError('phi freeze differs')
    if (source/'pair_exit.txt').read_text().strip()!=f'target={target} B1_exit=0 DM065_exit=0':raise ValueError('paired exits differ')
    dest=BUNDLE/'native/phi_discovery'/target
    if os.path.lexists(dest):raise FileExistsError(dest)
    dest.parent.mkdir(parents=True,exist_ok=True);tmp=Path(tempfile.mkdtemp(prefix='.'+target+'-',dir=dest.parent))
    try:
        shutil.copyfile(freeze,tmp/'phi_freeze.json');shutil.copyfile(source/'pair_exit.txt',tmp/'pair_exit.txt');arms={}
        for arm in ('B1','DM065'):
            origin=source/arm;receipt=origin/'phi_receipt.json';record=json.loads(receipt.read_text());raw=origin/'phi_capture'/f'phi_rank{owner}.jsonl'
            if record['status']!='PASS_PHI_DISCOVERY' or record['arm']!=arm or record['target']!=target or sha(raw)!=record['event_file_sha256']:raise ValueError('phi receipt differs')
            out=tmp/arm;out.mkdir()
            for p in (receipt,origin/'case_receipt.json',origin/'phi_descendants.json',origin/'phi_launcher.log',origin/'phi_capture'/f'gdb_rank{owner}.log'):shutil.copyfile(p,out/p.name)
            packed=out/(raw.name+'.gz')
            with raw.open('rb') as f,packed.open('xb') as g:
                with gzip.GzipFile(filename='',fileobj=g,mode='wb',mtime=0) as z:shutil.copyfileobj(f,z)
            h=hashlib.sha256()
            with gzip.open(packed,'rb') as z:
                for block in iter(lambda:z.read(1048576),b''):h.update(block)
            if h.hexdigest()!=record['event_file_sha256'] or sha(raw)!=record['event_file_sha256']:raise ValueError('event readback differs')
            arms[arm]={'receipt_path':str((dest/arm/'phi_receipt.json').resolve()),'receipt_sha256':sha(out/'phi_receipt.json'),
                       'event_file_path':str(raw.resolve()),'event_file_sha256':sha(raw),
                       'archived_event_path':str((dest/arm/packed.name).resolve()),'archived_event_sha256':sha(packed),
                       'decompressed_sha256':h.hexdigest(),'raw_bytes':raw.stat().st_size,'compressed_bytes':packed.stat().st_size}
        closure={'status':'PASS','target':target,'freeze_sha256':FREEZE_SHA,'pair_exit_sha256':sha(tmp/'pair_exit.txt'),'arms':arms,
                 'scope':'Observed target phi/vspow, continuous P gap and prep/KDM word bridges; GDB watch PCs remain post-store until separately reviewed preinstruction replay.'}
        (tmp/'paired_closure.json').write_text(json.dumps(closure,indent=2)+'\n')
        if os.path.lexists(dest):raise FileExistsError(dest)
        os.rename(tmp,dest)
    except BaseException:
        shutil.rmtree(tmp,ignore_errors=True);raise
    print(target,sha(dest/'paired_closure.json'))


if __name__=='__main__':main(*sys.argv[1:])
