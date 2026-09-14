# 기존 처리 관측 입력을 사용한 실제 Fortran 실행

2026-09-11. 범위: 2026-08-16 13 UTC의 기존 처리 LAPS 입력을 사용하는 격리 진단 실행.
CP06-A 명세 전체 통과나 CP02 완료를 뜻하지 않는다.

## 수정

`cloud_bal_real_netcdf.f90`의 출력 경로가 새로 연결된 LCP/LTY를 거부하던 두 조건을 바로잡았다.
구름 입력이 있으면 기존 cloud/phase 검증과 전체 pipeline replay로 후보를 대조하고,
구름량·구름형·강수형의 값, 유효성, quality/source, 시각을 진단 파일에 저장한다.
`cloud_analysis_present=1`을 정확히 기록한다. 레이더 전용 no-echo 검사에서 구름 진단값
변화를 강수 변화로 간주하던 문제도 전체 replay 경로로 해결했다.

중복 cloud 검증은 추가하지 않았다. `cloud_bal_column_physics.f90`는 기존 검증 루틴 두 개를
공개했을 뿐 수식과 수치 제어값은 바뀌지 않았다. Python 감사기는 수정하지 않았다.

## 실행과 확인

증거: [실행 디렉토리](../scratch/cp06a_lcp_candidate_70n3enqs/).
입력: 기존 처리 입력 목록 (로컬 전용 자료: `../config/cp06a_observation_inputs_20260816T130000Z.json`; 공개 PR에 포함하지 않음).
원본과 private 입력 10종의 hash가 일치한다. 실제 전체 LAPSPREP를 pinned Intel ifx로
새 scratch에서 각각 O0/O2 빌드하고 실행했다.

- OFF/HYDRO/LIQUID_RADAR_RH1: 실제 전체 LAPSPREP O0/O2 모두 종료 0. 최종 로그는 `O0_final/`, `O2_final/`에 보존했다.
- OFF WPS 129 records는 수정 전 및 O0/O2 사이에서 byte-identical이다.
- HYDRO 및 LIQUID WPS 235 records도 각각 O0/O2 byte-identical이다.
- LIQUID는 3회 수렴했으며 T/vapor/cloud water 각각 49,448셀 변화, cloud ice 변화 0이다.
  thermo support 밖의 해당 필드 변화는 0이고 유효 지상 셀의 WPS TT/QV가 저장 후보와 일치한다.
- HYDRO 101변수·105전역속성 및 LIQUID 150변수·130전역속성을 모두 O0/O2 대조했다.
  값과 변수 metadata도 정확히 일치한다. `saved_final_checks.json`에 기록했다.
- 저장된 cloud fraction/type/phase는 각각 1,294,696 유효 셀이며 실제 LCP/LTY 값과 일치한다.
  PTY 5 우박은 unknown/uncertain으로 유지한다.
- HYDRO 비 55,031셀, 눈 12,788셀, 싸락눈 24셀이 바뀌었다. 무강수 셀의 수상체 변화는 0이다.
  다섯 수상체 WPS 필드를 sidecar와 재대조했다. 바람 u/v/omega는 동일하고 balance 변경은 0이다.
- 수송 flux input은 880,096,728.3488083 kg/s. 저장 항을 순차 합산한 독립 오차는
  5.4836273193359375e-6 kg/s, 허용치는 0.008800967283588082 kg/s이다.
  Fortran SUM의 보고 오차 5.364418029785156e-6와의 차이는 합산 순서 차이다.
- 상세 숫자: `saved_hydro_checks.json`; 소스 hash: `final_sources.sha256`.
- 최초 거부와 추가 no-echo 거부는 원래 로그에 보존했다. `diagnostic/`은 원인 확인용
  scratch 계측 복사본이며 최종 실행 파일에는 진단 계측을 넣지 않았다.

독립 GREEN의 직접 pipeline O0/O2 HYDRO와 LIQUID_RADAR_RH1 시험도 통과했다.
LIQUID는 radar 선택 67,567셀, wrapper의 최대 16회 중 3회 수렴했다.
증거는 `scratch/cp02_lcp_lty_pipeline13.e1Jfsu/`와
`scratch/cp02_liquid_lcp_lty13.YYMxVN/`이다.
RED는 최종 Fortran 수정과 실제 HYDRO 출력을 검토해 통과로 판정했다.

## 범위와 남은 작업

- 실제 wrapper는 10 km/20 kPa, LIQUID 최대 16회를 사용한다. 명세의 12 km/30 kPa/8회
  COUPLED 실험으로 표시하지 않는다. 직접 GREEN HYDRO probe만 12 km/30 kPa를 명시했다.
- HYDRO의 HGT 8개 pressure records에는 높이→geopotential→높이 저장 변환으로
  최대 0.0009765625 m 차이가 있다. 따라서 모든 WPS 배경 필드의 bitwise 불변을 주장하지 않는다.
- 구름 candidate QC는 background와 전체 replay로 복원한다. 별도 candidate QC 배열은 저장하지 않는다.
- 기존 `validate_shadow_diagnostics.py`는 새 cloud-present 확장을 지원하지 않아 거부한다.
  이 감사기 호환성은 이번 Fortran 실행 통과와 구분한다.
- `science_assessed=0`, `promotion_eligible=0`. 관측 유도 omega target/sigma 및 held-out LOS 연결,
  명세 조건의 결합 실행, WPS→metgrid→real/native 검증은 아직 남아 있다.

최종 GREEN 회귀시험도 종료 0으로 통과했다. 최종 reader `f880733f…f5156` 및
column `f7d640bb…f14e17d`의 실행 전후 hash가 일치한다.
기존 입출력·오류 입력·thermo·geometry·WPS 시험 로그는
`scratch/cp02_io_contract_final_launcher.cOcdP4/`, 산출물은
`scratch/real_shadow_io_tests.XttVdP/`에 보존했다.
전체 실행 색인은 [FINAL_RUN.json](../scratch/cp06a_lcp_candidate_70n3enqs/FINAL_RUN.json)이다.

후속 팀 검토에서 찾은 정상 구름 QC 변경 거부(P2)는
[QC 출력 수정 기록](CP06_A_CLOUD_QC_FIX_20260911.md)에서 수정·검증했다.
위 reader hash와 실행 결과는 이 후속 수정 이전의 보존 기록이다.
