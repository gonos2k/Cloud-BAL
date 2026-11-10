#!/usr/bin/env python3
"""Check all retained water and number model fields are finite in seven histories."""
import hashlib,json
from pathlib import Path
import netCDF4
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
RUNTIME=ROOT.parent/'runtime/nn_end'
FIELDS=('QVAPOR','QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QNCCN','QNCLOUD','QNICE','QIB','QNRAIN')

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    runpath=RUNTIME/'forecasts/MP10_NN_END/run_receipt.json';run=json.loads(runpath.read_text())
    if run['status']!='PASS' or len(run['histories'])!=7:raise ValueError('forecast not complete')
    results=[]
    for row in run['histories']:
        path=Path(row['path'])
        if sha(path)!=row['sha256']:raise ValueError('history changed before finite audit')
        counts={}
        with netCDF4.Dataset(path) as ds:
            ds.set_auto_maskandscale(False)
            for name in FIELDS:
                if name not in ds.variables:raise ValueError('missing water/number field '+name)
                values=np.asarray(ds.variables[name][:]);bad=int((~np.isfinite(values)).sum())
                if bad:raise ValueError(f'nonfinite values in {path} {name}: {bad}')
                counts[name]={'values':int(values.size),'nonfinite':bad}
        if sha(path)!=row['sha256']:raise ValueError('history changed during finite audit')
        results.append({'name':path.name,'sha256':row['sha256'],'fields':counts})
    result={'status':'PASS','run_receipt_sha256':sha(runpath),'fields':FIELDS,'histories':results,'scope':'finite values only; no conservation or sign claim'}
    (HERE/'finite_sanity.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS',len(results),'histories',len(FIELDS),'fields')
if __name__=='__main__':main()
