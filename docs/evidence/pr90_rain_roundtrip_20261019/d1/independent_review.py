import gzip, json, hashlib, struct, sys, time
from pathlib import Path

MAGIC_FIELDS={b'PR85QND2':12,b'PR85QNB1':12,b'PR85PLB1':5}

def records(path):
    with gzip.open(path,'rb') as f:
        while True:
            magic=f.read(8)
            if not magic: return
            if len(magic)!=8: raise RuntimeError('truncated magic')
            labelraw=f.read(32); header=f.read(60)
            if len(labelraw)!=32 or len(header)!=60: raise RuntimeError('truncated record header')
            kind,ts,rk,*b=struct.unpack('>15i',header)
            nf=MAGIC_FIELDS.get(magic)
            if nf is None: raise RuntimeError(f'unknown magic {magic!r}')
            expected=1 if magic != b'PR85PLB1' else 2
            if kind!=expected: raise RuntimeError(f'kind mismatch {kind} {magic!r}')
            cells=(b[9]-b[8]+1)*(b[11]-b[10]+1)*(b[7]-b[6]+1)
            if cells<=0: raise RuntimeError(f'invalid bounds {b}')
            nbytes=cells*4*nf
            h=hashlib.sha256(); h.update(magic+labelraw+header)
            left=nbytes
            while left:
                chunk=f.read(min(1024*1024,left))
                if not chunk: raise RuntimeError(f'truncated payload ts={ts} label={labelraw!r}')
                h.update(chunk); left-=len(chunk)
            if ts<=6:
                yield (magic.decode(),labelraw.decode('ascii').strip(),kind,ts,rk,tuple(b),cells,nbytes,h.hexdigest())

def compare(a,b):
    ia,ib=iter(records(a)),iter(records(b)); n=0; per={}; first=None
    while True:
        ra=next(ia,None); rb=next(ib,None)
        if ra is None or rb is None:
            if ra is not None or rb is not None: first={'end_mismatch': [ra,rb]}
            break
        n+=1
        per[ra[3]]=per.get(ra[3],0)+1
        if ra!=rb and first is None: first={'index':n,'d1':ra,'c5':rb}
    return {'records_compared':n,'records_per_timestep':per,'bitwise_equal':first is None,'first_difference':first}

if __name__=='__main__':
  started=time.time(); out=compare(Path(sys.argv[1]),Path(sys.argv[2])); out['elapsed_seconds']=time.time()-started
  print(json.dumps(out,sort_keys=True))
