#!/usr/bin/env python3
"""Render six paired-point hourly maps using sealed scores and offline coastlines."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import BoundaryNorm, SymLogNorm
from matplotlib.ticker import FuncFormatter
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[4]
RESULTS = HERE/'results'
COAST = ROOT/'docs/evidence/cp02_grouped_forecast_20261105/figures/data/ne_50m_coastline.geojson'
FONT = Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
COAST_SHA = '271f1c4c1908312bac6b29d158ea1356544beafc129f260005300913aa5ea283'
FONT_SHA = '48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733'
CANDIDATE = 'CONSERVATIVE_SEDIMENTATION'
B1 = 'IMPROVED_BG_FIXED'
FIELDS = ('reference','ORIGINAL',B1,CANDIDATE)
HOURS = range(13,19)


def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def load():
    receipt = json.loads((RESULTS/'receipt.json').read_text())
    if receipt.get('status') != 'COMPLETE' or receipt.get('mode') != 'forecast':
        raise ValueError('completed forecast scoring receipt required')
    hourly = {}; first_coords = None
    for hour in HOURS:
        name = f'hour_{hour}_arrays.npz'; path = RESULTS/name
        if sha(path) != receipt['outputs'][name]: raise ValueError(f'array hash mismatch: {name}')
        with np.load(path,allow_pickle=False) as data:
            record = {k:data[k].copy() for k in (*FIELDS,'latitude','longitude','flat_index_yx')}
        if any(v.shape != (3688,) or not np.isfinite(v).all() for v in record.values()):
            raise ValueError('all 3688 paired values must be finite')
        if len(np.unique(record['flat_index_yx'])) != 3688 or any(np.any(record[k] < 0) for k in FIELDS):
            raise ValueError('invalid point identity or hourly rainfall')
        coords = tuple(record[k] for k in ('flat_index_yx','latitude','longitude'))
        if first_coords is None: first_coords=coords
        elif any(not np.array_equal(a,b) for a,b in zip(first_coords,coords)):
            raise ValueError('point coordinates change between forecast hours')
        hourly[hour] = record
    return hourly


def coastline():
    if sha(COAST)!=COAST_SHA or sha(FONT)!=FONT_SHA: raise ValueError('pinned coastline or font differs')
    payload=json.loads(COAST.read_text()); lines=[]
    for feature in payload['features']:
        geo=feature['geometry']; kind=geo['type']; coord=geo['coordinates']
        segments=[coord] if kind=='LineString' else coord if kind=='MultiLineString' else []
        for segment in segments:
            line=np.asarray(segment,dtype=float)
            if line.ndim!=2 or line.shape[1]<2 or not np.isfinite(line[:,:2]).all():
                raise ValueError('invalid coastline geometry')
            lines.append(line[:,:2])
    if not lines: raise ValueError('empty coastline')
    return lines


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    hourly=load(); coast=coastline()
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(FONT)).get_name(),'axes.unicode_minus':False})
    maxrain=max(float(hourly[h][k].max()) for h in HOURS for k in FIELDS)
    delta=max(float(np.max(np.abs(hourly[h][CANDIDATE]-hourly[h][k]))) for h in HOURS for k in (B1,'ORIGINAL'))
    levels=[0,.1,.5,1,2.5,5,10,20,50,100,max(100.,maxrain)+1]
    rainnorm=BoundaryNorm(levels,256,clip=True); deltanorm=SymLogNorm(linthresh=.1,linscale=1,vmin=-max(delta,.01),vmax=max(delta,.01),clip=True)
    coords=hourly[13]; lon=coords['longitude']; lat=coords['latitude']; outputs={}
    for hour in HOURS:
        row=hourly[hour]; fig,axes=plt.subplots(3,2,figsize=(10.8,13.2),constrained_layout=True,sharex=True,sharey=True)
        panels=[('RN1 관측',row['reference'],False),('규준실험 (ORIGINAL)',row['ORIGINAL'],False),
                ('현재 B1',row[B1],False),('보존 침강 후보',row[CANDIDATE],False),
                ('후보 - 현재 B1',row[CANDIDATE]-row[B1],True),('후보 - 규준실험',row[CANDIDATE]-row['ORIGINAL'],True)]
        rain_artist=diff_artist=None
        for ax,(title,values,is_delta) in zip(axes.flat,panels):
            artist=ax.scatter(lon,lat,c=values,s=9,cmap='RdBu_r' if is_delta else 'viridis',
                              norm=deltanorm if is_delta else rainnorm,linewidths=0,rasterized=True,zorder=3)
            if is_delta: diff_artist=artist
            else: rain_artist=artist
            for line in coast: ax.plot(line[:,0],line[:,1],color='#333333',linewidth=.5,zorder=4)
            ax.set_title(title,fontsize=11); ax.set_xlim(float(lon.min()),float(lon.max())); ax.set_ylim(float(lat.min()),float(lat.max()))
            ax.set_aspect(1/np.cos(np.deg2rad(float(lat.mean()))),adjustable='box'); ax.grid(alpha=.17,linewidth=.4); ax.tick_params(labelsize=8)
        for ax in axes[-1,:]: ax.set_xlabel('경도 (°E)')
        for ax in axes[:,0]: ax.set_ylabel('위도 (°N)')
        fig.colorbar(rain_artist,ax=axes[:2,:].ravel().tolist(),orientation='vertical',label='한 시간 강수량 (mm)',ticks=levels[:-1],fraction=.025,pad=.015)
        ticks=sorted({-max(delta,.01),0.,max(delta,.01)} | {s*v for v in (.1,.5,1.,5.,10.) if v<delta for s in (-1,1)})
        fig.colorbar(diff_artist,ax=axes[2,:].ravel().tolist(),orientation='vertical',label='같은 지점 차이 (mm)',ticks=ticks,format=FuncFormatter(lambda v, pos: f'{v:g}'),fraction=.025,pad=.015)
        fig.suptitle(f'2026-08-16 12:00 UTC 초기화 · +{hour-12} h\n{hour-1:02d}:00–{hour:02d}:00 UTC 한 시간 강수량 · RN1 평가점 3,688개\n평가점만 표시 · 공간보간 없음 · 구간색 / 0 중심 대칭로그 차이색',fontsize=12)
        name=f'candidate_rn1_hour_{hour}_maps.png'; fig.savefig(args.output/name,dpi=170,metadata={'Software':'cp02 sedimentation paired maps'});plt.close(fig)
        outputs[name]=sha(args.output/name)
    meta={'inputs':{f'hour_{h}_arrays.npz':sha(RESULTS/f'hour_{h}_arrays.npz') for h in HOURS},
          'score_receipt_sha256':sha(RESULTS/'receipt.json'),'renderer_sha256':sha(Path(__file__)),
          'font_sha256':sha(FONT),'coastline_sha256':sha(COAST),'numpy':np.__version__,'matplotlib':matplotlib.__version__,
          'rain_boundaries_mm':levels,'maximum_hourly_value_mm':maxrain,'symmetric_delta_limit_mm':max(delta,.01),
          'difference_normalization':'SymLogNorm linthresh 0.1 mm', 'points':3688,'interpolation':'none; preserved paired RN1 point locations',
          'outputs':outputs}
    (args.output/'maps_metadata.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'outputs':len(outputs),'rain_max':maxrain,'delta_limit':delta}))


if __name__=='__main__': main()
