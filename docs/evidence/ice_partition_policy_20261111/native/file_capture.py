#!/usr/bin/env python3
import hashlib,json,struct,sys
from pathlib import Path
import netCDF4
p=Path(sys.argv[1]); out=Path(sys.argv[2]); cells=[(212,84,20),(199,111,22),(219,236,17),(209,94,17),(192,72,26)]
fields=['QICE','QSNOW','QNICE','AL','ALB','T','P','PB','QVAPOR']
with p.open('rb') as f: sha=hashlib.file_digest(f,'sha256').hexdigest()
assert sha=='9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'
result=[]
with netCDF4.Dataset(p) as ds:
 for i,j,k in cells:
  entry={'cell':[i,j,k],'fields':{}}
  for n in fields:
   v=float(ds.variables[n][0,k-1,j-1,i-1]);entry['fields'][n]={'value':v,'hex_le':struct.pack('<f',v).hex()}
  result.append(entry)
out.write_text(json.dumps({'source':str(p),'sha256':sha,'values':result},indent=2)+'\n')
