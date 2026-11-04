# Cloud-BAL

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
