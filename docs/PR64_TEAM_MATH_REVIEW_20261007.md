# PR64 team math review — feasible joint transport

Review scope: source requirements for a feasible joint trial and the causes
still open after PR63. This is an independent read-only review; Graphify was
used for navigation, and source plus the PR63 receipts remain authoritative.

## Findings from PR63 and the current evaluator

The PR63 prose mislabels the selected RK cell values. I inspected the exact
writer in the frozen `build_cutoff_v2/solve_em_pr63.F` source: its counters use
`qct=moist(...,pqc)` and `nct=scalar(...,pnc)`, and the printed fields are
`QC, NC, QG, BG` in that order. The RK-stage rows are present in both
successful matched runs and agree exactly; the raw `run_paired_v2b` rows show
the same values. They therefore mean:

| Cut | QC | NC |
|---|---:|---:|
| PRE_RK | 0 | 0 |
| RK1 end | `+1.6839790e-7` | `-1773.7578125` |
| RK2 end | `+2.5137101e-7` | `-3662.8056641` |
| RK3 end and later pre-call cuts | `+5.0365270e-7` | 0 |

The reported maximum-negative field is a separate aggregate QC statistic;
global negative-QC counts are still valid predicates. For the selected cell,
the negative values belong to NC, not QC. Also, the first positive-QC/zero-NC
cut is not the post-RK1-QC cut: the sampler only records RK-stage ends, and at
RK1/RK2 end NC is negative. The cell first meets the declared gap predicate
after RK3, when NC has returned to zero. The successful control raw file hash
is `3f51d87a…c8f9d89`, and the successful paired raw file hash is
`46283bca…d6a991cf`; both are bound by the pair audit receipt. The finer-grained
`pr63_rk_update_cuts.raw` file and its tendency diagnostics exist only in
incomplete `run_paired_v2b`. They do not establish a within-stage operator
cause in the successful pair.

These cuts localize state observations, not the transport cause. Neither the
donor face nor the complete tendency/process operator is identified by these
records. The one returned KDM-active QC/NC gap and the 23,494 negative
entry-QC values remain unresolved. Do not present their origin as solved or
make a per-stage PSD projection the remedy.

The existing `physical_joint_candidate_contract` and
`assess_physical_joint_candidate` are endpoint-accounting gates. They compare
the declared source, boundary and internal phase increments with extensive
endpoint changes on fixed pressure geometry. The source identity is a label;
the assessment does not authenticate source authority, construct a feasible
state, enforce process donor limits, or establish a moment-process trajectory.
Its PASS cannot establish stationarity or native conservation.

For fixed pressure mass, dry air is derived from represented water:
`md = mp / (1 + sum(r_s))`. Internal phase exchange must have zero dry-mass,
net-water and represented mixture-enthalpy increments and must use the
pre-transfer carrier. The accepted float32 endpoint may require canonical
`md` refresh; its representation delta needs a predeclared allowance and must
not be labeled external source. External water terms alter the implied dry
carrier unless geometry or a physical boundary budget also changes.

## Minimum dependencies for a real feasible trial

- **Source and boundary:** provenance-bound, case/time-specific declarations
  for external water, dry-air and enthalpy increments; complete temporal and
  lateral/top/bottom flux terms on the same carrier and map metrics; a source
  identity backed by authority rather than a free-form string. A fixed-pressure
  per-cell contract must satisfy its total-mass relation. A t+20 carrier or
  unweighted sum of mixing ratios is not a same-call closure.
- **Transport and process:** donor availability, finalized process extents,
  species-specific common-air transport, and differential sedimentation each
  need their own equations. Preserve the applicable joint Q/N/BG domain at
  the physical evaluation boundary and account explicitly for deletions. The
  PR63 call-boundary cuts alone do not identify the cause or certify a trial.
- **Phase and thermodynamics:** declare which species exchange and the signed
  extents independently of the resulting endpoint; bound donor use; close the
  represented mixture-enthalpy transfer with the pre-transfer dry carrier;
  refresh temperature/EOS from the stored species. The pressure-level gas EOS
  and research enthalpy constants do not establish KDM6 rate physics or native
  compressible total energy.
- **Phi and geometry:** bind pressure geometry, model gravity, vertical
  staggering/interpolation, and supported Phi reference values. The existing
  hydrostatic Phi increment is pressure-level diagnostic evidence; it does
  not authorize a wind change or reconstruct native geopotential from WPS
  fields. Keep pressure-fixed hydrostatic feasibility distinct from native
  mass/energy closure.
- **Wind and omega:** require an authenticated U/V frame and staggering,
  independent wind/omega targets or an authorized dynamics increment, and the
  relevant face metrics and boundaries. `omega = -rho*g*w` is conditional on
  the stated approximation; WPS lacks a lossless omega mapping, and native
  `ww` is reconstructed from mass continuity. A pressure-coordinate
  continuity/geostrophic diagnostic is not native C-grid closure.
- **Trial tests:** report endpoint feasibility, process path admissibility,
  observation fit, stationarity and step norm separately. Fix tolerances and
  priors before candidate execution. Without independently authorized source,
  boundary, phase and wind inputs, computation can only test a declared trial;
  it cannot infer or create physical authority.

## Review decision and implementation disposition

Related records: [call-duration contract](PR64_CALL_DURATION_CONTRACT_20261007.md),
[native transport cause investigation](PR64_NATIVE_TRANSPORT_CAUSE_20261007.md),
[actual-data phase candidate](PR64_REAL_CANDIDATE_20261007.md),
and [PR64 closure checklist](PR64_REVIEW_CLOSURE_CHECKLIST_20261007.md).

The selected-cell labeling correction is confirmed against both successful
matched PR63 stage files. The call-duration check now follows the host `dtm`
argument through the maintained driver to KDM6 `DELT`; the retained 20-second
capture passes, and malformed/mismatched records are tested. The compiled
driver object lineage and direct RK-step field in the KDM trace remain
unverified, as recorded in the call-duration report.

I reviewed the stage-text parser and its replay against the successful paired
run. Its field mapping separates the global `minimum_qc` from the selected
cell's `selected_qc` and `selected_nc`; the strict eight-record sequence,
float32 `qmin`, headers, and full-host-tile counts match the binary masks. The
runtime epsilon predicates remain checked separately against the public KDM6
arrays with zero mismatch. Full-host-tile counts and KDM6-active-window counts
are distinct: 23,539 negative-QC cells are reported on the host tile after
RK3, while 23,494 is the KDM6-active-window entry count. This replay confirms
the state interpretation, not its cause.

The successful PR63 transition capture supports the sequential state
interpretation only: target NC is negative at RK1/RK2 and zero by RK3 while
target QC stays positive; the later KDM6 global negative-QC minimum belongs to
another cell. Separate observer evidence now attributes target NC RK1/RK2
negative tendencies to scalar advection with zero `sc_tend`; it does not expose
individual donor faces. The follow-up observer also records the target's
pre-advection positive QC tendency equal to the aggregate PBL `rqcblten`
channel. This narrows channel attribution, but leaves internal PBL process
details and exact archived physics-object lineage open. The failed-run
subcuts are not used as causal evidence. No fix or floor is supported, and
full moment admissibility remains FAIL/OPEN.

The actual-data phase-only trial now passes pinned Intel O0 and O2 builds and
independent SHADOW readback. Both receipts bind the same six input hashes,
source manifests, compiler and NetCDF identities; each reports the same
single-cell condensation extent `-6.0007274473386669e-5 kg kg-1` at
`(143,191,9)` and physical endpoint feasibility over 1,294,186 above-ground
cells. The analysis copy withholds radar reflectivity, radar LOS, and
categorical cloud observations using canonical missing encoding; the complete
physical background fields are retained. This is conditional thermodynamic
feasibility with zero source and boundary increments declared by the test,
not authenticated authority. Wind-driver, downstream WPS handoff, native
transport, and joint physical approval remain unavailable. The earlier trials
that failed on observation mutations or radar contract encoding remain
separately identified failures and are not the basis for this scoped PASS.
The final provenance-complete O0 and O2 receipts are
`/var/tmp/cloud_bal_pr64_actual_phase.WFW1Hw/receipt.json` and
`/var/tmp/cloud_bal_pr64_actual_phase.pQJxk4/receipt.json`; their SHADOW
artifact hashes are identical. Earlier run directories are not the final
receipts.

The enthalpy storage allowance propagates the complete species enthalpy
sensitivity `h0_j + cp_j*(T-T0)` and the temperature/species cross term. This
is a representation-roundoff allowance for the declared pressure-level
contract; it does not validate KDM6 rates or native compressible energy.

The minimum physical dependencies above remain prerequisites for a feasible
joint Q/N/BG transport, phase, Phi, wind/omega, boundary, and observation-fit
trial. The existing endpoint contract is not a constructor or authority
mechanism. No new priors or scientific source authority were available to this
review.

## Final follow-up evidence

The later source-channel observer narrows the selected target-cell QC pathway
further than the first observer. At RK1 in the hash-matched one-rank run,
`moist_tend(P_QC)` before scalar advection is exactly the configured PBL
`rqcblten` value, `0.0024263537488877773`; cumulus, shallow-cumulus, and the
two number-channel tendencies are zero at that location. `DIFF_OPT=1`, and
the inspected source encloses the diffusion calls under `DIFF_OPT==2`, so
those calls are skipped for this run. The selected PBL scheme is
`SHINHONGSCHEME=11`. This identifies the aggregate PBL QC channel for this
cell and call. Source inspection shows `SHINHONGSCHEME=11` adds this PBL
channel through the QC tendency path; its vertical-tridiagonal routine has no
NC argument. The current maintained physics-source hashes are not tied to the
archived runtime physics object, so this source relationship is not exact
binary lineage. The internal PBL process that generated `rqcblten` remains
unresolved. The observer retained the archived advection member and matched
ten baseline artifacts; it is not a whole-host clean build or an individual
donor-face capture. The observer/parser replay passed, but its eight focused
test methods do not include a wrong-configuration execution case; rejection
of wrong configuration is source-reviewed, not claimed as tested. The
remaining global negative-QC cells and their causal source remain open.
The source/hash and runtime-object distinction is recorded in the
[PBL source follow-up](PR64_PBL_SOURCE_FOLLOWUP_20261007.md).

The phase-only candidate remains PASS_SCOPED at O0 and O2 with byte-identical
output and a passing independent reader. A separate phase-plus-Phi attempt
reached the physical evaluator but its first independent Phi readback failed
on schema/configuration assumptions; it is not a pass. The corrected
phase-plus-Phi rerun uses the existing 10,000 m / 20,000 Pa writer profile,
lowest supported background reference center `k=4`, and 18 common supported
hydrostatic layers. The candidate reports a common-mask RMS change from
`45.3114197335` to `45.3114356022 m2 s-2`, maximum layer residual change
`0.00390625 m2 s-2`, and four-Phi-storage-ULP allowance `0.0625 m2 s-2`.
The original corrected-profile phase-plus-Phi runner receipts remain
FAIL_OPEN because the malformed `(z,x,y)` test fixture attempted to assign an
untransposed `(z,y,x)` array and raised `ValueError` before the validator was
called. The checker-only repair makes that payload shape-compatible so the
reader can inspect the declared dimension order. The subsequent independent
normal replay and focused storage-tail checks pass at O0 and O2 on the
unchanged, byte-identical artifact SHA256
`ba4e8466903492b905a6f042257d8183614c9536fe0c0211acab7fcef4951991`:
the O0 composite receipt is
`/var/tmp/cloud_bal_pr64_phi_direct_O0.tihnuc78/receipt.json`, and the O2
receipt is `/var/tmp/cloud_bal_pr64_phi_tail_O2.7how9vic/receipt.json`.
Both bind artifact and reader-dependency pre/post hashes, assert independent
Phi validity while native assessment and promotion remain false, reject both
wrong storage dtype and wrong dimension order, and confirm that stripping the
Phi extension leaves no Phi/native claim. These are post-run readback checks
on preserved O0/O2 outputs, not Fortran reruns. The original receipts and
initial failed tail attempt remain preserved as FAIL_OPEN; do not report them
as PASS.
