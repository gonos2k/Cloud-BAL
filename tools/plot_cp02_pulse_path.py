#!/usr/bin/env python3
"""Render sealed surface and native-level pulse diagnostics without vertical averaging."""
import argparse
import csv
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from cp02_low_threshold_process import identity
from cp02_ice_false_alarm import evaluation
from plot_cp02_low_threshold_process import configure

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'docs/evidence/cp02_low_threshold_process_20261110/analysis'
NEW=ROOT/'docs/evidence/cp02_pulse_path_20261110/analysis'
NATIVE=ROOT/'docs/evidence/cp02_pulse_path_20261110/native'
ARMS=('FIX','CONSERVATIVE','ICE_FIXED')
LABELS=('B1','PR153','PR154')
COLORS=('#3b5998','#d17c10','#b52f48')
POINTS=(19145,19144,17804)
CONTRASTS=('CONSERVATIVE-FIX','ICE_FIXED-CONSERVATIVE')
METRICS=('entry_difference','local_difference_change','between_call_difference_change')
TITLES=('entry difference','within-call change in difference','between-call change in difference')


def sealed(folder,names):
    receipt=folder/'receipt.json'; meta=json.loads(receipt.read_text())
    if meta['status']!='COMPLETE': raise ValueError('input not complete')
    inputs=[identity(receipt)]
    for name in names:
        p=folder/name
        if p.is_symlink() or identity(p)['sha256']!=meta['outputs'][name]: raise ValueError('input identity mismatch: '+name)
        inputs.append(identity(p))
    return inputs


def load_surface(path):
    with np.load(path,allow_pickle=False) as data:
        steps=data['step'].copy(); ids=data['point_ids'].copy()
        arrays={arm:data[arm+'_rain_cumulative_mm'].copy() for arm in ARMS}
    if not np.array_equal(steps,np.arange(1081)) or len(set(ids.tolist()))!=len(ids): raise ValueError('surface axes differ')
    positions=[int(np.flatnonzero(ids==point)[0]) for point in POINTS]
    result={arm:arrays[arm][:,positions] for arm in ARMS}
    if any(v.shape!=(1081,3) or not np.isfinite(v).all() for v in result.values()): raise ValueError('incomplete surface')
    return result


def load_maps(path):
    arrays={(contrast,field,metric):np.full((3,180,39),np.nan) for contrast in CONTRASTS for field in ('QR','QG') for metric in METRICS}
    seen=set()
    with gzip.open(path,'rt',newline='') as f:
        for row in csv.DictReader(f):
            if row['hour']!='5' or row['contrast'] not in CONTRASTS or row['field'] not in ('QR','QG'): continue
            point=int(row['point']); step=int(row['step']); k=int(row['k'])
            if point not in POINTS or not 721<=step<=900 or not 1<=k<=39: raise ValueError('unexpected map coordinate')
            key=(row['contrast'],row['field'],point,step,k)
            if key in seen: raise ValueError('duplicate map coordinate')
            seen.add(key)
            for metric in METRICS:
                value=row[metric]
                arrays[(row['contrast'],row['field'],metric)][POINTS.index(point),step-721,k-1]=float(value) if value else np.nan
    if len(seen)!=len(CONTRASTS)*2*3*180*39: raise ValueError('incomplete map')
    for (contrast,field,metric),values in arrays.items():
        expected=np.ones(values.shape,dtype=bool)
        if metric==METRICS[2]: expected[:,0,:]=False
        if not np.array_equal(np.isfinite(values),expected): raise ValueError('map validity differs')
    return arrays


def write_data(out,surface,maps):
    with (out/'surface_full.csv').open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['step','point']+[a+'_RAINNC_counter_mm' for a in ARMS])
        for s in range(1081):
            for p,point in enumerate(POINTS): w.writerow([s,point]+[surface[a][s,p] for a in ARMS])
    with (out/'native_levels.csv.gz').open('wb') as raw:
        with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as z:
            with io.TextIOWrapper(z,encoding='utf-8',newline='') as f:
                w=csv.writer(f,lineterminator='\n');w.writerow(['contrast','field','point','step','native_k_1based',*METRICS])
                for contrast in CONTRASTS:
                    for field in ('QR','QG'):
                        for p,point in enumerate(POINTS):
                            for t in range(180):
                                for k in range(39):
                                    vals=[maps[(contrast,field,m)][p,t,k] for m in METRICS]
                                    w.writerow([contrast,field,point,t+721,k+1]+['' if not np.isfinite(x) else x for x in vals])


def save(fig,path):
    fig.savefig(path,dpi=150,metadata={'Software':'Cloud-BAL pulse diagnostics'})
    plt.close(fig)


def surface_plots(out,surface):
    fig,axes=plt.subplots(3,1,figsize=(11,8),sharex=True,constrained_layout=True)
    for p,ax in enumerate(axes):
        for arm,label,color in zip(ARMS,LABELS,COLORS): ax.plot(np.arange(1081)*20/3600,surface[arm][:,p],label=label,color=color,lw=1.4)
        ax.set_ylabel('RAINNC (mm)');ax.set_title('Point '+str(POINTS[p]),loc='left');ax.grid(alpha=.2)
    axes[0].legend(ncol=3,loc='upper left');axes[-1].set_xlabel('Forecast lead time (h)')
    fig.suptitle('Source cumulative RAINNC counter at 20 s boundaries; bilinear point values')
    save(fig,out/'01_surface_cumulative.png')
    fig,axes=plt.subplots(3,1,figsize=(11,8),sharex=True,constrained_layout=True)
    for p,ax in enumerate(axes):
        for arm,label,color in zip(ARMS,LABELS,COLORS):
            values=surface[arm][:,p];ax.plot(np.arange(721,901),values[721:901]-values[720:900],color=color,label=label,lw=1.4)
        ax.set_ylabel('Counter change\nper 20 s (mm)');ax.set_title('Point '+str(POINTS[p]),loc='left');ax.grid(alpha=.2)
    axes[0].legend(ncol=3);axes[-1].set_xlabel('Call step (h5: 721–900)')
    fig.suptitle('20 s changes of cumulative RAINNC; not the RAINNCV sum')
    save(fig,out/'02_surface_pulse_zoom.png')


def map_plot(out,maps,contrast,field,index):
    fig,axes=plt.subplots(3,3,figsize=(15,10),sharex=True,sharey=True,constrained_layout=True)
    for j,metric in enumerate(METRICS):
        data=maps[(contrast,field,metric)];limit=float(np.nanmax(np.abs(data))) or 1
        for p in range(3):
            ax=axes[p,j]
            image=ax.pcolormesh(np.arange(720.5,901.5),np.arange(.5,40.5),data[p].T,shading='flat',cmap='RdBu_r',vmin=-limit,vmax=limit,rasterized=True)
            ax.axvspan(845.5,862.5,color='black',alpha=.08)
            if j==0: ax.set_ylabel('Point '+str(POINTS[p])+'\nnative k (1–39)')
            if p==0: ax.set_title(TITLES[j])
            if p==2: ax.set_xlabel('Call step')
            ax.set_yticks([1,10,20,30,39]);ax.set_ylim(.5,39.5)
        fig.colorbar(image,ax=axes[:,j],label='kg kg⁻¹',shrink=.8,format='%.1e')
    fig.suptitle(f'{field}: {contrast} | h5, 20 s calls | shading: steps 846–862\nLocal and between-call changes partition the paired state path; not causal process contributions')
    save(fig,out/f'{index:02d}_{field}_{contrast}.png')


def cold_partition(out):
    path=NATIVE/'core_qg_partition.csv'; receipt=NATIVE/'recount_receipt.json'
    meta=json.loads(receipt.read_text())
    if meta['status']!='PASS' or meta['output_sha256']!=identity(path)['sha256']:
        raise ValueError('native core partition receipt mismatch')
    with path.open(newline='') as f: rows=list(csv.DictReader(f))
    terms=['pgdep','pgaut','piacr','praci','psacr','pracs','pgaci','paacw','pgacr','pgacs']
    data={(r['arm'],r['term']):float(r['weighted_integral_kg_kg']) for r in rows}
    if len(rows)!=20 or len(data)!=20 or any(r['point']!='19145' or r['step']!='858' or r['k']!='17' for r in rows):
        raise ValueError('native partition scope differs')
    fig,ax=plt.subplots(figsize=(12,5.6),constrained_layout=True)
    x=np.arange(len(terms)); width=.37
    for offset,arm,color,label in ((-width/2,'CONSERVATIVE',COLORS[1],'PR153'),(width/2,'ICE_FIXED',COLORS[2],'PR154')):
        ax.bar(x+offset,[data[arm,t] for t in terms],width,color=color,label=label)
    ax.axhline(0,color='black',lw=.7);ax.set_xticks(x,terms,rotation=35,ha='right')
    ax.set_ylabel('Signed time-integrated QG equation term (kg kg⁻¹)')
    ax.set_title('Point 19145, call 858, native k=17: cold QG source terms\nEach arm uses its own limited substeps; bilinear weighted, not surface precipitation')
    ax.grid(axis='y',alpha=.2);ax.legend()
    save(fig,out/'07_cold_qg_terms.png')
    shutil.copyfile(path,out/'cold_qg_terms.csv')
    return [identity(path),identity(receipt)]


def run(output):
    if os.path.lexists(output): raise FileExistsError(output)
    inputs=sealed(OLD,['point_surface_traces.npz'])+sealed(NEW,['calls.csv.gz','surface_windows.csv'])
    configure(); surface=load_surface(OLD/'point_surface_traces.npz');maps=load_maps(NEW/'calls.csv.gz')
    output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.pulse-figures-',dir=output.parent))
    try:
        surface_plots(stage,surface)
        for i,(contrast,field) in enumerate(((c,f) for c in CONTRASTS for f in ('QR','QG')),start=3): map_plot(stage,maps,contrast,field,i)
        write_data(stage,surface,maps)
        inputs+=cold_partition(stage)
        for item in inputs:
            if identity(item['path'])!=item: raise ValueError('input changed during render')
        meta={'status':'COMPLETE','inputs':inputs,'source':identity(__file__),'matplotlib':matplotlib.__version__,'numpy':np.__version__,
              'limits':['Native k is model level, not height. No vertical averaging.', 'RAINNC counter changes are not RAINNCV sums.',
                        'Differences are coupled forecast responses, not causal physical contributions.',
                        'Between-call changes include all operations outside the captured microphysics call.',
                        'Gray shading is a context interval, not a 15-call window.',
                        'Cold QG terms are signed limited equation rates integrated over each arm’s actual substeps; not rainfall.'],
              'outputs':{p.name:identity(p)['sha256'] for p in stage.iterdir()}}
        (stage/'receipt.json').write_text(json.dumps(meta,indent=2)+'\n')
        evaluation.publish_new(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
