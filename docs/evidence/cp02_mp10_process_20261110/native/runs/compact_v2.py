#!/usr/bin/env python3
"""Preserve selected keyed native bits in bounded three-step phase-group files."""
import csv, gzip, hashlib, json, re, sys
from pathlib import Path
import numpy as np
from read_frames_constants import frames

NATIVE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[5]
RUNTIME=ROOT.parent/'runtime/forecasts'
GROUPS={'constants':{0},'state':{30,32,33,34},'core':{1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,20,21},'faces':{18,22},'surface':{40,41,42,43,46,47,51,52,53,60,61,62,63,70,71,72,73}}
KEYS=['step','rank','call','j','i','k','loop','loops','substep','mstep','phase','nfields']
LIMIT=80000000
MAX_ROWS=150000

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    arm=sys.argv[1]
    if arm not in ('CONTROL','MP10'):raise ValueError('bad arm')
    case=RUNTIME/arm
    schema=json.loads((NATIVE/'schema/schema.json').read_text())
    counts={int(k):len(v['fields']) for k,v in schema['phases'].items()}
    overrides=schema['arm_overrides']['CONTROL and MP10']
    for phase in overrides['absent_phases']:counts.pop(phase,None)
    counts[10]=len(overrides['phase_10_fields'])
    cells={(int(r['i_fortran']),int(r['j_fortran'])) for r in csv.DictReader((NATIVE.parent/'cohorts/native_columns.csv').open())}
    out=NATIVE/'compact'/arm;out.mkdir(parents=True,exist_ok=False)
    files=[];raw=[]
    def save(name, keys, vals, dtype, width):
        keys=np.asarray(keys,dtype=np.int32)
        values=np.zeros((len(vals),width),dtype=dtype)
        for i,v in enumerate(vals):values[i,:len(v)]=v
        path=out/name
        with path.open('xb') as f:np.savez_compressed(f,keys=keys,bits=values)
        if path.stat().st_size>=LIMIT:raise ValueError('bounded artifact exceeds 80 MB: '+str(path))
        files.append({'name':path.name,'size_bytes':path.stat().st_size,'sha256':sha(path),'records':len(keys)})
    def chunk(paths, group, first):
        selected=GROUPS[group];is64=group=='faces';width=10 if group=='constants' else max(counts[p] for p in selected)
        keys=[];vals=[];part=0; observed={}; sediment={9:set(),10:set(),20:set(),21:set()}
        for path in paths:
            raw.append({'name':path.name,'sha256':sha(path),'size_bytes':path.stat().st_size})
            for head,constants,records in frames(path,counts):
                rank,call,step,j,its,ite,kts,kte=head
                if not first<=step<=first+2 or (kts,kte)!=(1,39):raise ValueError('unexpected frame')
                if group=='constants':
                    keys.append((step,rank,call,j,0,0,0,0,0,0,0,len(constants)))
                    vals.append(constants.astype(np.float32).view(np.uint32))
                for phase,i,k,loop,loops,sub,mstep,v in records:
                    if (i,j) not in cells:raise ValueError('outside selector')
                    if phase not in selected:continue
                    if group=='core' and phase in sediment:
                        event=(step,i,j,k,loop,sub,mstep)
                        if event in sediment[phase]:raise ValueError('duplicate sediment record')
                        sediment[phase].add(event)
                    if group in ('state','surface'):
                        key=(phase,step,i,j,k,loop)
                        if key in observed: raise ValueError('duplicate required record')
                        observed[key]=v.astype(np.float32).view(np.uint32).copy()
                    keys.append((step,rank,call,j,i,k,loop,loops,sub,mstep,phase,len(v)))
                    vals.append(v.astype(np.float64 if is64 else np.float32).view(np.uint64 if is64 else np.uint32))
                    if len(keys)>=MAX_ROWS:
                        save(f'{group}_{first:06d}_{part:03d}.npz',keys,vals,np.uint64 if is64 else np.uint32,width);keys=[];vals=[];part+=1
        if keys:save(f'{group}_{first:06d}_{part:03d}.npz',keys,vals,np.uint64 if is64 else np.uint32,width)
        steps=range(first,min(first+2,1080)+1); nloops=1 if arm=='CONTROL' else 2
        if group=='state':
            required={(p,t,i,j,k,l) for p in (30,32,33,34) for t in steps for i,j in cells for k in range(1,40) for l in range(1,nloops+1)}
            if set(observed)!=required: raise ValueError(f'state coverage mismatch at {first}: {len(observed)} / {len(required)}')
            if nloops==2:
                for t in steps:
                    for i,j in cells:
                        for k in range(1,40):
                            if not np.array_equal(observed[34,t,i,j,k,1],observed[30,t,i,j,k,2]):raise ValueError('loop carry bits differ')
        if group=='core':
            if not sediment[9] or sediment[9]!=sediment[10] or not sediment[20] or sediment[20]!=sediment[21]:raise ValueError('sedimentation pre/post coverage mismatch')
        if group=='surface':
            for t in steps:
                for i,j in cells:
                    for p in (40,41):
                        if (p,t,i,j,1,0) not in observed:raise ValueError('missing reset record')
                    for l in range(1,nloops+1):
                        for p in (42,43):
                            if (p,t,i,j,1,l) not in observed:raise ValueError('missing loop surface record')
                        if ((46,t,i,j,1,l) in observed)!=((47,t,i,j,1,l) in observed):raise ValueError('unpaired executed rain update')
                        if l>1 and not np.array_equal(observed[43,t,i,j,1,l-1],observed[42,t,i,j,1,l]):raise ValueError('surface loop carry differs')

    for stem,groups in [('cp04',('constants','state','core','faces')),('surface',('surface',))]:
        paths=sorted(case.glob(stem+'_t*_rank*.bin')); chunks={}
        for p in paths:
            m=re.fullmatch(stem+r'_t(\d{6})-(\d{6})_rank\d+\.bin',p.name)
            if not m:raise ValueError('bad filename '+p.name)
            first,last=map(int,m.groups())
            if first%3!=1 or last!=min(first+2,1080):raise ValueError('bad chunk')
            chunks.setdefault(first,[]).append(p)
        expected=set(range(1,1081,3)) if stem=='surface' else set(range(1,181,3))|set(range(361,541,3))|set(range(901,1081,3))
        if set(chunks)!=expected:raise ValueError('missing or extra chunks '+stem)
        for first,paths in sorted(chunks.items()):
            for group in groups:chunk(paths,group,first)
    for path in sorted(case.glob('state_selected_*_t*_rank*.bin')):
        target=out/(path.name+'.gz')
        with path.open('rb') as inp,target.open('xb') as rawout:
            with gzip.GzipFile(filename='',mode='wb',fileobj=rawout,mtime=0) as z:
                while data:=inp.read(1024*1024):z.write(data)
        if target.stat().st_size>=LIMIT:raise ValueError('wrapper artifact too large')
        files.append({'name':target.name,'size_bytes':target.stat().st_size,'sha256':sha(target)})
        raw.append({'name':path.name,'sha256':sha(path),'size_bytes':path.stat().st_size})
    if not any(x['name'].startswith('state_selected_entry') for x in files) or not any(x['name'].startswith('state_selected_return') for x in files):raise ValueError('missing wrapper streams')
    receipt={'status':'COMPLETE','arm':arm,'keys':KEYS,'integer_bits':'native REAL32 represented as uint32; faces REAL64 as uint64','padding':'bits after nfields ignored; absent key means missing','sources':raw,'outputs':files,'schema_sha256':sha(NATIVE/'schema/schema.json'),'source_receipt_sha256':sha(NATIVE/'source/source_receipt.json')}
    (out/'capture_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':main()
