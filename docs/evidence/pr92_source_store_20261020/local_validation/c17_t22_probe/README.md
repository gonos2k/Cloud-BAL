# C17 T22/RK3 joint-store probe

This bounded replay uses the parent-provided candidate with the current common store. It does not inspect the still-closing C17 stage payloads.

- Candidate Q/B bits: `374237F3DE250AFA` / `36A6E0DE5EEF31AA`.
- Continuous ratio: 815.43359903744931, inside 100–900.
- Nearest REAL32 pair: Q=`0000048E` (1166 eta), B=`00000001` (1 eta); density 1166 violates the strict upper bound.
- Both policy disabled and enabled reject at common-store failure stage 6. The enabled bulk-absence path does not apply because rounded B is positive.
- A positive strict-valid pair exists at Q=`00000384` (900 eta), B=`00000001` (1 eta), with density 900. Relative to the continuous candidate, Q loss is about 265.988 eta and B rounding loss about 0.429900 eta, each strictly within the 450 eta / 0.5 eta event budgets.

A narrow future option is to allow the existing directed-Q projection for subnormal Q when rounded B is positive, gated by the current strict continuous cone and the same two per-event loss limits. This is a positive-pair directed-Q adjustment (ordinary adjustment 2 and signed storage ledger), not bulk absence (adjustment 5). It remains a proposal; no core change was made.

Pinned Intel O0 and O2 both reported default `F 6 0`, enabled `F 6 0`, and the explicit positive boundary pair `T 0 0`. Full captured output and hashes are in [`result.json`](result.json).
