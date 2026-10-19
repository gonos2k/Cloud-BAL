# PR87 paired-rain flux caller review

## Finding

The suspected cross-column flux reuse is confirmed in the frozen KDM6 source used for V42 (SHA-256 `bdb1882afed860068cecbb6c7b958eef0938cadbd4225222ba7522e28ecc071a`). `pr87_rain_qrate(kts:kte)` and `pr87_rain_nrate(kts:kte)` are one-dimensional locals. `pr85_kdm6_paired_sediment_column` fills them inside the `do i=its,ite` loop at lines 2725–2746. After that loop, the top-level `k=kte` flux loop and lower-level sweep assign those same vectors into every active column's `falk(i,k,1)` and `falkn(i,k,1)` (lines 2749–2773). At each substep, only the last visited column's return vectors remain. Every column whose `n<=mstep(i)` then receives those last-column rates.

The neighboring graupel path assigns `falk(i,k,3)` inside the column loop. The ice path also assigns its returned rates inside the helper-call loop. The rain path's delayed consumption is the outlier.

The first runtime rain-ledger call is unambiguous: `PR87_RAIN_CALL` records model timestep **1**, wrapper row **2**, and `dtcld=20 s` in both OFF and COUPLED artifacts. That call contains 277 `PR87_RAIN_SED` rows over 232 distinct columns; 94 rows have nonzero `ground_approved_q`, ranging from `1.8789759503306067e-9` to `3.997545652201505e-3` (summed row values `0.04578623913483733`). The differing per-column decisions establish heterogeneous helper outputs. The full first-timestep sweep has 280 `PR87_RAIN_CALL` markers. The V42 PR67 stage-2 record writes `fall(its:ite,kts,1:4)`, including the rain phase, and the budget audit maps that captured phase through `DELZ`, `DENR`, and `DTCLD` to public `rainncv`. It finds helper ground-approved rain Q exceeds captured public rain by **661,841,232 kg OFF** and **661,852,232 kg COUPLED**. The runtime therefore confirms a large realized helper/public-rain discrepancy in addition to the caller-level rate reuse defect.

## Minimal source correction

The transform copies each rain helper result immediately into existing `falk(i,k,1)` and `falkn(i,k,1)` slots inside the same per-column loop, after the helper's validity check. It removes the two later assignments that re-read the one-dimensional result. The existing `fall/falln` accumulations, packet formulas, rates, helper order, substep gates, state updates, and vertical sweeps remain intact. This follows the nearby graupel and ice caller pattern and adds no new rate arrays.

The transform accepts only these frozen source preimages:

| Preimage | SHA-256 |
| --- | --- |
| V42 compiled KDM6 source | `bdb1882afed860068cecbb6c7b958eef0938cadbd4225222ba7522e28ecc071a` |
| V43 diagnostic plus small-positive graupel policy composition | `ed1f1ee12beb4395e08e7df831bd86163080e7d93fa60d6ac427a04c0862a148` |

Applying the transform in memory gives candidate hashes `d4dc50bfacbdb6209c61c07e0f69231140a1adbc9bef29ae2f54ac46f8736a6b` for V42 and `769cf33f7e6d59d46e2b31ec973a7d44cecce0b505fc18b0890b5b2a4ef2464f` for composed V43. These are source-transform identities; neither candidate has been compiled or run.

## Regression coverage

The regression extracts the helper interface and caller blocks from the full hash-checked frozen V42 source archive, substitutes a deterministic heterogeneous Q/N helper, and compiles both old and transformed call paths with the pinned Intel profile at O0 and O2 in fresh scratch directories. The cases use distinct rates and mstep values, including a substep where the final column is inactive. The old caller fails the independent per-column ground-flux assertions; the transformed caller passes. The focused regression passes at both optimization levels.

No frozen native source or saved run artifact was modified. The audit establishes both the caller-level reuse defect and the captured first-timestep discrepancy. The regression compiles only an extracted caller harness with a deterministic stub helper; the full model was not rebuilt or run.

## Files

- [`pr87_rain_flux_cache.py`](../../../../tools/pr87_rain_flux_cache.py) — source-pinned transform for V42 and composed V43 preimages.
- [`test_pr87_rain_flux_cache.py`](../../../../tests/test_pr87_rain_flux_cache.py) — source-anchor and heterogeneous-column regression coverage.
