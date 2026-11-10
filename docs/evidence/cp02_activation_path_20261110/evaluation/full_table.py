#!/usr/bin/env python3
"""Publish all six-case categorical and continuous scores from sealed CSV."""
import csv
import json
from pathlib import Path
import evaluate as e

here=Path(__file__).resolve().parent
results=here/'results'; receipt=json.loads((results/'receipt.json').read_text())
for name in ('categorical_scores.csv','continuous_scores.csv'):
    if e.identity(results/name)['sha256'] != receipt['outputs'][name]: raise ValueError('score CSV changed')
def read(name):
    with (results/name).open(newline='') as f:return list(csv.DictReader(f))
labels=dict(zip(e.CASES,('규준실험','B1','PR153','PR154','MP10','MP10 NN_END')))
cat=read('categorical_scores.csv');cont=read('continuous_scores.csv')
if len(cat)!=216 or len(cont)!=36:raise ValueError('incomplete table')
lines=['# 여섯 실험 시간별 강수 검증','','고정 RN1 짝 3,688개. 각 임계값과 시간을 독립적으로 평가.','','| 예보시간 | 임계값 mm | 실험 | 적중 | 놓침 | 허위경보 | CSI |','|---:|---:|---|---:|---:|---:|---:|']
lines += [f"| {r['lead_hour']} | {float(r['threshold_mm']):g} | {labels[r['case']]} | {r['hit']} | {r['miss']} | {r['false_alarm']} | {float(r['CSI']):.6f} |" for r in cat]
lines += ['','| 예보시간 | 실험 | MAE mm | RMSE mm |','|---:|---|---:|---:|']
lines += [f"| {r['lead_hour']} | {labels[r['case']]} | {float(r['MAE_mm']):.6f} | {float(r['RMSE_mm']):.6f} |" for r in cont]
(here/'FULL_SCORES.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
