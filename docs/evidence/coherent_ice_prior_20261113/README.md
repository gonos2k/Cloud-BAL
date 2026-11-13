# 같은 경계의 빙정 사전정보: 실행 근거

[결과 보고서](../../COHERENT_ICE_PRIOR_20261113.md)는 실제 CONTROL의 호스트 정리 전 QI·QS·NI와 물리 상태, 원래 선택 영역의 누락, 기존 공통 생성기의 진단을 구분한다. 이 묶음에는 새 초기장이나 예보 성능 검증 결과가 없다.

- [native](native/README.md): 실제 8개 rank의 gzip 원시 자료와 manifest, 실행 기록, 소스 밖 재조립 방법. 아홉 필드를 같은 호출 경계에서 읽었다.
- [fixed_application](fixed_application/definition.json): 원래 294,792셀과 수용 정책. 미확보 6,047셀 때문에 전체 제안은 중단한다.
- [science](science/README.md): 같은 확보 셀의 history 비교, pinned IFX 2026 공통 연산 진단과 재생 명령. 확보 교집합 288,745셀은 적용 영역이 아니다.
- [figures](figures/diagnostics.png): 자료의 확보 범위와 수치 관찰. `plot_diagnostics.py`는 두 공개 JSON에서 그림을 만든다.
- [validation](validation/): 입력·자료·코드·보고서의 독립 검토와 Python 경계 시험. 원래 실행 경로는 receipts에 남긴다.
- [kg](kg/): 별도 KLAPS50·Cloud-BAL 그래프 갱신과 파생 wiki 감사 기록. 구조 최신성은 실행·과학적 검증이 아니다.

정보 조립 PASS, 개별 공통 연산의 수용, 초기화 제안 전체의 수용, 과학적 사전정보의 신뢰도는 서로 다른 판정이다. 누락을 0이나 history 값으로 채우지 않으며, 배경이 극미량일 때의 신뢰도와 큰 분석 증분에 적용할 물리 가정은 미결정이다. 현재 B1·기존 26개 조건을 유지한다.
