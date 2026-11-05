#!/usr/bin/env python3
"""Preserve completed four-run receipts and small logs; large histories remain hash-bound externally."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[4]
BUNDLE=ROOT/'docs/evidence/cp02_grouped_forecast_20261105'
RUNTIME=ROOT.parent/'runtime/forecasts'


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    out=BUNDLE/'runtime/completed'
    out.mkdir(exist_ok=False)
    rows=[]
    for case in ('SHAM_A','SHAM_B','C','D'):
        source=RUNTIME/case
        receipt=json.loads((source/'run_receipt.json').read_text())
        if receipt['status']!='PASS' or len(receipt['histories'])!=7:
            raise ValueError('incomplete model run: '+case)
        dest=out/case;dest.mkdir()
        names=['prepared.json','run_receipt.json','descendants.json','namelist.input']
        names += [f'affinity_rank{rank}.json' for rank in range(8)]
        logs=['launcher.log']+[f'rsl.{kind}.{rank:04d}' for kind in ('out','error') for rank in range(8)]
        for name in names+logs:
            path=source/name;before=sha(path)
            target=dest/(name+'.gz' if name in logs else name)
            if name in logs:target.write_bytes(gzip.compress(path.read_bytes(),mtime=0))
            else:shutil.copyfile(path,target)
            if sha(path)!=before:raise ValueError('run artifact changed during packaging')
            rows.append({'source_path':str(path),'source_sha256':before,'packaged_path':str(target.relative_to(ROOT)),
                         'packaged_sha256':sha(target),'compressed':name in logs})
    result={'status':'PASS_FOUR_COMPLETED_SIX_HOUR_RUNS','files':rows,
            'large_external_artifacts':'ELF, libraries and full NetCDF histories remain at exact receipt paths with SHA-256; compact RN1 arrays are separately tracked.'}
    with (BUNDLE/'runtime/package_receipt.json').open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print('PASS:',len(rows),'packaged artifacts')


if __name__=='__main__':main()
