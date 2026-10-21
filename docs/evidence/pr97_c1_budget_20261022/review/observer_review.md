# PR97 liquid observer review

Reviewed `tools/pr97_liquid_observer.f90`, `tools/pr97_prepare_liquid_observer.py`, and `tests/test_pr97_liquid_observer.py`. This was a read-only review of the observer implementation; no model run was launched.

## Result: GO, diagnostic scope only

The preparation helper accepts only the pinned preprocessed C1 KDM6 source (SHA-256 `7329d618f87a2924f167bd36fab43a9bd107e2697fbb6ac72ef3cee195953a67`). Its unique anchors add the observer import/declarations and begin/record/end calls around the existing store sites. Inspection confirms the original water and cloud-ice `MAX` assignments and latent-heating expression are retained verbatim; no observer value is fed back to model state or branch selection. The two-store error is computed against the actual post-store values with a two-sum residual, and the tests compare it to an exact rational reference for 96 trace-derived store pairs plus three tiny-extent cases. The Intel O0/O2 parametrized test run passed all 3 test instances.

The observer weights mixing-ratio extent/errors by `den*delz`; for the source's kg/kg mixing ratio, kg/m3 density and m layer depth, the resulting signed column totals are kg/m2. It writes no normalized fraction. Output has one record per horizontal column for each KDM6 call: six counters (activation, full evaporation, general negative extent, general positive extent, target clipping, all nonzero events), then ten accumulated signed/absolute sums (vapor error, cloud-ice error, combined absolute error, signed extent, absolute extent, activation extent, full-evaporation extent, general negative extent, general positive extent, sum of absolute per-store errors), and a maximum weighted combined absolute error. The target-clip counter flags a negative pre-`MAX` target, keeping clipping visible rather than incorporating it silently. Full-evaporation records check the observed extent and zero cloud-ice result against the captured pre-store cloud-ice amount.

The report remains a same-call, signed transfer diagnostic. It does not establish whole-model water conservation, explain the independent native Q/N closure failure, or quantify observation skill. The raw source process label `COND` is not used to infer direction; direction bins come from the signed extent.

No code changes requested. This review does not cover the separate PR97 T1 reducer prototype while its rewrite is in progress.
