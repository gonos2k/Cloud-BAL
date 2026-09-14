# CP02 동일 입력 baseline / OFF native 비교

2026-09-11. CP02 원래 세 번째 조건의 실제 실행 증거다. 여섯 조건 전체의 완료 판정은 아니다.

최신 pinned Intel LAPSPREP O0/O2 실행파일에서 `CLOUD_BAL_SHADOW_EXPERIMENT`를 제거해
일반 baseline을 실행했다. 같은 13 UTC 처리 입력과 `lapsprep.nl`을 사용하는 이전 OFF와
대조했다. 두 경로는 동일 실행파일을 사용한다. baseline은 `prepare_shadow_wps`를 호출하지 않고,
OFF는 canonical identity 검사 뒤 원래 host slabs를 유지한다.

O0/O2 baseline 두 실행이 모두 종료 0이며 각각 이전 OFF와 전체 WPS bytes가 같다.
O0 baseline WPS를 새 scratch에서 같은 metgrid·연구 real 설정으로 전달했다.
metgrid·real도 종료 0이며 실제 native 출력까지 다음 동일성을 확인했다.

| 저장 결과 | 변수 | 전역 속성 | 판정 |
|---|---:|---:|---|
| metgrid | 92 | 128 | 전체 원시값·차원·dtype·변수/전역 metadata 동일, 파일 byte-identical |
| native wrfinput | 208 | 93 | 전체 원시값·차원·dtype·변수/전역 metadata 동일, 파일 byte-identical |

Native SHA256: `79717e03effb77a8ec787bcdec526ca4abad3b95e8b8fce5dc31f55efb25e6f1`.
입력·설정·실행파일 31개 해시는 실행 전후 일치한다. 새 컴파일이나 코드 변경은 없었다.

증거: [RESULT.json](../scratch/cp02_baseline_native_ruoww1a5/RESULT.json),
[실행 명령](../scratch/cp02_baseline_native_ruoww1a5/run.sh),
[경로](../scratch/cp02_baseline_native_ruoww1a5/paths.json).
OFF의 독립 실행과 연구 host 범위는 [이전 전달 기록](CP06_NATIVE_TRANSPORT_20260911.md)에 있다.

이 비교는 현재 유지되는 일반 경로와 Cloud-BAL OFF의 동일 입력 보존을 입증한다.
원래 운영 KLFS 실행파일과의 동등성이나 CP01의 수정된 private KDM6 profile로 실행했다는
주장은 아니다. OFF와 baseline 모두 SOILHGT 없는 같은 경로다. 두 잘못된 물리 상태도
서로 동일할 수 있으므로, byte 동일성을 canonical→native 질량분모·EOS·보존의 독립 검증으로
확대하지 않는다. CP02 네 번째 조건과 CP06-A 선행 결합 검증은 여전히 미완료다.

독립 [GREEN 검토](../scratch/cp02_baseline_native_ruoww1a5/GREEN_REVIEW.md)도 위 저장 파일과 OFF 분기를 확인했다.
