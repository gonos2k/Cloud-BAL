# CP02 후반 강수 실패 유형과 상태 진단

[논문 형식 보고서](../../CP02_FAILURE_REGIMES_20261104.md) · [28개 그림 모음](FIGURES.md) · [108개 시간·임계값·비교 전이 요약](figures/FULLTABLES.md)

## 결과와 범위

이 변경은 **기존 예보의 추가 진단**이다. 새 WRF 적분이나 새 초기화 후보를 만들지 않았다. 초기시각은 2026-08-16 12 UTC이며 모든 강수량은 예측시간별 한 시간 `RAINC+RAINNC` 차이다. 현재 B1을 유지하고 기존 26개 채택 조건도 유지한다.

- 현재 B1과 0.65 mm 후보가 통과한 낮은 임계값 회복 조건은 같은 +5시간 0.5·1 mm다. 현재 B1의 13개 미달 조건에서 새로 회복한 조건은 **0개**다.
- +2시간 실제 약한 강수(0.1≤RN1<1 mm)의 검출은 획득 2·소실 6개, 관측 음성(RN1<0.1 mm)의 오경보는 생성 25·해소 17개다.
- +5시간 5 mm 사건의 적중 순감소 3개는 소실 9·획득 6개로 나뉜다.
- 실패·유지 집단의 초기 습도·온도 분포는 중첩한다. +2시간 신규 오경보 25곳 중 15곳은 평가 네 모서리의 모든 층에서 초기 QNRAIN이 바뀌지 않았지만 이후 정시 비 질량·입자수 차이가 나타났다. 이는 차이의 실제 상류 위치나 수송 경로를 확인한 결과가 아니다.

## 자료 연결

| 경로 | 내용 |
|---|---|
| `transitions/protocol.json` | 출력 전 고정한 입력 배열·점수·선택 조건·관측 강도 구간·전이 규약 |
| `transitions/results/lead_*_point_transitions.csv.gz` | 6개 시간·6개 임계값·3개 B1 대비 비교의 전 지점 398,304행. gzip마다 원시 행을 보존 |
| `transitions/results/transition_counts.csv` | 3,456개 관측 구간·사건 전이 집계 |
| `transitions/results/focus_membership.csv` | 9,471개 상세 진단 집단 행. 서로 다른 집단에 같은 지점이 등장할 수 있음 |
| `transitions/results/recovery_conditions.csv` | 15개 낮은 임계값 조건의 기준·기존·조정 후보 판정과 새 회복 여부 |
| `state/protocol.json`, `state/source_context/` | 24개 외부 NetCDF·좌표·온도·포화 함수·입경·층별 요약 규약과 원문 발췌/해시 |
| `state/results/` | 3개 구성 × 초기 입력과 0–6시간 정시 × 3,688점 × 39층. 24개 분리 NPZ는 각각 6 MB 미만 |
| `state/README.md` | 필드별 단위, 모서리/마스크, 초기 입력과 h00 구분, 진단 정밀도·해석 제한 |
| `science/local_initial_change.csv` | 3,155개 DM065 집단·지점 행. 초기/정시 네 모서리 QRAIN·QNRAIN 최대 절대 차이와 위치 |
| `figures/population_summaries.csv` | 6,320개 집단·시각·변수·층의 유효 n·최소/최대·사분위·중앙값 |
| `validation/`, `kg/` | 원자료 대조·독립 팀 검토·집중 시험·과거 증거와 구조 그래프의 한정된 갱신 |

전체 점수는 [PR146의 144행 H/M/F·CSI 표](../cp02_rain_number_process_20261104/followup/figures/FULLSCORES.md)를 그대로 유지한다. 현재 표의 집단별 중앙값·사분위는 환경의 기술 통계이며 CSI를 평균하거나 후보 순위를 새로 매긴 값이 아니다.

## 저장 자료 재생

저장소 루트에서 실행한다. 출력 경로는 새 경로를 사용한다.

```bash
python tools/cp02_failure_regimes.py --output /tmp/cp02_failure_transition_replay
python tools/plot_cp02_failure_regimes.py \
  --state-results docs/evidence/cp02_failure_regimes_20261104/state/results \
  --output /tmp/cp02_failure_figure_replay
python docs/evidence/cp02_failure_regimes_20261104/validation/audit_pr146.py
```

전이·그림·국지 변경 진단은 저장소의 고정 배열만으로 재계산할 수 있다. 국지 변경 감사 스크립트 `science/recount_local_initial_change.py`는 현재 증거 폴더에 두 파일을 쓰는 고정 경로 감사이며 기존 결과를 덮어쓰지 않는다. 재생은 새 export에서 그 두 산출물만 제외한 상태로 수행한다. 실제 격리 실행·명령·바이트 대조는 `validation/`과 `science/local_initial_change_replay.json`에 보존한다.

24개 NetCDF에서 상태를 다시 추출하려면 보관 호스트의 원래 입력·history 및 `state/protocol.json`에 고정한 소스 경로가 필요하다.

```bash
python tools/cp02_failure_state_features.py \
  --protocol docs/evidence/cp02_failure_regimes_20261104/state/protocol.json \
  --output /tmp/cp02_failure_state_replay
```

이 원본 NetCDF 재추출은 저장 점 자료로 하는 재생과 구분한다. WRF·Intel 실행파일을 새로 빌드하거나 적분하는 명령이 아니다. 프로토콜은 특정 보관 실험의 정확한 SHA-256과 경로를 요구한다.

## 해석과 보존

`T`의 건조 온위 진단 출력과 `THM`을 구분하며 액체 물 기준 상대습도를 float64 함수로 복원한 뒤 float32 프로파일로 저장한다. 실행 중 내부 REAL32 과정을 비트 단위로 재생한 RH가 아니다. 입경은 QRAIN·QNRAIN이 모두 양수인 모멘트 비의 진단이며 필수 모서리에서 미정의이면 NaN과 유효 마스크를 보존한다. 미래 관측으로 정의한 집단은 초기화 규칙의 입력으로 사용하지 않는다.

0–1/1–3 km AGL 요약은 모서리별 해당 모형층의 산술평균이며 질량·두께 가중 적분이 아니다. 정시 자료는 고정 위치 단면으로, 첫 상태 차이 시각·입자 궤적·순수 수송이나 인과 기여율을 뜻하지 않는다. 국지 초기 NR 변화 유무는 평가 네 모서리의 양의 가중치만 사용하며 영역 전체의 초기 변화 유무가 아니다.

PR146의 원래 456개 manifest 자료와 최종 manifest·검토 기록 2개를 대조한다. 변경한 첫 화면·연구 상태의 원본은 `prior_versions/pr146/`, 당시 graph trio는 기존 날짜별 스냅숏에 보존한다. 기존 물리 코드·점수·보고서·원시 과정 캡처는 바꾸지 않는다. 용어 보정 전 그림 소스/metadata와 초반 검증 실행도 별도 이력으로 구분한다.

전체 물·에너지 수지, 실제 강수 공급·수송 경로, RN1 상류 시각·coverage/QC, 독립 사례, real 내부 작성 소스 대응, 별도 C2 T39와 H/A/N 1시간 완료는 계속 미완료다. 그래프 최신성을 이 항목들의 검증으로 사용하지 않는다.
