# CP06-A input readiness for the remaining CP02 native work

Status: **NOT READY FOR AN ACTUAL COUPLED RUN**. This is an engineering readiness
record, not an experiment approval or a replacement for CP06-A exit criteria.
CP02 E03 still requires both full OFF and an actual coupled candidate through
WPS and the subsequent native conversion.

## Existing processed observations — corrected input scope

Observation data already exist and are already used by the original KLAPS
processing chain. The selected processed products are listed in
`../config/cp06a_observation_inputs_20260816T130000Z.json` (로컬 전용 자료: `../config/cp06a_observation_inputs_20260816T130000Z.json`; 공개 PR에 포함하지 않음).
They include LW3, LT1, LQ3, LWC, LSX, VRZ, VRT, LCP, LTY and LCO from the retained
13 UTC producer tree. No request for a new raw-data directory is required.

The earlier empty canonical fields were not evidence of absent observations:
the reader omitted pressure-level LCP cloud fraction and LTY cloud/precipitation
types. Existing LCP contains fractions 0–1; LTY has cty 0–11 and pty 0–5.
The Fortran reader and derived/LAPSPREP callers now consume the LCP/LTY pair.
Legacy pty 5 denotes hail, not canonical graupel, and is preserved as unknown
with phase uncertainty. The retained historical payload below is unchanged;
new reader runs populate the cloud fields from the existing processed products. Target/sigma construction and propagation remain separate
implementation work, not a demand that upstream files already use Cloud-BAL names.

## Concrete available case

The 2026-08-16 13 UTC case is a useful candidate for defining the experiment:
current maintained O0/O2 producer/OFF chains pass, and the retained raw radar
recovery evidence is also for 13 UTC. Choosing it here does not authorize a
scientific target or run. The historical pre-QBAL O0 canonical state was:

- File: `scratch/cp02_maintained_derived_O0_qej27s72/matched_control_chain13_O0.b07iv296/derived_export/output/payload.nc`
- SHA256: `911189f0e3f52853c7240af53804c63cfe59ec0234a0ac58a2dbf0c42ca47cc1`
- Grid:235×283×22; valid time1786885200.
- `dynamic_target_authorized=0`; valid omega-target cells0; valid sigma cells0.
- Exact inspection: `scratch/cp02_link_input_pins_qj349ens/CP06_A_INPUT_READINESS.json`.

The available LGT and COM evidence is retained separately from dynamic target
and uncertainty. The 2026-09-11 direct comparison confirms that 244,326 valid
LCO COM cells are preserved exactly in cloud_omega_evidence after reversing the
vertical order. Target count zero therefore does not mean cloud omega input is
missing. The core improvement is the empirical cloud omega calculation; existing
multivariate Barnes remains the radial-wind processing path. Target construction
for the improved formulation remains distinct from preserving the legacy COM
baseline. Raw-radar recovery is supporting input evidence, not a replacement
for this physics improvement.

## Experiment specification

The requested specification is now recorded in
[CP06_A_EXPERIMENT_SPEC_20260816T130000Z.md](CP06_A_EXPERIMENT_SPEC_20260816T130000Z.md).
It fixes the case, candidate comparison, allowed-variable/support rules and
research controls. Actual observation target/sigma and their provenance are
still missing; creating the specification does not make this input run-ready.

## Required observation inputs and execution binding

Before actual coupled execution, the specification must bind the following to
one approved case/input identity. No numerical values are inferred here.

| Item | Current evidence | Missing decision or evidence |
|---|---|---|
| Initial state | Exact13 UTC pre-QBAL state above; O0/O2 OFF/reference comparisons | Accepted experiment case and identical initial state for all candidates |
| Dynamic target | Current valid target count0; COM remains separate evidence | Actual nonzero observation-derived target, source hashes, units, clocks, frame/QC and derivation |
| Uncertainty | Current valid sigma count0 | Positive finite sigma, consistent observation provenance and valid mask |
| Allowed update domain | Existing canonical geometry and masks | Allowed variables, thermo/dynamic support and validation shell fixed before execution |
| Acceptance controls | Existing validators and rollback behavior | Explicit target-fit/budget/residual thresholds, iteration caps, tolerances and reference definitions |
| Coupled experiment | OFF transport is verified | Same-state OFF, hydro+thermo and actual dynamic-coupled candidates; bounded outer-loop evidence |
| Native validation | Original WPS comparison is verified | Full OFF and actual coupled WPS→metgrid/real/native variable/mask/frame/mass-basis comparison after CP06-A |

## Implementation boundary

`src/common/cloud_bal_state.f90` validates positive finite sigma and common
observation source bits for target/sigma. `src/common/cloud_bal_pipeline.f90`
rejects manufactured target provenance in the normal pipeline. These checks must
remain intact. An input flag alone is not an approval record.

The current `src/common/cloud_bal_stage_payload.f90` exchange version1 rejects
`dynamic_target_authorized=true`; current stage/OFF publication gates intentionally
verify the cold/unbalanced OFF contract. Therefore an approved actual coupled
candidate also needs an explicit supported exchange/writer/validator extension.
The current OFF matrix cannot be renamed a coupled candidate. Preparing that
extension and small transport tests can proceed independently of an actual
observation experiment, without inventing observational authority.

The approval requirement comes from
`docs/CLOUD_BAL_FINAL_GOALS_CHECKPOINTS_20260907.md`, CP06-A: the case, inputs,
allowed variables/support, observation target authority and thresholds must be
specified and linked to the A receipt before execution. The same section states
that a sequencing GO does not approve unspecified targets or scope. The user requested creation of the specification; the linked v2 now supplies
the experiment design. Its missing observation inputs and implementation
prerequisites remain explicit.

2026-09-11: 기존 처리 LCP/LTY를 포함한 실제 전체 LAPSPREP OFF/HYDRO/LIQUID 실행과
출력 보완 결과는 [실행 기록](CP06_A_PROCESSED_INPUT_RUN_20260911.md)을 따른다.

## Existing Barnes uncertainty setting — 2026-09-11 correction

The active `wind.nl` already sets `WEIGHT_RADAR=0.25`, documented as inverse
radial-velocity error variance: the existing assumed radial error is 2 m/s.
Radial observations are already processed by multivariate Barnes and the
resulting LW3 wind is consumed by Cloud-BAL. The zero sigma count above refers
to the unpopulated canonical **omega-target sigma (Pa/s)**, not an absence of
radial-error settings. See [the settings/source trace](CP06_A_BARNES_SETTINGS_20260911.md).
No new radial retrieval or arbitrary error constant is needed for this setting.

## Empirical cloud omega baseline verified on 2026-09-11

The actual retained producer used Cu=0.5, Sc=0.10, St=0.017 m/s and Ct=1.3,
confirmed by both its launch receipt and Fortran output. These differ from some
source defaults. `deriv.nl` sets `L_BOGUS_RADAR_W=.false.`. The baseline uses
cloud-type/depth/grid-spacing profiles followed by `omega=-w*p/8000`.
[Exact input comparison and source hashes](../scratch/cp02_cloud_omega_baseline_20260911/RESULT.json)
record the existing baseline; they do not certify improved coupled physics.

## Current v3 input after fresh producer/export validation

The experiment now binds the latest O0 export in spec v3. Fresh pinned O0/O2
derived producers and same-executable EXPORT_OFF runs all exited 0. Their 14
producer products match the historical baseline, and all 128 payload variable
arrays agree between O0/O2. This resolves the current-source execution gap
for this producer/export scope; it does not establish the remaining native
mask/frame/mass mapping or an improved dynamic target.

- Payload: `scratch/cp02_current_derived_O0.7rF6zk/matched_control_chain13_O0.bouyq6a7/derived_export/output/payload.nc`
- SHA256: `d4f496174616a0adf69078ef4a02d6f82ebc5baa28401879c488f9495a0f6a11`
- Cloud fraction/type/phase each have 1,294,696 valid cells.
- Cloud omega evidence retains 244,326 exact LCO values; target count remains zero.
- [Actual execution and comparison](../scratch/cp02_current_derived_O0.7rF6zk/EXPORT_O0_RESULT.json).
