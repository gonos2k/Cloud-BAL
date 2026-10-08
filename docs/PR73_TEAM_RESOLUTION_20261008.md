# PR73 팀 조사와 수정 기록 — 2026-10-08

기준은 병합된 PR72 `e9a0e38a8ada142426a0b645f1598265611cf9d4`입니다. 독립 작업 네 갈래(최초 native 거부·물성, 상태변환·공동 혼합, 분석 추정·저장, 독립 검토)를 병행했습니다. 물리 승인 상태는 **FAIL/OPEN**, 현재 native 상태는 **REJECTED**입니다.

## 발견하고 수정한 구현·시험 누락

| 발견 | 수정·검증 |
|---|---|
| 최초 거부 로그에 종·값·단위·좌표 범위가 없었음 | 초기 입장 검사의 공통 결과를 추가하고 같은 pretrace의 실제 native 첫 거부로 확인. 호출 lat과 global j를 구분. |
| native 근거에 새 객체·archive member·실행파일의 연결 및 필수 post-call 검사 부족 | 강화된 두 번째 실행 receipt와 별도 완료 감사. 101 입력 보존, 필수 출력 4개 누락은 FAIL로 유지. |
| 종 조합 시험이 단순 classifier만 호출하거나 process 이후 상태를 물성 초기값으로 읽을 위험 | 실제 초기 cloud/ProgB/slope/rate 구성 직후의 test-only hook. 각 Intel profile에서 16 reference+16 poisoned history 재진입. n0·후속 과정 통과는 주장하지 않음. |
| 부재 mask를 legacy fixture의 QG/BG 설정이 덮어씀 | 순서를 수정. 별도 full-process mask-5 거부 로그는 보존. |
| QNI 추가 채널의 stacked offset 및 비활성 optional 출력·QI 인터페이스 gate 누락 | `(channel-1)*kte`, 출력 정의, QI 경향 존재 gate. 실제 Shinhong routine에서 QNI-only/NC+QNI 두 layout과 비활성·누락 인터페이스 검사. |
| 추정기의 bound/equality 결합·일관된 중복 제약 처리 부족 | scaled control/KKT와 선형 종속 제약 분류. 하·상·고정 bound, 단위 재표현, 중복/모순 제약 검사. |
| 분석증분을 외부 source와 혼동하거나 endpoint 총질량 검사 우회 가능 | 독립 analysis ledger. 같은 fixed-pressure mass helper를 pipeline preflight와 endpoint에 적용하고 writer가 재평가. 잘못된 입력은 반영·파일 생성 전 거부. |
| 분석 확장의 reader allow-list·부분 payload·legacy 호환 시험 누락 | 전체 확장 그룹의 일관성 검사와 오류 변이; 분석 그룹을 완전히 제거한 기존 상태 수용. |
| 시험이 미실행 producer 단계에 synthetic PASS를 부여함 | estimator-only writer 경로는 명시적 FAILED/AUTHORITY 단계 기록을 요구. 물리 성분 readback만 PASS; 전체 diagnostic CLI는 INVALID/UNBOUND, REJECTED. |
| 실행 후 source/test hash와 설명이 달라질 위험 | 실행별 원본 hash와 최종 source identity를 구분하고 최종 팀 검토로 대조. |

## 이번에 얻은 근거

- 실제 첫 거부: ice mass-only, QI `3.5308575789291633e-35`, NI `0`, i=133, call-lat=2, k=1. staged QICE/QNICE는 0/0이므로 불일치는 staged input 이후에 만들어짐. 최초 생성 연산자는 아직 미확인.
- 실제 소스의 초기 물성 종 조합과 이력 독립성은 제한적으로 통과. 별도 전체 process probe는 mask 5에서 거부됐으며 이후 mask와 O2는 미실행.
- 선택된 연구 Shinhong QI/QNI 공통 operator의 routine 수준 O0/O2 검증 통과. driver 누적·coupled native·dry-carrier 보존은 미검증.
- 제조 H/B/R 기반 비영 분석은 endpoint evaluator→writer→독립 성분 reader로 연결. 생산 pipeline 생성, 실제 12 UTC 관측 권한, PSD·대기 질량–바람·native 전달 승인은 별도 미완료.
- focused Python 17개 통과. pinned Intel의 물성·QI/QNI·분석 저장 O0/O2와 기존 SHADOW 회귀는 각 receipt의 범위로 유지.

## 남은 종료조건

실제 완료 갱신에서 Q/N/B를 함께 유지하는 원인 수정, freezing/초미량 입자의 유효한 생성·소멸 정책, 공통 dry carrier의 물·에너지·경계 회계, 독립 관측·배경 모형을 쓰는 실제 feasible 공동 후보, 동일 후보의 native 첫 호출과 10·30·60분 검증이 필요합니다. 국지 fixture와 실패 방어의 PASS를 합쳐 전체 물리 PASS로 승격하지 않습니다.

[체크리스트](PR73_PHYSICAL_CLOSURE_CHECKLIST_20261008.md) · [독립 검토](PR73_INDEPENDENT_REVIEW_20261008.md)
