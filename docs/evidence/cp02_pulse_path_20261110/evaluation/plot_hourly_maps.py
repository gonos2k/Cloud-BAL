#!/usr/bin/env python3
"""Map six hourly rainfall amounts at the sealed RN1 verification points."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm
import numpy as np

import evaluate as e
sys.path.insert(0,str(e.ROOT/'tools'))
import plot_cp02_ice_false_alarm as resources

CASES=('reference',e.ORIGINAL,e.B1,e.CONS,e.ICE,e.NEW)
LABELS=('RN1 관측','규준실험 (ORIGINAL)','현재 B1','PR153','PR154','MP10')


def load(results):
    receipt=results/'receipt.json';meta=json.loads(receipt.read_text())
    if meta['status']!='COMPLETE':raise ValueError('evaluation is incomplete')
    inputs=[e.identity(receipt),e.identity(resources.FONT),e.identity(resources.COAST),e.identity(resources.__file__),e.identity(e.__file__),e.identity(e.prior.__file__)]
    for hour in e.HOURS:
        path=results/f'hour_{hour}_arrays.npz'
        if path.is_symlink() or e.identity(path)['sha256']!=meta['outputs'][path.name]:raise ValueError('array identity mismatch')
        inputs.append(e.identity(path))
    arrays=e.prior.read_arrays(results)
    e.score(arrays)
    return arrays,inputs


def write_data(out,arrays):
    with (out/'hourly_rainfall_points.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['lead_hour','flat_index_yx','latitude','longitude',*CASES])
        for hour in e.HOURS:
            v=arrays[hour]
            for i in range(3688):w.writerow([hour-12,int(v['flat_index_yx'][i]),v['latitude'][i],v['longitude'][i],*[v[k][i] for k in CASES]])


def render(out,arrays,coast):
    maximum=max(float(np.max(arrays[h][case])) for h in e.HOURS for case in CASES)
    edges=[0,.1,.5,1,2.5,5,10,20,50,100,max(100.,maximum)+1]
    norm=BoundaryNorm(edges,256,clip=True)
    lon,lat=arrays[13]['longitude'],arrays[13]['latitude']
    for hour in e.HOURS:
        fig,axes=plt.subplots(2,3,figsize=(14,9),sharex=True,sharey=True,constrained_layout=True)
        for ax,case,label in zip(axes.flat,CASES,LABELS):
            artist=ax.scatter(lon,lat,c=arrays[hour][case],s=9,cmap='viridis',norm=norm,linewidths=0,rasterized=True,zorder=3)
            for line in coast:ax.plot(line[:,0],line[:,1],color='#333333',linewidth=.5,zorder=4)
            ax.set_title(label);ax.set_xlim(float(lon.min()),float(lon.max()));ax.set_ylim(float(lat.min()),float(lat.max()))
            ax.set_aspect(1/np.cos(np.deg2rad(float(lat.mean()))),adjustable='box');ax.grid(alpha=.17,linewidth=.4)
        for ax in axes[-1,:]:ax.set_xlabel('경도 (°E)')
        for ax in axes[:,0]:ax.set_ylabel('위도 (°N)')
        fig.colorbar(artist,ax=axes.ravel().tolist(),label='한 시간 강수량 (mm)',ticks=edges[:-1],shrink=.8)
        fig.suptitle(f'2026-08-16 12:00 UTC 초기화 · +{hour-12} h · {hour-1:02d}:00–{hour:02d}:00 UTC\nRN1 평가점 3,688개 · 점별 강수량 · 추가 공간보간 없음 · 공통 색 구간')
        fig.savefig(out/f'hour_{hour-12}_rainfall.png',dpi=170,metadata={'Software':'Cloud-BAL MP10 hourly maps'});plt.close(fig)
    return edges


def run(results,output):
    if os.path.lexists(output):raise FileExistsError(output)
    arrays,inputs=load(results);coast=resources.resources()
    output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.mp10-rain-map-',dir=output.parent))
    try:
        edges=render(stage,arrays,coast);write_data(stage,arrays)
        for item in inputs:
            if e.identity(item['path'])!=item:raise ValueError('input changed during rendering')
        receipt={'status':'COMPLETE','inputs':inputs,'source':e.identity(__file__),'numpy':np.__version__,'matplotlib':matplotlib.__version__,
                 'rain_boundaries_mm':edges,'points':3688,'interpolation':'forecast fields bilinearly mapped to paired RN1 points; no additional display interpolation',
                 'outputs':{p.name:e.identity(p)['sha256'] for p in stage.iterdir()}}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n');e.prior.publish_new(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.results,a.output)
