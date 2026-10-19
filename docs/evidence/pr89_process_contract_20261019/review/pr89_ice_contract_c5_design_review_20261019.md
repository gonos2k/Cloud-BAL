# PR89 C5 joint-absence proposal: independent design review — 2026-10-19

Read-only design review of the proposed extension to the frozen C4 ICE/QI joint-storage path. No source changes, tests, builds, or native runs were made.

## Assessment

The narrow extension is physically and numerically defensible if the added condition is derived from the existing ICE minimum particle-mass bound and REAL32's minimum positive subnormal, and is applied only to the existing opt-in inactive ICE path. It addresses an orphan number moment: QI rounds to zero while QNI remains a positive REAL32 subnormal, despite the entire number population being below the count that could carry one representable minimum-mass quantum.

For the stated C5 same-column `k=2` candidate, Q=`1.5521916836884197e-60` and N=`1.1916375247192763e-44`; Q/N is `1.3025703298946397e-16`, below the existing minimum particle-mass ratio `2.6055879053180625e-16`. Q is about `2.22e-15` of half a REAL32 subnormal quantum, while `N*minimum_mass` is about `3.10e-60`, also about `2.22e-15` of one REAL32 subnormal mass quantum. The proposed `N <= REAL64(min_positive_subnormal_R32)/minimum_mass` cap is therefore satisfied by a wide margin (N is about `2.22e-15` of the cap). This makes the rule source- and storage-derived, not a case-tuned epsilon.

## Conditions needed to keep the exception narrow

- Preserve the old/default and legacy-valid paths byte-for-byte in behavior. Only the existing explicit quantum-absence option plus positive finite inactive-mass limit on ICE/QI may enter this case; existing joint update validation already confines that limit to pair 2 and bars strict-mass/volume contracts.
- Require finite positive Q and N; Q must cast to zero, N must cast to a positive REAL32 value (the orphan case), and Q must satisfy the existing inclusive inactive cutoff. Then require `N <= REAL64(nearest(0.0_real32,1.0_real32))/minimum_particle_mass` using the pair's validated positive `minimum_particle_mass`. Do not use a normal-minimum `tiny()` value, a hard-coded epsilon, or a new tunable floor.
- Store exactly `(0,0)` with the existing adjustment code and preserve the existing signed extensive storage ledger, which adds `carrier_new*(stored-candidate)` for both moments. Do not round N upward or retain an N-only state.
- Keep continuous consumer validation strict. This is a store-time mapping to the existing inactive representation, not permission for a nonzero stored N whose `N*rho_dry` is unrepresentable. The absent stored pair still goes through the existing inactive-state validation on the next feasibility pass.
- Reject N above the derived cap, Q that does not round to zero, invalid/nonfinite/negative input, missing opt-in/cutoff, and any strict/volume request. Tests should hit the threshold and its next representable N value above it, the C5 orphan, an above-cutoff Q, missing opt-in, and one-sided/ordinary legacy cases.

The proposed one-REAL32-quantum cap is looser by a factor of two than a half-quantum bound inferred from round-to-nearest Q=0 alone. That is acceptable as the stated “at most one minimum-mass quantum” policy, and C5 lies roughly 15 orders of magnitude below it; document that exact one-quantum rationale rather than imply a half-quantum guarantee.

## Review boundary

This supports a narrow C5 code change, subject to the conditions above. It does not establish that every T5 endpoint belongs to this branch; the packet agent's full T5 population audit and source-bound regression should verify that before interpreting run completion. It also does not change the physical-approval status or establish completed process closure.
