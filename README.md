# Cloud-BAL

**2026-11-11 모멘트 초기화 검토 보완:** [학술 보고서](docs/MOMENT_FEASIBILITY_20261111.md), [그림·자료](docs/evidence/moment_feasibility_20261111/FIGURES.md). 파일 `T`의 중복 습윤온위 보정을 제거하고, 후보 부적합과 고정 질량의 해석적 허용구간 공집합을 구분했다. 실제 B1의 NI 공집합은 1,362개이며, 닫힌 증발·선택한 융해의 모멘트 교환과 실제 rain slope 기본값 분기를 국지 시험으로 연결했다. **새 예보 없이 현재 B1 유지**이며 첫 모형 사용은 미완료다.

**2026-11-10 물·열 상태와 미세물리 모멘트 초기화:** [학술 보고서](docs/PHYSICAL_MOMENT_INITIALIZATION_20261110.md), [최종 모형 입력 계약](docs/MODEL_MOMENT_HANDOFF.md), [그림·자료 모음](docs/evidence/physical_moment_handoff_20261110/FIGURES.md). 공통 상태에 NC·NI·NR·NN·BG와 출처를 결합하고, 같은 Fortran 연산으로 최종 파일의 모멘트를 완성하는 경로를 구현했다. 여섯 합성 물리 상태의 O0/O2 조합 시험과 파일 생성·복사·롤백 경계 11개 검증이 통과했다. 실제 B1 입력은 새 real.exe로 재현했으나 고정 빙정 사전값이 NI 상한을 넘어 **초기화가 거부됐고 새 예보는 실행하지 않았다. 현재 B1 유지**이며, 첫 모형 사용·독립 기상 사건 검증은 미완료다. 아래는 작성 시점별 기록이다.

**2026-11-10 활성화·NN 복원 시점과 실제 약한 강수 대조:** [학술 보고서](docs/CP02_ACTIVATION_PATH_20261110.md), [시간·임계값별 전체 점수](docs/evidence/cp02_activation_path_20261110/evaluation/FULL_SCORES.md), [그림 모음·ZIP](docs/evidence/cp02_activation_path_20261110/FIGURES.md). 실제 약한 강수 소실·유지 12000–12002의 3시간 계측은 기존 history 8개와 바이트 동일하다. 고정 입력 재생과 실제 둘째 반복을 구분하고, NN 하한을 마지막 내부 반복에만 적용한 단일 6시간 후보를 시험했다. 후보는 **보호 9/11·회복 12/15, 합계 21/26으로 미채택·현재 B1 유지**다. 12002의 적중은 회복하지 못했고 +6시간 실제 약한 강수 검출 증가와 무강수 오경보 증가가 함께 나타났다. 관련 시험 **545개**가 통과했다. 전체 수지·독립 사례·RN1 QC·C2 T39는 별도 미완료다. 아래는 작성 시점별 기록이다.

**2026-11-10 MP10 실제 내부 반복·오경보 대응 진단:** [학술 보고서](docs/CP02_MP10_PROCESS_20261110.md), [그림 7장·전체 수치](docs/evidence/cp02_mp10_process_20261110/FIGURES.md). PR154와 MP10을 각각 6시간 진단 재적분했고 정시 history 14개가 기존 결과와 바이트 동일하다. 30점·111기둥·39층에서 내부 이월과 총 7,012,980쌍의 주 수증기·기온 갱신을 재현하고, 전 1,080단계 실제 강수 누적을 검사했다. 대표점의 직접 미량 제거량 차이는 지상 강수 차이보다 작으며 수농도 조정·진입 상태·호출 사이 변화를 구분한다. **새 후보·성능 개선 없이 MP10 22/26·미채택, 현재 B1 유지**다. 관련 시험 529개가 통과했으며 전체 수지·독립 사례·RN1 QC·C2 T39는 별도 미완료다. 아래는 작성 시점별 기록이다.


**2026-11-10 강수 급증 경로와 내부 시간분할 6시간 실험:** [학술 보고서](docs/CP02_PULSE_PATH_AND_SUBSTEPS_20261110.md), [시간·임계값별 전체 점수](docs/evidence/cp02_pulse_path_20261110/evaluation/results/FULL_SCORES.md), [그림·ZIP](docs/evidence/cp02_pulse_path_20261110/FIGURES.md). 기존 20초 기록에서 19145·19144·17804의 실제 침강 경계량과 국지 싸락눈 성장 항을 연결했다. 보존식·빙정 단위·물리 계수를 유지하고 내부 시간분할만 바꾼 MP10과 대조를 각각 6시간 적분했다. CONTROL history 7개와 후보 초기 history는 기존 PR154와 바이트 동일하다. MP10은 **보호 9/11·회복 13/15, 합계 22/26으로 미채택·현재 B1 유지**다. +6시간 0.1·0.5 mm를 새로 회복했지만 +3시간 0.1 mm 회복을 잃었고 강한 강수 보호는 미달했다. 실제 내부 루프 직접 관측·별도 전체 KDM6 이월 시험·전체 수지·독립 사례·C2 T39는 미완료다. 아래는 작성 시점별 기록이다.


**2026-11-10 낮은 임계값 실패의 대응 과정 진단:** [학술 보고서](docs/CP02_LOW_THRESHOLD_PROCESS_20261110.md), [그림 27장·ZIP](docs/evidence/cp02_low_threshold_process_20261110/FIGURES.md). 기존 5 mm 집단 밖의 낮은 임계값 실패와 해소·약한 강도 유지 대조를 포함한 21곳·77개 WRF 기둥을 선정했다. B1·PR153·PR154를 실제 6시간 재적분했으며 정시 history 21개는 기존 예보와 바이트 동일하다. 0–1·4–6시간의 상태·과정과 0–6시간 지상 누적을 연결하고 관측된 기둥 잔차와 재구성한 제한 차이를 구분한다. **새 물리 후보·새 성능 개선 없이 PR154 21/26·미채택·현재 B1 유지**다. 전체 수지·독립 사례·C2 T39는 별도 미완료다. 아래는 작성 시점별 기록이다.


**2026-11-09 PR154 후속 오경보 진단:** [학술 보고서](docs/CP02_ICE_FALSE_ALARM_20261109.md), [새 진단 4장·기존 예보 12장과 ZIP](docs/evidence/cp02_ice_false_alarm_20261109/FIGURES.md)을 추가했습니다. 저장 history 28개에서 RAINC·RAINNC를 분리해 88,512개 시간·지점별 총강수를 기존 평가와 정확히 대조했습니다. +6시간 잔존 65곳·신규 26곳·해소 37곳과 +1시간 신규 10 mm 오경보 3곳을 함께 비교합니다. 강수 성분의 변화와 물리적 원인을 구분하며 **새 예보·새 후보 없이 PR154 21/26·미채택·현재 B1 유지**입니다. 아래는 작성 시점별 기록입니다.

**2026-11-09 첫 빙정 속도 단위 수정의 실제 6시간 평가:** [학술 보고서](docs/CP02_FIRST_ICE_VELOCITY_20261109.md), [모든 시간·임계값별 H/M/F·CSI](docs/evidence/cp02_first_ice_velocity_20261109/evaluation/results/FULL_SCORES.md), [그림 12장·ZIP](docs/evidence/cp02_first_ice_velocity_20261109/FIGURES.md). 공유 경계 보존식을 유지하고 첫 빙정 진입의 두 `/delz` 변환을 복원했습니다. 현재 B1 보호 **9/11**, 규준실험 수준 회복 **12/15(새 회복 10개)**, 합계 **21/26**으로 직전 19/26보다 진전했으나 **후보 미채택·현재 B1 유지**입니다. +4시간 5 mm 보호와 +3시간 낮은 세 임계값을 회복했지만 +1시간 10 mm와 +6시간 조건은 미달했습니다. CONTROL의 정시 history 7개는 PR153 보존 후보와 바이트 동일합니다. C2 T39·전체 수지·독립 사례 검증은 별도 미완료입니다. 아래는 작성 시점별 연구 기록입니다.

**2026-11-09 침강 보존 후보의 실제 6시간 평가:** [학술 보고서](docs/CP02_SEDIMENTATION_CONSERVATION_20261109.md), [시간·임계값별 전체 점수](docs/evidence/cp02_sedimentation_conservation_20261109/evaluation/results/FULL_SCORES.md), [그림 13장·ZIP](docs/evidence/cp02_sedimentation_conservation_20261109/FIGURES.md). 기존 침강의 유입 재제한을 전체 포착 원시 기록에서 확인하고 공유 경계 이동량 후보를 Intel 시험·실제 예보로 평가했습니다. 낮은 임계값 회복 **10/15(새 회복 8개)**, B1 보호 **9/11**, 합계 **19/26**입니다. +4·+6시간 5 mm 보호 실패로 **후보 미채택·현재 B1 유지**이며, 수치 보존과 예측성능을 구분합니다. CONTROL의 정시 history 7개는 현재 B1과 바이트 동일합니다. 아래는 작성 시점별 연구 기록입니다.

**2026-11-06 동일 B1 OLD/FIX 5시간 과정 진단:** [학술 형식 보고서](docs/CP02_PROTECTED_PROCESS_20261106.md), [그림 4장·ZIP](docs/evidence/cp02_protected_process_20261106/FIGURES.md), [모든 예보시간·임계값별 H/M/F·CSI](docs/evidence/cp02_protected_process_20261106/tables/FULL_SCORES.md). 실제 재적분의 정시 history 12개가 각 표준 예보와 바이트 단위로 같았습니다. +2시간 실패와 +5시간 보호 집단 150점을 같은 호출 경계로 비교했고, 강수 검증 요약의 잔차 집계 오류를 수정했습니다. **과정 진단의 추가이며 새 성능 개선·후보 채택은 없습니다. 현재 B1 유지, C·D 미채택**입니다. 별도 C2 T39/H/A/N 1시간과 전체 물·에너지 수지, 독립 사례 검증은 미완료입니다. 아래는 시점별 연구 기록입니다.

**2026-11-05 B1 실패 집단 공동 진단:** [학술 형식 보고서](docs/CP02_B1_FAILURE_FOCUS_20261105.md)와 [그림 5장 모음·ZIP](docs/evidence/cp02_failure_focus_20261105/figures/gallery.md)을 추가했습니다. 실제 history 28개에서 270개 초점·대조 지점을 연결했습니다. +2시간 소실 10곳 중 같은 B1 초기장의 기존 KDM6에서는 9곳이 적중하나, 신규 오경보 53곳 중 32곳도 실행파일 변경과 함께 문턱을 넘습니다. +5시간 C의 신규 5 mm 오경보 12곳을 포함해 시간·공간·선행 상태를 대조했습니다. **새 예보·후보 채택은 없으며 현재 B1 유지**입니다. 기존 26개 조건과 별도 C2 미완료 상태는 그대로입니다.

**2026-11-05 합산식 변경 6시간 전방 실험:** [논문 형식 보고서](docs/CP02_GROUPED_FORECAST_20261105.md), [전체 시간·임계값별 점수](docs/evidence/cp02_grouped_forecast_20261105/figures/rendered/full_score_tables.md), [그림 13장](docs/evidence/cp02_grouped_forecast_20261105/FIGURES.md). 기존 합산식의 B1·DM065 재빌드 대조는 history 14개가 과거 예보와 바이트 동일했고, 차분별 합산을 적용한 C·D도 6시간을 완료했습니다. 고정 26개 조건은 **C 10/26, D 11/26, 새 회복 0개**로 모두 미채택이며 **현재 B1 유지**입니다. +2시간 일부 저임계값 이득이 있으나 +5시간 5 mm 보호 조건은 통과하지 못했습니다. 아래는 각 작성 시점의 기록입니다.

**2026-11-05 초기 QNRAIN–첫 KDM6 NR 경계 추적:** [학술 형식 보고서](docs/CP02_INITIAL_BOUNDARIES_20261105.md)는 실제 호출 코어 2,533,440개에서 두 구성의 초기 QNRAIN 차이 199,111개와 진입 NR 차이 353,417개를 집계하고, 그중 초기값이 같았던 154,317개를 식별합니다. 제한된 20330 셀 재생은 DM065의 NR 생성이 첫 KDM6 전에 질량 결합 RK 이류 경로를 거침을 보이고, 20183 셀은 `calc_p_rho_phi`의 비정수압 설정·hypsometric_opt=2 경로와 `P → PII → TK` 초기 연계를 좁힙니다. 20183의 `phi7` lane 2에서는 두 arm 실제 원래 실행파일 재생으로 순차 REAL32 numerator 연산 순서를 확인했고 독립 raw-review가 이를 검증했습니다. grouped 대안은 오프라인 비교뿐이며 네이티브 실행은 하지 않았습니다. **새 수정·후보·예보 개선은 없고 현재 B1 유지**이며 물·에너지 수지와 독립 성능 검증은 미완료입니다. [관측 경로 그림](docs/evidence/cp02_initial_boundaries_20261105/mechanism_figures/gallery.md), [증거 번들](docs/evidence/cp02_initial_boundaries_20261105/README.md). 아래는 작성 시점별 기록입니다.

**2026-11-05 열역학–구름–강수 2시간 실제 추적:** [논문 형식 보고서](docs/CP02_THERMO_CLOUD_PATH_20261105.md)는 현재 B1과 미채택 DM065를 재적분하여 39점·123개 모서리 격자·39층·360단계의 진입·국지 과정·호출 사이 순변화를 연결합니다. 두 구성의 +0·+1·+2시간 전체 history 6개가 기존 예보와 바이트 단위로 같습니다. 정시 비 0과 이전 시간 전체의 비 부재를 구분하고, 신규·해소 오경보를 함께 비교합니다. **새 후보·새 6시간 성능 개선 없이 현재 B1 유지**이며 전체 수지·독립 사례·C2 T39는 미완료입니다. 아래는 작성 시점별 기록입니다.

**2026-11-04 후반 약한 강수 실패 유형 진단:** [새 보고서](docs/CP02_FAILURE_REGIMES_20261104.md)와 [그림·전이표](docs/evidence/cp02_failure_regimes_20261104/FIGURES.md)는 기존 6시간 예보의 모든 지점 전이와 전 평가점의 초기·시간별 상태를 비교합니다. 0.65 mm 후보가 현재 B1의 미달 조건에서 새로 회복한 조건은 **0개**입니다. +2시간 신규 오경보 25곳 중 15곳은 평가 네 모서리의 초기 QNRAIN 변화가 없어, 국지 초기 상태만으로 설명하기 어려운 전달 경로를 다음 조사 대상으로 좁혔습니다. **새 후보·새 적분 없이 현재 B1 유지**, 전체 수지·독립 사례 및 C2 T39는 미완료입니다. 아래는 작성 시점별 기록입니다.

**2026-11-04 최신 CP02 과정·입경 대조:** [논문 형식 보고서](docs/CP02_RAIN_NUMBER_PROCESS_20261104.md), [시간·임계값별 144행 점수](docs/evidence/cp02_rain_number_process_20261104/followup/figures/FULLSCORES.md), [23개 그림 모음](docs/evidence/cp02_rain_number_process_20261104/FIGURES.md). 현재 B1–기존 입자수 후보의 3시간 과정 진단과 입력 평균입경 0.65 mm 후보의 6시간 예보를 완료했습니다. 조정 후보는 보호 8/11·회복 2/15, 합계 **10/26으로 미채택·현재 B1 유지**입니다. 후반 낮은 임계값 회복은 미달성이고 C2 T39는 별도 미완료입니다. 아래 기록은 각 작성 시점의 결과입니다.

**2026-11-04 CP02 비 입자수 검증:** [학회논문 형식 보고서](docs/CP02_STATE_PATH_AND_RAIN_NUMBER_20261104.md)와 [전체 시간·임계값별 점수](docs/evidence/cp02_state_path_20261104/candidate/FULL_SCORES.md), [그림 22장 모음](docs/evidence/cp02_state_path_20261104/FIGURES.md)을 추가했습니다. 동일 B1 상태 차이의 첫 발생 경계를 추적하고 QNRAIN만 바꾼 후보의 6시간 예보를 완료했습니다. P01의 +2시간 적중은 회복했으나 사전 조건 12/26으로 **후보 미채택·현재 B1 유지**입니다. 아래 업데이트는 각 작성 시점의 기록입니다.

**2026-11-03 CP02 진단 업데이트:** 동일 B1 초기장의 기존/수정 KDM6를 2시간 재실행해 +0·+1·+2시간 전체 출력의 보관본 일치를 확인했습니다. [과정 진단 보고서](docs/CP02_B1_TWO_HOUR_PROCESS_20261103.md)는 비 증발률·수증기·냉각의 국지 연결을 다룹니다. 새 개선 후보나 강수 성능 개선을 채택한 단계는 아닙니다. 아래 PR143 현황은 당시 기록으로 보존됩니다.

Focused KLAPS baseline for improving cloud-derived vertical motion, balance
coupling, and hydrometeor initialization.

This initial snapshot intentionally contains only the source boundaries needed
to study and change:

- cloud classification and cloud-derived `w`/`omega`;
- optional radar-reflectivity adjustment of cloud vertical motion;
- `lco/COM` coupling into the balance analysis;
- cloud liquid, cloud ice, rain, snow, and precipitating-ice initialization;
- LAPSPREP hot-start conversion and WPS hydrometeor output;
- the relevant namelists and NetCDF schemas.

## Data flow

```text
cloud + reflectivity
        |
        v
get_cloud_deriv --> lco/COM (Pa/s) --> qbal --> balance/lw3
        |
        +----------> lwc/ice/rain/snow/pic --> LAPSPREP --> WPS
```

Positive geometric `w` is an updraft. The legacy conversion writes it as
negative pressure vertical velocity: `omega = -(w * pressure) / 8000`.

## Repository layout

- `src/cloud`: cloud-analysis call boundary and radar status handling.
- `src/deriv`: derived cloud products, thin-cloud insertion, and output.
- `src/lib`: cloud/radar vertical-motion algorithms and precipitation
  concentration support. The legacy mixed radar reader is reduced to its
  reflectivity routines; radial-velocity readers are intentionally omitted.
- `src/balance`: cloud-omega ingestion and balanced-field output.
- `src/lapsprep`: hydrometeor hot-start conversion and WPS output.
- `src/include`: includes directly required by the selected legacy sources.
- `config`: active cloud-derivation and LAPSPREP controls.
- `schema`: `lco`, `lwc`, `lcp`, and `lw3` field contracts.
- `docs`: baseline scope, known defects, and acceptance requirements.

## Deliberate exclusions

The repository includes selected research evidence under `docs/evidence`,
including compressed logs, diagnostic records, fixtures, manifests, and hashes.
It does not bundle the complete operational observation/model trees, native
executables, object/module files, wiki content, or wind Barnes/OpenMP releases.
`graphify-out` contains the source-and-document structural graph. Raw radar
ingest/remap and the complete KLAPS build system remain external. Historical
evidence and its identities are preserved; this change does not migrate or
remove large artifacts.

The selected files preserve their upstream FSL public-domain notices. This is
a focused source snapshot, not yet a standalone KLAPS build. External KLAPS and
NetCDF dependencies will be isolated behind tests as the implementation is
improved.

See [docs/BASELINE_REVIEW.md](docs/BASELINE_REVIEW.md) before changing the
algorithms.

The staged correction and validation strategy is documented in
[docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md).

The completed source changes, preserved legacy baseline, and verification
commands are summarized in
[docs/IMPLEMENTATION_REPORT.md](docs/IMPLEMENTATION_REPORT.md).

The historical candidate-v1 design for S-band precipitation fall trajectories,
downdraft energetics, compact balance support, divergent/rotational modes, and
wave-control handoff is retained in
[docs/RADAR_PRECIP_DOWNDRAFT_DESIGN.md](docs/RADAR_PRECIP_DOWNDRAFT_DESIGN.md).

The original-source-derived direct QBAL inputs, upstream producer chain,
prepared 2026-08-16 cases, radar extension, and fail-closed ban on final
`bigfile` inputs are defined in
[docs/QBAL_REAL_INPUT_CONTRACT.md](docs/QBAL_REAL_INPUT_CONTRACT.md).  Run
`tests/run_real_input_inventory.sh` to validate the four prepared hourly source
sets; the command intentionally confirms a `BLOCKED` direct closure until the
missing original upstream intermediates have been regenerated.

The current one-page authority and promotion decision is
[docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).  The cloud-regime,
S-band radial-velocity, precipitation-trajectory, local-balance, and wave-noise
basis is summarized with primary literature in
[docs/SCIENTIFIC_BASIS.md](docs/SCIENTIFIC_BASIS.md).

The goal, implemented scope, remaining integration work, and completion of the
separate radial-velocity/Barnes release are summarized in
[docs/STATUS_20260907.md](docs/STATUS_20260907.md).

The in-progress native mass/frame contract and bounded geometry test evidence are in
[docs/NATIVE_MASS_FRAME_CONTRACT.md](docs/NATIVE_MASS_FRAME_CONTRACT.md) and
[docs/CP01_EXECUTION_RECORD_20260907.md](docs/CP01_EXECUTION_RECORD_20260907.md).

The detailed design review and the 45 main requirements plus the separately
completed radial-velocity scope are available in
[docs/CLOUD_BAL_DESIGN_REVIEW_20260907.md](docs/CLOUD_BAL_DESIGN_REVIEW_20260907.md)
and [docs/CLOUD_BAL_CHECKLIST_20260907.md](docs/CLOUD_BAL_CHECKLIST_20260907.md).
Final goals and ten scoped development checkpoints are recorded in
[docs/CLOUD_BAL_FINAL_GOALS_CHECKPOINTS_20260907.md](docs/CLOUD_BAL_FINAL_GOALS_CHECKPOINTS_20260907.md),
with an editable [checkpoint ledger](docs/CLOUD_BAL_CHECKPOINTS_20260907.tsv).
These plans do not grant execution or promotion authority.
CP00 implementation and local evidence are tracked in
[docs/CP00_EXECUTION_RECORD_20260907.md](docs/CP00_EXECUTION_RECORD_20260907.md).
The bounded portable Python CI lane is described in
[docs/CI_CONTRACT.md](docs/CI_CONTRACT.md).
The editable requirement ledger is
[docs/CLOUD_BAL_REQUIREMENTS_20260907.tsv](docs/CLOUD_BAL_REQUIREMENTS_20260907.tsv).

The focused real-data evidence commands are:

```bash
tests/run_real_shadow_cases.sh
tests/run_real_shadow_figures.sh
tests/run_radar_velocity_audit.sh
tests/run_real_manufactured_balance_cases.sh
```

The real runner requires a clean exact-head tree and the pinned Intel ifx 2026
binary.  The figure and velocity-audit wrappers verify and pin that committed
generation before reading it.  The four prepared hours are never filtered by
outcome.  A failed stage returns the input state and is not published as a
candidate; its failure reason remains available in the stage result.

The manufactured-balance runner uses the four actual KLAPS geometries and
Intel ifx to exercise a nonzero solver path.  Its target and pressure-velocity
boundary are explicitly test-only, and every artifact states science authority
`NONE`.  See [docs/REAL_GEOMETRY_DYNAMIC_BALANCE.md](docs/REAL_GEOMETRY_DYNAMIC_BALANCE.md).


## Current research status — 2026-11-03

| Track | Comparison basis and current evidence | Status |
| --- | --- | --- |
| C2 stability | Same C2 experiment's OFF/HYDRO/COUPLED/PROJECTED/STRUCTURED/AMPLITUDE configurations completed 640 seconds. H/A/N one-hour runs stopped at 760 seconds / 38 steps at T39. The first group rejection `(199,52,21)` differs from fatal consumer `(2,219,13)`; [replay evidence](docs/evidence/recount_contract_20261103/c2/first_group_replay.json) records the sentinel path, while its source stencil remains uncaptured. | 14 UTC forecast and observation scores unevaluated. |
| CP02 B1 precipitation | Across 36 existing lead × threshold CSI cells, 21 improved and 15 worsened. CSI@5 mm improved at all six leads; several low-threshold cells worsened and +4 h RMSE increased. | This six-hour result does not complete the separate C2 one-hour runs. |
| Latest PR142 selection | Eight new six-hour forecasts completed; all 56 hourly histories passed validation. | All eight are `NO_QUALIFIED_CANDIDATE` under the frozen gate: each must meet or exceed ORIGINAL CSI in all 18 cells (six leads × 0.1, 0.5, 1 mm) and strictly improve +1 h CSI@10 mm. No averaging across leads, thresholds, or cases. |

These are separate experiments and selection rules, not sequential operational-best changes. Initial `QSNOW` is atmospheric snow mixing ratio; the verification scores total surface precipitation. As of 2026-11-03, main contains PR137 at `5f6641f2`; research contains PR142 at `83804668`, whose tree equals `5e3bba43`'s tree. PR142 is not yet in main. See the [dated research status](docs/CURRENT_RESEARCH_STATUS.md), [PR142 analysis](docs/WEAK_STRONG_BALANCE_REPORT_20261030.md), [source hash receipt](docs/evidence/recount_contract_20261103/status/source_hashes.json), and the [historical PR84 execution checklist](docs/FAST_COMPLETION_CHECKLIST_20261012.md).

The immediate C2 work is to connect the first grouped rejection to its RK1 source producer; actual 14 UTC observation scores remain unavailable. The `QRAIN`/`QNRAIN` writer, density and particle-size rules, RN1 upstream timing and coverage, independent cases, and full water/energy budgets remain open. The separate CP02 P2 recount fix is complete on this research branch: six focused tests pass; the [validation receipt](docs/evidence/recount_contract_20261103/validation.json) and [malformed-input manifest](docs/evidence/recount_contract_20261103/validator/manifest.json) record the scoped checks. It is not a fix on main, which remains at PR137.

The added CP02 work diagnoses localized vertical motion before time integration,
using the existing radar-informed horizontal analysis and hydrometeors.
The [plan](docs/CP02_MULTI_RADAR_BALANCED_INITIALIZATION_PLAN_20260914.md),
[checkpoints](docs/CP02_MULTI_RADAR_INITIALIZATION_CHECKLIST_20260914.md), and
[scientific review](docs/CP02_MULTI_RADAR_SCIENTIFIC_REVIEW_20260914.md) define observation reuse,
phase-change consistency, startup-wave controls, and 1–6 h precipitation validation.
These documents do not claim implemented or validated coupled initialization.
The archived 12 UTC CP02 OFF/HYDRO/LIQUID experiment has
[hourly precipitation scores through six hours](docs/PRECIP_HOURLY_VERIFICATION_20261027.md)
and a [paired-point transition and RN1 representativeness analysis](docs/CP02_PRECIPITATION_TRANSITIONS_20261027.md).
The first-hour lost-hit region is diagnostic, not a replacement scoring mask;
these older CP02 results do not validate the separate C2 H/A/N forecasts.
The [initial QR/QS trace](docs/CP02_INITIAL_SPECIES_TRACE_20261027.md) follows the archived preprocessing and native states;
[empty-loss handling](docs/PRECIP_EMPTY_LOSS_20261027.md) keeps valid no-loss and all-dry analyses complete.
The [OFF readback guard](docs/WPS_OFF_READBACK_20261028.md) rejects a mismatched actual control before issuing a PASS receipt and records the partial historical source recovery.
The [archived CP02 call-boundary replay](docs/CP02_CALL_BOUNDARY_20261028.md) locates the selected QR/QS changes across `derive_column_physics` with byte-identical WPS/shadow outputs; the first internal operation and forecast causality remain open.
The [CP02 event contract](docs/CP02_EVENT_CONTRACT_20261028.md) rejects incomplete, mispaired, or reordered call records before reporting a successful analysis.
The [conditional proofs](docs/CP02_MULTI_RADAR_MATHEMATICAL_PROOFS_20260914.md)
state the assumptions behind identifiability, conservation, and wave-energy bounds.
The [September 14 corrections](docs/CLOUD_BAL_DESIGN_REVIEW_20260907.md)
clarify covariance weighting, phase policy, development dependencies, and evidence closure.
