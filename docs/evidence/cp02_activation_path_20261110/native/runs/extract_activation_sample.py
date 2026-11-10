#!/usr/bin/env python3
"""Export one genuinely positive-supersaturation activation pair with exact bits."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
from read_frames import frames

NATIVE=Path(__file__).resolve().parents[1]

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    folder=Path(sys.argv[1]);output=Path(sys.argv[2]);schema_path=NATIVE/'schema/schema.json';schema=json.loads(schema_path.read_text());counts={int(k):len(v['fields']) for k,v in schema['phases'].items()};ov=schema['arm_overrides']['CONTROL and MP10'];counts[10]=len(ov['phase_10_fields'])
    for p in ov['absent_phases']:counts.pop(p,None)
    names=schema['phases']['35']['fields']
    for path in sorted(folder.glob('cp04_t*_rank*.bin')):
        for head,records in frames(path,counts):
            rank,call,step,j,*_=head; pre={};post={}
            for phase,i,k,loop,loops,sub,mstep,v in records:
                key=(i,k,loop,loops,sub,mstep)
                if phase==35:pre[key]=v
                elif phase==36:post[key]=v
            if pre.keys()!=post.keys():raise ValueError('activation pairs differ')
            for key,a in pre.items():
                if not a[0]>0:continue
                b=post[key];i,k,loop,loops,sub,mstep=key
                def encode(v):
                    x=np.asarray(v,dtype=np.float32);return {'values':{n:float(z) for n,z in zip(names,x)},'uint32_bits':{n:f'{int(z):08x}' for n,z in zip(names,x.view(np.uint32))}}
                result={'status':'PASS','source':str(path),'source_sha256':sha(path),'schema_sha256':sha(schema_path),'step':step,'rank':rank,'call':call,'i':i,'j':j,'k':k,'loop':loop,'loops':loops,'substep':sub,'mstep':mstep,'phase35':encode(a),'phase36':encode(b)}
                output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(result));return
    raise ValueError('no recorded positive supersaturation activation pair')
if __name__=='__main__':main()
