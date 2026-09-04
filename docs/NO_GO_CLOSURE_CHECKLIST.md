# Cloud-BAL NO-GO 폐합 실행 체크리스트

기준일: 2026-09-04
문서 유형: 실행 ledger (계획 검토·구현·검증·증거 세대 관리용)
현재 판정: **SHADOW / PROMOTION_BLOCKED / NO-GO**

## 권위와 사용 규칙

승인 판단의 권위 문서는 [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md)다. 이
문서는 그 문서의 항목을 구현 순서와 증거 단위로 쪼갠 실행 ledger이며, 상태를
독자적으로 `GO`로 바꾸거나 운영 권한을 부여하지 않는다. 두 문서가 충돌하면
`RELEASE_CHECKLIST.md`가 우선한다. 각 단계의 체크박스는 코드가 존재한다는
뜻이 아니라, 재현 가능한 exact-HEAD 증거가 해당 gate를 통과했다는 뜻이다.

운영 원본은 항상 불변·입력 전용이다. 실패, degraded, 불완전한 세대 또는
`NOT_READY`는 fallback 물리를 선택하지 않고 운영·과학 승격 후보를 거부한다.
비권위 diagnostic patch는 상태와 nonzero exit를 명시해 보존할 수 있다. 이 ledger의
어떤 단계도 `ACTIVE`를 직접 허용하지 않으며, P8의 모든 조건과
`RELEASE_CHECKLIST.md`의 모든 blocker 폐합이 함께 필요하다.

### 상태 정의

| 상태 | 의미 |
|---|---|
| `IN_PROGRESS` | 현재 팀이 이 단계의 증거를 모으고 있으며 아직 exit gate 미통과 |
| `BLOCKED` | 알려진 blocker가 있어 다음 단계의 승격을 막음 |
| `PLANNED` | 선행 단계 폐합 뒤 시작할 예정이며 아직 유효한 증거가 없음 |
| `DONE` | 이 ledger의 단계 범위가 exact-HEAD 증거로 폐합됨. 운영 승인을 뜻하지 않음 |
| `DONE (SCOPED)` | P1 operational-comparison 범위만 폐합됨. 실행 evidence, 과학 비교, 질량기준, full product 또는 운영 승인을 뜻하지 않음 |

### 진단 종료와 비교 준비를 분리한다

- `diagnostic_exit=0`은 명시된 진단 명령이 입력·구조·수치의 자기
  안전계약을 수행했고, 운영 원본을 변경하지 않았다는 뜻이다. 과학적 비교,
  bundle/current 원자성, mass-basis 일치, full-product provenance 또는 승격을
  뜻하지 않는다. 원자적 게시는 P2에서 별도로 검증한다.
- `comparison_status=NOT_READY`는 진단 실행이 끝났더라도 비교 계약의
  mass-basis, 독립 재계산, provenance, 동일 background 등의 gate가 닫히지
  않았다는 뜻이다. 이 상태에서는 `algorithm_comparison_ready=false`,
  `promotion_eligible=false`를 유지한다.
- 두 값은 동시에 가능하다: `diagnostic_exit=0`이고
  `comparison_status=NOT_READY`인 결과는 유효한 진단 증거일 뿐 비교/운영
  증거가 아니다. `NOT_READY`를 `COMPARISON_GO` 또는 비교 성공으로 덮어 쓰거나
  집계하지 않는다. `diagnostic_exit=0`은 진단 실행 성공으로만 집계한다.

## 단계 요약

| ID | 단계 | 현재 상태 | 현재 판정/다음 승격 |
|---|---|---|---|
| P1 | diagnostic compare 계약·fail-closed | **DONE (SCOPED)** | 13/14/15 UTC operational comparison scope만 폐합; 12 UTC는 `EXCLUDED_HISTORICAL_NOT_AVAILABLE` / `ARCHIVED_OPERATIONAL_LAPS_MISSING`; algorithm comparison·mass basis·full product·promotion/`ACTIVE`는 NO-GO/BLOCKED |
| P2 | provenance / atomicity | **BLOCKED** | TOCTOU·dirfd·세대 원자성 폐합 전 정지 |
| P3 | delta / mass / metrics | **BLOCKED** | `qC-qB` 및 질량분모 계약 전 비교 금지 |
| P4 | independent generation validation | **BLOCKED** | 원천자료 독립 재계산 전 생성 증거 불인정 |
| P5 | physical authority | **BLOCKED** | 경계·wind frame·target 권한 전 과학 승격 금지 |
| P6 | full KLAPS / WPS | **BLOCKED** | 전체 ifx/ABI/writer/link closure 전 full shadow 금지 |
| P7 | 0–6 h science | **PLANNED** | cold-start·held-out 과학 검증 전 운영 금지 |
| P8 | CI / main | **PLANNED** | 필수 check·보호 main 전 최종 GO 불가 |

각 단계는 GREEN/RED 팀의 계획 점검을 통과한 뒤 시작한다. 단계 시작 시
선행조건과 변경 범위를 다시 확인하고, 종료 시 GREEN은 재현성·계약 통과를,
RED는 적대시험·반례 부재를 각각 서명한다. 어느 한 팀이라도 실패하면 상태는
`BLOCKED`이고 다음 단계는 진행하지 않는다.

---

## P1 — Diagnostic compare 계약·fail-closed

현재 상태: **DONE (SCOPED)**
목표: 13/14/15 UTC의 archived operational comparison만 scope로 폐합하되,
진단 성공을 algorithm comparison 또는 운영 후보로 오인하지 않는다.

### P1 operational-comparison 범위 폐합

- [x] operational comparison pair는 정확히 13, 14, 15 UTC만 선언한다.
- [x] 12 UTC pair는 만들거나 대체하지 않고
      `EXCLUDED_HISTORICAL_NOT_AVAILABLE` /
      `ARCHIVED_OPERATIONAL_LAPS_MISSING`으로 기록한다.
- [x] 위 `DONE (SCOPED)`는 P1 scope 선언에만 적용한다. algorithm comparison,
      mass basis, full-product provenance, promotion/`ACTIVE`는 계속
      `NO-GO`/`BLOCKED`다.
- [x] raw SHADOW, upstream replay, manufactured-balance의 12--15 UTC 전수
      계약은 이 P1 comparison scope 변경으로 축소하지 않는다.

범위 폐합은 algorithm comparison 성공을 주장하지 않는다. 실행 증거는
`scratch/candidate/p1-operational-shadow-<source-commit>/comparison.json`,
`scope-manifest.json`, `STATUS.txt`에 scope, exact HEAD, pair-manifest hash,
입력·도구 hash와 exit를 기록한다. `comparison-manifest.json`과
`contract_evidence/READINESS.json`은 pair 구조 검증용이며 독자적인 scope 또는
source-HEAD receipt로 해석하지 않는다.

### 선행조건

- [x] GREEN/RED가 P1 계획과 입력 manifest를 교차 검토하고 범위를 고정했다.
- [x] 원본·live·diagnostic 입력이 독립 snapshot이며 원본은 입력 전용이다.
- [x] P1 pair manifest가 2026-08-16 13, 14, 15 UTC pair만 선언하고,
      `scope-manifest.json`이 12 UTC exclusion status/reason과 pair-manifest
      hash를 함께 기록한다.
- [x] 각 pair의 role/origin, valid time, field inventory, grid, level, unit,
      wind-coordinate, valid-mask hash가 선언되어 있다.

### 대상 파일

- 구현: `tools/compare_operational_shadow.py`,
  `tools/prepare_operational_comparison.py`,
  `tools/validate_shadow_diagnostics.py`
- 계약: `docs/OPERATIONAL_COMPARISON_CONTRACT.md`,
  `docs/RELEASE_CHECKLIST.md`
- 실행: `tests/run_real_shadow_cases.sh`,
  `tests/run_reproduction_comparison.sh`,
  `tests/run_real_shadow_io_contract_tests.sh`

### 체크리스트

- [x] authoritative operational comparison은 정확히 13, 14, 15 UTC만
      허용하고 중복·누락 시각은 fail-closed 한다. 12 UTC는 명시적
      historical exclusion으로만 기록하며 authoritative pair가 아니다.
- [x] scope 밖 시각을 추가하거나 13--15 중 하나를 생략하는 인자로 P1
      comparison 계약을 우회할 수 없다.
- [x] diagnostic 출력은 `DERIVED_DIAGNOSTIC_PATCH`로만 표시하고 full-product,
      operational candidate, scientific authority로 표시하지 않는다.
- [x] no-change는 `COMPLETED_NO_CHANGE` 진단 no-op으로 기록하고, missing field,
      non-finite, mask mismatch, invalid time, path traversal, symlink/hardlink는 거부한다.
- [x] 실패 시 운영 원본은 byte-identical이다. 명시적 debug partial은
      `PARTIAL_DIAGNOSTIC`, exit 3으로만 보존하고 `current`/승인 generation에는
      게시하지 않는다. bundle 전체 atomic publish는 P2에서 폐합한다.
- [x] 결과에 `diagnostic_exit`, `comparison_status`,
      `algorithm_comparison_ready`, `promotion_eligible`를 분리 기록한다.
- [x] `diagnostic_exit=0`이더라도 `comparison_status=NOT_READY`이면 해당
      결과를 승격·비교 GO로 집계하지 않는다.

### 테스트

- `tests/test_operational_shadow_compare.py`
- `tests/test_operational_comparison_prep.py`
- `tests/test_shadow_validator.py`
- `tests/run_real_shadow_io_contract_tests.sh`
- `tests/run_reproduction_comparison.sh`
- 적대시험: exact three operational-comparison hours (13/14/15), explicit
  12 UTC exclusion, reduced/expanded scope, duplicate/missing hour, relative
  path, path swap, no-change, invalid/missing field

### 증거

- `scratch/<generation>/RUN_SUMMARY.json`
- `scratch/<generation>/MANIFEST.json`, `COMMITTED`
- 사례별 validator JSON과 비교 `READINESS.json`
- scoped execution의 exact HEAD, 입력 SHA-256, tool hash와 exit 수치는
  `comparison.json`, `scope-manifest.json`, `STATUS.txt`를 함께 사용한다.
  `comparison-manifest.json`과 `READINESS.json`은 pair 구조 검증에 한정한다.
- 기존 참고: `scratch/green_unit_exact_head.log`는 시험 로그이며 P1 exit
  승인 자체가 아니다.

### 종료/GO gate

P1의 scoped diagnostic gate는 13/14/15 UTC 세 pair가 동일 exact HEAD에서
재현되고, 모든 실패 경로가 fail-closed이며 원본 변경이 0일 때 닫힌다.
12 UTC historical exclusion은 이 gate의 누락 pair가 아니다. 이 scope gate가
닫혀도 `mass_basis_gate=BLOCKED_UNRESOLVED` 또는 독립 provenance가 남아
있으면 최종 판정은 **P1 scope DONE / algorithm comparison NO-GO**다.
P2~P8이 닫히기 전에는 `ACTIVE`를 만들거나 운영장에 candidate를 게시하지
않는다.

### 2026-09-04 범위·실행 evidence 기록

- P1 scope closure: **DONE (SCOPED)**. operational comparison 대상은
  13/14/15 UTC로 고정한다.
- 12 UTC는 `EXCLUDED_HISTORICAL_NOT_AVAILABLE` /
  `ARCHIVED_OPERATIONAL_LAPS_MISSING`으로 보존하며 KLBG/met_em 대체를
  허용하지 않는다.
- exact-HEAD scoped 실행은 정확히 13/14/15 UTC를 처리하고
  `diagnostic_exit=0`, `comparison_status=NOT_READY_MASS_BASIS_UNRESOLVED`,
  `algorithm_comparison_ready=false`, `promotion_eligible=false`여야 한다.
- 따라서 P1 scope만 DONE이며 algorithm comparison·mass basis·full-product
  provenance·promotion/`ACTIVE`는 계속 NO-GO/BLOCKED다. P2 구현·승격은 해당
  별도 gate와 새 execution evidence 전까지 진행하지 않는다.

---

## P2 — Provenance / atomicity

현재 상태: **BLOCKED**
목표: 검증한 byte와 게시한 byte가 동일하고, path 교체·foreign staging·crash
중간 상태가 증거 세대를 오염시키지 않도록 한다.

### 선행조건

- [ ] P1의 13/14/15 UTC comparison manifest와 role/origin 계약이 고정되어
      있다.
- [ ] 원본 archive/live/current의 inode·hash·세대 식별 정책이 합의되어 있다.
- [ ] GREEN/RED가 hostile filesystem 가정과 failure-injection 목록을 승인했다.

### 대상 파일

- `tools/cloud_bal_transaction.py`
- `tools/prepare_operational_comparison.py`
- `tools/compare_operational_shadow.py`
- `tests/test_output_transaction.py`, `tests/test_state_atomic_refresh.f90`
- `tests/run_transaction_gate.sh`, `tests/run_isolation_gate.sh`
- `docs/OPERATIONAL_COMPARISON_CONTRACT.md`

### 체크리스트

- [x] 정규 generation은 schema 2 context와 staging 외부의 local begin receipt를 요구하고,
      owner 없는 schema 1 generation은 current 검증에서 거부한다.
- [x] generation metadata/product inventory를 `O_NOFOLLOW` dirfd와 동일 fd의
      `stat/hash/read`에 결속하고, generation·부모 inode 변경을 거부한다.
- [x] generation rename은 `RENAME_NOREPLACE`로 기존 target을 덮어쓰지 않고,
      current 임시 symlink의 target·inode 및 게시 직전 product 재검증을 요구한다.
- [ ] operational/archive 입력도 동일 fd의 `stat/hash/read` snapshot으로 고정한다.
- [ ] 외부 writer가 사용하는 `resolve_output()` pathname을 안전한 writer/import
      API로 교체하고 retained writable-fd 위협을 제거한다.
- [ ] 전체 bundle을 staging에서 검증한 뒤 한 번의 atomic rename으로 게시한다.
- [ ] symlink component, hardlink/shared inode, parent traversal, pathname
      replacement race를 거부한다.
- [ ] pipeline/tool/source commit과 입력·결과 hash를 서로 독립 receipt로
      기록한다.
- [ ] crash·disk-full·permission·foreign staging failure에서 current가
      이전 유효 세대로 유지되거나 게시물이 없어야 한다.

### 테스트

- `tests/test_output_transaction.py`
- `tests/run_transaction_gate.sh`
- `tests/run_isolation_gate.sh`
- `tests/test_operational_comparison_prep.py`
- 적대시험: symlink/hardlink, rename race, directory replacement, interrupted
  staging, foreign generation ID, stale lock

### 증거

- atomic publish receipt, generation ID, parent/current inode snapshot
- 입력·staging·게시 후 재읽기 SHA-256 목록
- failure-injection log와 이전 current 보존 확인
- `RUN_SUMMARY.json`, `MANIFEST.json`, `COMMITTED`의 동일 generation 결속

### 종료/GO gate

모든 적대시험에서 검증 대상과 게시 대상이 동일 fd/hash로 결속되고, 실패 후
부분 세대가 보이지 않을 때 P2를 닫는다. P2 미폐합 상태에서는 어떤 `exit=0`
진단도 provenance-authoritative evidence가 아니며 `ACTIVE`는 금지된다.

schema 2 전환은 fail-closed migration이다. 기존 schema 1 `current`를 자동
승계하거나 현장에서 고쳐 쓰지 않으며, runner는 비어 있는 새 publication root에
exact-head generation을 다시 생성해야 한다. 현재 보장은 publication root를 쓰는
동일 UID의 임의 공격 프로세스를 신뢰하는 모델이 아니다. 해당 위협은 writer API와
실행 계정/권한 격리가 완료될 때까지 P2 blocker로 유지한다.
Local begin receipt는 구조적 결속이며 인증·서명 증거가 아니다.

---

## P3 — Delta / mass / metrics

현재 상태: **BLOCKED**
목표: diagnostic absolute replacement와 operational background 사이의 차이를
Cloud-BAL 증분으로 잘못 해석하지 않고, 동일 질량기준에서 변경량·통계를
재현한다.

### 선행조건

- [ ] P1/P2의 pair identity와 byte-stable input snapshot이 완료되었다.
- [ ] `qB`(diagnostic background), `qO`(operational background), `qC`(candidate)의
      정의·단위·분모가 명시되었다.
- [ ] WPS가 `kg kg-1 dry air`인지와 Cloud-BAL canonical basis의 변환식이
      독립 자료로 확인되었다.

### 대상 파일

- `tools/compare_operational_shadow.py`
- `tools/prepare_operational_comparison.py`
- `docs/OPERATIONAL_COMPARISON_CONTRACT.md`,
  `docs/IMPROVEMENT_PLAN.md`, `docs/QBAL_REAL_INPUT_CONTRACT.md`
- `tests/test_compare_baseline.py`, `tests/test_operational_shadow_compare.py`

### 체크리스트

- [ ] `delta=qC-qB`, `qP=qO+T(delta)`를 명시하고 absolute patch를
      increment로 조용히 재명명하지 않는다.
- [ ] `qB==qO` 또는 검증된 basis transform을 사례별로 증명한다.
- [ ] WPS moisture denominator와 canonical dry-air/pressure mass를 field-level
      receipt로 기록한다.
- [ ] changed-only RMS, P50/P90/P99/P100, max neighbor jump와 dry-air mass
      적분을 all-domain 통계와 분리 게시한다.
- [ ] finite↔missing, mask-only change, sparse large increment, species별
      변경을 숨기지 않고 exact mask/hash로 비교한다.
- [ ] 질량 보존 실패·분모 불일치·basis 미확정은 `NOT_READY`로 종료한다.

### 테스트

- `tests/test_operational_shadow_compare.py`
- `tests/test_compare_baseline.py`
- `tests/test_qbal_real_input_manifest.py`
- `tests/run_qbal_acceptance_tests.sh`
- 적대시험: `qB!=qO`, denominator mismatch, all-domain finite but changed-only
  outlier, valid-mask transition, unchanged field with changed metadata

### 증거

- case별 `MASS_BASIS.json`, delta/mask/quantile statistics
- independent dry-air mass integral and species ledger
- `READINESS.json`의 `mass_basis_gate`, `comparison_status`,
  `promotion_eligible`
- 변환을 사용한 경우 식·계수·입력 hash·반올림 정책 receipt

### 종료/GO gate

P1의 13/14/15 UTC scoped pairs 모두에서 basis가 해소되고 independent mass
ledger가 허용 오차를 만족하며 changed-only 지표가 게시될 때만
`ALGORITHM_COMPARISON_GO` 검토가 가능하다. 현재 mass basis는 BLOCKED이며,
이 단계가 완료되기 전 candidate는 진단 patch이고 `ACTIVE`는 금지된다.

---

## P4 — Independent generation validation

현재 상태: **BLOCKED**
목표: generation/tool이 작성한 `D/G/L/target`과 수치 JSON을 같은 구현의
자기검사에 의존하지 않고 원천자료에서 독립 재계산한다.

### 선행조건

- [ ] P2의 immutable generation과 P3의 mass basis/metric 정의가 완료되었다.
- [ ] validator 구현·pipeline 구현·source/tool commit을 별도 identity로
      기록할 수 있다.
- [ ] 사례별 target, boundary, pressure interface, mask, input provenance가
      세대 내부에 self-contained로 저장된다.

### 대상 파일

- `tools/verify_real_manufactured_balance_generation.py`
- `tools/validate_real_manufactured_balance.py`
- `tests/run_real_manufactured_balance_cases.sh`
- `tests/real_manufactured_balance_driver.f90`
- `tests/test_shadow_validator.py`, `tests/test_balance_operator.f90`
- `docs/REAL_GEOMETRY_DYNAMIC_BALANCE.md`

### 체크리스트

- [ ] validator 입구에서 per-case numerical JSON 의미와 schema를 재검증한다.
- [ ] 원천 입력으로부터 별도 구현의 `S`, `D`, `G`, `L=-DSG`를 재계산한다.
- [ ] target/support/boundary와 cellwise residual을 독립 계산하고 게시값과
      tolerance 내 일치시킨다.
- [ ] 일관되게 변조한 diagnostic/ledger, case 누락, generation ID·commit
      불일치를 거부한다.
- [ ] manufactured/test-only 권한과 관측/운영 권한을 bitwise로 분리한다.
- [ ] 12/13/14/15 UTC 전 사례의 입력·build·derived receipt가 self-contained다.

### 테스트

- `tests/run_real_manufactured_balance_cases.sh`
- `tests/test_balance_operator.f90`
- `tests/test_balance_omega_authority.f90`
- `tests/test_missing_phase_continuity.f90`
- `tools/verify_real_manufactured_balance_generation.py` 적대 변조시험

### 증거

- 사례별 independent validator JSON 및 재계산 배열 hash
- `RUN_SUMMARY.json`, generation `MANIFEST.json`, `COMMITTED`
- source/tool/validator commit·binary hash와 compiler/runtime receipt
- 실패 사례는 게시되지 않고 staging result와 원인이 보존된 로그

### 종료/GO gate

독립 validator가 네 사례 모두에서 수치·구조·권한·provenance를 통과시키고
변조 적대시험을 거부할 때 `FULL_SHADOW_GO` 검토로 이동한다. 제조해 권한은
과학 증거가 아니므로 P4 완료만으로 `ACTIVE`를 허용하지 않는다.

---

## P5 — Physical authority

현재 상태: **BLOCKED**
목표: 경계조건·관측 target·바람 좌표계·storm motion·동역학 authority를
수치 경로와 분리하여 물리적으로 검증한다.

### 선행조건

- [ ] P4 independent generation validation이 완료되었다.
- [ ] target의 `R_w`, 자료 나이, driver provenance, confidence 계약이 있다.
- [ ] pressure interface, terrain height, PSFC, no-echo/beam/path 의미가
      사례별로 확정되었다.

### 대상 파일

- `src/common/cloud_bal_real_netcdf.f90`
- `src/common/`의 balance/column/trajectory 구현
- `tests/test_column_physics.f90`, `tests/test_nonuniform_localization.f90`
- `tests/run_radar_velocity_audit.sh`, `tools/audit_radar_velocity.py`
- `docs/REAL_GEOMETRY_DYNAMIC_BALANCE.md`,
  `docs/RADAR_PRECIP_DOWNDRAFT_DESIGN.md`, `docs/SCIENTIFIC_BASIS.md`

### 체크리스트

- [ ] terrain kinematic lower boundary와 실제 model-top flux를 복사 경계와
      구분하고 physical continuity를 독립 계산한다.
- [ ] grid-relative/earth-relative wind, storm motion, radar fall-speed frame을
      registry·receipt로 고정한다.
- [ ] no-echo 목적지 hard-block과 beam sensitivity/path coverage를 물리자료로
      검증한다.
- [ ] target의 `R_w`·age·driver provenance 없이는 dynamic authority를 0으로
      유지한다.
- [ ] checkerboard/null mode, conditioning, increment·direction·residual gate를
      실제 geometry에서 평가한다.
- [ ] 수상체 질량 변화가 잠열·부력·water/enthalpy budget에 미치는 영향을
      column contract로 닫는다.

### 테스트

- `tests/test_column_physics.f90`
- `tests/test_nonuniform_localization.f90`
- `tests/test_balance_omega_authority.f90`
- `tests/run_radar_velocity_audit.sh`
- `tests/run_contract_regressions.sh`
- 적대/물리시험: boundary flux, terrain cut-cell, wind frame, beam gap,
  checkerboard target, conditioning, no-echo deposition

### 증거

- physical residual/geostrophic/continuity report
- target authority·wind-frame·radar registry receipt
- boundary flux와 water/enthalpy source-to-sink ledger
- cellwise support/mask와 increment percentile report

### 종료/GO gate

독립 물리 검증이 실제 자료에서 통과하고 target·경계·frame 권한이 명시될 때
`FULL_SHADOW_GO`를 검토한다. P5 전에는 balance가 수치적으로 실행되어도
science authority는 `NONE`이고 `ACTIVE`는 금지된다.

---

## P6 — Full KLAPS / WPS

현재 상태: **BLOCKED**
목표: focused Cloud-BAL 시험을 넘어 원래 KLAPS 호출망과 WPS writer가 동일
ifx/NetCDF/HDF5 계약으로 연결되고, 직접 입력·출력 lineage를 보존한다.

### 선행조건

- [ ] P5 물리 authority gate가 완료되었다.
- [ ] LT1/LQ3/LCO/LSX를 원래 upstream에서 재생성하거나 미생성 사유를
      폐합한다.
- [ ] legacy deriv/cloud bogus-w, AIRDROP, qbal 경로의 운영 권한이 canonical
      transaction으로 대체될 계획과 rollback이 있다.

### 대상 파일

- `tests/run_intel_integration_audit.sh`, `tools/audit_intel_integration.py`
- `tests/run_original_upstream_replay_tests.sh`,
  `tools/original_upstream_replay.py`
- `tests/run_legacy_deriv_safety_audit.sh`,
  `tools/audit_legacy_deriv_safety.py`
- `tests/test_lapsio_abi.f90`, `tests/test_wps_writer_status.f90`,
  `tests/test_writeballaps_status.f90`
- 전체 `src/` canonical adapter 및 legacy KLAPS link 설정

### 체크리스트

- [ ] 전체 binary가 단일 Intel ifx toolchain과 동일 ABI로 clean link된다.
- [ ] NetCDF/HDF5 runtime closure와 WPS intermediate/met_em inventory가
      field-level로 재검증된다.
- [ ] 원래 producer가 직접 만든 LT1/LQ3/LCO/LSX와 upstream hash가 존재한다.
- [ ] legacy 경험적 cloud bogus-w 및 AIRDROP/시간전진 분기가 운영 경로에서
      제거되거나 명시적 fail-closed로 차단된다.
- [ ] 동일 직접 입력에서 legacy/candidate를 독립 실행하고 full transaction,
      input/build receipt를 보존한다.
- [ ] WPS writer 재읽기 결과와 canonical field provenance가 일치한다.

### 테스트

- `tests/run_intel_integration_audit.sh`
- `tests/run_original_upstream_replay_tests.sh`
- `tests/run_legacy_deriv_safety_audit.sh`
- `tests/run_legacy_shadow_adapter_test.sh`
- `tests/test_lapsio_abi.f90`, `tests/test_wps_writer_status.f90`,
  `tests/test_writeballaps_status.f90`
- `tests/run_qbal_acceptance_tests.sh`

### 증거

- clean link manifest, compiler/link/runtime versions, binary hash
- upstream replay manifest와 LT1/LQ3/LCO/LSX hash
- WPS input/output inventory·dimension·unit·source receipt
- full E2E generation `RUN_SUMMARY.json`, `MANIFEST.json`, `COMMITTED`

### 종료/GO gate

전체 KLAPS/WPS가 동일 직접 입력·동일 toolchain으로 재현되고 writer 재읽기와
lineage가 통과할 때 `FULL_SHADOW_GO`를 검토한다. P6 미폐합이면 diagnostic
patch와 focused test를 full-product evidence로 사용하거나 `ACTIVE`로
게시할 수 없다.

---

## P7 — 0–6 h science

현재 상태: **PLANNED**
목표: cold-start 예보에서 초기 조정이 음파·중력파·고주파 발산·표면기압과
수분/엔탈피 budget을 악화시키지 않는지 사전 고정 threshold로 평가한다.

### 선행조건

- [ ] P5 physical authority와 P6 full KLAPS/WPS가 완료되었다.
- [ ] calibration과 held-out manifest를 분리하고 threshold를 실행 전에
      고정·review했다.
- [ ] baseline과 candidate의 초기 상태·physics option·모델 버전이 동일하다.

### 대상 파일

- `docs/SCIENTIFIC_BASIS.md`, `docs/RELEASE_CHECKLIST.md`
- 전체 cold-start forecast driver/config 및 output diagnostics
- `tests/`의 신규 0–6 h integration/science harness

### 체크리스트

- [ ] 청천, 층운/안개, 층상성 비·눈, 혼합상, 대류, 산악·경계, radar 공백을
      포함한 고정 사례군을 실행한다.
- [ ] 0–6 h precipitation, surface pressure, high-frequency divergence,
      gravity/acoustic wave proxy를 baseline과 paired 비교한다.
- [ ] total water, hydrometeor, latent heat, buoyancy, enthalpy budget을
      column·domain 모두 적분한다.
- [ ] held-out 사례와 calibration 사례의 threshold·결과를 섞지 않는다.
- [ ] 실패·missing·unknown source는 평균에 숨기지 않고 사례를 거부한다.

### 테스트

- 신규 `run_cold_start_0_6h.sh` 및 독립 science validator
- baseline/candidate paired replay, wave/acoustic/gravity-wave stress cases
- water/enthalpy budget closure와 output safety regression

### 증거

- 사례별 0–6 h time series·분위수·paired delta report
- calibration/held-out manifest와 고정 threshold receipt
- wave, surface-pressure, moisture/enthalpy budget의 독립 validator JSON

### 종료/GO gate

모든 고정 threshold를 calibration과 held-out 모두에서 통과하고, 실패 사례가
누락 없이 기록될 때만 `ACTIVE` 검토 자료가 된다. P7 이전에는 어떤 수치
개선도 운영 승격의 근거가 아니다.

---

## P8 — CI / main

현재 상태: **PLANNED**
목표: 폐합된 계약을 exact HEAD에서 자동 재현하고, 필수 검사 없는 main
병합과 ACTIVE 게시를 구조적으로 차단한다.

### 선행조건

- [ ] P1~P7의 각 exit evidence가 승인되었고 `RELEASE_CHECKLIST.md`와
      불일치가 없다.
- [ ] 재현에 필요한 입력 snapshot, toolchain, data receipt가 CI에서 접근
      가능하며 비밀·운영 원본은 read-only로 격리된다.
- [ ] GREEN/RED가 required-check 목록과 branch protection 정책을 승인했다.

### 대상 파일

- `.github/workflows/`의 focused-ifx, comparison-adversarial,
  real-shadow-generation workflow
- `tests/run_unit_tests.sh`, `tests/run_contract_regressions.sh`,
  `tests/run_intel_integration_audit.sh`,
  `tests/run_real_shadow_cases.sh`
- `docs/RELEASE_CHECKLIST.md`와 이 ledger

### 체크리스트

- [ ] `focused-ifx-unit` required check가 exact HEAD에서 통과한다.
- [ ] `comparison-contract-adversarial`가 reduced-hours·TOCTOU·mass-basis·
      mask/provenance 반례를 모두 거부한다.
- [ ] `real-shadow-generation-verification`가 네 시각 generation과 독립
      validator/manifest/COMMITTED를 재검증한다.
- [ ] CI 실패 시 main 병합·게시·ACTIVE 경로가 모두 nonzero/fail-closed다.
- [ ] branch protection이 실제 protected `main`에 적용되고 우회 merge가 없다.
- [ ] 모든 check 결과와 evidence generation ID가 release receipt에 기록된다.

### 테스트

- `tests/run_unit_tests.sh`
- `tests/run_contract_regressions.sh`
- `tests/run_intel_integration_audit.sh`
- `tests/run_real_shadow_cases.sh`
- P1~P7의 validator와 failure-injection suite 전체

### 증거

- CI run URL/ID, exact commit SHA, artifact manifest와 hash
- protected branch 설정 export 및 required-check 결과
- release receipt와 최종 GREEN/RED sign-off

### 종료/GO gate

P8의 모든 required check가 protected `main`의 exact HEAD에서 통과하고,
`RELEASE_CHECKLIST.md`의 blocker가 0이며, 운영 원본 격리·rollback·승인
기록이 확인될 때만 별도 release authority가 `ACTIVE`를 검토할 수 있다.
이 ledger만으로는 `ACTIVE`를 선언할 수 없다.

---

## 현재 실행 순서와 금지 조건

1. P1 scope를 먼저 폐합한다. P1 계획·입력·적대시험을 GREEN/RED가 재검토하고,
   operational comparison은 13/14/15 UTC로만 기록하며 12 UTC exclusion을
   확인한다. 이는 실행 evidence나 `comparison_status`의 GO를 뜻하지 않는다.
2. 새 P1 execution evidence가 없으면 P2를 시작하지 않는다. P2~P8은 표의 순서대로
   한 단계씩 진행하며, 각 단계 종료 후 두 팀의 독립 review를 받는다.
3. 어느 단계에서든 원본 변경, missing-to-zero 은닉, provenance 불일치,
   partial generation, 독립 validator 불일치가 발생하면 해당 단계와 이후
   단계를 `BLOCKED`로 되돌리고 새 세대를 게시하지 않는다.
4. `diagnostic_exit=0`, numerical `VALID`, manufactured numerical pass,
   fixed-level plot pass 또는 unit-test pass는 단독으로 `GO`나 `ACTIVE`가
   아니다.
5. P1~P8 중 하나라도 `BLOCKED`/미완료이거나 `comparison_status=NOT_READY`,
   `promotion_eligible=false`, `science_authority=NONE`이면 **ACTIVE 금지**다.
6. 최종 승격 전에는 `RELEASE_CHECKLIST.md`의 모든 `BLOCKED` 항목도 같은
   exact HEAD와 self-contained evidence로 갱신·재검토해야 한다.

### 단계별 승인 기록

| 단계 | GREEN review (이름/일시/commit) | RED review (이름/일시/commit) | exit evidence | 승인 상태 |
|---|---|---|---|---|
| P1 | GREEN scoped execution review / 2026-09-04 / receipt exact HEAD | RED authority review / 2026-09-04 / 동일 | 13/14/15 complete, exit 0; comparison `NOT_READY_MASS_BASIS_UNRESOLVED` | DONE (SCOPED); algorithm/promotion NO-GO |
| P2 | 미기록 | 미기록 | 미완료 | BLOCKED |
| P3 | 미기록 | 미기록 | 미완료 | BLOCKED |
| P4 | 미기록 | 미기록 | 미완료 | BLOCKED |
| P5 | 미기록 | 미기록 | 미완료 | BLOCKED |
| P6 | 미기록 | 미기록 | 미완료 | BLOCKED |
| P7 | 미기록 | 미기록 | 미완료 | PLANNED |
| P8 | 미기록 | 미기록 | 미완료 | PLANNED |
