#!/usr/bin/env python3
"""Plot source-bound activation, melting and actual weak-rain diagnostics."""
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

import cp02_mp10_process as prior
from cp02_ice_false_alarm import evaluation

ROOT=Path(__file__).resolve().parents[1]
B=ROOT/'docs/evidence/cp02_activation_path_20261110'
FONT=Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
FONT_SHA='48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733'
FALLBACK_FONT=Path(matplotlib.get_data_path())/'fonts/ttf/DejaVuSans.ttf'
COLORS=('#777777','#cc9b39','#a83b53','#198364')


def rows(path):
    with path.open(newline='') as stream:return list(csv.DictReader(stream))


def save(fig,path):
    fig.savefig(path,dpi=150,metadata={'Software':'Cloud-BAL activation path'})
    plt.close(fig)


def write(path,data):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=data[0],lineterminator='\n')
        writer.writeheader();writer.writerows(data)


def verified(folder):
    receipt_path=folder/'receipt.json';record=json.loads(receipt_path.read_text())
    if record['status'] not in ('PASS','COMPLETE') or not record.get('outputs'):
        raise ValueError('unsealed analysis: '+str(folder))
    inputs=[prior.identity(receipt_path)]
    for name,expected in record['outputs'].items():
        if Path(name).name!=name:raise ValueError('unsafe output inventory')
        item=prior.identity(folder/name)
        if item['sha256']!=expected:raise ValueError('analysis hash differs')
        inputs.append(item)
    return inputs


def point_summary(points,out):
    cases=('ORIGINAL','IMPROVED_BG_FIXED','FIRST_ICE_VELOCITY','MP10')
    labels=('규준실험','B1','PR154','MP10')
    fig,ax=plt.subplots(figsize=(10,4.5),constrained_layout=True)
    x=np.arange(3)
    data=[]
    for i,(case,label,color) in enumerate(zip(cases,labels,COLORS)):
        values=[float(p[case+'_h3_mm']) for p in points]
        ax.bar(x+(i-1.5)*.19,values,width=.18,label=label,color=color)
        data += [{'point':p['flat_index_yx'],'case':case,'forecast_mm':v,
                  'observed_mm':float(p['reference_h3_mm'])} for p,v in zip(points,values)]
    ax.axhline(.1,color='black',ls='--',lw=1,label='0.1 mm detection threshold')
    ax.set_xticks(x,[p['flat_index_yx'] for p in points])
    ax.set(xlabel='Evaluation point',ylabel='Hour-3 precipitation (mm)',
           title='Actual weak observations: 12000 / 12001 / 12002\nObserved 0.4 / 0.6 / 0.8 mm; detection is distinct from amount accuracy')
    ax.legend(ncol=3);ax.grid(axis='y',alpha=.2)
    save(fig,out/'01_weak_points.png');write(out/'01_weak_points.csv',data)


def native_nn(data,out):
    anchor=[r for r in data if int(r['point'])==12446 and int(r['step'])==989 and int(r['i'])==154 and int(r['j'])==89]
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
    exported=[]
    for ax,arm,color in zip(axes,('CONTROL','MP10'),COLORS[2:]):
        records=sorted((r for r in anchor if r['arm']==arm),key=lambda r:int(r['loop']))
        if len(records)!=(1 if arm=='CONTROL' else 2):raise ValueError('anchor loop coverage differs')
        labels=[];values=[]
        for r in records:
            for phase in (8,11,12,33,34):
                labels.append(f"L{r['loop']} P{phase}");value=float(r[f'nn_{phase}']);values.append(value/1e8)
                exported.append({'arm':arm,'step':989,'i':154,'j':89,'k':16,'loop':r['loop'],'phase':phase,'NN_m3':value})
        ax.plot(range(len(values)),values,'o-',color=color)
        ax.axhline(1,color='black',ls='--',lw=.8)
        ax.set_xticks(range(len(values)),labels,rotation=55,ha='right')
        ax.set(title='PR154: 20 s once' if arm=='CONTROL' else 'MP10: 10 s twice',ylabel='NN / 10⁸ m⁻³')
        ax.grid(alpha=.2)
    fig.suptitle('Measured activation reservoir at point 12446, step 989, native k=16\nPhase positions are computational boundaries, not equally spaced physical times',fontsize=11)
    save(fig,out/'02_native_nn_cycle.png');write(out/'02_native_nn_cycle.csv',exported)


def partitions(data,out):
    main=next(r for r in data if int(r['point'])==12446 and int(r['step'])==982)
    melt=next(r for r in data if int(r['point'])==12446 and int(r['step'])==989)
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),constrained_layout=True)
    names=('exposure_pracw','exposure_paacw','exposure_prevp','exposure_pseml','exposure_pgeml','exposure_praut')
    values=[float(main[n])*1e6 for n in names]
    axes[0].bar(range(6),values,color='#a83b53')
    axes[0].set_xticks(range(6),('pracw','2×paacw','prevp','−pseml','−pgeml','praut'),rotation=25)
    axes[0].axhline(0,color='black',lw=.7);axes[0].set(title='Step 982: source main-update terms',ylabel='MP10 − PR154 increment (mg kg⁻¹)')
    names2=('pre_main_qr','pre_main_qs','pre_main_qg','pre_main_qv')
    axes[1].bar(range(4),[float(melt[n])*1e6 for n in names2],color=('#198364','#777777','#cc9b39','#3d83b9'))
    axes[1].set_xticks(range(4),('QR','QS','QG','QV'))
    axes[1].axhline(0,color='black',lw=.7)
    axes[1].set(title='Step 989: after sedimentation → pre-main\nSelected warm-branch proof; ice melt can also affect T',ylabel='MP10 − PR154 increment (mg kg⁻¹)')
    for ax in axes:ax.grid(axis='y',alpha=.2)
    fig.suptitle('Point 12446, native k=16: observed increments, not causal fractions',fontsize=12)
    save(fig,out/'03_process_partitions.png')
    write(out/'03_process_partitions.csv',[{'boundary':b,'term':n,'delta_kg_kg':float(r[n])}
          for b,r,ns in [('main_step982',main,names),('pre_main_step989',melt,names2)] for n in ns])


def historical_series(data,out):
    fig,axes=plt.subplots(2,2,figsize=(11,7),constrained_layout=True)
    exported=[]
    for column,point in enumerate((12446,12892)):
        selected=sorted((r for r in data if int(r['point'])==point),key=lambda r:int(r['step']))
        for row,(field,label,scale) in enumerate((('main_qr','Main QR update',1e6),('pre_main_qr','Post-sedimentation → pre-main QR',1e6))):
            ax=axes[row,column];ax.plot([int(r['step']) for r in selected],[float(r[field])*scale for r in selected],'o-')
            ax.axhline(0,color='black',lw=.7);ax.axvline(989,color='#198364',ls='--',lw=.7)
            ax.set(title=f'{point}: {label}',xlabel='Outer step (20 s)',ylabel='MP10 − PR154 (mg kg⁻¹)')
            ax.grid(alpha=.2)
            exported += [{'point':point,'step':r['step'],'field':field,'delta_kg_kg':r[field]} for r in selected]
    fig.suptitle('Existing hour-6 records: same native level k=16, distinct process paths',fontsize=12)
    save(fig,out/'04_historical_process_time.png');write(out/'04_historical_process_time.csv',exported)


def weak_plots(folder,out):
    data={}
    for arm in ('CONTROL','MP10'):
        with np.load(folder/(arm+'.npz'),allow_pickle=False) as z:data[arm]={k:v.copy() for k,v in z.items()}
    with np.load(folder/'paired.npz',allow_pickle=False) as z:paired={k:v.copy() for k,v in z.items()}
    fig,axes=plt.subplots(1,3,figsize=(13,4),constrained_layout=True);exported=[]
    for arm,color,label in zip(('CONTROL','MP10'),COLORS[2:],('PR154','MP10')):
        with np.load(folder/(arm+'_surface.npz'),allow_pickle=False) as z:
            minutes=(z['step']-360)/3
            for p,ax in enumerate(axes):
                values=z['rainnc_since_hour_start'][:,p];ax.plot(minutes,values,color=color,label=label)
                exported += [{'arm':arm,'point':int(z['point'][p]),'step':int(s),'RAINNC_since_hour_start_mm':float(v)} for s,v in zip(z['step'],values)]
    for point,ax in zip((12000,12001,12002),axes):
        ax.axhline(.1,color='black',ls='--',lw=.8);ax.set(title=str(point),xlabel='Minutes into hour 3',ylabel='RAINNC since hour start (mm)');ax.grid(alpha=.2)
    axes[0].legend();fig.suptitle('Measured third-hour rain: RAINC increment independently verified zero',fontsize=12)
    save(fig,out/'05_weak_surface_time.png');write(out/'05_weak_surface_time.csv',exported)
    fig,axes=plt.subplots(3,2,figsize=(12,10),constrained_layout=True);exported=[]
    for p,point in enumerate((12000,12001,12002)):
        for col,(field,label) in enumerate((('activation_delta','Activation NN consumption'),('nn_lower_restore','NN lower-bound restoration'))):
            ax=axes[p,col]
            for arm,color,name in zip(('CONTROL','MP10'),COLORS[2:],('PR154','MP10')):
                z=data[arm]
                # k=14 contains the measured floor-binding sample; it is not altitude.
                values=(-z[field][:,p,13,1] if field=='activation_delta' else z[field][:,p,13])
                cumulative=np.cumsum(values,dtype=np.float64)
                ax.plot((z['step']-360)/3,cumulative,color=color,label=name)
                exported += [{'arm':arm,'point':point,'k':14,'step':int(s),'field':field,'change_m3':float(v),'cumulative_m3':float(c)} for s,v,c in zip(z['step'],values,cumulative)]
            ax.set(title=f'{point}: {label}',xlabel='Minutes into hour 3',ylabel='Cumulative operation (number m⁻³)');ax.grid(alpha=.2)
    axes[0,0].legend();fig.suptitle('Native k=14: signed state changes summed over actual loops\nRepeated operator amounts are not a conserved particle inventory',fontsize=12)
    save(fig,out/'06_weak_activation_time.png');write(out/'06_weak_activation_time.csv',exported)
    fig,axes=plt.subplots(3,2,figsize=(12,9),constrained_layout=True);exported=[]
    for p,point in enumerate((12000,12001,12002)):
        for c,(field,name,scale) in enumerate((('QR','QR',1e6),('TK','Temperature',1))):
            index=list(paired['public_fields']).index(field)
            values=paired['public_entry'][:,p,:,index].T*scale
            bound=float(abs(values).max())
            ax=axes[p,c]
            image=ax.imshow(values,origin='lower',aspect='auto',extent=(0,60,.5,39.5),vmin=-max(bound,1e-30),vmax=max(bound,1e-30),cmap='RdBu_r')
            fig.colorbar(image,ax=ax,label='mg kg⁻¹' if field=='QR' else 'K')
            ax.set(title=f'{point}: entry {name}',xlabel='Minutes into hour 3',ylabel='Native k (1–39)')
            exported += [{'point':point,'step':int(s),'k':k+1,'field':field,'MP10_minus_PR154_native_unit':float(paired['public_entry'][t,p,k,index])} for t,s in enumerate(paired['step']) for k in range(39)]
    fig.suptitle('Actual weak-rain columns: per-panel scales, MP10 − PR154\nNative differences precede bilinear weights; k is not altitude',fontsize=12)
    save(fig,out/'07_weak_entry_state.png');write(out/'07_weak_entry_state.csv',exported)


def replay_plot(data,out):
    cases=list(dict.fromkeys(r['input'] for r in data))
    if len(cases)!=4 or len(data)!=12:raise ValueError('local replay scope differs')
    fig,axes=plt.subplots(2,2,figsize=(10,7),constrained_layout=True)
    exported=[]
    for ax,case in zip(axes.flat,cases):
        selected={r['variant']:r for r in data if r['input']==case}
        base=float(selected['20_once']['NC'])
        variants=('20_once','10_eachfloor','10_endonly')
        differences=[float(selected[v]['NC'])-base for v in variants]
        ax.bar(range(3),differences,color=('#777777','#a83b53','#198364'))
        ax.set_xticks(range(3),('20 s once','2×10 s / each floor','2×10 s / final floor'),rotation=15)
        ax.set(title=case,ylabel='NC difference to 20 s (m⁻³)')
        ax.axhline(0,color='black',lw=.6);ax.grid(axis='y',alpha=.2)
        if not any(differences):ax.text(.5,.6,'Replayed states equal',transform=ax.transAxes,ha='center')
        exported += [dict(r,NC_difference_to_20=delta) for r,delta in zip((selected[v] for v in variants),differences)]
    fig.suptitle('Extracted activation + NN floor: fixed preactivation inputs\nSynthetic and measured cases; not full KDM6 or a forecast score',fontsize=11)
    save(fig,out/'08_fixed_input_replay.png');write(out/'08_fixed_input_replay.csv',exported)


def run(output,weak=None):
    if os.path.lexists(output):raise FileExistsError(output)
    if prior.identity(FONT)['sha256']!=FONT_SHA:raise ValueError('font differs')
    font_manager.fontManager.addfont(FONT)
    font_manager.fontManager.addfont(FALLBACK_FONT)
    plt.rcParams.update({'font.family':['NanumGothic','DejaVu Sans'],'axes.unicode_minus':False,'font.size':9})
    inputs=[prior.identity(FONT),prior.identity(FALLBACK_FONT),prior.identity(Path(__file__))]+verified(B/'analysis')
    points_path=B/'cohorts/selected_points.csv';inputs.append(prior.identity(points_path))
    points=rows(points_path)
    if [int(r['flat_index_yx']) for r in points]!=[12000,12001,12002]:raise ValueError('point scope differs')
    if weak is not None:inputs+=verified(weak)
    replay_path=B/'local_replay/results/comparisons.csv'
    replay_receipt=B/'local_replay/results/receipt.json'
    local=json.loads(replay_receipt.read_text())
    if local['status']!='PASS' or local['row_count']!=12 or prior.identity(replay_path)['sha256']!=local['comparisons_sha256']:
        raise ValueError('local replay receipt differs')
    inputs += [prior.identity(replay_path),prior.identity(replay_receipt)]
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.activation-figures-',dir=output.parent))
    try:
        native=rows(B/'analysis/native_loops.csv');paired=rows(B/'analysis/paired_weighted.csv')
        point_summary(points,stage);native_nn(native,stage);partitions(paired,stage);historical_series(paired,stage)
        if weak is not None:weak_plots(weak,stage)
        replay_plot(rows(replay_path),stage)
        for item in inputs:
            if prior.identity(item['path'])!=item:raise ValueError('figure input changed')
        (stage/'receipt.json').write_text(json.dumps({'status':'COMPLETE','inputs':inputs,'matplotlib':matplotlib.__version__,
              'outputs':{p.name:prior.identity(p)['sha256'] for p in sorted(stage.iterdir())}},indent=2)+'\n')
        evaluation.publish_new(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--weak',type=Path)
    args=parser.parse_args();run(args.output,args.weak)
