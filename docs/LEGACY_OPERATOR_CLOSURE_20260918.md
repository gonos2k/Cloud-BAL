# Legacy continuity 연산자 교정 — 2026-09-18

기준: PR #26 병합 `3024d1305b991542d314f40677e7948510df1438`.
PR #25의 오류를 고친 국지 수학 계약과 실제 비영 balance 성공을 구분한다.
현재 판단은 **연산자 연결 교정 / 수정 경계 문제의 실자료 RHS 부적합 / ON 및 과학 승인 보류**다.
과거 [수학 검토](LEGACY_BALANCE_MATH_REVIEW_20260917.md), PR #24 초기화 재현,
기존 pressure/omega/rollback/writer 검증은 각 역사적 범위로 보존한다.

## 수정한 계산

`qbal_continuity_setup`이 유효 pressure/support 행과 허용된 face coefficient를 만든다.
`qbal_multiplier_increment`는 그 계수로 기존 stagger의 U/V/omega 증분을 계산한다.
`qbal_continuity_row`는 같은 계수에 실제 divergence의 metric을 적용하여 `A=DG`의 행을
구성한다. `LEIBP3`와 최종 선형 잔차가 이 행을 사용한다. 별도의 harmonic/평균 dp
행렬식과 사용하지 않는 `fthree`를 제거했다. canonical 코드는 변경하지 않았다.

목표는 활성 행에서 `D(y_proposed+delta_y)=0`, RHS는 `-D(y_proposed)`다.
Influence는 support와 mobility에만 쓰고 RHS에 추가로 곱하지 않는다. 기존 G를
유지한 직접 이산 보정이며, 변분 최적성·adjoint 또는 SPD를 주장하지 않는다.
고정 순서 Gauss–Seidel을 사용하며 200회와 기존 승수 correction 한도를 유지한다.
독립된 최종 lambda에서 `A lambda-b`의 RMS/max/위치를 계산하고 최대 잔차
`1e-10`도 요구한다. 저장 real32 상태는 명시적 덧셈/divergence 반올림 bound로 검사하며
기존 BALCON의 물리 acceptance는 완화하지 않는다. 최대 lambda correction과 실제
U/V/omega 증분, 전체 유효 pressure 영역과 지원 영역의 물리 잔차를 구분해 출력한다.

## 계획서를 보완한 이유와 경계 계약

기존 외곽 `lambda=0`은 외곽으로 보정 유량을 허용하지만 그 물리적 권한이 명시되지
않았다. 이번에는 **각 continuity 호출의 제안 상태가 가진 경계 유량을 고정**한다.
외곽·상하단·terrain/sentinel·지원 밖과 접하는 face의 증분은 0이다. 반복 중 이웃
lambda를 덮어쓰거나 비활성 행을 Dirichlet 저장소로 쓰지 않는다. 기존 BALCON의
다른 PHI/이류/마찰 단계와 최종 native 경계 전체를 재설계한 것은 아니다.

성분별 사전검사는 양의 양방향 연결에서 왼쪽 영벡터 후보를 얻고, 실제 `A^T w`
인증 후 `w^T b`를 검사한다. `4096*epsilon(real64)`는 이 대수 인증의 상대 반올림
한도이며 물리 오차 기준이 아니다. 일반 비가역 metric에서 후보를 인증하지 못하면
`UNRESOLVED`로 거부한다. 이는 일반 왼쪽 영공간 solver의 완성이 아니다. 영행의
비영 RHS는 아무리 작아도 거부하고, 양의 support인데 유효 행이 없을 때도 거부한다.
RHS 평균 제거·forcing 변경·tolerance 완화·영증분 성공 대체는 하지 않는다.

## 실제 전 영역 배열 검사

이 검사는 이전 실패 실행에서 보존한 2026-08-16 13 UTC, 235×283×22의 **실제 배열**을
새 생산 절차에 입력한다. 승인된 after 또는 새 예보가 아니다. 기존 lambda를 real64로
변환하고 새 비활성/ghost 위치를 0으로 제한한 허용 승수로 항등식을 검사한다.
새 생산 solver의 해라고 주장하지 않는다. source-bound Intel O0/O2를 각각 새 scratch
cwd에서 빌드하며, 입력 snapshot과 생산 소스의 전후 해시를 검사한다.

- 입력 snapshot SHA256: `96932e53e5f30bf3e9c307617765aaa7200750ec01d4ead6b45842faf97fa661`.
- 새 활성 행: **723,638개**. 기존 행렬의 777,213개와 비교할 때 유효 donor 및 경계
  제거 계약이 바뀌었음을 함께 명시해야 한다.
- 생산 계수/RHS의 O0/O2 sparse export는 바이트 일치했다.
- 실제 배열에서 `A lambda-D(G lambda)` RMS는 `8.073862774540482e-12`,
  real32 저장/차분 반올림 bound 위반은 0개였다. 잔차 선형성 검사도 bound 위반이 없었다.
- 새 연결 성분: **222개, 모두 닫힌 성분**, 그중 **171개 영행**.
- 독립 SciPy 행렬 구성/왼쪽 영공간 검사에서 **222개 모두 부적합**이다.
- 가장 큰 722,121행 성분: 정규화 `w^T b=7.091670514468622e-6`,
  전치 잔차의 상대 L1 norm `2.4153563470733697e-16`.

과거의 닫힌 3개 부적합 성분과 이번 222개를 같은 행렬의 진단처럼 합치지 않는다.
원래 `(45,208,4)` 정체의 단일 원인을 이번 새 경계 조건의 결과로 소급 확정하지 않는다.

## 같은 입력의 전체 legacy QBAL 재실행

최종 소스 SHA256 `cb49b1e92c6829e12bf8f26a936b5058c7f41f107dcc143f59a97e4a739dc951`로
고정 Intel O0/O2 전체 실행파일을 각각 새 scratch에서 빌드했다. 두 실행 모두 원본
manifest의 90개 입력과 격리 복사본 90개의 SHA256이 일치했다. 두 실행은 초기
continuity의 성분 검사에서 **222개 부적합을 검출하고 exit 1**로 종료했다.
반복 전 실제 잔차 RMS는 `1.172313659371345e-4`, 최대값은
`3.146454154594372e-3`, 위치는 `(162,71,11)`이었다.

반복을 시작하지 않았고 적용 증분은 0이다. 이는 실패 원복이며 영증분 성공이 아니다.
writer 진입이 거부됐고 `balance/lt1`, `balance/lw3` 산출물은 없었다.
ON LAPSPREP와 native 전후 비교는 수행하지 않았다. 근거는 로컬
`scratch/actual_qbal_rerun_receipt.json` 및 `scratch/actual_qbal_rerun_evidence/`다.
앞선 두 시도는 `get_grid_dim`에서 SIGSEGV가 발생하여 과학 검증에서 제외했다.
짧은 격리 경로와 충분한 stack을 사용한 후속 실행을 위의 최종 근거로 삼으며,
이 두 조건 중 어느 것이 앞선 오류의 원인인지는 분리 검증하지 않았다.

## 검증과 제한

- 집중 연산자 검사 O0/O2: 가변 influence/오차/metric/pressure 간격의 항등식,
  호환 RHS를 가진 가변계수 선형계의 비영 해와 실제 최대 잔차 `1e-10` 이하,
  모든 동결 face의 영증분, 부적합 사전검사의 입력 불변과 실패 원복 확인.
  RHS beta 재가중 및 행 lookup 이동 변이를 검출했다.

- 전체 BALCON O0/O2: 기존 비영 후보·localized 후보와 원복 검사 통과.
  최종 projection 우회, reverse PHI 누락, A-grid 수평항 제거와 omega 부호 반전의
  네 대조군은 각 최적화에서 거부됐다. 합성 회귀이며 실자료 성공이 아니다.
- nonlinear/stagger/omega 및 caller의 8개 복원문 삭제 변이: O0/O2 통과.
- 독립 Python 성분 검사: 전역 합이 0이어도 부적합한 비대칭 행렬, 전역 합이
  0이 아니어도 왼쪽 가중 합이 호환되는 행렬, 비가역 cycle, 영행/anchor 구분 확인.
- 초기 개발 BALCON 실행 한 건은 실행 중 소스 변경을 해시 가드가 검출하여
  최종 증거에서 제외했다. 이후 고정 소스의 전체 실행을 별도로 보존했다.

실제 실행·최종 source-bound 검사 근거는 작업공간 receipt에 기록한다. 대용량 배열,
실행파일, 실제 입력을 git에 포함하지 않는다. 새 비영 ON, native 전달, 초기 충격,
수분/열역학 보존 및 예보 개선은 승인되지 않았다.

## 재현 경로

```bash
CLOUD_BAL_KEEP_TEST_OUTPUT=1 bash tests/run_qbal_operator_tests.sh
CLOUD_BAL_KEEP_TEST_OUTPUT=1 bash tests/run_qbal_balcon_tests.sh
CLOUD_BAL_KEEP_TEST_OUTPUT=1 bash tests/run_qbal_nonlin_tests.sh
CLOUD_BAL_KEEP_TEST_OUTPUT=1 bash tests/run_qbal_real_operator_tests.sh \
  /absolute/path/operator_snapshot.bin /absolute/scratch/operator_rows
python3 tests/diagnose_qbal_components.py \
  /absolute/scratch/operator_rows.O0.bin /absolute/scratch/components.json
python3 tests/test_qbal_component_diagnostics.py
```

실제 snapshot이 없는 환경에서는 해당 검사를 수행했다고 표시하지 않는다.
부적합 진단 도구의 정상 종료는 물리 PASS가 아니다. `components.json`의
`INCOMPATIBLE`/`UNRESOLVED`를 판정해야 한다. 다음 설계에서는 관측/배경과 물리적으로
양립하는 경계 유량 또는 support/제약 정책을 정해야 한다. 현재 사례에 맞추기 위한
자동 평균 제거와 반복수 증가는 해결책으로 사용하지 않는다.
