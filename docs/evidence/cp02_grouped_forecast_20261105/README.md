# PH 차분별 합산의 실제 6시간 예보 검증

**현재 B1 유지. C 10/26·D 11/26으로 모두 미채택이며 새 회복 조건은 0개다.** 초기 시각은 2026-08-16 12 UTC, 종료는 18 UTC다. 시간별 강수는 각 한 시간 구간량이다.

- [논문 형식 보고서](../../CP02_GROUPED_FORECAST_20261105.md)
- [임계값별 CSI·시간별 지도 전체 13장](FIGURES.md)
- [모든 실험의 시간·임계값별 점수](figures/rendered/full_score_tables.md)
- [오프라인 그림 ZIP](figures/rendered/figures.zip)
- [고정 평가 계획](evaluation_plan.json), [52개 판정 조건](analysis/gate_results.csv), [선정 결과](analysis/winner.json)
- [실행 기록](runtime/package_receipt.json), [14개 대조 history 재현](runtime/comparability.json)
- [독립 점수 재계산](review/score_recount/recount_receipt.json)
- [네이티브 빌드·실제 명령 캡처와 원시 기록](native/proof_bundle_20261105/README.md)

## 실험축과 용어

ORIGINAL은 **규준실험**이며 2×2 설계 밖의 고정 기준이다. A는 **현재 B1**, B는 기존 미채택 DM065, C는 B1+차분별 합산, D는 DM065+차분별 합산이다. 네 실험 모두 KDM6 FIX를 유지한다. 합산식 단독 대조는 C-A와 D-B이며, D-A는 결합 후보를 현재 B1과 비교하는 값이다.

## 재현 범위

완전한 원시 예보 재계산에는 실행 receipt가 지정한 외부 WRF ELF·라이브러리·NetCDF와 RN1 자료가 필요하다. 이 대용량 원본을 Git에 포함했다고 주장하지 않는다. 파일 경로·크기·SHA-256과 실행·빌드 로그를 보존하며, 여섯 시간의 3,688점 평가 배열과 모든 점수표는 저장소에 포함한다.

그림은 저장된 분석 배열과 로컬 분석기·평가 계획의 해시를 검사하고, H/M/F·CSI·연속형 점수·전이·채택 조건을 다시 계산한 뒤 생성한다. 외부 원시 history를 그림 단계에서 다시 열지는 않는다. 새 checkout에서 다음 명령의 출력 경로를 **기존에 없는 별도 경로**로 지정하면 된다.

```bash
python tools/plot_cp02_grouped_forecast.py \
  --analysis docs/evidence/cp02_grouped_forecast_20261105/analysis \
  --output /absolute/fresh/path/grouped_figures
```

오프라인 ZIP의 `index.html`은 인터넷 연결 없이 그림을 표시한다. GitHub에서 바로 확인할 때는 [FIGURES.md](FIGURES.md)를 사용한다. 선형 강수량 차이와 비선형 색 눈금의 차이를 캡션에서 구분한다.

## 실패 및 수정 기록

`runtime/attempts/`에는 스택 설정 누락으로 입력 판독 중 종료된 첫 대조 실행을 보존했다. 무제한 스택으로 다시 실행한 네 구성은 모두 6시간을 완료했다. 네이티브 proof bundle은 컴파일 입력 누락과 경로·GDB JSON·검증기 연결 오류의 시도도 구분해 보존한다. `validation/attempts/`는 개발 중 변경된 파일 때문에 기각·취소한 시험 export를 보존한다. 이 시도들을 성공 예보나 최종 검증에 합산하지 않는다. `figures/attempts/`는 글꼴·눈금·대조 표시를 수정하기 전 그림이며, 최종 그림은 `figures/rendered/`에 있다.

단일 기상 사례의 진단이다. RN1 상류 시각·coverage·QC, 독립 사례, 전체 물·에너지 수지, C2 T39와 H/A/N 1시간 적분 완료는 별도 미완료다. KG 갱신은 코드 탐색을 위한 파생 자료이며 예보 성능·보존 검증의 증거가 아니다.
