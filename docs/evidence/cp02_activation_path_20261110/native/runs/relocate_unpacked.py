#!/usr/bin/env python3
"""Move audited redundant unpacked artifacts to scratch, retaining proof receipts."""
import json,shutil,sys
from pathlib import Path
from compact_v2 import NATIVE,sha

RUNTIME=NATIVE.parents[3].parent/'runtime'

def main():
    arm=sys.argv[1];src=NATIVE/'compact'/arm;dst=RUNTIME/'unpacked_compact'/arm;packed=NATIVE/'packed'/arm
    capture=src/'capture_receipt.json';recount=src/'raw_recount_receipt.json';packing=packed/'packing_receipt.json'
    c=json.loads(capture.read_text());r=json.loads(recount.read_text());p=json.loads(packing.read_text())
    if r['status']!='PASS' or p['status']!='PASS' or r['capture_receipt_sha256']!=sha(capture) or p['raw_recount_sha256']!=sha(recount):raise ValueError('missing audit or packing proof')
    if dst.exists():raise FileExistsError(dst)
    for item in c['outputs']:
        f=src/item['name']
        if f.stat().st_size!=item['size_bytes'] or sha(f)!=item['sha256']:raise ValueError('unpacked source changed')
    dst.parent.mkdir(parents=True,exist_ok=True);src.rename(dst)
    try:
        src.mkdir()
        for name in ('capture_receipt.json','raw_recount_receipt.json','surface_audit.json'):
            source=dst/name;target=src/name;shutil.copyfile(source,target)
            if sha(source)!=sha(target):raise ValueError('receipt changed on relocation')
        for item in c['outputs']:
            if sha(dst/item['name'])!=item['sha256']:raise ValueError('moved artifact differs')
        receipt={'status':'PASS','arm':arm,'destination':str(dst),'artifacts':len(c['outputs']),'capture_receipt_sha256':sha(src/'capture_receipt.json'),'packing_receipt_sha256':sha(packing),'method':'move same-filesystem then verify every audited artifact against original capture hash; original receipts copied back byte-for-byte'}
        (src/'relocation_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    except BaseException:
        if src.exists():
            for path in src.iterdir():path.unlink()
            src.rmdir()
        dst.rename(src)
        raise
    print(json.dumps(receipt))
if __name__=='__main__':main()
