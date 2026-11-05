# CP02 B1 실패 집중 진단 재현

이 묶음은 기존 예보·history 자료를 재분석한 사후 진단이다. **새 예보나 후보를 만들지 않으며, 고정 26개 채택 조건과 현재 B1 유지 결정을 바꾸지 않는다.** 임계값 전이, 표본별 이력, 계층 변수 차이는 기술 통계이며 인과나 물리적 동등성을 뜻하지 않는다.

## 고정 범위와 완료 산출물

- 분석 계획: `analysis_plan.json`, SHA-256 `bc33612e6d719791034d72a7de3e4ddfa09b81d66a9c1b73a8a7fffe668eb0d2` (`FROZEN_DIAGNOSTIC_SCOPE`).
- 상태 추출 계획: `state/extraction_plan.json`, SHA-256 `c3961eee66da7e1979d47baad64df15e75701ea586462b6b4a634c184d798c27` (`FROZEN_BEFORE_STATE_EXTRACTION`).
- 표적 결과: `targets/bundle_receipt.json`, SHA-256 `3ea1a834f61fa7a88c8f199c5ef8710298c489abc83c3c11965241d5dd7a420f` (`COMPLETE`).
- 상태 결과: `state/extracted/receipt.json`, SHA-256 `39f1cede1e47b173491a47e5f4f0182ef7f682be834fbea0f0e1ab37889e23ba` (`PASS`), 4개 사례 × UTC 12–18시 × 270개 점.
- 문맥 결과: `context/bundle_receipt.json`, SHA-256 `a63d4b0d43f94b7456a9ebd8dde68b1616aec521f28bab04e73ee8d48c3e014e` (`COMPLETE`), CSV 5개.
- 그림 결과: `figures/package_receipt.json`; PNG 5장과 `figures/offline_gallery.zip` 포함.
- 독립 재계산: `review/independent_context_review.json`은 문맥 산출물 5개 표의 행·통계와 각 입력/출력 해시를 재계산해 일치 확인.

`context/cohort_surface_context.csv`에서 `transition`과 `observed_band`는 matched-control 행에도 해당 target event의 분류 설명으로 반복 기록된다. `population`은 target/control 구분이며 `flat_index_yx`는 현재 행의 점, `target_flat_index_yx`는 짝을 이루는 target 점이다. 따라서 control 행의 반복 분류값을 control 자체의 전이로 해석하지 않는다. control의 수치량은 해당 control 지점에서 계산한 값이다.

## 재현 명령

명령은 Cloud-BAL 저장소 루트에서 실행한다. 각 `--output` 경로는 **아직 없어야** 하며, 기존 결과를 덮어쓰지 않는다.

```bash
# 1. 고정 그룹 예보 배열로 cohort/표적 테이블 재생성
python tools/cp02_b1_failure_targets.py \
  --source docs/evidence/cp02_grouped_forecast_20261105/analysis \
  --output /tmp/cp02_failure_targets

# 2. 상태 특성 추출: frozen plan에 고정된 28개 기존 history가 모두 필요
python tools/cp02_b1_failure_state.py \
  --plan docs/evidence/cp02_failure_focus_20261105/state/extraction_plan.json \
  --output /tmp/cp02_failure_state

# 3. 저장된 상태 NPZ, 표적 CSV, score NPZ만으로 문맥 표 재생성
python tools/cp02_b1_failure_context.py \
  --output /tmp/cp02_failure_context

# 4. 저장된 paired score/state/context 데이터로 그림과 오프라인 ZIP 재생성
python tools/plot_cp02_b1_failure_focus.py \
  --output /tmp/cp02_failure_figures

# 최종 clean export의 문맥 CSV와 그림 PNG/ZIP 목록을 byte 단위로 재검증
python docs/evidence/cp02_failure_focus_20261105/validation/reproduce.py \
  --root /path/to/final-clean-export
```

2번 상태 추출은 입력 history를 다시 읽으므로, 고정 계획에 기록된 모든 history 파일을 해당 SHA-256 그대로 사용할 수 있을 때에만 실행한다. **이동 가능한 문맥 표와 그림 재현에는 외부 history를 열지 않는다.** 3·4번은 고정 계획에 따라 저장된 compact NPZ/CSV, paired score 배열 및 번들에 포함된 고정 coastline 자료만 읽는다. 4번 그림 생성은 고정된 Nanum 글꼴 파일을 사용하며 해당 파일이 없거나 해시가 다르면 중단한다.

재현 검증기는 `context/`의 CSV 5개와 그림 PNG 5개의 바이트가 같은지, 오프라인 ZIP의 멤버 목록이 같은지 확인한다. 절대 경로가 포함될 수 있는 그림 `metadata.json`은 경로 차이 때문에 바이트 비교 대상에서 제외한다. 검증기는 임시 디렉터리에만 결과를 쓰고 export 안의 파일은 변경하지 않는다.
