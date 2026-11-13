#!/usr/bin/env python3
"""Validate rank-local wrapper-return dumps without filling unsupported cells."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

FIELDS = ('QI', 'QS', 'NI', 'DEN', 'TH', 'PII', 'P', 'QV', 'DELZ')
SHAPE = (39, 282, 234)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--step', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    ownership = np.zeros(SHAPE, dtype=np.uint8)
    ranks, stats = [], {name: {'finite': 0, 'nonfinite': 0, 'positive': 0, 'negative': 0,
                               'zero': 0, 'min': None, 'max': None} for name in FIELDS}
    errors = []
    for rank in range(8):
        meta_path = args.run / f'kdm_return_rank{rank}.json'
        metadata = json.loads(meta_path.read_text())
        binary = args.run / metadata['binary_file']
        digest = sha(binary)
        if digest != metadata['binary_sha256'] or metadata['rank'] != rank or metadata['target_step'] != args.step:
            errors.append(f'rank {rank}: binary hash, rank or timestep mismatch')
        if tuple(field['name'] for field in metadata['fields']) != FIELDS:
            errors.append(f'rank {rank}: unexpected fields')
        d = metadata['full_bounds_fortran_1based']
        box = metadata['processed_domain_intersection_fortran_1based']
        i0,i1=box['i'];j0,j1=box['j'];k0,k1=box['k']
        if not (1 <= i0 <= i1 <= SHAPE[2] and 1 <= j0 <= j1 <= SHAPE[1] and 1 <= k0 <= k1 <= SHAPE[0]):
            raise ValueError(f'rank {rank}: out-of-domain box')
        for axis,lo,hi in (('i',i0,i1),('j',j0,j1),('k',k0,k1)):
            expected=(max(d[axis+'ts'],d[axis+'ds']),min(d[axis+'te'],d[axis+'de']-1))
            if (lo,hi)!=expected or lo<d[axis+'ms'] or hi>d[axis+'me']:
                errors.append(f'rank {rank}: {axis} intersection differs')
        count=(i1-i0+1)*(j1-j0+1)*(k1-k0+1)
        if count!=metadata['cell_count']:errors.append(f'rank {rank}: cell count mismatch')
        ownership[k0-1:k1,j0-1:j1,i0-1:i1]+=1
        offset=0
        with binary.open('rb') as stream:
            for field in metadata['fields']:
                n=field['name'];size=4*count
                if field['offset_bytes']!=offset or field['bytes']!=size:errors.append(f'rank {rank}: {n} extent mismatch')
                raw=stream.read(size);offset+=size
                if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=field['sha256']:errors.append(f'rank {rank}: {n} hash/length mismatch');continue
                v=np.frombuffer(raw,dtype='<f4');finite=np.isfinite(v);s=stats[n]
                s['finite']+=int(finite.sum());s['nonfinite']+=int((~finite).sum());s['positive']+=int((v>0).sum());s['negative']+=int((v<0).sum());s['zero']+=int((v==0).sum())
                if finite.any():
                    lo=float(v[finite].min());hi=float(v[finite].max());s['min']=lo if s['min'] is None else min(s['min'],lo);s['max']=hi if s['max'] is None else max(s['max'],hi)
            if stream.read(1):errors.append(f'rank {rank}: trailing bytes')
        wrapper=(d['ite']-d['its']+1)*(d['jte']-d['jts']+1)*(d['kte']-d['kts']+1)
        ranks.append({'rank':rank,'metadata_sha256':sha(meta_path),'binary_sha256':digest,'bounds':box,'captured_cells':count,'full_wrapper_iterations':wrapper,'excluded_wrapper_iterations':wrapper-count})
    checks={'eight_ranks':len(ranks)==8,'no_capture_errors':not errors,'no_duplicate_domain_cells':not np.any(ownership>1),'all_fields_finite':all(s['nonfinite']==0 for s in stats.values()),'all_eight_rank_success':all('SUCCESS COMPLETE WRF' in (args.run/f'run/rsl.error.{i:04d}').read_text(errors='replace') for i in range(8)),'exit_zero':(args.run/'exit.status').read_text().strip()=='0'}
    result={'status':'PASS' if all(checks.values()) else 'FAIL','step':args.step,'checks':checks,'errors':errors,'ranks':ranks,'coverage':{'domain_shape_kji':SHAPE,'domain_cells':int(ownership.size),'captured_unique_cells':int((ownership==1).sum()),'unsupported_cells':int((ownership==0).sum()),'duplicate_cells':int((ownership>1).sum()),'excluded_wrapper_iterations':sum(r['excluded_wrapper_iterations'] for r in ranks)},'field_statistics':stats,'scope':'KDM wrapper RETURN, processed physical-domain intersection only. DEN/PII/P/DELZ are wrapper inputs; no history values or unsupported-edge fills were used. Recorded step is not a directly captured clock.'}
    args.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'checks':checks,'coverage':result['coverage']},indent=2));return 0 if all(checks.values()) else 1


if __name__=='__main__':
    raise SystemExit(main())
