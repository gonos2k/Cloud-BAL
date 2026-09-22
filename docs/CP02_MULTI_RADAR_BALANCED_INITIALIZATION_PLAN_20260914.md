# 다중 레이더 연직풍 복원 및 국지 균형초기화 추가 과제

작성: 2026-09-14. 추가 검토 반영: 2026-09-17. 상태: **계획 수립 / 자료·방정식 검토 중 / 결합 구현 및 검증 미완료**.

추가 검토 반영: 수학·수치해석·기상학 팀 검토와 상변화 유발 중력파 제어 요구를
R1–R5의 작업·통과 조건에 반영했다. 종합 검토 (로컬 작업공간 근거: `../scratch/cp02_multiradar_additional_review_20260914/REVIEW.md`)는
설계 보완의 근거이며, 결합 구현이나 초기 충격 억제를 실증한 결과는 아니다.
실행 상태와 완료 근거는 [체크리스트·체크포인트](CP02_MULTI_RADAR_INITIALIZATION_CHECKLIST_20260914.md)의
MR-C0–MR-C6에서 추적한다.
성립 가정·해 존재·유일성·보존·파동 제어의 수학적 근거는
[조건부 증명](CP02_MULTI_RADAR_MATHEMATICAL_PROOFS_20260914.md)에 정리한다.

## 2026-09-17 PR #25 후속 — 실제 legacy 균형의 수학적 연결을 먼저 교정

이 절은 아래 역사 기록의 “국소 수식 교정 다음 native 전달” 순서보다 우선한다.
기준은 PR #25 병합 `763f81cba568dd7fa9071972b0da56b8a702fd37`다.
[실자료 수학·기상학 검토](LEGACY_BALANCE_MATH_REVIEW_20260917.md)에서 실제
`235×283×22`, `2026-08-16 13 UTC` 배열을 사용해 solver와 실제 갱신/진단의
불일치를 확인했다. 준비된 원본 3차원 분석·배경·지표·static을 계속 사용한다.
새 작은 합성 기상장이나 다른 시각의 native seed로 통합 검증을 대체하지 않는다.

현재 QBAL main이 실행하는 것은 **legacy BALCON**이다. canonical 증분 projection의
소스·단위시험은 이 경로의 검증 근거가 아니다. PR #24 전 영역 metgrid/real 재현,
기존 pressure·omega collocation·terrain·원복·writer/reader의 `PASS_SCOPED`는 유지한다.
PR #25의 OFF 경로와 실패 기록도 유지하되, 승인된 ON/비영 after는 아직 없다.
기존 개별 시험의 성공을 결합 연산자 항등식이나 전체 물리 균형의 성공으로 합치지 않는다.

### PR #27 추가 검토에 따른 승인·인증 보강

PR #27 병합 기준 `5f39fff`의 `A=DG`, unweighted RHS 및 incident-row mobility
교정은 제한적 성과로 유지한다. 후속 검토는 다음 순서로 진행하며, 상세 근거는
[face 승인·영공간 인증 후속 기록](LEGACY_FACE_GATE_REVIEW_20260918.md)에 기록한다.

1. **P0 승인 검사:** 실제 변경 U/V/omega face 전체의 증분을 검사한다. pressure 행의
   beta=0이라는 이유로 다른 위치에 저장된 유효 face를 누락하지 않는다. 변경 권한과
   극값 계산을 구분하고 sentinel 전이를 거부한다. X/Y 각각 12 m/s 반례는 기존
   10 m/s 상한으로 거부돼야 한다. 서로 다른 face의 U/V를 같은 위치 벡터라고 부르지 않는다.
2. **P1 영공간 인증:** tree 후보의 전체 전치 잔차와 함께 모든 양의 연결의 상대
   상세균형 `|z_i A_ij-z_j A_ji|/(|z_i A_ij|+|z_j A_ji|)`을 검사한다. 약결합
   비가역 4행 반례는 반복 전에 `UNRESOLVED`로 거부한다. 인증이 어려운 metric을
   임의로 호환 처리하지 않으며, 근사 영벡터의 obstruction을 엄밀한 잔차 하한으로 단정하지 않는다.
3. **실제 해 존재 문제:** 동일 NE57 8개 성분에서 `z ∝ h*dp`를 독립 확인하고,
   `z^T D(y)`를 실제 외곽·상하단·인공 support·terrain/sentinel 경계의 signed
   contribution으로 분해한다. 배경과 제안은 같은 stagger·시각의 저장 상태가 확보된 경우에만
   분리한다. 입력 계보가 없으면 해당 분해를 미완료로 명시한다.
4. **후속 물리 결정:** 증거에 따라 허용할 경계/source `S eta`와 `Z^T S eta=Z^T b`,
   또는 승인된 증분만의 목표를 명시한다. 현 고정 경계 문제의 부적합은 기상장 자체의
   물리적 불가능성을 뜻하지 않는다. 권한·관측 근거·오차·상한이 없는 변경은 적용하지 않는다.

반복법·전처리 개선은 이 목표 결정 이후이며, 미완료 비영 ON·native·열역학·예보 상태는 유지한다.

### PR #28 추가 검토 이후의 실행 우선순위

병합 기준 `68239af`의 face 최대증분·상향 반올림과 약결합 상세균형 인증은
`PASS_SCOPED`로 닫고 회귀를 유지한다. 기존 NaN influence 방어는 유한성 검사 후
범위 검사로 분리하는 작은 수정으로 처리하며, 실자료 8개 부적합의 원인과 구분한다.

다음 작업은 큰 solver 재시도보다 **허용된 변경의 실현 가능성**이다.

1. 고정된 실제 graph에서 경계의 이웃 행을 제외한 조건을 분리한다. 지면 아래 판정,
   sentinel donor, support 밖 조건의 중첩과 실제 저장 face 좌표를 남긴다.
   sentinel은 곧 관측 결측이 아니므로 producer와 `terbnd`의 생성 경로를 확인한다.
2. 조정 변수마다 field/face/단위, 양쪽 incident 행, 자료·물리 근거, 변경 권한,
   사전 오차공분산과 상·하한을 명시한다. 유효 COM이나 큰 signed 기여만으로 권한을
   부여하지 않는다. native 불투과 조건과 pressure 격자의 제외면을 동일시하지 않는다.
3. `S=DE`와 `M=Z^T S`, `d=Z^T b`를 같은 stencil로 구성하고 **상한을 포함해**
   `M eta=d`를 검사한다. 한 공유 face는 모든 incident 행에 반영한다.
   rank/range 검사는 무상한 문제의 조건일 뿐이다. 성분별 도달 구간이 겹쳐도
   공통 eta가 존재하는지 별도 확인한다. 사후 clipping은 호환성을 깨뜨릴 수 있다.
4. 현재 허용된 내부 face만으로는 정확한 상쇄 가중치에서 `Z^T DE=0`이므로
   비영 결함을 제거할 수 없다. 새 경계/source 정책이 없으면 거부를 유지한다.
   지원 영역·geometry를 바꾸면 A/성분/Z와 전체 승인 검사를 다시 구성한다.

고정 graph에서 `d_b+gamma*d_delta`를 계산하면 670/453/135행 성분은 배경과 제안
차이의 부호가 같아 `0<=gamma<=1`의 감쇠로 해소되지 않는다. 증분 목표도
`Z^T(-D delta_y)`가 비영이면 같은 경계에서 부적합하다. 목표 전환을 자동 해결책으로
사용하지 않는다. 수렴 개선과 native 검증은 위 조건이 충족된 후보에 대해 진행한다.

실자료 후속 조건부 진단은 성분 호환성과 최종 상한을 따로 검사해야 함을 확인했다.
순수 support omega 조정으로 호환시킨 원래 A는 수렴했지만, 비제약 보정은 10/5
상한을 크게 넘었다. 같은 종류의 face에 상한을 직접 둔 유량 진단은 작은 활성 행
잔차의 후보를 만들었다. 이는 생산 경계 허가나 최소분산 해가 아니다.
다음 구현 전에는 **비활성 수신 행의 제약까지 포함한 E와, 최종 상한을 포함한
가중 최적화**를 확정한다. 내부 잔차만 줄여 이웃으로 결함을 옮기는 것을 전체
해결로 승인하지 않는다. 상세 수치와 재현 범위는
`LEGACY_FACE_GATE_REVIEW_20260918.md`의 PR #29 계속 진단에 기록한다.

### PR #29 검토 이후: 수신 영역의 공동 제약

`LEGACY_RECEIVER_CONSTRAINTS_20260921.md`에 같은 실제 후보의 수신 영역 검사를
추가했다. 변경된 행만 선택하지 않고 80,517개 가정한 support omega face의 전체
수신 집합 79,316행에서 before/변화/after를 평가한다. 8개 활성 성분은 공유 수신
행 때문에 7개 결합 집합을 이루며, 수신 가중치를 중복 사용하지 않는다.

다음 최적화 전에 `B=z_R^T r_before`, `d=z_P^T b`, `W=sum(z_R)`로
`sum(z_R*lower)<=B-d<=sum(z_R*upper)`를 검사한다. 이는 정확한 활성 목표의
필요조건이며 충분조건이 아니다. 활성 저장 잔차 허용값이 있으면 해당 가중 오차를
포함한다. 실자료에서 수신 잔차 불변과 전체 수신 잔차 0은 모두 이 고정 face 집합의
수지와 양립하지 않는다. 결과를 보고 receiver 허용오차를 정하지 않는다.

생산 구현 전에 권한 face, 자료·물리 근거와 비용, 수신 영역의 최종 잔차 범위를
명시하고 부분집합·face 용량·최종 U/V/omega 상한까지 함께 검증한다. 수신 영역을
계속 넓혀 결함을 밖으로 전달하는 것은 전체 해결로 인정하지 않는다.

PR #30 후속 재계산에서 행별 비악화 `|r_after|<=|r_before|`도 검사했다.
정확한 활성 목표의 필요조건 `|B-d|<=sum(z_R*|r_before|)`을 7개 결합 집합 중
4개가 위반한다. 이 고정 face 문제는 최적화 전에 이미 불가능하므로, 다음 단계는
물리 근거에 따라 목표·변경 권한·최종 구간 중 무엇을 바꿀지 확정하는 것이다.
활성 오차를 허용하는 문제는 별도의 `sum(z_P*t_P)`를 포함해 다시 검사해야 한다.
공유면 산술 검사는 상쇄 전 여섯 face 항의 크기로 보강하며 생산 허용오차와 구분한다.

### PR #31 이후 결정: 실제 물리 경계 재구성 우선

반올림 보강은 `PASS_SCOPED`로 닫는다. 현재 고정 face에서 정확한 활성 목표와
수신 행별 비악화는 양립하지 않으므로 같은 문제의 optimizer 재시도를 중단한다.
다음 연구 경로는 [실제 물리 경계 재구성](LEGACY_PHYSICAL_BOUNDARY_POLICY_20260921.md)이다.
같은 사례의 12/13/14 UTC LSX·06 UTC 주기 FSF를 확인했고, 13 UTC LSX PS는
snapshot PSFC와 전 격자에서 동일하다. `omega_s=partial_t p_s+v_s dot grad p_s`를
실제 지면과 pressure face에 연결하는 입력·기하·오차 계약을 먼저 확보한다.
시간차분만으로 omega나 오차 한도를 정하지 않으며, finite-pressure 상단·측면도
별도의 유량 계약을 유지한다. sentinel 절단면이나 support 경계를 지형면으로 간주하지 않는다.

legacy erru/tau, 한 예보 주기의 차이, COM 유효값은 새로운 경계 공분산이나 수신
허용량의 근거가 아니다. 현재는 생산 변경 권한이 미확정이므로 기존 거부를 유지한다.
좌표·표현 오차와 관측/배경 근거로 독립 설정한 범위가 생긴 뒤에만 공동 필요조건,
face/부분집합 용량과 총 상한, 가중 최적화 순서로 진행한다. 새 거부조건이나
임의 source를 추가하는 작업으로 이 물리 결정 단계를 대체하지 않는다.

### PR #32 후속: 실제 face·기주 연결의 읽기 전용 검증

[물리 경계 매핑 실행 기록](LEGACY_PHYSICAL_BOUNDARY_MAPPING_20260921.md)에 따라
지면압력과 정규 pressure level, 실제 omega donor 위치를 구분한다.
`balstagger`의 수직 배치를 먼저 복원하고, legacy `dp`로 계산한 기주 합의
대수적 폐합을 물리 부분층·상단까지 포함한 적분과 별도로 평가한다.
미확정 지면 바람·회전·부분층 endpoint를 0이나 가까운 저장값으로 대신하지 않는다.

12/14 UTC LSX 중심차분은 사후 진단이다. 실시간 경향은 발행시각까지 도착한
자료만 사용하고, 같은 예보 주기의 미래 유효시각 값은 가용시각을 확인한 prior로
구분한다. 시간 표현오차를 경계 sigma로 간주하지 않는다.
새 지면 변수의 성분별 영향은 `Z^T D E_s`로 확인하되, 단순 인접 저장 face의
영향과 물리적으로 승인된 `E_s`를 구별한다. 지면과 연결되지 않은 support 성분을
지면식 하나로 해소할 수 있다고 가정하지 않는다. 기하 변경 시 D·성분·Z를 재구성한다.

### PR #33 후속: 공유 유량과 실제 층 두께

[pressure 공유 유량 연구 코드](PRESSURE_SHARED_FLUX_KERNEL_20260921.md)는
하부 PS와 유한 상단을 같은 interface 배열로 구성하고, 적분된 공유 face 유량에
`D=V^-1 B`, `G=-K B^T`, `A=D G`를 적용한다. 수평항은 끝점 바람을 층 평균으로
대체하지 않고 선언한 profile을 적분한다. 기존 공유 pressure 분할 함수를 재사용한다.
실자료 기하 실행은 완료했지만, 이웃 기주 사이 비공유 pressure 구간의 경사진
지면·유량 재구성은 OPEN이다. 이를 임의의 불투과 벽으로 닫지 않는다.
다음 작업은 실제 face surface와 바람·metric·시간 계약을 연결한 기주 수지이며,
생산 solver 전환이나 기존 부적합 문제 재실행은 그 이후다.

### PR #34 후속: 실제 경사진 면과 조건부 바람 적분

[경사진 pressure 면 실행 기록](SLOPING_PRESSURE_FACES_20260921.md)에 따라
실제 위·경도의 면적 보존 좌표와 삼각형별 PS 재구성에서 셀별 면 metric·1차 모멘트를
검증한다. 같은 시각 원본 LW3를 지면 위 공통 pressure 구간에서 적분한다.
이 결과는 전체 삼각 기주에 대한 연구 재구성이며 PR34의 수직 layer remap은 아니다.
producer의 grid-relative 설정을 조건으로 한 바람 적분과, metadata/실행 계보로 확정할
풍향 기준을 구별한다. 모든 면에 남은 지면 근처 미관측 profile 구간을 0이나 외삽으로
채우지 않는다. 다음은 같은 면의 지면 바람·기압 경향·유한 상단 omega를 연결한 완전한
기주 수지다. 그 뒤 수직 분할과 변경 권한·오차·증분 복원을 연결한다.

### 먼저 고정할 문제와 구현 경계

legacy의 현재 주석상 목표인 **지원 영역에서 전체 후보 상태의 pressure-coordinate
continuity `D(y_proposed + delta_y)=0`**를 수정 작업의 출발 계약으로 둔다.
이는 native 전체 질량식 확정이나 canonical의 증분 전용 `D(delta_y)=0`와 다르다.
여기서 전체 후보는 증분만이 아닌 절대 상태를 뜻하며, 지원 밖까지 무발산으로
만들었다는 의미는 아니다. 물리 잔차는 influence로 제외하지 않은 **전 영역의 모든
유효 pressure 행**과 지원 영역을 각각 보고한다. 기준 stencil은 현재
`continuity_point`의 `i=2:nx,j=2:ny,k=2:nz`와 기존 terrain/sentinel 판정이며,
물리 경계 face는 실제 저장 배열에서 읽는다. `R_after-R_before-R_delta` 항등식도
같은 stencil로 확인하되 이것만으로 solver의 `A=DG`를 증명했다고 하지 않는다.
부분 보정 `(I-B)D(y_proposed)`를 전체 균형이라고 부르지 않는다. 실제 물리 경계와
COM/지원 영역 때문에 이 목표가 불가능하면 그 후보를 거부하고 원인과 필요한
제약 변경을 기록한다. 수렴을 위해 RHS 평균을 빼거나 부분 보정으로 자동 전환하지 않는다.
목표를 바꾸는 경우 변경 이유·허용 영역·기대 잔차·acceptance를 함께 검토한다.

D는 실제 continuity의 stagger/metric/pressure 위치, G는 허용된 face 증분으로
정의한다. `apply_divergence`, `apply_increment_from_multiplier`와 그 합성으로
정의한 normal operator를 중심으로 구현하고, 행렬 계수를 저장해야 할 때도 같은
face 계수를 재사용한다. `A=DG`만으로 SPD를 주장하지 않는다. 비용 가중 K와
격자/질량 내적에 대한 adjoint, 실제 경계 제거, gauge를 확인한 뒤 solver를 선택한다.
기존 PHI·이류·마찰·수분·acceptance·허용오차를 이 작업에 묶어 임의 변경하지 않는다.

### 2026-09-18 구현 검토에 따른 경계 계약 명확화

기존 계획의 전체 후보 목표와 실패 거부 정책은 유지한다. 다만 기존 코드의 외곽
`lambda=0`은 경계 보정 유량을 허용하는 Dirichlet 조건이며, 그 유량에 대한 물리적
권한이 확인되지 않았다. 이번 legacy 교정은 **각 continuity 호출의 제안 상태가 가진
외곽·상하단 유량을 고정**한다. terrain/sentinel 또는 지원 밖 행과 접하는 face의
보정도 0이다. inactive lambda를 0인 외부 저장소처럼 사용하지 않는다. 별도 경계 유량
변경이 필요하면 자료·허용 유량·수지·승인식을 먼저 정의한다. 이번 변경은 BALCON의
다른 PHI/바람 단계 전체를 새 경계 문제로 재설계하는 것은 아니다.

- 입력 배열 전체에서 beta의 finite 및 `[0,1]` 범위, erru/tau/dx/dy/dp의
  finite/양수, ps/p의 finite 조건을 검사한다. 사용하지 않는 위치의 잘못된 값도
  전역 입력 오류로 거부한다. 양의 support가
  있으나 유효 active row가 하나도 없으면 성공한 영보정으로 바꾸지 않고 거부한다.
- Active row는 기존 pressure stencil, `ps>=p`, 양의 influence, 유효한 여섯 donor로
  정의한다. 유효하지만 지원 밖인 pressure 행의 진단은 별도로 계속 보고한다.
- G의 기존 stagger/gradient를 유지하되 수평 mobility는 실제 연결하는 두 pressure 행의
  beta/erru에서 구성한다. 같은 face coefficient에서
  `A=DG`의 행을 구성한다. 경계는 구성 때 제거하며 sweep 중 이웃 lambda를 덮어쓰지 않는다.
  이 방식에 최소분산 또는 adjoint/SPD 성질을 추가로 주장하지 않는다.
- RHS는 동일 divergence의 real64 산술로 구성한다. 저장 상태는 기존 real32이며,
  단정도 RHS 반올림이 닫힌 성분에 인공 net source를 만들지 않도록 구분한다.
- 닫힌 성분은 양방향 양의 연결로 구분한다. edge ratio로 얻은 양의 왼쪽 영벡터를
  각 edge의 상대 상세균형과 실제 `A^T w`로 검증한 뒤 `w^T b`를 검사한다. 두 대수 검사의 상대 반올림 한도는
  `4096*epsilon(real64)`이며 물리 잔차 허용오차가 아니다. 이 구성으로 영공간을
  인증할 수 없는 일반 비가역 metric은 `UNRESOLVED`로 거부한다. 임의 격자에 대한
  일반 왼쪽 영공간 solver를 완성했다고 주장하지 않는다. 모든 유한 상수 beta는
  RHS 가중과 구분한다. zero row의 비영 RHS는 크기에 관계없이 거부한다.
- 기존 200회와 승수 correction 기준을 유지하고, 최종 lambda의 실제 최대 선형
  잔차 `1e-10`도 요구한다. 저장 후 상태에는 같은 기준과 명시적인 real32 덧셈/
  divergence 반올림 bound를 검사하며 기존 BALCON 물리 acceptance를 완화하지 않는다.
- 성분·zero row·anchor 수, 경계 보정 flux, 전체/지원 영역의 물리 잔차,
  선형 잔차 RMS/max/위치 및 실제 U/V/omega 증분을 분리해 기록한다. 닫힌 호환
  성분의 상수 lambda 자유도는 물리 증분에 영향을 주지 않으며, zero 초기값과 고정
  sweep 순서로 계산한다. RHS 평균 제거 또는 강제 gauge 행 치환은 하지 않는다.

이는 P0-1–4의 구현 범위 보완이며 MR-C2 전체/native 물리 경계의 승인이나 실제
비영 ON 성공이 아니다. 실제 수정 행렬의 호환성·실행 결과로 상태를 갱신한다.

| 순서 / 연결 | 작업 | 종료조건과 실패 처리 |
|---|---|---|
| P0-1 / B06, R2–R3 | solver–갱신–진단의 `A=DG` 폐합 | 가변 influence/erru/metric/dp와 실제 terrain·상하단·측면 경계에서 동일 lambda의 두 적용 결과 비교; 사전에 선언한 반올림 오차 기준과 불일치 위치 기록. 실제 전체 격자 진단 필수 |
| P0-2 / B01–B03, MR-C2 | RHS와 influence 역할 일치 | 전체 상태 목표의 RHS `-D(y_proposed)` 및 support/고정 face/경계 flux를 명시; mobility와 행 가중을 구분. 불가능한 목표를 부분 보정 성공으로 대체하지 않음 |
| P0-3 / M05, M07, MR-C2 | 실제 경계 제거 후 성분별 해 존재·gauge | 닫힌 성분의 왼쪽 영공간과 RHS/경계 flux 호환성, anchored 성분과의 구분을 기록. 물리적 근거 없는 평균 제거 금지. 수정된 연산자에서 성분·호환성을 다시 계산 |
| P0-4 / B06 | 선형 잔차와 승수 correction을 분리 | 동일한 최종 lambda에서 `A lambda-b` RMS/max/위치, 최대 delta lambda와 실제 delta U/V/omega를 별도 기록; sweep 중 서로 다른 행의 값을 곱한 `max residual` 폐기. 진단 자체는 상태 무변경 |
| 이후 / R3 | 조건수·정밀도·전처리와 실제 ON 실행 | P0-1–4를 충족하고 계약을 바꾸지 않고 수렴 개선. 같은 NE57 전 영역에서 비영 후보 생성, 실패 시 원복·무게시; 200→2000 반복 실패를 정상/물리 개선으로 세지 않음 |
| 이후 / MR-C4 | 최종 A-grid·native before/after | destagger·지표 조정·회전·저장 후 실제 잔차 재검사; 같은 사례·설정에서 ready→startup/halo→consumed 비교, 별도 omega/W 전달 확인 |

P0-1과 P0-2는 함께 설계·검증한다. P0-3의 현재 **진단은 완료**됐으나 처리 정책과
수정 후 통과는 미완료다. **PR #25의 과거 경계/행렬 기준선**은 777,213 active row,
4성분 중 닫힌 성분
241/670/453개에서 왼쪽 영공간 호환조건을 위반했다. 최대 correction 정체 셀은 다른
anchored 성분에 있어 정체 원인을 이 한 사실로 단정하지 않는다. 전체 forcing 합이나
작은 influence 하나로 진단을 대신하지 않는다.

2026-09-18의 수정 계약(외곽/지원/지형 보정 유량 고정)에서는 같은 실제 배열이
723,638 active row, 222개 닫힌 성분(171개 zero row)으로 구성되며 모두 RHS
부적합으로 판정됐다. 이는 과거 3개 성분의 진단과 다른 행렬의 결과다. P0-3의
검사 구현과 부적합 진단은 진척됐으나 **호환성 PASS 또는 비영 ON은 아니다**.
후속 설계는 물리적 근거를 가진 경계 유량/지원 영역/제약 선택을 명시해야 하며,
현재 강제 상태를 맞추기 위해 외곽 lambda를 다시 0으로 고정하거나 평균 RHS를
제거하는 자동 우회는 허용하지 않는다.

추가 [수학·수치 검토](LEGACY_SUPPORT_ALIGNMENT_20260918.md)는 수평 mobility의 beta/erru
참조 위치가 active pressure 행과 달라 33,808개의 연결을 불필요하게 끊었음을 확인했다.
위치를 정렬한 뒤 active 723,638행과 RHS는 그대로이며 성분은 8개, 영행은 4개다.
8개 모두 부적합하고 가장 큰 성분의 잔차 하한은 약 `7.09e-6`으로 `1e-10`을 넘는다.
P0-3은 계속 OPEN이다. 다음 순서는 경계/source 또는 증분 목표의 수학적 해 존재 조건,
그 다음 스케일링·전처리이며, 미수렴을 반복수나 계수 floor로 우회하지 않는다.

구현은 단순한 Fortran 절차와 기존 구조를 사용한다. 새 scratch cwd에서
`tests/intel_toolchain.sh`의 pinned Intel O0/O2로 검증한다. 외부 GNU 대수 반례는
보조 검토 근거로만 구분하며 프로젝트 실행으로 합산하지 않는다. 작은 수학 커널
검사는 보조로만 허용하고 실제 전 영역의 비영 before/after를 대신하지 않는다.
성분별 호환·연산자 오차·선형 및 물리 잔차 기준은 결과를 본 뒤 완화하지 않는다.

레이더 원시 Vr·선택 시각·Barnes 계보와 native 소비 경로 조사는 병렬로 계속한다.
관측 수집 ±300초와 분석파일 정확한 valid time 계약을 유지하며, 외부에서 완성된
omega 관측을 요구하지 않는다. COM의 경험적 cloud-derived 성격과 관측/배경 의존성을
구분하고, 정당한 비지균 대류·냉기류·산악파를 제거하는 목표로 바꾸지 않는다.
총수분/잠열·분석증분·경계/강수 유출, 첫 미세물리 및 초기 충격은 최종 소비 상태에서
별도 평가한다. 이 계획 변경은 물리 균형 PASS나 native 게시 승인이 아니다.

## 2026-09-15 추가 검토 반영 — 수식 수정과 native 통합 종료조건

검토 기준은 PR #5 병합 `ba45e8f6b9ed3bbd6fba5ddf2766133a3fe2657a`, tree
`948683c18fb43fd5235f6288373864e5f0b9707c`다. 이전 `816c038`과 구분한다.
종별 엔탈피·유한 상변화, 보존적 pressure remap, 제한된 outer feedback,
upstream 입력 및 native W 전달 부품은 이미 존재한다. 이를 미구현으로 되돌리지 않는다.
다만 루틴 시험·소스 존재·모델이 소비한 전체 초기장의 물리 정합성은 별도 판정이다.
이 절은 **후속 구현·검증 계획**이며 아래 결함을 수정 완료로 처리하지 않는다.
사용자 검토의 여섯 수식 반례는 독립 Python 재계산 근거로 인용하며, 이 계획 갱신에서
해당 파일이나 pinned ifx·NetCDF·startup 실행을 재현했다고 주장하지 않는다.

PR #6 병합 `3a7f4696270d7a8a6b350534ddf4491ba0e1f064` 이후 추가 검토도 반영한다.
PR #5와 비교한 `src/tests/tools/patches/config` tree는 동일하다. 아래 보강은 설계
결정이며 소스 수정이나 새 회귀시험 PASS가 아니다.

PR #7 병합 `7320165f1544668e2b20653a29d587be4581a6a9` 이후 검토는 raw/seed 단계,
최종 수정 후 잔차와 진단 비침습성 계약을 보강한다. **2026-09-15 사용자 계획 승인 완료이며,
구현 체크리스트·체크포인트의 팀 검토 후 코드 수정·회귀시험에 착수한다.** 첫 구현은 독립적인 legacy
P0 묶음, 다음은 native 전달로 나누고 레이더 자료·계보 조사는 병렬로 진행한다.

관측오차 공분산 방향, native 혼합상 정책, PASS/수동 폐합 구분 등 이전 문서 교정은
반영된 상태로 유지한다. 이후 검토는 실제 계산·소비 경로의 이행 여부에 집중한다.

| 우선순위 / 연결 | 수정·결정할 작업 | 종료조건 |
|---|---|---|
| P0 / B06, R3 | legacy `nonlin`의 압력미분 부호와 전체/섭동 omega 계약을 한 묶음으로 수정 | 실제 호출 인자·단위와 네 U/V 미분을 함께 검증; affine pressure 미분 및 영섭동 항등식의 생산 루틴 O0/O2 통과 |
| 통합 전 P0 / M06, E03, MR-C4 | baseline·staged candidate·geometry·실제 U/V 증분과 payload 결속 | 같은 시각·shape의 다른 수직 상태도 거부; actual native relevant fields를 소비 직전 대조 |
| 통합 전 P0 / M07, MR-C4 | seed와 최종 지형 하부 W의 전체값 경계조건 | pinned host의 stagger/map factor/CF·경계 stencil로 baseline와 consumed 상태 모두 검사; startup 후 재읽기 |
| P1 / B01, E03, E05 | mask 밖 실제 수평풍 변경 및 payload 재적용 처리 | 지원 밖 변경은 후보 거부 또는 관련 U/V/W를 함께 rollback; 재시도로 delta W가 두 번 더해지지 않음 |
| 새 결합 구현 P0 / MR-C0–C2 | 레이더별 관측→Barnes 사용 계보·정보 평가→전체 질량식·경계 선택 | 외부 paired target 없이 내부 진단 경로와 최소 수평풍 보정의 실현 가능성을 확정 |
| 병렬 P1 / G02, E03 | exact-source 시험·공개 CI와 소비 readback 연결 | code/input/config/compiler·실제 소비 상태가 같은 사례에 결속; CI 부재가 격리 연구를 막지는 않음 |

P1인 mask·재시도 항목도 native 통합 승인 전에 닫는다. P0/P1은 작업 우선순위이며
낮은 우선순위라는 이유로 MR-C4 완료조건에서 제외하지 않는다. 레이더 자료 연결과
기하 평가는 수식 수정·전달 계약 설계와 병렬 진행할 수 있다.

### PR #10 당시 후속 조건 — 실제 격자·terrain·원복 시험 연결 (역사 기록)

PR #10 병합 `2316cfe27490577cc15bafd4b9be27740b9da1e3`
(tree `f5f42d773c9b9f2081a17263ea3c26fc3e94bb96`) 당시에는 네 압력미분 부호와
전체/섭동 omega 구분이 생산 `nonlin` 루틴 범위에서 교정되었고, 아래 세 조건이
후속 과제로 남아 있었다. PR #11 병합 `f55c0b1`에서 실제 `balstagger` pressure
연결, active terrain donor, OM/OMO 원복 검출력의 제한적 `PASS_SCOPED` 근거가
추가되었다. 이 절의 표와 설명은 PR #10 시점의 계획과 그 후속 실행 이력이다.
문구 반영 자체와 실행 PASS를 구분하며 전체 B06·CP02/MR 상태는 유지한다.
사용자가 제공한 GNU Fortran 14.2.0 O0/O2 결과는 외부 교차검증 기록이다. 첨부 묶음을
이 작업공간에서 재실행한 근거가 아니며 프로젝트의 pinned ifx 검증을 대체하지 않는다.

| 순서 / 연결 | 후속 작업 | 종료조건 |
|---|---|---|
| 1, P1 / B06 | 실제 `balstagger→nonlin` pressure 좌표 연결 | 원래 U/V affine 입력부터 생산 stagger를 거쳐 균일·비균일 내부 및 상단 경계의 기대 미분/연직항 검증 |
| 2, P1 / B06 | active omega stencil의 terrain donor 유효성 | 전체/배경 중 한쪽 또는 양쪽의 필수 `bnd` donor를 검출; 진짜 0은 수용하고 terrain target skip은 유지 |
| 3, P2 / B06 | OM/OMO 변경 후 실패하는 caller fixture | snapshot 후 보호 배열을 실제 변경; 원복 성공 및 각 대응 복원문 삭제 변이의 실패 확인 |

**Pressure 좌표 (PR #10 당시 미해결):** 당시 `balstagger`는 `k<nz`에서 U/V를
입력 `p(k+1)`의 값으로 옮기고 최상층을 복제했다. `nonlin`에 직접 `u_k=a*p_k+b`를
넣는 기존 시험과 구분해야 했으며, 중복 상단의 영향을 받지 않는 내부에서 당시 연결식은
`D_p u_stag(k)=a*(p(k)-p(k+2))/(p(k-1)-p(k+1))`가 되어 affine에도 좌표 오차가 남았다.
원래 pressure와 실제 wind-pressure 좌표·유효 level을 구분하고 미분 donor의 실제 위치로
분모를 정의하는 조건은 PR #11의 제한적 pressure 연결 시험으로 닫혔다. 복제된 상단을
독립 물리 level로 사용하지 않는 상단 stencil/적용 범위와 공통 dp를 사용하는 다른
연산자의 계약도 함께 확인했다.
연결시험에는 `p=(100000,90000,85000,70000) Pa`, 배경 U 기울기 `1e-4`,
`delta omega=0.5 Pa/s`의 기대 연직항 `5e-5 m/s^2`와 V 대응항, 균일격자 상단을 포함한다.
사용자 반례의 `6.66667e-5` 및 `2.5e-5`는 후속 회귀의 오류 검출 기준이며 실제 예보 오차가 아니다.

**Terrain donor:** `bnd=1e-30`의 내부 제외 의미를 helper의 계약에 연결한다.
정확한 sentinel 또는 명시적 유효성 정보를 전달하며 0 근처 임계값으로 대체하지 않는다.
active target의 필수 donor가 제외되면 실패 또는 명시적 비적용으로 처리하고, 그 선택과
caller 원복을 시험한다. 전체/배경을 따로 재가중하거나 누락을 0의 정상 증분으로 숨기지 않는다.
양쪽 같은 sentinel, 한쪽만 sentinel, 실제 0, 제외 target skip을 별도 사례로 둔다.
실제 terrain 처리 후 active stencil에서의 발생 영역·빈도는 별도 확인하며 커널 반례만으로
운영 영향의 크기를 단정하지 않는다.

**원복 검출력 (PR #10 당시 미검증):** 당시 시험은 실패 후 8개 배열의 동일성을
확인했지만 OM/OMO가 snapshot 이후 바뀌지 않아 해당 복원 분기를 행사하지 않았다.
PR #11에서 작은 fixture가 실패 전에 보호 배열을 변경하고 각 복원문 삭제 변이를
검출하는 제한적 근거를 추가했다. 이 근거도 continuity/relaxation을 포함한 전체
BALCON 실행 증거로 확대하지 않는다.

후속 시험은 `tests/intel_toolchain.sh`의 pinned ifx, 새 실제 scratch cwd에서 O0/O2로
실행한다. 기존 수정·오류 복원 변이시험은 유지한다. 별도 대형 감사 계층은 추가하지 않는다.
Native fresh-start seed/적용/경계·halo/첫 small-step readback과 레이더별 Vr·Barnes 계보
조사는 병렬로 계속하며, 외부 omega target을 필수 경로로 되돌리지 않는다.

### PR #11 병합 기준 — B06 P1 가변 omega collocation

현재 기준은 PR #11 병합 `f55c0b1`이다. 기존 B06 제한 범위의 세 항목인 실제
`balstagger→nonlin` pressure 연결, active terrain donor 유효성, OM/OMO 원복 검출력은
각각 `PASS_SCOPED`를 유지한다. 새 B06 P1 가변 omega collocation의 제한적 구현·시험
결과도 MR 체크리스트의 별도 실행 근거에서 `PASS_SCOPED`로 추적한다. 이 추가 항목은 기존 B06
범위를 세분화한 계획 기록이며 새 MR/CP checkpoint ID나 대형 감사 계층을 만들지 않는다.

실제 collocation 계약은 다음과 같다.

- 내부에서 `omega(k)`는 `p_k`와 `p_{k+1}`의 pressure midpoint에 있고, wind level은
  `p_{k+1}`에 있다. 내부에서 동일 가중 double-average를 쓰면 affine omega 기울기 `c`에
  `c/4*(p_k-2*p_{k+1}+p_{k+2})`의 오차를 남기므로 pressure-distance weights로
  두 midpoint를 `p_{k+1}`에 보간한다. 내부 간격 `a=p_k-p_{k+1}`, `b=p_{k+1}-p_{k+2}`에
  대해 하부 midpoint 가중은 `b/(a+b)`, 상부 가중은 `1-b/(a+b)`다. 상단 가중은 `(0,1)`이다.
- 전체 omega와 background omega는 같은 horizontal pair 및 같은 pressure-distance
  weights를 사용한다. 필수 donor가 invalid이면 independent renormalization 없이
  caller를 reject하고 snapshot 상태로 rollback한다. weight가 정확히 0인 donor는
  산술·finite/sentinel/range validity 검사에 들어가지 않는 unused donor다.
- 최상층에는 저장된 `omega(nz)` 실제 endpoint만 사용한다. 상단에서 0 weight인 unused
  midpoint donor가 missing이어도 산술에 사용하거나 유효성 검사하지 않으며, 복제층을 새
  물리 donor로 만들거나 다른 donor로 재가중하지 않는다. 기존 `balstagger` mapping,
  공통 `dp`, continuity 계약은 변경하지 않는다.

제한적 시험 범위는 실제 forward→nonlin 경로에서 constant/affine omega를 U/V의
각 isolated term (`omega_b*d(delta_u_or_v)/dp`, `delta_omega*d(u_or_v_b)/dp`)별로
uniform/nonuniform pressure의 interior/top에 적용하는 것이다. 여기에 total과 background가
같은 varying field라서 delta가 0인 사례, required donor missing의 reject+rollback,
정확히 0 weight인 top midpoint donor missing의 산술·유효성 검사 제외를 포함한다. 고차 curvature/수렴,
이 helper 시험만으로 full BALCON, native startup/readback, 과학 검증을 주장하지 않는다. 문서의 계획 반영과
체크리스트의 실제 실행 근거를 구분한다.

### PR #12 이후 연결 검증

기존 pressure·terrain·원복·omega collocation의 제한적 완료는 유지한다. 다음 범위인
작은 합성 forward→전체 BALCON→reverse 연결은 pinned ifx O0/O2에서 비영 승인 및
계산 후 PHI 비수렴 원복을 확인했다. 확장 실행에서 발견한 진단/역 stagger 상단 bounds는
작은 guard 수정으로 처리했으며 근거·시험용 metadata 경계는 MR 체크리스트를 따른다.
이 시험의 산출물은 메모리 배열이다. 실자료 main/writer, native fresh seed→후보→consumed
및 레이더별 Vr·Barnes 계보 연결은 별도 실행 과제로 유지한다. 고차 profile 연구를 이들
연결의 일률적인 선행조건으로 추가하거나 새 외부 omega target을 요구하지 않는다.

### PR #13 이후 시험 범위 보강

PR #13의 합성 전체 BALCON 실행과 상단 보호는 제한적 완료로 유지한다. 기존 입력의
U/V/omega는 0이므로 기록된 continuity는 **역 stagger 전 잔차 유지**의 근거다.
비영 초기잔차 감소와 최종 출력 정합성을 해당 수치만으로 주장하지 않는다.

- 경계 flux와 양립하는 국지 발산·수렴 입력을 정 stagger부터 연결한다. 시험 입력의
  비영 최소신호와 감소율을 실행 전에 고정하고, 기존 acceptance를 완화하지 않는다.
- 여섯 역변환 출력의 finite 및 합성 수분 범위를 검사한다. A-grid 해석해 재현과
  출력 위치에 맞는 독립 차분 검사를 별도로 두며 staggered continuity 연산자를
  A-grid 배열에 그대로 적용하지 않는다.
- 실제 BALCON 출력의 독립 잔차 기록과 알려진 해석해의 PASS를 구분한다.
  경계·terrain·비균일 pressure·native 잔차 검증으로 확대하지 않는다.
- 역변환 해석해는 원래 A-grid 배경과 다른 staggered 후보를 사용해 출력 갱신을 검사한다.
  정답으로 미리 채운 배열의 불변만으로 PASS하지 않으며, projection 생략과 역변환 PHI
  대입 누락을 scratch 소스 변이로 검사한다. 음성시험은 지정된 수치 검사에서의 거부를
  요구하고 컴파일 실패·임의 실행 오류를 검출 성공으로 집계하지 않는다.
- 입력 경계 유량과 승인 후 경계 유량을 구분한다. solver가 조정하는 경계에 임의의
  불변 조건을 추가하지 않으며, 합성 내부 재구성 검사만으로 전체 출력 질량 폐합을 승인하지 않는다.

### PR #15 이후 — 첫 합성 BALCON writer/readback 시험 (PASS_SCOPED)

현재 B06 기준은 merged PR #15 `1eebfe1`이다. PR #14의 A-grid 항별 검출력과 실제
실행 `cwd` 검사는 해당 범위에서 `PASS_SCOPED`로 종료했으며 다시 열지 않는다. 기존
P0 pressure·omega·terrain·원복 및 합성 BALCON 제한 범위도 같은 상태로 유지한다.

완료된 첫 실행은 승인된 6×6×4 국지 BALCON 역변환 메모리 후보를
`write_bal_laps` → `write_laps_data` → 실제 NetCDF로 보내고, 독립 파일 reader로
`U3,V3,T3,HT,SH,OM` 여섯 필드와 pressure-level vector, valid time, units,
all-valid mask를 확인하는 작은 writer 시험이다. `U3,V3,T3,SH,OM`과 shape·level·time·
units·mask는 선언된 저장 표현에서 원소별 정확 일치로 비교한다. `HT`는 원본 `PHI`와
같다고 보지 않고 선언한 `HT=PHI/g`, `g=9.80665 m s^-2` 변환 결과를 선언한 저장
정밀도에서 비교한다. 새 허용오차나 다른 변환을 임의로 만들지 않는다.

이 시험은 full main의 `sfctempadj`·rotation·RH 과학 검증과 native startup/consumed
검사를 실행하지 않는다. native consumed는 이 파일 시험 다음의 별도 R4/MR-C4 단계이며,
그 완료를 작은 writer 시험의 선행조건으로 두지 않는다. pinned ifx O0/O2의 실제 writer와
독립 재읽기는 아래 체크리스트 근거에 따라 `PASS_SCOPED`다. 기존 CP02 메타데이터 보정
로직으로 오래된 온도/RH `valid_range`를 제거한 private CDL fixture를 사용하며, 원본
CDL·운영 설정·게시 경로를 변경하거나 검증한 것은 아니다.

### Legacy nonlin 수정 묶음

PR #10에서 교정한 국소 계약은 배열이 해당 pressure에 놓인다는 전제다.
감소하는 pressure level에서 `dp(k)=p(k-1)-p(k)>0`이다. 따라서
`du/dp=(u(k-1)-u(k+1))/(dp(k)+dp(k+1))`의 부호를 사용하거나 동일한 signed
pressure 차이로 계산한다. background/perturbation U/V의 네 미분을 함께 수정한다.
`u(p)=10^-4 p`이면 결과는 `+10^-4`여야 한다. 비균일 격자의 affine 검증도 포함하되,
이는 부호·선형 일관성 검사다. **P0 부호·섭동 수정과 P1 비균일격자 정확도 개선을 분리**한다.
`a=p(k-1)-p(k)>0`, `b=p(k)-p(k+1)>0`에서 양끝 차분의 전개는
`Ds u = u' + (a-b)u''/2 + (a*a-a*b+b*b)u'''/6 + ...`다.
비대칭 간격비를 유지한 세분화에서는 일반적으로 1차 오차이며, `a-b=O(h^2)`인
매끄러운 격자족에서는 2차가 가능하다. 실제 pressure inventory와 격자족을 먼저 확인한다.
필요시 검토할 3점 1차 미분식은
`D2 u = [(b/a)(u(k-1)-u(k)) + (a/b)(u(k)-u(k+1))]/(a+b)`다.
2차 함수에 정확하고 균일격자에서는 중앙차분이다. 곡률·격자수렴과 간격비에 따른
반올림 민감도는 P1로 검사하며, affine PASS로 정확도 검증을 대신하지 않는다.
`p=(100000,90000,85000) Pa`, `u=10^-8(p-90000)^2 m/s`의 중앙 미분은
정확값 0, Ds는 `5e-5`, D2는 0이다. 독립 산술 예제는 생산 루틴 실행 증거가 아니다.

연직 섭동 이류는 `omega_b*d(delta_u)/dp + delta_omega*du_b/dp`와 V의 대응식이다.
호출부와 함수에서 background와 delta를 명확히 구분하고, 전체 omega를 delta로
전달하지 않는다. 전체/배경 omega를 명시적으로 받아 내부 face 값에서 delta를 구하는
작은 구현도 검토하되, 연속성에 필요한 전체 omega를 덮어쓰거나 불필요한 3-D 배열을
추가하지 않는다. omega 부호·Pa/s·stagger를 같은 시험에서 확인한다. 수정 대상은
`src/balance/qbalpe.f`의 `balcon→nonlin` 경로다. `src/sfc/lapsvanl.f`의 별도
동명 호출은 인자 구성이 다르므로 링크·호출 범위를 확인하기 전에 일괄 치환하지 않는다.
`delta_u=delta_v=delta_omega=0`이면 background shear와 omega가 비영이어도
섭동항은 0이어야 한다. 미분 부호만 고친 비영 결과를 정답으로 인정하지 않는다.
`I(omega-omega_b)=I(omega)-I(omega_b)`는 같은 선형 보간 I에서만 사용한다.
전체/배경에 동일 donor·가중·유효성 기준을 적용하고 필수 donor 결측을 독립 재가중으로
숨기지 않는다. missing sentinel끼리 뺀 0도 유효한 영섭동이 아니다.
`omega_b*d(delta_u)/dp`만 비영인 경우와 `delta_omega*du_b/dp`만 비영인 경우를
U/V 각각 분리해 시험하여 항간 상쇄가 결함을 가리지 않게 한다.
비교용 원본은 보존하지만 잘못된 수식과의 바이트 일치를 새 경로의 정당화로 쓰지 않는다.
운영 영향 크기는 실제 binary–source 결속과 대조실험 전에는 단정하지 않는다.

### Native W 소비의 최소 계약

원본 `x_b_raw`와 준비 완료 `x_b_seed=N0(x_b_raw)`를 구분한다. N0는 pinned host의
첫 시간전진 전 필요한 초기·경계 준비 처리이며, 원본 파일은 불변으로 보존한다.
W 증분의 baseline은 준비 완료 seed다. `raw_state_id`와 기존 `baseline_state_id`의
관계를 기록하고, 모든 baseline U/V·W·geometry는 같은 seed 단계에서 취한다.
raw W=0은 host가 준비하는 정상 입력 표현일 수 있으므로 seed의 하부 경계 검사를
raw에 그대로 적용하지 않는다. 준비 완료 seed/consumed의 부적합 W는 거부한다.
N0의 W time level·내부 초기 처리·경계/halo·설정·파일/메모리 지점은 **미확정**이며
pinned host에서 고정한다. 실제 routine의 호출 전후 위치, 보존할 질량·geometry·지속 상태,
이미 끝난 처리와 후보 적용 후 재개할 호출을 함께 기록한다. 바닥 W 채우기만으로 전체 준비를 재현했다고 하지 않고,
전체 startup을 무조건 두 번 호출하거나 시간적분·외부 omega target으로 대신하지 않는다.
여기서 `x_b_ready=x_b_seed`이며 ready는 같은 준비 완료 연산 단계를 뜻한다.
알고리즘 효과는 같은 단계의 `delta x_CB=x_c_ready-x_b_ready`로 비교한다.
정상 준비 변화 `x_b_ready-x_b_raw`는 별도 기록하며 Cloud-BAL 증분으로 집계하지 않는다.

최소 식별 정보는 `baseline_state_id`, `staged_candidate_state_id`,
`geometry_fingerprint`, `increment_id`, `mapping_assumption`이다. 문자열·hash를
추가하는 것만으로 종료하지 않는다. 실제 native의 P/PB, PH/PHB, U/V, W와 필요한
질량·수직좌표·metric·시각의 결속 범위를 정하고, payload P/Z·미분값 및 DELTA_U/V가
그 배열에서 유도됐음을 소비 직전 검사한다. 정확한 필드 집합과 mapping은 **미확정**이며
R2에서 pinned host 정의에 맞게 선택한다. baseline U/V 파일, candidate U/V 파일,
W seed 파일, 최종 staged 파일의 역할을 분리하고 consumed U/V는 stage에 실제 저장된
candidate U/V를 뜻하도록 고정한다. 소비하는 host 경로별 W-level pressure 재구성,
중력상수·metric stencil·저장 정밀도도 선택·결속하기 전에는 payload를 exact native로
부르지 않는다. 변환식의 고정 geometry·동일 시간경향
가정이 깨지는 후보는 현행 증분 변환에 그대로 넣지 않는다.
예를 들어 `w=A*omega`, `A=z_eta/p_eta`이면 geometry 변화 시
`delta w=A_b*delta omega+delta A*omega_b+delta A*delta omega`다.
현재 고정 geometry 식이 뒤 두 항을 누락하는 후보는 음성시험으로 거부한다.
기존 식별 필드에는 역할을 붙인다: 불변 baseline, W 적용 전 `candidate_pre_w`,
재읽기 완료 `candidate_post_w`, startup 후 `consumed`, 입력 쌍과 mapping을 담은 payload.
기존 receipt를 재사용하고 `delta U/V=candidate_pre_w U/V-baseline U/V`를 실제 저장값으로
검사한다. 별도 hash 체계를 늘리기보다 relevant-field 범위와 변경 전후 역할을 고정한다.

`actual changed U/V support ⊆ validated W mapping support`를 native stagger와
보간 footprint에서 검사한다. mask 밖 payload NaN을 무시하는 것과 실제 staged
U/V 변경을 누락하는 것을 구분한다. 대응하지 않는 수평풍 변경을 남긴 채 W만 생략하지 않는다.

첫 구현의 재시도 정책은 **불변 준비 완료 seed에서 매번 새 private stage 생성**으로 선택한다.
존재하지 않는 경로에만 생성하고 승인된 candidate U/V 등 변경을 같은 입력에서 재구성한 뒤,
`candidate_pre_w`·payload·geometry·지원 영역을 대조하여 W를 한 번 적용한다.
실패·중단 stage는 재사용하지 않고 성공한 재읽기 결과만 다음 단계로 전달한다.
동일 stage에 같은 payload를 다시 적용하면 명시적으로 거부한다. 생성·거부를 보장하는
기존 실행 경로와 receipt 필드의 구현·시험은 미완료다. write 직전 W 비교만으로 이력을
대신하지 않는다. 반복 요청은 서로 다른 새 stage에서 같은 검증 결과를 내며,
기존 경로 덮어쓰기·중단 후 재사용·같은 stage 중복 호출은 거부하는 시험을 둔다.

고정 지형의 native 하부 연산자를 B라 하면 `W_seed,s=B(U_base,V_base)`와
`W_consumed,s=B(U_consumed,V_consumed)`를 모두 확인한다. 증분
`delta W_s=B(delta U,delta V)`만으로 baseline 경계 오류는 고쳐지지 않는다.
경사 0.01·수평풍 10 m/s·delta U=0·seed W=0인 반례는 부적합으로 검출해야 한다.
이 반례는 준비 완료 seed에 적용하며, raw W=0 자체를 실패로 분류하지 않는다.
baseline 경계를 먼저 검증한 뒤 최종 **하부 W만 실제 저장된 candidate U/V에 B를 적용해
재계산**한다. 내부 W는 기존 mapping을 유지한다. 하부 재계산도 명시된 변경 지원 영역에
포함하며, 지원 밖 변화가 필요하면 조용히 덮어쓰지 않고 후보를 거부한다.
변경된 U/V 자유도 집합 M_UV에 대해 하부 영향 영역은
`M_s={s: 어떤 f in M_UV에 대해 B_sf != 0}`로 정의한다. 작업 배열에서 B(candidate)를
구하고 승인된 stencil 출력 영역만 기록한다. 영역 밖 W는 seed 값을 정확히 유지하면서
전체 하부 잔차도 검사한다. U/V 셀과 W 셀의 같은 인덱스 mask로 대체하지 않는다.
실수에서 B가 선형이어도 real32 저장·연산 순서에 따른 bitwise 일치를 요구하지 않는다.
`epsilon_s=epsilon_physical+epsilon_arithmetic+epsilon_input`의 오차 출처와 중복 여부를
분리하고, 상쇄 시에는 결과 |B|만이 아니라 stencil 항 절댓값 합과 저장 오차를 고려한다.
CF 계수·map factor·비주기 경계 stencil에 따른 각 상한은 R2에서 근거로 확정한다.
반례의 작은 반올림 차이를 허용오차로 복사하거나 부적합 baseline을 맞추도록 조정하지 않는다.
`use_input_w` 보존 patch의 제거/전역 덮어쓰기 대신 이
검사를 적용하고 첫 시간전진 전 consumed 배열에서도 반복한다. 과거 v2 paired
readback은 선언된 증분 전달 범위의 이력으로 보존하며 seed의 전체값 경계조건을
확인한 M07 승인 증거로 사용하지 않는다. 임의의 새 입력도 자동 승인하지 않는다.

최종 검사는 **내부 증분→하부 W 재계산→최종 정밀도 저장→native 재읽기→실제 W/WW·
질량·metric 유량 재계산→전체 질량/하부 경계 잔차→첫 시간전진 전 consumed 재확인**
순서로 수행한다. 경계·halo 등이 다시 상태를 바꾸면 그 이후의 배열에서 재평가한다.
고정 geometry·동일 질량 경향에서는 `r_final=r_before+D*delta F_last`이므로 solver의
중간 PASS가 최종 PASS를 대신하지 않는다. geometry/질량도 변하면 전체 식을 재계산한다.
영증분 시험은 다음 세 범위로 구분한다. raw 원본 불변은 이들과 별도 불변량이다.

| 시험 범위 | 전제와 비교 대상 | 판정 |
|---|---|---|
| W consumer 단독 | 경계에 맞는 진입 직전 후보 상태에서 다른 입력·geometry·설정을 고정하고 `delta U=delta V=delta omega=0` | `W_post=W_pre`, `x_nonW_post=x_nonW_pre`; 이미 승인된 후보 필드를 baseline으로 되돌리지 않음 |
| 전체 pipeline 영변경 | 수분·온도·압력·바람 등 **모든** 제안 변경 `delta x_requested=0`, 같은 준비 조건·ready 단계 | `x_c_ready=x_b_ready` |
| 물리 변경 coupled 후보 | 수상체·열역학 등을 포함한 승인된 변경이 있음 | 각 필드의 후보 일치 및 수분·엔탈피·질량·경계 잔차 검사; 전체 baseline 동일성을 요구하지 않음 |

바람 영증분만으로 전체 상태 영변경을 추론하지 않는다. 첫 행의 pre/post는 consumer
적용 직전/직후이며 startup 전후 차이가 아니다. 기존 영증분 fixture의 전제와 비교 대상을
이 구분에 맞추고 별도 요구사항 ID를 추가하지 않는다.

### 추가할 작은 회귀·적대시험

| 시험 | 기대 판정 / 근거 연결 |
|---|---|
| U/V affine pressure profile; P1 곡률·격자수렴 별도 | P0 부호·선형 일관성; 일반 비균일 정확도와 구분 / B06 |
| 영섭동·각 연직 이류항 단독 비영·필수 donor 결측 | 유효 donor에서 항별 정답, 결측을 가짜 0으로 처리하지 않음 / B06 |
| 같은 시각·위경도·shape, 다른 P/Z·수직 geometry | 소비 전 거부, W 무변경 / M06, E03 |
| 실제 staged U/V 변경이 W 지원 밖에 존재 | 후보 거부 또는 관련 전체 변경 rollback / B01, E03 |
| 새 stage 재시도·기존 경로·중단 stage·같은 stage 중복 | 새 stage 결과 재현, 덮어쓰기·재사용·중복 거부 / E03, E05 |
| 경사 지형·비영 baseline U/V·부적합 seed W | 하부 전체값 경계 오류 검출 / M07 |
| 일관된 seed·알려진 surface delta U/V·저장 상쇄 | 저장 candidate U/V로 하부 B 재계산 및 오차 출처별 검사 / M07, MR-C4 |
| 초기화 phase ledger와 첫 MP 전후·낙하 유출 | 종전환·강수·수치 조정·경향 적용 시점을 분리해 수지 검사 / T03, MR-C5 |
| source-bound 사례의 O0/O2·startup readback | 같은 입력·설정·코드의 실제 소비 확인 / G02, E03 |

기존 native 사례에 raw→seed 정상 준비, W 전달 단독 영증분과 전체 pipeline 영변경, 하부/저장/경계 처리 후
잔차 및 진단 on/off 동일성을 추가한다. 별도 요구사항 ID나 큰 시험 계층은 만들지 않는다.

기존 시험에 작은 fixture를 추가하고 새 범용 감사 프레임워크를 생산 FORTRAN에
넣지 않는다. kernel 단독, NetCDF consumer, 실제 startup 시험의 PASS 범위를 분리한다.
전체 질량식은 `dot(m_d)+D F_d=0`의 경향·경계 가정을 먼저 고정하며, 기존 증분
projection RHS만 바꿔 full-state 균형을 달성했다고 하지 않는다. 다섯 feedback field의
저장값 고정점도 수상체·pressure geometry·native 전체 결합 수렴으로 승격하지 않는다.

다음 통합 milestone (위 PR #25 P0 폐합 이후): **하나의 고정 사례에서 레이더별 관측과 Barnes의 관계를 확인하고,
내부 결합 후보를 정확한 baseline에 결속해 전달한 뒤, 첫 시간전진 전 전체 하부 경계·
질량·열역학 잔차를 독립 재검증한다.** 이후 동일 수상체·열역학·pressure 처리·native
baseline으로 관측/균형 제약만 달리하여 초기 충격, 남한 육지의 1–6 h RN1/PTY·CSI를
평가한다. 기존 OFF/HYDRO/LIQUID 간 record·입력 우선순위·지표압 분기 차이를 순수
omega 효과로 해석하지 않는다. 새 결합 초기화의 과학·운영 승격은 아직 미승인이다.

## 1. 목적과 기존 과제와의 관계

시선속도를 이미 반영한 다변량 Barnes 수평풍, 기존 구름·수상체 및 열역학 분석장을
출발점으로 사용한다. 다중 레이더의 관측 기하가 제공하는 연직 정보와 질량·역학 제약을
함께 이용하여 **시간 적분 전에** 상승·하강 기류가 있는 3차원 초기장을 만든다.
초기 수상체가 이후 성장·발달·소멸할 수 있도록 스핀업을 줄이되, 변경에 따른 비물리적
압력 진동과 중력파·음향파 충격을 억제하는 것이 목적이다. 수상체의 영구 유지나
모든 구름에서 상승류를 강제하는 것은 목적이 아니다.

이 문서는 CP02/CP06의 물리 연산자 작업에 추가한 실행 계획이다. 기존 CP02 여섯
요구사항을 대체하거나 완료 처리하지 않는다. CP02 #4의 실제 결합 후보 native 전달과
CP06-A 물리 검증에 연결하며, 후속 적분 검증은 CP06-B와 연계한다.
기존 외부 모델 궤적 기반 omega 생산안은 비교 기록으로만 유지한다.

핵심 원칙:

- 기존 관측자료는 이미 원본 디렉토리에서 처리·통합되어 사용 중이다. 자료 부재를
  가정하지 않고 현재 입력과 레이더별 중간 산출물의 보존 범위부터 확인한다.
- Barnes U/V는 시선속도가 반영된 분석장이다. 원시 시선속도와 이 분석장을 독립적인
  두 관측으로 취급하지 않는다. 레이더 관측 연산자의 연직 성분 누락 여부도 확인한다.
- W 단독 주입이나 계산 후 마스크를 곱하는 방식으로 균형을 주장하지 않는다.
  분석장 보존을 우선하면서 필요한 최소 U/V·압력·열역학 보정을 함께 구한다.
- cloud omega 경험함수를 새로 만들지 않는다. 입자 낙하속도 관측 보정은 공기 연직풍
  경험함수와 구별하되, 기존 물리·입자종 정보에 근거하고 오차를 명시한다.
- 모델 시간 적분은 초기화 이후 검증에만 사용한다. 직접 omega 관측이나 외부 모델의
  omega target을 입력 필수조건으로 추가하지 않는다.
- 외부 모델의 omega/`w` target은 요구하지 않는다. Barnes 초기 분석장은 시작값 또는
  background일 뿐 독립 prior가 아니며, 같은 radial 표본을 다시 독립 관측으로 가중하지
  않는다.

## 2. 확인된 출발점과 해결해야 할 결함

현재 입력 경로의 `main_sub.f`는 `get_multiradar_vel`에서 레이더별 격자 시선속도,
Nyquist 관련 값, 레이더 인덱스·위치·이름·시각을 받는다. 읽기 경로가 존재한다는
것과 해당 사례에 모든 값이 유효하게 남아 있다는 것은 구분한다. 해당 소스의
900초 허용시간은 기존 수평풍 입력 설정이며, 연직풍 복원에 그대로 적합하다고
간주하지 않는다.

현재 Cloud-BAL reader는 합쳐진 U/V와 dBZ를 받으며 레이더별 Vr·빔 기하·QC/관측시각을
받지 않는다(`radar_los_used=0`). 따라서 기존 상류 자료를 조사해 필요한 필드만 연결하는
입력 확장이 R0/R3에 필요하다. 이는 관측자료가 없다는 뜻이 아니다.
기존 state의 `radar_los` 구조와 validator를 우선 검토하되, 현재 stage payload가 LOS
부재를 요구하는 계약도 함께 검토한다. 임의 sigma·가짜 동시시각을 채워 validator를
통과시키지 않는다. 필요한 계약 변경과 기존 OFF 호환성은 R2에서 정하고 R3에서 검증한다.
현재 `hydro_support`는 Q 존재 영역과 다른 radar-derived 의미이고, balance beta는
resolved omega target을 seed로 사용하므로 물리 국지화 mask와 구분해야 한다.
실제 HYDRO/LIQUID의 수상체 strict-positive 존재는 1,098,952 mass cells,
64,990 columns로 넓게 분포한다. **Q>0은 inventory 기준이며 최종 국지화 임계값이
아니다.** 미량 수상체까지 모두 활성화하면 국지화 목적을 달성하지 못할 수 있다.
근거: 지원 영역·입력 조사 (로컬 작업공간 근거: `../scratch/cp02_balance_reanalysis_20260914/support_inventory.md`).

기존 OFF/HYDRO/LIQUID 실험은 새 물리 연직풍 초기화 실험이 아니다.
입력 `wrfinput_d01`의 W는 세 경우 모두 0이었다. 반면 시간 적분 전 모델 시작 과정은
동일한 지형 유도 W를 생성했다. 기존 Cloud-BAL 균형 경로는 resolved target이 없어
solver 반복 0, 증분 0으로 종료했다. target-valid 셀은 있었지만 source authority·quality·
sigma를 포함한 resolved 조건을 충족하지 못한 것이며, 관측자료 전체가 없었던 것이 아니다.
이 성공 반환값은 물리 초기화 성공이 아니다.

또한 현재 증분 투영은 배경장의 질량 잔차를 없애는 연산자가 아니다. 기존 분석장의
전체 상태 수지와 후보의 증분 수지를 별도로 검사해야 한다. native `WW`는
mu-coupled eta-dot이며, 기하학적 W 및 물질 압력속도 omega와 구별한다.

현재 준비한 native 질량 진단 및 stationary-geopotential 진단은 **국지화하지 않은
진단 후보**다. 질량 경향이 허용된 WW 복원이나 geopotential 정지 가정만으로
관측 적합성·운동량 균형·초기 충격 억제의 달성을 주장하지 않는다.

근거: 수학 검토 (로컬 작업공간 근거: `../scratch/cp02_balance_reanalysis_20260914/mathematics.md`),
수치 검토 (로컬 작업공간 근거: `../scratch/cp02_balance_reanalysis_20260914/numerics.md`),
시작 시각 재읽기 (로컬 작업공간 근거: `../scratch/cp02_balance_reanalysis_20260914/T0_STARTUP_READBACK.json`).

## 3. 자료 조사와 관측 가능성 평가

최초 사례는 기존 비교와 같은 2026-08-16 12 UTC 분석이다. 디렉토리에서 실제 유효시각과
관측시각을 읽어 확정하며 파일명만으로 동시 관측을 판단하지 않는다.

| 자료 | 확인할 내용 | 산출물 |
|---|---|---|
| 기존 Barnes U/V | 시선속도 반영 방법, 연직·낙하 성분 처리, 좌표계·보간·오차 정보 | 관측→분석 코드 경로와 잔차 정의 |
| 레이더별 Vr | 통합 전/후 보존 위치, 부호·단위, 결측·dealiasing·QC·Nyquist | 사례별 파일·변수·시각 inventory |
| 레이더 기하 | 위치·고도, 방위각·고도각·거리, 빔 굴절/지구곡률, 차폐 | 격자별 단위 시선벡터와 유효 coverage |
| 시간 정보 | 레이더 간·고도각 간 시차, sweep 시각 유무 | 시차 분포 및 동시성/이류보정 가능 범위 |
| 수상체/열역학 | Qc/Qi/Qr/Qs/Qg, 반사도·상태/종 정보, T·수증기·밀도 | 종별 지원 영역과 낙하속도 입력 계약 |
| 모델 좌표 | 지형, map factor, stagger, 건조공기 질량, P/Phi | 질량·운동량 연산자와 관측 연산자의 좌표 계약 |

격자·고도별로 유효 레이더 수, 빔 교차각, 고도각 분포, 관측 행렬의 특이값/조건수,
시간차 및 유효 수상체 coverage를 지도와 표로 만든다. 레이더 총수가 많다는 이유만으로
각 격자의 3성분 바람 복원이 가능하다고 판단하지 않는다. 저고도각에서는 연직 민감도가
작으므로 Vr·수평풍 잔차의 오차가 크게 증폭된다. 공통 낙하속도 오차는 별도로 W에
전달되며, 레이더 수를 늘려도 이 공통 오차가 독립 표본처럼 감소하지 않는다.
원래 빔 기하와 Barnes 이후 남은 연직 정보의 rank·정보량을 별도로 평가한다.

레이더별 scan age·시차·빔 부피와 가능한 폭풍 이동량을 현재 5 km 격자의 표현 규모에
맞추어 평가한다. 단순 격자 보간이나 중복 표본 수가 정보량을 늘린다고 가정하지 않는다.
구름 생애주기 분류는 시간 자료가 허용할 때 민감도 층화에 사용하며, 분류 불명 자체를
물리적 W 진단의 금지 조건으로 두지 않는다. 구름 아래 증발 냉각·냉기류 유출도
검증 대상에 포함한다.

원시 빔 정보가 없고 레이더별 격자 Vr만 남았다면 보간으로 달라진 유효 시선 방향과
대표성 오차를 확인한다. U/V만 남은 영역에서는 없어진 독립 연직 정보를 복원했다고
주장하지 않고 질량·물리 제약 기반 진단 영역으로 구분한다.

## 4. 관측 방정식과 중복 사용 처리

레이더에서 멀어지는 방향을 Vr 양, 위쪽을 W 양, 아래쪽 입자 종단속도를 Vt 양으로
정의한 경우, 한 관측의 단순화된 연산자는 다음과 같다. 실제 자료 부호는 먼저 검증한다.

```
Vr_r = e_rx*u + e_ry*v + e_rz*(w - Vt_r) + epsilon_r
r_r  = Vr_r - e_rx*u_Barnes - e_ry*v_Barnes + e_rz*Vt_r
r_r  = e_rx*delta_u + e_ry*delta_v + e_rz*w + epsilon_r
```

다중 빔이 측정하는 연직 입자속도는 `w - Vt`다. 레이더 수가 늘어도 동일 지점에서
w와 Vt를 이 식만으로 별개로 식별할 수는 없다. 혼합상·입자종별 반사도 가중과
낙하속도 불확실성을 포함해야 하며, 작은 `e_rz`로 잔차를 단순 나누어 W를 확정하지 않는다.

두 경로를 비교하고 자료 조사 뒤 하나를 선택한다.

1. **기존 U/V를 기준으로 한 조건부 보정**: 레이더 잔차를 연직풍 제약에 쓰되,
   U/V 오차와 Vr의 상관을 포함한다. 기존 분석의 연직 성분 흡수 및 편향을 검사한다.
   상관을 추정할 근거가 없으면 이를 정식 통계 posterior나 독립 검증으로 표현하지 않는다.
2. **원래 관측 목적함수의 3성분 확장**: 기존 Barnes 자료 경로를 재사용하고 원 관측을
   한 번만 넣어 u/v/w를 공동 분석한다. 이미 동화한 U/V에 독립 관측 가중을 추가하지
   않으며, 최소 변경 원칙과 기존 수평풍 품질을 비교한다.

첫 경로는 작은 구현이 장점이지만 오차 상관과 비식별성 문제가 해소되어야 한다.
둘째 경로는 관측 중복을 명확히 처리할 수 있으나 분석기 변경 범위가 커진다.
상관을 무시한 강한 background 가중과 Vr 가중을 임의로 조합하지 않는다.

합성 기하의 수치 해석도 제한해서 기록한다. `0.412213%`는 수평 성분을 미지 nuisance로
둘 때와 수평 성분을 알고 고정할 때의 **조건부 연직 정보(제곱 민감도) 비율**이다
(`I_w,unknown/I_w,known=0.00412213`). 이는 Barnes가 정보의 99.6%를 파괴했다는
감쇠율이 아니다. 같은 합성 행렬에서 서로 독립인 Vr 오차를 `sigma_Vr=1 m s^-1`로
두고 Vt를 정확히 고정하면 조건부 연직 표준편차는 `1/sqrt(I_w,unknown)≈238.6 m s^-1`로
계산된다. 두 수치는 해당 fixture의 가정에만 해당하며 실제 Vr sigma나 실제 Vt 불확실도의
주장이 아니다. 원 관측을 한 번 넣는 공동 분석도 낮은 고도각·나쁜 rank/condition을
고치지 않으므로, geometry gate를 통과하지 못한 영역의 W를 식별한다고 표현하지 않는다.

조건부 경로의 단순 선형 예에서 `u_B=L*y`, `P=I-H_h*L`이면 잔차는 `r=P*y`다.
`L*H_h=I`인 수평 최소제곱 투영에서는 연직 민감도와 오차가 각각 `P*h_z`,
`P*R*P^T`가 된다. 이 경우 잔차 공분산은 특이할 수 있으므로 남은 부분공간에서
QR/SVD로 rank를 확인한다. 실제 Barnes의 배경·다른 관측·반복·QC는 별도로 포함하며,
위 투영식을 실제 분석 전체의 정확한 연산자로 단정하지 않는다.
R1/R2에서 조건부 연산자와 양의 준정부호 공분산의 근거가 부족하면 통계적 신뢰도를
발명하지 않고, 원 관측을 한 번 사용하는 공동 분석 경로로 전환한다. 그 경로도
미완료이면 해당 LOS 결과는 진단으로만 남기고 관측으로 식별된 W로 승격하지 않는다.

공통 Vt를 미지수로 둔 빔 행렬 `[e_x,e_y,e_z,-e_z]`에는 `[0,0,1,1]` 영공간이 있다.
따라서 W의 관측 식별성과 낙하속도 가정의 기여를 분리한다. 공통 Vt 오차를 주변화할
때는 `R_Vt=sigma_Vt^2*h_z*h_z^T`의 레이더 간 상관을 포함한다. 서로 다른 종·빔
부피에는 해당 공분산 계약을 사용한다. 종간 낙하속도 분산이 0이어도 PSD·입자형상·
대표성 오차가 0이라는 뜻은 아니다. 기존 진단 gate의 분산 하한을 복원 오차의
물리적 근거로 재사용하지 않는다.

## 5. 수상체 국지화와 균형초기화

지원 영역은 유효한 기존 수상체·레이더 정보와 필요한 주변 전이 영역으로 정의한다.
기존 임계값·수평/연직 영향반경의 실제 소스와 namelist를 먼저 조사하고, 현재 설정을
자동으로 최적값으로 채택하지 않는다. 관측이 없는 곳을 W=0 관측으로 취급하지 않는다.
배경 지형성 W와 맑은 영역의 기존 흐름은 보존 대상이다.

국지화는 **보정량**의 지원 영역·가중·경계조건에 넣는다. 구름 가장자리 밖의 환류와
질량 보정을 허용할 전이 영역이 필요할 수 있다. 최종 W에 마스크를 곱하면 발생하는
추가 발산 `delta_v · grad(beta)`를 무시하지 않는다.

물리·수치 설계는 다음 순서로 확정한다.

1. 건조공기 질량의 이산식 `dot(m_d) + D(F_d) = 0`을 기준으로 정하고,
   pressure carrier 및 moist/condensate 분모와의 변환을 명시한다.
2. 지표의 지형 추종 불투과 조건, 모델 상단·측면 조건, 국지화 경계 유량을 함께 고정한다.
   고정 U/V와 상·하단 유량이 양립하지 않는 column은 최소 U/V 보정 또는 명시적
   물리 질량 경향이 필요하다. 숨은 질량 경향으로 잔차를 지우지 않는다.
3. 관측 적합·기존 분석 보존 목적함수에 질량 제약을 연결한다. 기존 increment-only
   연산자는 그대로 full-state 균형으로 재명명하지 않는다.
4. 압력/기압경도, 부력·수상체 하중, 온도·수증기·응결상과 지형 좌표의 정합성을
   점검하고 필요한 연립 보정을 구한다. 수분·에너지 변화를 ledger로 검증한다.
5. 모든 수직 가속도를 0으로 강제하지 않는다. 관측된 대류의 발달에 필요한 가속도와
   초기장 불일치로 생긴 빠른 모드의 급증을 구분하는 진단을 사용한다.

어떤 질량 경향과 느린 역학 균형을 허용할지는 방정식·경계 호환성 검토의 산출물이다.
단일 snapshot만으로 결정할 수 없는 경향을 이미 확보한 값처럼 사용하지 않는다.
예를 들어 질량 경향 0은 명시적 정지 가정으로 선택할 수 있지만 관측된 사실과 구별하고
그 가정하에서 경계 호환성을 검증한다. native `calc_ww_cp`를 재사용할 경우 내부
`dmdt`, `sum(DNW*C1H)=-1`의 수치 오차, 상단 0 대입 전 재귀 잔차를 확인한다.
이는 전체 모델 `MU_TEND` 검증을 대신하지 않는다.
자료가 부족하면 식별 가능한 성분만 적용하고 해당 영역/성분을 미해결로 표시한다.

닫힌 보정 영역의 공유 face 유량은 상쇄되므로, 고정된 경계 증분으로 없앨 수 없는
원래의 질량 잔차가 있을 수 있다. R2에서 정확한 연산자 연결 성분별 raw mass budget을
평균 제거 전에 계산한다. 부적합한 경계·지원 영역은 명시적으로 수정하거나 후보를
되돌리며, RHS 평균을 제거하여 물리 수지가 닫혔다고 처리하지 않는다.
W 보정의 국지화와 압력/환류의 영향 범위를 구분하고 모든 변수에 같은 작은 마스크를
강제하지 않는다.

엄밀한 보존·유효성·경계 조건과, 관측 적합·배경 보존·허용된 역학 잔차의 오차 허용
목적을 구분한다. noisy Vr를 다른 모든 제약과 동시에 정확한 등식으로 맞추지 않는다.
물리 단위와 정규화 척도를 명시하고 해의 실현 가능성·rank를 확인한다. 기존 순차
1회 처리는 결합 수렴의 증거가 아니다. 필요한 최소 반복으로 T/Q/P·밀도·geometry를
재평가하고 실제 저장 정밀도의 상태에서 최종 잔차를 검증한다. 대형 연립 solver
프레임워크를 새로 만드는 것을 필수 조건으로 두지 않는다.

상변화·중력파 제어는 다음과 같이 결합한다.

- 응결·증착·동결의 가열과 증발·승화·융해의 냉각, 수상체 하중 변화를 구분한다.
  내부 상변화의 물/엔탈피 변화량, 관측 분석의 물/열 증분, 좌표 재분배, 후속
  미세물리 경향은 출처·단위가 다르므로 각각 기록한다.
- 고정 건조질량의 `sum(delta_q)=0`, `h(T_new,q_new)=h(T_old,q_old)`를 만족해도
  native 압축성 총에너지나 가열률이 검증된 것은 아니다. 임의 조정시간으로 delta_q를
  나누어 가열률이나 W를 만들지 않는다. 필요한 경향은 실제 downstream 미세물리의
  과정·시간간격·입자수/상태 계약에 연결한다.
- 상변화 후 같은 상태의 EOS·건조/전체 밀도·기압경도·geopotential·부력·하중과
  바람을 맞춘다. 첫 미세물리 호출에서 같은 상변화를 중복 적용하거나 서로 다른
  포화·혼합상 정책 때문에 과도하게 재조정하는지 확인한다.
- 잠열·부력의 실제 대류 응답과 불일치에 의한 자유 조정 파동을 구분한다. 모든
  수직 가속도를 0으로 만들거나 잠열을 제거해 통과시키지 않는다. `w=S_b/N^2`는
  N²≈0에서 특이하고 불안정 영역에서는 안정 중력파 가정이 맞지 않으므로 일반
  초기화식으로 쓰지 않는다. 습윤 안정도와 냉기류·지형성 파동의 보존도 평가한다.
- 전이 영역의 급변을 줄일 때 물·열·유량 예산을 보존한다. 기존 감쇠·상단 조건은
  비교군 간 동일하게 두며, 임의 ramp·감쇠 강화·일괄 평활화로 초기화 효과를 대신하지
  않는다. 시간 적분은 완성된 t0 상태의 후속 검증에만 사용한다.

## 6. 단계별 실행·산출물·종료 조건

| 단계 | 작업과 산출물 | 통과 조건 / 실패 시 처리 |
|---|---|---|
| R0 자료 경로 | 실제 사례 inventory, 코드 경로, 변수·시간·QC·좌표 계약 | 원자료와 U/V의 연결 재현; 부족한 metadata와 대체 가능성 명시 |
| R1 기하 평가 | 원래/조건부 연직 정보·rank, 시간/빔 규모, 낙하속도 공분산 | 관측 가능/약제약/불가 영역과 Vt 가정의 기여 구분; 허위 독립 정보 금지 |
| R2 방정식 확정 | 관측 경로, 전체 질량식, 엄밀/오차 허용 제약, 상변화·파동 계약 | raw 성분별 수지·경계 호환성·실현 가능성·단위/척도·물리 가정 확정 |
| R3 최소 구현 | 실제 FORTRAN·입력 연결, legacy P0 연결 교정, 최소 비선형 반복과 rollback | pinned ifx O0/O2, 저장 후 물/열·EOS·밀도·유량 잔차 및 지원 영역 검증 |
| R4 t0 전달 | private native 입력과 첫 시간전진 전 readback | W 보존·U/V/P/T/Q 정합성 및 native C-grid 전체 상태 수지 검증 |
| R5 초기 충격 | 첫 미세물리 재조정·부력/가열 경향, 음향/내부 중력파 진단 | 사전 기준 충족, 실제 잠열 응답·불안정 대류·냉기류/지형성 파동 보존 |
| R6 강수 효과 | 1–6시간 RN1/PTY·분석장·레이더 구조 비교 | 동일 시각·영역·임계값 비교; 개선/악화와 사례 한계 별도 판정 |

R2 산출물은 다음 다섯 범주를 한 결과나 한 PASS로 합치지 않고 각각 `PENDING`으로
기록한다.

| R2 산출물 범주 | 별도 기록할 내용 | 현재 상태 |
|---|---|---|
| 독립 제어변수 | 실제 최소화 제어변수(예: R2에서 선택한 U/V/W 증분), 개수·저장 위치·stagger | PENDING |
| 진단변수 | 종속적으로 계산한 W/omega/WW/Phi·pressure와 변환·provenance | PENDING |
| 고정 입력 | 선택한 terrain·time·boundary·geometry·basis 등 고정 입력(무조건 U/V 고정은 아님) | PENDING |
| 제약식 | mass/EOS/thermo 관계와 support·경계·rank·feasibility·rollback | PENDING |
| native checks | source 식·units·stagger와 최종 array의 mass/EOS/thermo/metric 잔차·readback 검사; native 폐쇄식은 별도 미확정 | PENDING |

R2에서 폐합해야 할 항목은 `n_unknown`과 자유도 목록, 실제 mass/EOS/thermo 제약식과
허용오차, 지형/상·하단/측면 경계, rank·호환성·실현 가능성이다. 질량 경향의 선택도 `PENDING`으로 두고
`data`/`fixed_quasisteady`/`bounded_estimation` 중 하나를 근거와 함께 고정한다.
자료나 경계로 정해지지 않은 경향을 사후에 `mdot=-DF`로 만들어 잔차를 없애지 않으며,
건조질량 식은 `d rho_d/dt + div(rho_d V)`의 full `rho_d V`를 유지한다. 이산 증분에도
`delta(rho_d V)=rho_d,b*delta V+V_b*delta rho_d+delta rho_d*delta V`를 포함한다.
이 목록과
native source 대조가 끝나기 전에는 닫힌 native formulation을 발명하지 않는다.

R0→R1→R2→R3→R4→R5→R6 순서다. 자료 조사와 방정식 검토는 병렬 진행할 수 있으나
R2 미확정 후보를 native 초기장으로 게시하지 않는다. 현재 R0/R2 검토와 기존 native
진단 준비가 진행 중이며 R3 이후의 추가 과제 완료 증거는 없다.

R3에 들어가기 전에 관측 경로를 하나로 고정한다. 실제 Barnes 선형화·background와
Vr의 교차공분산을 재현할 수 있으면 조건부 경로를 선택하고, 그렇지 않으면 원시 Vr를
공동 3성분 목적함수에 **한 번만** 넣는다. 두 경우 모두 공동 분석이 나쁜 기하를
보정한다고 가정하지 않으며, 외부 모델 또는 `omega_target`/`wtarget`은 필요조건으로
추가하지 않는다.

native 시작 설정은 실제 pinned host의 `use_input_w` 위치·기본값·표면/경계 처리와
결속한다. 현재 준비본은 `&dynamics use_input_w=.true.`를 사용하지만 설정만으로
전달 성공을 선언하지 않는다. **첫 시간전진 전 t0 readback**을 필수 산출물로 남긴다.
R4/MR-C4는 t0 전달·재읽기와 첫 미세물리 진단 준비까지, R5/MR-C5는 실제 첫 호출
전후 변화와 초기 충격 판정을 담당한다. pinned host의 호출 위치·수집 지점과 인접한
시간전진·경계 처리 순서를 고정한다. 호출 후 결과를 MR-C4 완료의 선행조건으로 두지 않는다.
readback은 `x_b→initialized t0` 전체 증분과 `immediately before first MP→immediately
after first MP` 증분을 분리해 수집한다. 전자의 전체 증분 안에서도 실제 phase operator
ledger의 종별 `Δr_phase`·`ΔT_phase`를 analysis/remap/기타 증분과 분리하고, 후자에는
종별 `Δr_extra_MP`·`ΔT_extra_MP`를 기록한다. 각 snapshot에 동일 cell·단위·별도 시간
태그와 사이의 연산을 붙인다. 각 짝진 상태의 buoyancy·pressure·vertical acceleration도
같은 snapshot 단위로 기록하며 두 증분을 한 차이로 합치지 않는다.

연직가속도는 단순 W readback이 아니라 `a_w=F_w(x0)`의 RHS 진단으로 정의한다.
상태·native 우변·mass coupling 변환과 `startup 단계/RHS 평가 여부/MP call index/
경계 처리 전후/물리 시간전진 여부`를 기존 snapshot에 연결한다. 아직 평가되지 않은
경향은 `NOT_EVALUATED`이며 0으로 채우지 않는다. t0 RHS는 가능한 순수 진단 경로로
확보하고 첫 미세물리를 MR-C4 충족용으로 미리 실행하지 않는다.
진단은 실제 수행되는 RHS·미세물리 호출의 입출력 관찰을 우선한다. 별도 RHS 평가가
필요하면 누적 tendency·첫 호출 상태·입자모멘트 등 다음 계산에 영향을 주는 상태를
바꾸지 않는 경로인지 확인한다. 같은 executable·설정·입력·스레드·연산 단계에서
`x_diagnostics_on=x_diagnostics_off`를 주 상태와 지속 상태에 대해 검사한다.
진단 출력 파일·실행시간은 이 동일성 대상이 아니다. MR-C4/C5의 기존 시험에 연결한다.

MR-C5의 `delta r_extra_MP`는 순수 상변화량이 아니라 해당 호출 구간의 순변화다.
내부 종전환, sedimentation·지표/경계 유출입, 분석 물·열 증분, clipping·number 재초기화와
tendency 누적/실제 state update 시점을 분리한다. 분해할 정보가 없으면 미분해 잔차로
남기며 상변화로 귀속하지 않는다. 물리적으로 정상인 추가 응결·증발·융해를 0으로 강제하지 않는다.
고정 dry mass의 column에서 `Q=sum_k m_d,k sum_s r_s`이면
`epsilon_Q=Q_after-Q_before+M_out-M_in-A_Q`로 계산한다.
M은 같은 호출 구간의 시간적분 유출입 질량(kg), A_Q는 명시된 외부 추가량(양의 유입)이다.
column 내부 sedimentation은 상쇄하며 외부 경계 flux만 장부에 더한다. 지표 누적강수는
해당 호출 증가량·실제 cell 면적·단위를 써서 변환하고 flux와 중복 집계하지 않는다.
dry mass/geometry도 변한 구간은 양끝의 실제 질량가중과 해당 수송항으로 다시 계산한다.
`1.0→0.9 kg`, 지표 유출 `0.1 kg`은 잔차 0인 작은 양성 예제로 둔다.
WRF 미세물리가 열·수분 경향과 지표강수를 제공한다는 일반 설명은
[WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html#microphysics)를
참조하되, 항별 배열·단위·호출 순서는 pinned host에서 확정한다.

## 7. 실험 구성과 수치·물리 검증

기존 OFF/HYDRO/LIQUID 6시간 결과는 보존한다. 새로운 초기화 효과는 동일한 수상체·
열역학 설정을 기준으로 비교하여 LIQUID의 열역학 변화와 혼동하지 않는다.

| 새 비교 구성 | 구분할 효과 |
|---|---|
| 기준: 동일 수상체·열역학 + 기존 초기풍 | 새 초기화가 없는 대조군 |
| 질량/균형 진단: 기존 U/V + 동일 수상체 지원 영역 | 내부 진단 초기화의 효과 |
| 레이더 연직 제약 + 동일 균형초기화 | 다중 레이더 정보의 추가 효과 |

불균형 W 단독 주입은 필요할 경우 격리된 짧은 실패 진단으로만 사용하며 배포 후보로
삼지 않는다. 생산 알고리즘 선정에 필요 없는 실험용 FORTRAN 구현을 늘리지 않는다.

평가 항목:

- t0: 전체/증분 질량 잔차와 경계 유량, 수분·열역학 수지, 관측 Vr 적합도,
  U/V 변경량, W·omega·WW의 단위/좌표 일치, 지원 영역 경계의 연속성.
- 초기 충격: 첫 시간전진 전과 이후 초–분 단위 압력 경향·발산·수직 가속도·고주파
  에너지의 크기와 공간 분포. 출력 주기는 실제 timestep/acoustic 설정에 맞추어 정한다.
  solver residual 감소만으로 충격이 없다고 결론 내리지 않는다.
- 상변화 파동: 첫 미세물리 계산의 가열/냉각·부력·하중 경향과 압력·바람의 전파 및
  위상관계를 함께 평가한다. 음향파와 내부 중력파를 분리하고, 안정도·지형·습윤 상태에
  맞지 않는 모드 에너지 공식을 적용하지 않는다. 일정 주파수 cutoff만으로 비물리
  신호를 판정하지 않는다. 파동 감소가 대류·잠열 응답의 소실로 얻어진 것이 아닌지 확인한다.
- native 수치: 실제 stagger·map factor·MU/MUB·DNW·WW·경계유량으로 C-grid 잔차를
  재계산한다. 등압면 잔차나 pointwise W 전달 성공을 native 질량 폐쇄로 대신하지 않는다.
  timestep·음향 subcycle·연직격자·미세물리 호출 순서를 고정하고 필요한 초기 출력만
  수집한다. 실제 5 km/20초 설정의 해상도 한계도 기록한다.
- 관측 검증: 동화한 Vr 재적합은 독립 검증이 아니다. 레이더/시각 제외 검증을 수행할
  경우 Barnes U/V도 해당 관측을 제외하여 재분석하거나 정보 누출을 명시한다.
- 1시간: 해당 시각 분석장의 수평풍·수상체·열역학과 레이더 구조 비교.
- 1–6시간: 각 시간 구간의 RN1, 정의를 맞춘 PTY, 강수량/위치/구조 비교.
  CSI는 기존 **0.1, 1, 5, 10 mm/h**를 유지하고 시간별 및 6개 시간표본 합산을
  함께 제시한다. 6시간 누적 강수 임계값과 혼동하지 않는다.
- 강수 검증 영역은 기존 **남한 육지 3,688격자**만 사용한다. 바다·북한 제외,
  결측/coverage와 격자 매핑 계약을 유지한다. 전 계산영역의 질량 보존 검사는
  강수 검증 영역 제한과 별개다.
- 참조자료 계보: RN1은 계속 미래 시각의 강수 검증 기준으로 사용한다. 초기화와
  검증 제품의 관측 구간·처리 중복 및 상관 오차를 명시하고, 가능하면 독립 지상관측을
  보완한다. 같은 레이더 네트워크라는 이유만으로 예측 검증을 무효화하지 않으며,
  PTY의 레이더 의존성은 실제 생성 경로 확인 전 단정하지 않는다.

수치 허용오차는 기존 계약에서 재사용 가능한 값과 새 기준을 구분해 기록한다.
새 기준은 변수별 단위·정규화·상한·기준군 대비 허용 변화·자료 출처를 포함한다.
확정 시점은 MR 체크리스트를 따른다: 관측 정보는 MR-C1, 보존·수렴은 MR-C2,
파동·상변화는 MR-C3, 강수 검증은 MR-C6 실행 전이다. 각 기준은 해당 후보의 평가
결과를 보기 전에 고정하고 R2에서는 방정식에 필요한 관측·보존 계약을 연결한다.
아직 근거가 없는 수치를 발명하지 않는다.
미확정 기준이 남으면 관련 단계는 PASS로 승격하지 않는다. 한 사례의 CSI 개선은
일반적 성능 또는 배포 승인 근거가 아니며 후속 독립 사례 검증을 별도로 남긴다.

최소 시험은 약한/중복 빔의 rank, 닫힌 국지 영역의 부적합 질량수지, 내부 상변화와
분석 증분의 구분, 저장 후 canonical/native 잔차, 안정 파동과 불안정 대류의 보존을
확인한다. 기존 공유 face 연산자와 시험을 우선 재사용한다. timestep·격자 변경은
필요한 수렴성 확인에 한정하며, 현재 단일 영역에 쓰이지 않는 중첩 격자나 범용 감사
프레임워크를 새 필수 구현으로 추가하지 않는다.

시험 증거의 종류는 구분해서 기록한다. `DISCRETE_EXACT_SOLVER`/`INDEPENDENT_SPARSE`는
고정된 이산 행렬·희소 reference의 exact 또는 독립 대수 검증이고, 연속해의 수렴을
뜻하지 않는다. `CONTINUOUS_MMS_GRID_CONVERGENCE`는 제조해와 격자 세분화에 대한
연속 문제 수렴이며 실제 레이더 기하를 검증하지 않는다. `REAL_GRID_SINE_EXECUTION`은
실제 격자에서 sine 입력을 소비하는 실행·경로 검사이며 과학적 관측 가능성이나
solver 폐합의 증거가 아니다. 어느 시험도 다른 종류의 PASS를 대신하지 않는다.

## 8. 구현·검토·기록 관리

최대 네 역할로 병렬 검토한다: (1) 레이더 자료/관측 기하, (2) 역문제·균형 방정식,
(3) 실제 FORTRAN/native 전달, (4) 독립 수치·기상학 검토. 구현 담당의 같은 계산을
되풀이하는 시험보다 부호·질량경계·약한 관측기하·결측·rollback 반례를 우선한다.

배포 코드는 작은 단일 목적 루틴으로 유지한다. 자료 inventory, 그림, 통계·감사 보고는
시험/분석 경로에 두고 생산 FORTRAN에 큰 감사 프레임워크를 추가하지 않는다.
빌드는 `tests/intel_toolchain.sh`의 pinned Intel 프로필과 새 scratch 작업 디렉토리만
사용한다. 기존 입력·보존 실험·운영 경로를 수정하지 않는다.

각 단계는 입력·소스·설정 결속, 실행 여부, 결과와 제한을 기록한다. 유지 소스/문서의
완성된 변경 묶음은 Graphify 증분 관리에 반영한다. 그래프 최신성과 과학 검증 PASS는
구분하며 CP02/CP06 공식 상태는 실제 종료 조건을 만족했을 때만 변경한다.

## 9. 연결 문서와 문헌

- [CP02 전체 계획](CLOUD_BAL_FINAL_GOALS_CHECKPOINTS_20260907.md)
- [기존 모델 비교 실험과 내부 진단 범위](CP02_MODEL_DYNAMICS_INCREMENT_EXPERIMENT_20260914.md)
- [레이더 구조 검토](CP02_RADAR_STRUCTURE_REVIEW_20260914.md)
- [6시간 강수 검증](CP02_SIX_HOUR_PRECIPITATION_VERIFICATION_20260914.md)
- [실제 레이더 입력 코드](../src/upstream/wind_openmp/main_sub.f)
- [Oue et al. (2019)](https://amt.copernicus.org/articles/12/1999/2019/):
  다중 Doppler 연직풍 복원에서 고도각 밀도와 체적 관측 소요시간의 중요성을 확인한
  연구다. 그 논문의 스캔 시간 수치를 이 프로젝트의 허용값으로 그대로 채택하지 않는다.
- [Gao et al. (1999)](https://journals.ametsoc.org/view/journals/mwre/127/9/1520-0493_1999_127_2128_avmfta_2.0.co_2.xml):
  두 Doppler 레이더의 3차원 변분 바람 분석과 강수입자 낙하속도 처리를 검토할 근거.

문헌은 방법 선택의 근거이며 실제 한반도 사례의 복원 가능성을 인증하지 않는다.
관측 기하·입력 품질·native 이산식은 해당 사례와 pinned 소스로 확인한다.

### PR36: 같은 삼각 기주의 지면 법선 항과 미완성 수지

PR35의 소수초 절삭을 제거하고 정수초·단위·결측·schema 검사를 재사용한다.
12/14 UTC LSX의 사후 pressure 경향으로 `Fs=(V14-V12)/7200`을 같은 면에서
평가했다. 별도의 완성된 지면 omega를 새 필수조건으로 요구하지 않는다.
하지만 모든 하부 측면 구간은 미지원이고 5000 Pa COM도 전부 결측이므로
전체 기주 잔차는 `null`이다. 같은 격자의 LW3 OM은 명시적 조건부 상단 적분으로
별도 계산하되 생산 경계로 승격하지 않는다. 배경 OM은 원점 metadata가 달라 직접 대입하지 않는다.
다음은 하부 profile의 높이·풍향·표본 계약과 상단 prior의 좌표 대응을 먼저 닫고,
그 뒤 완전한 기주 수지와 수직 분할을 연결한다. 미정 항을 0으로 바꾸거나
알려진 부분합을 전체 잔차로 승인하지 않는다.
근거: `docs/PHYSICAL_COLUMN_TERMS_20260921.md`.

### PR37: 조건부 10 m 하부 적분과 같은 시간구간의 외곽 수지

[연구식·실행 근거](LOWER_TRANSPORT_INTERVAL_BUDGET_20260921.md)는 LSX 10 m
바람을 LT1 높이·static AVG의 조건부 log-pressure 보간과 연결한다. 실제 지면으로
바람을 연장하지 않고 10 m 아래는 미정으로 둔다. PS 기준 지면 위 level의 높이가
지형과 역전된 위치도 보정하거나 제외해 숨기지 않고 미지원으로 기록한다.
12/13/14 UTC 측면·상단은 Simpson 구간평균 근사, 지면은 같은 12–14 UTC 체적
secant를 사용한다. 순간 균형이나 정확한 연속시간 적분으로 승인하지 않는다.
내부 공유면 미정 유량은 전 영역에서 상쇄하고 외부 1,032개 면의 미정량만 남긴다.
음의 알려진 합계를 필요한 외곽 미정 총량으로 보고할 뿐 경계값으로 대입하지 않는다.
다음은 높이–기압·하부 profile의 물리 근거와 0–10 m 수송, 상단 자료의 상관,
시간 적분 표현오차를 독립적으로 평가하는 것이다. 생산 solver·D/G·권한·상한,
비영 ON 및 native/열역학/예보 상태는 변경하지 않는다.

PR37 추가 판정: 단조로운 높이–기압 보간에도 10 m 압력차가 암시하는 온도의
비현실적 극값이 있어 실제 하부 profile은 `NOT_SUPPORTED_FOR_PHYSICAL_PROFILE`이다.
조건부 적분의 수치 통과를 물리 경계 승인으로 올리지 않으며, 다음은 온도·수분·
높이 datum에 근거한 표본 pressure 연결을 확정하는 작업이다.


### PR38 — 열역학적 10 m pressure prior와 높이 기준 진단

[실행·입력 근거](SURFACE_THERMODYNAMIC_PRESSURE_20260922.md): LSX T2와 건조공기
기준 MR를 0–10 m에 일정하다고 선언한 prior를 기존 gas EOS와 연결했다.
새 Fortran 절차와 같은 사례의 Intel O0/O2 재계산은 통과했다. LT1 level 선택 없이
표본 pressure를 계산하며, 원래 HT/PS는 변경하지 않는다. 지면–첫 level의
정역학 두께 불일치는 내부 level 사이보다 크게 남아 `DATUM_UNVERIFIED`이다.
모든 하부 face가 prior상 계산 가능해도 0–10 m 유량은 미정이며, 전체 기주·영역
잔차는 null이다. `CONDITIONAL_THIN_LAYER_PRIOR`는 물리 profile·경계 권한·
비영 ON·native 승인이 아니다. 다음은 높이 기준과 층 대표성, 미정 0–10 m
수송의 독립적 근거를 연결하는 작업이다.
