# CP02 B1 상태 경계·비 입자수 후보 검증

최종 결과는 **NO_QUALIFIED_CANDIDATE (12/26)**다. P01의 +2시간 0.1 mm 적중은 회복했지만 FA03의 5 mm 오경보가 재발했다. 현재 B1을 대체하지 않는다.

- [논문 형식 보고서](../../CP02_STATE_PATH_AND_RAIN_NUMBER_20261104.md)
- [전체 시간·임계값별 H/M/F·CSI](candidate/FULL_SCORES.md)
- [그림 22장 — 페이지 안에서 바로 표시](FIGURES.md)
- [예보 전 고정한 26조건](candidate/evaluation_plan.json), [판정](candidate/analysis/winner.json)

초기시각은 2026-08-16 12 UTC(21 KST)다. +2시간은 13–14 UTC의 한 시간 강수이며 2시간 누적량이 아니다. `ORIGINAL`의 표시명은 규준실험, `IMPROVED_BG_FIXED`는 현재 B1, `B1_RAIN_NUMBER_PRIOR`는 미채택 연구 후보다. OLD/FIX 과정 진단은 같은 B1 초기장의 실행파일 차이를 비교한다.

## 검증 범위

| 항목 | 결과·근거 |
|---|---|
| 깨끗한 파일 사본의 관련 Python 시험 | 237 passed, 35개 파일, 54.30초 — [실행 기록](validation/clean_export_v2_pytest.json) |
| 새 시험 등록 | 8개 모듈 portable — [등록 점검](validation/test_tiers.json) |
| OLD/FIX 0·1·2시간 history | 두 구성의 6개 파일 모두 각각의 보관본과 바이트 동일 — [gate](native/capture/history_gate.json) |
| 상태 분석 재생 | 13개 산출물+receipt, 14/14 바이트 동일 — [재생](cli/final_byte_replay.json) |
| 후보 6시간 적분 | 8 ranks, 종료코드 0, 12–18 UTC 7개 history와 89개 입력 해시 검증 — [실행 gate](candidate/runtime_gate.json) |
| 강수 점수 | 108개 범주형·18개 연속형·26개 조건 독립 재계산 일치 — [독립 검산](candidate/review/recount_receipt.json) |
| 점수 분석 재생 | 12/12 파일 바이트 동일 — [재생](candidate/review/score_replay.json) |
| 그림 | 22개 PNG; 새 native 5개·candidate 14개 및 기존 형태 3개 — [그림 모음](FIGURES.md) |
| 과거 증거 | PR143·144의 305개 항목을 현재 파일·보존 원본·당시 graph snapshot으로 대조 — [대조표](validation/prior_manifest_audit.json) |

전체 portable suite, 독립 기상 사례 검증, C2 H/A/N 재적분을 수행한 기록은 아니다. RN1 상류 시간·coverage/QC, 정확한 real 내부 소스 대응 및 전체 물·에너지 수지는 미완료다. 상세 실패·수정 시도는 증거에 보존하고 본문 보고서와 분리했다.

## 저장 자료만으로 상태 분석 재생

저장소 루트에서 새 출력 경로를 지정한다. 기존 출력·dangling symlink는 거부한다. 원래 WRF history나 Intel 설치는 이 Python 분석에 필요하지 않다.

```bash
BUNDLE=docs/evidence/cp02_state_path_20261104
python tools/cp02_state_path.py \
  --old "$BUNDLE/native/capture/OLD" \
  --fix "$BUNDLE/native/capture/FIX" \
  --schema "$BUNDLE/native/capture/state_schema.json" \
  --corners "$BUNDLE/cohorts/point_corners.csv" \
  --expected-ranks "$BUNDLE/native/capture/expected_rank_manifest.json" \
  --observed-ranks "$BUNDLE/native/capture/observed_rank_manifest.json" \
  --archive-manifest "$BUNDLE/native/capture/capture_archive_manifest.json" \
  --output /absolute/fresh/state-analysis
```

`selected_history.npz`는 네 모서리 가중 프로파일이며 raw OLD/FIX는 별도 NPZ에 보존한다. 각 파일은 GitHub의 단일 파일 크기 한도 안에 있다. 순위·시간·연직층을 평균하지 않는다. 호출 사이 차이는 KDM6 이외 모든 연산의 순변화로 정의하며 순수 수송으로 부르지 않는다.

## 점수·첫 호출 검산

증거 사본에서 아래 유틸리티를 실행하면 해당 유틸리티가 작성한 검산 결과를 재생한다.

```bash
python docs/evidence/cp02_state_path_20261104/candidate/review/recount_b1_rain_number.py
python docs/evidence/cp02_state_path_20261104/candidate/replay_first_call_comparison.py
```

앞의 점수 검산은 저장된 여섯 NPZ만 읽으며, 뒤의 첫 호출 비교는 저장된 CBSP 캡처와 같은 바이트의 baseline alias를 읽는다. 최초 real 실행과 6시간 원자료 추출은 외부에 보존한 NetCDF·실행파일·입력 파일이 필요하다. 해당 외부 파일들은 실행 receipt에 해시로 연결했다.

후보의 원래 6시간 history를 다시 보간해 분석하려면 `tools/cp02_rain_number_evaluation.py`에 고정 계획과 `candidate/runtime_evaluation_gate.json`을 전달한다. 후자는 원래 `runtime_gate.json`의 `case_id`와 `history_files`를 평가기 명칭으로 옮긴 무손실 필드 사본이다. 원래 gate의 SHA-256과 변환 규칙을 함께 보존했으며 예보·임계값·점수·선정 조건은 바꾸지 않았다.

[오프라인 그림 묶음 검증](figures/package_receipt.json)은 원래 보고서와 로컬 링크로 변환한 ZIP 안의 사본 해시를 구분한다. HTML 그림 모음과 22개 PNG는 네트워크 없이 볼 수 있다.
