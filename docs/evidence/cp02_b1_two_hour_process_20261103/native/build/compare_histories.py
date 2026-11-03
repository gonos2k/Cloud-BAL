from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import netCDF4
import numpy as np

ROOT=Path('/var/tmp/b1-two-hour-probe-20261103')
HOURS=(12,13,14)

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):
            h.update(b)
    return h.hexdigest()

def value_signature(value):
    a=np.asarray(value)
    if a.dtype.kind in 'biufc':
        native=a.astype(a.dtype.newbyteorder('='),copy=False)
        return ('numeric',a.dtype.str,a.shape,native.tobytes(order='C'))
    if a.dtype.kind=='O':
        return ('object',a.shape,tuple((type(x).__name__,repr(x)) for x in a.flat))
    return ('other',a.dtype.str,a.shape,a.tobytes())

def canonical_array(var):
    a=np.ma.asarray(var[:])
    data=np.asarray(a.data)
    mask=np.ma.getmaskarray(a)
    return (value_signature(data),mask.shape,mask.tobytes())

def compare(new_path:Path,ref_path:Path)->dict:
    with netCDF4.Dataset(new_path) as new, netCDF4.Dataset(ref_path) as ref:
        assert new.dimensions.keys()==ref.dimensions.keys(),(new_path,ref_path,'dimension names differ')
        for name in new.dimensions:
            assert len(new.dimensions[name])==len(ref.dimensions[name]),(name,'dimension size differs')
            assert new.dimensions[name].isunlimited()==ref.dimensions[name].isunlimited(),(name,'unlimited dimension status differs')
        assert new.variables.keys()==ref.variables.keys(),(new_path,ref_path,'variable names differ')
        for name in new.variables:
            a,b=new.variables[name],ref.variables[name]
            assert a.dimensions==b.dimensions,(name,'variable dimensions differ')
            assert a.dtype.str==b.dtype.str,(name,'variable datatype differs')
            assert canonical_array(a)==canonical_array(b),(new_path,ref_path,name,'values differ bitwise')
            assert set(a.ncattrs())==set(b.ncattrs()),(name,'variable attribute names differ')
            for attr in a.ncattrs():
                assert value_signature(a.getncattr(attr))==value_signature(b.getncattr(attr)),(name,attr,'variable attribute differs')
        assert set(new.ncattrs())==set(ref.ncattrs()),(new_path,ref_path,'global attribute names differ')
        for name in new.ncattrs():
            a,b=new.getncattr(name),ref.getncattr(name)
            assert value_signature(a)==value_signature(b),(name,'global attribute differs bitwise/exactly')
    return {'new':str(new_path),'reference':str(ref_path),'new_sha256':sha(new_path),'reference_sha256':sha(ref_path),'all_history_values_and_metadata_exact':True}

def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=('OLD','FIX'),required=True)
    args=parser.parse_args()
    refs=json.loads((ROOT/'references.json').read_text())
    case=Path(json.loads((ROOT/'case_plan.json').read_text())['case_receipts'][args.case]['path'])
    reference=Path(refs[args.case]['path'])
    checks=[]
    for hour in HOURS:
        name=f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
        checks.append(compare(case/name,reference/name))
    output={'case':args.case,'status':'PASS','history_prefix_checks':checks,'scope':'all variables (including Times and coordinates), variable/global attributes, dimensions, datatype metadata, and unlimited-dimension status at 12/13/14 UTC compare exactly; numeric payloads and numeric attributes compare bitwise'}
    (case/'history_prefix_comparison.json').write_text(json.dumps(output,indent=2)+'\n')
if __name__=='__main__': main()
