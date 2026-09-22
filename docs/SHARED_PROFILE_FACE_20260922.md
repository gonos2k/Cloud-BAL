# Endpoint profiles on a shared pressure face

## Model and supported domain

This research path reconstructs each endpoint once, then defines the face
interior by linear interpolation of those two fixed profiles. It does not fit
again at quadrature points. The endpoint fits reuse PR39's explicit diagonal
variance objective, separately for the two chart velocity components.

All supplied pressure knots must lie in the common above-ground pressure
interval: `p(1) <= min(PS_left, PS_right)`. Both sample pressures must lie inside
the fixed knot domain, with pressure strictly greater than the finite top pressure. The helper refuses
out-of-domain samples. It neither invents an additional lower knot nor uses an
underground pressure-level wind to cover a gap.

These are computational pressure-domain checks, not certification of the HT
datum, wind-height mapping, source frame or error model. Actual input lineage
and those remaining qualifications are recorded with the selected face.

For fitted endpoint profiles the face model is

\[
 \widehat{\mathbf v}(s,p)
 =(1-s)\widehat{\mathbf v}_L(p)+s\widehat{\mathbf v}_R(p),
 \qquad p_{10}(s)=(1-s)p_{10,L}+s p_{10,R}.
\]

The oriented transport is

\[
 F=\int_0^1\int_{p_t}^{p_{10}(s)}
       \widehat{\mathbf v}(s,p)\cdot[\Delta y,-\Delta x]\,dp\,ds.
\]

Existing `edge_wind_flux` splits where the sample-pressure line crosses a knot.
In each segment the pressure integral is quadratic in s and multiplication by
the endpoint interpolation weight makes the integrand at most cubic. Two-point
Gauss integration is therefore exact for this declared model, up to arithmetic
roundoff. This argument would not apply to independently refitting at each s.

No cap enters the reconstruction. A constant cap below both sample pressures
only partitions the integral of the same profile. Passing the partition through
a knot cannot replace the model on a finite interval.

This continuity statement fixes the knot set and error model. It does not
certify continuity when an operational support selector adds/removes knots as
the ground changes. The actual experiment freezes one valid face domain at one
time; crossing its boundary is an explicit unsupported case, not a new cap.

## Shared transport and unknown lower layer

One oriented F is consumed with opposite signs by the two incident cells.
Face reversal swaps coordinates, profiles, sample values and variances together.
It reverses F; the pressure span below the samples keeps its sign and magnitude.

The helper returns

\[
 \overline{\Delta p}_{\mathrm{missing}}
 =\tfrac12[(p_{s,L}-p_{10,L})+(p_{s,R}-p_{10,R})].
\]

This is a mean pressure span, not a missing flux or an uncertainty bound. The
0–10 m wind transport remains unknown. A successful fit and integral do not
make the full face, column or domain physically complete.

The new procedure commits its fitted profiles, innovations and flux only after
the entire face succeeds. Failed calls return NaN outputs. Input knots, source
winds and supplied variances remain immutable.

## Conditional actual-data experiment

The experiment selects one internal face by input-domain eligibility and index,
before considering fitted transport or any column/domain residual. No actual
variance calibration is available. The predeclared research scenarios use
unit diagonal variance for the chart U/V knot values and sample variances
0.25, 1 and 4 in the corresponding squared chart-velocity units. These define
three explicit sensitivity objectives, not observational covariance estimates.
There is no selection of a preferred ratio based on budget closure.

The models omit cross-covariance between LSX and LW3 and between components.
Chart velocity is not an isometric physical wind norm. Thus the supplied
numbers are neither physical kinetic-energy weights nor production increment
limits. The experiment cannot establish optimal atmospheric estimation.

Only the source-supported common knot range is tested. Most faces may remain
outside that domain; a successful selected example does not grant them a lower
prior or authorize extrapolation. The original lower-transport replay remains
`CAP_DEPENDENT_LEGACY_EXPERIMENT / NOT_AUTHORIZED_FOR_PHYSICAL_PROFILE`.

## Validation and retained evidence

The actual experiment uses the hash-pinned PR39 thermodynamic prepared replay.
The full input inventory contains 198,480 faces:

| Input-domain condition | 12 UTC | 13 UTC | 14 UTC |
|---|---:|---:|---:|
| Existing common knots contain both sample pressures | 462 | 425 | 363 |
| Also HT above AVG and strictly increasing upward | 364 | 348 | 314 |
| Also internal and both first HT intervals bracket 10 m | 83 | 90 | 70 |

Only two faces pass all three conditions at all three times. Selection for this
experiment is instead the lowest-index eligible internal **13 UTC** face,
before reading any fitted transport. It is face 21,193 (Fortran numbering),
with nodes 7,007/7,242 and incident triangles 13,953/13,956. The selected face
does not satisfy the same conditions at every time; this is not a new interval
budget. The pressure and HT tests do not certify a common absolute height datum.

Its endpoint PS is 100,020.5234375 / 100,034.7578125 Pa, and the conditional
thermodynamic p10 is 99,907.29588464522 / 99,921.4277779061 Pa. Twenty existing
knots span 100,000 to 5,000 Pa. At the highest-pressure knot, HT minus AVG is
5.695556640625 / 2.9529876708984375 m; at the next knot it is
457.2567138671875 / 454.37657165527344 m. No new underground knot is supplied.
Raw LW3/LSX winds are rotated and converted to chart rates in Fortran under the
previously declared conditional grid-relative source contract. An independent
inverse diagnostic recovers the raw endpoint winds. This checks implementation,
not the historical producer's unverified frame metadata.

| Sample variance R, with C=I | Fitted sample-to-top transport (m² Pa/s) | Maximum chart-component knot change (m/s) |
|---|---:|---:|
| 0.25 | 1,207,520,345.965622 | 0.23332966 |
| 1 | 1,208,496,693.376257 | 0.14420931 |
| 4 | 1,209,452,888.374504 | 0.05704930 |

The original fixed-knot profile integrated over the **same** sample-to-top
interval gives 1,210,079,463.821028 m² Pa/s. It is not the old cap-dependent
transport. None of the three variance scenarios is preferred by a budget
criterion. Chart-component changes are not physical speed-increment approval.
The unresolved mean PS-to-p10 span is 113.2787937243411 Pa in every scenario.
Full column/domain residuals remain null; no 0–10 m wind is invented.

The new Fortran suite passes 49 checks at each pinned Intel O0/O2 level,
including nonzero unequal-endpoint transport, sample-knot continuity, explicit
piecewise-knot exact integration, input immutability and transactional NaN
failure. Replacing the sample-pressure bound with PS and erasing the unresolved
span are both rejected at both optimization levels (four mutation runs).
Six malformed topology cases and four prepared-input faults at each level
are also rejected (14 input checks).

Pinned Intel O0/O2 actual replay checks endpoint reversal, fixed-profile partitioning
at the second knot ±0.001 Pa, and the same stored flux consumed by opposite
incident-cell signs. The study driver explicitly requires that this partition
lie above the finite top and below both sample pressures; the general module
has no such second-knot restriction. The driver also pins C=1 and R=0.25/1/4,
so prepared input cannot silently change the documented research sweep.
Maximum partition discrepancy is 2.3842e-7 m² Pa/s; reversal discrepancy is zero;
volume-weighted shared contribution discrepancy is 1.8951e-7 m² Pa/s. The
0.07764 m² Pa/s arithmetic allowance uses uncancelled length, pressure, velocity
and summation scales. It is neither a physical residual tolerance nor sigma.

Run from the isolated PR40 checkout:

```sh
bash tests/run_qbal_profile_face_tests.sh
python3 tests/diagnose_qbal_profile_face.py \
  --source-dir /path/to/pr39_validation/final \
  --output-dir scratch/pr40_validation/new_replay
```

Retained evidence is under
`Cloud-BAL/scratch/pr40_shared_profile_20260922/Cloud-BAL/scratch/pr40_validation/`
relative to the KLAPS50 workspace. `final_checked/report.json` pins source and inputs,
`final_checked/domain.json` records eligibility and selection, and `final_checked/result.npz`
contains fitted endpoints and transport. `validation.json` and `team_review.md`
record test/review outcomes. `actual_v1/` and `final/` are intermediate evidence, not the final
source receipt. No large raw artifacts are committed.

## Same-stage HT replay

A separate scratch-only actual13 temperature-producer replay captures T just
after `insert_tobs`, background SH and pressure, then HT immediately after
`get_heights_hydrostatic`, before surface-temperature insertion. Source changes
are stream writes only; maintained producer source and operational inputs are
unchanged. The captured HT matches retained LT1 HT across all 1,463,110 cells,
and final LT1 is byte-identical with SHA-256
`3c8a1bf0be2149826a6050101e8371d072e7511be194f66f2c86dcb74a7186dd`.
Captured SH matches the selected FUA background SH. This closes the previous
absence of a captured same-stage T/SH state for this retained case.

T after `insert_tobs` differs from background T by at most 2.2265319824 K;
final T differs from that captured analyzed state by at most 3.6073608398 K.
These distinguish analysis-stage changes from later temperature changes. They
do not assign the surface datum residual to one cause, certify HT/AVG/PS
collocation, or quantify final LQ3 moisture's hydrostatic thickness effect.
That last same-state versus final-state thickness attribution remains OPEN.

The scratch object was compiled using the pinned Intel profile and linked with
hash-retained producer objects/libraries. A direct retained-binary control and
the instrumented executable both reproduce the retained LT1 when run with an
unlimited stack; both fail with the inherited 8 MiB stack. The existing verified
launcher refuses its stale `build_upstream_producer.sh` hash, so this evidence
is **conditional retained-binary/output reproduction**, not current full-source
verified-launcher closure. The stale pin is not silently updated or bypassed
in an authorized production launcher. The short scratch runroot preserves the
legacy path-length contract and actual13 PIN absence. Logs, source diff, hashes,
commands and comparisons are retained in `ht/` beside the face evidence.

No production D/G, solver, RHS, mask, boundary authority or speed limit changes.
No balanced ON candidate, native startup or forecast approval is claimed.
