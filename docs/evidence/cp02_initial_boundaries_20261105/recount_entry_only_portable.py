#!/usr/bin/env python3
"""Recount entry-only NR and raw QR statistics from portable derivatives."""
import hashlib,json
from pathlib import Path
import numpy as np
P=Path(__file__).resolve().parent

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    summary=json.loads((P/'entry_only/statistics.json').read_text())
    if summary['status']!='PASS' or sha(P/'results/receipt.json')!=summary['source_receipt_sha256'] or sha(P/'entry_only/entry_only_qr.npz')!=summary['QR_payload_sha256']:
        raise ValueError('source identity differs')
    receipt=json.loads((P/'results/receipt.json').read_text())
    arrays=[]
    for name in ('entry_NR','initial_NR'):
        path=P/'results/sparse'/f'{name}.npz'
        if sha(path)!=receipt['outputs'][f'sparse/{name}.npz']['sha256']:raise ValueError('sparse source differs')
        with np.load(path,allow_pickle=False) as z:arrays.append({k:z[k].copy() for k in z.files})
    en,ini=arrays;mask=~np.isin(en['index_jki_zero_based'],ini['index_jki_zero_based'],assume_unique=True)
    ix=en['index_jki_zero_based'][mask];d=en['DM065'][mask].astype('f8')-en['B1'][mask].astype('f8')
    with np.load(P/'entry_only/entry_only_qr.npz',allow_pickle=False) as z:
        if not np.array_equal(ix,z['index_jki_zero_based']):raise ValueError('entry-only keys differ')
        a=z['B1_QR'];b=z['DM065_QR'];bins={'both_QR_zero':int(((a==0)&(b==0)).sum()),'both_QR_positive':int(((a>0)&(b>0)).sum()),'B1_positive_DM_zero':int(((a>0)&(b==0)).sum()),'B1_zero_DM_positive':int(((a==0)&(b>0)).sum()),'either_QR_negative':int(((a<0)|(b<0)).sum())}
    q=np.quantile(abs(d),[0,.25,.5,.75,.99,1],method='linear')
    if len(ix)!=summary['count'] or int((d>0).sum())!=summary['positive_DM_minus_B1'] or int((d<0).sum())!=summary['negative_DM_minus_B1'] or bins!=summary['QR_sign_partition'] or dict(zip(('min_nonzero','q25','median','q75','q99','max'),map(float,q)))!=summary['abs_NR_delta_per_kg_quantiles']:
        raise ValueError('statistics differ')
    print(json.dumps({'status':'PASS_PORTABLE_ENTRY_ONLY_RECOUNT','count':len(ix),'statistics_sha256':sha(P/'entry_only/statistics.json'),'source_sha256':sha(Path(__file__))}))

if __name__=='__main__':main()
