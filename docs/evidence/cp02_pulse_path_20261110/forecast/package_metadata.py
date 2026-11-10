#!/usr/bin/env python3
"""Retain compact provenance and execution metadata without forecast binaries."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
RUNTIME=HERE.parents[3].parent/'runtime'


def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    result={'schema':'cp02_pulse_forecast_metadata_v1','cases':{}}
    for case in ('CONTROL','MP10'):
        build_path=RUNTIME/'native_build/variants'/case/'build_receipt.json'
        folder=RUNTIME/'forecasts'/case
        prep_path=folder/'prepared.json';run_path=folder/'run_receipt.json';driver_path=RUNTIME/f'{case}_driver_exit.json'
        build=json.loads(build_path.read_text());prep=json.loads(prep_path.read_text());run=json.loads(run_path.read_text());driver=json.loads(driver_path.read_text())
        if any(r['status']!='PASS' for r in (build,run,driver)) or run['exit_code']!=0: raise ValueError('run not passed')
        affinities=[json.loads((folder/f'affinity_rank{rank}.json').read_text()) for rank in range(8)]
        ranks=[]
        for rank in range(8):
            path=folder/f'rsl.out.{rank:04d}'
            lines=path.read_text(errors='replace').splitlines()
            if not any('SUCCESS COMPLETE WRF' in line for line in lines): raise ValueError('missing success marker')
            ranks.append({'rank':rank,'sha256':sha(path),'tail':lines[-5:]})
        result['cases'][case]={'build_receipt_sha256':sha(build_path),'prepared_receipt_sha256':sha(prep_path),
            'run_receipt_sha256':sha(run_path),'driver_receipt_sha256':sha(driver_path),
            'compiler':build['compiler'],'source':build['source'],'compile':build['compile'],
            'object':build['object'],'archive_member_sha256':build['archive_member_sha256'],
            'link':build['link'],'executable':build['executable'],'inputs_unchanged':build['inputs_unchanged'],
            'prepared_input_hashes':prep['inputs'],'cpus':prep['cpus'],'affinity':affinities,
            'start_utc':run['start_utc'],'end_utc':run['end_utc'],'elapsed_seconds':run['elapsed_seconds'],
            'histories':run['histories'],'rsl_sample':ranks}
    result['launch_plan_sha256']=sha(HERE/'launch_plan.json')
    result['comparability_sha256']=sha(HERE/'proof/comparability.json')
    out=HERE/'runtime_metadata.json'
    with out.open('x') as f: json.dump(result,f,indent=2);f.write('\n')


if __name__=='__main__': main()
