# 실제 전 영역 BALCON 수학·기상학 검토 — 2026-09-17

판정: 현재 실행되는 legacy BALCON을 수학적·기상학적으로 검증 완료라고 인정할 수 없다. 이산 연산자 불일치와 실제 우변의 해 존재 조건 위반을 확인했다. 실패 시 출력 차단은 작동하며, 승인된 균형 보정 후 상태는 없다. 기존 writer/reader 및 PR24 재현 PASS_SCOPED를 취소하는 판정은 아니다.

## 기준과 실행 범위

- 소스: `Cloud-BAL/scratch/pr24_balance_20260917/Cloud-BAL`, commit `4a7e31039895316f61ddb57c0714a2a62236f10f`; 병합 main `763f81cba568dd7fa9071972b0da56b8a702fd37`과 동일 소스 트리.
- `src/balance/qbalpe.f` SHA256: `e38758be0dac93402e198bc2e1d91ed30469a94ee6d0f2d7f13d5a864b4bcbe7`.
- 실제 2026-08-16 13 UTC, 원래 235×283×22 분석 격자. 기존 3차원 분석을 재사용했으며 새 관측 분석이나 WRF startup은 실행하지 않았다.
- 원본 90개 입력 해시를 재확인했다. 원본·운영 설정은 변경하지 않았다.
- scratch의 생산 소스 복사본에 초기 LEIBP3 반환 직후 배열 저장만 추가했다. 기본 200회 제한·계수·허용오차는 그대로이며 실제 실행은 실패했다. 저장된 lambda는 실패한 반복 상태이며 승인된 후보가 아니다.
- 수치 진단은 Fortran, pinned Intel profile, fresh scratch에서 수행했다. 생산 snapshot 실행은 O0이며 진단 프로그램의 O0/O2 로그가 일치했다. 전체 생산 코드의 O0/O2 교차검증이라고 주장하지 않는다.
- 현재 보통 QBAL 실행은 legacy BALCON 경로다. 별도 canonical 검증기의 성공을 이 경로에 대신 적용하지 않았다.

## 1. 푸는 연산자와 적용하는 보정이 다름 — P0

D를 `continuity_point`, G를 실제 wind/omega increment, L을 `leibp3` 행렬이라 하면 투영 보정에는 L=DG가 필요하다. 현재 셋은 일치하지 않는다.

소스 위치: qbalpe.f:1897–1944(G), 1968–2003(D), 3242–3281(L).

예를 들어 DG의 동쪽 계수는 stagger 때문에 beta/erru의 (i,j-1,k-1) 주변값과 dx(i,j-1)dx(i,j)를 사용하지만, L은 (i,j,k) 주변값과 dx(i,j)^2를 사용한다. 연직항도 실제 G의 beta(k), dp(k+1)와 L의 harmonic face beta 및 평균 dp가 다르다. tau는 2차원이며 연직 tau 변화 때문이라는 설명은 하지 않는다.

전체 snapshot에서 상단 특수 행과 terrain 대입을 제외한 711,949개 유효 stencil을 비교했다. 하단 고정 ghost에 인접한 일부 행은 포함될 수 있다. 실제 실패 반복 lambda를 사용했고 합성 기상장을 만들지 않았다.

- RMS(L lambda − DG lambda) = 3.752674300689891e-5
- RMS(L lambda) = 1.066704761646372e-4
- 비율 = 0.351800651465917
- 최대 차이 = 1.492951281295538e-3, 위치 (207,85,20)

35.18%는 이 snapshot의 연산자 차이 비율이다. 예보 오차율이나 실제 보정 후 발산 잔차가 아니다. 선형해가 정확해져도 현재 보정의 연속방정식 개선을 같은 행렬로 보증할 수 없다는 근거다.

## 2. 국소화 RHS와 정확한 연속방정식 보정 계약 불일치 — P0

qbalpe.f:3145–3148의 주석은 `L lambda = -div(V)`와 unweighted RHS를 선언하지만 실제 식은 `f3=-influence*cont`다. G의 계수에도 influence(beta)가 이미 들어 있다.

L=DG라고 가정해도 현재 식을 정확히 풀면 D(V+G lambda)=(1-beta)DV다. 따라서 beta<1인 곳에서 정확한 무발산 투영과 같지 않다. 유효 stencil 중 472,420개가 0<beta<1이었다.

이는 모든 완화법에서 beta 곱이 금지된다는 뜻은 아니다. 의도한 것이 부분 보정이면 그 목적식·반복·수렴 기준을 명시해야 한다. 현재 lmax=1과 unweighted 주석을 함께 놓고 정확한 투영이라고 설명할 수 없다. 현재 acceptance는 강제 상태 잔차의 25% 이하 및 배경 상대/절대 한도 등을 검사하며, 모든 점에서 잔차 0을 요구하는 검사는 아니다.

## 3. 실제 닫힌 성분 3개의 우변이 호환되지 않음

실제 active row 777,213개를 양의 face 연결로 조사했다. 연결 성분 4개 중 3개는 외부 고정 lambda 경계에 연결되지 않은 닫힌 성분이다. beta=0 face, terrain Neumann 복사, 상단 Neumann을 구분했다.

비대칭 행렬에서 필요한 조건은 A^T w=0인 왼쪽 영벡터에 대해 w^T f=0이다. 단순 산술평균으로 대체하지 않았다. 실제 float32 face 계수를 구성하고 real64로 왼쪽 영벡터를 구해 sum(w)=1로 정규화했다.

| 성분 크기 | w^T f | abs(w^T f)/max(abs(f)) |
|---:|---:|---:|
| 241 | -7.601329944473046e-7 | 0.024299895 |
| 670 | -2.452190705007376e-6 | 0.069564633 |
| 453 | -4.077708481347616e-7 | 0.013753953 |

정규화 전치 잔차는 최대 2.9e-17, A*1 상대 잔차는 최대 4.2e-19, w는 모두 양수다. 잘못 제외한 양의 face가 없는지, finite, 정규화, pivot을 명시적으로 검사했다. real64 face 구성 대조도 같은 결론이다.

이 세 블록은 현재 RHS 그대로 정확한 해를 가질 수 없다. 반복 횟수 증가만으로 해결되지 않는다. 다만 이전 최대 보정량 정체 셀 (45,208,4)은 775,849개 행의 다른 고정 경계 연결 성분에 있으므로 그 정체 원인을 이 영공간 문제 하나로 설명하지 않는다.

해 존재 조건 참고: [PETSc MatSetNullSpace](https://petsc.org/release/manualpages/Mat/MatSetNullSpace/). RHS 평균을 조용히 빼거나 tolerance를 완화하는 것을 물리적 해결로 승인하지 않는다. 원래 forcing·경계·지형 연결과 허용 가능한 변화부터 결정해야 한다.

## 4. 현재 max residual 로그는 실제 최대 선형 잔차가 아님

qbalpe.f:3309 및 3333의 `reslm=corlm*cortm`은 sweep 최대 승수 correction과
마지막 처리 행의 diagonal을 곱한다. 같은 행의 값이라는 보장이 없으며, 각 행의
잔차도 순차 갱신 중의 상태에서 계산하므로 최종 lambda의 잔차 norm이 아니다.
따라서 출력 label `max residual`을 실제 `max(abs(A lambda-f))`로 해석하면 안 된다.
244라는 correction도 바람 m/s 또는 omega Pa/s가 아니라 lambda 보정량이다.

후속 구현에서는 최종 lambda를 변경하지 않는 동일 operator 적용으로 RMS/max/위치를
계산하고, 최대 delta lambda와 실제 delta U/V/omega를 구분한다. 이 로그 결함의
소스 확인은 기존 실패를 성공으로 바꾸지 않으며 정체 원인을 단독으로 규명하지 않는다.

## 기상학적 판단

타당한 부분: descending Pa와 양의 dp, pressure-coordinate continuity의 omega 부호, 높이↔geopotential 변환, 압력면 지균 잔차 부호는 정합적이다. 수평 발산만 무조건 0으로 만들려는 식이 아니라 omega의 연직 변화와 연결한다. 실패 시 candidate rollback과 writer 차단도 타당하다.

그러나 다음을 물리 검증 완료로 볼 수 없다.

1. COM은 구름 종류·깊이 등에 기반한 경험적 cloud-derived omega다. 직접 관측한 다중 레이더 W와 같지 않다. 관측 연산자·원래 시각·Barnes 계보·불확실성 연결이 필요하다. [NOAA/FSL LAPS balance 설명](https://www2.mmm.ucar.edu/mm5/workshop/ws01/shaw.pdf)도 구름 유도 연직운동과 질량·발산 조정이라는 방법의 성격을 설명한다.
2. 고정 scale height 8000 m의 omega↔w 변환은 근사이며 현지 밀도와 native 좌표/metric을 이용한 완전한 변환이 아니다. hydrostatic 온도 재구성과 지균 잔차만으로 대류성 습윤 비정역학 균형이 입증되지 않는다.
3. SH는 pipeline에서 stagger/destagger 평균을 거친다. 따라서 점별 불변 또는 총수분 보존이라고 주장할 수 없다. RH 재진단도 응결·잠열·수상체를 포함한 총수분/에너지 수지를 닫지 않는다.
4. acceptance 뒤에도 destagger, 지표 온도 조정, 회전, RH 계산이 이어진다. 최종 저장/native consumed 상태의 연속방정식과 질량·열역학을 다시 평가하지 않으므로 내부 후보 gate가 최종 상태의 물리 정합성을 보증하지 않는다.
5. 이번에는 실제 균형 후 산출물이 없다. 전후 비교·native W/WW 소비·초기 충격·예보 효과는 미검증이다.

## 수정 순서 제안

1. 실제 D와 G의 위치·계량·경계 조건을 먼저 고정하고 L=DG를 일치시킨다. 변분법으로 설명하려면 선언한 가중 내적에서 adjoint 관계도 확인한다.
2. beta가 비용 가중인지, 지원 영역인지, 부분 보정률인지 명확히 하고 RHS/반복/acceptance를 같은 목적에 맞춘다.
3. 닫힌 성분의 호환성을 사전 판정하고 물리적으로 허용한 경계·forcing 정책으로 처리한다. 자동 평균 제거로 목표를 숨겨 바꾸지 않는다.
4. 같은 실제 전 영역으로 다시 실행하여 최종 A-grid와 native 마지막 변환 후 상태를 비교한다. 승인된 비영 보정 후 산출물이 생기기 전까지 전후 개선을 주장하지 않는다.

## 증거 파일과 제한

아래 파일은 작업공간 `Cloud-BAL/scratch/baudit_20260917/`에 보존되어 있다.
대용량 실제 snapshot·바이너리를 저장소에 포함하지 않는다. 증거 디렉터리가 없는
환경에서 이 문서만으로 실제 재실행을 했다고 주장할 수 없다.


- `argv.json`, `build.log`, `run/qbal_snapshot.log`: snapshot 생산 빌드/실패 실행.
- `run/operator_snapshot.bin`: 실제 전체 배열, big endian, 42,658,888 bytes.
- `audit_operator.f90`, `build/audit-O0.log`, `build/audit-O2.log`.
- `audit_components.f90`, `audit_compatibility.f90`, `build/compatibility-checked-O0.log`, `build/compatibility-checked-O2.log`.
- `audit_compatibility_real64.f90`: face 정밀도 대조용.
- `review_receipt.json`: 원본 보존과 위 증거 SHA256.

수학·기상학·gate·연산자 구현을 분담 검토했다. 보조 gate 검토자가 실행한 기존 소규모 acceptance/nonlin/BALCON 테스트는 이 실자료 전 영역 증거에 합산하지 않았다. 이번 핵심 수치 결과는 실제 전체 snapshot의 Fortran 진단이다. 생산 수치식·허용오차·운영 입력 수정이나 균형 후보 게시를 하지 않았다.

Graphify는 관계 탐색에만 사용했다. 이번 maintained source 변경은 없으며 scratch 진단은 graph corpus 밖이다. 기존 두 graph snapshot의 날짜를 유지하며 구조적 최신성을 물리 검증으로 해석하지 않는다.

### 고정한 진단 artifact SHA256

| 작업공간 상대 경로 | SHA256 |
|---|---|
| `run/operator_snapshot.bin` | `96932e53e5f30bf3e9c307617765aaa7200750ec01d4ead6b45842faf97fa661` |
| `audit_operator.f90` | `ad89f74cfba4846594dade664fce03fd6ad6ce25dd0ae9500fceb695caac846a` |
| `audit_compatibility.f90` | `9e5c5d2ba08ea580a513cb631adc229a76d23defb0d4c24c0db384be07a62d69` |
| `build/audit-O0.log` | `d61711616c2b09a6f1ce37edd1c503a51afc044d1fcbdfed7ce3a56c94aa8000` |
| `build/audit-O2.log` | `d61711616c2b09a6f1ce37edd1c503a51afc044d1fcbdfed7ce3a56c94aa8000` |
| `build/compatibility-checked-O0.log` | `abd31168ec1c803681b7565f8434080e37e600889ea34e5a1eec67a91fa453e8` |
| `build/compatibility-checked-O2.log` | `abd31168ec1c803681b7565f8434080e37e600889ea34e5a1eec67a91fa453e8` |

위 검토는 PR #25 이후 수행한 pinned Intel 실제 배열 진단이다. 사용자가 별도로
제공한 GNU O0/O2 18개 대수 검사는 이 실행 횟수에 합산하지 않는다.
