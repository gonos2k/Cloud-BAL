# 현재 연구 상태

실행 근거: PR106 종료 기록과 PR107 병합본
`4c290f1fff9c78cbe9967ce312114f0f53a27a43`의 진단 구현.
실제 native 근거는 선택 객체를 교체한 C2 partial-host 구성이다.
전체 WRF·종속 라이브러리 clean rebuild나 운영 승인을 뜻하지 않는다.

| 항목 | 확인된 범위 |
| --- | --- |
| OFF/HYDRO/COUPLED/PROJECTED/STRUCTURED/AMPLITUDE | 같은 C2의 640초 실행 완료 |
| 동일 진폭 대조·0–600초 반응 | 비교 완료; STRUCTURED는 일부 반응을 줄이고 Phi는 증가 |
| H/A/N 1시간 요청 | 모두 38단계·760초 후 INCOMPLETE, 모델 종료코드 1 |
| 실제 14 UTC 관측·paired 점수 | 모델 출력 부재로 건너뜀; NOT_EVALUATED |
| T1 미세물리 회계 | 선언한 한 호출의 source별 설명; 전체 host 수지와 별도 |
| 위성 IR112 원자료 재생 | 9개 LAPS 지원 셀에서 S8A=필터된 최대 BT, S8W=평균 BT 확인 |
| 전체 물·에너지·질량–바람·초기 충격·독립 skill | OPEN / NOT_EVALUATED |

PR107의 HYDRO T39 진단 실행은 38단계 완료 뒤 timestep 39에서 `INCOMPLETE`로 종료됐다.
닫힌 receipt와 후처리 결과는 [T39 종료 포착·재생 인계](T39_CLOSED_REPLAY_20261027.md)에 기록했다.
최초 T39/RK2 group 거부 셀 `(199,52,21)`은 알려진 fatal consumer `(2,219,13)`와 다르다.
prefix 비간섭 비교는 HYDRO의 공통 0–600초 범위에 한정된다. Pinned Intel O0/O2에서
최초 셀의 저장 거부와 별도 fatal 셀의 확산 producer를 국지 재생했다. 최초 후보의 정확 입력식은
Q/B 상한 밖이며, fatal producer에서는 REAL128에서 REAL64로 각각 변환할 때 상한을 넘는다.
최초 셀의 원래 생성 stencil과 수정 실행 검증은 미완료다. 물리 검증은 OPEN, T2는 NOT_EVALUATED다.

PR108에서는 [입력·실행 실패 계약](PR108_INPUT_EXECUTION_CONTRACTS_20261026.md)을
보강했다. PR109에서는 [DOUBLE 입력·출력 검증·portable 격리](PR109_MEMORY_AND_PORTABILITY_20261027.md)의
남은 공백을 수정했다. PR110은 [정적 격자 입력과 portable 잔여 의존성](PR110_STATIC_INPUT_AND_PORTABILITY_20261027.md)을
보강한다. PR111은 [정적 격자의 결측값·좌표 검증](PR111_STATIC_VALUE_VALIDATION_20261027.md)을
실제 reader–WPS 출력 경계에 연결한다. 이 공학적 변경은 예보·관측 판정을 승격하지 않는다.

## 바로 다음 작업

1. 보존된 T39 결과에서 group 첫 거부와 fatal consumer가 다른 셀임을 유지하고,
   최초 셀 `(199,52,21)`의 source·transport 생성 입력을 추가로 연결한다.
2. 보존된 국지 재생을 기준으로 source 표현의 공동 반올림·보존 계약을 검토한다.
   별도 fatal 셀의 원인을 전체 group으로 일반화하거나 상한·cache를 임의 변경하지 않는다.
3. 원인이 확인된 연산만 수정한다. 모델 정책을 바꾸면 같은 실행파일로 H/A/N의
   기존 640초·T39 이후·원래 1시간 종료점을 다시 검증한다.
4. 완료된 동일 유효시각 자료에 기존 관측·paired 평가를 적용한다. 위성은 실제
   센서 계수·관측기하·집계를 갖춘 한 채널 전방연산자가 별도로 필요하다.

바람 투영·평활화, 허용오차, N/B prior, source cache 정책은 원인 확인 없이
바꾸지 않는다. 극소량이라는 이유만으로 무조건 0 처리하지 않는다.
진단 구현·시험 통과나 이 불완전한 T39 포착은 수정·물리 검증·1시간 완료를 대신하지 않는다.

## 근거

- [PR106 종료·실패·위성 범위](PR106_CLOSED_FORECAST_AND_IR_SCOPE_20261026.md)
- [PR103 동일 진폭 대조](PR103_AMPLITUDE_ATTRIBUTION_20261026.md)
- [PR105 관측 판독·paired 평가](PR105_OBSERVATION_PAIRING_20261026.md)
- [PR84 체크리스트 — 역사 기록](FAST_COMPLETION_CHECKLIST_20261012.md)

기존 과학적·운영 승격 조건은 유지한다. 더 작은 norm이나 정상 종료만으로
관측 적합성·물리적 균형을 승인하지 않는다.

## CP02 강수 소실 지점의 초기 수종 추적

[보관 실행파일 호출 경계 재생](CP02_CALL_BOUNDARY_20261028.md)에서 HYDRO·LIQUID의
20점 × 22층 QR·QS 차이가 `derive_column_physics` 반환 시 이미 나타남을 확인했다.
일반·계측 재생의 WPS와 shadow는 당시 보관본과 바이트 동일하다. 마지막 derive 반환과
pipeline 후보도 포착한 8개 필드에서 같다.
[내부 경계·평가 입력 재생](CP02_INNER_SPECIES_20261028.md)은 첫 HYDRO의 선택 표본에서
레이더 진단 작업 배열이 수송 호출 전후에 유지되고, `publish_hydrometeor_candidate`
호출에서 배경 QR·QS가 이 작업 배열의 REAL32 값으로 바뀜을 확인한다.
HYDRO의 evaluation 인자는 null이며, LIQUID의 실제 평가 상태·설정·반환 budget을 포착했다.
[레이더 입력·publish 조건 재생](CP02_RADAR_INPUTS_20261028.md)은 원래 반사도와
상분할의 값·valid·quality·source, 실제 밀도 피연산자, 190개 위치의 진단·저장 값을
연결한다. refresh 표본 누락은 분석 전에 거부하며 정수 반환 상태도 원시 바이트로 포착한다.
진단 입력과 배경 대체 조건의 물리적 타당성, 전체 물수지와 강수 개선의
인과관계는 아직 미확정이다. CP02 결과는 위 C2 T39 완료와 별개다.

[배경 CSV 계약과 QC·상별 비교](CP02_BACKGROUND_CONTRACT_20261028.md)에서는
캡처의 기준 CSV 해시와 실제 분석 입력을 대조한다. quality 0인 선택 표본에서도
rain·snow 감소가 커서 `0x20`만을 원인으로 지목하지 않는다. 기존 비관측 250개 표본은
배경 수종도 모두 0이므로 비관측 양의 배경 수종 보존을 검증한 것으로 보지 않는다.
진단 total과 배경 생성 규약의 계수·단위·밀도 기준 및 대조 표본 연결이 다음 조사 대상이다.

[공통 밀도 비교와 강수검증 대조 지점](CP02_DENSITY_CONTROLS_20261029.md)은
190개 원시 표본의 진단 농도와 배경 등가 농도를 같은 진단 밀도로 비교한다.
16개 RN1 지점의 실제 WRF 네 모서리·가중치로 첫 시간 48개 강수량을 재현하고,
별도 탐색용 양의 배경 수종 표본을 추가했다. 이는 새로운 예보 성능 개선을
입증한 결과가 아니며, 당시 배경 생성식·과정 수지·강수 영향은 계속 조사한다.
