# PR87 두 단계 공동 상태 점검

현재 V42 OFF·COUPLED 40초와 완료 상태 감사가 통과했습니다. 동일 실행파일의 60초 대조가 진행 중입니다.

- [x] PR85 v17 실행파일·입력·기존 receipt 보존
- [x] 동일 지점의 POST_KDM6 → host cleanup → STEP_END → STEP_BEGIN → FogDES 입력 연결
- [x] QC만 지우는 host cutoff를 최초 생성 연산자로 확인
- [x] MP37의 paired moisture만 KDM6 공동 cleanup에 맡기고 QV·QS·scalar·경계 방어 유지
- [x] 원문 cleanup/FogDES의 pinned Intel O0/O2 인과 회귀
- [x] 짧은 실행의 요청 길이별 snapshot schedule 및 엄격한 완료 gate
- [x] 진단 경량화의 첫 KDM6 입력·출력 바이트 동일성 확인
- [x] 기존 NG/AUT/G ledger의 개별 alpha와 composite gamma 기여 분리
- [x] AUT/G의 실제 full proposal을 기존 상태검사에 연결한 제한 사유 기록
- [x] 같은 입력·후보 실행파일의 OFF/COUPLED 40초 실행 완료 (V42; 두 KDM6 호출·입력 무결성 확인)
- [x] 두 단계 Q/N/B·단위·선언 수용범위의 완료 상태 감사 — V42 통과; 얼음은 기존 8-ULP 기준, exact-source 진단 별도
- [x] 실제 기록의 제한 사유별 물리량 가중 집계와 다음 수정 대상 선정
- [ ] 60초 확대 완료 — V42 진행 중; 과거 V39는 세 번째 단계 RK1에서 INCOMPLETE
- [ ] 600초 확대와 관측·역학 반응 평가 — V42의 유효한 40·60초 확인 뒤 진행
- [ ] 같은 호출의 host hybrid carrier·전체 물·에너지 폐합
- [ ] 질량–바람 균형과 초기 충격 감소의 과학적 승인

모델 정상 종료와 마지막 두 과학적 승인은 별개입니다. 기존 1차 수송과
보류 과정의 물리적 영향은 계속 OPEN으로 둡니다. 실행·검사 근거는
[통합 기록](evidence/pr87_integration_20261016.json)과
[설명](PR87_TWO_STEP_COMPLETION_20261016.md)에 연결합니다.
