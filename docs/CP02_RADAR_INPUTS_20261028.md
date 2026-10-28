# CP02 refresh 검증과 레이더 진단 입력 추적

기준은 PR120 `f648805ec060fbdcd94bc7259011784de80bf853`이다. 이번 변경은
후처리의 refresh 표본 검증, GDB 스칼라 판독, 보관 LAPSPREP 실행파일의
첫 HYDRO derive 계측에 한정한다. 생산 Fortran과 예보 설정은 변경하지 않았다.

## 누락 표본과 스칼라 반환 상태

refresh 진입·반환 각각에 일반 상태 검증을 적용하고, 20개 지점의 키를
바깥 pipeline 입력과 대조한다. 두 상태가 함께 비거나 같은 일부 표본이
빠져도 실패한다. 값이 없는 상태를 변경 개수 0으로 기록하지 않는다.
원래 HYDRO 캡처의 두 `points`만 비운 CLI 대조는 수정 전 종료 0·산출물 생성,
수정 후 종료 1·summary와 profiles 미생성이다.
[대조 기록](evidence/cp02_radar_inputs_20261028/refresh_reproducer.json)

`read_storage()`는 정수·실수·논리·열거 스칼라를 `scalar_record()`로 읽고,
구조체는 기존 멤버 판독을 유지한다. 과거 캡처의 미판독 상태를 수정하거나
추정값으로 채우지 않는다. 새 실제 재생에서 refresh의 INTEGER*4 반환 상태는
`14000000`, 즉 20으로 확보됐다.

## 실제 입력과 진단 결과의 구분

선택 표본은 기존 첫 시간 적중 소실 합집합 20점 × 저장 기압층 22개다.
사후 선택 진단 표본이며 전체 강수 성능 표본을 대신하지 않는다.

`observed`, `phase`, `phase_uncertain`, `zlinear`는 diagnose 호출 경계 양쪽에서
읽는다. 이번 실행에서는 진입 때 0이던 observed·phase·zlinear가 반환 때
190개 위치에서 채워졌다. 따라서 진입 배열을 원래 레이더 관측으로 해석하지 않는다.
진단에 전달된 상태의 반사도·상분할 자료와 진단이 만든 배열을 분리한다.
`radar_derived`는 diagnose의 formal 인자가 아닌 호출자의 문맥 값이며,
publish의 입력 조건으로 별도 기록한다.

밀도 함수의 실제 pressure·temperature·vapor와 반환 rho_d, 상분할 후 total·
종별 작업값·정수 상태, 배열 저장 직후 값은 같은 `(i,j,k)`로 연결한다.
방문되지 않은 내부 분기는 `NOT_CAPTURED`와 빈 수치로 표현한다. 이를 0이나
실행되지 않았다는 전 영역 결론으로 바꾸지 않는다.

## 실제 포착 결과

[440개 연결 행](evidence/cp02_radar_inputs_20261028/analysis/profiles.csv)과
[요약](evidence/cp02_radar_inputs_20261028/analysis/summary.json)은 저장된 캡처만으로 재생성한다.
[독립 원시 바이트 계산](evidence/cp02_radar_inputs_20261028/independent_raw_review.json)은
분석기 함수를 재호출하지 않고 다음 관계를 대조했다.

| 포착 항목 | 선택 표본의 결과 |
| --- | --- |
| 전체 표본 / 진단 관측 마스크 참 | 440 / 190 |
| 반사도 valid 참과 진단 마스크 | 190개 위치 모두 일치 |
| 상분할 코드 | 1: 154개, 2: 36개, 0: 250개 |
| 관측 190개의 반사도 source 정수 | 모두 8 |
| 관측 190개의 반사도 quality 정수 | 0: 75개, 32 (`0x20`): 115개 |
| publish 직전 radar_derived 참 | 같은 190개 위치 |
| publish phase_uncertain 참 | 0개 |
| 실제 밀도 함수 입력 | 190개 모두 상태의 REAL32 T/p/qv를 REAL64로 확장한 값과 동일 |
| 밀도 반환 → 상분할 반환 → 작업 배열 저장 | 같은 190개 키에서 각 단계 포착 |
| 진단·publish·refresh 및 각 상분할 반환 상태 | 정수 20, 원시 바이트 `14000000` |

관측 위치의 `zlinear`는 원래 REAL32 반사도를 사용한
\(10^{0.1\,dBZ}\)와 최대 상대 차이 약 `1.75e-16`이다. 이는 보관된 값의 수치
대조이며, 누락된 당시 소스 전체를 복구했다는 뜻은 아니다. 상분할 반환의
rain+snow+graupel은 포착한 total과 같고, 각 종은 바로 뒤 작업 배열 저장값과 같다.
최종 후보의 REAL32 저장은 기존 분석기의 검사를 그대로 거친다.

반사도 quality의 `0x20`과 publish의 `phase_uncertain`은 서로 다른 필드이다.
이번 자료는 전자가 설정된 115개 관측 위치에서도 후자가 거짓인 실제 경로를
보여준다. 과거 소스·QC 계약과의 연결 없이 이것을 오류 또는 허용 가능한 관측이라고
승인하지 않는다. 다음 확인은 이 표지의 당시 의미와 상분할 불확실성 전달 정책이다.
배경 QR·QS를 일괄 증량하거나 항상 배경 이상으로 강제하는 수정은 하지 않았다.

[실행 영수증](evidence/cp02_radar_inputs_20261028/replay_receipt.json)의 최종 v2는
모델 종료 코드 0, CAPTURE_COMPLETE이고 WPS·shadow가 기존 보관본과 바이트 동일하다.
실행 전후 원본·복사 입력 각 114개와 runtime 41개, 실행파일과 계측 소스 해시를 확인했다.
그 전에 내부 표본 구조를 확인한 예비 재생은 종료 전 중단했으며
[미완료 기록](evidence/cp02_radar_inputs_20261028/preliminary_probe.json)으로 구분하고
최종 분석·통과 수에 넣지 않았다.

## 범위와 남은 연구

이 재생은 당시 해시의 Intel LAPSPREP 실행파일을 사용한다. 현재 소스를
과거 소스로 대체한 재빌드가 아니며, 새 WRF 예보도 아니다. GDB는 상태를
읽기만 하고 inferior 함수 호출이나 메모리 변경을 하지 않는다.
정확한 원시 입력·실행파일·runtime 및 출력 동일성은 별도 실행 영수증으로 연결한다.

포착한 440개 표본의 단순 혼합비 평균은 건조 질량·층 두께·면적 가중 물수지가
아니다. 진단 수종과 배경 수종의 차이를 찾았다는 사실만으로 진단식의 결함이나
강수 악화의 인과관계를 확정하지 않는다. 다음 연구에는 같은 강수대의 유지 적중·
오경보 제거 대조 지점과 원인에 대응한 동일 조건 예측 비교가 필요하다.

RN1 상류 시각·coverage, 최신 C2 T39 수정 및 H/A/N 1시간 완료, 전체 물·에너지
수지와 독립 예측 skill은 계속 미완료다. 기존 3,688점·6시간·여섯 임계값의
강수 점수와 과거 캡처·validation은 그대로 보존한다.

## 재생과 검증

저장된 캡처의 후처리는 외부 Intel·NetCDF 원본 없이 실행된다. 두 출력 경로는
새 경로여야 하며, 잘못된 상태·이벤트·레이더 표본은 파일 작성 전에 거부한다.

```bash
python docs/evidence/cp02_radar_inputs_20261028/analyze_radar_inputs.py \
  docs/evidence/cp02_radar_inputs_20261028/hydro_capture.json.gz \
  --prior-outer docs/evidence/cp02_call_boundary_20261028/hydro_capture.json.gz \
  --output /var/tmp/new-radar-summary.json \
  --profiles /var/tmp/new-radar-profiles.csv
```

집중 시험은 77개 통과다. P2의 양쪽 동시 빈 표본·부분 누락·키 불일치, 스칼라와
구조체 판독, 레이더 원자료 누락·내부 호출 순서·부모 연결·반환 상태 변조를 포함한다.
유지 파일별 실행기의 새 radar 시험 10개도 모두 통과했고 portable 등록을 확인했다.
이 10개는 77개에 포함된다. 전체 portable suite와 Fortran 재빌드는 실행하지 않았다.
[시험 로그](evidence/cp02_radar_inputs_20261028/focused_tests.txt)

수정된 기존 분석기로 과거 HYDRO·LIQUID 캡처를 재분석한 summary·profiles 4개는
모두 기존 보존본과 바이트 동일하다.
[이전 분석 보존 확인](evidence/cp02_radar_inputs_20261028/old_analysis_preservation.json)

새 실제 캡처는 `tests/intel_toolchain.sh`를 source한 별도 scratch에서
`CP02_CAPTURE_RADAR_INPUTS=1`, `CLOUD_BAL_SHADOW_EXPERIMENT=HYDRO`,
`OMP_NUM_THREADS=1`, `ulimit -s unlimited`로 실행했다. 실행파일·입력·출력 경로와
해시는 실행 영수증에 있다. `gdb -q -batch <보관 실행파일> -x
 docs/evidence/cp02_inner_capture_20261028/capture_inner.py`가 날짜 인자
`262281200`으로 실행하며, `CP02_CAPTURE_OUTPUT`과 `CLOUD_BAL_WPS_OUTPUT`은
새 절대 경로를 사용한다. `LAPS_DATA_ROOT`는 사전 해시 검사를 통과한 보관 입력 복사본이다.
