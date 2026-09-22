# Fixed state basis and explicit pressure sample operator

## Bounded implementation

A piecewise-linear pressure profile is a state representation,

\[
 v(p)=\sum_l c_l\phi_l(p),\qquad y=a(p_s)^Tc+e.
\]

The coefficient c at a basis knot is not automatically an observation at that
knot. The new public `profile_sample_row` in
`tests/qbal_profile_reconstruction.f90` exposes the existing two-weight
interpolation row without changing its mathematics. The original
`fit_profile_sample` calls that same row, so there are not two competing
sampling implementations. Pressure-domain validation belongs to that row
procedure; the fit validates its wind and variance inputs. Out-of-domain
samples reject without extrapolation;
invalid rows remain NaN.

This is a small research interface, not a new generic assimilation framework.
It does not supply an actual lower-state coefficient, infer a covariance or
route a new profile into the actual-domain transport driver.

## Manufactured lower-domain experiment

The tests explicitly distinguish state knots from the narrower set of
pressure samples. A declared state basis can extend below the lowest
manufactured pressure observation because its lower coefficient and variance
are explicitly supplied as a **manufactured prior**, not copied from a finite
underground LW3 value. A sample within that state range can therefore be
represented even when it lies outside the observation-knot range. A sample
outside the declared state range still fails.

The experiment retains the fixed positive C/R objective of PR39, fits an
endpoint once and integrates that same fitted profile. It checks partition
of unity, affine sampling, knot/lowest-observation-boundary transitions,
conflicting sample values and cap-independent integration. Exact repeated
sample assimilation is not introduced; no updated posterior is mistaken for
an independent original prior.

Fixed-basis continuity does not prove continuity under a changing physical
support set. In particular this experiment does not justify adding a basis
coefficient when terrain moves across a level without specifying how its
prior and sampling operators change. An unsupported actual lower state is
still unsupported after this interface is available.

## Actual-source status

The existing source-family separation in
[Lower-profile domain design](LOWER_PROFILE_DOMAIN_DESIGN_20260922.md)
remains unchanged: LW3/LT1, FUA/FUA and LSX lower analyzed samples have distinct
height, frame, time and shared-analysis error contracts. No new actual C/R,
0–10 m transport, full column residual or physical balance forcing is produced.
Numerical success here is `PASS_SCOPED / MANUFACTURED_STATE_BASIS`, while
actual domain expansion remains `DESIGN_ONLY / NOT_AUTHORIZED`.

## Validation

Pinned Intel O0/O2 fresh scratch builds pass the 20 new basis checks, the
35 existing reconstruction checks and the 49 existing shared-face checks.
The refactor preserves the original fit/face regression expectations. The
manufactured test uses a 98000 Pa sample below the lowest-altitude 95000 Pa
observation knot but inside the explicitly supplied 100000 Pa state domain;
this is not an actual underground-value fill. Its crossing experiment keeps
that state domain and prior fixed.

Run `bash tests/run_qbal_profile_basis_tests.sh`,
`bash tests/run_qbal_profile_reconstruction_tests.sh` and
`bash tests/run_qbal_profile_face_tests.sh` from the PR42 worktree.
The run directories and hashes are in `scratch/pr42_validation/basis_review.md`.
PR41's thickness test now counts assertions at runtime: **52**, at both
optimization levels. The previous manual 54 count is corrected without
changing that numerical kernel.
