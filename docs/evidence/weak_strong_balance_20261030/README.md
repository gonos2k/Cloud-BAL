# Weak/strong precipitation balance: six-hour diagnostic batch

This bundle follows the lower-factor QSNOW experiments at base commit `ce576730241e3461e813b368de175260ae39c086`. It is one initialization case, 2026-08-16 12 UTC, verified on the same 3,688 RN1 analysis points at +1 through +6 hours. Each lead is a separate one-hour total precipitation window. QSNOW means atmospheric snow mixing ratio, not surface snowfall.

## Frozen design and result

`selection_plan.json` was frozen before the new forecast outputs. Eight new six-hour forecasts compare three input-only spatial QSNOW gates with their three equal-initial-snow-total uniform controls, plus two crossed executable/input diagnostics. No future observation or forecast field is used to define the gate. `runtime/frozen/gate_manifest.json` distinguishes each horizontal gate α(x,y) in [1,3] from its separate uniform equal-mass scalar. A gate's spatial mean α is not a uniform dose.

Admission requires every CSI at 0.1, 0.5 and 1 mm across all six leads to be at least ORIGINAL, and first-hour CSI at 10 mm to be strictly higher. The counts are compared with exact integer cross-products; no time/threshold/case average is used. All eight forecasts completed, but none meets the joint criteria: `NO_QUALIFIED_CANDIDATE`, selected case `null`. A strong-only diagnostic leader is not adopted as a joint improvement.

Low-threshold CSI also includes heavier observed events. The separate observed-intensity transitions distinguish actual light, moderate and strong precipitation changes. CSI decomposition into hit and false-alarm terms is exact score algebra, not a physical process budget. The 2×2 executable/input comparison likewise describes forecast-score responses, not a single-process causal effect.

## Reproduction entry points

- `tools/cp02_weak_strong_balance.py`: verifies the frozen plan, native staged fields, histories and paired cohort, then writes 28 data files and a receipt.
- `tools/recount_cp02_weak_strong_balance.py`: independently recounts saved arrays and optionally reruns the complete scorer, requiring all 29 files to match byte-for-byte. Replay resolves runtime and plan paths before scoring, as tested with relative arguments. The bound canonical commands use absolute paths; scientific input identities remain unchanged.
- `tools/plot_weak_strong_balance.py`: verifies the sealed analysis and frozen gate maps before rendering all thresholds and the hourly RN1/case/case−ORIGINAL maps.
- `build_report.py` and `build_full_score_tables.py`: construct the paper and full lead/threshold tables from those sealed outputs. The figure-reference option points published images to the immutable asset commit.

The validation directory records clean-export tests, runtime/scoring/figure replay, independent reviews, package validation and prior evidence readbacks. Failed postprocessing attempts are retained under `review/attempts/` with their diagnosis in `review/scoring_attempts.json`; they are not final outputs. Large pre-review native scratch copies were preserved outside the repository, with their inventory bound by `runtime/attempts/pre-review-scratch-relocation.json`.

## Next physical question

The retained source and capture inspection in `review/stage3_probe.md` separates the zero-rate limiter guard from QRAIN/QNRAIN initialization. Positive rain mass and zero rain number occur in selected initial samples; the slope fallback does not create a number moment. The guard changes coupled rain/vapor/temperature treatment but does not specify a particle size distribution. Trace the authoritative mass/number initialization writer and its intended distribution before proposing any number seed. Source-to-stack-operand mapping remains an inference where debug symbols are absent.

These runs are diagnostic sensitivity experiments. Equal initial diagnostic QSNOW mass does not establish complete water or energy balance; a same-event score gain is not independent-case validation or production approval. RN1 timing/coverage, full coupled budgets and the separate C2 stability/forecast-completion work remain open. Scoped Graphify/wiki freshness supplies structural bookkeeping, not runtime or scientific validation.
