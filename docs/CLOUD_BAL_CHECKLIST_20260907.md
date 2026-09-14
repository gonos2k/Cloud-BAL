# Cloud-BAL 최종 요구사항 체크리스트

기준일: 2026-09-07 (KST)  
검토 저장소: `gonos2k/Cloud-BAL`  
기준 HEAD: `f837bad0bdf1050a34975d93b178b7dee4420094` (2026-09-07 원본 기준선)
최신 검토 기준: `main@816c03820a92571dd5eb2efac41b2bf010be7722`
기준 tree: `2f70cce203d9822b4df9e5c9c28690385846fa11`

이 문서는 [Cloud-BAL 설계 검토](./CLOUD_BAL_DESIGN_REVIEW_20260907.md)와 [단일 승인 체크리스트](./RELEASE_CHECKLIST.md)를 보조하는 사람이 읽는 체크리스트다. 편집 정본은 [CLOUD_BAL_REQUIREMENTS_20260907.tsv](./CLOUD_BAL_REQUIREMENTS_20260907.tsv) 하나이며, 이 문서와 TSV의 불일치는 TSV를 기준으로 정정한다.

## 사용 규칙

- 전체 범위는 필수 본체 45개(G01–V06)와 별도 완료 항목 X01 1개다. O06의 `O06.a`(입력 연결)와 `O06.b`(공동분석 수용)는 하나의 O06 아래 하위 판정이며 요구사항 분모를 늘리지 않는다.
- 현재 구현 분류는 본체 기준 `구현확인 8`, `부분구현 29`, `설계·계약 6`, `구현미확인 2`다. X01은 `외부완료` 1개이며 본체 필수 gate와 완료율 분모에서 제외한다.
- 모든 행은 실제 담당자를 배정하지 않고 역할만 `미배정 — ...`으로 표시한다.
- 본체 45행의 초기 운영 필드는 `gate_result=NOT_RUN`, `tested_sha` 빈 값, `evidence_uri` 빈 값, `reviewer` 빈 값, `closure=OPEN`이다. X01은 `NOT_APPLICABLE / EXTERNAL_COMPLETE`로 완료 보고를 보존한다. 문서·과거 기록·fixture의 존재는 exact HEAD 실행 또는 과학 검증 PASS를 뜻하지 않는다.
- 필수 gate는 평균점수로 상쇄하지 않는 논리 AND다. `MANUFACTURED_TEST`, 진단 patch, 외부 완료 보고를 운영 승격 또는 `ACTIVE`의 증거로 사용하지 않는다.
- `gate_result=PASS`는 시험 결과를 기록한 상태이고 `closure=CLOSED`는 별도 승인 상태다. PASS 기록만으로 폐합·운영 승격을 만들지 않는다.
- 선행 ID가 있어도 pressure-level field/mass/enthalpy/metric 계약과 명시된 scoped test는 전체 선행 gate PASS를 기다리지 않고 격리 수행할 수 있다. 다만 그 증거는 선행 closure·후속 통합·승격을 충족하지 않으며 최종 canonical AND는 그대로다.
- 9월 7일 원문 검토에는 XLSX 파일 자체가 없었다. 원장 규칙 보완을 Excel 직접 편집·재계산의 완료로 표시하지 않으며, workbook 검증은 별도 결과로 기록한다.

## 공통 증거 기준

| 필드 | 초기값/규칙 |
|---|---|
| `gate_result` | `NOT_RUN`; 시험이 실제로 해당 exact HEAD에서 완료되고 검토되기 전에는 바꾸지 않음 |
| `tested_sha` | 빈 값; exact HEAD 시험 때만 실행 SHA를 기록 |
| `evidence_uri` | 빈 값; 검증된 self-contained receipt URI만 기록 |
| `reviewer` | 빈 값; 독립 검토자 확인 전에는 기록하지 않음 |
| `closure` | `OPEN`; 모든 완료조건·적대시험·선행조건·증거가 폐합될 때만 변경 |
| PASS 기록 | exact test SHA와 증거 유형 검증이 끝난 경우에만 `gate_result=PASS`; 이 상태는 선행조건이나 범위 승인을 대신하지 않음 |
| 폐합 승인 | `closure=CLOSED`에는 비어 있지 않은 frozen required-ID set, 검증된 evidence type, trim 후에도 비어 있지 않은 self-contained `evidence_uri`, 폐합된 모든 predecessor, 사전 승인된 scope, `doc_sha`와 `tested_sha`의 결속, 독립 승인 기록이 모두 필요 |
| X01 | `NOT_APPLICABLE / EXTERNAL_COMPLETE`; 외부완료보고를 보존하며 Cloud-BAL 본체 gate/분모에 포함하지 않음 |

## 요구사항 색인

아래 색인은 TSV의 행을 빠르게 찾기 위한 것이다. 다음 절의 카드가 각 요구사항의 다음 작업·완료조건·적대시험을 완전하게 기록한다.

| ID | 분야 | 요구사항 | 긴급도 | 기존 단계 | 현재 구현 | 현재 증거 | 선행 ID | gate | closure |
|---|---|---|---|---|---|---|---|---|---|
| G01 | 목표·권한 | 최종 목표·비목표와 기능별 승인 범위 고정 | P0 | P1/P5 | 구현확인 | 소스검토 | — | NOT_RUN | OPEN |
| G02 | 목표·권한 | 최신 SHA·입력·도구·시험 증거 기준선 | P0 | P8 | 부분구현 | 소스검토 | — | NOT_RUN | OPEN |
| G03 | 목표·권한 | 운영 원본 불변 / OFF no-op / SHADOW 격리 | P0 | P1/P2 | 구현확인 | 소스검토 | G02 | NOT_RUN | OPEN |
| G04 | 목표·권한 | 시각 범위 및 12 UTC 제외의 명시성 | P0 | P1 | 구현확인 | 과거기록 | G02 | NOT_RUN | OPEN |
| G05 | 목표·권한 | 필수 CI·main 보호·검증자 분리 | P0 | P8 | 구현미확인 | 소스검토 | G02 | NOT_RUN | OPEN |
| M01 | 격자·질량 | 단일 value/valid/quality/source/time/unit 계약 | P0 | P5 | 구현확인 | 소스검토 | G02 | NOT_RUN | OPEN |
| M02 | 격자·질량 | OM 독립 도메인 및 지형·PSFC 정합성 | P0 | P5 | 구현확인 | 소스검토 | M01 | NOT_RUN | OPEN |
| M03 | 격자·질량 | pressure interface / cell_dp / center spacing 분리 | P0 | P5 | 구현확인 | 소스검토 | M02 | NOT_RUN | OPEN |
| M04 | 격자·질량 | canonical–WPS–native 질량분모 계약 | P0 | P3/P6 | 부분구현 | 소스검토 | M03 | NOT_RUN | OPEN |
| M05 | 격자·질량 | 수분 분석증분과 dry mass / PSFC 결합 | P0 | P3/P5 | 설계·계약 | 소스검토 | M04 | NOT_RUN | OPEN |
| M06 | 격자·질량 | 바람 frame·투영·metric·w↔omega 계약 | P0 | P5/P6 | 부분구현 | 소스검토 | M01 | NOT_RUN | OPEN |
| M07 | 격자·질량 | 물리적 top/bottom boundary와 관측시각 | P0 | P5 | 부분구현 | 과거기록 | M06 | NOT_RUN | OPEN |
| O01 | 구름·레이더 | 실제 cloud analysis ingest 및 수상체 정합성 | P1 | P5/P6 | 부분구현 | 소스검토 | M04 | NOT_RUN | OPEN |
| O02 | 구름·레이더 | 운형·dBZ-only 연직속도 금지 유지 | P0 | P5 | 구현확인 | 소스검토 | M01 | NOT_RUN | OPEN |
| O03 | 구름·레이더 | H_Z와 종별 retrieval 불확실도 | P1 | P3/P5 | 부분구현 | 소스검토 | M04,O01 | NOT_RUN | OPEN |
| O04 | 구름·레이더 | no-echo / missing / QC-reject 분리 | P1 | P5 | 부분구현 | 소스검토 | O03 | NOT_RUN | OPEN |
| O05 | 구름·레이더 | 내부 물리제약 dynamic target 추정 및 R_w/식별가능성 | P0 | P5 | 부분구현 | 소스검토 | M06,M07,O03 | NOT_RUN | OPEN |
| O06 | 구름·레이더 | 레이더별 LOS 입력 연결과 Cloud-BAL 공동분석 수용 (`O06.a`/`O06.b`) | P1 | P5/P6 | 부분구현 | 소스검토 | M01,M06 | NOT_RUN | OPEN |
| O07 | 구름·레이더 | 시간·storm-relative trajectory frame | P1 | P5 | 부분구현 | 소스검토 | M06 | NOT_RUN | OPEN |
| O08 | 구름·레이더 | 낙하속도의 mass-weighted / Z-weighted 분리 | P1 | P5 | 부분구현 | 소스검토 | O03,M01,M06 | NOT_RUN | OPEN |
| T01 | 수분·열역학 | 수분 분석증분과 물리 수송 ledger 분리 | P0 | P3/P5 | 부분구현 | 소스검토 | M05,O03 | NOT_RUN | OPEN |
| T02 | 수분·열역학 | 범위별 source-to-sink 종별 보존 수송 | P1 | P3/P5 | 부분구현 | 소스검토 | T01,O07,O08 | NOT_RUN | OPEN |
| T03 | 수분·열역학 | 증발·승화·융해와 T/qv 동시 조정 | P0 | P5 | 부분구현 | 소스검토 | T01,M05 | NOT_RUN | OPEN |
| T04 | 수분·열역학 | loading·잠열·압력섭동의 일관된 부력 | P1 | P5 | 부분구현 | 소스검토 | T03,O05 | NOT_RUN | OPEN |
| T05 | 수분·열역학 | state-dependent geometry·thermo outer coupling | P0 | P5/P6 | 설계·계약 | 소스검토 | M05,T03,B01 | NOT_RUN | OPEN |
| B01 | 국지 balance | 등압면 연산자와 모델면 변환 후 정합성 | P0 | P5/P6 | 부분구현 | 소스검토 | M03,M06,M07 | NOT_RUN | OPEN |
| B02 | 국지 balance | A-grid parity·target sign 왜곡 폐합 | P0 | P5 | 부분구현 | 과거기록 | B01 | NOT_RUN | OPEN |
| B03 | 국지 balance | 국지 support·질량 compatibility·배경 보존 | P0 | P5 | 부분구현 | 소스검토 | B01 | NOT_RUN | OPEN |
| B04 | 국지 balance | PCG preconditioner·conditioning·성능 | P1 | P5 | 부분구현 | 과거기록 | B02,B03 | NOT_RUN | OPEN |
| B05 | 국지 balance | 수상체·바람 증분·vorticity·큰규모 gate | P0 | P5/P7 | 부분구현 | 소스검토 | T05,B03 | NOT_RUN | OPEN |
| B06 | 국지 balance | 독립 verifier와 다격자 수렴 | P0 | P4/P5 | 부분구현 | 소스검토 | B01,T03 | NOT_RUN | OPEN |
| E01 | 공학·통합 | 원래 QBAL 직접 upstream 입력 재생성 | P0 | P6 | 부분구현 | 과거기록 | G02,M01 | NOT_RUN | OPEN |
| E02 | 공학·통합 | 전체 KLAPS pinned ifx/NetCDF/HDF5 ABI | P0 | P6 | 부분구현 | 과거기록 | E01 | NOT_RUN | OPEN |
| E03 | 공학·통합 | thin full-state writer 및 native round-trip | P0 | P3/P6 | 부분구현 | 소스검토 | M04,E02 | NOT_RUN | OPEN |
| E04 | 공학·통합 | legacy 광역 QBAL/bogus-w 호출 대체 | P0 | P6 | 부분구현 | 소스검토 | E03,T05,B06 | NOT_RUN | OPEN |
| E05 | 공학·통합 | generation 원자성·Lustre capability | P0 | P2 | 부분구현 | 과거기록 | G03 | NOT_RUN | OPEN |
| E06 | 공학·통합 | self-contained evidence와 writer 수명 | P1 | P2/P4 | 부분구현 | 소스검토 | G02,E05 | NOT_RUN | OPEN |
| E07 | 공학·통합 | 진단 patch와 full candidate 권한 분리 | P0 | P1/P3 | 구현확인 | 소스검토 | G04 | NOT_RUN | OPEN |
| E08 | 공학·통합 | 동일 배경의 알고리즘 비교 및 Δ 분해 | P0 | P3/P6 | 부분구현 | 소스검토 | M04,E03 | NOT_RUN | OPEN |
| V01 | 과학·운영 검증 | 독립 사건·regime·hold-out manifest | P1 | P7 | 설계·계약 | 소스검토 | G04,O06 | NOT_RUN | OPEN |
| V02 | 과학·운영 검증 | 실제 수송 양성경로 및 ablation | P1 | P5/P7 | 설계·계약 | 과거기록 | T02,V01 | NOT_RUN | OPEN |
| V03 | 과학·운영 검증 | 0–6 h 강수·바람·구름·열역학 검증 | P0 | P7 | 구현미확인 | 소스검토 | E04,B06,V01,V04 | NOT_RUN | OPEN |
| V04 | 과학·운영 검증 | 초기 음파·중력파와 cold-pool 안전성 | P0 | P7 | 부분구현 | 소스검토 | E04,T03,B05 | NOT_RUN | OPEN |
| V05 | 과학·운영 검증 | 정확도·운영 p95 예산·원클릭 rollback | P1 | P6/P7/P8 | 설계·계약 | 소스검토 | E05,V03,V04,G05 | NOT_RUN | OPEN |
| V06 | 과학·운영 검증 | 필수 gate AND·독립 승격 승인 | P0 | P8 | 설계·계약 | 소스검토 | G05,E04,V03,V04,V05 | NOT_RUN | OPEN |
| X01 | 별도 완료 | 시선속도/Barnes release 완료 범위 보존 | 별도 | 외부 완료 | 외부완료 | 외부완료보고 | — | NOT_APPLICABLE | EXTERNAL_COMPLETE |

## 상세 기준 카드

카드의 `다음 작업`, `완료조건`, `적대/회귀시험`, `근거`는 요구사항별 실행 계약이다. 역할은 모두 미배정이며 실제 인력 지정이 아니다.

### G01 — 최종 목표·비목표와 기능별 승인 범위 고정

- 분류/증거: `구현확인` / `소스검토`; 긴급도 `P0`; 기존 단계 `P1/P5`.
- 담당 역할: `미배정 — 제품·권한 책임`; 선행 ID: 없음.
- 다음 작업: HYDRO/THERMO/DYNAMIC의 승인 범위를 하나의 요구사항 표에 고정.
- 완료조건: 목표에 수상체·T/qv·질량/압력·바람·파동 안전·원본보호 포함; 진단을 운영 승격으로 해석하지 않음.
- 적대/회귀시험: 문서·CLI·manifest의 mode/authority 일치 검사.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### G02 — 최신 SHA·입력·도구·시험 증거 기준선

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P8`.
- 담당 역할: `미배정 — 릴리스·증거 책임`; 선행 ID: 없음.
- 다음 작업: 실제 시험 대상 source SHA·tree·input/config·compiler/tool hash를 각각 동결하고 provenance receipt를 재생성; 문서 SHA와 시험 SHA를 분리 기록.
- 완료조건: 실행 source SHA·tree·input/config/compiler hash와 결과가 동일 세대에 결속하며 문서 SHA는 시험 SHA와 별도로 추적.
- 적대/회귀시험: dirty tree, old SHA, changed config, stale receipt 거부.
- 근거: [R12]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### G03 — 운영 원본 불변 / OFF no-op / SHADOW 격리

- 분류/증거: `구현확인` / `소스검토`; 긴급도 `P0`; 기존 단계 `P1/P2`.
- 담당 역할: `미배정 — 안전·권한 격리 책임`; 선행 ID: `G02`.
- 다음 작업: 최신 SHA에서 failure injection과 operational state/file identity 재확인.
- 완료조건: 승인·실패·degraded 모든 경로에서 operational value/metadata/hash 불변.
- 적대/회귀시험: stage별 실패·잘못된 mode·no-op·writer 오류.
- 근거: [R09]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### G04 — 시각 범위 및 12 UTC 제외의 명시성

- 분류/증거: `구현확인` / `과거기록`; 긴급도 `P0`; 기존 단계 `P1`.
- 담당 역할: `미배정 — 검증 범위 책임`; 선행 ID: `G02`.
- 다음 작업: P1 비교 13/14/15와 raw/upstream/manufactured 12–15를 각각 검증.
- 완료조건: historical exclusion을 누락/성공으로 바꾸지 않으며 정해진 범위 내 누락은 fail-closed.
- 적대/회귀시험: 축소/확대/중복/순서변경 시각; full scope 12 UTC 누락.
- 근거: [R10]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### G05 — 필수 CI·main 보호·검증자 분리

- 분류/증거: `구현미확인` / `소스검토`; 긴급도 `P0`; 기존 단계 `P8`.
- 담당 역할: `미배정 — CI·저장소 관리자`; 선행 ID: `G02`.
- 다음 작업: 가벼운 contract CI를 즉시 만들고 ifx self-hosted check와 연결.
- 완료조건: exact HEAD 필수 check 통과; branch/ruleset 적용; 산출자와 승인 판단의 증거 분리.
- 적대/회귀시험: 누락 check, old green SHA, manufactured artifact 승격 거부.
- 근거: [R01]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### M01 — 단일 value/valid/quality/source/time/unit 계약

- 분류/증거: `구현확인` / `소스검토`; 긴급도 `P0`; 기존 단계 `P5`.
- 담당 역할: `미배정 — 상태·자료계약 책임`; 선행 ID: `G02`.
- 다음 작업: 필수와 선택 필드의 coverage 및 시간창 계약 재확인.
- 완료조건: 모든 과학 연산이 usable predicate 사용; unknown bit·단위·시각 불일치 거부.
- 적대/회귀시험: valid=true/source=0, NaN, unknown enum, 시간 mismatch.
- 근거: [R06]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### M02 — OM 독립 도메인 및 지형·PSFC 정합성

- 분류/증거: `구현확인` / `소스검토`; 긴급도 `P0`; 기존 단계 `P5`.
- 담당 역할: `미배정 — 실자료 ingest·geometry 책임`; 선행 ID: `M01`.
- 다음 작업: 완화된 지형 조건까지 제조해·edge case로 확인.
- 완료조건: 도메인이 OM 결측으로 축소되지 않음; 지표/기압/고도의 허용 불일치 명시.
- 적대/회귀시험: bottom OM 한 층 결측, 내부 hole, subterrain, column 전체 결측.
- 근거: [R07]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### M03 — pressure interface / cell_dp / center spacing 분리

- 분류/증거: `구현확인` / `소스검토`; 긴급도 `P0`; 기존 단계 `P5`.
- 담당 역할: `미배정 — pressure geometry 책임`; 선행 ID: `M02`.
- 다음 작업: 절단 셀의 column sum 및 인접 partial-face overlap 추가 검증.
- 완료조건: cell_dp=interface 차; 총질량=A·Σcell_dp/g; level spacing은 질량으로 사용하지 않음.
- 적대/회귀시험: PSFC=center/face/center 사이, 경사면, top closure, analytic column.
- 근거: [R06]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### M04 — canonical–WPS–native 질량분모 계약

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P3/P6`.
- 담당 역할: `미배정 — native I/O·질량계약 책임`; 선행 ID: `M03`.
- 다음 작업: pressure-level field/단위와 dry-air·moist-air·condensate-included 분모·변환을 생산자까지 추적하고 scoped known-column 시험을 실행.
- 완료조건: 유입·canonical·WPS·metgrid/native의 종별 질량기준 일치 및 왕복 검사 통과; 초기 등압면 계약·known-column 시험만으로 최종 폐합하지 않음.
- 적대/회귀시험: 습윤 column field 누락·분모 mismatch·단위 오류와 dry/moist 역변환·column mass audit.
- 근거: [R10]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### M05 — 수분 분석증분과 dry mass / PSFC 결합

- 분류/증거: `설계·계약` / `소스검토`; 긴급도 `P0`; 기존 단계 `P3/P5`.
- 담당 역할: `미배정 — 질량·수분 보존 책임`; 선행 ID: `M04`.
- 다음 작업: pressure-level Δqv·Δdry-mass·PSFC와 A_Q/A_E/A_M·enthalpy convention을 고정하고 pressure-fixed/native-dry-mass scoped cell/column budget을 실행.
- 완료조건: 고정 pressure mass와 수분추가로 생기는 dry-mass 변화를 숨기지 않으며 결합 후보의 A_Q/A_E/A_M ledger 폐합; 독립 cell/column 시험만으로 완료하지 않음.
- 적대/회귀시험: 같은 Δ수분을 pressure-fixed/native-dry-mass로 처리하고 denominator·PSFC·enthalpy budget 차이를 비교.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### M06 — 바람 frame·투영·metric·w↔omega 계약

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P5/P6`.
- 담당 역할: `미배정 — 바람 frame·metric 책임`; 선행 ID: `M01`.
- 다음 작업: earth/grid-relative 회전, map factor, pressure tendency/advection 포함 여부 명시.
- 완료조건: 변환 왕복과 균일 물리바람 제조해 통과; 근사 omega 변환 범위 표시.
- 적대/회귀시험: 회전격자·경사 지표·이동 pressure surface·단위 km/m.
- 근거: [R11]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### M07 — 물리적 top/bottom boundary와 관측시각

- 분류/증거: `부분구현` / `과거기록`; 긴급도 `P0`; 기존 단계 `P5`.
- 담당 역할: `미배정 — 경계·관측시각 책임`; 선행 ID: `M06`.
- 다음 작업: 실제 model-top flux와 USF/VSF frame 확보; 경계 tendency cycle 일치.
- 완료조건: copied/test boundary는 science authority NONE; 관측 승인 경계와 엄격 분리.
- 적대/회귀시험: 정지경사면, 지표 pressure tendency, 모델 cycle 혼합, 상부 flux.
- 근거: [R05]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### O01 — 실제 cloud analysis ingest 및 수상체 정합성

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P1`; 기존 단계 `P5/P6`.
- 담당 역할: `미배정 — cloud analysis·수상체 책임`; 선행 ID: `M04`.
- 다음 작업: cloud fraction/type/base/top/T/qv를 실제 adapter에 연결.
- 완료조건: 운형이 아니라 관측과 오차로 수상체 prior/constraint 구성.
- 적대/회귀시험: 안개/층운/shallow/deep Cu/층상강수/중첩 cloud layer.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### O02 — 운형·dBZ-only 연직속도 금지 유지

- 분류/증거: `구현확인` / `소스검토`; 긴급도 `P0`; 기존 단계 `P5`.
- 담당 역할: `미배정 — 동역학 권한 책임`; 선행 ID: `M01`.
- 다음 작업: 관측값·추정값·test target·권한을 별도로 표시.
- 완료조건: cloud presence 또는 reflectivity만으로 동역학 승인 bit를 부여하지 않음.
- 적대/회귀시험: 운형만 변경, 높은 dBZ만 제공, manufactured bit 주입.
- 근거: [R09]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### O03 — H_Z와 종별 retrieval 불확실도

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P1`; 기존 단계 `P3/P5`.
- 담당 역할: `미배정 — radar operator·오차모형 책임`; 선행 ID: `M04,O01`.
- 다음 작업: host microphysics 일치 forward operator와 retrieval parameter ID/R_Z 도입; 산란·입자분포·대표성 불확실성이 커지면 R_Z를 확대하거나 정밀도 가중 R_Z^-1을 낮춤.
- 완료조건: phase/PSD/wavelength/bright-band 가정을 cell provenance와 불확실도에 반영하고 불확실성 증가를 R_Z 축소로 처리하지 않음.
- 적대/회귀시험: rain/snow/mixed-phase·beam filling·계수변화 ablation.
- 근거: [R11]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### O04 — no-echo / missing / QC-reject 분리

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P1`; 기존 단계 `P5`.
- 담당 역할: `미배정 — radar QC·결측 계약 책임`; 선행 ID: `O03`.
- 다음 작업: 현재 destination block 유지 검증 후 검출한계 기반 censored constraint 평가.
- 완료조건: no-echo는 검출상한이며 missing은 무정보; blocked flux를 증발로 간주하지 않음.
- 적대/회귀시험: 약한 echo, high beam, attenuation, QC hole, 명시 no-echo.
- 근거: [R08]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### O05 — 내부 물리제약 dynamic target 추정 및 R_w/식별가능성

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P5`.
- 담당 역할: `미배정 — dynamic target·관측권한 책임`; 선행 ID: `M06,M07,O03`.
- 다음 작업: 분석풍·질량/연속성·부력 등 내부 물리제약과 관측 근거·오차·영역평균을 한 계약으로 연결; 외부 w target을 필수 입력으로 요구하지 않음.
- 완료조건: core w를 grid mean으로 대입하지 않음; 외부 w가 없어도 내부 제약 추정을 평가하며 관측·제약이 부족하거나 식별불능이면 적용 권한을 0으로 하고 원본 사용·rollback을 유지.
- 적대/회귀시험: 0관측·poor geometry·반복관측·큰 R_w·상승 core 면적변화·외부 w target 부재.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### O06 — 레이더별 LOS 입력 연결과 Cloud-BAL 공동분석 수용

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P1`; 기존 단계 `P5/P6`.
- 담당 역할: `미배정 — Barnes 통합·LOS 계약 책임`; 선행 ID: `M01,M06`.
- 하위 의존성: `O06.a`는 M01·M06(입력 계약·frame/metric)에 의존하고, `O06.b`는 O06.a·O03·O04·O05 또는 동등한 내부 관측가능성 단계·O08(낙하속도)·M05·M07(질량/경계)에 의존한다. 두 하위 판정은 하나의 O06 ID 아래에서 기록한다.
- 다음 작업: `O06.a` 입력 연결에서 레이더별 Vr·기하·시각·QC·frame/dealias/beam/uncertainty와 provenance를 연결; `O06.b` 공동분석에서 관측가능성·질량/경계 계약을 확인한 뒤 R2에서 원 관측 공동분석 또는 명시된 조건부 경로를 선택.
- 완료조건: `O06.a`는 실제 자료 ID·시각·기하·QC·단위·계보를 확인하고, `O06.b`는 선택된 원 관측 공동분석 또는 조건부 경로에서 V_r=beam·(u,v,w−Vt_Z)·assimilated/held-out 중복 제거를 검증한다. 외부 w target 부재는 자동 거부 사유가 아니며 unresolved/incompatible 상태는 적용 권한 0·원본 유지·rollback.
- 적대/회귀시험: `O06.a` 누락/중복 ID·folded/dealiased provenance·Nyquist·frame 불일치; `O06.b` poor multi-radar rank·공통 Vt·관측 재사용·incompatible mass/boundary.
- 근거: [R02]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### O07 — 시간·storm-relative trajectory frame

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P1`; 기존 단계 `P5`.
- 담당 역할: `미배정 — trajectory·시간 frame 책임`; 선행 ID: `M06`.
- 다음 작업: 시간진화 parcel은 지구고정 u, 준정상 storm-frame 재구성은 u−c로 모델 분리.
- 완료조건: 두 frame에서 같은 물리 궤적 복원; unknown motion을 관측된 0으로 표시하지 않음.
- 적대/회귀시험: 균일 storm translation·강한 shear·시각 mismatch·u/c 동시변환.
- 근거: [R11]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### O08 — 낙하속도의 mass-weighted / Z-weighted 분리

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P1`; 기존 단계 `P5`.
- 담당 역할: `미배정 — terminal velocity·PSD 책임`; 선행 ID: `O03,M01,M06`.
- 다음 작업: O06.a 입력 연결이 준비된 뒤 flux에는 Vt_mass, Doppler에는 Vt_Z 사용; PSD 없으면 근사/오차 표기.
- 완료조건: 하나의 terminal speed를 이유 없이 양쪽 관측·질량 연산에 공유하지 않으며 O06.b 공동분석이 사용할 Vt_Z·공통 낙하속도 오차를 독립적으로 기록.
- 적대/회귀시험: 다분산 PSD known moments; updraft suspension와 flux 역산; O06.a 입력 누락·Vt_Z 미기록.
- 근거: [R11]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### T01 — 수분 분석증분과 물리 수송 ledger 분리

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P3/P5`.
- 담당 역할: `미배정 — 수분 ledger·budget 책임`; 선행 ID: `M05,O03`.
- 다음 작업: pressure-level A_Q를 finite-time transport·phase conversion과 분리하고 synthetic column ledger를 먼저 실행.
- 완료조건: 실제 관측 분석 A_Q·내부 상변화·선택한 수송 모형의 장부를 분리하고 출처·종·부호·경계 budget 폐합; kg/s interface throughput을 kg global source-to-sink mass로 부르지 않음; 합성 ledger만으로 완료하지 않음.
- 적대/회귀시험: uniform flux 다층 통과, single-source budget, missing qv와 boundary sink 혼동.
- 근거: [R08]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### T02 — 범위별 source-to-sink 종별 보존 수송

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P1`; 기존 단계 `P3/P5`.
- 담당 역할: `미배정 — 보존 수송 책임`; 선행 ID: `T01,O07,O08`.
- 다음 작업: 사전 승인한 실행 범위(분석 재구성·실제 시간수송·기존 수상체 기반 연직풍 복원) 중 하나를 선택하고 범위별 장부·주장·필수 검사를 고정; 선택하지 않은 범위는 미실행으로 보존.
- 완료조건: 선택한 범위의 요구 장부를 충족한다. 실제 시간수송이면 source 제거·sink 추가·지표/경계 유출입·positivity를 폐합하고, 분석 재구성이면 분석 증분 장부를, 기존 수상체 기반 복원이면 질량기준·낙하속도·불확실도 변경을 기록한다; 범위 선택만으로 DONE/N 또는 폐합으로 자동 변경하지 않음.
- 적대/회귀시험: 순회순서/permutation·tilted shaft·surface sink·split step·CFL·범위 미승인/범위 외 자동완료.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### T03 — 증발·승화·융해와 T/qv 동시 조정

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P5`.
- 담당 역할: `미배정 — 열역학·상변화 책임`; 선행 ID: `T01,M05`.
- 다음 작업: 종별 Δm/Δh와 적용할 enthalpy convention을 고정하고 기존 bounded cell/column 조정을 등압면 후보 경로에 연결; 독립 시험과 실제 연결 증거 분리.
- 완료조건: 실제 후보 경로의 내부 phase change가 total water·선택한 enthalpy를 보존하고 positivity·실패 시 전체 rollback을 검증; T01/M05 선행 최종 조건도 충족하며 standalone 시험만으로 완료하지 않음.
- 적대/회귀시험: evap/sublimation/melting/freezing, 건조·포화 극한, enthalpy mismatch와 iteration-cap rollback.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### T04 — loading·잠열·압력섭동의 일관된 부력

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P1`; 기존 단계 `P5`.
- 담당 역할: `미배정 — 부력·압력섭동 책임`; 선행 ID: `T03,O05`.
- 다음 작업: native 물·얼음 포화 기준, 혼합상 및 과냉각 액체수 정책을 host 미세물리와 고정하고 loading 후보는 prior/tendency로 제한하여 pressure-gradient·entrainment·area를 함께 평가.
- 완료조건: dBZ→고정 하강 w 금지; 수치적 overshoot·중복 상변화·비현실적 냉각을 억제하되 native 물/얼음·혼합상·과냉각 액체수의 물리적 허용 상태를 일괄 제거하지 않음; 관측 오차 내 응답.
- 적대/회귀시험: 같은 dBZ의 dry/moist subcloud·updraft·stratiform·cold-pool 사례; 물/얼음 혼합상·과냉각 액체수·포화기준 경계 사례.
- 근거: [R11]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### T05 — state-dependent geometry·thermo outer coupling

- 분류/증거: `설계·계약` / `소스검토`; 긴급도 `P0`; 기존 단계 `P5/P6`.
- 담당 역할: `미배정 — coupled outer-loop 책임`; 선행 ID: `M05,T03,B01`.
- 다음 작업: 등압면 수분·온도→density/EOS·geometry·metric→balance→전체 재검증의 bounded outer iteration 구현; surrogate 시험은 초기 검증으로만 사용.
- 완료조건: 실제 결합 후보의 nonlinear fixed-point/전체 제약잔차와 변화량이 사전 기준에 수렴; cap 도달은 거부; 단순 순차 transaction·surrogate 수렴만으로 최종 폐합하지 않음.
- 적대/회귀시험: 강한 moisture increment, damping sensitivity, stale metric, 후속 block의 선행 budget 훼손.
- 근거: [R09]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### B01 — 등압면 연산자와 모델면 변환 후 정합성

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P5/P6`.
- 담당 역할: `미배정 — balance operator·native handoff 책임`; 선행 ID: `M03,M06,M07`.
- 다음 작업: pressure-grid face DOF·metric의 solve/update 동일 C/G/L을 고정하고, WPS→real 뒤에는 native 좌표의 operator/residual을 재계산; 두 좌표계에 같은 matrix를 가정하지 않음.
- 완료조건: pressure-grid solve/update와 그 residual은 동일 operator로 폐합하고 transformed native state는 native C/G/L 재계산 후 폐합; 좌표계 간 동일 matrix는 요구하지 않음.
- 적대/회귀시험: 등압면 adjoint dot·symmetry/energy·support boundary·terrain partial faces; pressure→native 변환 후 metric/sign/unit·stale copied matrix 검출.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### B02 — A-grid parity·target sign 왜곡 폐합

- 분류/증거: `부분구현` / `과거기록`; 긴급도 `P0`; 기존 단계 `P5`.
- 담당 역할: `미배정 — 수치 balance 검증 책임`; 선행 ID: `B01`.
- 다음 작업: 6/16 adverse response fixture 고정; target 위치/허용치를 성과에 맞춰 바꾸지 않음.
- 완료조건: manufactured smooth target의 설계오차 감소와 mesh-convergence; nullspace/gauge 명시.
- 적대/회귀시험: single/multi column, 위치 1cell 이동, checkerboard, mesh refinement.
- 근거: [R05]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### B03 — 국지 support·질량 compatibility·배경 보존

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P5`.
- 담당 역할: `미배정 — localization·compatibility 책임`; 선행 ID: `B01`.
- 다음 작업: local zero-normal에서 admissible target/δdotm 조건 계산.
- 완료조건: support 밖 increment0; target 없는 component no-op; incompatible RHS는 거부.
- 적대/회귀시험: 분리 component, uniform wind, nonzero background residual, infeasible forcing.
- 근거: [R09]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### B04 — PCG preconditioner·conditioning·성능

- 분류/증거: `부분구현` / `과거기록`; 긴급도 `P1`; 기존 단계 `P5`.
- 담당 역할: `미배정 — solver 성능 책임`; 선행 ID: `B02,B03`.
- 다음 작업: gauge 처리 후 Jacobi/vertical-line 등 단순 preconditioner 비교.
- 완료조건: 잔차·정확도 유지하며 iteration/memory/wall p95 예산 충족.
- 적대/회귀시험: thin cells, anisotropy, sparse/dense support, bad conditioning.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### B05 — 수상체·바람 증분·vorticity·큰규모 gate

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P5/P7`.
- 담당 역할: `미배정 — 다변량 gate 책임`; 선행 ID: `T05,B03`.
- 다음 작업: changed-region·shell·large-scale residual과 uncertainty-normalized 변화율 추가.
- 완료조건: 대류의 비지균성을 제거하지 않으면서 불필요한 종관/회전 증분 통제.
- 적대/회귀시험: 회전배경, frontogenesis, calm wind, compact forcing boundary.
- 근거: [R11]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### B06 — 독립 verifier와 다격자 수렴

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P4/P5`.
- 담당 역할: `미배정 — 독립 검증자 책임`; 선행 ID: `B01,T03`.
- 다음 작업: pressure-level field·mass·enthalpy·metric 계약을 입력으로 별도 sparse-matrix reference와 column oracle을 구성하고 scoped mutation/multigrid test를 실행.
- 완료조건: 공유 wrong helper 재사용 없이 원천 입력→최종 state/ledger/operator를 독립 재계산하고 다격자·제조해·native round-trip 검증; 초기 등압면 oracle만으로 B01/T03 포함 최종 폐합을 대체하지 않음.
- 적대/회귀시험: metric/sign/unit/denominator/enthalpy mutation, stale WPS→native operator, manufactured·round-trip convergence.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### E01 — 원래 QBAL 직접 upstream 입력 재생성

- 분류/증거: `부분구현` / `과거기록`; 긴급도 `P0`; 기존 단계 `P6`.
- 담당 역할: `미배정 — upstream 재생성 책임`; 선행 ID: `G02,M01`.
- 다음 작업: LT1/LQ3/LCO/LSX를 원래 producer로 isolated tree에서 생성.
- 완료조건: 완료순서·nonzero exit·cycle/valid time·freshness·coverage 모두 증거화.
- 적대/회귀시험: VRT race, missing producer, stale COM, equal valid-time 다른 cycle.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### E02 — 전체 KLAPS pinned ifx/NetCDF/HDF5 ABI

- 분류/증거: `부분구현` / `과거기록`; 긴급도 `P0`; 기존 단계 `P6`.
- 담당 역할: `미배정 — ifx·ABI 통합 책임`; 선행 ID: `E01`.
- 다음 작업: 전체 source/dependency pin·out-of-source clean link·binary/source receipt.
- 완료조건: derived→QBAL→LAPSPREP의 실제 binary가 canonical symbols와 ABI/runtime closure 보유.
- 적대/회귀시험: ldd-r/symbol audit·clean link·compiler hash·O0/O2.
- 근거: [R02]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### E03 — thin full-state writer 및 native round-trip

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P3/P6`.
- 담당 역할: `미배정 — full-state I/O 책임`; 선행 ID: `M04,E02`.
- 다음 작업: 초기에는 작은 OFF 읽기/쓰기에서 field/shape/metadata 확인; 등압면 결합 검증 뒤 full OFF 및 coupled candidate의 WPS→real 왕복 확대; 기존 LAPS 출력만으로 후보 전달을 대체하지 않음.
- 완료조건: canonical→WPS→metgrid/native의 수분·T·wind·geometry·mask·time·질량분모가 변환 계약과 사전 허용오차에 부합; OFF와 실제 coupled candidate 전체 왕복 필수; 작은 I/O 시험만으로 완료하지 않음.
- 적대/회귀시험: coupled candidate asymmetric impulse·level remap·wind rotation·species denominator와 OFF/oldLAPS-only 누락 경로.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### E04 — legacy 광역 QBAL/bogus-w 호출 대체

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P6`.
- 담당 역할: `미배정 — production call graph 책임`; 선행 ID: `E03,T05,B06`.
- 다음 작업: 격리 사본에서 단일 adapter와 legacy 재진입 차단 구현 준비; 실제 full-KLAPS 통합은 CP06-B 및 기존 RELEASE/NO-GO 선행조건 충족 후 검증.
- 완료조건: 동일입력 read→coupled candidate→independent gate→publish 한 경로와 중복 balance/잠열 보정 부재; E03/T05/B06 및 기존 최종 통합 gate 모두 충족.
- 적대/회귀시험: legacy bypass/re-entry, partial·oldLAPS-only candidate, duplicated correction, missing verifier, symbol/runtime trace.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### E05 — generation 원자성·Lustre capability

- 분류/증거: `부분구현` / `과거기록`; 긴급도 `P0`; 기존 단계 `P2`.
- 담당 역할: `미배정 — publisher·filesystem 안전 책임`; 선행 ID: `G03`.
- 다음 작업: 시작 시 no-replace/CAS/fsync 기능 probe; 지원 backend만 게시.
- 완료조건: 고유 generation 불변·검증byte=게시byte·current 전체전환; unsafe fallback 없음.
- 적대/회귀시험: unsupported rename, crash points, racing publisher, retained writer fd.
- 근거: [R02]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### E06 — self-contained evidence와 writer 수명

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P1`; 기존 단계 `P2/P4`.
- 담당 역할: `미배정 — provenance·evidence 책임`; 선행 ID: `G02,E05`.
- 다음 작업: 입력/build/실행/validator/그림 receipt 하나의 provenance DAG로 결속.
- 완료조건: producer 종료 후 읽기전용 snapshot 검증; source/config/deps/결과 재현.
- 적대/회귀시험: 변경 file descriptor·path swap·unsigned local claim·stale input.
- 근거: [R04]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### E07 — 진단 patch와 full candidate 권한 분리

- 분류/증거: `구현확인` / `소스검토`; 긴급도 `P0`; 기존 단계 `P1/P3`.
- 담당 역할: `미배정 — artifact 권한 책임`; 선행 ID: `G04`.
- 다음 작업: 현행 PATCH_RECEIPT/NOT_READY 경계를 회귀시험으로 유지.
- 완료조건: patch는 DERIVED_DIAGNOSTIC_PATCH; source generation/full product로 자기증명 금지.
- 적대/회귀시험: full-role 위장, schema downgrade, missing validation, stale manifest.
- 근거: [R10]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### E08 — 동일 배경의 알고리즘 비교 및 Δ 분해

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P3/P6`.
- 담당 역할: `미배정 — 비교 실험 책임`; 선행 ID: `M04,E03`.
- 다음 작업: 초기 등압면 비교는 동일 pre-QBAL x_b의 OFF/후보로 제한; 이후 같은 입력의 전체 baseline/candidate를 native 상태까지 전달해 비교.
- 완료조건: qC−qB와 qB−qO를 각 비교 좌표·질량기준에서 별도 기록하고 동일 배경의 full-native 비교까지 폐합; mass basis unresolved이면 NO-GO; 등압면 비교만으로 완료하지 않음.
- 적대/회귀시험: 등압면 pass 뒤 native remap 잔차 악화, qB≠qO, zero-change, unapplied levels, mask/coordinate mismatch, false RMS improvement.
- 근거: [R10]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### V01 — 독립 사건·regime·hold-out manifest

- 분류/증거: `설계·계약` / `소스검토`; 긴급도 `P1`; 기존 단계 `P7`.
- 담당 역할: `미배정 — 과학 검증 설계 책임`; 선행 ID: `G04,O06`.
- 다음 작업: 연속 네 시각을 독립 네 사건으로 세지 않고 event-level split.
- 완료조건: calibration/검증/최종평가 분리; 관측 ID와 시간·공간 누수 차단.
- 적대/회귀시험: 청천/안개/층상/강한대류/혼합상/산악/radar outage·held-out overlap.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### V02 — 실제 수송 양성경로 및 ablation

- 분류/증거: `설계·계약` / `과거기록`; 긴급도 `P1`; 기존 단계 `P5/P7`.
- 담당 역할: `미배정 — 수송 과학 검증 책임`; 선행 ID: `T02,V01`.
- 다음 작업: deposition>0·tilted shaft를 실제 결측/부분 coverage 사례로 검증.
- 완료조건: 기존 deposition0 사례는 분기 실행 검증으로 오인하지 않음; source lineage 확인.
- 적대/회귀시험: control, hydro-thermo-only, coupled, legacy paired experiments.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### V03 — 0–6 h 강수·바람·구름·열역학 검증

- 분류/증거: `구현미확인` / `소스검토`; 긴급도 `P0`; 기존 단계 `P7`.
- 담당 역할: `미배정 — paired forecast·과학 평가 책임`; 선행 ID: `E04,B06,V01,V04`.
- 다음 작업: V04 초기 안전성 확인 후 같은 model/physics/forcing으로 paired forecast 수행.
- 완료조건: FSS/CSI/POD/FAR/bias·vector wind RMSE·T/qv·cloud base/top·budget noninferiority; V04 초기 충격·파동 gate 없이 전체 예보 성능을 폐합하지 않음.
- 적대/회귀시험: event-block bootstrap·regime worst-case·clear-sky false precipitation·V04 이전 실행 경로.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### V04 — 초기 음파·중력파와 cold-pool 안전성

- 분류/증거: `부분구현` / `소스검토`; 긴급도 `P0`; 기존 단계 `P7`.
- 담당 역할: `미배정 — 초기화 파동·cold-pool 검증 책임`; 선행 ID: `E04,T03,B05`.
- 다음 작업: 실제 E04 handoff 후보에서 첫 시간전진 전에 초기 고빈도 ps tendency/divergence를 진단하고 모델 timestep 수준 sampling을 별도 확인.
- 완료조건: 분석잔차뿐 아니라 시간전진 고주파 excess가 대조군 허용범위 이내이며 정당한 대류·cold-pool을 유지; E04 handoff와 T03/B05 물리·다변량 조건을 확인하고 V03 전체 예보보다 먼저 폐합.
- 적대/회귀시험: 첫 미세물리 호출과 초기 고빈도 구간의 10/30/60분 진단; 6 h 후속 평가는 V03에서 별도 수행; sampling aliasing·DFI/IAU 없음/있음 대조·handoff 누락·상변화 반복·과도한 vorticity/파동.
- 근거: [R05]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### V05 — 정확도·운영 p95 예산·원클릭 rollback

- 분류/증거: `설계·계약` / `소스검토`; 긴급도 `P1`; 기존 단계 `P6/P7/P8`.
- 담당 역할: `미배정 — 운영 SLO·rollback 책임`; 선행 ID: `E05,V03,V04,G05`.
- 다음 작업: 업무 cycle에서 latency/memory/rejection/freshness SLO와 shadow monitor 설정.
- 완료조건: 장애 시 원본 사용·원인표시·publisher 재시도 동일성·rollback 검증.
- 적대/회귀시험: 자료지연, IO 장애, memory pressure, dense support, consecutive cycles.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### V06 — 필수 gate AND·독립 승격 승인

- 분류/증거: `설계·계약` / `소스검토`; 긴급도 `P0`; 기존 단계 `P8`.
- 담당 역할: `미배정 — 승격 심사·독립 승인 책임`; 선행 ID: `G05,E04,V03,V04,V05`.
- 다음 작업: 공학/물리/통합/과학 gate를 모두 통과한 exact SHA만 별도 promotion 심사.
- 완료조건: 평균점수로 critical FAIL/NOT_RUN 상쇄 금지; ACTIVE는 별도 설계·리뷰 후만.
- 적대/회귀시험: gate 하나 누락/과거 PASS/manufactured/partial patch 승격 거부.
- 근거: [R03]. gate=`NOT_RUN`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`OPEN`.

### X01 — 시선속도/Barnes release 완료 범위 보존

- 분류/증거: `외부완료` / `외부완료보고`; 긴급도 `별도`; 기존 단계 `외부 완료`.
- 담당 역할: `미배정 — 외부 release liaison`; 선행 ID: 없음.
- 다음 작업: release와 Cloud-BAL 통합 책임을 분리하고 기존 산출물 receipt만 참조.
- 완료조건: 별도 작업을 Cloud-BAL 미완료 항목으로 재분류하지 않음; 통합은 O06에만 집계.
- 적대/회귀시험: 기존 release hash·thread/repeat regression receipt 확인.
- 근거: [R02]. 외부 완료 보고를 runtime PASS로 재분류하지 않음. gate=`NOT_APPLICABLE`; tested_sha/evidence_uri/reviewer=`(빈 값)`; closure=`EXTERNAL_COMPLETE`.

## 근거 자료 범례

아래 URL은 기준 HEAD에 고정한 링크다. R01은 최신 main 메타데이터의 원자료와 함께 기준 commit으로 고정한 링크를 제시한다. 카드의 `[Rxx]`는 이 범례와 원문 설계 검토의 근거 ID를 따른다.

| ID | 고정 근거 |
|---|---|
| R01 | [기준 commit 메타데이터](https://github.com/gonos2k/Cloud-BAL/commit/f837bad0bdf1050a34975d93b178b7dee4420094); 원자료 [main branch API](https://api.github.com/repos/gonos2k/Cloud-BAL/branches/main) |
| R02 | [STATUS_20260907.md](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/docs/STATUS_20260907.md) |
| R03 | [RELEASE_CHECKLIST.md](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/docs/RELEASE_CHECKLIST.md) |
| R04 | [NO_GO_CLOSURE_CHECKLIST.md](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/docs/NO_GO_CLOSURE_CHECKLIST.md) |
| R05 | [REAL_GEOMETRY_DYNAMIC_BALANCE.md](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/docs/REAL_GEOMETRY_DYNAMIC_BALANCE.md) |
| R06 | [cloud_bal_state.f90](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/src/common/cloud_bal_state.f90) |
| R07 | [cloud_bal_real_netcdf.f90](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/src/common/cloud_bal_real_netcdf.f90) |
| R08 | [cloud_bal_column_physics.f90](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/src/common/cloud_bal_column_physics.f90) |
| R09 | [cloud_bal_pipeline.f90](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/src/common/cloud_bal_pipeline.f90) |
| R10 | [compare_operational_shadow.py](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/tools/compare_operational_shadow.py) |
| R11 | [SCIENTIFIC_BASIS.md](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/docs/SCIENTIFIC_BASIS.md) |
| R12 | [exact-HEAD workflow runs](https://api.github.com/repos/gonos2k/Cloud-BAL/actions/runs?head_sha=f837bad0bdf1050a34975d93b178b7dee4420094&per_page=100) |

## 폐합 판정 규약

`gate_result=PASS`는 한 시험 또는 검증의 결과를 기록하는 상태다. 이는 요구사항 전체의 폐합, 범위 승인, 선행조건 충족 또는 운영 승격을 뜻하지 않는다. `closure=CLOSED`는 다음을 모두 독립적으로 확인한 승인 상태로만 사용한다.

- 승인된 frozen required-ID set이 비어 있지 않고, 해당 판정 시점의 요구사항 목록과 일치한다.
- 증거 유형(`evidence_type`)이 해당 요구사항의 필수 증거 등급에 맞고 검증되었으며, 검증일·receipt hash·reviewer가 기록되어 있다. `evidence_uri`는 trim 후에도 비어 있지 않은 self-contained receipt를 가리킨다.
- `prerequisite_ids`에 열거된 모든 predecessor가 폐합되어 있고, 적용 범위(scope)가 사전에 승인되어 있다.
- 문서 기준 SHA(`doc_sha`)와 시험 대상 SHA(`tested_sha`)가 receipt와 승인 기록에 함께 결속되어 있다.
- 독립 reviewer와 승인 기록이 존재하고, FAIL·NOT_RUN·unresolved 증거가 남아 있지 않다.

위 조건 중 하나라도 빠지면 시험이 PASS로 기록되어 있어도 `closure=OPEN`을 유지한다. 범위 선택, 행 제거, 필수 ID를 `N`으로 바꾸는 것, URI 문자열만 채우는 것은 폐합을 만들지 않는다. 이 규약은 Excel 계산 엔진을 전제로 하지 않으며, 원장과 self-contained receipt를 검토자가 함께 확인하는 기준이다.

명세 적대시험의 기대 판정은 다음과 같다.

- G02가 미폐합인데 G03만 PASS·동일 SHA·URI를 기록하면 G03은 PASS 기록일 수 있어도 `closure=OPEN`이다.
- V03이 `구현미확인`·소스검토 상태인데 PASS만 입력하면 요구된 과학·실행 증거가 없으므로 `closure=OPEN`이다.
- 검증 근거 URI가 공백뿐이면 trim 후 빈 값이므로 `closure=OPEN`이다.
- 승인된 필수 ID 집합의 모든 값을 `N`으로 바꾸면 집합 불일치 또는 필수 집합 누락으로 판정하며, 완료율·폐합을 만들지 않는다.

## 폐합 메모

이 문서 작성은 설계·정적 검토 결과의 기록이며 pinned ifx 전체 suite, 실제자료 generation, native round-trip, paired 0–6 h forecast를 실행했다는 뜻이 아니다. 본체 45개 gate의 초기값은 `NOT_RUN`이다. X01은 `NOT_APPLICABLE / EXTERNAL_COMPLETE`로 별도 완료를 유지하며 Cloud-BAL 통합 O06의 선행 증거를 대신하지 않는다.

## 정적 검토 보완 사항

원문의 요구사항 ID·분류·현재 상태는 유지하고, 2026-09-14 검토에서 O06·V03·V04의 의존성과 해당 카드의 해석을 교정했다. O06.a와 O06.b는 O06 아래의 하위 판정이며 별도 분모나 독립 요구사항이 아니다. [설계 검토 §3](CLOUD_BAL_DESIGN_REVIEW_20260907.md)의 REV01–REV08은 별도 요구사항 분모가 아니라 해당 ID의 해석·시험 보완이다. 특히 B04의 PCG는 향후 설계이고 현행 recurrence는 가중 CR 형태다. O08의 `vt_z_mean`은 현재 mass-weighted proxy이며 Z-weighted 구현 완료가 아니다. M03/B01에는 이웃 pressure interval의 공통 면과 두께 평균을 구별하는 반례를 포함한다.
