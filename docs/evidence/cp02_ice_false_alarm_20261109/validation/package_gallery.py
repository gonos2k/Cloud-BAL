#!/usr/bin/env python3
"""Publish the false-alarm gallery and a self-contained, link-checked ZIP."""
import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[4]
CURRENT = Path('docs/evidence/cp02_ice_false_alarm_20261109')
PRIOR = Path('docs/evidence/cp02_first_ice_velocity_20261109')
REPORT = Path('docs/CP02_ICE_FALSE_ALARM_20261109.md')
PRIOR_RECEIPT = PRIOR/'gallery_receipt.json'
NEW_RECEIPT = CURRENT/'figures/receipt.json'
PRIOR_RECEIPT_SHA = 'c451caf49e92316ed97323f4368e50ac73ff6a3c0946cea28f0c332bce2674e5'
NEW = [
    ('6시간 오경보 평가점', 'h6_false_alarm_map.png'),
    ('6시간 오경보 집단의 시간별 강수', 'h6_pointwise_paths.png'),
    ('첫 시간 새 오경보 3개 평가점', 'h1_three_false_alarms.png'),
    ('약한 관측 강수의 예측 강도', 'weak_observed_intensity.png'),
]
PRIOR_FIGURES = [
    *( (f'{t} mm 이상 시간별 CSI', f'csi_{t}mm.png') for t in ('0.1','0.5','1','2.5','5','10') ),
    *( (f'+{h-12}시간: {h-1:02d}–{h:02d} UTC 한 시간 강수', f'rn1_hour_{h}_maps.png') for h in range(13,19) ),
]


def record(path):
    with path.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'sha256':digest, 'size_bytes':path.stat().st_size}


def validate_figure_receipts(expected_new):
    if record(ROOT/NEW_RECEIPT)['sha256'] != expected_new: raise ValueError('new figure receipt changed')
    if record(ROOT/PRIOR_RECEIPT)['sha256'] != PRIOR_RECEIPT_SHA: raise ValueError('prior gallery receipt changed')
    new=json.loads((ROOT/NEW_RECEIPT).read_text())
    prior=json.loads((ROOT/PRIOR_RECEIPT).read_text())
    if new.get('status') != 'COMPLETE' or set(new.get('outputs',{})) != {name for _,name in NEW}: raise ValueError('new figure receipt scope mismatch')
    if prior.get('status') != 'PASS' or prior.get('png_count') != 12: raise ValueError('prior gallery receipt scope mismatch')
    for _,name in NEW:
        if record(ROOT/CURRENT/'figures'/name)['sha256'] != new['outputs'][name]: raise ValueError(f'new figure mismatch: {name}')
    for _,name in PRIOR_FIGURES:
        if record(ROOT/PRIOR/'figures'/name) != prior['members'][f'figures/{name}']: raise ValueError(f'prior figure mismatch: {name}')


def gallery_text():
    opening = ('기존 PR154 예측의 저장 결과를 재분석한 진단입니다. 새 예측 적분은 수행하지 않았습니다. '
               'RN1 공통 평가점 3,688개와 시간별 누적 강수 차이를 사용합니다. '
               '그룹은 결과에 따른 사후 분류이며, RAINC와 RAINNC는 단일 물리 과정의 원인으로 해석할 수 없습니다.')
    sections = [(title, f'figures/{name}') for title,name in NEW]
    sections += [(title, f'../cp02_first_ice_velocity_20261109/figures/{name}') for title,name in PRIOR_FIGURES]
    links = [('분석 보고서', '../../CP02_ICE_FALSE_ALARM_20261109.md'),
             ('PR154 전체 점수', '../cp02_first_ice_velocity_20261109/evaluation/results/FULL_SCORES.md'),
             ('평가점 집단', 'cohorts/membership.csv'), ('평가점별 경로', 'cohorts/point_paths.csv'),
             ('강수 강도 구간', 'cohorts/lead_bins.csv'),
             ('시간별 표면 강수 성분', 'surface/native/hourly_points.csv'),
             ('고정 집단 성분 평균', 'surface/native/group_means.csv')]
    md = ['# 첫 빙정 수정 후보 오경보 진단', '', opening, '']
    md += [f'[{label}]({url})  ' for label,url in links]
    for title,url in sections: md += ['', f'## {title}', '', f'![{title}]({url})']
    body = ['<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>첫 빙정 수정 후보 오경보 진단</title>',
            '<style>body{font-family:sans-serif;max-width:1100px;margin:auto;padding:1rem;line-height:1.5}img{max-width:100%;height:auto}section{margin:2rem 0}nav a{margin-right:1em}</style></head><body>',
            '<h1>첫 빙정 수정 후보 오경보 진단</h1>',f'<p>{html.escape(opening)}</p>','<nav>']
    body += [f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>' for label,url in links]
    body += ['</nav>']
    body += [f'<section><h2>{html.escape(title)}</h2><img src="{html.escape(url,quote=True)}" alt="{html.escape(title,quote=True)}"></section>' for title,url in sections]
    body += ['</body></html>']
    return '\n'.join(md)+'\n', '\n'.join(body)+'\n'


class Links(HTMLParser):
    def __init__(self): super().__init__(); self.urls=[]
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key in ('href','src') and value: self.urls.append(value)


def local_links(path, data):
    text=data.decode('utf-8')
    if path.suffix == '.html':
        parser=Links();parser.feed(text); urls=parser.urls
    else:
        urls=re.findall(r'!?\[[^\]]*\]\(\s*<?([^\s)>]+)>?(?:\s+[^)]*)?\)',text)
    result=[]
    for url in urls:
        parsed=urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path: continue
        target=PurePosixPath(os.path.normpath(str(path.parent / unquote(parsed.path))))
        if target.is_absolute() or '..' in target.parts: raise ValueError(f'link escapes archive root: {path}: {url}')
        result.append(Path(target))
    return result


def publish(files):
    published=[]
    try:
        for source,dest in files:
            os.link(source,dest)
            published.append(dest)
    except BaseException:
        for path in published: path.unlink()
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--figure-receipt-sha256',required=True)
    p.add_argument('--report-sha256',required=True)
    args=p.parse_args()
    destination=ROOT/CURRENT
    outputs=[destination/name for name in ('FIGURES.md','gallery.html','all_figures.zip','gallery_receipt.json')]
    if any(os.path.lexists(x) for x in outputs): raise FileExistsError('gallery output already exists')
    if record(ROOT/REPORT)['sha256'] != args.report_sha256: raise ValueError('final report changed')
    validate_figure_receipts(args.figure_receipt_sha256)
    md,web=gallery_text()
    fixed=[REPORT,NEW_RECEIPT,PRIOR_RECEIPT,
           *(CURRENT/'figures'/name for _,name in NEW),
           *(PRIOR/'figures'/name for _,name in PRIOR_FIGURES),
           PRIOR/'evaluation/results/FULL_SCORES.md',
           *(CURRENT/'cohorts'/name for name in ('membership.csv','point_paths.csv','lead_bins.csv')),
           *(CURRENT/'surface/native'/name for name in ('hourly_points.csv','group_means.csv'))]
    stage=Path(tempfile.mkdtemp(prefix='.gallery-',dir=destination))
    try:
        (stage/'FIGURES.md').write_text(md,encoding='utf-8');(stage/'gallery.html').write_text(web,encoding='utf-8')
        generated={CURRENT/'FIGURES.md':(stage/'FIGURES.md').read_bytes(),CURRENT/'gallery.html':(stage/'gallery.html').read_bytes()}
        # Every direct local link in the report and both galleries is a ZIP member.
        links=[]
        for path,data in [(REPORT,(ROOT/REPORT).read_bytes()),*generated.items()]: links.extend(local_links(path,data))
        paths=set(fixed) | set(links)
        sources={path:record(ROOT/path) for path in paths if path not in generated}
        members={**{path:(ROOT/path).read_bytes() for path in sources},**generated}
        if any(path not in members for path in links): raise ValueError('archive has an unresolved local link')
        archive=stage/'all_figures.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for path,data in sorted(members.items()): z.writestr(path.as_posix(),data)
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None or set(z.namelist()) != {p.as_posix() for p in members}: raise ValueError('archive verification failed')
            for path,data in members.items():
                if z.read(path.as_posix()) != data: raise ValueError(f'archive member changed: {path}')
        for path,expected in sources.items():
            if record(ROOT/path) != expected: raise ValueError(f'source changed during packaging: {path}')
        validate_figure_receipts(args.figure_receipt_sha256)
        receipt={'status':'PASS','new_forecast_integration':False,'figure_count':16,'input_figure_receipt':record(ROOT/NEW_RECEIPT),'prior_gallery_receipt':record(ROOT/PRIOR_RECEIPT),'report':record(ROOT/REPORT),'sources':{str(k):v for k,v in sorted(sources.items())},'members':{str(k):{'sha256':hashlib.sha256(v).hexdigest(),'size_bytes':len(v)} for k,v in sorted(members.items())},'outputs':{x.name:record(x) for x in (stage/'FIGURES.md',stage/'gallery.html',archive)},'packager':record(Path(__file__))}
        (stage/'gallery_receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
        publish([(stage/p.name,p) for p in outputs])
        print(json.dumps({'status':'PASS','members':len(members),'figures':16,'links':len(links)}))
    finally: shutil.rmtree(stage)

if __name__ == '__main__': main()
