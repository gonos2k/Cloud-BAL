#!/usr/bin/env python3
"""Render the fixed comparison from sealed evaluation outputs."""
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

CASES=('reference',*e.CASES)
LABELS=('RN1 관측','규준실험','B1','PR153','PR154','MP10','MP10 NN_END')

def run(results,output):
    results=Path(results);output=Path(output)
    if os.path.lexists(output): raise FileExistsError(output)
    receipt=json.loads((results/'receipt.json').read_text())
    if receipt.get('status')!='COMPLETE': raise ValueError('evaluation incomplete')
    names=[f'hour_{h}_arrays.npz' for h in e.HOURS]+['categorical_scores.csv']
    inputs=[e.identity(results/'receipt.json'),e.identity(resources.FONT),e.identity(resources.COAST),e.identity(resources.__file__)]
    for name in names:
        p=results/name
        if e.identity(p)['sha256']!=receipt['outputs'][name]:raise ValueError('evaluation artifact changed')
        inputs.append(e.identity(p))
    arrays={}
    for h in e.HOURS:
        with np.load(results/f'hour_{h}_arrays.npz',allow_pickle=False) as d: arrays[h]={k:d[k].copy() for k in d.files}
    e.score(arrays,e.load_policy())
    with (results/'categorical_scores.csv').open() as f: rows=list(csv.DictReader(f))
    coast=resources.resources();output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.nn-plots-',dir=output.parent))
    try:
        maximum=max(float(np.max(arrays[h][case])) for h in e.HOURS for case in CASES)
        edges=[0,.1,.5,1,2.5,5,10,20,50,100,max(100.,maximum)+1]
        norm=BoundaryNorm(edges,256,clip=True);lon=arrays[13]['longitude'];lat=arrays[13]['latitude']
        for h in e.HOURS:
            fig,axes=plt.subplots(2,4,figsize=(16,8),sharex=True,sharey=True,constrained_layout=True)
            for ax,case,label in zip(axes.flat,CASES,LABELS):
                artist=ax.scatter(lon,lat,c=arrays[h][case],s=8,cmap='viridis',norm=norm,linewidths=0,rasterized=True)
                for line in coast:ax.plot(line[:,0],line[:,1],color='#333333',linewidth=.5)
                ax.set_title(label);ax.set_xlim(lon.min(),lon.max());ax.set_ylim(lat.min(),lat.max());ax.set_aspect(1/np.cos(np.deg2rad(float(lat.mean()))),adjustable='box');ax.grid(alpha=.17)
            axes.flat[-1].set_visible(False)
            fig.colorbar(artist,ax=list(axes.flat[:-1]),label='한 시간 강수량 (mm)',ticks=edges[:-1],shrink=.8)
            fig.suptitle(f'2026-08-16 12 UTC 초기화 · +{h-12} h · RN1 평가점 3,688개\n예보장 RN1 점에 쌍선형 대응 · 표시용 추가 공간 보간 없음')
            fig.savefig(stage/f'hour_{h-12}_rainfall.png',dpi=150);plt.close(fig)
        fig,axes=plt.subplots(2,3,figsize=(15,8),sharex=True,sharey=True,constrained_layout=True)
        for ax,threshold in zip(axes.flat,e.THRESHOLDS):
            for case,label in zip(e.CASES,LABELS[1:]):
                series=[r for r in rows if r['case']==case and float(r['threshold_mm'])==threshold]
                if len(series)!=6:raise ValueError('score coverage differs')
                series.sort(key=lambda r:int(r['lead_hour']))
                ax.plot([int(r['lead_hour']) for r in series],[float(r['CSI']) for r in series],marker='o',markersize=3,label=label)
            ax.set_title(f'{threshold:g} mm');ax.grid(alpha=.2);ax.set_xticks(range(1,7));ax.set_ylim(0,1)
        axes[1,0].set_xlabel('예보시간 (h)');axes[0,0].set_ylabel('CSI');axes[1,0].set_ylabel('CSI')
        handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=6);fig.suptitle('시간별 강수 CSI · RN1 3,688점 · 각 임계값 개별 비교')
        fig.savefig(stage/'csi_by_hour_threshold.png',dpi=150);plt.close(fig)
        for item in inputs:
            if e.identity(item['path'])!=item:raise ValueError('plot input changed')
        (stage/'receipt.json').write_text(json.dumps({'status':'COMPLETE','inputs':inputs,'source':e.identity(__file__),'points':e.POINTS,'rain_boundaries_mm':edges,'interpolation':'forecast bilinear to RN1 points; no display interpolation','outputs':{p.name:e.identity(p)['sha256'] for p in stage.iterdir()}},indent=2)+'\n')
        os.rename(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.results,a.output)
