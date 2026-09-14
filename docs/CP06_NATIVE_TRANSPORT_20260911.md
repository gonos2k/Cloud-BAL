# 최신 처리 관측 후보의 연구 native 전달

2026-09-11. 최신 구름 QC 출력 수정본에서 생성한 2026-08-16 13 UTC
OFF/HYDRO/LIQUID_RADAR_RH1 WPS를 기존 metgrid와 연구용 real에 전달했다.
범위는 초기 입력 전달 진단이다. CP06-A COUPLED, CP06-B 또는 CP02 완료 판정이 아니다.

## 입력과 실행

- 입력은 [QC 수정 검증](CP06_A_CLOUD_QC_FIX_20260911.md)의
  `scratch/cloud_qc_fix_20260911/O0_final/original/*.wps`다. 이 WPS는 이전 단계에서 O0/O2 동일성을 확인했다.
- 기존 `metgrid13_fresh_off.tEo3hs`와 `real13_fresh_off.pYpsN8`의 13 UTC 설정·자료 연결을
  새 scratch로 복사했다. 원래 OML/SST/TAVGSFC/토양/배경/격자/table을 사용했다.
- pinned `tests/intel_toolchain.sh`와 기존 NetCDF runtime으로 실행했다. 이번에는 재컴파일하지 않았다.
  metgrid는 기존 `MODL/KLFS/NE57/EXET/klfs_lc05_prep_mgrd.e`, real은 기존 KIM-meso 연구 실행파일이다.
  real SHA256 `fa76d4bb17c0c63ecfed12a09ed912ba149248c1378f45b1938b16d2f729bdff`는 이전 기록과 일치한다.
- 세 후보의 metgrid와 real 총 6회가 모두 종료 0이며 각각 `met_em`과 `wrfinput_d01`을 생성했다.
  예보는 실행하지 않았다. 원본 운영 경로는 수정하지 않았다.
- 실행 전후 입력·설정 23개 해시가 일치한다. 실제 loader 검사에도 미해결 symbol/library가 없다.

## 저장 결과 검사

기존 `check_native_hybrid_geometry.py`를 변경 없이 사용했다.

| 검사 | OFF | HYDRO | LIQUID_RADAR_RH1 |
|---|---|---|---|
| metgrid / real 종료 | 0 / 0 | 0 / 0 | 0 / 0 |
| native hybrid 압력층 구조 | PASS | PASS | PASS |
| direct-QV 지표압 재계산 | 거부: SOILHGT 없음 | PASS | PASS |

저장된 6개 파일의 시각은 모두 13 UTC다. 필수 물리장의 유효값은 유한하고 여섯 수분
성분은 비음수다. 필드별 shape·mask·범위는
[stored_fields.json](../scratch/cp06_native_transport_mmz5mo7g/stored_fields.json)에 보존했다.

Native 격자는 39 × 282 × 234다. HYDRO/LIQUID의 지표압 재계산 최대 오차는
0.00982115 Pa, dry 지표압은 0.01329708 Pa로 기존 0.05 Pa 허용치 이내다.
이는 Rd=287 J/(kg K), g=9.81 m/s² 및 기존 host profile을 가정한 진단이며 보존 승인과 다르다.

OFF는 원래 129-record 출력을 유지하며 SOILHGT를 제공하지 않는다. 후보는 235-record로
SOILHGT와 수상체를 추가한다. metgrid의 QV 및 다섯 수상체 flag는 셋 모두 1이나,
OFF 수상체는 기존 배경 우선순위 경로를 사용하므로 후보 차이를 순수 알고리즘 증분으로
해석할 수 없다. OFF는 real의 `sfcprs`, 두 후보는 `sfcprs2` 경로를 선택한다.
OFF 지표압 검사의 실패 로그를 보존했으며 입력 필드를 추가해 통과시키지 않았다.

## 증거와 잔여 연결

[실행 색인](../scratch/cp06_native_transport_mmz5mo7g/RESULT.json),
[재현 명령](../scratch/cp06_native_transport_mmz5mo7g/run.sh),
[종료 기록](../scratch/cp06_native_transport_mmz5mo7g/exits.txt)에 경로·hash·검사 결과를 보존한다.
[RED 검토](../scratch/cp06_native_transport_mmz5mo7g/RED_REVIEW.md)는 이 6회 전달 실행 범위에서 통과다.
[GREEN 검토](../scratch/cp06_native_transport_mmz5mo7g/GREEN_REVIEW.md)도 시각·차원·필수 필드,
수분 비음수, direct-QV 선택과 HYDRO/LIQUID 저장 후보 차이를 독립 확인했다.
보존된 run.sh는 당시 실행 기록이며, 다시 실행하려면 새 scratch 경로를 먼저 준비해야 한다.

기존 처리·통합 관측은 이미 입력으로 사용된다. 남은 동적 결합 작업은 관측자료 재확보가 아니라
omega target/sigma의 도출·불확실도 연결과 post-QC LOS의 beam/Nyquist/시각/표본 분할 전달이다.
현재 reader는 target/sigma를 채우지 않고, COM은 별도 evidence로 유지하며, exchange v1은
동적 입력과 LOS를 받지 않는다. 원래 OFF 계약을 보존하는 결합 전달 구현이 필요하다.

기존 연구 real을 실제로 실행한 결과이며 원본 KLFS real과의 동등성, native 전체 상태 왕복,
질량·에너지 보존 및 과학적 성능 통과를 주장하지 않는다. 새 물리 코드나 감사 프레임워크는 추가하지 않았다.

## Independent native mapping readback — 2026-09-11

The additional [mapping review](../scratch/cp02_native_mapping_review_20260911/NATIVE_MAPPING_REVIEW.md)
checks the retained OFF/HYDRO/LIQUID outputs. Six moisture field names/units and
the direct QV path are source-bound. Native moisture values are finite and
nonnegative. Independent float32 recomputation of
`THM=(T+300)*(1+(461.6/287)*QVAPOR)-300` matches all 2,573,532 cells in each mode
exactly. Physical pressure `P+PB` is finite and positive.

These checks do not independently reproduce pressure-level interpolation,
mask/frame transfer, or dry-mass closure. The pressure difference involving
`MU+MUB+P_TOP` and PSFC remains a dry/total diagnostic, not a conserved-mass
identity. CP02 #4 remains incomplete.
