# Cloud-BAL progress audit — 2026-09-09

## Scope and conclusion

This is a point-in-time inspection of the requirement/checkpoint ledgers, execution records, selected source, and retained test logs. Three independent reviews covered the checklist, checkpoints, and receipts. No new numerical tests, compilation, native execution, or operational changes were performed. Existing sources and ledgers were not edited. Source files and logs were changing during inspection; this audit does not certify the latest working tree.

The intended path is pressure-level analysis -> WPS -> metgrid -> real model-level initialization. CP00 is COMPLETE/PASS in isolated engineering scope. CP01 remains IN_PROGRESS/NOT_RUN. CP02–CP09 remain PLANNED/NOT_RUN. FG1–FG3 are not achieved, and promotion remains blocked.

## Canonical checklist

Source: [requirements TSV](CLOUD_BAL_REQUIREMENTS_20260907.tsv), [human checklist](CLOUD_BAL_CHECKLIST_20260907.md).

- 45 mandatory requirements: 45 OPEN / NOT_RUN; no final requirement is closed.
- Historical implementation classification: 8 confirmed, 29 partial, 6 design/contract, 2 unconfirmed. These baseline classifications are not a current completion percentage.
- X01: NOT_APPLICABLE / EXTERNAL_COMPLETE, preserved separately from the mandatory denominator.
- Requirement and checkpoint IDs/column structure were checked. All mandatory requirement IDs map to at least one checkpoint; X01 is intentionally outside that mapping.
- CP00 and CP01 evidence paths referenced by the checkpoint ledger exist.

## Checkpoints

Source: [checkpoint TSV](CLOUD_BAL_CHECKPOINTS_20260907.tsv), [stage plan](CLOUD_BAL_FINAL_GOALS_CHECKPOINTS_20260907.md).

| ID | Canonical state | Evidence and remaining scope |
|---|---|---|
| CP00 | COMPLETE / PASS, LOCAL_SCOPED | Baseline, portable CI, local ifx tests, independent GREEN/RED handoff. Not clean-release or hosted-CI certification. |
| CP01 | IN_PROGRESS / NOT_RUN | Substantial pressure geometry, mass/thermo, partial-face, remap, WPS and independent replay work; full transition and host contract closure remain open. |
| CP02 | PLANNED / NOT_RUN | Upstream/build and experimental WPS/metgrid/real preparation exists; complete OFF native round-trip/publication gate is unclosed. |
| CP03 | PLANNED / NOT_RUN | Balance/partial-face/residual work exists within CP01 evidence; whole balance checkpoint has no closure receipt. |
| CP04 | PLANNED / NOT_RUN | Thermodynamic block, independent replay and stage-budget tests exist; complete observation/coupled-physics closure remains open. |
| CP05 | PLANNED / NOT_RUN | Actual observation target, lineage, frame, terminal velocity and transport closure remain required. |
| CP06-A | No separate canonical row; parent PLANNED / NOT_RUN | Full pressure-level coupled candidate and independent acceptance remain required. |
| CP06-B | No separate canonical row; parent PLANNED / NOT_RUN | Accepted A candidate plus CP02/integration prerequisites and final native verification are required for FG1. |
| CP07 | PLANNED / NOT_RUN | Complete functionality/native regression follows CP06 A+B. |
| CP08 | PLANNED / NOT_RUN | Independent-event 0–6 h science, ablation and wave-safety evidence required for FG2. |
| CP09 | PLANNED / NOT_RUN | All 45 requirements, release identity, recovery/SLO and independent acceptance required for FG3. |

Preparation and partial receipts must not be interpreted as whole-checkpoint PASS. CP02/03/04 PLANNED labels are coarse scheduling labels and do not mean zero implementation activity.

## Verified progress and limits

The [CP01 execution record](CP01_EXECUTION_RECORD_20260907.md) documents:

- Pressure geometry and partial-face/thin-cell oracles; pressure/dry-mass separation and WPS mapping.
- Independent thermodynamic reconstruction, pressure-column remap, union-domain geometry accounting, Phi replay and candidate-domain geostrophic assessment.
- Earlier experimental 13 UTC metgrid/real paths produced wrfinput files. Initial order-2 interpolation produced negative QVAPOR and was rejected; isolated order-1 experiments removed that undershoot. These experiments do not establish native conservation, forecast validity or FG1.
- Same-background OFF comparison was added; the earlier comparison with different hydrometeor backgrounds is not algorithm-only evidence.
- KDM6 startup source behavior was investigated. Zero number fields in initial files alone are not proof of a bug; actual first-step behavior remains unverified.
- The later host-pressure experiment converged in four iterations to approximately 0.004070 Pa, but writer reason 9 prevented WPS/SHADOW output. The previously encountered terrain-center rejection was addressed; it must not be reported as the latest failure.

The current production guard at [cloud_bal_real_netcdf.f90](../src/common/cloud_bal_real_netcdf.f90) in validate_shadow_write_contract rejects allocated pressure_transition_seed before full artifact creation. Component serialization/replay PASS does not remove that guard.

Latest inspected logs:

- [transition_pressure_metadata_python.log](../scratch/transition_pressure_metadata_python.log): portable Python contract suite PASS.
- [transition_pressure_metadata_io.log](../scratch/transition_pressure_metadata_io.log): pinned Intel/NetCDF I/O contract suite PASS.
- The latter explicitly includes UNBOUND / UNBOUND_REQUIRES_COMMITTED_GENERATION, promotion_eligible=false, science_assessed=false, and pressure_transition_physics_independently_validated=false. Fixture/replay checks are not full transition acceptance.
- These logs postdate the execution record read during this audit. No self-contained exact-source manifest was found for the newest fixture directory; historical PASS cannot certify subsequent edits.

## Next closure work

- [ ] Close remaining transition uncertainty/error propagation and end-to-end original-input physical replay; verify the full production candidate rather than only copied fixtures.
- [ ] Reconcile the latest pressure metadata provenance tests with the execution record's older producer-only limitation.
- [ ] Complete final pressure/dry-mass, species, enthalpy, geometry, Phi and residual checks on the serialized candidate before considering the writer guard satisfied.
- [ ] Replay the accepted candidate through the existing WPS/metgrid/real path and independently check final native arrays and conservation contracts.
- [ ] Finish host-specific species/denominator, KDM6 startup, mass/EOS/metric, frame, boundary/time and source-to-binary contracts relevant to the acceptance scope.
- [ ] Bind final tests, input/config/toolchain/source hashes and independent closure review to one evidence generation before changing CP01 gate status.

This list is an audit of remaining work, not authorization to remove a guard merely to produce output.

## Documentation drift

- STATUS_20260907.md uses the older 66a63bd7 review baseline; current repository HEAD and the main requirement/checkpoint baseline are f837bad0bdf1050a34975d93b178b7dee4420094. The worktree is dirty.
- CP01_HANDOFF_20260907.md and wiki hot/overview describe earlier work. Their initial H1–H4 list must be reconciled against the later source investigations and native experiments; it is not a current exhaustive blocker list.
- The detailed execution record is the best progress source but is itself older than the latest pressure-metadata test logs inspected here.
- The requirements' 8/29/6/2 implementation classification remains a baseline snapshot. A current activity/evidence view is needed without automatically promoting final gates.
- No canonical gate, checklist checkbox, checkpoint state, or KG cache was changed by this audit.

## Capture metadata

Captured UTC: 2026-09-09T04:19:16.231482+00:00

- `docs/CLOUD_BAL_REQUIREMENTS_20260907.tsv`: SHA256 `32c0209e0f3b9acf42a9ca2efe3f150f7feff50f5cacbba0a000c0f5dd60d624`
- `docs/CLOUD_BAL_CHECKPOINTS_20260907.tsv`: SHA256 `d8c42e04b3344fb33071945fe48292bb29fdb037d49e7481f99c09a296558772`
- `docs/CP01_EXECUTION_RECORD_20260907.md`: SHA256 `60eda00d75af42d2aac8a941180cedaf991593e674023a3895cef82111566283`
- `src/common/cloud_bal_real_netcdf.f90`: SHA256 `9dff5ed5900e4ff96ad6670b6dcc445472aaf80926bf0bd05ff56131551ca8af`
- `tools/validate_shadow_diagnostics.py`: SHA256 `255b896590607cfca263aa508460dbd27117cee479399f82df2a72f79b1f2880`
- `scratch/transition_pressure_metadata_python.log`: SHA256 `30c47612992fafa02db744f87a2804c162432cad08357fedac69354fbd369bf7`
- `scratch/transition_pressure_metadata_io.log`: SHA256 `108ac07fafd586b49afffef7f479a332d42c6a8b4496aa239e3a128e07060aa9`

## Subsequent progress — exact replay and research native execution

The earlier audit above is historical. The unconditional transition rejection
and old writer failure are no longer the latest candidate status. Frozen
independent replay now passes the complete exact stored-state criterion, four
retained O0/O2 fixtures pass, and five malformed/one-ULP/probe mutations reject.
A guarded local metgrid→real run also succeeds with unchanged manifest inputs;
hybrid algebra and host-pressure replay pass. Evidence and limitations are in
[the CP01 execution record](CP01_EXECUTION_RECORD_20260907.md) and
[the execution receipt](../scratch/native_handoff_stage.ymn6MM/execution_receipt.json).

- [x] Validate this serialized candidate under exact_stored_state_v1.
- [x] Execute its existing direct-QV metgrid/real research path and pressure diagnostics.
- [ ] Complete same-input OFF/native comparison and native conservation/coupling evidence.
- [ ] Close KDM6, mass/EOS/metric, producer-bound frame/boundary and build contracts.
- [ ] Bind the complete scoped CP01 exit evidence and independent review.

These checked items are bounded engineering evidence, not completed canonical
requirements. CP01 remains IN_PROGRESS/NOT_RUN; CP02–CP09 and all 45 mandatory
gates retain their existing state. The kg-orient cache is historical and is not
rewritten during read-only orientation.

The subsequent native OFF comparison is now measured, but its old producer
receipt lacks a binary/config snapshot. Matching upstream inputs and logged
options are insufficient to claim same-build causality. The current closure
step is a privately staged OFF reproduction with explicit input/config/binary
binding. KDM6 auxiliary field presence is verified; first-call initialization
and physical consistency remain open. See the latest CP01 execution entries.

The OFF receipt gap is now narrowed by a private qf63eH-bound reproduction:
121 staged inputs remain unchanged and its SHADOW-OFF WPS bytes exactly match
the paired OFF artifact. The binary, configuration and manifests are retained
in `scratch/off_qf63eH_run.yeYUmP/receipt/launch_receipt.final.txt`. Historical
launch provenance is not retroactively certified; native conservation and the
remaining CP01 contracts remain open.

## Subsequent executable checks — KDM6 and native wind

- [x] Reproduce a concrete zero-QIB division with literal KDM6 source and actual
  candidate-column values under pinned Intel. Masked exceptions complete after
  density capping; -fpe0 terminates at the division. Full KDM6 startup is untested.
- [x] Identify the 500 Pa close-level selection branch at the largest native
  wind-change cells. Selected U change matches; V and full-column replay remain
  incomplete, so no full attribution or native balance PASS is assigned.
- [ ] Resolve KDM6 volume/number initialization and demonstrate full first-call behavior.
- [ ] Finish original-source native interpolation replay and coupled invariants.

Exact artifacts and limits are in the latest CP01 execution entry. All canonical
checkpoint/requirement states remain unchanged.


### Latest scoped contract progress (13 UTC cycle and wind producer)

- [x] Frozen 13 UTC reader: pinned Intel O0/O2, matched older forecast cycle
  positive case and four exact-error reference-time mutations PASS; source and
  input hashes retained; independent scoped review completed.
- [x] Fresh pinned wind build/private 13 UTC execution completed; durable
  logs/manifests and new LW3/LWM retained, with parent manifest verification.
- [ ] Integrate/validate the final shared reader implementation. Another
  session is editing it; the tested isolated version has not overwritten it.
- [ ] Complete exact compiled-source wind-frame interpretation and remaining
  host/species/denominator/EOS/metric and boundary contract enforcement review.

Cycle evidence: `scratch/cp01_contract_snapshot.hvp19t_7/reftime_13z_receipt.json`.
Wind evidence: `scratch/cp01_lw3_success_20260909/durable_manifest.sha256`.
The new wind fields differ from historical LW3; this does not authenticate
historical bytes. CP01 items 4 and 6 remain SCOPED PASS; whole CP01 stays
IN_PROGRESS / NOT_RUN, CP02–09 PLANNED / NOT_RUN, all 45 mandatory requirements
OPEN / NOT_RUN. The six-item exit matrix governs CP01 scope.
