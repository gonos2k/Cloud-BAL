# PR74 actual-driver QNI and common moment comparison

The preserved PR73 common audit remains at
[`receipt.json`](evidence/pr74_common_moment_audit_20261008/receipt.json).
This comparison applies the same trace parser and common Q/N/B audit to both
actual-driver QNI O0/O2 pretraces, using each run's own pre-microphysics
geometry. The O0 and O2 pretraces and geometry captures are byte-identical;
the stage-1 pretrace differs from PR73. The 100 staged input hashes remain
unchanged.

The actual driver records QNC and QNI enabled at `(i=133,call_lat_index=2)`,
39 returned state levels, 39 single tendency additions to `scalar_tend`, and
`DRIVER_BRANCH_COMPLETE`. The following KDM6 call exits 128 at
`KDM6 invalid NI number basis input`, before common paired-state preflight.
No completed timestep or post-call physics capture exists.

The input pretrace has **0 negative and 0 nonfinite NI cells** across 2,533,440
active cells. Public NI is number per kg dry air; KDM6 converts it to number
per m3 with `NI_internal = NI_public * rho_d`, where
`rho_d = DEN/(1+Q)`. The common audit’s hypothetical earliest pair mismatch
changes from PR73 ice mass-only at `(133,2,1)` to ice moment-only at `(104,2,1)`
with `QI=0` and `NI=3.8173049035872155e-36 kg-1`. This is an input-state
classification; it is not the observed fatal location.

Source-order conversion (`j,k,i`, then `NC,NI,NN,NR`) identifies the first
subnormal product at NI `(211,2,15)`: public NI is `1.356338643876034e-38
kg-1`, `rho_d=0.7680497765541077 kg m-3`, and the gradual-underflow product is
`1.041735647987705e-38 m-3`. At this cell NC converts to a normal valid value
before NI. The exact receipt-bound source helper returns nonzero/valid under
the pinned strict no-FTZ O0 and O2 profiles. With `-ftz`, it returns zero and
invalid at this same NI value. The durable QNI driver evidence records `-ftz`
in both final O0/O2 link commands; runtime MXCSR itself was not captured. The
trace has 2,399 NI products and 4,331 NC products that would be subnormal under
gradual arithmetic across the full active tile; these are potential FTZ zeros,
not cells observed after the run stopped at the first failure.

The QNI pretrace changes NC in 1,675,415 cells and NI in 966,757 cells. It also
has smaller changes in TH, PII, DEN, P, DELZ, Q, QC, QR, QI, QS, NN, and NR.
Same-call geometry bounds and KDM6 duration match. Relative to the PR73
geometry capture, the new capture changes 100 MU2 values by at most
`3.9673e-4`; scalar headers match.

The common audit counts, maxima, and same-carrier scales are in
[`actual_driver_comparison.json`](evidence/pr74_common_moment_audit_20261008/actual_driver_comparison.json).
The exact-source Intel conversion replay and hashes are in
[`ni_conversion_probe.json`](evidence/pr74_common_moment_audit_20261008/ni_conversion_probe.json).
Neither artifact establishes producer correctness, water or energy closure,
or native physics completion.

The conversion replay sources, exact expanded commands, and four compiler
outputs are retained under
[`ni_conversion_probe/`](evidence/pr74_common_moment_audit_20261008/ni_conversion_probe/).
The strict O0/O2 runs use the pinned profile. The `-ftz` runs append the
captured native link flag as a sensitivity replay and are not represented as a
separate compiler profile. The final QNI link commands both include `-ftz`;
runtime MXCSR was not directly captured.
