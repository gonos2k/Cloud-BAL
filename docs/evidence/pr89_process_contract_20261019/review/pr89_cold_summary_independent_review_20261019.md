# PR89 cold-summary independent review — 2026-10-19

## Verdict

No source-scope blocker found. The collector, reader, documentation, and source-form fixture are internally consistent for compact proposed/applied/deferred water-request activity. The result is explicitly not reaction throughput, a model budget closure, or global kilograms.

## Checks

- The source transform is bound to SHA-256 `769cf33f7e6d59d46e2b31ec973a7d44cecce0b505fc18b0890b5b2a4ef2464f` and inserts the collector at the current KDM62D cell commit point, before the disabled raw-row writer. The writer emits one summary row per call after the loop.
- Group vectors match the source: NG uses `rain_ng_q_process` plus `rain_ng_qv_process`; AUT uses `rain_aut_q_process` and zero vapor; G uses `rain_q_process_request` (copied from `rain_g_q_process`) plus `rain_g_qv_process`. The applied/deferred split uses the final NG/AUT/G alphas. Source inspection confirms the composite retry multiplies NG/AUT/G alpha by `rain_composite_gamma`, and sets `rain_process_alpha` to the final G alpha.
- `dry_carrier_density(i,k)` is assigned from `den(i,k)` in the bound source. Weighting with `DBLE(dry_carrier_density)*DBLE(delz)` therefore yields `kg m-2` per column and summing columns does not yield global kg. No horizontal area or map factor is present.
- Counts distinguish activity from absent records: each transaction is counted, verbose raw rows are hard-coded to zero while their writer guard is `.false.`, and the remainder is `unrecorded_transactions`. A compact row with zero AUT/G proposal activity remains `EVALUATED` with a call record; a header-only current legacy ledger is `NOT_EVALUATED`.
- The parser checks the 25-field schema, finite metrics, duplicate `(step,lat)` calls, and count arithmetic. The gzip opener supports both compact and legacy `.gz` artifacts; truncated gzip input is rejected.
- The source-form fixture extracts the transformed declaration, initialization, accumulator, writer, and final NG/AUT/G alpha assignments from the hash-verified V44 source. It supplies distinct nonzero requests for all three groups and distinct initial alphas with composite gamma `0.5`, then compiles/runs in fresh `/var/tmp` O0/O2 directories through `tests/intel_toolchain.sh`. Assertions cover each group's signed and half-L1 proposed/applied/deferred values, exercising group-major parser ordering. The focused suite passed: `9 passed`.

## Review notes

- The documentation now distinguishes a legacy header-only ledger (`NOT_EVALUATED`) from a compact header/data mismatch (rejected).
- The fixture executes the actual source's gamma multiplication assignments on manufactured distinct alphas; it does not exercise runtime gamma backtracking.
- Validation is source-form instrumentation only; it does not run the full KDM6 model with the new collector.

## Reviewed file identities

- `tools/pr89_cold_process_summary.py`: `63467b4113efdbfb61aa5c9b83b52e0d714de3ff3c193fe47d1aa6691007b3d9`
- `tests/test_pr89_cold_process_summary.py`: `b16447cc75bbb3cc5d7a14e4106443a89e72a0dc7ea658763da71b7e7e39c83c`
- `docs/PR89_COLD_SUMMARY_20261019.md`: `c0493560b4bb859fb046705ea1760efb918b4eaf336d56a123d8c0467f59c883`
