# Cloud-BAL 시간별 강수 검증 진행 현황과 근거 부록

**보고서 부록 · 근거 기준일 2026-10-30**

이 부록은 이미 수행된 단일 사례 재예보와 그 검증의 진행 상황을 정리한다. 기준일은 작업 현황을 정리한 날짜이며, 모델 사례는 **2026-08-16 12 UTC 초기화, 12–18 UTC**다. 이 문서를 위해 새로운 예보 적분을 수행하지 않았다. 근거는 PR #132에서 고정한 로컬 자료를 사용한다.

## 1. 현재 진행 현황

| 구분 | 항목 | 현재 상태와 남은 범위 | 근거 |
|---|---|---|---|
| 완료 | 네 실험 6시간 적분 | ORIGINAL과 CURRENT_OFF, CURRENT_HYDRO, CURRENT_LIQUID가 18 UTC까지 완주했다. CURRENT 초기장은 현행 `a63a802` 소스로 생성했고, 네 실험에 같은 보관 CP02 WRF 실행파일을 사용했다. | [실행 계보](evidence/current_forecast_paper_20261029/runtime/README.md) |
| 완료 | 시간별 강수 검증 | 공통 3,688개 지리 평가점에서 +1~+6시간을 각각 평가했다. 범주 점수 144행, 연속 점수 24행, 대응 전이 180행을 산출하고 독립 검산했다. | [범주](evidence/current_forecast_paper_20261029/scores/categorical_scores.csv), [연속](evidence/current_forecast_paper_20261029/scores/continuous_scores.csv), [전이](evidence/current_forecast_paper_20261029/scores/transitions.csv), [검산](evidence/current_forecast_paper_20261029/validation/independent_scores.json) |
| 완료 | 회귀 확인 | 고정된 clean export의 집중 시험 35개가 통과했다. 이는 전체 모델의 물리 검증을 뜻하지 않는다. | [시험 결과](evidence/current_forecast_paper_20261029/validation/clean_tests.txt), [소스 동일성](evidence/current_forecast_paper_20261029/validation/clean_test_source_identity.json) |
| 제한 | 비교 기준과 성능 | 후보 결과는 시간·임계값·기준군에 따라 달라진다. ORIGINAL과 CURRENT_OFF의 초기장 준비 경로가 달라 그 차이를 한 물리 효과로 분리할 수 없다. | [초기장 비교](evidence/current_forecast_paper_20261029/initial_original_vs_current_off.json), [기존 보고서](CURRENT_FORECAST_CONFERENCE_PAPER_20261029.md) |
| 제한 | 보관 KDM6 진단 | 선택 표본의 호출 경계와 분기를 관찰했으나 배열의 물리적 의미, 0 입력의 생성 원인 및 지상 강수 변화와의 인과관계는 미확정이다. | [호출 진단](CP02_KDM6_CONTROLS_20261029.md), [분기 진단](CP02_ZERO_CANDIDATE_20261029.md) |
| 남음 | RN1 시간·관측 범위 | 상류 입력의 시간별 최신성과 coverage/QC, 공간 대표성을 확인해야 한다. 유한한 0을 관측 가능 영역의 확정적 무강수로 단정할 수 없다. | [RN1 범위](CP02_RN1_REPRESENTATIVENESS_20261027.md), [입력 확인](evidence/precip_hourly_20261027/rn1_recovery/source_findings.md) |
| 남음 | 최신 C2와 수지 | 최신 C2 T39, H/A/N 1시간 완료와 전 과정의 물·에너지 수지 및 강수 flux 검증은 별도로 남아 있다. 보관 사례의 6시간 완주로 대체할 수 없다. | [T39 범위](T39_C2_BUDGET_SCOPE_20261027.md), [물리 검증 범위](CURRENT_FORECAST_CONFERENCE_PAPER_20261029.md) |

## 2. 용어와 비교 기준

- **RN1 분석장**: 레이더·AWS와 추가 처리로 생성된 강수 참조 분석장이다. 원시 우량계 독립 관측으로 취급하지 않는다.
- **ORIGINAL**: 보관된 실제 OFF 초기장을 사용한 기준이다. 보관 WPS와 `real.exe`의 준비 경로를 포함한다.
- **CURRENT_OFF**: 현행 소스로 준비한 OFF 초기장이다. CURRENT 후보의 대응 대조군이다.
- **CURRENT_HYDRO**, **CURRENT_LIQUID**: 현행 소스로 준비한 두 후보 초기장이다. 각 모드의 초기장 작성 차이도 함께 포함한다.
- **1시간 누적강수량(mm)**: 모델의 `RAINC + RAINNC` 누적량을 인접 시각 사이에 차분한 값이다. RN1 분석장의 해당 시간과 같은 평가점에서 비교한다. 예측시간 +1~+6h의 유효구간은 아래 표와 같다.

ORIGINAL과 CURRENT_OFF는 WPS 레코드와 `real.exe` 등 준비 경로가 다르고 주요 초기장 값도 다르다. 따라서 ORIGINAL과의 차이는 전처리 변화가 섞인 비교다. CURRENT 후보와 CURRENT_OFF의 비교도 모드별 초기장 작성 차이를 포함한다. 같은 WRF 실행 조건만으로 개별 물리 과정의 효과가 분리되지는 않는다. [실험 정의와 한계](CURRENT_FORECAST_CONFERENCE_PAPER_20261029.md)

## 3. 시간별 강수 결과

표의 CSI는 1시간 누적강수량 **5 mm 이상**의 적중 H, 미탐지 M, 오경보 F를 이용한 `H/(H+M+F)`다. 각 행은 2026-08-16의 서로 다른 1시간 유효구간이며 6시간 누적 점수가 아니다.

| 예측시간 | 유효구간 UTC | ORIGINAL | CURRENT_OFF | CURRENT_HYDRO | CURRENT_LIQUID |
|---|---|---:|---:|---:|---:|
| +1h | 12–13 | 0.2751 | 0.1414 | 0.2140 | 0.2174 |
| +2h | 13–14 | 0.1815 | 0.1987 | 0.1796 | 0.1815 |
| +3h | 14–15 | 0.1622 | 0.1643 | 0.1618 | 0.1686 |
| +4h | 15–16 | 0.1148 | 0.0944 | 0.1199 | 0.1167 |
| +5h | 16–17 | 0.1831 | 0.0960 | 0.1652 | 0.1632 |
| +6h | 17–18 | 0.2623 | 0.2253 | 0.2786 | 0.2838 |

+1h에서 두 후보는 CURRENT_OFF보다 높지만 ORIGINAL보다 낮다. +2h에는 두 후보 모두 CURRENT_OFF보다 낮고, +6h에는 두 기준보다 높다. 기준과 시간에 따라 결과가 엇갈리며 이 한 사례는 일반적인 예측 성능 향상을 입증하지 않는다. 다른 문턱값, counts 및 추가 지표는 [전체 범주 점수](evidence/current_forecast_paper_20261029/scores/categorical_scores.csv)와 [연속 점수](evidence/current_forecast_paper_20261029/scores/continuous_scores.csv)에 있다.

