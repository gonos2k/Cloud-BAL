#!/usr/bin/env python3
"""Compare extracted operators with all saved whole-routine stage records."""
from pathlib import Path
import json,struct,subprocess,sys,collections,hashlib
root=Path(sys.argv[1]); exe=Path(sys.argv[2]).resolve(); opt=sys.argv[3]
def bits(value): return f'{struct.unpack(">I",struct.pack(">f",float(value)))[0]:08X}'
inputs=[]; expected=[]
for folder in sorted((root/(opt+'_instrumented')).glob('case*')):
 records={}
 for line in (folder/'stages.txt').read_text().splitlines():
  s,loop,i,k,qi,ni,den,aux,t=line.split()
  records[(s,int(loop),int(i),int(k))]=(qi,ni,den,aux)
 for key,values in records.items():
  stage,loop,i,k=key
  if stage not in ['SLOPE','PSD1_PRE','PSD2_PRE','PSD3_PRE']: continue
  qi,ni,den,aux=values
  mode=stage.replace('_PRE','')
  inputs.append(f'{mode} {den} {qi} {ni} 1e-15 10\n')
  if mode=='SLOPE':
   expected.append((mode,bits(ni),bits(aux),str(int(float(qi)>struct.unpack('f',struct.pack('f',1e-15))[0])),str(folder.name),key))
  else:
   post=records[(mode+'_POST',loop,i,k)]
   act=records.get((mode+'_ACTIVE',loop,i,k))
   expected.append((mode,bits(post[1]),bits(act[3] if act else -1),str(int(act is not None)),str(folder.name),key))
run=subprocess.run([str(exe)],input=''.join(inputs),text=True,capture_output=True,check=True)
out=run.stdout.splitlines()
assert len(out)==len(expected),(len(out),len(expected))
errors=[]; counts=collections.Counter()
for actual,exp in zip(out,expected):
 counts[exp[0]]+=1
 if actual.split()!=list(exp[:4]):errors.append({'actual':actual,'expected':exp})
result={'opt':opt,'counts':dict(counts),'failures':len(errors),'first_errors':errors[:10],
 'input_sha256':hashlib.sha256(''.join(inputs).encode()).hexdigest(),'output_sha256':hashlib.sha256(run.stdout.encode()).hexdigest()}
Path(f'oracle_{opt}_inputs.txt').write_text(''.join(inputs))
Path(f'oracle_{opt}_outputs.txt').write_text(run.stdout)
print(json.dumps(result,indent=2))
if errors:raise SystemExit(1)
