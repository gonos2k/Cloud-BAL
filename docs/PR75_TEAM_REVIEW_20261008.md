# PR75 team review

## Scope and result

Reviewed the frozen solver candidate `tools/pr73_joint_analysis.py` at SHA-256
`6efbf6753c68b8a7344fba4b823ce7b39d1c87ad13f350ea30055f878a6de991` and its
focused tests at SHA-256
`02250766fdbbe811a9860ce6a5d48c749b7c98e499f826e3ebebeaa16379441b`.
The source review found no unresolved numerical blocker. The native O0
floating-point diagnostic is also bound to its retained source, call, and
execution artifacts; the review found no unresolved provenance blocker.

The reported P1 was reproduced on the scalar problem `B=R=1`, `H=2`, background
`0`, observation `1`, with no equalities or bounds. The exact minimizer is `x=0.4`.
The current source evaluates the gradient in normalized-control coordinates and
forms its stationarity scale from the absolute, uncancelled background,
observation, and equality-multiplier contributions. It retains the existing
`4096 * epsilon` certification threshold; this is not tolerance inflation.

The lower/upper dual sign conventions and fixed-bound handling remain intact.
Primal bounds are checked in original state units, and the active state is
assigned from its exact declared bound before the complementarity check. The
scale sum has an explicit finite check that returns `NUMERICAL_FAILURE` on
overflow. Covariance normalization precedes equality rank selection, and active
face rank checks continue to operate in normalized-control coordinates.

Focused coverage includes the P1 regression, rejection of a perturbed interior
solution, rejection of an incorrect upper-bound dual sign, 396 scalar box
oracles, 128 independent Decimal covariance/equality oracles, and a state-unit
re-expression of an active-bound/equality certificate. The solver owner reports
20 focused unit tests and `py_compile` passing. This review did not rerun tests.

## Source and graph map

The maintained Cloud-BAL graph inspected read-only is the pre-PR75 snapshot at
`graphify-out/graph.json` (8,409 nodes, 15,650 edges; SHA-256
`3b7bc538122162db0ad2a71b7f64451638da808841d8e4ca02dfe94fbc2c8a03`). Its
`evaluate()` node has 19 extracted connections, including `main()`, covariance
factorization, equality rank selection, solve, and physical adapter calls. It
also records the import from the PR74 independent oracle to the solver. The
snapshot predates the PR75 stationarity edits and new oracle file, so it provides
navigation but no PR75 graph delta. No graph freshness or physical/runtime
validation is inferred from it.

The Python solver is called by `main()` and the `tests/run_pr73_joint_analysis.sh`
endpoint path. Direct tests import it from `tests/test_pr73_joint_analysis.py`,
`tests/test_pr74_independent_oracle.py`, and the new
`tests/test_pr75_stationarity_oracle.py`. The new PR75 oracle is not yet present
in the inspected graph snapshot.

The independent stationarity reviewer ran the six oracle tests against the same
frozen solver and test hashes. Its receipt records 396 scalar box cases, 128
80-digit Decimal covariance/equality cases, wrong-solution and wrong-dual-sign
fault injection, and a 1000x unit re-expression. The oracle set is deterministic
and uses well-conditioned SPD fixtures; it does not claim broad ill-conditioned
covariance coverage.

## Native diagnostic and authority boundary

The final diagnostics-only O0 partial-host run is bound to the same PR74 O0
selected-driver capture and pretrace: both hashes match the prior receipt. It
also retained all 100 staged input hashes and left the incoming archive
unchanged. At the first source-order NI conversion site `(i,j,k)=(211,2,15)`
the captured public NI and dry density match the prior pretrace values. Here
`j=2` means the wrapper's `call_lat_index`; no global-j mapping is claimed.

At the failing call, the same OS thread (ID `4081559`) read MXCSR `0x9FFD`
before and after conversion. FTZ (bit 15) and DAZ (bit 6) were set. The normal
binary32 inputs (`0093B134` and `3F449EE9`) produced positive zero
(`00000000`) and `valid=F`; the failure-time runtime state directly confirms
the FTZ mode that earlier `-ftz` helper replay had only inferred. The diagnostic
helper did not change MXCSR. Status bits 0–5 were already `0x3D` before the
call and remained so, so those sticky exception flags cannot be attributed to
this conversion. The prior strict no-FTZ helper replay produced a nonzero
subnormal result at this same coordinate.

The first direct capture attempt is preserved separately and is marked
nonfinal. It omitted the original `-convert big_endian` KDM6 compile option;
its first-call pretrace therefore differed from PR74. The final run restored
that option and reproduced the exact PR74 pretrace and selected-driver capture
hashes. Review conclusions use only the final receipt and raw capture.

This is one O0 diagnostics-only partial-host run. It retained the inherited
`-ftz` link, stopped with the expected NI-adapter fatal (exit 128), and did not
complete a timestep. Main-startup MXCSR and other threads were not captured;
there was no new O2 state capture. The final receipt is
`docs/evidence/pr75_native_fp_O0_20261008.json` (SHA-256
`fd547009d3e9059bfad46fe1d1c4775f6c8371412e110ad42751f06f79922aae`); its raw
capture is SHA-256
`71f7c6426b8d723f62cf0d18bf19a525a8af7f266039195a6672f50ad2fefd27`, and the
runtime note is SHA-256
`43795ae3d5f4388f08fca5fece5b98358746ed5e646395dc2ad8d6f73feaa99e`. These
limits do not weaken the direct O0 failure-site observation, but the run is
not a full clean native validation.

Separately, the parent validation receipt binds the same solver hash to fresh
pinned Intel O0/O2 Cloud-BAL endpoint builds and writer/readback passes. The
61-test suite passed. The canonical endpoint remains `UNBOUND` / `REJECTED`,
and no physical approval follows from the endpoint fixture or native trace.

The parent also retained the final native compile/run logs and diagnostic-only
patch, then ran the two native transform tests against the frozen sources. The
retention receipt binds those artifacts to the final O0 receipt; it reports
`py_compile` and shell syntax checks passing. This review read those receipts
and did not rerun their tests.

Scientific approval remains `FAIL_OPEN`; native candidate status remains
`REJECTED`. The solver fixture and native diagnostic do not grant physical
authority.
