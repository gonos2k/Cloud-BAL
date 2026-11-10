#!/usr/bin/env python3
"""Copy and hash native build, probe, forecast and comparison receipts."""
import hashlib,json,shutil
from pathlib import Path

NATIVE=Path(__file__).resolve().parents[1]
RUNTIME=NATIVE.parents[3].parent/'runtime'

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    inventory={}
    for arm in ('CONTROL','MP10'):
        out=NATIVE/'proof'/arm;out.mkdir(exist_ok=False)
        sources={'build':RUNTIME/'native_build/variants'/arm,'probe':RUNTIME/'probe'/arm,'run':RUNTIME/'forecasts'/arm}
        selected={'build':['build_receipt.json','compile.log','link.log','ldd.txt'],
                  'probe':['probe_receipt.json','probe_validation.json','namelist.input','launcher.log'],
                  'run':['prepared.json','run_receipt.json','history_comparison.json','shared_comparison.json','descendants.json','namelist.input','launcher.log']}
        rows=[]
        for group,names in selected.items():
            for name in names:
                source=sources[group]/name
                if not source.exists():raise FileNotFoundError(source)
                target=out/(group+'_'+name);before=sha(source);shutil.copyfile(source,target)
                if sha(target)!=before or sha(source)!=before:raise ValueError('provenance copy differs')
                rows.append({'source':str(source),'name':target.name,'sha256':before,'size_bytes':target.stat().st_size})
        driver=RUNTIME/f'{arm}_driver_exit.json';target=out/'driver_exit.json';before=sha(driver);shutil.copyfile(driver,target)
        if sha(target)!=before:raise ValueError('driver copy differs')
        rows.append({'source':str(driver),'name':target.name,'sha256':before,'size_bytes':target.stat().st_size})
        inventory[arm]=rows
    (NATIVE/'proof/provenance_inventory.json').write_text(json.dumps({'status':'PASS','arms':inventory},indent=2)+'\n')
if __name__=='__main__':main()
