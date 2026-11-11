#!/usr/bin/env python3
import json,sys,struct
from pathlib import Path
j=json.loads(Path(sys.argv[1]).read_text()); out=Path(sys.argv[2]); out.mkdir(exist_ok=True)
def f32(x): return struct.unpack('f',struct.pack('f',x))[0]
variants=['QNICE','NI_nominal_maximum_mass_kg-1','NI_fixed_50um_kg-1']
meta=[]
for n,case in enumerate(j['cases']):
 p=case['profiles']
 for variant in variants:
  name=f'case{n}_{variant}'; meta.append({'name':name,'roles':case['roles'],'variant':variant})
  with (out/(name+'.txt')).open('w') as f:
   print(case['XLAND'],file=f)
   for k in range(39):
    vals=[f32(p['T'][k]+300),p['dry_tk'][k],f32(p['P'][k]+p['PB'][k]),p['den'][k],p['DELZ'][k]]
    vals += [p[a][k] for a in ['QVAPOR','QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QNCCN','QNCLOUD',variant,'QNRAIN','QIB']]
    print(*[format(x,'.17g') for x in vals],file=f)
(out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
