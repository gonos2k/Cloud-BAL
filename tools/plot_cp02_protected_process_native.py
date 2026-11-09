#!/usr/bin/env python3
"""Render two selected fixed-level process ledgers after a validated native run."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'docs/evidence/cp02_protected_process_20261106'
DEFAULT_LEDGER = BUNDLE / 'native/analysis/summary/point_level_process_ledger.csv'
DEFAULT_SUMMARY_RECEIPT = DEFAULT_LEDGER.with_name('summary_receipt.json')
DEFAULT_OUTPUT = BUNDLE / 'native_figures'
SUMMARY_TOOL = ROOT / 'tools/cp02_protected_process_summary.py'
FONT = Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
FONT_SHA256 = '48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733'
COHORT_RECEIPT = BUNDLE / 'cohorts/receipt.json'
ROLE_TABLE = BUNDLE / 'cohorts/role_membership.csv'
COHORT_RECEIPT_SHA256 = 'cd1e03fbc075c25f6a4904ce278935dea8d23a2157162274835fca21fc911826'
ROLE_TABLE_SHA256 = '54cbe13a13a7494fdaf10159919c480f90dfad26dcdcf8337735828d05132cb6'
LEADS = (1, 2, 5)
FIELDS = ('QV', 'QC', 'QR', 'TK')
EXPECTED_UNITS = {'QV': 'kg kg-1', 'QC': 'kg kg-1', 'QR': 'kg kg-1', 'TK': 'K'}
POINT_SPECS = {
    'RN1_10942': {'lead_hour': 2, 'steps': [181, 360], 'role': 'plus2_OA_weak_loss',
                  'panel_label': '+2시간 약한 강수 적중 소실'},
    'RN1_12299': {'lead_hour': 5, 'steps': [721, 900], 'role': 'plus5_strong_protected_hit_12299',
                  'panel_label': '+5시간 보호 5 mm 적중'},
}
K_LEVELS = tuple(range(1, 40))
COMPONENTS = ('internal', 'between_call', 'phase8_minus_phase6', 'process_substep', 'remaining')
COLORS = {'internal': '#263238', 'between_call': '#78909c', 'phase8_minus_phase6': '#1565c0',
          'process_substep': '#ef6c00', 'remaining': '#8e24aa'}
LABELS = {'internal': '호출 내부 L: 상태 변화 합',
          'between_call': '호출 사이 E: 반환/다음 진입 차이 합',
          'phase8_minus_phase6': '단계 8-6 주 업데이트',
          'process_substep': '침강(QR) / 응결 하위단계(QV·TK)',
          'remaining': '잔여 호출 내부 성분'}


class NativeFigureInputError(ValueError):
    """The native summary table or its provenance is invalid."""


def sha256(path: Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def configure_font() -> str:
    if not FONT.is_file() or sha256(FONT) != FONT_SHA256:
        raise NativeFigureInputError('pinned Nanum Gothic font is missing or changed')
    font_manager.fontManager.addfont(str(FONT))
    name = font_manager.FontProperties(fname=str(FONT)).get_name()
    plt.rcParams.update({'font.family': name, 'axes.unicode_minus': False,
                         'savefig.dpi': 170, 'figure.facecolor': 'white'})
    return name


def optional_float(value: str | None, field: str) -> float:
    if value is None or value.strip() == '':
        return float('nan')
    result = float(value)
    if not np.isfinite(result):
        raise NativeFigureInputError(f'{field}: nonfinite values must be blank/null in the ledger')
    return result


def verify_cohort_roles() -> dict[str, set[str]]:
    if sha256(COHORT_RECEIPT) != COHORT_RECEIPT_SHA256:
        raise NativeFigureInputError('cohort receipt differs from its frozen hash')
    receipt = json.loads(COHORT_RECEIPT.read_text(encoding='utf-8'))
    if receipt.get('outputs', {}).get('role_membership.csv') != ROLE_TABLE_SHA256 or sha256(ROLE_TABLE) != ROLE_TABLE_SHA256:
        raise NativeFigureInputError('role membership table differs from its frozen hash')
    roles: dict[str, set[str]] = {}
    with ROLE_TABLE.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if not {'point_id', 'role'} <= set(reader.fieldnames or ()):
            raise NativeFigureInputError('role membership table has an unexpected schema')
        for row in reader:
            roles.setdefault(row['point_id'], set()).add(row['role'])
    for point_id, spec in POINT_SPECS.items():
        if spec['role'] not in roles.get(point_id, set()):
            raise NativeFigureInputError(f'{point_id}: required illustrative cohort role is absent')
    return roles


def prepare_profiles(rows: list[dict[str, str]]) -> dict:
    """Validate and organize just the selected point/hour profiles for plotting."""
    expected = {(point_id, spec['lead_hour'], field, level)
                for point_id, spec in POINT_SPECS.items() for field in ('QR', 'QV', 'TK')
                for level in K_LEVELS}
    found = {}
    for row in rows:
        point_id = row.get('point_id', '')
        field = row.get('field', '')
        if point_id not in POINT_SPECS or field not in ('QR', 'QV', 'TK'):
            raise NativeFigureInputError('selected profile contains an unexpected point or field')
        lead = int(row['lead_hour'])
        key = (point_id, lead, field, int(row['native_k_1based']))
        if key not in expected or key in found:
            raise NativeFigureInputError(f'invalid or duplicate selected profile key: {key}')
        if row.get('units') != EXPECTED_UNITS[field]:
            raise NativeFigureInputError(f'{key}: field units differ from the summary schema')
        values = {
            'internal': optional_float(row.get('delta_call_internal_sum'), 'delta_call_internal_sum'),
            'between_call': optional_float(row.get('delta_between_call_sum'), 'delta_between_call_sum'),
            'endpoint': optional_float(row.get('delta_endpoint_change'), 'delta_endpoint_change'),
            'ledger_residual': optional_float(row.get('ledger_residual'), 'ledger_residual'),
            'phase8_minus_phase6': optional_float(row.get('delta_phase8_minus_phase6_sum'), 'phase8-6'),
            'sedimentation': optional_float(row.get('delta_rain_sedimentation_sum'), 'sedimentation'),
            'condensation': optional_float(row.get('delta_condensation_substep_sum'), 'condensation'),
            'remaining': optional_float(row.get('remaining_call_internal_sum'), 'remaining internal'),
        }
        if not all(np.isfinite(values[name]) for name in ('internal', 'between_call', 'endpoint',
                                                          'ledger_residual', 'phase8_minus_phase6')):
            raise NativeFigureInputError(f'{key}: required ledger component is missing')
        if abs(values['ledger_residual']) > 1e-10 or not np.isclose(
                values['endpoint'], values['internal'] + values['between_call'] + values['ledger_residual'],
                rtol=0, atol=1e-10):
            raise NativeFigureInputError(f'{key}: endpoint ledger does not close within tolerance')
        paired_text = row.get('paired_sedimentation_calls', '')
        paired = int(paired_text) if paired_text.strip() else None
        if field == 'QR':
            if paired is None or not 0 <= paired <= 180:
                raise NativeFigureInputError(f'{key}: QR paired-sedimentation count is invalid')
            if paired == 180:
                if not np.isfinite(values['sedimentation']) or not np.isfinite(values['remaining']):
                    raise NativeFigureInputError(f'{key}: complete sedimentation profile is missing its values')
            elif np.isfinite(values['sedimentation']) or np.isfinite(values['remaining']):
                raise NativeFigureInputError(f'{key}: incomplete conditional sedimentation must remain null')
            if np.isfinite(values['condensation']):
                raise NativeFigureInputError(f'{key}: QR has an unexpected condensation component')
            values['process_substep'] = values['sedimentation']
        else:
            if paired is not None or np.isfinite(values['sedimentation']):
                raise NativeFigureInputError(f'{key}: non-QR sedimentation must remain null')
            if not np.isfinite(values['condensation']) or not np.isfinite(values['remaining']):
                raise NativeFigureInputError(f'{key}: required condensation/remaining component is missing')
            values['process_substep'] = values['condensation']
        found[key] = values
    if set(found) != expected:
        raise NativeFigureInputError(f'selected profile is incomplete: expected {len(expected)}, found {len(found)}')
    result = {}
    for point_id, spec in POINT_SPECS.items():
        for field in ('QR', 'QV', 'TK'):
            records = [found[(point_id, spec['lead_hour'], field, level)] for level in K_LEVELS]
            scale = 1e6 if field in ('QR', 'QV') else 1.0
            result[(point_id, field)] = {
                name: np.asarray([record[key] for record in records], dtype=np.float64) * scale
                for name, key in (('internal', 'internal'), ('between_call', 'between_call'),
                                  ('phase8_minus_phase6', 'phase8_minus_phase6'),
                                  ('process_substep', 'process_substep'), ('remaining', 'remaining'))
            }
    return result


def load_profiles(ledger_path: Path, summary_receipt_path: Path) -> tuple[dict, dict]:
    ledger_path, summary_receipt_path = Path(ledger_path), Path(summary_receipt_path)
    if (not ledger_path.is_file() or ledger_path.is_symlink() or not summary_receipt_path.is_file()
        or summary_receipt_path.is_symlink()):
        raise NativeFigureInputError('validated summary ledger or receipt is missing')
    if ledger_path.name != 'point_level_process_ledger.csv' or summary_receipt_path.parent.resolve() != ledger_path.parent.resolve():
        raise NativeFigureInputError('summary ledger and receipt must be the paired filenames in one directory')
    receipt = json.loads(summary_receipt_path.read_text(encoding='utf-8'))
    if (receipt.get('status') != 'CONTIGUOUS_PROCESS_COMPARISON_VALIDATED'
        or receipt.get('rows') != 70200 or receipt.get('hours') != list(LEADS)
        or receipt.get('points') != 150 or receipt.get('levels') != 39
        or receipt.get('fields') != EXPECTED_UNITS):
        raise NativeFigureInputError('summary receipt scope or status differs from the frozen full table contract')
    if receipt.get('tool_sha256') != sha256(SUMMARY_TOOL):
        raise NativeFigureInputError('summary tool changed after it produced this ledger')
    output_record = receipt.get('outputs', {}).get(ledger_path.name)
    if (not output_record or ledger_path.stat().st_size != output_record.get('size_bytes')
        or sha256(ledger_path) != output_record.get('sha256')):
        raise NativeFigureInputError('summary ledger differs from its receipt hash or size')
    verify_cohort_roles()
    expected_count = 150 * len(LEADS) * len(FIELDS) * len(K_LEVELS)
    seen = set()
    selected_rows = []
    point_ids = set()
    required_columns = {'lead_hour', 'point_id', 'native_k_1based', 'field', 'units',
                        'delta_call_internal_sum', 'delta_between_call_sum', 'delta_endpoint_change',
                        'ledger_residual', 'delta_phase8_minus_phase6_sum',
                        'delta_rain_sedimentation_sum', 'paired_sedimentation_calls',
                        'delta_condensation_substep_sum', 'remaining_call_internal_sum'}
    with ledger_path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if not required_columns <= set(reader.fieldnames or ()):
            raise NativeFigureInputError('summary ledger columns differ from expected schema')
        for row in reader:
            lead, level, field, point_id = int(row['lead_hour']), int(row['native_k_1based']), row['field'], row['point_id']
            if lead not in LEADS or level not in K_LEVELS or field not in FIELDS:
                raise NativeFigureInputError('summary ledger has an unexpected lead, level, or field')
            if row['units'] != EXPECTED_UNITS[field]:
                raise NativeFigureInputError(f'{point_id}/{field}: units differ from frozen summary schema')
            point_ids.add(point_id)
            key = (lead, point_id, field, level)
            if key in seen:
                raise NativeFigureInputError(f'duplicate summary ledger key: {key}')
            seen.add(key)
            if point_id in POINT_SPECS and lead == POINT_SPECS[point_id]['lead_hour'] and field in ('QR','QV','TK'):
                selected_rows.append(row)
    if len(seen) != expected_count or len(point_ids) != 150:
        raise NativeFigureInputError(f'full summary population differs: {len(seen)} rows, {len(point_ids)} points')
    profiles = prepare_profiles(selected_rows)
    metadata = {
        'summary_receipt_sha256': sha256(summary_receipt_path),
        'summary_ledger_sha256': output_record['sha256'],
        'summary_tool_sha256': receipt['tool_sha256'],
        'cohort_receipt_sha256': COHORT_RECEIPT_SHA256,
        'role_membership_sha256': ROLE_TABLE_SHA256,
        'full_launch_receipt_sha256': receipt['full_launch_receipt_sha256'],
        'collector_receipt_sha256': receipt['collector_receipt_sha256'],
    }
    return profiles, metadata


def make_figure(profiles: dict, path: Path) -> None:
    if set(profiles) != {(point_id, field) for point_id in POINT_SPECS for field in ('QR', 'QV', 'TK')}:
        raise NativeFigureInputError('figure requires the six frozen point/field profiles')
    configure_font()
    fig, axes = plt.subplots(3, 2, figsize=(14, 10), sharex=True, constrained_layout=False)
    rows = (('QR', 'QR'), ('QV', 'QV'), ('TK', 'TK'))
    for row_index, (field, _label) in enumerate(rows):
        for col_index, (point_id, spec) in enumerate(POINT_SPECS.items()):
            ax = axes[row_index, col_index]
            values = profiles[(point_id, field)]
            if set(values) != set(COMPONENTS) or any(np.asarray(values[key]).shape != (39,) for key in COMPONENTS):
                raise NativeFigureInputError(f'{point_id}/{field}: component profile must have 39 native levels')
            for component in COMPONENTS:
                array = np.asarray(values[component], dtype=np.float64)
                if np.isinf(array).any():
                    raise NativeFigureInputError(f'{point_id}/{field}/{component}: infinite value')
                label = LABELS[component]
                ax.plot(K_LEVELS, array, marker='o', markersize=2.5, linewidth=1.1,
                        color=COLORS[component], label=label)
            units = 'mg kg⁻¹' if field in ('QR', 'QV') else 'K'
            ax.axhline(0, color='#777777', linewidth=.7, zorder=0)
            substep = '침강' if field == 'QR' else '응결 하위단계'
            ax.set_title(f"{spec['panel_label']} · {point_id} · {field} (주황: {substep}; 호출 {spec['steps'][0]}–{spec['steps'][1]})",
                         fontsize=9)
            ax.set_ylabel(f'실제 호출 시간합 Δ ({units})')
            ax.set_xlim(1, 39)
            ax.set_xticks((1, 5, 10, 15, 20, 25, 30, 35, 39))
            ax.grid(alpha=.22)
    for ax in axes[-1, :]:
        ax.set_xlabel('모형 층 k (1부터 시작; 고도 환산 없음)')
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncol=3, frameon=False, bbox_to_anchor=(.5, .96), fontsize=8)
    fig.suptitle('두 지점의 OLD→FIX 과정 성분 · 고정 모형 층별 시간합', y=.995, fontsize=14)
    fig.text(.5, .012,
             '각 선은 실제 호출 180회의 OLD/FIX 차이를 모형 층 k별로 시간합한 값입니다.\n'
             '호출 내 순서(loop=1): 침강(9/10) → 지표 누적(13/14) → 주 업데이트(5–8) → 후속 미세물리 조정\n'
             '→ 응결(11/12) → 임계값·입자수 정리와 조건부 입도분포 재구성 → wrapper 반환.\n'
             '호출 내부 L은 전체 상태 변화입니다. 단계 8-6·침강/응결·잔여선은 L의 분해이므로 L에 더하지 않습니다.\n'
             '호출 사이 E는 반환과 다음 진입 사이의 순변화이며 순수 이류가 아닙니다. 조건부 침강 null은 0이 아닌 공백입니다.\n'
             '두 지점은 사례 예시입니다. 수직합, 전 물수지, 강수 인과분율을 주장하지 않습니다.',
             ha='center', va='bottom', fontsize=8, wrap=False)
    fig.subplots_adjust(left=.09, right=.98, bottom=.22, top=.84, hspace=.34, wspace=.22)
    fig.savefig(path, bbox_inches='tight', metadata={'Software': 'CP02 protected-process native plotter'})
    plt.close(fig)


def run(ledger_path: Path = DEFAULT_LEDGER, summary_receipt_path: Path = DEFAULT_SUMMARY_RECEIPT,
        output: Path = DEFAULT_OUTPUT) -> dict:
    output = Path(output)
    if os.path.lexists(output):
        raise FileExistsError(output)
    profiles, inputs = load_profiles(ledger_path, summary_receipt_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.native-figure-stage-', dir=output.parent))
    try:
        image_name = 'two_point_process_components.png'
        make_figure(profiles, stage / image_name)
        metadata = {
            'schema': 'cp02_protected_process_native_figure_v1', 'status': 'PASS',
            'inputs': inputs,
            'font_sha256': sha256(FONT),
            'points': {point_id: {'lead_hour': spec['lead_hour'], 'actual_steps': spec['steps'], 'role': spec['role']}
                       for point_id, spec in POINT_SPECS.items()},
            'fields': {'QR': 'mg kg-1 (1e6 scaling from kg kg-1)',
                       'QV': 'mg kg-1 (1e6 scaling from kg kg-1)', 'TK': 'K'},
            'components': {'internal_L': 'delta_call_internal_sum',
                           'between_call_E': 'delta_between_call_sum; not pure transport',
                           'phase8_minus_phase6': 'main within-call state update sum',
                           'sedimentation_or_condensation': 'field-specific captured substep',
                           'remaining_internal': 'remaining_call_internal_sum'},
            'interpretation_limits': [
                'Each profile is summed over actual hourly calls at fixed native k; there is no vertical sum.',
                'Within a captured one-loop call, source order is sedimentation, surface accumulator, main phase 5–8 update, later microphysical adjustments, phase 11–12 condensation, threshold/number cleanup, optional PSD reconstruction, then wrapper return.',
                'Internal L is the total internal-call change; other internal components are its breakdown and must not be added to L.',
                'Between-call E is net change between call return and following entry; it is not pure advection.',
                'Missing conditional sedimentation stays null and plots as a gap, not zero.',
                'Two selected points illustrate the frozen roles and do not represent all 150 cohort points.',
                'No column/domain water conservation or causal precipitation fraction is claimed.',
            ],
            'outputs': {image_name: sha256(stage / image_name)},
        }
        (stage / 'metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False,
                                                          sort_keys=True) + '\n', encoding='utf-8')
        receipt = {'schema': 'cp02_protected_process_native_figure_receipt_v1', 'status': 'PASS',
                   'renderer_sha256': sha256(Path(__file__)),
                   'metadata_sha256': sha256(stage / 'metadata.json'),
                   'figures': metadata['outputs']}
        (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        os.rename(stage, output)
        return receipt
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, default=DEFAULT_LEDGER)
    parser.add_argument('--summary-receipt', type=Path, default=DEFAULT_SUMMARY_RECEIPT)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(run(args.ledger, args.summary_receipt, args.output_dir), sort_keys=True))


if __name__ == '__main__':
    main()
