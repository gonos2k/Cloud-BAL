#!/usr/bin/env python3
"""Plot each lead and threshold separately after the MP10 evaluation is sealed."""
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
import numpy as np

import evaluate as e
sys.path.insert(0,str(e.ROOT/'tools'))
from plot_cp02_low_threshold_process import configure


def read_rows(folder,name):
    with (folder/name).open(newline='') as f:return list(csv.DictReader(f))


def sealed(folder):
    receipt=folder/'receipt.json';data=json.loads(receipt.read_text())
    if data['status']!='COMPLETE':raise ValueError('evaluation is incomplete')
    inputs=[e.identity(receipt)]
    for name in ('categorical_scores.csv','observed_forecast_bands.csv','observation_transitions.csv',*[f'hour_{h}_arrays.npz' for h in e.HOURS]):
        path=folder/name
        if path.is_symlink() or e.identity(path)['sha256']!=data['outputs'][name]:raise ValueError('evaluation output differs: '+name)
        inputs.append(e.identity(path))
    return inputs


def save(fig,path):
    fig.savefig(path,dpi=150,metadata={'Software':'Cloud-BAL MP10 evaluation'});plt.close(fig)


def csi_plot(out,rows):
    index={(int(r['lead_hour']),float(r['threshold_mm']),r['case']):float(r['CSI']) for r in rows}
    if len(index)!=180:raise ValueError('CSI score coverage differs')
    fig,axes=plt.subplots(2,3,figsize=(13,7),sharex=True,constrained_layout=True)
    for threshold,ax in zip(e.THRESHOLDS,axes.flat):
        for base,label,color in ((e.B1,'MP10 - B1','#356b9a'),(e.ICE,'MP10 - PR154','#b52f48')):
            vals=[index[(h,threshold,e.NEW)]-index[(h,threshold,base)] for h in range(1,7)]
            ax.plot(range(1,7),vals,marker='o',ms=3,color=color,label=label)
        ax.axhline(0,color='black',lw=.7);ax.grid(alpha=.2);ax.set_title(f'{threshold:g} mm');ax.set_xlabel('Lead hour');ax.set_ylabel('CSI difference')
    axes.flat[0].legend(fontsize=8);fig.suptitle('CSI change at each lead and threshold; no averaged selection score')
    save(fig,out/'01_csi_change.png')


def weak_plot(out,bands,transitions):
    fig,axes=plt.subplots(2,3,figsize=(13,7),constrained_layout=True)
    for lead,ax in enumerate(axes.flat,1):
        selected=[r for r in bands if int(r['lead_hour'])==lead and r['baseline']==e.ICE and r['observed_band'] in ('[0.1,0.5)','[0.5,1)')]
        names=[b[0] for b in e.BINS];x=np.arange(len(names));width=.36
        for shift,case,color,label in ((-width/2,e.ICE,'#d17c10','PR154'),(width/2,e.NEW,'#b52f48','MP10')):
            vals=[sum(int(r['point_count']) for r in selected if r['forecast_case']==case and r['forecast_band']==name) for name in names]
            ax.bar(x+shift,vals,width,label=label,color=color)
        rows=[r for r in transitions if int(r['lead_hour'])==lead and r['baseline']==e.ICE and r['observation_subset']=='dry_observed']
        if len(rows)!=1:raise ValueError('dry transition coverage differs')
        r=rows[0];ax.set_title(f"Lead {lead}: dry FA gained {r['forecast_gained']}, lost {r['forecast_lost']}")
        ax.set_xticks(x,names,rotation=30,ha='right');ax.set_ylabel('Observed light points');ax.grid(axis='y',alpha=.2)
    axes.flat[0].legend(fontsize=8);fig.suptitle('Observed 0.1–1 mm forecast bands; dry false alarms use threshold 0.1 mm')
    save(fig,out/'02_weak_bands_false_alarms.png')


def map_plot(out,folder):
    arrays=e.prior.read_arrays(folder)
    fig,axes=plt.subplots(2,3,figsize=(13,8),sharex=True,sharey=True,constrained_layout=True)
    differences=[arrays[h][e.NEW]-arrays[h][e.ICE] for h in e.HOURS]
    limit=max(float(np.max(np.abs(a))) for a in differences) or 1.
    for hour,ax,diff in zip(e.HOURS,axes.flat,differences):
        v=arrays[hour];image=ax.scatter(v['longitude'],v['latitude'],c=diff,s=5,cmap='RdBu_r',vmin=-limit,vmax=limit,linewidths=0)
        ax.set_title(f'Lead {hour-12} h');ax.set_xlabel('Longitude');ax.set_ylabel('Latitude');ax.set_aspect('equal',adjustable='box')
    fig.colorbar(image,ax=axes.ravel().tolist(),label='Hourly total difference (mm)',shrink=.8)
    fig.suptitle('MP10 - PR154 on frozen RN1 points; CONTROL history is byte-identical to PR154')
    save(fig,out/'03_candidate_minus_control.png')


def run(results,output):
    if os.path.lexists(output):raise FileExistsError(output)
    inputs=sealed(results);configure();categorical=read_rows(results,'categorical_scores.csv');bands=read_rows(results,'observed_forecast_bands.csv');transitions=read_rows(results,'observation_transitions.csv')
    output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.mp10-figures-',dir=output.parent))
    try:
        csi_plot(stage,categorical);weak_plot(stage,bands,transitions);map_plot(stage,results)
        for item in inputs:
            if e.identity(item['path'])!=item:raise ValueError('input changed during plotting')
        receipt={'status':'COMPLETE','inputs':inputs,'source':e.identity(__file__),'matplotlib':matplotlib.__version__,'numpy':np.__version__,'outputs':{p.name:e.identity(p)['sha256'] for p in stage.iterdir()}}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');e.prior.publish_new(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.results,a.output)
