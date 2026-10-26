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

PR107에서는 단계·좌표 선택을 수정하고 pinned Intel 진단 빌드를 완료했다.
HYDRO 한 건의 T39 포착용 실행을 시작했으며, 종료·원인 규명은 아직 미확인이다.
[진단 변경과 실행 범위](PR107_T39_CAPTURE_20261026.md)를 따른다.

PR108에서는 [입력·실행 실패 계약](PR108_INPUT_EXECUTION_CONTRACTS_20261026.md)을
보강한다. 이 공학적 변경은 아래 예보·관측 판정을 승격하지 않는다.

## 바로 다음 작업

1. 기존 T15 producer/T32 공동 실패 근거를 보존하면서 진단 대상을 명시한다.
   T39/RK1 `(2,219,13)`의 실제 source 생성과 T39/RK2 소비,
   최초 group predicate·pair·cell·store stage·retry 결과를 연결한다.
2. HYDRO 한 실행에서 원래 거부를 포착하고 국지 재생한다. callback 한 셀의
   비트가 세 arm에서 같아도 첫 grouped 원인이 같다고 미리 판단하지 않는다.
3. 원인이 확인된 연산만 수정한다. 모델 정책을 바꾸면 같은 실행파일로 H/A/N의
   기존 640초·T39 이후·원래 1시간 종료점을 다시 검증한다.
4. 완료된 동일 유효시각 자료에 기존 관측·paired 평가를 적용한다. 위성은 실제
   센서 계수·관측기하·집계를 갖춘 한 채널 전방연산자가 별도로 필요하다.

바람 투영·평활화, 허용오차, N/B prior, source cache 정책은 원인 확인 없이
바꾸지 않는다. 극소량이라는 이유만으로 무조건 0 처리하지 않는다.
진단 구현·시험 통과나 실행 시작은 실제 T39 포착·수정·1시간 완료를 대신하지 않는다.

## 근거

- [PR106 종료·실패·위성 범위](PR106_CLOSED_FORECAST_AND_IR_SCOPE_20261026.md)
- [PR103 동일 진폭 대조](PR103_AMPLITUDE_ATTRIBUTION_20261026.md)
- [PR105 관측 판독·paired 평가](PR105_OBSERVATION_PAIRING_20261026.md)
- [PR84 체크리스트 — 역사 기록](FAST_COMPLETION_CHECKLIST_20261012.md)

기존 과학적·운영 승격 조건은 유지한다. 더 작은 norm이나 정상 종료만으로
관측 적합성·물리적 균형을 승인하지 않는다.
