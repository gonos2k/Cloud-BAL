#!/usr/bin/env python3
"""Compare a sparse wrapper-return capture to history without applying it."""
import argparse
import json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset, chartostring
from science_support import sha, stats


def quantiles(x):
    if not x.size: return {'count': 0}
    return {'count': int(x.size), **dict(zip(('min','p01','p10','p25','median','p75','p90','p99','max'), map(float,np.quantile(x,[0,.01,.1,.25,.5,.75,.9,.99,1]))))}


def main():
    p=argparse.ArgumentParser()
    for arg in ('snapshot','receipt','analysis','history','mask','policy','out'):
        p.add_argument('--'+arg,required=True,type=Path)
    a=p.parse_args(); inputs={str(x):sha(x) for x in (a.snapshot,a.receipt,a.analysis,a.history,a.mask,a.policy,Path(__file__).resolve(),Path(__file__).resolve().parent/'science_support.py')}
    receipt=json.loads(a.receipt.read_text())
    if (receipt.get('schema')!='coherent_ice_snapshot_receipt_v1' or receipt.get('status')!='PASS'
        or receipt.get('snapshot_file')!=a.snapshot.name or receipt.get('snapshot_sha256')!=inputs[str(a.snapshot)]):
        raise ValueError('snapshot receipt binding mismatch')
    if receipt.get('snapshot_context',{}).get('baseline_history_sha256')!=inputs[str(a.history)]:
        raise ValueError('history differs from snapshot baseline')
    with np.load(a.mask,allow_pickle=False) as z:
        fixed=z['valid'].astype(bool);analysis_hash=str(z['source_sha256'].item())
    if inputs[str(a.analysis)]!=analysis_hash: raise ValueError('analysis differs from frozen mask identity')
    with Dataset(a.analysis) as d:
        d.set_auto_maskandscale(False);qa=d['QICE'][0].astype(np.float64);sa=d['QSNOW'][0].astype(np.float64)
        den=np.divide(np.float32(1),np.add(d['AL'][0],d['ALB'][0],dtype=np.float32),dtype=np.float32)
    if not np.array_equal(fixed,(qa+sa)>0): raise ValueError('mask differs from frozen analysis')
    with np.load(a.snapshot,allow_pickle=False) as z:
        names=('QI','QS','NI','DEN','TH','PII','P','QV','DELZ'); coverage=z['coverage']
        if coverage.dtype!=np.bool_ or coverage.shape!=fixed.shape: raise ValueError('invalid coverage')
        data={n:z[n] for n in names}
        for n,x in data.items():
            if x.dtype!=np.float32 or x.shape!=fixed.shape: raise ValueError('invalid field '+n)
            if not np.isnan(x[~coverage]).all(): raise ValueError('uncovered cells not NaN in '+n)
    observed=fixed&coverage; missing=fixed&~coverage
    if (int(fixed.sum()),int(observed.sum()),int(missing.sum()))!=(294792,288745,6047): raise ValueError('unexpected frozen-mask coverage; review geometry')
    with Dataset(a.history) as d:
        d.set_auto_maskandscale(False);h={n:d[var][0] for n,var in [('QI','QICE'),('QS','QSNOW'),('NI','QNICE')]};time=chartostring(d['Times'][:]).tolist();cycle=d.SIMULATION_START_DATE
    if time!=['2026-08-16_12:00:00'] or cycle!='2026-08-16_06:00:00': raise ValueError('history time mismatch')
    policy=json.loads(a.policy.read_text()); target=qa+sa
    old=stats(h['QI'],h['QS'],h['NI'],observed,policy,target,den);coherent=stats(data['QI'],data['QS'],data['NI'],observed,policy,target,den)
    qi=data['QI'].astype(np.float64);qs=data['QS'].astype(np.float64);ni=data['NI'].astype(np.float64);total=qi+qs
    valid=observed&np.isfinite(qi)&np.isfinite(qs)&np.isfinite(ni)&(qi>0)&(qs>=0)&(ni>0)&(total>0)
    fraction=np.zeros(fixed.shape);mean=np.zeros(fixed.shape);alpha=np.zeros(fixed.shape)
    np.divide(qi,total,out=fraction,where=valid);np.divide(qi,ni,out=mean,where=valid);np.divide(target,total,out=alpha,where=valid)
    result={'scope':'Read-only diagnostic on the frozen mask intersection with actual snapshot coverage. The 6047 uncovered selected cells remain unavailable; no candidate, acceptance, modified mask, confidence policy, or substitute prior is generated. Source ABI, target event, timing, geometry and provenance require independently verified assembler receipt and native execution review. Pair support and cap observations are not the full Fortran transaction or new-first-use validation.','input_sha256':inputs,'receipt_schema':receipt.get('schema'),'coverage':{'whole_fixed_selected':int(fixed.sum()),'covered_selected':int(observed.sum()),'uncovered_selected':int(missing.sum()),'full_grid_covered':int(coverage.sum()),'full_grid_uncovered':int((~coverage).sum())},'history_same_covered_cells':old,'coherent_return_covered_cells':coherent,'covered_word_differences':{n:int((observed&(data[n].view('u4')!=h[n].view('u4'))).sum()) for n in ('QI','QS','NI')},'positive_pair_context':{'description':'Positive QI and NI, nonnegative QS, finite captured values; descriptive distribution, no confidence cutoff.','background_total_kg_kg':quantiles(total[valid]),'fraction_qi_over_total':quantiles(fraction[valid]),'mean_kg_particle':quantiles(mean[valid]),'analysis_over_background_total':quantiles(alpha[valid])},'density_scope':'Rounded proposal NI cap uses analysis-file REAL32 1/(AL+ALB), not captured DEN; captured DEN is separate same-call background context.','uncovered_data':'NaN for all nine fields; excluded only from descriptive covered-cell comparisons, never from frozen mask or a production transaction.'}
    a.out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(result,indent=2,allow_nan=False))
if __name__=='__main__':main()
