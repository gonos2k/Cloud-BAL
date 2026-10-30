#!/usr/bin/env python3
"""Dry-mass-weighted water added by reciprocal QRAIN/QSNOW swaps, not closure."""
import hashlib
import json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
PATHS = {'ORIGINAL': ROOT / 'scratch/current_forecast_paper_20261029/run.PomEr8/original/wrfinput_d01',
         'HYDRO': ROOT / 'Cloud-BAL/scratch/cp02_six_hour_20260914/hydro/run/wrfinput_d01'}
EXPECTED = {'ORIGINAL': '5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc',
            'HYDRO': '7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126'}
HOST_CONSTANTS = Path('/var/tmp/firsthour-runtime-plan-20261030/experiment/host/share/module_model_constants.F')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def measure(d):
    def field(n):
        a = d[n][0]
        if np.ma.getmaskarray(a).any() or not np.isfinite(a).all(): raise ValueError(f'invalid {n}')
        return np.asarray(a, dtype=np.float64)
    mu, mub, mx, my = (field(n) for n in ('MU','MUB','MAPFAC_MX','MAPFAC_MY'))
    c1, c2, dnw = (field(n) for n in ('C1H','C2H','DNW'))
    if np.any(mx <= 0) or np.any(my <= 0) or np.any(dnw >= 0): raise ValueError('invalid geometry')
    area = float(d.DX)*float(d.DY)/(mx*my)
    dp = -(c1[:,None,None]*(mu+mub)[None,:,:]+c2[:,None,None])*dnw[:,None,None]
    mass = area[None,:,:]*dp/float(np.float32(9.81))
    if not np.isfinite(mass).all() or np.any(mass <= 0): raise ValueError('invalid layer mass')
    return mass


def main():
    if {n:sha(p) for n,p in PATHS.items()} != EXPECTED: raise ValueError('parent input changed')
    if 'REAL    , PARAMETER :: g = 9.81' not in HOST_CONSTANTS.read_text(): raise ValueError('gravity source mismatch')
    with Dataset(PATHS['ORIGINAL']) as original, Dataset(PATHS['HYDRO']) as hydro:
        mo,mh=measure(original),measure(hydro)
        changes={n:np.asarray(original[n][0],dtype=np.float64)-np.asarray(hydro[n][0],dtype=np.float64) for n in ('QRAIN','QSNOW')}
        if any(x.shape != mo.shape or x.shape != mh.shape for x in changes.values()): raise ValueError('shape mismatch')
        result={}
        for label,mass,sign in [('H_ORIGINAL_QRQS',mh,1),('ORIGINAL_H_QRQS',mo,-1)]:
            contributions={name:float(np.sum(sign*delta*mass,dtype=np.float64)) for name,delta in changes.items()}
            result[label]={'water_increment_kg':contributions,'total_water_increment_kg':sum(contributions.values()),
                           'dry_mass_kg':float(mass.sum()),'cell_count':mass.size}
    if {n:sha(p) for n,p in PATHS.items()} != EXPECTED: raise ValueError('parent changed during read')
    out={'status':'PASS','scope':'All native mass cells, including lateral boundary cells; water imposed at fixed receiving-arm dry mass, not a closed water budget or physical-balance test.',
         'formula':'dm=-(C1H*(MU+MUB)+C2H)*DNW*DX*DY/(MAPFAC_MX*MAPFAC_MY*g); sum(dm*delta_q)',
         'gravity':float(np.float32(9.81)),'gravity_source_path':str(HOST_CONSTANTS),'gravity_source_sha256':sha(HOST_CONSTANTS),
         'parent_sha256':EXPECTED,'arms':result}
    output=Path(__file__).with_name('water_increment.json')
    with output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
