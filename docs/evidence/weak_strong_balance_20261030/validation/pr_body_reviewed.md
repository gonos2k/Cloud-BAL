강한 강수 CSI의 이득이 낮은 임계값·후반 예측시간의 손실을 가리는지 확인하기 위해, 초기 QSNOW의 공간 배치와 총량을 분리한 8개 신규 6시간 진단 실험을 수행했습니다. **8개 모두 완주했지만 사전 공동 조건을 만족한 새 설정은 없어 개선안으로 채택하지 않습니다.**

#141의 후속입니다. 동일 초기시각(2026-08-16 12 UTC), RN1 평가점 3,688개, +1~+6시간의 한 시간 강수량, 임계값 0.1·0.5·1·2.5·5·10 mm를 유지했습니다. 예측시간·임계값·실험을 평균하지 않았습니다.

- 공간 게이트 3개와 초기 건조질량 가중 QSNOW 총량 대응 균일 대조 3개를 비교합니다. 게이트는 초기장만 사용하며 저값 기둥의 눈을 감소시키지 않습니다.
- 실행파일/입력 교차 2개를 추가해 기존 ORIGINAL·B1과 2×2 대조를 완성합니다. 점수 대비를 단일 물리 과정의 인과 기여로 해석하지 않습니다.
- 채택에는 낮은 임계값 CSI 18개(+1~+6 h × 0.1/0.5/1 mm)가 모두 ORIGINAL 이상이고, +1 h CSI@10 mm가 엄격히 높아야 합니다. 기준은 새 예보 출력 전에 동결했습니다.

| 진단 비교 | +1 h CSI ≥10 mm | 낮은 임계값 보호조건 미달 /18 | 판단 |
| --- | ---: | ---: | --- |
| 규준실험 1.0 · ORIGINAL | 0.049296 | — | 공통 비교 기준 |
| 기존 CONTROL α=3 | 0.127389 | 별도 기존 맥락 | 새 후보 아님 |
| GATE_G50_90 | 0.129032 | 9 | 새 강한 CSI 진단 상위, 미채택 |
| EQ_G50_90 | 0.111842 | 5 | 미채택 |

낮은 임계값 CSI에는 강한 관측 강수의 적중도 포함됩니다. 관측 강도별 전이를 따로 계산했으며, 낮은 임계값 CSI의 저하를 약한 강수 강도만의 악화로 일반화하지 않습니다. 후속 소스 조사에서는 양의 비 질량과 0인 입자수 상태, 0 과정률 제한 수정의 관계를 확인했습니다. 임의의 입자수 하한을 도입하기 전에 초기화 작성 경로와 입도분포 규약을 연결하는 것이 다음 물리 개선 목표입니다.

- [학회논문 형식 보고서](https://github.com/gonos2k/Cloud-BAL/blob/research/weak-strong-balance/docs/WEAK_STRONG_BALANCE_REPORT_20261030.md)
- [모든 실험·예측시간·임계값 점수표](https://github.com/gonos2k/Cloud-BAL/blob/research/weak-strong-balance/docs/WEAK_STRONG_BALANCE_FULL_SCORES_20261030.md)
- [그림 38개 전체 갤러리](https://github.com/gonos2k/Cloud-BAL/blob/research/weak-strong-balance/docs/WEAK_STRONG_BALANCE_FIGURES_20261030.md)
- [단계별 진행 현황](https://github.com/gonos2k/Cloud-BAL/blob/research/weak-strong-balance/docs/WEAK_STRONG_BALANCE_PROGRESS_20261030.md)

![임계값 0.1 mm CSI 차이](https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_delta_0.1mm.png&output=png)

![임계값 10 mm CSI](https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fcsi_absolute_10mm.png&output=png)

![공간 게이트와 초기 눈 총량 대응 대조 비교](https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fgate_minus_equal_mass_csi_10mm.png&output=png)

![시간별 RN1·게이트 실험·규준 대비 강수 차이](https://images.weserv.nl/?url=raw.githubusercontent.com%2Fgonos2k%2FCloud-BAL%2Fbd645348fd444a0721134f97e3043515231fc914%2Fdocs%2Fevidence%2Fweak_strong_balance_20261030%2Ffigures%2Fmaps_gate_g50_90.png&output=png)

검증: 관련 소스와 동결 규약을 별도 Git 내보내기에서 실행해 147개 시험 통과. 최종 분석 29개 파일의 독립 재계산·바이트 재현, 그림 38개 재현, 브라우저 이미지 38/38 로드, 이전 증거 201개 대조, 오프라인 ZIP CRC/해시 검사를 통과했습니다. 첫 내보내기에서 발견된 경로 의존성을 보완했으며, 수정 전 실패와 최종 재현 기록을 함께 보존합니다.

오프라인 그림 묶음 절대 경로:
`/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_figures_20261030/all_experiments.zip`

단일 사례의 탐색 실험이며 독립 사례 성능이나 운영 적용을 승인하지 않습니다. QSNOW는 대기 중 눈 혼합비이고 점수는 지상 총강수에 대한 것입니다. 초기 눈 총량 대응은 전체 물·에너지 수지 보존을 의미하지 않습니다. RN1 시각·coverage와 전체 과정 수지, 별도 C2 실행 완료는 미완료 범위로 유지합니다.
