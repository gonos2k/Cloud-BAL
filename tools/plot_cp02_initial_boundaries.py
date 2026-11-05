#!/usr/bin/env python3
"""Render pinned global and selected first-call boundary evidence."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap, BoundaryNorm
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'docs/evidence/cp02_initial_boundaries_20261105'
OUTPUT=BUNDLE/'figures'
FONT=Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
PINS={'font':'48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733','global_receipt':'f76b74141410d5b287c554467fd0f3803fe9a8c8debceb6e33dd30639aa69681','selected_receipt':'d93b979f455c7ff07a38deb04af3c6ea1ae8196b01f9775bd7a0420ed2b76219','plan':'06bcef5161a9d1016e19f8344c8ca086f8f83650c94f1a284054fda9ef184812'}
FIELDS=('TH','QV','QC','QR','QI','QS','QG','NN','NC','NI','NR','BG','DEN','TK','P','PII')
ANCHORS=('NFA05','NFA12','RFA08','RFA11')


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def load():
    paths={'font':FONT,'global_receipt':BUNDLE/'results/receipt.json','selected_receipt':BUNDLE/'baseline/results/receipt.json','plan':BUNDLE/'plan.json'}
    for key,path in paths.items():
        if not path.is_file() or path.is_symlink() or sha(path)!=PINS[key]:raise ValueError(f'pinned input mismatch: {key}')
    g=json.loads(paths['global_receipt'].read_text()); s=json.loads(paths['selected_receipt'].read_text())
    if g['status']!='PASS' or s['status']!='PASS' or g['plan_sha256']!=PINS['plan'] or s['steps']!=[1,2,3,4] or s['native_cells']!=123 or tuple(s['fields'])!=FIELDS:raise ValueError('scope or selected schema mismatch')
    gp=BUNDLE/'results/domain_and_support.npz';sp=BUNDLE/'baseline/results/early_selected.npz'
    if sha(gp)!=g['outputs']['domain_and_support.npz']['sha256'] or sha(sp)!=s['outputs']['early_selected.npz']:raise ValueError('source derivative hash mismatch')
    with np.load(gp,allow_pickle=False) as z:domain={k:z[k].copy() for k in z.files}
    with np.load(sp,allow_pickle=False) as z:selected={k:z[k].copy() for k in z.files}
    called=domain['called']; initial=domain['initial_NR_changed'];entry=domain['entry_NR_changed']
    if called.shape!=(282,234,39) or initial.shape!=called.shape or entry.shape!=called.shape or np.any(entry&~called):raise ValueError('domain coverage mismatch')
    if not np.all((called.sum(axis=2)==0) | (called.sum(axis=2)==39)):raise ValueError('partial called columns require level-wise masking')
    initial_called=initial&called
    if int(called.sum())!=g['summary']['called_cells'] or int(initial_called.sum())!=199111 or int(entry.sum())!=353417 or int((entry&~initial_called).sum())!=154317 or int((initial_called&~entry).sum())!=11:raise ValueError('global counts inconsistent')
    for key in ('B1_entry','DM065_entry','B1_return','DM065_return'):
        if selected[key].shape!=(4,39,123,16) or not np.isfinite(selected[key]).all():raise ValueError('invalid selected trace')
    if tuple(selected['fields'])!=FIELDS or selected['point_corner_indices'].shape!=(39,4) or selected['point_corner_weights'].shape!=(39,4):raise ValueError('invalid point mapping')
    ids=list(selected['point_ids'].astype(str))
    if len(set(ids))!=39 or any(x not in ids for x in ANCHORS):raise ValueError('anchor identities differ')
    return g,domain,selected,paths


def font():
    font_manager.fontManager.addfont(str(FONT));plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(FONT)).get_name(),'axes.unicode_minus':False,'savefig.dpi':140})


def support_map(domain,selected,path):
    called=domain['called'].any(axis=2);fig,axes=plt.subplots(1,2,figsize=(13,7),constrained_layout=True)
    cmap=ListedColormap(['#ffffff','#b9def1','#56a3c8','#195b83','#e09836','#bc4226']);cmap.set_bad('#9e9e9e');norm=BoundaryNorm([-.5,.5,1.5,5.5,10.5,20.5,39.5],cmap.N)
    for ax,key,title in zip(axes,('initial_NR_changed_levels','entry_NR_changed_levels'),('초기 입력 QNRAIN 차이','첫 KDM6 ENTRY NR 차이')):
        data=np.ma.masked_where(~called,domain[key]);im=ax.imshow(data,origin='lower',interpolation='nearest',cmap=cmap,norm=norm,aspect='equal');ax.set_title(title);ax.set_xlabel('native i (0부터)');ax.set_ylabel('native j (0부터)')
    ids=list(selected['point_ids'].astype(str)); inset=axes[1].inset_axes([0.03,0.57,0.43,0.39]); inset.set_facecolor('white')
    for pid,color in zip(ANCHORS,('#0065a8','#c32630','#14834f','#8b45a8')):
        index=ids.index(pid); corners=selected['native_cells_i_j_1based'][selected['point_corner_indices'][index]]-1
        ij=np.average(corners,axis=0,weights=selected['point_corner_weights'][index]);inset.scatter(*ij,s=30,color=color,label=pid,zorder=3)
        for ax in axes:ax.scatter(*ij,s=35,facecolors='none',edgecolors='black',linewidths=1,zorder=3)
    inset.set_title('4개 지점의 가중 위치 (native 0부터)',fontsize=8);inset.set_xlabel('i',fontsize=8);inset.set_ylabel('j',fontsize=8);inset.tick_params(labelsize=7);inset.legend(fontsize=6,loc='center left',bbox_to_anchor=(1,0.5));inset.grid(alpha=.2)
    fig.colorbar(im,ax=axes.tolist(),label='차이가 있는 모형층 수 (회색: 호출되지 않은 영역)',ticks=[0,1,3,8,15,30]);fig.suptitle('호출된 각 native 열에서 B1과 후보 비 입자수 혼합비가 다른 층 수',fontsize=15)
    fig.savefig(path,metadata={'Software':'CP02 boundary plotter'});plt.close(fig)


def counts_plot(receipt,path):
    summary=receipt['summary'];cross=summary['comparisons']['entry_NR']['input_NR_cross'];labels=('입력과 ENTRY 둘 다 다름','ENTRY만 다름','입력만 다름','둘 다 같음'); vals=[cross['both'],cross['entry_only'],cross['input_only'],cross['neither']]
    fig,axes=plt.subplots(1,2,figsize=(14,5),constrained_layout=True)
    bars=axes[0].barh(labels,vals,color=['#426f98','#d07b2f','#ae493c','#aeb7bc']);axes[0].bar_label(bars,fmt='%d',padding=4,fontsize=9);axes[0].set_xlim(0,max(vals)*1.25);axes[0].set_xlabel('호출된 native 셀 수 (열 × 층)');axes[0].set_title('초기 NR × 첫 ENTRY NR')
    names=('NR','QC','QV','TH','TK');v=[summary['comparisons']['entry_'+name]['changed'] for name in names];bars=axes[1].bar(names,v,color='#3d7aa3');axes[1].bar_label(bars,fmt='%d',padding=4);axes[1].set_ylim(0,max(v)*1.2);axes[1].set_ylabel('후보와 B1이 다른 호출 셀 수');axes[1].set_title('첫 ENTRY 필드별 차이')
    fig.suptitle('첫 호출의 실제 영역 2,533,440개 셀 · 수치 부등 비교',fontsize=15);fig.savefig(path,metadata={'Software':'CP02 boundary plotter'});plt.close(fig)


def frontier_counts(selected):
    ids=list(selected['point_ids'].astype(str));corners=selected['point_corner_indices'];diff=selected['DM065_entry'].astype(np.float64)-selected['B1_entry'].astype(np.float64)
    return {pid:np.count_nonzero(diff[:,:,corners[ids.index(pid)],:],axis=(1,2)).T for pid in ANCHORS}


def frontier_plot(selected,path):
    counts=frontier_counts(selected);fig,axes=plt.subplots(2,2,figsize=(13,11),constrained_layout=True)
    for ax,pid in zip(axes.flat,ANCHORS):
        im=ax.imshow(counts[pid],origin='upper',aspect='auto',vmin=0,vmax=156,cmap='YlOrRd',interpolation='nearest')
        for field in range(16):
            for step in range(4):
                n=int(counts[pid][field,step])
                if n:ax.text(step,field,str(n),ha='center',va='center',fontsize=7,color='white' if n>100 else 'black')
        ax.set_yticks(range(16),FIELDS);ax.set_xticks(range(4),('+20 s','+40 s','+60 s','+80 s'));ax.set_title(pid);ax.set_xlabel('단계 종료시각 (호출은 그 단계 중)')
    fig.colorbar(im,ax=axes.ravel().tolist(),label='서로 다른 native 모서리 × 층 수 (최대 156)');fig.suptitle('4개 지점의 최초 4단계 ENTRY · 정확히 다른 native 표본',fontsize=15)
    fig.savefig(path,metadata={'Software':'CP02 boundary plotter'});plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUTPUT);a=parser.parse_args();out=a.output
    if os.path.lexists(out):raise FileExistsError(out)
    receipt,domain,selected,paths=load();font();out.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.boundaries-figures-',dir=out.parent))
    try:
        names=('native_nr_support.png','first_entry_counts.png','first_four_entry_frontier.png');support_map(domain,selected,stage/names[0]);counts_plot(receipt,stage/names[1]);frontier_plot(selected,stage/names[2])
        gallery='# 초기 입력과 첫 KDM6 경계\n\n그림은 고정된 두 예보의 표본된 경계 차이를 나타냅니다. 호출되지 않은 셀은 0이 아닙니다. 첫 네 단계는 단계 종료시각으로 표시하며 호출은 단계 중 일어납니다. 원시 native 모서리×층의 개수는 빌리니어 평균이 아니며 최초 기록 차이는 원인이나 실제 최초 분기 시각을 증명하지 않습니다. 전역 14개 필드에 P/PII는 없고, 선택된 모서리의 16개 필드에만 P/PII가 있습니다. KDM6 내부 T→TH→TK 재구성은 호출 내 변화에 포함됩니다.\n\n'+'\n\n'.join(f'![{n}]({n})' for n in names)+'\n';(stage/'gallery.md').write_text(gallery,encoding='utf-8')
        html='<!doctype html><html lang="ko"><meta charset="utf-8"><title>초기 입력과 첫 호출 경계</title><style>body{font-family:sans-serif;max-width:1200px;margin:auto}img{width:100%;height:auto}</style><h1>초기 입력과 첫 호출 경계</h1><p>미호출 셀은 결측이며 원인과 실제 최초 분기는 확인되지 않았습니다.</p>'+''.join(f'<figure><figcaption>{n}</figcaption><img src="{n}" alt="{n}" loading="lazy"></figure>' for n in names)+'</html>\n';(stage/'index.html').write_text(html,encoding='utf-8')
        metadata={'status':'PASS','inputs':{k:sha(v) for k,v in paths.items()},'source_derivatives':{'domain_and_support.npz':sha(BUNDLE/'results/domain_and_support.npz'),'early_selected.npz':sha(BUNDLE/'baseline/results/early_selected.npz')},'source_sha256':sha(Path(__file__)),'matplotlib':matplotlib.__version__,'outputs':{name:sha(stage/name) for name in (*names,'gallery.md','index.html')}};(stage/'metadata.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        with zipfile.ZipFile(stage/'offline_gallery.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
            for name in (*names,'gallery.md','index.html','metadata.json'):
                info=zipfile.ZipInfo(name,(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,(stage/name).read_bytes())
        with zipfile.ZipFile(stage/'offline_gallery.zip') as z:
            if z.testzip() is not None:raise ValueError('ZIP verification failure')
        (stage/'receipt.json').write_text(json.dumps({'status':'PASS','metadata_sha256':sha(stage/'metadata.json'),'offline_gallery_sha256':sha(stage/'offline_gallery.zip'),'figure_count':len(names)},indent=2)+'\n')
        if os.path.lexists(out):raise FileExistsError(out)
        stage.rename(out)
    finally:
        if stage.exists():shutil.rmtree(stage)


if __name__=='__main__':main()
