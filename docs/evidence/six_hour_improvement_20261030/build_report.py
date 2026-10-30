#!/usr/bin/env python3
"""Render hourly threshold tables from the sealed six-hour analysis outputs."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ANALYSIS = HERE / 'analysis'
OUTPUT = ROOT / 'docs/SIX_HOUR_IMPROVEMENT_20261030.md'
CASES = ('ORIGINAL', 'CURRENT_HYDRO', 'IMPROVED_BG_FIXED')
LABELS = dict(zip(CASES, ('원본 OFF', '기존 HYDRO', '개선안')))
THRESHOLDS = (0.1, 0.5, 1, 2.5, 5, 10)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |',
                      *['| ' + ' | '.join(map(str, row)) + ' |' for row in rows]])


def main():
    receipt = json.loads((ANALYSIS / 'receipt.json').read_text())
    if receipt['status'] != 'COMPLETE':
        raise ValueError('incomplete analysis')
    for name, item in receipt['analysis_outputs'].items():
        path = ANALYSIS / name
        if path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
            raise ValueError(f'analysis artifact changed: {name}')
    with (ANALYSIS / 'categorical_scores.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    with (ANALYSIS / 'continuous_scores.csv').open() as stream:
        errors = list(csv.DictReader(stream))
    keyed = {(int(r['lead_hour']), r['case'], float(r['threshold_mm'])): r for r in rows}
    cont = {(int(r['lead_hour']), r['case']): r for r in errors}
    if len(rows) != 108 or set(keyed) != {(h,c,t) for h in range(1,7) for c in CASES for t in THRESHOLDS}:
        raise ValueError('missing, duplicate or unexpected categorical row')
    if len(errors) != 18 or set(cont) != {(h,c) for h in range(1,7) for c in CASES}:
        raise ValueError('missing, duplicate or unexpected continuous row')
    def value(h,c,t,metric='CSI'):
        return float(keyed[(h,c,t)][metric])
    headers = ['예측시간','실험',*[f'≥{t:g} mm' for t in THRESHOLDS]]
    def metric_table(metric):
        return table(headers, [[f'+{h} h', LABELS[c], *[f'{value(h,c,t,metric):.4f}' for t in THRESHOLDS]]
                               for h in range(1,7) for c in CASES])
    parts = [
        '# 배경 강수 보존·영 전환항 수정의 +1~+6시간 강수예보 비교',
        '**2026-10-30 · 단일 사례의 시간대별 검증**',
        '## 1. 실험 및 검증 구간',
        '2026년 8월 16일 12 UTC 초기화 사례에서 기존 개선안(B1)을 18 UTC까지 확장했다. 새 예보 실행은 1회이며 원본 OFF와 기존 HYDRO는 완료·보존된 6시간 대조군이다. 개선안은 생산자 단계 배경 강수 수종 보존과 KDM6 정확한 영 전환항 처리를 결합한다. 원본과의 차이는 결합 변경의 비교이며 정책과 실행파일 수정의 독립적인 인과효과가 아니다. 실행파일·초기장·경계자료는 기존 1시간 개선안과 같고 예보·history 종료 시각만 변경했다. 새 13 UTC history는 이전 1시간 실행과 바이트 단위로 동일하다.',
        table(['표기','실험 ID','설정'], [
            ['원본 OFF',CASES[0],'실제 원본 초기장·기존 WRF'],
            ['기존 HYDRO',CASES[1],'기존 HYDRO 초기화·기존 WRF'],
            ['개선안',CASES[2],'배경 강수 보존 초기화·수정 WRF']]),
        '각 점수는 공통 3,688개 처리 RN1 평가점의 해당 **한 시간 강수량**을 비교한다. +6 h는 17–18 UTC이며 12–18 UTC 누적량이 아니다. 임계값은 mm 단위이고 사건은 강수량 ≥ 임계값이다.',
        table(['예측시간','검증 구간 (UTC)','검증 구간 (KST)'], [[f'+{h} h',f'8월 16일 {11+h:02d}–{12+h:02d}시',
            ['8월 16일 21–22시','8월 16일 22–23시','8월 16일 23시–17일 00시','8월 17일 00–01시','8월 17일 01–02시','8월 17일 02–03시'][h-1]] for h in range(1,7)]),
        '## 2. 수학적 정의',
        r'누적 강수 $C(t)=RAINC(t)+RAINNC(t)$에서 $P_h=C(t_0+h)-C(t_0+h-1)$를 계산한다. RAINSH는 0인지 별도로 검사하고 합에서 제외한다. 고정된 WRF 네 모서리 bilinear 보간 뒤 임계값을 적용한다. 적중 H, 누락 M, 오경보 F, 전체 점 수 N에 대해 다음 점수를 사용한다.',
        r'\[CSI=\frac{H}{H+M+F},\quad POD=\frac{H}{H+M},\quad FAR=\frac{F}{H+F},\quad Bias=\frac{H+F}{H+M}.\]',
        r'\[H_r=\frac{(H+M)(H+F)}{N},\qquad ETS=\frac{H-H_r}{H+M+F-H_r}.\]',
        r'오차 $e_i=f_i-o_i$에 대해 $MAE=N^{-1}\sum_i|e_i|$, $RMSE=\sqrt{N^{-1}\sum_i e_i^2}$, $ME=N^{-1}\sum_i e_i$다. CSI·ETS·POD는 클수록, FAR·MAE·RMSE는 작을수록 좋다. 빈도 Bias는 1, ME는 0이 기준이다. POD 증가만으로 개선이라고 판정하지 않고 오경보와 함께 본다.',
        '## 3. 예측시간·임계값별 CSI', metric_table('CSI'),
        '## 4. 원본 대비 개선안의 CSI 차이',
        'ΔCSI = 개선안 − 원본이다. 양수는 해당 시간·임계값의 개선, 음수는 악화다. 표는 소수 넷째 자리 반올림이며 개선 판정에는 반올림 전 수치를 사용했다.',
        table(['예측시간',*[f'≥{t:g} mm' for t in THRESHOLDS]], [[f'+{h} h', *[f'{value(h,CASES[2],t)-value(h,CASES[0],t):+.4f}' for t in THRESHOLDS]] for h in range(1,7)]),
        '## 5. 시간별 강수량 오차 (mm)',
        table(['예측시간','실험','MAE','RMSE','ME'], [[f'+{h} h',LABELS[c],*[f'{float(cont[(h,c)][m]):.4f}' for m in ('MAE_mm','RMSE_mm','mean_error_mm')]] for h in range(1,7) for c in CASES])]
    for c in CASES[:2]:
        differences = [value(h,CASES[2],t)-value(h,c,t) for h in range(1,7) for t in THRESHOLDS]
        parts.append(f'{LABELS[c]} 대비 CSI 36개 시간·임계값 조합 중 개선 {sum(x>0 for x in differences)}개, 동일 {sum(x==0 for x in differences)}개, 악화 {sum(x<0 for x in differences)}개다. 36개 조합은 독립적인 36개 기상 사례를 뜻하지 않는다.')
    threshold_counts = []
    for threshold in THRESHOLDS:
        d = [value(h,CASES[2],threshold)-value(h,CASES[0],threshold) for h in range(1,7)]
        threshold_counts.append([f'≥{threshold:g} mm', sum(x>0 for x in d), sum(x==0 for x in d), sum(x<0 for x in d)])
    parts += ['원본 대비 임계값별 개선·악화 시간 수는 다음과 같다.',
              table(['임계값','개선 시간 수','동일 시간 수','악화 시간 수'],threshold_counts),
              '## 6. 시간별 분포와 기상학적 해석',
              '5 mm CSI는 원본보다 여섯 시간 모두 높다. 그러나 약한 강수 임계값의 CSI는 첫 시간 이후 다수 구간에서 낮아진다. 특히 +4시간은 MAE·RMSE와 10 mm CSI가 함께 악화된다. +5시간은 MAE·RMSE와 0.5 mm 이상 다섯 CSI가 함께 개선된다. +6시간은 5·10 mm CSI가 높지만 낮은 네 임계값 CSI와 MAE·RMSE는 악화된다. 따라서 강한 강수 사건의 겹침 개선을 전체 강수량·위치 오차의 일관된 개선으로 확대해서는 안 된다.',
        '강수 분포도는 같은 평가점과 색 구간을 사용한다. 점 사이를 공간 보간하거나 RN1 coverage를 확정적으로 표현하지 않는다. 초기 수상체와 열역학 상태의 차이는 이후 미세물리·수송·낙하와 상호작용한다. 시간별 점수만으로 과정별 기여를 분해할 수 없으며, 첫 시간 개선의 지속 여부는 각 시간의 실제 점수와 적중·오경보 전이로 판단한다. 강한 강수의 적중 회복과 오경보 증가를 함께 검토해야 한다.',
        '![시간·임계값별 점수와 시간별 오차](evidence/six_hour_improvement_20261030/figures/six_hour_skill_summary.png)',
        '![+1~+3시간 강수 분포](evidence/six_hour_improvement_20261030/figures/precipitation_maps_leads_1_3.png)',
        '![+4~+6시간 강수 분포](evidence/six_hour_improvement_20261030/figures/precipitation_maps_leads_4_6.png)',
        '## 7. 범위와 제한',
        '한 기상 사례의 +1~+6시간 연구 비교다. RN1 상류 입력 최신성·coverage/QC·공간 대표성은 미확정이다. 배경 보존 정책은 8개 native 초기장 필드를 함께 바꾸므로 QR·QS만의 효과가 아니다. 전체 물·에너지 수지와 과정별 강수 flux, 다른 사례의 일반화 성능, 별도 C2 안정성 및 운영 승인은 이 검증으로 완료되지 않는다. 기존 1시간 요인 실험의 독립 효과와 상호작용을 이번 6시간 결합 실험의 각 시간으로 외삽하지 않는다.',
        '[전체 점수 CSV](evidence/six_hour_improvement_20261030/analysis/categorical_scores.csv) · [연속 점수](evidence/six_hour_improvement_20261030/analysis/continuous_scores.csv) · [적중·오경보 전이](evidence/six_hour_improvement_20261030/analysis/transitions.csv) · [분석 영수증](evidence/six_hour_improvement_20261030/analysis/receipt.json)']
    for metric,title in [('ETS','ETS'),('POD','적중률 POD'),('FAR','오경보율 FAR'),('frequency_bias','강수 빈도 Bias')]:
        parts += ['## 부록. '+title, metric_table(metric)]
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise FileExistsError(OUTPUT)
    OUTPUT.write_text('\n\n'.join(parts)+'\n',encoding='utf-8')
    (HERE/'report_receipt.json').write_text(json.dumps({'report':str(OUTPUT.relative_to(ROOT)),
        'report_sha256':digest(OUTPUT),'builder_sha256':digest(Path(__file__)),
        'analysis_receipt_sha256':digest(ANALYSIS/'receipt.json'),
        'scope':'Tables from sealed 108 categorical and 18 continuous rows; independent score replay is separate.'},indent=2)+'\n')
    print(OUTPUT)


if __name__=='__main__':
    main()
