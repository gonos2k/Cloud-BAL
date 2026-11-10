"""Read original or gzip CBSP0001 selected wrapper records without precision loss."""
import gzip, struct
from pathlib import Path
import numpy as np

HEADER=struct.Struct('>8s15i')
ROW=np.dtype([('i','>i4'),('j','>i4'),('k','>i4'),('v','>f4',(16,))])
FIELDS=('TH','QV','QC','QR','QI','QS','QG','NN','NC','NI','NR','BG','DEN','TK','P','PII')

def read_wrapper(paths, stage, steps, cells):
    """Return values [step,column,k,field], validity, preserving float32 bits.

    stage is 6 for entry or 7 for return. Cells are Fortran (i,j) pairs;
    steps are actual WRF outer timesteps. Missing/duplicate rows raise.
    """
    if stage not in (6,7):raise ValueError('stage must be 6 or 7')
    steps=tuple(steps);cells=tuple(cells)
    if len(set(steps))!=len(steps) or len(set(cells))!=len(cells):raise ValueError('duplicate axis')
    ix={s:n for n,s in enumerate(steps)}; ci={cell:n for n,cell in enumerate(cells)}
    values=np.empty((len(steps),len(cells),39,16),np.float32);valid=np.zeros(values.shape[:3],bool)
    for path in sorted(map(Path,paths)):
        with (gzip.open(path,'rb') if path.suffix=='.gz' else path.open('rb')) as f:
            while raw:=f.read(HEADER.size):
                if len(raw)!=HEADER.size:raise ValueError('truncated header')
                magic,sid,rank,call,step,ilo,ihi,jlo,jhi,klo,khi,si,sj,sk,nfields,nrows=HEADER.unpack(raw)
                if magic!=b'CBSP0001' or sid!=stage or (si,sj,sk,nfields)!=(1,1,1,16) or nrows<0:raise ValueError('invalid wrapper header')
                data=f.read(nrows*ROW.itemsize)
                if len(data)!=nrows*ROW.itemsize:raise ValueError('truncated rows')
                if step not in ix:continue
                for row in np.frombuffer(data,dtype=ROW):
                    i,j,k=map(int,(row['i'],row['j'],row['k']));column=ci.get((i,j))
                    if column is None:continue
                    if not (ilo<=i<=ihi and jlo<=j<=jhi and klo<=k<=khi and 1<=k<=39):raise ValueError('record outside bounds')
                    index=(ix[step],column,k-1)
                    if valid[index]:raise ValueError('duplicate wrapper record')
                    values[index]=row['v'];valid[index]=True
    if not valid.all():raise ValueError(f'incomplete wrapper records: {valid.sum()} / {valid.size}')
    tk=np.multiply(values[...,0],values[...,15],dtype=np.float32)
    if not np.array_equal(tk.view(np.uint32),values[...,13].view(np.uint32)):raise ValueError('TH * PII does not reproduce TK bits')
    return values,valid
