#!/usr/bin/env python3
"""Build the reviewed standalone figure gallery and verify its local links."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

BUNDLE=Path(__file__).resolve().parents[1]
ROOT=BUNDLE.parents[2]
REPORT=ROOT/'docs/CP02_PULSE_PATH_AND_SUBSTEPS_20261110.md'
GALLERY=BUNDLE/'FIGURES.md'
ARCHIVE=BUNDLE/'all_figures.zip'


def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def links(text):
    return [x for pair in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)|!\[[^\]]*\]\(([^)]+)\)',text)
            for x in pair if x and not x.startswith(('http:','https:','#'))]


def main():
    groups=[('급증의 과정 분석',BUNDLE/'figures',7),('후보의 점수와 비교',BUNDLE/'evaluation/figures',3),
            ('관측점의 시간별 강수',BUNDLE/'evaluation/hourly_maps',6)]
    images=[]; receipts=[]
    for title,folder,count in groups:
        receipt=folder/'receipt.json'; data=json.loads(receipt.read_text())
        if data.get('status')!='COMPLETE': raise ValueError('incomplete figure receipt')
        names={name for name in data['outputs'] if name.endswith('.png')}
        if len(names)!=count or {p.name for p in folder.glob('*.png')}!=names: raise ValueError('figure inventory mismatch')
        for name in names:
            if sha(folder/name)!=data['outputs'][name]: raise ValueError('figure hash mismatch')
        images.extend(sorted(folder/name for name in names)); receipts.append(receipt)
    if len(images)!=16: raise ValueError('expected 16 figures')
    labels={'01_surface_cumulative':'지상 누적 강수','02_surface_pulse_zoom':'5분 강수 급증의 시간 변화',
            '03_QR_CONSERVATIVE-FIX':'PR153−B1 비 혼합비','04_QG_CONSERVATIVE-FIX':'PR153−B1 싸락눈 혼합비',
            '05_QR_ICE_FIXED-CONSERVATIVE':'PR154−PR153 비 혼합비','06_QG_ICE_FIXED-CONSERVATIVE':'PR154−PR153 싸락눈 혼합비',
            '07_cold_qg_terms':'급증 전 싸락눈 성장 항','01_csi_change':'시간과 임계값별 CSI 차이',
            '02_weak_bands_false_alarms':'약한 강수 예측과 오경보','03_candidate_minus_control':'후보와 대조의 차이'}
    text=['# 강수 급증과 내부 시간분할: 그림 모음','',
          '[전체 보고서](../../CP02_PULSE_PATH_AND_SUBSTEPS_20261110.md) · [전체 점수표](evaluation/results/FULL_SCORES.md)','',
          'MP10은 26개 조건 중 22개를 충족해 채택되지 않았으며 B1을 유지한다. 과정 진단은 선택 사례의 분석이고, 시간분할 실험은 전체 미세물리 연산에 대한 수치 민감도다.','']
    for title,folder,_ in groups:
        text.extend([f'## {title}',''])
        for image in [x for x in images if x.parent==folder]:
            label=labels.get(image.stem, f'{image.stem.split("_")[1]}시간 강수 지도')
            text.extend([f'### {label}','',f'![{label}]({image.relative_to(BUNDLE).as_posix()})',''])
    GALLERY.write_text('\n'.join(text),encoding='utf-8')
    files={REPORT,GALLERY,*images,*receipts}
    files.update((BUNDLE/'evaluation/results').glob('*.csv'))
    files.update([BUNDLE/'evaluation/results/FULL_SCORES.md',BUNDLE/'evaluation/results/verdict.json',
                  BUNDLE/'evaluation/results/receipt.json',BUNDLE/'evaluation/hourly_maps/hourly_rainfall_points.csv',
                  BUNDLE/'forecast/proof/comparability.json',BUNDLE/'forecast/runtime_metadata.json',
                  BUNDLE/'forecast/proof/artifact_manifest.json',BUNDLE/'native/core_qg_partition.csv',
                  BUNDLE/'native/sediment_faces_summary.csv',BUNDLE/'native/sediment_recount_receipt.json',
                  BUNDLE/'analysis/receipt.json'])
    for md in (REPORT,GALLERY):
        for link in links(md.read_text(encoding='utf-8')):
            path=(md.parent/link.split('#',1)[0]).resolve()
            if not path.is_relative_to(ROOT.resolve()) or not path.is_file(): raise ValueError(f'unresolved local link: {md}: {link}')
            files.add(path)
    files={p.resolve() for p in files}
    if any(not p.is_file() for p in files): raise ValueError('missing package input')
    with zipfile.ZipFile(ARCHIVE,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(files): z.write(path,path.relative_to(ROOT).as_posix())
    members={}
    with zipfile.ZipFile(ARCHIVE) as z:
        if z.testzip() is not None or len(z.namelist())!=len(files) or len(set(z.namelist()))!=len(files): raise ValueError('ZIP CRC or inventory failed')
        for path in sorted(files):
            name=path.relative_to(ROOT).as_posix();digest=hashlib.sha256(z.read(name)).hexdigest()
            if digest!=sha(path): raise ValueError('ZIP member hash mismatch')
            members[name]={'sha256':digest,'size_bytes':path.stat().st_size}
        for md in (REPORT,GALLERY):
            entry=PurePosixPath(md.relative_to(ROOT).as_posix())
            for link in links(z.read(str(entry)).decode('utf-8')):
                parts=[]
                for part in (entry.parent/PurePosixPath(link.split('#',1)[0])).parts:
                    if part=='..': parts.pop()
                    elif part!='.': parts.append(part)
                if '/'.join(parts) not in members: raise ValueError('ZIP link unresolved: '+link)
        if any(n.lower().endswith('.pdf') or '/native/compact/' in n or n.endswith('/wrf.exe') or '/wrfout_' in n for n in z.namelist()):
            raise ValueError('unintended archive member')
    if ARCHIVE.stat().st_size>=100*1024*1024: raise ValueError('archive exceeds 100 MiB')
    receipt={'status':'PASS','gallery_sha256':sha(GALLERY),'report_sha256':sha(REPORT),'archive_sha256':sha(ARCHIVE),
             'archive_size_bytes':ARCHIVE.stat().st_size,'figure_count':16,'zip_crc':'PASS',
             'local_and_archive_links':'PASS','members':members,'generator_sha256':sha(Path(__file__))}
    (BUNDLE/'gallery_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':'PASS','figures':16,'members':len(members),'archive_bytes':ARCHIVE.stat().st_size,'archive_sha256':receipt['archive_sha256']},indent=2))


if __name__=='__main__': main()
