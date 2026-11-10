#!/usr/bin/env python3
"""Build the reviewed standalone figure gallery and verify its local links."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

BUNDLE=Path(__file__).resolve().parents[1]
ROOT=BUNDLE.parents[2]
REPORT=ROOT/'docs/CP02_MP10_PROCESS_20261110.md'
GALLERY=BUNDLE/'FIGURES.md'
ARCHIVE=BUNDLE/'all_figures.zip'


def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def links(text):
    return [x for pair in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)|!\[[^\]]*\]\(([^)]+)\)',text)
            for x in pair if x and not x.startswith(('http:','https:','#'))]


def main():
    groups=[('MP10 실제 내부 반복과 실패 지점의 과정 진단',BUNDLE/'figures',7)]
    images=[]; receipts=[]
    for title,folder,count in groups:
        receipt=folder/'receipt.json'; data=json.loads(receipt.read_text())
        if data.get('status')!='COMPLETE': raise ValueError('incomplete figure receipt')
        names={name for name in data['outputs'] if name.endswith('.png')}
        if len(names)!=count or {p.name for p in folder.glob('*.png')}!=names: raise ValueError('figure inventory mismatch')
        for name in names:
            if sha(folder/name)!=data['outputs'][name]: raise ValueError('figure hash mismatch')
        images.extend(sorted(folder/name for name in names)); receipts.append(receipt)
    if len(images)!=7: raise ValueError('expected 7 figures')
    labels={'01_transition_geometry':'실패·해소 전이와 계측 지점',
            '02_weak_conditional':'실제 약한 관측 강수의 검출·강도·조건부 오차',
            '03_surface_components':'같은 지점의 RAINC·RAINNC 차이',
            '04_cleanup_removal':'내부 반복의 미량 수상량 제거',
            '05_psd_number_adjustment':'PSD·수농도 조정의 부호 있는 변화',
            '06_state_contrasts':'진입 비·싸락눈·기온의 시간–층 차이',
            '07_public_ledger':'호출 내부·호출 사이 상태 장부'}
    text=['# MP10 내부 반복과 오경보: 그림 모음','',
          '[학술 보고서](../../CP02_MP10_PROCESS_20261110.md) · 묶음 파일: `all_figures.zip` · [모든 시간·임계값의 전체 점수](../cp02_pulse_path_20261110/evaluation/results/FULL_SCORES.md)','',
          'MP10은 22/26으로 미채택이며 현재 B1을 유지한다. 이번 진단 재적분은 두 구성의 기존 정시 history 14개를 그대로 재현한다. 30점은 과정 진단 집단이며 독립 기상 사례가 아니다.','']
    for title,folder,_ in groups:
        text.extend([f'## {title}',''])
        for image in [x for x in images if x.parent==folder]:
            label=labels.get(image.stem, f'{image.stem.split("_")[1]}시간 강수 지도')
            text.extend([f'### {label}','',f'![{label}]({image.relative_to(BUNDLE).as_posix()})',''])
    GALLERY.write_text('\n'.join(text),encoding='utf-8')
    files={REPORT,GALLERY,*images,*receipts}
    files.update((BUNDLE/'figures').glob('*.csv'))
    files.update([BUNDLE/'analysis/summary.json',BUNDLE/'native/proof/comparability.json',
                  BUNDLE/'native/compact/CONTROL/surface_audit.json',BUNDLE/'native/compact/MP10/surface_audit.json'])
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
        if any(n.lower().endswith('.pdf') or ('/native/compact/' in n and not n.endswith('/surface_audit.json')) or n.endswith('/wrf.exe') or '/wrfout_' in n for n in z.namelist()):
            raise ValueError('unintended archive member')
    if ARCHIVE.stat().st_size>=100*1024*1024: raise ValueError('archive exceeds 100 MiB')
    receipt={'status':'PASS','gallery_sha256':sha(GALLERY),'report_sha256':sha(REPORT),'archive_sha256':sha(ARCHIVE),
             'archive_size_bytes':ARCHIVE.stat().st_size,'figure_count':7,'zip_crc':'PASS',
             'local_and_archive_links':'PASS','members':members,'generator_sha256':sha(Path(__file__))}
    (BUNDLE/'gallery_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':'PASS','figures':7,'members':len(members),'archive_bytes':ARCHIVE.stat().st_size,'archive_sha256':receipt['archive_sha256']},indent=2))


if __name__=='__main__': main()
