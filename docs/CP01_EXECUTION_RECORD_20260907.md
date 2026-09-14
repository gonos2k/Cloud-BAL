# CP01 실행 기록 — Native 질량·격자·frame 계약

상태: IN_PROGRESS / NOT_RUN. 진입 근거: CP00 local scoped 종료와
`scratch/cp00_handoff_20260907.json`, workspace의 `wiki/log.md` 단계 종료 KG 기록.
기존 P1–P8·45개 기능 gate 및 운영 승격은 변경하지 않는다.

## 현재 범위와 작업 배정

- Primary: pressure interface·cell_dp·인접 partial-face·독립 column oracle 계약 점검.
- cp01_native_inventory: 실제 host/version/options/microphysics/native binary의 읽기 전용 목록.
- cp01_mass_mapping: canonical–LAPSPREP–WPS 변수·분모·wind frame의 소스 추적.
- 후속 구현·시험 전 GREEN/RED로 계약·threshold와 변경 범위를 독립 점검한다.

원본 ANAL/MODL와 legacy release는 읽기 전용이다. 운영 producer·forecast·publisher 실행,
원격 설정 변경, 실제 DYNAMIC 권한·ACTIVE 승격은 하지 않는다. 대상 모델이 불명확하면
추정으로 native 계약을 완료시키지 않는다.

## 진입 시 미폐합 항목

1. 실제 host model/version, 질량좌표·staggering·microphysics와 binary/options pin.
2. canonical/WPS/native species 및 분모, pressure/EOS와 A_Q/A_M/A_E 계약.
3. pressure-fixed 진단과 native-dry-mass 경로의 차이, optional species coverage.
4. pressure column·부분 면적 교집합·thin cell·PSFC 절단에 대한 독립 해석 oracle.
5. earth/grid frame·metric·w/omega 근사·상하부 경계·자료시각 계약.
6. 위 항목의 양성/음성 시험 및 독립 종료 검토. 현재 PASS 항목은 없다.

CP01은 계약과 작은 oracle의 단계다. Native writer 왕복이나 state-dependent 전체 결합은
CP02/CP06/CP07에서 실제 수행해야 하며 이 단계의 문서만으로 대신하지 않는다.

## Geometry 소스 확인과 oracle 설계 (아직 실행 전)

`configure_pressure_geometry`는 pressure center로 활성 셀을 정하고 첫 활성 셀을 PSFC까지
확장한다. 단순히 모든 원래 midpoint cell을 PSFC와 자른 모형과는 다르다. 테스트의 독립
기대값은 이 **center-domain / surface-extended pressure diagnostic** 계약으로 명시해야 한다.
Native dry-pressure 좌표의 cell thickness와 같다고 가정하지 않는다.

중심 pressure `[100000, 95000, 90000] Pa`, 상단 interface `87500 Pa`의 해석 표:

| PSFC Pa | 활성 center index (1-based) | cell_dp Pa | 전체 column Δp Pa |
|---:|---|---|---:|
| 100000 | 1,2,3 | 2500,5000,5000 | 12500 |
| 99000 | 2,3 | 0,6500,5000 | 11500 |
| 95500 | 2,3 | 0,3000,5000 | 8000 |
| 95000 | 2,3 | 0,2500,5000 | 7500 |
| 92500 | 3 | 0,0,5000 | 5000 |
| 91000 | 3 | 0,0,3500 | 3500 |

각 열의 독립 합은 `Σm_tot = dx*dy*(PSFC-87500)/9.80665`다. 입력은 binary32로 정확하게
표현되는 정수 Pa이며, 합산은 binary64로 수행한다. 이 해석 시험의 사전 오차 기준은
pressure `1e-8 Pa + 64*epsilon64*|reference|`, mass `1e-6 kg + 64*epsilon64*|reference|`다.
이는 작은 해석 fixture의 부동소수점 비교 기준이지 native remap/관측/과학 허용오차가 아니다.

Partial face의 pressure interval `[top,bottom]` 공통 두께는
`max(0, min(bottom_left,bottom_right)-max(top_left,top_right))`다. 실제 지형 면적과 map factor를
곱하는 native metric은 별도다. 현재 `build_balance_operator`는 양쪽 `cell_dp` 산술평균을 사용하므로
서로 다른 절단 셀에서 위 교집합과 일치하지 않는다. 예: 두 번째 cell의 PSFC 99000/95500 Pa는
교집합 3000 Pa, 평균 4750 Pa다. 이 차이는 CP03 actual operator 설계에서 닫아야 하며
oracle-only 성공으로 B01을 PASS로 바꾸지 않는다.

다음 시험은 이 표와 열합을 실제 `configure_pressure_geometry` 결과에 대조하고, PSFC/단위/pressure
순서 오류 시 원자적 거부, 비활성 셀 질량 0, optional water 분모와 OM-independent domain을 함께 검사한다.
현재는 계약 초안이며 독립 계획 검토와 시험 receipt가 아직 없다.

### Geometry 시험 진입 검토와 고정 fixture

cp00_green: GO, cp00_red: conditional GO (CP01 test-only). RED의 조건에 따라 수평격자는
`dx=2000 m`, `dy=3000 m`, 면적 `6000000 m²`로 고정한다. 전체 interface 기대값은 다음과 같다.

| PSFC Pa | pressure_interface Pa (4개) |
|---:|---|
| 100000 | 100000,97500,92500,87500 |
| 99000 | 99000,99000,92500,87500 |
| 95500 | 95500,95500,92500,87500 |
| 95000 | 95000,95000,92500,87500 |
| 92500 | 92500,92500,92500,87500 |
| 91000 | 91000,91000,91000,87500 |

질량 reference는 위 면적·독립 decimal 계산으로 시험 소스에 상수로 저장한다.
기존 production validator의 허용오차를 재사용하지 않고 위 analytic-fixture tolerance를 사용한다.
잘못된 pressure 순서, PSFC NaN, 단위 오류는 모든 게시 geometry 배열(dx/dy 제외), domain의
변경이 없어야 한다. 아직 qv/species를 구성하지 않은 상태의 dry_air_mass_measure는 0이어야 하며
`pressure_geometry_is_valid`의 전체 상태 PASS를 이 시험의 판정으로 사용하지 않는다.

## 첫 geometry 시험·수정 결과

실제 pinned ifx `-fpe0`에서 새 oracle의 NaN PSFC 입력이 `configure_pressure_geometry`
946행의 ordered comparison에서 `forrtl: error (65): floating invalid`로 중단됐다.
Fortran `.OR.`는 short-circuit을 보장하지 않으므로 finite와 range 검사를 같은 식에 넣으면
NaN 비교가 먼저 평가될 수 있다. Dx/Dy, PSFC/center에서 finite 거부를 별도 IF로 앞당겼다.
유효 입력의 물리식·compiler flag·권한은 변경하지 않았다.

- 수정 전 executable 재현: `scratch/cp01_geometry.2qYWQq/reproduced_failure.json`/`.log`,
  Intel runtime profile을 적용했을 때 returncode -6. 최초 compile은 도구 대화 기록에 있고
  별도 precompile source receipt는 없으므로 완전한 source-to-binary 인증으로 주장하지 않는다.
- 같은 디렉터리의 `prefixed_failure.*`는 Intel runtime 미설정으로 exit 127인 별도 시도다.
  이 로더 오류를 NaN 결함 재현 증거로 사용하지 않는다.
- 수정 후 전체 unit suite: `scratch/cp01_oracle_verify.zluclmo2/receipt.json`, `run.log`.
  04:12:08–04:14:03 UTC, `bash tests/run_unit_tests.sh` exit 0.
  Log SHA256 `664876df5ad86011b427ab801ef7201842521519544977492d645be2511dc50e`.
- 새 table oracle: 6개 column 및 단위/PSFC NaN/pressure 순서/center NaN/dx NaN 5개 거부 사례.
  전체 게시 geometry 배열·domain 원자성 검사. 기존 unit runner에 통합했다.
- RED 코드 검토: configure-only PASS. `grid_arrays_valid`/`pressure_geometry_is_valid`의
  별도 NaN 경로에는 같은 유형의 위험이 남으므로 전체 canonical NaN 안전을 주장하지 않는다.
- GREEN 구현 검토: oracle의 독립 상수·고정 오차와 수정 범위 및 실제 전체 unit PASS를 확인했다.
  현재 CP01 receipt에는 ifx/runtime 상세 hash 대신 검증된 toolchain script hash만 있으므로
  강한 재현성 주장에는 CP00의 toolchain 증거 연결 또는 별도 실행 환경 receipt가 필요하다.
- 기존 baseline receipt는 수정 전 코드의 과거 증거다. 이번 코드는 dirty worktree의 새 hash로
  검증했으며 이전 CP00 PASS를 새 코드 검증으로 복사하지 않는다.

## Native 및 writer 읽기 전용 조사 결과

실제 대상 후보는 `MODL/KLFS/NE57/DAIO/2026081613/klfs_lc05_prep_init.202608161300`이다.
Primary가 NetCDF header에서 `REAL_EM V4.6.0 PREPROCESSOR`, valid/start 2026-08-16 13 UTC,
`GRIDTYPE=C`, dx/dy=5000 m, HYBRID_OPT=2, MP_PHYSICS=37을 직접 확인했다.
U/V/W는 각 축 staggered, T/P/PB/MU/MUB와 species는 mass-grid로 저장된다.
Native T의 정의와 PH/PHB·MU/MUB 분해를 canonical T·Phi·mass에 직접 복사해서는 안 된다.

cp01_native_inventory가 확인한 binary identity:

- `MODL/KLFS/NE57/EXET/klfs_lc05_init_latb.e`:
  `49e5d54c58259baa21a07899b56af10ed67f56925f829bd7b5beb04a00e5fbf2`.
- `MODL/KLFS/NE57/EXET/klfs_lc05_fcst.e`:
  `c956cdcb352d7a5cc8de4092e5a5103c41dd168b4f684c56b30ba8b05c84f9d9`.
- 수정 WRF source/commit 및 mp_physics=37의 정확한 scheme 구현은 아직 미확인이다.
  Binary의 version 문자열만으로 공식 upstream source와 동일하다고 간주하지 않는다.
- 실제 template 경로는 `MODL/KLFS/NE57/DABA/namelist/namelist.input_real` 및
  `namelist.input_fcst`이며 primary가 각각 SHA256
  `6b73a751f58fdbeea5abccf5dbbf607ad4049e45e2a510dc04fa427257ba4a04`,
  `6af4afe9125a2788456d2b62626f98d740f88b0f26388f731366ab7506bb8f40`를 확인했다.
  Per-case materialized forecast namelist/log/forecast output은 scoped 조사에서 발견되지 않았다.
- `prep_chnk.202608161300`의 내부 START_DATE는 2024-07-23 06 UTC라는 agent 보고가 있다.
  원인·실제 유효성 미검증이므로 정상 초기화 입력으로 승인하지 않는다.

cp01_mass_mapping 소스 추적 결과:

- Canonical real reader: `sh → r_v=sh/(1-sh)`, `ht → Phi=g*ht`,
  `lwc/ice/rai/sno/pic [kg m^-3] → r_j=C_j/rho_d`.
- Legacy LAPSPREP는 vapor virtual-temperature 기반 다른 density로 C_j를 나눠 WPS QC/QI/QR/QS/QG를 쓴다.
  Generic kg/kg label만으로 dry-air denominator 일치를 증명할 수 없다.
- `output_ungrib_format`은 legacy 배열 인자를 받으며 canonical state의 직접 연결이 없다.
  WPS writer에는 w/omega, dry-air mass, pressure interfaces 등의 출력 인자가 없다.
- WPS wind-frame flag는 있지만 실제 회전은 writer가 수행하지 않는다. Canonical source frame도
  아직 명시되지 않아 flag를 맞춘 것만으로 물리 frame 계약을 닫을 수 없다.

따라서 CP01 전체 NOT_RUN은 유지한다. 다음은 정확한 native/source·microphysics 계약 확인,
분모와 staggering 변환 정의, thin cell/부분 face·moist column·NaN validator 경로의 후속 시험이다.

## Native hybrid oracle 진입 계약 (2026-09-07 후속)

읽기 전용 독립 진단에서 `mu=MU+MUB`, `dp=-(C1H*mu+C2H)*DNW`를
`p_interface=C3F*mu+C4F+P_TOP`의 인접 차 및 column 합 `mu`와 대조한다.
이는 native dry-pressure geometry의 내부 정합성 시험이며 EOS, 수분 보정 또는
수정 host binary의 동치성 검증은 아니다. `P+PB`를 dry pressure로 대체하지 않는다.

실자료 실행 전 고정한 허용오차는 pressure `0.05 Pa + 2e-6*pressure_scale`이다.
Binary32 계수의 곱·차를 binary64로 재계산하는 오차를 위한 공학적 기준으로,
관측오차·분석증분·과학 승격 허용치가 아니다. 작은 정수/이진분수 해석 fixture는
별도로 `1e-10` 절대오차를 사용한다. Eta/DNW 정합은 `2e-7` 절대오차로 검사한다.
계수·shape·mask·단위·NaN·양의 DNW·map factor 오류는 거부해야 한다.

`md=area*dp/g`의 g는 호출자가 명시한다. 공식 upstream WRF 4.6은 g=9.81,
현 canonical은 9.80665이므로 같은 상수라고 숨기지 않는다. 실제 수정 binary의 g는
미확인이다. Native dry mass에 수분 분모 `(1+r_t)`를 다시 적용하지 않는다.
운영 파일은 읽기 전용이며 원본 hash의 전후 동일성을 기록한다.

### NaN validator 후속 수정 및 전체 회귀

`cp01_validator_nan`이 두 geometry predicate의 finite/ordered 검사 분리와 직접
dx/dy 검사를 구현했다. Primary가 pressure center/PSFC를 추가하여 양성 canonical
baseline과 9개 NaN mutation을 검사했다. Private `grid_arrays_valid`는 public
`validate_canonical_state`를 통해, `pressure_geometry_is_valid`는 직접 호출한다.
기존 6-column 해석 표와 configure의 5개 원자적 거부 사례는 유지했다.
수정 전 **이 두 predicate 자체**의 실행 재현을 독립 보존한 것은 아니므로,
앞선 configure 결함 재현과 이번 후속 회귀 성공을 구분한다.

- 전체 suite: `scratch/cp01_oracle_verify.or8pxnzw/receipt.json`, `run.log`.
- 실행: `bash tests/run_unit_tests.sh`, 04:33:28–04:35:44 UTC, exit 0.
- log SHA256: `470aeaa063aa7366f90bb24352f6126910f879ae0fa8e4efbb5ff1c426021cb1`.
- 신규 hybrid synthetic 4 tests도 포함한다. 새 Python tool/test를 포함한 소스 7개,
  setvars/ifx/libimf/libintlc 4개 hash는 실행 전후 동일하다.
- `cp00_red` 독립 검토는 bounded validator 수정 PASS. Canonical 모든 수치
  overflow/NaN 경로를 포괄한 인증은 아니며 CP01 전체 종료도 아니다.
- Native mapping 초안: [NATIVE_MASS_FRAME_CONTRACT.md](NATIVE_MASS_FRAME_CONTRACT.md).

현재 기초 geometry/NaN/synthetic hybrid 시험은 통과했으나, 수정 host source와
MP_PHYSICS=37의 species/상수/분모 계약, upstream frame/boundary 및 부분 face 시험은
남아 있다. 따라서 CP01 `IN_PROGRESS / NOT_RUN`과 본체 gate는 유지한다.

### 실제 13 UTC hybrid algebra 진단

GREEN `cp00_green` 및 독립 `cp01_native_oracle_review`의 bounded 진입 검토 후
primary가 읽기 전용 CLI를 실행했다. 후자의 RED 조건인 전후 input hash 명시는
wrapper receipt에 반영했다. 이 검토의 native/mass/science 폐합 판정은 HOLD다.

- `scratch/cp01_native_geometry.d_i2aw_i/receipt.json`, `run.log`, exit 0.
- 04:37:00 UTC, `python3 tools/check_native_hybrid_geometry.py <실제 prep_init> --gravity 9.81`.
- input before/after SHA256 모두 `3be13db84355692f0c42fe8d1460e902d9428e714f54ac3606d9c78b78bc2265`.
- log SHA256 `e606aed21321bbd9dfbbfabb0891f3ee2e422b9367a01452fd54cb8cf3c18533`.
- 39×282×234 전체 배열, 입력 float32 / 계산 float64.
- 인접 interface와 계수 layer의 최대 차 `0.0024648676608194364 Pa`.
- column 합과 MU+MUB의 최대 차 `0.0003556745359674096 Pa`.
- 위 고정 오차에 대해 geometry algebra PASS. 면적·kg 합은 명시한 map metric/g의
  **가정 기반 진단값**으로만 남기고 native 보존 검증으로 사용하지 않는다.
- 도구/시험 소스 hash는 full-unit receipt와 동일하다. 문서는 실행 당시 hash를
  보존했으며 이후 이 결과와 근거를 추가했다. 이전 receipt를 덮어쓰지 않았다.

공식 v4.6.0 commit `0a11865f97680fdd6865b278ea29d910e5db3ed7`의 Registry에
MP_PHYSICS=37 package가 없다. `phys/module_physics_init.F:5326–5340`의 AREA2D는
map-factor 식이 비활성이고 DX*DY가 활성이다. 실제 입력에는 AREA2D/DX2D가 없다.
이를 dynamics 보존 면적과 동일시하지 않으며 수정 host source가 여전히 필요하다.
정확한 근거 URL과 해석 제한은 [native 계약](NATIVE_MASS_FRAME_CONTRACT.md)에 있다.

다음 진입 조건: 수정 WRF Registry/미세물리/상수/build 출처 확보, 이어서 species·frame·
boundary 계약 및 남은 CP01 oracle 완료. CP01은 종료하지 않았으므로 CP02로 넘어가지
않고 단계 종료 KG도 아직 실행하지 않는다. 코드 graph는 CP01 이전 스냅샷이다.

## CP01 후속 — partial-face/thin-cell와 frame 출처

사용자 `go`에 따라 수정 host 출처를 읽기 전용으로 추가 조사하고 독립 geometry
시험을 보완한다. 새 테스트는 production balance나 native 면적을 변경하지 않는다.
사전 고정한 fixture는 기존 surface-extended cell 교집합(99000/95500 Pa 열의
cell 2: 3000 Pa, 산술평균 4750 Pa)과 binary32-exact thin centers
`[95000,94999,94998] Pa`, top `94997.5 Pa`다. 허용오차는 기존
`1e-8 Pa + 64*epsilon64*|reference|`를 유지한다. 시험 helper는 pressure interval
교집합의 해석 oracle일 뿐 실제 balance가 그 값을 쓰는지 검증하는 것은 아니다.

Primary가 `src/include/main_sub.inc`의 `l_grid_north_out=.true.` 및
`src/wind_openmp/main_sub.f`의 output rotation/writer를 추적했다. 현 소스 설정은
LW3 grid-relative 출력을 지시한다. 실제 13 UTC final_ordered LW3에는 frame attribute가
없으며, `scratch/cp01_frame_trace.ig53avsk/receipt.json`에 소스 7개와 입력 hash 전후
동일성을 보존했다. 이는 기존 Barnes 완료를 재심사하지 않으며 binary→bytes 연결이나
FSF frame을 새로 인증한 것도 아니다. 자세한 경계는 native mass/frame 계약에 추가했다.

### 수정 host 빌드 출처 추가 조사

`cp01_host_provenance_followup` 조사 후 primary가 두 binary의 문자열과 ELF notes를
재확인했다. `scratch/cp01_host_trace.hibfq2e0/receipt.json`에 binary·실행 shell·namelist
6개 파일 hash 전후와 다음 정적 근거를 저장했다.

| binary | Build ID | 포함된 source 경로 |
|---|---|---|
| `klfs_lc05_fcst.e` | `e06cda8398288e500ef8484d08663c8c31c0c042` | `/h2/home/sop/fcst/MODL/KLBG/NE57_2604/.SRC/KIM-meso_v0.9.5/inc/set_timekeeping_alarms.inc` |
| `klfs_lc05_init_latb.e` | `02479a7312111fdebaf8cf30effa90ff0ec76dad` | `/mnt/gpfs/nmcdss2/gdps/pjh21/src/kma/klbg_v0.9.4.1/inc/set_timekeeping_alarms.inc` |

외부 경로에 접속하거나 binary를 실행하지 않았다. `readelf -n`은 두 파일의 build
notes gap 경고를 냈다. Build ID/포함 문자열은 식별 단서이지 source commit이나 완전한
빌드 증명이 아니다. 다른 source-tree 경로만으로 binary 비호환을 단정하지 않는다.
공통 V4.6.0 문자열만으로 같은 수정본이라고 간주하지도 않는다.

두 shell은 `DABA/namelist/namelist.input_*`를 치환해 실행하려는 구조지만, 외부
`~/jobs/${GRID}/UTIL/ENVI/klfs_src`의 환경 및 당시 materialized namelist/run receipt는
이 조사에서 확인되지 않았다. 따라서 **의도된 호출 구조와 정적 파일 identity**만
확인했으며 실제 해당 시각 runtime→binary→input의 결속을 인증한 것은 아니다.

필요한 후속 자료는 위 두 수정본의 Registry, microphysics driver/module, model
constants, configure/build receipt와 호환성 근거다. 특히 MP_PHYSICS=37의 선택 및
종별/number-field 정의가 필요하다. 기존 Barnes 완료 범위에는 변경이 없다.

### Partial-face/thin-cell oracle 완료 — CP01 전체 종료 아님

`tests/test_pressure_partial_face_oracle.f90`를 추가하고 기존 unit runner에 연결했다.
두 독립 리뷰 `cp00_green`/`cp00_red`는 test-only PASS다. 초기 targeted run은
`scratch/cp01_partial_face_oracle.mNUOw6/`의 exit 0이나 receipt.txt가 최소 기록이므로
전체 source/build 인증으로 사용하지 않는다. Primary의 확대 suite는 다음과 같다.

- `scratch/cp01_oracle_verify.ichm3gif/receipt.json`, `run.log`.
- `bash tests/run_unit_tests.sh`, 04:54:25–04:56:46 UTC, exit 0.
- log SHA256 `e8e75eac3ec4a7ab11d7686b73d5a9150acf9f1f487ab0c183e60da1ab0f433c`.
- 신규 test 포함 소스 8개 및 setvars/ifx/libimf/libintlc 4개는 실행 전후 동일.
- production state는 직전 suite와 같은 hash `008f3b91ff0338c4e4197e09cae6bd3f53b3ee90132ea3048bdfcf1026c397f9`.
- 새 시험은 literal 6-column geometry, 3000/4750 Pa 교집합-평균 구분, zero/touch/disjoint,
  thin 3-column 및 0.5/1 Pa cell을 검사한다. Production balance의 평균 metric은
  변경·재인증하지 않았다. 그 수정과 native face metric은 CP03의 별도 범위다.

현재 CP01의 pressure diagnostic 해석시험 묶음은 scoped PASS다. 수정 host 소스/
MP_PHYSICS=37 및 frame/build/boundary 연결은 미폐합이므로 CP01 전체 `NOT_RUN`,
CP02 미진입, 운영·DYNAMIC·science 권한 NONE을 유지한다. 단계 종료 KG 조건도 아직
충족되지 않았다. 위 두 외부 수정본의 소스와 빌드 기록이 다음 진행에 필요하다.

### Pressure-face 분할 구현 (2026-09-07 05:12 UTC)

- `cloud_bal_grid_geometry`에 선형 시간 `partition_pressure_face`를 구현했다.
  서로 다른 층 번호의 접촉면까지 반환하며, zero-width 셀은 면을 만들지 않는다.
- 실제 configure 출력의 cross-level 1500 Pa, 독립 dense oracle, thin cell,
  좌우 교환, 불량 입력 시험을 추가했다. 같은 층의 교집합만으로는 전체 면을 표현할 수 없다.
- pinned ifx 전체 `tests/run_unit_tests.sh` exit 0; 추적 소스 9개와 toolchain은 실행 전후 동일.
  증거: `scratch/cp01_oracle_verify.akvamfzw/receipt.json` 및 `run.log`.
- 이 변경은 geometry 구현이다. Balance D/G·연결성·최종 residual의 공동 연결은 아직 하지
  않았으며, CP01 전체와 native/science 승격 상태는 변경하지 않았다.

### 공통 면의 balance 연결 구현 (2026-09-07)

- 이후 `balance_operator`에 sparse cross-level 면을 연결했다. 발산·수반·최종 상태
  잔차·연결성 판정이 같은 면을 사용한다. 일부 면이 권한 밖 셀에 닿으면 해당 바람
  자유도를 고정한다. 분할면 합산의 roundoff는 연결성에서만 처리하며 D/G 값은 바꾸지 않는다.
- 독립 dense oracle은 x/y 지형, 혼합 active/inactive 이웃, 비균일 metric,
  float32 최종 상태를 검사한다. 기존 HEAD 연산자는 새 flux 검사에서 실패한다.
- pinned ifx 전체 suite PASS: `scratch/cp01_oracle_verify.xrw6pctr/receipt.json`.
  앞선 연결성 실패 실행 `gyhcpfoc`도 보존했다. O2 focused 시험도 통과했다.
- 13 UTC 실격자 제조해: `scratch/diagnostic_single_13utc.xqobpw/receipt.tsv`.
  22회 반복, support 밖 변경 0; target 실패율 6/16은 남아 있다. 게시하지 않은
  dirty-tree 수치 진단이며 native face DOF, A-grid 응답 문제, CP01 전체를 완료한 것은 아니다.
- `kg-update`로 코드 구조만 반영했다. Native 연계에 필요한 수정 WRF 소스 경로 두 곳은
  이 환경에서 접근되지 않는다. 운영·DYNAMIC·science 승격 상태는 유지한다.

후속 12/14/15 UTC도 동일 binary·설정으로 driver/validator exit 0이었다
(`scratch/diagnostic_single_13utc.xqobpw/extra_times_receipt.json`). 12–15 UTC의 반복수는
30/22/22/23, support 밖 변경은 모두 0이다. Target 약응답 비율은 각각
50/37.5/46.7/50%로 남는다. 네 연속시각의 **실격자 제조해 진단**이며 독립 네 사건의
과학 검증 또는 게시된 exact-HEAD suite가 아니다. 입력·소스·dependency 불변 확인을 보존했다.

### 독립 cell solver 선행 수정 (2026-09-07)

- Native 소스 대기 중 기존 `saturation_adjust_cell`의 수치 결함 두 개를 수정했다.
  극단 phase endpoint가 온도 범위 밖이어도 내부 해를 탐색하며, 수렴 오차는 전체
  reservoir가 아니라 가능한 phase transfer로 정규화한다. 온도 경계 도달은 phase
  소진 성공으로 바꾸지 않는다. CP04 진입/완료 또는 새로운 열역학 권한은 부여하지 않았다.
- 독립 310 K 응결·290 K 증발·250 K 승화 해, 큰 reservoir 적대시험, NaN/Inf/HUGE
  18개 입력 거부와 원본 bit 보존, 실제 소진/온도 한계 실패를 검사했다. 원래의 큰 ice
  reservoir 실패 fixture는 실제 내부 해가 있으므로 양성 회귀로 보존했다.
- 최초 root 실패 binary: `scratch/thermo_root.u1qoFD`; 수렴 scale 실패 binary:
  `scratch/thermo_scale_red.GXYZRf`. 최종 O2 PASS: `scratch/thermo_scale_final.Nh30M5`.
- 최종 pinned ifx 전체 suite exit 0: `scratch/cp01_oracle_verify.3zjrhqw0/receipt.json`
  (06:23:51–06:25:54 UTC). 추적 소스 19개와 toolchain 4개 실행 전후 동일.
  로그 SHA256: `0019d9be2624087a6873743f21fb0c5000cbbe07254b43113a9867c83f2c7dae`.
- 독립 검토와 코드 KG 갱신 완료. 기존 혼합상 순차정책, native enthalpy/energy,
  종별 transaction·EOS·balance outer coupling은 미폐합이다. 운영 원본은 변경하지 않았다.

### Standalone cloud-column transaction (2026-09-07)

- Added `saturation_adjust_column` in the existing physics module: explicit fixed
  dry mass, selected-cell work storage, one commit after all cells succeed, and
  signed vapor/liquid/ice kg plus sensible/latent J budgets. Inactive values remain
  opaque and bit-preserved. This is isolated preparation, not CP04/native approval.
- Independent tests cover three constructed liquid/ice equilibria with unequal
  dry masses, later-cell rollback, inactive NaN/Inf, shape/mass/RH rejection,
  weighted overflow, true exhaustion, and empty/all-inactive no-ops. An existing
  radar-only pipeline test now explicitly forbids implicit T/qv adjustment.
- Pinned ifx full suite exit 0, 06:38:33–06:40:38 UTC:
  `scratch/cp01_oracle_verify.3htdxw69/receipt.json`. All 21 tracked source/test
  files and four toolchain files were unchanged during execution. Log SHA256:
  `eb82c8bfbffdec7be3cfe86ee641b31f6dcd80189869ac8a690c940e0e52394a`.
  Focused O2 also passed: `scratch/thermo_column_o2.AFFX5b/test_thermo_column`.
- Independent review found no blocking issue. Code KG refreshed. Normal pipeline,
  EOS/mass refresh, precipitation phase transfer, external analysis increments,
  native total energy and operational authority remain outside this implementation.

### Pressure-analysis WPS vapor handoff capability (2026-09-07)

- User confirmed pressure-level analysis → WPS → real model-level initialization.
  Independent pressure-level work no longer waits for full native-source closure.
  Added optional dry-air `vapor_mixing_ratio` → `QV` to the existing WPS writer;
  no producer call, operational configuration, or authority was changed.
- Independent record tests cover asymmetric cells/levels, the 200100 Pa surface
  sentinel, skipped 1050 hPa, zero vapor, hotstart on/off, unchanged non-QV bytes,
  caller preservation, and shape/NaN/Inf/negative rejection before file creation
  or replacement. The pre-change legacy fixture remains byte-identical:
  `scratch/wps_vapor.YeSfMM/{before,after}/resolved-candidate.wps`.
- Full pinned-ifx suite exit 0 (07:12:21–07:14:28 UTC):
  `scratch/cp01_oracle_verify.84dsb7aj/receipt.json`; 26 scoped source/test files
  and four toolchain files unchanged. Log SHA256:
  `b161ae4584464034cce0976206bc9ba1ee8f48e3eb766a1e40f50d896e1fa662`.
  Focused O2 and independent review passed; retained O2 binary/output:
  `scratch/wps_vapor_o2.WZixRF/`. Code KG updated, semantic docs not rebuilt.
- The accessible KIM reference requires `use_sh_qv=true` for direct QV
  interpolation and gives SH precedence. Existing LAPSPREP calls remain
  RH-only. Producer coverage/basis, metgrid flags, real interpolation, KDM6
  number/volume fields and omega/w handoff remain open; no native PASS claimed.

### Automatic next step: actual LAPSPREP vapor caller (2026-09-07)

- Added default-off `wps_output_vapor` and connected both WPS output-path calls.
  Complete SH/MR_SFC/T3/T_SFC read coverage is required before pressure-level
  conversion; direct QV cannot use the legacy surface fallback. Corrected six
  field checks that incorrectly included the extra surface slab, and made the
  five required-field validation failures explicitly nonzero exits.
- Full pinned-ifx suite exit 0: `scratch/cp01_oracle_verify.uz_6z8yp/receipt.json`
  (07:29:04–07:31:08 UTC; 28 scoped files and four toolchain files unchanged).
  Actual caller + pinned NetCDF fixture: three positive paths and six negative
  paths pass; O0/O2 output bytes match. Evidence/binaries/logs:
  `scratch/lapsprep_vapor_tests.6MOlAm/receipt.json`. HEAD caller rejects the
  same valid strict fixture with `invalid_lt1_field` and no output.
- Independent review confirmed the slice and exit-status fixes. Grid/date and
  unused output formats are test stubs, not full KLAPS/native validation.
  Read-only 13 UTC metgrid inspection found RH, no QV/SH fields or their flags.
  The next integration task is explicit QV propagation/configuration, not an
  operational namelist change. Code KG refreshed; native/science gates unchanged.

### Pressure-analysis-first scheduling update (2026-09-07)

- User GO approves the checkpoint/checklist ordering revision, not a scientific
  or operational promotion. Earlier execution evidence above is unchanged.
- Next implementation: resolve the pressure-level mass/enthalpy contracts and
  connect the existing thermo block to the pressure-level candidate. Full
  metgrid/real validation expansion follows CP06-A; necessary input acquisition
  and small handoff contract tests may proceed earlier.
- CP01 remains IN_PROGRESS/NOT_RUN. CP06-A/B are internal milestones of CP06;
  FG1 still requires the full native result and all existing integration gates.

### Pressure-level thermo candidate transaction (2026-09-07)

- Added `saturation_adjust_pressure_state` to the existing column module. An
  explicit mask selects internal vapor/cloud-liquid/cloud-ice transfers with
  fixed pressure geometry and dry mass. All six water species must be usable
  on selected cells; rain/snow/graupel, winds and support remain unchanged.
- One candidate commit follows all selected columns and final canonical
  validation. The kg/J budget is independently recomputable from final float32
  values, with storage-roundoff gates separate from the float64 cell solve.
  Changed fields retain metadata and add only column-physics provenance.
- Independent constructed condensation/evaporation/sublimation, final RH and
  budget checks, each missing hydrometeor, invalid metadata/RH, inactive NaN,
  selected/empty no-ops and a true later-column solver rollback pass at O0/O2.
  Focused binaries: `scratch/pressure_thermo_final.40N9Dw/`.
- Final pinned-ifx full suite exit 0 (08:29:58–08:31:58 UTC):
  `scratch/cp01_oracle_verify.tvjy_51z/receipt.json`; 29 scoped source/test files
  and four toolchain files unchanged. Log SHA256:
  `53999607614a822fb03ff38a49aa4edd1774a6a061869c50827a4b1577713b85`.
  Earlier `scratch/cp01_oracle_verify.z93dgn38/` had exit 0 but its source
  snapshot changed while tests were refined; it is not final-snapshot evidence.
- This is a thermo-only research candidate, not normal SHADOW wiring or CP04
  completion. Copied omega targets/fall-speed diagnostics are not refreshed;
  a coupled caller must rebuild dependent physics before using the result.
  The existing sequential mixed-phase policy and reduced enthalpy are not a
  KDM6 thermodynamic/EOS or native total-energy contract. No external water,
  mass or energy analysis increments, operational writes or gate promotion.
- Next implementation boundary: settle pressure-level phase/enthalpy policy
  and dependent-state refresh, then connect the pressure coupled path. Full
  WPS/metgrid/real validation expansion still follows CP06-A.

### Shared pressure EOS and primary-phase root correction (2026-09-07)

- Moved dry-air density into the canonical state module and added moist-gas
  density. Omega/w and pressure-thickness trajectory/loading now use the same
  dry-mixing-ratio gas EOS; species flux still uses dry density. This replaces
  the separate approximate virtual temperature and dry-density pressure height.
  Condensate-loaded density, pressure tendency/advection and native EOS are not
  supplied by this gas-only path; no authority or normal thermo wiring changed.
- Independent EOS and absolute omega/w tests cover dry/typical/upper-bound
  vapor, invalid inputs and masked payloads. A nonzero tilted-trajectory oracle
  checks gas-density displacement separately from dry-density mass conversion.
  Focused O2: `scratch/pressure_eos_final.RWUqjG/`.
- Fixed the roundoff-triggered second phase pass: the primary reservoir must
  actually be exhausted before a secondary reservoir is used. At 85 kPa/RH 0.8,
  both cold and warm mixed-reservoir roots now preserve the unused phase and
  survive repeated adjustment. Cross-freezing/full mixed-phase closure remains
  open; no instantaneous KDM6 equilibration is claimed.
- Independent O0/O2 case logs: `scratch/phase_primary_cases.ifx{,_o2}.log`,
  identical SHA256 `398029b25bc2268ce422885fcfdb181cc868d081f7c1a90d6dd7d78200383efb`.
  Final focused column/pressure-state binaries: `scratch/thermo_eos_final.N6NxeM/`.
- KDM6 source review followed actual keyword bindings and init constants,
  correcting a same-name XLV0 interpretation before recording the contract.
  Reference HEAD `24e82afde6f9cb4b299ee330643253fbbc565a79` is not an
  authentication of the installed native binary. CP01/CP04/CP06 gates stay open.
- Final pinned-ifx full suite exit 0 (08:56:28–08:58:32 UTC):
  `scratch/cp01_oracle_verify.q_ho2x8t/receipt.json`; all 30 scoped source/test
  files and four toolchain files unchanged before/after execution. Log SHA256:
  `45b1a64d73900f47b4b4ffa494a5432591c271da654536c4b15d7ce3f0ac990b`.
  Earlier `scratch/cp01_oracle_verify.pa_cz77y/` had test exit 0 but a changed
  source snapshot; it is not final-snapshot evidence. This dirty-tree receipt
  is scoped regression evidence, not exact-HEAD CI or native/science acceptance.

### Explicit saturation surface and six-species phase transfer (2026-09-07)

- Saturation cell/column/pressure APIs now require explicit liquid/ice surface
  selection. Removed the initial-temperature selector and secondary fallback.
  Liquid permits supercooled crossings; ice rejects a required warm root.
  Existing callers are research tests, not normal-pipeline/operational callers.
- Added a prescribed six-species internal-transfer kernel and atomic pressure
  candidate. Final-mixture heat capacity and species enthalpies determine T
  together; no implicit freezing rule, external water increment or amount clip.
  Signed kg/J budgets use final float32 state and input dry mass, with storage
  roundoff gates and whole-candidate rollback. Constants/units/equations are in
  `NATIVE_MASS_FRAME_CONTRACT.md` under the six-species contract.
- Independent O0/O2 kernel tests and review:
  `scratch/water-phase-final-o0.vGKATB/build-and-test.log` and
  `scratch/water-phase-final-o2.sN5CE8/build-and-test.log`. These focused logs
  identify their source snapshot; the final full-suite receipt below supersedes
  them for the final integrated snapshot.
- The two thermodynamic conventions remain explicitly separate: the saturation
  test path uses reduced enthalpy; prescribed six-species transfers use mixture
  enthalpy. Neither is full KDM6 kinetics/native energy. Next: unify saturation
  with the mixture budget and rebuild dependent diagnostics for pressure-level
  coupling. Normal SHADOW wiring, CP04/CP06 full gates and promotion remain open.
- Final pinned-ifx full suite exit 0 (09:24:05–09:26:11 UTC):
  `scratch/cp01_oracle_verify.ubmm05zw/receipt.json`; all 32 scoped source/test
  files and four toolchain files unchanged. Log SHA256:
  `34123297082052cf13a735a7a597884c59fb65e2df6524a358b25f5c94182f29`.
  Final O2 column/column-thermo/pressure-thermo/pressure-transfer binaries:
  `scratch/phase_surface_final.AS6dje/`; O2 six-species kernel:
  `scratch/phase_final.Ql6trY/`. Independent review corrected the cold-ice test's
  transfer units and ensured temperature-limit rejection was not an overdraw
  false positive. Neither test fixture nor implementation grants science authority.

### Unified mixture saturation and pressure publication (2026-09-07)

- Replaced the reduced saturation law with the six-species mixture enthalpy
  kernel. Liquid/ice selection stays explicit; unchanged precipitation contributes
  heat capacity. Removed the old reduced diagnostic and duplicate pressure
  publication path. Both pressure APIs now return `water_phase_budget`.
- Saturation is checked again after the finite transfer and after final float32
  storage. Vapor/temperature limits are not condensate exhaustion; invalid or
  infeasible selected cells reject the entire candidate with empty budgets.
- Independent scalar/column O0/O2 oracles and math review checked the finite
  enthalpy equation, monotone bracket, freezing crossings and cap rejection.
  Pressure tests include nonzero precipitation heat capacity, final kg/J budgets,
  provenance, inactive missing values, malformed support and late solver rollback.
  Parent review corrected false-positive thermal/domain fixtures before acceptance.
- Final focused O2 pressure/scalar tests: `scratch/mixture-pressure-o2.6i8cVe/`.
  O2 prescribed/saturation mixture and pressure-transfer tests:
  `scratch/mixture-final.BC0EXX/`. Column O0/O2 logs:
  `scratch/mixture_scalar_tests_latest.MIoSvW/` (the full-suite receipt below
  additionally covers the final fixture assertions).
- Final pinned-ifx full suite exit 0 (09:54:32–09:56:39 UTC):
  `scratch/cp01_oracle_verify.ym3q0dbc/receipt.json`; all 32 scoped source/test
  files and four toolchain files unchanged. Log SHA256:
  `f3cd64ff208d72ed8c615f0338530841272250c1ffbdeb46502eb96c7c987e86`.
- This is isolated pressure thermodynamics, not exact-HEAD CI, native KDM6
  kinetics/total energy, a coupled forecast, or CP01/CP04/CP06 completion.
  Next implementation: refresh dependent diagnostics and connect the pressure
  candidate to bounded coupled iteration without relaxing authority/pristine-input
  contracts. Native handoff and science/operational gates remain open.

### Explicit thermo SHADOW route and diagnostic refresh (2026-09-07)

- Added an explicit support/surface/RH request to the existing column/pipeline
  API. Hydrometeors are published once, then saturation adjusts T/vapor/cloud
  species and diagnostics are rebuilt using final stored thermodynamics. Original
  echo/reconstruction lineage and authorized targets are retained.
- Internal six-species kg/J budgets are separate from the pre-thermo radar
  increment diagnostic. Column or later localization/balance failure rolls back
  the candidate and accepted budget. OFF and operational input identity remain
  unchanged; absent/empty requests do not implicitly enable thermo. Generated
  T/vapor cannot bypass the pristine-background guard.
- Independent column O0/O2 tests include final-EOS loading, terminal-speed
  refresh, no duplicated precipitation and late-cell rollback:
  `scratch/column_thermo_test.SpmgLU/`,
  `scratch/column_thermo_test_o2.RyIlzl/`. Pipeline O2:
  `scratch/thermo-pipeline-o2.jDHeTQ/`; thermo-only changes grant no wind authority.
- Final pinned-ifx full suite exit 0 (10:13:56–10:16:08 UTC):
  `scratch/cp01_oracle_verify.fevv9ox4/receipt.json`; all 33 scoped source/test
  files and four toolchain files unchanged. Log SHA256:
  `6bd6a2bd3487766db6e8622b84ce4d19a9c509808ba327f07e4656f892f68ae9`.
- This closes the opt-in single-pass implementation/test step only. Transport
  still uses the original state; pressure/mass coupling and bounded outer
  convergence remain next. No full native writer/model run, exact-HEAD release,
  CP01/CP04/CP06 closure, science authority or operational promotion is claimed.

### Pressure-thermo diagnostic serialization (2026-09-07)

- Accepted, nonempty explicit thermo requests now persist schema 6 diagnostics:
  original/final temperature and six water species, field metadata, request
  support/surface/RH, candidate dry mass and signed kg/J budgets. Default schema 5
  and operational identity remain unchanged. Writer replay checks do not relax
  canonical equality; an independent Python verifier recomputes stored-array
  mass, water, enthalpy and saturation without calling the production solver.
- Independent review narrowed the no-echo exception to requested T/vapor/cloud
  changes only. Unrelated precipitation, target metadata and support changes still
  reject. Mutation tests also exposed and fixed valid-but-QC-rejected metadata
  outside thermo support.
- Liquid/ice and no-echo writer tests passed with pinned ifx O0/O2; retained O2
  artifact: `scratch/thermo_shadow_io_o2.v4hTWf/thermo-shadow.nc`. The independent
  round-trip and all 28 corrupted-file cases passed and now run in the I/O suite.
- Final full suite exit 0 (10:45:54–10:48:05 UTC):
  `scratch/cp01_oracle_verify.x9h44ayx/receipt.json`; all 37 scoped source/test
  files and four toolchain files unchanged. Log SHA256:
  `7cfc80ff7c023b0ccdf1fc59997a9055f2c46222d4f88e8098b45e05e6f1d3b9`.
- This closes diagnostic persistence, not a full native writer, outer convergence,
  exact-HEAD release or science gate. Next: pressure/mass analysis-increment
  accounting and coupled convergence; WPS/real handoff remains separately open.

### Pressure-fixed analysis mass budget (2026-09-07)

- Added pre-thermo six-species mass accounting and dry-mass redistribution to
  the existing column/pipeline result. A shared represented-species accessor
  keeps its denominator consistent with canonical mass refresh. Accounted and
  incomplete cell counts prevent missing condensate from implying measured zero;
  global and maximum cell residuals are separate diagnostics.
- Independent raw-field tests recompute dry mass from pressure geometry, check
  the mass-increment decomposition, unchanged vapor ratio with changed vapor
  mass, incomplete coverage, OFF/no-observation, late rollback and thermo
  separation. Focused pinned-ifx O0/O2 tests passed.
- Full pinned-ifx suite exit 0 (11:03:31–11:05:42 UTC):
  `scratch/cp01_oracle_verify.n189hwxk/receipt.json`; 37 scoped source/test files
  and four toolchain files unchanged. Log SHA256:
  `f8f51e4a015f166a17898df98f1ec43628ba44b45a76739e537d5f9d527e80d4`.
- This is an in-memory represented-analysis ledger, not transport, native dry
  mass conservation or total energy. Next: persist/recheck this ledger and add
  external enthalpy accounting before pressure/native and outer-loop closure.
  CP01/CP04/CP06 and science/operational gates remain open.

### External analysis enthalpy increment (2026-09-07)

- The pre-thermo pressure analysis budget now includes signed extensive mixture
  enthalpy change, including dry-air and vapor mass changes. It is not latent
  heating or native total energy. Overflow checks precede weighted products;
  comparison tolerances use unsubtracted extensive terms, not the small net change.
- Independent warm-rain/cold ice-snow oracles, empty/rollback budgets and
  final-minus-background = analysis increment + internal thermo residual pass.
  Pinned-ifx O0/O2 binaries: `scratch/pipeline-enthalpy-o0-final.HQzwFQ/` and
  `scratch/pipeline-enthalpy-o2-final.d2UfXN/`.
- Full suite exit 0 (11:16:11–11:18:22 UTC):
  `scratch/cp01_oracle_verify.zb37zlo6/receipt.json`; 37 scoped source/test and
  four toolchain files unchanged. Log SHA256:
  `34fad91b68349c279991f2969d0993891b4b5e341f447c0c5e183c0e911a1e03`.
- Next: persist and independently recheck both analysis ledgers. Native mass,
  full energy, outer convergence and CP01/CP04/CP06/science/operations remain open.

### Persisted analysis and phase ledgers (2026-09-07)

- Explicit nonempty thermo diagnostics now use schema 7 and persist the
  pre-thermo six-species analysis mass/enthalpy ledger separately from internal
  phase budgets. Writer replay rejects inconsistent budgets; the Python verifier
  independently reconstructs them from stored fields and pressure geometry.
  Default schema 5 is unchanged; legacy schema 6 remains readable without an
  analysis-ledger verification claim. All remain diagnostic proposals only.
- Pinned-ifx O0/O2 writer/readback and forged-result tests passed. Independent
  round-trip and 63 file-mutation cases passed; a retained genuine schema 6
  artifact also validated with `analysis_ledger_validated=false`.
- Full suite exit 0 (11:38:45–11:40:59 UTC):
  `scratch/cp01_oracle_verify.qnofxme6/receipt.json`; all 37 scoped source/test
  files and four toolchain files unchanged. Log SHA256:
  `19a407e070106bf17312846f98f896e85cde5ac8f41bb6ad1df78995cfc92fd7`.
- Retained schema 7 artifact:
  `scratch/real_shadow_io_analysis_budget_o2/thermo-shadow.nc`, SHA256
  `4c0dffcf8fd04b52df6bcc4875f2ad3bfcaad8c9fd240779348589d8dcbd127b`.
- Next: pressure/mass coupling and bounded outer consistency of the pressure-level
  analysis, followed by WPS/real native handoff verification. This is not native
  conservation, total energy, full-product closure or operational promotion.

### Bounded pressure-fixed feedback (2026-09-07)

- Added immutable-background/evaluation-state separation to column physics and
  an opt-in bounded pipeline fixed point (`maximum_outer_iterations=2..32`).
  Each fresh radar/thermo/balance proposal uses the preceding T/vapor/u/v/omega
  for coefficient evaluation. Observation metadata, pressure geometry and the
  analysis-budget anchor stay original; neither precipitation nor wind increments
  accumulate between trials. Default 1 remains the existing single pass.
- The thermo/radar fixture converges in three trials and differs from single-pass
  precipitation. A fixed two-trial cap rejects with complete candidate/budget
  rollback. Explicit production replay reproduces final feedback and the anchored
  budget; a separate density formula checks retrieval response. These are not an
  independent full coupled solver oracle or real-observation science validation.
- Focused column and pipeline ifx O0/O2 tests pass, including changed observations,
  geometry, previous-candidate reuse and contradictory cloud-QC feedback. Existing
  diagnostic schemas reject outer results rather than mislabel iteration lineage.
- Full suite exit 0 (12:00:14–12:02:29 UTC):
  `scratch/cp01_oracle_verify.g098gfrg/receipt.json`; all 37 scoped source/test
  files and four toolchain files unchanged. Log SHA256:
  `210e710dbf6d25a780b4d8326dc264184f85933ae6dc28a9334e7637534a234d`.
- Exact stored-value convergence is conservative; undamped cycles/exhaustion fail.
  Native PSFC/geopotential/dry-mass closure, physical rates, serialized outer
  lineage, WPS/real final-state verification and science/operations remain open.

### Actual LAPSPREP dry-air denominator (2026-09-07)

- Fixed hotstart concentration conversion to use dry-air density rather than
  approximate moist-gas density. The later omega/w approximation uses moist-gas
  density separately. Host Rd/gravity are retained; native constants are not
  assumed equal. Invalid hotstart pressure/T/vapor rejects before conversion.
- Actual `lapsprep.f90` caller, with fixture dependencies and real NetCDF, passes
  O0/O2 hotstart checks for all five nonzero species, unchanged TT and direct QV.
  Independent Python algebra distinguishes the old denominator. Deliberately
  large synthetic humidity/concentrations are sensitivity tests, not atmospheric
  validation. Existing coldstart and malformed-input checks remain passing.
- Added this caller test to the full suite. Exit 0 (12:20:33–12:22:57 UTC):
  `scratch/cp01_oracle_verify.cutf32mo/receipt.json`; 41 scoped source/test files
  and four toolchain files unchanged. Log SHA256:
  `14f47cfda0b4e331a515a63794270af63159083c89fbb398eb2a6867838ca3fa`.
- Checkpoint order remains pressure analysis first, native handoff second.
  The inspected WPS path lacks vertical input; native mu-coupled eta-dot must
  not be substituted for pressure omega. CP01/CP06-B now explicitly require
  the actual native reconstruction contract. No native source was modified.
- Next implementation: persist/recheck bounded pressure-analysis iteration
  lineage before accepting an outer result as a stored diagnostic. Actual real
  executable/source binding and native/science/operational closure remain open.

### Stored bounded-iteration diagnostics (2026-09-07)

- Accepted explicit thermo outer runs now write schema 8, with original/final
  states, anchored analysis/phase budgets, cap/count and five-component per-trial
  maximum changes. The writer replays the bounded producer from immutable input
  and checks candidate/count/history before opening output. Default schema 5 and
  single-pass schema 7 remain unchanged; legacy schema 6 remains readable.
- The three-trial fixture has nonzero prior changes and an exactly zero final
  trial. Count, negative/nonfinite history, unused tail, nonzero final residual
  and candidate tampering are rejected. Cap failure retains measured diagnostic
  history but rolls back candidate, budgets and accepted thermo support.
- O0/O2 real writer tests pass with Python round-trip and 63 schema-7 / 74
  schema-8 mutations per build. A genuine retained schema-6 file also validates
  without analysis-ledger or outer-lineage claims.
- Full suite exit 0 (12:35:16–12:37:57 UTC):
  `scratch/cp01_oracle_verify.cbp5hy5u/receipt.json`; all 41 scoped source/test
  and four toolchain files unchanged. Log SHA256:
  `f3309f8a99fec7309e04d58332e2d7c7dbf41e2e525686680561e86223c7594c`.
- Python's outer scope is metadata only, not a replay of the complete map;
  `outer_fixed_point_independently_validated=false`. Next: an independent final
  radar/trajectory/balance-map oracle with complete input/config provenance.
  This step is durable diagnostic progress, not CP06-A/native/science promotion.

### Independent radar reconstruction reference (2026-09-07)

- Added a separate Python reconstruction/transport implementation and schema-8
  original phase/config inputs. Stored rain/snow/graupel, all eight throughput
  ledger terms and substep count are recomputed, including replacement versus
  background-addition rules. Older schema 8 remains readable without this claim;
  independent full outer fixed-point validation remains false.
- Pinned ifx O0/O2: nine positive kernel cases and three rejection cases agree
  with the reference without modifying inputs. Writer checks pass with 63
  schema-7 and 78 schema-8 mutations per build, including balanced ledger edits.
- The uniform-wind substep case exposes an open defect: requested displacement
  is 2.000000 cells but deposited-rate centroid displacement is 0.806255 cells
  in both builds. Source-only displacement arrays are reused after scattering
  into initially empty cells. Reference agreement reproduces this behavior;
  it does not pass physical trajectory accuracy. Next implementation priority
  is this pressure-analysis transport issue, before CP06-B native expansion.
- Full suite exit 0, 13:03:12–13:06:01 UTC:
  `scratch/cp01_oracle_verify.22e0nsaq/receipt.json`; all 45 scoped source/test
  and four toolchain files unchanged. Log SHA256:
  `95e1c03eb24b7fd751071f788939f05b5ad6d5f6d996411364e7027e729dcfa8`.
- This is dirty-worktree execution evidence, not an exact-HEAD release receipt.
  Interface throughput remains kg/s, not finite-time global transport in kg.
  CP06-A/B, native initialization, science and promotion remain open.

### Source-resolved layer trajectories (2026-09-07)

- Replaced repeated grid remapping with continuous-position stepping for each
  frozen-source layer segment, followed by one bilinear endpoint deposition.
  Crossing sources retain distinct displacement and reflectivity until arrival.
  Destination masks, throughput categories and transactional publication remain
  unchanged. Within-layer shear/phase evolution and finite-time transport are
  not implemented by this approximation.
- Independent Python uses the analytic endpoint. O0/O2 pass 11 valid / three
  rejected cases, including full endpoint footprints, both centroids, same-phase
  crossing sources, three/four-substep equivalence and partial boundary exit with
  complementary observation blocking. New footprint assertions reject both
  retained old outputs in `scratch/radar_reference.MKLvkV/`.
- Schema-8 reconstruction contract is now v2; v1 is explicitly rejected rather
  than reinterpreted. Genuine schema 8 without the group stays readable without
  an independent-radar claim. O0/O2 writer checks pass 63 schema-7 / 79 schema-8
  mutations, including simultaneous +1 input/deposited ledger tampering.
- Full suite exit 0, 13:19:58–13:23:23 UTC:
  `scratch/cp01_oracle_verify.qdh54s96/receipt.json`; 45 scoped source/test files
  and four toolchain files unchanged. Log SHA256:
  `36d64c250342eb05efad5c8806ec3e6a98cb7afaf1d492d72a70a06f5f06c308`.
- This closes the reproduced substep under-travel defect under the stated
  approximation, not full outer-map, actual trajectory, native or science gates.

### Pressure-target uncertainty (2026-09-08)

- Canonical schema 4 carries a finite positive pressure-omega standard deviation.
  Observational proposal and inverse metric use B/(B+R) and BR/(B+R), with
  R=sigma squared. Missing error grants no target authority; malformed error
  rejects atomically. Manufactured tests retain their separate authority.
- Pinned ifx tests cover exact posterior coefficients, error-dependent response,
  missing/invalid error, identity and rollback. O0/O2 diagnostic checks pass
  78 schema-7 and 94 schema-8 mutations. Large-grid execution exposed domain
  temporary-memory failures; scalar sigma checks and allocated mask buffers
  fixed them without compiler-profile or stack-limit changes.
- Full suite exit 0, 2026-09-07 23:29:20–23:32:15 UTC:
  `scratch/cp01_oracle_verify.q1l0go2n/receipt.json`; 48 scoped source/test files
  and four toolchain files unchanged. Log SHA256:
  `4bbe235d2bd64ef9324d22884e2e7347f7b7164979bc61dd1de045735132893f`.
- Physical-boundary balance and unused-sigma serialization are separate tests.
  The copied-only writer still rejects physical boundaries; nonzero observational
  candidate publication requires original-target lineage and an explicit boundary
  extension next. No provenance is relabeled after a pipeline run to bypass it.
  This is dirty-worktree engineering evidence, not actual error calibration,
  CP06-A/B closure, native/science evidence or promotion approval.

### Opt-in physical-boundary pressure candidate (2026-09-08)

- Added explicit pressure-candidate diagnostics with immutable original-target
  arrays and unchanged physical boundary provenance. Default radar-only writing
  remains copied-only. Producer replay checks candidate identity; independent
  Python checks stored state/operator residuals and existing acceptance gates.
- The single signed target is rejected; its compensating same-grid opposite
  target forms a represented interior-u divergence mode and passes with the same
  sigma=0.5 Pa/s and unchanged gates. Earlier inactive-beta speculation was
  refuted: beta=0.015625 exceeds the 0.001 threshold. The rejection is not proof
  of missing support, and the paired fixture does not close arbitrary-target fit.
- O0/O2 nonzero candidate serialization and mutation checks pass, including
  target edits concealed by hydrometeor changes, physical boundary finite-flux
  tampering, residual changes and false authority flags. Existing thermo checks
  retain 78 schema-7 / 94 schema-8 passing mutations.
- Full suite exit 0, 2026-09-07 23:54:36–23:57:36 UTC:
  `scratch/cp01_oracle_verify.1gh6oz64/receipt.json`; 49 scoped source/test files
  and four toolchain files unchanged. Log SHA256:
  `bf91cccd47d2667d964cf97cbc98a324c3ba63ac12795500ba3e96a8bdf42d52`.
- Dirty-worktree engineering evidence only. Joint thermo/dynamic outer-loop
  round-trip, actual observation calibration, native handoff, science and
  promotion remain open. No operational producer or publisher was changed.

### Joint thermo/dynamic pressure candidate (2026-09-08)

- Added schema-7/8 fixtures with simultaneous T/vapor/cloud-water and nonzero
  wind changes; outer mode converges beyond its first trial. O0/O2 round-trip
  checks cover thermo/analysis budgets, immutable targets, outer lineage and
  false authority/history mutations. Operational state remains identical.
- Review identified that producer replay checked final state/history but not
  numerical receipts. It now compares every column/balance numerical component.
  Balanced fabricated flux and forged solver iteration receipts are rejected
  before file creation in both joint paths. No acceptance threshold changed.
- Full suite exit 0, 2026-09-08 00:11:29–00:14:36 UTC:
  `scratch/cp01_oracle_verify.1mwfekn4/receipt.json`; 49 scoped source/test files
  and four toolchain files unchanged. Log SHA256:
  `adf774b93db4eafa152d22aa6f80ca7baa53921410af6a662ca79d309705406b`.
- This closes the scoped joint diagnostic round-trip, not CP06-A/B or FG1.
  Five-field pressure-fixed feedback is not full species/metric coupling;
  independent full nonlinear-map verification, actual observation calibration,
  native handoff and science/promotion remain open. Separate Barnes completion
  and operational boundaries are unchanged.

### Represented dry-air advective flux (2026-09-08)

- Added `state_dry_air_mass_flux_divergence`: kg/s signed dry outflow on
  existing pressure faces, interpolating `f_d * velocity`. Pressure D/G and
  projection metric are unchanged; boundary composition uses the adjacent cell.
  No sedimentation or invented analysis-to-time source is applied to dry air.
- O0/O2 tests cover partial cells, uniform fraction scaling, varying vapor and
  wind, analytic lateral/top/bottom budgets, condensate dependence, stale mass
  rejection and metric identity. Fixed the fixture's nonzero beta below terrain;
  canonical validation was not weakened. Zero carrier motion gives no dry flux.
- Full suite exit 0, 2026-09-08 00:26:39–00:29:52 UTC:
  `scratch/cp01_oracle_verify.k95f_68c/receipt.json`; 49 scoped source/test files
  and four toolchain files unchanged. Log SHA256:
  `1863cfd6afc13aa7498b979411dd8abb3d89a83629ea4d8940a7e43361cf1724`.
- This supplies only `D F_d`, not mass tendency or full dry continuity. Next
  integration must retain that distinction when connecting candidate diagnostics
  and physical tendencies. CP06-A/B, native/science and promotion remain open.

### Persisted dry-air flux and independent replay (2026-09-08)

- Joint pressure-candidate schemas 7/8 now store background/candidate `D F_d`
  in kg/s, with explicit adjacent-cell boundary composition and no mass-tendency
  claim. Python independently reconstructs dense pressure-overlap faces.
- Initial full-suite attempt `scratch/cp01_oracle_verify.xae30zb3/receipt.json`
  failed `independent background_dry_air_flux_divergence` and
  `independent candidate_dry_air_flux_divergence`. Retained artifacts in
  `scratch/dry_io_probe.by4I64/` showed a maximum 4.6575e-9 kg/s difference:
  Fortran sums flux/mass then multiplies by mass, whereas Python sums kg/s.
  The affected donor throughput was about 4.55e7 kg/s. Added an operation-count
  float64 bound on absolute donor terms, not an empirically enlarged constant.
- Analytic partial-face, high-throughflow cancellation, zero-flow, historical
  no-extension, +1 kg/s/NaN/missing-field/false-authority tests pass. Independent
  luna/high review confirmed signs, masks and the roundoff-bound construction.
- Full suite exit 0, 2026-09-08 00:55:47–00:59:03 UTC:
  `scratch/cp01_oracle_verify.ptn1q78x/receipt.json`; 49 scoped source/test files
  and four toolchain files unchanged. Log SHA256:
  `c0fe7b79f39d76268082fe0d8e43f5038bd07863bfc998eede01d58565d06323`.
- Dirty-worktree engineering evidence only. This does not supply physical dry
  mass tendency, pressure/geopotential reconstruction, native handoff or science
  acceptance. Next physical work must distinguish total-mass pressure analysis
  from host dry-mass coordinates; a generic hydrostatic column formula alone
  cannot certify the native adapter. OFF/SHADOW and Barnes boundaries unchanged.

### Pressure-level hydrostatic increment block (2026-09-08)

- Added the pure `hydrostatic_geopotential_increment` column block. It integrates
  the change in full-mixture `p/rho` over log pressure, with zero increment at
  the lowest represented center and atomic output rollback. No absolute
  background rebalance, native dry-pressure substitution or pipeline activation.
- Independent luna/high tests cover dry/moist heating, condensate loading,
  exact no-change, log-pressure-linear analytic solutions, second-order mesh
  convergence, existing phase-transfer outputs, bad inputs/shapes and one-level
  anchoring. Independent review confirms the sign, mixture convention and scope.
- Full pinned-ifx suite exit 0, 2026-09-08 01:09:24–01:12:47 UTC; O0/O2
  hydrostatic tests both pass. Receipt:
  `scratch/cp01_oracle_verify.vpj9t5_u/receipt.json`; 50 scoped source/test files
  and four toolchain files unchanged. Log SHA256:
  `bb1a642efb5a1d2476e9e975af0a2e37c743dc2f3ddfb7bc81cfcc9af157cfe7`.
- Candidate attachment still needs explicit geopotential support and anchor
  inputs; hydrometeor support is not that authority. Surface/topography retention,
  final Phi serialization and WPS/real coupling remain next implementation work.
  CP01/CP06-A/B and FG1–FG3 are not completed by this standalone block.

### Explicit pressure-candidate geopotential coupling (2026-09-08)

- Added an atomic state adapter and explicit pipeline support/reference arrays.
  Thermo precedes Phi, which precedes localized balance. Each outer trial starts
  from original Phi; the lowest represented center remains fixed. Mathematical
  increments outside selected-column support are rejected, not clipped.
- Tests cover stored float32 Phi, complete mixture/provenance, pressure geometry,
  support/anchor errors, repeated correction, no new wind authority, OFF identity,
  bounded outer determinism, downstream failure/cap rollback and request cleanup.
  Review prompted two regressions: empty support still checks fixed geometry;
  unchanged Phi values cannot conceal altered reference quality/source.
- The existing writer explicitly rejects these requests and hidden Phi changes
  before file creation; this prevents an incomplete diagnostic from dropping Phi.
- Final pinned-ifx suite exit 0, 2026-09-08 01:30:41–01:34:19 UTC, including
  O0/O2 state-adapter tests: `scratch/cp01_oracle_verify.9bemayfz/receipt.json`.
  51 scoped source/test and four toolchain files unchanged. Log SHA256:
  `4cce3496661a85147472c2662aabeda931518c8f9e3525cefc155b880c81b227`.
- Next: serialize original/final Phi plus support/reference metadata and replay
  independently. Physical surface anchoring, full energy/dry-mass closure and
  WPS/real/native/science acceptance remain open. No operational promotion.

## Pressure-geopotential serialization and independent replay — 2026-09-08

- Schemas 7/8 pressure candidates now persist original/final Phi, full field
  metadata, explicit support and lowest-center reference indices. Producer
  replay runs before file creation; absent requests still require unchanged Phi.
- Python independently integrates saved mixture specific volume in log pressure,
  checking float32 results, selected-column coverage, support, monotonicity,
  references and provenance. Phi propagates above a middle-level thermo cell in
  a different column from the radar target; its changes enter overall evidence,
  not the column-physics mask. Historical diagnostics gain no Phi validation.
- Regression review fixed optional-stage compatibility, stage-mask conflation,
  manufactured Phi provenance and contradictory reference-index attributes.
  Missing/altered fields, metadata, support, references and source bits reject.
- Final full pinned-ifx suite exit 0, 2026-09-08 02:02:34–02:06:26 UTC:
  `scratch/cp01_oracle_verify.a7jckmut/receipt.json`. O0/O2 writer and independent
  replay/mutation tests passed; 52 scoped source/test files and four toolchain
  files unchanged, independently rehashed after completion. Log SHA256:
  `57362380fce4de830bdb6df05faf2d175f251ce387bbbaa28ac2397ee6301f8c`.
- This is dirty-worktree engineering evidence, not exact-HEAD release or native
  acceptance. Next is immutable-original versus final-candidate residual
  assessment: existing geostrophic stage metrics already start with adjusted
  Phi. Physical surface anchoring, energy/native mass closure, WPS/real and
  FG1–FG3 acceptance remain open. No operational promotion.

## Original/final pressure-geostrophic diagnostics — 2026-09-08

- Added one original/final residual assessment using fixed geometry and the
  balance/Phi support union plus a same-level cross halo. The writer persists
  both RMS values and support; Python independently recomputes them. Existing
  stage metrics remain separate, and no new science acceptance threshold applies.
- Analytic, O0/O2, historical-file and mutation tests cover support, stored
  metrics and false science claims. Review reproduced and fixed logical-operator
  precedence in hidden-change detection and quiet-NaN traps outside the stencil.
  Value identity is bitwise; range checks select valid values before comparison.
- Final full pinned-ifx suite exit 0, 2026-09-08 02:29:14–02:33:20 UTC:
  `scratch/cp01_oracle_verify.3dd1q15g/receipt.json`. All 54 scoped source/test
  and four toolchain hashes were unchanged and independently rechecked after
  completion. Log SHA256:
  `8eb96483da9a1b693a8ed1b152aa7a6cf413a63d2ed10675eef164c30951cd9e`.
- Dirty-worktree engineering evidence only. Next implementation candidate is
  the isolated pressure-candidate-to-WPS mapping, with explicit ancillary
  surface/SLP inputs rather than fabricated canonical fields. Native source,
  surface anchoring, mass/energy and FG1–FG3 science/acceptance remain open.

## Isolated pressure-candidate WPS mapping — 2026-09-08

- Added an array-only adapter with exact pressure-coordinate mapping in both
  orders, explicit matching wind declaration, direct dry-air water ratios and
  Phi/9.80665 height. Surface TT/PSFC map from the candidate; supplied ancillary
  and subterranean slabs remain unchanged. Unsupported writer-skipped levels,
  incomplete/degraded candidates and malformed inputs reject atomically.
- O0/O2 tests feed the mapped arrays to the existing WPS writer. Independent
  Python checks verify all affected records, units, dimensions, pressure order,
  surface data and subterranean fills. Retained RH follows the producer's
  0–200 percent range and is not recomputed or treated as authoritative.
- Initial full run `scratch/cp01_oracle_verify.fv4oi9a2/receipt.json` failed
  at a full-grid PACK range check. Scalar loops now skip invalid cells without
  large stack temporaries; missing-cell NaNs and real-grid regression both pass.
- Full pinned-ifx suite PASS, 02:55:39–02:59:48 UTC:
  `scratch/cp01_oracle_verify.8mzjkyni/receipt.json`, log SHA256
  `363521074d06843a014811f8bbbdcb4ffe9c6566650283ad7e5117c456ab74b1`.
  The subsequent RH-only adapter/test adjustment has a separate final O0/O2
  PASS, 03:00:23–03:00:27 UTC: `scratch/cp01_oracle_verify.a_ky9whg/receipt.json`,
  log SHA256 `588d2b9ac2239dbaad8e9ed79e1bda868905f013e2c1fb1b99695115fc6a08ec`.
  Each run retained 58 source/test and four toolchain hashes unchanged; final
  rehashing confirmed only the adapter and its test differ between these runs.
  The full-suite result is not relabeled as a full-suite run of the later source.
- A subagent reported an exploratory GNU compile; it is excluded from approved
  evidence. No GNU fallback was added. Evidence above uses pinned ifx only.
- Operational callers remain unchanged. Next is actual producer-to-writer
  integration with time/grid/frame/ancillary provenance, not another numerical
  diagnostic wrapper. Real/native and FG1–FG3 acceptance remain open.

### Live pipeline candidate to WPS — 2026-09-08

- The controlled thermo/Phi pipeline now passes its in-memory candidate to the
  existing mapper and actual WPS writer. The same invocation writes its physics
  diagnostic; no diagnostic-to-canonical reconstruction or authority upgrade.
- Independent comparison checks T, u/v, vapor, five species and Phi/g at every
  pressure level, nonzero T/QV/HGT response, exact time, retained records and
  seven corruptions. The existing verifier separately recomputes the physics.
- Pinned-ifx focused I/O suite PASS at O0/O2, including real-reader negative
  tests: `scratch/cp01_oracle_verify.ny_guexg/receipt.json`, UTC
  03:21:23–03:23:56, exit 0. All 59 captured source/test files and four toolchain
  files were unchanged; current hashes and log were independently rechecked.
  Log SHA256: `e64c4e2cf5ca4535f12eebd9284fd48477dde88a29750050d685f2abd5c846d5`.
  This is focused dirty-worktree evidence, not a new full-suite/exact-HEAD PASS.
- Review corrected fixture timestamp and pressure-unit assumptions. Legacy
  SNOWCOVR serialization is commented out, so no snow-cover file claim is made.
- Real LT1/LQ3/LCO/LSX production and same-generation ancillary binding remain
  open. The real 22-level inventory includes 1100/1050 hPa; its explicit level
  selection and coverage must be resolved before using the current mapper
  (which rejects writer-skipped levels). Full LAPSPREP caller, metgrid/real,
  native and science acceptance are still open; no operational path changed.

### Full 22-level WPS selection — 2026-09-08

- The mapper now accepts the full 1100…50 hPa inventory when writer-skipped
  levels contain no represented candidate cells. Arrays/domain are not reduced;
  any active skipped cell rejects the candidate and preserves the output.
- Original 3-level regressions remain. A separate 22-level case verifies all
  20 emitted pressure levels plus surface in both orders. Canonically valid
  PSFC 105000/106000/110000 Pa cases explicitly fail on active skipped levels.
- Focused pinned-ifx O0/O2 PASS: `scratch/cp01_oracle_verify.trcn1l6u/receipt.json`,
  03:37:00–03:37:04 UTC, exit 0. Current 59 source/test and four toolchain hashes
  were rechecked. Log SHA256:
  `00f302920a233bfeab25187b94abe34d85653b9853d6b85c497fcdc3ef3465c9`.
- This closes the controlled level-selection gap, not real producer lineage,
  physical adequacy of native interpolation or FG1. Legacy writer unchanged;
  actual source/ancillary binding and full LAPSPREP/native integration remain.

### Original temperature producer source build — 2026-09-08

- `tools/build_upstream_temperature.sh` builds 210 original C/Fortran source
  units in fresh scratch with pinned ifx/icx, fixed 72-column source, original
  COMMON alignment, explicit preprocessing and pinned NetCDF archives. No old
  KLAPS object/archive is linked; no producer is run or installed.
- Final build: `scratch/upstream_temperature_build.u18PHK/`, exit 0,
  `BUILD_AND_LINK_PASS; NOT_EXECUTED; NOT_GENERATION_READY`. Input/header/compiler
  and observed runtime hashes were rechecked. `ldd -r` found no missing library
  or undefined symbol in the prepared Intel environment.
- Executable SHA256: `faee73eba003d10473bcc9fcad1e8b93112dfec1e02e82d9f01a4cc87037872f`.
  Build log SHA256: `b52e686e8add573f43818d2197692031f6373e4e8fe544db80f0758887c566e5`.
- Legacy C warnings remain (201 warning lines). Link success does not validate
  those interfaces or scientific behavior. Next: isolated input/failure behavior
  and source/runtime binding into the replay path. LT1 generation, remaining
  producers, full KLAPS/native and science gates are not closed by this build.

### Temperature producer failure status — 2026-09-08

- Added `src/temp/puttmpanal_drv.f` as an isolated status-driver overlay;
  original sources remain unchanged. Failed time/dimensions/LT1 return exit 1.
  LT1 status is initialized on all paths and is not overwritten by optional
  PBL failures; failed PBL height conversion prevents the PBL writer call.
- Fresh 210-unit ifx/icx build/link PASS: `scratch/upstream_temperature_build.8nzFWp/`.
  Executable SHA256: `3a91f524c9f31731d8fb59de2e94654baba34c65a346ff03a2c1b1fe5a384131`.
  Build log SHA256: `148aec8528a5b8a9cba2802a9a474382050bdbb643515deb586c8ac2ce038f7a`.
  Input/runtime hashes rechecked; the 201 legacy C warning lines remain.
- Controlled stub O0/O2 PASS: `scratch/upstream_temperature_status.vpYl8l/`.
  Each variant checks eight main exit paths and nine internal status/call-count
  cases. Source/compiler/include/runner hashes are checked before/after.
  The focused runner is included in `run_unit_tests.sh`; the full suite was not
  rerun for this change. Independent AI source review found no status defect.
- Strict `bwrap --unshare-all` probe failed with `RTM_NEWADDR: Operation not
  permitted`; no real producer was executed and isolation was not weakened.
  Stub tests do not prove LT1 file contents, input freshness, actual generation,
  full native handoff or science acceptance. Those gates remain open.

### Surface producer source build — 2026-09-08

- Renamed the temperature-only builder to `tools/build_upstream_producer.sh`;
  use `bash tools/build_upstream_producer.sh temperature` or `surface`.
  The historical temperature receipts above retain their original script name.
  One explicit producer selection shares the compiler/dependency checks and
  scratch-only build path; there is no execution or installation option.
- Surface: 233 source units, `scratch/upstream_surface_build.O3qHQI/`, exit 0.
  Executable SHA256: `9deec5fe4c0ee284a71b40ea55d7d3e269f0b92d5a742c6ab39349d4a55c3b5f`.
  Build log SHA256: `ecf9e830466c3b08500c25853e13637bbd1672c4ed500a6c7d9823d3b976cc51`.
- Temperature regression: 210 source units,
  `scratch/upstream_temperature_build.0C5Cu3/`, exit 0.
  Executable SHA256: `b332cd8a12b077b837bf6e25b1517d132b69d10f06201ea3be6d7c9fc20c3623`.
  Both input/runtime hash sets were rechecked; `ldd -r` was clean. Invalid
  producer and excess arguments reject with exit 2 before creating a build.
- Existing C warnings remain; surface adds four `SFCOB` structure-alignment
  warnings. Original surface error paths can still terminate normally or only
  log a failed analysis status (`laps_sfc.f:44,812,839–847`); a successful link
  does not close that failure-reporting contract or prove LSX generation.
  No real producer, native initialization or forecast was run.

### LSX failure propagation and OpenMP build scope — 2026-09-08

- Surface overlays preserve the writer return in `jstatus(3)` and return before
  post-write diagnostics on failure. Config/domain, required surface-data,
  MDAT and final LSX status failure paths now use exit 1; success remains exit 0.
  Original files and scientific calculations are unchanged. Independent AI
  source review found no blocking status defect.
- Corrected an earlier build-profile mismatch: only producer mains and surface
  sources use OpenMP, matching their Makefiles. Common/temp/mthermo/util libraries
  are serial. Prior source-build receipts above do not establish this corrected
  profile. Both final common Barnes objects have no `__kmpc_` references (earlier
  builds did); this is a compile-scope check, not scientific equivalence.
- Final builds, exit 0 with input/runtime hash rechecks:
  surface `scratch/upstream_surface_build.kCzbgT/`, executable SHA256
  `d3b3e3c45badbf9ef7373cc24fd80a99ce8736db0a81d92a18f8d21eb46c9ac5`;
  temperature `scratch/upstream_temperature_build.tHnrlv/`, executable SHA256
  `c3548c8927c58d3a812084d95fb332d9e7c7b33bd51a9139d64006c87b5adbcb`.
- Focused O0/O2 tests: `scratch/upstream_surface_status.F9n0zD/`, exit 0,
  before/after hashes unchanged. Executes extracted main (three cases) and writer
  acceptance block (four return values); remaining subroutine STOP guards are
  checked statically, not by a full mocked analysis. Full suite not rerun.
- Compiler warnings, full input/field validation, strict sandbox capability,
  actual LSX/LT1 generation and FG1–FG3 remain open. No producer was executed or
  installed; post-write verification is not LSX scientific acceptance.

### Humidity build and full local regression — 2026-09-08

- `build_upstream_producer.sh humidity` builds 276 original source units,
  including serial fm/powell/opt90/mthermo and humidity sources. The 15 opt90
  modules follow explicit Makefile dependencies; the duplicate forward-model
  entry is deduplicated with source-set equality checked. Free/fixed source form
  is explicit and compilation runs inside fresh scratch, with fresh modules
  searched first. Independent dependency review found no missing requirement.
- Humidity build/link PASS: `scratch/upstream_humidity_build.u2yxJc/`;
  executable SHA256 `5d1bf1cccf5ed7566abdd325b33b5027f1d4d8433c5dc40d8802bc407b16980d`;
  log SHA256 `ecf31fe489e84c5e28091b168a9bb01ff3d3a65a57b0347655ee5da35dc35157`.
  Temperature/surface regression builds also passed in
  `scratch/upstream_temperature_build.h8vE6g/` and
  `scratch/upstream_surface_build.b5U29x/`. Input/runtime hashes rechecked.
- Full `tests/run_unit_tests.sh` PASS, 04:33:03–04:37:20 UTC, exit 0:
  `scratch/cp01_oracle_verify.e8l1pqsh/receipt.json`. All tracked 67 source/test
  and four toolchain hashes unchanged. Log SHA256:
  `a91296655d2767877cfb40fb5acfc1c36676ae1ad82d1b0477117df833dad33c`.
- This is CP02 build preparation permitted by the pressure-first plan, not CP01
  or CP02 whole-gate closure. Compiler warnings, humidity driver input/status
  checks, remaining producers and strict sandbox execution remain open. No actual
  LQ3 generation, native initialization, forecast or operational change occurred.

### Humidity input and required-writer status — 2026-09-08

- The isolated humidity build now selects `src/humid/lq3driver.f`: failed
  config/dimensions/cycle, unreadable or malformed time input, parse failure and
  timestamp mismatch reject before analysis. Existing time input is read-only.
  Success requires LQ3 `jstatus(1)==1`; optional LH3/LH4 cannot mask its failure.
- Build/link PASS: `scratch/upstream_humidity_build.GJkIFO/`, executable SHA256
  `4b65cd1c7082b462abea7644836348803308401792a28dc11ea0675b65ce196f`.
  Input/runtime hashes rechecked; real producer not executed.
- Focused O0/O2 PASS: `scratch/cp01_oracle_verify.czburuvg/receipt.json`.
  Thirteen cases per optimization check exit/marker, producer entry count and
  input identity. Tracked 70 source/test and four toolchain hashes unchanged.
  Hook added to `run_unit_tests.sh`; the preceding full-suite PASS predates it.
- Timestamp equality is a stricter fail-closed contract than the original
  filename-authoritative reader. Operational pair consistency must be checked
  before actual replay. This remains CP02 preparation, not checkpoint closure.

- Follow-up full `run_unit_tests.sh` PASS, 04:47:37–04:51:58 UTC:
  `scratch/cp01_oracle_verify.v1jy3p8e/receipt.json`, exit 0; tracked 70
  source/test and four toolchain hashes unchanged. Log SHA256
  `7374c0d7ac001e5bf27a7789d136cb9ba7b7a8b798aad89989b8933cf8fc4fcd`.
  This includes the humidity hook but predates the subsequent derived build profile.

### Derived producer isolated build — 2026-09-08

- `build_upstream_producer.sh derived` compiled 225 source units from the
  original common/mthermo/util/deriv Makefile lists, serial as originally configured.
  The main is excluded from the archive and linked once. `comconst` is already
  covered by the original include-directory hash inventory.
- Build/link PASS: `scratch/upstream_derived_build.Ji4QsZ/`, exit 0;
  input/runtime hashes rechecked. Executable SHA256:
  `2d03da25f8e016464fb9abb843fefb7700c2dacd3f59c3d49ce7d5760537afaf`.
- Real derived execution remains prohibited here. Original LCO writer calls
  status-less `put_laps_3d` then unconditionally marks success; this must be
  repaired and tested before generation readiness. No LCO or native product made.

### Original-upstream LCO status and cloud build — 2026-09-08

- Separate `src/upstream/laps_deriv*.f` status overlays preserve the existing
  `src/deriv` research code. Main requires LCO index 10 success; early errors
  return nonzero. Four internal STOPs are nonzero. LCO uses the existing
  `put_laps_multi_3d` with one field and only marks success on writer status 1.
- Modified derived build/link PASS: `scratch/upstream_derived_build.DTpTzz/`,
  executable SHA256 `a6fc5f6bd4681569af768f778888c8dffaceb773c7657913de346be1d54b2c96`.
  Independent source review found no blocking status defect.
- Focused O0/O2 PASS: `scratch/cp01_oracle_verify.o406kkst/receipt.json`.
  Twelve main cases and four writer return values per optimization; real main
  and bounded writer block are extracted, scientific dependencies stubbed.
  Checks include metadata/4D layout, entry count and success-only continuation.
  Tracked 74 source/test and four toolchain hashes unchanged. Unit hook added;
  the preceding full-suite result predates this addition.
- Original cloud build/link PASS, 240 units: `scratch/upstream_cloud_build.Vvy9uW/`,
  SHA256 `5d0430d67424e2fad863ff12f5420c27e0f9200aa5d17902ad27bace9dc7ddd8`.
  Cloud status propagation is not yet repaired. No actual cloud/LCO production,
  native initialization, forecast validation or promotion occurred.

### Cloud status and OpenMP wind build — 2026-09-08

- LCO-inclusive full local suite PASS: `scratch/cp01_oracle_verify.fmaukmhz/`,
  05:03:52–05:08:15 UTC, exit 0, tracked 74 source/test + four toolchain hashes
  unchanged. This predates the cloud hook and wind build profile below.
- Separate original-upstream cloud overlays require LC3/LCB/LCV success, guard
  dimensions and observation-count overflow, propagate LC3 failure and use nonzero
  error STOPs. LC3 writer rejects invalid sizes and more than 42 levels.
  Parent review corrected initialization placement before full build.
- Cloud build/link PASS: `scratch/upstream_cloud_build.YCleuT/`, SHA256
  `3300629f412df2af763a97d562a5405df6430821e6da70f8de1290cd2e3241fd`.
  Focused O0/O2 PASS: `scratch/cp01_oracle_verify.kux9rmio/receipt.json`, tracked
  78 source/test + four toolchain hashes unchanged. Main/helper execute with
  controlled stubs; LC3 caller status guard is checked statically, not full science.
- Wind OpenMP build/link PASS, 180 units: `scratch/upstream_wind_openmp_build.rCZ7Va/`,
  SHA256 `470d96933cf838cdea9cbf4783d966249a08c4684ea9c6faa5e7366da72f9181`.
  Link map selects `libwind_openmp.a(barnes_multivariate.o)`, not common serial
  Barnes. Source is unchanged; this does not recertify the externally completed release.
- Cloud/wind input/runtime hashes rechecked. Wind status propagation and actual
  producer/input closure remain open; no native, forecast or operational execution.

### Wind status and stale-success regression — 2026-09-08

- Cloud-inclusive full local suite PASS: `scratch/cp01_oracle_verify.t_ybyqft/`;
  tracked 78 source/test + four toolchain hashes unchanged. Predates wind status hook.
- Separate `src/upstream/wind_openmp/main*.f` retains scientific calculations.
  Main validates grid/counts, owned-run log I/O status and required LW3 status/time;
  LWM remains optional. Five main-sub error STOPs now return nonzero. The
  post-process and writer jacket initialize `istat_lw3=0`, closing the uninitialized
  return on vertical-wind failure. Unset log directory outputs reject safely.
- Build/link PASS: `scratch/upstream_wind_openmp_build.BYGpip/`, executable SHA256
  `f3167a984c43dec8ab1d6ba2175239432c94522f9c07832149d529b4dec75acc`.
  Input/runtime hashes rechecked; OpenMP Barnes selected by link map. This does
  not establish identity with or recertify the separately completed Barnes release.
- Focused O0/O2 PASS: `scratch/cp01_oracle_verify.9gticgo6/receipt.json`, tracked
  82 source/test + four toolchain hashes unchanged. Actual main and post-process
  execute with controlled stubs; prior success plus vertical failure returns 0
  and never writes. Log retention is not evidence of a forced CLOSE failure test.
- Deeper legacy helper STOP paths and full field/time/grid output validators remain
  required. No actual upstream, native or forecast execution or promotion occurred.

### LT1 content gate and independent PSFC coverage

- `check_qbal_real_inputs.py --inspect-lt1 PATH --case-id ID` checks T3/HT,
  22 pressure levels, written inventories, time, domain size and navigation
  against the pinned FSF. The domain is `p_center <= PSFC`, never LT1 availability.
  Explicit missing values are honored without stale CDL `valid_range` masking;
  packed fields reject. Legacy encoded Dx/Dy matching is not physical metric proof.
- Synthetic contract/negative tests, optional synthetic-LT1 plus real-FSF CLI
  tests, and existing manifest tests PASS in
  `scratch/cp01_oracle_verify.cki1n5c2/receipt.json` (85 tracked files unchanged).
  An earlier test-refactor NameError is retained in `cp01_oracle_verify.doa2hwpe`.
  These are content tests, not actual temperature-analysis generation or a new
  full ifx suite result. Generic unit tests do not require archived FSF inputs.
- Strict bwrap probe still fails with `Failed RTM_NEWADDR: Operation not permitted`.
  No producer run, generation readiness, native validation or promotion is claimed.

### Current QBAL full ifx link

- The existing scratch builder now supports `balance`, using the current
  `qbalpe.f`, `writeballaps.f`, `src/lib/bgdata/lapsio.f`, and explicit
  grid-geometry/localization/wind-modes module order. Original dependencies are
  compiled from source; no existing operational archive or executable is reused.
- Initial full link in `scratch/upstream_balance_build.rjk7fk` failed on
  `get_laps_3d_analysis_data_ex_`, revealing the required `lapsio.f` overlay.
  The corrected clean build `scratch/upstream_balance_build.HYhtZD` compiles
  252 units and passes full link, `ldd -r`, and input/runtime hash rechecks.
  Executable SHA256: `5fb6ccd7d74a9c0d863b89cf8315ae507b25f79d7e129af0eac82f108c3733e5`.
  Link map and symbols confirm the reader, writer and three research modules.
- This is the current legacy/research QBAL binary, not the canonical full-state
  SHADOW adapter. It was not executed or installed. OFF/native round-trip,
  producer input closure, canonical call-graph replacement and science remain open.

### Current LAPSPREP full ifx link

- Scratch builder `lapsprep` profile compiles original common/mthermo/modules
  libraries and current LAPSPREP overlays. Explicit module order is checked
  against Makefile FMOD membership; all modules are written/read in fresh scratch.
  This is existing-host integration, not the deferred latest-WRF modernization.
- `scratch/upstream_lapsprep_build.0Ki3wd` passes 224-unit compilation, full link,
  `ldd -r`, and input/runtime hash rechecks. Binary SHA256:
  `414850b1fb10272d324a3a33bed553a56fd396288c32f337d5fc0241c1741f16`.
  Defined symbols include the current WPS writer, field contracts and moisture
  routines. The full binary was not executed or installed.
- Existing actual-caller/WPS-writer O0/O2 contract tests pass in
  `scratch/cp01_oracle_verify.y4oe0a2y/receipt.json` (85 tracked files unchanged).
  Those tests use numerical fixtures and controlled host stubs, not the full
  executable above or real upstream products. Native OFF/full-SHADOW round-trip,
  metgrid/real, physical/science verification and promotion remain open.

### Per-case runtime clock and LT1 CDL preparation

- Replay now derives the original six-line `systime.dat` from each fixed case:
  signed INTEGER*4 seconds since 1960, matching YYJJJHHMM, HH/MM, ASCII time and
  YYJJJ. Non-UTC/minute, inconsistent identities and overflow reject. The correct
  235x283x22 `ANAL/NE57/DABA/cdl/lt1.cdl` is hash-declared in the replay spec;
  the stale 125x105x21 source-tree default is not used.
- Four `runtime/time` and `runtime/cdl` input pairs were prepared read-only in
  `scratch/original_upstream_replay/runtime_time_cdl_20260908_v2` and all eight
  hashes rechecked. Manifest harness hash matches the current script. Runtime
  PREPARED means these two inputs only; `execution_ready=false`, generation
  BLOCKED and exit 3 are intentional. Current LSX, remaining runtime inputs,
  source/binary binding and strict sandbox remain unresolved.
- Ten replay tests plus existing manifest tests pass in
  `scratch/cp01_oracle_verify.if0wjt41/receipt.json` (88 tracked files unchanged).
  The full original producers and native model were not executed. No stage gate
  or promotion was closed by this preparation.

### Legacy runtime static and background layout

- Runtime materialization now places static grid, grid/pressure/background/temp
  configurations and LT1 CDL at the legacy reader paths; FUA/FSF go under
  `lapsprd/{fua,fsf}/wrf`, with LW3/VRZ/VRT under their respective product folders.
  Source bytes and configuration parameters are unchanged. Unresolved shell
  placeholders/external background paths remain explicitly blocked pending rebinding.
- `scratch/original_upstream_replay/runtime_layout_20260908` contains four case
  layouts, each with 11 hash-declared copies and one derived clock. All 48 file
  hashes recheck. Generation remains BLOCKED, with no producer execution.
- Twelve replay tests and existing manifest tests PASS in
  `scratch/cp01_oracle_verify.5dco_tgi/receipt.json` (88 tracked files unchanged).
  Exact path mapping, missing-role rejection, read-only copies and repeat/hash
  failure paths are covered. This does not close optional-observation inventory,
  current LSX, configuration rebinding, executable binding or strict sandbox.

### Runtime configuration path rebinding

- Grid placeholders and nonempty BGPATHS entries now use the required short
  `/cloud-bal-case` mount namespace. Model selection, physical settings, empty
  background slots and slot indices are preserved. Original templates and derived
  configurations are separately hashed, read-only files; duplicate BGPATHS and
  unsupported placeholders reject. No mount or producer execution is performed.
- Four case layouts in `scratch/original_upstream_replay/runtime_rebound_20260908`
  contain 56 verified files including clocks and original templates. Configuration
  status is `PATHS_REBOUND_REFERENCED_INPUTS_INCOMPLETE`, not execution readiness.
  Referenced static/observation inputs, current LSX, binary binding and strict
  sandbox still block generation. Existing local FUA/WRF selection is unchanged.
- Fourteen replay tests plus existing manifest tests pass in
  `scratch/cp01_oracle_verify.4nu8as8k/receipt.json`; 88 tracked files are unchanged
  during verification. This scoped preparation does not close CP01 or a science gate.

### Temperature observation input bytes

- The replay spec pins target-hour SND/PIN/ADB inputs for all four cases:
  eight present files and four explicitly expected absences. Audit rejects
  missing declarations, path/role/hash mismatches and aliases. Successful inputs
  are copied read-only to original `lapsprd/{snd,pin,adb}` reader paths; absent
  inputs are not synthesized. Receipt hashes include status and expected hash.
- `scratch/original_upstream_replay/runtime_observations_20260908` contains 64
  runtime files with verified hashes. The new spec hash is
  `4693b5a37470313fab9717566392a9aceb5d6a4d387ec705b43c33fbaeacc8c3`.
  Twenty replay tests plus manifest tests pass in
  `scratch/cp01_oracle_verify.xfryxzq7/receipt.json` (88 tracked files unchanged).
- Scope is `INPUT_BYTES_ONLY`; parsing, observation time-window acceptance and
  QC remain NOT_RUN. LRS uses a separate nearest-file +/-3600-second selection
  (`src/lib/temp/read_tsnd.f`); no LRS files were found, but that selection is
  not yet bound in this replay contract. Current LSX, other producer inputs,
  binary binding and strict sandbox still block execution. No checkpoint closes.

### LRS candidate inventory and nearest-time selection

- Replay now binds the complete declared canonical `YYJJJHHMM.lrs` inventory
  against the source directory and preserves every candidate in runtime. It
  selects the nearest time, earlier on ties, with an inclusive 3600-second
  window, matching `get_file_names.f`/`get_file_time.f` and `read_tsnd.f`.
  The 1950 year cutoff and native signed INTEGER*4 time range are explicit;
  unsupported filename formats, aliases, undeclared files and hash mismatch reject.
- Default spec SHA is
  `00352a2edaa0839155e4e910089f97042fda7da7eb1645708cebf013df0839d3`.
  All four cases in `scratch/original_upstream_replay/runtime_lrs_20260908_v2`
  record EXPECTED_ABSENT (no source LRS directory); 64 runtime hashes match.
  Candidate-present paths use fixtures, not observed LRS data.
- Twenty-six replay tests plus manifest tests pass in
  `scratch/cp01_oracle_verify.69lo2c1j/receipt.json` (88 tracked files unchanged),
  including candidate copying, earlier ties, time bounds and post-copy inventory
  digest checks. `INPUT_BYTES_ONLY`/NOT_RUN content validation and execution
  blockers remain; this does not close CP01 or grant scientific authority.

### Surface producer static and LSO inputs

- Runtime now includes unchanged `surface_analysis.nl`, `drag_coef.dat`, the
  correct 235x283x1 `lsx.cdl`, and four hash-pinned target-hour raw LSO files.
  `read_surface_obs.f` opens exact timestamps; the pinned configuration retains
  USE_LSO_QC=0 and L_REQUIRE_LSO=false. Missing/invalid declarations reject, but
  byte acceptance does not certify parsing, QC or surface analysis success.
- `scratch/original_upstream_replay/runtime_surface_inputs_20260908` contains
  80 verified runtime files. Spec SHA is
  `0c2fc9b9cd8b4d3ab1048fe423f84c49b8a6f6d79687e3bd2a02c556613e807a`.
  Twenty-nine replay tests plus manifest tests pass in
  `scratch/cp01_oracle_verify.48zfagll/receipt.json` (88 tracked files unchanged).
- No actual LSX exists under ANAL/NE57. Temperature reads its T/PS through
  `get_laps_2dgrid`, allowing nearest time within half a cycle; these four hourly
  cases still lack an eligible product. Surface production, remaining runtime
  closure, sandbox and native/science execution remain open; no gate closes.

### Previous-cycle LSO for surface internal QC

- Replay now pins the previous raw LSO separately from current LSO and copies
  both under their original filenames. The pinned batch mode uses ihours=1 and
  a 3600-second cycle; date rollover is tested. For 12 UTC the missing 11 UTC
  file is EXPECTED_ABSENT, not replaced by another hour or marked QC-successful.
- `scratch/original_upstream_replay/runtime_surface_previous_20260908` contains
  three additional previous-cycle copies and 83 verified runtime files. Spec SHA:
  `4f09289fb419ed32627da26988c29ecc760890707764d4476885d3a62bea0b38`.
  Thirty-two replay tests plus manifest tests pass in
  `scratch/cp01_oracle_verify.ympvmklh/receipt.json` (88 tracked files unchanged).
- Missing hash, wrong hour, aliases and unexpected presence reject. Existing
  byte-only scope, producer execution block and native/science gates remain.
- Follow-up source audit: FSF supplies surface thermodynamic backgrounds;
  surface wind instead tries LWM/RSF/LGB (not LW3), with zero-weight fallback.
  The remaining enabled satellite branch needs `satellite_lvd.nl` and four
  `lvd/kogk2a/*.lvd` inputs (band 8, +/-970 seconds). Runtime also needs writable
  `lapsprd/lsx`, `lapsprd/tmp`, `log` and `log/qc` directories. These are next,
  not yet materialized or executed. Previous-LSX fallback is disabled in the
  reviewed background routines; historical policy blocker is not execution proof.

### Processed satellite inputs and surface output directories

- Added unchanged `static/satellite_lvd.nl` and four hash-pinned target-hour
  `lapsprd/lvd/kogk2a/*.lvd` files. The enabled processed-LVD reader requests
  S8W within 970 seconds; only exact hourly candidates exist in this snapshot.
  Raw-satellite paths in the namelist are not used by this branch and were not
  rewritten. This is byte preparation, not band-content or satellite QC proof.
- Fresh owner-writable `lapsprd/lsx`, `lapsprd/tmp`, `log` and `log/qc` directories
  are scoped to runtime; input copies remain read-only. The four cases in
  `scratch/original_upstream_replay/runtime_surface_lvd_20260908` contain 91
  verified files. Spec SHA:
  `15a4d87e712f69b3b10a54f459310b14ebf69a978541504d9ad9774b2e682e73`.
- Thirty-five replay tests plus manifest tests pass in
  `scratch/cp01_oracle_verify.67aid9jy/receipt.json` (88 tracked files unchanged).
  Original producer execution, LSX content acceptance, sandbox and native/science
  validation remain open. No operational file or stage authority was changed.

### Surface observation reader bounds and I/O failures

- The surface-only `read_surface_obs.f` overlay now checks header/station/cloud
  reads, observation counts and the five-layer cloud bound; errors return 0
  with cleared counts and closed units. Missing files and valid zero-observation
  headers retain optional-input status -1. Other routines remain unchanged.
- Controlled extracted-reader tests pass at ifx O0/O2, including malformed input,
  bounds, output-open failure, unit closure and recovery. Read-only copies of the
  four pinned LSO files yield 816/816/803/814 observations at both optimizations.
  Receipt: `scratch/cp01_oracle_verify.ki_dc0oi/receipt.json`; 91 tracked files and
  compiler/runtime hashes were unchanged. This is parsing evidence, not full QC.
- Full surface link `scratch/upstream_surface_build.O9nxsa` passes with the new
  reader selected; input/runtime hashes recheck clean. Binary SHA:
  `f3e31a2799cbd4bfa1da967afed15ac123485f09581cba55833696da9724f1dc`.
  The full producer was not executed, installed or published.
- `read_surface_old` still converts reader failures into optional absence for
  previous-cycle QC; end-to-end error propagation is not closed. Strict bwrap
  still fails at loopback namespace setup. CP01/native/science gates remain open.

### Previous-hour raw LSO error propagation

- Surface-only overlays now preserve reader -1 as optional absence, map other
  reader failures to QC -2, and make the surface caller exit nonzero. QC 0 means
  no usable observation pair, not a passed QC analysis. All QC early-return paths
  close the log; normal completion explicitly returns 1. Interfaces are unchanged.
- Filename/time guards precede raw/QC reader calls. The legacy time-status local
  was implicitly REAL despite the actual INTEGER ABI; it is now explicitly
  INTEGER. Tests use the real ABI, not a matching but incorrect REAL stub.
- O0/O2 actual-wrapper and actual-QC tests with controlled reader inputs, plus
  the extracted actual caller branch, pass in
  `scratch/cp01_oracle_verify.x_mw4zut/receipt.json` (95 tracked files unchanged).
  Cases include absence, malformed/unknown status, invalid time, no observation
  pair, normal background checks, log-open failure and log-unit closure.
- Final full surface build `scratch/upstream_surface_build.cxBlLe` passes with
  matching input/runtime hashes; binary SHA
  `31ae8a2610dbc93dd88546d3a88e8591de312d1460c9041e9ac0e30866c3d6a4`.
  Earlier `w7ttpL` build predates the INTEGER ABI correction and is historical.
  No full producer execution, LSX generation, native or science gate is claimed.
  Other producers still use their original wrapper; LSOQC corruption semantics
  are not closed by this raw-LSO change. Strict sandbox remains unavailable.

### Integrated unit regression after surface reader/QC changes

- `bash tests/run_unit_tests.sh` completed with exit 0 in 283 seconds at
  `scratch/cp01_oracle_verify.whubzoo6/receipt.json`. The 95 tracked files and
  pinned compiler/runtime hashes match before/after; this dirty-worktree result
  is not an exact clean-HEAD release certification.
- The suite includes pressure physics/balance, research SHADOW I/O and rejection
  checks, replay contracts, the new reader/QC O0/O2 cases, six producer status
  suites and final QBAL fixed-72 compilation. Array-temporary warnings remain.
  This does not execute original producers or WPS/real/native forecasts.
- Next implementation: LSX acceptance before LT1 consumption (exact case/time,
  grid/navigation, required T/PS fields, coverage and source/build provenance).
  A validator cannot create the missing LSX; strict sandbox still fails with
  `RTM_NEWADDR: Operation not permitted`. No checkpoint or promotion gate closes.

### LSX content contract before temperature analysis

- Added `--inspect-lsx PATH --case-id CASE` to the existing input checker.
  It checks exact case filename, analysis valtime/reftime, 235x283x1 layout,
  full finite T/PS coverage, units and LAPS metadata, written inventories,
  AGL level zero and writer dimensions (24 output variables). LSX/FSF encoded
  navigation shares the existing LT1 comparison helper. The CLI pins FSF hashes
  to the four-case inventory and rejects generation-option mixing and aliases.
- This bounded domain uses T 150..350 K and PS 50000..110000 Pa. It validates
  the two temperature-consumer fields, not the remaining 22 LSX fields, scientific
  quality, producer provenance or native metric correctness. PASS retains
  `LSX_CONTENT_ONLY`, `producer_provenance=NOT_VERIFIED`, generation BLOCKED.
- Synthetic mutations and four synthetic-LSX/actual-FSF CLI cases pass in
  `scratch/cp01_oracle_verify.qxcb7nns/receipt.json` (96 tracked files unchanged).
  Existing LT1 and pre-QBAL manifest tests also pass after navigation reuse.
  The initial fixture used `surfacelevel` instead of CDL `level`; its failed
  receipt is retained, and only the corrected fixture passes.
- No LSX was produced by the actual surface executable. Connecting a verified
  producer receipt and sealed LSX to LT1 launch remains open, along with strict
  sandbox capability and full native/science validation. No stage closes.

### LSX contract review and execution boundary

- Independent source review confirms 24-field writer dimensions, AGL zero,
  analysis-time valtime/reftime and T/PS units. The consumer's 200..400 K check
  applies to `temp_sfc_eff` after background-difference and theta adjustments
  (`src/lib/temp/puttmpanal.f:331-454`), not directly to raw LSX T. The bounded
  raw-content range is therefore unchanged; it cannot certify consumer success.
- The next required evidence is actual isolated surface production, accepted
  LSX and temperature consumption. The strict bwrap probe still fails with
  `loopback: Failed RTM_NEWADDR: Operation not permitted`. A capable execution
  host is needed; no unconfined fallback or synthetic generation is substituted.

### User-authorized directory-separated experiment

- The user explicitly replaced mandatory kernel isolation with a simpler
  separate-directory experiment. This is path separation, not a security sandbox;
  the historical strict-sandbox gate is not retroactively marked PASS.
- Copied the prepared 12 UTC runtime and current surface executable into
  `scratch/sfc_dir.QugOdh`. Replaced `/cloud-bal-case` only in the copied grid
  and background configurations. Ran from this directory with a clean environment,
  local LAPS_DATA_ROOT/TMPDIR, pinned Intel library path and one OpenMP thread.
- Initial execution hit the default 8 MB stack limit. A per-process unlimited
  stack permitted calculation; adding the existing NetCDF-C install/bin to PATH
  supplied ncgen. Final execution exited 0 and produced actual
  `lapsprd/lsx/262281200.lsx` (SHA
  `7abb05002e2086915365f570b2972f0ef22b03dd674ac7139512b053dfa6a24d`).
  Logs `surface.log`, `surface_stack.log`, `surface_ncgen.log` retain all attempts.
- LSX T/PS have complete 66505-cell coverage: T 284.6001..302.5837 K,
  PS 77631.54..101011.24 Pa. Content acceptance still FAILs exact La1/Lo1 equality
  against FSF (differences -3.8147e-6 and +1.5259e-5 degrees). Dx/Dy match.
  Resolve static/background navigation encoding before temperature handoff;
  do not reinterpret this actual producer run as full native/science completion.

### Actual directory-separated LSX to LT1 execution

- Navigation investigation found that LSX matches `static.nest7grid` exactly;
  FSF encodes rounded CDL constants (`La1=31.34451`, `Lo1=119.7993`). This is
  encoding precision, not evidence of a displaced data array.
- Rebuilt temperature with pinned ifx in `scratch/upstream_temperature_build.fQy0xI`;
  input and runtime hashes passed before execution. Copied its executable into
  the same owned `scratch/sfc_dir.QugOdh` runtime, retaining actual LSX and FUA.
- First attempts exposed missing output directories `tmg` and `lpbl`, then a
  missing PBL CDL. Created only experiment output directories and copied original
  `ANAL/NE57/DABA/cdl/pbl.cdl`. Earlier logs and LT1 copies are retained.
- Final `temperature_complete.log`: exit 0, `LT1_PRODUCER_SUCCESS`, with actual
  LT1 and PBL products. LT1 SHA is
  `90e7bba8a188796d84b19264d721c9ac9a254250c461eab9c453524924ba3d2d`;
  the preceding successful LT1 write has the same hash. LSX hash is unchanged.
  T3 spans 200.2106..308.8584 K on 22 pressure levels; the pinned FSF defines
  1,294,568 above-ground cells. This is actual temperature consumption and
  production, not synthetic generation, complete upstream closure or science
  approval. Directory separation remains distinct from kernel isolation.
- LSX and LT1 content checks now PASS for this actual case. Only La1/Lo1 allow
  the documented FSF CDL decimal precision plus float32 encoding error; other
  navigation comparisons remain exact. Synthetic LSX mutations, four pinned
  FSF-reference CLI cases and LT1 contract regressions pass. This scoped check
  does not certify the complete producer manifest, native handoff or forecasts.
- Replay preparation now declares the PBL CDL and creates LT1/TMG/LPBL/PBL
  output directories. All 35 replay tests pass; the updated default spec SHA is
  `5525a96555799924c786747e6ab790deb2391d87fc05af6b5464eb2b44c38ff6`.
  This does not retroactively rebind the earlier prepared runtime's receipt.

### Actual cloud and humidity continuation

- Same directory-separated 12 UTC experiment: fresh pinned-ifx cloud build
  `scratch/upstream_cloud_build.jthea2` and humidity build
  `scratch/upstream_humidity_build.KnwBxl`; input/runtime hashes checked before
  execution. Copied original cloud configuration, output CDLs and GOES lookup
  table. Cloud first failed on missing `static/goeslib/for044.dat`; after its
  copy, `cloud_goeslib.log` exits 0 with all LC3/LPS/LCB/LCV statuses 1.
- LC3 has 42 cloud-height levels, complete finite cloud fraction in [0,1], and
  the correct valid time. This is not the 22-level pressure analysis grid.
  SHA: `85419e24ece048c8a382ac8dd1a6aada955ef322e2c3fe1fe3ebe608fea8848a`.
- `humidity.log` exits 0 with LQ3/LH3/LH4 statuses 1. Original moisture switches
  are unchanged; only the copied GPS path points to the experiment directory
  (no GPS files supplied). The actual cloud analysis is consumed. LQ3 has
  22 pressure levels and 1,294,674 nonmissing finite SH values in
  [1e-10, 0.02217136] kg/kg. SHA:
  `37c24038bbefdb44d221315c14cd3f6db1d1cc4783805eac1217ef48480259dc`.
- Fresh derived build `scratch/upstream_derived_build.0LrfKM` reads the actual
  products but traps at `get_cloud_deriv.f:227`: missing lightning converts
  real missing data to an integer. `derived.log` retains exit 134 and traceback.
  No trap suppression or fabricated lightning observations are used.
- Missing previous LM2/GPS and background-search fallbacks remain explicit;
  file production alone is not independent scientific validation or native
  SHADOW completion. All executables and writes remain experiment-local.
- The derived-only upstream overlay now uses integer `-1` for missing lightning,
  handles malformed/truncated input and closes an opened unit on fallback. Other
  physics remains original upstream; the separate research overlay is not
  substituted. Five input cases pass at pinned-ifx O0/O2 with traps enabled
  (`scratch/get_cloud_deriv_lightning.q61U5M`); added to the normal unit runner.
- Rebuilt derived in `scratch/upstream_derived_build.qBxP3X`; input/runtime hashes
  checked before execution. `derived_complete.log` exits 0 with
  `LCO_PRODUCER_SUCCESS`. Missing auxiliary CDL files were copied from original
  DABA into the experiment, without changing prior files or operational outputs.
  LCO SHA: `6e7a061aeb2eadb7290ae3822a8bcd7c4fe96a41a9fe1d7b6b19423616c84e01`.
  LCO is legacy cloud omega, not hydrometeor mass or observational authority.
  Actual LWC product contains finite nonnegative LWC/ICE/SNO/RAI/PIC/PCN fields
  on all 1,463,110 pressure-grid cells. LSX and LT1 hashes remain unchanged.
- Cloud preparation now includes its four CDLs/output directories, cloud.nl and
  GOES lookup table. Replay tests: 36 PASS; default spec SHA
  `8f645d9ff55f4d37b6ab5e69e03b55c1ceb58ec8ec0ffcdcbb9c824057dc84c6`.
  Humidity/derived runtime copies in this experiment are not yet incorporated
  into the general preparation contract. Historical receipts retain old pins.

### Direct existing-product SHADOW input

- Extended the existing `read_real_shadow_state` with all-or-none optional LT1,
  LQ3, LWC and LSX paths. No new intermediate input format or duplicate physics
  pipeline is introduced. The legacy FUA/FSF signature remains supported.
  Direct mode uses LSX PSFC, LT1 T/height, LQ3 specific humidity and LWC species;
  it does not open or fall back to FUA/FSF. LW3/VRZ/VRT inputs are unchanged.
- Analyzed thermo/surface provenance is OUTPUT_ADAPTER, not an invented
  independent-observation claim. Hydrometeors additionally identify CLOUD_ANALYSIS.
  LCO is not converted to a dynamic target. Unit and dry-air conversions reuse
  existing helpers; legacy LWC `kg/meter**3` is accepted only in direct mode.
- `tests/run_analyzed_shadow_case.sh` is an experiment test, not an alternative
  operational runner. Latest actual run `scratch/analyzed_shadow.OFkZDT` exits 0
  with deliberately nonexistent FUA/FSF arguments. All hashed inputs/source files
  are unchanged; the complete operational state equality check passes.
  70,083 cells have hydrometeor changes; wind/omega increments remain zero.
- SHADOW NetCDF SHA:
  `adbd6eb2ce5a0d47ba57f99d254245068139cb465875a2f568d6f46310550876`.
  Repeated runs produce identical bytes. The runner now invokes the existing
  independent numerical validator and propagates its failure; validation.json
  and validation.log are retained. These remain UNBOUND diagnostics, not full native products.
  The historical real SHADOW reader/writer contract suite also passes.
- The independent direct-reader normalization/all-or-none test passes at pinned
  ifx O0 (`scratch/analyzed_shadow.GDTeX9/test_reader*`). The execution preflight
  reuses product-to-product navigation checks. Static latitude parameters have
  obsolete longitude-unit labels: only their numerical equality is checked,
  explicitly, while inter-product unit checks remain strict. No input is edited.
- This closes a direct-input execution slice only. The actual run does not yet
  request coupled thermo/outer iteration, observational dynamics, native WPS/real
  handoff or forecast verification; no CP01/FG1 completion is inferred.

### Actual liquid-saturation coupling experiment

- The existing driver accepts explicit `--thermo-liquid-radar` only with direct
  analysis inputs. It selects the immutable usable-radar footprint, liquid
  saturation with target RH 1, and an outer cap of 16. The default is unchanged.
  This is a liquid-only ablation, not a mixed-phase/KDM6 rate policy or wind
  authorization; supercooled liquid is not implicitly frozen.
- First actual trial `scratch/analyzed_shadow.h2TJro` selects 70,083 cells and
  converges in three iterations. T changes in 52,936 cells (minimum -2.8820801 K);
  vapor/cloud liquid change in 52,937. Ice and wind remain unchanged, and the
  complete operational state is preserved. Independent validation rejects this
  trial on `flux_ledger_error independent radar ledger`; do not count it as PASS.
- Pinned-ifx real SHADOW I/O regression suite passes. Invalid experiment options
  are rejected by both the shell runner and driver before input access.
- The same rebuilt driver without the option produces `default-shadow.nc` with
  unchanged historical SHA `adbd6eb2ce5a0d47ba57f99d254245068139cb465875a2f568d6f46310550876`.
- The independent radar residual comparison now propagates the existing
  operand-comparison error budgets through subtraction. Individual flux tests
  and the separate same-artifact conservation gates are unchanged. A paired
  +1 kg/s input/terrain mutation closes internally but fails independent replay;
  the regression is wired into the existing I/O suite.
- Final actual rerun `scratch/analyzed_shadow.trpUUc` exits 0 with unchanged
  hashed sources/inputs and identical physical output to the rejected first
  trial: SHA `af6a2d2c6f0edcd38f986b4a03f3ebc8ff6549f45c933e2caf3f9b98d814e599`.
  Independent numerical, analysis-ledger and radar reconstruction checks pass.
  Outer fixed-point replay remains producer-only (independent metadata checks),
  not an independent nonlinear solve or full native/science acceptance.
- Final I/O suite, including the new balanced-ledger mutation regression,
  exits 0: `scratch/analyzed_shadow.trpUUc/io-regression.log`.

### Actual pressure-geopotential coupling: diagnostic coverage remains open

- Added explicit `--thermo-liquid-radar-phi` to the same driver/runner. It uses
  the existing hydrostatic increment, full above-ground support in radar columns,
  and a fixed lowest represented pressure-center anchor (not a surface boundary).
  Other experiment modes retain their prior meaning. Phi requests select the
  existing pressure-candidate serialization contract.
- Actual trials converge in three iterations and change 136,653 Phi cells.
  First trial `scratch/analyzed_shadow.HOHv3z` omitted the pressure-candidate
  writer declaration; corrected calls still fail geostrophic assessment.
  `scratch/analyzed_shadow.kVZQaU` records the precise writer-stage rejection.
  No candidate file is published and the operational state remains unchanged.
- Independent inspection of the same actual domain finds 150,624 hydrostatic
  support cells, a 197,173-cell geostrophic cross-halo, and 34 cells lacking
  an x or y same-pressure neighbor. The current diagnostic requires both
  derivatives at every requested cell. Next: distinguish requested and
  stencil-evaluable diagnostic support explicitly, without zero-filling or
  silently dropping terrain cells or claiming full scientific coverage.
- The existing LAPSPREP WPS callsite and mapper can retain actual host arrays.
  Actual RH, surface slabs and ancillary data remain host-owned; no synthetic
  fixture arrays should be substituted as an integration shortcut. WPS/real
  handoff and mixed-phase/native scientific acceptance remain incomplete.

### Explicit geostrophic diagnostic coverage: actual candidate saved

- The v2 diagnostic preserves all 197,173 requested cells and separately marks
  197,139 stencil-evaluable cells. The 34 terrain-edge cells remain explicitly
  unevaluated, not zero residuals. Invalid requested inputs still fail; v1
  remains strict, and a nonempty request with no evaluable cells is rejected.
- Final actual run `scratch/analyzed_shadow.80ljUi` exits 0 with unchanged
  source/input hashes and operational state. It converges in three outer steps,
  changes 136,653 Phi cells, and makes no wind increment. Candidate SHA256:
  `0ca1a8521dbbbcc818b309f642100a0c3a6a8316752ef2b036344d30829f3f9a`.
  Independent numerical, radar, analysis-ledger, Phi and partial-geostrophic
  checks pass. Intermediate `J4tJoD` is excluded from final-source evidence
  because its post-run source identity check failed during a concurrent edit.
- Pinned Intel I/O suite exits 0 (`scratch/geostrophic-v2-io-regression.log`),
  including v2 mutations and v1 compatibility. Focused Fortran assessment
  tests also pass at O0/O2. This is liquid-RH1 research, not KDM6 or native
  acceptance; independent outer fixed-point replay and science remain open.
- A later validator edit changes its original input-receipt hash (all other
  listed inputs still match). The unchanged artifact also passes the current
  validator independently: `current-validation.json`, validator SHA256
  `ac6c5cfc00448e19c18f785973877f5d327b31fda0d16349989b6e1ddb8e94fa`.
  The original execution receipt remains historical, not rewritten.

### Existing LAPSPREP actual-input continuation

- Reused the original `lapsprd` paths in `scratch/sfc_dir.QugOdh` and the
  existing full LAPSPREP build profile; no parallel production pipeline.
  Research namelist requests WPS/QV, with legacy balance/hotstart and uncoupled
  evaporation disabled. The grid-relative flag is a research declaration,
  not independently verified frame provenance for the pinned LW3.
- Actual `Nzj4JB` rejects unused LW3 omega. WPS-only calls now skip OM and
  surface VV reads/conversion; mixed and other outputs retain existing checks.
- Actual `ykEmWa` exposes the descending-only pressure restriction. All actual
  LT1/LW3/LH3/LQ3/LWC coordinates ascend 50--1100 hPa. The caller now accepts
  either strict direction without reordering arrays, and selects surface winds
  by greatest represented pressure above terrain rather than array position.
  Invalid pressure coordinates now terminate nonzero, not character STOP/exit 0.
- Final full pinned-ifx build `scratch/upstream_lapsprep_build.ZGnE9o` passes
  compile/link/source checks. Actual run reaches LQ3 and fails `invalid_sh_field`
  with exit 1, before any WPS output. Independent input inspection finds all
  168,436 invalid SH cells below PSFC and zero invalid above-ground SH cells.
  Next is the real below-ground WPS missing/extrapolation contract, not invented
  humidity or relaxed above-ground checks. This is not a successful OFF/native
  round-trip or a completed candidate handoff.
- Extended caller regressions pass with pinned ifx: WPS-only missing/invalid
  OM/VV, strict mixed-output and U/V rejection, ascending pressure mapping,
  duplicate/nonmonotonic pressure rejection, and order-independent surface-wind
  selection. Log: `scratch/lapsprep-output-contract-regression.log`; retained
  cases: `scratch/lapsprep_vapor_tests.KQXEwM`. Existing hotstart O0/O2 cases
  also remain green. New order/requiredness cases are O0 checks, not O2 claims.

### Actual baseline WPS through the existing LAPSPREP

- WPS-only/QV now permits explicit finite +/-1e37 SH missing values strictly
  below a valid PSFC to use the existing surface mixing ratio. Raw SH validity
  stays degraded; invalid above-ground, equality-boundary and malformed values
  are not extrapolated. The complete file and surface inputs remain required.
- Full pinned-ifx build and actual execution in
  `scratch/upstream_lapsprep_build.G9A4QA` succeed. `baseline.wps` is 34,348,056
  bytes; SHA256 `f50a031d9795cc87bfe47fae475bbe111a3984073c9fe784c6d2cdcbdd4a10fd`.
  A second run is byte-identical. All 168,436 extrapolated SH cells are below
  ground; source/build checks and the prior raw-analysis input hashes still match.
- This reuses the existing analysis file layout and writer. It is the baseline
  path with hotstart/balance disabled, not the coupled Cloud-BAL candidate or
  WPS/metgrid/real/native round-trip. Missing LM2 retains the documented legacy
  zero-snow default; GRID_RELATIVE remains a source-consistent declaration with
  unresolved binary-bound input-frame provenance. CP01 and FG1 remain open.
- Extended caller suite passes (`scratch/lapsprep-subterrain-regression.log`,
  artifacts `scratch/lapsprep_vapor_tests.3dxlfg`). Three new positive cases
  preserve degraded SH metadata and use surface QV only below ground. Seven
  negatives reject missing LQ3, above-ground/equality missing SH, below-ground
  NaN/Inf/out-of-range SH, and invalid PSFC even without legacy enforcement.
  A separate run of these ten cases with the retained O2 binary yields identical
  positive WPS bytes to O0 and rejects every negative before output.
- Independent raw-array comparison covers all 129 WPS slabs, exact time and
  235x283 dimensions, and finite output: 20 pressure levels each for
  TT/HGT/UU/VV/RH/QV plus nine surface/ancillary slabs. All non-QV values are
  exact; pressure QV differs from the double-precision reference by at most
  1.5504198e-9 kg/kg. Surface QV is exact. Logs in the actual build directory:
  `parent-array-check-final.log` and `parent-surface-height-check.log`.
  Focused independent code review found no blocking defect. These numerical
  checks do not establish native frame provenance or coupled initialization.

### In-process coupled candidate through the existing LAPSPREP writer

- The shared `run_pressure_analysis_shadow` routine now serves both the research
  driver and the actual LAPSPREP WPS callsite. Existing `lapsprd` inputs and the
  existing WPS writer are reused; `.shadow.nc` is a diagnostic sidecar, not a new
  production input format. Experiment outputs remain in a separate directory.
- Pinned-ifx build `scratch/upstream_lapsprep_build.BKkLw2` and its 347-entry
  build-input hash check pass. Default `baseline.wps` is byte-identical to the
  prior actual baseline. Actual `LIQUID_RADAR_RH1_PHI` execution exits zero and
  writes `candidate.wps` (SHA256
  `f4c0cbe18345c03f9513635a38194b60643586e1f2ce7e5a46d67a8d9a768bdf`).
- The same-run `candidate.wps.shadow.nc` is byte-identical to the earlier
  standalone coupled artifact (`0ca1a8521dbbbcc818b309f642100a0c3a6a8316752ef2b036344d30829f3f9a`).
  Its independent validator exits zero; `candidate-validation.json` records
  numerical validity, analysis/thermo/geopotential checks and partial geostrophic
  coverage (197139 of 197173 requested cells). It does not independently replay
  the outer fixed point or grant science/native/promotion authority.
- Full pinned-ifx real I/O and actual LAPSPREP caller suites pass:
  `scratch/pressure-shared-io-regression.log` and
  `scratch/lapsprep-inprocess-regression.log`. The latter rejects unknown
  experiments, missing output/QV and incompatible legacy processing settings.
- This remains a liquid-RH1 research experiment, not KDM6 closure. RH is retained
  as nonauthoritative; downstream direct-QV configuration, actual metgrid/real,
  native mass/frame and boundary contracts remain open. CP01 and FG1 are not
  complete. Independent final WPS-array comparison is a separate check.
- Focused independent source review finds no blocking defect or duplicate
  vapor/species correction in this slice. Two limits remain: the legacy default
  integer clock reaches its range limit in January 2028, and a post-open WPS
  write failure can leave a partial file beside the completed diagnostic. These
  research files are not an atomic published generation or a success receipt.
- Parent read-only array comparison passes all 234 candidate WPS records
  (baseline: 129). Above-ground T/U/V/QV/five species exactly match the same-run
  canonical candidate, and HGT matches float32(Phi/9.80665). Below-ground and
  retained records match baseline; newly emitted below-ground/surface species
  are zero under the explicit hotstart-off configuration. This verifies stored
  pressure-level values, not the subsequent model-plane interpolation.
- The reusable independent checker is `tests/check_actual_lapsprep_shadow.py`.
  Parent execution passes exact 234-record inventory/units/time/grid and array
  checks, plus three value/level/retained-RH mutations. HGT is independently
  converted in float64 and then stored as float32, matching the declared adapter
  arithmetic without loosening equality tolerances.
- Next existing-path inventory identifies operationally renamed KLFS metgrid
  and real executables and geogrid/table assets. The real namelist does not
  explicitly enable direct QV; same-cycle ancillary inputs and runtime library
  closure need resolution before a directory-separated run. The new candidate
  can supply the missing 12 UTC LAPS intermediate; other-cycle constants must
  not be silently substituted. Reference KIM source is not binary provenance.
- Follow-up independent saturation checks now evaluate only the explicitly
  selected thermo cells, avoiding exponential overflow on inactive underground
  placeholders. The same actual candidate validates with RuntimeWarning treated
  as an error; `candidate-validation-selected.json` is byte-identical to the
  previous validation JSON. Small validator tests and 67 thermo mutations pass;
  equations, selected-cell tolerances and acceptance decisions are unchanged.

### Existing downstream ancillary preparation

- KLFS wrapper time selection for 2026081612 chooses background cycle 2026081606
  (fallbacks 00 and previous-day 18). Its SST boundary filename is a link to
  `klbg_lc05_usst.2026081606`, not a missing independent SST producer. Existing
  valid-12 KLBG/KIM/soil inputs are present. The KLBG WPS inventory has no SH or
  SPECCLDL/F override; duplicate hydrometeor fields still need metgrid priority
  verification. The reference real path requires explicit direct QV selection.
- Actual original `klfs_lc05_prep_tavgsfc.e` exits zero in
  `scratch/existing_tavgsfc.HMQRGk`, without installing or replacing anything.
  The unchanged wrapper's 24-hour configuration consumes eight 3-hourly surface
  T fields from 12 UTC through next-day 09 UTC (the endpoint is excluded).
  `tests/check_existing_tavgsfc.py` independently checks all 66505 cells, units,
  grid metadata and a +1 K mutation. Maximum error is 8.77380371e-5 K, within
  the standard float32 accumulation bound; input/executable hashes are unchanged.
  Output SHA256: `e510aa4de756f59ef6654edc2b66cd0fccf7306867e5c18a0851dc84cd1db78d`.
  Its timeless WPS header is retained; the explicit input window supplies lineage.
- This is execution evidence for the existing external producer, not a newly
  pinned-ifx source/build certificate. Actual metgrid/real have not run: local
  MPI resolves, but their required old NetCDF shared libraries are absent in
  inspected project/local roots, with additional HDF5/MKL dependencies for real.
  KLFS OML requires a valid-12 KLBG forecast wrfout that has not been located.
  No SONAME aliases, different-time OML, or replacement host were substituted.

### Existing metgrid execution with pressure-analysis candidate

- Follow-up runtime recovery completed in `scratch/metgrid_netcdf_runtime.YPWjEW`:
  NetCDF-C 4.6.3 and Fortran 4.5.2 were built with pinned Intel compilers in
  scratch only. Their actual SONAMEs are 15 and 7. Fortran 4.5.3 correctly
  rejected the older C dependency; its version check was not bypassed.
  Six focused C tests, two Fortran writer/reader tests, and an actual geogrid
  Fortran read pass. With existing Intel MPI, original metgrid `ldd -r` reports
  no missing library or undefined symbol (`metgrid-loader.log`).
- Original `klfs_lc05_prep_mgrd.e` now exits zero for both candidate
  (`scratch/existing_metgrid_run.MN5Fl5`) and baseline
  (`scratch/existing_metgrid_baseline.P8QOCt`). Only the linked LAPS file differs;
  namelists, original geogrid/table, background-cycle 06 valid-12 KLBG/soil/wave
  data, SST and regenerated TAVGSFC are shared. All recorded input hashes remain
  unchanged. Both runs produce actual `met_em.d01.2026-08-16_12:00:00.nc` files.
- This is explicitly a one-time pressure-field handoff diagnostic. The missing
  original-cycle OML constant was excluded, not replaced with another cycle or
  fabricated zeros. H0ML/TMOML are absent. The ocean-enabled original real/full
  forecast contract therefore remains incomplete; no native or science gate
  advances. Original real also still needs its additional runtime dependencies.
- Actual paired arrays have identical U/V, PRES, RH, PSFC and SST. TT, GHT, QV
  and the five hydrometeors differ and are finite. Maximum TT/GHT/QV differences
  are 3.01132202 K, 24.2163086 m and 0.000973343849 kg/kg. Hydrometeor differences
  include source-priority changes (baseline KLBG versus explicit candidate LAPS),
  so these are handoff observations, not isolated algorithm skill estimates.
  Direct-QV selection in real and native mass/energy validation remain required.
- Independent output inspection confirms the internal 12 UTC time, expected
  mass/U/V staggering, QV and five hydrometeor presence flags, and finite,
  nonnegative moisture arrays. There is no SH field in this output. The stored
  PRES units attribute is blank despite numerically pressure-like levels;
  producer/consumer unit semantics still need explicit verification. Candidate
  sidecar and metgrid arrays are on different grids and cannot be compared
  elementwise. Candidate/baseline output SHA256 values are respectively
  `6d6168b0ac1df1e0ef3e2987591d8f77445cf8ed2c69a527a00469af79af3b7b`
  and `611be865399f8f0f9ff63aa680c756d4c87216ee7a70ec08de001d2cb4ef7278`.

### Original real runtime recovery in progress

- `scratch/real_runtime.NyjY9H` owns all new dependency work. MKL 2021.4
  provides versioned `.so.1` files and was not renamed to satisfy the old
  executable. Official MKL 2019.0 provides the required unversioned filenames;
  the four missing MKL libraries now resolve without aliases. Archive SHA256:
  `065e3c415029da2b2cdf2097cecb05f67e834354b358448aca683da7f4e3d344`.
- `real-loader-mkl.log` still contains missing HDF5 libraries, 356 PnetCDF
  `ncmp*` references and four Intel `__libm*` references. Loader completion and
  real execution are not claimed. The metgrid NetCDF build uses system serial
  HDF5; the eventual real runtime must avoid mixing two HDF5 implementations.
- HDF5 1.10.4 source archive SHA256:
  `8f60dc4dd6ab5fcd23c750d1dc5bca3d0453bdce5c8cdaf0a4a61a9d1122adb2`.
  Running CMake from its build directory fixes the old Fortran probe output
  location. Pinned Intel compilation exposed a wrong continuation-message cast,
  a missing API-context header, and callback signature mismatches. Scratch-only
  compatibility work is ongoing; no compiler fallback or diagnostic suppression
  was used, and no HDF5 build PASS is recorded yet.
- Follow-up OML path audit: the original wrapper actually reads `KLBGDAOU`,
  not `KLBGDAIO`. Its defining `~/jobs/NE57/UTIL/ENVI/klbg_src` is absent;
  neither workspace `MODL/KLBG/NE57/DAOU` nor the inspected home production-root
  candidate exists. The original archive root is unresolved, not proven empty
  everywhere. Existing 13--15 UTC OML products may support an additional native
  engineering case, but do not close or remove the fixed 12--15 UTC regression.
- Explicitly preloading either current Intel libimf or official `icc-rt`
  2020.0.133 does not resolve the four old `__libm*` symbols. No dummy symbol
  implementation or global runtime replacement was introduced. The runtime-only
  wheel hash is `17a173e65cee0c516358172b9cc96fe297dd54f4d6b23d57f79c62d9e105e3cf`;
  this failed compatibility probe is not compiler/build or real execution PASS.
- PnetCDF 1.12.3 shared-library build/install is available under
  `scratch/pnetcdf_runtime.vTUWlK/install` (source archive SHA256
  `439e359d09bb93d0e58a6e3f928f39c2eae965b6c97f64e67cd42220d6034f77`).
  Parent's process-local loader probe `real-loader-pnetcdf.log` resolves all
  356 `ncmp*` references using this actual library. The four `__libm*`
  references and HDF5 runtime requirements remain; this is not a successful
  real run. No operational environment or executable was changed.
- Unified NetCDF-C 4.6.3 build/install now exits zero in
  `scratch/real_runtime.NyjY9H/netcdf-unified`, using pinned Intel MPI/icx,
  regular HDF5 1.10.4 and PnetCDF 1.12.3. Library SHA256:
  `da1d0550cae69949722a72f25132d866fa53c8bc1288b936bcad92e64680616d`.
  `unified-netcdf-loader.log` has no missing/undefined references or serial
  HDF5 dependency. Reused NetCDF-Fortran 4.5.2 successfully reads the actual
  234x282 geogrid through this C library; ncdump reads the candidate met_em.
  `real-loader-unified.log` resolves all named dependencies and PnetCDF without
  LD_PRELOAD, leaving exactly the four old `__libm*` references. Real remains
  unexecuted; native/science/operational gates are unchanged.
- HDF5 targeted library builds, component installs and a C file round-trip
  finish successfully (`build-hdf5-libs.log`, `install-hdf5-components.log`,
  `hdf5-roundtrip.log`). Scratch compatibility edits correct callback prototypes,
  one pointer cast and one missing header; HL-Fortran is built with the actual
  autotools-style SONAME. The full example/test build still fails in unrelated
  `test/dt_arith.c`, so no full HDF5 suite PASS is claimed.
- Original real embeds WRF V4.6.0 and classic Intel 19.1.3.304, with substantial
  static PnetCDF 1.12.1 symbols. Local KIM source is also V4.6.0 but its ifx
  artifact has different build provenance and I/O configuration. Loader symbol
  resolution with shared PnetCDF 1.12.3 is only a diagnostic, not proof that
  mixing it with the embedded static implementation is runtime-safe. No private
  math shim was created. Existing local ifx binary receipts are being audited
  for a separately identified research host, not silent original-host replacement.
- Unified NetCDF focused C tests both pass (`nc_test`: 328.63 seconds;
  `nc_test4_tst_types`: 0.04 seconds). The same live test completed without
  restart; process I/O counters had continued increasing during observation.

### Additional 13 UTC upstream case, without replacing 12 UTC coverage

- Owned runtime `scratch/upstream13.Sfb68E` copies the prepared 13 UTC surface
  input layout, not 12 UTC analysis products. Existing pinned-ifx surface and
  temperature executables are reused. Only the background path binding and
  owned output directories are changed; original input/operational paths remain
  untouched. Original PBL CDL is copied as a static format definition.
- Actual surface and temperature runs exit zero. LSX and LT1 read-only content
  checks pass against the pinned 13 UTC FSF (`lsx-validation.json`,
  `lt1-validation.json`). LSX SHA256:
  `e94384c402a08a78c3dbddaa50ea203c6a5d0e19f25587ded645570831eecb08`;
  LT1 SHA256:
  `9dc247b9628e482edd3c098f8ba1aacca9a3e22d451563652bde95044359296c`.
  The first temperature run lacked the PBL output directory; after creating it,
  PBL output succeeds and LT1 remains byte-identical to the first run.
- This additional case does not remove fixed 12--15 UTC tests or close FG1.
  Reused cloud, humidity and corrected derived executables now exit
  zero (`cloud.log`, `humidity.log`, `derived.log`); LQ3 and LCO success markers
  are present. LWC contains six finite, nonnegative concentration arrays without
  sentinels, with valid/reference time 1786885200 (13 UTC). LCO retains 1,198,264
  explicit missing cells and is not promoted to an observational wind target.
- The same existing LAPSPREP executable produces both 13 UTC WPS files under
  `scratch/upstream13.Sfb68E/wps`, with no operational file replacement.
  Baseline SHA256: `e28b68f4a3452f8b15e5838b022d89a53b0c9c80fd4671e3a7d5f0c03b828c47`;
  candidate SHA256: `b62358ea930f721367210efe39d1704ee3ce83f093e1182313f8416681a8c634`;
  sidecar SHA256: `11b5efc8779d4b13363c862a8e9cc9d1378f308feb94c22a3fba2682939ce0a1`.
  `mapping-validation.log` passes all 234 records, exact metadata and stored
  candidate mapping, including rejection of three checker mutations. This
  LIQUID_RADAR_RH1_PHI experiment is not KDM6 closure, authorized nonzero dynamic
  coupling, or a completed metgrid/real/native round-trip. CP01 remains open.
- The 13 UTC standalone numerical validator also exits zero with runtime
  warnings treated as errors (`wps/candidate-validation.json`). Its authority
  remains numerical content only, with no observational dynamic target and no
  promotion eligibility. Independent LC3/LQ3 inspection confirms exact 13 UTC
  valid/reference times; all 168,111 SH sentinels are strictly below the actual
  LSX surface pressure, with none at or above the surface. These observations
  do not turn missing below-ground SH into valid source observations.
- Existing local KIM ifx `main/real.exe` matches its build manifest hash
  `fa76d4bb17c0c63ecfed12a09ed912ba149248c1378f45b1938b16d2f729bdff`;
  configure hash also matches and compiler/MPI environment resolves all symbols.
  Tracked changes since the recorded source commit are certificate files only.
  Generated/untracked build inputs are not fully captured, so the receipt is an
  identity check for this research binary, not complete build reproducibility or
  proof of equivalence to the original KLFS executable. No native run is claimed.

### Actual 13 UTC metgrid and research-native initial-state handoff

- Original metgrid exits zero for both paths, using identical original 13 UTC
  ancillary links including OML, the original table and input order. Only the
  LAPS WPS link differs. Candidate directory: `scratch/metgrid13_existing.kGBYC7`;
  baseline: `scratch/metgrid13_baseline.jAF1jm`. Candidate met_em SHA256:
  `7309d819c31763141ff60a903d9b9808d49bcbcdf62153f1529886b05c3a7a41`;
  baseline: `6f4053c99ad9dea5cdc707a19365618c856b8584a9a0824bedf4d9f2fe89eb16`.
  Both contain 21 levels at 13 UTC, direct QV and five hydrometeors. All these
  fields are finite and nonnegative. U/V/PRES/PSFC/RH and OML/SST are identical;
  temperature, vapor, hydrometeors and height differ. Hydrometeor differences
  also include the existing LAPS-versus-KLBG priority change, not only the
  canonical proposal increment.
- Existing ifx research `real.exe` now exits zero for both paths and creates
  actual `wrfinput_d01` files. Candidate: `scratch/real13_candidate.ORj7ke`, SHA256
  `fc078b4f6c213603b9dcbec5ab6134d197eefca3256a5a4ab79c4cdc876beb53`;
  baseline: `scratch/real13_baseline.RfWxbE`, SHA256
  `4ddd63a9c6be59b3b58f4fea84cab3a22b2ae61c8c5f2b06a664a28e6b1b0f91`.
  The original physics template is retained (MP=37, CU=37, ocean=1), with
  `use_sh_qv=true`, local input path, and start=end=13 UTC. This is initial-state
  only: no boundary file, forecast, original-host equivalence or FG1 acceptance.
  First attempt failed on `met_em.d01.2026-08-16_13:00:00.nc.nc`; retaining the
  original `<date>` filename pattern fixes the duplicated suffix. First logs
  are preserved. No input data or operational executable was replaced.
- Native fields have 39 mass layers and 40 interfaces. Both pass the existing
  independent hybrid coefficient/interface/column algebra checker, using
  research-host source gravity 9.81 m/s2; reports are `hybrid-geometry.json`.
  Candidate maximum layer/column closure errors are 0.002500/0.000110 Pa.
  This does not certify the canonical gravity convention or native conservation.
- Despite identical metgrid winds, native U/V differ by up to 0.008109/0.018640
  m/s. MU differs by up to 28.3515625 Pa, P by 524.90625 Pa and PH by 456.8515625
  m2/s2; PB/MUB/PHB, W and PSFC remain identical. The source interpolates winds
  in dry-pressure coordinates (`module_initialize_real.F`, calls near 2777/2791),
  so native remapping must be evaluated independently of analysis wind targets.
  Diagnostic domain dry mass changes by -1.03107875140e11 kg. This is an exposed
  mass/coordinate coupling result, not a conservation PASS or an approved wind
  innovation. Dry-mass/PSFC policy and final native increment support remain open.
- OML ocean temperatures are positive, but 82 water-mask cells have zero H0ML
  in both metgrid paths. No artificial floor was added. Native/forecast handling
  must be checked before any time-integration safety claim. KDM6 number/volume
  initialization, nonzero observational dynamics, boundary and 0--6 h tests
  remain unresolved. CP01 and FG1 stay open.
- The native candidate contains `QNCCN`, `QNCLOUD`, `QNICE`, `QIB` and `QNRAIN`,
  but all five are zero despite nonzero hydrometeor mass. Their presence alone
  is not a valid KDM6 number/volume initialization. Host microphysics startup
  behavior and the mass-consistent initialization policy must be checked next.
  OML1D itself guards division by zero depth, so zero H0ML is not by itself
  evidence of an inevitable crash; its physical interpretation is still untested.

### Direct-QV native interpolation correction experiment

- Independent native inspection finds 92,909 negative QVAPOR cells in both
  original-order baseline and candidate, minimum -3.5362813e-5 kg/kg, despite
  positive metgrid QV. Thus successful real execution and geometry algebra did
  not establish native moisture validity. These order-2 outputs are rejected
  by the new paired moisture check; they are not accepted initial states.
- The existing `lagrange_order=1` setting is tested in new owned directories
  `scratch/real13_linear_baseline.KZbb28` and
  `scratch/real13_linear_candidate.cDHzm4`. All input links, physics and direct-QV
  choice remain unchanged; log-pressure and constant extrapolation retain
  existing defaults. Both real runs exit zero with zero negative QVAPOR cells
  and minimum 1.2136383e-7 kg/kg. No source QV clipping, RH substitution, model
  rebuild or operational configuration change was used. This setting changes
  other vertically interpolated variables too and is not a QV-only fix or
  science-approved default.
- Existing `check_native_hybrid_geometry.py --baseline` now separates native
  species changes into baseline-mass composition change and candidate-composition
  mass-metric change: `mc*qc-mb*qb = mb*(qc-qb)+(mc-mb)*qc`. It requires matching
  time, horizontal coordinates, hybrid metric and valid six-species dry mixing
  ratios. This is an accounting diagnostic, not a native adapter or conservation
  certificate; no A_Q, boundary flux or independent approval is inferred.
- Actual linear-pair report `paired-budget.json` has dry-mass change
  -1.0310787514692511e11 kg and total water change +3.3696866441973535e12 kg.
  Source-priority and background differences remain in this comparison. The
  dry-mass/PSFC policy, coupled KDM6 startup and nonzero dynamic target are not
  closed by eliminating the interpolation undershoot. FG1 remains incomplete.
- Focused native geometry/budget tests pass (10 tests): literal independent
  column masses, no change, vapor/cloud transfer, separate mass/composition
  increments, and rejection of mismatched time/coordinates/metrics, missing or
  invalid species and identical malformed/masked timestamps. The actual
  order-2 pair is rejected for negative QVAPOR, while the order-1 pair produces
  the bounded accounting report. Neither result is a scientific acceptance gate.

### Same-background full-state OFF baseline

- Explicit `CLOUD_BAL_SHADOW_EXPERIMENT=OFF` now uses the same canonical reader,
  mapper and full hydrometeor WPS writer as the candidate, invoking the existing
  MODE_OFF pipeline and requiring original=candidate=operational identity.
  Unset-environment legacy behavior is unchanged. OFF does not write a SHADOW
  sidecar; the SHADOW writer's mode gate remains unchanged. An initial attempt
  correctly rejected OFF at that gate before output; no authority was relaxed.
- Fresh pinned-ifx build `scratch/upstream_lapsprep_build.kAaVsE` passes build,
  link and input/runtime checks. Actual 13 UTC `wps/off.wps` exits zero, SHA256
  `aadc0cc1d59448d9f24cac6f9c130457e42bf1a03ada950cf4a9079fbf936118`.
  Independent comparison verifies all 234 records against canonical background
  fields and retained host slabs, with no OFF SHADOW sidecar.
  Re-running the candidate with this same fresh executable produces byte-identical
  WPS and diagnostic files (`candidate-off-paired.wps` and its sidecar). Existing
  LAPSPREP caller regressions also pass. The dedicated OFF check in
  `test_lapsprep_vapor.py` passes actual inventory, time, dimensions and canonical
  background values. HGT uses float64 division before float32 storage, without
  relaxed tolerances. Four in-memory mutations (time, shape, missing species,
  cloud value) are rejected; real artifacts remain unchanged.
- Original metgrid `scratch/metgrid13_off.oQviM0` and existing research real
  `scratch/real13_linear_off.pPGy6w` both exit zero using the same ancillary
  inputs and order-1 interpolation. OFF native SHA256:
  `a1781f78bc5cca4ad3c2c7f9f8c5d2f3d99dbde2a98b127d12b4b14c05d22b2a`.
  `same-background-budget.json` compares the existing candidate against this
  full-state OFF: dry mass -1.0310789852089084e11 kg; total water
  -8.559885456374106e10 kg. The earlier +3.3696866441973535e12 kg comparison
  included different hydrometeor backgrounds and is not algorithm-only evidence.
  Neither comparison proves conservation or science improvement.
- KDM6 source follow-up distinguishes native startup from file inventory:
  `start_em.F` and the first KDM6 call synthesize QNCCN from configured CCN and
  height/land-sea information; kdm6init initializes constants, not 3-D fields.
  QNCLOUD/QNICE/QIB/QNRAIN enter the first physics call at zero and evolve through
  process terms. No arbitrary positive values are injected. Actual first-step
  behavior remains to be verified; zero file values alone are not a proven bug.

### Host vapor-column pressure primitive

- Added `host_vapor_pressure_column` to the existing WPS adapter, following
  the research host's `integ_moist` discrete vapor integral with explicit Rd/g,
  surface-first input, either pressure order, and no above-top tail. This is
  not a bitwise host emulation or a PSFC/MU correction; runtime coupling remains open.
- Independent analytic, ordering, invalid-input and overflow tests pass together
  with existing WPS mapping tests at checked O0 and optimized O2. The runner now
  uses the reproduction flags for O2 so runtime debug checks cannot disable it.
  Log: `scratch/host_vapor_regression.5yGMXx.log`. CP01/FG1 remain incomplete.

### Source terrain and PSFC handoff through the existing host

- Actual metgrid had no `FLAG_SOILHGT`; real selected `sfcprs` from sea-level
  pressure instead of the input-PSFC terrain adjustment. Added optional SOILHGT
  emission to the existing LAPSPREP writer, enabled only for explicit OFF/SHADOW.
  It uses the existing source-topography surface slab; legacy output is unchanged.
- Build `scratch/upstream_lapsprep_build.VHQEZy` succeeds. Actual
  `upstream13.Sfb68E/wps/{off,candidate}-soilhgt.wps` have 235 records; all previous
  234 candidate records remain identical. Actual independent mapping and five
  mutations pass, as do O0/O2 mapping and legacy caller regressions (logs
  `scratch/soilhgt_mapping.C8dMRD.log`, `scratch/soilhgt_lapsprep.Bx3avv.log`).
- Original metgrid runs in `metgrid13_soilhgt_off.JejAQs` and
  `metgrid13_soilhgt_candidate.7XDCho` supply FLAG_SOILHGT=1. Existing research
  real runs in `real13_soilhgt_off.o1TlKc` and `real13_soilhgt_candidate.UJqCyD`
  select `sfcprs2` with an owned `sfcp_to_sfcp=true` namelist; both exit zero.
  Independent source-terrain/TAVGSFC PSFC calculations differ from native PSFC
  by at most 0.009822 Pa; vapor-integral/native dry-pressure closure by 0.004029 Pa.
  Both have zero negative native QVAPOR cells. No operational namelist changed.
- Native SHA256 OFF `6929efa97363810e32ca72dfe0a212dcd409d04e897278b0e86194493f66c800`,
  candidate `f18326c719a0f9ef953fdeeaeba7588006bc41af07df6e51766a13a129773621`.
  Paired dry-mass change remains -1.031072773398e11 kg: input-pressure handoff is
  connected, not dry-mass conservation, full coupled initialization or FG1 closure.

### Bounded host surface-pressure solve

- The existing WPS adapter now solves `F*p_source-I_vapor(p_source)=p_dry_surface`
  analytically for an unchanged first above-ground level. The target includes
  model-top pressure, not MU alone. Explicit increment caps, level-crossing
  rejection and a recomputed residual precede success; no state is modified.
- Independent humidity-compensation, terrain-factor, no-op and rejection tests
  pass at O0/O2 (`scratch/host_pressure_solve.jbD46K.log`). Actual metgrid-column
  feasibility calculations require at most 28.352423 Pa over 65,988 columns;
  two columns cross a pressure level and require a coupled domain/height remap.
  No resulting pressures were written to the actual candidate. Production
  coupling, storage-rounding validation and native dry-mass closure remain open.

### Surface-anchored hydrostatic column increment

- Extended the existing hydrostatic increment routine with explicit paired
  surface pressure, temperature and six-species mixing ratios. It integrates
  the changed surface-to-first-center thickness at fixed terrain instead of
  forcing the first-center increment to zero. Omitted boundary arrays retain
  the existing behavior; partial/invalid boundaries preserve the output.
- Independent boundary/rollback and existing state tests pass with pinned ifx
  at checked O0 and optimized O2 in `scratch/surface_anchor.JcXdb3`. Actual
  pipeline boundary ingestion, candidate geometry and serialization remain open.
- Also reproduced and fixed a finite-scale real128-to-real64 overflow in the
  host PSFC solver; pinned O0/O2 regression log is
  `scratch/host_pressure_overflow_fix.NVjIgm.log`. GNU reviewer tests are excluded;
  its two generated module caches were moved to `scratch/excluded_gnu_modules.1nb2a4`.

### Existing surface inputs retained through the WPS adapter

- Canonical state now retains optional surface vapor (dry-air kg/kg) and
  surface height (m), including validity, quality, source, and time. Existing
  LSX `mr` is converted from g/kg; static `avg` supplies terrain. Missing vapor
  remains invalid; no RH-derived or constant replacement is introduced.
- The existing WPS mapper uses valid canonical boundary cells and retains
  supplied WPS surface cells elsewhere. Exact state equality and manufactured
  provenance rejection include both fields. No new production file tree,
  operational executable replacement, or runtime installation is required.
- Pinned Intel canonical tests pass. Mapping and host-pressure regressions
  pass at O0/O2 (`scratch/surface_boundary_mapping_final.log`). The actual
  12 UTC reader test passes at O0 (`scratch/surface_boundary_reader.9xuzIH`).
- Final-source O2 actual-reader verification passes in
  `scratch/surface_boundary_final.rSBQ9x`. The unchanged 13 UTC direct-input
  thermo/Phi case and independent sidecar validator finish with exit 0 in
  `scratch/analyzed_shadow.E7KQdv`; source/input hashes remain unchanged,
  outer iteration converges in 3 steps, and operational core differences are
  zero. Dynamic balance remains unauthorized; this does not validate the new
  surface fields through sidecar replay or close native conservation.
- The analyzed-case runner now compiles from its scratch directory, with an
  absolute script path in its input receipt. The first revised run exposed and
  rejected the relative script path; a subsequent run correctly rejected a
  state-source change during execution. Neither is a final-source PASS.
- This is an in-memory and existing-WPS connection, not surface-boundary
  sidecar replay, coupled PSFC/geometry closure, native dry-mass conservation,
  or CP01 completion. Canonical sidecar schema remains unchanged pending the
  explicit boundary serialization/replay extension.

### Surface boundary serialization and independent readback

- Canonical schema 5 now writes background/candidate pressure, temperature,
  vapor, and terrain fields through the existing SHADOW NetCDF writer, with
  value/valid/quality/source, units, and valid time. The existing input-geometry
  `surface_pressure` variable is unchanged. The extension is identified by
  `CANONICAL_SURFACE_BOUNDARY_V1`; no separate product format was introduced.
- The independent validator checks the full extension, bitwise boundary
  preservation, usable provenance, and consistency with input PSFC. Historical
  canonical 3/4 files remain readable without claiming surface validation.
  Schema downgrade with retained new fields is rejected. Missing temperature,
  vapor, or terrain remains explicit; serialization does not authorize using
  missing data as a physical boundary.
- Focused surface-validator and existing Python validator tests pass. Canonical
  state and existing WPS/host-pressure tests pass at O0/O2. Actual 13 UTC run
  `scratch/analyzed_shadow.UdRqaH` finishes with exit 0, independent validation,
  unchanged input/source hashes, and zero operational core differences. Direct
  readback of all four fields (66505 cells each) agrees with LSX/static inputs,
  validity masks, and time. No new nonzero wind target is authorized.
- All 128 pre-existing diagnostic variable payloads are byte-identical to the
  prior same-input `scratch/analyzed_shadow.E7KQdv/shadow.nc`; only 32 surface
  value/metadata variables were added.
- The full pinned Intel/NetCDF I/O contract runner finishes with exit 0
  (`scratch/surface_boundary_io_complete.log`), including O0/O2 writer/physics
  readback and mutations, historical schema fixtures, live pipeline WPS
  comparison, and the actual 12 UTC reader/invalid-input cases. Earlier logs
  preserve the overstrict temperature-coverage and outdated schema-test
  failures; they are superseded by this final-source run, not counted as PASS.

### Surface-anchored pressure-analysis Phi

- Existing hydrostatic application now accepts reference 0 on selected columns
  as an explicit fixed-terrain surface anchor; positive center anchors retain
  their previous behavior. It requires usable supplied surface p/T/qv/terrain,
  unchanged PSFC/geometry and terrain, and full increment support. Surface
  condensates use the declared `WPS_SURFACE_ZERO_CONDENSATE` convention, not
  observed-zero authority. Invalid boundaries reject without changing inputs.
- The shared analysis dispatcher, standalone driver and LAPSPREP accept
  `LIQUID_RADAR_RH1_SURFACE_PHI`. Existing writer and independent verifier use
  `pressure_hydrostatic_surface_increment_v1`; mixed anchor modes are rejected.
- Actual same-input 13 UTC run `scratch/analyzed_shadow.i0wmEf` finishes with
  exit 0, three outer steps, independent surface/Phi validation, unchanged
  source/input hashes, and zero operational core differences or wind increments.
  Of 7999 selected columns, 6911 have nonzero first-center Phi increments;
  maximum magnitude is 5.8525390625 m2/s2. Pressure, temperature, all six water
  species and winds match the prior fixed-center case exactly at the array-value
  level; this change is the surface-anchored Phi adjustment.
- Parent full pinned Intel/NetCDF I/O regression finishes with exit 0
  (`scratch/surface_anchor_pipeline_io.log`), including O0/O2 surface/center
  anchor replay, boundary mutations, pipeline/WPS and actual reader cases.
- This preserves the background hydrostatic residual rather than solving a new
  absolute native equilibrium. Native mass conservation, KDM6 phase policy,
  forecast safety, and CP01/FG1 closure remain unproven. Next handoff uses the
  existing LAPSPREP -> metgrid -> real chain without installing a new runtime.
- Surface-anchored coupled pressure/Phi adjustment and native mass closure
  remain next work; this does not close CP01 or FG1.

### Surface-anchor handoff through the existing native chain

- Rebuilt only the modified LAPSPREP (`scratch/upstream_lapsprep_build.PmJ9gK`;
  build input hashes rechecked). Reused the existing upstream inputs, original
  metgrid executable/table, and existing research real executable and namelist.
  Only output directories and the LAPS input link differ; no new runtime or
  operational input changes were introduced.
- `scratch/surface_phi_handoff.gD2eal` completes LAPSPREP, the actual 235-record
  WPS mapping checker with five mutations, and independent numerical-content
  validation. Surface-boundary and pressure-Phi replay pass; dynamic authority,
  science and promotion remain absent. The first attempt in `JzJkNV` failed at
  the writer's large MERGE temporary with the default 8 MB stack. Its partial
  sidecar/log are retained as failed evidence. Reusing the existing runner's
  `ulimit -s unlimited` setting succeeds with the same binary.
- Original metgrid completes in `scratch/metgrid13_surface_phi.pvhRI2`; existing
  research real completes in `scratch/real13_surface_phi.1aKerK`. Native SHA256:
  `47bedda168d57848e03e68d707ed51299cad0809f39f182c33d66056c43c4dd6`.
  The unchanged research namelist retains `lagrange_order=1`; equivalence to the
  original operational real executable is still unverified.
- Existing independent hybrid geometry and paired-budget checks complete;
  reports are stored beside wrfinput. Layer/column algebra errors are at most
  0.002501/0.000110 Pa. All six native water species are finite and nonnegative.
  The checker regression suite also passes all ten tests.
- Relative to the same-input OFF native state, dry mass changes by
  -103083867453.99048 kg and water by -85597865430.60493 kg. Relative to the
  prior fixed-center candidate, dry mass changes by +23409885.81021 kg;
  PSFC and W are identical, while maximum absolute changes in MU/P/PH are
  0.125 Pa / 0.2109375 Pa / 0.09375 m2/s2. Native U/V change by at most
  0.001001/0.001945 m/s despite unchanged pressure-analysis winds, exposing
  state-dependent native remapping rather than an authorized wind target.
- This is successful existing-path handoff, not mass conservation or FG1
  acceptance. Next implementation must couple source PSFC/geometry/Phi and
  native dry mass with explicit analysis budgets; downstream array patching
  would not close that physical contract. CP01 remains in progress.

### Coupled host-column pressure and height solve (2026-09-09)

- Extended the existing `solve_host_surface_pressure` with an optional paired
  height response/output. Under fixed terrain, thermodynamics and active levels,
  it solves `scale*ps - I_vapor(ps, z(ps)) = target`, with
  `z(ps)=z(old_ps)+c*log(ps/old_ps)`. The caller must derive the common active-level
  coefficient from the full-mixture surface/lowest-center hydrostatic quadrature;
  the vapor-only host integral does not provide that coefficient.
- The bounded bisection commits pressure and heights together only after residual,
  cap and unchanged-level checks. Invalid responses, missing paired arguments,
  below-terrain heights and unbracketed roots retain caller outputs. The original
  fixed-height path is unchanged. No new experiment or runtime was introduced.
- Pinned O0/O2 mapping and host-column tests pass in
  `scratch/coupled_ps_height_explicit.log`, including an independently integrated
  manufactured root, logarithmic heights, zero-response agreement and rollback.
  An intermediate internal-procedure version passed O0 but failed O2; explicit
  arguments between module-private pure routines remove that observed discrepancy
  with unchanged equations/tolerances/compiler flags. Earlier logs are not PASS.
- This is a coupled column block, not a canonical/native conservation claim.
  Connecting it still requires a single staged PSFC/geometry/dry-mass/Phi update,
  refreshed analysis budgets, storage-rounding checks and actual native replay.
  In particular, source/native horizontal remapping cannot be bypassed by copying
  a native per-column correction into the pressure-analysis grid.

### Pressure-geometry analysis accounting (2026-09-09)

- `account_pressure_analysis` now has explicit bookkeeping-only geometry opt-in;
  default callers still reject changed PSFC/interfaces/cell mass. Active cells,
  pressure centers/spacing, horizontal measures and valid time must match.
  This routine never grants application authority or changes either state.
- The ledger exposes pressure-mass analysis change separately and evaluates
  `delta_dry_mass + sum(delta_species_mass) - delta_pressure_mass`. The enthalpy
  product split is `mb*(ha-hb) + (ma-mb)*ha`; its dry-mass term includes water
  denominator changes even at fixed geometry, not exclusively a PSFC effect.
- `test_pressure_geometry_budget` exercises PSFC +20 Pa with rebuilt geometry
  and refreshed dry mass, `area*delta_PSFC/g`, combined mixture/enthalpy changes,
  legacy rejection, unchanged-domain requirements and input identity. It is
  included in the existing checked/optimized unit-test loop. In-memory pipeline
  comparison/no-op checks include all new budget members.
- No current production/SHADOW dispatcher opts into changed geometry. New
  ledger members are not yet a serialized variable-geometry contract; staging
  PSFC/Phi/geometry together and independently verifying their persisted budget
  remains required before actual source-to-native replay or CP01 acceptance.

### Atomic surface-pressure/geometry/Phi application (2026-09-09)

- Extended the existing hydrostatic application with paired requested PSFC (Pa)
  and geometry-budget arguments. It stages stored-float32 PSFC, pressure geometry,
  dry mass and surface-anchored Phi together; only full-support surface anchors
  may change PSFC, without changing represented pressure-level classification.
  Failure retains the proposal and a zero output budget. Unchanged columns retain
  their original geometry bits even when valid rounding differs from regeneration.
- The first-center terrain check now also applies to surface anchors without a
  PSFC request. Final-source O0/O2 transaction/regression tests pass in
  `scratch/surface_ps_verified.4K7GIm`, with source/test hashes unchanged across
  execution. An earlier rounded-metric fixture was invalid; the corrected fixture
  uses one-ULP perturbations and retains the original production tolerances.
- Actual 13 UTC surface-Phi regression `scratch/analyzed_shadow.V43s2d` completes
  with independent numerical VALID, failures empty and unchanged input hashes.
  All serialized variable payloads match `analyzed_shadow.i0wmEf`. This exercises
  the existing no-PS-request path, not a real-data nonzero PSFC correction.
- The preceding full unit run also exits zero
  (`scratch/pressure_geometry_budget_unit.log`). The new applier remains an
  explicitly called state API: host-target construction, dispatcher/serialized
  variable-geometry contracts and nonzero-PSFC native replay remain open.

### Prescribed-pressure pipeline connection (2026-09-09)

- `run_cloud_bal_pipeline` now forwards an explicit PSFC request to the atomic
  applier and commits its request record and separate geometry budget only after
  all stages succeed. OFF remains identity; failed trials publish neither item.
  Final pipeline O0/O2 tests pass in `scratch/pipeline_ps_request.2L7jmu`.
- This is currently a prescribed single-step research path. The existing
  five-field outer loop excludes pressure geometry, so combining that loop with
  this request is rejected instead of claiming variable-geometry convergence.
  Host-target construction and a coupled geometry-aware iteration remain open.
- The current writer explicitly refuses pressure-request results before file
  creation: its schema stores only background pressure geometry. Tests cover
  rejection without creating a misleading fixed-geometry sidecar. A versioned
  background/candidate geometry and ledger contract is the next serialization
  task; the command dispatcher does not yet expose a nonzero-PSFC experiment.

### Prescribed-pressure serialization and independent replay (2026-09-09)

- Extended the existing writer with `prescribed_surface_pressure_v1`: exact
  float64 request, stored candidate geometry and the separate post-thermo
  geometry ledger. Legacy fixed-geometry files retain their original contract.
- Continuity diagnostics explicitly use candidate/balance-stage geometry;
  `continuity_original_background` preserves the original-geometry baseline on
  the same diagnostic support. Dry-air advection uses each state's geometry;
  neither field claims a diagnosed mass tendency or native conservation.
- Independent continuity replay now uses pressure-overlap faces, replacing its
  incorrect same-level averaged-thickness assumption. Geometry accounting also
  distinguishes retained pre-thermo dry mass from refreshed candidate mass,
  including float32 species-storage roundoff.
- The retained focused fixture is
  `scratch/variable_geometry_io.ewnMoT/run.Tqwnw4/variable-pressure-shadow.nc`.
  It exercises localized fractional-Pa requests, active bottom cells, nonzero
  wind response, unchanged columns and thermo rounding on both PSFC branches.
  The independent column-mass oracle and missing/mutated payload tests pass.
- The full pinned Intel/NetCDF O0/O2 writer, independent validator, live WPS and
  actual 12 UTC reader regression suite exits zero:
  `scratch/variable_geometry_full_io_final.log`. The pressure-overlap hand
  oracle passes. Geostrophic geometry opt-in tests also pass at O0/O2; default
  rejection and invalid center/grid/geometry cases remain covered.
- This closes a serialization component, not CP01 or FG1. Host-derived pressure
  requests, geometry-aware outer coupling and nonzero-PSFC native replay remain
  open; the dispatcher and operating files are unchanged.

### Existing metgrid-to-native pressure replay (2026-09-09)

- Extended `tools/check_native_hybrid_geometry.py` with `--metgrid` and explicit
  `--gas-constant`, reusing the existing files without rebuilding the host or
  adding a second execution chain. The independent calculation covers the
  direct-QV/TAVGSFC `sfcprs2` and `integ_moist` profile. Source PSFC and source
  terrain enter the vapor integral; destination terrain enters the surface
  pressure adjustment. This is a stated host-profile assumption, not binary
  equivalence or conservation approval.
- Actual OFF and surface-Phi candidate replays pass at the existing 0.05 Pa
  stored-pressure tolerance. Maximum errors are 0.00982115 Pa for PSFC and
  0.01329708 Pa for `MU+MUB+P_TOP`. Reports are retained as
  `scratch/real13_soilhgt_off.o1TlKc/host-pressure-replay.json` and
  `scratch/real13_surface_phi.1aKerK/host-pressure-replay.json`; input hashes
  remain unchanged. Metgrid/native coordinates match exactly at 234 x 282.
- This closes a reproducible downstream pressure diagnostic, not the source
  pressure solve. The 235 x 283 analysis grid must still pass through the
  existing WPS interpolation; a native target cannot simply be copied back.
  Nonzero source PSFC construction and geometry-aware coupling remain open.
- The existing `MODL/KLFS/NE57/DABA/METGRID.TBL.ARW.OML` selects
  `four_pt+average_4pt` for PSFC/SOILHGT, `four_pt` for TAVGSFC and
  `sixteen_pt+four_pt+average_4pt` for TT/GHT. Reuse that forward path rather
  than inventing a crop or inverse mapping from array dimensions.
- Five independent host-pressure tests (including analytic columns and small
  file mutations) pass. Both existing Python/unit runners include them. The
  complete portable Python suite passes in
  `scratch/native_host_pressure_python_contracts.log`; no Fortran changed in
  this slice and no new full ifx/native execution is claimed.

### Source-grid host pressure proposal in actual LAPSPREP (2026-09-09)

- Added the explicit `LIQUID_RADAR_RH1_SURFACE_PHI_HOST_PSFC` experiment to
  the existing LAPSPREP path. It maps the same canonical OFF background and a
  single-pass surface-Phi candidate to the retained WPS inventory, constructs
  source-grid host pressure requests, and calls the same pipeline again from
  the immutable original. This initial proposal uses host Rd=287, g=9.81 and
  a 100 Pa cap; the six-species height response uses canonical g=9.80665.
  Neither native-grid conservation nor pressure-geometry outer convergence is
  claimed. Existing experiments retain their previous iteration settings.
- `build_source_host_pressure_request` reuses the existing host column solve.
  Unselected columns retain original PSFC; failure preserves the caller's
  entire request array. Stored-PSFC caps, active-level classification and a
  forward storage-rounding check precede acceptance. Failed solves report one
  reproducible column profile, not a full-grid dump or a reduced support mask.
- Pinned Intel full LAPSPREP build/link passes in
  `scratch/upstream_lapsprep_build.Cueb2B` (binary SHA256
  `8d03d1041afbe191f6b2be36b1a0005540ab59badc41d642ec13e9203c673595`).
  O0/O2 mapping/host/request tests pass in
  `scratch/source_host_pressure_mapping_final.log`; O0/O2 full SHADOW I/O,
  dispatch request-scope/OFF checks and actual reader regressions pass in
  `scratch/source_host_pressure_io_final.log`. Existing LAPSPREP caller tests
  pass in `scratch/host_psfc_lapsprep_regression.log`. The previous 13 UTC
  surface-Phi experiment also passes in `scratch/analyzed_shadow.mfB5cM`.
- Actual new-mode run `scratch/host_psfc_handoff.yXlkfW` exits 1 before WPS or
  sidecar creation at source column (122,39). Its original PSFC is 99999.125 Pa;
  the source dry-pressure target is 99333.3156905378 Pa. Independent replay of
  the recorded profile gives target residual -12.15092392 Pa at original PSFC
  and -11.29374448 Pa at the 100000 Pa boundary. The target therefore cannot
  be reached on the current active-level interval. This is not a tolerance
  failure. The earlier `host_psfc_handoff.jnHHed` run fails at the same column.
- At this column, raw LT1 T3 and LQ3 SH at 1000 hPa are masked; raw LT1 height
  is 42.70056 m. Canonical temperature/vapor/geopotential are unrepresented
  there. The next implementation must explicitly construct newly exposed
  layer values and conservatively reconcile pressure-cell mass/enthalpy before
  extending the pressure solve across a center. Do not treat retained WPS
  underground fills as independent analyzed observations, drop the column or
  clamp its pressure and call the dry-mass target closed. Input hashes remain
  unchanged; no operating file, METGRID policy or native output was replaced.

### Conservative pressure-column repartition prerequisite (2026-09-09)

- Added `remap_pressure_column` inside the existing column physics module.
  Pressure-overlap weights redistribute dry mass and all six species masses;
  a mixture heat-capacity moment preserves the existing reduced enthalpy.
  Identity and single-donor temperature/species values are bitwise preserved.
  Invalid inputs or failed public-precision closure leave outputs unchanged.
- Independent split/merge, unequal-moisture pressure-mass, extensive-budget,
  near-1000-hPa partition and rejection tests pass with pinned ifx at O0/O2:
  `scratch/remap_final_check.OvSQHf`. The test is in the existing unit runner.
- The existing full unit runner completes with exit 0 in
  `scratch/pressure_partition_unit.log`, including SHADOW I/O, actual reader,
  WPS/host-pressure, original upstream and fixed-form compilation regressions.
- This primitive only repartitions identical outer pressure endpoints. It
  neither creates a missing analyzed pressure-center observation nor extends
  the column boundary. Actual active-level changes still require an explicit
  reconstruction prior, boundary-increment budget, metadata and native handoff
  integration. The failed actual HOST_PSFC case and CP01 remain open.

### Domain-budget and stored-state handoff prerequisites (2026-09-09)

- `account_pressure_analysis` now optionally accounts the union of two active
  domains, only with both geometry and domain opt-ins. Absent volumes contribute
  zero extensive content without reading missing T/species. Incomplete active
  species coverage rejects the domain opt-in. This is endpoint bookkeeping,
  not a reconstruction prior or a source-to-boundary conservation certificate;
  production activation guards and writer/replay contracts remain unchanged.
- Activation/removal, inactive NaN exclusion, incomplete-species rejection and
  legacy-equivalence tests pass at O0/O2 in `scratch/domain_budget_literal.uELyIR`.
  A literal column oracle verifies `delta M = A*delta PS/g`: the new 2510 Pa
  cell takes 2499.125 Pa from the old bottom cell, leaving only 10.875 Pa of
  added column thickness. Counting the whole new cell as a boundary increment
  is incorrect. This test is included in the existing checked/optimized runner.
- Existing geometry-budget, hydrostatic-state and remap tests pass at O0/O2
  after this change in `scratch/domain_budget_final.nmKAYR`. The remap test now
  roundcasts actual production results to float32 and independently rebuilds
  dry mass from pressure mass. Nonzero storage errors satisfy derived bounds
  for dry mass, six species masses and reduced enthalpy; an exactly representable
  identity survives storage. This remains a scalar storage simulation, not an
  integrated state transaction.
- The actual WPS checker now compares PSFC against candidate surface pressure
  when present, requires it under the supported boundary/pressure contracts,
  and retains the legacy fallback only without that requirement. The existing
  `scratch/surface_phi_handoff.gD2eal` passes all 235 records and nine mutations,
  including changed-PS acceptance and stale-background-PS rejection. No existing
  WPS, metgrid or native file was modified.

### Explicit pressure-domain state transition (2026-09-09)

- `apply_pressure_domain_transition` now stages one newly exposed pressure
  center from a complete explicit prior, conservatively repartitions old
  column content plus the boundary strip, and preserves the old hydrostatic
  residual. Stored dry mass, six species and reduced enthalpy have bounded
  rounding checks; old winds and untouched columns remain unchanged.
- Focused checked/optimized tests pass in
  `scratch/domain_transition_final.09TKsX`, including two-column isolation,
  retained phase-step dry-mass rounding, invalid inputs and atomic rollback.
- This is not yet connected to the actual host pressure solve, pipeline or
  changed-domain writer/replay. CP01 and FG1 remain open. Existing
  LAPSPREP/WPS/metgrid/real file connections remain the integration path.
- The full pinned unit runner subsequently passes in
  `scratch/pressure_transition_unit.log`, including rejection of stale
  inactive `balance_beta`. Canonical validation already rejects that input;
  no duplicate cleanup was added to the transition.
- `read_real_shadow_state` can now return optional retained LW3 omega from
  the same read, before domain masking. It preserves validity/quality/time,
  leaves canonical output unchanged, and publishes nothing on ingest failure.
  The pinned I/O suite passes with valid/missing/out-of-range outside-domain
  markers and stale-output rejection in
  `scratch/retained_omega_reader_tests.20260908T181109Z.log`. No omega field
  was added to WPS, and no second LW3 read was introduced.
- `build_pressure_transition_prior` reuses retained WPS slabs plus that
  omega field to construct a complete one-center reconstruction input.
  Pressure order, time, frame, missing/QC omega and authority are checked;
  old fields remain unchanged and changed prior geometry gets its own mass
  denominator. The immutable background still supplies conservative donors.
- Constructor-to-transition tests pass at O0/O2 in
  `scratch/pressure_transition_prior_verified.log`. A real-reader-style masked
  pressure coordinate exposed a transition bug: the newly active coordinate
  metadata was not promoted. The transition now copies that metadata only
  at the newly represented center. The earlier failing run is retained in
  `scratch/pressure_transition_prior_final.log`.
- Actual LAPSPREP host-root/pipeline/writer integration of the transition
  remains pending; these tests do not certify a changed-domain native run.
- The complete pinned unit suite passes after the coordinate fix and new
  constructor tests: `scratch/pressure_transition_connected_unit.log`.
  The next pipeline integration must preserve the existing original-to-thermo
  hydrostatic increment before domain transition; replacing that step with a
  transition referenced only to post-thermo T/q would omit its Phi correction.
  WPS conversion remains at the adapter boundary, not inside the physics core.
- The in-memory pipeline now accepts an explicit transition seed after the
  original-to-thermo Phi correction. Positive requests can mix zero and one
  newly active center per column; both use the same disjoint boundary-strip
  remap, and existing wind/target metadata is retained on old cells.
  Mixed-column, fully active bottom, pipeline and existing WPS mapping tests
  pass at pinned O0/O2: `scratch/pressure_mixed_transition_verified.log`.
  The preceding failure in `scratch/pressure_mixed_transition_pipeline.log`
  exposed masked pressure coordinates in the legacy same-domain geometry
  refresh; coordinate availability is now temporary and metadata is restored.
  Actual host-root connection and changed-domain serialization/replay remain
  pending. The writer explicitly rejects transition seeds until that extension
  is implemented; CP01 and operational promotion remain open/blocked.
- Final mapped source-grid host residual evaluation is now wired into the
  LAPSPREP host-pressure experiment. It uses each state's actual T/Q/height,
  not the proposal solver's fixed-profile approximation; no native closure or
  root-convergence authority is granted by this diagnostic value.
  O0/O2 wiring and crossing/order tests pass in
  `scratch/source_host_residual_mapping_crossing_ref.log` (direct column
  reference, not an independent physics verifier). The pinned full LAPSPREP
  build is `scratch/upstream_lapsprep_build.SIVgXe/klps_anal_prep.exe`, SHA-256
  `dbe0c9b027b63f44e2b6458a90736db94387417134d4f055bfc2fa16af65f16f`.
  The next host solve must drive this final-state residual to its declared
  tolerance before publication; the existing scalar proposal alone cannot
  certify a remapped candidate. No new actual native experiment was run here.
- Subsequent actual HOST_PSFC execution now converges using the bounded
  original-input pipeline loop. A terrain-excluded 1000-hPa center at column
  (207,64) exposed an incorrect pressure-only rejection: its original PS was
  already above 1000 hPa while its height remained below terrain. Positive
  pressure changes now retain that existing domain; genuinely new pressure
  crossings still require the explicit transition. Existing transition tests
  pass at pinned O0/O2 in `scratch/terrain_transition_direct.EayuU2`.
- Clean pinned LAPSPREP build `scratch/upstream_lapsprep_build.RJ1E3D`
  passed its source-hash gate; binary SHA-256 is
  `190cf60018db5aeb968dd021a76f5ff7d6d0b3e75739bef2476a783c2e4787e7`.
  Actual run `scratch/host_coupled_pressure.Jr8ubu/host_psfc_run.log`
  records residuals 32.723912, 1.226979, 0.025259, and 0.004070 Pa;
  convergence occurs at iteration 4 with maximum PS increment 33.328125 Pa.
  This is source-grid host-vapor pressure closure, not native conservation.
  The producer exits 1 at the explicit transition-seed writer authority gate
  (`shadow_write_contract_reason=9`). No WPS or SHADOW file is produced;
  LT1/LQ3/LW3/LWC/LSX hashes are unchanged. The next implementation is seed
  serialization and changed-domain replay in the existing writer/verifier.
  CP01 remains OPEN; this run does not certify FG1 or science promotion.
- The added terrain-exclusion regression passes with the complete pinned
  O0/O2 pressure/WPS runner in
  `scratch/pressure_transition_terrain_excluded_final.log`. It exercises the
  actual stored pressure increment, constructor, selected-column rebase,
  conservative transition and pipeline; the excluded cell remains excluded,
  its thermodynamic metadata is retained, geometry mass changes only by
  `area * delta_PS / g`, and operational input remains identical.
- The existing NetCDF writer now has a `pressure_transition_seed_v1` payload:
  separate candidate/seed domains, seed PS and dry mass, and 12 fields with
  value/valid/quality/source/time metadata. Existing field writers are reused;
  no new file-link or publication path is introduced. Producer replay restores
  the original-domain request before rebuilding added support, and compares
  final state, stage results, and analysis/thermodynamic/geometry budgets.
  Same-domain and one-center payloads pass Fortran-to-Python readback and
  producer replay checks at O0/O2 in
  `scratch/real_shadow_transition_extension_final.log`; consumed-seed and
  budget mutations are rejected. Portable Python contracts also pass in
  `scratch/pressure_transition_python_contracts.log`.
- Full transition artifacts remain explicitly rejected by the writer and main
  independent validator. Payload validity is not independent physics closure.
  Next: reconstruct the original radar proposal before thermo/transition
  (final remapped precipitation cannot stand in for that proposal), then bind
  candidate-domain geometry, water/enthalpy, continuity and geostrophic checks.
  Only after those checks are connected should the existing writer gate open.
- Radar replay now exposes the pre-thermo proposal with explicit background
  or outer-evaluation selection. Existing artifact behavior passes the pinned
  I/O suite (`scratch/radar_proposal_io_regressions.log`); portable contracts
  pass in `scratch/pressure_proposal_python_contracts_final.log`.
  The independent pressure-overlap remap matches checked/optimized Fortran
  fixtures in `scratch/pressure_column_remap_crosslang.qjp4dR`, with separate
  dry-mass, species and reduced-enthalpy error scales. These are components of
  changed-domain replay, not full candidate/native acceptance; CP01 stays OPEN.
- Independent pre-remap thermodynamics now solves temperature-space water/
  reduced-enthalpy equilibrium rather than copying the production transfer
  solve. Twelve tests cover liquid/ice adjustment, reservoir exhaustion,
  infeasible states, and thermo -> canonical float32 storage -> remap.
  Portable contracts pass (`scratch/pressure_thermo_reference_contracts.log`).
  Integration must retain proposal-side dry mass for existing donors; the
  added boundary strip uses `area * delta_PS / g / (1 + sum(prior_species))`,
  not the seed cell's full dry mass. Final changed-domain validation remains
  unconnected, so the full transition writer gate is unchanged.
- The existing thermo validator now reconstructs stored T/species and
  proposal-side dry mass through the independent temperature solve, while
  retaining its budget/saturation/metadata checks. Fifteen focused tests and
  portable contracts pass (`scratch/thermo_donor_replay_python.log`). This
  closes the reusable pre-remap thermo calculation, not transition-domain
  geometry or native handoff acceptance.
  The full pinned Intel unit runner and the dedicated I/O runner both exit 0
  (`scratch/pressure_thermo_reference_units.log`,
  `scratch/thermo_donor_replay_io.log`), including legacy/outer thermo and
  malformed-input regressions. No transition artifact authority is granted.
- Surface-pressure replay now adds the explicit boundary strip before remap;
  18 calculation tests and actual Fortran same-domain/one-center O0/O2
  fixtures pass (`scratch/surface_pressure_reference.k0IlDD`). The checker
  separates conserved remap mass from final float32-state mass refresh.
  Six geometry tests verify candidate-domain interfaces, terrain exclusions,
  authorization and crossing limits. The main geometry reader receives a
  candidate mask only from a clean seed payload; original-domain checks stay
  unchanged. Pinned I/O regression exits 0 in
  `scratch/surface_transition_geometry_io.log`. Full transition acceptance
  remains gated pending final thermo/remap, union-ledger and residual binding.
- Balance-stage wind reconstruction now retains original old-cell winds and
  uses explicit seed winds only on added cells. LAPSPREP uses that diagnostic
  state for its before-residual; Python separates candidate-stage residuals
  from original-geometry residuals/fluxes. Six Python tests, pinned O0/O2
  `test_prebalance_wind`, portable contracts and I/O regression pass.
  The full LAPSPREP build `scratch/upstream_lapsprep_build.LFHCvo` passes
  source-hash/link checks (binary SHA256
  `636fac8e68c142e5f88b94a3ee25f89ffd797c64c2ae3233b23d5adbe568cd04`).
  Actual same-input replay `scratch/prebalance_host_run.EFbDIc` converges in
  four iterations to 0.0040697997 Pa and reaches writer reason 9; exit 1 is
  the remaining transition acceptance gate, not successful generation.
  Five direct-input hashes are unchanged; no WPS/SHADOW output exists.
  CP01 remains OPEN; next is post-thermo/final-remap and union-ledger binding.
- Geometry ledger arithmetic now uses one before/after union-domain kernel;
  absent-side mass/species are zeroed before arithmetic. Five analytic tests
  cover additions/removals, missing placeholders, decomposition and stage
  telescoping; the related 36-test set and portable contracts pass. Final
  pinned I/O regression exits 0 (`scratch/union_geometry_ledger_final_io.log`).
  The ordinary validator uses the kernel without changing its accepted scope.
  Transition wiring still needs post-thermo replay values and their float32
  uncertainty propagated into the final remap/ledger comparison. CP01 OPEN;
  no transition generation or native/science acceptance is claimed.
- Reproduced and fixed an upper-cell dry-mass validator mismatch: production
  refreshes every active cell in a changed-PS column, not just changed-dp
  cells. The added real-writer fixture fails before the fix
  (`scratch/upper_column_mass_red.log`) and passes afterward, including an
  isolated pre-thermo-denominator mutation (`scratch/upper_column_mass_final_io.log`).
  Array-level post-thermo pressure replay now reuses the existing boundary-strip
  remapper for positive requests, refreshes negative-request columns, and keeps
  untouched columns exact. The related 38 tests, portable contracts and saved
  Fortran O0/O2 transition fixtures pass. Main transition replay/uncertainty
  binding is still pending; writer authority and CP01 OPEN are unchanged.
- Original-input radar/thermo/remap replay now reports final temperature,
  six species and dry-mass residuals without granting acceptance. The test-only
  same-domain file reuses existing serializers; O0/O2 residuals are zero and
  isolated final-state mutations are detected (`scratch/transition_replay_telemetry_io.log`).
  The full pinned Intel/NetCDF I/O suite exits 0; ten focused tests and portable
  Python contracts pass. This is not an
  added-cell production replay: uncertainty propagation, union-ledger binding
  and transition acceptance remain open. CP01 OPEN; no KG checkpoint update.
- Transition geometry-ledger checks now start from independently replayed
  post-thermo T/species and retained proposal dry mass, and end at serialized
  candidate arrays over the union domain. Independent proposal validity feeds
  old-cell counts; source/quality usability separately controls represented
  precipitation. Added-cell algebra, forged ledgers, donor substitution and
  incomplete-donor rejection pass in the 14-test focused set. The pinned I/O
  binding regression exits 0 (`scratch/transition_ledger_binding_io.log`);
  subsequent source/quality masking passes focused and portable contracts
  (`scratch/transition_ledger_binding_python.log`). Strict arithmetic tolerance
  and the production transition block remain unchanged. Root/retrieval/storage
  uncertainty, remaining thermo/Phi checks and native acceptance are not closed.
- Ordinary and transition paths now share the thermo-stage budget checker.
  The transition check uses independent proposal/post-thermo fields and retained
  dry mass, not final remapped fields; unselected placeholders are excluded
  before arithmetic. Hand-calculated phase totals, malformed/forged ledgers and
  mass substitution pass in the 15-test focused set. Pinned I/O and portable
  contracts exit 0 (`scratch/transition_thermo_budget_io.log`,
  `scratch/transition_thermo_budget_python.log`). Final-state thermo metadata,
  saturation/support scopes and replay error bounds still need transition-aware
  handling. CP01 OPEN; no production authority or checkpoint promotion.
- Transition validation now builds the original-input replay once and reuses
  it for thermo-stage budgets and final remap checks. Final T/species mutations
  leave the independently reconstructed thermo budget unchanged but fail the
  final-state check. Derived precipitation quality follows the existing
  producer's observed/descendant rules. A temperature-indexing regression was
  reproduced and fixed; 15 focused tests, portable contracts and pinned Intel
  O0/O2 I/O checks pass (`scratch/transition_thermo_scope_python.log`,
  `scratch/transition_thermo_scope_fixed_io.log`). No-echo safeguards remain
  unchanged. Transition uncertainty, Phi and native acceptance remain open;
  CP01 OPEN, with no KG checkpoint update or production promotion.
- Added an independent positive-PS Phi replay preserving separate old-cell
  and added-cell seed residuals. Fresh pinned O0/O2 transition fixtures match
  stored Phi exactly in both same-domain and one-center cases
  (`scratch/transition_phi_reference.IRV3kg`). The existing unit runner now
  requires Phi records; corrupted/NaN Phi and omitted records are rejected.
  The 32-test focused set and portable contracts pass
  (`scratch/transition_phi_reference_python.log`). This tests the transition
  stage, not original-input full-pipeline acceptance. The main Phi validator
  still needs the intermediate float32 Phi stage and candidate-domain/seed
  provenance wiring. CP01 OPEN; production transition block unchanged.
- Connected the shared original-input replay to Phi validation. One common
  hydrostatic loop retains the intermediate float32 store, then uses the
  positive-PS reference on candidate-domain cells. Added-cell seed provenance,
  immutable pressure centers, explicit support and terrain clearance are checked.
  A fixed-offset regression rejects collapsing the two float32 stages. Pinned
  I/O passes (`scratch/transition_phi_scope_io.log`); final guard/scope checks
  pass on retained O0/O2 fixtures (`scratch/transition_phi_io.JpOGZ2`,
  `scratch/transition_phi_final_o2.WB0VOz`). Fourteen focused tests and portable
  contracts pass (`scratch/transition_phi_scope_final_python.log`). The new-cell
  NetCDF scope case is a numerical copy, not a full published transition.
  Fixed-domain geostrophic assessment still needs a paired producer/verifier
  extension; uncertainty and native acceptance remain open. CP01 OPEN, no KG
  checkpoint update, and the production transition block is unchanged.
- Extended the existing geostrophic assessor to the candidate domain: retained
  cells use immutable original Phi/u/v; added bottom cells use the explicit
  transition seed. Pressure metadata may change only at those added cells, and
  their Phi support must be declared. The existing residual loop is reused;
  ordinary diagnostics avoid a full-state copy. The paired v3 writer/verifier
  contract labels the original-plus-seed reference explicitly, without science
  authority. Pinned O0/O2 analytic and rejection tests pass on the final core
  (`scratch/transition_geo_checked.xsNY3U`), including negative same-domain PS
  changes, seed provenance and missing support. Portable contracts and 12 focused
  Python tests pass (`scratch/transition_geostrophic_python.log`). The full
  Intel/NetCDF I/O suite passes (`scratch/transition_geostrophic_io.log`); the
  final equivalent baseline-copy simplification was subsequently checked by
  the focused O0/O2 tests. The upgraded same-domain NetCDF probe is a numerical
  copy, not an executed production v3 publication. Full transition publication,
  uncertainty and native acceptance remain open. CP01 OPEN; no KG checkpoint
  update or operational promotion.
  Review boundary: original inactive-cell pressure valid/quality/source metadata
  are not serialized, so their cross-state identity is currently checked by the
  Fortran producer only, not independently replayed by Python.
- Closed that serialized pressure-metadata gap in transition payload v2 using
  the existing full-field writer. Background/candidate pressure values, units,
  time, validity, quality and source now reach the independent reader. Non-added
  cells, including inactive cells, retain exact original metadata. The actual
  Fortran one-center fixture exposed the added-cell source rule: seed source
  OR COLUMN_PHYSICS (not seed source alone). Both the independent reader and
  geostrophic assessor now enforce that rule; seed valid/quality remain unchanged.
  Legacy v1 remains readable without claiming this new evidence. Final pinned
  O0/O2 geostrophic tests pass (`scratch/transition_pressure_provenance.gbN8TU`),
  as do v2 mutations, portable Python contracts and full Intel/NetCDF I/O
  (`scratch/transition_pressure_metadata_python.log`,
  `scratch/transition_pressure_metadata_io.log`). The production transition
  block remains intact. Next physical work must distinguish the seed's stored
  full-cell mass from the actual boundary-strip donor and verify the remaining
  replay uncertainty/native mass constraints. CP01 OPEN; no KG checkpoint update.

### Independent transition seed mass validation (2026-09-09)

- Connected an independent full-cell seed mass check to original-input replay.
  Seed geometry is reconstructed from its own stored surface pressure, immutable
  pressure centers and domain. Unchanged pressure-mass cells retain original
  background dry mass; changed cells use the full seed pressure mass divided by
  `1 + sum(seed_species)`, matching the constructor contract. This full-cell
  mass is separate from the remap donor strip `area * delta_PS / g / (1 + sum(q))`.
- Analytic and mutation tests cover retained donors, changed cells and the large
  difference between full-cell and boundary-strip mass. Full-file seed-mass
  mutation is rejected before physical replay. The new check exposed a numerical
  probe that copied post-thermo candidate mass into an unchanged seed metric;
  the probe now preserves the original donor, without relaxing the check.
- Portable Python contracts and the complete pinned Intel/NetCDF I/O runner
  both exit 0 (`scratch/transition_seed_mass_python_final.log`,
  `scratch/transition_seed_mass_io_final.log`). Compilation used fresh scratch
  directories and `tests/intel_toolchain.sh`. O0/O2 probe T/species/dry-mass
  replay residuals are zero. Earlier failed logs are retained separately.
- `scratch/transition_seed_mass_receipt.json` records the final logs and source
  inventory comparison: 204 of 205 files remained unchanged; a concurrent edit
  refactored the Python validator geometry calculation during the final run.
  Therefore this run is not a sealed final-source receipt. Independent AI review
  found no blocking issue in the reviewed seed-mass scope. This local dirty-tree
  evidence is not a clean release or native acceptance.
- The production transition gate remains closed. Full replay uncertainty,
  native mass constraints and CP01 closure remain open; no canonical gate or
  operational promotion was changed.

### Seed physical binding correction (2026-09-09)

- Supersedes the generic retained-donor validation claim above. Constructor
  provenance alone does not establish a seed's physical mass consistency.
  The independent reader now checks `md * (1 + sum(stored species))` against
  the seed's own pressure-cell mass, allowing only summed float32 half-ULP
  storage error plus float64 arithmetic error. Boundary-strip donation remains
  separate; production constructor and remap equations are unchanged.
- Removed the numerical probe's artificial replacement of post-thermo seed
  mass with original mass. The unmodified physical candidate is now checked.
  Candidate and seed geometry reuse one independent pressure-cell calculation;
  masked domains are rejected. Nine analytic/adversarial geometry scenarios
  are included in the existing portable runner.
- Validation: 29 focused pytest tests passed; portable Python contracts and
  the complete pinned Intel/NetCDF I/O suite exited 0. Both O0/O2 full-file
  probes report zero T/species/dry-mass replay residuals. Logs:
  `scratch/seed_physical_binding_python.log` and
  `scratch/seed_physical_binding_io.log`. These are local dirty-tree tests,
  not a sealed release, real forecast experiment or native acceptance.
- CP01 remains OPEN. Next work is the remaining coupled replay error bounds
  and final native mass/continuity constraints, not additional bookkeeping.
  Production transition rejection and separate promotion approval remain;
  no completed checkpoint means no KG refresh.

### Actual coupled transition cross-language check (2026-09-09)

- The existing Fortran same-domain and one-added-center cases now execute
  nonzero liquid saturation adjustment (RH 0.8) before pressure remapping.
  Their test-only NetCDF payload includes original/final T, six species,
  dry mass, PS and the accepted thermo request; science authority stays zero.
- The existing Python payload test independently reconstructs pressure cells,
  thermo equilibrium and conservative remap from original input. O0 and O2
  both match final stored T/species exactly and dry mass within float64
  arithmetic tolerance. Final T, vapor and dry-mass mutations are rejected.
- Next production change is staged writer lineage, not another residual
  threshold: `thermo_candidate_is_coherent` still takes proposal precipitation
  from final output, `candidate_result_is_coherent` still measures new-cell
  winds against raw background, and `pressure_geopotential_request_valid`
  still excludes new-cell support. Reuse the accepted transition/pre-balance
  state to fix those assumptions before lifting any serialization gate.
- Logs: `scratch/coupled_transition_crosslang_io.log` and
  `scratch/coupled_transition_crosslang_python.log`. This is local numerical
  evidence, not native or forecast acceptance. CP01 remains OPEN; production
  transition rejection and separate operational promotion remain unchanged.

### Transition writer integration (2026-09-09)

- SHADOW diagnostic serialization now accepts a canonical transition seed only
  when the existing producer pipeline reproduces the complete candidate,
  operational identity, stage masks and budgets. Fixed-domain shortcuts are
  retained for ordinary cases; they are not used to infer pre-remap species or
  new-cell winds from final transition output. Manufactured seed data remain
  forbidden, and transition Phi support uses the retained-plus-added domain.
- Actual full writer tests exposed two stale independent-reader assumptions:
  positive PS metadata inherits the seed before adding column-physics source;
  column/thermo changed masks describe the pre-remap stage, not new-cell or
  remap changes. Both were corrected using the existing independent replay,
  without increasing numerical tolerances.
- O0/O2 same-domain and one-center full files pass all independent checks
  except the deliberate transition publication block. They remain UNBOUND,
  science-unassessed and promotion-ineligible; final T/species/dry-mass replay
  errors are zero. Seed/final-state/Phi/support/request/operational mutations
  are rejected before writing. Reader mutations additionally cover stage-mask
  misclassification and lost seed PS provenance.
- Four retained artifacts: `scratch/full_transition_evidence.pIX3wf/o0/` and
  `scratch/full_transition_evidence.pIX3wf/o2/`. Logs:
  `scratch/transition_full_writer_io_final.log` and
  `scratch/transition_full_writer_python.log`; earlier failed runs remain as
  `transition_full_writer_io.log` and `transition_full_writer_io_retry.log`.
- This supersedes the earlier blanket **serialization** rejection, not the
  independent publication block or operational approval. It does not certify
  a full native product. Next: rebuild/replay the actual isolated LAPSPREP
  pressure-analysis case and inspect its complete diagnostic/native handoff.
  CP01 remains OPEN; no KG checkpoint refresh.

### Remap interval propagation and CP05 input inventory (2026-09-09)

- Added an independent pressure-column interval reference for explicit donor
  mass, temperature and six-species uncertainty. Outward-rounded pressure
  overlap, extensive sums and positive quotient bounds enclose the dry mass,
  species mixing ratios and heat-capacity-weighted temperature. Input endpoint
  arithmetic is also outward-rounded; masked errors, negative species intervals
  and unbounded mass denominators are rejected. No existing validator tolerance
  or production authority gate was changed.
- The focused suite has 24 passing tests, including hand-calculated extreme
  states, exact Fraction endpoint checks, arithmetic-only envelopes and rejection
  cases. Fresh pinned Intel O0/O2 remap fixtures lie inside the independently
  computed envelopes. Portable Python contracts also exit 0.
- Sources were tested in the owned snapshot
  `scratch/cp01_replay_work.lyn33uac`; the final two-file patch was applied only
  after verifying live files still matched its baseline. The receipt and
  retained O0/O2 fixtures are under that snapshot's `scratch/` directory:
  `remap_bounds_receipt.json` and the path in `remap_bounds_run_path.txt`.
  Independent review found and resolved negative-species interval clipping;
  the final focused and O0/O2 fixture checks pass after that correction.
- This propagates supplied donor uncertainties; it does not yet establish their
  thermo root, radar retrieval/storage or Phi bounds. Those certificates and
  full original-input transition acceptance remain required before CP01 closure.
- Parallel CP05 preparation inspected the explicitly referenced 13–15 UTC
  inputs in `scratch/cp05_observation_inventory.OyC3xs/inventory.json`: 33 files,
  29 present, 4 missing, 12 NetCDF headers, plus a checked Barnes release
  manifest. Beam/wavelength/dealias/uncertainty, wind-frame/storm-motion and
  independent-event forecast provenance remain unverified in that bounded set.
  This is an input inventory, not CP05 or CP08 PASS.

### Fixed-input thermo equilibrium certificate and radar lineage (2026-09-09)

- Added an independent fixed-input six-species equilibrium certificate. Directed
  Decimal interval arithmetic encloses transfer residuals, the ideal equilibrium
  temperature/species and canonical float32 storage. Ambiguous physical endpoint
  signs are rejected; condensate exhaustion requires a certified active reservoir
  bound. The capped saturation-pressure branch is enclosed monotonically.
- Final validation: 27 focused tests pass, both retained pinned Intel O0/O2
  saturation fixtures pass (five valid and one rejected case each), and the
  portable Python contract suite exits 0. The three merged files match the
  tested snapshot byte for byte; live baseline equality was checked first.
- This certifies the ideal physical law for exact supplied float64 inputs. It
  does not certify the production solver's finite stopping error, uncertain
  retrieval inputs, Phi propagation, native conversion or science acceptance.
  The retained Intel fixture comparisons establish storage containment only for
  those fixtures. Full transition acceptance still requires the missing bounds
  and original-input replay; CP01 remains IN_PROGRESS / NOT_RUN.
- Independent review corrected saturation-pressure cap enclosure and physical
  endpoint certification. Work was isolated in
  `scratch/cp01_thermo_bounds.m7vt8uih`. The source/fixture hashes, final checks
  and merge identity are retained in that snapshot's
  `scratch/thermo_certificate_receipt.json`.
- The parallel CP05 provenance addendum is
  `scratch/cp05_provenance.Zp7oPS/provenance_addendum.json`. UF/RSL headers
  contain beam width and wavelength, but the inspected UF-to-NetCDF path omits
  them. Runtime Nyquist/frame/dealias support and a nominal wind-error weight
  do not establish case-bound observation uncertainty or frame provenance.
  Raw case inputs, actual beam/wavelength values, runtime flags and storm-motion
  lineage remain unverified in the bounded search. CP05/CP08 are not closed.

### Actual signed-pressure replay correction (2026-09-09)

- Actual isolated LAPSPREP completed in `scratch/transition_actual_run.Ex6c5w`;
  its five upstream inputs retained their pre-run hashes. This is not native
  or science acceptance.
- Corrected two independent-reader assumptions without changing production
  physics: the positive-transition seed retains background PS on negative
  requests, and the geometry-stage mask includes complete pressure-changed
  columns even when the final stored Phi is unchanged.
- The actual recheck in `validation_signed_pressure.json` no longer reports
  seed-pressure identity, geostrophic-context, or overall-mask failures.
  Final species/dry-mass replay and three geometry-ledger checks still fail;
  the explicit transition publication block remains. Do not hand this rejected
  candidate to the native acceptance path. CP01 remains open.
- `scratch/actual_transition_signed_io.log`: fresh pinned Intel O0/O2 full
  I/O suite exited 0. Read-only WPS inspection also matched all 200 mapped
  pressure records on the candidate domain (including three newly active cells)
  and PSFC exactly to the same-run sidecar. Neither check closes physical replay.

### Actual thermo storage residual removed (2026-09-09)

- Replaced the mixture solver's premature tolerance exit with transfer-root
  convergence; retained the iteration cap, atomic transfer and physical checks.
  Nine actual-cell float32 regressions pass independently under pinned O0/O2.
- Fresh LAPSPREP build `scratch/upstream_lapsprep_build.HEntOF` and isolated run
  `scratch/actual_thermo_root_run.SuqsSJ` exited 0; upstream hashes are unchanged.
  The run's `validation.json` reports zero error for T, all six water species
  and dry mass, with no geometry-ledger failures. Only the explicit transition
  publication block remains. This is not native/science/operational acceptance.
- Added a storage-stable bracket exit for near-zero transfers: both endpoints
  must satisfy the existing tight bracket/residual criteria and produce identical
  float32 states through the transfer kernel. The 80-iteration cap still rejects
  nonconvergence. Pinned O0/O2 now pass 15 valid / 1 invalid scalar cases.
- Final build `scratch/upstream_lapsprep_build.qf63eH` and run
  `scratch/thermo_storage_stable_run.Z3KSCv` exited 0 with unchanged inputs.
  All 228 diagnostic arrays and the entire WPS file match the preceding
  zero-residual run exactly; final independent validation is run separately.
- Final `Z3KSCv/validation.json` confirms all eight replay errors are zero and
  only the explicit transition block remains. The next numerical implementation
  is to consume complete clean replay evidence with a defined exact-storage
  criterion; generation, native, science and promotion approvals stay separate.

### Exact stored-state transition criterion

- `exact_stored_state_v1` is single-pass numerical-content acceptance, not a
  forecast or uncertainty certificate. It requires complete clean input,
  geometry, radar, thermo/ledger, Phi and geostrophic checks and all eight replay
  residuals (T, six species, dry mass) to be finite and exactly zero at their
  serialized precision. Missing or nonzero residuals do not pass; no tolerance
  was enlarged. Other physically plausible rounding paths may remain rejected.
- Numerical probes are excluded from candidate acceptance. A passing file
  remains UNBOUND, non-science and ineligible for promotion; generation/native
  handoff and final coupled/science requirements remain separate open gates.
- Final actual `Z3KSCv/validation_exact_gate.json` exits 0: numerical VALID,
  independent transition replay true, UNBOUND/non-science/non-promotion retained.
  Portable contracts and fresh pinned Intel O0/O2 I/O suites exit 0
  (`scratch/transition_exact_gate_python.log`, `transition_exact_gate_io_final.log`).

### Transition candidate reaches the existing research native path

- Reused existing metgrid/real binaries, namelists and input links; only the
  LAPS input changed to the validated transition WPS, in new output directories.
  `scratch/metgrid13_transition.ndHi79` and `scratch/real13_transition.MHJU9Q`
  both completed successfully. No operational input/output was replaced.
- Independent native diagnostics pass: maximum layer closure 0.002500423 Pa,
  column closure 0.000109374 Pa, host surface-pressure replay 0.009821148 Pa,
  and dry surface-pressure replay 0.013297083 Pa. Reports are the native run's
  `hybrid-geometry.json` and `host-pressure-replay.json`.
- This is one research native handoff, not conservation/science or operational
  binary equivalence. A fresh same-input OFF comparison, further native-state
  coupling checks and the remaining CP01 requirements are still open.

### Precipitation provenance and fresh same-input OFF comparison

- Reused radar replay to reconstruct exact precipitation source metadata;
  retained cells cannot acquire unrelated dynamic/boundary source bits, and
  newly represented cells retain the explicit column-physics source contract.
  Shared the remapped-column mask with phase checks; no extra validation layer.
  Portable tests and four retained O0/O2 fixtures pass, including source
  mutations (`scratch/transition_precip_source_python.log` and
  `scratch/transition_precip_source_fixtures.log`).
- Fresh OFF uses the same LAPSPREP binary and five unchanged upstream inputs:
  `scratch/transition_fresh_off.b5KQjD`,
  `scratch/metgrid13_fresh_off.tEo3hs`, and
  `scratch/real13_fresh_off.pYpsN8` all exit 0. Namelists match the candidate;
  existing executable/static/background links are reused, outputs separated.
- Native geometry and host-pressure diagnostics pass. The existing paired
  checker reports candidate-minus-OFF dry mass -3,808,417.48 kg and total
  water -83,477,376,950.09 kg (`real13_fresh_off.pYpsN8/paired-candidate.json`).
  The water difference is dominated by composition, not the mass metric.
  This is a diagnostic decomposition, not conservation or science acceptance.
  Next: trace analysis increments through pressure-level, WPS/metgrid and
  native stages. CP01 remains open; no checkpoint or KG completion claimed.

### Same-input water-change attribution

- OFF/candidate WPS inventories match (235 records). All six water fields
  exactly match background/candidate diagnostic values on represented pressure
  cells. The omitted 1050/1100-hPa levels contain no above-ground cells.
- Independent pressure replay locates precipitation removal in 67,567 observed
  radar cells, with no changed non-radar cells: rain -1.80228525e10 kg,
  snow -6.30731214e10 kg, graupel -4.0567519e8 kg. This is the explicit
  observed-cell replacement, not transport loss. Thermo transfers approximately
  9.78088123e10 kg from cloud water to vapor without changing precipitation.
- The native total-water difference is -0.0884868% of OFF water; native rain
  and snow decrease 14.9919% and 16.5706%. Pressure/native totals use different
  domains and mass/vertical metrics; their difference is not a conservation
  residual or a proved interpolation loss.
- Metgrid QI/UU/VV are unchanged. Native QICE and wind nevertheless change;
  real interpolates using changed dry-pressure coordinates. Native wind RMS
  differences are U=0.0147173 and V=0.0172843 m/s, but lower-level extrema are
  4.8802/6.7365 m/s. The first stencil reconstruction used a temporary SLP
  dry-pressure rewrite that real later restores, and the wrong target-pressure
  stage. Its apparent unchanged stencil is not valid exclusion evidence.
  U/V interpolation uses restored pd_gc and the then-current half-level pb;
  pb is rebuilt again before output. Actual entry/exit arrays must establish
  the stencil behavior. No interpolation setting was tuned.

### KDM6 missing graupel volume: reproduced failure and isolated fix

- All 817 positive native graupel cells exceed KDM6's qcrmin while QIB is zero.
  Exact extracted ProgB_param/GAMMLN/RGMMA with pinned ifx -fpe0 reproduces
  divide-by-zero (exit 134) at qg=1.76653848e-4, QIB=0. The zero-mass control
  exits 0. Evidence: `/NHNHOME/WORKSPACE/26weather002_A/yhlee/kdm6_qib_probe.545m3r`.
- `patches/kdm6_missing_graupel_volume.patch` initializes missing volume with
  qg/rho_mid before division, using the host's declared 400 kg/m3 density as
  an explicit research prior. It does not infer observed particle density or
  initialize missing number concentrations. Apply with `patch -p1 --fuzz=0`
  only inside an isolated copy of the host `phys` directory.
- The fresh patched copy is `scratch/kdm6_missing_volume.final.qM9lpQ`.
  `tests/test_kdm6_graupel_startup.f90` passes pinned O0/O2: missing volume,
  zero mass, supplied densities 200/700, unchanged mass and finite outputs.
  Final logs: `scratch/kdm6_volume_verify.V7c8xk/run_O0.log` and `run_O2.log`.
- Original host source and binaries are untouched; source SHA remains
  `02c9dc1f6711c9785d3c5841cbf2c14ebc454fa4628466407ae7f8879e965c5a`.
  This is a kernel fix, not a rebuilt full model, complete KDM6 initialization,
  native-state certification or forecast acceptance. Those remain open.

### Actual-case thermo diagnostics and asymmetric remap bounds (2026-09-09)

- Added `remap_pressure_column_intervals_reference` so explicit asymmetric
  donor endpoints, including a zero condensate lower bound, can feed the
  existing conservative interval equations. The absolute-error API delegates
  to the same implementation. Invalid, reversed, masked and nonphysical
  endpoints are rejected. A composition test carries independent thermo
  float32-storage intervals through the remapper.
- Added `thermo_output_certificate.py` for exact-input, exact-float32-output
  diagnostics: ideal discrepancy bounds, storage containment, directed vapor
  transfer residual and independent phase-water/mixture-enthalpy closure.
  Physical transfer bounds are checked before residual evaluation. Invalid
  transfer mutations and exhausted reservoirs cannot acquire a root-error
  claim. Independent review identified an out-of-domain saturation-pole
  overflow; physical gating and its concrete regression resolve it. These
  diagnostics do not introduce a production acceptance tolerance.
- Final focused tests: 37 PASS. Portable Python contracts: PASS, including
  the new diagnostic tests. Revised snapshot checkers also pass the retained
  pinned Intel O0/O2 saturation and remap fixtures; no Fortran compilation
  was required for this Python change. Five merged files exactly match the
  tested snapshot after live-baseline checks. Concurrent actual-case additions
  to `tests/check_saturation_reference.py` were preserved; the snapshot's
  fixture-checker changes were not merged.
- Work and receipt: `scratch/cp01_actual_bounds.vm5je21c/`, with
  `scratch/actual_bounds_receipt.json`. The retained actual artifact is
  `scratch/transition_actual_run.Ex6c5w/FILE:2026-08-16_13.shadow.nc`. A frozen
  replay reproduces its nine validator failures. It finds nine cloud-water
  mismatch cells in nine columns, all exactly one float32 ULP; maximum cloud
  difference is 5.820766091346741e-11 kg/kg dry air. Eight selected mismatch
  columns are saved in `scratch/actual_thermo_probe.npz` with JSON/hash context.
- In all eight retained mismatch cells, actual dry mass equals the independent
  calculation using its own stored species and supplied pressure geometry.
  The difference from replay dry mass is exactly reproduced by substituting
  replay species; the largest is 0.7253513336181641 kg. Five cells with
  identity pressure overlap are contained in the ideal float32-storage
  enclosure. This locates the discrepancy without declaring all remapped
  cells, input retrieval, stage ledgers or the complete transition verified.
- Early isolated extraction attempts lacked `pressure_radar_reference.py` and
  returned no replay. The successful run includes the frozen dependency set.
  Those replay hashes identify the diagnostic computation, not the producer
  build; producer source-to-binary identity remains a separate requirement.
  CP01 remains IN_PROGRESS / NOT_RUN; no canonical checkpoint or KG refresh.
- Conditional positive-strip propagation is now recorded in
  `scratch/propagated_selected_columns.json` within the same snapshot. All
  eight selected columns use positive same-domain strips; 158 active final
  cells have T/species and refreshed dry mass inside the propagated bounds.
  Boundary mass and final pressure/species mass quotients use directed Decimal
  arithmetic. Replay post-thermo dry mass, radar proposal, pressure geometry
  and supplied seeds remain fixed conditional inputs. This is not a proof
  of their lineage or a justification to remove the full-transition gate.
  The retained case's pressure/Phi context, changed-mask and geometry-ledger
  failures remain separate closure work.

### Independently bound exact replay and guarded native execution (2026-09-09)

- Frozen Python dependencies in `scratch/cp01_exact_replay_review._eta4b0x`
  independently validate the retained actual candidate: all eight stored-state
  residuals are exactly zero, numerical VALID, UNBOUND, science/promotion false.
  Four retained pinned O0/O2 transition fixtures pass. Five mutations (missing
  Phi, missing geostrophic group, one-ULP dry mass, one-ULP water and numerical
  probe marker) are rejected. See `actual_validation.json`, `contract_review.json`
  and frozen `source_hashes.json` in that directory.
- The HEntOF producer manifest audit found 346/347 current input matches and
  41/41 runtime matches; the changed input was the later storage-stable thermo
  solver. That retained build is not labelled a current-source build. However,
  parent SHA256 checks confirm that both WPS and sidecar of SuqsSJ and the later
  storage-stable Z3KSCv run are byte-identical. Older Ex6c5w one-ULP and geometry
  failures in historical diagnostic sections are not current candidate failures.
- Guarded execution in `scratch/native_handoff_stage.ymn6MM` completed metgrid
  and real successfully with fresh local outputs and all 34 manifest inputs
  unchanged. The script's STAGED_ONLY line is its initial preflight message;
  terminal model logs and `execution_receipt.json` establish actual execution.
- Independent hybrid algebra passes: maximum layer closure 0.002500423 Pa and
  column closure 0.000109374 Pa. Direct-QV/TAVGSFC host replay passes with
  surface and dry-surface residuals 0.0098211472 and 0.0132970822 Pa. Reports:
  `hybrid_algebra.json` and `native_hybrid_geometry.json` in the stage directory.
  Explicit research constants are g=9.81 and Rd=287. Native mass/EOS/metric,
  first-step KDM6 behavior, producer-bound frame/boundary and operational
  source/build equivalence are not established by these diagnostics.
- CP01 remains IN_PROGRESS/NOT_RUN; CP02–CP09 remain PLANNED/NOT_RUN and all
  45 mandatory requirements remain OPEN/NOT_RUN. Same-input OFF/native paired
  evidence and the remaining contracts are still required. No KG refresh or
  automatic canonical/science/promotion gate change accompanies this receipt.
- Independent repeat identity: new metgrid and wrfinput files are byte-identical
  to the separately retained ndHi79/MHJU9Q outputs; SHA256 pairs are saved in
  `native_handoff_stage.ymn6MM/repeated_execution_identity.json`. This confirms
  this repeated execution only, not operational-host or cross-platform parity.

### Paired native differences and KDM6 auxiliary coverage (2026-09-09)

- The fresh OFF native output `scratch/real13_fresh_off.pYpsN8/wrfinput_d01`
  completed successfully. Read-only comparison to the guarded candidate passes
  same-grid hybrid diagnostic checks; both inputs remain unchanged. The native
  diagnostic dry-mass difference is -3,808,417.4755 kg and represented six-species
  water difference is -83,477,376,950.0869 kg. Conservation is explicitly NOT
  assessed. Native maximum differences include T=3.5163574 K (stored potential
  temperature perturbation), U=4.8802071 m/s, V=6.7365394 m/s and PSFC=28.90625 Pa.
  Reports: `native_pair_diagnostic.json` and `native_pair_field_differences.json`
  in `scratch/native_handoff_stage.ymn6MM`.
- `scratch/off_candidate_identity_audit.vhd9Rq/REPORT.md` finds identical logged
  LAPSPREP options, same upstream root/time and matching five present input
  hashes, with optional lm2 absent in both runs. WPS UU/VV are unchanged while
  HGT/PSFC/T/species differ, so native wind changes are downstream differences,
  not direct analyzed wind increments. The comparison does not yet isolate the
  precise interpolation cause. The OFF producer lacks an executable receipt
  and both old runs lack per-run config snapshots; same-build causality must
  not be inferred from shared current paths. A privately staged OFF reproduction
  with explicit binary/config/pre-post input binding is the next evidence fix.
- KDM6 registry/driver tracing and current native field statistics are retained
  as `kdm6_mp37_aux_trace.json` and `.md` in the guarded stage. QNCCN, QNCLOUD,
  QNICE, QNRAIN and QIB all exist, are finite and identically zero. Source startup
  synthesizes CCN, but the inspected MP37 path has no mass-to-number fallback
  for the other number fields, and no mass-consistent QIB startup rule was found.
  Nonzero QGRAUP occurs in 817 cells. This does not prove a crash or a physical
  error; first-call runtime instrumentation and initialization policy remain
  required. The evidence is bound to current source/output hashes, not a complete
  operational source-to-binary certificate. No checkpoint status is promoted.

### Bound OFF reproduction closes the control-output identity gap (2026-09-09)

- Private run `scratch/off_qf63eH_run.yeYUmP` binds the qf63eH executable,
  pinned Intel environment and copied LAPSPREP configuration. All 121 staged
  input files match the source snapshot and remain identical after execution.
  `receipt/launch_receipt.final.txt` preserves command, hashes and scope.
- The comparable control is `CLOUD_BAL_SHADOW_EXPERIMENT=OFF`, with explicit
  scratch WPS output. It completes successfully and produces byte-identical
  WPS to `transition_fresh_off.b5KQjD` (SHA256 3501a1348d00d2ea1c8549600f03e4dbd9540d59cba55dee91d1ad89d1b88f3b).
  Parent independently checked WPS, config and pre/post/source manifest identity.
  Existing native paired diagnostics therefore have a reproducible OFF WPS input
  from this named binary/config, without repeating metgrid/real. This does not
  retroactively certify the historical OFF launch or operational equivalence.
- A preliminary plain-OFF attempt encountered a private read-only output path
  and failed safely. Its subsequent separate output has 129 records and remains
  labelled plain_off; it is not substituted for the comparable SHADOW-OFF control.
  No shared configuration or operational output was changed. The new receipt
  strengthens causal input identity but does not close native conservation,
  KDM6 startup, frame/boundary or CP01 as a whole.

### Literal KDM6 zero-volume probe and selected native wind branch (2026-09-09)

- Read-only inventory of the accessible KLBG 00/06/12 UTC wrfinput files finds
  MP37 with all five auxiliary fields and QGRAUP identically zero. Those cold
  initial fields do not supply a positive-volume policy for the new candidate.
  Evidence: `scratch/kdm6_background_inventory.4098sy1q/inventory.json`.
- The new candidate contains 817 cells with QGRAUP>1e-9 and QIB=0. Source
  `ProgB_param` divides QGRAUP by QIB before bounding density to [100,900] kg/m3,
  then reconstructs QIB from bounded density. Thus earlier startup notes must
  not be interpreted as absence of all process-time reconstruction.
- Literal unmodified GAMMLN/rgmma/ProgB_param extraction and the actual candidate
  column (i=30,j=114, zero based) are tested in fresh scratch with pinned Intel.
  All 22 graupel-bearing levels in this column meet the zero-divisor condition.
  Explicit -fpe3 completes with density maximum 900 kg/m3 and QIB maximum
  6.4651335378584918e-6. The pinned -fpe0 probe exits 134 at the original division
  with Intel error 73 (floating divide by zero). This is not a full KDM6 first
  call, nor proof that the installed forecast binary traps. Auxiliary startup
  policy and full-host behavior remain open; no positive fields were invented.
- Early rewritten/reduced probes are not literal-source evidence. Final proof
  uses the exact source slices in `scratch/kdm6_literal_source.egtpumhf` and
  `scratch/kdm6_progb_probe.V0h1Wp/receipt.json`. Parent independently confirms
  literal byte identity and all selected QRAIN/QSNOW/QGRAUP/QIB input values;
  hashes are in `parent_verified_receipt.json` in the probe directory.
- Selected native U/V replay isolates a sensitive source branch: the candidate
  surface-to-first-level dry-pressure gaps (500.3984 Pa U / 500.6641 Pa V) exceed
  the existing 500 Pa close-level filter, whereas OFF gaps (499.4453 / 496.2813)
  fall below it. Thus different levels are retained despite identical metgrid
  UU/VV. Selected U change is reproduced exactly; V change has 0.00122118 m/s
  residual. Full-column residual maxima are 1.5258789e-5 U and 0.00614548 V m/s.
  `scratch/native_wind_attribution_20260909/RECEIPT.md` is explicitly
  REPLAY_INCOMPLETE. Early large-mismatch outputs were diagnostic failures,
  not accepted attribution. Complete native interpolation and balance closure
  remain required; neither branch agreement nor pressure algebra establishes them.
- Next: resolve the zero-volume KDM6 contract without silently selecting an
  unapproved physical initialization, and complete original-source native wind
  replay before treating the observed increments as validated. CP01 remains
  IN_PROGRESS/NOT_RUN. No later checkpoint or science/promotion status changes.

### Reviewable zero-volume numerical guard (2026-09-09)

- Added `docs/patches/kdm6-zero-volume.patch` against the unchanged research
  host source. A read-only `git apply --check` passes. The shared host source
  and operational binaries are unchanged. This is a concrete research patch,
  not an applied host release or a scientific initialization-policy approval.
- For an exact zero divisor, the guard uses explicit IEEE sign inspection to
  select the original bounded masked-exception result; nonzero division and
  the existing clamp/reconstruction remain unchanged. An earlier SIGN-based
  guard failed negative-zero byte equivalence with the pinned compiler and
  was rejected. The final patch uses ieee_is_negative instead.
- Literal original versus repaired procedures are compiled in fresh scratch
  under pinned Intel at O0/O2. All 817 actual candidate zero-volume cells and
  10 boundary cases give byte-identical values in all 19 output arrays.
  Original -fpe3 sets division-by-zero; repaired -fpe0 completes with division,
  invalid and overflow flags clear and all outputs finite. Fixed common helper
  coefficients are used; this is not a full kdm6init/first-call execution.
- Evidence and exact compiler flags: `scratch/kdm6_zero_guard.hu0w47hl/receipt.json`.
  Independent Luna high review confirms source-patch/tested-procedure identity
  and the numerical scope. Nonzero subnormal-divisor overflow is unchanged.
  The later reproduction recipe is syntax-checked and creates new scratch
  outputs; recorded tests used the equivalent compiler commands directly.
- Concurrent missing-QIB experiments select the source's named rho_mid=400,
  while this equivalence patch preserves the old positive-zero masked limit
  of 900 kg/m3. They are distinct initialization choices: QIB differs by a
  factor of 2.25 at fixed mass and density-dependent fall parameters change.
  Neither local helper PASS establishes the scientific startup policy. Do not
  combine their receipts or replace the full-host initialization validation.
- CP01 exit is being checked against its actual contract/oracle scope, which
  explicitly defers full writer, native round-trip and final M04/M05 conservation
  to later stages. No checkpoint state is promoted by this helper repair.

### CP01 scope correction after independent checkpoint audit

The stage plan's CP01 exit (CLOUD_BAL_FINAL_GOALS_CHECKPOINTS_20260907.md,
CP01 section) requires explicit adapter/variable/mass/geometry/frame/boundary
contracts, host/options pinning and small positive/negative oracle receipts.
It explicitly excludes full native writer and final M04/M05 conservation.
An independent Luna high audit confirms that full KDM6 first-call runtime,
complete native interpolation/coupling and science must not be added as blanket
CP01 exit prerequisites: these remain CP06-B/07/08 obligations.

CP01 still needs unambiguous species/auxiliary/denominator policy (or explicit
reject/no-authority behavior), host and producer evidence, mass/EOS/metric and
frame/boundary/time contracts, targeted contract tests and independent exit
review. The zero-QIB finding affects that policy, while its full-host runtime
acceptance belongs downstream. Earlier next-action statements that bundled
full first-call/interpolation proof into CP01 are superseded by this split.
The checkpoint next_action is corrected; its IN_PROGRESS/NOT_RUN status and
all final requirement gates remain unchanged. Contract evidence must be mapped
to the six actual CP01 checklist items before a scoped completion decision.

### Literal wind harness handoff and scoped exit matrix

Literal upstream wind helper slices and four actual paired column inputs are
retained in `scratch/literal_upstream_uv_20260909/MANIFEST.json`. Pinned Intel
compilation in fresh `build.b33x` succeeds. Execution stops in original
lagrange_setup because the temporary harness's final target log pressure 8.5156
is outside the supplied top bracket endpoint 8.5172. This is an incomplete
harness input/geometry replay, not a native-model failure or accepted wind proof.
Build/run logs are preserved; no source endpoint, level, tolerance or upstream
algorithm was changed to manufacture acceptance. Complete replay is tracked as
CP06-B/07 work. The six actual CP01 contract/oracle items and their remaining
bindings are now explicit in `CP01_CONTRACT_EXIT_MATRIX_20260909.md`.

### Frozen CP01 contract/oracle run (2026-09-09)

A fresh source/test/tool snapshot in `scratch/cp01_contract_snapshot.hvp19t_7`
passes eight Fortran programs under pinned Intel at O0 and O2: canonical state,
pressure geometry, partial-face overlap, pressure-column remap, domain transition,
pressure thermo state, water phase transfer and hydrostatic state. Independent
Python remap, surface/geopotential and stored-state fixture checks pass at each
optimization. Additional Python contracts pass 10 native-hybrid cases, 5 host
pressure cases and 4 pressure-cell geometry main-function cases. The latter
script is intentionally silent on success; its main invokes all four tests.

All 36 captured source/test/tool hashes match the frozen bytes and the live files
at post-run comparison. `receipt.json` binds the profile/compiler, exact source
manifest, fixtures, test binaries and logs. This is engineering evidence for the
CP01 small-test categories; actual producer frame/physical boundaries, full host
startup and final conservation are not tested by this subset. Independent item
4/6 coverage review is pending before marking those matrix rows verified.

### Scoped item 4/6 independent review and concrete cycle gap

Independent Luna high review confirms CP01 checklist items 4 (column geometry,
partial faces, thin cells and PSFC cuts) and 6 (named small positive/negative
cases) as SCOPED PASS from the frozen test receipt. Known moist columns,
asymmetric impulse, sloped terrain, missing OM/domain and bad-unit rejection
are covered. A silent Python geometry log was not used alone as proof: all
three separate Python scripts were rerun with explicit command/exit records
in `python_execution_receipt.log`. The matrix marks these two bounded rows;
whole CP01 and all final requirement gates remain unchanged.

Host and frame audits are retained at `scratch/cp01_host_binding_audit.20260909`
and `scratch/cp01_frame_boundary_time_OWN_20260909.md`. Their source clues do
not establish actual producer/binary equivalence. The audits' broader native
writer/enforcement/runtime statements must not become extra CP01 exit criteria.
Also, QIB has source process-time reconstruction after the unsafe quotient;
absence of a declared startup contract is not absence of all reconstruction.

A concrete reader gap is that open_case_file checks valtime without comparing
reftime. The actual staged inventory shows LAPS analysis products at reference
and valid time 13 UTC, while the paired FSF/FUA forecast background has reference
06 UTC and valid 13 UTC. A blanket reftime==valtime rule would reject legitimate
forecast input. Work therefore targets explicit product-specific reference-time
and same-forecast-cycle validation, preserving the existing FSF boundary-cycle
checks and avoiding claims of observational or frame authority from timestamps.

### Actual wind interpolation and KDM6 startup probes (2026-09-09)

- `scratch/real_wind_trace.uHpxb8` contains a private traced real executable
  and successful OFF/candidate runs. U/V/QVAPOR/T/P/PB are bitwise identical
  to their earlier uninstrumented native outputs. Actual float32 face-pressure
  gaps cross `zap_close_levels=500 Pa`: U 499.4453125 -> 500.3984375 and
  V 496.953125 -> 501.34375 Pa. Identical input winds therefore use different
  retained source levels, reproducing native level-2 changes -4.8802070618
  and +6.7365393641 m/s. This replaces the invalid final-PB reconstruction;
  no interpolation threshold or physics was changed to pass the test.
- Three private KDM6 variants in `scratch/research_host_patch.LX6gHp` reuse
  the existing host libraries: original, numerical legacy-equivalence guard,
  and the distinct rho_mid=400 research prior. Strict fresh-main runs stop in
  Noah LSMINIT before KDM6. GDB in
  `scratch/MANUFACTURED_BOUNDARY_STARTUP_TEST.gdb.nzPMoq/gdb.log` shows
  finite meaningful division operands and unused SIMD lanes performing 0/0;
  this is not evidence of invalid soil temperatures.
- Reusing the original host main object, all three runs finish one 20-second
  step with periodic manufactured boundaries, unchanged physics options and
  the same native candidate input. Outputs are retained in scratch directories
  `MANUFACTURED_BOUNDARY_STARTUP_TEST.hostmain.baseline.d3WhQP`,
  `MANUFACTURED_BOUNDARY_STARTUP_TEST.hostmain.legacy_guard.kVZ5VQ`, and
  `MANUFACTURED_BOUNDARY_STARTUP_TEST.hostmain.candidate400.Wdk451`.
  All 240 floating fields match baseline versus legacy guard at both stored
  times (NaNs compared as equal); the 400-density prior changes 19 fields.
- Startup is not clean scientific acceptance: REFL_10CM contains 40,323 NaNs
  for baseline/guard and 40,324 for the prior. The other 239 floating fields
  are finite. In baseline, 39,639 NaN cells have QRAIN>1e-9 with QNRAIN=0,
  exposing the radar operator's zero-number division; 684 NaNs need separate
  attribution. Missing auxiliary initialization is not solved by the QIB guard.
  These are normal-host-runtime probes, not full-model strict-FPE PASS or
  physical-boundary forecasts. Original host source/object/binary hashes hold.
- The explicit constructed moist-column test additionally passes fresh pinned
  O0/O2 in `scratch/cp01_moist_column.7o8ZrV`; copied source hashes are unchanged.
  CP01 remains open; full native acceptance and science gates are unchanged.

### Exact rain-number attribution (2026-09-09)

The diagnostic-only trace in `scratch/kdm6_refl_trace.1dn3rS` completes the same
20-second run. All 240 floating output arrays remain identical to the numerical
legacy-guard run, including NaN locations. All 40,323 NaNs originate in the rain
reflectivity contribution with positive rain mass and zero number at the actual
operator call; snow and graupel contributions are finite. The previously
unattributed 684 cells have rain between 1.008e-9 and 9.910e-9 kg/kg at that call.
The later `microphysics_zero_outa` path (`MP_ZERO_OUT=2`, threshold 1e-8) removes
that rain before history output. Final history therefore cannot substitute for
the diagnostic's actual input in this attribution.

The existing real mass-to-number startup helpers are Thompson-only and impose
a named PSD closure; they are not a neutral KDM6 fallback. Independent source
audits also identify a number-basis mismatch: Registry/dynamics use #/kg while
KDM6 internal moment equations use #/m3 without boundary conversion. A separate
research unit-conversion patch is under test; it cannot create missing QNRAIN
or establish a physical PSD/initialization policy. No native/science gate changes.

The first tested revision of `patches/kdm6_number_basis.patch` implemented public #/kg to internal
#/m3 conversions and uses the converted number concentrations in effective-radius
formulas. The existing first-call CCN volume profile is not multiplied by density
twice. The public pre-call CCN initialization in start_em remains a separate gap;
no missing-rain PSD is supplied by this patch. It is unapplied to the shared host.
That revision applied to the original source with zero fuzz. The actual-module test
`tests/test_kdm6_number_density_invariance.f90` holds specific mass and number
constant at air densities 0.5/1/2: baseline fails radius invariance, while patched
O0/O2 pass without clipping. Evidence is in
`scratch/kdm6_number_oracle.7tqSHB/corrected_fixture`. This test supplies a named
graupel radar constant solely to initialize the cloud/ice oracle; it does not
certify full startup or the full number-tendency boundary. Initial harness attempts
and their unrelated initialization/clipped-fixture failures are retained separately.

#### CCN entry correction and repeatability (2026-09-09)

The subsequent research revision removes KDM6's duplicated first-call CCN
reset. Apply `patches/kdm6_number_basis.patch` together with
`patches/kdm6_ccn_initialization.patch`: start_em converts its configured #/m3
profile with `al+alb` to public #/kg dry air, and the wrapper consistently
converts all four number fields at entry/exit. Existing nonmissing CCN and
other schemes retain their start_em behavior. No missing-rain PSD is supplied.

Evidence: `scratch/kdm6_ccn_contract.TXN16P`. Actual-wrapper test
`tests/test_kdm6_ccn_entry.f90` preserves 4e9 #/kg at densities 0.5/1/2 on
timesteps 1 and 2, including untouched storage halos. Original O2 fails the
same CCN assertion (exit 2). An initial candidate O2 repeat exposed an undefined
read of output-only `rhox` in kdm62D; its earlier single PASS is not reliable.
The separate `patches/kdm6_diagnostic_initialization.patch` initializes that
diagnostic to zero before later recomputation, without choosing a density prior.
With this correction, `corrected_O0` and `corrected_O2` each pass five wrapper
repeats and the actual cloud/ice radius oracle. Tested combined module SHA256:
`71f5614383bf727ce8562955879229e55d373f0b0441626a4c32cf4654a3f656`.

Exact extracted start_em block tests in `run.t64QtU` pass seven original and
candidate cases at O0/O2: land/sea profiles, positive/nonpositive scale height,
nonmissing preservation, WDM6 nonchange and bounded upper copying. These are
block tests, not a full start_em binary or restart integration run. Wrapper
fixtures use positive graupel volume and a radar initialization constant to
isolate CCN; they do not certify physical graupel startup. All patches apply
with zero fuzz to private copies; the shared host remains unchanged.
CP01 and native/science gates are not promoted by these scoped results.

#### Actual CCN startup integration (2026-09-09)

`scratch/ccn_native_start.j2U4Rf` links the current-source patched start_em and
KDM6 into a private copy of the host archive, reusing the existing host main,
dependencies, static links and unchanged input/namelist. Fresh preprocessing in
`scratch/start_em_ifx.GVv02O` matches the original generated source before the
patch; the candidate adds only the five intended CCN lines. Pinned Intel O2
compilation and private linking both exit 0. This is not an O3/precise rebuild
equivalent to the historical host object.

The unchanged periodic-boundary 20-second startup test exits 0 and writes both
13:00:00 and 13:00:20 states. Executable SHA256 is
`583a9c628a3677fe699ad255b6772feca1c301c46d875d0b9e32dfa2bfd2cc1c`;
input SHA256 remains `f0ccee31f6f7214c9d7b5ccf19e0ae55d9fe43751e0fcffbcaedfc6080a052e1`.
Independent initial-state reconstruction from P/PB, dry theta, QVAPOR, PH/PHB,
XLAND and the configured CCN profile agrees with QNCCN to maximum relative
error 5.90e-6. The 240 floating history fields still include 40,322 nonfinite
REFL_10CM values; the other 239 fields are finite. The independent scratch
`verify_initial_qnn.py` also rejects the legacy output's old number basis
(maximum relative error 0.9163, exit 1); candidate exits 0 for the CCN check.
This is CCN-path integration
evidence, not a physical-boundary forecast, rain-number closure, restart test,
or science PASS. The shared host hashes remain unchanged; CP01 stays open.

### Final 13 UTC reference-time contract snapshot (2026-09-09)

The isolated reader in `scratch/cp01_contract_snapshot.hvp19t_7` passed the
actual `20260816T130000Z` case at pinned Intel O0 and O2. Both accepted the
legitimate 06 UTC FSF/FUA forecast cycle at valid time 13 UTC. Independently
mutated LW3 reference time, missing reference variable, NaN reference value,
and mismatched FUA/FSF cycle were rejected with the exact expected
`reftime-mismatch` or `reftime-read` diagnostic. The missing-variable fixture
was copied from the valid input and only renamed `reftime`, avoiding an
unrelated malformed-field rejection. Manifest input hashes were checked before
and after each mode and rechecked at receipt creation.

Final evidence: `scratch/cp01_contract_snapshot.hvp19t_7/reftime_13z_receipt.json`,
`reftime_13z_final.log`, and `scratch/reftime_contract.sAxKkI/` beneath that
snapshot. The earlier parent 12 UTC run remains separate; the earlier agent
receipt/patch is superseded for final 13 UTC claims. The tested reader hash is
`a092e843372741bfa83998a8eaaee2384321acd57f994decd18e7a897495b563`.

Integration is pending: another session changed the shared live reader after
its captured baseline `01bf28b4...`. The verified snapshot was not copied over
those edits. The live implementation needs its own final diff/review and
verification. Timestamp consistency alone establishes neither producer/frame
lineage nor scientific authority. CP01 remains IN_PROGRESS / NOT_RUN.

### New wind producer frame binding (2026-09-09)

The fresh pinned wind build and private 13 UTC invocation completed, with
source/input/config integrity recorded in `scratch/cp01_lw3_success_20260909`.
The parent verified the durable manifest, then verified its refreshed version
including `frame_interpretation_receipt.md`. Current compiled frame control is
`src/upstream/wind_openmp/main_sub.f` SHA256
`9bc4773852c48573f114f2ed2085a7ef4188ac774c21685aa287103f95fdebcf`, not the
older upstream driver. The hashed include fixes grid-north input/analysis/output
flags true; the log confirms observation rotation to grid north, and the reverse
output rotation branch is disabled. The new U3/V3 and SU/SV therefore have a
source/runtime-bound grid-relative interpretation. OM remains pressure vertical
velocity, separate from native ww. This interpretation is scoped to this new
execution and does not validate physical background-input assumptions.

New LW3 SHA256 is
`2eb193f38e98a2501d7ce4a887eb88ef97d434a151af6ae560903503222008fa`.
Historical final_ordered U3/V3/OM differ (RMS 0.1135018 m/s, 0.1524808 m/s,
0.0395943 Pa/s); no historical lineage or explicit NetCDF frame attribute is
established. The earlier SIGSEGV run is a retained failed attempt, superseded
only for the claim that fresh private generation is feasible. Whole CP01 is
not promoted by this producer receipt.

### Current live time-policy integration review (2026-09-09)

Independent source review found the current enum-policy reader
`c29f62dde3017e2f4b92d42381d2e4ca746f9592a04a03b04b5b14bf4bdd6ac8`
semantically sound: analysis reference equals valid time, forecasts cannot have
a future reference, FUA matches the FSF cycle, and adjacent boundary FSF files
retain the same-cycle rule. This is a separate implementation from the earlier
verified optional-expected-time snapshot and requires current evidence.

The external broad I/O suite observed at PID 2887159 terminated; its log
`/tmp/cloud-bal-time-contract-suite.log` ends with the direct-analysis positive
fixture rejected (`status=-10`, `reason=3`, required coverage), before the new
direct-product time mutations. No time-policy regression is established by
that coverage failure, and the direct-path additions are not a PASS receipt.
The reviewer also identified missing exact-diagnostic assertions in the broad
time mutation tests. A separate frozen current-source 13 UTC test is closing
those named-diagnostic gaps without editing the concurrently maintained suite.

### Research-source constants and unresolved auxiliary semantics

Source review receipt `scratch/cp01_kim_host_source_binding_OWN_20260909.md` (SHA256 `068d051a7a1dc3525fa809b8f7e4b0331a71e9f0b754e95c079eb61eb5c74c23`) binds the accessible research
host constants g=9.81, Rd=287, Rv=461.6, cp=7*Rd/2 and cv=cp-Rd. Its named
`epsilon=1e-15` is a numerical small constant, **not** the water molecular/gas
constant ratio used by the canonical EOS. With USE_THETA_M=1, the traced source
uses `(T+300)/(1+(Rv/Rd)*qv)` for physical potential temperature. Parent header
inspection of the hash-bound staged native file confirms USE_THETA_M=1,
MP_PHYSICS=37 and HYBRID_OPT=2. This binds source/serialized declarations;
full source-to-binary equivalence is still separate.

The active non-restart `compute_2d_dx_area` source sets `area2d=dx*dy`; its
map-factor expression is disabled under `#if 0`. This physics field alone does
not establish the full native dry-mass conservation integral, so the existing
hybrid diagnostic's explicitly assumed map-factor area is not relabeled as a
verified host metric. The energy ledger convention remains unbound.

QN fields are passed directly to KDM6 local number arrays. Registry/driver
labels say per kg, while the traced `n/(rho*q)` equations and CCN initialization
behave dimensionally like volume concentrations. This is a source/interface
conflict requiring resolution, not a missing external source-file problem.
QIB has declared volume-per-air-mass dimensions; dry-air basis is a source
inference and does not resolve the QN conflict. No arbitrary conversion or
number initialization has been applied.

### Executable MP37 declaration checks

`tools/mp37_aux_contract.py` and `tests/test_mp37_aux_contract.py` now provide
pure coverage/declaration checks, included in the portable Python runner.
Eleven tests pass, including missing each auxiliary, unknown/inconsistent
denominators, malformed shapes/types, nonfinite values, fabricated evidence
identifiers and a heterogeneous per-cell QGRAUP/QIB gap. The parent corrected
an initial global-any QIB check that could conceal a missing-volume cell.
No input is filled or mutated. Structurally valid declarations remain
`accepted=false`, `native_authority=NONE`; checking hash syntax does not
authenticate a producer.

The actual 13 UTC file remains NO_AUTHORITY because its expected denominator
mapping is absent; all five auxiliaries are zero and 817 cells have positive
QGRAUP with zero QIB. Parent evidence is
`scratch/cp01_aux_validator.20260909/parent_actual_receipt.json`, with unchanged
native input SHA and current validator/test hashes. This is executable
contract inspection, not native writer integration or physical startup
acceptance. CP01 item 3 and whole CP01 remain open pending those scoped bindings.

### Live time-policy closure and contract evidence bindings

The current enum-policy implementation is now integrated and tested, superseding
the earlier pending-live-integration status for this bounded time contract.
Reader SHA256: `e56dd13129d9e532cc2e071ad1a0ef3703282e0163f73df4a84586c2c56f2187`.
Evidence: `scratch/cp01_live_time_4kzu5zp2/receipt.json`, its source snapshot,
`suite.log`, three preserved O0 executables and `independent_review.json`.

- Full `tests/run_real_shadow_io_contract_tests.sh`: exit 0 using pinned Intel
  in fresh scratch. Existing O0/O2 numerical/I/O contracts and final byte-level
  SHADOW comparison pass. All 56 captured source/tool hashes and six pinned
  first-case input hashes match after execution.
- Direct positive input with absent FUA/FSF passes. Singleton reference-time
  mutations reject LW3, VRZ, VRT, LT1, LQ3, LWC and LSX. Six legacy mutations
  reject missing reference, bad reference units, NaN, future reference, and
  mismatched FUA or FSF forecast cycles. These new mutations run at O0.
- The same preserved reader accepts actual 13 UTC inputs from the 06 UTC
  forecast cycle; missing reference, NaN and mismatched FUA cycle reject with
  the expected diagnostics. Separate receipt:
  `scratch/time_contract_receipt.UOHjSf/receipt.json`.
- The initial direct positive fixture failed because netCDF4 applied the old
  PSFC `valid_range` and masked valid pressure above 100000 Pa. The fixture
  now copies raw values. Production ranges and input bytes were not changed.
  Missing-reference testing now renames only that variable in a valid copy.
- Independent source review is PASS_SCOPED for the time policy. Historical
  optional-time and c29 snapshots keep their original provenance and scope.

`CP01_HOST_SPECIES_BINDING_20260909.md` and
`CP01_MASS_FRAME_BINDING_20260909.md` map items 1/2/3/5 to explicit inventory,
source conventions, receipts and unresolved authority. Required policies are
separate from implemented enforcement. Native auxiliary denominator/startup,
host EOS/metric authority and producer-frame/physical-boundary evidence are
not certified by the time tests. CP01 stays IN_PROGRESS / NOT_RUN; final
requirement gates, native/science acceptance and promotion are unchanged.

### Current reader named-error validation completed

Final evidence is `scratch/cp01_time_contract_snapshot.c29_13z/reftime_named_receipt.json`
with artifacts `scratch/reftime_contract.B3gJos` beneath that snapshot. The
historical directory name contains c29, but the tested reader hash is
`e56dd13129d9e532cc2e071ad1a0ef3703282e0163f73df4a84586c2c56f2187`, matching
live at parent review. Pinned Intel O0/O2 compiled with each fresh mode directory
as the actual working directory, recorded in build_cwd.log. Both accept actual
13 UTC valid data from matched 06 UTC FSF/FUA and assert exact errors for analysis
shift/missing/NaN, future FSF, future FUA and mismatched FUA cycle. Parent
rechecked source/input manifests and retained log hashes. Earlier optional-time
and 8oiHS2 artifacts are superseded for current-reader claims.

`tests/run_named_reftime_contract.sh` installs this narrow test recipe with the
live repository's workspace-root default; shell syntax is checked. The frozen
O0/O2 execution is the runtime evidence, not an unperformed new live launch.
Direct-product broad-suite coverage and the boundary same-cycle negative test
remain separate; no full CP01 or native physical-boundary acceptance is claimed.

### CP01 item 5 independent scoped closure

Corrected boundary evidence `scratch/cp01_boundary_reftime.20260909/parent_final_receipt.json`
uses `boundary_reftime.jFcnSB`, with actual 07 UTC reference mutations and
unchanged 12/13/14 UTC valid times. Parent verified each of the six O0/O2
mutation headers, exact negative status/reason, state preservation, and complete
source/input manifests. The initial CnJ9WO before/center future-time mutations
are not used for same-cycle claims. Reusable boundary test and runner files
are now under tests/; their runtime evidence is the frozen execution.

Independent Luna high review accepts item 5 as SCOPED PASS for the documented
contract and current evidence: newly source-bound wind interpretation, explicit
map-area assumptions, gas-only w/omega relation, ww distinction, named timestamp
errors and boundary rejection. Historical LW3, FSF wind frame and physical
boundary flux retain their no-authority status. Native continuity remains
CP06-B/07. CP01 items 4, 5 and 6 are now SCOPED PASS; items 1–3 and whole CP01
remain open. No canonical mandatory requirement or later checkpoint is promoted.

### CP01 auxiliary-input validation precedence — 2026-09-09

Scoped evidence: `scratch/aux_validation_order_rzvb7ynf/receipt.json`.
Malformed auxiliary arrays are now rejected before denominator, metadata or
source-authority checks. A malformed denominator container is rejected, while
missing/incomplete/unknown mappings retain NO_AUTHORITY. Sixteen tests pass,
including 18 mixed payload/declaration cases and four invalid-container cases.
The actual 13 UTC input remains NO_AUTHORITY; a QNRAIN NaN introduced only in
memory rejects as NONFINITE_FIELD, with the original input hash unchanged.
Independent review confirms no mutation or promotion behavior.

This closes a diagnostic classification gap only. QCLOUD/QNCLOUD and
QICE/QNICE pair coverage are not yet represented in this validator API. QN
source/interface denominator binding, startup authority and native handoff
integration remain open. Whole CP01 stays IN_PROGRESS/NOT_RUN.

Source-revision clarification: earlier paragraphs calling e56 the current
reader describe their historical frozen runs. The subsequent NaN/time-edge
receipt binds e665a39b, and the finite-extreme follow-up receipt
`scratch/finite_payload_fix_j2i4kbu9/receipt.json` binds 74533e1b with O0/O2
full I/O PASS and unchanged diagnostic bytes. These are distinct tested
revisions; this Python-only step did not rerun Fortran validation or promote
physical-boundary/native authority.

### CP01 nonzero QN wrapper and internal dependency fixture — 2026-09-09

[Bounded report](CP01_QN_WRAPPER_PROBE_20260909.md) and
`scratch/kdm6_number_wrapper_internal.E5am33/receipt.json` bind the final
internal-source O0/O2 run. Five unchanged host sources plus a fail-on-call
diagnostic stub remove the external KIM source/archive dependency; the pinned
Intel compiler/runtime remains required. All 23 compared fields match exactly
for the scaled reference and candidate at rho 0.5/1/2, and candidate O0/O2
results agree exactly. NC/NI/NR remain positive and each detects the unscaled
negative control at rho 0.5/2. Ice-radius flooring and CCN clipping limit the
diagnostic interpretation; no unbounded radius or new CCN claim is made.

The initial wrong-cwd attempt, missing-libmassv link attempt and depleted-ice
fixtures are retained as excluded development evidence. Final builds each
record a fresh scratch cwd and source/binary hashes; shared host hashes match
the original snapshot. This validates a conditional conversion proposal, not
the active host denominator or physical startup. CP01 remains
IN_PROGRESS / NOT_RUN, with no native/science/final-gate promotion.

### CP01 cloud/ice diagnostic pair coverage — 2026-09-09

`scratch/aux_cloud_ice_w6guiaaf/receipt.json` binds 21 passing tests and the
unchanged actual-input probe. The validator now requires QCLOUD and QICE,
validates malformed mass payloads before declarations and checks per-cell
positive mass with zero QNCLOUD/QNICE. The earlier API pair-coverage gap is
closed in the diagnostic layer. All current non-scratch callers are updated.
No filling, mutation, authority authentication or native promotion is added.
Native integration, denominator/startup authority and whole CP01 remain open;
CP01 is IN_PROGRESS / NOT_RUN. No Fortran rebuild was needed.

### CP01 native-file auxiliary reader — 2026-09-09

`tools/check_native_mp37_aux.py` now connects a single-time MP37 wrfinput
to the existing pure validator. The frozen receipt at
`scratch/native_aux_reader_m44m_vlj/receipt.json` records 12 file-based tests
and the unchanged retained actual input returning NO_AUTHORITY/exit 3.
Malformed dimensions, masks, missing fields, invalid values and read failures
reject with exit 2. No success code, metadata-authority inference, output
write or forecast launch is provided. The portable Python runner includes
the new test; only the focused tests were executed in this step.

Source tracing confirms Cloud-BAL writes WPS intermediate data, while the
external real.exe creates native wrfinput. The retained scratch launcher is
historical and was not modified. WPS STATUS='REPLACE' lacks mid-write rollback;
SHADOW transaction machinery does not establish native atomic publication.
These are explicit integration limits, not newly fixed behavior. The next
launcher connection belongs after real output and before forecast/publication,
with authoritative denominator/startup binding still required. CP01 remains
IN_PROGRESS / NOT_RUN; no native/science promotion or Fortran rebuild.

## CP01 final scoped exit — 2026-09-09

CP01 is COMPLETE / PASS for the original six research contract and small-test
criteria after independent red and green review. The current authority is
CP01_CONTRACT_EXIT_MATRIX_20260909.md and CP01_COMPLETION_AUDIT_20260909.md;
earlier IN_PROGRESS entries are historical.

The selected private corrected KIM profile binds 53 artifact identities, dry-air
QN/QIB basis and explicit startup coverage. Native integration weight, T/THM,
EOS and A_Q/A_M/A_E definitions are bound; the asymmetric metric oracle passes.
Frozen geometry evidence remains current (36 source hashes, 106 artifacts),
as does the latest reader suite (56 source hashes). New focused evidence is
19 native preflight tests, 21 shared tests and the transaction suite, all exit 0.
Final sources, logs and checks are in scratch/cp01_final_binding_vpoe3vby/.

The actual 13 UTC file stays NO_AUTHORITY. Independent preflight rejection
leaves input bytes, every prior committed file hash and the current pointer
unchanged, with no new generation or launch marker. The only positive
publication is a constructed diagnostic receipt, not native permission.

The initial NAS prior-generation seed failed because atomic no-replace rename
is unsupported. The preserved failure is not passed evidence; successful
atomicity uses fresh local scratch. CP02 must establish publication storage
and full native integration. No non-atomic fallback or guard bypass was added.

Red review found only two record defects: a driver source line reference
(corrected to 2549) and the stale exit matrix (now replaced). Green found no
blocking implementation defect. Native roundtrip, full-host clean-build
equivalence, physical boundaries, continuity and water/energy conservation
remain CP02/06/07. Final M01–M07/science and operational promotion gates
are unchanged.

KG: Cloud-BAL 3887 nodes / 8143 edges / 252 communities, +174 IDs and -8,
zero missing endpoints or exact duplicate edges, zero LLM extraction tokens.
Parent KLAPS50 and document semantics were not refreshed in this bounded run.
