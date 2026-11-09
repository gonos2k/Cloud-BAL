#!/usr/bin/env python3
"""Render six CSI plots and six paired-point maps from sealed score arrays."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import tempfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import BoundaryNorm, SymLogNorm
from matplotlib.ticker import FuncFormatter
import numpy as np
from evaluate import B1, CASES, CONS, HOURS, NEW, ORIGINAL, ROOT, THRESHOLDS, identity, publish_new, read_arrays, score

FONT=Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
COAST=ROOT/'docs/evidence/cp02_grouped_forecast_20261105/figures/data/ne_50m_coastline.geojson'
NAMES={ORIGINAL:'규준실험 (ORIGINAL)',B1:'현재 B1',CONS:'PR153 보존 침강',NEW:'첫 빙정 단위 수정'}
COLORS={ORIGINAL:'#555555',B1:'#2166ac',CONS:'#8b5a2b',NEW:'#d14932'}
STYLES={ORIGINAL:('--','s'),B1:(':','^'),CONS:('-.','D'),NEW:('-','o')}


def resources():
    if identity(FONT)['sha256'] != '48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733' or identity(COAST)['sha256'] != '271f1c4c1908312bac6b29d158ea1356544beafc129f260005300913aa5ea283': raise ValueError('pinned font or coastline differs')
    font_manager.fontManager.addfont(str(FONT)); plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(FONT)).get_name(),'axes.unicode_minus':False})
    lines=[]
    for feature in json.loads(COAST.read_text())['features']:
        geo=feature['geometry']; coords=geo['coordinates']; kind=geo['type']
        for segment in ([coords] if kind=='LineString' else coords if kind=='MultiLineString' else []):
            line=np.asarray(segment,dtype=float)
            if line.ndim!=2 or line.shape[1]<2 or not np.isfinite(line[:,:2]).all(): raise ValueError('invalid coast')
            lines.append(line[:,:2])
    if not lines: raise ValueError('empty coast')
    return lines


def render(arrays, out):
    categorical, _, _, _ = score(arrays); coast=resources()
    for threshold in THRESHOLDS:
        fig,ax=plt.subplots(figsize=(7.5,4.4)); all_csi=[]
        for case in CASES:
            rows=[r for r in categorical if r['case']==case and r['threshold_mm']==threshold]
            y=[r['CSI'] for r in rows]; all_csi.extend(y); style,marker=STYLES[case]
            ax.plot(range(1,7),y,linestyle=style,marker=marker,label=NAMES[case],color=COLORS[case])
        margin=max((max(all_csi)-min(all_csi))*.12,.015)
        ax.set(xlabel='Forecast lead (hours)',ylabel='CSI (axis varies by threshold)',title=f'CSI at ≥ {threshold:g} mm per hour',xticks=range(1,7),ylim=(max(0,min(all_csi)-margin),min(1,max(all_csi)+margin)))
        ax.grid(alpha=.25); ax.legend(frameon=False); fig.tight_layout(); fig.savefig(out/f'csi_{threshold:g}mm.png',dpi=170); plt.close(fig)
    fields=('reference',*CASES)
    maxrain=max(float(arrays[h][k].max()) for h in HOURS for k in fields)
    delta=max(float(np.max(np.abs(arrays[h][NEW]-arrays[h][k]))) for h in HOURS for k in (B1,CONS,ORIGINAL))
    levels=[0,.1,.5,1,2.5,5,10,20,50,100,max(100.,maxrain)+1]
    rainnorm=BoundaryNorm(levels,256,clip=True); delta_limit=max(delta,.01)
    diffnorm=SymLogNorm(linthresh=.1,linscale=1,vmin=-delta_limit,vmax=delta_limit,clip=True)
    lon,lat=arrays[13]['longitude'],arrays[13]['latitude']
    for hour in HOURS:
        row=arrays[hour]; fig,axes=plt.subplots(4,2,figsize=(11,16.8),constrained_layout=True,sharex=True,sharey=True)
        panels=[('RN1 관측',row['reference'],False), (NAMES[ORIGINAL],row[ORIGINAL],False),(NAMES[B1],row[B1],False),(NAMES[CONS],row[CONS],False),(NAMES[NEW],row[NEW],False),('첫 빙정 단위 수정 - 현재 B1',row[NEW]-row[B1],True),('첫 빙정 단위 수정 - PR153',row[NEW]-row[CONS],True),('첫 빙정 단위 수정 - 규준실험',row[NEW]-row[ORIGINAL],True)]
        for ax,(title,values,difference) in zip(axes.flat,panels):
            artist=ax.scatter(lon,lat,c=values,s=9,cmap='RdBu_r' if difference else 'viridis',norm=diffnorm if difference else rainnorm,linewidths=0,rasterized=True,zorder=3)
            if difference: diff_artist=artist
            else: rain_artist=artist
            for line in coast: ax.plot(line[:,0],line[:,1],color='#333333',linewidth=.5,zorder=4)
            ax.set_title(title,fontsize=10); ax.set_xlim(float(lon.min()),float(lon.max())); ax.set_ylim(float(lat.min()),float(lat.max())); ax.set_aspect(1/np.cos(np.deg2rad(float(lat.mean()))),adjustable='box'); ax.grid(alpha=.17,linewidth=.4); ax.tick_params(labelsize=8)
        for ax in axes[-1,:]: ax.set_xlabel('경도 (°E)')
        for ax in axes[:,0]: ax.set_ylabel('위도 (°N)')
        fig.colorbar(rain_artist,ax=axes[:2,:].ravel().tolist(),label='한 시간 강수량 (mm)',ticks=levels[:-1],fraction=.025,pad=.015)
        ticks=sorted({-delta_limit,0.,delta_limit}|{s*v for v in (.1,.5,1.,5.,10.) if v<delta_limit for s in (-1,1)})
        fig.colorbar(diff_artist,ax=axes[2:,:].ravel().tolist(),label='같은 지점 차이 (mm)',ticks=ticks,format=FuncFormatter(lambda v,pos:f'{v:g}'),fraction=.025,pad=.015)
        fig.suptitle(f'2026-08-16 12:00 UTC 초기화 · +{hour-12} h\n{hour-1:02d}:00–{hour:02d}:00 UTC 한 시간 강수량 · RN1 평가점 3,688개\n평가점만 표시 · 공간보간 없음 · 구간색 / 0 중심 대칭로그 차이색',fontsize=12)
        fig.savefig(out/f'rn1_hour_{hour}_maps.png',dpi=170); plt.close(fig)
    return {'rain_boundaries_mm':levels,'maximum_hourly_value_mm':maxrain,'symmetric_delta_limit_mm':delta_limit,'difference_normalization':'SymLogNorm linthresh 0.1 mm','points':3688,'interpolation':'none; preserved paired RN1 point locations'}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--results',type=Path,required=True); p.add_argument('--output',type=Path,required=True); args=p.parse_args()
    if os.path.lexists(args.output): raise FileExistsError(args.output)
    arrays=read_arrays(args.results); args.output.parent.mkdir(parents=True,exist_ok=True)
    inputs=[identity(args.results/'receipt.json')]+[identity(args.results/f'hour_{h}_arrays.npz') for h in HOURS]+[identity(FONT),identity(COAST)]
    stage=Path(tempfile.mkdtemp(prefix='.figure-stage-',dir=args.output.parent))
    try:
        meta=render(arrays,stage)
        for record in inputs:
            if identity(record['path']) != record: raise ValueError('input changed while plotting')
        meta.update(inputs=inputs,renderer=identity(__file__),numpy=np.__version__,matplotlib=matplotlib.__version__,outputs={f.name:identity(f)['sha256'] for f in sorted(stage.iterdir())})
        (stage/'maps_metadata.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False)+'\n')
        if os.path.lexists(args.output): raise FileExistsError(args.output)
        publish_new(stage,args.output)
    finally:
        if stage.exists(): shutil.rmtree(stage)

if __name__=='__main__': main()
