# PR75 후속 해소 체크리스트 — 2026-10-08

검토 main `2e5f3b8f98aa2d9d0d8de2b5824dd12a950b7920` (PR74), 이번 변경의
시작 커밋 `0492d8eab2f2cc9841a9359ddafc664e22737ff0` (기존 PR75 후속).
최종 물리 초기화 **FAIL/OPEN**, 실제 native 후보 **REJECTED**를 유지한다.
원래 PR74/PR75 receipt와 실패 기록은 수정하지 않는다.

## 해소와 제한적 완료

| 항목 | 판정 | 직접 근거와 범위 |
|---|---|---|
| P1: 상쇄된 gradient로 자기 정규화해 정상 최소해를 거부 | PASS_SCOPED | 정류성의 배경·관측·등식 피연산자 절댓값으로 척도를 구성. `x=0.4`, 비용 0.1과 KKT PASS. 4096ε 기준은 그대로 유지. |
| 잘못된 해·승수의 수용 방지 | PASS_SCOPED | 내부해 perturbation과 잘못된 상한 승수 계속 거부; 기존 primal·상보성·rank 검사를 유지. |
| 독립 최적해 대조 | PASS_SCOPED | 396개 varied-H scalar 및 128개 80자리 Decimal 공분산형 fixture, 단위 재표현과 등식·bound 조합. well-conditioned 제조문제의 근거이다. |
| 최종 root Python suite | PASS_SCOPED | 61개 시험 통과. 개별 시험 함수 수와 그 내부 제조사례 수를 합산하지 않는다. |
| 새 Intel endpoint 저장·재읽기 | PASS_SCOPED | pinned ifx O0/O2로 각각 새 scratch에서 Fortran을 컴파일하고 평가기·writer·성분 reader 통과. 생산 `run_cloud_bal_pipeline` 미실행, canonical artifact UNBOUND/candidate REJECTED. |
| 실제 FP 모드·좌표의 연결 | PASS_SCOPED | 진단용 O0 partialhost의 NI adapter `(i=211, call_lat_index=2, k=15)`에서 MXCSR `0x9FFD`와 양의 normal NI→0 결과를 같은 thread에서 직접 캡처. FTZ/DAZ 활성, mode 변경 없음. 원 pretrace·driver capture·100 inputs 일치. |
| 팀 교차검토·과거 근거 보존 | PASS_SCOPED | solver·고정밀 oracle·native 진단·독립 reviewer가 교차검토. 최초 진단의 누락된 `-convert big_endian`과 thread 기록 불일치를 바로잡고 재검증했으며 첫 시도도 보존. |

## 남은 물리 종료조건

- [ ] main 시작·필요 thread·물리 진입의 일관된 FP 정책과 전체 host build를 연결한다.
  NI adapter 한 thread의 진단은 전체 실행환경의 검증이 아니다.
- [ ] 같은 완료 갱신에서 Q/N/B의 생성·혼합·이류·소멸과 표현 변화를 함께 유지한다.
  FTZ/DAZ를 끄는 것만으로 기존 moment-only·음수 QC가 해결됐다고 판단하지 않는다.
- [ ] PBL DEL과 native hybrid 건조질량에서 행렬·RHS·반환 경향·경계 회계를 연결한다.
- [ ] freezing·초미량 QG/BG를 다음 물성 모형이 소비할 수 있도록 생성·활성화·승화·소멸의
  물질·부피·열역학 규약을 확정한다. floor·clamp·임의 삭제로 바꾸지 않는다.
- [ ] 동일한 유효 후보의 첫 native 호출을 끝내 필수 pre/post 자료를 확보한다.
- [ ] 같은 carrier·시각·영역에서 물·에너지·강수·수치 정리·경계항을 폐합한다.
- [ ] 독립 H/B/R·관측·배경 prior·변경 권한으로 실제 공간 후보를 생성하고 공통 pipeline에 연결한다.
  analysis와 source/boundary/phase를 계속 분리한다.
- [ ] 최종 pressure/Phi/면 바람/질량경향·경계를 공동 평가하고 WPS/metgrid/real/native로 전달한다.
- [ ] 동일 설정 BASE/HYDRO/COUPLED 첫 호출 및 10·30·60분의 시간반응·독립 관측을 평가한다.
  관측된 구름·강수·상승류를 줄여 조용해진 후보를 성공으로 고르지 않는다.

## 근거

- [원문 P1 전후 재현](evidence/pr75_stationarity_reported_p1_reproduction_20261008.json)
- [공통 척도 구현](PR75_STATIONARITY_CERTIFICATE_20261008.md)
- [독립 고정밀 oracle](evidence/pr75_stationarity_independent_20261008.json)
- [root 61개 시험·fresh Intel endpoint](evidence/pr75_stationarity_endpoint_20261008/receipt.json)
- [실제 native FP 진단](pr75_native_fp_runtime.md)
- [팀 검토](PR75_TEAM_REVIEW_20261008.md)
- [보존 baseline](evidence/pr75_stationarity_preservation_20261008.json)

Graphify/KG는 코드 batch가 동결된 뒤 별도로 증분 갱신한다. KLAPS50과 Cloud-BAL의
스냅샷·delta를 따로 기록하고 wiki derived report/index/log만 동기화한다.
AST/Markdown heading 및 부분 Fortran CALL 추출의 제한을 적시한다.
Graph freshness는 수치·런타임·과학적 수용의 근거가 아니다.

## 직접 FP 관측의 범위

NI 입력은 `1.356338643876034e-38 kg^-1` (bits `0093B134`), 건조밀도는
`0.7680497765541077 kg m^-3` (bits `3F449EE9`)이고 내부 결과는 `+0`
(bits `00000000`, valid=false)이다. 같은 OS thread `4081559`의 변환 전후
MXCSR는 `0x9FFD`로, FTZ/DAZ가 모두 켜져 있다. 두 입력은 normal이므로
양의 subnormal 결과를 FTZ가 0으로 만드는 기전을 직접 연결할 수 있다.
DAZ 활성도 관측됐지만 이 두 normal 피연산자에서 필요한 원인은 아니다.

낮은 sticky status bits `0x3D`는 이미 호출 전에 켜져 있으므로 이 변환에서
발생한 예외라고 귀속하지 않는다. main 시작과 다른 thread의 MXCSR는 미측정이다.
원 PR74 실행의 레지스터를 사후 측정한 것이 아니라, 같은 입력/pretrace/driver
및 원 flags를 유지한 진단 실행에서 확인했다. 해당 실행은 exit 128로 첫 호출에서
중단됐다. 이 증거를 실행 정책 수정이나 Q/N 공동 상태 수용으로 승격하지 않는다.

- [root native 로그·patch·2개 transform 시험](evidence/pr75_native_fp_retained_20261008/receipt.json)
- [첫 nonfinal native 시도](evidence/pr75_native_fp_first_attempt_20261008.json)

첫 시도는 원 compile의 `-convert big_endian` 누락으로 pretrace 직렬화 해시가
달랐다. 해당 receipt를 보존하고, 원 옵션을 복원한 최종 진단만 PR74와 같은 호출의
근거로 쓴다. 최종 진단이 동일한 failure-time mode와 실제 거부 위치를 확보했으므로
O2 진단 실행을 추가하지 않았다.

## 동결 source의 Graphify/KG 완료

[PR75](https://github.com/gonos2k/Cloud-BAL/pull/75)의 커밋
`978c2396e93b003002d2d6cb56dbabd01cbc3404`에서 46개 변경경로를 증분 반영했다.
KLAPS50과 Cloud-BAL은 `2026-10-08-pr75-stationarity`에 각각 별도 스냅샷을
저장했다. 앞선 PR74/PR75 스냅샷·receipt와 wiki content/schema·private profile을
보존하고 derived graph report/index/log만 동기화했다.

| Corpus | 노드 | edge | 이번 delta |
|---|---:|---:|---|
| KLAPS50 | 34,299 | 74,154 | +57 nodes / +78 edges |
| Cloud-BAL | 8,466 | 15,727 | +57 nodes / +77 edges |

두 corpus는 겹치므로 수치를 합산하지 않는다. 구조 추출은 AST/Markdown heading에
한정되며 semantic refresh나 외부 WRF/KDM6 tree 전체 추출을 하지 않았다.
Fortran cross-file CALL 관계는 부분적이다. Metadata followup은 이 frozen source
추출 뒤 별도로 기록하며 graph freshness를 수치·런타임·과학적 수용 근거로 쓰지 않는다.

- [새 KG receipt](evidence/pr75_stationarity_kg_receipt_20261008.json)
- [publication 및 보존](evidence/pr75_stationarity_publication_20261008.json)
- [KG 독립 검토](evidence/pr75_stationarity_kg_independent_review_20261008.json)

**이번 P1 인증 오거부는 해소했고 진단 native의 FP 기전도 직접 연결했다.
실행 정책·Q/N/B 공동 갱신·동일 후보의 물/에너지/질량–바람/시간반응은 계속 OPEN이다.**
