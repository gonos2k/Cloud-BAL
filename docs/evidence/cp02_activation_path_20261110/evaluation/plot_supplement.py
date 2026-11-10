#!/usr/bin/env python3
"""Separate threshold CSI and hourly differences against ORIGINAL."""
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
plt.rcParams['axes.unicode_minus'] = False
from matplotlib.colors import TwoSlopeNorm
import numpy as np
import evaluate as e
sys.path.insert(0,str(e.ROOT/'tools'))
import plot_cp02_ice_false_alarm as resources

LABELS=('규준실험','B1','PR153','PR154','MP10','MP10 NN_END')

def run(results,output):
    results=Path(results);output=Path(output)
    if os.path.lexists(output):raise FileExistsError(output)
    receipt=json.loads((results/'receipt.json').read_text())
    if receipt.get('status')!='COMPLETE':raise ValueError('evaluation incomplete')
    inputs=[e.identity(results/'receipt.json'),e.identity(resources.FONT),e.identity(resources.COAST),e.identity(resources.__file__)]
    for name in [f'hour_{h}_arrays.npz' for h in e.HOURS]+['categorical_scores.csv']:
        path=results/name
        if e.identity(path)['sha256']!=receipt['outputs'][name]:raise ValueError('input changed')
        inputs.append(e.identity(path))
    arrays={}
    for h in e.HOURS:
        with np.load(results/f'hour_{h}_arrays.npz',allow_pickle=False) as d:arrays[h]={k:d[k].copy() for k in d.files}
    e.score(arrays,e.load_policy())
    with (results/'categorical_scores.csv').open() as f:rows=list(csv.DictReader(f))
    coast=resources.resources();output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.nn-supp-',dir=output.parent))
    try:
        for n,threshold in enumerate(e.THRESHOLDS,1):
            fig,(ax,delta)=plt.subplots(2,1,figsize=(10,8),sharex=True,constrained_layout=True)
            reference={int(r['lead_hour']):float(r['CSI']) for r in rows if r['case']==e.B1 and float(r['threshold_mm'])==threshold}
            if set(reference)!=set(range(1,7)):raise ValueError('missing baseline scores')
            for case,label in zip(e.CASES,LABELS):
                series=sorted((int(r['lead_hour']),float(r['CSI'])) for r in rows if r['case']==case and float(r['threshold_mm'])==threshold)
                if len(series)!=6 or {x[0] for x in series}!=set(range(1,7)):raise ValueError('missing score row')
                line=ax.plot([h for h,v in series],[v for h,v in series],marker='o',label=label)[0]
                delta.plot([h for h,v in series],[v-reference[h] for h,v in series],marker='o',color=line.get_color())
            ax.set_ylabel('CSI');ax.set_ylim(0,1);ax.grid(alpha=.2);ax.legend(ncol=3)
            delta.axhline(0,color='black',linewidth=.7);delta.set_ylabel('CSI - B1');delta.set_xlabel('예보시간 (h)');delta.set_xticks(range(1,7));delta.grid(alpha=.2)
            fig.suptitle(f'강수 임계값 {threshold:g} mm · RN1 평가점 3,688개')
            fig.savefig(stage/f'csi_threshold_{n}.png',dpi=150);plt.close(fig)
        maximum=max(float(np.max(np.abs(arrays[h][case]-arrays[h][e.ORIGINAL]))) for h in e.HOURS for case in e.CASES)
        limit=max(maximum,1.e-6);norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit)
        lon=arrays[13]['longitude'];lat=arrays[13]['latitude']
        for h in e.HOURS:
            fig,axes=plt.subplots(2,3,figsize=(14,9),sharex=True,sharey=True,constrained_layout=True)
            for ax,case,label in zip(axes.flat,e.CASES,LABELS):
                artist=ax.scatter(lon,lat,c=arrays[h][case]-arrays[h][e.ORIGINAL],s=9,cmap='RdBu_r',norm=norm,linewidths=0,rasterized=True)
                for line in coast:ax.plot(line[:,0],line[:,1],color='#333333',linewidth=.5)
                ax.set_title(label+' - 규준실험');ax.set_xlim(lon.min(),lon.max());ax.set_ylim(lat.min(),lat.max());ax.set_aspect(1/np.cos(np.deg2rad(float(lat.mean()))),adjustable='box');ax.grid(alpha=.17)
            fig.colorbar(artist,ax=list(axes.flat),label='한 시간 강수량 차이 (mm)',shrink=.8)
            fig.suptitle(f'+{h-12} h · 규준실험 대비 · RN1 3,688점 · 전 시간 공통 색상\n예보장 RN1 점에 쌍선형 대응 · 표시용 추가 공간 보간 없음')
            fig.savefig(stage/f'hour_{h-12}_difference_original.png',dpi=150);plt.close(fig)
        for item in inputs:
            if e.identity(item['path'])!=item:raise ValueError('input changed during plotting')
        (stage/'receipt.json').write_text(json.dumps({'status':'COMPLETE','inputs':inputs,'source':e.identity(__file__),'points':e.POINTS,'difference_color_limit_mm':limit,'interpolation':'forecast bilinear to RN1 points; no display interpolation','outputs':{p.name:e.identity(p)['sha256'] for p in stage.iterdir()}},indent=2)+'\n')
        os.rename(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.results,a.output)
