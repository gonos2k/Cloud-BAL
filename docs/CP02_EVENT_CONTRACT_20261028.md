# CP02 호출 이벤트 구성 검증

PR118의 원시 캡처는 완전하지만, 분석기는 실제 이벤트 구성이 불완전한 입력을
정상으로 처리할 수 있었다. 이번 수정은 실제 stage·호출 쌍·순서를 검증한 뒤
호출 경계 분석을 진행하게 한다. 기존 수치와 과학적 결론은 바뀌지 않는다.

## 결함 재현과 수정

기준은 PR118 병합본 `f308ebcb0378ab367951656f75598b1ec9267e33`이다.
보존된 HYDRO의 주 실행 첫 `derive_entry_state_in` 하나를
`unrecognized_derive_entry_state_in`으로 바꾸고 counts, record 수, 모든 수치는
유지했다. 실제 연구 호스트의 원본 NetCDF와 기존 기대 해시를 그대로 사용했다.

| 입력 / 분석기 | 종료 코드 | 결과 |
| --- | ---: | --- |
| 잘못된 stage / 수정 전 | 0 | PASS, HYDRO 주 실행 derive 누락; writer 재생 호출만 분석 |
| 같은 잘못된 stage / 수정 후 | 1 | 거부; summary.json·profiles.csv 미생성 |
| 원래 정상 HYDRO·LIQUID / 수정 후 | 0 | 기존 프로파일 4,224행 바이트 동일 |

정상 결과의 요약도 입력 식별 정보와 프로파일 경로를 제외하면 기존 보존본과
동일하다. HYDRO의 shadow vapor·temperature 끝점 부재는 계속 명시한다.
[수정 전 재현](evidence/cp02_event_contract_20261028/before_fix.json),
[수정 후 실제 CLI](evidence/cp02_event_contract_20261028/after_fix.json).

검사는 다음을 요구한다.

1. 네 종류의 허용 stage만 존재해야 한다.
2. 실제 stage별 record 수가 선언된 counts와 일치해야 한다.
3. pipeline·derive의 진입/반환 키가 각 실험의 기대 집합과 일치해야 한다.
4. 주 실행과 writer 재생이 기대 순서대로 진행돼야 한다. 각 derive의 진입·반환은
   같은 정수 호출 번호로 짝지어진다.

이 도구는 HYDRO의 주 실행 1 / 재생 2, LIQUID의 주 실행 1–3 / 재생 4–6을
대상으로 하는 고정 실험 판독기다. JSON records는 capture 도구가 기록한 시간순
배열이며, 임의 정렬한 이벤트나 다른 실행 규약을 자동으로 수용하지 않는다.
독립 검토 중 같은 역할의 호출 번호를 서로 바꾸면 키 집합만으로는 잘못된 연결을
검출하지 못함을 확인해 순서 검증도 추가했다.

## 회귀와 증거 보존

[새 portable 시험](../tests/test_cp02_boundary_events.py)은 저장소의 압축 캡처만
읽는다. 변경 입력은 임시 JSON으로 작성해 실제 판독 함수를 실행하며, 외부 연구
파일의 존재 여부나 Intel 설치에 의존하지 않는다. 정상 두 arm, 알 수 없는 stage,
실제 횟수 불일치, 잘못된 역할, 고립된 반환, 호출 번호 교환과 진입/반환 오연결을
검사한다. 새 8개와 기존 WPS·전이·점수 31개를 합쳐 **39개 통과**했다.
기존 Matplotlib/pyparsing deprecation warning 196건은 실패로 세지 않았다.
전체 portable suite나 Fortran 빌드·WRF 예보는 이번에 실행하지 않았다.

이전 capture, profiles, summary, validation과 과거 manifest는 수정하지 않는다.
과거 validation의 analyzer 해시는 당시 코드의 해시이며, 수정된 analyzer와 새
시험은 이번 [validation](evidence/cp02_event_contract_20261028/validation.json)에
별도로 연결한다. [독립 팀 검토](evidence/cp02_event_contract_20261028/team_review.json)는
수정 및 실제 실패 거부를 확인하고 GO로 종료했다.

## 다음 내부 계측을 위한 바이너리 확인

새 모델 실행 없이 같은 보관 실행파일의 DWARF와 disassembly를 조사했다.
실행파일 SHA-256은 `dbea173ec059afba40ae2d46193e5f5f33a63c18d02d4fd5db5ac23b504e2e65`다.

| 확인 | 근거 / 범위 |
| --- | --- |
| `evaluation_state` 인자 | derive의 10번째 formal parameter, DWARF DIE `0x2976f`, `cloud_bal_state_type` 참조 |
| 실제 인자 존재·값 | 아직 포착하지 않음; formal parameter가 있다는 사실과 구분 |
| 직접 하위 호출 후보 | `saturation_adjust_pressure_state` (`0x670080`), `refresh_dry_air_mass_measure` (`0x5ab1e0`) |
| 최초 QR·QS 변경 연산 | 여전히 미확정 |

DWARF에 `DW_AT_optional`이 없다는 사실만으로 인자가 필수라거나 런타임에
존재한다고 판단하지 않는다. 이름을 함수 목록에서 찾지 못한 것을 인자 부재로
해석하지도 않는다. 다음 계측은 derive 진입 시 실제 `evaluation_state`와 설정
인자를 확인하고, HYDRO 첫 호출 안의 실제 하위 호출 전후 상태를 연결해야 한다.
정적 call 명령이 있다는 것만으로 해당 분기를 실제로 실행했거나 QR·QS를 바꿨다고
판단할 수 없다. [정적 조사 기록](evidence/cp02_event_contract_20261028/inner_probe.json).

이번 수정은 LAPSPREP 초기화 판독의 공학적 보강이다. 혼합비 감소의 물질량 수지,
강수 개선 인과관계, RN1 시각·coverage, 최신 C2 T39 수정·1시간 완료는 기존과 같이
OPEN이다. 보관 소스의 부분 복구 상태도 그대로이며 새 GDB 재생을 수행하지 않았다.
