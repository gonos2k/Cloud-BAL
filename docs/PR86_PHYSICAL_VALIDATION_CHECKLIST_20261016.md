# PR86 physical validation checklist

## Fixed research baseline

- [x] Freeze merged PR85 `743e9f28bdd9f29d039c9b671d7bd24fbfb3ffa9`.
- [x] Retain the successful v17 executable, both PR84 moment candidates and
  the shared boundary. No transport or microphysics equation is changed.
- [x] Carry forward first-call / first-20-second `PASS_SCOPED`.
- [x] Keep global physical/scientific approval `FAIL_OPEN`.

## Saved first-call accounting

- [x] Bind pre/post, process and numerical ledgers to original run receipts.
- [x] Use one same-call KDM6 density/thickness/map-area measure; distinguish
  the unavailable same-call host hybrid measure.
- [x] Compute six-water storage changes and bottom precipitation once.
- [x] Separate actual cutoff removal and ice→snow storage residual.
- [x] Save both numerical tables and spatial column maps.
- [x] Use proposed process activity as the suppression denominator, with
  source-specific number and volume units.
- [x] Finish independent review of all weighted suppression summaries.
- [ ] Reconcile remaining process/storage residuals and same-call hybrid
  carrier and boundary terms; a small ratio alone is not closure.
- [ ] Close complete thermodynamic and precipitation energy accounting.

## Frozen-physics time response

- [x] Extend runtime duration/output scheduling independently of physics.
- [x] Distinguish exact timestep progress, earliest failure, complete final
  state and successful first call.
- [x] Launch isolated OFF ten-minute diagnostic against the frozen binary.
- [x] Close and receipt OFF result, including an incomplete result if it fails.
- [x] Execute and receipt matched COUPLED result.
- [x] Compare available matched 20 s / 1 min / 5 min / 10 min states, retaining
  missing observations as missing and never inferring a final success from
  first-step checks.
  Both attempts completed 20 s and stopped in the next timestep at FogDES;
  first-call comparisons are retained, and 1/5/10 min responses are missing.
- [ ] Quantify Eulerian analysis-response evolution and precipitation/echo
  behavior; distinguish that response from independent observation fit and
  a transport-only diffusion experiment.

## Physical work after these measurements

- [x] Rank withheld freezing, cold-process groups and sedimentation by their
  weighted transfer activity before choosing a local physics revision.
- [ ] Preserve v17 while evaluating a separate revision if a large physical
  suppression or spatial signal loss is confirmed.
- [x] Treat absent-graupel rain freezing as a structural volume-domain issue;
  reducing dt does not admit a 1000 kg/m3 birth into a 100–900 kg/m3 model.
- [ ] Evaluate native force/continuity/pressure/Phi/wind consistency on the
  same candidate and time support.
- [ ] Extend successful matched runs to 30/60 min and HYDRO only after the
  ten-minute result is understood.

## Publication

- [x] Complete team review, resolve implementation findings and run focused
  validation appropriate to the changed analysis/runner code.
- [ ] Update selected maintained Graphify corpora, separate dated snapshots,
  derived wiki reports and append-only audit log. Structural freshness is
  not physical acceptance.
- [ ] Commit, push and open a reviewable PR with explicit successful,
  incomplete and scientific-open results.
