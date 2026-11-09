#!/usr/bin/env python3
"""Build the inline and offline four-figure research gallery without editing images."""
import hashlib
import html
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_protected_process_20261106'
FIGURES = [
    ('figures/whole_domain_weak_hits.png', '그림 1. 동일 초기장의 예보시간별 실제 약한 강수 검출',
     '실제 약한 관측 구간은 0.1≤RN1<1 mm, 검출은 예측≥0.1 mm다. 시간이나 임계값을 평균하지 않는다.'),
    ('figures/protected_failure_map.png', '그림 2. 실패·보호 집단과 인접 오경보의 위치',
     'OA와 XA 소실 집단을 구분한다. 신규·해소 오경보 33·30은 X→A 비교다. 화살표는 공간 이웃 대응이며 강수계 이동 경로가 아니다.'),
    ('figures/qrain_lower_layer_plus1h.png', '그림 3. 하층 비 혼합비의 원래 양·남은 양과 지점별 차이',
     '0–1 km 모형층 산술평균 뒤 공간 보간한 진단이다. 질량 평균이 아니며 중앙값의 차이와 차이의 중앙값을 구분한다.'),
    ('native_figures/two_point_process_components.png', '그림 4. 실제 호출 경계의 고정 모형층별 과정 비교',
     'RN1_10942의 +2시간과 RN1_12299의 +5시간이다. 호출 내부 L과 그 분해항을 중복 합산하지 않는다. E는 호출 사이 전체 순변화이며 순수 이류가 아니다.'),
]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    targets = [BUNDLE / name for name in ('FIGURES.md', 'gallery.html', 'all_figures.zip', 'gallery_receipt.json')]
    if any(path.exists() or path.is_symlink() for path in targets):
        raise FileExistsError('preserve the existing combined gallery before regeneration')
    native = json.loads((BUNDLE / 'native_figures/receipt.json').read_text())
    if native['status'] != 'PASS' or native['figures'][Path(FIGURES[-1][0]).name] != sha(BUNDLE / FIGURES[-1][0]):
        raise ValueError('native figure receipt does not bind the real image')
    for name, _title, _caption in FIGURES:
        if (BUNDLE / name).read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError('invalid PNG signature')
    md = ['# 보고서 그림 모음', '', '같은 B1 초기장의 OLD/FIX를 비교합니다. 규준실험은 ORIGINAL이며, X는 B1 초기장·OLD, A는 현재 B1·FIX입니다. 새 후보 채택이나 성능 개선을 추가한 자료가 아닙니다.', '',
          '[학술 형식 보고서](../../CP02_PROTECTED_PROCESS_20261106.md) · [시간·임계값별 전체 점수](tables/FULL_SCORES.md) · [그림 묶음 ZIP](all_figures.zip)', '']
    body = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>OLD/FIX 과정 진단 그림</title>',
            '<style>body{font-family:sans-serif;max-width:1300px;margin:2rem auto;padding:0 1rem;line-height:1.6}img{display:block;width:100%;height:auto}figure{margin:2rem 0}figcaption{padding:.5rem 0}</style>',
            '<h1>동일 B1 초기장의 OLD/FIX 과정 진단</h1><p>그림은 파일에서 직접 표시됩니다. 시간·임계값의 점수를 평균하지 않습니다.</p>']
    for name, title, caption in FIGURES:
        md += [f'## {title}', '', f'![{title}]({name})', '', caption, '']
        body += [f'<figure><h2>{html.escape(title)}</h2><img src="{name}" alt="{html.escape(title)}"><figcaption>{html.escape(caption)}</figcaption></figure>']
    md += ['## 이전 보존 그림', '', '[PR151 그림 5장 모음](../cp02_failure_focus_20261105/figures/gallery.md)은 기존 경로에 그대로 보존했습니다.', '']
    body += ['<p>시간·임계값별 전체 수치는 <a href="tables/FULL_SCORES.md">부속 표</a>에 있습니다.</p></html>']
    targets[0].write_text('\n'.join(md), encoding='utf-8')
    targets[1].write_text('\n'.join(body) + '\n', encoding='utf-8')
    members = ['FIGURES.md', 'gallery.html', 'tables/FULL_SCORES.md', *(row[0] for row in FIGURES)]
    identities = {name: {'sha256': sha(BUNDLE / name), 'size_bytes': (BUNDLE / name).stat().st_size} for name in members}
    with zipfile.ZipFile(targets[2], 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in members:
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o644 << 16
            archive.writestr(item, (BUNDLE / name).read_bytes())
    with zipfile.ZipFile(targets[2]) as archive:
        if archive.testzip() is not None or archive.namelist() != members:
            raise ValueError('offline gallery ZIP inventory or CRC failed')
        for name in members:
            if hashlib.sha256(archive.read(name)).hexdigest() != identities[name]['sha256']:
                raise ValueError('gallery member differs')
    receipt = {'status': 'PASS_INLINE_AND_OFFLINE_GALLERY', 'members': identities,
               'archive': {'path': targets[2].name, 'sha256': sha(targets[2]), 'size_bytes': targets[2].stat().st_size},
               'images_edited': False, 'tool_sha256': sha(Path(__file__))}
    targets[3].write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': receipt['status'], 'png_count': len(FIGURES), 'zip_bytes': targets[2].stat().st_size}))


if __name__ == '__main__':
    main()
