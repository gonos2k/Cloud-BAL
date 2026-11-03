#!/usr/bin/env python3
"""Build the lower-factor report and image galleries from scored outputs."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ANALYSIS = HERE / 'analysis'
FIGURES = HERE / 'figures'
PLAN_SHA256 = '8d30f3f7a3d82a34332013334d5f0d6c66f1a1576198db228b98b1a89c950cf2'
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
LEADS = tuple(range(1, 7))
FOCUSED_CASES = ('CONTROL_SNOW_050', 'CONTROL_SNOW_060', 'CONTROL_SNOW_070',
                 'CONTROL_SNOW_080', 'CONTROL_SNOW_090',
                 'IMPROVED_SNOW_050', 'IMPROVED_SNOW_060', 'IMPROVED_SNOW_070',
                 'IMPROVED_SNOW_080', 'IMPROVED_SNOW_090')
OUTPUT = ROOT / 'docs/SNOW_LOWER_SENSITIVITY_20261030.md'
FIGURE_GALLERY = ROOT / 'docs/SNOW_LOWER_FIGURES_20261030.md'
IMPROVED_GALLERY = ROOT / 'docs/SNOW_LOWER_IMPROVED_FIGURES_20261030.md'
sys.path.insert(0, str(ROOT / 'tools'))
try:
    import plot_snow_lower as plotter
finally:
    sys.path.remove(str(ROOT / 'tools'))
sys.path.insert(0, str(HERE))
try:
    from build_full_score_tables import check_analysis
finally:
    sys.path.remove(str(HERE))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def optional_float(value: str | None) -> float | None:
    return None if value in (None, '', 'None') else float(value)


def check_comparison(categorical: list[dict], cases: list[str]) -> None:
    rows = read_csv(ANALYSIS / 'comparison_vs_original.csv')
    expected = {(case, lead, threshold) for case in cases if case != 'CURRENT_HYDRO'
                for lead in LEADS for threshold in THRESHOLDS}
    actual = set()
    cat = {(int(row['lead_hour']), row['case'], float(row['threshold_mm'])): row
           for row in categorical}
    for row in rows:
        case, lead, threshold = row['case'], int(row['lead_hour']), float(row['threshold_mm'])
        key = case, lead, threshold
        if key in actual or row.get('baseline_case') != 'ORIGINAL':
            raise ValueError(f'invalid or duplicate ORIGINAL comparison row: {key}')
        actual.add(key)
        source, baseline = cat[(lead, case, threshold)], cat[(lead, 'ORIGINAL', threshold)]
        for field, output in (('CSI', 'CSI'), ('FAR', 'FAR')):
            if optional_float(row[output]) != optional_float(source[field]):
                raise ValueError(f'{key}: comparison {field} differs from categorical score')
            baseline_value = optional_float(baseline[field])
            if optional_float(row[f'baseline_{field}']) != baseline_value:
                raise ValueError(f'{key}: comparison baseline {field} differs from ORIGINAL')
            delta_field = 'delta_CSI_vs_ORIGINAL' if field == 'CSI' else 'delta_FAR_vs_ORIGINAL'
            value = optional_float(source[field])
            expected_delta = value - baseline_value if value is not None and baseline_value is not None else None
            if optional_float(row[delta_field]) != expected_delta:
                raise ValueError(f'{key}: comparison delta {field} is inconsistent')
    if actual != expected or len(rows) != len(expected):
        raise ValueError('comparison_vs_original.csv does not cover all eligible case×lead×threshold keys')


def label(case: str) -> str:
    if case == 'ORIGINAL':
        return '규준 실험 α=1.0'
    if case == 'CURRENT_HYDRO':
        return '기존 HYDRO (참고)'
    if case == 'IMPROVED_BG_FIXED':
        return '기존 개선안 B1 (개선 계열 α=1.0)'
    family, _, suffix = case.split('_')
    return f"{'규준 계열' if family == 'CONTROL' else '개선 계열'} α={int(suffix) / 100:g}"


def validate() -> tuple[dict, list[dict], list[dict], dict, list[str]]:
    if digest(HERE / 'selection_plan.json') != PLAN_SHA256:
        raise ValueError('frozen lower-sensitivity plan hash mismatch')
    receipt, categorical, continuous, _, _ = check_analysis()
    prior_analysis = ROOT / 'docs/evidence/snow_fine_20261030/analysis'
    prior_receipt = json.loads((prior_analysis / 'receipt.json').read_text(encoding='utf-8'))
    prior_selection_path = prior_analysis / 'selection.json'
    prior_selection_record = prior_receipt.get('analysis_outputs', {}).get('selection.json', {})
    if (prior_selection_path.is_symlink() or not prior_selection_path.is_file()
            or prior_selection_path.stat().st_size != prior_selection_record.get('size_bytes')
            or digest(prior_selection_path) != prior_selection_record.get('sha256')):
        raise ValueError('prior fine-factor selection output is not bound to its score receipt')
    cases = receipt.get('cases', [])
    eligible = receipt.get('eligible_cases', [])
    if (len(cases) != 39 or len(set(cases)) != 39 or len(eligible) != 38
            or set(eligible) != set(cases) - {'CURRENT_HYDRO'}
            or receipt.get('context_only_cases') != ['CURRENT_HYDRO']
            or len(categorical) != 1404 or len(continuous) != 234):
        raise ValueError('analysis outputs do not cover all 39 contexts and 38 candidates')
    check_comparison(categorical, cases)
    selection = json.loads((ANALYSIS / 'selection.json').read_text(encoding='utf-8'))
    if (selection.get('selected_case') not in eligible
            or set(selection.get('selection_order', ())) != set(eligible)):
        raise ValueError('selection output does not rank all eligible cases')
    manifest_path = FIGURES / 'figure_manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError('figure manifest is missing or not a regular file')
    figures = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (figures.get('status') != 'COMPLETE'
            or figures.get('receipt_sha256') != digest(ANALYSIS / 'receipt.json')
            or figures.get('selection_plan_sha256') != PLAN_SHA256
            or figures.get('renderer_sha256') != digest(ROOT / 'tools/plot_snow_lower.py')):
        raise ValueError('figure manifest is not bound to current score inputs and renderer')
    analysis_outputs = receipt.get('analysis_outputs', {})
    difference_record = figures.get('pointwise_precipitation_difference', {})
    difference_sources = difference_record.get('source_sha256', {})
    difference_sizes = difference_record.get('source_size_bytes', {})
    expected_difference_sources = {
        name: analysis_outputs.get(name, {}).get('sha256')
        for name in difference_sources
    }
    expected_difference_sizes = {
        name: analysis_outputs.get(name, {}).get('size_bytes')
        for name in difference_sizes
    }
    if (len(difference_sources) != 6 or difference_sources != expected_difference_sources
            or len(difference_sizes) != 6 or difference_sizes != expected_difference_sizes
            or any(not value for value in expected_difference_sources.values())):
        raise ValueError('pointwise difference NPZ hashes differ from the sealed analysis receipt')
    plotter.validate_figure_coverage(figures, tuple(cases), selection['selected_case'])
    for name, expected_hash in figures.get('figure_sha256', {}).items():
        path = FIGURES / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected_hash:
            raise ValueError(f'figure asset hash mismatch: {name}')
    return receipt, categorical, continuous, figures, selection['selection_order']


def cell(row: dict, key: str, places: int = 4) -> str:
    value = row.get(key)
    if value in ('', None, 'None'):
        return '—'
    return f'{float(value):.{places}f}'


def delta_cell(row: dict, baseline: dict, key: str = 'CSI') -> str:
    if row.get(key) in ('', None, 'None') or baseline.get(key) in ('', None, 'None'):
        return '—'
    return f'{float(row[key]) - float(baseline[key]):+.4f}'


def table(headers: list[str], rows: list[list[str]]) -> str:
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |',
                      *('| ' + ' | '.join(row) + ' |' for row in rows)])


def image(path: str, alt: str, figure_ref: str) -> str:
    raw = ('https://raw.githubusercontent.com/gonos2k/Cloud-BAL/'
           f'{figure_ref}/docs/evidence/snow_lower_20261030/figures/{path}')
    return f'![{alt}](https://images.weserv.nl/?url={quote(raw, safe="")}&output=png)'


def build_galleries(figures: dict, cases: list[str], figure_ref: str) -> tuple[str, str]:
    groups = plotter.case_groups(tuple(cases))
    all_lines = [
        '# 하위 배율 실험 그림 모음', '',
        '각 임계값 그림은 개별 CSI 또는 규준 실험 α=1.0 대비 ΔCSI를 lead별로 표시한다. '
        'ΔCSI heatmap은 전체 그림에서 공통인 대칭 색 범위를 사용한다. 점수는 lead나 임계값을 평균하지 않는다.',
        '', '## 요청한 α=0.5, 0.6, 0.7, 0.8, 0.9와 규준 실험 α=1.0 비교', '',
        '각 임계값마다 절대 CSI와 규준 실험 α=1.0 대비 ΔCSI를 별도 그림으로 제공한다. '
        '집중 그림의 가로축 표기는 C=CONTROL, I=IMPROVED다. 전체 gallery의 가족별 그림은 제목으로 계열을 구분한다.', '',
    ]
    for threshold in THRESHOLDS:
        csi_path = f'focused/low_factor_csi_t{plotter.threshold_slug(threshold)}.png'
        delta_path = f'focused/low_factor_delta_csi_t{plotter.threshold_slug(threshold)}.png'
        if (csi_path not in figures['focused_csi_heatmaps']
                or delta_path not in figures['focused_delta_csi_heatmaps']):
            raise ValueError(f'missing focused comparison at threshold {threshold:g} mm')
        all_lines.extend([f'### 임계값 ≥{threshold:g} mm', '',
                          image(csi_path, f'α=0.5, 0.6, 0.7, 0.8, 0.9와 규준 실험 α=1.0 · ≥{threshold:g} mm 절대 CSI', figure_ref), '',
                          image(delta_path, f'α=0.5, 0.6, 0.7, 0.8, 0.9와 규준 실험 α=1.0 · ≥{threshold:g} mm ΔCSI', figure_ref), ''])
    all_lines.extend([
        '', '## 임계값별 절대 CSI', '',
    ])
    group_title = {'control': '규준 계열 (규준 실험 α=1.0 포함)',
                   'improved': '개선 계열 (B1 포함)', 'context': '참고 실험'}
    for group_name, group_cases in groups:
        all_lines.extend([f'### {group_title[group_name]}', ''])
        for threshold in THRESHOLDS:
            path = f'csi/{group_name}/csi_t{plotter.threshold_slug(threshold)}.png'
            if path not in figures['csi_heatmaps']:
                raise ValueError(f'missing CSI heatmap: {path}')
            all_lines.extend([f'#### 임계값 ≥{threshold:g} mm', '',
                              image(path, f'{group_title[group_name]} · ≥{threshold:g} mm 절대 CSI', figure_ref), ''])
    all_lines.extend(['## 임계값별 규준 실험 α=1.0 대비 ΔCSI', ''])
    for group_name, group_cases in groups:
        all_lines.extend([f'### {group_title[group_name]}', ''])
        for threshold in THRESHOLDS:
            path = f'delta_csi/{group_name}/delta_csi_t{plotter.threshold_slug(threshold)}.png'
            if path not in figures['delta_csi_heatmaps']:
                raise ValueError(f'missing ΔCSI heatmap: {path}')
            all_lines.extend([f'#### 임계값 ≥{threshold:g} mm', '',
                              image(path, f'{group_title[group_name]} · ≥{threshold:g} mm · 규준 실험 α=1.0 대비 ΔCSI', figure_ref), ''])
    all_lines.extend(['## 시간별 총강수 지도', '',
                      '각 그림은 RN1 분석, 해당 실험 강수, 같은 시간·같은 paired point의 ΔP를 세 열에 보인다. '
                      'ΔP=P실험−P규준 실험 α=1.0이며 mm 단위다. 붉은색은 규준 실험보다 많은 강수, 파란색은 적은 강수이며 성능 향상을 뜻하지 않는다. '
                      '모든 39개 분석 맥락에 동일한 0 중심 대칭 색 범위를 쓴다.', ''])
    maps = figures['hourly_precipitation_maps']
    for group_name, group_cases in groups:
        all_lines.extend([f'### {group_title[group_name]}', ''])
        for case in group_cases:
            item = maps[case]
            all_lines.extend([f'#### {label(case)}', '', f'실험 ID: `{case}`', '',
                              image(item['figure'], f'{label(case)} · RN1, +1–+6시간 강수 및 규준 실험 대비 지점 ΔP', figure_ref), ''])

    improved_cases = next(group for name, group in groups if name == 'improved')
    improved = ['# 개선 계열 그림 모음', '',
                '모든 ΔCSI는 규준 실험 α=1.0(ORIGINAL)을 공통 기준으로 계산했다. '
                '각 임계값을 별도 그림으로 제시하며 시간·임계값 평균은 없다.', '',
                '## 임계값별 절대 CSI', '']
    for threshold in THRESHOLDS:
        path = f'csi/improved/csi_t{plotter.threshold_slug(threshold)}.png'
        improved.extend([f'### 임계값 ≥{threshold:g} mm', '',
                         image(path, f'개선 계열 · ≥{threshold:g} mm 절대 CSI', figure_ref), ''])
    improved.extend(['## 임계값별 규준 실험 α=1.0 대비 ΔCSI', ''])
    for threshold in THRESHOLDS:
        path = f'delta_csi/improved/delta_csi_t{plotter.threshold_slug(threshold)}.png'
        improved.extend([f'### 임계값 ≥{threshold:g} mm', '',
                         image(path, f'개선 계열 · ≥{threshold:g} mm · 규준 실험 α=1.0 대비 ΔCSI', figure_ref), ''])
    improved.extend(['## 시간별 총강수 지도', '',
                     'B1과 개선 계열 18개 실험을 RN1 분석·실험 강수·규준 실험 α=1.0 대비 같은 점의 ΔP로 비교한다. '
                     '붉은색은 기준보다 많은 강수이며 성능 향상을 뜻하지 않는다.', ''])
    for case in improved_cases:
        item = maps[case]
        improved.extend([f'### {label(case)}', '', f'실험 ID: `{case}`', '',
                         image(item['figure'], f'{label(case)} · RN1, +1–+6시간 강수 및 규준 실험 대비 지점 ΔP', figure_ref), ''])
    return '\n'.join(all_lines).rstrip() + '\n', '\n'.join(improved).rstrip() + '\n'


def build(figure_ref: str) -> tuple[str, str, str]:
    receipt, categorical, continuous, figures, order = validate()
    cat = {(int(row['lead_hour']), row['case'], float(row['threshold_mm'])): row
           for row in categorical}
    focused_tables = []
    for lead in LEADS:
        rows = []
        baselines = {threshold: cat[(lead, 'ORIGINAL', threshold)] for threshold in (5.0, 10.0)}
        for case in FOCUSED_CASES:
            metrics = []
            for threshold in (5.0, 10.0):
                row, baseline = cat[(lead, case, threshold)], baselines[threshold]
                delta = delta_cell(row, baseline)
                metrics.extend([cell(row, 'CSI'), delta])
            rows.append([label(case), *metrics])
        base_metrics = []
        for threshold in (5.0, 10.0):
            baseline = baselines[threshold]
            base_metrics.extend([cell(baseline, 'CSI'),
                                 '+0.0000' if baseline['CSI'] not in ('', 'None') else '—'])
        rows.insert(0, [label('ORIGINAL'), *base_metrics])
        focused_tables.extend([f'### +{lead}시간 · CSI@5 및 CSI@10 mm · {lead + 12 - 1:02d}:00–{lead + 12:02d} UTC', '',
                               table(['실험', 'CSI@5', 'ΔCSI@5', 'CSI@10', 'ΔCSI@10'], rows), ''])

    all_gallery, improved_gallery = build_galleries(figures, receipt['cases'], figure_ref)
    best = order[0]
    prior_selection = json.loads((ROOT / 'docs/evidence/snow_fine_20261030/analysis/selection.json')
                                 .read_text(encoding='utf-8'))['selected_case']
    global_winner_status = '유지됐다' if best == prior_selection else '변경됐다'
    low_factor_winner = plotter.rank_cases(categorical, continuous, FOCUSED_CASES)[0]
    low_csi5 = cat[(1, low_factor_winner, 5.0)]
    low_csi10 = cat[(1, low_factor_winner, 10.0)]
    baseline_csi5 = cat[(1, 'ORIGINAL', 5.0)]
    baseline_csi10 = cat[(1, 'ORIGINAL', 10.0)]
    report = f'''# 초기 QSNOW 하위 배율 민감도: 0.5–0.9

## 핵심 결과

2026년 8월 16일 12 UTC 기상사례에서 규준 계열과 개선 계열의 초기 QSNOW 배율 0.6, 0.7, 0.8, 0.9 실험을 추가했다. 이미 검증된 각 계열 α=0.5 결과도 같은 비교에 포함하고, 규준 실험 α=1.0(ORIGINAL)을 공통 기준으로 삼았다. 총 {len(receipt['cases'])}개 분석 맥락({len(receipt['eligible_cases'])}개 후보와 참고 실험 1개)의 모든 시간·임계값 점수를 같은 3,688개 RN1 paired point에서 계산했다.

아래 표는 요청된 α=0.5, 0.6, 0.7, 0.8, 0.9와 규준 실험 α=1.0의 +1–+6시간 CSI@5 및 CSI@10을 lead별로 보인다. ΔCSI는 같은 lead·임계값의 규준 실험 α=1.0 CSI를 뺀 값이다. 다른 네 임계값의 절대 CSI 및 ΔCSI는 각각 별도 그림에 수록했다. 점수들을 시간이나 임계값에 걸쳐 평균하지 않았다.

{chr(10).join(focused_tables)}

## 설계와 해석 범위

계열별 초기 native QSNOW를 $q_s^{{(\\alpha)}}=\\operatorname{{REAL32}}[\\alpha\\,\\operatorname{{REAL64}}(q_s^{{(1)}})]$로 바꿨다. 다른 상태변수와 메타데이터는 유지했다. 따라서 이는 같은 기상사례 안에서 초기 눈 혼합비 배율의 민감도를 보는 진단이며, 다른 물상·에너지 보상 없이 수행했으므로 보존적 초기화로 해석하지 않는다.

계열 간에는 초기장과 실행파일 차이도 있으므로 CONTROL과 IMPROVED의 차이를 QSNOW 배율만의 효과로 해석하지 않는다. IMPROVED 계열의 B1(α=1.0)은 ORIGINAL과 다른 개선 입력·실행파일 조합이다. 모든 ΔCSI 그림과 표는 요청대로 규준 실험 α=1.0을 공통 기준으로 쓰며, B1을 해당 계열의 비교 기준으로 바꾸지 않는다.

검증량은 지상 누적 총강수 $C=RAINC+RAINNC$의 직전 1시간 차 $P_h=C(t_0+h)-C(t_0+h-1)$다. CSI는 $H/(H+M+FA)$, FAR는 $FA/(H+FA)$다. 10 mm h⁻¹는 분석 임계값이지 공식 특보 기준이 아니다. 한 사건·한 초기시각의 결과이며 독립 사례 검증이나 미세물리 과정의 인과 증거가 아니다.

## 그림과 전체 점수

- [모든 계열의 임계값별 CSI·ΔCSI 및 39개 시간별 강수 지도](SNOW_LOWER_FIGURES_20261030.md)
- [개선 계열 전용 그림 모음](SNOW_LOWER_IMPROVED_FIGURES_20261030.md): B1과 개선 계열 18개 배율 실험.
- [전체 점수표](SNOW_LOWER_FULL_SCORES_20261030.md): 42개 표, 범주형 {len(categorical)}행과 연속형 {len(continuous)}행.
- 요청 범위의 10개 하위 배율 후보 중 사전 지정 점수순 1위는 {label(low_factor_winner)}다. 규준 실험 α=1.0 대비 +1시간 CSI@5는 {cell(low_csi5, 'CSI')} vs {cell(baseline_csi5, 'CSI')} (Δ{delta_cell(low_csi5, baseline_csi5)}), CSI@10은 {cell(low_csi10, 'CSI')} vs {cell(baseline_csi10, 'CSI')} (Δ{delta_cell(low_csi10, baseline_csi10)})다. 이는 하위 배율 부분집합 요약이다. 38개 후보 전체의 단일 순위 1위는 **{label(best)}**이며 +1시간 CSI@10은 {cell(cat[(1, best, 10.0)], 'CSI')}다. 기존 30개 후보의 1위 {label(prior_selection)}은 이번 확장 후 {global_winner_status}. 두 순위는 구분되며 같은 사례의 진단 결과이지 별도 검증 결과가 아니다.

분석 receipt SHA-256: `{digest(ANALYSIS / 'receipt.json')}`. 그림 manifest는 점수 receipt·선택계획·renderer와 모든 PNG SHA-256에 묶여 있다.
시간별 ΔP는 같은 lead의 같은 paired point에서 계산한 $P_{{case}}-P_{{ORIGINAL}}$ (mm)다. 분석 receipt는 6개 difference NPZ의 해시를 보유하며 그림 manifest도 이를 기록한다. ΔP 지도 공통 색 범위는 [{figures['pointwise_precipitation_difference']['shared_color_limits_mm'][0]:.1f}, {figures['pointwise_precipitation_difference']['shared_color_limits_mm'][1]:.1f}] mm이고 관측 범위는 [{figures['pointwise_precipitation_difference']['observed_min_mm']:.6g}, {figures['pointwise_precipitation_difference']['observed_max_mm']:.6g}] mm다.

- 점수 receipt: [receipt.json](evidence/snow_lower_20261030/analysis/receipt.json)
- 그림 manifest: [figure_manifest.json](evidence/snow_lower_20261030/figures/figure_manifest.json)
- 재현: `python tools/plot_snow_lower.py --analysis-dir docs/evidence/snow_lower_20261030/analysis`; `python docs/evidence/snow_lower_20261030/build_report.py`
'''
    return report, all_gallery, improved_gallery


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--figure-ref', default=os.environ.get(
        'SNOW_LOWER_FIGURE_REF', 'research/snow-lower-sensitivity'),
        help='GitHub ref used to load figure PNGs through images.weserv.nl')
    figure_ref = parser.parse_args().figure_ref
    report, gallery, improved = build(figure_ref)
    outputs = ((OUTPUT, report.encode()), (FIGURE_GALLERY, gallery.encode()),
               (IMPROVED_GALLERY, improved.encode()))
    for path, content in outputs:
        if path.is_symlink():
            raise ValueError(f'refusing to replace symlink: {path}')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for path, content in outputs:
        if not path.exists() or path.read_bytes() != content:
            path.write_bytes(content)
    print(json.dumps({'status': 'COMPLETE', 'reports': [
        {'path': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(content).hexdigest(),
         'size_bytes': len(content)} for path, content in outputs]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
