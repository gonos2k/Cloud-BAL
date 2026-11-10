#!/usr/bin/env python3
"""Verify packaged provenance and replay actual selected three-step framed samples."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

import numpy as np

HERE=Path(__file__).resolve().parent
NATIVE=HERE.parent
sys.path.insert(0,str(NATIVE/'runs'))
from read_frames import frames


def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    package=HERE/'native_provenance'; inventory=json.loads((package/'inventory.json').read_text())
    if inventory['status']!='PASS': raise ValueError('inventory not PASS')
    for row in inventory['files']:
        p=package/row['path']
        if not p.is_file() or p.stat().st_size!=row['size_bytes'] or sha(p)!=row['sha256'] or p.stat().st_size>=100*1024**2:
            raise ValueError('packaged file mismatch: '+str(p))
        if row['encoding']=='gzip':
            with gzip.open(p,'rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=row['original_sha256']: raise ValueError('gzip source mismatch')
    schema=json.loads((NATIVE/'schema/schema.json').read_text())
    cells={(int(r['wrf_i_1based']),int(r['wrf_j_1based'])) for r in csv.DictReader((NATIVE/'source/columns.csv').open())}
    expected={(step,i,j,k) for step in range(1,4) for i,j in cells for k in range(1,40)}
    for arm in ('FIX','CONSERVATIVE','ICE_FIXED'):
        folder=package/arm; counts={int(k):len(v['fields']) for k,v in schema['phases'].items()}
        absent=schema['arm_overrides']['FIX']['absent_phases'] if arm=='FIX' else schema['arm_overrides']['CONSERVATIVE and ICE_FIXED']['absent_phases']
        for p in absent: counts.pop(p)
        if arm!='FIX': counts[10]=len(schema['arm_overrides']['CONSERVATIVE and ICE_FIXED']['phase_10_fields'])
        for rank in range(8):
            if 'SUCCESS COMPLETE WRF' not in (folder/'run'/f'rsl.out.{rank:04d}').read_text(errors='replace'): raise ValueError('rank completion missing')
            lines=(folder/'sample'/f'state_calls_rank{rank}_first3.txt').read_text().splitlines()
            if {int(line.split()[0]) for line in lines}!={1,2,3}: raise ValueError('call inventory coverage missing')
        for stage,stage_id in (('entry',6),('return',7)):
            seen=set(); header=struct.Struct('>8s15i'); dtype=np.dtype([('i','>i4'),('j','>i4'),('k','>i4'),('v','>f4',(16,))])
            for path in sorted((folder/'sample').glob(f'state_selected_{stage}_t*.bin.gz')):
                with gzip.open(path,'rb') as f:
                    while raw:=f.read(header.size):
                        if len(raw)!=header.size: raise ValueError('truncated state header')
                        magic,sid,rank,call,step,ilo,ihi,jlo,jhi,klo,khi,si,sj,sk,fields,count=header.unpack(raw)
                        if magic!=b'CBSP0001' or sid!=stage_id or fields!=16 or step not in (1,2,3): raise ValueError('state header mismatch')
                        data=f.read(count*dtype.itemsize)
                        if len(data)!=count*dtype.itemsize: raise ValueError('truncated state payload')
                        rows=np.frombuffer(data,dtype=dtype)
                        if not np.isfinite(rows['v']).all(): raise ValueError('nonfinite state')
                        for row in rows:
                            key=(step,int(row['i']),int(row['j']),int(row['k']))
                            if key not in expected or key in seen: raise ValueError('duplicate or unselected state')
                            seen.add(key)
            if seen!=expected: raise ValueError('state sample coverage missing')
        mandatory=(1,2,3,4,5,6,7,8,11,12);seen={p:set() for p in mandatory}
        paths=sorted((folder/'sample').glob('cp04_t*.bin.gz'));presence=json.loads((folder/'sample/process_rank_presence.json').read_text())
        if sorted(presence['present']+presence['absent'])!=list(range(8)) or len(paths)!=len(presence['present']): raise ValueError('process rank inventory mismatch')
        for path in paths:
            with tempfile.NamedTemporaryFile() as tmp, gzip.open(path,'rb') as inp:
                while chunk:=inp.read(1<<20): tmp.write(chunk)
                tmp.flush()
                for header, records in frames(Path(tmp.name),counts):
                    rank,call,step,j,its,ite,kts,kte=header; local={}
                    if rank not in presence['present'] or step not in (1,2,3): raise ValueError('sample frame identity mismatch')
                    for phase,i,k,loop,loops,sub,mstep,values in records:
                        key=(i,k,loop,sub,mstep)
                        if (phase,key) in local: raise ValueError('duplicate process sample record')
                        local[(phase,key)]=1
                        if phase in seen:
                            point=(step,i,j,k)
                            if point not in expected or point in seen[phase]: raise ValueError('duplicate or unselected phase')
                            seen[phase].add(point)
                    for pre,post in ((9,10),(20,21)):
                        a={k for p,k in local if p==pre};b={k for p,k in local if p==post}
                        if a!=b: raise ValueError('unpaired sampled sedimentation')
                        face=23 if arm=='FIX' and pre==20 else 18 if pre==9 else 22
                        if (arm!='FIX' or pre==20) and {k for p,k in local if p==face}!=a: raise ValueError('sampled face mismatch')
        if any(x!=expected for x in seen.values()): raise ValueError('mandatory sample phase coverage missing')
    rows=list(csv.DictReader((package/'surface_endpoint_bindings.csv').open()))
    if len(rows)!=3*7*77 or len({(r['arm'],r['hour'],r['i_1based'],r['j_1based']) for r in rows})!=len(rows) or any(r['source_rain_float32_hex']!=r['history_rainnc_float32_hex'] for r in rows): raise ValueError('surface endpoint binding differs')
    result={'status':'PASS','package_inventory_sha256':sha(package/'inventory.json'),'package_files':len(inventory['files']),
            'sample_steps':[1,2,3],'arms':3,'native_columns':len(cells),'levels':39,'surface_endpoint_rows':len(rows),'verifier_sha256':sha(Path(__file__))}
    (HERE/'provenance_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
