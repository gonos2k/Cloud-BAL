# PR89 C2 ICE consumer-contract independent review — 2026-10-19

## Verdict

No source-level blocker found for the requested pair-2 transient ICE exception. The new limit is opt-in, source- and core-hash-bound, scoped to ice mass/number pair 2 in the host joint update, and does not admit zeroed or unrepresentable stored values. The actual transformed host call sites use the same native threshold where pair 2 is validated or stored. The broader C2 native build remains pending; this review does not claim native-run validation.

## Source and policy checks

- `connect_ice_consumer` pins the V50 `module_em_pr85.F` text (`4d07170e…c34a14c0`) and shared joint transport source (`cdebf80f…7d0066e`). The transformed output replaces the embedded transport module before applying host call-site edits. The test asserts the prepared output begins with the exact hash-bound shared core; its extracted host store call comes from that transformed source.
- The host `joint_qnb_update` gets `[0, ICE_LIMIT, 0, 0]`. Host setup assigns volume-number bounds only to pairs 1 and 3, and the existing strict mass pair is 4. In the shared core, any positive inactive limit overlapping a volume-constrained or strict-mass pair is rejected. The direct store helper likewise rejects positive limits combined with strict mass or volume contracts. Pair 4's graupel bulk-density rule and pairs 1/3 volume rules remain separate.
- The full-candidate and failed-baseline diagnostics use `MERGE(ICE_LIMIT,0,p==2)`. The certifier's unguarded ICE limit call is within the `ELSE` branch of `IF (p==1.OR.p==3) ... ELSE IF (p==4) ... ELSE`, so it is pair 2 only. Both source-prepared endpoint/fallback stores use the same `p==2` merge. The failure-only source diagnostic retains its ordinary predicate and does not gate a successful candidate.
- Omitting the optional argument preserves the existing strict PSD gate. With a positive limit, the exception is inclusive at `Q<=limit`, requires a positive Q and N, retains the exact R32 casts with `adjustment=0`, and bypasses only the Q/N particle-mass ratio. Existing finite/range and `N*rho_dry` representability checks still apply. If Q or N rounds to zero, or `N*rho_dry` is not representable, the direct path rejects rather than repairing or erasing the pair. Values above the threshold return to the ordinary strict check.
- Optional values are accessed only inside `PRESENT`/presence-controlled branches. The test cases exercise absent limits, quiet-NaN limit rejection, and a quiet-NaN pair-2 limit leaving the joint update uncommitted.

## T5 test binding

The source-form fixture binds the actual V50 host source, actual KDM6 source (`769cf33f…b04f`), and exact shared core hashes. It reconstructs the source-derived pair-2 T5 endpoint, shows the default strict joint candidate rejects it, then checks opt-in joint update and the actual transformed pair-2 certifier store preserve the exact REAL32 Q/N endpoint. It feeds those values to the extracted actual full KDM6 NG consumer and checks acceptance using the same native transient threshold. The fixture also checks the limit equals `nearest(1.e-14,-1.0)` in R32.

The Fortran transport test adds exact-threshold, just-above-threshold, orphan Q/N, zero-rounding, unrepresentable `N*rho_dry`, NaN, default-strict, and pair-scope/strict-contract cases. The packet owner reports both test targets passed at Intel O0/O2; I did not rerun builds. Root plans a focused-suite rerun before native preparation.

## Reviewed file hashes

- `src/common/cloud_bal_joint_transport.f90`: `cdebf80f369ce9cf2bff894859233d1d4910abd02ded9d864816e53ed7d0066e`
- `tools/pr89_ice_consumer_contract.py`: `e9016ce47c4f81a8d0dd8f7c60c648596457eb4110a3e9ccd57b798297a439c8`
- `tests/test_joint_qnb_transport.f90`: `b71c53794672cdbe62adf85c6d87add75cb45319bc97dfe8849de3c0b63e6a8a`
- `tests/test_pr89_ice_consumer_contract.py`: `de2384b2ad6ef988e39f4d666b654e8574db0e4da2d54c3539ba93a9e5612f55`
