# Cloud-BAL 과학적 기초와 구현 경계

## 결론

구름·강수는 부력과 수상체 loading을 바꾸므로 국지적인 질량-바람 반응이
필요하다. 그러나 cloud type이나 S-band reflectivity는 수평·연직 바람을
유일하게 결정하지 않는다. 따라서 현재 구현은 다음의 작은 문제만 푼다.

```text
직접 관측된 강수 support
  -> interface fall-flux 폐합과 loading pseudo-target 진단
  -> 별도로 승인된 dynamic target만 국지 projection
  -> 물리·수치 gate에서 하나라도 실패하면 후보 거부
```

배경 전장을 다시 균형화할 권한은 없다. 회전 increment를 target으로
지정하지도 않는다. 다만 A-grid projection 뒤 작은 회전 성분이 남을 수
있으므로 현재 회전류 값은 진단일 뿐 승인 근거가 아니다.

## 1. 운형과 연직속도

대류형과 층상형은 서로 다른 통계·연직 구조를 가진다. 대류 영역은 젊고
강한 상승 core와 저층 수렴·상층 발산이 특징인 반면, MCS의 층상 강수
영역을 합성한 개념 모형은 상층의 약한 상승, 하층의 하강과 중층 수렴을
보인다. 이 평균 구조를 한 사례의 결정론적 target으로 사용하지 않는다.
한 개의 대류 cloud-type
level이 연결된 구름층 전체를 같은 sine profile로 바꾸는 것은 이 구조를
표현하지 못한다. [Houze (1997)](https://doi.org/10.1175/1520-0477(1997)078%3C2179:SPIROC%3E2.0.CO;2),
[Houze (1989)](https://doi.org/10.1002/qj.49711548702),
[Houze (2004)](https://doi.org/10.1029/2004RG000150).

모델 격자에서 필요한 값은 cloud-core 속도가 아니라 면적 평균 mass flux다.

\[
M=\rho_d\left(a_u w_u+a_d w_d+a_e w_e\right),
\qquad a_u+a_d+a_e=1.
\]

격자 해상도가 바뀌면 core가 차지하는 면적과 resolved vertical velocity가
바뀌므로 level 수나 `cloud_depth/dx`로 진폭을 보정해도 해상도 독립 관측이
되지 않는다. 깊은 대류의 연직속도 구조가 격자에 강하게 의존한다는 직접
수치 증거는 [Bryan et al. (2003)](https://doi.org/10.1175/1520-0493(2003)131%3C2394:RRFTSO%3E2.0.CO;2)와
[Sueki et al. (2019)](https://doi.org/10.1029/2019GL084491)에 제시돼 있다.

따라서 구현 계약은 다음과 같다.

- Sc/stratus/fog: cloud analysis만 있으면 평균 innovation은 0이다.
- shallow/deep Cu: 비영 target에는 독립적인 convergence, buoyancy, area/mass
  flux 또는 air-motion retrieval과 불확실도 `R_w`가 필요하다.
- cloud type은 layer/regime support와 prior family만 고른다.
- core `w`를 분석 격자 전체에 복사하지 않는다.

현재 준비 입력에는 이 동역학 driver와 검증된 `R_w`가 없으므로
cloud-type-only 경험함수는 제거되어 있다.

## 2. S-band 반사도와 시선속도

강수 입자가 있는 radar radial velocity의 단순 observation operator는

\[
V_r = b_x u+b_y v+b_z\left(w-V_t\right)+\epsilon_r,
\]

이다. 여기서 \(\boldsymbol b\)는 beam 단위벡터이고 \(V_t\)는
reflectivity-weighted terminal fall speed다. 즉 radial velocity에는
hydrometeor 정보가 들어 있지만, 그것은 air motion과 합쳐져 있다. WRF
radar assimilation도 hydrometeor-dependent fall-speed 항을 포함한다.
[Sun and Wang (2013)](https://doi.org/10.1175/MWR-D-12-00168.1).

S-band Doppler만으로 두 항을 분리하려면 추가 air-motion 정보, 다중주파수,
vertical profiler 또는 spectrum/polarimetric constraint가 필요하다.
[Protat and Williams (2011)](https://doi.org/10.1175/JAMC-D-10-05031.1),
[Orr and Kropfli (1999)](https://doi.org/10.1175/1520-0426(1999)016%3C0029:AMFEPF%3E2.0.CO;2).

따라서 S-band echo는 낙하 강수일 가능성을 우선 고려하되, dBZ를 공기
하강속도로 직접 바꾸지 않는다. 현재 실제 `vNN` 자료는 velocity는 있지만
usable Nyquist가 없고 파일 내부 wavelength provenance도 부족하므로,
시선속도는 진단만 하고 update 권한을 갖지 않는다.

실행 설정의 0.10 m는 관측 파일 메타데이터가 아니라 S-band 가정의 범위
guard다. 현재 고정 (Z^{0.55}) 질량식과 loading 효율은 보정되지 않은
SHADOW 진단이며, phase·fall-speed uncertainty가 남은 target에는
`SOURCE_DYNAMIC_TARGET`을 부여하지 않는다.

## 3. 기울어진 강수 구조와 fall-flux 재구성

상대 낙하속도를 \(r=V_t-w\)라 둔다. \(r\le v_{min}\)이면 상승류가
낙하를 지지하는 상태이므로 속도 하한으로 억지 수송하지 않고 해당
interface rate를 `suspended`로 기록한다. \(r>v_{min}\)인 경우에만 한 수직
step을

\[
\Delta t={\Delta z\over r},\qquad
\Delta x=u\Delta t,\qquad
\Delta y=v\Delta t
\]

로 진행하고, 동일한 \(r\)로 interface rate를 계산한다.

\[
F_p=\rho_d q_p r\,\Delta A.
\]

도착 농도도 도착층의 유효한 상대속도로 나누어 계산한다. 현재 real-data
SHADOW v3는 입력 LW3 U/V를 그대로 사용하지만 grid-relative/earth-relative
계보와 시간 인접 radar motion vector가 모두 없다. 따라서
`INPUT_WIND_NATIVE_UNRESOLVED`와 \(c_x=c_y=0\) 가정을 metadata에 기록한다.
좌표계와 storm motion이 검증되면 같은 frame의 \((u-c_x,v-c_y)\)로
바꾸어야 하며, 그 전에는 trajectory를 과학 검증 완료로 승격하지 않는다.
바람 shear, fall speed와 melting이 trajectory와 size sorting을 바꾼다는
근거는 [Lauri et al. (2012)](https://doi.org/10.1175/MWR-D-11-00045.1)와
[Dawson et al. (2015)](https://doi.org/10.1175/JAS-D-14-0084.1)에 있다.

각 interface는 다음 ledger를 닫는다.

\[
F_{in}=F_{deposited}+F_{suspended}+F_{boundary}
      +F_{terrain}+F_{blocked}+F_{microphysical}.
\]

이는 각 수직면을 지나는 flux 연산의 폐합이다. source 농도를 제거하는
finite-time 수송이나 최초 source부터 최종 sink까지의 전역 강수질량 보존을
뜻하지 않는다. 또한 단일 S-band dBZ에서 얻은 loading target은 보정되지
않은 SHADOW pseudo-observation이다. 현재 ACTIVE 바람 권한은 없다.

증발·승화·융해가 활성화될 때에는 반드시 수상체 감소, 수증기 증가와 잠열
온도 변화가 같은 transaction에 있어야 한다. 현재 radar evaporation은 이
폐합이 전체 legacy 경로에 연결될 때까지 OFF다.

## 4. 국지 질량-바람 projection

반사도는 회전류를 직접 관측하지 않으므로 target이 만든 발산 increment만
조정한다. 배경 바람 \(V_b\)의 잔차를 compact subdomain 안에서 다시 푸는
문제와 분리하여

\[
D_\Delta\left(q_\omega+\delta V\right)=0
\]

만 푼다. 하나의 구현에서

\[
A=DS,\qquad G=-K A^T M,\qquad L=-AG
\]

을 만들고 solve, update, 전후 residual이 같은 `S/D/G/L`을 사용한다.
support 밖 increment와 support 경계의 normal increment는 0이다. target 또는
독립적인 dynamic constraint가 없는 connected component는 수정하지 않는다.

현재 A-grid 평균 연산자는 격자 간격의 checkerboard mode를 연속방정식에서
보지 못한다. 실제 SHADOW 자료에는 승인된 dynamic target이 없어 바람
수정이 0이지만, 이 null mode를 제거하기 전에는 `BALANCE_ACTIVE`를 만들지
않는다. 비균일 격자도 누적 face 거리를 도입하기 전에는 ingest에서 거부한다.

승인식은 적어도 다음을 동시에 만족해야 한다.

\[
\|D V_c\|\le
\min\left(\|D V_b\|+\epsilon_b,\ r_{absolute}\right),
\]

\[
\|D_\Delta(q_\omega+\delta V)\|
\le\gamma\|D_\Delta q_\omega\|,
\]

그리고 wind/omega increment와 cellwise target response ratio,
geostrophic diagnostic, support locality가 각각 제한 안에 있어야 한다.
하나를 넘으면 전체 후보를 거부한다.

## 5. 파동과 동역학적 안전성

짧은 시간에 큰 수분·온도·발산 increment를 넣으면 compressible model의
acoustic mode와 inertia-gravity mode를 자극할 수 있다. Digital filtering은
이를 줄일 수 있지만 강한 penalty나 filter는 정당한 대류·발산 에너지도
약화시킬 수 있으므로, 잘못된 초기장을 덮는 수단으로 사용하지 않는다.
[Polavarapu et al. (2000)](https://doi.org/10.1175/1520-0493(2000)128%3C2491:FDVDAW%3E2.0.CO;2),
[Peckham et al. (2016)](https://doi.org/10.1175/MWR-D-15-0219.1),
[Weygandt et al. (2022)](https://doi.org/10.1175/WAF-D-21-0142.1).

따라서 최종 안전성은 분석 시각의 residual만으로 판정하지 않는다. 고정된
여러 실제 사례에서 0--6 h cold start를 수행하고 첫 10/30/60분의 표면기압,
고주파 발산, 강수 spin-up, 온도·수분·엔탈피와 중력파/음파 진폭을 legacy와
비교해야 한다. 그 전에는 `SCIENCE_UNASSESSED / PROMOTION_BLOCKED`다.
