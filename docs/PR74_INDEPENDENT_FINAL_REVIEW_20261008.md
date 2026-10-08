# PR74 Independent Final Review (2026-10-08)

## Review result

The reviewed solver changes and bounded Shinhong QNI driver replay have no unresolved implementation defect in the checked scope. This is a scoped review result, not physical approval: the canonical endpoint remains `UNBOUND` / `REJECTED`, and the actual native replay exits at the NI unit adapter before a completed timestep.

## Solver and endpoint evidence

I reviewed the analytic scalar, covariance-form, partial-unit-transform, active-bound/equality, conservative box-range, and finite-overflow cases. In particular, the reported one-dimensional optimum is now `x=0.3`; the six-state U/V-only `×1000` transform succeeds; a fixed-width bound is represented as `side=fixed`; the KKT stationarity/dual certificate is in normalized-control coordinates; and finite-input arithmetic overflow is classified as numerical failure. The equality-at-active-lower-bound and outward-rounded `C=[1,1]`, `rhs=0.3`, box `[0.1,0.2]` to `[1,1]` cases pass.

Independent verification command:

```text
python3 -m unittest tests.test_pr73_joint_analysis tests.test_pr74_independent_oracle tests.test_pr74_common_moment_audit tests.test_native_kdm6_call_geometry tests.test_native_kdm6_trace -v
```

Result: 51 tests passed. The independent scalar oracle covers 396 signed target/bound combinations. The root validation receipt binds solver source SHA-256 `02b2afda770760052813dc9f08cccc9fedc067ecea3966cd3e81b5cf024a360c`; both pinned Intel endpoint profiles pass their manufactured fixture, while the canonical diagnostic intentionally exits 1 with `UNBOUND` / `REJECTED`. Physical approval remains `FAIL/OPEN`.

## Actual Shinhong QNI driver replay

The primary runner compiles the retained Shinhong source and instrumented selected `module_pbl_driver` with the pinned Intel profile, replaces exactly the two archive members and verifies their bytes, relinks the captured partialhost, then runs the same 100 staged inputs at O0 and O2. The receipts bind the runner, instrumented driver, retained Shinhong source, baseline receipt/archive, host sources, and input hashes. The selected actual call is at `(i=133,j=2)`, with QNC and QNI enabled, `p_qni=4`, and `num_scalar=6`. Both profiles record one QNI tendency addition at each of 39 levels followed by `DRIVER_BRANCH_COMPLETE`; O0/O2 geometry, pretrace, and driver captures match, and the 100 input hashes remain unchanged.

The replay exits 128 with `KDM6 invalid NI number basis input` in the wrapper's NI specific-to-volume adapter. The required post-call captures and next output time are absent. The independent helper replay finds zero negative or nonfinite public NI values and shows that the first source-order NI subnormal product at `(211,2,15)` stays valid under strict no-FTZ O0/O2 but becomes zero/invalid with `-ftz`. The final QNI receipt now serializes both O0/O2 link argv and includes `-ftz`; the helper result supports that adapter failure mechanism. Runtime MXCSR was not directly observed, so actual processor FTZ state remains inferred from link configuration. The separate common-predicate mismatch at `(104,2,1)` is explicitly hypothetical and is not called the native fatal site.

The compact profile harness also has the required declarations and its pinned O0/O2 receipt records matching successful output. It remains secondary evidence, separate from the actual driver replay.

## Remaining limits and publication checks

- The exact O0/O2 candidate link argv includes `-ftz`, and an exact-source helper replay reproduces the first NI adapter invalid result with that flag. Runtime MXCSR was not directly captured, so the processor FTZ state is inferred from link configuration rather than observed directly.
- The actual replay uses a preserved PR73 partialhost: only the two research modules were rebuilt, while other host objects remain from the retained build. This is not a clean full WRF build and did not complete a timestep.
- Reproduction depends on retained `/var/tmp` source, hostcopy/include, archive, model executable dependencies, and staged input artifacts. The runner checks hashes, but these external prerequisites are not portable repository artifacts.
- At review time, the PR74 runner, instrumented source, fixtures, receipts, and documentation were still untracked. Include every intended PR artifact in the eventual commit so the evidence chain is reviewable.
- No water/energy closure, dry-carrier identity, first upstream mass-only QI producer, whole-scheme conservation, global geographic mapping, or physical validation is established.

The machine-readable hash/status index is [pr74_independent_final_review_20261008.json](evidence/pr74_independent_final_review_20261008.json). The root validation and physical closure checklist remain authoritative for endpoint and approval scope.
