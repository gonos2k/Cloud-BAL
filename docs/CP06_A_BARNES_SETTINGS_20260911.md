# 기존 다변량 Barnes 설정과 Cloud-BAL 입력 연결

2026-09-11. 사용자의 namelist 확인 지시에 따라 실제 설정과 Fortran 사용처를 대조했다.
시선속도는 기존 다변량 Barnes 바람 분석에 이미 사용된다. 관측 또는 오차 근거가 전혀
없다고 분류하지 않는다. 새 시선속도 분석이나 오차 상수는 추가하지 않았다.

## 실제 설정

운영 참조 `ANAL/NE57/DABA/namelist/wind.nl`과 현재 13 UTC 격리 입력의
`prepared/static/wind.nl`은 byte-identical이다.

| 항목 | 값 | 기존 의미 |
|---|---|---|
| `L_USE_RADIAL_VEL` | `.true.` | Doppler 시선속도 사용 |
| `WEIGHT_RADAR` | `0.25` | 정의가 `1/err²`; 가정된 시선속도 오차 `err=2 m/s` |
| `RMS_THRESH_WIND` | `1.0` | 관측 오차 RMS로 정규화한 반복 종료 기준; `1 m/s`라는 뜻이 아님 |
| `WEIGHT_BKG_CONST_WIND` | `5e28` | Barnes 배경 가중치 |
| `I_3D` | `1` | 3차원 Barnes 가중 방식 |
| 레이더 subsampling 기준 | `300 / 600` | 레벨별 관측 수에 따른 2배/4배 thinning 기준 |

`src/include/main_sub.inc`에는 `L_correct_unfolding=.true.`, `l_3pass=.true.`,
분석·출력 `GRID_NORTH=.true.`가 정의돼 있다. `main_sub.f`의 레이더 입력 시간창은
`i4_tol=900`초다. `qcradar.f`의 residual QC 기준은 12 m/s이고 unfolding 판정은
Nyquist의 0.7배를 사용한다. 두 수치는 namelist의 관측 오차 2 m/s와 역할이 다르다.

## 실제 처리 경로

1. `get_wind_parms`가 `wind.nl`을 읽어 `weight_radar` 등을 main에 전달한다
   (`klaps-v5.0_/src/lib/read_namelist.f:401`).
2. `get_multiradar_vel`이 기존 vXX 속도·Nyquist·레이더 위치·시각을 읽는다
   (`Cloud-BAL/src/upstream/wind_openmp/main_sub.f:359`).
3. `laps_anl`의 기존 QC와 single/multi-radar 파생 관측 구성이 수행된다.
   `insert_derived_radar_obs`는 `weight_radar`를 받고, `arrays_to_barnesobs`는
   `wt_p_radar`를 `obs_barnes%weight`로 전달한다.
4. `get_inst_err2`는 관측 weight와 시간 가중치의 역수 평균에서 `rms_inst`를 구하고,
   `rms_thresh = rms_inst * RMS_THRESH_WIND`를 계산한다
   (`klaps-v5.0_/src/wind_openmp/windanal.f:871`).
5. `barnes_multivariate`가 관측 weight·공간·시간 가중으로 U/V를 분석한다.
   현재 호출은 `windanal.f:705` 부근이며 기존 세 차례 분석 경로를 유지한다.
6. Cloud-BAL의 실제 reader는 처리된 LW3의 U/V/OM을 `SOURCE_ANALYZED_WIND`로 읽는다.
   따라서 시선속도 정보는 이미 분석 바람을 통해 입력된다.

## 바로잡은 경계

- `sigma_vrad`의 기존 설정 근거는 존재한다: `1/sqrt(WEIGHT_RADAR)=2 m/s`.
  이를 새로운 임의 상수나 근거 없는 결측 보충으로 분류하지 않는다.
- 이 값은 시선속도의 가정 오차(m/s)다. Cloud-BAL의 `omega_target_sigma`(Pa/s)와는
  변수·단위가 다르다. 기존 Barnes 분석 결과와 오차의 omega 변환·전파 연결이 남아 있다.
- `RMS_THRESH_WIND`, QC 12 m/s, Nyquist는 서로 대체할 수 없다.
- 기존 Barnes가 사용한 관측을 같은 후보 평가에서 자동으로 독립 held-out으로 표시하지 않는다.
- 기존 vXX에서 Nyquist가 결측이라는 기록은 그 저장 파일 범위다. 보존된 수정 remap의
  GSN 자료에는 VEL과 NYQ가 함께 유효한 5,086셀이 있으며 원시 자료 재확보가 필요하지 않다.

[소스 해시](../scratch/cp02_baseline_native_ruoww1a5/barnes_settings_sources.json)와
[GSN 저장 자료 대조](../scratch/cp02_baseline_native_ruoww1a5/GSN_NYQUIST_CONNECTION.json)를 보존했다.
설정·물리 코드·감사 도구는 변경하지 않았다. 후속 연결은 기존 Barnes 처리 결과를 재사용한다.

## Omega 계산과 오차 배열의 정확한 상태

`wind_post_process`는 Barnes 분석 U/V와 지상 U/V를 `vert_wind`에 전달한다
(`Cloud-BAL/src/upstream/wind_openmp/main_sub.f:717`). `vertwind.f`는 지형 압력경사와
지상풍으로 하단 omega를 만들고, `FFLXC`의 수렴을 수직 좌표 간격으로 적분해 `OM`을
저장한다. 단일 시선속도에 단위 변환 계수만 곱하는 경로가 아니다.

`klaps-v5.0_/src/wind_openmp/windanal.f:147`은 `aerr`를 명시적으로
“only a dummy ATTM”이라고 설명한다. 유지되는 `barnes_multivariate.f90`에서도 `aerr`는
인자·선언·하위 호출에만 등장하며 값을 계산하지 않는다. 따라서 이름만 보고 저장된
Barnes 오차장이라고 사용하지 않는다. `vertwind.f`/`fflxc.f`의 `sigma`는
`get_sigma`가 계산하는 지도 투영 계수이고, 통계 오차의 표준편차가 아니다.

Barnes 오차 전파는 분석 바람의 불확실성을 다루는 별도 검토 항목이다. 이를 이번 개선의
핵심이나 cloud omega 개선의 필수 선행 구현으로 단정하지 않는다. 관측 오차 설정 부재나
시선속도 처리 부재로 다시 분류하지 않는다.

## 사용자 확인: 기존 cloud omega 경험함수의 역학·물리 기반 대체

이번 개선의 중심은 구름 분석의 경험적 상승류/omega 산정을 역학·물리 기반으로
대체하는 것이다. 기존 경험함수의 계수 조정이나 새 경험함수 제작이 아니다. 기존 다변량 Barnes는
시선속도 분석 경로이며, LW3의 연속방정식 기반 OM과 LCO의 cloud omega를 구분한다.

실제 `src/upstream/get_cloud_deriv.f:640` 부근은 `cloud_bogus_w_lgt_ct`를 호출하고,
`:661`에서 `w_to_omega`로 변환한다. 원본 `klaps-v5.0_/src/lib/vv_lgt_ct.f`는
구름형·구름 깊이·격자 간격에 따른 포물선 상승류와 층운 최소 상승류를 사용한다.
계수는 namelist가 아닌 `GA_VV_TO_HEIGHT_RATIO_CU`, `GA_VV_TO_HEIGHT_RATIO_SC`,
`GA_VV_FOR_ST`, `GA_VV_TO_HEIGHT_RATIO_CT` 환경변수에서 읽는다. 소스 기본값은
각각 0.5, 0.05, 0.01, 0.5이며 실제 실행값은 실행 환경과 로그로 확인해야 한다.
Ct 기본값 안내 문구의 1과 실제 대입값 0.5는 다르다.
`klaps-v5.0_/src/lib/conversions.f:51`의 변환은 `omega = -w*p/8000`이다.

후속 물리 개선과 비교 설계는 이 경험함수를 기준선으로 삼는다. 개선안의 구름 상승류,
열역학·수상체 정합성, 연속방정식 및 기존 분석 바람과의 결합을 평가한다.
Barnes 재구현이나 오차 전파만으로 이 개선을 완료했다고 판단하지 않는다.
현재 `build_cloud_targets`의 배경 w 유지와 `add_loading_downdraft`의 경험적
효율 계수 기반 하강류 진단도 완성된 역학적 omega 산정으로 취급하지 않는다.

## 13 UTC 기준 사례의 실제 경험함수 계수 및 입력 검증

소스 기본값과 실제 실행값을 구분한다. 기존 producer 실행 receipt와 `stage.log:904–907`에서
확인한 실제 값은 Cu=0.5, Sc=0.10, St=0.017 m/s, Ct=1.3이다.
`deriv.nl`은 `MODE_EVAP=0`, `L_BOGUS_RADAR_W=.false.`이며 원본 namelist와 동일하다.
따라서 `laps_deriv_sub.f:893`의 반사도 기반 `get_radar_deriv` 재계산은 이 사례에서 꺼져 있다.

실제 사용되는 `vv.f:220`의 포물선은 구름 깊이 D에 대해
`wmax=(coefficient/dx)*D`, `halfspan=0.55*D`, `zmax=ztop-halfspan`,
`w=wmax*(1-((z-zmax)/halfspan)**2)`다. 구름형별 적용과 최소 상승류 처리는
`vv_lgt_ct.f`에서 수행한다. 이 계수와 근사 변환은 기존 경험함수의 기준선이며
검증된 개선 계수로 해석하지 않는다.

저장 LCO의 `COM`을 canonical `cloud_omega_evidence`와 직접 비교했다. 수직 순서를
뒤집으면 유효 **244,326셀의 값이 정확히 동일**하며 범위는
**−9.1410675 ~ −0.00014722347 Pa/s**다. 즉 cloud omega 자료는 이미 읽혀 보존된다.
`omega_target_valid=0`은 이 경험적 값을 관측 target으로 승격하지 않는 현재 구현의
결과다. 이를 cloud omega 입력자료 부재로 표현하지 않는다.
`cloud_bal_real_netcdf.f90:57–91`은 LCO를 별도 evidence로 읽으며 target/sigma는 할당하지 않는다.

[실제 계수·값 대조 증거](../scratch/cp02_cloud_omega_baseline_20260911/RESULT.json).
이 검증은 기존 경험함수 기준선 연결을 확인한 것이며 개선 물리의 완성이나 CP02 전체 PASS가 아니다.

현재 `src/lib/vv_lgt_ct.f:149`에는 새 `build_multilayer_w_profile`을 호출하는 별도
wrapper가 존재한다. 그러나 검증한 실제 upstream producer는 원본 lib를 링크했으므로
위 244,326셀 비교는 기존 경험함수의 기준선이다. 새 profile 코드의 존재나 단위시험을
실제 producer 개선 적용 증거로 간주하지 않는다.

GREEN/RED는 기존 LCO와 evidence의 값·mask 일치를 독립 확인했다. 다만 해당 producer
실행 이후 일부 adapter/column/build 소스가 변경됐다. 이 과거 실행을 최신 전체 소스의
실행 증거로 사용하지 않는다. [소스 차이](../scratch/cp02_cloud_omega_baseline_20260911/SOURCE_DRIFT.json)와
[RED 검토](../scratch/cp02_cloud_omega_baseline_20260911/RED_REVIEW.md)를 함께 보존한다.

실제 호출은 5인자이고 별도 profile wrapper는 cloud fraction을 포함한 6인자다.
wrapper만 교체하면 ABI가 맞지 않는다. 또한 별도 wrapper는 `max(Cu,Ct)`를 사용해
낙뢰 계수를 일반 Cu/Cb에 적용한다. 이 코드는 기존 simplification plan
491–563행에서 제외한 경험식이므로 재활성화하지 않는다. 후속 물리 개선은 현재
column physics의 동역학 driver/격자 평균 질량 flux 계약을 따른다.

## 최신 소스 실행으로 기준선 재확인

이후 fresh pinned O0/O2 derived producer와 같은 실행파일의 EXPORT_OFF를 각각 실행했다.
네 실행 모두 종료 0이며 모든 소스 pin이 현재 파일과 일치한다. 14개 producer 제품은
과거 기준선과 바이트 단위로 같고, O0/O2 export의 128개 변수 배열도 정확히 같다.
따라서 과거 receipt의 소스 차이를 지우지 않고, 최신 producer/export 실행 증거를 추가했다.

[최신 O0/O2 대조](../scratch/cp02_current_derived_O0.7rF6zk/EXPORT_O0_RESULT.json),
[최신 O2 producer](../scratch/cp02_derived_current_O2.OtirDj/RESULT.json).
실험 명세 v3는 이 최신 O0 payload를 배경 입력으로 고정한다. 기존 경험함수 기준선의
연결 검증이며, 비활성 profile의 적용이나 개선 동역학의 완료는 아니다.

최신 O2의 [GREEN 검토](../scratch/cp02_derived_current_O2.OtirDj/GREEN_REVIEW.md)는
388개 소스 pin, 같은 실행파일의 producer/export 정상 종료, LCO evidence의 정확한
보존과 기존 구름 필드 입력을 독립 확인했다.

[최신 소스 RED 검토](../scratch/cp02_cloud_omega_baseline_20260911/CURRENT_SOURCE_RED_REVIEW.md)도
O0/O2 producer/export의 각 388개 소스 pin과 정상 종료, 128개 변수 배열의 동일성,
LCO/LCP/LTY 연결을 확인했다. 이 producer/export 범위의 과거 소스 차이 문제는
새 실행 증거로 해소됐으며 CP02 전체 및 개선 물리 완료와는 구분한다.
