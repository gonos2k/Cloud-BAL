#!/usr/bin/env python3
"""Build the fine snow sensitivity report from sealed scoring outputs."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys
from build_full_score_tables import check_analysis as check_full_score_analysis

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ANALYSIS = HERE / 'analysis'
FIGURES = HERE / 'figures'
OUTPUT = ROOT / 'docs/SNOW_FINE_SENSITIVITY_20261030.md'
FIGURE_GALLERY = ROOT / 'docs/SNOW_FINE_FIGURES_20261030.md'
IMPROVED_GALLERY = ROOT / 'docs/SNOW_FINE_IMPROVED_FIGURES_20261030.md'
PLAN_SHA256 = '99d810d036d3bb6931065cc54117e90d85e2a76e388fbb12f5760729a2b703d3'
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
LEADS = tuple(range(1, 7))
FINE_CASES = tuple(f'{family}_SNOW_{factor}' for family in ('CONTROL', 'IMPROVED')
                   for factor in ('110', '120', '130', '140'))
sys.path.insert(0, str(ROOT / 'tools'))
try:
    import plot_snow_fine as plotter
finally:
    sys.path.remove(str(ROOT / 'tools'))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def label(case: str) -> str:
    labels = {'ORIGINAL': '규준 실험', 'CURRENT_HYDRO': '기존 HYDRO (참고)',
              'IMPROVED_BG_FIXED': '기존 개선안 B1'}
    if case in labels:
        return labels[case]
    family, _, suffix = case.split('_')
    return f"{'규준 계열' if family == 'CONTROL' else '개선 계열'} α={int(suffix) / 100:g}"


def validate() -> tuple[dict, list[dict], list[dict], list[dict], dict, list[str], dict]:
    if digest(HERE / 'selection_plan.json') != PLAN_SHA256:
        raise ValueError('frozen fine-sensitivity selection plan hash mismatch')
    receipt, categorical, continuous, _, _ = check_full_score_analysis()
    prior_analysis_dir = ROOT / 'docs/evidence/snow_extension_20261030/analysis'
    prior_receipt = json.loads((prior_analysis_dir / 'receipt.json').read_text(encoding='utf-8'))
    prior_selection_path = prior_analysis_dir / 'selection.json'
    prior_selection_record = prior_receipt.get('analysis_outputs', {}).get('selection.json', {})
    if (prior_selection_path.is_symlink() or not prior_selection_path.is_file()
            or prior_selection_path.stat().st_size != prior_selection_record.get('size_bytes')
            or digest(prior_selection_path) != prior_selection_record.get('sha256')):
        raise ValueError('pinned previous selection output changed')
    choices = read_csv(ANALYSIS / 'selection_scores.csv')
    selection = json.loads((ANALYSIS / 'selection.json').read_text(encoding='utf-8'))
    cases = receipt.get('cases', [])
    eligible = receipt.get('eligible_cases', [])
    if (len(cases) != 31 or len(set(cases)) != 31 or len(eligible) != 30
            or set(eligible) != set(cases) - {'CURRENT_HYDRO'}
            or receipt.get('context_only_cases') != ['CURRENT_HYDRO']
            or len(categorical) != 1116 or len(continuous) != 186
            or {row['case'] for row in categorical} != set(cases)
            or {row['case'] for row in continuous} != set(cases)):
        raise ValueError('analysis outputs do not match the complete 31-case score grid')
    if {row['case'] for row in choices} != set(eligible):
        raise ValueError('selection table does not contain all 30 eligible cases')
    cat_keys = {(int(row['lead_hour']), row['case'], float(row['threshold_mm'])) for row in categorical}
    cont_keys = {(int(row['lead_hour']), row['case']) for row in continuous}
    if (len(cat_keys) != 1116 or cat_keys != {
            (lead, case, threshold) for lead in LEADS for case in cases for threshold in THRESHOLDS}
            or len(cont_keys) != 186 or cont_keys != {
                (lead, case) for lead in LEADS for case in cases}):
        raise ValueError('score table keys do not match the full lead × case × threshold grid')
    order = selection.get('selection_order')
    if (not isinstance(order, list) or set(order) != set(eligible)
            or selection.get('selected_case') != order[0]
            or selection.get('selected_case') not in eligible):
        raise ValueError('selection does not identify exactly one eligible winner')
    ranked = sorted((row for row in choices if row.get('rank') not in ('', None)),
                    key=lambda row: int(row['rank']))
    if [row['case'] for row in ranked] != order:
        raise ValueError('selection order differs from ranked score rows')
    figures_path = FIGURES / 'figure_manifest.json'
    if figures_path.is_symlink() or not figures_path.is_file():
        raise ValueError('figure manifest is missing or not a regular file')
    figures = json.loads(figures_path.read_text(encoding='utf-8'))
    if (figures.get('status') != 'COMPLETE'
            or figures.get('receipt_sha256') != digest(ANALYSIS / 'receipt.json')
            or figures.get('selection_plan_sha256') != PLAN_SHA256
            or figures.get('renderer_sha256') != digest(ROOT / 'tools/plot_snow_fine.py')):
        raise ValueError('figure manifest is not bound to current scores, plan, and renderer')
    plotter.validate_figure_coverage(figures, tuple(cases), selection['selected_case'])
    for name, expected_hash in figures.get('figure_sha256', {}).items():
        path = FIGURES / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected_hash:
            raise ValueError(f'figure asset hash mismatch: {name}')
    return receipt, categorical, continuous, choices, selection, order, figures


def cell(row: dict, key: str, places: int = 4) -> str:
    value = row.get(key)
    if value in ('', None, 'None'):
        return '—'
    return f'{float(value):.{places}f}'


def table(headers: list[str], rows: list[list[str]]) -> str:
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |',
                      *('| ' + ' | '.join(row) + ' |' for row in rows)])


def link(path: str, label_text: str = 'PNG') -> str:
    return f'[{label_text}](evidence/snow_fine_20261030/figures/{path})'


def build_galleries(figures: dict, cases: list[str]) -> tuple[str, str]:
    groups = plotter.case_groups(tuple(cases))
    heatmaps = figures['delta_csi_heatmaps']
    maps = figures['hourly_precipitation_maps']
    limits = figures['heatmap_coverage']['shared_color_limits']
    all_gallery = [
        '# 미세배율 실험 그림 모음', '',
        'CSI 차이는 각 실험에서 규준 실험 CSI를 뺀 값이다. 모든 heatmap의 공통 색 범위는 '
        f'[{limits[0]:.3f}, {limits[1]:.3f}]이며 가운데 0은 규준 실험과 같은 점수다. '
        '행은 +1–+6시간, 각 칸은 개별 lead·임계값 점수다.',
        '', '## 임계값별 ΔCSI heatmap', '',
    ]
    for group_name, group_cases in groups:
        title = {'control': '규준 계열 (규준 실험 + 14개 CONTROL)',
                 'improved': '개선 계열 (B1 + 14개 IMPROVED)',
                 'context': '참고 실험'}[group_name]
        all_gallery.extend([f'### {title}', '',
                            '| 임계값 | 그림 |', '| --- | --- |'])
        for threshold in THRESHOLDS:
            path = f'delta_csi/{group_name}/delta_csi_t{plotter.threshold_slug(threshold)}.png'
            pdf = path[:-4] + '.pdf'
            if path not in heatmaps:
                raise ValueError(f'missing heatmap link target: {path}')
            all_gallery.append(f'| ≥{threshold:g} mm | {link(path)} · {link(pdf, "PDF")} |')
        all_gallery.extend(['', f'Columns: {len(group_cases)} experiments. Every row is a separate lead.', ''])
    all_gallery.extend(['## 시간별 총강수 지도', '',
                        '각 PNG는 RN1 분석과 한 실험의 6개 시간별 총강수를 나란히 보인다. '
                        '모든 지도는 같은 색 구간과 공통 RN1 평가점을 사용한다.', ''])
    for group_name, group_cases in groups:
        title = {'control': '규준 계열', 'improved': '개선 계열', 'context': '참고 실험'}[group_name]
        all_gallery.extend([f'### {title}', '', '| 실험 ID | 실험 표기 | 지도 |', '| --- | --- | --- |'])
        for case in group_cases:
            item = maps[case]
            all_gallery.append(f'| `{case}` | {label(case)} | {link(item["figure"])} · {link(item["figure"][:-4] + ".pdf", "PDF")} |')
        all_gallery.append('')

    improved_cases = next(group for name, group in groups if name == 'improved')
    improved_gallery = [
        '# 개선 계열 그림 모음', '',
        '개선 계열은 기존 개선안 B1(α=1)과 IMPROVED_SNOW 실험 14개를 한 그림 형식으로 정리했다. '
        '모든 ΔCSI는 규준 실험 ORIGINAL을 기준으로 하며 heatmap 색 범위는 전체 실험에 공통이다.', '',
        '## 임계값별 ΔCSI heatmap', '', '| 임계값 | 그림 |', '| --- | --- |',
    ]
    for threshold in THRESHOLDS:
        path = f'delta_csi/improved/delta_csi_t{plotter.threshold_slug(threshold)}.png'
        improved_gallery.append(f'| ≥{threshold:g} mm | {link(path)} · {link(path[:-4] + ".pdf", "PDF")} |')
    improved_gallery.extend(['', '## 시간별 총강수 지도', '',
                             '각 지도는 RN1 분석과 해당 개선 실험의 +1–+6시간을 같은 색 구간으로 비교한다.', '',
                             '| 실험 ID | 실험 표기 | 지도 |', '| --- | --- | --- |'])
    for case in improved_cases:
        item = maps[case]
        improved_gallery.append(f'| `{case}` | {label(case)} | {link(item["figure"])} · {link(item["figure"][:-4] + ".pdf", "PDF")} |')
    return '\n'.join(all_gallery) + '\n', '\n'.join(improved_gallery) + '\n'


def build() -> tuple[str, str, str]:
    receipt, categorical, continuous, _, selection, order, figures = validate()
    cat = {(int(row['lead_hour']), row['case'], float(row['threshold_mm'])): row
           for row in categorical}
    cont = {(int(row['lead_hour']), row['case']): row for row in continuous}
    best = selection['selected_case']
    previous_selection_path = ROOT / 'docs/evidence/snow_extension_20261030/analysis/selection.json'
    previous_selection = json.loads(previous_selection_path.read_text(encoding='utf-8'))['selected_case']
    winner_change = '유지됨' if best == previous_selection else '변경됨'
    comparison_cases = ('ORIGINAL', 'IMPROVED_BG_FIXED', *FINE_CASES)
    comparison_rows = [[label(case), *[cell(cat[(lead, case, 10.0)], 'CSI') for lead in LEADS]]
                       for case in comparison_cases]
    comparison_table = table(['실험', *[f'+{lead} h CSI@10' for lead in LEADS]], comparison_rows)
    primary_rows = []
    for position, case in enumerate(order, 1):
        row = cat[(1, case, 10.0)]
        primary_rows.append([str(position), label(case), cell(row, 'CSI'),
                             cell(cat[(1, case, 5.0)], 'CSI'), cell(row, 'FAR'),
                             cell(cont[(1, case)], 'RMSE_mm')])
    score_receipt = digest(ANALYSIS / 'receipt.json')
    all_gallery, improved_gallery = build_galleries(figures, receipt['cases'])
    prior_receipt = receipt.get('prior_analysis_receipt', {})
    prior_line = ''
    if isinstance(prior_receipt, dict) and prior_receipt.get('path'):
        prior_line = f"- 이전 전체 점수 분석 영수증 SHA-256: `{prior_receipt.get('sha256', '미기록')}`.\n"
    main_report = rf'''# 초기 QSNOW 미세배율 민감도: 1.1–1.4

## 핵심 결과

2026년 8월 16일 12 UTC 기상사례에서 규준 계열과 개선 계열 각각의 초기 QSNOW 배율 1.1, 1.2, 1.3, 1.4 실험을 기존 배율 실험에 추가했다. 31개 실험의 공통 RN1 분석점 3,688개에서 매 lead의 직전 1시간 지상 총강수를 평가했다. 사전 지정 순위의 1순위는 **{label(best)}**이며, +1시간 CSI@10 mm는 {cell(cat[(1, best, 10.0)], 'CSI')}이다. 이 선택은 기존 22개 후보의 결과를 알고 있는 같은 기상사례의 진단적 재선정이며 독립 검증 성능은 아니다.

기존 선정 실험({label(previous_selection)})은 이번 순위에서 **{winner_change}**. 개선 계열 α=1.0 기준은 기존 개선안 B1이다. CONTROL과 IMPROVED 계열 사이에는 초기장 및 실행파일 차이가 함께 있으므로, 계열 간 차이를 α 효과만으로 해석하지 않는다.

## 규준·B1 및 추가 8개 실험: +1–+6시간 CSI@10

10 mm h⁻¹ 임계값의 각 lead 점수를 개별적으로 보인다. 시간·실험 간 평균을 계산하지 않는다.

{comparison_table}

## 실험과 물리량

각 계열 안에서 초기 native QSNOW만 다음과 같이 바꿨다.

$$q_s^{{(\alpha)}}=\operatorname{{REAL32}}\left[\alpha\,\operatorname{{REAL64}}(q_s^{{(1)}})\right].$$

다른 수종, 열역학 변수와 메타데이터는 그대로 둔다. 따라서 이 조작은 초기 눈 혼합비에 대한 민감도 진단이다. 다른 물상이나 에너지를 보상하지 않으므로 보존적 초기화라고 해석하지 않는다.

검증량은 눈 강설량만이 아니라 지상 누적 총강수 $C=RAINC+RAINNC$의 시간 차 $P_h=C(t_0+h)-C(t_0+h-1)$다. 각 lead는 해당 한 시간 강수량(mm)이며 0–h 누적량이 아니다. CSI는 $H/(H+M+FA)$, FAR는 $FA/(H+FA)$이며 H/M/FA는 적중·누락·오경보다. 10 mm h⁻¹는 분석 임계값이지 공식 특보 기준이 아니다.

## 사전 지정 단일 실험 선정

30개 완료 후보를 +1시간 CSI@10 mm 내림차순, CSI@5 mm 내림차순, FAR@10 mm 오름차순, RMSE 오름차순, $|\alpha-1|$ 오름차순, 실험 ID 오름차순으로 정렬했다. undefined CSI는 정의된 점수 아래, undefined FAR는 정의된 FAR 뒤에 둔다. 시간이나 임계값을 합친 평균 점수는 선정에 사용하지 않았다. CURRENT_HYDRO는 참고 실험이며 후보에서 제외했다.

{table(['순위', '실험', '+1 h CSI@10', '+1 h CSI@5', '+1 h FAR@10', '+1 h RMSE (mm)'], primary_rows)}

선정된 실험의 +1시간 CSI@10은 {cell(cat[(1, best, 10.0)], 'CSI')}, CSI@5는 {cell(cat[(1, best, 5.0)], 'CSI')}, FAR@10은 {cell(cat[(1, best, 10.0)], 'FAR')}, RMSE는 {cell(cont[(1, best)], 'RMSE_mm')} mm다. {label(best)}의 H/M/FA는 {cat[(1, best, 10.0)]['hit']}/{cat[(1, best, 10.0)]['miss']}/{cat[(1, best, 10.0)]['false_alarm']}이며 규준 실험은 {cat[(1, 'ORIGINAL', 10.0)]['hit']}/{cat[(1, 'ORIGINAL', 10.0)]['miss']}/{cat[(1, 'ORIGINAL', 10.0)]['false_alarm']}다. 이는 점수 요약이며 개별 격자 전이나 미세물리 인과를 뜻하지 않는다.

## 그림과 전체 점수

- [전체 CSI heatmap 및 시간별 강수 지도 모음](SNOW_FINE_FIGURES_20261030.md)
- [개선 계열 전용 그림 모음](SNOW_FINE_IMPROVED_FIGURES_20261030.md)
- [전체 점수표](SNOW_FINE_FULL_SCORES_20261030.md): 42개 표, 총 {len(categorical) + len(continuous):,}개 score row (categorical {len(categorical)}행, continuous {len(continuous)}행).
- 세밀 배율 반응: [lead·임계값별 CSI](evidence/snow_fine_20261030/figures/refined_dose_response_csi.png).

시간·임계값·실험에 걸친 평균은 점수로 보고하거나 선정에 사용하지 않았다. 평가는 2026-08-16 12 UTC 기상사례의 공통 RN1 paired point {receipt.get('points_per_hour', 3688):,}개에서 수행했으며, WRF 지상 총강수의 시간별 차(mm h⁻¹)를 사용했다.

{prior_line}- 기존 결과 및 선택 맥락: [고강수 임계값 확장 보고서](SNOW_HEAVY_EXTENSION_20261030.md).
- 분석 영수증: [receipt.json](evidence/snow_fine_20261030/analysis/receipt.json); figure coverage and asset hashes: [figure_manifest.json](evidence/snow_fine_20261030/figures/figure_manifest.json).
- 재현: `python tools/plot_snow_fine.py --analysis-dir docs/evidence/snow_fine_20261030/analysis` and `python docs/evidence/snow_fine_20261030/build_report.py`.
- Score analysis receipt SHA-256: `{score_receipt}`.
'''
    return main_report, all_gallery, improved_gallery


def main() -> None:
    main_report, all_gallery, improved_gallery = build()
    reports = ((OUTPUT, main_report.encode('utf-8')),
               (FIGURE_GALLERY, all_gallery.encode('utf-8')),
               (IMPROVED_GALLERY, improved_gallery.encode('utf-8')))
    for path, content in reports:
        if path.is_symlink() or (path.exists() and path.read_bytes() != content):
            raise ValueError(f'refusing to replace non-identical generated output: {path}')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for path, content in reports:
        if not path.exists():
            path.write_bytes(content)
    print(json.dumps({'status': 'COMPLETE', 'reports': [
        {'path': path.relative_to(ROOT).as_posix(),
         'sha256': hashlib.sha256(content).hexdigest(), 'size_bytes': len(content)}
        for path, content in reports]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
