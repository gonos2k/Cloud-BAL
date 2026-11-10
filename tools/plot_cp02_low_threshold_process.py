#!/usr/bin/env python3
"""Render sealed low-threshold process diagnostics and point traces."""
import argparse
import csv
import gzip
import json
import os
from pathlib import Path
import shutil
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter, NullFormatter
import numpy as np

from cp02_ice_false_alarm import evaluation as E

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'docs/evidence/cp02_low_threshold_process_20261110'
COHORT = BUNDLE / 'cohorts/results'
ANALYSIS = BUNDLE / 'analysis'
SCIENCE = BUNDLE / 'science/full'
FONT = Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
FONT_SHA = '48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733'
ARMS = ('FIX', 'CONSERVATIVE', 'ICE_FIXED')
ARM_LABEL = {'FIX':'B1', 'CONSERVATIVE':'PR153', 'ICE_FIXED':'PR154'}
COLORS = {'FIX':'#3b5998', 'CONSERVATIVE':'#d17c10', 'ICE_FIXED':'#b52f48', 'ORIGINAL':'#555555'}
CONTRASTS = ('CONSERVATIVE-FIX', 'ICE_FIXED-CONSERVATIVE', 'ICE_FIXED-FIX')
CONTRAST_LABELS = ('PR153 - B1', 'PR154 - PR153', 'PR154 - B1')


def read_csv(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def sealed(folder, names):
    path = folder / 'receipt.json'
    receipt = json.loads(path.read_text())
    if receipt['status'] not in ('PASS', 'COMPLETE'):
        raise ValueError('incomplete input receipt')
    inputs = [E.identity(path)]
    for name in names:
        p = folder / name
        identity = E.identity(p)
        expected = receipt['outputs'][name]
        if isinstance(expected, dict): expected = expected['sha256']
        if identity['sha256'] != expected:
            raise ValueError('input hash mismatch: ' + str(p))
        inputs.append(identity)
    return inputs


def configure():
    if E.identity(FONT)['sha256'] != FONT_SHA:
        raise ValueError('font differs from pinned NanumGothic')
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(FONT)).get_name(),
                         'axes.unicode_minus':False, 'font.size':10, 'figure.facecolor':'white',
                         'savefig.facecolor':'white', 'axes.spines.top':False, 'axes.spines.right':False})


def save(fig, path):
    fig.savefig(path, dpi=150, metadata={'Software':'Cloud-BAL sealed diagnostic figures'})
    plt.close(fig)


def coverage(summary, out):
    data = summary['counts']['ORIGINAL']
    thresholds = ('0.1', '0.5', '1.0')
    outside = [data[t]['outside_old_128'] for t in thresholds]
    inside = [data[t]['new']-data[t]['outside_old_128'] for t in thresholds]
    fig, ax = plt.subplots(figsize=(8,4.8), constrained_layout=True)
    x = np.arange(3)
    ax.bar(x, outside, color='#356b9a', label='Outside old 128')
    ax.bar(x, inside, bottom=outside, color='#d99435', label='Inside old 128')
    for i, (a, b) in enumerate(zip(outside, inside)):
        ax.text(i, a+b+2, f'{a+b} total' + (f'\n{b} inside' if b else ''), ha='center', va='bottom', fontsize=9)
        ax.text(i, a/2, str(a), ha='center', va='center', color='white', fontweight='bold')
    ax.set(xticks=x, xticklabels=['0.1','0.5','1.0'], xlabel='Hourly event threshold (mm)', ylabel='RN1 points', ylim=(0,195))
    ax.legend(loc='upper left', ncols=2)
    ax.set_title('+6 h new false alarms: ORIGINAL to PR154\nObservation < threshold; ORIGINAL < threshold; PR154 >= threshold')
    save(fig,out/'01_low_false_alarm_coverage.png')


def weak(rows, out):
    cases = ('ORIGINAL','IMPROVED_BG_FIXED','CONSERVATIVE_SEDIMENTATION','FIRST_ICE_VELOCITY')
    labels = ('ORIGINAL','B1','PR153','PR154')
    colors = ('#555555',COLORS['FIX'],COLORS['CONSERVATIVE'],COLORS['ICE_FIXED'])
    fig, axes = plt.subplots(1,2,figsize=(11.5,4.7),sharey=True,constrained_layout=True)
    for case,label,color in zip(cases,labels,colors):
        for ax,key in zip(axes,('forecast_at_least_0.1','forecast_0.1_to_1')):
            rates=[]
            for lead in range(1,7):
                group=[r for r in rows if int(r['lead_hour'])==lead and r['case']==case]
                rates.append(100*sum(int(r[key]) for r in group)/sum(int(r['observations']) for r in group))
            ax.plot(range(1,7),rates,marker='o',color=color,label=label,lw=1.8,ms=4)
    axes[0].set_title('Detection: forecast >= 0.1 mm')
    axes[1].set_title('Forecast in [0.1, 1) mm')
    for ax in axes:
        ax.set(xlabel='Forecast lead (h)',xticks=range(1,7),ylim=(0,100));ax.grid(alpha=.18)
    axes[0].set_ylabel('Share of observed [0.1, 1) mm cases (%)')
    axes[1].legend(loc='best',fontsize=9)
    fig.suptitle('Weak observed hourly precipitation: detection and forecast intensity')
    save(fig,out/'02_weak_detection_intensity.png')


def heatmap(ledger, point_ids, layout, title, filename, out):
    fig = plt.figure(figsize=(18,11))
    grid = fig.add_gridspec(3,4,width_ratios=(1,1,1,.025),left=.095,right=.95,bottom=.16,top=.9,wspace=.12,hspace=.18)
    axes = np.array([[fig.add_subplot(grid[r,c]) for c in range(3)] for r in range(3)])
    indexed={(r['contrast'],r['field'],int(r['flat_index_yx']),int(r['native_k_1based'])):r for r in ledger if int(r['lead_hour'])==6}
    for row, (field, columns, label) in enumerate(layout):
        matrices=[]
        for column in columns:
            contrast, value_key = column[:2]
            matrix=np.full((39,len(point_ids)),np.nan)
            for x,point in enumerate(point_ids):
                for k in range(1,40):
                    r=indexed[(contrast,field,point,k)]
                    raw=r[value_key]
                    if raw != '': matrix[k-1,x]=float(raw)
            matrices.append(matrix)
        scale=max(np.nanmax(np.abs(m)) for m in matrices)
        if not np.isfinite(scale): raise ValueError('no heatmap data')
        scale=max(scale, 1e-20)
        for col, (ax,matrix) in enumerate(zip(axes[row],matrices)):
            art=ax.imshow(matrix,origin='lower',aspect='auto',cmap='RdBu_r',vmin=-scale,vmax=scale,interpolation='nearest', extent=(-.5,len(point_ids)-.5,.5,39.5))
            ax.set_yticks([1,5,10,15,20,25,30,35,39])
            ax.set_title(columns[col][2] if len(columns[col])>2 else CONTRAST_LABELS[col], fontsize=10)
            if col==0: ax.set_ylabel(f'{label}\nNative model k (1-39)')
            if row==2:
                ax.set_xticks(range(len(point_ids)),[str(p) for p in point_ids],rotation=90,fontsize=6)
                ax.set_xlabel('RN1 flat index (representative points)')
            else:
                ax.set_xticks([])
            if col != 0: ax.set_yticklabels([])
        cax=fig.add_subplot(grid[row,3])
        fig.colorbar(art,cax=cax,format='%.1e',label='K' if field=='TK' else 'kg kg-1')
    fig.suptitle(title,fontsize=14)
    save(fig,out/filename)


def residual_ecdf(out):
    fig, ax = plt.subplots(figsize=(8,5.1),constrained_layout=True)
    for arm in ARMS:
        with gzip.open(SCIENCE/arm/'calls.csv.gz','rt',newline='') as f:
            rows=[r for r in csv.DictReader(f) if r['species']=='rain' and 901<=int(r['step'])<=1080 and r['low_new_fa_corner']=='1']
        values=np.sort([float(r['residual_kg_m2']) for r in rows if r['residual_kg_m2']!=''])
        ax.plot(values,np.arange(1,len(values)+1)/len(values),color=COLORS[arm],lw=1.8,
                label=f"{ARM_LABEL[arm]}: n={len(values):,}, missing={len(rows)-len(values):,}")
    ax.axvline(0,color='#444',lw=.8,ls='--')
    ax.set_xscale('symlog',linthresh=1e-8)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: '0' if x == 0 else f'{x:.0e}'))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set(xlabel='Rain column state change + captured surface export (kg m-2)',ylabel='Empirical cumulative fraction',ylim=(0,1))
    ax.grid(alpha=.17);ax.legend(fontsize=9)
    ax.set_title('+6 h rain sedimentation residual: selected low-FA native corners\nDEND × DELZ source carrier; missing surface phase excluded')
    save(fig,out/'06_column_residual_ecdf.png')


def traces(point_rows, traces, out):
    points=[int(x) for x in traces['point_ids']]
    point_map={int(r['flat_index_yx']):r for r in point_rows}
    if len(points)!=21 or set(points)!=set(point_map): raise ValueError('point identity mismatch')
    times=traces['step']/180.
    for n,point in enumerate(points):
        r=point_map[point]
        fig=plt.figure(figsize=(10.4,6),constrained_layout=True)
        grid=fig.add_gridspec(2,1,height_ratios=(3.5,1.1))
        ax=fig.add_subplot(grid[0])
        ax.axvspan(0,1,color='#e8eef6',alpha=.9,label='Process capture windows')
        ax.axvspan(4,6,color='#e8eef6',alpha=.9)
        for arm in ARMS:
            ax.plot(times,traces[f'{arm}_rain_cumulative_mm'][:,n],color=COLORS[arm],lw=2,label=ARM_LABEL[arm])
        ax.set(xlabel='Forecast lead (h)',ylabel='Cumulative RAINNC since initial time (mm)',xlim=(0,6),xticks=range(7))
        ax.grid(alpha=.2);ax.legend(ncols=4,fontsize=9,loc='upper left')
        ax.set_title(f'RN1 {point}: cumulative RAINNC component\n{r["cohort"]}',fontsize=12)
        table_ax=fig.add_subplot(grid[1]);table_ax.axis('off')
        cells=[]
        for label,field in [('RN1 observed total','reference'),('B1 total forecast','IMPROVED_BG_FIXED'),('PR153 total forecast','CONSERVATIVE_SEDIMENTATION'),('PR154 total forecast','FIRST_ICE_VELOCITY')]:
            cells.append([label]+[f"{float(r[f'{field}_h{h}_mm']):.2f}" for h in (1,5,6)])
        table=table_ax.table(cellText=cells,colLabels=['Hourly total precipitation (mm)','+1 h','+5 h','+6 h'],cellLoc='center',loc='center',colWidths=[.52,.14,.14,.14])
        table.auto_set_font_size(False);table.set_fontsize(8.5);table.scale(1,1.13)
        save(fig,out/f'point_{point}_rainnc.png')


def run(output):
    if os.path.lexists(output): raise FileExistsError(output)
    configure()
    inputs=sealed(COHORT,['summary.json','selected_points.csv','weak_detection.csv'])
    inputs+=sealed(ANALYSIS,['paired_process_ledger.csv','point_surface_traces.npz'])
    for arm in ARMS: inputs+=sealed(SCIENCE/arm,['calls.csv.gz'])
    inputs.append(E.identity(FONT));inputs.append(E.identity(__file__))
    points=read_csv(COHORT/'selected_points.csv')
    ids=[int(r['flat_index_yx']) for r in points]
    ledger=read_csv(ANALYSIS/'paired_process_ledger.csv')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.figure-stage-',dir=output.parent))
    try:
        coverage(json.loads((COHORT/'summary.json').read_text()),stage)
        weak(read_csv(COHORT/'weak_detection.csv'),stage)
        heatmap(ledger,ids,[(f,[(c,'return_delta') for c in CONTRASTS],f) for f in ('QR','QI','TK')],
                '+6 h return-state difference at 21 RN1 representatives\nNative k index, not geometric height', '03_return_state_contrasts.png',stage)
        heatmap(ledger,ids,[(f,[(CONTRASTS[2],k,l) for k,l in [('local_sum','Within-call local'),('external_sum','Between-call external'),('endpoint_change','Endpoint change')]],f) for f in ('QR','QI','TK')],
                '+6 h PR154 - B1 ledger components\nCoupled response diagnostics; not independent causal contributions', '04_local_external_endpoint.png',stage)
        heatmap(ledger,ids,[(f,[(c,k) for c in CONTRASTS],label) for f,k,label in [('QR','sed_rsg_sum','QR: rain/snow/graupel sedimentation'),('QI','sed_ice_sum','QI: ice sedimentation'),('QC','cond_sum','QC: final condensation')]],
                '+6 h measured stage differences: 21 RN1 representatives\nStage endpoint differences; not a complete process budget', '05_source_stage_contrasts.png',stage)
        residual_ecdf(stage)
        with np.load(ANALYSIS/'point_surface_traces.npz',allow_pickle=False) as d:
            traces(points,{k:d[k].copy() for k in d.files},stage)
        png=sorted(stage.glob('*.png'))
        if len(png)!=27: raise ValueError('expected 27 figures')
        for record in inputs:
            if E.identity(record['path']) != record: raise ValueError('input changed during plotting')
        record={'status':'COMPLETE','inputs':inputs,'source_sha256':E.identity(__file__)['sha256'],
                'plot_environment':{'matplotlib':matplotlib.__version__,'numpy':np.__version__,'font_sha256':FONT_SHA,
                                    'backend':'Agg','dpi':150,'unicode_minus':False},
                'outputs':{p.name:E.identity(p)['sha256'] for p in png}}
        (stage/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
        E.publish_new(stage,output)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    return len(png)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    print(f'{run(a.output)} figures complete')


if __name__=='__main__': main()
