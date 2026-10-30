#!/usr/bin/env python3
"""Build complete per-threshold and per-lead tables from sealed CSVs."""

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'docs/evidence/snow_fine_20261030'
ANALYSIS = EVIDENCE / 'analysis'
ANALYSIS_RECEIPT = ANALYSIS / 'receipt.json'
PLAN_SHA256 = '99d810d036d3bb6931065cc54117e90d85e2a76e388fbb12f5760729a2b703d3'
ANALYSIS_RECEIPT_SHA256 = '62519a61700aa106419517a2acb4b31c50dd5c1f8860cdadf6c7314e65c948ae'
CATEGORICAL_SHA256 = '8fa7923add0e4e8e22fafc7d65d180fd23d685a2994d8e5f9fb82e259c78cc3d'
CONTINUOUS_SHA256 = '365dacaddda8b0db816478a0551d6b9445cd16d99289943a5875937077891d07'
PRIOR_ANALYSIS_RECEIPT_SHA256 = 'c1a10562d9d8bef95a3a3cdc5ad71ef574b78649c2313fe49e7061273c876086'
REPORT = ROOT / 'docs/SNOW_FINE_FULL_SCORES_20261030.md'
BUILD_RECEIPT = EVIDENCE / 'full_tables_receipt.json'
FACTORS = ('000', '025', '050', '075', '125', '150', '175', '200', '250', '300',
           '110', '120', '130', '140')
EXPECTED_CASES = (
    'ORIGINAL', 'CURRENT_HYDRO', 'IMPROVED_BG_FIXED',
    *(f'{arm}_SNOW_{suffix}' for arm in ('CONTROL', 'IMPROVED') for suffix in FACTORS),
)
NEW_CASES = {f'{arm}_SNOW_{suffix}' for arm in ('CONTROL', 'IMPROVED')
             for suffix in ('110', '120', '130', '140')}
ALPHA_BY_SUFFIX = {'000': '0', '025': '0.25', '050': '0.5', '075': '0.75',
                   '110': '1.1', '120': '1.2', '125': '1.25', '130': '1.3',
                   '140': '1.4', '150': '1.5', '175': '1.75', '200': '2',
                   '250': '2.5', '300': '3'}
EXPECTED_THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
EXPECTED_LEADS = tuple(range(1, 7))
POINTS = 3688
CAT_FIELDS = ('hit', 'miss', 'false_alarm', 'correct_dry', 'CSI', 'ETS', 'POD', 'FAR', 'frequency_bias')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def file_record(path):
    path = Path(path)
    return {'path': path.relative_to(ROOT).as_posix(),
            'sha256': sha256(path), 'size_bytes': path.stat().st_size}


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def check_analysis():
    if not ANALYSIS_RECEIPT.is_file() or ANALYSIS_RECEIPT.is_symlink():
        raise ValueError('fine-sensitivity analysis receipt is missing or not a regular file')
    prior_receipt = ROOT / 'docs/evidence/snow_extension_20261030/analysis/receipt.json'
    if sha256(prior_receipt) != PRIOR_ANALYSIS_RECEIPT_SHA256:
        raise ValueError('pinned prior extension analysis receipt changed')
    receipt = json.loads(ANALYSIS_RECEIPT.read_text(encoding='utf-8'))
    if sha256(EVIDENCE / 'selection_plan.json') != PLAN_SHA256:
        raise ValueError('frozen fine-sensitivity selection plan hash mismatch')
    if (receipt.get('status') != 'COMPLETE'
        or receipt.get('cases') != list(EXPECTED_CASES)
        or receipt.get('eligible_cases') != [case for case in EXPECTED_CASES if case != 'CURRENT_HYDRO']
        or receipt.get('context_only_cases') != ['CURRENT_HYDRO']
        or receipt.get('points_per_hour') != POINTS
        or tuple(receipt.get('hours_utc', ())) != tuple(range(13, 19))
        or tuple(receipt.get('thresholds_mm', ())) != EXPECTED_THRESHOLDS
        or receipt.get('row_counts', {}).get('categorical') != len(EXPECTED_CASES) * 36
        or receipt.get('row_counts', {}).get('continuous') != len(EXPECTED_CASES) * 6):
        raise ValueError('analysis receipt does not describe the complete 31-case grid')
    outputs = receipt.get('analysis_outputs', {})
    for name, record in outputs.items():
        path = ANALYSIS / name
        if (path.is_symlink() or not path.is_file()
            or path.stat().st_size != record.get('size_bytes')
            or sha256(path) != record.get('sha256')):
            raise ValueError(f'analysis output hash mismatch: {name}')
    for name in ('categorical_scores.csv', 'continuous_scores.csv', 'selection_scores.csv',
                 'selection.json', *(f'hour_{hour}_arrays.npz' for hour in range(13, 19))):
        if name not in outputs:
            raise ValueError(f'analysis receipt omits required output: {name}')
    cat_path, cont_path = ANALYSIS / 'categorical_scores.csv', ANALYSIS / 'continuous_scores.csv'
    categorical, continuous = read_csv(cat_path), read_csv(cont_path)
    validate_categorical(categorical, EXPECTED_CASES)
    validate_continuous(continuous, EXPECTED_CASES)
    return receipt, categorical, continuous, cat_path, cont_path


def validate_categorical(rows, cases):
    expected = {(lead, case, threshold) for lead in EXPECTED_LEADS
                for case in cases for threshold in EXPECTED_THRESHOLDS}
    actual = set()
    for row in rows:
        lead, case, threshold = int(row['lead_hour']), row['case'], float(row['threshold_mm'])
        key = lead, case, threshold
        if key in actual:
            raise ValueError(f'duplicate categorical key: {key}')
        actual.add(key)
        if row.get('valid_obs') != str(POINTS):
            raise ValueError(f'{key}: paired valid-observation count is not {POINTS}')
        hour = lead + 12
        if (lead not in EXPECTED_LEADS
            or row.get('valid_utc') != f'2026-08-16T{hour:02d}:00:00Z'
            or row.get('window_start_utc') != f'2026-08-16T{hour - 1:02d}:00:00Z'
            or row.get('window_end_utc') != f'2026-08-16T{hour:02d}:00:00Z'):
            raise ValueError(f'{key}: score has an invalid lead or accumulation window')
        counts = [int(row[name]) for name in ('hit', 'miss', 'false_alarm', 'correct_dry')]
        if any(value < 0 for value in counts) or sum(counts) != POINTS:
            raise ValueError(f'{key}: contingency counts do not partition all paired points')
        if any(name not in row for name in CAT_FIELDS):
            raise ValueError(f'{key}: required categorical score column is missing')
    if len(rows) != len(cases) * len(EXPECTED_LEADS) * len(EXPECTED_THRESHOLDS) or actual != expected:
        raise ValueError('categorical CSV is not the complete case×6×6 score grid')


def validate_continuous(rows, cases):
    expected = {(lead, case) for lead in EXPECTED_LEADS for case in cases}
    actual = set()
    for row in rows:
        lead, case = int(row['lead_hour']), row['case']
        key = lead, case
        if key in actual:
            raise ValueError(f'duplicate continuous key: {key}')
        actual.add(key)
        hour = lead + 12
        if (row.get('valid_obs') != str(POINTS)
            or lead not in EXPECTED_LEADS
            or row.get('valid_utc') != f'2026-08-16T{hour:02d}:00:00Z'
            or row.get('window_start_utc') != f'2026-08-16T{hour - 1:02d}:00:00Z'
            or row.get('window_end_utc') != f'2026-08-16T{hour:02d}:00:00Z'):
            raise ValueError(f'{key}: continuous score has invalid observations or time window')
        for name in ('mean_forecast_mm', 'mean_reference_mm', 'MAE_mm', 'RMSE_mm'):
            value = float(row[name])
            if not math.isfinite(value):
                raise ValueError(f'{key}: non-finite continuous metric: {name}')
    if len(rows) != len(cases) * len(EXPECTED_LEADS) or actual != expected:
        raise ValueError('continuous CSV is not the complete case×6 score grid')


def display_case(case):
    if case == 'ORIGINAL':
        return '규준 실험'
    if case == 'CURRENT_HYDRO':
        return '기존 HYDRO (참고)'
    if case == 'IMPROVED_BG_FIXED':
        return '기존 개선안 B1'
    arm, _, suffix = case.partition('_SNOW_')
    family = {'CONTROL': '규준 계열', 'IMPROVED': '개선 계열'}[arm]
    label = f'{family} α={ALPHA_BY_SUFFIX[suffix]}'
    return f'{label} (추가)' if case in NEW_CASES else label


def fmt_metric(value):
    if value in (None, '', 'None'):
        return '—'
    number = float(value)
    return f'{number:.6f}' if math.isfinite(number) else '—'


def fmt_count(value):
    if value is None or value == '':
        return '—'
    return str(int(value))


def categorical_lookup(rows):
    return {(int(row['lead_hour']), row['case'], float(row['threshold_mm'])): row
            for row in rows}


def continuous_lookup(rows):
    return {(int(row['lead_hour']), row['case']): row for row in rows}


def markdown_table(headers, rows):
    lines = ['| ' + ' | '.join(headers) + ' |',
             '| ' + ' | '.join('---' for _ in headers) + ' |']
    lines.extend('| ' + ' | '.join(str(value) for value in row) + ' |' for row in rows)
    return '\n'.join(lines)


def build_markdown(receipt, categorical, continuous):
    case_order = receipt['cases']
    eligible = set(receipt['eligible_cases'])
    cat = categorical_lookup(categorical)
    cont = continuous_lookup(continuous)
    lines = [
        '# 전체 점수표: 시간·임계값별 강수 검증',
        '',
        '이 부록은 완료된 31개 실험을 임계값별·예측시간별로 모두 제시한다. '
        '표기와 실험 ID는 다음과 같다: 규준 실험=ORIGINAL, 기존 HYDRO (참고 실험)=CURRENT_HYDRO, '
        '기존 개선안 B1=IMPROVED_BG_FIXED, 규준 계열 α=값=CONTROL_SNOW_접미사, '
        '개선 계열 α=값=IMPROVED_SNOW_접미사. 접미사→α는 '
        '000→0, 025→0.25, 050→0.5, 075→0.75, 110→1.1, 120→1.2, 125→1.25, '
        '130→1.3, 140→1.4, 150→1.5, 175→1.75, 200→2, 250→2.5, 300→3이다. '
        '세밀 배율 추가 8개 실험에는 `(추가)`를 붙였다. CURRENT_HYDRO는 점수표에는 포함하지만 '
        '30개 선정 후보에는 포함하지 않는다.',
        '',
        '각 점수는 앞선 한 시간 동안의 총 지상 강수(mm)를 3,688개 공통 paired point에서 평가한다. '
        '표의 `ΔCSI(규준대비)`는 같은 예측시간·임계값에서 규준 실험 CSI를 뺀 값이다. '
        '혼동행렬 열은 적중(H), 누락(M), 오경보(FA), 정기각(CN: 관측·예보 모두 해당 임계값 미만) 개수다. '
        '각 시간·임계값의 점수는 따로 읽으며 시간·임계값·실험을 평균해 합치지 않는다. '
        '정의되지 않은 값은 `—`로 둔다.',
        '',
        '전체 표는 표시상 소수점 여섯 자리까지 반올림한다. 원래 정밀도의 값은 '
        '[categorical CSV](evidence/snow_fine_20261030/analysis/categorical_scores.csv)와 '
        '[continuous CSV](evidence/snow_fine_20261030/analysis/continuous_scores.csv)에 있다. '
        '[미세배율 결과 보고서](SNOW_FINE_SENSITIVITY_20261030.md)도 함께 참조한다.',
        '',
        '## 범주형 점수',
        '',
    ]
    for threshold in EXPECTED_THRESHOLDS:
        threshold_label = format(threshold, 'g')
        lines.extend([f'### 강수 임계값 ≥{threshold_label} mm', ''])
        for lead in EXPECTED_LEADS:
            example = cat[(lead, case_order[0], threshold)]
            lines.extend([f'#### +{lead}시간 · {example["window_start_utc"][11:16]}–{example["window_end_utc"][11:16]} UTC', ''])
            table_rows = []
            original = cat[(lead, 'ORIGINAL', threshold)]
            for case in case_order:
                row = cat[(lead, case, threshold)]
                original_csi = original.get('CSI')
                row_csi = row.get('CSI')
                delta = None
                if original_csi not in (None, '', 'None') and row_csi not in (None, '', 'None'):
                    baseline, value = float(original_csi), float(row_csi)
                    if math.isfinite(baseline) and math.isfinite(value):
                        delta = value - baseline
                table_rows.append([
                    display_case(case), fmt_metric(row.get('CSI')),
                    fmt_metric(delta), fmt_metric(row.get('ETS')),
                    fmt_metric(row.get('POD')), fmt_metric(row.get('FAR')),
                    fmt_metric(row.get('frequency_bias')),
                    fmt_count(row.get('hit')), fmt_count(row.get('miss')),
                    fmt_count(row.get('false_alarm')), fmt_count(row.get('correct_dry')),
                ])
            lines.append(markdown_table(
                ['Case', 'CSI', 'ΔCSI(규준대비)', 'ETS', 'POD', 'FAR',
                 'Frequency bias', 'H', 'M', 'FA', 'CN'], table_rows))
            lines.append('')
    lines.extend(['## 연속형 점수', '',
                  '각 예측시간별로 별도 계산한 평균 예보·관측, MAE, RMSE와 ORIGINAL 대비 오차 차이를 보인다. '
                  '이 표의 지표도 시간이나 실험에 걸쳐 평균하지 않는다.', ''])
    for lead in EXPECTED_LEADS:
        example = cont[(lead, case_order[0])]
        lines.extend([f'### +{lead}시간 · {example["window_start_utc"][11:16]}–{example["window_end_utc"][11:16]} UTC', ''])
        base = cont[(lead, 'ORIGINAL')]
        table_rows = []
        for case in case_order:
            row = cont[(lead, case)]
            table_rows.append([
                display_case(case), fmt_metric(row.get('mean_forecast_mm')),
                fmt_metric(row.get('mean_reference_mm')), fmt_metric(row.get('MAE_mm')),
                fmt_metric(row.get('RMSE_mm')),
                fmt_metric(float(row['MAE_mm']) - float(base['MAE_mm'])),
                fmt_metric(float(row['RMSE_mm']) - float(base['RMSE_mm'])),
            ])
        lines.append(markdown_table(
            ['Case', '평균 예보 (mm)', '평균 관측 (mm)', 'MAE (mm)', 'RMSE (mm)',
             'ΔMAE vs 규준 (mm)', 'ΔRMSE vs 규준 (mm)'], table_rows))
        lines.append('')
    lines.extend(['## 자료 및 재현', '',
                  f'- 범주형 표: 36개 ({len(case_order)}실험 × 6 lead × 6 임계값), {len(categorical)}행.',
                  f'- 연속형 표: 6개 ({len(case_order)}실험 × 6 lead), {len(continuous)}행.',
                  f'- 선정 후보는 {len(eligible)}개다. 추가 실험 표시는 선정 여부와 별개로 실험 구분만 나타낸다.',
                  '- 원본 분석 영수증: [analysis receipt](evidence/snow_fine_20261030/analysis/receipt.json).',
                  '- 표 재생성: `python docs/evidence/snow_fine_20261030/build_full_score_tables.py`.',
                  '- 재현 영수증: [full_tables_receipt.json](evidence/snow_fine_20261030/full_tables_receipt.json).',
                  ''])
    return '\n'.join(lines).encode('utf-8')


def check_markdown_tables(report_bytes, receipt, categorical, continuous):
    """Parse rendered tables independently and compare every display cell with its CSV row."""
    parsed_tables = []
    current = []
    for line in report_bytes.decode('utf-8').splitlines() + ['']:
        if line.startswith('|'):
            cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
            if all(cell and set(cell.replace(':', '')) <= {'-'} for cell in cells):
                continue
            current.append(cells)
        elif current:
            parsed_tables.append(current)
            current = []

    case_order = receipt['cases']
    cat = categorical_lookup(categorical)
    cont = continuous_lookup(continuous)
    expected_tables = []
    for threshold in EXPECTED_THRESHOLDS:
        for lead in EXPECTED_LEADS:
            rows = [['Case', 'CSI', 'ΔCSI(규준대비)', 'ETS', 'POD', 'FAR',
                     'Frequency bias', 'H', 'M', 'FA', 'CN']]
            original = cat[(lead, 'ORIGINAL', threshold)]
            for case in case_order:
                row = cat[(lead, case, threshold)]
                delta = None
                if row.get('CSI') not in (None, '', 'None') and original.get('CSI') not in (None, '', 'None'):
                    delta = float(row['CSI']) - float(original['CSI'])
                rows.append([display_case(case), fmt_metric(row.get('CSI')), fmt_metric(delta),
                             fmt_metric(row.get('ETS')), fmt_metric(row.get('POD')),
                             fmt_metric(row.get('FAR')), fmt_metric(row.get('frequency_bias')),
                             fmt_count(row.get('hit')), fmt_count(row.get('miss')),
                             fmt_count(row.get('false_alarm')), fmt_count(row.get('correct_dry'))])
            expected_tables.append(rows)
    for lead in EXPECTED_LEADS:
        rows = [['Case', '평균 예보 (mm)', '평균 관측 (mm)', 'MAE (mm)', 'RMSE (mm)',
                 'ΔMAE vs 규준 (mm)', 'ΔRMSE vs 규준 (mm)']]
        baseline = cont[(lead, 'ORIGINAL')]
        for case in case_order:
            row = cont[(lead, case)]
            rows.append([display_case(case), fmt_metric(row.get('mean_forecast_mm')),
                         fmt_metric(row.get('mean_reference_mm')), fmt_metric(row.get('MAE_mm')),
                         fmt_metric(row.get('RMSE_mm')),
                         fmt_metric(float(row['MAE_mm']) - float(baseline['MAE_mm'])),
                         fmt_metric(float(row['RMSE_mm']) - float(baseline['RMSE_mm']))])
        expected_tables.append(rows)
    if len(parsed_tables) != 42 or parsed_tables != expected_tables:
        raise ValueError('rendered Markdown tables differ from the sealed CSV values')
    return {'status': 'PASS', 'table_count': len(parsed_tables),
            'categorical_data_cells': len(categorical) * 11,
            'continuous_data_cells': len(continuous) * 7,
            'matched_data_cells': len(categorical) * 11 + len(continuous) * 7}


def write_if_new_or_equal(path, content):
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f'refusing to replace symlink: {path}')
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f'refusing to replace non-identical generated output: {path}')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main():
    receipt, categorical, continuous, cat_path, cont_path = check_analysis()
    report_bytes = build_markdown(receipt, categorical, continuous)
    table_csv_match = check_markdown_tables(report_bytes, receipt, categorical, continuous)
    generator_record = file_record(Path(__file__).resolve())
    build_receipt = {
        'status': 'COMPLETE',
        'schema': 'snow-fine-full-score-tables-v1',
        'analysis_receipt': file_record(ANALYSIS_RECEIPT),
        'sources': [file_record(cat_path), file_record(cont_path)],
        'generator': generator_record,
        'report': {'path': REPORT.relative_to(ROOT).as_posix(),
                   'sha256': hashlib.sha256(report_bytes).hexdigest(),
                   'size_bytes': len(report_bytes)},
        'cases': receipt['cases'],
        'eligible_cases': receipt['eligible_cases'],
        'context_only_cases': receipt['context_only_cases'],
        'thresholds_mm': list(EXPECTED_THRESHOLDS),
        'lead_hours': list(EXPECTED_LEADS),
        'points_per_hour': POINTS,
        'table_counts': {'categorical': 36, 'continuous': 6, 'total': 42},
        'row_counts': {'categorical': len(categorical), 'continuous': len(continuous),
                       'total_table_rows': len(categorical) + len(continuous)},
        'table_csv_match': table_csv_match,
        'display_precision_decimal_places': 6,
        'delta_definition': 'Per lead and threshold CSI(case) minus CSI of the 규준 실험 (ORIGINAL); continuous deltas subtract same-lead 규준 error.',
        'reproduction_contract': 'Refuse to write unless existing Markdown and receipt bytes equal freshly generated bytes.'
    }
    receipt_bytes = (json.dumps(build_receipt, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    if sha256(ANALYSIS_RECEIPT) != ANALYSIS_RECEIPT_SHA256:
        raise ValueError('sealed analysis receipt changed during table generation')
    if sha256(cat_path) != CATEGORICAL_SHA256 or sha256(cont_path) != CONTINUOUS_SHA256:
        raise ValueError('sealed analysis CSV changed during table generation')
    # Check both destinations before writing either file.
    for path, content in ((REPORT, report_bytes), (BUILD_RECEIPT, receipt_bytes)):
        if path.is_symlink() or (path.exists() and path.read_bytes() != content):
            raise ValueError(f'refusing non-identical generated output: {path}')
    write_if_new_or_equal(REPORT, report_bytes)
    write_if_new_or_equal(BUILD_RECEIPT, receipt_bytes)
    print(json.dumps({'status': 'COMPLETE', 'report': REPORT.relative_to(ROOT).as_posix(),
                      'report_sha256': hashlib.sha256(report_bytes).hexdigest(),
                      'table_counts': build_receipt['table_counts'],
                      'row_counts': build_receipt['row_counts']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
