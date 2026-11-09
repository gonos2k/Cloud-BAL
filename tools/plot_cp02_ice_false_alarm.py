#!/usr/bin/env python3
"""Plot sealed false-alarm cohorts and hourly precipitation components."""
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
import numpy as np

from cp02_ice_false_alarm import evaluation

ROOT=Path(__file__).resolve().parents[1]
PRIOR=ROOT/'docs/evidence/cp02_first_ice_velocity_20261109/evaluation/results'
FONT=Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
COAST=ROOT/'docs/evidence/cp02_grouped_forecast_20261105/figures/data/ne_50m_coastline.geojson'
CASES=evaluation.CASES
B1,CONS,NEW=evaluation.B1,evaluation.CONS,evaluation.NEW
LABELS={CASES[0]:'규준실험',B1:'현재 B1',CONS:'PR153',NEW:'PR154'}
GROUPS={'persistent':('잔존 65곳','#e69f00','o'),'new':('신규 26곳','#d55e00','^'),'resolved':('해소 37곳','#0072b2','s')}


def read_csv(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))


def verify_bundle(folder):
    receipt=json.loads((folder/'receipt.json').read_text())
    if receipt['status']!='COMPLETE':raise ValueError('incomplete input bundle')
    inputs=[evaluation.identity(folder/'receipt.json')]
    for name,digest in receipt['outputs'].items():
        record=evaluation.identity(folder/name)
        if record['sha256']!=digest:raise ValueError('input receipt mismatch: '+name)
        inputs.append(record)
    return inputs


def resources():
    if evaluation.identity(FONT)['sha256']!='48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733':raise ValueError('font differs')
    if evaluation.identity(COAST)['sha256']!='271f1c4c1908312bac6b29d158ea1356544beafc129f260005300913aa5ea283':raise ValueError('coast differs')
    font_manager.fontManager.addfont(str(FONT));plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(FONT)).get_name(),'axes.unicode_minus':False})
    lines=[]
    for feature in json.loads(COAST.read_text())['features']:
        g=feature['geometry'];segments=[g['coordinates']] if g['type']=='LineString' else g['coordinates'] if g['type']=='MultiLineString' else []
        lines.extend(np.asarray(segment) for segment in segments)
    return lines


def save(fig,path):
    fig.savefig(path,dpi=170);plt.close(fig)


def maps(arrays,members,coast,out):
    a=arrays[18];fig,axes=plt.subplots(1,3,figsize=(14,5),sharex=True,sharey=True,constrained_layout=True)
    lookup={int(key):i for i,key in enumerate(a['flat_index_yx'])}
    for ax,case in zip(axes,(B1,CONS,NEW)):
        art=ax.scatter(a['longitude'],a['latitude'],c=a[case],s=8,cmap='viridis',vmin=0,vmax=20,rasterized=True)
        for name,(label,color,marker) in GROUPS.items():
            ids=[lookup[int(r['flat_index_yx'])] for r in members if r['cohort']==name]
            ax.scatter(a['longitude'][ids],a['latitude'][ids],s=34,facecolors='none',edgecolors=color,marker=marker,linewidths=.8,label=label)
        for line in coast:ax.plot(line[:,0],line[:,1],color='#444',lw=.4)
        ax.set(xlim=(a['longitude'].min(),a['longitude'].max()),ylim=(a['latitude'].min(),a['latitude'].max()),xlabel='경도 (°E)',title=LABELS[case]);ax.set_aspect(1/np.cos(np.deg2rad(a['latitude'].mean())),adjustable='box')
    axes[0].set_ylabel('위도 (°N)');axes[-1].legend(fontsize=8,loc='lower right')
    fig.colorbar(art,ax=axes,label='17–18 UTC 한 시간 강수 (mm, 20 이상 같은 색)',fraction=.022,pad=.02)
    fig.suptitle('+6시간 5 mm 오경보 집단의 위치 · 초기 2026-08-16 12 UTC\n고정 쌍선형 대응 RN1 평가점 · 표시점 사이 추가 보간 없음')
    save(fig,out/'h6_false_alarm_map.png')


def paired(paths,surface,out):
    fig,axes=plt.subplots(1,3,figsize=(14,4.5),constrained_layout=True)
    keyed={(int(r['lead_hour']),r['case'],int(r['flat_index_yx'])):r for r in surface}
    for name,(label,color,marker) in GROUPS.items():
        rows=[r for r in paths if r['cohort']==name]
        base=np.array([float(r[B1+'_h6_mm']) for r in rows]);new=np.array([float(r[NEW+'_h6_mm']) for r in rows])
        axes[0].scatter(base,new,s=23,c=color,marker=marker,label=label)
        summed=np.array([float(r[NEW+'_h5_h6_sum_mm'])-float(r[B1+'_h5_h6_sum_mm']) for r in rows])
        axes[1].scatter(summed,new-base,s=23,c=color,marker=marker)
        delta=[]
        for r in rows:
            n=keyed[6,NEW,int(r['flat_index_yx'])];b=keyed[6,B1,int(r['flat_index_yx'])]
            delta.append([float(n['rainnc_mm'])-float(b['rainnc_mm']),float(n['rainc_mm'])-float(b['rainc_mm'])])
        d=np.asarray(delta);axes[2].scatter(d[:,0],d[:,1],s=23,c=color,marker=marker)
    lim=max(axes[0].get_xlim()[1],axes[0].get_ylim()[1]);axes[0].plot([0,lim],[0,lim],color='#777',lw=.7);axes[0].axhline(5,color='#555',ls='--');axes[0].axvline(5,color='#555',ls='--');axes[0].legend(fontsize=8)
    axes[0].set(xlabel='현재 B1 +6시간 (mm)',ylabel='PR154 +6시간 (mm)')
    axes[1].set(xlabel='PR154-B1: +5·+6시간 합 차이 (mm)',ylabel='PR154-B1: +6시간 차이 (mm)')
    axes[2].set(xlabel='PR154-B1: RAINNC 한 시간 차이 (mm)',ylabel='PR154-B1: RAINC 한 시간 차이 (mm)')
    for ax in axes[1:]:ax.axhline(0,color='#777',lw=.7);ax.axvline(0,color='#777',lw=.7)
    fig.suptitle('개별 지점의 강도·시간 분포·누적 성분 비교\n시간 합은 보조 진단이며 물수지·원인 기여율이 아님')
    save(fig,out/'h6_pointwise_paths.png')


def first_hour(arrays,surface,out):
    fig,axes=plt.subplots(1,3,figsize=(12,4.4),sharey=True,constrained_layout=True)
    keyed={(int(r['lead_hour']),r['case'],int(r['flat_index_yx'])):r for r in surface}
    a=arrays[13]
    for ax,point in zip(axes,(10813,11571,11855)):
        rows=[keyed[1,c,point] for c in CASES];c=np.array([float(r['rainc_mm']) for r in rows]);n=np.array([float(r['rainnc_mm']) for r in rows])
        x=np.arange(4);ax.bar(x,c,label='RAINC 한 시간 증분',color='#66a5ad');ax.bar(x,n,bottom=c,label='RAINNC 한 시간 증분',color='#c4dfe6')
        obs=float(a['reference'][np.flatnonzero(a['flat_index_yx']==point)[0]])
        ax.axhline(obs,color='#222',label=f'관측 {obs:g} mm');ax.axhline(10,color='#d55e00',ls='--',label='10 mm 문턱')
        ax.set(xticks=x,xticklabels=[LABELS[c] for c in CASES],title=f'평가점 {point} · 관측 {obs:g} mm')
    axes[0].set_ylabel('12–13 UTC 한 시간 강수 (mm)');axes[-1].legend(fontsize=8)
    fig.suptitle('+1시간 신규 10 mm 오경보 3곳 · 시각 내부의 생성·강화 순서는 미확보')
    save(fig,out/'h1_three_false_alarms.png')


def weak_intensity(bins,out):
    fig,axes=plt.subplots(2,3,figsize=(13,7),constrained_layout=True)
    fields=('forecast_[0,0.1)','forecast_[0.1,0.5)','forecast_[0.5,1)','forecast_[1,2.5)','forecast_[2.5,5)','forecast_[5,10)','forecast_[10,inf)')
    colors=('#ddd','#a1d99b','#41ab5d','#fee391','#fec44f','#fb6a4a','#a50f15')
    labels=('<0.1','0.1–0.5','0.5–1','1–2.5','2.5–5','5–10','≥10')
    for lead,ax in enumerate(axes.flat,1):
        bottom=np.zeros(4)
        for field,color,label in zip(fields,colors,labels):
            values=[sum(int(r[field]) for r in bins if int(r['lead_hour'])==lead and r['case']==case and r['observation_bin_mm'] in ('[0.1,0.5)','[0.5,1)')) for case in CASES]
            ax.bar(range(4),values,bottom=bottom,color=color,label=label);bottom+=values
        ax.set(xticks=range(4),xticklabels=[LABELS[c] for c in CASES],ylabel='평가점 수',title=f'+{lead}시간, 관측 0.1≤RN1<1 mm')
    axes[0,0].legend(title='예측 강수 (mm)',fontsize=7,ncol=2)
    fig.suptitle('실제 약한 관측 강수에서의 예측 강도 분포\n≥0.1 mm 검출에는 강도 과잉도 포함 · 모든 예측시간을 별도 표시')
    save(fig,out/'weak_observed_intensity.png')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if os.path.lexists(args.output):raise FileExistsError(args.output)
    inputs=verify_bundle(args.bundle/'cohorts')+verify_bundle(args.bundle/'surface/native')
    arrays=evaluation.read_arrays(PRIOR);inputs += [evaluation.identity(PRIOR/'receipt.json')]+[evaluation.identity(PRIOR/f'hour_{h}_arrays.npz') for h in evaluation.HOURS]+[evaluation.identity(FONT),evaluation.identity(COAST)]
    coast=resources();members=read_csv(args.bundle/'cohorts/membership.csv');paths=read_csv(args.bundle/'cohorts/point_paths.csv');bins=read_csv(args.bundle/'cohorts/lead_bins.csv');surface=read_csv(args.bundle/'surface/native/hourly_points.csv')
    args.output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.ice-fa-figures-',dir=args.output.parent))
    try:
        maps(arrays,members,coast,stage);paired(paths,surface,stage);first_hour(arrays,surface,stage);weak_intensity(bins,stage)
        for record in inputs:
            if evaluation.identity(record['path'])!=record:raise ValueError('input changed while plotting')
        meta={'status':'COMPLETE','source':evaluation.identity(__file__),'inputs':inputs,'matplotlib':matplotlib.__version__,'numpy':np.__version__,'figures':4,'limits':['Counter components do not attribute physical causation.','Hourly histories cannot identify subhour onset or transport tendencies.','Maps show paired points with no additional interpolation.'],'outputs':{f.name:evaluation.identity(f)['sha256'] for f in sorted(stage.iterdir())}}
        (stage/'receipt.json').write_text(json.dumps(meta,indent=2)+'\n');evaluation.publish_new(stage,args.output)
    finally:
        if stage.exists():shutil.rmtree(stage)


if __name__=='__main__':main()
