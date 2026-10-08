# PR73 independent review — 2026-10-08

Base: PR72 merge `e9a0e38a8ada142426a0b645f1598265611cf9d4`.
Review scope: first-rejection capture, species-state coverage, additive analysis
accounting, provenance, rollback/index remapping, and physical-scope claims.
Implementation review status: **SIGNED OFF WITH SCOPE LIMITS**. Overall
scientific status: **REJECTED / FAIL_OPEN**. The manufactured endpoint and
property-stage fixtures pass their stated scopes, but production lineage,
full-module mask coverage, and actual 12 UTC authority remain open.

## Findings and resolution state

| Finding | State | Review evidence |
|---|---|---|
| Species mask setup reactivated graupel after clearing it for absent-mask cases. | Fixed in current fixture source; property-validator matrix passes; full-module gate incomplete. | Mask-specific zeroing now occurs after the legacy active-graupel setup. The dedicated 16-mask property-validator fixture passes O0/O2; the separate KDM6 full-module probe stopped at mask 5 with `ProgB unsupported PSD state rejected`, after masks 0–4. |
| Objective fixture constrained omega analysis change to `0.1` while the test required zero; SPD test mutated a nonexistent root-level `R`. | Fixed; all 12 current solver tests pass. | The omega RHS is zero and the malformed covariance test mutates `observation.R`. |
| Analysis contract code briefly referenced undeclared `contract` and `source` inside `internal_phase_contract_valid`. | Fixed; focused tests pass. | That accidental line is absent; analysis accounting remains in `assess_physical_joint_candidate` and `increment_matches`. |
| New analysis extension was not accepted by the independent validator's extension allow-list. | Fixed; malformed/legacy read tests pass. | The validator recognizes the optional field and removes its extension token from the base extension comparison. |
| Native receipt initially omitted hashes for the fresh build artifacts and executable. | Fixed in the stronger attempt-2 receipt. | The receipt includes instrumented source, object, archive member/archive, compiler/link identities and commands, executable, and 101 guarded inputs including the executable. |
| Species fixture did not exercise active-to-absent history. | Fixed and covered by the O0/O2 property-stage matrix. | Each mask has a clean reference and an all-active call followed by poisoned-output target re-entry in the same executable. |
| Species matrix runner expected four density rows while compiling the one-density EOS-consistent profile. | Fixed; one graupel density is covered. | The receipt gate expects the one EOS-consistent density row per mask; active graupel uses QG/BG=400 kg m-3. Other densities and full-module masks remain open. |
| Analysis contract had no focused endpoint-to-NetCDF artifact test. | Manufactured estimator-to-endpoint/writer/readback fixture passes; production pipeline lineage remains open. | Pinned Intel O0/O2 fixtures pass and explicitly record pipeline/stage receipts as FAILED/AUTHORITY. The writer recomputes the endpoint evaluation and budget. The independent physical-contract checker passes. This does not run `run_cloud_bal_pipeline` or prove producer-stage lineage. |
| Independent reader had no malformed-analysis mutations or explicit all-absent legacy compatibility case. | Fixed; independent replay passed. | The checker rejected partial groups and invalid values, then stripped the complete optional group, restored an unchanged endpoint, and accepted the legacy artifact. |
| Shinhong ice-number research patch initially had shifted stacked-channel offsets and left an inactive optional output undefined. | Fixed; pinned O0/O2 numerical routine test passes. | Final patch uses `(channel-1)*kte`, initializes `rqniblten` to zero, and gates QNI on the QI tendency being available. The fixture tests QNI channel 4, NC+QNI channels 4/5, disabled output zeroing, and QNI-enabled with the optional QI tendency omitted. Driver accumulation, coupled host behavior, and native cell output remain untested. |
| Endpoint-only analysis writer path could be mistaken for a fully accepted SHADOW artifact. | No acceptance bypass found; scope boundary is explicit. | Writer permits the estimator-only fixture only with exact FAILED/AUTHORITY pipeline and producer stage receipts, then recomputes physical endpoint evaluation and budget. Dedicated physical-contract readback passes. The canonical standalone diagnostic CLI rejects the artifact as INVALID/UNBOUND (candidate REJECTED) because it lacks operational geometry/support/stage metadata and has pipeline status FAILED; it is not a normally accepted SHADOW candidate. |

## Evidence and scientific scope

The native first-failure record is now direct evidence, not the earlier inferred
tuple. It reports ice `mass_only`, `q=3.5308575789291633E-035 kg kg-1`,
`n=0 m-3`, at `i=133`, `call_lat_index=2`, `k=1`, within `i=2:233`, `k=1:39`.
The record does not claim geographic latitude or global-j mapping. The stronger
attempt-2 receipt reports 100 unchanged scientific inputs plus the executable,
declared-input isolation PASS, and the PR72 first-call pretrace hash match. The
separate completion audit reports the required post-call output guard FAIL: four
post-call files are missing, step completion is not established, and native
status is REJECTED (return code 128). It is a copied partialhost run that stops
at controlled admission rejection; it does not complete a timestep or validate
full physics.

The 16-mask property-stage matrix uses actual KDM6 cloud/ice/rain/graupel
property and terminal-velocity construction under the pinned Intel O0/O2
profiles. Its guarded hook returns before the first n0 reconstruction,
substep-counting, rate application, and microphysical process work. Its pass
does not establish full-module execution for every combination or prove that a
full particle size distribution is valid. The separate full-module probe
stopped at mask 5 as described above.
PR72's native-fixed source remains the basis for the instrumentation. It
retains the repaired PR72 ice-branch behavior; the regression introduced in
PR71 remains corrected.

The H/B/R trial identifies itself as a manufactured algorithm fixture. Its
authority IDs are labels in that fixture, not external observational evidence.
The analysis increment is distinct from source, boundary, and phase terms. The
endpoint evaluator, writer serialization, physical-contract readback, and
corruption checks pass, but no production pipeline candidate or stage lineage
is established. The standalone diagnostic CLI rejects this manufactured-only
artifact as INVALID/UNBOUND; this is consistent with the artifact's explicit
unrun stage receipts and missing operational metadata. The actual 12 UTC
full-observation candidate remains BLOCKED because independent real-case
declarations are still missing.

The Shinhong patch is a candidate NI transport mechanism. Its O0/O2 routine
fixture demonstrates proportional tendencies for one manufactured profile.
Applying the same `DEL` transport operator to ice mass and number does not alone establish
conservation under a changing dry-air carrier, prove that QI and QNI are paired
at each producer boundary, or identify the captured upstream mismatch.

No PR73 diff changes the pressure-remap or staged-commit/rollback routines.
Static review found no new index-remapping or rollback defect. A preexisting
`0.02/rho_d` cap in radar precipitation diagnosis remains outside this PR73
diff; it is not evidence of a new PR73 density policy. No PR73 change adds a
mass/number floor, clips or deletes arbitrary density state, or substitutes a
new density into the native physics.

## Validation status

The reviewer independently ran 12 joint-analysis and 3 native-input audit
Python tests and reran the physical-contract artifact checker; unit tests,
round-trip, malformed-extension, and legacy-without-analysis checks passed.
The pinned Intel O0/O2 endpoint fixture and 16-mask property-stage matrix are
recorded in their owner receipts; they were inspected but not rerun by this
reviewer. The canonical standalone diagnostic CLI on the current manufactured
artifact returns INVALID/UNBOUND and candidate REJECTED because operational
pressure geometry, support-radius, and successful stage metadata are absent.
That is a scope limitation, not a full diagnostic acceptance. The native
receipt records the pinned Intel profile and fresh partialhost build. The
species full-module matrix and Shinhong ice-number mechanism still require the
project validation gate before any full-science acceptance. This implementation
review does not block a PR on those explicitly open scientific claims. No Graphify update,
commit, push, or pull request was made by this reviewer.
