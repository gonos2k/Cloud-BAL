# C18 prelaunch source review

Read-only review of the C18 common-core change, host transform, and pinned generated module on 2026-10-20. This is not a runtime or scientific approval.

## Pins reviewed

- Current core `src/common/cloud_bal_joint_transport.f90`: SHA-256 `faa4ce0e31bf5b394c9a5ec2045a917464dca7cd4d902b6aa62be80a19aa5ac0`.
- Current policy fixture: SHA-256 `4cc7f5242dc16363ea4867c02b14980f02dcbbde4b75941ebe1d4594053ce659`.
- Generated C18 `module_em.F`: SHA-256 `f88708844994a30540fc458aeede7e0eda4503a04a341caf714050e52f8c18af`.
- The current C18 executable pin reported for the pending paired run is `32a324d49366487f68ec1e6e687a465ef2533bd9163e2fe09733e83cc2272c16`.

## Findings

- Relative to the archived C17 core, the C18 diff is confined to the storage opt-in name, a bounded directed-Q path for positive subnormal Q with positive rounded B, and shared loss-bound validation. Existing default behavior remains opt-out: `store_directed_q` rejects subnormal inputs unless its new private optional argument is explicitly true. The opt-in path requires positive Q, strict mass checking, no volume-number contract, and positive rounded B. It reuses the directed projection, then checks both absolute event errors against the existing half-quantum budgets before accepting adjustment 2.
- The shared bound predicate uses REAL128 comparisons for `abs(stored_Q-candidate_Q) < rho_max*eta_B/2` and `abs(stored_B-candidate_B) < eta_B/2`. The zero-pair branch remains code 5 and the positive directed pair is adjustment 2; the policy-only bulk absence ledger therefore records only code 5. The normal storage deltas and adjustments continue to account for adjustment 2. The grouped transaction still stages candidate arrays and ledgers locally before commit.
- The captured T22 case in the fixture has a strict-valid continuous pair, while nearest storage `(1166 eta_B, eta_B)` fails the strict upper density. The tested directed pair `(900 eta_B, eta_B)` is strict-valid and stays within the stated absolute event budgets. The fixture also covers default-off rejection, the actual candidate bits, half-quantum and Q-budget edges, out-of-cone inputs, negative/zero helper inputs, separate ledgers, option compatibility, and rollback.
- The generated C18 host differs from the preserved C17 host by the public opt-in rename and uses that opt-in on the existing pair-4 path and retry-selection probe. The probe retains local-only diagnostic outputs, so it does not commit ledger deltas. Positive adjustment-2 changes remain in the existing general storage ledger; code-5 events remain in the separate bulk ledger.
- No precision, tolerance, continuous density predicate, physical coefficient, or donor identity rule changed in this diff. The reported pinned Intel O0/O2 policy-fixture and focused Python passes are consistent with the current pins; I did not rerun them.

## Gate status

No source-level blocker found for the bounded C18 candidate before paired launch. C18's paired runtime result, post-run evidence closure, and scientific gates remain pending. C17's earlier failure is historical evidence and must remain distinct from any C18 result.
