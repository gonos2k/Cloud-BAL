# PR83 same13 native initialization evidence

PR83 uses a single prior transaction on a copied `wrfinput_d01` at the real-to-WRF input boundary. A completed candidate would be checked against the source, policy, and prior receipt before the retained WRF startup is launched. The ordinary PR82 runner remains on its original same13 mass-only path unless an explicit PR83 receipt and policy are supplied. This does not add an initialization call inside KDM6, PBL, advection, or RK, and makes no claim of a `start_em.F` source hook.

The actual same13 source is `/var/tmp/pr82_same13_real_boundary_candidate.final2_20261012/wrfinput_d01`, SHA256 `dce4a2633521639a4195babc461a45427f669dc808cb7b2d99d321b153b77afb`, at 2026-08-16 13:00 UTC. The declared prior is [PR83_NATIVE_MOMENT_POLICY_20261013.json](PR83_NATIVE_MOMENT_POLICY_20261013.json), SHA256 `dde8df58f840d2fb11579876450749964ea2a54e36a68856c92bc979f46bae2a`. Its density operation follows WRF's actual real32 `AL+ALB` followed by real32 reciprocal, over active cells. The retained KDM6 consumer source and executable identities are bound separately in the policy and prior receipt.

The transaction returned `BLOCKED_SOURCE_CAP_INFEASIBLE` before writing a candidate NetCDF. Of 244,498 positive active QICE cells, 2,305 cannot satisfy both the selected source PSD envelope (`lambda >= 9,080 m-1`) and KDM6's native internal-number cap (`NI <= 1,000,000 m-3`). At WRF cell `[i,j,k]=[195,73,17]`, `QICE=0.0033685904927551746 kg kg-1` requires at least `1,095,670.895959 m-3` internal NI at the source minimum lambda. The largest minimum over the infeasible cells is `1,529,145.816030 m-3` at `[191,66,26]`. These are internal number-per-volume operands; the rejection is not a public `QNICE` unit conversion issue. There are 2,326 infeasible positive-QICE cells over the full horizontal array; the policy's active interior count is 2,305.

This is a global transaction rejection: proposed feasible counts are not committed. The policy reports proposed QNCLOUD 960,289, QNICE 242,193 feasible plus 2,305 infeasible, QNRAIN 205,577, and QIB 1,010; all committed counts are zero. No mass or number values were changed, no floor or cap was introduced, and the source wrfinput hash is identical before and after. QSNOW remains mass-only. CCN (`QNCCN`) initialization is separate and was not tested in this rejected transaction.

The wrapper's exit status was 2, with `native_launch_attempted=false` and no native output directory. Thus there is no PR83 native initial `wrfout`, no first-call pre/post KDM6 observation, and no Xa/Xb model comparison for this candidate. The retained PR81 executable SHA is `a805a1afff42021f322337c69d4e0818faf30e677f625f9a9d1b308728b32c00`; its identity is recorded, but it was not launched. The copied-input path is scoped to the reviewed single-domain same13 cold-start namelist. Restart, cycling, and DFI are rejected if enabled, and this evidence does not extend to restart, nesting, or DFI cases.

Machine-readable records are [the transaction evidence](evidence/pr83_same13_native_20261013/pr83_same13_native_initialization_evidence.json) and [the source-cap prior receipt](evidence/pr83_same13_native_20261013/pr83_same13_native_moment_prior.json). The receipt binds policy SHA256 `dde8df58f840d2fb11579876450749964ea2a54e36a68856c92bc979f46bae2a`, initializer SHA256 `6d5db11a58bc27ae6a3693551b127fc5653d672333a561986683aea6fa763a31`, and records `PASS_PRE_POST_HASHES_IDENTICAL`. The candidate readback helper is wired into the successful-prior launch and post-run paths; its synthetic valid-candidate tests exercise candidate preservation and moment validity without representing the rejected same13 case as valid.

Focused transaction regression:

```sh
python3 -m unittest tests.test_pr83_same13_native_transaction -v
```

No Fortran source changed in this integration, so there was no native rebuild. A separate MODE_OFF mass-only control did run at 13 UTC. It passed the scoped initial-output and Xa/Xb pair readbacks, then hit the expected first-call KDM6 rejection because positive hydrometeor mass lacked number/volume state; see [the MODE_OFF control record](PR83_SAME13_OFF_CONTROL_20261013.md). That control does not turn the rejected PR83 prior preflight into a candidate.

This result records a valid physical preflight rejection, not a native first-call pass and not a scientific or operational approval.
