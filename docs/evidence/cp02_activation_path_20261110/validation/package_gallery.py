#!/usr/bin/env python3
"""Build the reviewed standalone figure gallery and verify its local links."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

BUNDLE=Path(__file__).resolve().parents[1]
ROOT=BUNDLE.parents[2]
REPORT=ROOT/'docs/CP02_ACTIVATION_PATH_20261110.md'
GALLERY=BUNDLE/'FIGURES.md'
ARCHIVE=BUNDLE/'all_figures.zip'


def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def links(text):
    return [x for pair in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)|!\[[^\]]*\]\(([^)]+)\)',text)
            for x in pair if x and not x.startswith(('http:','https:','#'))]


def main():
    groups=[('활성화·융해와 실제 약한 강수 대조',BUNDLE/'figures',8),('전 구성 시간별 강수 지도와 CSI 개요',BUNDLE/'evaluation/figures',7),('임계값별 CSI와 규준실험 대비 강수 차이',BUNDLE/'evaluation/supplementary_figures',12)]
    images=[]; receipts=[]
    for title,folder,count in groups:
        receipt=folder/'receipt.json'; data=json.loads(receipt.read_text())
        if data.get('status')!='COMPLETE': raise ValueError('incomplete figure receipt')
        names={name for name in data['outputs'] if name.endswith('.png')}
        if len(names)!=count or {p.name for p in folder.glob('*.png')}!=names: raise ValueError('figure inventory mismatch')
        for name in names:
            if sha(folder/name)!=data['outputs'][name]: raise ValueError('figure hash mismatch')
        images.extend(sorted(folder/name for name in names)); receipts.append(receipt)
    if len(images)!=27: raise ValueError('expected 27 figures')
    labels={'01_weak_points':'실제 약한 강수 세 지점의 비교','02_native_nn_cycle':'실제 활성화·NN 하한 복원',
            '03_process_partitions':'주 과정 비 증가와 침강 후 융해','04_historical_process_time':'과잉점의 과정 시간 변화',
            '05_weak_surface_time':'실제 약한 강수의 지상 도달 시간','06_weak_activation_time':'활성화와 NN 하한 복원 시간합',
            '07_weak_entry_state':'실제 약한 강수의 진입 상태 차이','08_fixed_input_replay':'고정 입력 활성화 재생',
            'csi_by_hour_threshold':'시간·임계값별 전체 CSI'}
    text=['# 활성화·NN 복원 시점: 그림 27장 모음','',
          '[학술 보고서](../../CP02_ACTIVATION_PATH_20261110.md) · [그림 ZIP](all_figures.zip) · [전체 점수표](evaluation/FULL_SCORES.md)','',
          'MP10_NN_END는 보호 9/11·회복 12/15, 합계 21/26으로 미채택이며 현재 B1을 유지한다. 규준실험은 ORIGINAL이다. 지도는 RN1 평가점 3,688개에 대응한 한 시간 강수량이며, 차이 지도는 각 실험에서 규준실험을 뺀 값이다.','']
    for title,folder,_ in groups:
        text.extend([f'## {title}',''])
        for image in [x for x in images if x.parent==folder]:
            label=labels.get(image.stem,image.stem)
            if image.stem.startswith('hour_'): label=f'+{image.stem.split("_")[1]}시간 ' + ('강수량−규준실험 차이 지도' if 'difference' in image.stem else '모든 실험 강수 지도')
            if image.stem.startswith('csi_threshold_'): label=f'임계값 {(.1,.5,1,2.5,5,10)[int(image.stem.rsplit("_",1)[1])-1]:g} mm: CSI와 B1 대비 차이'
            text.extend([f'### {label}','',f'![{label}]({image.relative_to(BUNDLE).as_posix()})',''])
    GALLERY.write_text('\n'.join(text),encoding='utf-8')
    files={REPORT,GALLERY,*images,*receipts}
    files.update((BUNDLE/'figures').glob('*.csv'))
    files.update([BUNDLE/'weak_analysis/summary.json',BUNDLE/'native/proof/comparability.json',BUNDLE/'forecast/proof/comparability.json',BUNDLE/'evaluation/results/verdict.json',BUNDLE/'evaluation/results/admission_constraints.csv',BUNDLE/'evaluation/results/weak_bands.csv'])
    for md in (REPORT,GALLERY):
        for link in links(md.read_text(encoding='utf-8')):
            path=(md.parent/link.split('#',1)[0]).resolve()
            if path == ARCHIVE.resolve(): continue
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
                if '/'.join(parts) == ARCHIVE.relative_to(ROOT).as_posix(): continue
                if '/'.join(parts) not in members: raise ValueError('ZIP link unresolved: '+link)
        if any(n.lower().endswith('.pdf') or ('/native/compact/' in n and not n.endswith('/surface_audit.json')) or n.endswith('/wrf.exe') or '/wrfout_' in n for n in z.namelist()):
            raise ValueError('unintended archive member')
    if ARCHIVE.stat().st_size>=100*1024*1024: raise ValueError('archive exceeds 100 MiB')
    receipt={'status':'PASS','gallery_sha256':sha(GALLERY),'report_sha256':sha(REPORT),'archive_sha256':sha(ARCHIVE),
             'archive_size_bytes':ARCHIVE.stat().st_size,'figure_count':27,'zip_crc':'PASS',
             'local_and_archive_links':'PASS','members':members,'generator_sha256':sha(Path(__file__))}
    (BUNDLE/'gallery_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':'PASS','figures':27,'members':len(members),'archive_bytes':ARCHIVE.stat().st_size,'archive_sha256':receipt['archive_sha256']},indent=2))


if __name__=='__main__': main()
