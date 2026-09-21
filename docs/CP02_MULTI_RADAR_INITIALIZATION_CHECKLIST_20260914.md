# 다중 레이더·국지 균형초기화 실행 체크리스트와 체크포인트

작성: 2026-09-14. 추가 검토·P0 교정 반영: 2026-09-18.
상위 계획: [추가 과제 계획서](CP02_MULTI_RADAR_BALANCED_INITIALIZATION_PLAN_20260914.md).
검토 근거: 수학·수치해석·기상학 종합 검토 (로컬 작업공간 근거: `../scratch/cp02_multiradar_additional_review_20260914/REVIEW.md`).
수학 근거: [정리·증명과 실제 적용 조건](CP02_MULTI_RADAR_MATHEMATICAL_PROOFS_20260914.md).

## 상태와 사용 방법

**계획·체크리스트 작성 완료 / 입력·방정식 조사 진행 / 새 결합 초기화 미검증**.
2026-09-15 사용자 계획 승인 완료. 아래 구현 체크리스트의 팀 검토 후 코드 수정·회귀시험을 진행한다.
`MR-C0`–`MR-C6`는 이 추가 과제의 체크포인트다. 기존 CP00–CP07 번호나 CP02의
여섯 요구사항을 대체하지 않는다. 체크는 실제 산출물·판정·입력/소스/설정 근거가
있을 때만 완료한다. 문서 작성, 정상 종료, 0회 solver 또는 기존 OFF 실험은 새
물리 초기화의 완료 근거가 아니다.
현재 MR-C0–MR-C6에는 실제 `PASS`가 없으며, 아래 결정·매핑의 상태도 `PENDING` 또는
`NOT_RUN`으로 유지한다.

| 체크포인트 | 계획 연결 | 현재 상태 | 종료 산출물 |
|---|---|---|---|
| MR-C0 입력 연결 | R0 | IN_PROGRESS | 실제 사례의 레이더별·분석장 입력 목록과 좌표/시각 계약 |
| MR-C1 연직 정보 | R1 | NOT_RUN | 관측 가능 영역·조건부 정보·낙하속도 오차와 경로 선택 |
| MR-C2 결합 방정식 | R2 | IN_PROGRESS | 전체 질량식·경계·엄밀/오차 허용 제약·실현 가능성 판정 |
| MR-C3 상변화·파동 | R2, R5 설계 | IN_PROGRESS | 상변화·native 정합성·물리 파동 보존의 사전 검증 기준 |
| MR-C4 구현·t0 전달 | R3, R4 | NOT_RUN | 실제 FORTRAN 검증과 첫 시간전진 전 native 재읽기 |
| MR-C5 초기 충격 | R5 | NOT_RUN | 첫 미세물리·음향/중력파·대류 보존의 초기 시간 진단 |
| MR-C6 강수 효과 | R6 | NOT_RUN | 동일 사례 1–6시간 RN1/PTY·CSI 및 분석장 비교 |

MR 체크포인트와 기존 본체 45개 ID의 추적 매핑은 다음과 같다. 이 표는 기존 ID의
gate/closure를 승격하지 않으며, 각 MR 상태는 위 표의 실제 상태를 따른다.

| MR | 기존 45-ID 추적 범위 |
|---|---|
| MR-C0 | M01, M04, M06, O01, O06, E01 |
| MR-C1 | O03, O05, O06, O08, B06 |
| MR-C2 | M05, M07, B01–B03, T05 |
| MR-C3 | T01, T03, T04, V04 |
| MR-C4 | E02–E04, B06 |
| MR-C5 | V04, T03, B05 |
| MR-C6 | V01–V03, E08 |

MR-C0→MR-C1→MR-C2/MR-C3→MR-C4→MR-C5→MR-C6 순서로 통과한다.
자료 조사와 방정식 검토는 병렬로 진행할 수 있다. MR-C2/C3를 통과하지 않은 진단
후보를 실제 초기화 후보로 게시하지 않는다. 실패는 해당 체크포인트에 남기고
소유한 scratch 후보를 폐기하거나 원상태로 되돌린다. 운영 입력과 보존 실험은 유지한다.

## 2026-09-17 PR #25 후속 실행 순서 — 현재 적용

상위 계획의 **PR #25 legacy 수학적 연결 교정** 절을 다음 실행의 우선순위로 적용한다.
이 표는 기존 MR/45-ID를 대체하지 않으며 개별 `PASS_SCOPED`를 취소하지 않는다.
현행 legacy의 선언된 전체 후보 continuity 목표를 출발점으로 삼고, canonical 증분
projection과 구분한다. 물리 경계에서 목표가 불가능하면 거부하며 RHS 평균 제거나
부분 보정 전환으로 성공을 만들지 않는다.

| 구현 작업 / 연결 | 현재 상태 | 다음 종료 근거 |
|---|---|---|
| `A_solver=DG` / B06, R2–R3 | IMPLEMENTED_SCOPED | 같은 face 계수로 solve/update/residual 연결; 실제 723,638행 및 작은 가변계수·경계 검사의 Intel O0/O2 근거는 [교정 기록](LEGACY_OPERATOR_CLOSURE_20260918.md) |
| RHS·influence 목표 / B01–B03, MR-C2 | IMPLEMENTED_SCOPED | RHS `-D(y)`; beta는 mobility/support. 외곽·terrain·지원 경계의 제안 상태 유량 고정; 전체/native 물리 승인은 아님 |
| 성분·호환 진단 / M05, M07 | IMPLEMENTED / INCOMPATIBLE | 과거 3개 부적합 성분과 별도로, 첫 폐합의 222개/171 영행 이후, 수평 mobility 위치 정렬로 8개/4 영행. 현재 8개 모두 부적합. 인증 실패·비영 부적합 RHS는 사전 거부; 후속 물리 제약 설계 OPEN |
| P0-4 실제 residual 로그 / B06 | INSTRUMENTATION_IMPLEMENTED | 최종 lambda 잔차·delta lambda·실제 U/V/omega 및 전체/지원 pressure 잔차의 분리 계측 구현, 합성 검사에서 검증. 실자료는 preflight RMS/max/위치와 실패 시 적용 증분 0만 확인했으며, 수렴한 최종 lambda 또는 승인 after의 계측 근거는 없음 |
| 같은 NE57의 비영 ON 생성 / R3 | PREFLIGHT_REJECTED / ON_BLOCKED | 수평 위치 정렬 후 같은 실자료의 전체 Intel O0/O2 실행 모두 8개 부적합으로 exit 1·무게시. [후속 근거](LEGACY_SUPPORT_ALIGNMENT_20260918.md) 참조. 물리적으로 정당한 경계/support/제약 설계 후 재실행 필요 |
| 최종 A-grid/native 전후 / MR-C4 | NOT_RUN | 마지막 변환·startup·halo 후 실제 상태와 질량·열역학·omega/W 대응 |

근거: [보존한 수학·기상학 검토](LEGACY_BALANCE_MATH_REVIEW_20260917.md).
실제 입력은 `2026-08-16 13 UTC`이며 PR #24의 역사 후보 재현과 이번 비영 balance
목표를 같은 성공으로 세지 않는다. 기존 분석을 재사용했으며 3차원 분석 프로그램을
새로 실행했다는 주장은 하지 않는다. 작은 합성 기상장 또는 다른 시각 seed로 대체하지 않는다.

P0-1/2 공동 설계→P0-3 경계·호환 정책 및 P0-4 실제 잔차 검증→수렴/비영 후보→최종 상태 비교
순서다. 실제 residual 진단은 P0 구현과 함께 준비한다. 레이더 시각/Barnes 계보 및
native 경로 조사는 병렬이며, 미완료 물리 후보를 게시하지 않는다. 현재는 수정된
전체 상태/고정 경계 문제의 실제 부적합이 확인돼, 물리적 경계 유량·support·제약
선택의 후속 설계가 필요하다. 검사 구현 완료를 호환성 통과로 바꾸지 않는다. 반복 상한 증가,
허용오차 완화, 영증분 대체는 종료 근거가 아니다.

## PR #27 후속 승인·인증 점검

기준 `5f39fff`. 이전 연산자·RHS 폐합의 제한적 인정과 실자료 8개 부적합을 구분한다.
[후속 검토·실행 기록](LEGACY_FACE_GATE_REVIEW_20260918.md)에 재현, 수정 및 검증 근거를 남긴다.

| 항목 | 종료 조건 | 상태 |
|---|---|---|
| P0 실제 face 최대증분 | beta=0 저장 위치의 X/Y 12 m/s 보정을 빠짐없이 계산하고 10 m/s gate로 거부 | PASS_SCOPED |
| P1 약결합 인증 | edge별 상대 상세균형 검사; 비가역 4행은 UNRESOLVED, 가역 약결합은 인증 가능 | PASS_SCOPED |
| 실제 8개 성분 해석 | 해석적 이산 가중치 인증·signed 경계 결함 수지; 같은 초기 제안과 배경의 계측·분해 | PASS_SCOPED / TARGET_OPEN |
| 경계/source 또는 증분 목표 | 관측·배경 근거, 변경 권한·오차·상한·승인식과 해 존재 조건 확정 | OPEN |
| 팀 검토·Intel 검증·PR | 지적사항 조치·현재 소스 Intel 검증·팀 검토 완료; PR 게시와 비영 ON 승인 구분 | REVIEWED_SCOPED |

## PR #28 후속 경계·실현 가능성 점검

두 기존 승인·인증 지적은 위 `PASS_SCOPED`를 유지한다. 변경은 같은 이산 문제의
안전한 거부와 읽기 전용 진단을 보강하며 새 경계 권한을 부여하지 않는다.

| 항목 | 종료조건 | 상태 |
|---|---|---|
| P2 NaN influence | finite 검사 후 min/max; pinned Intel O0/O2에서 중단 없이 status=0 | PASS_SCOPED |
| 제외된 이웃의 실제 이유 | 지면 아래/sentinel/support 중첩을 분리하고 큰 기여 face·donor 좌표 기록 | DIAGNOSED_SCOPED |
| 단일 감쇠·증분 목표 | 같은 graph에서 성분별 결함 평가; 자동 해소가 아님을 명시 | DIAGNOSED_SCOPED |
| 허용 조정 목록 | face/source별 물리·자료 근거, E, 단위, 양쪽 행, 오차·상한 | OPEN |
| 상한 포함 성분 문제 | 진단용 support omega로 호환 가능; 생산 E/권한은 미확정 | DIAGNOSED_SCOPED / POLICY_OPEN |
| 전체 행·총 증분 상한 | 원래 A의 비제약 해는 상한 위반; bounded 유량 후보는 별도 조건부 진단 | DIAGNOSED_SCOPED |
| 수신 before/변화/after | 고정 79,316행·저장 후보·같은 D로 평가; Intel O0/O2 절차 대조 | DIAGNOSED_SCOPED |
| 수신 공동 수지 | 공유 receiver를 한 번만 센 7개 결합 집합의 필요조건 | DIAGNOSED_SCOPED |
| 공유면 산술 반올림 | PR31 정상 순환·오류 주입 회귀; 독립 검토 폐합 | PASS_SCOPED |
| 수신 행별 비악화 필요조건 | 정확한 활성 목표에서 7개 결합 집합 중 4개 위반; 상한 최적화로 해소 불가 | DIAGNOSED_SCOPED |
| 실제 물리 경계 입력 | 12/13/14 UTC LSX/FSF 시간·단위·해시 확인; 13 UTC LSX PS와 snapshot PS 동일 | EVIDENCE_REVIEWED |
| 물리 경계 재구성 경로 | 지면기압 시간변화+수평 이류·실제 face 매핑을 우선; 오차·권한은 별도 필요 | SELECTED / NOT_AUTHORIZED |
| 지면·저장 face·부분층 대응 | 실제 ps와 stagger 위치·incident 행을 읽기 전용으로 기록; 물리 권한과 분리 | DIAGNOSED_SCOPED / NOT_AUTHORIZED |
| 기주·상단·측면 연결 | legacy 기주 합 검증·상단 2500/5000 Pa 차이 확인; 물리 경계항 미확정 | DIAGNOSED_SCOPED / PHYSICAL_OPEN |
| 시간 계약 | 사후 LSX 중심차분·발행시각 가용 자료·예보 prior 구분 | DOCUMENTED / AVAILABILITY_OPEN |
| 비활성 수신 영역·가중 목적함수 | 최종 잔차 범위·관측 비용·권한·총 상한을 포함한 전체 문제 확정 | OPEN |
| 비영 ON·native·예보 | 위 정책과 해 존재 조건을 만족한 실제 후보 검증 | BLOCKED / NOT_RUN |

## 승인 후 구현 체크리스트 (2026-09-15)

사용자가 승인한 계획을 기준으로 아래 실행 체크리스트를 팀 검토한 뒤 개선한다.
기존 45개 요구사항과 MR 상태를 대체하지 않는 구현 작업 기록이다. 첫 묶음은 독립적인
B06 legacy P0이며 MR-C2/C3 전체 완료를 요구하지 않는다. native 통합의 MR 선행조건은 유지한다.

| 구현 체크포인트 | 실행 항목 / 완료 근거 | 현재 상태 |
|---|---|---|
| 팀 사전 검토 | GREEN/RED GO; 생산 루틴과 caller fragment의 8개 배열 원복을 검증하며 full BALCON 증거로 확대하지 않음 | GO |
| B06 legacy P0 | 네 pressure 미분 부호, 같은 donor의 전체/배경 omega 차이, 실패 시 balcon 원상복구 | IMPLEMENTED_SCOPED |
| B06 생산 루틴 검증 | pinned ifx O0/O2: affine, 영섭동, U/V 각 연직항 단독 비영, 결측 donor, 입력 불변; 실제 caller wind 계약과 실패 fragment 확인; 아래 범위 한정 | PASS_SCOPED |
| B06 P1 pressure 연결 | 원래 pressure-affine U/V→실제 balstagger→nonlin; wind-pressure donor 좌표·중복 상단 처리 검증, 곡률·수렴 별도 미검증 | PASS_SCOPED |
| B06 P1 terrain donor | active target의 양쪽/한쪽 bnd donor 검출, 유효 0 수용, terrain target skip 및 실패 전파 확인 | PASS_SCOPED |
| B06 P2 원복 검출력 | snapshot 후 OM/OMO 포함 보호 배열 변경→실패→원복; 각 복원문 삭제 변이 검출 | PASS_SCOPED |
| B06 P1 가변 omega collocation | PR #11 병합 기준 `f55c0b1`; 실제 forward→nonlin에서 pressure-distance weights, top endpoint, zero-weight donor의 산술·유효성 검사 제외, required invalid reject+rollback 검증 | PASS_SCOPED |
| E03 native 준비 | 마지막 startup 및 첫 solve 전 경계 호출망 조사 중; time level/derived state 연결과 raw·seed 실행 증거는 미완료 | IN_PROGRESS |
| B06 합성 BALCON 연결 | 실제 forward→전체 BALCON→reverse, 비영 승인과 PHI 비수렴 후 원복; 실자료 main/writer·native 제외 | PASS_SCOPED |
| CP02 첫 synthetic writer/readback | 승인된 6×6×4 역변환 후보→`write_bal_laps`→`write_laps_data`→NetCDF와 독립 six-field/metadata readback; 보정된 private CDL fixture | PASS_SCOPED |
| CP02 synthetic writer→실제 LAPSPREP | 실제 reader의 여섯 배열·WPS 다섯 pressure field와 명시적 변환 확인; cold WPS 초 보존 확인, native 시각은 OPEN | PASS_SCOPED |
| CP02 Lambert 공간 metadata | 실제 static 원점·간격·투영값→WPS 전달과 finite/양수 조건; remapping 제외 | PASS_SCOPED |
| E03/M07 native 소비 | 새 stage·payload/geometry/실제 U/V 차이·footprint·하부 W·최종 저장 후 질량/경계 검사 | NOT_RUN |
| E03 native 회귀 | W 단독 영증분/전체 영변경/물리 변경 분리; 유효 비영 전달·geometry/지원 밖/중복/중단 거부; 진단 비침습성 | NOT_RUN |
| MR-C0/C1 병렬 조사 | 실제 레이더별 Vr·기하·시각·QC·Barnes 계보 및 남은 연직 정보; 외부 omega target을 필수로 추가하지 않음 | IN_PROGRESS |

- [x] 팀 사전 검토의 차단사항을 닫고 첫 코드 묶음을 시작한다.
- [x] 생산 코드 변경은 작은 기존 함수/호출 경로에 한정하고, P1 비균일 고차 정확도는 별도 기록한다.
- [x] donor 결측·실패를 0의 성공으로 만들지 않고 원본/입력·최종 게시를 보호한다.
- [x] 시험은 새 실제 scratch cwd와 pinned Intel profile을 사용한다. 추출 루틴, caller 확인,
  source compile, native 실행의 증거 범위를 나눠 기록한다.
- [ ] 구현 후 독립 팀 검토·관련 회귀를 통과한 묶음만 원본에 반영하고 Graphify를 증분 갱신한다.
- [x] 한 묶음의 제한적 통과를 CP02·MR-C4/C5/C6 전체 PASS로 승격하지 않는다.

### 첫 구현 묶음 — legacy P0 제한 범위 검증

- 기준: PR #9 `d25faf9`. 생산 `qbalpe.f` SHA256:
  `0bd45cb1e2423c80b5f4fbdee8c681fba7e69c60292ab6c40677bfa45a0b7b60`.
- 팀 사전 GREEN/RED GO 뒤 구현; 독립 소스·시험 검토에서 차단사항 없음.
- `bash tests/run_qbal_nonlin_tests.sh`: pinned ifx O0(runtime checks) 및 실제 O2 PASS.
  O2는 최적화를 비활성화하는 `-check all`을 제외하고 pinned 부동소수점 설정을 유지한다.
- 균일/비균일 pressure-affine, 영섭동, U/V 각 연직항, 이질 donor, 필수 donor NaN,
  terrain skip 및 입력 불변을 생산 `nonlin` 추출본에서 확인했다.
- 실제 caller의 wind 섭동 변환·호출·실패 복구 구간을 추출하여 비영 omega 차이와
  결측 시 8개 최종 배열의 bitwise 동일성을 확인했다. OM/OMO는 snapshot 후 변경되지 않아
  PR #10 당시 두 복원 분기는 미행사였다. 아래 후속 시험에서 이 공백을 보강했다. continuity/relaxation 및 전체 BALCON 실행은 아니다.
- `tests/run_tests.sh`의 core/source gates 및 기존 `run_qbal_acceptance_tests.sh` PASS.
  전체 unit suite, native consumer/startup, 실자료 예보는 이번 묶음에서 실행하지 않았다.
- 로컬 실행 근거: `scratch/cp02_approved_20260915/Cloud-BAL/scratch/`의
  `nonlin_final.log`, `nonlin_validation.json`, `source_gates_final.log`, `qbal_acceptance.log`.
  B06 전체 및 CP02/MR 상태는 유지한다. P1 비균일 고차 정확도와 native 계약은 후속이다.

### PR #10 당시 후속 종료조건 (PR #11에서 제한적 PASS_SCOPED로 기록)

기준 `2316cfe`: 당시 기존 P0 제한적 통과와 아래 세 후속 조건을 기록한다. 실제
`balstagger` pressure 연결, active terrain donor, OM/OMO 원복 검출력은 PR #11 병합
`f55c0b1`에서 각각 제한적 `PASS_SCOPED`로 유지·기록한다. 상세 계약과 반례는 상위
계획의 PR #10 역사 절을 따른다. GNU 교차검증은 사용자 제공 외부 근거이며 자체 ifx
실행과 구분한다.

- [x] 실제 `balstagger`의 한 level 이동 및 중복 상단을 거친 U/V affine 연결시험을 둔다.
  실제 donor pressure·상단 stencil을 고정하고 균일/비균일 내부·상단을 검사한다.
  좌표 정합성은 곡률에 따른 비균일격자 정확도와 별도 판정한다.
- [x] active target의 전체/배경 필수 donor에 양쪽 또는 한쪽 `bnd`가 있으면 검출한다.
  진짜 omega=0과 terrain target skip은 유지하며 개별 재가중으로 누락을 숨기지 않는다.
- [x] OM/OMO 등 보호 배열이 snapshot 후 실제 변경된 상태에서 실패시킨다.
  원본은 복원되고 대응 복원문을 각각 삭제한 변이는 실패해야 한다. caller fragment 범위는 유지한다.
- [x] 각 후속 행은 해당 종료조건의 새 scratch cwd·pinned ifx O0/O2 근거로 갱신한다.
  실제 terrain 지원 영역·발생 빈도 조사는 커널 시험과 별도로 기록하고, 이를 다른 두
  후속 행의 선행조건으로 추가하지 않는다. B06 전체·MR-C4 및 native/과학 검증은 자동 승격하지 않는다.

실행 근거 (2026-09-15):

- 생산 source SHA256: `6ab5b0a953eefc9141a6a2a88fc2f663fd6d56fe152877a7a5bd82cc829cfd56`.
- caller는 wind pressure `p(2:nz)`를 전달한다. 마지막 물리층은 후방 차분으로 처리하고
  복제층을 미분 donor에서 제외했다. 공통 `dp`와 다른 balance 연산자는 유지했다.
- 새 scratch cwd의 pinned Intel ifx O0/O2에서 실제 `balstagger` 연결, 균일/비균일
  affine 내부·상단, exact `bnd` 거부 및 유효 0·작은 유한값 수용을 확인했다.
- 각 최적화에서 8개 복원문 삭제 변이를 모두 검출했다. 잘못된 caller pressure 연결,
  terrain 검사 제거, 상단 기울기 변경의 추가 3개 변이도 각각 검출했다.
- `run_tests.sh` source/core gates와 기존 QBAL acceptance PASS. 팀 수학·실패 경로 검토 GO.
- 로컬 근거: `scratch/pr10_followup_plan_20260915/Cloud-BAL/scratch/`의
  `P1_VALIDATION.json`, `p1_nonlin_tests.log`, `p1_source_gates.log`, `p1_acceptance.log` 및
  `p1_mutations_vxqjsdq3/RESULT.json`. 자체 인정 근거는 pinned Intel 실행으로 한정한다.
- 전체 BALCON·전체 unit suite·native startup·실자료 예보 및 실제 terrain 발생 빈도는
  이번 실행 범위가 아니다. 비균일격자의 가변 omega 보간 정합성과 고차 곡률·수렴도
  별도 미검증이다. 세 행의 제한적 통과로 B06 전체나 CP02/MR를 승격하지 않는다.

### PR #11 후속 — B06 P1 가변 omega collocation (PASS_SCOPED)

현재 기준은 merged PR #11 `f55c0b1`이다. 위 PR #10 후속 세 행의
`PASS_SCOPED`는 유지한다. 가변 omega collocation도 아래 신규 시험 범위에서
`PASS_SCOPED`로 기록한다. 이 항목은 기존 B06 범위의 추가 검증이며 새
MR/CP checkpoint ID나 대형 감사 계층을 추가하지 않는다.

- 내부 `omega(k)`는 `p_k`와 `p_{k+1}`의 midpoint이고 wind level은 `p_{k+1}`이다.
  내부에서 동일 가중 double-average를 쓰면 affine omega `c`에
  `c/4*(p_k-2*p_{k+1}+p_{k+2})` 오차가 생기므로 pressure-distance weights를 사용한다.
- total/background는 같은 horizontal pair와 같은 pressure-distance weights를 사용한다.
  정확히 0인 weight의 donor는 산술 및 finite/sentinel/range validity 검사에서 제외한다.
  필수 donor가 invalid이면 renormalization 없이 reject하고 caller snapshot을 rollback한다.
- 최상층은 저장된 `omega(nz)` 실제 endpoint만 사용한다. 상단에서 0 weight인 unused
  midpoint donor가 missing이어도 산술에 사용하거나 유효성 검사하지 않으며, 기존
  `balstagger`, 공통 `dp`, continuity 계약은 유지한다.

실행한 시험은 실제 forward→nonlin에서 constant/affine omega를 U/V의 각 isolated
term (`omega_b*d(delta_u_or_v)/dp`, `delta_omega*d(u_or_v_b)/dp`)별로 uniform/nonuniform
pressure의 interior/top에 적용하는 사례다. total과 background가 같은 varying field라서
delta가 0인 사례, required donor missing의 reject+rollback, zero-weight top midpoint donor
missing의 산술·유효성 검사 제외도 포함한다. 고차 curvature/수렴, full BALCON, native startup/readback, 과학 검증은
계속 미검증이며 아래 제한적 통과로 전체 B06·CP02/MR를 승격하지 않는다.

실행 근거 (2026-09-15, 기준 `f55c0b1`):

- 생산 `qbalpe.f` SHA256: `55722851b4dc1114488d2386b2a8a7138ec18bb1c6ff04f7f4400d5d2fc23b56`.
- 새 scratch cwd, pinned Intel ifx O0/O2에서 기존 세 driver와 확장된 가변 omega 시험 PASS.
  상단 결측/미사용 donor는 helper 시험, 실패 원복은 기존 caller fragment 시험으로 확인했다.
- 최적화별 8개 복원문 삭제 변이를 계속 검출했다. 내부 동일 가중 복원, 상단 평균 복원,
  미사용 donor까지 검사하는 세 추가 변이도 O0/O2 각각 검출했다.
- `tests/run_tests.sh` source/core gates PASS. 전체 unit suite 및 실제 BALCON/native/예보는 미실행.
- 근거: `scratch/pr11_omega_20260915/Cloud-BAL/scratch/`의 `OMEGA_VALIDATION.json`,
  `omega_final.log`, `omega_source_gates.log`, `omega_mutations.log`.
- 최초 비균일 stencil 기대값은 이전 동일 가중 기준이었다. pressure 가중 3/4·1/4에서
  독립 계산한 U=23.25, V=14.375로 교정한 뒤 위 최종 시험을 수행했다.

### PR #14 이후 — A-grid 항별 검출력과 실행 디렉터리

- 기준은 merged PR #14 `fdb5cc2`다. 생산 수치식·acceptance와 기존 PASS_SCOPED는 유지한다.
- 기존 역변환 사례의 수평항은 상쇄되며 RMS/최대 절댓값만으로 omega 부호 반전을
  구분하지 못했다. U 단독 `u=a*x`, V 단독 `v=a*y`의 기대 잔차 `a`와,
  `u=a*x, omega=-0.5*a*(p-p0)`의 기대 잔차 `0.5*a`를 별도로 검사한다.
  혼합 입력에서 omega 부호를 뒤집으면 `1.5*a`가 되어 허용오차 변경 없이 검출된다.
- runner의 실행도 `cd "$variant_root"`를 포함한 subshell 안에서 수행한다.
  실행 지점의 실제 디렉터리를 `run.cwd`에 기록하고 manifest 작성 시 variant scratch와
  일치하는지 검사한다. 컴파일 위치만으로 실행 위치를 주장하지 않는다.
- scratch 진단기 소스의 수평항 누락·omega 부호 반전 변이를 기존 projection 생략·PHI
  대입 누락과 함께 검사한다. 지정된 검사 메시지와 Intel 종료 128을 모두 요구한다.
- pinned ifx O0/O2 정상 2회 PASS, 네 변이×O0/O2 8회 검출이다. 저장소 밖 빈 디렉터리에서
  runner를 호출해 10개 실행의 scratch cwd 일치와 호출자 디렉터리 무출력을 확인했다.
  로컬 근거: `scratch/qbal_balcon.Nsumyf/manifest.json`, `summary.log`, 각 variant의 `test.log`와 `run.cwd`.
- 이 보강은 진단기 항별 검출력과 실행 위치에 한정한다. 최종 출력 전체 질량 폐합,
  실자료 writer·native 소비 상태·예보 검증은 OPEN이며 다음 주요 통합 범위로 유지한다.

### PR #15 이후 — 첫 합성 writer/readback 시험 (PASS_SCOPED)

- 현재 B06 기준은 merged PR #15 `1eebfe1`이다. PR #14의 A-grid 항별 검출력과 실제
  실행 `cwd` 검사는 해당 범위의 `PASS_SCOPED`로 닫혔고 재개하지 않는다.
- 완료된 첫 실행은 승인된 6×6×4 국지 BALCON 역변환 메모리 후보를 실제
  `write_bal_laps` → `write_laps_data` → NetCDF로 연결한 뒤 독립 reader로
  `U3,V3,T3,HT,SH,OM` 여섯 필드, pressure levels, valid time, units,
  all-valid mask를 확인한다.
- `U3,V3,T3,SH,OM`과 shape·pressure-level vector·time·units·mask는 선언된 저장
  표현에서 원소별 정확 일치로 비교한다. `HT`는 `PHI`를 그대로 비교하지 않고
  `HT=PHI/g`, `g=9.80665 m s^-2`의 선언된 변환 결과를 선언된 저장 정밀도에서 비교한다.
  새 threshold나 변환을 임의로 추가하지 않는다.
- 이 작은 writer 시험에는 full main의 `sfctempadj`·rotation·RH 과학 검증과 native
  startup/consumed가 포함되지 않는다. native consumed는 다음 별도 단계이며 이 시험의
  선행조건이 아니다. 최종 출력 전체 질량 폐합과 native/예보는 OPEN이다.
- pinned ifx O0/O2 정상 BALCON 2회와 기존 변이 8회 검출을 유지했다. 승인된 국지 후보는
  little-endian float32 stream으로 내보내고 정상 실행 manifest에 SHA256을 묶었다.
  O0/O2 후보 SHA256은 모두 `a1ef61ef6c8c0a5d0de894c3c064679382148a6e4bc11e4e031c3222a68efe9c`다.
- 실제 `write_bal_laps`, `write_laps_data`, `rwl_v3.c`, pinned `ncgen`으로 새 scratch에서
  파일을 생성했다. `get_config/get_directory/get_pres_1d`와 static navigation은 합성 metadata다.
  RH는 별도 50% fixture이며 수분/열역학 정확해로 해석하지 않는다.
- pressure는 후보의 `[100000,90000,80000,70000] Pa`에서 파일의
  `[700,800,900,1000] hPa` 순서로 바뀐다. 이 층 대응과 float32 `PHI/9.80665`를 반영한
  여섯 필드의 비트 일치, dimensions·units·시각·all-valid mask·층별 inventory를 확인했다.
- 원본 `lt1.cdl`의 Kelvin 온도 `valid_range=0..100`은 실제 재읽기에서 280 K를 가렸다.
  기존 `tools/stage_cp02_metadata.py`의 정확한 reviewed transformation을 재사용해
  private CDL의 stale 온도/RH 범위만 제거하고 변경 내역을 기록했다. 범위를 새로 맞추거나
  reader의 mask를 끄지 않았다. 원본 CDL·운영 입력은 수정하지 않았다.
- 최초 O0/O2 명명 디렉터리에서 actual writer/readback 2회 PASS와 네 파일 변이×2회
  검출을 기록했다. PR #16 추가 검토에서 fixed-form O2에 `-check all`이 남아
  실제 O2 근거가 제한됨을 확인했다. 해당 근거는 아래 수정 후 재실행으로 대체한다.
- 로컬 근거: `scratch/qbal_balcon.r6EmUU/manifest.json`,
  `scratch/qbal_writer.nhlRP8/manifest.json`, 각 최적화의 `writer.log`, `readback.json`,
  `negative_controls.json`, `metadata_corrections.json`. 소스/도구 입력 해시는 실행 전후 대조했다.
- 재실행: `CLOUD_BAL_KEEP_TEST_OUTPUT=1 bash tests/run_qbal_balcon_tests.sh` 후 출력된
  scratch 경로를 `bash tests/run_qbal_writer_tests.sh <BALCON_SCRATCH_ROOT>`에 전달한다.
  전자는 승인 후보를 생성하고 후자는 실제 writer를 새 scratch cwd에서 컴파일·실행한다.
  atomic publication 및 full main 전처리·native 소비는 이번 시험 범위가 아니다.

### PR #16 추가 검토 — 실제 O2와 좌표 유효성 보강 (PASS_SCOPED)

- 기준은 merged PR #16 `664dedc`이다. writer fixed-form O2에서 `-check`와 인자
  `all`을 함께 제거했다. O0 runtime checks와 O0/O2 strict floating-point 계약은 유지한다.
  manifest의 각 level `compiler_argv`는 fixed-form 9개, C 2개, free-form driver 1개의
  실제 컴파일 인자 배열을 기록한다. O2 ifx 인자에 `-check`가 없음을 확인했다.
- `level`, `reftime`, `valtime`은 mask 없음과 finite를 먼저 확인한 뒤 값을 비교한다.
  NetCDF `missing_value` 속성만 추가하는 세 변이는 원시 숫자 바이트 불변도 확인한다.
  실제 NetCDF4 전체 `verify()`에서 기존 reader는 6회 모두 통과시켰지만 수정 reader는
  O0/O2 각각 세 변이를 지정된 mask 오류로 거부했다.
- 새 scratch에서 pinned ifx/icx로 O0/O2 actual writer/readback 2회와 여섯 필드의
  float32 bitwise 일치를 확인했다. 기존 4종+신규 3종 파일 변이×O0/O2 14회 검출,
  BALCON 정상 2회와 기존 변이 8회 검출, 입력 해시 전후 검증도 통과했다.
  reader는 netCDF4 1.7.4 / NumPy 1.26.4다.
- 보존된 로컬 근거(유지 checkout `Cloud-BAL/` 기준):
  `scratch/pr16_validation_20260916/Cloud-BAL/scratch/qbal_balcon.u9xjgE/manifest.json`,
  `scratch/pr16_validation_20260916/Cloud-BAL/scratch/qbal_writer.TKPjE9/manifest.json`,
  같은 writer scratch의 `coordinate_regression.json`과 각 level `compiler_argv.jsonl`.
- 생산 BALCON 수치식·acceptance·허용오차 변경은 없다. 보정된 private CDL과 합성 RH의
  all-valid 전달시험 범위이며 full main, terrain/missing-mask 정합, native consumed,
  원자적 게시, 전체 질량·열역학·예보 검증은 기존 OPEN을 유지한다.

### PR #17 이후 — 실제 LAPSPREP reader 연결 (수치 전달 PASS_SCOPED / 시각 보존 OPEN)

PR #17 `7834b7d`의 writer O2·좌표 유효성 두 지적은 `PASS_SCOPED`로 폐합한다.
독립 검토의 Bash 인자/좌표 검사식 실행과 저장소의 실제 Intel writer/netCDF4 실행
근거를 구분한다. 이번 작업은 기존 R3의 제한적 입력 경계·reader 경로 근거와 R4 전달 준비이며,
R3의 물/열·EOS·밀도·유량 잔차 조건이나 R4/MR-C4 전체 완료가 아니다.

- 검증된 실제 writer 파일을 바이트 그대로 private `lapsprd/balance/`에 전달한다.
  synthetic LSX/static을 추가하고 실제 `lapsprep.f90`, setup/static reader, WPS writer를 실행한다.
- 300 hPa anchor는 optional JAX 보정만 사용한다. JAX 비활성 경로도 중단하던
  무조건 요구를 JAX 활성 조건으로 제한한다. BALCON 방정식·acceptance·허용오차는 변경하지 않는다.
- 수치 기준식과 reader/WPS 값 비교는 `tests/verify_qbal_lapsprep.f90`에 모은다.
  Python은 시험자료·metadata 사전 검사·변이 생성·결과 기록을 담당한다. 기존 PR #17 writer
  검증을 선행 검사로 재사용하되, 새 reader/WPS 수치 기준식은 Fortran에만 작성한다.
- actual cold caller의 출력 인자를 test-only CDF hook으로 관찰한다. 여섯 필드의 pressure
  대응과 float32 값을 검사하며 수분에는 `q/(1-q)` 변환식을 적용한다. 이 hook은 실제 CDF/native writer가 아니다.
- 실제 WPS의 U/V/T/HGT/QV 다섯 pressure field를 검사한다. cold caller의 `w(:,:,1:z3)`는
  아직 omega(Pa/s)이고 surface slot은 LSX `VV`(m/s)다. WPS에는 omega slab가 없다. 이를 native W 전달로 승격하지 않는다.
- reader가 pressure를 얻는 ancillary LH3도 pressure-level 좌표·시각·mask preflight 대상에 포함한다.
  이 Python 사전 검사는 legacy NCVGT 자체의 metadata/mask 검출 능력과 구별한다.
- 시각 제한: 기존 fixture `i4time=2000000000`은 `2023-05-18T03:33:20Z`다.
  A9 파일명과 WPS 출력은 분 단위 `03:33:00`이므로 20초 차이가 있다. 이 동작을
  명시적으로 검사하되 시각 보존 PASS로 간주하지 않는다. 실제 native 연결 전 시각 계약은 OPEN이다.
- 계획 상태 유지: MR-C4, native ready seed→후보→startup/halo 이후 consumed,
  실제 terrain/missing-mask, full main·질량/열역학·초기 충격·예보는 미완료다.

Fortran 기준 검증기 최종 실행 근거 (2026-09-16):

- PR #17 수정 후 writer `qbal_writer.TKPjE9`의 보존 산출물을 hash 검증 후 재사용했다.
  이번에는 writer를 다시 컴파일하지 않고 실제 LAPSPREP reader를 새 scratch에서 컴파일했다.
- pinned ifx O0/O2 각 정상 1회 PASS; 각 12개 artifact 변이 거부와 old-k300 조건의
  실제 caller 중단 검출로 총 26개 대조군을 확인했다. old-k300는 STOP exit 0이어도
  지정 메시지와 산출물 부재로 검출한다. WPS QV slab 손상과 다섯 surface slab 값도 검사한다.
- O0/O2 각 25개 실제 compiler/link argv, build/runtime cwd, 실행 전후 입력 해시를
  기록했다. 620개 산출물 해시를 부모가 재확인했고 reader-state O0/O2 바이트가 일치했다.
  기존 `run_lapsprep_vapor.sh` 전체 회귀도 pinned O0/O2에서 exit 0이다.
- 유지 checkout 기준 최종 근거:
  `scratch/pr17_reader_20260916/fortran_final_20260916/manifest.json`,
  `scratch/pr17_reader_20260916/Cloud-BAL/scratch/pr18_regression_cwd/vapor.log`.
  초기 Fortran 변환 시험의 endian 문자열 잘림에 따른 `WPS open failed` 실행과
  이전 Python 수치 판정 실행은 이 최종 횟수에 포함하지 않는다.
- 재현: `bash tests/run_qbal_lapsprep_tests.sh <PR17_WRITER_SCRATCH_ROOT> <NEW_RUN_ROOT>`.
  `NEW_RUN_ROOT`는 존재하지 않아야 한다. 검증 범위는 pressure-level 배열·WPS 전달 및
  명시된 surface fixture이며, source mask의 native 보존이나 위경도 remap 검증이 아니다.

### PR #20 이후 — 관측 수집 윈도우와 분석장 시각 계약

사용자가 확정한 관측 수집 범위는 분석 기준시각의 **±5분, 경계 포함**이다.
원본 관측시각을 분석시각으로 덮어쓰거나 분석장의 시각 오차로 해석하지 않는다.

- 레이더 LOS 계약은 `abs(observation_time - analysis_time) <= 300 s`를 요구한다.
  실제 구현은 int64 끝값에서도 뺄셈 overflow 없이 비교한다. 하나라도 범위 밖이면
  해당 LOS 묶음을 거부하며, 원본 관측시각과 분석장 field의 valid time을 보존한다.
  이 변경은 LOS 계약의 수용 범위다. 실제 레이더 수집기·Barnes 계보 연결 완료는 아니다.
- 분석장 파일끼리는 ±300초를 허용하지 않는다. cold LAPSPREP의 원본 NetCDF 시각을
  확인하고, WPS header에는 동일한 초를 전달한다. A9 파일명은 검색 키로 사용한다.
- PR #19/#20의 입력 `03:33:20`을 그대로 두고 WPS `03:33:20`을 요구한다.
  원본 시각을 분 단위로 내리거나 기대값을 `03:33:00`으로 바꿔 통과시키지 않는다.
- 이번 시간 전달 범위는 cold WPS다. 관찰용 CDF hook은 native writer가 아니며,
  다른 출력형식·hotstart·실제 metgrid/native 소비 시각은 별도 검증 대상이다.
- PR #19 수치 전달과 PR #20 Lambert metadata 전달의 기존 `PASS_SCOPED`는 유지한다.
  전체 위경도 격자의 자기일관성·remapping·별도 omega/W·최종 consumed 상태와
  질량·열역학·초기 충격·예보 효과는 계속 OPEN이다.

실행 근거 (2026-09-16):

- LOS canonical 계약은 pinned Intel O0/O2에서 통과했다. ±299/300초 수용,
  ±301초 및 분석 field 시각 불일치 거부, mixed radar·int64 극값을 검사했다.
- retained PR #17 writer 파일을 변경하지 않고 fresh scratch에서 실제 LAPSPREP를
  빌드했다. 기본·대체 geometry × O0/O2 정상 4회 통과, 지정 음성 대조군 총 90회
  거부했다. 그중 30회는 Python preflight 없이 실제 실행기에 원본 시각 오류를 넣고
  지정 오류·비영 종료·WPS/CDF hook 출력 부재를 확인한 결과다.
- 최종 근거: `scratch/pr20_time_20260916/run_time_final/manifest.json`, SHA256
  `170c3c8027af34e1fed2499ac38d7a4fa78934bd64f7236cf610d97421a601f0`.
  2,126개 산출물 해시와 입력 해시·수준당 25개 compiler argv를 확인했다.
- PR #20 실행의 여섯 caller 배열과 이번 배열은 바이트가 같다. 모든 WPS 바이트도
  header 시각의 `03:33:00 → 03:33:20` 외에는 같다. 수치식·허용오차는 변경하지 않았다.
- 원본 시각은 단일 record의 NetCDF double 정수초와 선언된 Unix 단위를 요구한다.
  cold WPS 시각 검사는 field-contract 옵션과 무관하게 수행한다. NaN·fraction·결측·단위 오류,
  파일끼리의 시각 차이와 A9 검색 분 불일치는 출력 전 거부한다.

아래 PR #19/#20 당시의 20초 손실·정책 선택 대기 기록은 수정 전 이력이다.
현재 scoped 판정은 위의 LOS 수집 범위와 cold WPS 시각 전달 근거를 따른다.

### PR #19 이후 — Lambert 공간 metadata 전달 검사 (PASS_SCOPED)

PR #19 `cda5b886ca6710153ffce98bcae895b733a27cbe`의 실제 cold LAPSPREP 수치 전달은
`PASS_SCOPED`로 유지한다. 외부 독립 검토는 원본 Fortran oracle의 GNU 합성 실행이고,
저장소의 pinned Intel 실제 LAPSPREP 실행과 구분한다. 그 검토에서 확인한 공간 metadata
검사 공백을 보강하며, 이전 수치 전달 범위를 다시 OPEN으로 되돌리지 않는다.

- Fortran oracle은 해시가 고정된 실제 `static.nest7grid`를 독립적으로 읽어 WPS와 비교한다.
  원점은 `lat/lon(1,1)`이며, source의 `Dx/Dy`는 m에서 WPS의 km로 변환한다.
  longitude 정규화와 `LoV/Latin1/Latin2` 대응을 명시적으로 확인한다.
- 모든 WPS record에서 geometry finite, `DX/DY/EARTH_RADIUS > 0`, `KNOWNLOC=SWCORNER`,
  source-bound geometry의 float32 정확 일치, 분석 `XFCST=0`을 요구한다.
  writer가 선언한 지구 반경은 `6371.229 km`다.
- 보존된 PR #19 pinned Intel oracle로 `DX`, 원점 위도, 반경 NaN, `KNOWNLOC`, `XFCST`
  변이를 재실행해 O0/O2 총 10회 모두 과거 `PASS_SCOPED`였음을 직접 재현했다.
  근거: 이 작업트리의 `scratch/geometry_before/results.json`. 실제 writer 결함의 증거는 아니다.
- 오류 metadata 16개와 기존 수치/metadata 대조군을 함께 검사한다. 다른 static 원점·격자
  간격·투영값을 사용하는 정상 실행도 수행해, source 변화가 실제 reader/writer를 통과하고
  oracle이 기존 fixture의 상수를 정답으로 사용하지 않는지 검사한다.
- 이 범위는 공간 **metadata 전달**이다. 전체 lat/lon 격자의 Lambert 자기일관성,
  metgrid remapping, 실제 native 사용 상태의 지리적 정확성을 검증한 것은 아니다.
- 시각 정책은 별도 선택 대기다. 기존 `03:33:20 → 03:33:00` 20초 손실은 OPEN이며,
  공간 metadata PASS로 시각 보존이나 native W·WW 전달을 승인하지 않는다.

실행 근거 (2026-09-16):

- pinned Intel O0/O2에서 기본·대체 geometry의 실제 LAPSPREP 실행 4회가 통과했다.
  각 수준의 기존 12개 + 신규 공간 metadata 16개 변이는 지정 오류로 거부했고,
  old-k300 중단 2회를 포함해 총 58개 음성 대조군을 확인했다.
- 소스 기대값은 static에서 독립적으로 읽는다. 대체 사례는 Dx/Dy=12000/14000 m,
  원점 위도 45.25°, 원점 경도·LoV=233°(WPS -127°), Latin1/2=44/46°다.
  변경 geometry에서도 여섯 caller 배열은 기본 사례와 바이트가 같다.
- 최종 근거: 유지 checkout 기준
  `scratch/pr19_geometry_20260916/run_geometry_validated/manifest.json`.
  컴파일/link argv는 수준당 25개이며 source와 dependency는 실행 전후 해시로 고정한다.
  source 결측 표지의 NaN을 float32로 축소하며 발생했던 탐색 실패는 최종 실행에서 제외한다.
- 생산 LAPSPREP·WPS writer 수치 코드, 허용오차와 기존 시각 동작은 변경하지 않았다.

형식 근거: [WPS 공식 intermediate format](https://www2.mmm.ucar.edu/wrf/users/wrf_users_guide/build/html/wps.html#writing-meteorological-data-to-the-intermediate-format).

### PR #13 이후 — 비영 잔차·역변환 출력 (PASS_SCOPED / 출력 질량 폐합 OPEN)

- 생산 소스·승인 기준은 PR #13 `1f56aa3` 그대로다. 기존 PHI 비영 승인·늦은 실패 원복을 유지한다.
- 6×6×4 원래 A-grid의 내부 `U(3,3,:)=0.2 m/s`만 변경한다. 정 stagger 뒤 네 측면
  유량이 0인지 검사한다. 각 층 25개 셀 중 두 셀의 발산은 `±1e-5 s^-1`이므로
  초기 RMS는 `1e-5*sqrt(2/25)`다. 이 해석값과 비영 최소신호를 검사한 뒤 기존
  RMS/max 25% 감소 조건을 적용한다. 바람 변경량 기준은 별도 m/s 단위로 둔다.
- pinned ifx O0/O2: 초기 RMS/max `2.8284271e-6 / 1e-5`에서 역변환 전
  `2.3457572e-7 / 7.2383540e-7 s^-1`로 감소했다. 배경 불변도 확인한다.
- 여섯 역변환 출력의 finite와 합성 specific humidity `[0,0.05]`를 검사한다.
  별도 8×8×6 해석해 `u=a*x, v=-a*y`, 상수 omega/q, 정역학 PHI를 실제
  정·역 stagger에 통과시켜 내부 U/V/omega/PHI/q 재현과 A-grid 중앙차분 잔차 0을 확인했다.
  온도는 finite 검사이며 열역학 정확해 또는 고차 수렴의 증거가 아니다.
- 실제 BALCON 출력의 독립 A-grid RMS/max는 `1.3718337e-6 / 4.7921303e-6 s^-1`이다.
  이는 균일 Cartesian/pressure 내부 중앙차분 진단이며 staggered 잔차와 같은 연산자가 아니다.
  **해석해 PASS와 실제 출력의 전체 질량 폐합은 구분하며 후자는 OPEN이다.**
  terrain·일반 비균일격자·경계·native 소비 상태의 검증으로 확대하지 않는다.
- 탐색 중 경계를 건드린 입력은 성공 근거에서 제외했다. 내부 `0.02 m/s` 입력의
  기존 25% gate 거부도 남겼다. 최종 입력은 solver의 `0.01 m/s` 보정 규모보다 충분히
  큰 `0.2 m/s`로 정했으며, 생산 solver나 acceptance 허용치를 완화하지 않았다.
- 최종 projection을 direct copy로 바꾼 음성시험은 O0/O2 모두 기존 continuity gate에서
  거부됐다(`projection_bypass_20260915/summary.log`). 정상 실행은 원본 소스 복원 후 다시 검증했다.
- 근거: `scratch/pr13_residual_20260915/Cloud-BAL/scratch/balcon_output_verified.log`.
  `balcon_output_candidate.log`/`balcon_output_final.log`는 각각 제외한 경계 입력/작은 신호 거부의
  탐색 기록이며 최종 PASS 근거가 아니다. 전체 unit suite·실자료·native·예보는 재실행하지 않았다.

### 2026-09-16 재검토 — 역변환 갱신 누락 검출

- 위 2026-09-15 해석해는 출력 배열을 기대값으로 미리 채워 PHI 대입 누락에도
  O0/O2 연결시험이 통과했다. 이는 시험 검출력의 허점이며 생산 PHI 오류의 재현은 아니다.
- 원래 A-grid 배경을 유지하고 staggered 후보에 알려진 상수 증분을 더한다.
  내부 U/V/PHI/q/omega가 각각 배경과 다른 해석값으로 갱신되는지 검사한다.
  온도는 finite 범위만 확인하며 열역학 정확해 검증으로 확대하지 않는다.
- omega 증분 `0.1 Pa/s`와 원래 하단 배경 사이의 차이 때문에 중앙차분 잔차는
  `k=2`에서만 생긴다. 최대 절댓값 `0.1/(p(1)-p(3))=5e-6 s^-1`,
  RMS `5e-6/sqrt(nz-2)=2.5e-6 s^-1`를 독립 기대값으로 검사한다.
  잔차를 0으로 만드는 입력만으로 연산자를 검증하지 않는다.
- 승인 전후 U/V 측면 경계의 최대값·변경량(m/s), omega 양 끝 층의
  최대값·변경량(Pa/s)을 따로 기록한다. 경계를 고정하거나 전체 질량 수지를 검증한 것은 아니다.
- runner는 원본에서 추출한 scratch 소스에만 최종 projection 생략과 역변환 PHI
  대입 누락을 각각 적용한다. 정상 실행의 성공과 각 변이의 지정된 검사 실패를 구분한다.
  실제 BALCON 출력의 전체 질량 폐합·실자료 main/writer·native·예보 검증은 OPEN이다.
- 최종 pinned ifx O0/O2 정상 2회 PASS, 두 변이×O0/O2 4회 검출이다.
  변이는 Intel `ERROR STOP` 종료 128과 해당 거부 메시지를 모두 요구한다.
  근거는 로컬 `scratch/qbal_balcon.F4pa3u/manifest.json` 및 각 실행의 `test.log`다.
  runner는 컴파일 전 소스·실행기·toolchain·setvars·compiler·runtime 해시를 수집하고
  실행 후 불변을 확인한다. 전체 unit suite·실자료·native·예보는 이번에 실행하지 않았다.

### PR #12 이후 — 작은 전체 BALCON 연결 (PASS_SCOPED)

- 기준: merged PR #12 `cea70d0`; 생산 `qbalpe.f` SHA256
  `e38758be0dac93402e198bc2e1d91ed30469a94ee6d0f2d7f13d5a864b4bcbe7`.
- `tests/run_qbal_balcon_tests.sh`는 생산 DIAGNOSE 이후 루틴 전체와 실제 wind-mode,
  move/zero/array-diagnosis 유틸리티를 컴파일한다. 수치 routine을 stub으로 대체하지 않는다.
  fixture의 6×6 격자 metadata, missing 값, timer 네 함수만 시험용으로 공급한다.
- 6×6×4 합성 입력에서 실제 정 stagger→BALCON(continuity, nonlin, PHI relaxation,
  최종 projection, acceptance)→역 stagger를 실행했다. 최대 바람 증분은 약
  `1.2452605e-4 m/s`, 역 stagger 전 continuity rms/max는 `1.1829953e-16 / 3.1862092e-16`이다.
  이는 작은 합성 사례의 수치 결과이며 허용오차나 운영 영향의 제안이 아니다.
- finite PHI 비수렴(`itmax=1`)은 continuity 호출·PHI 섭동 구성 및 첫 relaxation 뒤
  실패하며, 작업/관측 8개 배열과 고정 배경의 bitwise 원복/불변을 확인했다. 이 사례는
  실패 전에 PHI가 변경된다. 8개 배열 모두가 변경됐다는 뜻은 아니며, 각 복원문 검출력은
  기존 caller fragment의 8개 삭제 변이로 별도 유지한다.
- 확장 실행에서 진단 omega의 `ksmx+1>nz`와 역 stagger의 `.and.` 조건 내 `p(k+1)`
  상단 접근을 실제 Intel O0에서 검출했다. 진단 level 상한, forcing 최대 절댓값 기록,
  `destagger_x`의 별도 상단 guard로 수정했다. 두 bounds 수정 제거 변이는 O0에서 각각 검출했다.
- pinned ifx 새 scratch cwd의 O0/O2 연결시험 PASS. 기존 nonlin 세 driver 및 8개 원복문
  삭제 변이 O0/O2, source/core gates도 PASS. 전체 unit suite는 재실행하지 않았다.
- 근거: `scratch/pr12_balcon_20260915/Cloud-BAL/scratch/`의 `BALCON_VALIDATION.json`,
  `balcon_final.log`, `bounds_mutations.log`, `nonlin_regression.log`, `source_gates.log`.
  `balcon_initial.log`/`balcon_second.log`는 수정 전 bounds 실패 근거다.
- 실자료 input/main/writer와 NetCDF 게시, native seed/consumed, 초기 충격·RN1/PTY 예보는
  미검증이다. 이번 전체 routine의 작은 연결시험으로 B06 전체·CP02/MR를 승격하지 않는다.

### native N0 호출 위치 조사 (실행 미검증)

Pinned host 소스에서 준비 완료 seed 후보는 `module_wrf_top.F`의 마지막
`start_domain(head_grid,.TRUE.)` 반환 직후다. 더 이른 입력 중의 startup 호출을
seed 완료로 간주하지 않는다. 첫 `solve_interface` 앞의 `med_before_solve_io`가
지정 경계를 다시 갱신할 수 있어 consumed 검사는 그 처리 이후에 둔다.
U/V/W 두 time level과 PH/PHB, MU/MUB, WW 및 metric/지속 상태의 관계를 함께 확인한다.
현재 staged-file W consumer의 재읽기는 host 메모리의 이 상태들을 검증하지 않는다.
Generated input 경로에서 fresh 파일 `W`는 `w_2`에 읽히고, `w_1`은 첫
`small_step_prep`에서 `w_2`로 동기화된다. Restart에는 이 fresh 계약을 적용하지 않는다.
첫 `med_latbound_in`은 W/U/V/PH/T/MU 경계 버퍼를 읽으며, 그 호출만으로 W 전체장을
직접 덮지는 않는다. 이후 solver의 경계 처리가 후보를 바꿀 수 있다.
적용 지점 후보는 첫 경계 입력 반환 후 `solve_interface` 직전이며, seed capture는
마지막 `start_domain` 반환 후로 구분한다. 실제 specified/경계 알람·파일과 후보 변경 후
halo 재교환, 첫 small-step 전후 readback을 확인하기 전 실행 경로 확정으로 집계하지 않는다.
이 조사는 N0 실행, 정상 seed, E03/MR-C4 통과 증거가 아니다.

## MR-C0 — 기존 관측과 분석장 연결

담당: 레이더 입력/자료 경로. 최초 사례: 2026-08-16 12 UTC.

- [ ] 원본 디렉토리의 관측별 처리자료·통합자료에서 레이더별 Vr가 보존된 위치를 확인한다.
- [ ] Barnes U/V에 사용된 레이더·관측시각·QC·보간/반복 경로와 연직/낙하 성분 처리를 추적한다.
- [ ] Vr 부호·단위, 결측·dealiasing/Nyquist, 실제 관측시각과 위치·빔 방향의 근거를 확인한다.
- [ ] cloud/hydrometeor·T·수증기·압력·geometry·입자수의 실제 입력과 질량분모를 연결한다.
- [ ] Cloud-BAL의 현재 merged U/V·dBZ 입력과 필요한 LOS 입력 확장의 차이를 기록한다.
- [ ] state/validator/stage payload의 LOS 계약과 기존 OFF 호환성을 검토한다. 임의 sigma나
  가짜 동시시각으로 계약을 통과시키지 않는다.
- [ ] 외부 모델 omega/`w` target은 요구하지 않으며, Barnes 초기 분석장은 독립 prior가
  아닌 background/시작값으로 기록한다.

통과: 실제 파일·변수·시각·좌표·QC에서 다음 단계로 사용할 입력을 재현할 수 있다.
정보 부족은 필드/영역별로 표시한다. 이미 쓰는 관측 전체를 “자료 없음”으로 처리하지 않는다.
근거 출발점: 기존 입력·지원 영역 조사 (로컬 작업공간 근거: `../scratch/cp02_balance_reanalysis_20260914/support_inventory.md`).

## MR-C1 — 남은 연직 정보와 낙하속도

담당: 관측 기하/역문제. 선행: MR-C0.

- [ ] 고도별 레이더 수·빔 교차각·연직 민감도·유효 rank와 조건수를 계산한다.
- [ ] Barnes가 이미 흡수한 성분을 고려한 잔존 연직 연산자와 오차 공분산을 평가한다.
- [ ] 조건부 보정 또는 원 관측을 한 번 사용하는 공동 분석 중 구현할 경로를 선택한다.
- [ ] 실제 Barnes 선형화·교차공분산을 재현할 수 있을 때만 조건부 경로를 선택하고,
  그렇지 않으면 raw Vr를 공동 3성분 목적함수에 한 번만 넣는다. 공동 분석도 poor
  geometry/rank를 고치지 않는다.
- [ ] 조건부 경로는 공분산의 양의 준정부호성·유효 rank·특이 부분공간 처리 근거를 갖춘다.
  이를 복원할 수 없으면 원 관측 1회 경로로 전환하고, 미완료 상태를 관측 W로 승격하지 않는다.
- [ ] `w-Vt`와 공기 W를 구분하고, 혼합상·PSD·입자형상·대표성 및 공통 Vt 오차를 반영한다.
- [ ] 같은 Vt 오차가 여러 빔에 작용할 때 레이더 간 상관을 포함한다. 종간 분산 0을
  전체 낙하속도 오차 0으로 해석하지 않는다.
- [ ] 합성 sanity check의 `0.412213%`를 unknown-horizontal 대 known-horizontal의
  조건부 연직 정보비로 기록한다. 이는 Barnes 99.6% 손실률이 아니다. 독립 Vr
  `sigma=1 m s^-1`, exact Vt fixture의 조건부 표준편차 `약 238.6 m s^-1`도
  합성 계산값으로만 기록하고 실제 sigma/Vt 불확실도로 사용하지 않는다.
- [ ] scan age·레이더 간 시차·가능한 폭풍 이동·빔 부피를 5 km 모델의 표현 규모와 비교한다.
- [ ] 약한/중복 빔의 알려진 해를 확인하고 관측 가능·약제약·불가 영역을 분리한다.

통과: 각 영역에서 관측이 제약하는 성분과 물리/낙하속도 가정이 정하는 성분을 설명할 수 있다.
단일 snapshot의 생애주기 불명은 그 자체로 물리 진단 금지 조건이 아니다.

## MR-C2 — 전체 상태의 국지 결합 균형

담당: 방정식/수치 연산자. 선행: MR-C1; MR-C3와 함께 확정.

- [ ] 건조공기 전체 질량식·허용 질량 경향·pressure carrier 변환을 명시한다.
- [ ] 지형 하단·모델 상단·측면과 보정 영역의 경계 유량을 정의한다.
- [ ] 연결 성분·column별 raw mass budget을 평균 제거 전에 검사한다.
- [ ] 고정 U/V·경계·지원 영역이 양립하지 않을 때의 최소 보정/범위 변경/실패 처리를 정한다.
- [ ] 수상체 core와 전이 영역을 별도 물리 mask로 정의한다. target authority나 기존
  radar-derived `hydro_support`의 의미를 바꾸어 재사용하지 않는다.
- [ ] W 국지화와 pressure/환류 영향 범위를 구분하고 최종 W에 beta를 곱하지 않는다.
- [ ] 엄밀 제약과 오차 허용 목적, 변수별 단위·척도, rank·실현 가능성·수렴·rollback을 정한다.
- [ ] 최소 비선형 반복 후 T/Q/P·밀도·geometry와 실제 저장 상태의 잔차를 다시 검사한다.
- [ ] canonical 등압면과 native C-grid의 잔차를 구분하고 기존 공유 face 보존 구조를 활용한다.
- [ ] unknown 수(`n_unknown`)와 자유도 목록, 등식/부등식·허용오차, 지형/상·하단/측면
  경계, rank·호환성·feasibility·rollback을 별도 R2 결정으로 기록한다. 현재 결정은
  `PENDING`이다.
- [ ] 질량 경향은 `data`/`fixed_quasisteady`/`bounded_estimation` 중 하나를 근거와
  함께 선택하며, 사후 `mdot=-DF`로 잔차를 지우지 않는다. 건조질량 식은
  `d rho_d/dt + div(rho_d V)`의 full `rho_d V`를 유지하고, 이산 증분
  `delta(rho_d V)=rho_d,b*delta V+V_b*delta rho_d+delta rho_d*delta V`를 포함한다.
- [ ] R2 결과를 independent control, diagnostic, fixed, constraints, native checks로
  분리하고 native checks를 닫힌 native formulation이나 solver 완료로 기록하지 않는다.

R2 범주별 기록은 다음처럼 정의한다.

| 범주 | 기록할 항목 | 상태 |
|---|---|---|
| 독립 제어변수 | 실제 최소화 제어변수(예: R2에서 선택한 U/V/W 증분), 개수·저장 위치·stagger | PENDING |
| 진단변수 | 종속적으로 계산한 W/omega/WW/Phi·pressure와 변환·provenance | PENDING |
| 고정 입력 | 선택한 terrain·time·boundary·geometry·basis 등 고정 입력 | PENDING |
| 제약식 | mass/EOS/thermo 관계와 support·경계·rank·feasibility·rollback | PENDING |
| native checks | source 식·units·stagger와 최종 array의 mass/EOS/thermo/metric 잔차·readback 검사; native 폐쇄식은 미확정 | PENDING |

통과: 물리적으로 가능한 제약 집합과 실패 판정이 명확하며, 증분 폐쇄를 전체 상태
폐쇄로 혼동하지 않는다. 이론상 계약 확정과 실제 수치 검증 완료는 별도로 기록한다.

## MR-C3 — 상변화와 중력파 제어 기준

담당: 열역학/미세물리·역학. 선행: MR-C0; MR-C2와 함께 확정.

- [ ] 응결·증발·증착·승화·동결·융해와 수상체 하중 변화의 부호·단위·예산을 구분한다.
- [ ] 내부 상변화, 관측 물/열 증분, 좌표 재분배, 미세물리 경향을 각각 기록한다.
- [ ] 유한 delta_q·엔탈피를 임의 시간으로 나누어 가열률 또는 W를 만들지 않는다.
- [ ] 실제 downstream 미세물리의 포화·혼합상·입자수·시간간격 계약을 확인한다.
- [ ] 변경 후 EOS·밀도·기압경도·Phi·부력·하중·바람의 정합성과 보존 기준을 정한다.
- [ ] 첫 미세물리 계산에서 상변화의 중복/누락·과도한 재조정을 확인할 진단을 정한다.
- [ ] 안정/중립/불안정 및 습윤 상태에 맞는 파동 진단을 정한다. `w=S_b/N²`나
  모든 수직 가속도 0을 일반 조건으로 사용하지 않는다.
- [ ] 음향파·내부 중력파를 구분할 출력 주기와 공간 규모, 가열/냉각·부력·압력/바람의
  전파·위상관계 및 비교 기준군을 정한다.
- [ ] 실제 잠열 응답·대류·냉기류·지형성 파동 보존 기준을 함께 정한다. 감쇠 강화나
  잠열 제거·임의 ramp로 충격 검증을 통과시키지 않는다.

통과: “파동이 작다” 이상의 판정이 가능하도록 입력 불일치와 물리 강제 응답을 구분하는
사전 기준이 있다. 기존 실제 5 km/20초 설정과 음향 subcycle·상단/감쇠 조건을 결속한다.
수치 상한이 미확정이면 이 체크포인트는 완료하지 않는다.

## MR-C4 — 실제 FORTRAN과 적분 전 전달

담당: 구현/native I/O. 선행: MR-C2 및 MR-C3.

- [ ] 실제 사용하는 기존 FORTRAN 경로에 작은 단일 목적 변경으로 연결한다.
- [ ] PR #11의 B06 pressure 연결·terrain donor·원복 검출력 세 `PASS_SCOPED`를 유지한다. B06 P1 가변 omega collocation은 실제 forward→nonlin에서 검증하고, 루틴 PASS를 MR-C4 전체 완료로 대체하지 않는다.
- [ ] 전체/배경 omega의 donor·가중·유효성 기준을 공유하고 결측 sentinel의 가짜 영섭동을 거부한다. 두 연직 이류항의 단독 비영 사례를 U/V 각각 검사한다. P1 비균일격자 곡률·수렴성은 P0 부호·선형 일관성과 별도 기록한다.
- [ ] baseline/staged candidate/geometry/increment/mapping을 actual native P/PB·PH/PHB·U/V·W 및 필요한 질량·좌표·metric에 결속한다. 시각·위경도·shape 일치만으로 수용하지 않는다.
- [ ] raw 불변 입력과 N0 준비 완료 seed의 관계를 고정한다. 실제 routine의 호출 전후·W time level·질량/geometry/지속 상태·완료된 경계/halo 처리·후보 적용 후 재개 지점을 pinned host에서 확인한다. raw W=0과 부적합 ready W를 구분하고 같은 ready 단계에서 Cloud-BAL 증분을 계산한다.
- [ ] 실제 변경된 native U/V 지원 영역이 W mapping의 검증된 stagger·보간 footprint 안에 있는지 확인한다. 지원 밖 변경은 거부 또는 관련 U/V/W 전체 rollback한다.
- [ ] raw/seed/pre-W/post-W/consumed와 payload의 역할을 기존 receipt에 결속한다. 매번 불변 준비 완료 seed에서 존재하지 않는 새 private stage를 만들고 candidate 변경을 재구성한다. 기존 경로 덮어쓰기·실패/중단 stage 재사용·동일 stage 중복 적용을 실제 경로에서 거부한다.
- [ ] native CF·map factor·경계 stencil의 B로 seed W_s=B(U_base,V_base)를 검사한 후, 저장된 candidate U/V로 최종 하부 W를 재계산한다. 변경 지원 영역과 물리·연산·입력 오차를 구분한 epsilon_s로 검사하고 startup 후 W_s=B(U_consumed,V_consumed)를 재확인한다. 상쇄 사례에 bitwise 일치를 강제하지 않는다.
- [ ] 변경 U/V를 참조하는 B stencil의 출력 영역만 기록하고 영역 밖 W는 seed와 동일하게 유지한다. raw 원본 불변은 별도 검사한다.
- [ ] 영증분 fixture를 구분한다: W consumer 단독은 다른 입력·geometry·설정이 같고 진입 후보가 경계에 맞을 때 바람 영증분에 대해 W와 비-W 필드의 pre/post 동일성을 검사한다. 전체 pipeline은 모든 제안 변경이 없을 때만 ready 기준·후보 전체 동일성을 요구한다. 물리 변경 후보는 승인 필드·수지·경계 검사로 판정한다.
- [ ] geometry 불일치·mask 밖 실제 변경·중복 적용·부적합 seed의 거부 및 일관된 surface 증분의 양성 사례를 기존 NetCDF 시험에 추가한다.
- [ ] `tests/intel_toolchain.sh`의 pinned ifx로 새 scratch cwd에서 O0/O2를 검증한다.
- [ ] 약한 관측 기하·부적합 질량경계·상변화·결측·저장 정밀도·rollback의 필요한 시험을 한다.
- [ ] canonical/native 잔차, 물/열 예산, 지원 영역과 U/V/W/P/T/Q 변경을 재읽어 비교한다.
- [ ] 하부 W·저장 정밀도·native 경계/halo의 마지막 수정 후 실제 W/WW·질량·metric으로 유량과 전체 질량/하부 경계 잔차를 재계산한다. solver 중간 잔차로 최종 consumed 검사를 대신하지 않는다.
- [ ] `W`, material pressure omega, mu-coupled eta-dot WW와 그 변환 가정을 구분한다.
- [ ] `use_input_w`와 실제 startup/경계 처리 후 **첫 시간전진 전** W 및 결합 상태를 확인한다.
- [ ] `x_b→initialized t0` 전체 증분과 그 안의 실제 phase operator ledger 종별
  `Δr_phase`·`ΔT_phase`를 analysis/remap/기타 증분과 분리하고, 별도 시간 태그와
  동일 cell/unit을 기록한다.
- [ ] t0 짝진 상태의 buoyancy·pressure·vertical acceleration을 같은 snapshot 단위로
  확인한다. 가속도는 상태·native RHS·mass coupling 변환을 명시한 진단으로 기록한다.
  startup/RHS 평가/MP call index/경계 처리/시간전진을 구분하며 미평가 경향은
  `NOT_EVALUATED`로 남긴다. 첫 미세물리 호출 위치와 전후 수집 지점을 pinned host에서 정하고,
  MR-C5의 진단 준비를 확인한다. 호출 후 결과는 MR-C4 완료조건에 포함하지 않는다.
- [ ] 진단 on/off에서 같은 연산 단계의 주 상태·지속 상태가 동일함을 확인한다. 실제 호출 관찰을 우선하고 추가 물리 호출로 상태를 바꾸지 않는다. 첫 MP 이후 동일성은 MR-C5에서 확인한다.
- [ ] 변경 예정 필드는 후보와 일치하고, 변경 대상 밖 필드와 원본 입력은 보존됨을 확인한다.

통과: 해당 후보의 소스·입력·설정·빌드·readback이 결속되고 적분 전 실제 소비가 입증된다.
기존 unlocalized WW/정지-Phi 진단이나 W-only consumer 시험만으로 완료하지 않는다.
위 2026-09-15 추가 항목은 모두 미완료다. 상세 우선순위와 작은 시험 행렬은
[상위 계획의 9월 15일 보완](CP02_MULTI_RADAR_BALANCED_INITIALIZATION_PLAN_20260914.md)을 따른다.
새 stage 재시도 정책은 설계상 선택했다. 식별 필드·호출 경로·epsilon_s의 세부 확정과
구현·시험은 미완료이며 문서 반영으로 체크하지 않는다.

## MR-C5 — 첫 미세물리와 초기 충격 검증

담당: native 실행/기상학 독립 검토. 선행: MR-C4.

- [ ] 동일 수상체·열역학·모델 설정의 기준군을 고정한다.
- [ ] 시간 적분 전에 기준 상태를 저장하고, 이후 초–분 단위의 필요한 출력만 수집한다.
- [ ] `immediately before first MP→immediately after first MP` 짝에서 종별
  `Δr_extra_MP`·`ΔT_extra_MP`와 buoyancy·pressure·vertical acceleration을
  동일 cell/unit·별도 시간 태그로 재읽는다. 사이의 연산과 인접한 시간전진·경계 처리를
  구분하며, MR-C4의 phase 증분과 extra-MP 증분을 한 차이로 합치지 않는다.
- [ ] 첫 미세물리 호출의 물·열 경향과 과도한 포화/상변화 재조정을 검사한다.
- [ ] MR-C4에서 정한 진단 on/off 동일성을 실제 첫 MP 이후에도 확인한다. 누적 tendency·첫 호출 상태·입자모멘트를 포함하고 진단 파일·실행시간은 제외한다.
- [ ] 호출 전후 순변화를 내부 종전환·sedimentation·지표/경계 유출입·clipping/number 조정·분석 증분과 구분한다. tendency 누적과 실제 state update 시점도 확인하며 정상적인 추가 상변화를 0으로 강제하지 않는다.
- [ ] 같은 호출의 질량기준·단위·강수 증가량으로 `Q_after-Q_before+M_out-M_in-A_Q`를 검사한다. 내부 낙하와 지표 유출을 중복 집계하지 않고 `1.0→0.9 kg + 유출 0.1 kg` 양성 사례를 포함한다. 정확한 native 장부는 상위 계획에 따른다.
- [ ] 압력 경향·발산·수직 가속도·부력·하중과 음향/내부 중력파 응답을 비교한다.
- [ ] MR-C3의 사전 기준과 물리 대류·냉기류·지형성 파동 보존 조건을 함께 판정한다.
- [ ] 필요할 때만 timestep 민감도·해상도 수렴성을 추가 확인한다. 동일 수치를 강제하지 않는다.

통과: 단순 작은 잔차나 파동 감쇠가 아니라 비물리적 초기 조정 감소와 물리 신호 보존을
함께 입증한다. 실패한 후보로 6시간 적분만 늘려 초기화 성공을 주장하지 않는다.

## MR-C6 — 1–6시간 강수·분석장 검증

담당: 검증/기상학. 선행: MR-C5.

- [ ] 기준/내부 질량·균형 진단/레이더 연직 제약의 실제 변경 필드와 같은 설정을 확인한다.
- [ ] 1시간 예측을 해당 시각 분석장·수상체·레이더 구조와 비교한다.
- [ ] RN1의 각 1시간 관측 구간과 모델 누적 차분을 맞춘다.
- [ ] PTY의 실제 생성 경로·코드 매핑·결측을 확인하고 시간별 혼동행렬을 작성한다.
- [ ] 남한 육지 3,688격자만 강수 검증에 사용하며 바다·북한을 제외한다.
- [ ] 0.1/1/5/10 mm/h CSI를 시간별·6개 시간표본 합산으로 계산하고 적중/누락/오경보를 보존한다.
- [ ] 동일 레이더/처리 정보의 시각·계보 중복과 상관 오차를 명시한다. 가능하면 독립
  지상관측으로 보완하되 RN1 미래 시각 검증 자체를 무효화하지 않는다.
- [ ] 개선/악화·위치/강도/형태·사례 한계를 보고하고 기존 OFF/HYDRO/LIQUID 결과와 구분한다.

통과: 사전 고정한 비교에서 효과와 한계를 재현할 수 있다. 수치 실행 완료와 예측 성능
개선은 별도 판정이며, 한 사례의 개선만으로 일반 성능이나 CP02 전체 완료를 선언하지 않는다.

## 사전 기준과 완료 기록

각 기준은 **이름 / 단위·정규화 / 값 또는 근거 있는 판정 규칙 / 출처 / 고정 시점**을
기록한다. 새 값을 임의로 채우지 않는다. 기존 코드 허용오차를 쓰면 정확한 설정/소스를
연결하고 native 적용 가능성을 확인한다.

| 기준 묶음 | 확정 체크포인트 | 필수 내용 | 현재 상태 |
|---|---|---|---|
| 관측 정보 | MR-C1 | rank·공분산·시각/빔 규모·Vt 오차·지원 영역 | 미확정 |
| 보존·수렴 | MR-C2 | raw 질량 budget·경계·native 잔차·물/열·저장 정밀도 | 새 결합 경로 미확정 |
| 파동·상변화 | MR-C3 | 초기 재조정·음향/중력파·물리 신호 보존·출력 주기 | 미확정 |
| 강수 검증 | MR-C6 실행 전 | 영역·시간구간·CSI·PTY 매핑·비교 판정 | 영역/CSI 기존 계약 유지, PTY 등 잔여 확인 |

완료 기록은 체크포인트마다 다음 여섯 항목만 남긴다. 별도 배포용 감사 프레임워크를
만들지 않고 기존 보고서/receipt를 재사용한다.

시험 유형은 서로 대체하지 않는다. `DISCRETE_EXACT_SOLVER`/`INDEPENDENT_SPARSE`는
고정 이산 연산자의 exact·독립 희소 검증, `CONTINUOUS_MMS_GRID_CONVERGENCE`는
제조해의 연속 문제 격자 수렴, `REAL_GRID_SINE_EXECUTION`은 실제 격자 sine 입력의
소비·실행 경로 점검이다. 마지막 유형은 실제 기하 관측 가능성이나 solver/과학 폐합을
증명하지 않는다.

1. 판정과 날짜: PASS / FAIL / IN_PROGRESS / NOT_RUN, 과학/수치 판정의 범위.
2. 입력·소스·설정 및 후보 식별자.
3. 실제 실행한 검사와 사전 기준.
4. 결과표·로그·readback 경로.
5. 실패/제한 및 rollback 여부.
6. 다음 체크포인트와 재검증이 필요한 변경 범위.

현재 재개 위치는 **MR-C0의 레이더별 입력 연결과 MR-C2/MR-C3의 방정식·기준 확정**이다.
MR-C1은 아직 실행하지 않은 선행 단계이며, 방정식의 병렬 검토가 이를 통과시킨 것은 아니다.
관측자료는 이미 사용 중이며, 새 연직풍 경로에 필요한 정보의 보존·전달 범위를 확인한다.

### PR21 이후 실제 metgrid reader 연결

PR21의 LOS ±300초 및 명시적 cold WPS 초 보존은 검토 결과에 따라
`PASS_SCOPED`로 유지한다. 원본 `2023-05-18_03:33:20` WPS 네 파일을
변경하지 않고, 고정한 공식 WPS v4.6.0의 실제 `read_met_module`에 전달하는
독립 실행기를 추가했다. source/빌드/검사 범위는
[metgrid reader 전달 기록](PR22_METGRID_READER_HANDOFF_20260916.md)을 따른다.
전체 metgrid/real 또는 설치된 KLFS 실행파일의 동등성 검증과 구분한다.

전체 metgrid는 `interval_seconds`에 따라 검색명·출력 시각을 줄이므로,
다음 full-domain 실행에서 실제 `met_em`·`wrfinput`의 초를 확인해야 한다.
기존 wind 수집기의 900초 tolerance와 Barnes 유도 U/V의 분석시각 부여는
canonical LOS ±300초 계약과 별도 경로다. 실제 관측 원시시각·수신시각·Barnes
기여 계보, 준비 완료 native seed·omega/W·startup/halo 이후 consumed 검사는
계속 OPEN이다. 과거 2026 실제 native 실행과 현재 2023 합성 후보를 혼합하지 않는다.

고정 Intel O0/O2에서 실제 reader 정상 8회(각 33레코드), 지정 오류 거부 14회와
78개 아티팩트 해시 재검사를 통과했다. 이번 `PASS_SCOPED`는 little endian으로
명시한 공식 WPS reader의 보간 전 반환 상태다. 설치된 KLFS full metgrid/real의
시각·byte order·remapping 또는 native 소비 완료로 확대하지 않는다.

## 2026-09-17 full metgrid handoff (PR23)

The approved base 2023 cold WPS case now has a full serial metgrid test, beyond
the PR22 pre-interpolation reader boundary. A narrow patch preserves exact
seconds while keeping the actual `interval_seconds=300`; aligned legacy names
remain supported. The input WPS bytes are reused unchanged.

The Fortran fixture/reference checks a coherent synthetic inner Lambert C-grid,
source/target sphere radii, nearest source-cell membership, exact analysis time,
pressure/surface roles, scalar fields, and the actual staggered U/V rotation
sequence. See [the full handoff record](PR23_FULL_METGRID_HANDOFF_20260917.md)
for the final pinned Intel run, controls, source pins, and evidence limitations.

This stage does not consume the alternate geometry, run `real.exe`, pass omega
through WPS, or certify native startup/halo state. Real radar selection/Barnes
lineage and the ±300-second canonical contract still need a bridge. Physical
budgets, initialization response, and forecast outcomes remain OPEN. Earlier
writer, LAPSPREP, metadata, and time `PASS_SCOPED` results remain separate.

## 2026-09-17 full real-data domain replay (PR24)

- User scope correction: use the already prepared whole-domain real-data case;
  no synthetic meteorological/static fixture or subdomain is used in this stage.
- The existing `2026-08-16_13:00:00` LAPS analysis and matching background,
  soil/surface/static inputs feed actual full metgrid and real. Mass dimensions
  are 234×282, with 21 metgrid levels and 39 native mass levels (40 interfaces).
- The selected `METGRID.TBL` resolves to `METGRID.TBL.ARW.OML.KWW`; its hash is
  additionally pinned. The old manifest pinned the neighboring OML table.
- Corrected replay `met_em` and `wrfinput` are byte-identical to the prepared
  reference. Existing 3-D analysis reuse and real initialization are confirmed;
  the 3-D analysis programs were not rerun.
- Producer `BALANCE=F`, historical zero wind/omega increments, and the absence
  of wrf.exe startup mean this is not BALCON/omega-W/consumed-state completion.
  Existing interpolation and soil-category fallback behavior is recorded.
- Full details, evidence identity and reproduction: `PR24_FULL_REAL_DOMAIN_20260917.md`.
  Native startup/halo, balance application, observation lineage, conservation
  and forecasts remain OPEN. Prior synthetic PR17–23 receipts retain their
  historical scopes and are not represented as full real-data execution.

## 2026-09-17 actual full-domain balance comparison attempt

- Use the original actual 2026-08-16 13 UTC analysis on all 235×283×22 LAPS
  cells, with the same input copies and operational balance configuration.
  The historical thermo research candidate used in PR24 remains a separate
  replay baseline. No synthetic meteorology or subdomain is used here.
- Current pinned Intel QBAL fails its initial continuity solve at the default
  200-iteration budget. A private 2000-iteration diagnostic also fails without
  changing tolerances, acceptance, or rollback. No balanced files are published.
- OFF LAPSPREP completes. ON LAPSPREP and the actual before/after comparison
  remain NOT_RUN/OPEN because no accepted after state exists. A rejected solve
  is not a zero increment or a successful balance result.
- The Fortran full-grid comparison utility reports differences and mask counts;
  its O0/O2 self-comparisons use actual fields and are smoke checks only.
- Evidence and unresolved scope: [actual balance comparison record](REAL_BALANCE_COMPARISON_20260917.md).
  Native before/after consumption, separate omega/W delivery, conservation,
  and forecast response remain OPEN. PR24 replay PASS_SCOPED is unchanged.

## 2026-09-21 PR #33 후속 공유 pressure 유량 연구

- `surface_layer`의 마지막 pressure 구간 검색을 수정하고 endpoint 회귀를 추가한다.
- [새 연구 코드 및 실자료 기하](PRESSURE_SHARED_FLUX_KERNEL_20260921.md):
  하부 부분층·유한 상단, 공유 유량 incidence와 가중 adjoint를 Fortran으로 검증한다.
- 실제 66,505개 기주 기하와 공유 2,583,082개 구간은 GEOMETRY_ONLY다.
  경사진 face의 비공유 구간, 실제 바람 보간·회전·metric은 아직 연결하지 않았다.
- 생산 D/G·RHS·경계 권한·상한은 유지한다. 비영 ON 및 native/예보는 OPEN이다.

## 2026-09-21 PR #34 후속 경사진 면 재구성

- [실행 기록](SLOPING_PRESSURE_FACES_20260921.md): 실제 좌표·PS에서 131,976개
  삼각 기주의 셀별 일정장·affine metric 폐합을 검증했다. 기존 생산 기하 변경은 없다.
- 실제 LW3 공통 지면 위 표본으로 198,480개 면의 조건부 측면 유량을 적분했다.
  모든 면의 지면 근처 미계산 구간을 별도로 보존한다. 전체 물리 잔차는 null이다.
- source 풍향 설정과 역사적 실행 metadata의 확인, 지면 표본·PS 시간경향·상단
  omega 연결은 OPEN이다. 수직 layer remap·K·속도증분 상한·ON/native 승인은 후속이다.

### PR36 — 지면 pressure 경향 연결

- [x] 소수초를 절삭하지 않는 정확한 정수초 입력 검사.
- [x] 같은 삼각 기주에서 사후 지면 법선 항과 압력 체적 변화율 일치.
- [x] 알려진 부분합과 미정 전체 잔차 분리; COM 상단 결측을 0으로 대체하지 않음.
- [x] 같은 격자 LW3 OM의 조건부 상단 적분을 COM 결측 경로와 별도 기록.
- [ ] 하부 측면 profile·상단 omega의 물리적 표본/좌표 계약.
- [ ] 완전한 기주 수지·새 후보·ON·native·열역학·예보 승인.

실제 결과와 한계: `docs/PHYSICAL_COLUMN_TERMS_20260921.md`.

### PR37 — 조건부 하부 표본과 구간 외곽 수지

- [x] LSX 10 m–LT1 pressure 표본의 명시적 연구 보간; 지면으로의 외삽 없음.
- [x] PS/높이 역전 위치의 미지원 보존, 같은 고유 face의 조건부 하부 적분.
- [x] 12/13/14 수송 Simpson 평균과 12–14 지면 체적 secant의 시간구간 정렬.
- [x] 내부 미정 공유면 상쇄와 외부 미정 face 개수 분리; 전체 잔차 NaN 유지.
- [ ] 높이 datum·하부 profile·0–10 m 수송의 물리 권한과 오차 근거.
- [ ] 연속시간 적분오차·독립 상단 prior·완전한 기주 수지.
- [ ] 새 균형 후보·ON·native·열역학·예보 승인.

근거: [조건부 하부 적분과 구간 수지](LOWER_TRANSPORT_INTERVAL_BUDGET_20260921.md).

PR37 추가 판정: 단조로운 높이–기압 보간에도 10 m 압력차가 암시하는 온도의
비현실적 극값이 있어 실제 하부 profile은 `NOT_SUPPORTED_FOR_PHYSICAL_PROFILE`이다.
조건부 적분의 수치 통과를 물리 경계 승인으로 올리지 않으며, 다음은 온도·수분·
높이 datum에 근거한 표본 pressure 연결을 확정하는 작업이다.
