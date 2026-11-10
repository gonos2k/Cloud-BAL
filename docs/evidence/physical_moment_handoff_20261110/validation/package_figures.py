#!/usr/bin/env python3
"""Package report figures and linked evidence, preserving relative Markdown links."""
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT/'docs/evidence/physical_moment_handoff_20261110'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def links(text):
    return [p for p in re.findall(r'\]\(([^)]+)\)',text) if not p.startswith(('https:','http:','#'))]


def main():
    report=ROOT/'docs/PHYSICAL_MOMENT_INITIALIZATION_20261110.md'
    gallery=BUNDLE/'FIGURES.md';archive=BUNDLE/'report_figures.zip'
    gallery.write_text('''# 물·열·모멘트 초기화: 그림과 자료

[학술 보고서](../../PHYSICAL_MOMENT_INITIALIZATION_20261110.md) · [보고서·그림·핵심 자료 ZIP](report_figures.zip) · [모형 입력 계약](../../MODEL_MOMENT_HANDOFF.md)

새 예보·강수 점수는 없다. 실제 B1 입력에 적용한 고정 사전값은 NI 상한 위반으로 거부됐으며 현재 B1을 유지한다. 그림은 초기화 구조와 이론적 PSD 자유도를 나타낸다.

## 초기화의 물리 경로와 실제 사용 경계

![초기화 경로](figures/01_initialization_path.png)

## 같은 비 질량에 가능한 입경·입자수·반사도

관측이나 최적 입경을 뜻하지 않는 이론 예시이다.

![비 PSD의 자유도](figures/02_rain_psd_freedom.png)

[이론 자료 CSV](figures/rain_psd_family.csv) · [실제 생산 재생·초기화 거부 근거](native/actual_real/README.md)
''')
    figure_receipt=json.loads((BUNDLE/'figures/receipt.json').read_text())
    assert figure_receipt['status']=='PASS' and len(figure_receipt['outputs'])==3
    for name,digest in figure_receipt['outputs'].items():assert sha(BUNDLE/'figures'/name)==digest
    files={report,gallery,BUNDLE/'figures/receipt.json',*(BUNDLE/'figures'/n for n in figure_receipt['outputs'])}
    files.update(p for p in (BUNDLE/'native/actual_real').iterdir() if p.is_file())
    queue=[report,gallery];seen=set()
    while queue:
        md=queue.pop()
        if md in seen:continue
        seen.add(md)
        for name in links(md.read_text()):
            path=(md.parent/name.split('#',1)[0]).resolve()
            if path==archive:continue
            assert path.is_relative_to(ROOT) and path.is_file(),(md,name)
            files.add(path)
            if path.suffix=='.md':queue.append(path)
    assert not any(p.suffix=='.pdf' or p.stat().st_size>=100*1024**2 for p in files)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(files):z.write(p,p.relative_to(ROOT).as_posix())
    members={}
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(set(z.namelist()))==len(files)
        for p in files:
            name=p.relative_to(ROOT).as_posix();assert hashlib.sha256(z.read(name)).hexdigest()==sha(p)
            members[name]={'sha256':sha(p),'size_bytes':p.stat().st_size}
    receipt={'status':'PASS','figures':2,'report_sha256':sha(report),'gallery_sha256':sha(gallery),
             'archive_sha256':sha(archive),'archive_size_bytes':archive.stat().st_size,'zip_crc':'PASS',
             'local_links':'PASS','members':members,'generator_sha256':sha(__file__)}
    (BUNDLE/'gallery_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':'PASS','figures':2,'members':len(members),'archive_bytes':archive.stat().st_size}))


if __name__=='__main__':main()
