#!/usr/bin/env python3
"""Preserve and hash the completed candidate build, probe and forecast receipts."""
import hashlib,json,shutil
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
RUNTIME=ROOT.parent/'runtime/nn_end'

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    proof=HERE/'comparability.json'
    if json.loads(proof.read_text())['status']!='PASS':raise ValueError('comparability not passed')
    build=RUNTIME/'native_build/variants/MP10_NN_END';diagnostic=RUNTIME/'native_build/variants/MP10_NN_END_PROBE';probe=RUNTIME/'probe';run=RUNTIME/'forecasts/MP10_NN_END'
    groups={'build':(build,['build_receipt.json','compile.log','link.log','ldd.txt']),'probe_build':(diagnostic,['build_receipt.json','compile.log','link.log','ldd.txt']),'probe':(probe,['probe_receipt.json','namelist.input','launcher.log']),'run':(run,['prepared.json','run_receipt.json','namelist.input','launcher.log','descendants.json'])}
    out=HERE/'records';out.mkdir(exist_ok=False);rows=[]
    for group,(folder,names) in groups.items():
        for name in names:
            path=folder/name;target=out/(group+'_'+name);before=sha(path);shutil.copyfile(path,target)
            if sha(target)!=before or sha(path)!=before:raise ValueError('provenance copy changed')
            rows.append({'source':str(path),'name':target.name,'sha256':before,'size_bytes':target.stat().st_size})
    result={'status':'PASS','comparability_sha256':sha(proof),'records':rows}
    (HERE/'provenance_inventory.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
