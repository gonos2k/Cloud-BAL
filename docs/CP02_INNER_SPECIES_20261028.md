# CP02: 초기 QR·QS 후보 기록 구간과 실제 evaluation 입력

## 결론과 범위

보관된 CP02 LAPSPREP 실행파일을 같은 입력과 pinned Intel runtime으로 재생했다.
첫 HYDRO derive에서 선택한 **20점 × 22개 저장층**의 후보 QR·QS가 배경값에서
바뀌는 구간은 `publish_hydrometeor_candidate` 호출이다. 이 호출 직전 작업 배열은
`diagnose_radar_cells`의 반환값이며, 중간 `transport_precipitation_flux` 호출에서
선택 표본의 rain·snow·graupel 작업 배열은 바뀌지 않았다.

이는 초기화 실행 구간의 관측이다. 레이더 역산의 물리적 타당성, 전체 영역의 수송,
물질량 보존 위반이나 지상 강수 적중 소실의 인과관계를 판정하지 않는다.
생산 Fortran, 물리 정책, 임계값과 예측값은 변경하지 않았다.

## 실제 HYDRO 실행 순서

아래는 PC 숫자의 정렬이 아니라 실제 breakpoint 방문 순서다.

| 실행 경계 | rain 평균, g/kg | snow 평균, g/kg |
| --- | ---: | ---: |
| derive 입력 / publish 직전 후보 | 0.078104856 | 0.051504678 |
| diagnose 직전 REAL64 작업 배열 | 0 | 0 |
| diagnose 직후 REAL64 작업 배열 | 0.053394824300 | 0.006995739219 |
| transport 직전·직후 작업 배열 | 위 값과 비트 동일 | 위 값과 비트 동일 |
| publish 직후 REAL32 후보 | 0.053394824429 | 0.006995739206 |

평균은 저장 기압층을 포함한 440개 표본의 동일 가중 평균이며, 건조 질량·층 두께·면적
가중 물질량이 아니다. 작업 배열의 0은 진단용 배열의 호출 전 값이며, 배경 QR·QS가
0이었다는 뜻이 아니다.

publish 전 후보의 8개 포착 필드는 derive 입력과 동일하다. publish 후 rain 154개,
snow 36개 표본이 감소하며, 나머지 포착 필드는 유지된다. 세 강수 수종의 publish 후
REAL32 값은 전달된 REAL64 작업 배열을 REAL32로 변환한 결과와 각각 440개 모두 같다.
publish 후 후보는 마지막 derive 반환과도 포착한 8개 필드에서 동일하다.

첫 HYDRO derive의 `saturation_adjust_pressure_state` 호출은 **0회**다.
`refresh_dry_air_mass_measure`는 publish 안에서 1회 관찰되며, 선택 수종 상태의
전후 비교와 질량 계수 표본을 별도로 보존했다. 이 호출의 이름만으로 전체 물수지를
검증했다고 판단하지 않는다.

따라서 다음 조사 대상은 보관 바이너리의 `diagnose_radar_cells`가 사용하는 실제
레이더·상분할·밀도 입력과, 진단된 수종을 기존 배경 대신 기록하는 조건이다.
현재 최신 소스를 당시 미복구 물리 소스로 대체하거나 QR·QS를 일괄 증량하지 않는다.

## 실제 선택 입력

derive 진입의 원시 ABI 포인터와, 함수 prologue 및 선택 배열 descriptor 초기화가
끝난 뒤의 DWARF 값 읽기를 분리했다. 포인터가 nonzero라는 사실만으로 정상 데이터를
주장하지 않고, 배열 bounds와 실제 읽기 가능 여부를 함께 기록했다.

| 항목 | HYDRO | LIQUID 주 실행 호출 1–3 |
| --- | --- | --- |
| evaluation_state 인자 포인터 | null | nonzero, 실제 상태 읽기 가능 |
| thermo_active / thermo_surface | null | 235×283×22 배열 읽기 가능 |
| target_rh | null | REAL64 1.0 |
| config | 실제 scalar 필드 보존 | 실제 scalar 필드 보존 |
| thermo_budget / analysis_budget | 반환 후 원시 값 보존 | 반환 후 원시 값 보존 |

LIQUID의 evaluation_state는 전체 이전 후보 복사본이 아니다. 호출 2·3의 평가 상태는
호출 1에 비해 수증기와 온도 153개 표본에서 달라지고, 포착한 다른 수종과 압력은 같다.
평가 상태의 수증기·온도는 해당 이전 derive 반환과 같다. 반면 cloud water·rain·snow는
이전 반환과 각각 153·154·36개 표본에서 다르다. 고정된 `state_in`과 별도로 전달되는
평가 상태를 구분해야 호출별 반환 변화의 입력을 설명할 수 있다.
평가 상태 호출 2→3에서도 수증기 8개 표본이 달라지므로, 두 평가 입력이 완전히
같다고 해석하지 않는다. 내부 하위 호출 계측은 첫 HYDRO에만 적용했다.
LIQUID capture의 내부 호출 수 0은 **미계측**을 뜻하며 실제 호출 부재의 근거가 아니다.

반환 수지 구조체와 grid의 `pressure_mass_measure`, `dry_air_mass_measure`도 보존했다.
이를 전체 영역의 독립 과정량 검산으로 승격하지 않는다. 미포착·읽기 불가능한 값은
0으로 대체하지 않는다.

## 실행 식별과 비간섭

- 실행파일 SHA-256: `dbea173ec059afba40ae2d46193e5f5f33a63c18d02d4fd5db5ac23b504e2e65`.
- 입력 114개는 보관 원본·재생 사본 모두 실행 후에도 기존 해시와 일치한다.
- runtime manifest의 41개 라이브러리를 재검사했다. `tests/intel_toolchain.sh`를 적용하고
  `OMP_NUM_THREADS=1`, unlimited stack으로 별도 `/var/tmp` 작업 디렉터리에서 실행했다.
- HYDRO·LIQUID 모두 실제 LAPSPREP 종료 코드 0, 완전한 capture를 얻었다.
- 두 arm의 WPS 및 shadow **4개 출력 모두 이전 pinned 재생 및 보관 해시와 동일**하다.
- 각 arm은 주 실행과 writer 검증 재생의 pipeline 2회를 포함한다. HYDRO derive 2회,
  LIQUID derive 6회이며, 이를 새 물리 시간 단계로 세지 않는다.
- GDB callbacks는 메모리 읽기와 별도 기록만 수행한다. inferior 함수 호출·값 대입은 없다.

정확한 당시 column-physics/LAPSPREP 소스의 완전 복구나 clean rebuild는 수행하지 않았다.
코드 위치는 해시로 고정한 실행파일의 DWARF와 disassembly에 연결한다. 초기 탐색 재생은
최종 분석에서 제외하며, 보존된 두 final capture는 동일한 계측기 해시로 생성했다.

## 자료와 재분석

자료: [replay receipt](evidence/cp02_inner_capture_20261028/replay_receipt.json),
[HYDRO capture](evidence/cp02_inner_capture_20261028/hydro_capture.json.gz),
[LIQUID capture](evidence/cp02_inner_capture_20261028/liquid_capture.json.gz),
[바이너리 구간](evidence/cp02_inner_capture_20261028/binary_intervals.json).

후처리는 실제 event 구성·호출 쌍·표본 키·raw bytes를 검사한 뒤 요약을 생성한다.
상태·질량 계수 표본과 반환 budget은 capture에 보존하며, 선택 표본의 수종 평균만으로
영역 총량을 계산하지 않는다. 재분석 명령과 검증 결과는 같은 디렉터리의 validation에 기록한다.

[HYDRO 요약](evidence/cp02_inner_capture_20261028/analysis/hydro_summary.json)과
[LIQUID 요약](evidence/cp02_inner_capture_20261028/analysis/liquid_summary.json),
각 `*_profiles.csv`는 호출 번호·주 실행/재생 역할·REAL64 작업 배열/REAL32 상태를 구분한다.
`changed_count`는 작업 배열 또는 후보 상태의 PRE→POST 비교에만 수치를 기록한다. 직접 비교하지 않은
행은 CSV에서 빈 값, JSON에서 null이며 변경 0개를 뜻하지 않는다.
새 디렉터리를 만든 뒤 다음처럼 재분석할 수 있다(출력 경로가 이미 있으면 거부).

```bash
evidence=docs/evidence/cp02_inner_capture_20261028
prior=docs/evidence/cp02_call_boundary_20261028
result=$(mktemp -d /var/tmp/cp02-inner-analysis.XXXXXX)
python "$evidence/analyze_inner.py" "$evidence/hydro_capture.json.gz" \
  --arm HYDRO --prior-outer "$prior/hydro_capture.json.gz" \
  --output "$result/hydro_summary.json" --profiles "$result/hydro_profiles.csv"
python "$evidence/analyze_inner.py" "$evidence/liquid_capture.json.gz" \
  --arm LIQUID_RADAR_RH1 --prior-outer "$prior/liquid_capture.json.gz" \
  --output "$result/liquid_summary.json" --profiles "$result/liquid_profiles.csv"
```

새 회귀시험 12개를 포함한 호출 경계·WPS·강수 집중 시험 **51개**가 통과했다.
기존 파일별 runner에서도 새 시험 **12 passed, 0 skipped**를 확인했다.
portable 등록은 확인했지만 전체 portable suite, Fortran 재빌드나 WRF 적분을 실행한
결과로 계산하지 않는다. 독립 코드 검토와 원시 capture 재계산에서도 차단 사항이 없었다.

RN1 상류 입력 시각·coverage, C2 T39 수치 수정·1시간 완료, WRF 첫 미세물리 반응과
6시간 강수 개선 판정은 여전히 별도 미완료 항목이다.
