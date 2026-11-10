#!/usr/bin/env python3
"""Move verified unpacked capture artifacts to scratch, retaining public receipts."""
import json,os,sys
from compact_v2 import NATIVE,ROOT,sha


def main():
    arm=sys.argv[1];source=NATIVE/'compact'/arm;packed=NATIVE/'packed'/arm
    dest=ROOT.parent/'runtime/unpacked_compact'/arm
    capture=source/'capture_receipt.json';recount=source/'raw_recount_receipt.json';packing=packed/'packing_receipt.json'
    c=json.loads(capture.read_text());r=json.loads(recount.read_text());p=json.loads(packing.read_text())
    if r['status']!='PASS' or p['status']!='PASS' or r['capture_receipt_sha256']!=sha(capture) or p['capture_receipt_sha256']!=sha(capture) or p['raw_recount_sha256']!=sha(recount):raise ValueError('capture/audit/packing chain invalid')
    byname={x['name']:x for x in p['outputs']}
    if set(byname)!={x['name'] for x in c['outputs']}:raise ValueError('packing coverage mismatch')
    for x in c['outputs']:
        orig=source/x['name'];packed_file=packed/x['name'];record=byname[x['name']]
        if sha(orig)!=x['sha256'] or record['source_sha256']!=x['sha256'] or sha(packed_file)!=record['sha256']:raise ValueError('artifact hash mismatch')
    dest.mkdir(parents=True,exist_ok=False);moved=[]
    try:
        for x in c['outputs']:
            orig=source/x['name'];target=dest/x['name']
            os.rename(orig,target);moved.append((orig,target))
            if sha(target)!=x['sha256']:raise ValueError('relocation changed bytes')
        result={'status':'PASS','arm':arm,'destination':str(dest),'capture_receipt_sha256':sha(capture),'raw_recount_sha256':sha(recount),'packing_receipt_sha256':sha(packing),'files':[{'name':x['name'],'sha256':x['sha256'],'size_bytes':x['size_bytes']} for x in c['outputs']],'method':'same-filesystem rename; hashes verified before and after; original receipts retained publicly'}
        (source/'relocation_receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    except BaseException:
        for orig,target in reversed(moved):os.rename(target,orig)
        dest.rmdir()
        raise
if __name__=='__main__':main()
