# Cloud-BAL 최종 목표와 단계별 체크포인트

기준일: 2026-09-07. 추가 입력: 사용자가 제공한 「Cloud-BAL 최종 목표 설계와 개발 로드맵」 본문.
검토 source HEAD: `f837bad0bdf1050a34975d93b178b7dee4420094`.
Tree: `2f70cce203d9822b4df9e5c9c28690385846fa11`.
이 문서는 개발 목표·증거 계획이다. 구현 완료, 실행 승인, 운영 승격 기록이 아니다.
사용자 링크의 `/mnt/data` Markdown/XLSX는 현재 환경에서 읽을 수 없어 본문과 저장소 자료만 대조했다.

- 단계별 편집 원장: [CLOUD_BAL_CHECKPOINTS_20260907.tsv](CLOUD_BAL_CHECKPOINTS_20260907.tsv)
- 기능별 편집 원장: [CLOUD_BAL_REQUIREMENTS_20260907.tsv](CLOUD_BAL_REQUIREMENTS_20260907.tsv)
- 상세 요구사항: [CLOUD_BAL_CHECKLIST_20260907.md](CLOUD_BAL_CHECKLIST_20260907.md)
- 이전 소스 대조: [CLOUD_BAL_DESIGN_REVIEW_20260907.md](CLOUD_BAL_DESIGN_REVIEW_20260907.md)
- 승인 권위: [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), 실행 정책: [NO_GO_CLOSURE_CHECKLIST.md](NO_GO_CLOSURE_CHECKLIST.md)

## 1. 최종 목표 — 한 사례의 성공과 프로젝트 완료를 구분

**최종 목표:** 같은 직접 입력에서 구름·레이더 수상체, T/qv, 건조공기 질량·압력·지위고도,
바람을 등압면에서 일관되게 분석하고 WPS → real을 통해 모델면에서 초기화하며, 독립 사건의 관측 적합성과 초기 파동·광역
바람 안전성 및 실행 재현성을 입증한 KLAPS 초기화 후보를 독립 승격 심사에 제공한다.

사용자가 확정한 처리 순서는 **등압면 분석 → WPS → real 모델면 초기화**다.
분석에 쓰는 변수는 등압면에서 제공해야 하며, 모델면 초기화에서 나중에 채운다고 가정하지 않는다.
Native 계약은 전달·초기화 검증의 기준이지 분석 격자를 모델면으로 옮기는 지시가 아니다.
미확정 native 출처는 관련 통합 인증을 막지만 독립적인 등압면 물리 구현을 일괄 중단시키지 않는다.
합의된 격리 구현·시험·KG 갱신은 사용자의 자율 진행 승인에 따라 반복 승인 없이 수행한다.
운영 원본 변경과 ACTIVE/과학 승격은 이 자동 승인에 포함하지 않는다.

| 목표 ID | 도달점 | 완료를 입증할 결과 | 이것만으로 주장할 수 없는 것 |
|---|---|---|---|
| FG1 | 한 사례 통합 실증 (CP06) | 동일 pre-QBAL 배경의 OFF와 비영 coupled 후보가 실제 모델 초기장까지 전달되고 최종 배열을 독립 재계산 | 여러 사건의 일반성, 과학 성능 개선, 운영 승인 |
| FG2 | 과학적으로 검증된 초기화 (CP07+CP08) | 고정 회귀 범위·독립 사건·ablation에서 물리/관측/파동 조건 및 사전 정의한 개선·비열등 기준 충족 | 장애복구·운영 예산·승격 승인 |
| FG3 | 최종 인수·독립 승격 심사 (CP09) | 45개 필수 요구사항의 증거 폐합, exact-release 재현, SLO/복구와 독립 승인 기록 | 문서만으로 ACTIVE 생성 또는 운영 파일 변경 |

FG1의 비영 후보는 수상체·열역학·바람 연결이 실제로 실행된 사례여야 한다. 관측 권한 없는
no-op이나 제조해만으로 달성하지 않는다. 다만 관측 없는 경우의 정확한 no-op은 별도 필수 안전시험이다.
FG2에서는 안전성만 확인한 후보를 “개선 성공”으로 부르지 않는다. 주 효과 지표와 최소 개선량을
사전에 정하고, 나머지 핵심 지표의 비열등 조건과 함께 판정한다. 개선 증거가 불충분하면 보류한다.
FG1은 운영·과학 승격 권한이 없는 연구 통합 결과다. 승인된 실험 target 사용과 과학 성능
인증을 구분하고 artifact에는 미평가 과학/승격 상태를 명시한다.
FG3 이후 실제 ACTIVE 경로는 별도 설계·변경·승인 업무다. 현재 OFF/SHADOW 경계는 그대로다.

## 2. 추가 검토에서 보완한 의사결정

| 보완 | 적용 원칙 | 연결 |
|---|---|---|
| 단일 사례를 최종 완료로 오인 | FG1은 통합 milestone, FG2는 과학 검증, FG3는 인수·승격 심사로 분리 | CP06–09 |
| native 대상이 아직 추상적 | host 모델/버전·grid·좌표·microphysics·초기화 executable·경계 forcing을 먼저 pin; WPS까지만 연결한 것을 native 완료로 부르지 않음 | CP01/02 |
| 중간 단계가 서로의 전체 완료를 요구 | 계약/부분 시험 증거를 넘기는 작업 DAG와 45개 요구사항의 최종 폐합 DAG를 분리 | §3/§6 |
| 병렬화가 승인 우회로 해석될 위험 | 격리 연구 제안과 통합·게시·승격 권한을 분리; 기존 GREEN/RED 시작·종료 정책 변경은 별도 승인 | CP00/06/09 |
| 예보 검증 긴급도 불일치 | 추가 본문 표의 P1 묶음은 일정 순서로 해석; 정본 V03/V04의 P0를 낮추지 않음 | CP08 |
| threshold 없이 “허용 범위”만 존재 | tolerance/효과·비열등 margin/시간 sampling/자원 예산의 버전·근거·승인자를 결과 열람 전에 고정 | §5 |
| OFF no-op과 파일 bitwise 요구 혼용 | 같은 pipeline의 OFF 대조로 비교; 입력/운영 원본은 불변, 변환 배열은 승인된 왕복 허용오차, 비결정적 header는 명시 목록만 제외 | CP02/07 |
| solver·낙하속도 명칭으로 구현 오인 | 현행 CR와 제안 PCG, 질량가중 `vt_z_mean` proxy와 Doppler Vt_Z를 구분 | CP03/05 |

기존에 고친 OM 독립 domain, pressure interface/cell_dp 분리, no-echo 목적지 전달과
제조해/diagnostic patch 권한을 다시 미구현으로 돌리지 않는다. 새 체크포인트는 최종 연결과
증거를 추가하는 것이며, 이전 8/29/6/2 구현 분류나 X01 완료 상태를 바꾸지 않는다.

WRF 문서는 face에 놓인 바람과 mass point의 다른 변수를 구분하고 dry-pressure 좌표를 정의한다.
따라서 host adapter와 최종 handoff를 고정하는 것이 중요하다. 이는 프로젝트 설계상 적용이며,
그 문서가 Cloud-BAL의 metric이나 보존을 인증한 것은 아니다.
[WRF 공식 Dynamics 문서](https://github.com/wrf-model/Users_Guide/blob/main/dynamics.rst)

## 3. 실행 순서 — 10개 체크포인트

CP는 이 문서의 개발 체크포인트 ID다. 기존 P1–P8 단계, 긴급도 P0/P1/P2, solver iteration이나
모델 restart 파일과 다르다. 아래 화살표는 승인된 격리 개발에서 필요한 **최소 증거 전달 관계**다.
어느 화살표도 현행 RELEASE/NO-GO 승인 선행조건을 제거하지 않는다.
2026-09-07 순서 조정: 등압면 결합 구현을 주 경로로 둔다. CP 번호는 식별자이지
착수 순서가 아니며, CP06-A/B는 기존 CP06의 하위 종료점이다. 상위 CP 10개는 유지한다.

```text
CP00 범위·기준선·승인계획
  └─ CP01 등압면 분석–WPS–real 질량·격자·관측 계약
       ├─ 분석 계약 → CP04 열역학 + CP03 balance + CP05 관측/수송
       │                    ↓ 필요한 등압면 범위 증거
       │              CP06-A 등압면 결합 한 사례 검증
       └─ CP02 입력/출력 계약·작은 OFF 시험은 조기 병행
                            ↓ A 이후 전체 후단 검증 확대
                      CP02 upstream / full ifx / OFF 왕복 / 게시
                            ↓ A + CP02 + 통합 선행 증거
                      CP06-B WPS → metgrid → real full SHADOW [FG1]
                    ↓
              CP07 전체 기능·native 회귀 재검증
                    ↓
              CP08 독립 사건 0–6 h 과학·파동 [FG2]
                    ↓
              CP09 운영 예산·복구·독립 인수 [FG3]
```

CP00부터 가벼운 CI를 구축하고, 해당 기능이 생기는 CP02/03/04/05/07에서 required check를
확장한다. CP09까지 CI를 미루지 않는다. 과학 사건·hold-out·sampling 계획도 CP00부터 준비한다.
실제 O06 관측 계보 검증 전에는 V01의 누수 차단 완료를 선언하지 않는다.
CP02 전체 완료는 CP06-A의 선행조건이 아니다. 반대로 CP06-A의 성공만으로 CP02나
CP06-B를 통과시키지 않는다. 등압면 분석에 필요한 직접 입력 확보는 미루지 않으며,
입력 부족 시 관련 upstream 재생성은 분석 선행 작업으로 수행한다.

### CP00 — 범위·증거 기준선과 승인 계획

담당: primary 연구 책임, cp00_ci QA·CI, cp00_green/cp00_red 독립 AI 연구 검토.
현재 CP00는 격리 연구 범위 COMPLETE/PASS이며 [실행·검토 기록](CP00_EXECUTION_RECORD_20260907.md)을 따른다.
진입: 기존 승인 문서와 고정 HEAD를 읽고, 현재 blocker를 포함한 작업 범위를 작성.
주 연결: G01/G02/G03/G04/G05/E07/V01. 최종 요구사항 전체 폐합을 뜻하지 않는다.

- [x] FG1/FG2/FG3와 HYDRO/THERMO/DYNAMIC의 역할·비목표·허용 산출물을 구분한다.
- [x] source/tree, dirty diff, input/config/compiler/dependency, 기대 사례와 기존 시험의 SHA를 구분한 기준선을 저장한다.
- [x] 운영 원본 read-only·OFF/SHADOW 격리, 제조해/진단 patch 승격 거부를 exact-build 회귀 항목에 넣는다.
- [x] P1 비교 13/14/15 UTC와 raw/upstream/manufactured 12–15 UTC를 별도 manifest로 고정한다.
- [x] 가벼운 계약 CI와 후속 ifx/native/science required-check 확장 계획, reviewer/승인 주체를 기록한다.
- [x] 수치 tolerance·hold-out·주 효과/비열등 margin·고주파 sampling·SLO의 확정 시점과 책임자를 정한다.
- [x] 병렬 연구 범위와 legacy 단계 선행조건을 대조하고 필요한 계획 변경을 실제 권한자가 승인한다.

완료 산출물: 범위·권한 표, baseline receipt, 시험/임계값 계획, CI 및 승인 기록.
실패 시: 권한 미확정/출처 없는 과거 PASS/축소된 시험 범위이면 실행 진입 보류. 문서 초안은 보존한다.

### CP01 — 등압면 분석–WPS–real 질량·격자·frame 계약

진입: CP00의 범위·계약 작성 권한과 기준선. 주 연결: M01–M07.
담당 역할: native adapter / 질량·격자 담당.

격리 구현에는 사용할 등압면 변수·질량분모·상별 enthalpy·EOS/geometry·frame·경계의
명시 계약과 관련 시험 증거가 먼저 필요하다. 이 범위가 확정되면 후단 binary 출처나
전체 native 왕복의 미폐합만으로 CP03/04/05 연구를 일괄 중단하지 않는다.
분석에서 쓰는 계약 자체가 미확정이면 해당 결합은 시작하지 않는다. CP01 전체 종료에는
아래 host/adapter 항목도 필요하며 부분 계약을 CP01 전체 PASS로 기록하지 않는다.

- [x] host 모델 버전, 미세물리 종 목록·분모, grid staggering, top/bottom, 초기화·예보 binary와 좌표 옵션을 pin한다.
- [x] canonical/WPS/native 변수 매핑, dry mass, pressure/EOS, A_Q/A_M/A_E 정의와 단위를 문서화한다.
- [x] pressure-fixed diagnostic과 native-dry-mass 보존 경로를 분리하고 optional species coverage를 명시한다.
- [x] cell_dp·center spacing·인접 partial-face 교집합·thin cell·PSFC 지표 절단을 독립 column oracle로 검사한다.
- [x] earth/grid frame, 회전/map factor, w–omega 근사, top/bottom 경계와 valid time 계약을 명시한다. native mu-coupled eta-dot(`ww`)를 pressure omega와 구별하고, WPS 입력 유무와 `real` 이후 연속방정식 재구성의 검증 위치를 CP06-B에 연결한다.
- [x] known moist column, 비대칭 impulse, 경사 지표, 결측 OM/domain 및 잘못된 단위의 양성·음성 시험을 정의하고 작은 계약 시험을 실행한다.

완료 산출물: adapter 변수·질량·geometry 계약과 해석 oracle/계약 시험 receipt.
이 단계는 전체 native writer나 M04/M05 최종 보존을 인증하지 않는다. 실제 왕복은 CP02/07,
state-dependent 재구성은 CP06/07에서 확인한다.
실패 시: 분모·좌표·종 coverage가 모호하면 후보 경로 통합 금지; 계약을 수정하고 후속 관련 시험 무효화.

### CP02 — 실행·통합 기반: upstream → full ifx → OFF·결합 후보 native 왕복

진입: CP00 승인 범위 + CP01 adapter 계약. 주 연결: E01/E02/E03/E05/E06.
담당 역할: KLAPS 실행망·빌드 / native I/O / 게시 담당.

조기 범위는 필수 입력 확보, 변수·단위·질량분모·시각·mask 계약, 작은 OFF 읽기/쓰기와
빌드 준비다. 전체 metgrid/real 검증 확대는 CP06-A 이후에 배치한다. 초기 시험은
후단 실패를 일찍 찾는 목적이며 등압면 결합 완료나 CP02 전체 PASS를 대신하지 않는다.
이 CP의 실행·writer·게시 실패주입과 `current` 전환 시험은 소유한 scratch 세대 안에서만
수행하며 운영 경로를 변경하지 않는다. CP02 PASS는 P2/P6의 정식 종료가 아니고,
정식 full-KLAPS 통합·게시에는 기존 RELEASE/NO-GO 선행조건을 별도로 만족해야 한다.

- [ ] isolated 입력 tree에서 원래 producer로 LT1/LQ3/LCO/LSX를 만들고 cycle·완료순서·exit·freshness·coverage를 검증한다.
- [ ] pinned ifx/NetCDF/HDF5로 out-of-source full link, symbol·ABI·runtime audit와 source/binary receipt를 확보한다.
- [ ] 같은 입력·모델 설정의 baseline과 Cloud-BAL OFF를 실제 후속 초기화까지 실행한다. OFF가 후보 계산을 하지 않음을 확인한다.
- [ ] canonical → WPS → 실제 후속 변환 → native 초기장의 모든 필수 변수·mask·frame·질량기준을 재읽어 비교한다.
- [ ] 실행 초기에 선택 filesystem의 no-replace/CAS/fsync 능력을 검사하고, 미지원이면 게시를 거부한다. overwrite fallback은 금지한다.
- [ ] producer 종료 → snapshot 재검증 → seal → 고유 generation → current 전환의 실패주입과 재시도 증거를 만든다.

진행 갱신 (2026-09-14): **CP02 IN_PROGRESS / E03 OPEN**. 위 여섯 요구사항은 유지한다.
항목별 근거 (로컬 작업공간 근거: `../scratch/cp02_requirement_matrix_20260911/CP02_REQUIREMENT_MATRIX.md`)에 따라
#1·2·3·5·6은 기록된 소스·설정·격리 실행 범위에서 `PROVEN-SCOPED`, #4는 `INCOMPLETE`다.
이는 공식 체크박스나 전체 gate의 PASS 승격이 아니다. 관련 소스·입력·설정 변경 또는
새 실패가 해당 근거를 무효화할 때만 그 범위를 재검증한다.

기존 관측·처리자료는 확보되어 입력으로 사용 중이다. 추가로
12/15 UTC OFF native 준비 (로컬 작업공간 근거: `../scratch/cp02_native_12_15.B4Lwmh/RUN_REPORT.md`)는
metgrid/real 종료 0, 12 UTC 초기장과 12→15 UTC 경계자료 생성을 기록한다.
이는 물리 omega 구현이나 실제 결합 후보 전달의 완료 근거가 아니다.

남은 작업 순서와 책임 범위:

추가 과제 (2026-09-14): [다중 레이더 연직풍·국지 균형초기화 계획](CP02_MULTI_RADAR_BALANCED_INITIALIZATION_PLAN_20260914.md).
시선속도가 이미 반영된 Barnes 수평풍을 기준으로 남은 연직 관측 제약을 평가하고,
수상체와 주변 전이 영역에서 최소 보정으로 전체 상태의 질량·역학 정합성을 맞춘다.
관측 중복 사용, 입자 낙하속도, 레이더 기하의 비식별성을 먼저 검토한다.
적분 전 W 소비 확인과 이후 초기 충격 검증을 분리하며, 질량 진단만으로 균형초기화
완료를 선언하지 않는다. 단계 R0–R6의 산출물·통과 조건은 추가 계획서에 따른다.
기존 CP02 여섯 요구사항과 CP06 의존관계는 유지한다.
추가 과학 검토를 반영하여 Barnes 이후 조건부 연직 정보, 공통 낙하속도 오차,
연결 성분별 질량 호환성, 상변화 후 native 열역학·역학 정합성 및 음향/중력파
구분 검증을 R1–R5에 명시했다. 물리적 잠열 응답·대류·냉기류·지형성 파동을 보존하며
불일치로 생긴 과도한 초기 조정을 줄인다. 이 계획 갱신은 구현·충격 억제 PASS가 아니다.
추가 과제의 실행 상태는 [MR-C0–MR-C6 체크리스트](CP02_MULTI_RADAR_INITIALIZATION_CHECKLIST_20260914.md)에서
입력 연결→연직 정보→결합 방정식/상변화·파동→t0 전달→초기 충격→강수 효과 순으로 추적한다.

현재 단계의 OMEGA는 시간 적분하는 예측변수가 아니라, 같은 분석 시각의 질량 연속성을
만족하도록 내부에서 진단적으로 할당하는 변수다. 기존 Barnes 분석 바람과 현재
압력·질량기준·geometry를 사용하며, 이산 질량수지와 경계 질량유량의 정합성을 검증한다.
외부 omega target, 모델 궤적 생성, 새 ACTIVE 되먹임이나 모델 시간 적분을 이번 단계의
선행조건으로 두지 않는다. 모델 시간 적분 및 그에 따른 물리 되먹임은 다음 단계에서
고려한다. 진단 연산자의 수치적 반복과 물리 시간 적분은 구분한다.


후속 모델 적분의 1차 검증 기준은 기존 ODAM **RN1**(1시간 누적 격자 지상강수)과
**PTY**(지상 강수형태)다. 같은 시간 구간의 모델 누적 강수 및 정의를 맞춘 강수형태와
비교한다. 변수 확보 현황과 격자·파일 계약은 [ODAM 기준자료](CP02_ODAM_PRECIPITATION_REFERENCE_20260914.md)에
기록한다. 통합파일 pc/spt/ptt나 순간 진단 강수율·층간 수송 ledger로 대체하지 않는다.
이 후속 검증을 위해 현재 진단 초기화 단계에 모델 시간 적분을 추가하지 않는다.
질량수지와 물·열역학 보존은 별도로 충족해야 한다.

omega는 직접 관측 검증 대상이 아니라 강수 과정에 영향을 주는 역학적 진단량이다.
직접 omega 관측을 선행조건으로 요구하지 않고, 질량·경계 정합성과 초기 수상체 구조,
1시간 예측의 동일 시각 분석장 및 RN1/PTY 오차를 통해 간접 평가한다.
[정밀 팀 검토와 13 UTC 분석장 비교](CP02_PRECISION_REVIEW_20260914.md)에 현재 증거와
증분 균형·상태 전체 질량 균형의 차이를 기록한다.

1. 물리 연산자 담당: 기존 다변량 Barnes 바람과 구름·수상체·열역학 입력을 사용하여
   cloud omega 경험함수를 대체할 질량 연속성 기반 진단 방정식·경계조건·보존 조건과
   구현을 확정한다.
   외부 모델 실행이나 외부에서 생산한 omega target에 의존하지 않고 Cloud-BAL 내부에서
   산정한다. 외부 WRF 궤적은 비교·진단 자료로만 남기며, 그 reader/producer를 Fortran으로
   옮기는 작업은 이 의존성 제거의 구현으로 취급하지 않는다. 내부 산정량을 관측 target으로
   표시하지 않으며, 출처·유효성 계약을 연결한다.
2. 등압면 결합 담당: CP03/04/05의 필요한 등압면 근거를 갖춰 CP06-A의 동일 배경
   OFF/수상체·열역학/물리 결합 후보를 검증한다. CP06-A는 CP02 전체 완료를 요구하지 않는다.
3. native I/O 담당: 필수 수분·T·바람·geometry·mask·시각·질량기준의 전달 경로와
   사전 허용오차, pressure omega·geometric W·native WW의 변환/초기화 책임을 고정한다.
   CP06-A에서 검증한 실제 후보를 WPS→metgrid→real로 전달하고 전체 필수 배열을 재읽어 #4를 검증한다.
4. 통합/검토 담당: 동일 입력·소스·설정·후보에 결속된 근거를 CP06-B에서 재사용한다.
   CP06-B 자체의 후단 통합·초기 시간전진 조건은 별도로 확인한다.

KDM6 수정과 제조한 W의 20초 실행은 필요한 입력/초기화 진단 범위로 제한한다.
20초 예보 성공을 CP02의 새 종료조건으로 추가하지 않는다. 기존 native 시간적분 실험은
비교·진단 기록으로 보존하며, 추가 모델 시간 적분은 다음 단계로 미룬다.
기본 등압면 분석→WPS→real 경로는 유지한다.
실제 사용할 Fortran 구현과 필요한 검증을 우선하며 감사 코드는 배포 대상에 포함하지 않는다.

완료 산출물: 동일 입력 OFF 및 실제 결합 후보의 native state와 전체 필수 변수 재읽기,
full build/runtime·upstream receipts, 게시 protocol 시험.
작은 읽기/쓰기 시험만으로 이 단계 PASS가 되지 않는다. FG1에서는 이 경로를 그대로 재사용한다.
실패 시: 원본/current 보존, failed staging은 진단용 격리. 전체 산출물·게시 완료로 표시하지 않는다.

### CP03 — 등압면 국지 balance와 후단 정합성

진입: CP01의 고정 geometry/frame/boundary 계약. 주 연결: B01/B02/B03/B04/B06.
담당 역할: 수치 연산자 / 독립 reference 담당.

- [ ] 등압면 face DOF 또는 검증 가능한 collocated coupling을 선택하고 해당 격자 solve/update/최종 저장 residual의 C·metric을 통일한다.
- [ ] adjoint dot, symmetry/energy, rank·gauge·component compatibility, support 밖 identity와 zero-normal increment를 검사한다.
- [ ] feasible δ*와 λ*로 만든 q를 independent sparse reference와 비교하고 위치 이동·thin cell·격자 세분화를 시험한다.
- [ ] 기존 6/16 adverse-response 사례를 고정한다. target 위치·50% 실패 허용·1% 반응 기준을 성과에 맞춰 바꾸지 않는다.
- [ ] 현행 weighted CR을 기준으로 기록한다. PCG/전처리는 해당 공간의 SPD와 정확도 유지가 입증될 때만 후보로 비교한다.
- [ ] 등압면 face→저장 재구성의 residual과 iteration/memory/wall 분포를 검사한다. WPS→real 변환 뒤에는 native 좌표·metric의 연산자로 별도 재계산한다.

완료 산출물: 해석해·독립 reference·metric/target-response 검증. 여기의 비영 제조해는 과학 권한 NONE이다.
이 등압면 범위 증거는 CP06-A의 입력이다. 좌표 변환 전후에 같은 행렬을 요구하거나
projection이 자동 보존된다고 가정하지 않는다. B01의 최종 native 정합성과 B06의
전체 결합 oracle은 CP06-B/07에서 재검증하며 CP03 단독 PASS로 폐합하지 않는다.
실패 시: non-convergence/부적합 RHS/parity/저장 후 잔차 실패면 후보 거부; full-domain fallback 금지.

### CP04 — 종별 수분·엔탈피 block

진입: CP01 질량·종별 enthalpy 계약. 주 연결: T01/T03; T04/T05 결합 준비.
담당 역할: 미세물리·열역학 / 독립 cell oracle 담당.

- [ ] condensation/evaporation/sublimation/melting/freezing의 종별 Δr·ΔT·Δh와 latent heat convention을 고정한다.
- [ ] 총수분과 선택한 enthalpy를 함께 보존하는 bounded cell/block solve를 독립 transaction으로 검사한다.
- [ ] 이를 명시된 등압면 후보장 경로에 연결하고 종별 Δr·ΔT·budget과 실패 시 전체 상태 rollback을 검사한다. 독립 함수 시험과 실제 경로 연결 증거를 구분한다.
- [ ] 분석증분 A_Q/A_E와 내부 phase transfer를 분리하고 positivity·포화 극한·실패 시 전체 rollback을 검증한다.
- [ ] reduced moist enthalpy와 native total energy 진단을 구분한다. pressure work·sedimentation·경계 에너지의 포함 범위를 표시한다.
- [ ] 강한 moisture increment, 작은/큰 증발, 온도의존 계수와 iteration cap 도달을 독립 oracle로 시험한다.

완료 산출물: 작은 thermo block 및 analytic/adversarial receipts. 관측을 대신한 명시 시험 A_Q는
허용되지만 이는 T01의 실제 retrieval lineage 폐합이 아니다. O03/T01 실제 연결과
thermo 이후 EOS/geometry·balance 재평가는 CP05/CP06-A에서 필요하다. 기존 standalone
함수의 PASS만으로 이 연결이나 KDM6 열역학 호환을 완료 처리하지 않는다.
실패 시: native 물·얼음 포화/혼합상 정책 위반, 수치적 overshoot·중복 상변화·음수 종·budget 실패/상한 도달을 숨기는 clip 성공 처리 금지; 원본 복귀. 물리적으로 허용되는 얼음 과포화·과냉각 액체수는 보존한다.

### CP05 — 실제 관측·동역학 target·수송 의미

진입: CP01의 frame·시간·질량 계약. 주 연결: O01–O08/T02/V02.
담당 역할: 구름·레이더 / 바람 관측 adapter / 수송 담당.

- [ ] 실제 cloud fraction/base/top/type/T/qv와 H_Z·parameterization ID·R_Z를 연결한다.
- [ ] ECHO/BELOW_DETECTION/MISSING/QC_REJECTED와 검출한계를 분리한다. no-echo 목적지 차단을 증발·지표 sink로 세지 않는다.
- [ ] Barnes 완료 receipt를 참조해 frame·beam·dealias/Nyquist 필요조건·관측 ID·time·오차와 중복 관측을 검증한다. Barnes 재개발이 아니다.
- [ ] O06의 레이더별 입력 연결을 O05의 완성된 target보다 먼저 진행한다. 직접 w 관측이나 외부 모델 target을 필수 입력으로 요구하지 않는다.
- [ ] 관측·물리 결합으로 추정하는 격자평균 연직풍의 식별가능성·오차·physical boundary를 검증한다. 관측 제약/물리·배경 의존/미해결을 구분하며, type/dBZ-only 및 기존 무권한 입력의 wind innovation 0·rollback은 유지한다.
- [ ] Vt_mass와 Vt_Z를 분리하거나 근사/PSD/오차를 선언하고, suspension/상승·양의 deposition·boundary exit·terrain intercept를 실행한다.
- [ ] earth-fixed 시간수송과 storm-relative reconstruction 중 모형을 선택한다. 실제 시간수송은 source 제거·sink·boundary kg budget, 재구성은 A_Q 장부로 검사한다.
- [ ] 관측 계약/단위/종별 ledger를 CP04와 상호 점검한다. Poor geometry·held-out ID 중복·결측 sigma는 거부한다.

완료 산출물: 관측 contract receipt, 관측·물리 결합으로 승인 조건을 검사한 실제 초기 연직풍 후보, 실행 범위에 맞는 재구성/시간수송/기존 수상체 장부 검사. 비영 값 자체는 승인 근거가 아니다.
CP05의 단독 수송 fixture는 T01/T02의 전체 결합 보존이나 V02의 사건 검증을 닫지 않는다.
실패 시: 정보 없는 no-op과 잘못된 필수 입력 거부를 구분; 제조해로 실제 target을 대체하지 않는다.

### CP06 — 한 사례 coupled full SHADOW (FG1)

진입은 아래 A/B로 나눈다. CP06 전체 PASS와 FG1은 B까지 통과해야 한다.
주 연결: T04/T05/B05/E04/E08 및 앞 단계의 모든 물리/입출력 계약.
담당 역할: 통합 담당 / 독립 verifier / 단계 승인자.

#### CP06-A — 등압면 결합 한 사례 검증

진입: CP00 격리 범위, CP01의 필요한 분석 계약, CP03/04/05의 해당 등압면 범위 증거.
CP02 전체 완료나 native 왕복은 요구하지 않는다. 실제 관측 기반 후보를 검사하며,
제조해는 별도 시험 경로에만 남긴다. 하위 상태는 현재 `PLANNED / NOT_RUN`이다.
실행 전에 사례·입력·허용 변수/support·관측 target 권한·threshold가 정해진 격리 실험
승인 근거를 A receipt에 연결한다. 이번 순서 변경 GO만으로 미확정 실제 target이나
범위를 승인한 것으로 간주하지 않는다. 승인 범위가 없으면 그 실자료 결합 실행은 보류한다.
새 다중 레이더 경로를 사용하는 후보는 MR-C0–MR-C3의 계약·증거를 A receipt에 연결한다.
격리된 native 전달·소비 시험은 MR-C4에서 수행하며, 그 통과 증거가 있는 후보를
MR-C5 초기 충격 검증으로 넘긴다. 기존 등압면 연구 범위와 소규모 진단은 유지한다.

- [ ] 사전 지정한 동일 pre-QBAL x_b에서 OFF, hydro+thermo, 실제 dynamic-coupled 후보를 각각 만든다.
- [ ] proposal → thermo → EOS/geometry → balance → 전체 제약의 bounded outer loop를 연결한다.
- [ ] 명시된 필요 영역 외 자동 재균형을 금지한다. thermo/dynamic support와 validation shell을 미리 고정하고 state-dependent forcing compatibility를 재평가한다.
- [ ] 필수 등압면 변수·단위·질량분모·시각·QC를 확인하고 A_Q/A_E/A_M과 내부 상변화·수송 budget을 분리한다. pressure-fixed 진단을 dry-mass 보존으로 표시하지 않는다.
- [ ] 최종 저장 등압면 후보에서 positivity·water/선택 enthalpy·EOS/질량 정합성·support 밖 불변·target fit·잔차를 독립 재계산한다. cap 도달·필수 결측·budget 실패는 전체 rollback한다.
- [ ] 선택한 trajectory 모형의 이동거리·도착 분포·관측 충돌·경계 유출을 독립 검증한다. frozen-source 층 내 직선 근사는 source별 연속 이동으로 과소 이동을 수정하고 균일풍·동일종 교차·소단계 크기 불변·부분 유출 수치시험을 추가했다. 이 범위의 통과를 실제 frame/shear/상변화 경로 전체의 과학적 폐합으로 간주하지 않는다.
- [ ] 동일 배경 OFF 대비 수상체·T/qv·바람 증분과 관측 provenance를 고정한다. 무관측 wind innovation 0은 필수 음성시험이며 실제 비영 동역학 결합 성공을 대체하지 않는다.

완료 산출물: 검증된 등압면 후보와 입력/설정/연산자/독립 verifier receipt.
이는 `FULL_SHADOW_PRODUCT`, FG1, native/과학 승인 증거가 아니다. 수상체·열역학만
연결된 중간 결과는 그 범위로만 기록하며 CP06-A 전체 완료로 표시하지 않는다.

#### CP06-B — 후단 통합 검증과 FG1

진입: CP06-A PASS + CP02 완료 + 필요한 CP01/03/04/05 통합 계약 및 현행
RELEASE/NO-GO 통합·게시 선행조건. 하위 상태는 현재 `PLANNED / NOT_RUN`이다.

- [ ] A에서 검증한 동일 등압면 후보를 WPS → metgrid → real로 전달한다. 기존 LAPS 출력이나 일부 QV 기록만을 결합 후보로 대체하지 않는다.
- [ ] QV/SH/RH 우선순위·단위·시각·mask·변환을 확인한다. 분석 w/omega의 전달/초기화 정책과 KDM6 수농도·체적 변수의 초기화 책임을 명시하고, 분석에 필요한 값을 real의 사후 보충으로 대신하지 않는다.
- [ ] 실제 derived→QBAL→LAPSPREP 호출망에서 중복 latent adjustment·legacy 광역 balance/bogus-w 재진입이 없음을 trace한다.
- [ ] 수상체/T/qv/질량·압력·지위고도/바람 전체 후보를 native 초기장까지 기록하고 독립 verifier가 게시할 최종 배열·budget·operator residual을 재계산한다.
- [ ] qC−qB와 qB−qO를 분리하고 FULL_SHADOW_PRODUCT lineage를 결속한다. 부분 patch는 이 산출물이 아니다.
- [ ] 초기 시간전진 smoke를 수행하되 “한 사례 실행 가능” 범위로만 기록한다. FG2의 0–6 h 과학 통과로 집계하지 않는다.

완료 산출물: 같은 배경의 완전한 OFF/후보 native generation과 독립 검증·초기 실행 receipt.
비영 target이 실제 적용되고 필요 block이 실행되었다는 증거가 있어야 한다. 무권한 no-op은 FG1 대체 불가.
실패 시: generation/current 승격 금지, candidate 거부. 마지막 통과한 독립 block과 입력 receipt로 돌아간다.

### CP07 — 전체 기능·최종 native 회귀

진입: CP06-A/B 모두를 포함한 CP06 전체 PASS. 주 연결: G03/M01–M07/B01/B06/E03/E04 및 O/T 기능 전반.
담당 역할: 통합 QA / 독립 수치·물리 검증자.

- [ ] 고정 12–15 UTC raw/upstream/manufactured와 13–15 UTC archived 비교 범위를 각각 검증한다. FG1 한 사례로 축소하지 않는다.
- [ ] wet/dry/mixed phase, terrain/partial-face, no-observation·missing 필수 필드, poor geometry·강한 상승류의 기능 회귀를 완료한다.
- [ ] 최종 float32 native 배열에서 residual·budget·mask·frame·time을 재계산하고 float64 계산오차와 저장 양자화를 구분한다.
- [ ] 작은 독립 sparse/column oracle과 mutation test로 공용 helper의 잘못된 부호·단위·metric을 검출한다.
- [ ] OFF 운영 원본 불변, failure/timeout/IO 오류의 rollback, 중복 보정 차단을 실제 경로에서 재검사한다.
- [ ] 재구성/물리수송 선택, 적용된 관측 권한과 모든 요구사항의 남은 증거 공백을 목록화한다.

완료 산출물: 고정 범위 회귀 matrix, native replay/oracle, unresolved-requirement inventory.
적용하지 않은 경로를 “시험 통과”로 집계하지 않는다. 과학 필수 항목이 남아 있어도
그 사실을 명시한 기술 회귀 범위만 종료할 수 있으며 최종 요구사항 전체 PASS는 아니다.
실패 시: 관계 있는 CP01–06 증거를 무효화하고 회귀 재실행; 허용 사례/시각을 줄여 통과시키지 않는다.

### CP08 — 독립 사건 0–6 h와 파동 안전성 (FG2)

진입: CP07 전체 PASS + O06 관측 계보와 V01 hold-out 검증 + 시험 전 승인한 threshold/평가 계획.
주 연결: V01/V02/V03/V04, B05/E08. 담당 역할: 과학 평가 / 독립 통계·관측 검증자.
새 다중 레이더 후보의 추가 증거 순서는 MR-C4 실제 native 게시·소비, MR-C5 초기 충격,
MR-C6 1–6시간 강수 검증이다. 이는 기존 45개 분모·상태·선행 DAG를 변경하지 않는다.

- [ ] 연속 네 시각을 독립 네 사건으로 세지 않고 사건별 split·hold-out 관측 ID·regime coverage를 고정한다.
- [ ] 같은 model/physics/forcing의 OFF·가능한 legacy·hydro/thermo·full 후보를 paired 비교한다. Legacy 불가 시 원인과 대조군 공백을 명시하고 승인받는다.
- [ ] 강수 FSS/CSI/POD/FAR/bias, wind-vector/T/qv/PSFC, cloud base/top, cold pool·수분/에너지 예산을 평가한다.
- [ ] 검증하려는 주파수 대역에 맞는 초기 sampling(필요 시 acoustic substep 진단)으로 pressure tendency/divergence와 10/30/60분 checkpoint 및 전체 0–6 h를 함께 검사한다. 출력 간격만으로 고주파 안전을 주장하지 않는다.
- [ ] 주 효과의 사전 정의한 개선 기준 + 핵심 안전 지표 비열등 + regime별 critical-failure 부재를 확인한다. 불충분한 사건 수나 신뢰구간은 보류한다.
- [ ] 관측 독립성·누수·event-level 불확실성을 검토하고 worst-regime 실패를 전체 평균으로 상쇄하지 않는다.

완료 산출물: frozen event/observation manifest, paired forecast generations, 독립 science/wave 검토.
DFI/IAU를 필요 시 별도 ablation으로 두되 baseline/candidate 기본 설정을 몰래 바꾸지 않는다.
DFI의 고주파 감소와 첫 시간 parameterized convection 약화는 보고되어 있으나, 프로젝트에 대한
효과는 직접 검증해야 한다. [Peckham et al. (2016), NOAA 원자료](https://repository.library.noaa.gov/view/noaa/16494)
실패 시: FG2 보류, 개발/calibration으로 복귀. Hold-out을 본 뒤 tuning하면 별도 미사용 평가 세트를 요구한다.

### CP09 — 운영 준비·독립 최종 인수 (FG3)

진입: CP08 전체 PASS + 최종 release identity로 재검증된 선행 receipts. 주 연결: G02/G05/E05/E06/V05/V06, 본체 45개 전부.
담당 역할: 운영 담당 / GREEN 재현성 검토 / RED 적대 검토 / 별도 승격 승인자.

- [ ] source SHA/tree, compiler/deps, inputs/config/thresholds, writer/verifier/output을 하나의 immutable release evidence로 연결한다.
- [ ] 모든 필수 check와 main 보호·검증자 분리를 실제로 확인한다. 과거 green SHA 또는 main에 문서가 있다는 사실로 대체하지 않는다.
- [ ] cycle latency/memory p95, input freshness, rejection rate, dense-support·연속 cycle·자료 지연·IO 장애의 사전 승인 SLO를 검사한다.
- [ ] 게시 경쟁/실패 재시도/원본 선택/last approved generation으로 복구를 격리 환경에서 시연한다. 초기조건 checkpoint 재사용은 §7의 identity 규칙을 따른다.
- [ ] 45개 본체 요구사항의 완료조건·적대시험·선행 ID·증거를 개별 검토한다. X01은 완료 유지하되 분모에서 제외하고 O06은 별도 확인한다.
- [ ] GREEN/RED 결과와 별도 승인 주체의 실제 결정을 기록한다. 미승인 또는 단 하나의 필수 FAIL/NOT_RUN이면 최종 인수 보류다.

완료 산출물: 운영 준비 보고, 복구 drill, 45개 폐합 matrix와 독립 최종 결정 기록.
최종 판단의 권위는 RELEASE_CHECKLIST와 승인 주체다. CP09 상태만으로 ACTIVE API나 운영 설정을 만들지 않는다.

## 4. 추적 원칙 — 단계 종료 ≠ 기능 전체 폐합

단계 TSV의 `requirement_ids`는 해당 단계가 **기여·재검증하는 요구사항**이다. 같은 ID가
여러 단계에 나타나는 것은 의도적이다. CP01의 M04 계약 PASS가 CP02/07 native 왕복을 생략하게
하거나 CP03의 B06 수치 oracle이 CP04 thermo oracle을 대체하게 하지 않는다.

원장의 선행 ID는 그대로 유지한다. 특히 다음은 작업 병렬화를 위한 scoped evidence와 구분한다.

- T01은 M05/O03, T03은 T01/M05를 요구한다. CP04 단독 합성 A_Q 시험은 실제 O03 연결의 대체가 아니다.
- T04는 T03/O05, T05는 M05/T03/B01을 요구하므로 전체 결합 폐합은 CP06 이후다.
- B06은 B01/T03, E04는 E03/T05/B06, V01은 G04/O06을 요구한다. 그룹을 통째로 선행 단계로 바꿔 가짜 순환을 만들지 않는다.
- V03/V04는 P0 필수 과학 gate다. 후반 일정 또는 P1 개발 묶음이라는 이유로 완화하지 않는다.
- X01은 `EXTERNAL_COMPLETE` 유지. 별도 알고리즘 개발을 재개하지 않으며 완료가 O06을 자동 통과시키지도 않는다.

초기 계획의 10개 단계는 `PLANNED / NOT_RUN`이었다. 현재 상태는 §8과 단계 TSV를 따른다.
순서 조정으로 기존 분류·gate/closure를 승격하지 않는다. CP06-A/B의 receipt는 상위
CP06의 evidence에 함께 연결하고, A만 통과했으면 CP06 전체는 `IN_PROGRESS / NOT_RUN`이다.

## 5. 수치 기준을 결정하는 체크포인트

숫자는 현재 자료 없이 임의로 채우지 않는다. 아래 항목은 해당 시험 전에 versioned threshold
설정과 승인 기록으로 고정한다. `TBD`는 그 gate를 통과할 수 없다는 뜻이지 허용오차 무제한이 아니다.

| 기준군 | 최소 정의 | 확정 시점 |
|---|---|---|
| 질량·enthalpy·energy·EOS | 잔차 단위, 기준량, `abs_tol + rel_tol × physical_scale`, 종/경계 포함 범위 | CP01 계약, CP04/06 시험 전 |
| 연산자·제조해·target | dot/symmetry/residual norm, rank/gauge, independent-reference 오차, expected convergence order, target fit | CP03 결과 평가 전 |
| 국지성·원본 보호 | 운영 원본/허용 영역 밖 불변 조건; 양자화·변환이 있는 경우 대조 방식과 예외 필드 | CP00/01, CP02 실행 전 |
| 관측·trajectory | QC·time window·R/identifiability·detection·PSD·support 범위와 error budget | CP05 실제 사례 평가 전 |
| coupled 수렴 | 모든 block 잔차·변화량·positivity·outer cap·damping·최종 gate | CP06 실행 전 |
| 과학·고주파 | primary effect, improvement/noninferiority margins, 사건 수·uncertainty method, cutoff/normalizer·sampling | CP00 설계 착수, CP08 hold-out 실행 전 |
| 운영 예산 | cycle deadline, latency/memory p95, freshness/rejection 예산, 복구 시간과 반복 수 | CP00 초안, CP09 평가 전 |

검증 코드는 `없음/NaN/음수 tolerance/unknown policy`를 정상 값으로 처리하지 않아야 한다.
고정된 양수 비영 시험은 최소 경로 실행 여부를 보이지만 관측/과학 개선 기준을 대신하지 않는다.

## 6. 증거와 판정의 최소 기록

새로운 publisher/framework를 먼저 만들라는 요구가 아니다. 기존 generation schema/validator에
필요 필드를 매핑하고 없는 항목만 명시적으로 확장한다. 아래는 계획상 receipt 계약이며 구현된
파일 형식이나 자동 검증 도구가 있다는 뜻은 아니다.

```text
checkpoint_id + scope/authority + prerequisite_receipt_ids
source_SHA/tree + dirty_diff_status + binary/compiler/dependency hashes
input_snapshot_manifest + case_ids/cycles/valid_times + observation lineage
config/threshold/host_model/writer/verifier versions and hashes
result/output hashes + numerical/science failure reasons
producer completion + independent review + approval/reuse decision
```

Gate는 `NOT_RUN / FAIL / PASS`, 작업 상태는 `PLANNED / IN_PROGRESS / BLOCKED / COMPLETE`로
분리한다. 작업 착수는 IN_PROGRESS일 뿐 PASS가 아니다. FAIL이면 BLOCKED, 오류 없이 아직 안 돌렸으면
NOT_RUN이다. PASS는 해당 범위의 실제 증거와 독립 검토를 확인한 뒤에만 기록한다.
전체 프로젝트 COMPLETE는 기능 45개 AND와 FG3의 독립 승인까지 필요하다.

TSV는 수동 편집 원장이다. SHA·URI 문자열 입력으로 자동 PASS/closure가 계산되지 않는다.
실제 담당자·시험 SHA·evidence URI·reviewer·승인은 처음에는 비워 두며 역할을 배정 완료로 오인하지 않는다.
`entry_checkpoint_ids`는 선행 증거의 출처다. CP01–CP06-A의 격리 연구 착수는 필요한
계약/부분 증거로 가능하지만, CP06-B와 CP07–09는 명시된 전체 PASS 조건을 충족해야 한다.
정확한 범위는 각 단계의 진입 문구로 고정한다. CP06 행의
진입 ID는 A 기준이고 B의 CP02 등 추가 조건은 `exit_criteria`에 기록한다.
이는 45개 요구사항 원장의 최종 `prerequisite_ids` 또는 기존 승격 gate를 완화하지 않는다.
CP06 하위 receipt는 `checkpoint_id=CP06`, `subcheckpoint_id=CP06-A` 또는 `CP06-B`와
각각의 `work_state`, `gate_result`, 입력/출력 hash, 독립 검토, 실험 승인 근거를 명시한다.
B는 통과한 A receipt의 URI/hash를 선행 증거로 참조한다. A/B를 구분할 수 없거나
승인·hash가 누락/변경된 기록은 B의 진입 증거로 사용하지 않는다. 상위 TSV의
`evidence_uri`는 두 receipt를 나열한 기록을 가리키며 부분 PASS를 전체 PASS로 복사하지 않는다.
이는 기존 최소 receipt를 구체화한 계획이며 새 runtime schema나 자동 승인 구현은 아니다.

TSV 단독 사용 시에도 범위가 사라지지 않도록 `checkpoint_scope`, `canonical_gate_effect`,
`science_authority`, `promotion_eligible`, `publication_scope`를 기록한다. 이들은 개발 계획용
필드이지 현재 실행 artifact schema에 새 enum/권한을 구현한 것이 아니다. 초기값은 모든 단계에서
`NO_AUTOMATIC_CHANGE / NONE / false / NO_OPERATIONAL_PUBLICATION`이다. CP06은
`REAL_OBSERVATION_RESEARCH` 범위지만 실험 승인 기록 없이는 실행할 수 없고 과학 승격 권한은 없다.
CP08 과학 평가나 CP09 인수의 PASS도 이 값을 자동으로 변경하지 않는다. 운영 권한은 별도 승인 체계가 결정한다.

## 7. 체크포인트 재개·증거 무효화

재개점은 마지막 로그 줄이나 `PASS` 텍스트가 아니라 **검증된 immutable receipt 집합**이다.

1. 같은 checkpoint/scope, input/cycle, code/config/deps/threshold/host/writer/verifier identity를 확인한다.
2. 하나라도 달라지면 영향받는 요구사항과 downstream 체크포인트를 NOT_RUN 또는 재검토 대상으로 돌린다.
   이전 receipt는 삭제하지 않고 `superseded/reuse_pending` 같은 명시 기록으로 보존한다.
3. 변경 없는 독립 block만 기존 정책이 허용하는 dependency-equivalence와 승인 기록으로 재사용한다.
   문서 변경도 자동으로 전체 과거 PASS를 최신 SHA PASS로 복사하지 않는다.
4. Crash 후 부분 파일·retained writer·unsealed generation은 완료 checkpoint가 아니다.
   verifier 실패/current 충돌이면 원본 또는 마지막 승인 generation을 유지한다.
5. 재실행에는 새 attempt/generation identity와 parent receipt를 붙인다. 예보 restart 시험은
   복구 능력 증거이며 V03의 clean cold-start 과학 사례를 대신하지 않는다.
6. Threshold·모델물리·관측 ID·질량분모가 바뀌면 그에 의존하는 science 결과도 재평가한다.
   Hold-out 재튜닝은 독립 검증 세트를 새로 분리해야 한다.

## 8. 지금 시작할 묶음과 현재 판정

다음 구현은 등압면 질량·enthalpy 계약의 미확정 부분을 닫고 기존 열역학 block을 후보장에
연결하는 작업이다. CP03 수치 검증과 CP05 관측/수송 계약은 독립 범위에서 병행한다.
CP02는 필요한 입력 확보와 작은 전달 계약 시험에 한정해 조기 병행하고, 전체 후단
검증 확대는 CP06-A 이후로 둔다. 새 문서·guard보다 물리 구현과 해당 시험을 우선한다.
담당자·일정·수치 임계값은 승인/자료 없이 추정해 고정하지 않았다.

초기 계획 작성 때는 10개 체크포인트 모두 PLANNED / NOT_RUN이었다. 이후 CP00는
독립 AI GREEN/RED 검토를 거쳐 **COMPLETE / PASS (격리 연구 범위)**로 종료했다.
CP01은 **COMPLETE / PASS (격리 연구 계약·소규모 시험 범위)**로 종료했다.
[종료 매트릭스](CP01_CONTRACT_EXIT_MATRIX_20260909.md)와
[완료 감사](CP01_COMPLETION_AUDIT_20260909.md)에 여섯 조건의 red/green 검토와 증거를 결합했다.
실제 13 UTC native 입력은 계속 NO_AUTHORITY이며, native 실행 승인이나 NAS 게시 준비 완료가 아니다.
이는 CP03/04/02 전체 종료가 아니며 나머지 8개 상위 단계는 `PLANNED / NOT_RUN`이다.
[CP00 실행 기록](CP00_EXECUTION_RECORD_20260907.md)에 portable CI 구현과 pinned ifx 로컬 unit suite
통과를 기록했다. 이는 dirty worktree의 제한된 실행 증거이며 clean release·native E2E·예보 검증이 아니다.
이번 순서 조정은 사용자의 GO에 따른 격리 연구 계획 변경이다. 운영 설정·ACTIVE 권한과
기존 RELEASE/NO-GO의 통합·게시·과학 승격 종료조건은 변경하지 않았다.
다음 통합 목표는 FG1, 최종 개발 인수 목표는 FG3이며 현재 PROMOTION_BLOCKED를 해제하지 않는다.

## 9. 10단계 완료 후 별도 조사 — LAPSPREP와 최신 WRF

사용자 지시(2026-09-08)에 따라 **DEFERRED / NOT_RUN**으로 등록한다.
착수 조건은 기존 CP00–CP09의 완료이며, 현재 10단계 구현을 대체하거나 확장하지 않는다.

조사 착수 시점의 최신 WRF/WPS 버전과 공식 문서를 고정하고, 기존 LAPSPREP와의
변수·단위·수분/질량 기준, 바람 좌표계, 연직 보간, intermediate 입력 및 real 초기화,
KDM6 호환성과 빌드 인터페이스 차이를 조사한다. 근거가 있는 개선 항목과 우선순위를
별도 결과로 정리하며, 현재 단계에서 최신 버전 호환성을 확인했다고 간주하지 않는다.
코드 현대화·운영 전환은 이 조사와 구분하며 기존 체크포인트 번호와 승격 조건은 유지한다.

## 2026-09-15 검토 연결

PR #5 병합 `ba45e8f` 기준의 추가 검토를 [다중 레이더 계획](CP02_MULTI_RADAR_BALANCED_INITIALIZATION_PLAN_20260914.md)과 [MR 체크리스트](CP02_MULTI_RADAR_INITIALIZATION_CHECKLIST_20260914.md)에 반영했다. B06의 legacy nonlin 부호·섭동 수정은 한 묶음이며, E03/M06/M07의 native 기준 상태·geometry·지원 영역·재시도·전체 하부 W 경계 검사는 MR-C4 승인 전에 필요하다. 작은 수치시험·consumer 시험·native startup 검증을 구분하고 기존 부품 구현을 전체 결합 완료로 집계하지 않는다. 이번 반영은 계획 수정이며 CP02 또는 MR-C4/C5의 PASS가 아니다.
