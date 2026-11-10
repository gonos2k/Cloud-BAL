#!/usr/bin/env python3
"""Draw the initialization contract and an analytical liquid-rain PSD family."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import matplotlib
matplotlib.use('Agg')
from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FONT = Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def render(output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    font_manager.fontManager.addfont(FONT)
    plt.rcParams.update({'font.family': 'NanumGothic', 'axes.unicode_minus': False})
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.moment-figures-', dir=output.parent))
    try:
        fig, ax = plt.subplots(figsize=(12, 8), constrained_layout=True)
        ax.set(xlim=(0, 10), ylim=(0, 10)); ax.axis('off')
        boxes = [(8.8, '관측 · 배경 · 명시적 사전정보', '#e2edf7'),
                 (7.0, '물·열 분석과 보존적 상변화\n분석 증분과 내부 상변화 분리', '#e2f3ea'),
                 (5.2, '최종 모형 격자의 물·열 상태\nQC · QI · QR · QS · QG · QV · T · P', '#e2f3ea'),
                 (3.4, '필요 모멘트 완성\n유효 관측 → 유효 배경 → 명시적 PSD 사전정보\nNC · NI · NR · NN · BG와 출처', '#f9efd9'),
                 (1.3, '모형의 초기 처리 → 첫 이류 → 첫 미세물리\n파일 상태와 실제 첫 사용의 동일성은 별도 검증', '#f8e5e3')]
        for y, text, color in boxes:
            ax.text(5, y, text, ha='center', va='center', fontsize=14,
                    bbox={'boxstyle': 'round,pad=0.7', 'facecolor': color, 'edgecolor': '#526476'})
        for top, bottom in zip(boxes, boxes[1:]):
            ax.annotate('', xy=(5, bottom[0]+.6), xytext=(5, top[0]-.6),
                        arrowprops={'arrowstyle': '->', 'linewidth': 1.7,
                                    'linestyle': '--' if bottom is boxes[-1] else '-'})
        ax.set_title('초기화에서 함께 보존할 물리 의미와 실제 사용 경계', fontsize=18)
        fig.savefig(stage/'01_initialization_path.png', dpi=160); plt.close(fig)

        # KDM6 rain: mur=1, C=4000*pi, Dm=5/lambda. This is a family of
        # analytically admissible PSDs, not an inferred or optimal rain size.
        diameter = np.linspace(.2, 2., 181)
        slope = 5. / (diameter * 1.e-3)
        rain = 1.e-4
        density = 1.
        number = rain * slope**3 / (4000.*np.pi)
        rayleigh = 1.e18 * density * number * 5040. / slope**6
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
        axes[0].plot(diameter, number, color='#235b85'); axes[0].set_yscale('log')
        axes[0].set_ylabel('입자수 혼합비 N (1/kg dry air)')
        axes[1].plot(diameter, 10.*np.log10(rayleigh), color='#a74624')
        axes[1].set_ylabel('액체 물 Rayleigh 등가 반사도 (dBZ)')
        for panel in axes:
            panel.set_xlabel('질량가중 평균입경 Dm (mm)'); panel.grid(alpha=.25)
        fig.suptitle('같은 비 질량만으로 입경·입자수·반사도가 정해지지 않음\n'
                     '이론 예시: q=0.1 g/kg dry air, 밀도=1 kg/m³, 감마 형상 μ=1', fontsize=13)
        fig.savefig(stage/'02_rain_psd_freedom.png', dpi=160); plt.close(fig)
        with (stage/'rain_psd_family.csv').open('w', newline='') as stream:
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerow(['Dm_mm', 'lambda_m-1', 'number_kg-1', 'rayleigh_mm6_m-3', 'dBZ'])
            writer.writerows(zip(diameter, slope, number, rayleigh, 10.*np.log10(rayleigh)))
        pins = ['src/common/cloud_bal_state.f90',
                'src/common/cloud_bal_microphysics_initialization.f90',
                'docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90']
        receipt = {'status': 'PASS', 'inputs': {p: sha(ROOT/p) for p in pins},
                   'generator_sha256': sha(__file__), 'font_sha256': sha(FONT),
                   'scope': 'Architecture diagram and analytical liquid-rain PSD family; no observations or forecast scores.',
                   'q_r_kg_kg': rain, 'density_kg_m3': density, 'mur': 1,
                   'outputs': {p.name: sha(p) for p in sorted(stage.iterdir())}}
        (stage/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    render(parser.parse_args().output)
