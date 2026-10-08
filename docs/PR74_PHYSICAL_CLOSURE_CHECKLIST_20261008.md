# PR74 해소 체크리스트 — 2026-10-08

기준 main: `1ae50a87b606614fafc0f647f517d4472efdfc05` (PR73).
작업: 격리된 `fix/pr74-certified-analysis` worktree. 유지관리 WRF/KDM6/PBL
소스와 private profile, 과거 실패 receipt를 보존한다.

**현재 전체 물리 초기화: FAIL/OPEN. 실제 연구 native 후보: REJECTED.**
완료 표시는 아래 범위만 의미한다. 분석 최소해, 성분 회계, driver 반환,
미세물리 첫 호출, 대기장 공동 균형, 예보 시간반응의 판정을 각각 유지한다.

## 이번 해소 항목

| 항목 | 상태 | 직접 근거와 범위 |
|---|---|---|
| P1: 경계 반올림이 최적 하한을 제거하고 반대쪽 상한을 반환 | 완료 | 기존 main의 1.3/cost 2.845를 재현. 활성 좌표를 제거한 reduced solve 후 정확한 0.3/cost 0.545 반환. 최종 clipping 없음. |
| P1: U/V만 m/s→mm/s로 변경하면 SPD 공분산을 특이행렬로 거부 | 완료 | 원문 main의 오류 재현. B와 R을 각각 표준편차로 정규화한 뒤 Cholesky factor solve. 동등한 U/V 해와 비용, KKT 검사 통과. |
| 원문 제약·정류성·승수 부호·상보성 인증 | 제한적 완료 | 최대 8변수 제조 solver의 모든 반환에 인증. primal은 원래 단위, 정류성·bound 승수는 정규화 제어좌표. 물리 tolerance 확대 없음. |
| 고정 bound, active bound와 등식 중복, decimal box-edge | 완료 | 자유 승수, 독립 등식 basis, outward-rounded 불가능성 선별. 수치 실패와 증명된 box 불가능성 구분. |
| 유한 입력의 누적 overflow가 infeasible로 오분류 | 완료 | 과정량·배경+과정량·등식 RHS를 유한성 검사하여 NUMERICAL_FAILURE. |
| 새 solver→Fortran endpoint→NetCDF 성분 readback | 제한적 완료 | 새 scratch에서 pinned Intel O0/O2. 실제 pipeline 미실행의 FAILED/AUTHORITY 유지. 전체 canonical CLI는 UNBOUND/REJECTED. |
| QNI의 실제 Shinhong driver 연결 | 제한적 완료 | 실제 선택 driver/PBL 객체를 O0/O2로 재컴파일·archive member 확인·partialhost relink. 실제 CALL/반환/39층 단일 누적/DRIVER_BRANCH_COMPLETE 캡처. |
| 최초 미소 위반 외 전체 모멘트 규모 | 제한적 완료 | 보존 PR73 raw 전체와 같은 호출 기하에서 유형별 수·최대값·건조질량 가중 규모. 물 생성량이나 수지 폐합으로 해석하지 않음. |
| 에이전트 팀 교차검토 | 제한적 완료 | 독립 oracle, 공통 audit, driver 및 solver를 서로 검토. 발견한 보조 시험 선언 누락·profile 출처·receipt hash 불일치를 수정·재검증. 최종 기록은 팀 resolution 참조. |

## 실제 native와 잔여 종료조건

- [x] 새 QNI 경로의 NI 변환을 정확한 source helper와 pinned Intel O0/O2로 재생했다.
  캡처 NI에는 음수·비유한 값이 없다. `(211,2,15)`의 NI × 건조밀도는 strict
  no-ftz에서 양의 subnormal, FTZ sensitivity에서는 0/invalid다. 실제 partialhost
  link argv의 `-ftz`를 확인했으며 runtime MXCSR·정확한 fatal 좌표는 미캡처다.
- [ ] 완료된 일관된 host build의 표현 정책과 실제 adapter 실패 좌표를 연결한다.
  현재 gate는 wrapper adapter이며 common classifier의 최초 위반은 가상 재생이다.
  `(104,2,1)`을 실행된 fatal 좌표라고 보고하지 않는다.
- [ ] 입력과 완료된 host RK 갱신에서 QI/QNI, QC/NC의 공동 상태를 유지한다.
  같은 선형 연산자라도 binary32 underflow 및 서로 다른 host 갱신은 별도 위험이다.
- [ ] PBL `DEL`과 hybrid dry carrier의 연결, 행렬·RHS·반환 경향·경계항을 폐합한다.
- [ ] freezing의 초미량 QG/BG 생성·활성화·승화·소멸을 하나의 물질·부피·열역학 규약으로 연결한다.
  1000→900 density clamp, floor, 임의 삭제로 대체하지 않는다.
- [ ] 같은 수용 후보의 native 첫 호출을 정상 완료하고 필수 pre/post 산출물을 확보한다.
- [ ] 같은 carrier·시각·계산영역에서 물·수치 정리·경계·강수·에너지 회계를 폐합한다.
- [ ] 독립 H/B/R·배경 prior·관측연산자·변경 권한을 가진 실제 관측 후보를
  `run_cloud_bal_pipeline`의 상태 재구성·평가와 연결한다.
  추정 결과의 analysis ledger를 physical source/boundary/phase와 계속 분리한다.
- [ ] pressure/Phi/면 바람/연속식/경계를 같은 최종 후보에서 평가하고 WPS/metgrid/real 전달을 확인한다.
- [ ] 동일 설정 BASE/HYDRO/COUPLED의 첫 호출 및 10·30·60분 반응과 독립 관측을 비교한다.
  구름·강수·상승류 신호를 제거한 조용한 후보를 성공으로 채택하지 않는다.

## 검증 근거

- [P1 전후 재현](evidence/pr74_reported_p1_reproduction_20261008.json)
- [solver 및 독립 oracle](PR74_CERTIFIED_ANALYSIS_20261008.md)
- [root Python/Intel endpoint 검증](evidence/pr74_validation_20261008.json)
- [실제 QNI driver/partialhost](evidence/pr74_shinhong_qni_driver_20261008.json)
- [보존 pretrace 공통 모멘트 감사](PR74_COMMON_MOMENT_AUDIT_20261008.md)
- [새 QNI pretrace·동일 호출 비교](evidence/pr74_common_moment_audit_20261008/actual_driver_comparison.json)
- [정확한 NI 변환·FTZ sensitivity](evidence/pr74_common_moment_audit_20261008/ni_conversion_probe.json)
- [독립 최종 검토](PR74_INDEPENDENT_FINAL_REVIEW_20261008.md)
- [보존 baseline](evidence/pr74_preservation_20261008.json)

Graphify와 KG는 frozen 변경의 관계를 별도로 갱신한다. KLAPS50과 Cloud-BAL
스냅샷을 각각 날짜·delta와 함께 기록하며, 부분 Fortran CALL/Markdown heading
추출과 외부 native 소스 미추출의 제한을 밝힌다. Graph freshness는 런타임이나
과학적 검증의 근거가 아니다. 완료 후 KG receipt를 별도 publication 기록에 연결한다.

## Graphify/KG 후속 완료

동결 구현 커밋 `d3b1a6e17b2170c3de8bea3e5cdf402b60668114`의 67개 변경경로를
Graphify 0.9.53으로 증분 반영하고 `kg-update`의 derived report/index/log를
동기화했다. 각 corpus의 별도 `2026-10-08-pr74` 스냅샷을 보존했다.

| Corpus | 노드 | edge | 이번 delta |
|---|---:|---:|---|
| KLAPS50 | 34,229 | 74,065 | +116 nodes / +145 edges |
| Cloud-BAL | 8,396 | 15,639 | +116 nodes / +145 edges |

Graph integrity의 missing/duplicate/collapsed edge는 0이다. 원래 dated snapshot,
receipt, 보호 wiki·private-profile 노드를 보존했다. AST/Markdown heading만 추출했으며
semantic refresh를 수행하지 않았다. Fortran cross-file CALL 추출은 부분적이고
외부 native tree 전체를 추출하지 않았다. Corpus는 겹치므로 합산하지 않는다.

[KG receipt](evidence/pr74_kg_receipt_20261008.json)와 publication 후속에
근거를 고정한다. 이 갱신은 구조 탐색 근거이며 물리 판정은 **FAIL/OPEN**이다.

## 최종 rank 분류 보강

최종 코드의 near-dependent 등식 `C=[[1,0],[1,1e-15]], rhs=[1,2]`는
수학적으로 가능한데 작은 floating pivot 때문에 미해결 상태가 된다. 이를
`NUMERICAL_FAILURE`로 분류한다. 정확히 모순인 원래 C/rhs만 rational rank
확인 후 `INFEASIBLE`로 보고한다. 정규화·face 제거 후의 반올림은 물리적
모순의 증거로 사용하지 않는다. Decimal box-edge도 v2에서는 수치 실패로
남을 수 있으며, v1의 허용 endpoint 기록을 수정하지 않았다.

중간 b4 source의 52개 focused Python 시험과 독립 검토를 통과했다. 새 Python이
만든 control은 이전 것과 바이트 동일했고, 이전 scratch에서 pinned Intel로
컴파일한 O0/O2 binary를 고정하여 **새 출력경로에서** writer와 성분 reader를
다시 통과했다. 새 Fortran 컴파일을 수행한 것으로 집계하지 않는다.

- [rank v2 receipt](evidence/pr74_joint_analysis_receipt_20261008_v2.json)
- [새 source endpoint replay](evidence/pr74_rank_endpoint_replay_20261008/receipt.json)
- [첫 frozen graph의 독립 검토](evidence/pr74_kg_independent_review_20261008.json)

첫 `d3b1a6e` 구현의 KG와 후속 rank 구현의 KG는 별도 스냅샷으로 연결한다.
**동일 후보의 native 첫 호출·수지·질량–바람·시간반응은 계속 OPEN이다.**

## 최종 정규화 순서와 source 검증

등식의 floating rank 선택도 공분산 정규화 **뒤**에서 수행한다. 정규화 이전의
고정 tolerance로 큰 단위변환을 오거부하는 경로를 제거했고, `x=0.3`와
`x′=10^15 x`의 등가 문제를 공통 회귀시험에 추가했다. 최종 solver SHA
`97ef288d5e32add28749bb2be36ee846e198ad38a3b048fac8797c614c8a5c12`에서
53개 focused Python 시험이 통과했다. 최종 Python으로 생성한 control은 첫
batch와 바이트 동일하며, pinned Intel O0/O2 보존 binary를 새 scratch에 복사해
writer·성분 재읽기를 각각 다시 통과했다. Fortran은 이번 재생에서 재컴파일하지 않았다.

- [최종 source endpoint와 53개 시험](evidence/pr74_final_endpoint_replay_20261008/receipt.json)
- [최종 독립 검토](evidence/pr74_final_independent_review_20261008.json)
- 중간 b4 receipt는 [원바이트 보존본](evidence/pr74_joint_analysis_receipt_20261008_rank_intermediate.json)으로 유지했다.

이 결과는 제조 endpoint의 수치·직렬화 검증이다. 공통 pipeline 실행, 실제 native
첫 호출 수용, 전체 물·에너지·질량–바람·초기 시간반응을 인증하지 않는다.

## 게시 경계

PR74는 외부에서 2026-10-08 08:17:03 UTC에 main
`2e5f3b8f98aa2d9d0d8de2b5824dd12a950b7920`으로 병합됐다.
첫 구현 `d3b1a6e`와 해당 main의 tree는 동일하다. 병합 뒤의 rank 분류·정규화 순서
보강, 최종 53개 시험과 endpoint 재읽기, 첫 KG의 publication 기록은
`fix/pr75-analysis-rank-followup`의 별도 후속 PR로 게시한다.
과거 PR74 publication receipt의 OPEN 표기는 게시 상태를 재확인하기 전의
오래된 기록으로 보존한다. 해당 상태 필드를 현재 병합 상태의 근거로 사용하지 않는다.

## 후속 PR75의 별도 Graphify/KG 완료

후속 동결 커밋 `2f2685846d814d0131b862b6c0a0ab507aef7ae7`의 37개 변경경로를
main `2e5f3b8` 기준으로 증분 추출했다. 첫 batch의 snapshot·receipt를
보존하고 `2026-10-08-pr74-v2`에 별도 스냅샷을 두었다. 이 폴더의 후속 PR은
[PR75](https://github.com/gonos2k/Cloud-BAL/pull/75)이며 과거 이름을 유지했다.

| Corpus | 노드 | edge | 후속 delta |
|---|---:|---:|---|
| KLAPS50 | 34,242 | 74,076 | +13 nodes / +11 edges |
| Cloud-BAL | 8,409 | 15,650 | +13 nodes / +11 edges |

각 corpus에 16개 ID를 추가하고 3개를 교체했으며, missing/duplicate/collapsed
edge는 0이다. wiki derived report/index/log를 동기화했고 schema·content·private
profile·유지관리 native source는 보존했다. 두 corpus는 겹치므로 합산하지 않는다.
추출은 AST와 Markdown heading에 한정되며, semantic refresh와 외부 native 전체
추출을 수행하지 않았다. Fortran CALL 관계는 부분적이다. 최종 publication
metadata는 이 frozen extraction 이후 별도로 기록하며 graph freshness를
수치·런타임·과학적 수용 근거로 사용하지 않는다.

- [후속 KG receipt](evidence/pr74_kg_followup_receipt_20261008.json)
- [PR75 publication 및 보존](evidence/pr75_publication_20261008.json)
- [후속 KG 독립 검토](evidence/pr74_kg_followup_independent_review_20261008.json)

**종합: 두 P1 추정기 수정은 완료. native 후보 REJECTED, 전체 물리 초기화 FAIL/OPEN.**
