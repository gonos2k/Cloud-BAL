#!/usr/bin/env python3
"""Build the reviewed, self-contained figure gallery archive and audit its links."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

BUNDLE=Path(__file__).resolve().parent
ROOT=BUNDLE.parents[2]
REPORT=ROOT/'docs/CP02_LOW_THRESHOLD_PROCESS_20261110.md'
GALLERY=BUNDLE/'FIGURES.md'
ARCHIVE=BUNDLE/'all_figures.zip'


def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def links(text):
    return [x for x in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)|!\[[^\]]*\]\(([^)]+)\)',text) for x in x if x and not x.startswith(('http:', 'https:', '#'))]


def main():
    fig=BUNDLE/'figures'; receipt=fig/'receipt.json'; data=json.loads(receipt.read_text())
    if data['status']!='COMPLETE' or len(data['outputs'])!=27: raise ValueError('final figure receipt is incomplete')
    for name,digest in data['outputs'].items():
        if sha(fig/name)!=digest: raise ValueError('figure hash changed: '+name)
    if set(p.name for p in fig.glob('*.png'))!=set(data['outputs']): raise ValueError('figure set differs from receipt')
    titles={'01_low_false_alarm_coverage.png':'낮은 임계값 오경보 집단의 포괄 범위',
            '02_weak_detection_intensity.png':'약한 강수 검출과 예측 강도',
            '03_return_state_contrasts.png':'호출 반환 상태의 구성별 차이',
            '04_local_external_endpoint.png':'호출 내부·사이와 마지막 상태',
            '05_source_stage_contrasts.png':'실제 과정 경계의 상태 차이',
            '06_column_residual_ecdf.png':'선택 기둥의 source 잔차 분포'}
    text=['# 낮은 강수 임계값 과정 진단: 그림 모음','',
          '[전체 보고서](../../CP02_LOW_THRESHOLD_PROCESS_20261110.md) · [기존 전체 점수표](../cp02_first_ice_velocity_20261109/evaluation/results/FULL_SCORES.md)','',
          '세 구성은 같은 B1 초기장에서 적분했다. 지점은 선택 사례이며 전체 실패 집단의 통계적 표본이 아니다.','', '## 요약 그림','']
    for name,title in titles.items(): text += [f'### {title}','',f'![{title}](figures/{name})','']
    text += ['## 21개 선정 지점의 지상 강수 추적','',
             'RAINNC는 격자규모 누적 강수다. RN1 총강수와는 직접 동일시하지 않는다.','']
    for name in sorted(n for n in data['outputs'] if n.startswith('point_')):
        point=name.split('_')[1];text += [f'### 평가점 {point}','',f'![평가점 {point}의 RAINNC](figures/{name})','']
    GALLERY.write_text('\n'.join(text),encoding='utf-8')
    files=[REPORT,GALLERY,receipt,*sorted(fig.glob('*.png')),
           *sorted((BUNDLE/'cohorts/results').glob('*.csv')),
           *sorted((BUNDLE/'analysis').glob('*.csv')),
           BUNDLE/'science/h6_review/summary.json',BUNDLE/'science/h6_review/raw_event.json',
           BUNDLE/'native/proof/comparability.json',BUNDLE/'native/proof/provenance_verification.json',
           ROOT/'docs/evidence/cp02_first_ice_velocity_20261109/evaluation/results/FULL_SCORES.md']
    if len(files)!=len(set(files)) or any(not p.is_file() for p in files): raise ValueError('missing or duplicate ZIP input')
    for md in (REPORT,GALLERY):
        for link in links(md.read_text(encoding='utf-8')):
            target=(md.parent/link).resolve()
            if not target.is_file() or target not in files: raise ValueError(f'local link missing from standalone ZIP: {md}: {link}')
    with zipfile.ZipFile(ARCHIVE,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in files: z.write(path,path.relative_to(ROOT).as_posix())
    members={}
    with zipfile.ZipFile(ARCHIVE) as z:
        if z.testzip() is not None: raise ValueError('ZIP CRC failed')
        if len(z.namelist())!=len(files) or len(set(z.namelist()))!=len(files): raise ValueError('ZIP inventory differs')
        for path in files:
            name=path.relative_to(ROOT).as_posix(); digest=hashlib.sha256(z.read(name)).hexdigest()
            if digest!=sha(path): raise ValueError('ZIP member mismatch: '+name)
            members[name]={'sha256':digest,'size_bytes':path.stat().st_size}
        for md in (REPORT,GALLERY):
            entry=PurePosixPath(md.relative_to(ROOT).as_posix())
            for link in links(z.read(str(entry)).decode('utf-8')):
                parts=[]
                for part in (entry.parent/PurePosixPath(link)).parts:
                    if part=='..': parts.pop()
                    elif part!='.': parts.append(part)
                if '/'.join(parts) not in members: raise ValueError('ZIP link unresolved: '+link)
        if any(name.lower().endswith('.pdf') or '/native/compact/' in name for name in z.namelist()): raise ValueError('unintended ZIP member')
    output={'status':'PASS','gallery_sha256':sha(GALLERY),'report_sha256':sha(REPORT),'figure_receipt_sha256':sha(receipt),
            'archive_sha256':sha(ARCHIVE),'archive_size_bytes':ARCHIVE.stat().st_size,'figure_count':27,
            'zip_crc':'PASS','local_and_archive_links':'PASS','members':members,'generator_sha256':sha(Path(__file__))}
    (BUNDLE/'gallery_receipt.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({'status':'PASS','figures':27,'members':len(members),'archive_bytes':ARCHIVE.stat().st_size,'archive_sha256':output['archive_sha256']},indent=2))


if __name__=='__main__': main()
