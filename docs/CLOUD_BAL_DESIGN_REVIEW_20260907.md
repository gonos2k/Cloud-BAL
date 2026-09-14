# Cloud-BAL 최종 설계 검토와 실행 로드맵

검토일: 2026-09-07 KST. 입력 자료: 사용자가 대화에 제공한
`Cloud_BAL_최종설계_개선로드맵_20260907.md` 전체 본문.
이 파일은 원문을 변경한 사본이 아니라 소스 대조 결과를 덧붙인 검토본이다.
원문이 언급한 Excel workbook은 제공되지 않아 열람·검증하지 않았다.

- 저장소: `gonos2k/Cloud-BAL`
- 고정 HEAD: `f837bad0bdf1050a34975d93b178b7dee4420094`
- 고정 tree: `2f70cce203d9822b4df9e5c9c28690385846fa11`
- 구현 체크리스트: [CLOUD_BAL_CHECKLIST_20260907.md](CLOUD_BAL_CHECKLIST_20260907.md)
- 편집 가능한 요구사항 원장: [CLOUD_BAL_REQUIREMENTS_20260907.tsv](CLOUD_BAL_REQUIREMENTS_20260907.tsv)
- 현재 승인 기준: [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## 2026-09-14 검토 반영 — 현재 설계 해석

위 `f837bad`는 9월 7일 정적 코드 검토의 기준이다. 다중 레이더 계획의 병합 기준은
`main@816c03820a92571dd5eb2efac41b2bf010be7722` (PR #4)이며, 문서 기준 SHA와
실제 시험 대상 SHA·dirty source hash를 구분한다. 문서 변경으로 과거 시험을 최신
코드의 PASS로 복사하지 않는다. 아래 정정은 현재 설계에 적용하고 과거 실행 기록은 유지한다.

사용자가 제시한 원 보고서 §3.2의 “R_Z와 retrieval confidence를 낮춘다”는 문구는
관측오차 공분산의 가중 방향과 반대다. 이 저장소 검토본에는 해당 문구가 없었으므로
원 보고서를 직접 수정한 것으로 표시하지 않고, 다음을 O03의 적용 기준으로 명시한다.

$$
J_Z=\tfrac12(H_Z(x)-y_Z)^T R_Z^{-1}(H_Z(x)-y_Z),\quad
R_{Z,new}=R_{Z,old}+Q,\quad Q\succeq0.
$$

`R_Z`가 양의 정부호이면 `A=R_Z^{-1/2} Q R_Z^{-1/2} ⪰ 0`이고
`(R_Z+Q)^{-1}=R_Z^{-1/2}(I+A)^{-1}R_Z^{-1/2} ⪯ R_Z^{-1}`이다.
따라서 산란·입자분포·대표성 불확실성이 클수록 **공분산을 확대하거나 정밀도 가중을
낮춘다**. 고정 innovation의 관측항 영향에 대한 관계이며, 결합 최적해의 모든 성분이
단조 변화한다는 뜻은 아니다. 오차모형을 정당화할 수 없으면 적용 범위를 제한하고
진단으로 남긴다. 특이 공분산의 지원 공간을 바꾸면서 이 역행렬 식을 그대로 쓰지 않는다.

Native 미세물리의 물·얼음 포화 기준, 혼합상·과냉각 액체수 정책을 따른다.
물리적 얼음 과포화·과냉각 액체수 자체를 제거하는 완료조건은 사용하지 않는다.
검출 대상은 수치적 overshoot, 중복 상변화, 비현실적 냉각과 해당 host 정책 위반이다.
Morrison의 정책을 현재 pinned KDM6의 정책으로 대신 가정하지 않는다.

사용자가 보고한 Excel 122개 수식·네 반례는 외부 검토 결과이며, 이 문서·원장의
수정 검증으로 Excel 엔진 실행이나 workbook 수식 교정을 완료 처리하지 않는다.
Excel 파일의 직접 편집·재계산은 별도 결과로 기록한다.
저장소의 Markdown/TSV는 수동 원장으로 유지하며, `PASS 기록요건 충족`과
선행조건·검증된 증거·승인 범위까지 갖춘 `폐합`을 구분한다. 상세 판정은
[체크리스트 운용 규칙](CLOUD_BAL_CHECKLIST_20260907.md)을 따른다.

다음 milestone은 실제 첫 사례의 레이더별 자료로 연직 정보와 공통 낙하속도 오차를
정량화한 후, 최소 제어변수·질량 경향·경계조건을 확정하는 것이다.
[다중 레이더 계획](CP02_MULTI_RADAR_BALANCED_INITIALIZATION_PLAN_20260914.md)과
[MR 체크포인트](CP02_MULTI_RADAR_INITIALIZATION_CHECKLIST_20260914.md)를 함께 사용한다.
새 결합 초기화 구현·과학 검증·운영 승격은 아직 완료가 아니다.

## 1. 검토 결론

설계의 중심인 **작은 full-state 경로, dry-mass 기준, 관측 권한에 따른 국지
보정, 최종 native 배열의 독립 검증**을 개발 방향으로 권고한다. 현재 canonical
SHADOW 코어를 유지하면서 열역학과 실제 모델 연결을 완성하는 접근이 타당하다.
새 범용 프레임워크보다 질량분모·격자/면 측도·관측오차·최종 출력의 계약을 먼저
정해야 한다. 이 검토는 설계 및 정적 소스 평가이며 운영 승인이 아니다.

기존에 고친 OM 독립 도메인, pressure interface/cell thickness 분리,
no-echo 목적지 정책, 제조해 권한 분리, diagnostic patch 범위와 schema 2
게시 검증은 재구현 과제로 돌리지 않는다. 최종 요구사항에 남은 native/물리
연결과 실행 증거를 닫는 일로 정의한다.

별도 시선속도/Barnes는 **X01 외부 완료**다. Cloud-BAL LOS 연결은 O06이며,
X01을 본체 미완료 분모에 넣거나 Barnes 알고리즘 재개발로 해석하지 않는다.

## 2. 직접 확인한 기준선과 증거의 한계

2026-09-07 Git fetch 및 GitHub API 조회에서 다음을 확인했다.

| 항목 | 관찰 |
|---|---|
| main HEAD/tree | 위 고정 값과 일치; PR #3 병합 커밋 |
| 해당 SHA의 Actions 실행 | `total_count=0` |
| main branch protection | `protected=false` |
| 저장소 rulesets API | 빈 목록 |
| 해당 tree의 `.github` 파일 | 없음 |
| 현행 pipeline | `OFF/SHADOW`, `operational_out=state_in` |

Actions 부재는 로컬 시험 부재의 증명이 아니다. 직전 작업에서 실행한
`tests/run_unit_tests.sh`는 `66a63bd7` 기반 문서/그래프 작업트리에서 exit 0을
확인했다. 이를 고정 HEAD `f837bad`의 실자료·과학 검증으로 복사하지 않는다.
이번 설계 검토에서는 pinned ifx suite, 전체 KLAPS 또는 0–6 h 예보를 재실행하지
않았다. 본체 45개 초기 gate는 `NOT_RUN`이며 구현 분류와 독립적이다.
X01은 `NOT_APPLICABLE / EXTERNAL_COMPLETE`로 별도 완료 보고를 보존한다.

조회 근거: [main API](https://api.github.com/repos/gonos2k/Cloud-BAL/branches/main),
[exact-SHA Actions](https://api.github.com/repos/gonos2k/Cloud-BAL/actions/runs?head_sha=f837bad0bdf1050a34975d93b178b7dee4420094&per_page=100),
[repository rulesets](https://api.github.com/repos/gonos2k/Cloud-BAL/rulesets).
메타데이터는 이후 바뀔 수 있으므로 위 표는 조회 시점의 기록이다.

## 3. 코드 대조에서 구체화한 검토 항목

아래 REV 항목은 45개 요구사항의 보완 메모이며 별도 요구사항 수로 집계하지 않는다.
정적 식/호출 확인과 설계상 우려를 구분하며, 실자료 오차를 새로 재현했다는 주장은 하지 않는다.

| 검토 | 코드에서 확인한 내용 | 설계·시험에 반영할 사항 | 요구사항 |
|---|---|---|---|
| REV01 질량 기준 | `state:1000–1033`은 `pressure_mass/(1+total_water)`로 dry mass를 재계산하며 `column:887`이 이를 호출 | pressure-fixed 진단과 native dry-mass 보존 경로의 의미, A_Q/A_M/A_E를 먼저 고정 | M04/M05/T01 |
| REV02 부분 셀 공통 면 | `balance:235–251`의 옆면 계수는 이웃 `cell_dp`의 산술평균 사용 | pressure interval 교집합·지형 경계의 shared-face metric을 독립 계산해 비교 | M03/B01 |
| REV03 낙하속도 가중 | `column:869–877`은 rain/snow/graupel 질량 가중 평균을 `vt_z_mean`에 기록하고 불확실 quality를 부여 | 필드명만으로 Z 가중 Doppler 속도라고 해석하지 말고 PSD/산란 가중과 근사오차 명시 | O03/O06/O08 |
| REV04 현행 solver | `balance:844–928`은 가중 CR 형태 recurrence이며 explicit preconditioner 없음 | 현행 CR과 제안 PCG를 구분; metric/self-adjointness/nullspace 확인 후 비교 | B01/B02/B04/B06 |
| REV05 순차 처리 | `pipeline:88–127`은 column 뒤 balance를 한 번 호출 | nonlinear thermo/geometry outer loop는 미구현 설계; 후속 block이 선행 budget을 깨는 반례 필요 | T03/T05 |
| REV06 enthalpy 범위 | `column:1144–1147`은 `CP_DRY*T + LV*rv - LF*ri`의 reduced enthalpy; `saturation_adjust_cell` 호출은 현재 tests에서만 확인 | host species enthalpy/열용량/압력일·native total energy를 구분하고 정상 pipeline 연결을 검증 | T03/T04/V03 |
| REV07 게시 기능 | `transaction:343–393`은 no-replace 미지원 errno를 거부 | 시작 시 같은 filesystem에서 기능 probe; 안전한 backend/protocol 선택 전 대규모 실행 회피 | E05/E06 |
| REV08 증거·선행정책 | 기존 ledger의 P2 이후 정지 정책과 새 설계의 병렬 연구 허용 제안이 다름 | 연구 의존성과 통합·승격 의존성을 구분한 계획 변경으로 검토; 이 문서만으로 기존 승인정책 변경 안 함 | G01/G05/P2–P8 |

위 코드 위치의 파일은 고정 SHA의
[state](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/src/common/cloud_bal_state.f90),
[column](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/src/common/cloud_bal_column_physics.f90),
[balance](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/src/common/cloud_bal_balance_operator.f90),
[pipeline](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/src/common/cloud_bal_pipeline.f90),
[transaction](https://github.com/gonos2k/Cloud-BAL/blob/f837bad0bdf1050a34975d93b178b7dee4420094/tools/cloud_bal_transaction.py)이다.

### 검토용 해석 예

고정된 전체 pressure mass에서 `md=mtot/(1+rt)`이면
`dmd/drt=-mtot/(1+rt)^2 < 0`이다. 따라서 전체 수분을 외부에서 추가하면서
pressure-cell total mass와 dry mass를 모두 불변이라고 할 수 없다. 이는
대수적 조건이며 현재 source의 저장 방식이 native conservation을 이미 만족한다는
뜻이 아니다. ARW에 넘길 때는 host dry-mass 좌표에서 이미 정의된 질량을
다시 `(1+rt)`로 나누지 않는다.

부분 셀 예로 두 압력 구간이 `[900,1000]`과 `[900,950]` hPa라면 공통 구간은
50 hPa이고 각 두께의 평균은 75 hPa다. 현재 평균 계수가 모든 native 지형에서
공통 면 측도를 표현한다고 가정할 수 없음을 보여주는 해석 예다. 실제 adapter와
지형 좌표의 보존 오차는 별도 제조해로 평가해야 한다.

## 4. 질량·열역학 계약의 보완안

기본 변수는 `u,v,w/omega,T,rv,rc,ri,rr,rs,rg,ps,Phi`와 독립 geometry다.
각 r은 먼저 dry-air mixing ratio로 통일하되 native model의 실제 분모와
재구성 방법을 adapter 계약에 적는다. Center spacing과 cell thickness를
분리한 현행 구조를 유지하고, thin-cell·공통 면·column mass sum·remap을 닫는다.

`state:1315–1336`의 `represented_total_water`는 usable species만 합산한다.
따라서 optional species 결측을 물리적 질량 0으로 해석하지 않도록 종별 coverage와
분모의 포함 범위를 mass-basis 계약에 적어야 한다.

다음 두 실행 의미를 구분한다.

1. **Pressure-fixed diagnostic:** pressure mass 고정, 수분 변경에 따른 implicit
   dry-mass 변화를 보고하며 native 보존 완료로 표시하지 않는다.
2. **Native coupled candidate:** dry mass를 기본량으로 두고 수분 분석증분 A_Q,
   에너지/enthalpy 분석증분 A_E와 필요한 질량/pressure 조정 A_M을 별도 기록한다.
   geometry/EOS를 native 규칙에 따라 재구성한다. 이 경로는 아직 설계다.

내부 phase transfer는 A_Q와 다르다. 수분 총량 Q에 대해
`Qa-Qb=A_Q+dt*(F_in-F_out)+epsilon_Q`를 사용하고, 외부 분석과 source-to-sink
물리수송을 분리한다. Interface throughput kg/s를 층마다 합한 값은 고유 source
mass kg가 아니다. Reconstruction prior와 source-removing 시간수송 중 실행
모형을 고정하고 ledger의 단위·시간창·source ID를 일치시킨다. 기존 수상체 기반
연직풍 복원은 수상체의 질량기준·낙하속도·오차·변경 여부를 기록하며 새 시간수송기를
항상 선행시키지 않는다. 적용 요구사항 집합은 실행 전 범위와 함께 승인하며 미선택을
기능 완료로 바꾸거나 임의로 필수 항목을 제외하지 않는다.

`h_d=h_dry(T)+sum(rj*hj(T))`는 종별 기준점과 열용량을 host microphysics와
맞춘 뒤 사용한다. Reduced cell enthalpy 보존은 native compressible total-energy
보존과 다르다. 문헌의 conservation 논의는 이 구분을 뒷받침하지만 프로젝트의
구체적 EOS·microphysics 선택을 대신하지 않는다.

근거: 사용자 설계 §2/§4,
[Lauritzen et al. (2022), S03](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2022MS003117),
[ARW v4 기술문서 §2, 추가 근거 S09](https://www2.mmm.ucar.edu/wrf/users/docs/technote/v4_technote.pdf).

## 5. 관측·trajectory·boundary 계약의 보완안

- `omega=partial_t p|z + vh·grad_z p + w*partial_z p`에서 `partial_z p=-rho*g`
  근사를 써도 pressure tendency와 horizontal advection은 자동으로 사라지지 않는다.
  Copied/test boundary와 observational boundary를 분리한다.
- `Vr=beam·(u,v,w-Vt_Z)`에는 beam 방향·positive-away/toward 부호, frame,
  time window와 error model을 적는다. Transport에는 Vt_mass를 사용하며 동일
  terminal speed 재사용은 명시된 PSD/phase 근사 아래에서만 평가한다.
- 이미 dealiased된 자료의 검증 가능한 receipt와 uncertainty를 설계할 수 있다.
  이것이 현재 gate의 즉시 완화를 승인하지는 않는다. Folded 표현에는 Nyquist
  계약이 필요하다. X01 완료를 유지하고 이 연결을 O06으로 추적한다.
- ECHO/BELOW_DETECTION/MISSING/QC_REJECTED를 분리한다. 제안된
  `-log Phi((Zdet-HZ)/sigmaZ)`는 Gaussian dBZ 오차·유효 검출한계 아래의
  censored 모델이다. 구현 시 log-CDF 수치안정성, sigma>0, 상관/대표성 오차와
  detection metadata 결측 거부를 검증해야 한다. 현재 구현이라고 기록하지 않는다.
- Earth-fixed time trajectory와 storm-relative reconstruction은 별도 모형이다.
  Unknown translation을 관측된 0으로 표시하지 않고, no-echo hard-block을
  증발 또는 경로 전체 장벽으로 재해석하지 않는다.

## 6. Balance와 outer iteration의 보완안

고정된 선형 block에서 SPD W와 feasible constraint `C delta=d`를 가정하면
`C W^-1 C^T lambda=Cq-d`, `delta=q-W^-1 C^T lambda`라는 설계식은 맞다.
Gauge 외 rank deficiency와 비양립 RHS도 검사해야 한다. `C W^-1 C^T`는
일반적으로 positive semidefinite이고, PCG를 적용할 공간에서 SPD가 되는지
독립 확인해야 한다. 권한 없는 DOF는 제거하거나 별도 고정해 singular W를
형식적으로 역행렬 처리하지 않는다.

현재 구현은 `alpha=<r,Ap>_M/<Ap,Ap>_M`,
`beta=<Ar,Ap>_M/<Ap,Ap>_M`, `p=r-beta*p` 형태다.
따라서 PCG는 향후 후보 알고리즘이며 현행 코드의 이름으로 사용하지 않는다.
Metric·units·adjoint·component gauge와 scaling을 먼저 검증하고 이후 간단한
Jacobi/vertical-line 전처리 후보를 정확도·iteration·p95 wall로 비교한다.

현재 zero-normal target-increment projection과 full compressible initialization을
분리한다. Coupled 상태에서 `D delta_Fd=-delta_dot_md`를 평가할 때, 수분 증가를
dry-air source로 넣거나 geometry가 바뀌어도 무조건 `d=0`으로 두지 않는다.

이산 정확해 시험은 feasible `delta*`, gauge-compatible `lambda*`에서
`q=delta*+W^-1 C^T lambda*`를 만들어 복원을 검사한다. 같은 C로 생성·검사한
일치는 공간 미분의 정확도를 증명하지 않는다. 독립 sparse reference로 solver·adjoint·
nullspace를 검사하고, 연속 제조해와 격자수렴으로 metric·경계·미분 정확도를 별도 검사한다. 저장소에 기록된
6/16 adverse-response와 50% 허용은 numerical path exercise다. 같은 target
위치와 고정 threshold에서 독립 sparse reference·다격자·지형 partial face·
native handoff 뒤 residual과 target fit을 함께 검사한다.

Outer iteration은 proposal -> phase/enthalpy -> geometry/EOS -> balance ->
full-state 재평가 순서로 설계한다. Damping, 반복 cap, 잔차/변화량 cap과 원본
rollback을 명시한다. Cap 도달이나 하나의 transaction 안에 들어갔다는 사실을
nonlinear 수렴으로 간주하지 않는다.

## 7. 실행 순서와 병렬 연구의 합류점

| 순서 | 산출물 | 주 요구사항 | 다음 단계로 넘길 조건 |
|---|---|---|---|
| A0 | exact-SHA 증거 목록·가벼운 contract CI 설계 | G02/G05/G03/G04 | code/input/config/tool/결과 역할 구분; CI 설정은 별도 구현 |
| A1 | native 질량분모·PSFC·frame 계약 | M04/M05/M06/M07/T01 | 단일 column mass/enthalpy와 변환 왕복의 해석 기준 |
| A2 | native-compatible 작은 projection reference | B01/B02/B03/B06 | partial face·gauge·target recovery·handoff 확인 |
| A3 | 작은 thermo block와 bounded outer coupling | T03/T05/B05 | 종별 수분·enthalpy와 후속 geometry/balance 재검증 |
| B1 | 실제 upstream·전체 ifx·OFF native 왕복 | E01/E02/E03 | 동일 입력으로 최소 full-state vertical slice |
| B2 | 시작 시 capability probe·세대 seal | E05/E06 | 지원 backend에서 검증한 byte와 게시 byte 결속 |
| 합류 | 관측·물리 결합 근거가 검증된 FULL_SHADOW_PRODUCT | O05/O06/E04/E08 | native 최종 상태를 독립 verifier가 검사 |
| 이후 | 사건별 paired 0–6 h와 운영 예산 | V01–V06 | 사전 고정 지표·hold-out·wave sampling·독립 승인 |

위 순서는 구현 착수/설계 검토 제안이다. 기존 P1–P8 단계와 긴급도 P0/P1/P2는
다른 축이다. 격리된 연구의 병렬 수행과 통합·게시·운영 승격의 의존성을 구분하되,
기존 구현의 권한 검사·rollback은 유지한다. 새 개발의 O06 입력 연결은 O05보다
먼저 가능하며, O06 결합 분석은 입력·관측 가능성·질량·경계 계약을 충족한 뒤 진행한다.
R2의 실제 조건부/공동 분석 경로 선택 전 대형 solver 확장을 선행하지 않는다.

## 8. 체크리스트 운용과 평가

원문 45개 본체 요구사항의 분류(구현확인 8, 부분구현 29, 설계·계약 6,
구현미확인 2)는 소스/문서 수준 분류다. 시간·완성도 백분율로 환산하지 않는다.
X01 외부 완료는 별도 집계한다. 모든 항목에 담당 역할, 미지정 실제 담당자,
선행 ID, 다음 작업, 완료조건, 적대시험, 출처, gate, tested SHA, evidence URI,
reviewer와 closure를 둔다.

`PASS` 한 칸이나 SHA 문자열만으로 완료되지 않는다. 증거의 실제 내용·hash,
설정·입력 범위, independent review와 선행조건을 확인해야 한다. Evidence
재사용이 필요한 경우 dependency equivalence와 명시적 재사용 승인 기록을
요구한다. 운영 승격은 필수 gate의 AND 및 별도 승인이고 평균 점수가 아니다.

문서에서 언급한 workbook을 본 것으로 처리하지 않는다. 이번 산출물은 Markdown
체크리스트와 UTF-8 TSV 원장이며, 원문의 gate를 자동으로 PASS로 바꾸지 않았다.

## 9. 과학 검증의 최소 설계

네 연속시각은 하나의 회귀 사례군이며 독립 사건 네 개가 아니다. Regime별
event split, calibration/hold-out ID 중복 제거, 고정 effect/noninferiority margin을
먼저 정한다. 기존 deposition=0 사례 외 deposition>0, suspension, boundary exit,
terrain intercept, observation conflict의 양성·음성 경로를 포함한다.

동일 background의 OFF, 가능한 legacy E2E, hydro/thermo-only, dynamic-coupled
candidate를 대조한다. 강수·풍벡터·T/qv/PSFC·cloud base/top·수분/에너지 budget과
초기 pressure tendency/divergence를 같이 평가한다. Acoustic/high-frequency
aliasing을 피하도록 모델 timestep 또는 충분한 빈도의 진단을 수집한다.
10/30/60분 checkpoint와 0–6 h skill은 이를 보완한다. DFI/IAU는 독립 ablation이며
기본 물리 불일치를 덮는 필수 후처리로 채택하지 않는다.

## 10. 출처 추적

- 원문 R01–R12는 요구사항 원장/체크리스트에, S01–S08은 아래 문헌 목록에 유지한다.
- R02/R03/R04는 각각 상태 요약/승인 기준/실행 ledger이며 동일한 권위를 갖지 않는다.
- 이번 정적 검토의 추가 코드 근거는 §3에 exact-SHA URL로 고정했다.
- S09는 ARW v4 공식 기술문서이며 native dry mass와 pressure-coordinate adapter를
  구분할 때 참고한다. 외부 논문은 설계 근거이며 Cloud-BAL 실행 인증이 아니다.
- 사용자 원문, 기존 문서의 기록, 직접 소스 확인, 원격 metadata 조회, 해석상 제안을
  구분했다. 이번 작업은 물리 코드·CI·branch protection·운영 자료를 변경하지 않는다.

## 11. 문헌 대조와 보존 목록

핵심 질량/열역학·radar 해석·격자 연산자 주장을 중심으로 1차 자료를 대조했다.
모든 논문의 모든 식을 독립 검증한 전면 문헌 재현은 아니다. 논문이 해당 기법을
다룬다는 사실을 Cloud-BAL 구현의 검증으로 옮기지 않는다.

| ID | 1차 자료와 검토 범위 |
|---|---|
| S01 | [Wang et al. (2013), Radar Data Assimilation with WRF 4D-Var. Part I: System Development and Preliminary Testing](https://doi.org/10.1175/MWR-D-12-00168.1) — 다변량 관측연산자/모델 결합의 근거; Cloud-BAL loading target 승인 아님 |
| S02 | [Wattrelot et al. (2014), Operational Implementation of the 1D+3D-Var Assimilation Method of Radar Reflectivity Data in the AROME Model](https://journals.ametsoc.org/abstract/journals/mwre/142/5/mwr-d-13-00230.1.xml) — no-rain/detection 정보; 제안 censored Gaussian 식 자체의 검증 논문으로 표시하지 않음 |
| S03 | [Lauritzen et al. (2022), Reconciling and Improving Formulations for Thermodynamics and Conservation Principles in Earth System Models (ESMs)](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2022MS003117) — 분모·종별 보존·열역학 기준 구분 |
| S04 | [Yamaguchi & Feingold (2012)](https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/2012ms000164) — 원문 ARW mass-coordinate 참고문헌; 직접 host 정의는 S09도 대조 |
| S05 | [Bryan, Wyngaard & Fritsch (2003)](https://journals.ametsoc.org/view/journals/mwre/131/10/1520-0493_2003_131_2394_rrftso_2.0.co_2.xml) — 깊은 대류의 해상도 의존성; fixed core-to-grid w 변환 보장 아님 |
| S06 | [Peckham et al. (2016), DFI 연구의 NOAA 저장본](https://repository.library.noaa.gov/view/noaa/16494) — 고주파 감소와 초기 대류 영향의 trade-off; DFI 기본 적용 권고 아님 |
| S07 | [Protat & Williams (2011)](https://journals.ametsoc.org/abstract/journals/apme/50/10/jamc-d-10-05031.1.xml) — air motion/입자 낙하 분리와 Doppler 해석 |
| S08 | [Cotter & Shipton (2012), DOI 10.1016/j.jcp.2012.05.020](https://doi.org/10.1016/j.jcp.2012.05.020) — compatible pressure/velocity 공간과 computational mode; C-grid 명칭만으로 native closure 보장 아님 |
| S09 | [ARW v4 공식 기술문서](https://www2.mmm.ucar.edu/wrf/users/docs/technote/v4_technote.pdf) — dry hydrostatic coordinate, dry-mass 결합 변수와 native 방정식의 직접 참고 |
