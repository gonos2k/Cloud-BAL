# PR72 team resolution — 2026-10-08

Base: merged PR71 `3523fa7cddbf5641f86c8abc081c1479d3862352`. This selected-source research work preserves scientific **FAIL/OPEN**.

## Correcting the prior attribution

PR71's graupel-absence wrapper accidentally enclosed the subsequent ice slope block. With graupel absent, ice slope-derived outputs were skipped. This is a PR71 implementation regression, not a defect inherited from PR70. A separate existing ordering error also wrote number velocity after a zero-number gate, undoing the zero.

A new live first-rejected point has exact zero QI and NI, correctly initialized Gamma velocity coefficients, plausible density factor and layer thickness, but unassigned ice slope-derived values. The run's coordinate differs from the historical PR71 `(i=107,k=5)`; neither a different coordinate nor rounded logged operands is used to claim an exact replay of that historical point. Exact source and executable identities remain separate.

The same EOS graupel-absent fixture does not provide a passing oracle: PR70 and the ice-slope repair reject an earlier infeasible moment trial, while PR71 reaches the recorded n0i divide with missing slope initialization. The previous statement that this divide was inherited is therefore withdrawn. Historical receipts and outputs are retained; new causal evidence records the correction.

## Validation and next consumer

Pinned Intel O0/O2 direct-slope regressions pass with a real 3×3 crop, nonunit active bounds, eight absent neighbors and poisoned outer halos. Active velocity ratio and PSD clamps are tested; absolute initialized coefficients and density-correction calibration are not independently certified by that harness. Whole-module and native records are frozen separately. An ice-only source repair removes the previous count rejection on identical incoming native pretrace, then reaches the existing unsupported TRANSIENT graupel property gate. This is a causal improvement, not an accepted first call or an energy/water closure result.

Common absence classification distinguishes absent, paired positive, mass-only and number-only states before requiring PSD properties. New restrictions must be labeled as research admission policy, and pending source transfers require explicit process authorization. No tiny positive mass is deleted or positive number fabricated to pass.

## Parallel atmospheric path

The current full-observation 12 UTC path lacks independent declarations. Its fail-closed preflight and the fresh conditional single-cell fixed-wind phase/readback baseline are distinct results. A model file at 13 UTC cannot authorize a 12 UTC candidate. No absent sigma, boundary or source is reconstructed from endpoint residuals.

## Review and preservation

Four focused agents cover actual ice state, species absence, atmospheric declarations and independent review. The independent review confirms final source/object/executable, input and receipt identities; no unresolved implementation blocker remains within this scoped delivery. Scientific acceptance remains OPEN. Root-owned Graphify/KG maintenance follows the frozen implementation; two unintended isolated-worktree graph refreshes are archived separately, and their tracked derived files were restored. Neither is a maintained-corpus delta or runtime validation.

The provisional isolated Graphify receipt records a rebuild from the inherited 1,499-node graph, not a delta against the maintained 7,965-node Cloud-BAL corpus. Its generated files were not published as maintained snapshots. The preservation receipt records both scratch archives; final root-owned dated overlays and wiki sync are a separate delivery.

The team additionally found and addressed declaration type-checking gaps, a repeated whole-array scan inside per-cell property loops, the nonunit index remapping risk in assumed-shape local validators, and a late ice slope-reconstruction consumer outside the first two intercept rebuilds. Final source counts and fixtures are recorded by the independent reviewer. A strictly positive pair is a necessary admission condition, not full PSD validity or physical certification.

Nonfinite manufactured inputs exposed a Fortran logical-expression hazard: `.or.` does not guarantee short-circuit evaluation, so combining an IEEE finiteness test with a NaN ordering comparison can trap before controlled rejection. The species classifier now separates those checks; the negative/nonfinite O0/O2 cases exercise the actual compiled path.

The latest exact-operand [expression replay](evidence/pr72_live_ice_expression_replay_20261008.json) is scoped to the new instrumented first rejection at `(lat=2,i=83,k=7)`. It recovers both `V_N` and `V_N/DELZ` exactly in binary64, with QI=NI=0, correctly initialized coefficients, and an unassigned slope moment. This resolves the earlier rounded-field comparison limitation for that point; it does not replay historical i107/k5.

The final combined-source native run uses source `1fbd9d5c…55e819` and the original incoming pretrace; strict pair admission rejects positive mass without its paired moment before PSD work. Its source, object, executable, inputs and missing post-call outputs are recorded in a separate receipt. Neither that result nor the ice-only TRANSIENT rejection is a physical PASS.
