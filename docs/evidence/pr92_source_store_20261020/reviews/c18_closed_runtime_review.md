# C18 closed-runtime review

Read-only review of the paired C18 receipts, closed-state audits, T22 storage endpoints, and T24 freezing-base replay on 2026-10-20.

## Runtime and state audit

- Both arms used executable SHA-256 `32a324d49366487f68ec1e6e687a465ef2533bd9163e2fe09733e83cc2272c16` and generated `module_em.F` SHA-256 `f88708844994a30540fc458aeede7e0eda4503a04a341caf714050e52f8c18af`.
- OFF receipt SHA-256 `22888b80b072cac26f91366ab087ecd169ae073f2556ea672b706564fee5bc75`; COUPLED receipt SHA-256 `cda8f4fedad8e5ba2eb06d9f180f089879f8caa2ef4bca93af677f0fb16ed091`.
- Both closed `INCOMPLETE`, return code 128, after 23 complete timesteps / 460 seconds, with no collector processing errors. Both completed T15 and T22. T24 entered KDM6 and stopped at the cloud-ice freezing packet-base check.
- Each closed-state audit reports 138 states (`6 × 23`), declared ice-policy `PASS`, zero active outliers, and zero strict-state failures. The generic exact-source audit remains `FAIL` in both arms and is separately retained. Partial T24 states are excluded from the 138-state count.
- The captured T22 endpoint confirms the directed positive Q/B pair at the selected coordinate in both arms. The T15 and T22 storage paths therefore pass within this 460-second experiment; no 600-second completion is established.

## T24 immediate failure

The bounded Intel O0/O2 replay reproduces the immediate failure from the exact captured PINU row at `(230,247,20)`. QI bits are `3623A538`, NI bits `441BBBE7`, and dry-density bits `3F0938B8`. QI is above the inactive cutoff, so the active-ice cone applies. The ice mean mass exceeds its configured maximum by about 10.8 REAL32 ULP, outside the helper's 8-ULP allowance; the cloud condition passes. The unchanged helper returns `base_valid=F, accepted=F` at both profiles.

This classifies and reproduces the immediate predicate only. Earlier C18 Q/B storage adjustments precede this state, and neither the unchanged KDM6 helper nor the small per-event Q/B budgets establish that they had no downstream effect. Upstream causality remains OPEN. The classification's next probe—capturing the exact ice state around upstream updates—is appropriately scoped; the evidence does not support widening tolerance, flooring number concentration, or changing freezing physics here.

## Publication scope

The contract's scoped 460-second report is consistent with these artifacts if it keeps the request `INCOMPLETE`, states the exact T24 failure, preserves the generic audit `FAIL` beside the declared policy result, and calls upstream causality unresolved. Physical approval remains `FAIL_OPEN`; this review does not treat the run as a successful 600-second integration or infer independence from the new Q/B representation policy.

## PR description scope correction

The initial PR-body draft overextended the declared ice-policy PASS to cloud/rain/graupel conditions. The revised PR body now limits PASS to the separate inactive/active ice policy over the 138 completed states per arm and retains the independent generic exact-source `FAIL`. The contract records 619 OFF and 617 COUPLED rain exact-bound cell-state outliers; none exceed 8 ULP, but they are not exact passes. The revised wording also preserves the T24 cause as unresolved and leaves physical/scientific approval open. This resolves the scope finding.
