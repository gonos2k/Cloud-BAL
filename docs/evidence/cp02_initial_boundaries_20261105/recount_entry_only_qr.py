#!/usr/bin/env python3
"""Describe entry NR differences where same-cell initial NR did not differ."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = ROOT / 'docs/evidence/cp02_initial_boundaries_20261105'
sys.path.insert(0, str(ROOT/'tools'))
import cp02_initial_boundaries as cp
import cp02_state_path as state

EXPECTED = 'f76b74141410d5b287c554467fd0f3803fe9a8c8debceb6e33dd30639aa69681'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run():
    if sha(HERE/'results/receipt.json') != EXPECTED:
        raise ValueError('first-call receipt changed')
    receipt = json.loads((HERE/'results/receipt.json').read_text())
    for name in ('sparse/entry_NR.npz', 'sparse/initial_NR.npz', 'domain_and_support.npz'):
        if sha(HERE/'results'/name) != receipt['outputs'][name]['sha256']:
            raise ValueError('derivative changed')
    cp.verify_plan(HERE/'plan.json')
    inputs=cp.verify_inputs()
    with np.load(HERE/'results/sparse/entry_NR.npz',allow_pickle=False) as data:
        entry_index=data['index_jki_zero_based'].copy();b1=data['B1'].copy();dm=data['DM065'].copy()
    with np.load(HERE/'results/sparse/initial_NR.npz',allow_pickle=False) as data:
        initial_index=data['index_jki_zero_based'].copy()
    only=~np.isin(entry_index,initial_index,assume_unique=True)
    ix=entry_index[only];b1=b1[only];dm=dm[only]
    if len(ix)!=154317 or not np.all(b1!=dm):
        raise ValueError('entry-only selection differs from frozen global result')
    output=HERE/'entry_only'
    if os.path.lexists(output):raise FileExistsError(output)
    stage=Path(tempfile.mkdtemp(prefix='.entry-only-',dir=HERE))
    try:
        with tempfile.TemporaryDirectory(prefix='entry-only-work-',dir=ROOT.parent) as work:
            _,specs=state.load_schema(ROOT/'docs/evidence/cp02_state_path_20261104/native/state_schema.json')
            values={};masks={};owners={}
            for arm in cp.ARMS:
                root=Path(inputs[arm]['root']);calls=state.read_call_inventory(root)
                values[arm],masks[arm],owners[arm],_=state.read_global_stage(root,specs[1],calls,[],cp.SHAPE,Path(work)/arm)
            if not np.array_equal(masks['B1'],masks['DM065']) or not np.array_equal(owners['B1'],owners['DM065']) or not masks['B1'][ix].all():
                raise ValueError('ownership differs')
            for arm,expected in (('B1',b1),('DM065',dm)):
                actual=np.asarray(values[arm][10,ix],dtype=np.float32)
                if not np.array_equal(actual.view('u4'),expected.view('u4')):
                    raise ValueError('sparse entry NR values differ from raw')
            qa=np.asarray(values['B1'][3,ix],dtype=np.float32)
            qb=np.asarray(values['DM065'][3,ix],dtype=np.float32)
            np.savez_compressed(stage/'entry_only_qr.npz',index_jki_zero_based=ix,B1_QR=qa,DM065_QR=qb)
        d=dm.astype(np.float64)-b1.astype(np.float64);mag=np.abs(d)
        if not np.isfinite(d).all() or np.any(mag==0):raise ValueError('invalid nonzero NR difference')
        bins={}
        for name,mask in (('both_QR_zero',(qa==0)&(qb==0)),('both_QR_positive',(qa>0)&(qb>0)),
                          ('B1_positive_DM_zero',(qa>0)&(qb==0)),('B1_zero_DM_positive',(qa==0)&(qb>0)),
                          ('either_QR_negative',(qa<0)|(qb<0))):bins[name]=int(mask.sum())
        if sum(bins.values())!=len(ix):raise ValueError('QR sign partition incomplete')
        cp.verify_plan(HERE/'plan.json')
        if cp.verify_inputs()!=inputs:raise ValueError('raw inputs changed')
        quant=np.quantile(mag,[0,.25,.5,.75,.99,1],method='linear')
        result={'status':'PASS','source_receipt_sha256':EXPECTED,'source_sha256':sha(Path(__file__)),
                'population':'called cells where first wrapper ENTRY NR differs and the same native input QNRAIN values are numerically equal',
                'count':len(ix),'positive_DM_minus_B1':int((d>0).sum()),'negative_DM_minus_B1':int((d<0).sum()),
                'abs_NR_delta_per_kg_quantiles':dict(zip(('min_nonzero','q25','median','q75','q99','max'),map(float,quant))),
                'QR_sign_partition':bins,'B1_QR_positive':int((qa>0).sum()),'DM065_QR_positive':int((qb>0).sum()),
                'QR_payload_sha256':sha(stage/'entry_only_qr.npz'),'QR_payload_bytes':(stage/'entry_only_qr.npz').stat().st_size,
                'limits':'Raw wrapper entry QR signs, no activation threshold. The QNRAIN input and first wrapper entry are different model boundaries; this does not identify an intervening writer or transport mechanism.'}
        (stage/'statistics.json').write_text(json.dumps(result,indent=2)+'\n')
        if os.path.lexists(output):raise FileExistsError(output)
        os.rename(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':run()
