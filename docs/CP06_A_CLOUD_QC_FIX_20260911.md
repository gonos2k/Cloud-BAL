# 구름 QC 후보 출력 거부 수정

2026-09-11. 팀 검토에서 재현한 P2의 후속 수정이다. CP06-A 결합 실험 또는 native 완료를 뜻하지 않는다.

## 문제와 수정

유효 구름형이 있는 셀의 구름량이 임계값보다 작으면 column 계산은 해당 구름 필드에
`QUALITY_QC_REJECTED`를 붙인다. 이전 출력 검증은 이 정상적인 QC 변경도 원본과 달라졌다고
거부해, 전체 pipeline replay에 도달하기 전에 `reason=9`로 종료했다.

`cloud_bal_real_netcdf.f90`의 기존 조건 몇 줄만 수정했다. 구름 출처가 있는 경우에는
중복된 선행 thermo 비교 대신 이미 존재하는 전체 pipeline replay로 후보를 검증한다.
임의 후보 변경은 정확한 stage·budget·support·전체 상태 비교에서 계속 거부한다.
phase storage 검증 후에 구름 출처 여부를 읽도록 순서도 유지했다.
수식, 물리 제어값, 운영 상태 보존, 과학·배포 승인 조건은 변경하지 않았다.
새 감사 프레임워크는 추가하지 않았다.

최종 reader SHA256: `88b63fcd19e212014c854fdc8cc8d04a2ddb8a2dbdac7eb61269df330a91fd85`.
이전 reader와의 차이는 `scratch/cloud_qc_fix_20260911/reader.before.f90`를 기준으로 확인할 수 있다.

## 실제 검증

- 수정 전: 원래 입력의 private 복사본에서 native LCP `[10,0,102]`만 `0.7150400877 → 0`으로
  변경했다. 기존 CTY=2를 유지한 이 유효 입력은 실제 O0 실행에서 종료 1, `reason=9`를 재현했다.
  [재현 기록](../scratch/cloud_qc_review.c5s3d3cp/mutation.json)과 원래 실패 로그는 보존했다.
- 수정 후: pinned Intel ifx 전체 LAPSPREP를 새 scratch에서 O0/O2 각각 빌드했다.
  원래 OFF/HYDRO/LIQUID와 QC 입력 HYDRO/LIQUID, 총 10회가 모두 종료 0이다.
- 원래 세 후보의 WPS는 수정 전과 byte-identical이다.
- QC 사례 WPS와 sidecar NetCDF도 O0/O2 byte-identical이다. 저장된 입력 셀은 유효한 LCP=0,
  CTY=2를 그대로 유지한다. 후보 u/v/omega는 배경과 동일하다.
- `science_assessed=0`, `promotion_eligible=0`을 유지한다.
- 중간 `27a6c9b9…` 실행은 보존하되 최종 판정에는 `O0_final/`, `O2_final/`만 사용한다.

실행·build·source/output hash 색인: [RESULT.json](../scratch/cloud_qc_fix_20260911/RESULT.json).
RED 검토: [RED_REVIEW.md](../scratch/cloud_qc_fix_20260911/RED_REVIEW.md).

GREEN은 기존 Fortran 회귀시험에 정상 구름 QC 허용과 임의 품질·출처 변경 거부 사례를
추가했다. pinned Intel O0/O2 전체 시험이 종료 0으로 통과했다. 시험 산출물은
`scratch/real_shadow_io_tests.gsl3lB/`에 보존했다.
`tests/test_real_shadow_io_contract.f90` SHA256:
`7dcfbfdcfcebf8bfc2e68fbc904feb549e40ce7f4d4774afd18923be1da4f051`.
GREEN 검토: [GREEN_REVIEW.md](../scratch/cloud_qc_fix_20260911/GREEN_REVIEW.md).

기존 Python 감사기의 cloud 확장 미지원, HGT 저장 반올림, 실제 관측 target/LOS 연결 및
결합·native 검증 범위는 [이전 실제 실행 기록](CP06_A_PROCESSED_INPUT_RUN_20260911.md)과 동일하다.

후속 [연구 native 전달 기록](CP06_NATIVE_TRANSPORT_20260911.md)은 최신 세 WPS의
metgrid/real 실행과 OFF SOILHGT 검사 한계를 별도로 보존한다.
