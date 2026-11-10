# MP10 NN_END 평가

후보는 동결한 26개 조건 중 21개를 충족했다. B1 보호 조건은 9/11, 규준실험 대비 회복 조건은 12/15다. 따라서 B1을 유지한다. 후보를 채택하려면 모든 조건 충족 외에도 별도 사례와 영역 물·에너지 예산 검증이 필요하다.

[전체 점수](FULL_SCORES.md)는 여섯 실험의 216개 시간·임계값 범주형 점수와 36개 연속형 점수를 포함한다. [고정 조건별 결과](results/admission_constraints.csv)는 CSI를 적중 수와 분모의 정확한 정수 비율로 비교한다. [약한 관측 구간](results/weak_bands.csv)은 검출, 같은 구간, MAE 및 RMSE를 포함하며 [허위경보 생성·해소](results/false_alarm_transitions.csv)는 B1 및 MP10 각각과 비교한다. 관측과 예보에 각각 같은 임계값을 적용한다.

[평가 정책](../forecast/policy.json), [사전 평가 동결](freeze.json), [독립 사전 검토](preflight_review.json), [결과 출처](results/receipt.json)가 데이터와 스크립트를 연결한다. 후보 판정 전에 기존 점수 180개와 연속형 점수 30개가 이전 결과와 같음을 확인했다. 여섯 시간의 RN1 3,688개 고정 쌍을 사용하고, 후보 예보장을 RN1 점에 쌍선형 대응시켰다. 표와 그림은 동일한 쌍을 사용하며 그림 생성에 추가 공간 보간을 하지 않았다.

[시간별 절대 강수와 CSI 그림](figures/) 및 [임계값별 CSI·B1 차이와 시간별 규준실험 차이 그림](supplementary_figures/)의 출처와 해시는 각 디렉터리의 receipt.json에 있다. 차이 지도는 모든 시간과 실험에 공통 색상 범위를 사용하므로 작은 차이는 희미할 수 있다.

첫 평가 실행은 후보 디렉터리를 상대 경로로 지정해 최종 경로 동일성 검사에서 중단되었으며 결과를 게시하지 않았다. 동결된 코드를 바꾸지 않고 후보 경로를 절대 경로로 지정한 재실행은 성공했다. 재실행은 `evaluate.py --candidate <absolute-candidate-directory> --proof <comparability.json> --freeze <freeze.json> --output <new-directory>`를 사용한다. 원시 후보 파일과 환경은 별도 forecast proof에 연결되어 있어 이 저장소 단독 재현은 해당 원본과 Intel 환경을 필요로 한다.
