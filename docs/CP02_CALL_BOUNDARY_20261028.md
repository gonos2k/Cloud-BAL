# CP02 초기 QR·QS: 보관 실행파일의 호출 경계 재생

CP02의 당시 LAPSPREP 실행파일을 그대로 사용해 HYDRO와 LIQUID를 재실행했다.
첫 시간 ≥5 mm 적중 소실 합집합 20점의 22개 저장층에서, QR·QS 차이는
`derive_column_physics` 호출의 입력과 반환값 사이에 이미 나타난다.
마지막 derive 반환값과 pipeline 최종 후보는 기록한 8개 필드 모두 동일하다.
이 결과는 **변경이 발생하는 호출 구간**을 좁힌다. 내부에서 최초로 값을 바꾼
수식·분기나 강수 손실의 인과관계를 확정하지는 않는다.

## 실행파일·입력·출력 연결

- 기준 소스: PR117 `f79bc2a190de78ac9209109766f4d0e2ddec0a2b`.
- 당시 실행파일: `upstream_lapsprep_build.HjBepF/klps_anal_prep.exe`,
  SHA-256 `dbea173ec059afba40ae2d46193e5f5f33a63c18d02d4fd5db5ac23b504e2e65`.
- 입력: `cp02_actual12_liquid_wps.HisIOM/input`의 114개 파일을 새 외부 scratch에 복사.
  실행 전후 원본과 사본의 해시를 확인했다.
- 시각·설정: `262281200` (2026-08-16 12 UTC), 기존 namelist, HYDRO 또는
  `LIQUID_RADAR_RH1`, OMP 1, unlimited stack, pinned Intel profile.
- Fortran 재컴파일 없이 보관된 Intel 실행파일과 확인된 runtime을 사용했다.
  정확한 당시 소스 일부가 없으므로 기존 source-verifying launcher의 통과나
  clean rebuild로 표현하지 않는다.

| 비교 | HYDRO | LIQUID |
| --- | --- | --- |
| 일반 실행 → 보관 WPS·shadow | 두 파일 바이트 동일 | 두 파일 바이트 동일 |
| GDB 계측 실행 → 일반 실행·보관본 | 두 파일 바이트 동일 | 두 파일 바이트 동일 |
| GDB / inferior 종료 코드 | 0 / 0 | 0 / 0 |
| derive 진입·반환 수 | 각각 2 | 각각 6 |
| pipeline 진입·반환 수 | 각각 2 | 각각 2 |

전체 파일 동일성은 이 두 재생의 산출물 비간섭 근거다. 모든 내부 연산의
동일성이나 다른 설정·예보에 대한 비간섭으로 일반화하지 않는다.
[실행 receipt](evidence/cp02_call_boundary_20261028/run_receipt.json)와
[사전 입력·runtime 검사](evidence/cp02_call_boundary_20261028/preflight.json)에
실제 경로와 해시를 보존했다.

초기 8192 KB stack 시험은 NetCDF writer에서 종료코드 174로 끝났다. 동일
실행파일·입력에 unlimited stack을 적용한 정상 재생과 구분해 기록했다.
GDB startup·배열 descriptor·호출자 변수 탐색을 개발하던 실패 probe도 완료
근거에 포함하지 않았다. 최종 도구는 반환 인자의 주소와 호출자 상태의 주소를
일치시켜 읽으며 inferior 변수에 대입하거나 함수를 호출하지 않는다.
기존 capture 경로 재사용은 거부하고 원래 파일을 보존하는 것도 확인했다.

## 실제 호출 구조와 선택 표본

첫 pipeline은 `run_pressure_analysis_shadow`에서 호출된다. 두 번째는
`write_shadow_diagnostics → validate_shadow_write_contract → pipeline_result_replays`
의 검증 재생이다. 두 번째 pipeline을 새 물리 시간 단계나 외부 반복으로 세지 않는다.
HYDRO는 각 pipeline에서 derive를 1회, LIQUID는 3회 호출했다.

CSV의 zero-based `shadow_i/j`를 Fortran 인덱스로 변환하고, 20점 × 22층 ×
8개 필드(vapor, cloud water, cloud ice, rain, snow, graupel, temperature, pressure)를
원시 REAL32 바이트와 함께 저장했다. 모든 저장층의 동일 가중 통계이며 440개 중
382개가 above-ground다. 지하 저장층을 제외한 물질량·면적 평균이 아니다.
valid flag와 above-ground도 기록했지만 source/quality, density, 과정별 수지,
선택적 `evaluation_state` 인자는 포착하지 않았다.

| 경계 (주 실행) | rain 평균 g/kg | snow 평균 g/kg |
| --- | ---: | ---: |
| 두 실험의 pipeline 입력 / derive state_in | 0.078104856 | 0.051504678 |
| HYDRO derive 1 반환 / pipeline 후보 | 0.053394824 | 0.006995739 |
| LIQUID derive 1 반환 | 0.053394824 | 0.006995739 |
| LIQUID derive 2·3 반환 / pipeline 후보 | 0.053354812 | 0.006994303 |

HYDRO 첫 derive 반환에서 입력 대비 rain 154개·snow 36개 값이 달라지고,
다른 6개 포착 필드는 동일하다. LIQUID의 각 반환은 같은 `state_in` 대비
rain 154개·snow 36개와 vapor·cloud water·temperature 각각 153개가 다르다.
LIQUID 반환 1→2에서는 rain 139개·snow 14개·vapor 8개·cloud water 55개가
달라지고, 반환 2→3은 선택 표본에서 동일하다.

모든 derive의 `state_in`은 선택 표본에서 초기 pipeline 입력과 같다.
그러나 `evaluation_state` 등 다른 인자는 포착하지 않았으므로 “동일한 모든
입력으로 다른 결과를 냈다”고 해석하면 안 된다. 주 실행과 writer 재생의
입력·각 대응 derive 반환·최종 후보는 8개 필드에서 모두 같다.

## 보관 shadow와 직접 비교한 범위

HYDRO shadow에는 5개 수상체의 background/candidate 배열이 있고,
LIQUID에는 여기에 vapor·temperature가 추가된다. 해당 모든 가용 배열에서
진입값은 background, 최종 반환값은 candidate와 440개씩 비트 동일하다.
pressure는 별도의 1차원 저장 기압 좌표와 비교해 동일했다.
HYDRO vapor·temperature의 독립 shadow endpoint 배열은 없어 그 비교는
`unavailable`로 남겼다. 내부 capture끼리의 동일성 확인과 구분한다.
QR·QS의 기존 프로파일 CSV도 실제 shadow 값과 일치했다.

- [분석 요약](evidence/cp02_call_boundary_20261028/analysis/summary.json)
- [층별 8필드 통계](evidence/cp02_call_boundary_20261028/analysis/profiles.csv)
- [HYDRO capture](evidence/cp02_call_boundary_20261028/hydro_capture.json.gz),
  [LIQUID capture](evidence/cp02_call_boundary_20261028/liquid_capture.json.gz)
- [계측 도구](evidence/cp02_call_boundary_20261028/capture_boundaries.py),
  [후처리 도구](evidence/cp02_call_boundary_20261028/analyze_boundaries.py)

## 소스 검색과 다음 조사

이름이 다른 Fortran 파일·backup·archive와 Git 잔여 객체까지 범위를 넓혔지만,
이번 검색에서도 당시 column physics와 LAPSPREP의 정확한 해시 사본을 찾지 못했다.
이는 기록된 검색 범위의 결과이며 다른 경로나 archive에 없다는 증명이 아니다.
[Column 검색](evidence/cp02_call_boundary_20261028/column_source_search.json),
[LAPSPREP 검색](evidence/cp02_call_boundary_20261028/lapsprep_source_search.json)을 보존한다.
PR117에서 확보한 정확한 pipeline 소스의 부분 복구 상태는 유지된다.

이번에는 보관 바이너리의 실제 호출 경계로 자료 공백을 일부 좁혔다. 다음 조사는
같은 바이너리의 derive 내부 하위 호출 또는 정확한 소스와 연결된 중간 상태에서
전체 수종·열역학 변화를 확인하는 것이다. 이번 결과만으로 특정 수종 분배식,
증발·침강·상한 처리에 원인을 부여하거나 QR·QS를 일괄 증량하지 않는다.

20점은 사후 원인 추적 표본이다. 기존 3,688점·6시간·6임계값 점수와 예측값은
바꾸지 않았고 새 예보도 수행하지 않았다. RN1의 실제 상류 시각·coverage,
최신 C2 T39 최초 생성 stencil·수치 수정·1시간 완료, 전체 물·에너지 수지는
여전히 OPEN이다. 평균 혼합비 감소는 물질량 손실이나 지상 강수 감소량이 아니다.

검증은 보관 Intel 실행파일의 두 일반 재생·두 계측 재생, 실제 NetCDF endpoint
대조와 독립 팀 검토에 한정한다. 전체 portable suite·Fortran clean build·WRF
적분을 이번 작업의 통과 항목으로 계산하지 않는다.

기존 WPS 판독·무손실/무강수 전이·강수 점수의 집중 시험은 31개 통과했다.
Matplotlib/pyparsing deprecation warning 196건이 있었고 실패는 없었다.
이 시험은 이번 실제 호출 계측의 독립 검토와 구분해 기록한다.
