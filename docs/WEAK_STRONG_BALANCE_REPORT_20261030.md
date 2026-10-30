# 약한 강수와 강한 강수의 균형: 초기 눈 증가의 공간 배치 실험



## 초록

2026년 8월 16일 12 UTC의 단일 사례에서 초기 강수 수종 기둥 평균을 기준으로 선택한 고값 영역에 QSNOW를 증가시키고, 초기 건조 공기 질량 가중 QSNOW 총량을 맞춘 균일 증가 대조군과 비교했다. 추가로 실행파일과 초기 입력을 교차한 두 진단 실험을 포함했다. 평가에는 공통 RN1 분석점 3,688개의 시간별 지상 총강수와 여섯 임계값을 사용했다. 낮은 강수 임계값 CSI를 여섯 예측시간 모두에서 기존 ORIGINAL 이상으로 유지하고 +1 h CSI@10 mm를 엄격히 높이는 두 조건을 사전에 고정했다. **적격 후보가 없다.** 낮은 임계값 18개 CSI 조건과 +1 h ≥10 mm CSI 엄격 개선을 함께 통과한 새 설정이 없어 ORIGINAL을 비교 기준으로 둔 채 신규 후보를 선정하지 않는다. 순위 선정을 하지 않았으며 기준을 사후 완화하지 않았다.



## 1. 배경과 연구 질문

기존 39개 설정의 독립 재산출에서는 CONTROL α=3이 +1 h의 여섯 CSI 임계값 모두에서 ORIGINAL보다 높았지만 +2–+3 h의 낮은 임계값 6개 셀 중 일부에서는 CSI가 낮았다. 이 구간에서 낮은 셀은 5/6이다. IMPROVED α=0.8은 +2, +3, +4, +6 h의 낮은 임계값 CSI에서 약화가 나타났고, 그 12개 셀 중 12개가 ORIGINAL보다 낮았다. 반면 같은 사례의 ≥5 mm 강수 CSI는 여섯 lead×두 임계값 12개 조합 중 11개에서 높았다. 같은 고정 관측 사건 수에서 +6 h IMPROVED α=0.8, ≥0.1 mm는 ΔH=-36, ΔFA=-19, ΔH−CSI₀ΔFA=-28.929로 CSI가 낮았다. +6 h ≥10 mm에서는 ΔH=+11, ΔFA=-9, ΔH−CSI₀ΔFA=+12.645로 CSI가 높았고, CONTROL α=3의 +6 h ≥0.1 mm는 ΔH=-6, ΔFA=+56, ΔH−CSI₀ΔFA=-26.842였다. 이 exact-count sign check는 CSI 산술이지 물리 인과 귀속이 아니다. 검증-only 관측 강도별 전이 감사는 +4 h, ≥0.1 mm에서 IMPROVED α=0.8의 순 적중 변화가 light +2, moderate +2, strong -20, very strong -14였음을 보인다. +6 h에는 각각 -12, -31, +2, +5였다. 따라서 낮은 임계값 CSI 하락을 약한 강도만의 적중 손실로 읽어서는 안 된다. 이 보조 감사는 같은 사례의 원자료 구간을 설명하며 적격성 기준을 변경하지 않는다. 이 분리는 강한 강수 개선을 약한 강수 전반의 개선으로 일반화할 수 없음을 보여 주며, 현재 검토의 동기를 제공한다. 전 수치는 [재산출 셀표](evidence/weak_strong_balance_20261030/review/results.csv), 기존 HYDRO 별도 맥락은 [참고 셀표](evidence/weak_strong_balance_20261030/review/current_hydro_context.csv), 검증·입력 해시는 [감사 영수증](evidence/weak_strong_balance_20261030/review/results.json), 재산출 코드는 [audit script](evidence/weak_strong_balance_20261030/review/prior_tradeoff_audit.py), 관측 강도 구간 코드는 [band audit](evidence/weak_strong_balance_20261030/review/prior_observed_band_audit.py)와 [band receipt](evidence/weak_strong_balance_20261030/review/prior_observed_band_receipt.json)을 참조한다.

이 결과는 모든 임계값·시간에서 일관된 개선이 흔하지 않다는 문제를 보여 준다. 이번 실험은 강한 강수 기준에서 유리한 변화가 낮은 강수 임계값 CSI의 시간별 바닥 조건을 만족하는지, 그리고 같은 초기 QSNOW 총량에서 공간 배치만 달라질 때 예보 점수의 차이가 나타나는지 시험한다. 낮은 임계값 CSI에는 큰 강수 사건의 적중도 포함되므로, 이를 관측된 약한 강수 강도만의 검증으로 해석하지 않는다.



## 2. 설계 및 물리적 정의

### 2.1 초기 강수 수종 게이트

WRF 문서는 수직 좌표를 지표 부근에서 지형 추종하고 지정 고도부터 등압면으로 전이되는 hybrid terrain-following mass coordinate로 설명한다 ([WRF Dynamics: Hybrid Vertical Coordinate](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/dynamics.html), 2026-10-30 확인). 아래 층 가중치 $\Delta p_d$는 해당 웹페이지 식을 직접 대입한 값이 아니라 이 저장소의 `tools/check_native_hybrid_geometry.py::read_geometry`가 HYBRID_OPT=2 계수와 closure 검사를 적용해 계산한 값이다.

ORIGINAL 초기장에서 각 수평 기둥의 진단값을 $X=\frac{\sum_k (QRAIN_k+QSNOW_k+QGRAUP_k)\,\Delta p_{d,k}}{\sum_k\Delta p_{d,k}}$로 정의했다. 이는 초기 강수 수종 혼합비의 기둥 평균 proxy이며, 향후 강수량이나 지상 강우 예측량이 아니다. $\Delta p_d$는 HYBRID_OPT=2 계수로 계산한 건조 공기 질량 층 가중치다. 이 계산은 초기 입력장만 사용하며 예보 출력과 관측값은 게이트 설정에 쓰지 않는다.

양의 $X$ 값의 사전 고정 분위수 두 개 사이에서 로그 $X$를 선형 정규화한 $u$를 만들고 $w=u^2(3-2u)$, $\alpha=1+2w$를 적용한다. 세 마스크 G50–90, G75–95, G90–99의 고-$X$ 끝은 각각 90, 95, 99 백분위다. 바깥쪽 저-$X$ 영역은 $\alpha=1$을 유지하고, 같은 2-D $\alpha$를 모든 QSNOW 질량층에 적용했다. 따라서 이 설정은 약한 초기 강수 기둥의 QSNOW를 낮추는 것이 아니라 기존 눈을 보존하고 선택된 기둥에 더한다.

$q_s^{gate}=\mathrm{REAL32}[\alpha(x,y)\,\mathrm{REAL64}(q_s^{orig})]$. 여기서 QSNOW는 초기 대기 중 눈 수상체의 혼합비(kg kg$^{-1}$)이며 지상 적설 깊이나 지상 눈 강수량이 아니다. 각 균일 증량 EQ 케이스는 짝 GATE 케이스와 건조 공기 질량 가중 초기 QSNOW 총량이 $10^{-6}$ 상대오차 이내가 되도록 맞췄다. 두 케이스의 눈 총량은 ORIGINAL보다 크다. 이 일치는 **초기 눈 총량 진단값**에만 해당한다. 수증기·비·싸락눈·온도·에너지 보상을 하지 않으며 입자 수농도·크기분포·엔탈피도 고정하지 않으므로 전체 물·에너지 보존이나 초기화의 완전한 보존성을 뜻하지 않는다.

![초기 X에서 게이트·질량 일치 대조를 거쳐 시간별 CSI를 계산하는 흐름](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Finitial_gate_concept.png&output=png>)

G50–90, G75–95, G90–99는 양의 초기 X 열의 경험적 백분위 구간을 뜻한다(50–90 mm 강수량 구간이 아니다). 게이트 입력은 ORIGINAL 초기 기둥의 강수 수종 혼합비 진단값이다. 이 값은 지상 강수 관측이나 예보 출력이 아니며 그 자체가 지상 강수의 발생·강도를 보장하지 않는다.

![초기 강수 수종 게이트, α, 질량 일치 공간 배치](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Finitial_precip_gate_maps.png&output=png>)

| Positive-X percentile interval | Gate α(x,y) range | Uniform EQ α | Initial mass mismatch |
| --- | --- | --- | --- |
| 50–90% | 1.0–3.0 | 2.681447 | 1.289e-10 |
| 75–95% | 1.0–3.0 | 2.359909 | 7.888e-11 |
| 90–99% | 1.0–3.0 | 1.856840 | 6.645e-11 |

열의 α(x,y)는 공간게이트의 범위다. Uniform EQ α는 각 짝 GATE의 초기 건조 질량 가중 QSNOW 총량을 맞추는 별도의 균일 계수다. GATE의 공간 평균 α를 EQ scalar와 동일시하지 않는다.

각 GATE/EQ 짝은 초기 건조 질량 가중 QSNOW 양을 맞춘다. 점수 차이는 이 한 사례에서 배치가 다른 두 초기장에 대한 예보 반응을 나타낸다. 질량 일치는 초기 수상체 분포와 이후 응결·융해·낙하·수송의 동일성을 보장하지 않는다.

### 2.2 두 요인 실행파일/입력 교차 진단

FIXED_ORIGINAL_100은 수정 실행파일과 ORIGINAL 입력을, ORIGINAL_B1_100은 ORIGINAL 실행파일과 B1 입력을 사용한다. ORIGINAL과 B1 자체를 포함하면 실행파일 상태와 입력 계보의 2×2 대조가 된다. CSI·오차 차이와 차이의 차이는 비선형 검증 점수의 통계적 대조다. 단일 미세물리 과정의 인과 기여량으로 해석하지 않는다.

### 2.3 강수 검증 정의

지상 누적 총강수 $C=RAINC+RAINNC$에서 시간별 한 시간 총강수량 $P_h=C(t_0+h)-C(t_0+h-1)$을 계산했다. 검증량은 눈 강수만이 아니라 강수 전체다. 따라서 +6 h는 17–18 UTC 시간창이며 초기시각부터의 6시간 누적이 아니다. CSI=$H/(H+M+FA)$, FAR=$FA/(H+FA)$다. 낮은 강수 임계값은 0.1, 0.5, 1 mm이고 강한 사건의 사전 지정 지표는 +1 h 10 mm CSI다. 이 임계값은 본 연구 설계값이지 공식 특보 등급이 아니다.

모든 사례는 동일한 처리 RN1 분석의 동일 3,688점과 공통 시간창을 사용했다. 모델−RN1 차이는 예보 오차와 RN1 분석·대표성·품질관리 오차를 함께 포함할 수 있으며 이 자료만으로 두 오차를 분리하지 않는다. 관측 품질과 마스크 coverage의 불확실성이 남아 있으므로 RN1은 독립적인 관측 진실값이나 전국적인 coverage의 보증으로 부르지 않는다.



## 3. 사전 지정 적격성 및 순위

후보별로 여섯 lead × 낮은 임계값 세 개의 모든 18개 셀(0.1, 0.5, 1 mm)에서 CSI ≥ ORIGINAL이어야 한다(허용오차 0). 동시에 +1 h CSI@10 mm > ORIGINAL이어야 한다(엄격 비교, 허용오차 0). 두 조건은 모두 필수다. CSI의 낮은 임계값 사건에는 강한 강수 적중도 포함될 수 있어 약한 강도 전용 점수는 아니다. 적격 후보가 없으면 개선안을 선정하지 않는다. 통과한 경우에만 +1 h CSI@10 내림차순, CSI@5 내림차순, FAR@10 오름차순, RMSE 오름차순, ID 오름차순으로 순위화한다.

| Case | Low-threshold cells passed / 18 | Failed | +1 h CSI@10 | Strong condition | Admitted |
| --- | --- | --- | --- | --- | --- |
| Gate 50–90% | 9 | 9 | 0.1290 | PASS | no |
| Equal mass 50–90% | 13 | 5 | 0.1118 | PASS | no |
| Gate 75–95% | 10 | 8 | 0.1258 | PASS | no |
| Equal mass 75–95% | 12 | 6 | 0.0933 | PASS | no |
| Gate 90–99% | 8 | 10 | 0.0625 | PASS | no |
| Equal mass 90–99% | 11 | 7 | 0.0612 | PASS | no |
| Fixed executable / ORIGINAL input | 5 | 13 | 0.0704 | PASS | no |
| ORIGINAL executable / B1 input | 10 | 8 | 0.0493 | FAIL | no |

**적격 후보가 없다.** 낮은 임계값 18개 CSI 조건과 +1 h ≥10 mm CSI 엄격 개선을 함께 통과한 새 설정이 없어 ORIGINAL을 비교 기준으로 둔 채 신규 후보를 선정하지 않는다. 순위 선정을 하지 않았으며 기준을 사후 완화하지 않았다.

강한 기준만 비교한 진단 상위는 **Gate 50–90%**(+1 h CSI@10 0.1290)다. 낮은 임계값 CSI 바닥 조건 18개 중 9개를 통과하지 못했으므로 적격·선정 후보가 아니며, 이 진단 비교는 적격성 조건을 만족한 후보로 간주되지 않는다.

No candidate met both conditions; the criteria were not relaxed.



## 4. 시간·임계값별 결과

낮은 임계값 바닥과 사전 지정 강한 임계값의 대표 결과를 보인다. 각 lead는 별개의 한 시간 검증이며 threshold·lead 평균은 순위·주장에 사용하지 않았다. 여섯 임계값 전체, 정확한 적중·오경보 분해, paired gate contrasts, 모든 사례의 시간별 지도는 부록 B에 따로 제시한다.

+1 h, ≥10 mm에서 GATE_G50_90 CSI는 0.129032, 짝 EQ_G50_90은 0.111842, ORIGINAL은 0.049296, 기존 CONTROL α=3은 0.127389였다. 공간 게이트가 강한 임계값 CSI에서 균일 질량 대조보다 높았지만, GATE의 낮은 임계값 보호 셀 중 9/18, EQ는 5/18이 기준을 밑돌아 어느 쪽도 적격이 아니었다. 이 결과는 이 사례에서 강한 임계값 한 셀의 배치 효과와 사전 지정한 전체 균형 조건이 다름을 보인다. 다음 표는 +2, +3, +4, +6 h의 2×2 단순 대비를 분리한다(각 셀은 ΔCSI, ΔH, ΔFA). 같은 입력에서 실행파일을 바꾼 변화는 B1 입력과 ORIGINAL 입력에서 크기가 달랐고, 입력 대비도 실행파일에 따라 달랐다. 이는 이 표본의 점수 대비이며 미세물리 원인이나 일반적 실행파일 효과의 인과 추정이 아니다. 후속 단계는 실행파일 차이에 대응하는 초기화·모델 응답을 보존 수지와 함께 진단해야 한다; 현재 점수만으로 특정 융해·증발 과정이나 물리 인과를 지정할 수 없다.

| Lead | Execution change · ORIGINAL input | Execution change · B1 input | Input change · ORIGINAL executable | Input change · fixed executable |
| --- | --- | --- | --- | --- |
| +2 h | -0.01618 (ΔH -21, ΔFA +40) | -0.01178 (ΔH -24, ΔFA +3) | -0.00320 (ΔH +2, ΔFA +26) | +0.00120 (ΔH -1, ΔFA -11) |
| +3 h | -0.00921 (ΔH -17, ΔFA +16) | -0.00081 (ΔH -10, ΔFA -25) | -0.00557 (ΔH -5, ΔFA +26) | +0.00282 (ΔH +2, ΔFA -15) |
| +4 h | -0.01269 (ΔH -31, ΔFA +0) | -0.01226 (ΔH -31, ΔFA -3) | +0.00055 (ΔH +4, ΔFA +8) | +0.00098 (ΔH +4, ΔFA +5) |
| +6 h | -0.01753 (ΔH -46, ΔFA -5) | -0.00908 (ΔH -32, ΔFA -25) | +0.00010 (ΔH +1, ΔFA +2) | +0.00855 (ΔH +15, ΔFA -18) |

![≥0.1 mm CSI difference from ORIGINAL](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_delta_0.1mm.png&output=png>)

![≥10 mm CSI by lead](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_absolute_10mm.png&output=png>)

### 적중·오경보 변화의 CSI 대수 분해

같은 관측 지점 집합에서 각 케이스의 관측 사건 수 $O=H+M$는 ORIGINAL과 같다. 기준 및 후보 CSI 분모를 각각 $D_0=O+F_0$, $D_c=O+F_c$라 놓고 $\Delta H=H_c-H_0$, $\Delta F=F_c-F_0$라 하면 $\Delta CSI=H_c/D_c-H_0/D_0=\Delta H/D_c-H_0\Delta F/(D_0D_c)$. 분모가 양수일 때 부호는 $\Delta H-CSI_0\Delta F$의 부호와 같아 적중 변화와 오경보 변화의 크기를 함께 고려한다. 두 항의 합은 관측된 $\Delta CSI$와 같다. 이는 점수식의 정확한 대수 분해이지 모델 물리 과정의 기여도나 인과효과가 아니다.

각 그림은 임계값별로 모든 12개 문맥과 6개 lead를 표시한다. 세 패널은 적중 변화 항, 오경보 변화 항, 순 ΔCSI이며 세 패널의 색 범위는 해당 그림 안에서 공통이고 0 중심이다. 항을 시간·임계값·사례별로 평균하지 않는다.

### 공간 게이트와 균일 질량 대조

각 칸은 같은 초기 QSNOW 건조 질량 진단 총량을 가진 GATE와 EQ 예보 CSI 차이다. +값은 해당 점수에서 공간 게이트가 높고 −값은 균일 대조가 높음을 나타낸다. 이 비교는 초기량을 맞춘 공간배치 실험의 점수 반응이며, 이후 미세물리 과정의 원인 분석은 아니다.

![GATE−EQ CSI at ≥10 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fgate_minus_equal_mass_csi_10mm.png&output=png>)

### 시간별 강수량 분포

모든 hour별 RN1·case·같은 점 ORIG 대비 강수차 지도는 부록 B에 있다. 차이 지도는 새 값을 공간 보간하지 않으며 전 사례·전 예측시간에 공통 영점 중심 색 범위를 쓴다.



## 5. 해석

각 게이트/EQ 짝은 초기 QSNOW 총량을 제약해 양과 배치의 영향을 구별하도록 설계했다. 점수의 차이가 나타나도 이것은 동일 질량의 두 공간 배치에 따른 **예보 결과 차이**다. 관측점 검증 CSI의 비선형 변화 자체가 눈의 물리과정별 원인을 식별하지 않으며, 개별 융해·증발 과정을 귀속할 진단·플럭스·전체 보존 수지가 없다. 이 사례만으로는 QSNOW 변경 효과와 입자 크기분포·엔탈피 등 다른 미세물리 상태의 변화를 분리할 수 없다.

두 교차 실행 실험도 계산의 검증 결과를 비교하는 실행파일/입력 조합이다. interaction 항은 그 점수 체계에서의 차이의 차이이며, 개별 수정의 보편적 인과효과가 아니다. 여덟 새 예보는 하나의 초기 사례·강수 상황에 대한 진단이다. 독립 사례 예측 성능이나 운영 적합성을 증명하지 않는다.

## 6. 실행파일 교차 해석과 다음 진단 단계

별도의 제한된 KDM6 소스·실행 캡처 검토에서는 HYDRO 선택 셀 P05_00의 첫 내부 호출 입력에서 QRAIN 질량은 0.000284018 kg kg⁻¹였지만 내부 QNRAIN 수 모멘트는 float32 0이었다. 초기 입력의 네 점·네 격자 모서리·39층 표본에서는 양의 QRAIN과 0 QNRAIN이 각 arm에서 확인됐으나 표본 수는 OFF 210/624, HYDRO 210/624, LIQUID 210/624이며 전 영역 빈도나 전체 첫 호출 소비를 뜻하지 않는다. 캡처된 부동소수점 식은 음의 습도 인자와 양의 0을 곱해 음의 0을 만들었다. 소스 순서상 양의 0 피연산자가 $n_{0r}$일 가능성은 있지만, 디버그 심볼이 없어 해당 기계 피연산자와 기호의 대응은 추론이다. BASE–fixed 소스 차이는 zero-rate limiter 조건 한 곳이고, 그 guard는 포화 제한률이 비·수증기와 잠열 온도 항에 미치는 효과를 바꾸지만 누락된 QNRAIN을 생성하지 않는다. 이 독립 소스 조사와 선택 셀 캡처는 위 점수 대비의 원인임을 증명하지 않으며, 강수 skill 향상이나 검증된 수 모멘트 초기화를 주장하지 않는다. 다음 단계는 QRAIN/QNRAIN의 권위 있는 초기화·분석 작성 경로와 의도된 입자 크기분포 또는 관측 제약을 확인하는 것이다. 질량만으로 수 모멘트는 정해지지 않으므로 $n_{r,min}$을 물리적 seed로 간주하지 말고, 후보 정책은 강수·수증기·온도 예산을 함께 검증해야 한다.



## 부록 B. 전체 임계값 그림과 시간별 지도

본 부록은 모든 임계값별 절대 CSI·ORIGINAL 대비 ΔCSI와 정확한 CSI 대수 항을 별도 그림으로 둔다. gate/equal-mass paired CSI도 threshold별로 분리했다. 각 지도는 같은 점 위치의 RN1 분석, case hourly total, case−ORIGINAL ΔP 세 열과 여섯 lead로 구성되며 ΔP는 실제 extrema 전체를 포함하는 공통 zero-centered scale을 사용한다.

![≥0.1 mm CSI by lead](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_absolute_0.1mm.png&output=png>)

![≥0.1 mm CSI difference from ORIGINAL](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_delta_0.1mm.png&output=png>)

![≥0.5 mm CSI by lead](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_absolute_0.5mm.png&output=png>)

![≥0.5 mm CSI difference from ORIGINAL](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_delta_0.5mm.png&output=png>)

![≥1 mm CSI by lead](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_absolute_1mm.png&output=png>)

![≥1 mm CSI difference from ORIGINAL](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_delta_1mm.png&output=png>)

![≥2.5 mm CSI by lead](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_absolute_2.5mm.png&output=png>)

![≥2.5 mm CSI difference from ORIGINAL](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_delta_2.5mm.png&output=png>)

![≥5 mm CSI by lead](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_absolute_5mm.png&output=png>)

![≥5 mm CSI difference from ORIGINAL](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_delta_5mm.png&output=png>)

![≥10 mm CSI by lead](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_absolute_10mm.png&output=png>)

![≥10 mm CSI difference from ORIGINAL](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_delta_10mm.png&output=png>)

![CSI algebra at ≥0.1 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_algebra_decomposition_0.1mm.png&output=png>)

![CSI algebra at ≥0.5 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_algebra_decomposition_0.5mm.png&output=png>)

![CSI algebra at ≥1 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_algebra_decomposition_1mm.png&output=png>)

![CSI algebra at ≥2.5 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_algebra_decomposition_2.5mm.png&output=png>)

![CSI algebra at ≥5 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_algebra_decomposition_5mm.png&output=png>)

![CSI algebra at ≥10 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_algebra_decomposition_10mm.png&output=png>)

![GATE−EQ CSI at ≥0.1 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fgate_minus_equal_mass_csi_0.1mm.png&output=png>)

![GATE−EQ CSI at ≥0.5 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fgate_minus_equal_mass_csi_0.5mm.png&output=png>)

![GATE−EQ CSI at ≥1 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fgate_minus_equal_mass_csi_1mm.png&output=png>)

![GATE−EQ CSI at ≥2.5 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fgate_minus_equal_mass_csi_2.5mm.png&output=png>)

![GATE−EQ CSI at ≥5 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fgate_minus_equal_mass_csi_5mm.png&output=png>)

![GATE−EQ CSI at ≥10 mm](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fgate_minus_equal_mass_csi_10mm.png&output=png>)

![Hourly RN1, forecast, and ORIGINAL difference: ORIGINAL](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_original.png&output=png>)

![Hourly RN1, forecast, and ORIGINAL difference: CONTROL α=3](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_control_snow_300.png&output=png>)

![Hourly RN1, forecast, and ORIGINAL difference: B1 입력 + 수정 실행파일](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_improved_bg_fixed.png&output=png>)

![Hourly RN1, forecast, and ORIGINAL difference: IMPROVED α=0.8](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_improved_snow_080.png&output=png>)

![Hourly RN1, forecast, and ORIGINAL difference: Gate 50–90%](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_gate_g50_90.png&output=png>)

![Hourly RN1, forecast, and ORIGINAL difference: Equal mass 50–90%](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_eq_g50_90.png&output=png>)

![Hourly RN1, forecast, and ORIGINAL difference: Gate 75–95%](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_gate_g75_95.png&output=png>)

![Hourly RN1, forecast, and ORIGINAL difference: Equal mass 75–95%](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_eq_g75_95.png&output=png>)

![Hourly RN1, forecast, and ORIGINAL difference: Gate 90–99%](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_gate_g90_99.png&output=png>)

![Hourly RN1, forecast, and ORIGINAL difference: Equal mass 90–99%](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_eq_g90_99.png&output=png>)

![Hourly RN1, forecast, and ORIGINAL difference: Fixed executable / ORIGINAL input](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_fixed_original_100.png&output=png>)

![Hourly RN1, forecast, and ORIGINAL difference: ORIGINAL executable / B1 input](<https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_original_b1_100.png&output=png>)



## 7. 자료와 재현성

- 동결 실험·선정 계획: [selection_plan.json](evidence/weak_strong_balance_20261030/selection_plan.json), SHA-256 `17e8833f2f28da76e1474f82440a88889bd55ba723ef9cd6618d06a0eb786248`.

- 분석 점수·전이·초기장 대조: [analysis outputs](evidence/weak_strong_balance_20261030/analysis/receipt.json) 및 [전체 점수 부록](WEAK_STRONG_BALANCE_FULL_SCORES_20261030.md).

- 기존 설정의 비교 감사: [원자료 셀표](evidence/weak_strong_balance_20261030/review/results.csv) · [감사 영수증](evidence/weak_strong_balance_20261030/review/results.json) · [관측 강도별 전이표](evidence/weak_strong_balance_20261030/review/prior_observed_band.csv) · [전이표 영수증](evidence/weak_strong_balance_20261030/review/prior_observed_band_receipt.json).

- 실행파일의 rain-number 초기화와 zero-rate limiter를 따로 조사한 읽기 전용 source probe: [분석](evidence/weak_strong_balance_20261030/review/stage3_probe.md) · [machine-readable evidence](evidence/weak_strong_balance_20261030/review/stage3_probe.json) · [독립 검토](evidence/weak_strong_balance_20261030/review/stage3_probe_review.json).

- 실행파일, 초기 입력, 공통 입력, 시간별 산출물은 runtime 계획과 사례별 영수증에 SHA-256으로 결속한다. 모든 예보는 pinned Intel 프로파일에서 실행하고 source tree 밖의 scratch 디렉터리를 사용했다.

- 낮은 임계값 점수 전이와 관측 강수구간별 보조 진단은 [observation_band_transitions.csv](evidence/weak_strong_balance_20261030/analysis/observation_band_transitions.csv) 및 [observed_forecast_bin_counts.csv](evidence/weak_strong_balance_20261030/analysis/observed_forecast_bin_counts.csv)에 있다. 이 구간별 진단은 사전 적격성 조건을 바꾸지 않는다.

- [그림 manifest](evidence/weak_strong_balance_20261030/figures/figure_manifest.json)와 이 빌더의 receipt는 생성 이미지와 보고서 hash를 기록한다.



## 제한 사항

단일 사례의 사후 분석, RN1 처리자료 사용, 공통 점수 마스크의 범위, 초기 QSNOW만 변경하는 진단 개입, 건조 질량 가중 눈 총량만 맞춘 EQ 비교, 전체 물·에너지 수지 미계산, 강수 종별 과정 플럭스 미분리, 실행파일×입력 interaction의 비선형 점수 해석을 포함한다. 점수와 그림은 이 한 사례의 약한/강한 강수 균형을 설명하며 일반 예측 향상을 보증하지 않는다.



## 부록 A. 재현 자료와 hash inventory

분석 영수증은 아래 데이터·모델·도구 입력과 생성 배열/점수의 SHA-256을 결속한다. 경로는 영수증의 원 경로이며 빌드한 호스트의 파일 위치를 나타낸다.

| Bound source | SHA-256 | Bytes |
| --- | --- | --- |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8/original/wrfinput_d01 | 5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/BROADBAND_CLOUD_GODDARD.bin | ad4bb1dd8446a2b00559ac425e21255a01b79a4cac7b5e3e693a3c98c222a1c8 | 172680 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAM_ABS_DATA | 91ee3079e43a6d908256fe3d1bd4bc5f3ac5662d2a8a1ed6ac9685be0555ad87 | 20580056 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAM_AEROPT_DATA | 9782ca59f2ebd12128e23f775e74665d7eb3dc386f53aaa053adfd926a388049 | 18208 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAMtr_volume_mixing_ratio | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAMtr_volume_mixing_ratio.A1B | 898ae2e2dbb8ba61934a2eda3b53727b44a13d7ab5339a9347dabd88e1bf21a1 | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAMtr_volume_mixing_ratio.A2 | f3110d6941e3880bf6a134bf36b7e039289f5653ee61a687a9edf6ce76b851ae | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAMtr_volume_mixing_ratio.RCP4.5 | ddbd4a28582380a396f4bf6f567ea2b1d2b326166bb1328dad8958445acd8ac8 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAMtr_volume_mixing_ratio.RCP6 | 5d3a5bbdaba4e18b9d271956081757a247a86c2674fbc7bac2446005c299ee30 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAMtr_volume_mixing_ratio.RCP8.5 | 82e8c0cd521784707d039030cd611ab473f8359c10ee64a7df8a45ac78331c32 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAMtr_volume_mixing_ratio.SSP119 | 8c99cb5622a087b0f4a7dc8be351e0e67c2b34ac3a4c266efc16ed730968401e | 42781 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAMtr_volume_mixing_ratio.SSP126 | 94070e69a7b96163178c4b1404c8fb6d240dec5294b67d51cea1bdd6fdbba191 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAMtr_volume_mixing_ratio.SSP245 | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAMtr_volume_mixing_ratio.SSP370 | 28d7cab970360f66fe8ea271d97c6a9705fc123c4c3bcb4f9e76ffb043355845 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CAMtr_volume_mixing_ratio.SSP585 | cb014ecc482e9fbd79dc676e5f815b96c7679291de6cdd5a27705e116603e12b | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CCN_ACTIVATE.BIN | f2b8d3916560f9046f89f8ac5f32c5292a1800498fd75301e422f147c82a3dbd | 35288 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CLM_ALB_ICE_DFS_DATA | b8ae396abd12f488f87ce3a516d707c73ec5350a3d241238f0cc064c92d99c28 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CLM_ALB_ICE_DRC_DATA | 067f83f7543e102ca92a36138cd71be795da5872bb83cf8a8eef7bbcbff8f45e | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CLM_ASM_ICE_DFS_DATA | db963d6cadfbec4a5706dbf589c2e95b229091f8d191949d1b46c723e4c3a0ed | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CLM_ASM_ICE_DRC_DATA | 6a1d9e1dd8c046d497216a37ac3d0d7da3faa53b2962b966be61ba38963b86e6 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CLM_DRDSDT0_DATA | e98303374a1f49f1ebe68375455daf61126b79f2a84b156e97738fcef3e44d8e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CLM_EXT_ICE_DFS_DATA | d53a1ac63d1aecaec091f55beea6842e535d47d166651da36ca44ea032644417 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CLM_EXT_ICE_DRC_DATA | e74c212073c04fb60007e47c4ce9b1b4da2e2688ae291e51d179422281a13971 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CLM_KAPPA_DATA | 8b8b1d624b417152ba639d4b3024d7011abf7218baea42ea6026d8aec57ed01e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/CLM_TAU_DATA | cb706cedda2fa8c807d2693eeec5b7da05a0fd5b1cc6fa08c476aef40ada4aa5 | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/ETAMPNEW_DATA | a913785f0bf5f75f8428ede706ce67ae804c3b285b4a34aeb533c4ad5cd9bea2 | 30200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/ETAMPNEW_DATA.expanded_rain | 28e60e6c83eb55889c4ab65eaa33e9fc3b557e5ab45c3dde7ee7153c2ef95a13 | 43400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/ETAMPNEW_DATA.expanded_rain_DBL | 28eae1101b529d36846434d3978c91ebbb7e46bd6adefc8226d3d992422dcbc4 | 86408 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/ETAMPNEW_DATA_DBL | 38e0b62ae898e5e26dc365b873eee23b8278a8b19eae55935767aa6c3d6a6334 | 60296 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/GENPARM.TBL | 9c02832a0e4a2ecaf47fcee485539aad95cd732c379c5c258161a88eb3d25ea2 | 261 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/HLC.TBL | 46b9e9575655ceac80f2ebf23fad59044a46615cffcfeebd69380a6a087df67d | 5513 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/LANDUSE.TBL | 7f661318ff5f06aed6b4b5508e4d077dc794cff03d5fb4447fe59c88d0ed2ece | 40650 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/MPTABLE.TBL | 7fae6a77660c90ad80845565ecfb057093c100de41f35f25a7ffa63f41c19e5d | 56140 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/README.namelist | 7aeb895ff81c7784254df227de404019479155a81075d8e4032451d45a6316e5 | 162590 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/README.physics_files | 60545c9eb7da132810cc20fefc8f71802efbb84179ad97ed097fe0f04e8b514b | 4487 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/README.rasm_diag | 5248bf40f945a6e2a5a416e6a22f2da97717448cc271b7405cf4c3497b34620c | 2646 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/README.tslist | c921f8902e64f3220ab71ea16cf0ca4f1d0cc8c630a7fe967a86131f6b528556 | 7619 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/RRTMG_LW_DATA | bcfdee24b63a4c909522a329b8e16c539f0173c7e5aea2caf933ab4fe28c5c97 | 847552 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/RRTMG_LW_DATA_DBL | c93ec6190e16ecbb5bb4fe31e1b1ea4924c3b88a741779749f6eaec1acf989fc | 1694976 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/RRTMG_SW_DATA | a7d25f5b4d33be8629cbef7ecacc1ff413bf398a021297793e843ba1cc627baf | 680368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/RRTMG_SW_DATA_DBL | 5a6a0e0ba830b41519889f8c4a2be771437db56ea4f7526bc0798332b06234a5 | 1360572 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/RRTM_DATA | 45dc91514cf018e133301a1b667deeb17f5b65c49ccfaa9140761a8028bc8ae0 | 749248 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/RRTM_DATA_DBL | 4be1fa00674f947f306edde20433dc170b90ea1e71c0d25a98bcb6a0676e71ff | 1498368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/SOILPARM.TBL | 65ebc19ff475dd16c0a7482486b9f78dab951ac433af9b6b6688bf1f37e570de | 4399 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/SOILPARM.TBL_Kishne_2017 | 4cfe36cca32b2ea2618eeafc5d79174c75f7849077d5c953481adf82cec483a9 | 4400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/STOCHPERT.TBL | e0e6f147628f91ab3e7f3f4be6fc27296a43e1da8ded404b7fe06501fb42559e | 1105 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/TREECANOPY.TBL | a956353d335e64110f6485a42e14aaf2b4907dcc984aea92f92fa34d08caaf3c | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/TREECANOPY21.TBL | 1c87980ab9f82b5d6a2ebc62a984e88898a57f11e625e38fdc65d414d5b3ed02 | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/URBPARM.TBL | 5811226b3db503ae02d8b35cb5cb10e0e90804e451f0f4a5b76a274ee64773d0 | 12038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/URBPARM_LCZ.TBL | 2d1d4481875fa8d762a9115ac8f59b88d03d9557e02193439e156aed711f867e | 16132 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/URBPARM_UZE.TBL | 19da35cad1a70a0bc19ee3b183f356e2f5043a32039d22d45844ea2db0a715df | 8550 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/VEGPARM.TBL | 0fd2eccdb23b1e36023fc87c1d830e7bfe756f2f3560c84816eddbba721a40ba | 23037 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/aerosol.formatted | 5551eeccf5b4aa80e6ed8ae94e73c4ce8a4306a32aae9b3cc954cfa9c2c2d6aa | 29772567 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/aerosol_lat.formatted | 16121ba61f026c57ba18200988ae786609304f52959d24db86d50d8411473a1a | 736 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/aerosol_lon.formatted | 8201ebcba7199b5b737edf4f9f2a75d36ef4afa27fbdcffa9029dadcf8e61376 | 1152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/aerosol_plev.formatted | 3992b2acecbf604430cdb1975497d617cca3e314ee0ae3624f03e5a7f788fc96 | 192 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/bulkdens.asc_s_0_03_0_9 | a5607b3d0b9eb1fcdba30e50b714e348a81aabb64d963b0a00ff4f7b2a24caa6 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/bulkradii.asc_s_0_03_0_9 | e88c840873cc45f4b21bd7bf1a17a93c8275c5478a6c07e1b7d40f8d59d44d32 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/capacity.asc | 33759dbb0e238b37403ce2ad62759cca57c03538d72d34c2cc04bb7b2547c951 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/co2_trans | bdffafa58f96769b19112ccdce15dd02eb74df9b5c2025061b9fd3cb76651ea8 | 48000 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/coeff_p.asc | 22e2385ba836176919514fed221db94681fdd169182acec14af121426527b2ad | 206228 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/coeff_q.asc | 83ab3d88f266443b1bd3691771c9e99f907db1fbc9729b1c300edc85ad90ee3f | 9398 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/constants.asc | ef4f16ec1397ce9892684d4350f76c62f9673b99ee6520ca6c07b1f8a3b22c0e | 3950 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/create_p3_lookupTable_1.f90-v5.4 | a89e6c8fc4ea8cae609f042cc28d37c7f2b0587357eaf90d52a78006551c0954 | 71456 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/create_p3_lookupTable_2.f90-v5.3 | ffbdbd32f6e3355e5805caa4bbfce8619cb29dd2098604bc56b6fc6de4c49dbe | 45251 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/eclipse_besselian_elements.dat | 2a1367ae68a832c7b2bac26a8d28eeda6dbe860126e50dbb0714eec4c9d6eed7 | 80040 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/grib2map.tbl | 846ff6ffec204e8f15a5ef4540af4a369dec68ef862cb219001ac778a2c0a641 | 30547 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/gribmap.txt | 24425f411fcfb460a47436ea1aeb00f388f450ba3cb1734af89116a02cb8961b | 65700 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/ishmael-gamma-tab.bin | d85e4960053024a73034fb962ff52bd62aeae1b975dd5b4f62244ec82d622daa | 6060012 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/ishmael-qi-qc.bin | b8e4cea138b78668f027934bb8e39c6ea2cb62c1d277c17249c72003c8f4646c | 23346576 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/ishmael-qi-qr.bin | 69dd41d3d285318c95cac0d2dde10f8a3b25f802bf52ac781f29c87adb964cc4 | 46693152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/kernels.asc_s_0_03_0_9 | 170b34c8ba0e50cd433917cfe9a1cc673018113ca7e4b2ae33898e8fa1cabfa6 | 702587 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/kernels_z.asc | ce4e140595ff6db2434ecd5376a16c50ea410d03ddc1700bfa95a3490c15106f | 43016 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/masses.asc | f53d3acdaa0a3e2a265272fa22a2a0bd54292f51815149370bbf315e3fa1bee4 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/namelist.input | eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df | 5065 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/ozone.formatted | 2a13ee25809672e0419e40062c1fc753580adbf604bfc67a9166ef77c815dbc0 | 543744 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/ozone_lat.formatted | 761597f3454b99e3dbf15d2621b1ede88269948e96e47f4695b79fabd3cc6348 | 536 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/ozone_plev.formatted | df26a938273b22d2d04ec52b7297827a316cac0061fab020519241cdc0e61d48 | 708 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/p3_lookupTable_1.dat-v5.4_2momI | be1ab6fb03481e376e47c6c79d808af5d8ab069f2b242931e9c54801bad4ae84 | 1606038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/p3_lookupTable_1.dat-v5.4_3momI | 9a3c57ecc09498802c8d7cb3931dbb0200dcf0f51466b3e288120c080271e6dc | 17886038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/p3_lookupTable_2.dat-v5.3 | c9103041ead719cf9e2e215cf846e0ef81b2004f29386156444a079af6b24d97 | 15250032 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/physical_history.txt | 7118db9077324c840223830670527093ba12bdf4337d63352ac38b670b184a5b | 20 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/termvels.asc | 2b22e4ccf63e21e7dd7b381f46ed0f406b7e313b1e5fb43902423708e25443f3 | 3043 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/tr49t67 | 97501d7f0dc6b93a03803e5c59e57732010dd543686aa55404a1400dc62ae039 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/tr49t85 | b7b6aff5c9dbf05d7a0b8ecf08fd13b2762690aa4d0de77030b81a9167608e89 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/tr67t85 | 92a3320df2b0a9eb6fa6e4d62819969d7f410823fe11f3959090202c2a486388 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wind-turbine-1.tbl | d2f863483ab050673ebe15bd1e8510277e7a641845048b08afd7cdc97be7e069 | 485 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrf.exe | de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168 | 71834200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfbdy_d01 | 74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45 | 51979816 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfinput_d01 | c07d2261be49c29b893947a2c700b147ae7a2bb9fb96561be2f2b39c6b45210e | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfinput_d01 | c07d2261be49c29b893947a2c700b147ae7a2bb9fb96561be2f2b39c6b45210e | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_12:00:00 | 2cff54ff1f307026ecc3cbc59947ae540510001169bf523eae5a7878eed73450 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_12:00:00 | 2cff54ff1f307026ecc3cbc59947ae540510001169bf523eae5a7878eed73450 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_13:00:00 | 818289b240f9b777c7d9388e1b8cfe4fd15bee1b799dd71e373fa05783cb8143 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_13:00:00 | 818289b240f9b777c7d9388e1b8cfe4fd15bee1b799dd71e373fa05783cb8143 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_14:00:00 | 6a42bf9e04e0a30517c8327c0f0a54c0dcb7cd305a83446524c348b3da11106e | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_14:00:00 | 6a42bf9e04e0a30517c8327c0f0a54c0dcb7cd305a83446524c348b3da11106e | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_15:00:00 | 46c3bef4bf8d36bddbcc108bab2cff09f3f48b790b7b875f9fb324a389a27b62 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_15:00:00 | 46c3bef4bf8d36bddbcc108bab2cff09f3f48b790b7b875f9fb324a389a27b62 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_16:00:00 | 0fc2934101c641e2a45be00361114d701f179307c8f648cca1af3a46d6b91b9d | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_16:00:00 | 0fc2934101c641e2a45be00361114d701f179307c8f648cca1af3a46d6b91b9d | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_17:00:00 | 5244fa29609e5a26ff638f8e2c1193d941ad7073af488b3595329cb5c8e51933 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_17:00:00 | 5244fa29609e5a26ff638f8e2c1193d941ad7073af488b3595329cb5c8e51933 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_18:00:00 | 2a28678f993674a72d24a6fdd4e584569830eeb529cfdf0f5d937c89db1ceaf2 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G50_90/wrfout_d01_2026-08-16_18:00:00 | 2a28678f993674a72d24a6fdd4e584569830eeb529cfdf0f5d937c89db1ceaf2 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/BROADBAND_CLOUD_GODDARD.bin | ad4bb1dd8446a2b00559ac425e21255a01b79a4cac7b5e3e693a3c98c222a1c8 | 172680 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAM_ABS_DATA | 91ee3079e43a6d908256fe3d1bd4bc5f3ac5662d2a8a1ed6ac9685be0555ad87 | 20580056 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAM_AEROPT_DATA | 9782ca59f2ebd12128e23f775e74665d7eb3dc386f53aaa053adfd926a388049 | 18208 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAMtr_volume_mixing_ratio | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAMtr_volume_mixing_ratio.A1B | 898ae2e2dbb8ba61934a2eda3b53727b44a13d7ab5339a9347dabd88e1bf21a1 | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAMtr_volume_mixing_ratio.A2 | f3110d6941e3880bf6a134bf36b7e039289f5653ee61a687a9edf6ce76b851ae | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAMtr_volume_mixing_ratio.RCP4.5 | ddbd4a28582380a396f4bf6f567ea2b1d2b326166bb1328dad8958445acd8ac8 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAMtr_volume_mixing_ratio.RCP6 | 5d3a5bbdaba4e18b9d271956081757a247a86c2674fbc7bac2446005c299ee30 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAMtr_volume_mixing_ratio.RCP8.5 | 82e8c0cd521784707d039030cd611ab473f8359c10ee64a7df8a45ac78331c32 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAMtr_volume_mixing_ratio.SSP119 | 8c99cb5622a087b0f4a7dc8be351e0e67c2b34ac3a4c266efc16ed730968401e | 42781 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAMtr_volume_mixing_ratio.SSP126 | 94070e69a7b96163178c4b1404c8fb6d240dec5294b67d51cea1bdd6fdbba191 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAMtr_volume_mixing_ratio.SSP245 | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAMtr_volume_mixing_ratio.SSP370 | 28d7cab970360f66fe8ea271d97c6a9705fc123c4c3bcb4f9e76ffb043355845 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CAMtr_volume_mixing_ratio.SSP585 | cb014ecc482e9fbd79dc676e5f815b96c7679291de6cdd5a27705e116603e12b | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CCN_ACTIVATE.BIN | f2b8d3916560f9046f89f8ac5f32c5292a1800498fd75301e422f147c82a3dbd | 35288 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CLM_ALB_ICE_DFS_DATA | b8ae396abd12f488f87ce3a516d707c73ec5350a3d241238f0cc064c92d99c28 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CLM_ALB_ICE_DRC_DATA | 067f83f7543e102ca92a36138cd71be795da5872bb83cf8a8eef7bbcbff8f45e | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CLM_ASM_ICE_DFS_DATA | db963d6cadfbec4a5706dbf589c2e95b229091f8d191949d1b46c723e4c3a0ed | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CLM_ASM_ICE_DRC_DATA | 6a1d9e1dd8c046d497216a37ac3d0d7da3faa53b2962b966be61ba38963b86e6 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CLM_DRDSDT0_DATA | e98303374a1f49f1ebe68375455daf61126b79f2a84b156e97738fcef3e44d8e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CLM_EXT_ICE_DFS_DATA | d53a1ac63d1aecaec091f55beea6842e535d47d166651da36ca44ea032644417 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CLM_EXT_ICE_DRC_DATA | e74c212073c04fb60007e47c4ce9b1b4da2e2688ae291e51d179422281a13971 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CLM_KAPPA_DATA | 8b8b1d624b417152ba639d4b3024d7011abf7218baea42ea6026d8aec57ed01e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/CLM_TAU_DATA | cb706cedda2fa8c807d2693eeec5b7da05a0fd5b1cc6fa08c476aef40ada4aa5 | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/ETAMPNEW_DATA | a913785f0bf5f75f8428ede706ce67ae804c3b285b4a34aeb533c4ad5cd9bea2 | 30200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/ETAMPNEW_DATA.expanded_rain | 28e60e6c83eb55889c4ab65eaa33e9fc3b557e5ab45c3dde7ee7153c2ef95a13 | 43400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/ETAMPNEW_DATA.expanded_rain_DBL | 28eae1101b529d36846434d3978c91ebbb7e46bd6adefc8226d3d992422dcbc4 | 86408 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/ETAMPNEW_DATA_DBL | 38e0b62ae898e5e26dc365b873eee23b8278a8b19eae55935767aa6c3d6a6334 | 60296 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/GENPARM.TBL | 9c02832a0e4a2ecaf47fcee485539aad95cd732c379c5c258161a88eb3d25ea2 | 261 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/HLC.TBL | 46b9e9575655ceac80f2ebf23fad59044a46615cffcfeebd69380a6a087df67d | 5513 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/LANDUSE.TBL | 7f661318ff5f06aed6b4b5508e4d077dc794cff03d5fb4447fe59c88d0ed2ece | 40650 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/MPTABLE.TBL | 7fae6a77660c90ad80845565ecfb057093c100de41f35f25a7ffa63f41c19e5d | 56140 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/README.namelist | 7aeb895ff81c7784254df227de404019479155a81075d8e4032451d45a6316e5 | 162590 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/README.physics_files | 60545c9eb7da132810cc20fefc8f71802efbb84179ad97ed097fe0f04e8b514b | 4487 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/README.rasm_diag | 5248bf40f945a6e2a5a416e6a22f2da97717448cc271b7405cf4c3497b34620c | 2646 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/README.tslist | c921f8902e64f3220ab71ea16cf0ca4f1d0cc8c630a7fe967a86131f6b528556 | 7619 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/RRTMG_LW_DATA | bcfdee24b63a4c909522a329b8e16c539f0173c7e5aea2caf933ab4fe28c5c97 | 847552 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/RRTMG_LW_DATA_DBL | c93ec6190e16ecbb5bb4fe31e1b1ea4924c3b88a741779749f6eaec1acf989fc | 1694976 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/RRTMG_SW_DATA | a7d25f5b4d33be8629cbef7ecacc1ff413bf398a021297793e843ba1cc627baf | 680368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/RRTMG_SW_DATA_DBL | 5a6a0e0ba830b41519889f8c4a2be771437db56ea4f7526bc0798332b06234a5 | 1360572 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/RRTM_DATA | 45dc91514cf018e133301a1b667deeb17f5b65c49ccfaa9140761a8028bc8ae0 | 749248 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/RRTM_DATA_DBL | 4be1fa00674f947f306edde20433dc170b90ea1e71c0d25a98bcb6a0676e71ff | 1498368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/SOILPARM.TBL | 65ebc19ff475dd16c0a7482486b9f78dab951ac433af9b6b6688bf1f37e570de | 4399 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/SOILPARM.TBL_Kishne_2017 | 4cfe36cca32b2ea2618eeafc5d79174c75f7849077d5c953481adf82cec483a9 | 4400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/STOCHPERT.TBL | e0e6f147628f91ab3e7f3f4be6fc27296a43e1da8ded404b7fe06501fb42559e | 1105 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/TREECANOPY.TBL | a956353d335e64110f6485a42e14aaf2b4907dcc984aea92f92fa34d08caaf3c | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/TREECANOPY21.TBL | 1c87980ab9f82b5d6a2ebc62a984e88898a57f11e625e38fdc65d414d5b3ed02 | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/URBPARM.TBL | 5811226b3db503ae02d8b35cb5cb10e0e90804e451f0f4a5b76a274ee64773d0 | 12038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/URBPARM_LCZ.TBL | 2d1d4481875fa8d762a9115ac8f59b88d03d9557e02193439e156aed711f867e | 16132 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/URBPARM_UZE.TBL | 19da35cad1a70a0bc19ee3b183f356e2f5043a32039d22d45844ea2db0a715df | 8550 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/VEGPARM.TBL | 0fd2eccdb23b1e36023fc87c1d830e7bfe756f2f3560c84816eddbba721a40ba | 23037 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/aerosol.formatted | 5551eeccf5b4aa80e6ed8ae94e73c4ce8a4306a32aae9b3cc954cfa9c2c2d6aa | 29772567 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/aerosol_lat.formatted | 16121ba61f026c57ba18200988ae786609304f52959d24db86d50d8411473a1a | 736 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/aerosol_lon.formatted | 8201ebcba7199b5b737edf4f9f2a75d36ef4afa27fbdcffa9029dadcf8e61376 | 1152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/aerosol_plev.formatted | 3992b2acecbf604430cdb1975497d617cca3e314ee0ae3624f03e5a7f788fc96 | 192 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/bulkdens.asc_s_0_03_0_9 | a5607b3d0b9eb1fcdba30e50b714e348a81aabb64d963b0a00ff4f7b2a24caa6 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/bulkradii.asc_s_0_03_0_9 | e88c840873cc45f4b21bd7bf1a17a93c8275c5478a6c07e1b7d40f8d59d44d32 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/capacity.asc | 33759dbb0e238b37403ce2ad62759cca57c03538d72d34c2cc04bb7b2547c951 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/co2_trans | bdffafa58f96769b19112ccdce15dd02eb74df9b5c2025061b9fd3cb76651ea8 | 48000 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/coeff_p.asc | 22e2385ba836176919514fed221db94681fdd169182acec14af121426527b2ad | 206228 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/coeff_q.asc | 83ab3d88f266443b1bd3691771c9e99f907db1fbc9729b1c300edc85ad90ee3f | 9398 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/constants.asc | ef4f16ec1397ce9892684d4350f76c62f9673b99ee6520ca6c07b1f8a3b22c0e | 3950 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/create_p3_lookupTable_1.f90-v5.4 | a89e6c8fc4ea8cae609f042cc28d37c7f2b0587357eaf90d52a78006551c0954 | 71456 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/create_p3_lookupTable_2.f90-v5.3 | ffbdbd32f6e3355e5805caa4bbfce8619cb29dd2098604bc56b6fc6de4c49dbe | 45251 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/eclipse_besselian_elements.dat | 2a1367ae68a832c7b2bac26a8d28eeda6dbe860126e50dbb0714eec4c9d6eed7 | 80040 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/grib2map.tbl | 846ff6ffec204e8f15a5ef4540af4a369dec68ef862cb219001ac778a2c0a641 | 30547 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/gribmap.txt | 24425f411fcfb460a47436ea1aeb00f388f450ba3cb1734af89116a02cb8961b | 65700 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/ishmael-gamma-tab.bin | d85e4960053024a73034fb962ff52bd62aeae1b975dd5b4f62244ec82d622daa | 6060012 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/ishmael-qi-qc.bin | b8e4cea138b78668f027934bb8e39c6ea2cb62c1d277c17249c72003c8f4646c | 23346576 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/ishmael-qi-qr.bin | 69dd41d3d285318c95cac0d2dde10f8a3b25f802bf52ac781f29c87adb964cc4 | 46693152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/kernels.asc_s_0_03_0_9 | 170b34c8ba0e50cd433917cfe9a1cc673018113ca7e4b2ae33898e8fa1cabfa6 | 702587 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/kernels_z.asc | ce4e140595ff6db2434ecd5376a16c50ea410d03ddc1700bfa95a3490c15106f | 43016 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/masses.asc | f53d3acdaa0a3e2a265272fa22a2a0bd54292f51815149370bbf315e3fa1bee4 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/namelist.input | eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df | 5065 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/ozone.formatted | 2a13ee25809672e0419e40062c1fc753580adbf604bfc67a9166ef77c815dbc0 | 543744 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/ozone_lat.formatted | 761597f3454b99e3dbf15d2621b1ede88269948e96e47f4695b79fabd3cc6348 | 536 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/ozone_plev.formatted | df26a938273b22d2d04ec52b7297827a316cac0061fab020519241cdc0e61d48 | 708 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/p3_lookupTable_1.dat-v5.4_2momI | be1ab6fb03481e376e47c6c79d808af5d8ab069f2b242931e9c54801bad4ae84 | 1606038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/p3_lookupTable_1.dat-v5.4_3momI | 9a3c57ecc09498802c8d7cb3931dbb0200dcf0f51466b3e288120c080271e6dc | 17886038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/p3_lookupTable_2.dat-v5.3 | c9103041ead719cf9e2e215cf846e0ef81b2004f29386156444a079af6b24d97 | 15250032 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/physical_history.txt | 7118db9077324c840223830670527093ba12bdf4337d63352ac38b670b184a5b | 20 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/termvels.asc | 2b22e4ccf63e21e7dd7b381f46ed0f406b7e313b1e5fb43902423708e25443f3 | 3043 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/tr49t67 | 97501d7f0dc6b93a03803e5c59e57732010dd543686aa55404a1400dc62ae039 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/tr49t85 | b7b6aff5c9dbf05d7a0b8ecf08fd13b2762690aa4d0de77030b81a9167608e89 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/tr67t85 | 92a3320df2b0a9eb6fa6e4d62819969d7f410823fe11f3959090202c2a486388 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wind-turbine-1.tbl | d2f863483ab050673ebe15bd1e8510277e7a641845048b08afd7cdc97be7e069 | 485 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrf.exe | de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168 | 71834200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfbdy_d01 | 74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45 | 51979816 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfinput_d01 | adaa1d21af3de7e394d4c464c3e3bbca30a40669ec8a817e517f88a6f29298c3 | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfinput_d01 | adaa1d21af3de7e394d4c464c3e3bbca30a40669ec8a817e517f88a6f29298c3 | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_12:00:00 | 4052a2c14b4710a92cbdc350dfef36f43c73f5466c6d03fc4ef4ade672b1a62b | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_12:00:00 | 4052a2c14b4710a92cbdc350dfef36f43c73f5466c6d03fc4ef4ade672b1a62b | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_13:00:00 | 4e5ef498cd2d77051534110970626cb56dc4da528839acd3fc727ea47c98e70b | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_13:00:00 | 4e5ef498cd2d77051534110970626cb56dc4da528839acd3fc727ea47c98e70b | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_14:00:00 | 09fb25d8eb4465d353f84ede6eb8e4a66d62ec9145656731fc6ded60a8f4ad58 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_14:00:00 | 09fb25d8eb4465d353f84ede6eb8e4a66d62ec9145656731fc6ded60a8f4ad58 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_15:00:00 | e8250b50e39ac59874aa932d89e23fbf38064cfbb0281aabf363e8b26b12efcb | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_15:00:00 | e8250b50e39ac59874aa932d89e23fbf38064cfbb0281aabf363e8b26b12efcb | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_16:00:00 | c43553216ce1ad053f597599e93bd40102afc6756eb5d85136f5b78657165136 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_16:00:00 | c43553216ce1ad053f597599e93bd40102afc6756eb5d85136f5b78657165136 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_17:00:00 | 6ca9b8f01f0e55adf82dc7a4017db7ec4f4e83440b82376db9a6c97a3f07b30c | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_17:00:00 | 6ca9b8f01f0e55adf82dc7a4017db7ec4f4e83440b82376db9a6c97a3f07b30c | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_18:00:00 | 97ce6efa51b693f2747be9d3886b8235e820a0347e8a9d66dc56d681e684b754 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G75_95/wrfout_d01_2026-08-16_18:00:00 | 97ce6efa51b693f2747be9d3886b8235e820a0347e8a9d66dc56d681e684b754 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/BROADBAND_CLOUD_GODDARD.bin | ad4bb1dd8446a2b00559ac425e21255a01b79a4cac7b5e3e693a3c98c222a1c8 | 172680 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAM_ABS_DATA | 91ee3079e43a6d908256fe3d1bd4bc5f3ac5662d2a8a1ed6ac9685be0555ad87 | 20580056 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAM_AEROPT_DATA | 9782ca59f2ebd12128e23f775e74665d7eb3dc386f53aaa053adfd926a388049 | 18208 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAMtr_volume_mixing_ratio | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAMtr_volume_mixing_ratio.A1B | 898ae2e2dbb8ba61934a2eda3b53727b44a13d7ab5339a9347dabd88e1bf21a1 | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAMtr_volume_mixing_ratio.A2 | f3110d6941e3880bf6a134bf36b7e039289f5653ee61a687a9edf6ce76b851ae | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAMtr_volume_mixing_ratio.RCP4.5 | ddbd4a28582380a396f4bf6f567ea2b1d2b326166bb1328dad8958445acd8ac8 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAMtr_volume_mixing_ratio.RCP6 | 5d3a5bbdaba4e18b9d271956081757a247a86c2674fbc7bac2446005c299ee30 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAMtr_volume_mixing_ratio.RCP8.5 | 82e8c0cd521784707d039030cd611ab473f8359c10ee64a7df8a45ac78331c32 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAMtr_volume_mixing_ratio.SSP119 | 8c99cb5622a087b0f4a7dc8be351e0e67c2b34ac3a4c266efc16ed730968401e | 42781 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAMtr_volume_mixing_ratio.SSP126 | 94070e69a7b96163178c4b1404c8fb6d240dec5294b67d51cea1bdd6fdbba191 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAMtr_volume_mixing_ratio.SSP245 | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAMtr_volume_mixing_ratio.SSP370 | 28d7cab970360f66fe8ea271d97c6a9705fc123c4c3bcb4f9e76ffb043355845 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CAMtr_volume_mixing_ratio.SSP585 | cb014ecc482e9fbd79dc676e5f815b96c7679291de6cdd5a27705e116603e12b | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CCN_ACTIVATE.BIN | f2b8d3916560f9046f89f8ac5f32c5292a1800498fd75301e422f147c82a3dbd | 35288 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CLM_ALB_ICE_DFS_DATA | b8ae396abd12f488f87ce3a516d707c73ec5350a3d241238f0cc064c92d99c28 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CLM_ALB_ICE_DRC_DATA | 067f83f7543e102ca92a36138cd71be795da5872bb83cf8a8eef7bbcbff8f45e | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CLM_ASM_ICE_DFS_DATA | db963d6cadfbec4a5706dbf589c2e95b229091f8d191949d1b46c723e4c3a0ed | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CLM_ASM_ICE_DRC_DATA | 6a1d9e1dd8c046d497216a37ac3d0d7da3faa53b2962b966be61ba38963b86e6 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CLM_DRDSDT0_DATA | e98303374a1f49f1ebe68375455daf61126b79f2a84b156e97738fcef3e44d8e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CLM_EXT_ICE_DFS_DATA | d53a1ac63d1aecaec091f55beea6842e535d47d166651da36ca44ea032644417 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CLM_EXT_ICE_DRC_DATA | e74c212073c04fb60007e47c4ce9b1b4da2e2688ae291e51d179422281a13971 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CLM_KAPPA_DATA | 8b8b1d624b417152ba639d4b3024d7011abf7218baea42ea6026d8aec57ed01e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/CLM_TAU_DATA | cb706cedda2fa8c807d2693eeec5b7da05a0fd5b1cc6fa08c476aef40ada4aa5 | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/ETAMPNEW_DATA | a913785f0bf5f75f8428ede706ce67ae804c3b285b4a34aeb533c4ad5cd9bea2 | 30200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/ETAMPNEW_DATA.expanded_rain | 28e60e6c83eb55889c4ab65eaa33e9fc3b557e5ab45c3dde7ee7153c2ef95a13 | 43400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/ETAMPNEW_DATA.expanded_rain_DBL | 28eae1101b529d36846434d3978c91ebbb7e46bd6adefc8226d3d992422dcbc4 | 86408 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/ETAMPNEW_DATA_DBL | 38e0b62ae898e5e26dc365b873eee23b8278a8b19eae55935767aa6c3d6a6334 | 60296 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/GENPARM.TBL | 9c02832a0e4a2ecaf47fcee485539aad95cd732c379c5c258161a88eb3d25ea2 | 261 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/HLC.TBL | 46b9e9575655ceac80f2ebf23fad59044a46615cffcfeebd69380a6a087df67d | 5513 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/LANDUSE.TBL | 7f661318ff5f06aed6b4b5508e4d077dc794cff03d5fb4447fe59c88d0ed2ece | 40650 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/MPTABLE.TBL | 7fae6a77660c90ad80845565ecfb057093c100de41f35f25a7ffa63f41c19e5d | 56140 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/README.namelist | 7aeb895ff81c7784254df227de404019479155a81075d8e4032451d45a6316e5 | 162590 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/README.physics_files | 60545c9eb7da132810cc20fefc8f71802efbb84179ad97ed097fe0f04e8b514b | 4487 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/README.rasm_diag | 5248bf40f945a6e2a5a416e6a22f2da97717448cc271b7405cf4c3497b34620c | 2646 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/README.tslist | c921f8902e64f3220ab71ea16cf0ca4f1d0cc8c630a7fe967a86131f6b528556 | 7619 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/RRTMG_LW_DATA | bcfdee24b63a4c909522a329b8e16c539f0173c7e5aea2caf933ab4fe28c5c97 | 847552 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/RRTMG_LW_DATA_DBL | c93ec6190e16ecbb5bb4fe31e1b1ea4924c3b88a741779749f6eaec1acf989fc | 1694976 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/RRTMG_SW_DATA | a7d25f5b4d33be8629cbef7ecacc1ff413bf398a021297793e843ba1cc627baf | 680368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/RRTMG_SW_DATA_DBL | 5a6a0e0ba830b41519889f8c4a2be771437db56ea4f7526bc0798332b06234a5 | 1360572 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/RRTM_DATA | 45dc91514cf018e133301a1b667deeb17f5b65c49ccfaa9140761a8028bc8ae0 | 749248 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/RRTM_DATA_DBL | 4be1fa00674f947f306edde20433dc170b90ea1e71c0d25a98bcb6a0676e71ff | 1498368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/SOILPARM.TBL | 65ebc19ff475dd16c0a7482486b9f78dab951ac433af9b6b6688bf1f37e570de | 4399 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/SOILPARM.TBL_Kishne_2017 | 4cfe36cca32b2ea2618eeafc5d79174c75f7849077d5c953481adf82cec483a9 | 4400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/STOCHPERT.TBL | e0e6f147628f91ab3e7f3f4be6fc27296a43e1da8ded404b7fe06501fb42559e | 1105 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/TREECANOPY.TBL | a956353d335e64110f6485a42e14aaf2b4907dcc984aea92f92fa34d08caaf3c | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/TREECANOPY21.TBL | 1c87980ab9f82b5d6a2ebc62a984e88898a57f11e625e38fdc65d414d5b3ed02 | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/URBPARM.TBL | 5811226b3db503ae02d8b35cb5cb10e0e90804e451f0f4a5b76a274ee64773d0 | 12038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/URBPARM_LCZ.TBL | 2d1d4481875fa8d762a9115ac8f59b88d03d9557e02193439e156aed711f867e | 16132 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/URBPARM_UZE.TBL | 19da35cad1a70a0bc19ee3b183f356e2f5043a32039d22d45844ea2db0a715df | 8550 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/VEGPARM.TBL | 0fd2eccdb23b1e36023fc87c1d830e7bfe756f2f3560c84816eddbba721a40ba | 23037 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/aerosol.formatted | 5551eeccf5b4aa80e6ed8ae94e73c4ce8a4306a32aae9b3cc954cfa9c2c2d6aa | 29772567 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/aerosol_lat.formatted | 16121ba61f026c57ba18200988ae786609304f52959d24db86d50d8411473a1a | 736 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/aerosol_lon.formatted | 8201ebcba7199b5b737edf4f9f2a75d36ef4afa27fbdcffa9029dadcf8e61376 | 1152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/aerosol_plev.formatted | 3992b2acecbf604430cdb1975497d617cca3e314ee0ae3624f03e5a7f788fc96 | 192 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/bulkdens.asc_s_0_03_0_9 | a5607b3d0b9eb1fcdba30e50b714e348a81aabb64d963b0a00ff4f7b2a24caa6 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/bulkradii.asc_s_0_03_0_9 | e88c840873cc45f4b21bd7bf1a17a93c8275c5478a6c07e1b7d40f8d59d44d32 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/capacity.asc | 33759dbb0e238b37403ce2ad62759cca57c03538d72d34c2cc04bb7b2547c951 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/co2_trans | bdffafa58f96769b19112ccdce15dd02eb74df9b5c2025061b9fd3cb76651ea8 | 48000 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/coeff_p.asc | 22e2385ba836176919514fed221db94681fdd169182acec14af121426527b2ad | 206228 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/coeff_q.asc | 83ab3d88f266443b1bd3691771c9e99f907db1fbc9729b1c300edc85ad90ee3f | 9398 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/constants.asc | ef4f16ec1397ce9892684d4350f76c62f9673b99ee6520ca6c07b1f8a3b22c0e | 3950 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/create_p3_lookupTable_1.f90-v5.4 | a89e6c8fc4ea8cae609f042cc28d37c7f2b0587357eaf90d52a78006551c0954 | 71456 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/create_p3_lookupTable_2.f90-v5.3 | ffbdbd32f6e3355e5805caa4bbfce8619cb29dd2098604bc56b6fc6de4c49dbe | 45251 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/eclipse_besselian_elements.dat | 2a1367ae68a832c7b2bac26a8d28eeda6dbe860126e50dbb0714eec4c9d6eed7 | 80040 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/grib2map.tbl | 846ff6ffec204e8f15a5ef4540af4a369dec68ef862cb219001ac778a2c0a641 | 30547 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/gribmap.txt | 24425f411fcfb460a47436ea1aeb00f388f450ba3cb1734af89116a02cb8961b | 65700 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/ishmael-gamma-tab.bin | d85e4960053024a73034fb962ff52bd62aeae1b975dd5b4f62244ec82d622daa | 6060012 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/ishmael-qi-qc.bin | b8e4cea138b78668f027934bb8e39c6ea2cb62c1d277c17249c72003c8f4646c | 23346576 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/ishmael-qi-qr.bin | 69dd41d3d285318c95cac0d2dde10f8a3b25f802bf52ac781f29c87adb964cc4 | 46693152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/kernels.asc_s_0_03_0_9 | 170b34c8ba0e50cd433917cfe9a1cc673018113ca7e4b2ae33898e8fa1cabfa6 | 702587 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/kernels_z.asc | ce4e140595ff6db2434ecd5376a16c50ea410d03ddc1700bfa95a3490c15106f | 43016 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/masses.asc | f53d3acdaa0a3e2a265272fa22a2a0bd54292f51815149370bbf315e3fa1bee4 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/namelist.input | eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df | 5065 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/ozone.formatted | 2a13ee25809672e0419e40062c1fc753580adbf604bfc67a9166ef77c815dbc0 | 543744 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/ozone_lat.formatted | 761597f3454b99e3dbf15d2621b1ede88269948e96e47f4695b79fabd3cc6348 | 536 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/ozone_plev.formatted | df26a938273b22d2d04ec52b7297827a316cac0061fab020519241cdc0e61d48 | 708 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/p3_lookupTable_1.dat-v5.4_2momI | be1ab6fb03481e376e47c6c79d808af5d8ab069f2b242931e9c54801bad4ae84 | 1606038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/p3_lookupTable_1.dat-v5.4_3momI | 9a3c57ecc09498802c8d7cb3931dbb0200dcf0f51466b3e288120c080271e6dc | 17886038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/p3_lookupTable_2.dat-v5.3 | c9103041ead719cf9e2e215cf846e0ef81b2004f29386156444a079af6b24d97 | 15250032 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/physical_history.txt | 7118db9077324c840223830670527093ba12bdf4337d63352ac38b670b184a5b | 20 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/termvels.asc | 2b22e4ccf63e21e7dd7b381f46ed0f406b7e313b1e5fb43902423708e25443f3 | 3043 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/tr49t67 | 97501d7f0dc6b93a03803e5c59e57732010dd543686aa55404a1400dc62ae039 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/tr49t85 | b7b6aff5c9dbf05d7a0b8ecf08fd13b2762690aa4d0de77030b81a9167608e89 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/tr67t85 | 92a3320df2b0a9eb6fa6e4d62819969d7f410823fe11f3959090202c2a486388 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wind-turbine-1.tbl | d2f863483ab050673ebe15bd1e8510277e7a641845048b08afd7cdc97be7e069 | 485 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrf.exe | de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168 | 71834200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfbdy_d01 | 74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45 | 51979816 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfinput_d01 | c9f36cab6a5401b6576b45ffb03ce7561a4b9f87d049ed9b01d33c1da666064a | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfinput_d01 | c9f36cab6a5401b6576b45ffb03ce7561a4b9f87d049ed9b01d33c1da666064a | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_12:00:00 | c3289cdd050378aa0bae9217f9bd05343404cb65bab14310cd6fd0b6477e3b15 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_12:00:00 | c3289cdd050378aa0bae9217f9bd05343404cb65bab14310cd6fd0b6477e3b15 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_13:00:00 | 0f55f123e49c1dea0df483e8152b50def13a6e156feff66109fa03c69ed846d8 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_13:00:00 | 0f55f123e49c1dea0df483e8152b50def13a6e156feff66109fa03c69ed846d8 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_14:00:00 | 190a57e0327755b67ea939ca9975569e2d4a30259b1a194b59ef202883beed23 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_14:00:00 | 190a57e0327755b67ea939ca9975569e2d4a30259b1a194b59ef202883beed23 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_15:00:00 | 2adf915814be029472492e40db10c3170861710dfd50d8474f5044a153c6ec59 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_15:00:00 | 2adf915814be029472492e40db10c3170861710dfd50d8474f5044a153c6ec59 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_16:00:00 | 4c6dccee885e95c15e2efb76efac26d026f46362e49936787d8d310e349611dc | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_16:00:00 | 4c6dccee885e95c15e2efb76efac26d026f46362e49936787d8d310e349611dc | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_17:00:00 | 345233afc91b1932a894a44d447a2b2b8b7e69ef10a1b9f97f50d51efe609012 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_17:00:00 | 345233afc91b1932a894a44d447a2b2b8b7e69ef10a1b9f97f50d51efe609012 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_18:00:00 | 014c6046c218829222fb8b249cdf6f7ae4300fe69570579d790546ea81201f24 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/EQ_G90_99/wrfout_d01_2026-08-16_18:00:00 | 014c6046c218829222fb8b249cdf6f7ae4300fe69570579d790546ea81201f24 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/BROADBAND_CLOUD_GODDARD.bin | ad4bb1dd8446a2b00559ac425e21255a01b79a4cac7b5e3e693a3c98c222a1c8 | 172680 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAM_ABS_DATA | 91ee3079e43a6d908256fe3d1bd4bc5f3ac5662d2a8a1ed6ac9685be0555ad87 | 20580056 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAM_AEROPT_DATA | 9782ca59f2ebd12128e23f775e74665d7eb3dc386f53aaa053adfd926a388049 | 18208 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAMtr_volume_mixing_ratio | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAMtr_volume_mixing_ratio.A1B | 898ae2e2dbb8ba61934a2eda3b53727b44a13d7ab5339a9347dabd88e1bf21a1 | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAMtr_volume_mixing_ratio.A2 | f3110d6941e3880bf6a134bf36b7e039289f5653ee61a687a9edf6ce76b851ae | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAMtr_volume_mixing_ratio.RCP4.5 | ddbd4a28582380a396f4bf6f567ea2b1d2b326166bb1328dad8958445acd8ac8 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAMtr_volume_mixing_ratio.RCP6 | 5d3a5bbdaba4e18b9d271956081757a247a86c2674fbc7bac2446005c299ee30 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAMtr_volume_mixing_ratio.RCP8.5 | 82e8c0cd521784707d039030cd611ab473f8359c10ee64a7df8a45ac78331c32 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAMtr_volume_mixing_ratio.SSP119 | 8c99cb5622a087b0f4a7dc8be351e0e67c2b34ac3a4c266efc16ed730968401e | 42781 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAMtr_volume_mixing_ratio.SSP126 | 94070e69a7b96163178c4b1404c8fb6d240dec5294b67d51cea1bdd6fdbba191 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAMtr_volume_mixing_ratio.SSP245 | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAMtr_volume_mixing_ratio.SSP370 | 28d7cab970360f66fe8ea271d97c6a9705fc123c4c3bcb4f9e76ffb043355845 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CAMtr_volume_mixing_ratio.SSP585 | cb014ecc482e9fbd79dc676e5f815b96c7679291de6cdd5a27705e116603e12b | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CCN_ACTIVATE.BIN | f2b8d3916560f9046f89f8ac5f32c5292a1800498fd75301e422f147c82a3dbd | 35288 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CLM_ALB_ICE_DFS_DATA | b8ae396abd12f488f87ce3a516d707c73ec5350a3d241238f0cc064c92d99c28 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CLM_ALB_ICE_DRC_DATA | 067f83f7543e102ca92a36138cd71be795da5872bb83cf8a8eef7bbcbff8f45e | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CLM_ASM_ICE_DFS_DATA | db963d6cadfbec4a5706dbf589c2e95b229091f8d191949d1b46c723e4c3a0ed | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CLM_ASM_ICE_DRC_DATA | 6a1d9e1dd8c046d497216a37ac3d0d7da3faa53b2962b966be61ba38963b86e6 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CLM_DRDSDT0_DATA | e98303374a1f49f1ebe68375455daf61126b79f2a84b156e97738fcef3e44d8e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CLM_EXT_ICE_DFS_DATA | d53a1ac63d1aecaec091f55beea6842e535d47d166651da36ca44ea032644417 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CLM_EXT_ICE_DRC_DATA | e74c212073c04fb60007e47c4ce9b1b4da2e2688ae291e51d179422281a13971 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CLM_KAPPA_DATA | 8b8b1d624b417152ba639d4b3024d7011abf7218baea42ea6026d8aec57ed01e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/CLM_TAU_DATA | cb706cedda2fa8c807d2693eeec5b7da05a0fd5b1cc6fa08c476aef40ada4aa5 | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/ETAMPNEW_DATA | a913785f0bf5f75f8428ede706ce67ae804c3b285b4a34aeb533c4ad5cd9bea2 | 30200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/ETAMPNEW_DATA.expanded_rain | 28e60e6c83eb55889c4ab65eaa33e9fc3b557e5ab45c3dde7ee7153c2ef95a13 | 43400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/ETAMPNEW_DATA.expanded_rain_DBL | 28eae1101b529d36846434d3978c91ebbb7e46bd6adefc8226d3d992422dcbc4 | 86408 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/ETAMPNEW_DATA_DBL | 38e0b62ae898e5e26dc365b873eee23b8278a8b19eae55935767aa6c3d6a6334 | 60296 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/GENPARM.TBL | 9c02832a0e4a2ecaf47fcee485539aad95cd732c379c5c258161a88eb3d25ea2 | 261 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/HLC.TBL | 46b9e9575655ceac80f2ebf23fad59044a46615cffcfeebd69380a6a087df67d | 5513 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/LANDUSE.TBL | 7f661318ff5f06aed6b4b5508e4d077dc794cff03d5fb4447fe59c88d0ed2ece | 40650 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/MPTABLE.TBL | 7fae6a77660c90ad80845565ecfb057093c100de41f35f25a7ffa63f41c19e5d | 56140 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/README.namelist | 7aeb895ff81c7784254df227de404019479155a81075d8e4032451d45a6316e5 | 162590 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/README.physics_files | 60545c9eb7da132810cc20fefc8f71802efbb84179ad97ed097fe0f04e8b514b | 4487 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/README.rasm_diag | 5248bf40f945a6e2a5a416e6a22f2da97717448cc271b7405cf4c3497b34620c | 2646 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/README.tslist | c921f8902e64f3220ab71ea16cf0ca4f1d0cc8c630a7fe967a86131f6b528556 | 7619 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/RRTMG_LW_DATA | bcfdee24b63a4c909522a329b8e16c539f0173c7e5aea2caf933ab4fe28c5c97 | 847552 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/RRTMG_LW_DATA_DBL | c93ec6190e16ecbb5bb4fe31e1b1ea4924c3b88a741779749f6eaec1acf989fc | 1694976 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/RRTMG_SW_DATA | a7d25f5b4d33be8629cbef7ecacc1ff413bf398a021297793e843ba1cc627baf | 680368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/RRTMG_SW_DATA_DBL | 5a6a0e0ba830b41519889f8c4a2be771437db56ea4f7526bc0798332b06234a5 | 1360572 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/RRTM_DATA | 45dc91514cf018e133301a1b667deeb17f5b65c49ccfaa9140761a8028bc8ae0 | 749248 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/RRTM_DATA_DBL | 4be1fa00674f947f306edde20433dc170b90ea1e71c0d25a98bcb6a0676e71ff | 1498368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/SOILPARM.TBL | 65ebc19ff475dd16c0a7482486b9f78dab951ac433af9b6b6688bf1f37e570de | 4399 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/SOILPARM.TBL_Kishne_2017 | 4cfe36cca32b2ea2618eeafc5d79174c75f7849077d5c953481adf82cec483a9 | 4400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/STOCHPERT.TBL | e0e6f147628f91ab3e7f3f4be6fc27296a43e1da8ded404b7fe06501fb42559e | 1105 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/TREECANOPY.TBL | a956353d335e64110f6485a42e14aaf2b4907dcc984aea92f92fa34d08caaf3c | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/TREECANOPY21.TBL | 1c87980ab9f82b5d6a2ebc62a984e88898a57f11e625e38fdc65d414d5b3ed02 | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/URBPARM.TBL | 5811226b3db503ae02d8b35cb5cb10e0e90804e451f0f4a5b76a274ee64773d0 | 12038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/URBPARM_LCZ.TBL | 2d1d4481875fa8d762a9115ac8f59b88d03d9557e02193439e156aed711f867e | 16132 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/URBPARM_UZE.TBL | 19da35cad1a70a0bc19ee3b183f356e2f5043a32039d22d45844ea2db0a715df | 8550 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/VEGPARM.TBL | 0fd2eccdb23b1e36023fc87c1d830e7bfe756f2f3560c84816eddbba721a40ba | 23037 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/aerosol.formatted | 5551eeccf5b4aa80e6ed8ae94e73c4ce8a4306a32aae9b3cc954cfa9c2c2d6aa | 29772567 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/aerosol_lat.formatted | 16121ba61f026c57ba18200988ae786609304f52959d24db86d50d8411473a1a | 736 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/aerosol_lon.formatted | 8201ebcba7199b5b737edf4f9f2a75d36ef4afa27fbdcffa9029dadcf8e61376 | 1152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/aerosol_plev.formatted | 3992b2acecbf604430cdb1975497d617cca3e314ee0ae3624f03e5a7f788fc96 | 192 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/bulkdens.asc_s_0_03_0_9 | a5607b3d0b9eb1fcdba30e50b714e348a81aabb64d963b0a00ff4f7b2a24caa6 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/bulkradii.asc_s_0_03_0_9 | e88c840873cc45f4b21bd7bf1a17a93c8275c5478a6c07e1b7d40f8d59d44d32 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/capacity.asc | 33759dbb0e238b37403ce2ad62759cca57c03538d72d34c2cc04bb7b2547c951 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/co2_trans | bdffafa58f96769b19112ccdce15dd02eb74df9b5c2025061b9fd3cb76651ea8 | 48000 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/coeff_p.asc | 22e2385ba836176919514fed221db94681fdd169182acec14af121426527b2ad | 206228 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/coeff_q.asc | 83ab3d88f266443b1bd3691771c9e99f907db1fbc9729b1c300edc85ad90ee3f | 9398 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/constants.asc | ef4f16ec1397ce9892684d4350f76c62f9673b99ee6520ca6c07b1f8a3b22c0e | 3950 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/create_p3_lookupTable_1.f90-v5.4 | a89e6c8fc4ea8cae609f042cc28d37c7f2b0587357eaf90d52a78006551c0954 | 71456 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/create_p3_lookupTable_2.f90-v5.3 | ffbdbd32f6e3355e5805caa4bbfce8619cb29dd2098604bc56b6fc6de4c49dbe | 45251 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/eclipse_besselian_elements.dat | 2a1367ae68a832c7b2bac26a8d28eeda6dbe860126e50dbb0714eec4c9d6eed7 | 80040 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/grib2map.tbl | 846ff6ffec204e8f15a5ef4540af4a369dec68ef862cb219001ac778a2c0a641 | 30547 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/gribmap.txt | 24425f411fcfb460a47436ea1aeb00f388f450ba3cb1734af89116a02cb8961b | 65700 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/ishmael-gamma-tab.bin | d85e4960053024a73034fb962ff52bd62aeae1b975dd5b4f62244ec82d622daa | 6060012 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/ishmael-qi-qc.bin | b8e4cea138b78668f027934bb8e39c6ea2cb62c1d277c17249c72003c8f4646c | 23346576 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/ishmael-qi-qr.bin | 69dd41d3d285318c95cac0d2dde10f8a3b25f802bf52ac781f29c87adb964cc4 | 46693152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/kernels.asc_s_0_03_0_9 | 170b34c8ba0e50cd433917cfe9a1cc673018113ca7e4b2ae33898e8fa1cabfa6 | 702587 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/kernels_z.asc | ce4e140595ff6db2434ecd5376a16c50ea410d03ddc1700bfa95a3490c15106f | 43016 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/masses.asc | f53d3acdaa0a3e2a265272fa22a2a0bd54292f51815149370bbf315e3fa1bee4 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/namelist.input | eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df | 5065 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/ozone.formatted | 2a13ee25809672e0419e40062c1fc753580adbf604bfc67a9166ef77c815dbc0 | 543744 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/ozone_lat.formatted | 761597f3454b99e3dbf15d2621b1ede88269948e96e47f4695b79fabd3cc6348 | 536 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/ozone_plev.formatted | df26a938273b22d2d04ec52b7297827a316cac0061fab020519241cdc0e61d48 | 708 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/p3_lookupTable_1.dat-v5.4_2momI | be1ab6fb03481e376e47c6c79d808af5d8ab069f2b242931e9c54801bad4ae84 | 1606038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/p3_lookupTable_1.dat-v5.4_3momI | 9a3c57ecc09498802c8d7cb3931dbb0200dcf0f51466b3e288120c080271e6dc | 17886038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/p3_lookupTable_2.dat-v5.3 | c9103041ead719cf9e2e215cf846e0ef81b2004f29386156444a079af6b24d97 | 15250032 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/physical_history.txt | 7118db9077324c840223830670527093ba12bdf4337d63352ac38b670b184a5b | 20 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/termvels.asc | 2b22e4ccf63e21e7dd7b381f46ed0f406b7e313b1e5fb43902423708e25443f3 | 3043 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/tr49t67 | 97501d7f0dc6b93a03803e5c59e57732010dd543686aa55404a1400dc62ae039 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/tr49t85 | b7b6aff5c9dbf05d7a0b8ecf08fd13b2762690aa4d0de77030b81a9167608e89 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/tr67t85 | 92a3320df2b0a9eb6fa6e4d62819969d7f410823fe11f3959090202c2a486388 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wind-turbine-1.tbl | d2f863483ab050673ebe15bd1e8510277e7a641845048b08afd7cdc97be7e069 | 485 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrf.exe | 68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f | 71834200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfbdy_d01 | 74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45 | 51979816 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfinput_d01 | 5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfinput_d01 | 5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_12:00:00 | e25ccaa70e78b4d4d4d71d6f840286905b88cfae74cd0e638591d4b110310f61 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_12:00:00 | e25ccaa70e78b4d4d4d71d6f840286905b88cfae74cd0e638591d4b110310f61 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_13:00:00 | 5bdcbabe30dbab2b7b75a9203417de9545513d0a5e7d313126f77a99418af76c | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_13:00:00 | 5bdcbabe30dbab2b7b75a9203417de9545513d0a5e7d313126f77a99418af76c | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_14:00:00 | 75ca2909f62b7e6d6f7ace30496112bfcca4454084301bde298d98c9f5115c16 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_14:00:00 | 75ca2909f62b7e6d6f7ace30496112bfcca4454084301bde298d98c9f5115c16 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_15:00:00 | 4e9f70025950ce1afb8cfffd9743caa8e5d104db811d9f5104ffc0dd74c9a251 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_15:00:00 | 4e9f70025950ce1afb8cfffd9743caa8e5d104db811d9f5104ffc0dd74c9a251 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_16:00:00 | c7c0cb1a36046c0e1fe1220fb60a55bcd650901b90505f008e5a22cfbf5cb831 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_16:00:00 | c7c0cb1a36046c0e1fe1220fb60a55bcd650901b90505f008e5a22cfbf5cb831 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_17:00:00 | 004b1fb2bf7d89cc2b88aaac4272e4df26113edd9cebcec71558cd150f99552f | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_17:00:00 | 004b1fb2bf7d89cc2b88aaac4272e4df26113edd9cebcec71558cd150f99552f | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_18:00:00 | 30054362579823e4d28706e188b5b1404167002c633a3fa7383f8a74c03776f8 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/FIXED_ORIGINAL_100/wrfout_d01_2026-08-16_18:00:00 | 30054362579823e4d28706e188b5b1404167002c633a3fa7383f8a74c03776f8 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/BROADBAND_CLOUD_GODDARD.bin | ad4bb1dd8446a2b00559ac425e21255a01b79a4cac7b5e3e693a3c98c222a1c8 | 172680 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAM_ABS_DATA | 91ee3079e43a6d908256fe3d1bd4bc5f3ac5662d2a8a1ed6ac9685be0555ad87 | 20580056 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAM_AEROPT_DATA | 9782ca59f2ebd12128e23f775e74665d7eb3dc386f53aaa053adfd926a388049 | 18208 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAMtr_volume_mixing_ratio | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAMtr_volume_mixing_ratio.A1B | 898ae2e2dbb8ba61934a2eda3b53727b44a13d7ab5339a9347dabd88e1bf21a1 | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAMtr_volume_mixing_ratio.A2 | f3110d6941e3880bf6a134bf36b7e039289f5653ee61a687a9edf6ce76b851ae | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAMtr_volume_mixing_ratio.RCP4.5 | ddbd4a28582380a396f4bf6f567ea2b1d2b326166bb1328dad8958445acd8ac8 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAMtr_volume_mixing_ratio.RCP6 | 5d3a5bbdaba4e18b9d271956081757a247a86c2674fbc7bac2446005c299ee30 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAMtr_volume_mixing_ratio.RCP8.5 | 82e8c0cd521784707d039030cd611ab473f8359c10ee64a7df8a45ac78331c32 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAMtr_volume_mixing_ratio.SSP119 | 8c99cb5622a087b0f4a7dc8be351e0e67c2b34ac3a4c266efc16ed730968401e | 42781 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAMtr_volume_mixing_ratio.SSP126 | 94070e69a7b96163178c4b1404c8fb6d240dec5294b67d51cea1bdd6fdbba191 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAMtr_volume_mixing_ratio.SSP245 | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAMtr_volume_mixing_ratio.SSP370 | 28d7cab970360f66fe8ea271d97c6a9705fc123c4c3bcb4f9e76ffb043355845 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CAMtr_volume_mixing_ratio.SSP585 | cb014ecc482e9fbd79dc676e5f815b96c7679291de6cdd5a27705e116603e12b | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CCN_ACTIVATE.BIN | f2b8d3916560f9046f89f8ac5f32c5292a1800498fd75301e422f147c82a3dbd | 35288 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CLM_ALB_ICE_DFS_DATA | b8ae396abd12f488f87ce3a516d707c73ec5350a3d241238f0cc064c92d99c28 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CLM_ALB_ICE_DRC_DATA | 067f83f7543e102ca92a36138cd71be795da5872bb83cf8a8eef7bbcbff8f45e | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CLM_ASM_ICE_DFS_DATA | db963d6cadfbec4a5706dbf589c2e95b229091f8d191949d1b46c723e4c3a0ed | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CLM_ASM_ICE_DRC_DATA | 6a1d9e1dd8c046d497216a37ac3d0d7da3faa53b2962b966be61ba38963b86e6 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CLM_DRDSDT0_DATA | e98303374a1f49f1ebe68375455daf61126b79f2a84b156e97738fcef3e44d8e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CLM_EXT_ICE_DFS_DATA | d53a1ac63d1aecaec091f55beea6842e535d47d166651da36ca44ea032644417 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CLM_EXT_ICE_DRC_DATA | e74c212073c04fb60007e47c4ce9b1b4da2e2688ae291e51d179422281a13971 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CLM_KAPPA_DATA | 8b8b1d624b417152ba639d4b3024d7011abf7218baea42ea6026d8aec57ed01e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/CLM_TAU_DATA | cb706cedda2fa8c807d2693eeec5b7da05a0fd5b1cc6fa08c476aef40ada4aa5 | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/ETAMPNEW_DATA | a913785f0bf5f75f8428ede706ce67ae804c3b285b4a34aeb533c4ad5cd9bea2 | 30200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/ETAMPNEW_DATA.expanded_rain | 28e60e6c83eb55889c4ab65eaa33e9fc3b557e5ab45c3dde7ee7153c2ef95a13 | 43400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/ETAMPNEW_DATA.expanded_rain_DBL | 28eae1101b529d36846434d3978c91ebbb7e46bd6adefc8226d3d992422dcbc4 | 86408 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/ETAMPNEW_DATA_DBL | 38e0b62ae898e5e26dc365b873eee23b8278a8b19eae55935767aa6c3d6a6334 | 60296 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/GENPARM.TBL | 9c02832a0e4a2ecaf47fcee485539aad95cd732c379c5c258161a88eb3d25ea2 | 261 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/HLC.TBL | 46b9e9575655ceac80f2ebf23fad59044a46615cffcfeebd69380a6a087df67d | 5513 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/LANDUSE.TBL | 7f661318ff5f06aed6b4b5508e4d077dc794cff03d5fb4447fe59c88d0ed2ece | 40650 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/MPTABLE.TBL | 7fae6a77660c90ad80845565ecfb057093c100de41f35f25a7ffa63f41c19e5d | 56140 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/README.namelist | 7aeb895ff81c7784254df227de404019479155a81075d8e4032451d45a6316e5 | 162590 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/README.physics_files | 60545c9eb7da132810cc20fefc8f71802efbb84179ad97ed097fe0f04e8b514b | 4487 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/README.rasm_diag | 5248bf40f945a6e2a5a416e6a22f2da97717448cc271b7405cf4c3497b34620c | 2646 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/README.tslist | c921f8902e64f3220ab71ea16cf0ca4f1d0cc8c630a7fe967a86131f6b528556 | 7619 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/RRTMG_LW_DATA | bcfdee24b63a4c909522a329b8e16c539f0173c7e5aea2caf933ab4fe28c5c97 | 847552 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/RRTMG_LW_DATA_DBL | c93ec6190e16ecbb5bb4fe31e1b1ea4924c3b88a741779749f6eaec1acf989fc | 1694976 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/RRTMG_SW_DATA | a7d25f5b4d33be8629cbef7ecacc1ff413bf398a021297793e843ba1cc627baf | 680368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/RRTMG_SW_DATA_DBL | 5a6a0e0ba830b41519889f8c4a2be771437db56ea4f7526bc0798332b06234a5 | 1360572 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/RRTM_DATA | 45dc91514cf018e133301a1b667deeb17f5b65c49ccfaa9140761a8028bc8ae0 | 749248 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/RRTM_DATA_DBL | 4be1fa00674f947f306edde20433dc170b90ea1e71c0d25a98bcb6a0676e71ff | 1498368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/SOILPARM.TBL | 65ebc19ff475dd16c0a7482486b9f78dab951ac433af9b6b6688bf1f37e570de | 4399 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/SOILPARM.TBL_Kishne_2017 | 4cfe36cca32b2ea2618eeafc5d79174c75f7849077d5c953481adf82cec483a9 | 4400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/STOCHPERT.TBL | e0e6f147628f91ab3e7f3f4be6fc27296a43e1da8ded404b7fe06501fb42559e | 1105 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/TREECANOPY.TBL | a956353d335e64110f6485a42e14aaf2b4907dcc984aea92f92fa34d08caaf3c | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/TREECANOPY21.TBL | 1c87980ab9f82b5d6a2ebc62a984e88898a57f11e625e38fdc65d414d5b3ed02 | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/URBPARM.TBL | 5811226b3db503ae02d8b35cb5cb10e0e90804e451f0f4a5b76a274ee64773d0 | 12038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/URBPARM_LCZ.TBL | 2d1d4481875fa8d762a9115ac8f59b88d03d9557e02193439e156aed711f867e | 16132 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/URBPARM_UZE.TBL | 19da35cad1a70a0bc19ee3b183f356e2f5043a32039d22d45844ea2db0a715df | 8550 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/VEGPARM.TBL | 0fd2eccdb23b1e36023fc87c1d830e7bfe756f2f3560c84816eddbba721a40ba | 23037 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/aerosol.formatted | 5551eeccf5b4aa80e6ed8ae94e73c4ce8a4306a32aae9b3cc954cfa9c2c2d6aa | 29772567 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/aerosol_lat.formatted | 16121ba61f026c57ba18200988ae786609304f52959d24db86d50d8411473a1a | 736 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/aerosol_lon.formatted | 8201ebcba7199b5b737edf4f9f2a75d36ef4afa27fbdcffa9029dadcf8e61376 | 1152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/aerosol_plev.formatted | 3992b2acecbf604430cdb1975497d617cca3e314ee0ae3624f03e5a7f788fc96 | 192 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/bulkdens.asc_s_0_03_0_9 | a5607b3d0b9eb1fcdba30e50b714e348a81aabb64d963b0a00ff4f7b2a24caa6 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/bulkradii.asc_s_0_03_0_9 | e88c840873cc45f4b21bd7bf1a17a93c8275c5478a6c07e1b7d40f8d59d44d32 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/capacity.asc | 33759dbb0e238b37403ce2ad62759cca57c03538d72d34c2cc04bb7b2547c951 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/co2_trans | bdffafa58f96769b19112ccdce15dd02eb74df9b5c2025061b9fd3cb76651ea8 | 48000 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/coeff_p.asc | 22e2385ba836176919514fed221db94681fdd169182acec14af121426527b2ad | 206228 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/coeff_q.asc | 83ab3d88f266443b1bd3691771c9e99f907db1fbc9729b1c300edc85ad90ee3f | 9398 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/constants.asc | ef4f16ec1397ce9892684d4350f76c62f9673b99ee6520ca6c07b1f8a3b22c0e | 3950 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/create_p3_lookupTable_1.f90-v5.4 | a89e6c8fc4ea8cae609f042cc28d37c7f2b0587357eaf90d52a78006551c0954 | 71456 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/create_p3_lookupTable_2.f90-v5.3 | ffbdbd32f6e3355e5805caa4bbfce8619cb29dd2098604bc56b6fc6de4c49dbe | 45251 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/eclipse_besselian_elements.dat | 2a1367ae68a832c7b2bac26a8d28eeda6dbe860126e50dbb0714eec4c9d6eed7 | 80040 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/grib2map.tbl | 846ff6ffec204e8f15a5ef4540af4a369dec68ef862cb219001ac778a2c0a641 | 30547 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/gribmap.txt | 24425f411fcfb460a47436ea1aeb00f388f450ba3cb1734af89116a02cb8961b | 65700 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/ishmael-gamma-tab.bin | d85e4960053024a73034fb962ff52bd62aeae1b975dd5b4f62244ec82d622daa | 6060012 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/ishmael-qi-qc.bin | b8e4cea138b78668f027934bb8e39c6ea2cb62c1d277c17249c72003c8f4646c | 23346576 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/ishmael-qi-qr.bin | 69dd41d3d285318c95cac0d2dde10f8a3b25f802bf52ac781f29c87adb964cc4 | 46693152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/kernels.asc_s_0_03_0_9 | 170b34c8ba0e50cd433917cfe9a1cc673018113ca7e4b2ae33898e8fa1cabfa6 | 702587 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/kernels_z.asc | ce4e140595ff6db2434ecd5376a16c50ea410d03ddc1700bfa95a3490c15106f | 43016 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/masses.asc | f53d3acdaa0a3e2a265272fa22a2a0bd54292f51815149370bbf315e3fa1bee4 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/namelist.input | eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df | 5065 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/ozone.formatted | 2a13ee25809672e0419e40062c1fc753580adbf604bfc67a9166ef77c815dbc0 | 543744 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/ozone_lat.formatted | 761597f3454b99e3dbf15d2621b1ede88269948e96e47f4695b79fabd3cc6348 | 536 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/ozone_plev.formatted | df26a938273b22d2d04ec52b7297827a316cac0061fab020519241cdc0e61d48 | 708 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/p3_lookupTable_1.dat-v5.4_2momI | be1ab6fb03481e376e47c6c79d808af5d8ab069f2b242931e9c54801bad4ae84 | 1606038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/p3_lookupTable_1.dat-v5.4_3momI | 9a3c57ecc09498802c8d7cb3931dbb0200dcf0f51466b3e288120c080271e6dc | 17886038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/p3_lookupTable_2.dat-v5.3 | c9103041ead719cf9e2e215cf846e0ef81b2004f29386156444a079af6b24d97 | 15250032 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/physical_history.txt | 7118db9077324c840223830670527093ba12bdf4337d63352ac38b670b184a5b | 20 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/termvels.asc | 2b22e4ccf63e21e7dd7b381f46ed0f406b7e313b1e5fb43902423708e25443f3 | 3043 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/tr49t67 | 97501d7f0dc6b93a03803e5c59e57732010dd543686aa55404a1400dc62ae039 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/tr49t85 | b7b6aff5c9dbf05d7a0b8ecf08fd13b2762690aa4d0de77030b81a9167608e89 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/tr67t85 | 92a3320df2b0a9eb6fa6e4d62819969d7f410823fe11f3959090202c2a486388 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wind-turbine-1.tbl | d2f863483ab050673ebe15bd1e8510277e7a641845048b08afd7cdc97be7e069 | 485 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrf.exe | de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168 | 71834200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfbdy_d01 | 74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45 | 51979816 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfinput_d01 | 55bc49c5d264f7009b9dee5ef2f83f50c58ac2c0c6d7fd9c9d61161ce1b43c8c | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfinput_d01 | 55bc49c5d264f7009b9dee5ef2f83f50c58ac2c0c6d7fd9c9d61161ce1b43c8c | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_12:00:00 | 3a79f178c31917b0b23d93f3e07f52a8c98033a02215b3a502883186a7aee54b | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_12:00:00 | 3a79f178c31917b0b23d93f3e07f52a8c98033a02215b3a502883186a7aee54b | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_13:00:00 | c23afd52722fbd355f67a7e77027aee47dd643ce1f458904b75768b9fabbbca5 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_13:00:00 | c23afd52722fbd355f67a7e77027aee47dd643ce1f458904b75768b9fabbbca5 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_14:00:00 | e09ec27f2fd576fe68d75289e8f4515f974dcf933c9a26a3896d0cdb85e1ae31 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_14:00:00 | e09ec27f2fd576fe68d75289e8f4515f974dcf933c9a26a3896d0cdb85e1ae31 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_15:00:00 | b4587327bb3e128b6cf488ab8e9d753781ab69e560e856c23c2ee4d0e5870d79 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_15:00:00 | b4587327bb3e128b6cf488ab8e9d753781ab69e560e856c23c2ee4d0e5870d79 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_16:00:00 | 3d14e6ff271ae85b0c9c57a09bc2c3c49584f01357054d1b61cf1ef1fcf4c59e | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_16:00:00 | 3d14e6ff271ae85b0c9c57a09bc2c3c49584f01357054d1b61cf1ef1fcf4c59e | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_17:00:00 | f55a9f04f3dd6416fedf2eb3e5b974a2dae1602c94ba80a5051f58a7e17b0fe4 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_17:00:00 | f55a9f04f3dd6416fedf2eb3e5b974a2dae1602c94ba80a5051f58a7e17b0fe4 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_18:00:00 | f4443a63a592b3cfc09389eaf0b58820c8a307c8ecc1734231c0434035730c27 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G50_90/wrfout_d01_2026-08-16_18:00:00 | f4443a63a592b3cfc09389eaf0b58820c8a307c8ecc1734231c0434035730c27 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/BROADBAND_CLOUD_GODDARD.bin | ad4bb1dd8446a2b00559ac425e21255a01b79a4cac7b5e3e693a3c98c222a1c8 | 172680 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAM_ABS_DATA | 91ee3079e43a6d908256fe3d1bd4bc5f3ac5662d2a8a1ed6ac9685be0555ad87 | 20580056 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAM_AEROPT_DATA | 9782ca59f2ebd12128e23f775e74665d7eb3dc386f53aaa053adfd926a388049 | 18208 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAMtr_volume_mixing_ratio | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAMtr_volume_mixing_ratio.A1B | 898ae2e2dbb8ba61934a2eda3b53727b44a13d7ab5339a9347dabd88e1bf21a1 | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAMtr_volume_mixing_ratio.A2 | f3110d6941e3880bf6a134bf36b7e039289f5653ee61a687a9edf6ce76b851ae | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAMtr_volume_mixing_ratio.RCP4.5 | ddbd4a28582380a396f4bf6f567ea2b1d2b326166bb1328dad8958445acd8ac8 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAMtr_volume_mixing_ratio.RCP6 | 5d3a5bbdaba4e18b9d271956081757a247a86c2674fbc7bac2446005c299ee30 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAMtr_volume_mixing_ratio.RCP8.5 | 82e8c0cd521784707d039030cd611ab473f8359c10ee64a7df8a45ac78331c32 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAMtr_volume_mixing_ratio.SSP119 | 8c99cb5622a087b0f4a7dc8be351e0e67c2b34ac3a4c266efc16ed730968401e | 42781 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAMtr_volume_mixing_ratio.SSP126 | 94070e69a7b96163178c4b1404c8fb6d240dec5294b67d51cea1bdd6fdbba191 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAMtr_volume_mixing_ratio.SSP245 | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAMtr_volume_mixing_ratio.SSP370 | 28d7cab970360f66fe8ea271d97c6a9705fc123c4c3bcb4f9e76ffb043355845 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CAMtr_volume_mixing_ratio.SSP585 | cb014ecc482e9fbd79dc676e5f815b96c7679291de6cdd5a27705e116603e12b | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CCN_ACTIVATE.BIN | f2b8d3916560f9046f89f8ac5f32c5292a1800498fd75301e422f147c82a3dbd | 35288 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CLM_ALB_ICE_DFS_DATA | b8ae396abd12f488f87ce3a516d707c73ec5350a3d241238f0cc064c92d99c28 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CLM_ALB_ICE_DRC_DATA | 067f83f7543e102ca92a36138cd71be795da5872bb83cf8a8eef7bbcbff8f45e | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CLM_ASM_ICE_DFS_DATA | db963d6cadfbec4a5706dbf589c2e95b229091f8d191949d1b46c723e4c3a0ed | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CLM_ASM_ICE_DRC_DATA | 6a1d9e1dd8c046d497216a37ac3d0d7da3faa53b2962b966be61ba38963b86e6 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CLM_DRDSDT0_DATA | e98303374a1f49f1ebe68375455daf61126b79f2a84b156e97738fcef3e44d8e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CLM_EXT_ICE_DFS_DATA | d53a1ac63d1aecaec091f55beea6842e535d47d166651da36ca44ea032644417 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CLM_EXT_ICE_DRC_DATA | e74c212073c04fb60007e47c4ce9b1b4da2e2688ae291e51d179422281a13971 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CLM_KAPPA_DATA | 8b8b1d624b417152ba639d4b3024d7011abf7218baea42ea6026d8aec57ed01e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/CLM_TAU_DATA | cb706cedda2fa8c807d2693eeec5b7da05a0fd5b1cc6fa08c476aef40ada4aa5 | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/ETAMPNEW_DATA | a913785f0bf5f75f8428ede706ce67ae804c3b285b4a34aeb533c4ad5cd9bea2 | 30200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/ETAMPNEW_DATA.expanded_rain | 28e60e6c83eb55889c4ab65eaa33e9fc3b557e5ab45c3dde7ee7153c2ef95a13 | 43400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/ETAMPNEW_DATA.expanded_rain_DBL | 28eae1101b529d36846434d3978c91ebbb7e46bd6adefc8226d3d992422dcbc4 | 86408 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/ETAMPNEW_DATA_DBL | 38e0b62ae898e5e26dc365b873eee23b8278a8b19eae55935767aa6c3d6a6334 | 60296 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/GENPARM.TBL | 9c02832a0e4a2ecaf47fcee485539aad95cd732c379c5c258161a88eb3d25ea2 | 261 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/HLC.TBL | 46b9e9575655ceac80f2ebf23fad59044a46615cffcfeebd69380a6a087df67d | 5513 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/LANDUSE.TBL | 7f661318ff5f06aed6b4b5508e4d077dc794cff03d5fb4447fe59c88d0ed2ece | 40650 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/MPTABLE.TBL | 7fae6a77660c90ad80845565ecfb057093c100de41f35f25a7ffa63f41c19e5d | 56140 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/README.namelist | 7aeb895ff81c7784254df227de404019479155a81075d8e4032451d45a6316e5 | 162590 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/README.physics_files | 60545c9eb7da132810cc20fefc8f71802efbb84179ad97ed097fe0f04e8b514b | 4487 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/README.rasm_diag | 5248bf40f945a6e2a5a416e6a22f2da97717448cc271b7405cf4c3497b34620c | 2646 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/README.tslist | c921f8902e64f3220ab71ea16cf0ca4f1d0cc8c630a7fe967a86131f6b528556 | 7619 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/RRTMG_LW_DATA | bcfdee24b63a4c909522a329b8e16c539f0173c7e5aea2caf933ab4fe28c5c97 | 847552 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/RRTMG_LW_DATA_DBL | c93ec6190e16ecbb5bb4fe31e1b1ea4924c3b88a741779749f6eaec1acf989fc | 1694976 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/RRTMG_SW_DATA | a7d25f5b4d33be8629cbef7ecacc1ff413bf398a021297793e843ba1cc627baf | 680368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/RRTMG_SW_DATA_DBL | 5a6a0e0ba830b41519889f8c4a2be771437db56ea4f7526bc0798332b06234a5 | 1360572 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/RRTM_DATA | 45dc91514cf018e133301a1b667deeb17f5b65c49ccfaa9140761a8028bc8ae0 | 749248 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/RRTM_DATA_DBL | 4be1fa00674f947f306edde20433dc170b90ea1e71c0d25a98bcb6a0676e71ff | 1498368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/SOILPARM.TBL | 65ebc19ff475dd16c0a7482486b9f78dab951ac433af9b6b6688bf1f37e570de | 4399 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/SOILPARM.TBL_Kishne_2017 | 4cfe36cca32b2ea2618eeafc5d79174c75f7849077d5c953481adf82cec483a9 | 4400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/STOCHPERT.TBL | e0e6f147628f91ab3e7f3f4be6fc27296a43e1da8ded404b7fe06501fb42559e | 1105 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/TREECANOPY.TBL | a956353d335e64110f6485a42e14aaf2b4907dcc984aea92f92fa34d08caaf3c | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/TREECANOPY21.TBL | 1c87980ab9f82b5d6a2ebc62a984e88898a57f11e625e38fdc65d414d5b3ed02 | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/URBPARM.TBL | 5811226b3db503ae02d8b35cb5cb10e0e90804e451f0f4a5b76a274ee64773d0 | 12038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/URBPARM_LCZ.TBL | 2d1d4481875fa8d762a9115ac8f59b88d03d9557e02193439e156aed711f867e | 16132 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/URBPARM_UZE.TBL | 19da35cad1a70a0bc19ee3b183f356e2f5043a32039d22d45844ea2db0a715df | 8550 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/VEGPARM.TBL | 0fd2eccdb23b1e36023fc87c1d830e7bfe756f2f3560c84816eddbba721a40ba | 23037 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/aerosol.formatted | 5551eeccf5b4aa80e6ed8ae94e73c4ce8a4306a32aae9b3cc954cfa9c2c2d6aa | 29772567 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/aerosol_lat.formatted | 16121ba61f026c57ba18200988ae786609304f52959d24db86d50d8411473a1a | 736 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/aerosol_lon.formatted | 8201ebcba7199b5b737edf4f9f2a75d36ef4afa27fbdcffa9029dadcf8e61376 | 1152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/aerosol_plev.formatted | 3992b2acecbf604430cdb1975497d617cca3e314ee0ae3624f03e5a7f788fc96 | 192 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/bulkdens.asc_s_0_03_0_9 | a5607b3d0b9eb1fcdba30e50b714e348a81aabb64d963b0a00ff4f7b2a24caa6 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/bulkradii.asc_s_0_03_0_9 | e88c840873cc45f4b21bd7bf1a17a93c8275c5478a6c07e1b7d40f8d59d44d32 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/capacity.asc | 33759dbb0e238b37403ce2ad62759cca57c03538d72d34c2cc04bb7b2547c951 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/co2_trans | bdffafa58f96769b19112ccdce15dd02eb74df9b5c2025061b9fd3cb76651ea8 | 48000 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/coeff_p.asc | 22e2385ba836176919514fed221db94681fdd169182acec14af121426527b2ad | 206228 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/coeff_q.asc | 83ab3d88f266443b1bd3691771c9e99f907db1fbc9729b1c300edc85ad90ee3f | 9398 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/constants.asc | ef4f16ec1397ce9892684d4350f76c62f9673b99ee6520ca6c07b1f8a3b22c0e | 3950 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/create_p3_lookupTable_1.f90-v5.4 | a89e6c8fc4ea8cae609f042cc28d37c7f2b0587357eaf90d52a78006551c0954 | 71456 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/create_p3_lookupTable_2.f90-v5.3 | ffbdbd32f6e3355e5805caa4bbfce8619cb29dd2098604bc56b6fc6de4c49dbe | 45251 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/eclipse_besselian_elements.dat | 2a1367ae68a832c7b2bac26a8d28eeda6dbe860126e50dbb0714eec4c9d6eed7 | 80040 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/grib2map.tbl | 846ff6ffec204e8f15a5ef4540af4a369dec68ef862cb219001ac778a2c0a641 | 30547 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/gribmap.txt | 24425f411fcfb460a47436ea1aeb00f388f450ba3cb1734af89116a02cb8961b | 65700 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/ishmael-gamma-tab.bin | d85e4960053024a73034fb962ff52bd62aeae1b975dd5b4f62244ec82d622daa | 6060012 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/ishmael-qi-qc.bin | b8e4cea138b78668f027934bb8e39c6ea2cb62c1d277c17249c72003c8f4646c | 23346576 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/ishmael-qi-qr.bin | 69dd41d3d285318c95cac0d2dde10f8a3b25f802bf52ac781f29c87adb964cc4 | 46693152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/kernels.asc_s_0_03_0_9 | 170b34c8ba0e50cd433917cfe9a1cc673018113ca7e4b2ae33898e8fa1cabfa6 | 702587 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/kernels_z.asc | ce4e140595ff6db2434ecd5376a16c50ea410d03ddc1700bfa95a3490c15106f | 43016 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/masses.asc | f53d3acdaa0a3e2a265272fa22a2a0bd54292f51815149370bbf315e3fa1bee4 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/namelist.input | eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df | 5065 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/ozone.formatted | 2a13ee25809672e0419e40062c1fc753580adbf604bfc67a9166ef77c815dbc0 | 543744 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/ozone_lat.formatted | 761597f3454b99e3dbf15d2621b1ede88269948e96e47f4695b79fabd3cc6348 | 536 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/ozone_plev.formatted | df26a938273b22d2d04ec52b7297827a316cac0061fab020519241cdc0e61d48 | 708 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/p3_lookupTable_1.dat-v5.4_2momI | be1ab6fb03481e376e47c6c79d808af5d8ab069f2b242931e9c54801bad4ae84 | 1606038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/p3_lookupTable_1.dat-v5.4_3momI | 9a3c57ecc09498802c8d7cb3931dbb0200dcf0f51466b3e288120c080271e6dc | 17886038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/p3_lookupTable_2.dat-v5.3 | c9103041ead719cf9e2e215cf846e0ef81b2004f29386156444a079af6b24d97 | 15250032 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/physical_history.txt | 7118db9077324c840223830670527093ba12bdf4337d63352ac38b670b184a5b | 20 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/termvels.asc | 2b22e4ccf63e21e7dd7b381f46ed0f406b7e313b1e5fb43902423708e25443f3 | 3043 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/tr49t67 | 97501d7f0dc6b93a03803e5c59e57732010dd543686aa55404a1400dc62ae039 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/tr49t85 | b7b6aff5c9dbf05d7a0b8ecf08fd13b2762690aa4d0de77030b81a9167608e89 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/tr67t85 | 92a3320df2b0a9eb6fa6e4d62819969d7f410823fe11f3959090202c2a486388 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wind-turbine-1.tbl | d2f863483ab050673ebe15bd1e8510277e7a641845048b08afd7cdc97be7e069 | 485 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrf.exe | de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168 | 71834200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfbdy_d01 | 74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45 | 51979816 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfinput_d01 | 22a6ac3831773d336db74804fed2de20601467e9db02e67730d9ef4ec0127179 | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfinput_d01 | 22a6ac3831773d336db74804fed2de20601467e9db02e67730d9ef4ec0127179 | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_12:00:00 | 5b45456ed14977309a409072815ac5e45b00d9c00211f98edad21a6bc26bda5d | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_12:00:00 | 5b45456ed14977309a409072815ac5e45b00d9c00211f98edad21a6bc26bda5d | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_13:00:00 | 4e41355ac9f6136eb412ce79cd517a204803e6668e2a3a3cda35a5cebbf26aba | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_13:00:00 | 4e41355ac9f6136eb412ce79cd517a204803e6668e2a3a3cda35a5cebbf26aba | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_14:00:00 | de6344718c3af896489c19acbbda65e96658b0d6adb9928a105aaaad7cf0772f | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_14:00:00 | de6344718c3af896489c19acbbda65e96658b0d6adb9928a105aaaad7cf0772f | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_15:00:00 | fbd81dad3e004998576ffca2f2a6f1a933ebd789fd16ec1e7e248a77eef03320 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_15:00:00 | fbd81dad3e004998576ffca2f2a6f1a933ebd789fd16ec1e7e248a77eef03320 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_16:00:00 | 119bb0cc327c9da168a806f8dc638b0dccd8acadab1bede668cc554db60e8da5 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_16:00:00 | 119bb0cc327c9da168a806f8dc638b0dccd8acadab1bede668cc554db60e8da5 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_17:00:00 | 04ce171da302fe676e55e08c8256fd5e0322c1619ed82c33c75a2f71b061ff9a | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_17:00:00 | 04ce171da302fe676e55e08c8256fd5e0322c1619ed82c33c75a2f71b061ff9a | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_18:00:00 | d1aa914b41c050ccfeeaf32b256e8f558848a381f93f6a56f272c9799f4d7e19 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G75_95/wrfout_d01_2026-08-16_18:00:00 | d1aa914b41c050ccfeeaf32b256e8f558848a381f93f6a56f272c9799f4d7e19 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/BROADBAND_CLOUD_GODDARD.bin | ad4bb1dd8446a2b00559ac425e21255a01b79a4cac7b5e3e693a3c98c222a1c8 | 172680 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAM_ABS_DATA | 91ee3079e43a6d908256fe3d1bd4bc5f3ac5662d2a8a1ed6ac9685be0555ad87 | 20580056 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAM_AEROPT_DATA | 9782ca59f2ebd12128e23f775e74665d7eb3dc386f53aaa053adfd926a388049 | 18208 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAMtr_volume_mixing_ratio | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAMtr_volume_mixing_ratio.A1B | 898ae2e2dbb8ba61934a2eda3b53727b44a13d7ab5339a9347dabd88e1bf21a1 | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAMtr_volume_mixing_ratio.A2 | f3110d6941e3880bf6a134bf36b7e039289f5653ee61a687a9edf6ce76b851ae | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAMtr_volume_mixing_ratio.RCP4.5 | ddbd4a28582380a396f4bf6f567ea2b1d2b326166bb1328dad8958445acd8ac8 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAMtr_volume_mixing_ratio.RCP6 | 5d3a5bbdaba4e18b9d271956081757a247a86c2674fbc7bac2446005c299ee30 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAMtr_volume_mixing_ratio.RCP8.5 | 82e8c0cd521784707d039030cd611ab473f8359c10ee64a7df8a45ac78331c32 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAMtr_volume_mixing_ratio.SSP119 | 8c99cb5622a087b0f4a7dc8be351e0e67c2b34ac3a4c266efc16ed730968401e | 42781 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAMtr_volume_mixing_ratio.SSP126 | 94070e69a7b96163178c4b1404c8fb6d240dec5294b67d51cea1bdd6fdbba191 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAMtr_volume_mixing_ratio.SSP245 | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAMtr_volume_mixing_ratio.SSP370 | 28d7cab970360f66fe8ea271d97c6a9705fc123c4c3bcb4f9e76ffb043355845 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CAMtr_volume_mixing_ratio.SSP585 | cb014ecc482e9fbd79dc676e5f815b96c7679291de6cdd5a27705e116603e12b | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CCN_ACTIVATE.BIN | f2b8d3916560f9046f89f8ac5f32c5292a1800498fd75301e422f147c82a3dbd | 35288 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CLM_ALB_ICE_DFS_DATA | b8ae396abd12f488f87ce3a516d707c73ec5350a3d241238f0cc064c92d99c28 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CLM_ALB_ICE_DRC_DATA | 067f83f7543e102ca92a36138cd71be795da5872bb83cf8a8eef7bbcbff8f45e | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CLM_ASM_ICE_DFS_DATA | db963d6cadfbec4a5706dbf589c2e95b229091f8d191949d1b46c723e4c3a0ed | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CLM_ASM_ICE_DRC_DATA | 6a1d9e1dd8c046d497216a37ac3d0d7da3faa53b2962b966be61ba38963b86e6 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CLM_DRDSDT0_DATA | e98303374a1f49f1ebe68375455daf61126b79f2a84b156e97738fcef3e44d8e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CLM_EXT_ICE_DFS_DATA | d53a1ac63d1aecaec091f55beea6842e535d47d166651da36ca44ea032644417 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CLM_EXT_ICE_DRC_DATA | e74c212073c04fb60007e47c4ce9b1b4da2e2688ae291e51d179422281a13971 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CLM_KAPPA_DATA | 8b8b1d624b417152ba639d4b3024d7011abf7218baea42ea6026d8aec57ed01e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/CLM_TAU_DATA | cb706cedda2fa8c807d2693eeec5b7da05a0fd5b1cc6fa08c476aef40ada4aa5 | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/ETAMPNEW_DATA | a913785f0bf5f75f8428ede706ce67ae804c3b285b4a34aeb533c4ad5cd9bea2 | 30200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/ETAMPNEW_DATA.expanded_rain | 28e60e6c83eb55889c4ab65eaa33e9fc3b557e5ab45c3dde7ee7153c2ef95a13 | 43400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/ETAMPNEW_DATA.expanded_rain_DBL | 28eae1101b529d36846434d3978c91ebbb7e46bd6adefc8226d3d992422dcbc4 | 86408 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/ETAMPNEW_DATA_DBL | 38e0b62ae898e5e26dc365b873eee23b8278a8b19eae55935767aa6c3d6a6334 | 60296 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/GENPARM.TBL | 9c02832a0e4a2ecaf47fcee485539aad95cd732c379c5c258161a88eb3d25ea2 | 261 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/HLC.TBL | 46b9e9575655ceac80f2ebf23fad59044a46615cffcfeebd69380a6a087df67d | 5513 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/LANDUSE.TBL | 7f661318ff5f06aed6b4b5508e4d077dc794cff03d5fb4447fe59c88d0ed2ece | 40650 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/MPTABLE.TBL | 7fae6a77660c90ad80845565ecfb057093c100de41f35f25a7ffa63f41c19e5d | 56140 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/README.namelist | 7aeb895ff81c7784254df227de404019479155a81075d8e4032451d45a6316e5 | 162590 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/README.physics_files | 60545c9eb7da132810cc20fefc8f71802efbb84179ad97ed097fe0f04e8b514b | 4487 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/README.rasm_diag | 5248bf40f945a6e2a5a416e6a22f2da97717448cc271b7405cf4c3497b34620c | 2646 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/README.tslist | c921f8902e64f3220ab71ea16cf0ca4f1d0cc8c630a7fe967a86131f6b528556 | 7619 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/RRTMG_LW_DATA | bcfdee24b63a4c909522a329b8e16c539f0173c7e5aea2caf933ab4fe28c5c97 | 847552 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/RRTMG_LW_DATA_DBL | c93ec6190e16ecbb5bb4fe31e1b1ea4924c3b88a741779749f6eaec1acf989fc | 1694976 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/RRTMG_SW_DATA | a7d25f5b4d33be8629cbef7ecacc1ff413bf398a021297793e843ba1cc627baf | 680368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/RRTMG_SW_DATA_DBL | 5a6a0e0ba830b41519889f8c4a2be771437db56ea4f7526bc0798332b06234a5 | 1360572 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/RRTM_DATA | 45dc91514cf018e133301a1b667deeb17f5b65c49ccfaa9140761a8028bc8ae0 | 749248 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/RRTM_DATA_DBL | 4be1fa00674f947f306edde20433dc170b90ea1e71c0d25a98bcb6a0676e71ff | 1498368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/SOILPARM.TBL | 65ebc19ff475dd16c0a7482486b9f78dab951ac433af9b6b6688bf1f37e570de | 4399 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/SOILPARM.TBL_Kishne_2017 | 4cfe36cca32b2ea2618eeafc5d79174c75f7849077d5c953481adf82cec483a9 | 4400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/STOCHPERT.TBL | e0e6f147628f91ab3e7f3f4be6fc27296a43e1da8ded404b7fe06501fb42559e | 1105 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/TREECANOPY.TBL | a956353d335e64110f6485a42e14aaf2b4907dcc984aea92f92fa34d08caaf3c | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/TREECANOPY21.TBL | 1c87980ab9f82b5d6a2ebc62a984e88898a57f11e625e38fdc65d414d5b3ed02 | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/URBPARM.TBL | 5811226b3db503ae02d8b35cb5cb10e0e90804e451f0f4a5b76a274ee64773d0 | 12038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/URBPARM_LCZ.TBL | 2d1d4481875fa8d762a9115ac8f59b88d03d9557e02193439e156aed711f867e | 16132 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/URBPARM_UZE.TBL | 19da35cad1a70a0bc19ee3b183f356e2f5043a32039d22d45844ea2db0a715df | 8550 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/VEGPARM.TBL | 0fd2eccdb23b1e36023fc87c1d830e7bfe756f2f3560c84816eddbba721a40ba | 23037 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/aerosol.formatted | 5551eeccf5b4aa80e6ed8ae94e73c4ce8a4306a32aae9b3cc954cfa9c2c2d6aa | 29772567 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/aerosol_lat.formatted | 16121ba61f026c57ba18200988ae786609304f52959d24db86d50d8411473a1a | 736 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/aerosol_lon.formatted | 8201ebcba7199b5b737edf4f9f2a75d36ef4afa27fbdcffa9029dadcf8e61376 | 1152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/aerosol_plev.formatted | 3992b2acecbf604430cdb1975497d617cca3e314ee0ae3624f03e5a7f788fc96 | 192 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/bulkdens.asc_s_0_03_0_9 | a5607b3d0b9eb1fcdba30e50b714e348a81aabb64d963b0a00ff4f7b2a24caa6 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/bulkradii.asc_s_0_03_0_9 | e88c840873cc45f4b21bd7bf1a17a93c8275c5478a6c07e1b7d40f8d59d44d32 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/capacity.asc | 33759dbb0e238b37403ce2ad62759cca57c03538d72d34c2cc04bb7b2547c951 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/co2_trans | bdffafa58f96769b19112ccdce15dd02eb74df9b5c2025061b9fd3cb76651ea8 | 48000 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/coeff_p.asc | 22e2385ba836176919514fed221db94681fdd169182acec14af121426527b2ad | 206228 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/coeff_q.asc | 83ab3d88f266443b1bd3691771c9e99f907db1fbc9729b1c300edc85ad90ee3f | 9398 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/constants.asc | ef4f16ec1397ce9892684d4350f76c62f9673b99ee6520ca6c07b1f8a3b22c0e | 3950 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/create_p3_lookupTable_1.f90-v5.4 | a89e6c8fc4ea8cae609f042cc28d37c7f2b0587357eaf90d52a78006551c0954 | 71456 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/create_p3_lookupTable_2.f90-v5.3 | ffbdbd32f6e3355e5805caa4bbfce8619cb29dd2098604bc56b6fc6de4c49dbe | 45251 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/eclipse_besselian_elements.dat | 2a1367ae68a832c7b2bac26a8d28eeda6dbe860126e50dbb0714eec4c9d6eed7 | 80040 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/grib2map.tbl | 846ff6ffec204e8f15a5ef4540af4a369dec68ef862cb219001ac778a2c0a641 | 30547 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/gribmap.txt | 24425f411fcfb460a47436ea1aeb00f388f450ba3cb1734af89116a02cb8961b | 65700 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/ishmael-gamma-tab.bin | d85e4960053024a73034fb962ff52bd62aeae1b975dd5b4f62244ec82d622daa | 6060012 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/ishmael-qi-qc.bin | b8e4cea138b78668f027934bb8e39c6ea2cb62c1d277c17249c72003c8f4646c | 23346576 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/ishmael-qi-qr.bin | 69dd41d3d285318c95cac0d2dde10f8a3b25f802bf52ac781f29c87adb964cc4 | 46693152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/kernels.asc_s_0_03_0_9 | 170b34c8ba0e50cd433917cfe9a1cc673018113ca7e4b2ae33898e8fa1cabfa6 | 702587 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/kernels_z.asc | ce4e140595ff6db2434ecd5376a16c50ea410d03ddc1700bfa95a3490c15106f | 43016 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/masses.asc | f53d3acdaa0a3e2a265272fa22a2a0bd54292f51815149370bbf315e3fa1bee4 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/namelist.input | eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df | 5065 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/ozone.formatted | 2a13ee25809672e0419e40062c1fc753580adbf604bfc67a9166ef77c815dbc0 | 543744 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/ozone_lat.formatted | 761597f3454b99e3dbf15d2621b1ede88269948e96e47f4695b79fabd3cc6348 | 536 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/ozone_plev.formatted | df26a938273b22d2d04ec52b7297827a316cac0061fab020519241cdc0e61d48 | 708 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/p3_lookupTable_1.dat-v5.4_2momI | be1ab6fb03481e376e47c6c79d808af5d8ab069f2b242931e9c54801bad4ae84 | 1606038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/p3_lookupTable_1.dat-v5.4_3momI | 9a3c57ecc09498802c8d7cb3931dbb0200dcf0f51466b3e288120c080271e6dc | 17886038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/p3_lookupTable_2.dat-v5.3 | c9103041ead719cf9e2e215cf846e0ef81b2004f29386156444a079af6b24d97 | 15250032 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/physical_history.txt | 7118db9077324c840223830670527093ba12bdf4337d63352ac38b670b184a5b | 20 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/termvels.asc | 2b22e4ccf63e21e7dd7b381f46ed0f406b7e313b1e5fb43902423708e25443f3 | 3043 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/tr49t67 | 97501d7f0dc6b93a03803e5c59e57732010dd543686aa55404a1400dc62ae039 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/tr49t85 | b7b6aff5c9dbf05d7a0b8ecf08fd13b2762690aa4d0de77030b81a9167608e89 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/tr67t85 | 92a3320df2b0a9eb6fa6e4d62819969d7f410823fe11f3959090202c2a486388 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wind-turbine-1.tbl | d2f863483ab050673ebe15bd1e8510277e7a641845048b08afd7cdc97be7e069 | 485 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrf.exe | de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168 | 71834200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfbdy_d01 | 74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45 | 51979816 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfinput_d01 | 1e9103ffa2018e8ef6908b0d9274a56fd8b04eb8d4aa84e5cd9dae828aabbe90 | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfinput_d01 | 1e9103ffa2018e8ef6908b0d9274a56fd8b04eb8d4aa84e5cd9dae828aabbe90 | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_12:00:00 | dce8dda457acf1263d8fef02d7427f945a891af1fb5f3c248339dd7f9577f38b | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_12:00:00 | dce8dda457acf1263d8fef02d7427f945a891af1fb5f3c248339dd7f9577f38b | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_13:00:00 | 2e8d924c3dde0a5c7e884253f9546327607a2ea6f9445a6f13286ffd4deb7c2b | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_13:00:00 | 2e8d924c3dde0a5c7e884253f9546327607a2ea6f9445a6f13286ffd4deb7c2b | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_14:00:00 | 6d6211e04656a2a24b84fc729edcb6e6b93773b5976e51c38059894849dce8ec | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_14:00:00 | 6d6211e04656a2a24b84fc729edcb6e6b93773b5976e51c38059894849dce8ec | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_15:00:00 | 87d2c38d896afe4d1cc1613f07e835b69fc371b9c9acf87a8d0da71f6c6293ae | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_15:00:00 | 87d2c38d896afe4d1cc1613f07e835b69fc371b9c9acf87a8d0da71f6c6293ae | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_16:00:00 | 8aecdf80088e610d768ba299f3334d534ffd7dcdab50001cf1c3b812150d15d5 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_16:00:00 | 8aecdf80088e610d768ba299f3334d534ffd7dcdab50001cf1c3b812150d15d5 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_17:00:00 | 6f4b5da541c36a7d16bdcb0584ced723005d2e9702c3edae62ea113f25a52995 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_17:00:00 | 6f4b5da541c36a7d16bdcb0584ced723005d2e9702c3edae62ea113f25a52995 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_18:00:00 | b738a0ae1e88c478ed52fe4cf24cb5656f68f2f204b402e0f3008ec00b64f6e6 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/GATE_G90_99/wrfout_d01_2026-08-16_18:00:00 | b738a0ae1e88c478ed52fe4cf24cb5656f68f2f204b402e0f3008ec00b64f6e6 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/BROADBAND_CLOUD_GODDARD.bin | ad4bb1dd8446a2b00559ac425e21255a01b79a4cac7b5e3e693a3c98c222a1c8 | 172680 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAM_ABS_DATA | 91ee3079e43a6d908256fe3d1bd4bc5f3ac5662d2a8a1ed6ac9685be0555ad87 | 20580056 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAM_AEROPT_DATA | 9782ca59f2ebd12128e23f775e74665d7eb3dc386f53aaa053adfd926a388049 | 18208 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAMtr_volume_mixing_ratio | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAMtr_volume_mixing_ratio.A1B | 898ae2e2dbb8ba61934a2eda3b53727b44a13d7ab5339a9347dabd88e1bf21a1 | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAMtr_volume_mixing_ratio.A2 | f3110d6941e3880bf6a134bf36b7e039289f5653ee61a687a9edf6ce76b851ae | 955 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAMtr_volume_mixing_ratio.RCP4.5 | ddbd4a28582380a396f4bf6f567ea2b1d2b326166bb1328dad8958445acd8ac8 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAMtr_volume_mixing_ratio.RCP6 | 5d3a5bbdaba4e18b9d271956081757a247a86c2674fbc7bac2446005c299ee30 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAMtr_volume_mixing_ratio.RCP8.5 | 82e8c0cd521784707d039030cd611ab473f8359c10ee64a7df8a45ac78331c32 | 42838 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAMtr_volume_mixing_ratio.SSP119 | 8c99cb5622a087b0f4a7dc8be351e0e67c2b34ac3a4c266efc16ed730968401e | 42781 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAMtr_volume_mixing_ratio.SSP126 | 94070e69a7b96163178c4b1404c8fb6d240dec5294b67d51cea1bdd6fdbba191 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAMtr_volume_mixing_ratio.SSP245 | 9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAMtr_volume_mixing_ratio.SSP370 | 28d7cab970360f66fe8ea271d97c6a9705fc123c4c3bcb4f9e76ffb043355845 | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CAMtr_volume_mixing_ratio.SSP585 | cb014ecc482e9fbd79dc676e5f815b96c7679291de6cdd5a27705e116603e12b | 42780 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CCN_ACTIVATE.BIN | f2b8d3916560f9046f89f8ac5f32c5292a1800498fd75301e422f147c82a3dbd | 35288 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CLM_ALB_ICE_DFS_DATA | b8ae396abd12f488f87ce3a516d707c73ec5350a3d241238f0cc064c92d99c28 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CLM_ALB_ICE_DRC_DATA | 067f83f7543e102ca92a36138cd71be795da5872bb83cf8a8eef7bbcbff8f45e | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CLM_ASM_ICE_DFS_DATA | db963d6cadfbec4a5706dbf589c2e95b229091f8d191949d1b46c723e4c3a0ed | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CLM_ASM_ICE_DRC_DATA | 6a1d9e1dd8c046d497216a37ac3d0d7da3faa53b2962b966be61ba38963b86e6 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CLM_DRDSDT0_DATA | e98303374a1f49f1ebe68375455daf61126b79f2a84b156e97738fcef3e44d8e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CLM_EXT_ICE_DFS_DATA | d53a1ac63d1aecaec091f55beea6842e535d47d166651da36ca44ea032644417 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CLM_EXT_ICE_DRC_DATA | e74c212073c04fb60007e47c4ce9b1b4da2e2688ae291e51d179422281a13971 | 148571 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CLM_KAPPA_DATA | 8b8b1d624b417152ba639d4b3024d7011abf7218baea42ea6026d8aec57ed01e | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/CLM_TAU_DATA | cb706cedda2fa8c807d2693eeec5b7da05a0fd5b1cc6fa08c476aef40ada4aa5 | 68448 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/ETAMPNEW_DATA | a913785f0bf5f75f8428ede706ce67ae804c3b285b4a34aeb533c4ad5cd9bea2 | 30200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/ETAMPNEW_DATA.expanded_rain | 28e60e6c83eb55889c4ab65eaa33e9fc3b557e5ab45c3dde7ee7153c2ef95a13 | 43400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/ETAMPNEW_DATA.expanded_rain_DBL | 28eae1101b529d36846434d3978c91ebbb7e46bd6adefc8226d3d992422dcbc4 | 86408 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/ETAMPNEW_DATA_DBL | 38e0b62ae898e5e26dc365b873eee23b8278a8b19eae55935767aa6c3d6a6334 | 60296 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/GENPARM.TBL | 9c02832a0e4a2ecaf47fcee485539aad95cd732c379c5c258161a88eb3d25ea2 | 261 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/HLC.TBL | 46b9e9575655ceac80f2ebf23fad59044a46615cffcfeebd69380a6a087df67d | 5513 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/LANDUSE.TBL | 7f661318ff5f06aed6b4b5508e4d077dc794cff03d5fb4447fe59c88d0ed2ece | 40650 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/MPTABLE.TBL | 7fae6a77660c90ad80845565ecfb057093c100de41f35f25a7ffa63f41c19e5d | 56140 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/README.namelist | 7aeb895ff81c7784254df227de404019479155a81075d8e4032451d45a6316e5 | 162590 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/README.physics_files | 60545c9eb7da132810cc20fefc8f71802efbb84179ad97ed097fe0f04e8b514b | 4487 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/README.rasm_diag | 5248bf40f945a6e2a5a416e6a22f2da97717448cc271b7405cf4c3497b34620c | 2646 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/README.tslist | c921f8902e64f3220ab71ea16cf0ca4f1d0cc8c630a7fe967a86131f6b528556 | 7619 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/RRTMG_LW_DATA | bcfdee24b63a4c909522a329b8e16c539f0173c7e5aea2caf933ab4fe28c5c97 | 847552 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/RRTMG_LW_DATA_DBL | c93ec6190e16ecbb5bb4fe31e1b1ea4924c3b88a741779749f6eaec1acf989fc | 1694976 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/RRTMG_SW_DATA | a7d25f5b4d33be8629cbef7ecacc1ff413bf398a021297793e843ba1cc627baf | 680368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/RRTMG_SW_DATA_DBL | 5a6a0e0ba830b41519889f8c4a2be771437db56ea4f7526bc0798332b06234a5 | 1360572 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/RRTM_DATA | 45dc91514cf018e133301a1b667deeb17f5b65c49ccfaa9140761a8028bc8ae0 | 749248 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/RRTM_DATA_DBL | 4be1fa00674f947f306edde20433dc170b90ea1e71c0d25a98bcb6a0676e71ff | 1498368 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/SOILPARM.TBL | 65ebc19ff475dd16c0a7482486b9f78dab951ac433af9b6b6688bf1f37e570de | 4399 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/SOILPARM.TBL_Kishne_2017 | 4cfe36cca32b2ea2618eeafc5d79174c75f7849077d5c953481adf82cec483a9 | 4400 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/STOCHPERT.TBL | e0e6f147628f91ab3e7f3f4be6fc27296a43e1da8ded404b7fe06501fb42559e | 1105 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/TREECANOPY.TBL | a956353d335e64110f6485a42e14aaf2b4907dcc984aea92f92fa34d08caaf3c | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/TREECANOPY21.TBL | 1c87980ab9f82b5d6a2ebc62a984e88898a57f11e625e38fdc65d414d5b3ed02 | 1945 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/URBPARM.TBL | 5811226b3db503ae02d8b35cb5cb10e0e90804e451f0f4a5b76a274ee64773d0 | 12038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/URBPARM_LCZ.TBL | 2d1d4481875fa8d762a9115ac8f59b88d03d9557e02193439e156aed711f867e | 16132 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/URBPARM_UZE.TBL | 19da35cad1a70a0bc19ee3b183f356e2f5043a32039d22d45844ea2db0a715df | 8550 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/VEGPARM.TBL | 0fd2eccdb23b1e36023fc87c1d830e7bfe756f2f3560c84816eddbba721a40ba | 23037 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/aerosol.formatted | 5551eeccf5b4aa80e6ed8ae94e73c4ce8a4306a32aae9b3cc954cfa9c2c2d6aa | 29772567 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/aerosol_lat.formatted | 16121ba61f026c57ba18200988ae786609304f52959d24db86d50d8411473a1a | 736 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/aerosol_lon.formatted | 8201ebcba7199b5b737edf4f9f2a75d36ef4afa27fbdcffa9029dadcf8e61376 | 1152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/aerosol_plev.formatted | 3992b2acecbf604430cdb1975497d617cca3e314ee0ae3624f03e5a7f788fc96 | 192 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/bulkdens.asc_s_0_03_0_9 | a5607b3d0b9eb1fcdba30e50b714e348a81aabb64d963b0a00ff4f7b2a24caa6 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/bulkradii.asc_s_0_03_0_9 | e88c840873cc45f4b21bd7bf1a17a93c8275c5478a6c07e1b7d40f8d59d44d32 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/capacity.asc | 33759dbb0e238b37403ce2ad62759cca57c03538d72d34c2cc04bb7b2547c951 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/co2_trans | bdffafa58f96769b19112ccdce15dd02eb74df9b5c2025061b9fd3cb76651ea8 | 48000 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/coeff_p.asc | 22e2385ba836176919514fed221db94681fdd169182acec14af121426527b2ad | 206228 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/coeff_q.asc | 83ab3d88f266443b1bd3691771c9e99f907db1fbc9729b1c300edc85ad90ee3f | 9398 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/constants.asc | ef4f16ec1397ce9892684d4350f76c62f9673b99ee6520ca6c07b1f8a3b22c0e | 3950 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/create_p3_lookupTable_1.f90-v5.4 | a89e6c8fc4ea8cae609f042cc28d37c7f2b0587357eaf90d52a78006551c0954 | 71456 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/create_p3_lookupTable_2.f90-v5.3 | ffbdbd32f6e3355e5805caa4bbfce8619cb29dd2098604bc56b6fc6de4c49dbe | 45251 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/eclipse_besselian_elements.dat | 2a1367ae68a832c7b2bac26a8d28eeda6dbe860126e50dbb0714eec4c9d6eed7 | 80040 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/grib2map.tbl | 846ff6ffec204e8f15a5ef4540af4a369dec68ef862cb219001ac778a2c0a641 | 30547 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/gribmap.txt | 24425f411fcfb460a47436ea1aeb00f388f450ba3cb1734af89116a02cb8961b | 65700 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/ishmael-gamma-tab.bin | d85e4960053024a73034fb962ff52bd62aeae1b975dd5b4f62244ec82d622daa | 6060012 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/ishmael-qi-qc.bin | b8e4cea138b78668f027934bb8e39c6ea2cb62c1d277c17249c72003c8f4646c | 23346576 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/ishmael-qi-qr.bin | 69dd41d3d285318c95cac0d2dde10f8a3b25f802bf52ac781f29c87adb964cc4 | 46693152 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/kernels.asc_s_0_03_0_9 | 170b34c8ba0e50cd433917cfe9a1cc673018113ca7e4b2ae33898e8fa1cabfa6 | 702587 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/kernels_z.asc | ce4e140595ff6db2434ecd5376a16c50ea410d03ddc1700bfa95a3490c15106f | 43016 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/masses.asc | f53d3acdaa0a3e2a265272fa22a2a0bd54292f51815149370bbf315e3fa1bee4 | 3042 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/namelist.input | eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df | 5065 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/ozone.formatted | 2a13ee25809672e0419e40062c1fc753580adbf604bfc67a9166ef77c815dbc0 | 543744 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/ozone_lat.formatted | 761597f3454b99e3dbf15d2621b1ede88269948e96e47f4695b79fabd3cc6348 | 536 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/ozone_plev.formatted | df26a938273b22d2d04ec52b7297827a316cac0061fab020519241cdc0e61d48 | 708 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/p3_lookupTable_1.dat-v5.4_2momI | be1ab6fb03481e376e47c6c79d808af5d8ab069f2b242931e9c54801bad4ae84 | 1606038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/p3_lookupTable_1.dat-v5.4_3momI | 9a3c57ecc09498802c8d7cb3931dbb0200dcf0f51466b3e288120c080271e6dc | 17886038 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/p3_lookupTable_2.dat-v5.3 | c9103041ead719cf9e2e215cf846e0ef81b2004f29386156444a079af6b24d97 | 15250032 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/physical_history.txt | 7118db9077324c840223830670527093ba12bdf4337d63352ac38b670b184a5b | 20 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/termvels.asc | 2b22e4ccf63e21e7dd7b381f46ed0f406b7e313b1e5fb43902423708e25443f3 | 3043 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/tr49t67 | 97501d7f0dc6b93a03803e5c59e57732010dd543686aa55404a1400dc62ae039 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/tr49t85 | b7b6aff5c9dbf05d7a0b8ecf08fd13b2762690aa4d0de77030b81a9167608e89 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/tr67t85 | 92a3320df2b0a9eb6fa6e4d62819969d7f410823fe11f3959090202c2a486388 | 748503 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wind-turbine-1.tbl | d2f863483ab050673ebe15bd1e8510277e7a641845048b08afd7cdc97be7e069 | 485 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrf.exe | de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168 | 71834200 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfbdy_d01 | 74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45 | 51979816 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfinput_d01 | 9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5 | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfinput_d01 | 9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5 | 376278396 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_12:00:00 | b637f559e5e5e633916b6bcd35e16424c8f3f1f3ef5309ca1ac554a6edd09ef6 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_12:00:00 | b637f559e5e5e633916b6bcd35e16424c8f3f1f3ef5309ca1ac554a6edd09ef6 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_13:00:00 | 8159eb06ca85695c533de590c27d9274c4fec4c31a11aeff58516171dae11468 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_13:00:00 | 8159eb06ca85695c533de590c27d9274c4fec4c31a11aeff58516171dae11468 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_14:00:00 | bb0afd836d622d06eef78c445c80c4544e879cfa6963f7932882e86309117ff5 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_14:00:00 | bb0afd836d622d06eef78c445c80c4544e879cfa6963f7932882e86309117ff5 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_15:00:00 | 328cf6e21f5bff3f7098ad5a3690e5096b50be214555ae7d477134aa6e204eda | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_15:00:00 | 328cf6e21f5bff3f7098ad5a3690e5096b50be214555ae7d477134aa6e204eda | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_16:00:00 | 9fffef1bc00fb9a64e718a5f958ced9b9e393febc348b909e3fdc5bd4a828dcf | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_16:00:00 | 9fffef1bc00fb9a64e718a5f958ced9b9e393febc348b909e3fdc5bd4a828dcf | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_17:00:00 | a6333e706c2d007d4ed7afce0e24a9b34b0ffbcf853c020de816c8cdc89933d2 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_17:00:00 | a6333e706c2d007d4ed7afce0e24a9b34b0ffbcf853c020de816c8cdc89933d2 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_18:00:00 | 4cdec4a58afe6d777b1fd2392f872e9ac45ce7d31b2a8c1f8308a4760bfa1fe2 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_18:00:00 | 4cdec4a58afe6d777b1fd2392f872e9ac45ce7d31b2a8c1f8308a4760bfa1fe2 | 328253340 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun | f9b09c6d24ce83d52221fbc1cc59dbdf9f350ccf50b264e89980c4530c6369d4 | 3662 |
| /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh | 1f807842591f742c0e285df3769b4a07e8944536cbd0b0905e88520ae07dbcf8 | 8769 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/snow_lower_20261030/analysis/categorical_scores.csv | 3dcab1e1ca19b3bce65611a3196eeaa93ae0c23560f00145ccfbd6b0fd170c7b | 287100 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/snow_lower_20261030/analysis/continuous_scores.csv | 3c00bfc8680387b953909fbccec4ab1be1a3696929c31dcc708b584f418a3d46 | 38067 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/snow_lower_20261030/analysis/hour_13_arrays.npz | db3c69de36fe7d82ff3223dc92f849031fe5bb68bb7118592526e65fa6501048 | 955621 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/snow_lower_20261030/analysis/hour_14_arrays.npz | 5b3411c6b03fc1a9fdad78dd05fa04d5181b18e28adb8de6f96a11a220e3a983 | 991762 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/snow_lower_20261030/analysis/hour_15_arrays.npz | 2dcbd2c0960c75fc18b1932e37187ad1b53079ca245ad2e225b0c0157ce44bba | 1076969 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/snow_lower_20261030/analysis/hour_16_arrays.npz | 902b55a65837f64a1ae78fab0d8a59f3ce40906e82fa0aa0eab7c88d115765e5 | 1074345 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/snow_lower_20261030/analysis/hour_17_arrays.npz | f48d9b98e6cdf6acb48466bb9e3669739ecdc148bc751a64e2ecc2f1af3222e7 | 1026105 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/snow_lower_20261030/analysis/hour_18_arrays.npz | 91732db992aa3936946d789dae7445f5d9b29c10ee8da03dcb72d922b5841130 | 1087450 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/snow_lower_20261030/analysis/receipt.json | a9b8fa97e12d85bd49ce91b42f5126c8fc727ef0846eba1eeddc6a552a044602 | 157559 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/snow_lower_20261030/runtime/common_plan.json | 58dae266e4b4f893f5a9d940e30c8e38574823b03785e68b089811ef9d085871 | 548292 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/batch_receipt.json | 2716f7376d20575c4cf015434266dcdb4e4050ce12e2d203c13beb317a66aa4a | 4302 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/cases/EQ_G50_90/receipt.json | de2a12a7059e3f4baf2eca1b53c7c4934dbd6131445d9fa05b3fc8c0a98bb632 | 66007 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/cases/EQ_G75_95/receipt.json | 78f1058f3798c554d0ad676aa4dd7fa23eba7ed309da02ef2c9700313e41166e | 66014 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/cases/EQ_G90_99/receipt.json | bc136a0a2ae9bedb40a3f343834f2051de722ef71193ac1f597abbbb1b073974 | 66008 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/cases/FIXED_ORIGINAL_100/receipt.json | 4b40403a497ab90f8a5f639661ae52dc0b6e668a05ec38ccec9547dff1e25bc5 | 64966 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/cases/GATE_G50_90/receipt.json | e5b3cfff87f7418788eae8ac55cb574391d8caf3f18503357a1aabb28cd2d20f | 65936 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/cases/GATE_G75_95/receipt.json | 51307e54945e86bb8ebc3f2f129d31db13af6b919738c4a06a3e1f743755d3c3 | 65967 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/cases/GATE_G90_99/receipt.json | cfb49ad63f604848de09e1de061bfaa01e5f0eaf8dd778fe1b26e78b5ec7d555 | 65962 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/cases/ORIGINAL_B1_100/receipt.json | 4c084d3917825f639f1829e4f602f1469860dd94c50e4e0509a97d848a253bf5 | 64954 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/common_plan.json | a2d06679ea3a9b24a04f9ff359c842172f06fd7ec0f402f802c91399b2ad6a3a | 416965 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/common_plan.json | a2d06679ea3a9b24a04f9ff359c842172f06fd7ec0f402f802c91399b2ad6a3a | 416965 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/env.sh | 942b0e34704ab1c8b018398ab925522d6b9bc4ef86af2caebf004a5fa047808e | 492 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/final_receipt.json | 4322b9de5a4490a3f874c6cdb826889a1f721185f907aa6383e07f9c113f3f58 | 11903 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/finalize_batch.py | f9df2b1df245c2da9d96772e43512079bebf88e6ac176ba47228b41817a33968 | 5209 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/frozen/gate_manifest.json | 07e95e73af040e4388c6636634e334606ad1292bab7f30340d5148e90841b29c | 3830 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/frozen/initial_precip_gate_maps.npz | 40b8b1d2fd772a1fbf462824ab77f958f31be19f86733d09e7504ff4630e4909 | 6384019 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/history_validation.json | 8d912c0c05940d3cd9dfe8d84048381e7e87abab4e47741d094744f00c1eae52 | 42352 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/prepare_cases.py | 9ef9192e23393b953a50b4673ffd33f90193547d08f5bd92ab342888c62fb1bd | 22057 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/run_all.py | 984da127d06ba6143dba376ee7f8e3b861a1d75681fba20a2343503063fe0dba | 3766 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/runtime/run_case.py | 05ffae05ee2ef0402321a24afc55dfaec49b102ae43406bf0f010e196ecbb884 | 10395 |
| /var/tmp/cloudbal-weak-strong/docs/evidence/weak_strong_balance_20261030/selection_plan.json | 17e8833f2f28da76e1474f82440a88889bd55ba723ef9cd6618d06a0eb786248 | 8194 |
| /var/tmp/cloudbal-weak-strong/tests/intel_toolchain.sh | 5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4 | 3470 |
| /var/tmp/cloudbal-weak-strong/tools/cp02_snow_extension.py | b450747f0d376a353eff8c33da7ebbddfedc5d137fa9e53e0b37f0e71907da86 | 40866 |
| /var/tmp/cloudbal-weak-strong/tools/cp02_snow_lower.py | 04108676ffe44db688ee53a24ee07fdb2031a0d9fd4012f17619a6245c03d3c2 | 38498 |
| /var/tmp/cloudbal-weak-strong/tools/cp02_snow_sensitivity.py | 95c3e8591318eafda06598616fdec1c11f67aa78aef3306ab473a1602ccadc17 | 58225 |
| /var/tmp/cloudbal-weak-strong/tools/cp02_weak_strong_balance.py | 2572d41d352c70d72d8488fe9f0dc9d961de8b10c21f7ade459f131e7c4fbdb5 | 65718 |
| /var/tmp/cloudbal-weak-strong/tools/initial_precip_gate.py | 7363b02b603659bdf85af58e33193774ceed5a35e3dce9c24739fa2b2685c9fa | 12179 |
| /var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED/wrfinput_d01 | 9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5 | 376278396 |

추가 표본 독립성·검증을 의미하지 않는 비교 자료: prior trade-off audit source SHA-256 `4bf973ebf148de55531d24a6df6ba86deded1b6bff8f2e2990b95a2b5dc42213`, CSV `096c82ad9facf5932a363dd5c92a124d1b83928c2b76c1df0a5105b9dce286c4`, audit JSON `ba835b62e748c4c26e51b3401e6fbdc9d370c18693c152d824789f71183105ee`. 관측 강도 audit CSV `13a8ee9988dc9a30501de905984f59806b867010f623b6341624b2d3271c1cf6`, audit receipt `ff96adedcdf811dc312651a92e66c22d3261c9b76125e012a0a47196f203e1a6`. Stage-3 source probe JSON `f2583c72a6f3ac386c0c01b8e3a2ed4b3d32cca412c770ddfe7ecede6c48507a`, Markdown `1fa4c9dbf8d323ec0304b5cfb4b0847adc468b31b65c95415f2316a057c30fe2`, review `aa29987a64fe443fa436378422a9299eb6710d8e4772f36c8d95bc69cf7eae52`. 초기 게이트 지도 NPZ SHA-256 `40b8b1d2fd772a1fbf462824ab77f958f31be19f86733d09e7504ff4630e4909`, gate manifest SHA-256 `07e95e73af040e4388c6636634e334606ad1292bab7f30340d5148e90841b29c`. prior observed-band CSV SHA-256 `13a8ee9988dc9a30501de905984f59806b867010f623b6341624b2d3271c1cf6`, receipt SHA-256 `ff96adedcdf811dc312651a92e66c22d3261c9b76125e012a0a47196f203e1a6`. 파일별 출력 SHA-256은 [analysis receipt](evidence/weak_strong_balance_20261030/analysis/receipt.json)와 [figure manifest](evidence/weak_strong_balance_20261030/figures/figure_manifest.json)에 있다.
