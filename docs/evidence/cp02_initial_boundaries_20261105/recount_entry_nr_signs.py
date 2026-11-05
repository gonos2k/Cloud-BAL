#!/usr/bin/env python3
"""Count first-entry NR signs among the portable changed-cell sparse subset."""
import hashlib,json
from pathlib import Path
import numpy as np
P=Path(__file__).resolve().parent
RECEIPT='f76b74141410d5b287c554467fd0f3803fe9a8c8debceb6e33dd30639aa69681'

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    receipt_path=P/'results/receipt.json'
    if sha(receipt_path)!=RECEIPT:raise ValueError('global receipt changed')
    receipt=json.loads(receipt_path.read_text());arrays=[]
    for name in ('entry_NR','initial_NR'):
        path=P/'results/sparse'/f'{name}.npz'
        if sha(path)!=receipt['outputs'][f'sparse/{name}.npz']['sha256']:raise ValueError('sparse data changed')
        with np.load(path,allow_pickle=False) as z:arrays.append({k:z[k].copy() for k in z.files})
    entry,initial=arrays;ix=entry['index_jki_zero_based'];a=entry['B1'];b=entry['DM065'];only=~np.isin(ix,initial['index_jki_zero_based'],assume_unique=True)
    def counts(mask):
        x,y=a[mask],b[mask];delta=y.astype('f8')-x.astype('f8')
        return {'n':len(x),'B1_negative':int((x<0).sum()),'B1_zero':int((x==0).sum()),'B1_positive':int((x>0).sum()),
                'DM_negative':int((y<0).sum()),'DM_zero':int((y==0).sum()),'DM_positive':int((y>0).sum()),
                'negative_difference_and_DM_negative':int(((delta<0)&(y<0)).sum())}
    r={'status':'PASS','scope':'Only first-entry NR cells numerically changed between arms; no claim for unchanged cells.',
       'global_receipt_sha256':RECEIPT,'source_sha256':sha(Path(__file__)),'all_entry_changed':counts(np.ones(len(ix),dtype=bool)),
       'initial_equal_entry_changed':counts(only),'limitations':['Raw pre-clamp values; not final NR or an error claim.','Unchanged-called cells are absent from the sparse file and their B1 values cannot be inferred from it.']}
    path=P/'entry_nr_signs.json'
    with path.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    print('PASS',sha(path))

if __name__=='__main__':main()
