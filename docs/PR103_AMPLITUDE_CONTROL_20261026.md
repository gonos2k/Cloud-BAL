# PR103 amplitude matched control

This control preserves the structured N field and adds a single comparison arm
whose free-face wind increment has the same norm as the actual stored N−H
increment. H, P, and N mean the byte-read REAL32 HYDRO, PROJECTED, and
STRUCTURED fields. The support, native fixed carrier, exterior zeros, and
additional-change budget come from the existing PR99/PR102 receipts.

The frozen policy in `docs/evidence/pr103_amplitude_control_20261026/policy.json`
defines

\[
s = \frac{\lVert N_{stored}-H_{stored}\rVert_2}
         {\lVert P_{stored}-H_{stored}\rVert_2},\qquad
A^* = H_{stored}+s(P_{stored}-H_{stored}).
\]

One scalar is applied to all free U/V faces and native levels. Fixed faces,
including the exterior, remain H. The ideal REAL64 formula is cast once to
REAL32. The stored readback norm may differ from the target because of
quantization; the pre-write tolerance is the L2 half-ULP envelope at the ideal
control plus the declared norm arithmetic bound. The builder records the
observed mismatch and does not adjust `s` to make it vanish.

For the equality reference, reconstruct the continuous PR99 projection
`Pcont = H + bP` using the existing PR102 reconstruction and its original
byte-match check. `H+s(Pcont-H)` inherits `A_k b_k=0`; the actual stored-P ideal
can differ from that reference. Bound the difference by
`s ||Pstored-Pcont||₂` plus the REAL32 half-ULP storage envelope and arithmetic
bound. Report the continuous reference and stored readback residual separately;
do not claim exact zero residual for the stored field. Existing archived native
consumer gates determine stored admission.

`tools/pr103_amplitude_control.py` implements the array math and a receipt-bound
NetCDF proposal CLI. It checks the PR99 and PR102 source identities, closed
STRUCTURED run input binding, inherited support, P/N equality to H outside free
faces, continuous projection reconstruction, old Δ budget, exact changed
variable contract, and input hashes before and after writing. The actual frozen
candidate is recorded below. It introduces no
solver, weight, model, or prior. The proposal status remains fail-open, with
observation skill not evaluated.


## Actual frozen control construction

One control file was produced in fresh external scratch; no source or input
pin changed during construction. Its SHA-256 is
`9038d0a26896a630b7048091a97a2c0055b26934513392195eb8e609626e74e2`.
The immutable [proposal](evidence/pr103_amplitude_control_20261026/generation/wrfinput_d01.proposal.json)
SHA-256 is `93821aa86b188a91a7f43de9e6c5d49815bde71fe92faa7a59cc3a340c78057f`.

| Input/readback quantity | Value |
|---|---:|
| Single global scale s | 0.7428606748807538 |
| Stored N−H target norm | 75.13531285394339 m/s |
| Ideal A−H norm before REAL32 | 75.13531285394340 m/s |
| Actual stored A−H norm | 75.13531243410655 m/s |
| Pre-write norm mismatch allowance | 0.00003882944062713 m/s |
| Stored A distance to continuous PR99 P | 26.00789676548 m/s |
| Inherited additional-change budget | 30.38133607225 m/s |
| Actual stored A to scaled continuous reference distance | 0.00002787196371023 m/s |
| Pre-write continuous-reference distance allowance | 0.00005513277705472 m/s |

These are equal-free-face aggregate velocity norms across both components and
all levels, not mean wind speeds or kinetic energy. The observed stored norm
mismatch is about −4.20×10⁻⁷ m/s; s was not adjusted after storage.

The same geometric G gives stored R(P−H)=18,681,276.8343485,
stored R(N−H)=7,808,150.6684431 and stored R(A−H)=10,309,112.7782238
in the previously declared geometric functional units m³/s². The ideal
uniform-scaling prediction s²R(P−H)=10,309,112.8398685 is recorded separately
from stored A. The small difference reflects stored-input representation and numerical
evaluation; no field correction is applied.

Precision-label clarification for the preserved PR102 summary: its
`roughness_amplitude_decomposition.functional_before` reused the proposal's
`roughness_before`, which is the continuous PR99 center (18,681,276.7807049),
although the surrounding summary discussed stored increments. PR103 computes
R on the actual stored P readback directly. The difference is about 0.054
functional units (2.9×10⁻⁹ relative); it does not change the stated structure
comparison at the reported precision. The original PR102 artifacts remain
unchanged. This construction alone does not attribute forecast response to
structure or amplitude; the separate matched comparison is recorded in
[the time-response analysis](PR103_TIME_RESPONSE_20261026.md).

Construction and the archived native consumer check are complete. The reference
constraint and source-arithmetic gates each have zero pointwise exceedances;
their observed L2 residuals are about 5.19×10⁻⁵ and 7.06×10⁻⁵ Pa/s, against
the predeclared 0.06556 Pa/s bounds. The second receipt uses the final strengthened
receipt validator and reproduces the first WW output byte for byte. This is a
stored-field admission check, not a forecast result. The separate matched C2
run completed 640 seconds and 32 steps; its [execution record](PR103_EXECUTION_20261026.md)
preserves the distinct procedural, source-policy, and generic audit results.
Physical approval remains FAIL_OPEN and independent
observation skill remains NOT_EVALUATED.
