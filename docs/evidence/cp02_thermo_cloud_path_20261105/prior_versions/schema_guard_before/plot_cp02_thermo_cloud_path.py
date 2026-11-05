#!/usr/bin/env python3
"""Render selected two-hour thermodynamic/cloud traces from verified split arrays."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import SymLogNorm
from matplotlib.ticker import FuncFormatter
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
ANALYSIS = BUNDLE / 'analysis'
OUTPUT = BUNDLE / 'figures'
FONT = Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
PINS = {'font': '48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733', 'capture': 'e41105c152b55991784f1fcf0b8c8e1c75fe03fc3d33160b897160adadd33245', 'paired_manifest': 'ecc4729ce321510e93aaef118e9b578464cb46776b8f5c3fbca74c55dd851440', 'points': '3343201b904a9b9874fea8f174715e37f1d642871f371bf1f378ed8a13a62197', 'surface_receipt': 'ea30ce9690ffa799fdf96f2ca2132ca953790f94deb77443641ae5e174eff516', 'surface': 'de81cd987b12c32ea84a240af17b5edd7391bd26e2e500f47e93b4ebb81137e2', 'rain_presence':'c50770c4b6ea3a750159be696e0d61e7a99966a2c5526543e6c1a92fb73f8c7e'}
PAIRED_KEYS = ('entry_difference','within_call_difference','between_call_difference','phase_5_difference','sedimentation_net_difference','between_theta_difference','between_exner_difference','between_product_roundoff_difference','gap_post_update_to_pre_cond_q_difference','gap_post_cond_to_return_q_difference','prevp_q_difference','condensation_q_change_difference')
PINS['schema'] = '64496e9f19ec0042762a7b8fa7d4f8006ea617a45433434242706c223db2210c'
GROUPS = ('new_fa_initial_nr_unchanged','removed_fa_initial_nr_unchanged','weak_lost','weak_retained_nearest_control')
GROUP_LABELS = ('신규 오경보 15','오경보 해소 12','약한 적중 소실 6','근접 적중 유지 6')


def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def read_csv(path):
    with path.open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))


def load_parts(manifest, names):
    spec=importlib.util.spec_from_file_location('selected_parts_loader',ROOT/'tools/pack_cp02_selected_npz.py')
    if spec is None or spec.loader is None: raise RuntimeError('missing verified parts loader')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.load_partarrays(manifest,names=list(names))


def verify_anchor_controls(points):
    by_flat={int(r['flat_index_yx']):r for r in points}; removed=[r for r in points if r['group']==GROUPS[1]]
    def distance(a,b):
        lat1,lon1,lat2,lon2=map(math.radians,(float(a['latitude']),float(a['longitude']),float(b['latitude']),float(b['longitude'])))
        h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
        return 12742*math.asin(math.sqrt(min(1.,max(0.,h))))
    for anchor,expected in ((17051,16454),(20183,20330)):
        nearest=min(removed,key=lambda r:(distance(by_flat[anchor],r),int(r['flat_index_yx'])))
        if int(nearest['flat_index_yx'])!=expected:raise ValueError('geographic comparator differs')


def load_verified():
    paths={'capture':ANALYSIS/'full_capture_receipt.json','paired_manifest':ANALYSIS/'paired_differences_parts/paired_differences.parts.json','points':BUNDLE/'cohorts/results/selected_points.csv','surface_receipt':BUNDLE/'science/surface_reference/receipt.json','surface':BUNDLE/'science/surface_reference/point_components.csv','rain_presence':ANALYSIS/'rain_presence_recount.csv','font':FONT}
    paths['schema']=BUNDLE/'native/schema/cp04_schema.json'
    for key,path in paths.items():
        if not path.is_file() or path.is_symlink() or sha(path)!=PINS[key]: raise ValueError(f'pinned input mismatch: {key}')
    schema=json.loads(paths['schema'].read_text())
    if schema['wrapper_selected']['fields']!=['TH','QV','QC','QR','QI','QS','QG','NN','NC','NI','NR','BG','DEN','TK=TH*PII','P','PII'] or schema['phases']['5']['fields'][:2]!=['praut(i,k)','pracw(i,k)']:
        raise ValueError('CP04 wrapper or rate field order differs')
    capture=json.loads(paths['capture'].read_text()); manifest=json.loads(paths['paired_manifest'].read_text()); sr=json.loads(paths['surface_receipt'].read_text())
    if capture['status']!='PASS_FULL_CAPTURE' or capture['steps']!=360 or capture['levels']!=39 or len(capture['point_ids'])!=39 or manifest['source_sha256']!=capture['paired_outputs']['paired_differences.npz']['sha256'] or sr['status']!='PASS' or sr['outputs']['point_components.csv']['sha256']!=PINS['surface']:
        raise ValueError('capture, part manifest or surface receipt differs')
    points=read_csv(paths['points']); ids=[r['point_id'] for r in points]
    if ids!=capture['point_ids'] or len(set(ids))!=39 or [sum(r['group']==g for r in points) for g in GROUPS]!=[15,12,6,6]: raise ValueError('point order or cohort differs')
    expected={17051:'NFA05',20183:'NFA12',16454:'RFA08',20330:'RFA11'}
    if {int(r['flat_index_yx']):r['point_id'] for r in points if int(r['flat_index_yx']) in expected}!=expected: raise ValueError('anchor identities differ')
    verify_anchor_controls(points)
    surface=read_csv(paths['surface']); keys={(r['arm'],r['point_id'],int(r['lead_hour'])) for r in surface}
    if len(surface)!=156 or len(keys)!=156 or keys!={(arm,point,lead) for arm in ('B1','DM065') for point in ids for lead in (1,2)}: raise ValueError('surface reference coverage differs')
    for r in surface:
        nc,cumulus,total,canonical,residual,bound=(float(r[k]) for k in ('RAINNC_hour_mm','RAINC_hour_mm','total_hour_mm','canonical_hour_mm','residual_mm','gamma64_bound_mm'))
        if not np.isfinite([nc,cumulus,total,canonical,residual,bound]).all() or abs(residual)>bound or not np.isclose(total-canonical,residual,rtol=1e-12,atol=1e-14) or not np.isclose(nc+cumulus,total,rtol=1e-12,atol=1e-14): raise ValueError('surface reconstruction invalid')
    arrays=load_parts(paths['paired_manifest'],PAIRED_KEYS)
    for key,value in arrays.items():
        n=359 if key.startswith('between_') else 360
        if value.shape[:3]!=(n,39,39) or not np.isfinite(value).all(): raise ValueError(f'invalid paired shape or missing mandatory data: {key}')
    return points,surface,arrays,paths


def configure_font():
    font_manager.fontManager.addfont(str(FONT));plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(FONT)).get_name(),'axes.unicode_minus':False,'savefig.dpi':130})


def draw_source_order(path):
    fig,ax=plt.subplots(figsize=(16,3),constrained_layout=True);ax.axis('off')
    labels=['래퍼 ENTRY\n원시 / 제한','포화 진단','비·눈·싸락눈\n침강 PRE / POST','조건부 지상 반환\nRAINNC','포화도 및 제한된\nPRAUT / PRACW\n주 과정 갱신','미할당 중간 변화\n(원인 미분해)','FINALCOND\nPRE / POST','정리 / PSD\n래퍼 RETURN']
    for i,label in enumerate(labels):
        x=(i+.5)/len(labels);ax.text(x,.55,label,ha='center',va='center',fontsize=10,transform=ax.transAxes,bbox={'boxstyle':'round,pad=.4','facecolor':'#edf3f8','edgecolor':'#718096'})
        if i<len(labels)-1: ax.annotate('',xy=((i+1.0)/len(labels)+.005,.55),xytext=((i+1.0)/len(labels)-.005,.55),xycoords=ax.transAxes,arrowprops={'arrowstyle':'->','color':'#555'})
    ax.text(.5,.2,'기록된 구름→비 생성 갱신은 같은 호출의 침강 뒤에 위치 · 호출 사이 변화와 미할당 구간은 단일 원인으로 해석하지 않음',ha='center',fontsize=11,transform=ax.transAxes)
    fig.suptitle('CP04 관측 단계의 실제 소스 순서',fontsize=16);fig.savefig(path,metadata={'Software':'CP04 plotter'});plt.close(fig)


def draw_surface(points,surface,path):
    ids=('NFA05','RFA08','NFA12','RFA11');lookup={(r['arm'],r['point_id'],int(r['lead_hour'])):r for r in surface}; point={r['point_id']:r for r in points}
    fig,axes=plt.subplots(2,2,figsize=(13,9),constrained_layout=True)
    for ax,pid in zip(axes.flat,ids):
        ymax=0.
        for lead in (1,2):
            for offset,arm in ((-.18,'B1'),(.18,'DM065')):
                r=lookup[arm,pid,lead];x=lead+offset;nc=float(r['RAINNC_hour_mm']); cu=float(r['RAINC_hour_mm'])
                ax.bar(x,nc,.32,color='#1769a3',label='RAINNC' if lead==1 and arm=='B1' else None);ax.bar(x,cu,.32,bottom=nc,color='#e4a432',label='RAINC' if lead==1 and arm=='B1' else None)
                ymax=max(ymax,nc+cu)
                ax.text(x,nc+cu,f'{nc+cu:.3g}',ha='center',va='bottom',fontsize=8)
        ax.set_ylim(0,max(ymax*1.2,1e-12));ax.set_xticks([.82,1.18,1.82,2.18],['+1 B1','+1 후보','+2 B1','+2 후보']);ax.set_ylabel('시간 강수량 (mm)');ax.set_title(f"{pid} · RN1 평면 {point[pid]['flat_index_yx']}");ax.grid(axis='y',alpha=.2)
    fig.legend(*axes[0,0].get_legend_handles_labels(),loc='outside lower center',ncols=2);fig.suptitle('지상 시간 강수 성분 · RAINC는 KDM6 반환 밖의 대류 성분',fontsize=15)
    fig.savefig(path,metadata={'Software':'CP04 plotter'});plt.close(fig)


def panels(arrays):
    entry=arrays['entry_difference'];rates=arrays['phase_5_difference'];sed=arrays['sedimentation_net_difference']
    return [('ENTRY QC 차이','kg/kg',entry[...,2]),('ENTRY QR 차이','kg/kg',entry[...,3]),('제한 PRAUT + PRACW 차이','kg/kg/s',rates[...,0]+rates[...,1]),('침강 QR 순증분 차이','kg/kg per call',sed[...,0]),('ENTRY QV 차이','kg/kg',entry[...,1]),('ENTRY 기온 차이','K',entry[...,13])]


def limit(data, indices):
    finite=np.abs(data[:,:,indices]);finite=finite[np.isfinite(finite)];return max(float(finite.max()) if finite.size else 0.,1e-30)


def heat(ax,data,limit_value,unit,steps=1):
    hours=np.arange(steps,steps+data.shape[0])/180
    norm=SymLogNorm(linthresh=limit_value/1000,vmin=-limit_value,vmax=limit_value)
    im=ax.pcolormesh(hours,np.arange(1,40),np.ma.masked_invalid(data.T),cmap='coolwarm',norm=norm,shading='auto')
    ax.set_xlabel('단계 종료 예측시간 (h)');ax.set_ylabel('모형층 번호');return im


def draw_anchor(points,arrays,anchor,control,path):
    ids=[r['point_id'] for r in points];indices=[ids.index(anchor),ids.index(control)]; variables=panels(arrays); all_indices=[ids.index(x) for x in ('NFA05','RFA08','NFA12','RFA11')]
    fig,axes=plt.subplots(2,6,figsize=(24,9),constrained_layout=True)
    for col,(title,unit,data) in enumerate(variables):
        scale=limit(data,all_indices)
        for row,index in enumerate(indices):
            ax=axes[row,col];im=heat(ax,data[:,:,index],scale,unit);ax.set_title(f'{ids[index]} · {title}',fontsize=9)
            fig.colorbar(im,ax=ax,label=unit,ticks=[-scale,-scale/100,0,scale/100,scale],format=FuncFormatter(lambda x,_:f'{x:.1g}'))
    fig.suptitle(f'{anchor} 와 {control} · 후보 - B1 · 근접 지리 비교 (물리적 동질성 미가정)',fontsize=15)
    fig.savefig(path,metadata={'Software':'CP04 plotter'});plt.close(fig)


def amplitude(data,point_index):
    v=np.abs(data[:,:,point_index]);finite=v[np.isfinite(v)]
    return float(finite.max()) if finite.size else np.nan


def draw_groups(points,arrays,path):
    entry=arrays['entry_difference'];local=arrays['within_call_difference'];between=arrays['between_call_difference'];rates=arrays['phase_5_difference'];sed=arrays['sedimentation_net_difference']
    metrics=[('ENTRY QC','kg/kg',entry[...,2]),('ENTRY QR','kg/kg',entry[...,3]),('호출 내 QV','kg/kg',local[...,1]),('호출 내 기온','K',local[...,13]),('호출 사이 QV','kg/kg',between[...,1]),('호출 사이 기온','K',between[...,13]),('PRAUT + PRACW','kg/kg/s',rates[...,0]+rates[...,1]),('침강 QR 증분','kg/kg per call',sed[...,0]),('PREVP 수증기 성분','kg/kg per call',arrays['prevp_q_difference']),('FINALCOND 수증기 성분','kg/kg per call',arrays['condensation_q_change_difference']),('갱신 후 미할당 QV','kg/kg',arrays['gap_post_update_to_pre_cond_q_difference']),('응결 후 미할당 QV','kg/kg',arrays['gap_post_cond_to_return_q_difference'])]
    fig,axes=plt.subplots(3,4,figsize=(18,13),constrained_layout=True); rows=[]
    for ax,(title,unit,data) in zip(axes.flat,metrics):
        boxes=[];positions=[];labels=[]
        for pos,(group,label) in enumerate(zip(GROUPS,GROUP_LABELS),1):
            indices=[i for i,r in enumerate(points) if r['group']==group];vals=np.array([amplitude(data,i) for i in indices]);vals=vals[np.isfinite(vals)];labels.append(f'{label}\nn={len(vals)}/{len(indices)}')
            if len(vals):
                q1,med,q3=np.quantile(vals,[.25,.5,.75]);boxes.append({'med':med,'q1':q1,'q3':q3,'whislo':vals.min(),'whishi':vals.max(),'fliers':[]});positions.append(pos)
            for i,v in zip(indices,[amplitude(data,i) for i in indices]): rows.append({'point_id':points[i]['point_id'],'group':group,'metric':title,'unit':unit,'max_abs':v if np.isfinite(v) else ''})
        if boxes:ax.bxp(boxes,positions=positions,showfliers=False)
        ax.set_xticks(range(1,5),labels,rotation=20,ha='right',fontsize=7);ax.set_title(title);ax.set_ylabel(unit);ax.grid(axis='y',alpha=.2)
    fig.suptitle('39개 지점 집단별 0–2시간·39층 최대 절대 차이 (중앙값 / 사분위 / 전체 범위)',fontsize=15)
    fig.savefig(path,metadata={'Software':'CP04 plotter'});plt.close(fig);return rows


def draw_first_rain(path):
    rows=read_csv(ANALYSIS/'rain_presence_recount.csv'); ids=('NFA05','RFA08','NFA12','RFA11');stages=('wrapper_entry','main_post_update','wrapper_return');series=('B1','DM065','DM065_minus_B1')
    keyed={(r['point_id'],r['stage'],r['arm_or_difference']):r for r in rows if r['field']=='QR' and r['point_id'] in ids and r['stage'] in stages and r['arm_or_difference'] in series}
    if len(keyed)!=36:raise ValueError('rain first-sample key coverage mismatch')
    fig,axes=plt.subplots(2,2,figsize=(14,10),constrained_layout=True)
    for ax,pid in zip(axes.flat,ids):
        for j,(arm,label,color,marker) in enumerate(zip(series,('B1 최초 양의 QR','후보 최초 양의 QR','후보-B1 최초 비영 차이'),('#1769a3','#c34435','#60378e'),('o','s','x'))):
            for k,stage_name in enumerate(stages):
                row=keyed[pid,stage_name,arm];value=row['first_sample_step']
                if value:
                    x=float(value)/3; y=k+(j-1)*.15
                    ax.scatter(x,y,color=color,marker=marker,s=40,label=label if k==0 else None)
                    ax.annotate(f"{float(row['first_sample_value']):.1e}",(x,y),xytext=(3,3),textcoords='offset points',fontsize=6)
        ax.set_yticks(range(3),('래퍼 ENTRY','주 갱신 후','래퍼 RETURN'));ax.set_xlim(0,128);ax.set_xlabel('단계 종료 예측시간 (분)');ax.set_title(pid);ax.grid(alpha=.2)
    fig.legend(*axes[0,0].get_legend_handles_labels(),loc='outside lower center',ncols=3,fontsize=9)
    fig.suptitle('최초로 표본된 양의 QR과 최초 비영 구성 차이 · 수치는 kg/kg',fontsize=14)
    fig.savefig(path,metadata={'Software':'CP04 plotter'});plt.close(fig)


def draw_thermo(points,arrays,path):
    ids=[r['point_id'] for r in points]; indices=[ids.index('NFA05'),ids.index('NFA12')];bc=arrays['between_call_difference']
    terms=[('ENTRY 압력 차이','Pa',arrays['entry_difference'][...,14],1),('ENTRY PII 차이','1',arrays['entry_difference'][...,15],1),('호출 사이 기온 차이','K',bc[...,13],2),('온위 항의 차이','K',arrays['between_theta_difference'],2),('Exner 항의 차이','K',arrays['between_exner_difference'],2),('곱 반올림 잔차 차이','K',arrays['between_product_roundoff_difference'],2),('갱신 후–응결 전 QV 미할당 차이','kg/kg',arrays['gap_post_update_to_pre_cond_q_difference'],1),('응결 후–반환 QV 미할당 차이','kg/kg',arrays['gap_post_cond_to_return_q_difference'],1)]
    fig,axes=plt.subplots(2,8,figsize=(30,9),constrained_layout=True)
    for col,(title,unit,data,first) in enumerate(terms):
        scale=limit(data,indices)
        for row,index in enumerate(indices):
            ax=axes[row,col];im=heat(ax,data[:,:,index],scale,unit,first);ax.set_title(f'{ids[index]} · {title}',fontsize=8)
            fig.colorbar(im,ax=ax,label=unit,ticks=[-scale,0,scale],format=FuncFormatter(lambda x,_:f'{x:.1g}'))
    fig.suptitle('후보 - B1 · 호출 사이 온도 항은 대수 분해, 미할당 구간과 순변화는 원인 분해가 아님',fontsize=14)
    fig.savefig(path,metadata={'Software':'CP04 plotter'});plt.close(fig)


def write_csv(path,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)


def render(output):
    output=Path(output)
    if os.path.lexists(output):raise FileExistsError(output)
    points,surface,arrays,paths=load_verified();configure_font();output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.cp04-figures-',dir=output.parent))
    try:
        names=('source_order.png','surface_components.png','anchor_17051.png','anchor_20183.png','group_amplitudes.png','temperature_algebra.png','first_rain_samples.png')
        draw_source_order(stage/names[0]);draw_surface(points,surface,stage/names[1]);draw_anchor(points,arrays,'NFA05','RFA08',stage/names[2]);draw_anchor(points,arrays,'NFA12','RFA11',stage/names[3]);rows=draw_groups(points,arrays,stage/names[4]);draw_thermo(points,arrays,stage/names[5]);draw_first_rain(stage/names[6]);write_csv(stage/'group_amplitudes.csv',rows)
        gallery='# 2시간 구름·비·열역학 경로\n\n단계 표시는 단계 종료시각이며 ENTRY와 내부 단계는 그 단계 중 관측이다. 색상은 후보−B1; 각 물리량에서 비교 지점의 공통 대칭 척도다. PRAUT/PRACW는 같은 호출의 침강 이후에 기록된다. 조건부 미관측은 0이 아니며 호출 사이와 미할당 구간은 특정 물리 원인으로 귀속하지 않는다. 현재 B1과 후보의 고정 오일러 지점 비교이며 궤적이 아니다. [39지점별 진폭 표](group_amplitudes.csv)\n\nNFA05(17051)↔RFA08(16454), NFA12(20183)↔RFA11(20330)는 각각 가장 가까운 해소 지점으로 약 21.1 km와 11.5 km 떨어져 있다. 지리적 비교이며 물리적 동질성을 가정하지 않는다. NFA12의 +1시간 총강수에는 별도 RAINC가 포함되고 +2시간 성분은 RAINNC다. 최초 양의 QR은 최초 구성 간 차이와 다르다. 빌리니어 평균에 원시 모서리의 qcrmin을 적용하지 않는다.\n\n'+'\n\n'.join(f'![{n}]({n})' for n in names)+'\n'
        (stage/'gallery.md').write_text(gallery,encoding='utf-8')
        html='<!doctype html><html lang="ko"><meta charset="utf-8"><title>2시간 구름·비·열역학 경로</title><style>body{font-family:sans-serif;max-width:1200px;margin:auto;padding:1rem}img{width:100%;height:auto}figure{margin:2rem 0}</style><h1>2시간 구름·비·열역학 경로</h1><p>고정 오일러 지점의 기술 진단입니다. 단계 표시는 단계 종료시각이며 내부 관측의 정확한 시각이 아닙니다. 호출 사이와 미할당 변화는 원인 분해가 아닙니다. 진폭 표는 0–2시간의 지점별 최대 절대값입니다.</p><p><a href="gallery.md">설명</a> · <a href="group_amplitudes.csv">39지점 진폭 표</a></p>'+''.join(f'<figure><figcaption>{n}</figcaption><img src="{n}" loading="lazy" alt="{n}"></figure>' for n in names)+'</html>\n'
        (stage/'index.html').write_text(html,encoding='utf-8')
        meta={'status':'PASS','input_sha256':{k:sha(v) for k,v in paths.items()},'renderer_sha256':sha(Path(__file__)),'loader_sha256':sha(ROOT/'tools/pack_cp02_selected_npz.py'),'matplotlib_version':matplotlib.__version__,'point_count':len(points),'outputs':{n:sha(stage/n) for n in (*names,'group_amplitudes.csv','gallery.md','index.html')}}
        (stage/'metadata.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        with zipfile.ZipFile(stage/'offline_gallery.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
            for name in (*names,'group_amplitudes.csv','gallery.md','index.html','metadata.json'):
                info=zipfile.ZipInfo(name,(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,(stage/name).read_bytes())
        with zipfile.ZipFile(stage/'offline_gallery.zip') as z:
            if z.testzip() is not None:raise ValueError('ZIP integrity error')
        receipt={'status':'PASS','metadata_sha256':sha(stage/'metadata.json'),'offline_gallery_sha256':sha(stage/'offline_gallery.zip'),'figure_count':len(names)}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        if os.path.lexists(output):raise FileExistsError(output)
        stage.rename(output)
    finally:
        if stage.exists():shutil.rmtree(stage)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=OUTPUT);args=p.parse_args();render(args.output)


if __name__=='__main__':main()
