#!/usr/bin/env python3
"""Losslessly repackage audited NPZ members using deterministic ZIP LZMA."""
import hashlib, json, shutil, sys, zipfile
from pathlib import Path
from compact_v2 import NATIVE, sha


def digest(data):return hashlib.sha256(data).hexdigest()
def main():
    arm=sys.argv[1];source=NATIVE/'compact'/arm;dest=NATIVE/'packed'/arm
    capture=source/'capture_receipt.json';recount=source/'raw_recount_receipt.json'
    if json.loads(recount.read_text())['status']!='PASS':raise ValueError('raw recount did not pass')
    if json.loads(recount.read_text())['capture_receipt_sha256']!=sha(capture):raise ValueError('recount does not bind capture')
    dest.mkdir(parents=True,exist_ok=False);outputs=[]
    for item in json.loads(capture.read_text())['outputs']:
        original=source/item['name'];target=dest/item['name']
        if sha(original)!=item['sha256']:raise ValueError('source changed')
        members=[]
        if original.suffix=='.npz':
            with zipfile.ZipFile(original) as inp, zipfile.ZipFile(target,'x',compression=zipfile.ZIP_LZMA) as out:
                names=inp.namelist()
                if len(names)!=len(set(names)):raise ValueError('duplicate member')
                for name in names:
                    data=inp.read(name);info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_LZMA;info.external_attr=0o600<<16
                    out.writestr(info,data);members.append({'name':name,'sha256':digest(data),'size_bytes':len(data)})
            with zipfile.ZipFile(target) as verify:
                if verify.testzip() is not None or verify.namelist()!=names:raise ValueError('packed zip integrity failure')
                for member in members:
                    if digest(verify.read(member['name']))!=member['sha256']:raise ValueError('member bytes changed')
        else:
            shutil.copyfile(original,target)
            if sha(original)!=sha(target):raise ValueError('wrapper copy changed')
        if target.stat().st_size>=80000000:raise ValueError('artifact exceeds cap')
        outputs.append({'name':target.name,'source_sha256':item['sha256'],'sha256':sha(target),'size_bytes':target.stat().st_size,'members':members})
    receipt={'status':'PASS','arm':arm,'capture_receipt_sha256':sha(capture),'raw_recount_sha256':sha(recount),'codec':'ZIP_LZMA; exact original .npy bytes; np.load allow_pickle=False','outputs':outputs}
    (dest/'packing_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':main()
