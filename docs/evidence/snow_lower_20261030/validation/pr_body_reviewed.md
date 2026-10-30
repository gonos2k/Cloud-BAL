초기 QSNOW 0.6·0.7·0.8·0.9배를 규준·개선 계열에 각각 적용한 8개 예보를 6시간까지 완료했습니다. 실행 조건과 14개 출력 해시가 일치하는 기존 0.5배 두 실험을 포함해, 모든 비교 기준을 규준실험 1.0배(ORIGINAL)로 통일합니다.

## 결과와 그림

- [요청 배율과 전체 실험 그림](https://github.com/gonos2k/Cloud-BAL/blob/research/snow-lower-sensitivity/docs/SNOW_LOWER_FIGURES_20261030.md): 87 PNG, 임계값별 CSI/ΔCSI 및 39개 실험의 시간별 강수 지도.
- [개선 계열 그림](https://github.com/gonos2k/Cloud-BAL/blob/research/snow-lower-sensitivity/docs/SNOW_LOWER_IMPROVED_FIGURES_20261030.md): 31 PNG.
- [전체 점수표](https://github.com/gonos2k/Cloud-BAL/blob/research/snow-lower-sensitivity/docs/SNOW_LOWER_FULL_SCORES_20261030.md): 42개 표, 1,404개 범주형 행과 234개 연속형 행.
- [실험·수학적 정의·해석 보고서](https://github.com/gonos2k/Cloud-BAL/blob/research/snow-lower-sensitivity/docs/SNOW_LOWER_SENSITIVITY_20261030.md)

가로축의 계열 문구는 배율 또는 C/I 배율 키로 줄였습니다. 각 강수 지도는 RN1·실험·실험−규준 1.0배를 세 열로 표시합니다. 강수 차이는 같은 예측시간·같은 3,688개 평가점에서 계산하며, 관측 오차와 구분합니다. 모든 차이 지도는 0 중심 공통 ±42.8 mm 범위로 표시하고 실제 극값을 포함합니다. 양의 강수 차이는 더 많은 강수를 뜻하며 스코어 개선 자체를 뜻하지 않습니다.

요청한 다섯 배율 중 +1시간 ≥10 mm CSI가 가장 높은 것은 개선 계열 0.8배로, 규준 1.0배의 0.0493에서 0.0643으로 높아졌습니다. 다만 +4시간에는 악화가 있습니다. 전체 38개 선정 후보의 기존 단일 1위는 규준 계열 3.0배(CSI@10=0.1274)로 유지됐습니다. 시간·임계값·실험을 평균하거나 여러 실험을 섞어 선정하지 않습니다.

## 오프라인 그림 묶음

압축을 모두 푼 뒤 `index.html`을 열면 인터넷 없이 그림을 볼 수 있습니다. 공유 작업공간의 절대경로입니다.

```text
/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/snow_lower_figures_20261030/requested_lower_factors.zip
/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/snow_lower_figures_20261030/all_experiments.zip
/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/snow_lower_figures_20261030/improved_experiments.zip
```

각각 23·87·31개 PNG를 포함하며 CRC와 그림 해시를 독립 검증했습니다. 웹 그림은 고정된 자산 커밋 `1dd452b84b44797d29f547d7f94660a2092d9192`를 별도 이미지 host에서 불러옵니다.

## 검증과 범위

8/8 예보 정상 종료, 56개 신규 시간별 출력의 시각·유한값·해시·입력 보존을 확인했습니다. 집중 회귀시험 125개 통과, 독립 스코어 재계산 오차 0, 분석 18개 파일과 그림 87개의 바이트 재현을 확인했습니다. 브라우저에서 전체 87개·개선 계열 31개 로딩을 확인했습니다. 팀 검토와 범위를 제한한 Graphify/KG 갱신 결과를 최종 증거 목록에 연결합니다.

초기 눈 혼합비만 배율 조정한 동일 사례의 진단입니다. 개선 계열은 실행파일과 부모 초기장도 규준 계열과 다르므로 계열 간 차이를 QSNOW 하나의 인과효과로 해석하지 않습니다. 독립 사례의 성능이나 물·에너지 수지 보존 검증을 주장하지 않습니다.

## ≥10 mm · 요청 배율의 CSI 차이

![α=0.5, 0.6, 0.7, 0.8, 0.9와 규준 실험 α=1.0 · ≥10 mm ΔCSI](https://images.weserv.nl/?url=https%3A%2F%2Fraw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2F1dd452b84b44797d29f547d7f94660a2092d9192%2Fdocs%2Fevidence%2Fsnow_lower_20261030%2Ffigures%2Ffocused%2Flow_factor_delta_csi_t10.png&output=png)
