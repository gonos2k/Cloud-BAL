# PR93 closed-run audit and replay

## C4 selected-column ice sedimentation replay

`replay_closed_ice_capture.py` is a bounded replay for the receipt-closed
selected column. It accepts a terminal `COMPLETE` or `INCOMPLETE` collector
receipt when timestep 24 was observed, the collector has no processing
errors, and the bound audit contains complete before/after calls; whole-step
completion through T24 is not required. It verifies the receipt-bound
compressed and expanded ice ledger hashes before parsing the capture. Each complete before/after
39-level call is passed through the exact external
`pr85_kdm6_paired_sediment_column` body extracted from the selected C4 source
unit. The extraction metadata and body SHA are recorded alongside the source
unit SHA. The fixture uses the source call's ice mode, zero thresholds and
rain coefficients, `trace=.FALSE.`, captured density, DELZ, rates, timestep,
substep count, and before-state REAL32 bits. It compares every resulting QI
and NI REAL32 bit pattern against that call's AFTER capture under pinned Intel
O0 and O2 builds.

After both bound arm audits are finalized, run one arm at a time with a new
output directory, for example:

```sh
python3 docs/evidence/pr93_active_ice_20261020/runtime/replay_closed_ice_capture.py \
  --audit docs/evidence/pr93_active_ice_20261020/runtime/OFF_closed_audit.json \
  --out /var/tmp/pr93_OFF_c4_ice_replay_20261020
```

Run the same command for `COUPLED_closed_audit.json` with a distinct output
directory. The replay itself creates fresh `/var/tmp` compiler directories;
only the generated fixture, per-profile logs, and compact result are written
to the requested output directory. Do not run it against active or unfinalized
receipts. A match establishes that the helper reproduces the observed C4
before/after call boundary; a mismatch localizes an unreproduced result to
that captured call. Neither proves historical C18 causality.

The harness smoke check uses a synthetic all-zero 39-level state only to
validate fixture generation and pinned O0/O2 execution. It is not a C4 replay
result. The exact helper body also compiles at O0/O2; both records are in
`helper_compile_O0_O2.log` and `replay_harness_smoke.json`.

## Closed C4 replay result

The OFF and COUPLED audits both bind COMPLETE 30-step receipts and report
`FIRST_VALID_TO_INVALID_CAPTURED` at call `(loop, substep, mstep) = (1,1,1)`.
The replay in `ice_replay/{off,coupled}/` reproduces all 39 levels' QI and NI
AFTER bits exactly at both Intel O0 and O2. The paired runs have identical
selected k=20 bits.

At k=20, the helper changes `(QI, NI_volume)` from
`(3616C0A1, 44167A96)` to `(3623A538, 441BBBE7)`. The exact
`REAL64(rho)*REAL64(QI)/REAL64(NI_volume)` mean changes from
`2.000467184384699e-9` kg (inside the cone) to `2.098277117513574e-9` kg.
That is 10.8029 REAL32 ULP above the configured maximum and 2.8029 ULP above
the existing 8-ULP allowance.

The immediately following stage1 ice PSD completion records
`Nbefore=622.9359741210938`, `Nnative=622.9367065429688`, and
`Ndirected=622.9367065429688`, against `exactNmin=622.9366862545476`.
The directed result gives mean mass `2.098274650450637e-9` kg, back below
the configured maximum. The helper output is therefore a transient pending
PSD state that the existing consumer repairs; this call-level result does
not identify a completed-state violation or establish a sedimentation fix.
The bound C4 endpoint active-ice check passes, while the generic QNB audit has
separate failures whose origin is not assigned here. No exact C18 source-prefix
and input identity match has been established, so the historical C18 first
writer remains unproven.

`ice_replay/call_origin_summary.json` records the per-arm audit, receipt,
ledger, source, helper, executable, and replay pins together with the k=20
transition and subsequent PSD repair values.

Run `/var/tmp/pr93_closed_audit_20261020.py` only after both bound C4 collectors have finalized `receipt.json` in:

- `/var/tmp/pr93_OFF_600s_c4_bound_20261020`
- `/var/tmp/pr93_COUPLED_600s_c4_bound_20261020`

The earlier `pr93_{OFF,COUPLED}_600s_c4_execution_20261020` attempts closed INCOMPLETE after one step because `PR91_RUN_ID` was absent from the model environment. That was a launch-environment failure, not a physical integration failure. Their preserved evidence is under `docs/evidence/pr93_active_ice_20261020/launch_environment_failure`; do not treat those receipts as the final paired run or audit them as the bound run. Once both initial and bound receipts are closed, the script also compares the exact serialized step-1 state and PBL trace prefix for each arm, stopping the prefix hash at the first step-2 record, or at EOF for the one-step attempt if step 2 is absent, while verifying each full trace against its receipt. It records both receipt hashes, executable/source/input pins, and compressed/expanded trace identities. A matching prefix supports only the initial-to-bound run comparison; it does not establish C18 source-prefix identity or historical causality. The report is `initial_step1_prefix_comparison.json`.

The script refuses to proceed without terminal `COMPLETE`/`INCOMPLETE` receipts, completed-prefix metadata, collector output rows, and zero collector processing errors. Each arm audit streams its stage trace once and its PSD ledger once. The separate initial-to-bound step-1 prefix comparison streams each stage trace again; all passes verify full compressed and expanded identities against their receipts. The stage trace's 8-byte magic, fixed header, field ordering, and `(j,k,i)` array shape follow the C18 streaming reader in `/var/tmp/pr92_c18_closed_extract.py`; the audit retains only one completed record at a time and delegates source predicates to the maintained PR85/PR87 audit helpers. It does not create a giant decompressed trace copy or save full-field NumPy snapshots.

For each completed timestep, it checks the required six-state sequence. The report keeps separate sections for the existing PR87 exact source endpoint gate (RK3, PRE_KDM6, POST_KDM6), the existing 8-ULP active ice policy with inactive positive ice counts separate, and existing Q/N/B pair and dry-density conversion checks. PRE_RK and RK1/RK2 exact-source results are reported as predictor diagnostics, not endpoint failures. Partial states beyond the receipt-derived prefix are parsed and hash-checked but excluded from completed-state claims.

The selected-column PSD ledger parser reads C4 BEFORE/AFTER rows for `(i,call_j,timestep)=(230,247,24)`, pairs rows by loop/substep/level, and evaluates internal KDM6 pairs with the freezing helper's REAL64 `rho*QI/NI_volume` expression and existing endpoint 8-ULP/inactive rules. It retains the raw QI, NI-volume, and dry-density REAL32 bits on both sides. It reports the first all-level transition call and a separate k=20 valid-to-invalid result; neither report infers write ordering among levels within a call. It also summarizes selected-column ice PSD boundary reconstruction rows by stage, including signed `Ndirected-Nbefore` event-row sums without carrier weighting. Those are unweighted boundary diagnostics, not a global number budget or nucleation evidence. Rows after the first selected call are counted separately as possible direct-miss catches when the source trace flag was false; this is a scope label, not causal attribution. These are C4-run observations; historical C18 attribution requires independent proof of matching source prefix and inputs.

The default output directory is this evidence directory; `--output` selects a separate audit directory. Output names are: `off_closed_audit.json`, `coupled_closed_audit.json`, `initial_step1_prefix_comparison.json`, and `closed_audit_summary.json`. The audit does not update Graphify snapshots. A successful structural audit is not runtime/scientific approval.

## Published closed results

Both final C4 receipts are COMPLETE through 600 seconds / 30 KDM6 calls.
`execution_summary.json`, `closed_runtime_summary.json`, `qnb_scope_split.json`,
and `independent_review.md` retain separate runtime/source/policy outcomes.
The complete per-arm metadata reports are `off_closed_audit.json.gz` and
`coupled_closed_audit.json.gz`; `audit_publication.json` binds compressed and
expanded hashes. Expand a report before passing it to the replay harness.
The native arrays remain in the receipt-bound private runs.
