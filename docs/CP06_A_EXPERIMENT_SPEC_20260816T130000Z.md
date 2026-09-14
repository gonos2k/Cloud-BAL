# CP06-A 실험 명세 — 2026-08-16 13 UTC

명세 ID: `CP06A-20260816T130000Z-v3`  
상태 (2026-09-14): **SPECIFIED / ACTUAL_COUPLED_NOT_RUN**.

- 기존 관측·처리 입력: 확보·사용 중. OFF/수상체·열역학의 기록된 실행 근거는 유지한다.
- 12/15 UTC OFF native 초기·경계자료: [준비 완료](../scratch/cp02_native_12_15.B4Lwmh/RUN_REPORT.md). 예보 실행 근거는 아니다.
- 물리 cloud omega 산정: 방정식·forcing·경계조건 및 실제 구현 미확정/미완료.
- v3 관측 target/sigma: 유효 필드와 출처 계약 미충족. 기존 실행기의 dynamic authority 조건도 미충족.
  모델 유래 물리 산정량은 관측 target/sigma로 대체 표기하지 않고 별도 의미·출처 계약을 정한다.

## 2026-09-14 unit-corrected native diagnostic

The [bounded runtime receipt](../scratch/cp02_unit12_runs/RESULT_RUNTIME.json)
records unit-corrected OFF, HYDRO, and LIQUID trajectories with the pinned
Intel executable. All three cases reached 12:59:40, 13:00:00, and 13:00:20,
with matching 88-file input manifests, exit 0, and finite numeric output
fields. The paired [unit-contract receipt](../scratch/cp02_host_unit_contract_x3bcr8ui/RESULT_UNIT.json)
records the O0/O2 number-basis, CCN-entry, domain-predicate, and metamorphic
successes.

This evidence remains a unit-corrected runtime diagnostic. It does not satisfy
the observational target/sigma contract, supply a physical cloud-omega driver,
or close CP06-A/CP02 requirement 4. The separate [CP02 model-dynamics
increment experiment](CP02_MODEL_DYNAMICS_INCREMENT_EXPERIMENT_20260914.md)
defines its covered-interior increment boundary mode; the original six CP02
gates and requirement #4 **INCOMPLETE** status remain unchanged.

기존 GO는 합의된 격리 연구·수정·검증 작업의 계속 진행 근거다. 미정의 물리량의
출처나 과학적 타당성이 확보됐다는 뜻은 아니다. 실제 결합 실행의 기술적 선행조건과
기존 CP06-A의 명시된 실험 범위 조건은 유지한다.

사용자의 “실험 명세 만들어 넣기” 요청에 따라 작성한 격리 연구 설계다.
아래 수치는 실행 전에 고정할 연구 제어값이며 과학적 성능이 검증된 기준이라는 뜻은 아니다.
명세 작성만으로 미정의 물리 산정량의 생성·검증이 완료되지는 않는다.
CP02·CP06-A 완료, native 검증, 운영 배포 상태는 변경하지 않는다.

**개선 목표:** 기존 cloud omega 경험함수를 역학·물리 방정식에 근거한 산정으로
대체한다. 기존 다변량 Barnes 분석 바람과 구름·수상체·열역학 입력을 사용하며,
경험계수 재조정이나 새로운 경험함수 작성은 개선 목표에 포함하지 않는다.
아래 v3의 관측 target 적합 실험은 기존 결합 구조의 명세이며, 물리적 omega
생성 방법의 확정·구현을 뜻하지 않는다. 방정식·경계조건·보존 검증을 포함한
새 산정 방법은 아래 「개선 대상 정정」의 범위에 따라 구체화한다.

## 1. 사례와 입력

- 시각: `2026-08-16T13:00:00Z`, epoch `1786885200`.
- 배경 x_b: `scratch/cp02_current_derived_O0.7rF6zk/matched_control_chain13_O0.bouyq6a7/derived_export/output/payload.nc`.
- SHA256: `d4f496174616a0adf69078ef4a02d6f82ebc5baa28401879c488f9495a0f6a11`.
- 격자: 235 × 283 × 22. 압력 순서·시각·격자·mask·질량분모 계약은 이 입력에서 유지한다.
- 현재 실측 상태: `dynamic_target_authorized=0`, 유효 omega target 0셀, 유효 sigma 0셀.
- 관측을 추가할 때 x_b의 물리장은 바꾸지 않고 관측 필드와 출처만 결합한다.
  결합 입력의 별도 경로와 SHA256을 실행 전에 기록한다. 원본 입력은 덮어쓰지 않는다.

## 2. 비교 후보와 순서

| 후보 | 처리 | 필수 비교 |
|---|---|---|
| OFF | 후보 계산 없이 x_b 전달 | 모든 물리장·mask·metadata 정확한 동일성 |
| HT | 같은 x_b에 수상체 proposal → thermo → EOS/geometry | 물·선택 enthalpy·질량 budget, support 밖 불변 |
| COUPLED | 같은 x_b에 proposal → thermo → EOS/geometry → 국지 balance → 전체 제약 | HT 대비 바람 증분, 관측 target fit, 전체 budget·잔차 |

각 outer trial은 동일 x_b에서 시작한다. 이전 trial의 증분을 누적하지 않는다.
COUPLED는 최대 8회로 고정한다(본 명세의 설계 선택; 현재 기본값 1회에서 변경).
각 단계 실패, 반복 한도 소진, 필수 결측, budget 실패 시 후보 전체를 x_b로 되돌린다.
무관측 대조에서는 wind innovation이 정확히 0이어야 하며 COUPLED 성공을 대신하지 않는다.

## 3. 허용 변수와 영역

- HT 갱신: T와 여섯 dry-air mixing ratio(rv, cloud liquid, cloud ice, rain, snow, graupel).
- COUPLED 추가 갱신: grid-relative u, v, pressure velocity omega(Pa/s).
- EOS/geometry: T·조성 변화에 필요한 높이·밀도·dry mass의 정합적 재계산만 허용한다.
  압력 좌표·PSFC·terrain mask는 고정한다. PSFC 변경과 below-ground/above-ground 전환은 v2에서 허용하지 않는다.
  고정 압력면의 진단을 dry-mass 보존으로 표시하지 않는다. 정합성 실패는 탈락이다.
- dynamic seed는 `above_ground AND observational_target_is_resolved(state) AND
  cell_is_usable(omega.valid, omega.quality, omega.source)`로 고정한다.
  cloud/radar 존재만으로 dynamic seed를 만들지 않는다.
- seed별 `r = sqrt((d_horizontal/12000 m)^2 + (abs(dp)/30000 Pa)^2)`가
  **1 미만**인 셀에만 kernel `(1-r)^4*(1+4*r)`를 부여한다. 여러 seed에서는 최댓값,
  seed 자체는 beta=1이다. 직사각형 반경 조건으로 대체하지 않는다.
- d_horizontal은 `cumulative_horizontal_distance`의 canonical dx/dy 누적 거리(m),
  dp는 canonical pressure의 Pa 차이다. 별도 위경도 거리·hPa 변환·보간을 추가하지 않는다.
  거리/kernel은 real64, 저장 beta는 real32로 계산한다. 실제 active mask는
  `real(beta,real64) > real(real(1e-3,real32),real64)`이며 경계 등호는 제외한다.
- seed mask, beta, active mask, pressure, dx/dy, units, dtype, 격자 순서와 생성 소스 hash를
  실행 전 support 파일에 함께 고정한다. 후보 결과에 따라 seed/허용 영역을 늘리지 않는다.
- thermo 허용 영역은 유효 cloud/radar seed와 사전 계산한 수송 도착 셀의 합집합이다.
  관측 입력·배경으로 한 번 계산해 고정하고, 후보 결과를 보고 확장하지 않는다.
- validation shell은 허용 영역에 연산자가 읽는 인접 셀/face를 한 겹 추가한 영역이다.
  thermo mask, dynamic mask, shell, 포화상 선택(liquid/ice), geometry reference level을
  실행 전에 배열 파일과 SHA256으로 고정한다. 이 union/shell 규칙은 명세의 설계 선택이며
  현재 Fortran이 자동 생성하지 않으므로 caller 입력으로 준비해야 한다. 셀별 포화상은 관측 phase 근거가 필요하다.
- support 밖 모든 원시 물리장·mask는 정확히 동일해야 한다. 경계 normal increment는 0이다.
  고정 support 안에 필요한 EOS/geometry 조정을 담을 수 없으면 자동 확장하지 않고 실패한다.

## 4. 고정 제어값과 판정

아래에 명시하지 않은 column/balance 설정도 7절 소스의 config 기본값 전체를 사용한다.
실행 시 실제 config를 보존하며 다른 값으로 바꾸려면 실행 전에 명세 버전을 올린다.
시험 결과를 본 뒤 같은 버전의 기준을 완화하지 않는다.
표준화 target-fit 감소는 본 명세가 추가한 독립 판정이며 현재 Fortran gate가 아니다.
실제 실행 전 이 설계 제어값과 관측 사용 근거를 함께 확정해 실행 기록에 연결한다.

| 제어/판정 | 값·정의 | 근거 |
|---|---|---|
| balance 최대 반복 / residual refresh | 800 / 50 | 현재 balance config |
| solver residual | RMS와 max 각각 ≤ max(초기 solver 잔차 × 0.002, 1e-12) | 현재 solver gate |
| increment residual | RMS와 max 각각 ≤ max(proposed increment residual × 0.25, 1e-12) | 현재 balance gate |
| physical residual | RMS와 max 각각 ≤ min(불변 배경의 해당 operator 잔차 + 1e-7, 1e-3) | 현재 physical_residual_limit |
| 바람 / omega 최대 증분 | 10 m/s / 5 Pa/s | 현재 balance config |
| target response ratio | [0.05, 1.50], 실패 셀 비율 0 | 현재 balance config |
| target fit | 사전 고정 유효 셀 N ≥ 20; J_OFF − J_candidate ≥ max(0.05 × J_OFF, 1e-6) | v2 사전 연구 설계 기준; 현재 Fortran gate 아님 |
| held-out LOS 검증 | 유효 20 samples 이상, radar ID 2개 이상; 가중 RMS_candidate ≤ 가중 RMS_input + 0.10 m/s | 표본 수는 config, 0.10 m/s는 evaluate_los_gate의 고정값 |
| forcing compatibility | 상대 1e-11, 절대 1e-14 | 현재 balance config |
| transport substeps | 최대 64, 수평 substep 최대 0.75 cell | 현재 column config |
| transport ledger | abs(I−O) ≤ 1e-13 kg/s + 1e-11 × max(abs(I),abs(O)) | 현재 flux_ledger_closes |
| thermo 목표 RH | 1.0, 사전 고정한 셀별 포화상에 대해 검사 | 본 명세가 선택한 caller 인자 |
| outer convergence | 저장 정밀도에서 T, rv, u, v, omega trial 차이가 모두 정확히 0; 추가로 여섯 종·geometry·전체 budget 판정 통과 | 기존 5-field feedback 기준 + 독립 verifier의 전체 상태 검사 |
| positivity / finite | 유효 셀의 여섯 종 ≥ 0, 모든 필수 물리장 유한 | canonical 계약 |

Target fit의 `J = sum(((omega-target)/sigma)^2)/N`는 무차원이다. N은 실행 전 고정한
서로 다른 canonical target 셀 수이며, OFF/COUPLED에 동일 mask·target·sigma를 사용한다.
후보의 결측·비유한값 때문에 셀을 사후 제외하면 실패다. 20셀·5%·1e-6은 이번 보완에서
선택한 연구 기준으로 통계적 독립성이나 과학적 타당성을 입증하지 않는다.

LOS 가중치는 `w_i=1/max(sigma_vrad_i^2 + beam_z_i^2*sigma_vt_i^2, 0.25 (m/s)^2)`이며,
`RMS=sqrt(sum(w_i*residual_i^2)/sum(w_i))`로 정규화한다.
residual은 관측 radial velocity에서 `beam_x*u + beam_y*v + beam_z*(w-vt_z)`를 뺀 값이다.
omega→w 변환과 유효성 검사는 기존 `evaluate_los_gate` 계약을 따른다.
`LOS_HELD_OUT`, `los_support=1`이고 vrad/nyquist/sigma_vrad/vt_z_mean/vt_z_sigma가
usable이며, fall-speed/phase/mixed QC와 입력·후보 omega→w 유효성을 통과한 표본만 쓴다.
이 사전 유효 표본 집합을 고정하고, 후보 결측으로 줄어들면 실패한다. 다른 무효 표본은
사유별 제외 수를 기록한다. N은 통과한 (i,j,k,radar) 수이며, radar 수는 서로 다른 ID 수다.
`N_eff=(sum(w))^2/sum(w^2)`도 보고하되 현재 20표본 gate를 N_eff 기준이라고 부르지 않는다.
표본 부족·radar 부족·가중치 합 0·LOS gate 미적용은 통과로 처리하지 않는다.

Transport ledger는 각 precipitation_flux_ledger의 I=`input`,
O=`deposited+suspended+boundary_exit+terrain_intercept+observation_blocked+
no_echo_blocked+microphysical_loss`이다. 각 항은 적분된 cell rate **kg/s**이며
kg/m²/s 또는 누적 질량 kg가 아니다. 모든 항의 유한성·비음수를 먼저 확인한 뒤 표의
오차식을 적용한다. 원장별 I/O/차이/허용오차를 보존한다.

물·선택 enthalpy·EOS·질량은 최종 저장 후보에서 기존 canonical validator 기준으로
독립 재계산한다. A_Q/A_E/A_M(분석으로 가한 변화), 내부 상변화, 수송 및 경계 유출을
각각 분리한다. 한 ledger의 허용오차를 다른 물리량의 단위에 그대로 적용하지 않는다.
독립 verifier가 해당 검사를 제공하지 못하면 통과가 아니라 미검증으로 남긴다.

## 5. 기존 처리·통합 관측의 연결 요건

관측자료는 원본 처리망에서 이미 읽고 사용 중이다. 입력 목록은
처리·통합 입력 선택 (로컬 전용 자료: `../config/cp06a_observation_inputs_20260816T130000Z.json`; 공개 PR에 포함하지 않음)에 기록한다.
아래 미완료 항목은 Cloud-BAL 필드 생성·연결 또는 계약 검증 상태이며, 원시 관측 부재를 뜻하지 않는다.

| 입력 | 요구 내용 | 현재 상태 |
|---|---|---|
| cloud/radar thermo seed | 원자료 경로·hash·valid time, QC/valid mask, cloud/phase 도출법·출처·사용 근거 | LCP/LTY 확보·Fortran 로더 연결; 우박은 uncertain unknown으로 보존 |
| omega target | 비영 관측 유도 값(Pa/s), mask, 도출식, 원관측 경로·hash·시각 | 기존 입력에서 해당 결합 필드 생성·연결 전 |
| target sigma | 동일 단위의 양수 유한값, uncertainty 산정 근거, target과 공통 출처 | 기존 입력에서 해당 결합 필드 생성·연결 전 |
| radar/LOS 근거 | 관측 clock, 좌표 frame, QC, dealias/Nyquist, fall-speed 구분·불확실성 | 기존 레이더 처리 자료 있음; LOS metadata 연결·검증 전 |
| 폭풍 이동·trajectory | 이동 벡터·frame·시간 구간·source/hash·불확실성 및 수송 경로 모형 | 없음; 수송 도착 영역 생성 보류 |
| 검증 관측 | 적합에 사용하지 않은 LOS sample·radar 분할 및 출처 | 기존 입력에서 해당 결합 필드 생성·연결 전 |
| 영역 배열 | 3절 규칙으로 만든 support·shell·포화상·reference level 및 hash | 기존 관측 연결 검증 후 생성 |
| 관측 사용 근거 | 해당 관측과 도출법을 이 사례에 사용할 수 있는 근거를 실행 기록에 연결 | 미확정 |

LGT/COM, 반사도 또는 강수유형만으로 omega target이나 sigma를 만들지 않는다.
0이나 상수 sigma로 누락을 메우지 않는다. 제조해는 기존 구조시험에서만 사용한다.
raw VELH/VELV는 LOS 관측이며 도출법 없이 omega로 사용하지 않는다. TID는 분류값이다.
모델 유효 시각과 radar volume의 관측 시작·종료 시각을 각각 보존하고, 폴더명으로
관측 시각을 대신하지 않는다. 13 UTC 폴더에서도 다른 시각의 volume은 제외한다.
`science_authority=NONE`인 target probe는 실제 target/sigma 공급원이 아니다.
누락된 held-out 관측은 채운 것으로 간주하지 않으며, 선택할 파일의 존재·내용을 먼저 확인한다.

## 6. 실행 준비와 산출물

1. 5절 실제 입력과 영역을 고정하고 입력/config/명세 hash를 실행 기록에 연결한다.
2. 현재 exchange v1의 동적 target 거부를 우회하지 않는다. 실제 후보 handoff와
   전체 상태·metadata 보존을 지원하는 Fortran 연결을 구현·검증한 후 사용한다.
3. 현재 5-field outer feedback만으로 가변 geometry 결합 완료를 주장하지 않는다.
   여섯 종·EOS/geometry와 함께 2절 반복 계약을 충족하는 구현이 준비돼야 실행한다.
4. `tests/intel_toolchain.sh`의 pinned ifx로 새 scratch에서 O0/O2 빌드한다.
   각 후보의 종료 상태, 최종 저장 상태, 단계별 budget, support 밖 변화, 독립 판정 결과를 남긴다.
5. GREEN은 동일 입력·설정과 물리량 비교를, RED는 누락 관측·support 위반·cap/rollback을 검사한다.
6. CP06-A 통과 후 동일 OFF/COUPLED 후보를 WPS→metgrid→real/native로 전달하고
   모든 필수 변수·mask·시각·frame·질량분모를 재읽어 비교해야 CP02 E03를 닫을 수 있다.

## 7. 고정 소스와 상위 계약

소스 경로는 Cloud-BAL 기준이다. 이 hash는 수치 제어값의 출처이며 실행 파일 hash를 대신하지 않는다.

| 소스 | SHA256 |
|---|---|
| `src/common/cloud_bal_pipeline.f90` | `188a2e1b9f467c6fa28e8f317e493975ddaf8dfbf5100398867666bbb6f2b478` |
| `src/common/cloud_bal_balance_operator.f90` | `9f460727d83a0b0ce428a10e5c51a76ebe358e5fc1b67bb8bf4d554569f47840` |
| `src/common/cloud_bal_column_physics.f90` | `f7d640bbee19a128af6556f16e346e9574d1845997d77eab48e844109f14e17d` |
| `src/common/cloud_bal_state.f90` | `0347dc140d3940013cf72d26a2d142980d0a8b2f0a1af1c55ed5f0305fffa9d5` |
| `src/common/cloud_bal_grid_geometry.f90` | `3e2b75c5a64730a65dd4762a4ed9cc8fe82017ca95a11cf40690bfa4bca3e703` |

검토 반영: v2는 영역 정의, LOS 가중 RMS, target-fit 최소 표본·개선폭, ledger 단위·규모,
cloud seed 출처 요건을 보완했다. 물리 코드와 실행 상태는 변경하지 않았다.

상위 계약: [CP06-A 완료 조건](CLOUD_BAL_FINAL_GOALS_CHECKPOINTS_20260907.md#cp06-a--등압면-결합-한-사례-검증),
[입력 준비 기록](CP06_A_INPUT_READINESS_20260910.md),
[CP02 E03 전달 준비](CP02_E03_COUPLED_TRANSPORT_READINESS_20260910.md).

2026-09-11: column 소스 hash 갱신은 기존 cloud/phase 검증 루틴의 PUBLIC 공개만 반영한다.
수식·제어값·수치 기준은 변경하지 않았다.

기존 처리 관측의 실제 OFF/HYDRO/LIQUID Fortran 실행 결과는
[2026-09-11 실행 기록](CP06_A_PROCESSED_INPUT_RUN_20260911.md)에 보존한다.
이 진단 실행은 본 명세의 COUPLED 통과를 대신하지 않는다.

2026-09-11 namelist 대조: 기존 `wind.nl`의 `WEIGHT_RADAR=0.25`는 시선속도 오차
2 m/s의 설정 근거다. 시선속도는 기존 다변량 Barnes에서 이미 처리되며 그 분석 바람은
Cloud-BAL에 입력된다. 위 target sigma 미연결은 omega(Pa/s) 오차 필드의 상태이며,
시선속도 오차 설정 자체의 부재를 뜻하지 않는다. [설정·사용처 확인](CP06_A_BARNES_SETTINGS_20260911.md).

## 개선 대상 정정 — 2026-09-11 사용자 확인

목표는 기존 cloud omega 경험함수를 역학·물리 기반 산정으로 대체하는 것이다.
경험함수를 다시 만들거나 구름형별 계수·곡선 모양을 조정하는 작업이 아니다. 원본
`cloud_bogus_w_lgt_ct`의 구름형·깊이·격자 간격 기반 상승류와
`w_to_omega = -w*p/8000`을 기준선으로 명시한다.
시선속도는 이미 기존 다변량 Barnes로 처리되므로, Barnes 재구현이나
분석 바람 오차 전파를 핵심 개선으로 대체하지 않는다.
LW3 분석 OM과 LCO 경험적 cloud omega를 별도로 추적한다.
기존 분석 바람, 구름·수상체·열역학 입력을 사용하되, omega의 비영 증분은
명시한 역학 방정식과 경계조건에서 구하고 질량 연속성 및 물·열역학 보존과 함께 검증한다.
부력·하중만으로 속도를 정하는 새 경험식은 이 목표의 완료 근거가 아니다.
현재 `build_cloud_targets`는 구름층을 구분하고 배경 w를 유지하므로 이러한
역학적 산정이 구현됐다는 뜻이 아니다. 기존 balance/thermo 검사 통과도
구름에 의한 역학적 forcing의 생성과 native omega 전달을 대신하지 않는다.
기존 실험의 결과와 실행 상태는 이 범위 정정으로 변경되지 않는다.
상세 근거는 [Barnes 및 cloud omega 구분](CP06_A_BARNES_SETTINGS_20260911.md)을 따른다.

현재 v3의 COUPLED는 관측 target/sigma를 받는 기존 balance 실험 계약이다.
`cloud_bal_pipeline.f90`는 `TARGET_AUTHORITY_OBSERVATIONAL`만 허용하고,
`build_localized_support`도 `observational_target_is_resolved`로 seed를 만든다.
따라서 이 계약 자체를 역학적 omega 생성 알고리즘으로 해석하지 않는다.
다음 구현에서는 기존 분석 바람을 포함한 물리 입력에서 forcing을 계산하는 방정식,
경계조건, 압력·질량 좌표 및 후보 전달을 먼저 명시해야 한다. 계산된 forcing을
관측 omega로 이름만 바꾸거나 source bit만 추가하는 것은 구현이 아니다.
이는 외부 omega 관측자료의 추가 확보를 요구하는 것으로 해석하지 않는다.
새 물리 계산의 실행 명세는 해당 방정식과 검증 조건을 포함해 별도 버전으로 고정한다.

### 물리 방정식 후보 검토 — 실행 조건 변경 아님

[Kohl and O'Gorman (2024), §2a–c](https://pog.mit.edu/src/kohl_vertical_velocity_distribution_asymmetry_2024.pdf)의
습윤 QG omega 역산은 잠열을 내부적으로 표현하는 후보지만, 포화 상승과
강수 제거, 준지균 흐름을 가정한다. 원문의 하단 경계는 모델 omega를 사용하며,
이 방법을 5 km 구름 초기화에 바로 적용할 수 있다는 근거는 아니다.
기존 경험함수를 대체할 구현으로 아직 선택하지 않았다. 임의의 안정도 감소
계수나 무조건 0인 하단 경계로 자료·물리 조건을 대신하지 않는다.
독립 검토 결과, 안정한 준지균 영역으로 범위를 줄인 solver는 별도 연구 진단일
수 있지만 이번 구름 omega 대체의 완료 조건을 대신하지 못한다. 따라서 이
제한된 후보를 구현하기 위해 배포 경로에 새 모듈이나 dry-QG fallback을 추가하지 않는다.

실제 13 UTC의 건조 안정도 진단은
`scratch/cp02_dry_stability_2tbjzu3y/RESULT.json`에 기록했다. 유효 구름 셀
537,249개 중 35개에서 건조 N²가 비양수다. 이는 습윤/일반화 연산자의
타원성을 판정한 결과가 아니며, 계수 floor나 clipping을 적용하지 않았다.
v3 제어값, 입력 권한과 실행 상태는 그대로다.

13 UTC 기존 실행의 경험함수 계수는 Cu=0.5, Sc=0.10, St=0.017 m/s, Ct=1.3이다.
`L_BOGUS_RADAR_W=.false.`이며 LCO→`cloud_omega_evidence`의 유효 244,326셀을
수직 순서 변환 후 정확히 보존함을 직접 확인했다. 현재 `omega_target_valid=0`은
별도 evidence/target 구분으로 인한 것이므로 입력자료 부재를 뜻하지 않는다.
개선 실험의 기준선은 이 실제 설정과 저장장을 사용한다.
[검증 기록](../scratch/cp02_cloud_omega_baseline_20260911/RESULT.json).

## v3 입력 갱신 — 최신 Fortran producer 및 EXPORT_OFF

v3는 동일 13 UTC 관측자료·실제 GA 계수를 사용한 최신 O0 producer/export 결과로
배경 입력을 갱신한다. O0/O2 각각 producer와 같은 실행파일의 EXPORT_OFF가 종료 0이며,
14개 producer 산출물은 기존 기준선과 동일하고 128개 payload 변수 배열은 O0/O2가
정확히 같다. global identity의 실행파일·configuration 해시는 각각의 실제 실행을 구분한다.

과거 v2 payload 해시는 `911189f0e3f52853c7240af53804c63cfe59ec0234a0ac58a2dbf0c42ca47cc1`이다.
v3에서 달라진 물리 필드 그룹은 기존 LCP/LTY를 읽은 cloud fraction/type/phase와
관련 valid/quality/source다. 실험 제어값과 허용 갱신·rollback 조건은 v2를 유지한다.
cloud omega evidence 244,326셀은 그대로 보존되며 target/sigma를 새로 생성하지 않았다.
따라서 입력 갱신만으로 결합 물리의 완료나 실행 상태를 승격하지 않는다.

[최신 O0/O2 export 대조](../scratch/cp02_current_derived_O0.7rF6zk/EXPORT_O0_RESULT.json),
[실제 LCP/LTY 재읽기](../scratch/cp02_derived_current_O2.OtirDj/CLOUD_INPUT_READBACK.json).


## Native physical-trajectory experiment candidate — 2026-09-11

Status: DESIGN_ONLY / NOT_RUN; this does not replace v3 or authorize a new
omega target. The purpose is to obtain cloud-related physical tendencies
from the model equations before defining a replacement initialization operator.
A forecast vertical velocity is not automatically an observational target.

The candidate interval is 2026-08-16 12:00 to 13:00 UTC. Initialize from the
12 UTC analysis and evaluate at 13 UTC; do not advance the 13 UTC analysis
and label the result as valid at 13 UTC. Existing 13 UTC analyzed fields are
an evaluation reference, not a source of inferred microphysical heating.
Both reference and candidate must use the same initial/boundary inputs and
physics configuration for the eventual paired comparison. A trajectory alone
does not isolate cloud forcing; its paired perturbation and attribution are
still to be specified.

The retained native namelist records timestep 20 s, adaptive stepping false,
nonhydrostatic true, MP_PHYSICS=37, CU_PHYSICS=37, radiation=4/4, and PBL=11.
These are inspected settings, not newly selected physical defaults. A 12→13
trajectory also needs valid boundary coverage: the current retained
INTERVAL_SECONDS=10800 must not be silently treated as hourly boundary data.
The [12/15 UTC preparation receipt](../scratch/cp02_native_12_15.B4Lwmh/RUN_REPORT.md)
now records initial and boundary files for this interval (10800 seconds), with
metgrid/real exit 0. No forecast was run. Native microphysics state/initialization,
startup W handling and the paired physical perturbation remain unresolved for
this research trajectory; the boundary preparation does not resolve them.

Diagnose pressure omega using the model pressure evolution, advection and
coordinate motion, with declared native metrics and staggering. Geometric W
and mu-coupled eta-dot remain distinct outputs. A buoyancy contribution times
an arbitrary interval, or continuity reintegration of unchanged winds, is not
the physical replacement. Fix the paired cloud perturbation, diagnostic
sampling, conservation checks and model-derived authority contract before
promoting any trajectory result into the coupled initialization path.
