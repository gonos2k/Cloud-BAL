# PR74 에이전트 팀 조사·해소 기록

4개 역할을 분리했다: 공통 제약 추정기, 실제 QNI driver/native,
전체 모멘트 audit, 독립 oracle·최종 검토. 모든 하위 에이전트는
`gpt-6-luna`, reasoning `high`로 실행했고 동시 최대 4개를 유지했다.
유지관리 소스와 과거 실패 receipt는 바꾸지 않았다.

| 발견사항 | 조치·재검증 |
|---|---|
| 보고된 최적 lower bound 누락 | 활성 좌표 제거, 정확한 경계 대입, KKT 정류성·승수 부호·상보성 인증. 원문 main 실패와 새 0.3/cost 0.545 재현. |
| 보고된 변수별 단위 재표현 오거부 | B/R marginal scaling을 factor 전에 적용. U/V만 1000배인 동등 문제 및 covariance-form 독립 해와 대조. |
| fixed bound의 승수 부호·라벨 | 등식처럼 자유 승수 처리, side=fixed. 원래 primal 단위와 정규화 gradient/duals를 명시. |
| active bound와 dependent equality, decimal bound 합산 | 등식 basis와 outward interval 선별, 실제 endpoint 검사 유지. 회귀 통과. |
| 유한 입력 누적 overflow | 원문 과정량·배경·RHS 계산에서 유한성 검사, NUMERICAL_FAILURE 분류. |
| 보조 QNI 시험의 undeclared 변수 | 선언 수정 후 실제 pinned Intel O0/O2 컴파일·실행. 더 넓은 actual driver 실행을 대신하지 않음. |
| runner가 profile flags를 복제 | pinned `intel_toolchain.sh` 배열을 직접 사용, 최종 runner replay를 새 scratch에 보존. |
| 변경 후 stale source/receipt hashes | solver·driver·comparison의 의존 순서를 확정하고 최종 bytes로 다시 연결. 과거 receipt는 보존. |
| NI 오류를 음수로 잘못 해석할 위험 | public trace에 음수·비유한 NI=0개. wrapper의 positive→zero 변환과 common pair validation을 분리. |
| strict compile만으로 실행 mode를 추정 | 실제 inherited partialhost link의 `-ftz` 확인. 정확한 helper no-ftz/FTZ sensitivity를 별도 기록; runtime MXCSR는 미캡처. |

## 범위와 판정

- 51개 focused Python 시험에 solver 16개, 독립 oracle 4개 및 공통 audit/parser
  회귀를 포함한다. 396개 scalar oracle는 제조 사례이며 실제 오류율이 아니다.
- 새 scratch의 pinned Intel O0/O2 estimator→endpoint evaluator/writer→성분
  재읽기는 통과한다. 전체 canonical CLI의 artifact=UNBOUND,
  candidate=REJECTED는 유지된다. `run_cloud_bal_pipeline`은 실행하지 않았다.
- 실제 PBL driver는 QNI를 한 번 누적하고 해당 branch를 완료한다. 100개 입력을
  보존한 partialhost O0/O2 run은 NI unit adapter에서 exit 128로 중단된다.
  필수 post-call 4개가 없으며 첫 물리 호출·timestep 완료를 주장하지 않는다.
- 공통 pair replay에서 신규 전체 negative=23,494, mass-only=740,
  moment-only=299,933, nonfinite=0이다. 첫 hypothetical pair는 ice
  `(104,2,1)`이며 실제 adapter fatal 좌표와 다르다. 이 개수는 물 수지가 아니다.
- 모델의 생성·수송·소멸·표현 정책, PBL DEL/dry carrier, freezing 밀도,
  동일 후보의 물·에너지·질량–바람·native 10/30/60분 검증은 OPEN이다.

[독립 최종 검토](PR74_INDEPENDENT_FINAL_REVIEW_20261008.md)와
[종료조건 체크리스트](PR74_PHYSICAL_CLOSURE_CHECKLIST_20261008.md)에
직접 실행 근거 및 미해소 조건을 연결한다. **전체 물리 초기화는 FAIL/OPEN,
실제 native 후보는 REJECTED**이며 작은 구현시험을 합산해 승인하지 않는다.
