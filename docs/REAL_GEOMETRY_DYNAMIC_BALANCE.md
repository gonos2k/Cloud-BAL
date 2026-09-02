# 실제 KLAPS 격자 동적 balance 수치 검증 계약

## 목적과 권한

이 단계는 실제 2026-08-16 12--15 UTC KLAPS/QBAL 입력의 격자, 지형,
pressure cell, 분석풍, 레이더 수상체 제안과 FSF 경계자료 위에서 비영
`u/v/omega` balance solver를 실행한다. 검증 대상은 수치 연산자, 수렴,
국지성, rollback과 진단 게시 경로다.

동적 target과 경계의 권한은 모두 `MANUFACTURED_TEST`다. 따라서 결과의
과학 권한은 `NONE`이고, 정상 OFF/SHADOW pipeline 및 운영 출력에는 들어갈
수 없다. 실제 관측 기반 연직속도 target의 검증을 대신하지 않는다.
산출물의 balance 범위도 `TARGET_INCREMENT_PROJECTION_ONLY`로 고정하며,
배경 전장의 연속오차를 해결한 full-state balance라고 부르지 않는다.

## 경계식

준비된 동일 06 UTC 모델 cycle의 전시각·현재·후시각 FSF를 사용해 하부
pressure velocity를 계산한다.

\[
\omega_s = \frac{p_s(t+1h)-p_s(t-1h)}{7200s}
          + u_s\frac{\partial p_s}{\partial x}
          + v_s\frac{\partial p_s}{\partial y}.
\]

내부는 centered difference, 외곽은 one-sided difference를 쓴다. 상부는
명시적 zero-flux test boundary다. FSF에는 `USF/VSF`가 grid-relative인지
earth-relative인지 선언돼 있지 않으므로, 이 경계는 수치시험 권한만 가진다.
관측 target을 승인하는 `SOURCE_BOUNDARY_CONDITION`과 구별하기 위해
`SOURCE_MANUFACTURED_TEST`를 함께 기록한다.

## target과 국지화

레이더 column proposal support 중 도메인 중앙에 가장 가까운 column을 골라,
3x3 column에 진폭 0.02 Pa/s인 매끄러운 연직 sine target을 둔다. 수평
localization은 반경 5 grid cell의 compact Wendland C2 함수다.

\[
q_\omega(k)=0.02\sin\left[\pi
\frac{k-k_b+1/2}{N_{active}}\right],
\]

최하·최상부의 약한 강제력이 projection 뒤 부호를 바꾸지 않도록
\(\sin(\cdot)\ge0.25\)인 내부 level만 target 권한을 가진다. 경계에 거의 0인
target은 권한 없는 값으로 두는 명시적 test fixture 정의다. 모든 권한 cell은
적용 후 원래 target의 최소 1%와
같은 부호로 응답해야 하며 한 cell도 실패하면 세대를 게시하지 않는다.

\[
\beta(r)=(1-r)^4(1+4r),\qquad 0\le r<1.
\]

이는 실제 cloud/precipitation에서 관측된 연직속도가 아니다. 실제 radar와
hydrometeor는 seed 위치와 real mass geometry만 제공한다.

## balance 문제

배경장을 재균형하지 않고 target이 만든 증분만 projection한다.

\[
r_q=D_\Delta q_\omega,
\qquad L\lambda=r_q,
\qquad L=-D_\Delta G,
\]

\[
\delta x=q_\omega+G\lambda,
\qquad D_\Delta\delta x\simeq0.
\]

동일한 face coefficient와 `D/G/L` 구현을 solve, correction, 전후 residual에
공용한다. support 밖 increment는 bitwise 0이어야 한다.

## 고정 수치시험 설정

| 항목 | 값 |
|---|---:|
| target amplitude | 0.02 Pa/s |
| `kappa_omega` | 0.1 |
| maximum CG iterations | 1200 |
| solver residual fraction | 0.05 |
| maximum wind increment | 0.50 m/s |
| maximum omega increment | 0.05 Pa/s |
| minimum trust fraction | 0.25 |
| minimum cellwise target response | 0.01 |
| maximum target-response failure fraction | 0.00 |

이 값은 real-geometry solver path를 닫기 위한 수치시험 profile이며 과학적
관측오차나 배경공분산 tuning이 아니다. 별도 preconditioner 없이 반복수가
큰 경우는 운영 준비가 아니라 conditioning blocker로 기록한다.

## 승인 gate

- 네 시각이 모두 같은 clean exact HEAD와 pinned ifx 2026으로 실행돼야 한다.
- 모든 입력은 실행 전후 SHA-256이 같아야 하며 `/ANAL`, `/MODL`,
  `/klaps-v5.0_`에는 쓰지 않는다.
- solver는 수렴하고 acceptance bitset은 0이어야 한다.
- projected increment residual은 proposed residual의 25% 이하여야 한다.
- candidate full-state residual은 background보다 `1e-7` 이상 나빠지면 안 된다.
- 최대 증분, operator identity, trust fraction, target response와 support 밖
  bitwise 불변 조건을 모두 만족해야 한다.
- neighbor jump는 `0.10 m/s`, `0.02 Pa/s` 이하의 공학적 대리 guard를 쓴다.
  이는 모델의 음파·중력파 안전성을 증명하지 않는다.
- 진단 NetCDF, validator JSON, log와 고정-scale PNG를 한 immutable
  transaction으로 게시한다. 같은 그림을 두 번 그려 byte identity를 검사한다.
- 게시 후 semantic verifier가 원본 FSF 세 파일을 다시 읽고 위 경계식을
  Python으로 독립 재계산해 Fortran 진단값과 `2e-6 Pa/s` 이내인지 확인한다.
- 수상체 총질량 변화와 cell별 절대 변화 분위수는 반드시 기록한다. 현재는
  과학적 허용범위가 없으므로 report-only이며, 큰 변화는 승격 차단 증거다.

## 실행과 해석

```bash
tests/run_real_manufactured_balance_cases.sh
```

성공 판정명은 `NUMERICAL_REAL_GEOMETRY_PASS`다. 다음 문구로 바꾸어 읽으면
안 된다.

- 실제 관측 기반 dynamic balance 검증 완료
- cloud/precipitation 연직속도 과학 검증 완료
- cold-start 음파·중력파 안전성 확인
- ACTIVE 또는 운영 승격 가능

그 단계에는 명시적 관측 target, `R_w`, 자료 나이, wind frame, physical
top/bottom boundary, 실제 LOS observation operator, 0--6 h paired forecast가
추가로 필요하다.
