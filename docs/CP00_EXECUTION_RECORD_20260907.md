# CP00 실행 기록 — 기준선·권한·계약 CI

시작일: 2026-09-07. 작업 상태: COMPLETE. CP00 gate: PASS (격리 연구 계획·기준선·계약 CI 범위).
기존 RELEASE/NO-GO 및 45개 기능 gate는 자동 변경하지 않는다. 아래 중간 상태 기록은 당시 시점의 이력이다.
사용자 지시: 최종 목표까지 한 단계씩 진행하고 토큰 비용을 고려해 서브에이전트를 적극 활용한다.
추가 지시: 단계가 끝나면 KG를 실행한다.

## 범위와 담당 (최초 착수 기록)

이번 실행은 local source/test/CI 정의와 scratch/temp 검증에 한정한다. 운영 ANAL/MODL와
legacy release는 읽기 전용이며 real producer 실행·운영 게시·ACTIVE·원격 repository 설정 변경은 하지 않는다.
기존 [RELEASE_CHECKLIST](RELEASE_CHECKLIST.md)와 [NO_GO_CLOSURE_CHECKLIST](NO_GO_CLOSURE_CHECKLIST.md)의
승인 gate는 유지한다. 사용자 개발 지시를 GREEN/RED 또는 최종 승격의 대리 서명으로 해석하지 않는다.

| 역할 | 이번 실제 수행자 | 권한 |
|---|---|---|
| 구현·로컬 기준선 시험 | Codex primary | 승인된 workspace 내 개발·시험 |
| Portable CI 구현 | cp00_ci (gpt-5.6-luna, xhigh) | 지정 신규 CI/runner 파일만 작성 |
| 계획·파일 접근 범위 독립 점검 | cp00_gate_review (gpt-5.6-luna, xhigh) | 읽기 전용 AI 검토; 인간 승인 대체 아님 |
| GREEN/RED의 공식 단계 승인·최종 release 승인 | 미지정 | 실제 승인 주체 결정 필요 |

모델당 동일 자료 전체 재검토는 피하고 파일 소유권을 나눈다. 새 agent는 독립 산출물이나
독립 검토가 있을 때만 사용한다. 빠른 실행 tier는 이 세션에서 별도 설정할 수 없으며 모델/effort만 지정했다.

## 고정 범위와 필수 불변조건

- 코드 기준 HEAD: `f837bad0bdf1050a34975d93b178b7dee4420094`, tree `2f70cce203d9822b4df9e5c9c28690385846fa11`.
- 시작 worktree에는 이전 설계/체크포인트와 graph 변경이 존재한다. clean exact-HEAD 실행으로 표시하지 않는다.
- 필수 read-only 원본, OFF no-op, SHADOW 원본 동일, 제조해·진단 patch 승격 거부를 기존 시험으로 검사한다.
- P1 historical comparison은 13/14/15 UTC; 12 UTC는 명시적 historical exclusion을 보존한다.
- Raw SHADOW/upstream/manufactured 계약은 12–15 UTC 네 시각이다. 한 unit/reader 사례의 PASS를 네 시각 전체 generation 완료로 표시하지 않는다.
- X01 Barnes 완료는 유지하며 O06 Cloud-BAL 관측 계약의 완료를 대신하지 않는다.

## Threshold·사건·CI 확정 계획

| 항목 | 준비·확정 단계 | 책임 역할 / 승인 |
|---|---|---|
| 자료·컴파일러·시간·mode·원본 identity hard gate | CP00에서 기존 계약 유지, 매 실행 재확인 | 구현/QA, 독립 reviewer |
| native mass/EOS·geometry 허용오차 | CP01, 작은 oracle 시험 평가 전 | native·물리 담당, 과학 검토자 |
| balance/reference·target fit | CP03 실행 평가 전 | 수치 담당, 독립 reference 검토자 |
| 수분/enthalpy 및 outer loop | CP04/CP06 평가 전 | 미세물리·통합 담당, 독립 검토자 |
| 관측오차·검출한계·분모·frame | CP05 실제 사례 평가 전 | 관측 담당, 과학 검토자 |
| held-out 사건/관측 ID·주 효과/비열등 margin·sampling | CP00 설계 착수, O06 계보 후 CP08 실행 전 고정 | 과학 평가 책임자(실명 미지정) |
| p95 시간/메모리·freshness/rejection·복구 예산 | CP00 초안, CP09 평가 전 고정 | 운영 책임자(실명 미지정) |

숫자는 확보한 관측·native 특성·운영 deadline 없이 임의 결정하지 않는다. 실제 필수 threshold가
미정이면 해당 후속 gate는 통과시킬 수 없다. 이번 portable CI는 단계 초기에 실행할 계약 회귀이며
ifx/native/science check를 대체하지 않는다. self-hosted runner에 외부 PR 코드를 자동 실행시키지 않는다.

## 현재 실행과 증거

- 계약 CI: `.github/workflows/contract-ci.yml`와 `tests/run_python_contract_tests.sh` 구현.
  Hosted ubuntu-24.04, read-only contents, immutable action SHA, 고정 Python·binary dependency 버전으로
  8개 기존 Python 계약 시험을 실행한다. [CI 범위](CI_CONTRACT.md)에 제외 항목과 wheel hash-lock 부재를 명시했다.
  원격 등록·실행 및 branch protection 적용은 아직 하지 않았다.
- Portable lane은 workspace 및 운영 자료가 없는 `/tmp`의 독립 local clone에서 exit 0을 확인했다
  (cp00_ci 실행 보고). 실제 로컬 Python은 3.12.3이며 CI가 선언한 3.11.11 실행 증거가 아니다.
  `/tmp` noexec 때문에 clone의 runner는 `bash`로 실행했다. 기존 eight-test logic 외 full ifx/native/science는 제외된다.
  격리 clone은 `/tmp/cloud-bal-ci-clone.eutGLf/Cloud-BAL`이며 runner SHA256은
  `5aaad5a971f8bc8483165a15f6c53a8b8a3fe03a1c5e6e0c92d378a742ef1601`로 workspace와 같다.
  최초 Portable 시험은 별도 로그·종료코드 파일을 보존하지 않아 도구 대화 기록과 agent 보고만 남았다.
  이후 아래 보완 실행은 별도 로그와 receipt를 보존했다. 최초 기록을 소급 인증하지 않는다.
- Pinned ifx 전체 unit suite: `bash tests/run_unit_tests.sh` exit 0 (2026-09-07 02:08:54–02:10:51 UTC).
  `ifx (IFX) 2026.0.0 20260331`, 지정 setvars/compiler/runtime hash 검사를 통과했다.
  source/test/tools/config/schema 추적 파일 124개와 지정 외부 입력·도구 19개의 before/after hash가 같았다.
  이는 제한된 파일 집합의 identity 검사이며 ANAL/MODL 전체 트리를 감사한 것은 아니다.
- 로컬 시험 기록: `scratch/cp00_baseline.f8fopx10/START.json`, `RESULT.json`, `unit_tests.log`.
  Log SHA256: `9a14c354039ae6d3928554da8bc67ccd5509f81e3b981f64eeb44ca8cc488d9d`.
  Receipt scope는 `CP00_LOCAL_BASELINE_NOT_RELEASE_EVIDENCE`, `exact_clean_head=false`다.
  이전 설계/graph의 dirty 상태와 diff hash를 기록했으며 immutable release generation으로 승격하지 않는다.
- 시험에는 현재 legacy와 upstream 실행을 올바르게 BLOCKED로 유지하는 음성 경로가 포함된다.
  12 UTC reader fixture 성공, 4/4 VRT preflight와 dry-run은 네 시각 전체 full SHADOW나 실제 producer 완료가 아니다.
- 전체 CP00: 종료조건별 증거와 실제 승인 주체를 확인하기 전 NOT_RUN 유지.

## 독립 검토와 남은 CP00 종료조건 (최초 답변 대기 시점)

cp00_gate_review의 읽기 전용 검토는 로컬 계약 CI·기준선 시험이 구현 권한 안에 있음을 확인했다.
기존 unit suite의 새 파일은 scratch/temp와 Python cache에 한정되고 운영 입력은 읽거나 복사한 뒤
복사본만 변경한다. CI 경계는 적절하지만 dependency version pin은 wheel-hash attestation이 아니다.
이 AI 검토는 인간의 release/운영 승인이나 기존 단계의 공식 GREEN/RED 서명을 대체하지 않는다.

사용자에게 다음 방식을 확인 중이다: 격리 연구 단계는 독립 AI GREEN/RED 검토로 진행하고,
실제 과학·운영 승격은 사용자에게 남길지, 각 단계마다 사용자 승인을 받을지.
답변 전에는 기존 권위 문서의 선행조건을 변경하지 않으며 CP00 COMPLETE/PASS 또는 CP01 진입을 선언하지 않는다.
원격 CI 실행/보호 main, immutable release evidence, 실제 과학 threshold와 FG1–FG3는 미완료로 유지한다.

## 단계 종료와 KG 규칙

완료조건과 독립 검토를 확인해 checkpoint를 갱신한 다음 KG에 구현 파일·실행 SHA/dirty 상태·
입력/설정·시험 결과·미폐합 항목·다음 CP를 기록한다. 새 소스 그래프는 실제 변경 범위만 갱신하며,
기존 상위 graph shrink guard를 강제로 해제하지 않는다. 미완료 단계의 진행 기록도 남기되 COMPLETE로 바꾸지 않는다.

## 보완 실행 — 2026-09-07 02:23 UTC

격리 clone에서 기존 portable runner를 다시 실행해 누락된 보존 증거를 확보했다.
실행은 02:23:39.130628129–02:23:40.336786856 UTC, exit 0이다. 전체 로그에
8개 시험 파일 실행과 각 성공 결과가 있다. Runner·시험 8개·도구 8개, 총 17개 파일의
before/after hash가 같으며 primary가 보존 로그 및 receipt를 직접 확인했다.

- 보존 사본: `scratch/cp00_portable_copy.zSm8dX/run.log`, `receipt.json`.
- Log SHA256: `951a9d07e144ebd79062410291d15b329561f2ee1a5cf9c134fac4c7cd361eed`.
- Receipt SHA256: `8948c72f6946e9de23c88910309fdcaf2625e7c0eda9c53b426bf3a8c84aa18e`.
- 사본은 원래 clone의 파일과 byte-identical이다. Receipt 내부 절대 경로는 원래 실행 위치를 유지한다.
- Python 3.12.3, NumPy 1.26.4, netCDF4 1.7.4, cftime 1.6.5. CI Python 3.11.11과의
  불일치가 명시되어 있다. Hosted Actions·wheel 공급망·native/science 실행 증거가 아니다.
- 기존 pinned ifx receipt의 추적 입력 124개도 현재 worktree와 hash가 같음을 재확인했다.
- [CI 범위](CI_CONTRACT.md)에 CP00–CP09별 required-check 확장 계획과 역할을 추가했다.
  원격 required-check 적용이나 실제 승인자 배정은 하지 않았다.

남은 진입 제한은 동일하다: 연구 GREEN/RED 검토 방식 및 실제 승인 주체 답변이 없다.
CP00는 IN_PROGRESS/NOT_RUN, CP01은 미착수로 유지한다. 이번 보완은 단계 완료가 아니므로
단계 종료 KG 갱신을 수행했다고 표시하지 않으며, 이전 KG Source의 과거 증거 상태를 덮어쓰지 않는다.

## 사용자 후속 지시와 현재 연구 검토 배정

사용자 후속 지시: **“완료되면 진입”**. 기존 단계별 개발·독립 agent 위임 지시와 함께,
각 CP의 종료조건과 독립 GREEN/RED 검토가 충족된 뒤 다음 CP로 진입하도록 적용한다.
이는 시험 결과를 미리 PASS로 정하거나 실제 과학·운영 승격을 AI가 승인하라는 뜻이 아니다.
위의 승인 방식 답변 대기 기록은 그 이전 시점의 기록으로 보존한다.

| 현재 역할 | 수행 주체 | 범위 |
|---|---|---|
| 격리 연구 책임·threshold 초안 준비·단계 순서 관리 | Codex primary | CP별 근거와 수치값은 해당 시험 전 고정; 연구 결과 자동 승격 금지 |
| QA·CI 구현 | cp00_ci | Portable CI 및 보존 시험 증거 |
| GREEN 독립 검토 | cp00_green | 현재 CP00 종료조건별 재현성·계약 증거 확인 |
| RED 독립 검토 | cp00_red | 현재 CP00 범위의 반례·권한 오인·누락 증거 점검 |
| 최종 과학·운영 승격 및 운영 SLO 인수 | 사용자/별도 지정 승인자 | AI 검토로 대체하지 않음; 실제 필요 시 별도 승인 |

후속 연구 threshold의 준비 책임은 primary, 독립 검토는 해당 CP에 배정한 GREEN/RED가 맡는다.
운영 SLO나 최종 과학 효과 기준은 초안 작성과 실제 인수를 구분하며, 최종 승인자 부재를
AI 서명으로 채우지 않는다. 단계 간 병렬 진입은 하지 않고 같은 단계의 독립 하위 작업만 병렬화한다.
Legacy P1–P8 gate·게시 선행조건은 유지하며 CP00 연구 종료로 자동 변경하지 않는다.

현재는 두 독립 검토의 결과를 기다린다. 결함이 있으면 보완 후 재검토하며, 둘 다 통과해야
CP00 scoped PASS를 기록한다. 이 배정 자체가 완료 증거는 아니다.

### 종료조건별 자료 위치

| CP00 항목 | 현재 확인 자료 | 주장 범위 |
|---|---|---|
| 목표·허용 산출물 | FINAL_GOALS_CHECKPOINTS §1, RELEASE_CHECKLIST 목표/단일 계약, 아래 기능 표 | 설계·권한 구분; 과학 성공 아님 |
| 기준선 identity | `scratch/cp00_baseline.f8fopx10/RESULT.json`, portable receipt | baseline HEAD/tree와 dirty diff 및 열거 입력 hash; clean release 아님 |
| 격리·권한 회귀 | `unit_tests.log` 및 실행된 `tests/run_unit_tests.sh` | 기존 OFF/SHADOW·제조해/patch 회귀; 전체 운영 트리 감사 아님 |
| 시각 manifest | 아래 4개 파일; baseline receipt의 동일 파일 hash | P1 세 시각과 raw/upstream/manufactured 네 시각 분리 |
| CI·담당 | `CI_CONTRACT.md`, workflow, 위 현재 역할 표 | 구현·확장 계획; remote required check 아님 |
| threshold 시점·책임 | 위 threshold 계획 및 현재 역할 표; FINAL_GOALS_CHECKPOINTS §5 | 연구 초안/사전 확정 책임; 미래 gate 자동 승인 아님 |
| 단계 진입 | 사용자 후속 지시, GREEN/RED 결과 및 현재 역할 표 | 같은 단계 안의 병렬 하위 작업만; legacy gate 불변 |

| 기능 | 현재 허용 산출물 | 금지된 해석 |
|---|---|---|
| HYDRO | OFF/SHADOW 수상체 proposal·interface ledger 진단 | full source-to-sink 보존·운영 적용 완료 |
| THERMO | 격리 cell/block 수분·enthalpy 계약 시험 | 전체 native 에너지·부력 결합 완료 |
| DYNAMIC | 권한 없는 실자료 innovation 0; 별도 MANUFACTURED_TEST solver 시험 | manufactured/loading target의 관측 권한·정상 pipeline 승격 |

고정 시각 manifest (모두 기존 baseline receipt에 SHA256이 포함됨):

- `tests/reproduction_cases_20260816.tsv`: P1 13/14/15 UTC.
- `tests/qbal_real_cases_20260816.tsv`: raw SHADOW 12/13/14/15 UTC.
- `tests/qbal_real_manufactured_cases_20260816.tsv`: 별도 수치시험 12/13/14/15 UTC.
- `tests/original_upstream_replay_20260816.json`: 원래 upstream 재생성 계획 12–15 UTC.

12 UTC archived operational LAPS 제외는 `EXCLUDED_HISTORICAL_NOT_AVAILABLE`이며,
나머지 네 시각 계약을 줄이지 않는다. Manifest의 존재·hash는 해당 실제 실행 완료와 다르다.

## 최종 연구 종료 판정

2026-09-07, 실제 독립 검토 결과:

- **cp00_green: PASS** — CP00 일곱 항목의 범위·baseline·기존 회귀·시각 manifest·CI 확장·
  threshold 준비·순차 연구 진입 증거를 확인했다. 원장의 검토/실행/승인 근거 연결을 요구했다.
- **cp00_red: PASS** — 같은 일곱 항목에 대해 범위 축소와 권한 오인을 검토했다.
  Portable 로그는 hosted CI가 아니며 baseline은 신규 CI 추가 전 dirty 상태라는 두 제한을
  PASS와 함께 보존할 것을 요구했다. 더 강한 release/science 해석에는 미충족 증거가 남는다.

Primary는 두 검토 결과, 실제 로그·receipt 및 현재 manifest identity를 대조하여
**CP00 local scoped COMPLETE/PASS**를 기록한다. 검토자 이름은 실제 AI agent 식별자이며
인간 서명이나 외부 독립 기관의 인증을 뜻하지 않는다.

연구 진입 근거는 사용자의 단계별 구현·독립 agent 위임과 후속 **“완료되면 진입”** 지시다.
이 지시에 따라 같은 단계의 종료조건과 양쪽 검토가 통과한 뒤에만 후속 CP로 진입한다.
KG 기록·그래프 갱신 결과를 먼저 남기고 CP01의 격리 계약·oracle 작업을 시작한다.
원격 설정·실제 과학/운영 승격은 별도 승인 대상이며 이 종료 판정에 포함하지 않는다.

종료 연결 증거: `scratch/cp00_handoff_20260907.json`은 실제 실행 receipt와 로그, 현재 신규 CI,
계획·시각 manifest의 hash를 함께 열거한다. 로컬 연구 handoff 목록이지 새 runtime 승인 schema나
immutable release generation이 아니다. 종료 문서의 hash는 실행된 코드의 hash를 대신하지 않는다.
