#!/usr/bin/env python3
"""Render the sensitivity report from hash-sealed score tables."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ANALYSIS = HERE / 'analysis'
OUTPUT = ROOT / 'docs/SNOW_SENSITIVITY_20261030.md'
THRESHOLDS = (0.1, 0.5, 1, 2.5, 5, 10)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(name):
    with (ANALYSIS / name).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def label(case):
    names = {'ORIGINAL': '규준 실험', 'CURRENT_HYDRO': '기존 HYDRO',
             'IMPROVED_BG_FIXED': '기존 개선안 B1'}
    if case in names:
        return names[case]
    family, _, factor = case.split('_')
    return f'{"규준 기반" if family == "CONTROL" else "개선본 기반"} α={int(factor)/100:g}'


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |',
                      *['| ' + ' | '.join(map(str, row)) + ' |' for row in rows]])


def main():
    if OUTPUT.exists() or OUTPUT.is_symlink() or (HERE / 'report_receipt.json').exists():
        raise FileExistsError('report or receipt already exists')
    receipt = json.loads((ANALYSIS / 'receipt.json').read_text())
    if receipt['status'] != 'COMPLETE':
        raise ValueError('complete scoring required')
    for name, item in receipt['analysis_outputs'].items():
        path = ANALYSIS / name
        if path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
            raise ValueError(f'changed analysis: {name}')
    rows = read_csv('categorical_scores.csv')
    errors = read_csv('continuous_scores.csv')
    choices = read_csv('selection_scores.csv')
    selection = json.loads((ANALYSIS / 'selection.json').read_text())
    cat = {(int(r['lead_hour']), r['case'], float(r['threshold_mm'])): r for r in rows}
    cont = {(int(r['lead_hour']), r['case']): r for r in errors}
    cases = {r['case'] for r in errors}
    if len(cases) != 15 or len(rows) != 540 or len(cat) != 540 or len(errors) != 90 or len(cont) != 90:
        raise ValueError('expected complete 15-case six-hour tables')
    if set(cat) != {(h, c, t) for h in range(1, 7) for c in cases for t in THRESHOLDS}:
        raise ValueError('categorical coverage differs')
    if set(cont) != {(h, c) for h in range(1, 7) for c in cases} or len(choices) != 14:
        raise ValueError('continuous or selection coverage differs')
    best = selection['best_eligible_overall_case']
    improved = selection['best_eligible_improved_case']
    exploratory = selection['ranking_all_eligible_cases'][0]
    compared = list(dict.fromkeys(['ORIGINAL', 'IMPROVED_BG_FIXED', best, improved, exploratory]))

    def display(case):
        suffix = ' (탐색·미선정)' if case == exploratory and case != best else ''
        return label(case) + suffix

    def score(h, c, t, metric='CSI'):
        value = cat[(h, c, t)][metric]
        return float(value) if value not in ('', 'None') else None

    def formatted(value):
        return '—' if value is None else f'{value:.4f}'

    def score_table(metric):
        return table(['예측시간', '실험', *[f'≥{t:g} mm' for t in THRESHOLDS]],
                     [[f'+{h} h', display(c), *[formatted(score(h, c, t, metric)) for t in THRESHOLDS]]
                      for h in range(1, 7) for c in compared])

    chosen = next(row for row in choices if row['case'] == best)
    status = ('새 민감도 설정을 채택하지 않고 기존 개선안 B1을 유지한다.'
              if best == 'IMPROVED_BG_FIXED' else f'사전 지정한 기준의 최상위 실험은 **{label(best)}**이다.')
    contrasts = []
    for candidate in dict.fromkeys([best, exploratory]):
        for baseline in ('ORIGINAL', 'IMPROVED_BG_FIXED'):
            if candidate == baseline:
                continue
            delta = [score(h, candidate, t) - score(h, baseline, t)
                     for h in range(1, 7) for t in THRESHOLDS]
            worse_mae = [str(h) for h in range(1, 7)
                         if float(cont[(h, candidate)]['MAE_mm']) > float(cont[(h, baseline)]['MAE_mm'])]
            worse_rmse = [str(h) for h in range(1, 7)
                          if float(cont[(h, candidate)]['RMSE_mm']) > float(cont[(h, baseline)]['RMSE_mm'])]
            contrasts.append(f'{display(candidate)}: {label(baseline)} 대비 CSI 36개 조합 중 '
                             f'{sum(d > 0 for d in delta)}개 개선, {sum(d == 0 for d in delta)}개 동일, '
                             f'{sum(d < 0 for d in delta)}개 악화다. MAE 악화 예측시간은 '
                             f'{", ".join(worse_mae) or "없음"}, RMSE 악화 예측시간은 '
                             f'{", ".join(worse_rmse) or "없음"}이다(시간 단위).')
    exploratory_row = next(r for r in choices if r['case'] == exploratory)
    base_row = next(r for r in choices if r['case'] == 'IMPROVED_BG_FIXED')
    exploratory_text = (
        f'조건 충족 여부를 무시한 +1시간 평균 CSI 최상위는 **{display(exploratory)}**이다. '
        f'평균 CSI는 B1의 {float(base_row["first_hour_mean_CSI_6_thresholds"]):.4f}에서 '
        f'{float(exploratory_row["first_hour_mean_CSI_6_thresholds"]):.4f}, '
        f'+1시간 RMSE는 {float(base_row["first_hour_RMSE_mm"]):.4f}에서 '
        f'{float(exploratory_row["first_hour_RMSE_mm"]):.4f} mm로 변했다. '
        '아래 시간별 표와 분포도에는 이 탐색 비교도 포함하지만 공식 선정 결과와 구분한다.')
    guard_labels = {
        'first_hour_CSI_at_5mm_at_least_alpha1': '+1시간 5 mm CSI ≥ B1',
        'first_hour_RMSE_at_most_alpha1': '+1시간 RMSE ≤ B1',
        'pooled_6h_MAE_at_most_alpha1': '6시간 전체 표본 MAE ≤ B1',
        'pooled_6h_RMSE_at_most_alpha1': '6시간 전체 표본 RMSE ≤ B1',
    }
    failed = selection['feasibility_failures'].get(exploratory, [])
    if failed:
        exploratory_text += ' **미충족 조건: ' + ', '.join(guard_labels[k] for k in failed) + '.**'
    transitions = [r for r in read_csv('transitions.csv')
                   if r['candidate'] == exploratory and r['baseline'] == 'IMPROVED_BG_FIXED'
                   and int(r['lead_hour']) == 1 and float(r['threshold_mm']) == 5]
    if len(transitions) == 1:
        r = transitions[0]
        exploratory_text += (f' +1시간 5 mm에서 B1 대비 새 적중 {r["hit_gains"]}개, '
                             f'적중 소실 {r["hit_losses"]}개, 새 오경보 {r["false_alarm_gains"]}개, '
                             f'오경보 제거 {r["false_alarm_losses"]}개다.')
    lowest_rmse = min(choices, key=lambda r: float(r['pooled_RMSE_mm']))
    parts = [
        '# 초기 눈 혼합비 민감도에 따른 1–6시간 강수예보 반응',
        '## 초록',
        '2026년 8월 16일 12 UTC 사례에서 규준 실험과 기존 개선안 B1 각각의 초기 눈 혼합비를 여섯 배율로 변화시켜 12개의 6시간 예보를 수행했다. 각 계열의 배율 1 대조군은 동일 입력 계보의 완료된 예보를 사용했다. 공통 RN1 평가점 3,688개에서 예측시간별 한 시간 강수량을 여섯 임계값으로 검증했다. '+status+
        f' 해당 실험의 +1시간 여섯 임계값 평균 CSI는 {float(chosen["first_hour_mean_CSI_6_thresholds"]):.4f}, '
        f'6시간 전체 표본 RMSE는 {float(chosen["pooled_RMSE_mm"]):.4f} mm이다. 결과는 같은 사례에서 선정한 탐색적 민감도이며 독립 사례의 예측 성능을 입증하지 않는다.',
        '## 1. 연구 목적',
        '첫 시간 강수 악화의 원인을 좁히기 위해, 기존 개선안에도 눈 수종 민감도를 적용하고 규준 실험의 반응과 비교한다. 앞선 연구는 초기 수종 감소와 첫 미세물리 반응의 차이를 확인했으나, 초기 눈 양의 변화만으로 지상 강수 변화의 방향을 결정할 수 없었다. 본 실험은 눈 초기량에 대한 수치적 반응을 분리해 비교한다.',
        '## 2. 실험 설계 및 수학적 정의',
        table(['계열', '배율 1의 대조군', '실행파일', '추가 배율 α'], [
            ['규준 기반', '규준 실험 (ORIGINAL)', '과거 CP02 WRF', '0, 0.25, 0.5, 0.75, 1.25, 1.5'],
            ['개선본 기반', '기존 개선안 B1 (IMPROVED_BG_FIXED)', '영 전환항 처리 수정 WRF', '0, 0.25, 0.5, 0.75, 1.25, 1.5']]),
        'B1은 생산자 단계의 배경 강수 수종 보존과 WRF의 정확한 영 전환항 처리 수정을 결합한다. 따라서 두 계열 사이의 차이는 눈 배율 하나의 독립 효과가 아니다. 같은 계열 안에서 배율만 바꾼 비교가 눈 초기량 민감도에 해당한다. 기존 HYDRO는 참고 점수로 보존하되 최적 실험 선정에서는 제외한다.',
        r'초기장 조작은 $q_s^{(\alpha)}=\operatorname{REAL32}[\alpha\operatorname{REAL64}(q_s^{(1)})]$이다. QSNOW 이외 207개 변수와 메타데이터는 유지한다. 따라서 반올림 전 관계는 $\Delta q_{\mathrm{water}}=(\alpha-1)q_s^{(1)}$이며, 수증기·온도 등을 보상 조정하지 않는다. 이는 물과 에너지를 보존하는 초기화 정책이 아니라 초기 눈 양을 직접 증감하는 진단 실험이다.',
        '```mermaid\nflowchart LR\n A[규준 초기장] --> C[QSNOW × α]\n B[개선본 초기장] --> D[QSNOW × α]\n C --> E[기존 WRF · 6시간]\n D --> F[수정 WRF · 6시간]\n E --> G[시간별 총강수 · 공통 검증점]\n F --> G\n G --> H[사전 기준 적용 · 선정 및 한계]\n```',
        r'검증량은 지상 눈 강수만이 아니라 누적 총강수 $C=RAINC+RAINNC$의 한 시간 증가량 $P_h=C(t_0+h)-C(t_0+h-1)$이다. +6시간 점수는 17–18 UTC 강수이며 6시간 누적강수 점수가 아니다. 기존과 동일한 네 모서리 보간·공통 지점·관측 자료를 사용한다.',
        r'적중 $H$, 누락 $M$, 오경보 $F$, 전체 지점 수 $N$에 대해 $CSI=H/(H+M+F)$, $POD=H/(H+M)$, $FAR=F/(H+F)$, $Bias=(H+F)/(H+M)$이다. 우연 적중 $H_r=(H+M)(H+F)/N$을 사용해 $ETS=(H-H_r)/(H+M+F-H_r)$를 계산한다.',
        r'오차 $e_i=f_i-o_i$에 대해 $MAE=N^{-1}\sum|e_i|$, $RMSE=\sqrt{N^{-1}\sum e_i^2}$이다. 6시간 전체 표본의 오차는 $MAE_{pool}=\sum_hN_hMAE_h/\sum_hN_h$, $RMSE_{pool}=\sqrt{\sum_hN_hRMSE_h^2/\sum_hN_h}$이다. 시간별 RMSE의 단순 평균을 사용하지 않는다.',
        '### 2.1 결과 확인 전 고정한 선정 기준',
        '기존 개선안 B1보다 +1시간 5 mm CSI가 낮지 않고, +1시간 RMSE와 6시간 전체 표본 MAE·RMSE가 높지 않은 실험만 선정 가능하다(비교 허용오차 10⁻¹²). 그중 +1시간 여섯 임계값 평균 CSI, +1시간 MAE, +1시간 RMSE, |α−1|, 실험 ID 순으로 결정한다. B1보다 높은 순위의 실험이 없으면 B1을 유지한다. 임계값 평균은 상관된 여섯 점수의 설계상 요약이며 독립적인 여섯 검증 사례가 아니다.',
        '## 3. 결과',
        '### 3.1 모든 민감도 실험의 비교',
        table(['실험', '+1 h 평균 CSI', '+1 h CSI ≥5', '+1 h MAE', '+1 h RMSE', '전체 MAE', '전체 RMSE', '선정 조건 충족'],
              [[label(r['case']), *[f'{float(r[k]):.4f}' for k in (
                  'first_hour_mean_CSI_6_thresholds', 'first_hour_CSI_at_5mm', 'first_hour_MAE_mm',
                  'first_hour_RMSE_mm', 'pooled_MAE_mm', 'pooled_RMSE_mm')],
                '예' if r['feasible'].lower() == 'true' else '아니오']
               for r in sorted(choices, key=lambda r: (r['arm'], float(r['alpha'])))]),
        status + f' 개선본 계열 내 최상위는 **{label(improved)}**이다. 각 배율의 전체 순위와 탈락 조건은 [선정 기록](evidence/snow_sensitivity_20261030/analysis/selection.json)에 공개한다.',
        exploratory_text,
        f'6시간 전체 표본 RMSE만 최소화하면 {label(lowest_rmse["case"])}가 '
        f'{float(lowest_rmse["pooled_RMSE_mm"]):.4f} mm로 가장 작다. 그러나 해당 실험의 +1시간 5 mm CSI는 '
        f'{float(lowest_rmse["first_hour_CSI_at_5mm"]):.4f}이다. 첫 시간 사건 검출과 전체 강수량 오차의 최적 설정은 같지 않으며, 한 지표의 최솟값을 사전 선정 기준과 혼동하지 않는다.',
        '![계열별 눈 배율 민감도](evidence/snow_sensitivity_20261030/figures/snow_alpha_dose_response.png)',
        '### 3.2 예측시간·임계값별 CSI', score_table('CSI'),
        '### 3.3 예측시간별 강수량 오차 (mm)',
        table(['예측시간', '실험', 'MAE', 'RMSE', '평균오차'],
              [[f'+{h} h', display(c), *[f'{float(cont[(h,c)][m]):.4f}' for m in ('MAE_mm','RMSE_mm','mean_error_mm')]]
               for h in range(1,7) for c in compared]),
        '\n\n'.join(contrasts),
        '![시간·임계값별 CSI 비교](evidence/snow_sensitivity_20261030/figures/selected_case_csi_comparison.png)',
        '![시간별 강수량 오차](evidence/snow_sensitivity_20261030/figures/selected_case_hourly_errors.png)',
        '### 3.4 시간별 강수 분포',
        '공통 평가점과 같은 색 구간으로 비교한다. RN1 지점 사이를 추가 보간하지 않으며 자료 coverage를 확정한 지도로 해석하지 않는다.',
        '![+1–+3시간 강수 분포](evidence/snow_sensitivity_20261030/figures/snow_sensitivity_maps_leads_1_3.png)',
        '![+4–+6시간 강수 분포](evidence/snow_sensitivity_20261030/figures/snow_sensitivity_maps_leads_4_6.png)',
        '## 4. 기상학적 의미 및 논의',
        '초기 눈 혼합비 변화는 얼음상 수상체의 저장량을 바꾼다. 이후 융해·승화·낙하·수송 및 열역학 반응이 지상 총강수에 영향을 줄 수 있으나, 본 실험의 점수와 분포만으로 개별 과정의 기여를 분리할 수 없다. 눈을 줄이면 지상 강수가 반드시 줄거나 예측이 반드시 개선된다는 단조 관계를 가정하지 않는다. 계열별 배율 반응과 적중·오경보 전이를 함께 판단해야 한다.',
        '다음 개념도는 가능한 반응 경로를 정리한 것으로, 이번 실험에서 과정별 기여를 직접 계측했다는 뜻이 아니다.',
        '```mermaid\nflowchart LR\n S[초기 눈 혼합비 변화] --> M[융해 및 수상체 분배]\n S --> V[승화 및 수증기·온도 반응]\n M --> T[낙하·수송과 후속 미세물리]\n V --> T\n T --> P[시간별 지상 총강수 분포]\n P --> H[적중·누락·오경보 및 강수량 오차]\n```',
        '같은 배율도 두 계열의 절대 초기 눈 양과 다른 초기 상태가 달라 같은 질량 변화가 아니다. 단순 격자 혼합비 합은 층별 건조 질량·면적을 가중한 눈 질량이 아니다. 정확한 물·에너지 수지와 강수 flux를 확보하기 전에는 이 진단 설정을 보존적인 물리 수정으로 채택할 수 없다.',
        '전체 표본 오차 조건을 충족해도 모든 시간·임계값이 좋아지는 것은 아니다. 동일 사례에서 배율을 선택했으므로 선택 편향이 있으며, 독립 사례와 다른 계절·강수계에서의 검증이 필요하다. RN1 상류 시각·coverage·QC의 미확정 범위와 C2 안정성 과제도 별도로 남는다.',
        '## 5. 결론', status + f' 개선본 계열의 우선 비교 대상도 {label(improved)}이다. 이 결과를 토대로 과정별 반응과 보존적인 초기화 구현을 검증한 뒤 독립 강수 사례로 평가해야 한다.',
        '## 자료 및 재현성',
        '[사전 선정 계획](evidence/snow_sensitivity_20261030/selection_plan.json) · [전체 시간·임계값 점수](evidence/snow_sensitivity_20261030/analysis/categorical_scores.csv) · [시간별 오차](evidence/snow_sensitivity_20261030/analysis/continuous_scores.csv) · [적중·오경보 전이](evidence/snow_sensitivity_20261030/analysis/transitions.csv) · [분석 영수증](evidence/snow_sensitivity_20261030/analysis/receipt.json)']
    for metric in ('ETS', 'POD', 'FAR', 'frequency_bias'):
        parts += ['## 부록. ' + metric, score_table(metric)]
    OUTPUT.write_text('\n\n'.join(parts) + '\n', encoding='utf-8')
    (HERE / 'report_receipt.json').write_text(json.dumps({
        'report': str(OUTPUT.relative_to(ROOT)), 'report_sha256': digest(OUTPUT),
        'builder_sha256': digest(Path(__file__)),
        'analysis_receipt_sha256': digest(ANALYSIS / 'receipt.json'),
        'scope': '15 cases; six hourly windows and six thresholds; 14 eligible cases.'
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
