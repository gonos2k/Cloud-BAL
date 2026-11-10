#!/usr/bin/env python3
"""Recount native core water changes and rate integrals by cell, level, and loop."""
import csv
import gzip
import io
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_low_threshold_process_20261110/Cloud-BAL/docs/evidence/cp02_low_threshold_process_20261110/native')
spec = importlib.util.spec_from_file_location('read_frames', HERE / 'read_frames_with_constants.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
schema = json.loads((OLD / 'schema/schema.json').read_text())
ARMS = ('FIX', 'CONSERVATIVE', 'ICE_FIXED')


def nominal(r, cold):
    p = lambda n: r[n + '(i,k)']
    # This line-by-line algebra is diagnostic float64, not a native replay.
    if cold:
        return [-(p('prevp')+p('psdep')+p('pgdep')+p('pinud')+p('pidep')),
                -(p('praut')+p('pracw')+p('piacw')+2*p('paacw')+p('pmulcs')+p('pmulcg')),
                -p('psaut')-p('praci')-p('psaci')-p('pgaci')+p('pinud')+p('pidep')+p('piacw')+p('pmulcs')+p('pmulcg')+p('pmulrs')+p('pmulrg'),
                p('praut')+p('pracw')+p('prevp')-p('piacr')-p('pgacr')-p('psacr')-p('pmulrs')-p('pmulrg'),
                p('psdep')+p('psaut')+p('paacw')-p('pgaut')+p('piacr')*r['delta3']+p('praci')*r['delta3']+p('psaci')-p('pgacs')-p('pracs')*(1-r['delta2'])+p('psacr')*r['delta2'],
                p('pgdep')+p('pgaut')+p('piacr')*(1-r['delta3'])+p('praci')*(1-r['delta3'])+p('psacr')*(1-r['delta2'])+p('pracs')*(1-r['delta2'])+p('pgaci')+p('paacw')+p('pgacr')+p('pgacs')]
    return [-(p('prevp')+p('psevp')+p('pgevp')),
            -(p('praut')+p('pracw')+2*p('paacw')), 0.,
            p('praut')+p('pracw')+p('prevp')+2*p('paacw')-p('pseml')-p('pgeml'),
            p('psevp')-p('pgacs')+p('pseml'), p('pgacs')+p('pgevp')+p('pgeml')]


def run():
    receipt = json.loads((HERE / 'extract_receipt.json').read_text())
    rows = []
    fields = schema['phases']['5']['fields']
    names = ('QV','QC','QI','QR','QS','QG')
    idx = (1,4,5,6,7,8)
    for arm in ARMS:
        path = HERE / receipt['arms'][arm]['output']
        if hashlib.sha256(path.read_bytes()).hexdigest() != receipt['arms'][arm]['output_sha256']:
            raise ValueError('subset hash mismatch')
        counts = {int(k): len(v['fields']) for k, v in schema['phases'].items()}
        override = schema['arm_overrides']['FIX' if arm == 'FIX' else 'CONSERVATIVE and ICE_FIXED']
        for phase in override['absent_phases']: del counts[phase]
        if arm != 'FIX': counts[10] = len(override['phase_10_fields'])
        for header, constants, records in module.frames(path, counts):
            rank, call, step, j, *_ = header
            grouped = {}
            for phase,i,k,loop,loops,sub,mstep,v in records:
                if phase in (5,6,8):
                    key = (i,k,loop,loops)
                    if phase in grouped.setdefault(key, {}): raise ValueError('duplicate endpoint')
                    grouped[key][phase] = v.astype('float64')
            for (i,k,loop,loops), g in grouped.items():
                if set(g) != {5,6,8}: raise ValueError('missing core endpoint')
                r = dict(zip(fields, map(float,g[5])))
                t0c = float(constants[1])
                cold = g[6][2] <= t0c
                dt = float(g[6][17])
                rates = nominal(r, cold)
                actual = [float(g[8][n]-g[6][n]) for n in idx]
                item = dict(arm=arm,step=step,rank=rank,call=call,i=i,j=j,k=k,loop=loop,loops=loops,
                            branch='cold' if cold else 'warm',t_pre_K=float(g[6][2]),dt_s=dt,
                            water_actual=sum(actual),water_rate_integral=sum(rates)*dt,
                            water_actual_minus_rate_integral=sum(actual)-sum(rates)*dt)
                for n, a, rate, pos in zip(names,actual,rates,idx):
                    item[n+'_pre'] = float(g[6][pos]); item[n+'_post'] = float(g[8][pos])
                    item[n+'_actual'] = a; item[n+'_rate_integral'] = rate*dt
                for name, value in r.items(): item['rate_'+name] = value
                rows.append(item)
    rows.sort(key=lambda x:(x['arm'],x['step'],x['j'],x['i'],x['k'],x['loop']))
    out = HERE / 'core_recount.csv.gz'
    with out.open('xb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as z, io.TextIOWrapper(z, encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    print('rows',len(rows),'sha256',hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == '__main__': run()
