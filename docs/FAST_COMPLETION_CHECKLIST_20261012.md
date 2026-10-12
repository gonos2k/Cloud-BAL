# Cloud-BAL 우선 실행 체크리스트

기준: PR77 main `a444a788e8e7301354bec14c3708aacddb8f31d3`.
이 목록은 작업 순서를 정한다. 기존 물리·승격 종료 조건을 대체하지 않는다.
상태는 아래 결과 파일로 갱신하며, 시험 수나 완료 항목 비율을 완성도로 사용하지 않는다.

## 고정된 진행 순서

```text
A: 실제 입력의 등압면 공간 producer ─────────────┐
B: 올바른 빌드의 통제된 native 기준 실행 ───────┤
                                               ↓
C: 완료된 공동 Q/N/B/T 갱신과 같은 후보의 수지·전달
                                               ↓
D: BASE/HYDRO/COUPLED 첫 호출·10/30/60분 반응
```

CP02 전체 완료는 A의 선행조건이 아니다. 분석 → WPS → real 순서를 유지한다.
관측 omega가 없으면 그 관측 분기는 사용할 수 없다. 기존 분석 바람과 명시한
질량경향·경계로 omega를 진단하는 경로는 별도로 검토한다. 계산한 omega를
관측 target으로 표시하거나 기존 경험함수를 새 물리식으로 표시하지 않는다.

## 완료로 유지하는 기반

- [x] 외부 추정 endpoint의 공통 pipeline 평가 진입점 — PR77의 제한적 완료.
- [x] 연구 KDM6 `.f90` 전처리 누락 수정 — 실제 `-fpp` 규약을 유지.
- [x] 실제 최초 ice orphan의 종·값·비트·호출 위치 확인 — 거부 결과는 유지.
- [x] 기존 소형 추정기/KKT·회계·입력 보존·rollback 회귀 기반 유지.

이 네 항목은 공간 producer, 물리적 수용 또는 native 성공을 뜻하지 않는다.

## 남은 네 묶음과 종료 조건

| 순서 | 산출물 | 종료 조건 | 현재 승인 상태 |
|---|---|---|---|
| A, 주 작업 | 실제 관측·배경에서 만든 비영 공간 후보 | 원본 전체 격자·연직·지형 유지, 조정영역과 stencil/shared-face 평가영역 고정, 같은 기하의 수상체·열역학·질량–바람 평가 및 저장 readback | OPEN |
| B, A와 병행 | 통제된 native 기준선 | 전처리 결과·macro·객체·archive·실행파일 연결, 같은 빌드/예외 mask의 FP 정책 대조, 별도 trap 진단의 정확한 식·피연산자, 우선 1 rank·1 thread | OPEN |
| C | 공동 모멘트 갱신·수지·전달 | 같은 carrier·물리시각·경계의 Q/N/B/T 갱신이 다음 과정 정의역을 만족, 분석·상변화·외부 source·경계 항 분리, WPS/real 실제 소비값의 의미·보존량 대응 | OPEN |
| D | 같은 후보의 초기 시간반응 | 동일 설정 BASE/HYDRO/COUPLED, 첫 호출과 10/30/60분, 압력·발산·연직운동·열역학·수상체·강수 및 독립 관측 평가 | NOT_RUN |

물리 시간의 질량식은 `dM_d/dt + B F_d = S_d`다. 최적화 반복간격을
물리 시간으로 사용하지 않으며 endpoint 잔차를 source에 복사하지 않는다.
정상 종료, producer 생성, 공간 균형, native 수용, 과학적 효과를 별도로 판정한다.

## 이번 작업 결과 연결

실제 13 UTC VXX에 유효 LOS 72,150셀이 있지만 Nyquist는 모두 결측이고 beam
vector 배열은 없다. 위치·격자·고도로 H를 계산할 자료는 있으며 그 파생값의
생성과 검증이 남아 있다. 기존 `WEIGHT_RADAR=0.25`의 2 m/s는 선언된 LOS
오차 가정이다. Barnes `WEIGHT_BKG_CONST_WIND=5e28`은 독립 B 공분산이 아니다.
기존 omega target/sigma는 모두 유효 0셀이고 COM은 경험식 근거다.
따라서 이 자료를 독립 H/B/R 공동 추정이 준비된 것으로 표시하지 않는다.
기존 분석 바람에서의 내부 연속식 진단은 별도 연구 경로로 진행한다.

| 이번 산출물 | 결과 | 근거 |
|---|---|---|
| 공통 면 기하의 내부 stationary omega producer | 위·아래 경계와 수평 분석 바람을 고정하고 dry-air flux 연속식을 진단. 호환성 실패 시 평균 제거 없이 전체 rollback. 공동 수상체·열역학 추정기의 완료가 아님 | [구현](../src/common/cloud_bal_balance_operator.f90), [실행·시험 기록](evidence/cp06a-stationary-20261012/README.md) |
| 실제 13 UTC 공간 진단 | 전체 235×283×22 유지, 사전 고정 8×8 기주 영역의 1,280 유효 셀. O0/O2 모두 `REJECTED`: 최초 실패 기주의 경계 불일치 약 134,682.1284 kg/s. 변경 0셀, artifact 없음, 저장 잔차는 미평가 | [보존된 실제 실행](evidence/cp06a-stationary-20261012/) |
| 분석 알고리즘과 기존 회귀 | 공간 비영 진단·변경영역·전체 rollback의 새 분석적 시험 O0/O2 통과. 기존 balance·partial-face·pipeline·prebalance 네 프로그램도 O0/O2 통과 | [새 시험](../tests/test_stationary_omega_diagnosis.f90), [최종 기존 회귀](evidence/cp06a-regression-20261012/receipt.json) |
| 동일 실행파일 FP 정책 대조 | 1 rank·1 thread, 예외 mask 고정, FTZ/DAZ만 변경. 두 arm 모두 같은 Noah `DIVPS`에서 중단. 사용하지 않는 상위 lane의 0/0을 operand·instruction으로 식별 | [통제된 startup 근거](evidence/native-controlled-20261012/receipt.json) |
| 별도 Noah 빌드 진단 | 두 Noah 객체의 strict O0·`-no-vec` 재빌드에서 Noah 통과. 이 효과를 `-no-vec` 단독 인과로 주장하지 않음. 이후 KDM6 `radar_init`의 `1/xam_g`에서 실제 0 분모로 중단 | [별도 빌드·피연산자 근거](evidence/native-controlled-20261012/scalar_noah/README.md) |

Native의 적격 대조는 두 쌍, 네 startup 실행이다. 준비·재생·중간 probe를 포함한
전체 10 WRF 시작은 [별도 실행 원장](evidence/native-controlled-20261012/execution_counts.json)에
구분했다. 시간 적분은 수행하지 않았다. 현재 수상체 입장 거부를 없애지 않았다.

## 결과에 따른 다음 결정

- A: 실제 고정 바람·복사된 omega 경계와 정지 dry-mass 가정은 이번 영역에서
  양립하지 않는다. 물리적 질량경향, 경계 prior와 허용 바람 조정을 같은 계약으로
  결정한 뒤 공간 공동 추정기로 이어간다. 실패 기주 잔차를 source에 복사하지 않는다.
- B: Noah 식·피연산자 식별은 완료로 유지한다. 새로운 반복 관측보다 사용한
  전체 native 빌드 규약을 고정하고, KDM6 radar의 graupel 계수 초기화 계약을
  확인한다. `xam_g`는 임의 상수로 보충하지 않는다.
- C/D: 유효한 비영 공동 후보가 아직 없으므로 공동 수지·WPS/real 전달·첫 호출·
  초기 시간반응은 계속 OPEN/NOT_RUN이다. A를 B의 전체 완료에 종속시키지 않는다.

## 판정 범위

한 사례의 native 연결과 초기 반응은 FG1이다. 독립 사례군의 과학적 효과는
FG2이며 운영 승격은 FG3다. 현재 두 native 거부 기록을 새 정상 종료 기록으로
덮어쓰지 않는다. cell별 N 삭제, 작은 Q 생성, 임의 floor/clamp로 수용하지 않는다.

정본 연결: [최종 목표와 체크포인트](CLOUD_BAL_FINAL_GOALS_CHECKPOINTS_20260907.md),
[같은 후보의 상세 실행 계약](JOINT_CANDIDATE_EXECUTION_CHECKLIST_20260928.md),
[분석시각 omega 방향](CP02_PRECISION_REVIEW_20260914.md).
