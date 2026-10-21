# PR96 final source review

## Review outcome

**GO for a DRAFT pull request only.** No source-level blocker was found in
this review. Keep merge readiness and all C1 runtime claims gated on the
three-arm closed receipts and their endpoint audits. At review time the C1
OFF, HYDRO, and COUPLED runs were still pending; this review does not claim a
600-second PASS.

## Reviewed scope

- The reader validates full-record finite values and declared fill sentinels
  before tile selection, checks positive finite spacing/map factors, and
  leaves latitude/longitude range policy unchanged. Focused tests cover all
  four geometry variables and the receipt-bound C4 geometry comparison
  reports unchanged area/coordinates on both 64,960-column histories.
- The liquid-transfer reducer uses exact rational representations of captured
  REAL32 operands, independent ties-to-even reconstruction, exact per-layer
  event/endpoint identities, and the larger adjacent spacing at binade edges
  for the conservative half-ULP bound. The trace patch is instrumentation-only;
  metadata binds the diagnostic source to SHA-256
  `24e3466d9d2a5dd12485540422b6976490152094e5e947cd0f85ab7508d1f2a7`.
  Both selected columns reproduce the captured 17-field post-call states.
  Scope remains two standalone C4 columns, not tile or global closure.
- The ice contract shares the consumer's strict number-bound calculation with
  all three completion blocks and reuses the existing directed bound helper.
  The harness resets the captured miss for every producer, covers lower and
  upper adjacent REAL32 misses at three q/rho scales through each block, and
  retains the 8-ULP freezing cone and inactive cutoff. The pinned Intel O0/O2
  source-derived regression passed.
- The configurable response reader preserves frozen C4 defaults and allows an
  explicit C1 executable identity. Its receipt checks still require complete
  matching 30-step schedules, shared boundary/namelist identity, and the
  current-generation HYDRO input chain.
- The closed C4 publication keeps 620-second OFF/COUPLED incomplete runs,
  their generic audit failures, the separate passing 0–600 second trace and
  ten-field history comparisons, and the 500-second HYDRO control distinct.
  It does not attribute generic audit failures as the runtime fatal cause.
- The guarded KG helper selects reviewed PR96 docs/tools/tests, keeps
  `docs/evidence/` hash-only, preserves separate corpus snapshots and
  protected content, and requires a clean source commit plus a matching open
  PR before apply. It has not been applied in this review.

## Validation

The focused review rerun passed: 44 tests across the map reader, response
reader, liquid reducer, and Intel source-derived ice harness. The recorded
93-test validation source hashes also match the current listed sources and
tests. No model, queue, Graphify, or KG apply was run for this review.

The native C1 build is a pinned Intel partial-host overlay, not a clean WRF
build. The three-arm C1 closed runtime receipts and audits remain the final
runtime gate; successful compilation and source-level harnesses do not prove
forecast completion, global budgets, or physical approval.
