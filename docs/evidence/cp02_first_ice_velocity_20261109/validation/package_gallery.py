#!/usr/bin/env python3
"""Build a receipt-checked, self-contained gallery without replacing outputs."""
import csv
import hashlib
import html
import json
import os
from pathlib import Path
import tempfile
import zipfile

BUNDLE = Path(__file__).resolve().parents[1]
THRESHOLDS = ('0.1', '0.5', '1', '2.5', '5', '10')
FIGURES = [(f'csi_{t}mm.png', f'{t} mm 이상 시간별 CSI') for t in THRESHOLDS]
FIGURES += [(f'rn1_hour_{h}_maps.png', f'+{h-12}시간: {h-1:02d}–{h:02d} UTC 한 시간 강수') for h in range(13, 19)]
TABLES = ('categorical_scores.csv', 'continuous_scores.csv', 'admission_constraints.csv', 'observation_transitions.csv')
OUTPUTS = ('FIGURES.md', 'gallery.html', 'all_figures.zip', 'gallery_receipt.json')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(path):
    return {'sha256': sha(path), 'size_bytes': path.stat().st_size}


def table(path):
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.reader(stream)
        rows = list(reader)
    if not rows or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError(f'invalid table: {path}')
    return rows


def markdown_table(rows):
    escape = lambda x: x.replace('|', r'\|').replace('\n', ' ')
    return ['| ' + ' | '.join(map(escape, rows[0])) + ' |',
            '| ' + ' | '.join(['---'] * len(rows[0])) + ' |'] + [
        '| ' + ' | '.join(map(escape, row)) + ' |' for row in rows[1:]]


def html_table(rows):
    cell = lambda tag, value: f'<{tag}>{html.escape(value)}</{tag}>'
    head = '<thead><tr>' + ''.join(cell('th', x) for x in rows[0]) + '</tr></thead>'
    body = '<tbody>' + ''.join('<tr>' + ''.join(cell('td', x) for x in row) + '</tr>' for row in rows[1:]) + '</tbody>'
    return '<table>' + head + body + '</table>'


def main():
    targets = [BUNDLE / name for name in OUTPUTS]
    if any(os.path.lexists(path) for path in targets):
        raise FileExistsError('preserve existing gallery outputs')
    results, figures = BUNDLE / 'evaluation/results', BUNDLE / 'figures'
    eval_path, plot_path = results / 'receipt.json', figures / 'maps_metadata.json'
    evaluation, plot = json.loads(eval_path.read_text()), json.loads(plot_path.read_text())
    if evaluation.get('status') != 'COMPLETE':
        raise ValueError('evaluation incomplete')
    if plot.get('points') != 3688 or len(FIGURES) != 12:
        raise ValueError('unexpected plot cohort or inventory')
    inputs = [eval_path, plot_path]
    for name in (*TABLES, 'FULL_SCORES.md', 'verdict.json', *(f'hour_{h}_arrays.npz' for h in range(13, 19))):
        path = results / name
        if sha(path) != evaluation['outputs'][name]:
            raise ValueError(f'evaluation receipt mismatch: {name}')
        inputs.append(path)
    plot_inputs = {Path(record['path']).name: record['sha256'] for record in plot['inputs']}
    for name in ('receipt.json', *(f'hour_{h}_arrays.npz' for h in range(13, 19))):
        if plot_inputs.get(name) != sha(results / name):
            raise ValueError(f'plot input mismatch: {name}')
    for name, _ in FIGURES:
        path = figures / name
        if path.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n' or sha(path) != plot['outputs'][name]:
            raise ValueError(f'plot receipt mismatch: {name}')
        inputs.append(path)
    hashes = {str(path.relative_to(BUNDLE)): identity(path) for path in inputs}
    verdict = json.loads((results / 'verdict.json').read_text())
    new = verdict['FIRST_ICE_VELOCITY']
    status = f"첫 빙정 단위 수정 후보 {new['passed_constraints']}/{new['required_constraints']} 조건 충족"
    if new['passed_constraints'] < new['required_constraints']:
        status += ", 미채택 · 현재 B1 유지"
    intro = ('초기시각 2026-08-16 12 UTC. 규준실험 ORIGINAL, 현재 B1, PR153 보존 침강 및 '
             '첫 빙정 단위 수정 후보를 비교합니다. RN1 공통 평가점 3,688개. 고정된 쌍선형 가중치로 WRF 네 모서리를 RN1 평가점에 대응하며, 그림에서 평가점 사이를 추가로 공간보간하지 않습니다. '
             'CSI 그림의 세로축 범위는 임계값마다 다릅니다. ' + status + '.')
    md = ['# 첫 빙정 단위 수정 후보: 전체 그림과 점수', '', intro, '', '[전체 점수표](evaluation/results/FULL_SCORES.md)', '']
    body = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>첫 빙정 단위 수정: 그림과 점수</title>',
            '<style>body{font-family:sans-serif;max-width:1400px;margin:2rem auto;padding:0 1rem;line-height:1.5}img{width:100%;height:auto}figure{margin:2rem 0}table{border-collapse:collapse;font-size:.85rem}td,th{border:1px solid #aaa;padding:.25rem} .table{overflow:auto}</style>',
            '<h1>첫 빙정 단위 수정: 그림과 점수</h1><p>' + html.escape(intro) + '</p><p><a href="evaluation/results/FULL_SCORES.md">전체 점수표</a></p>']
    for name, title in FIGURES:
        md += ['## ' + title, '', f'![{title}](figures/{name})', '']
        body += [f'<figure><h2>{html.escape(title)}</h2><img src="figures/{name}" alt="{html.escape(title)}"></figure>']
    for name in TABLES:
        rows = table(results / name)
        md += ['## ' + name, '', f'[CSV 다운로드](evaluation/results/{name})', ''] + markdown_table(rows) + ['']
        body += [f'<details><summary>{html.escape(name)} (전체 {len(rows)-1}행)</summary><p><a href="evaluation/results/{name}">CSV 다운로드</a></p><div class="table">{html_table(rows)}</div></details>']
    body += ['</html>']
    members = ['FIGURES.md', 'gallery.html', 'evaluation/results/FULL_SCORES.md'] + [f'evaluation/results/{name}' for name in TABLES] + [f'figures/{name}' for name, _ in FIGURES]
    published = []
    with tempfile.TemporaryDirectory(prefix='.gallery-stage-', dir=BUNDLE) as temp:
        stage = Path(temp)
        (stage / 'FIGURES.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
        (stage / 'gallery.html').write_text('\n'.join(body) + '\n', encoding='utf-8')
        def member_data(name):
            return (stage / name).read_bytes() if name in OUTPUTS else (BUNDLE / name).read_bytes()
        identities = {name: {'sha256': hashlib.sha256(member_data(name)).hexdigest(), 'size_bytes': len(member_data(name))} for name in members}
        with zipfile.ZipFile(stage / 'all_figures.zip', 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in members:
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o644 << 16
                archive.writestr(info, member_data(name))
        with zipfile.ZipFile(stage / 'all_figures.zip') as archive:
            if archive.testzip() is not None or archive.namelist() != members:
                raise ValueError('ZIP inventory or CRC mismatch')
            for name in members:
                if hashlib.sha256(archive.read(name)).hexdigest() != identities[name]['sha256']:
                    raise ValueError(f'ZIP member mismatch: {name}')
        if any(identity(BUNDLE / name) != record for name, record in hashes.items()):
            raise ValueError('gallery input changed during packaging')
        receipt = {'status': 'PASS', 'png_count': len(FIGURES), 'inputs': hashes, 'members': identities,
                   'archive': identity(stage / 'all_figures.zip'), 'tool': identity(Path(__file__))}
        (stage / 'gallery_receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n')
        try:
            for name in OUTPUTS:
                os.link(stage / name, BUNDLE / name)
                published.append(BUNDLE / name)
        except OSError:
            for path in published:
                path.unlink()
            raise
    print(json.dumps({'status': 'PASS', 'figures': len(FIGURES), 'archive_bytes': receipt['archive']['size_bytes']}))


if __name__ == '__main__':
    main()
