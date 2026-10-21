# PR95: reader integrity, declared history equivalence and same-call water accounting

## Baseline

This follow-up starts from published main `7c2d1e295c1930d64a98e9602c36289aabb1d440` (merged PR94). It keeps the C4 model physics, acceptance predicates, precision, moment prior, balance settings and three existing forecast requests unchanged. It does not launch another WRF forecast. A bounded replay of one archived KDM6 column uses the frozen component and diagnostic write gates, as documented below.

## Reader P2

`pr94_cloud_response.read_face_winds` and `pr86_compare_response.load_history` reuse `pr87_native_history._finite` before cropping, destaggering, summing or differencing. P/PB and PH/PHB are checked individually. Each U/V/W × `_FillValue`/`missing_value` case is tested independently, along with NaN/Inf and identical bad sentinels in both arms. Small real NetCDF operands exercise the state reader through an adapter retaining its frozen-domain shape contract.

The strengthened readers were also run on both closed C4 histories at all eleven 0–600-second records. No declared sentinel or nonfinite rejection occurred in the inspected fields. [The scan evidence](evidence/pr95_reader_closure_20261021/c4_reader_scan.json) lists the fields and times. This is a checked-data result, not a general claim about every output variable or scientific validity.

## Two separate equivalence results

The binary stage-prefix comparison continues to cover only `DEN,Q,QC,QI,QR,QS,QG,NN,NC,NI,NR,BG` at its recorded stage/RK boundaries.

A separate closed-history comparison checks `T,P,PB,PH,PHB,U,V,W,MU,MUB` at common minute records from 0 through 600 seconds. It checks original dtype, dimension names and non-Time extents, units and stagger, followed by exact numeric values without sums or destaggering. Different file record counts are allowed. Missing expected times, changed values/metadata and declared sentinels cannot produce PASS. Numeric equality here is not a bitwise signed-zero comparison.

This adds ten declared raw fields at saved times; it does not establish equality of every model variable or every intervening timestep. The C4-to-itself comparisons in the scan evidence are reader smoke tests. **Actual compact-run history equivalence remains pending closed outputs.** No running history or binary trace was read for this work.

## Existing forecast status

[The runtime result table](PR95_RUNTIME_RESULTS_20261021.md) and [its evidence](evidence/pr95_reader_closure_20261021/runtime_status.json) record the UTC capture time and the closed-receipt or text-log evidence. HYDRO has now closed as `INCOMPLETE`: 25 completed KDM6 calls and 500 seconds, then an invalid NG base at the next call (return code 128). This does not supply a completed 600-second HYDRO control. Text timing rows and live processes for the longer requests do not establish requested-duration completion, completed-state validity or physical approval. The original published waiting record is preserved.

Final evaluation requires the closed runner receipt, actual endpoint, immutable input/executable/history/trace identities and the separate trace/history comparisons. The existing post-run queue remains bound to its original tools and artifacts; supplementary checks use the strengthened readers when closed evidence becomes available. `tools/pr95_closed_results.py` waits for collector-closed receipts, reuses the receipt-bound existing trace audits, and runs the separate ten-field history check. It pins its source and reader dependencies and writes only an external, review-required result; it launches no forecast and does not publish or confer physical approval.

## HYDRO comparability before forecast evaluation

[The staged-input comparison](evidence/pr95_reader_closure_20261021/initial_input_comparison.json) checks hashes before and after reading twenty raw variables, plus time, dtype, dimensions, shape, units and stagger. It reads immutable `wrfinput_d01` files, not a running forecast history.

Within those declared variables, COUPLED and HYDRO have equal T, water mass/moments, P/PB, PH/PHB, W and MU/MUB. Their U/V differ. HYDRO versus OFF also has small U/V differences (maximum about 0.009825/0.005713 m/s). Therefore this is not labeled a pure wind-only treatment. The two configured continuity and force priors change together; their individual effects are not identified. Staged-field equality does not establish equality after WRF initialization or observation skill.

The predeclared forecast comparison remains the same location/time pressure/Phi/W response, cloud/water-species redistribution on fixed support/buffers, each arm's absolute water account, and authoritative observation residuals only when observations and their operator are available. The pointwise C−O=(H−O)+(C−H) identity checks data consistency and is not a quality score.

## Same-call water work

[The T1 water account](PR95_CALL_WATER_BUDGET_20261021.md) links actual pre/post fields, input DEN/DELZ, area and that call's bottom fall. It corrects the earlier overly broad claim that only a T3 geometry capture existed. It uses no RAINC, minute-history allocation, initial hybrid mass substitution or analysis increment as a timed source.

The local call measure and the host hybrid budget remain separate. Recorded numerical changes are subtracted with their signed source convention; unassigned or missing terms remain explicit. An unexplained residual is not renamed as a numerical correction to force closure.

## Scientific status

Existing OFF/COUPLED C4 600-second execution remains `PASS_SCOPED`. Water/energy closure, observation skill, native mass–wind balance, initial-shock reduction and longer-run acceptance remain OPEN or not evaluated as stated in the evidence. No precision, physical guard, N/B prior, wind cap or alpha weight is changed.

## Validation and review

The [validation record](evidence/pr95_reader_closure_20261021/validation.json) binds 103 passing focused Python tests and the selected one-column Intel replay. It is not a canonical or clean full-WRF build. Independent agent review covered the reader, history metadata, call ownership and top-boundary source proof, the closed-results queue, and guarded KG update. The review corrected an internal-loop/model-timestep attribution error before publication. The source tree and runtime identities remain separate from graph freshness.
