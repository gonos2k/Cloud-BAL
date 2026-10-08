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
