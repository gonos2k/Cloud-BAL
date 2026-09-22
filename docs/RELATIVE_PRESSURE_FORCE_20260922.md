# Common-reference relative geopotential and pressure force

## Diagnostic question and reference

PR41 separated final temperature and moisture changes into matched-layer
geopotential-height thickness changes. This study connects those same layer
changes to a pressure-surface horizontal gradient. It does not modify HT,
PS, temperature, humidity or wind, and it does not generate a balance candidate.

For the retained single 13 UTC case, choose the shared regular pressure
`p_ref=5000 Pa` and explicitly set `deltaPhi(p_ref)=0`. The relative field is

\[
 \delta\Phi_c(p)-\delta\Phi_c(p_{ref})
 = R_d\int_p^{p_{ref}}\delta T_{v,c}\,d\ln p,
 \qquad c\in\{T,q,total\}.
\]

The finite top is a **diagnostic reference**, not an approved fixed-height
physical boundary. Below that reference the integral is negative for a
positive thickness change. In descending pressure storage,

\[
 \delta\Phi_c(k)=\delta\Phi_c(k+1)-g_0\delta Z_c(k).
\]

The kernel also supports an interior reference and integrates upward with the
opposite recurrence. It starts only at a valid reference node and traverses
adjacent supported layers. A gap stops that direction; disconnected values
remain NaN. The reference itself can be known even if all neighboring layers
are unsupported. No differently truncated column sum is differentiated.

PR41 thickness input uses the same specific-humidity gas model and endpoint
integrands in ln(p). The new calculation preserves that discrete definition;
it does not redo historical HT generation or change its constants/lookup.
All three components have the same reference and support, so their relative
fields and their linear gradients retain the temperature-plus-moisture sum.

## Pressure gradient and physical metric

Use the retained NE57 static latitude/longitude and the same southwest-to-
northeast triangular mesh as the earlier shared-face research. Coordinates
are reconstructed by the existing `equal_area_point` procedure:

\[
 x=R\cos\phi_0(\lambda-\lambda_0),\quad
 y=R(\sin\phi-\sin\phi_0)/\cos\phi_0.
\]

At one fixed pressure, all three vertices must be connected to the common
reference. Define the relative scalar field to be affine over that triangle.
Its chart gradient is obtained from the two vertex difference equations.
For the chart centroid, recover latitude by

\[
 \phi_c=\arcsin(\sin\phi_0+\bar y\cos\phi_0/R).
\]

The reported physical east/north acceleration contribution is

\[
 \delta a_E=-\frac{\cos\phi_0}{\cos\phi_c}\partial_x\delta\Phi,
 \qquad
 \delta a_N=-\frac{\cos\phi_c}{\cos\phi_0}\partial_y\delta\Phi.
\]

These are covector/gradient metric factors, not the physical wind recovery
factors and not chart-coordinate second time derivatives. No grid-wind
rotation is needed for a scalar geopotential gradient. Output units are
m²/s² for deltaPhi and m/s² for the physical acceleration. The chart gradient
and the evaluation latitude are retained separately. Affine reconstruction
is a declared spatial approximation, not exact representation of arbitrary
atmospheric structure; metric variation within a triangle is represented at
its centroid only.

## Missing reference force and interpretation

For an actual reference change `b(x,y)=deltaPhi(p_ref,x,y)`,

\[
 \delta\mathbf a_{physical}(p)
 =\delta\mathbf a_{relative}(p)-\nabla_p b.
\]

The missing reference contribution is not inferred from thickness. A spatially
constant b changes no gradient. A horizontally varying b changes every
pressure-level gradient while leaving every vertical thickness difference
unchanged. Manufactured checks exercise this distinction. The reported
zero-reference result is therefore neither the complete actual pressure-force
change nor a diagnosed spurious model acceleration or observed wind error.
Pressure-level force differences relative to the same reference are the
quantity specified by this experiment.

Adding only deltaZ to legacy HT would preserve the old stage residual under
the PR41 operator. Reconstructing an entire hydrostatic state under a new
operator is a different problem. Neither operation is performed here. No
geostrophic conversion or suppression of convective convergence is used.

## Source binding and arithmetic checks

The preparation reads PR41's hash-pinned `arrays.npz` and report, and PR39's
hash-pinned prepared geometry. PR41's source-report hash must equal the selected
PR39 report hash; pressure values, central valid time and every LSX PS value
must agree exactly. The existing prepared reader validates the mesh incidence,
vertex indices and pressure order. The reused geometry is the same retained
case, not a newly interpolated grid. No wind or omega field participates in
this force calculation even though they occur in the source prepared stream.

The Fortran driver validates dimensions, exact byte extent, masks, above-ground
support, finite supported layers and nondegenerate triangle geometry before
creating output. Unsupported field entries remain NaN. Python independently
reconstructs connectivity to the reference and checks all support and NaN
patterns. Physical force is present only when all three endpoint paths are
available at that same pressure.

The arithmetic checks propagate PR41's layer allowances along supported paths,
then scale by the triangle gradient coefficients and chart metric. Additional
terms retain uncancelled geopotential and coordinate-subtraction magnitudes.
This is a conservative diagnostic comparison allowance, not a rigorous error
certificate, observation sigma or physical force tolerance. Both O0/O2
agreement and temperature-plus-moisture closure use it.

## Execution and remaining scope

Actual-case results and the final source receipts are recorded below after the
pinned Intel runs. The prior retained-producer capture remains conditional;
this calculation does not repair the verified launcher's builder pin. Native
mass, momentum, moisture/latent heat, startup and forecast behavior remain
unvalidated. The lower-state-basis experiment is separate and supplies no
actual lower prior or new physical boundary authority.

## Retained actual13 results

The common 5000 Pa reference connects **1,294,999 node-levels** and supports
**2,564,603 triangle-levels**. Counts include the zero reference level, not
new independent observations or full physical columns. The 110000/105000 Pa
planes have no above-ground support. All 66,505 nodes and 131,976 triangles
are supported at 75000 Pa and smaller pressure; low-altitude coverage is
more restricted. Missing terrain-cut intervals remain missing.

Selected levels, unweighted statistics over their own supported triangles:

| Pressure, Pa | Supported triangles | Maximum relative acceleration magnitude, m/s² | RMS magnitude, m/s² |
| ---: | ---: | ---: | ---: |
| 100000 | 79,778 | 0.02001361761 | 0.001079835185 |
| 95000 | 113,876 | 0.01974929392 | 0.000912312971 |
| 90000 | 128,376 | 0.01963145931 | 0.000829787918 |
| 75000 | 131,976 | 0.01514426478 | 0.000570706309 |
| 50000 | 131,976 | 0.007032790994 | 0.000344696325 |
| 25000 | 131,976 | 0.000383464298 | 0.000003656282 |
| 5000 | 131,976 | 0 | 0 |

The final row follows from the chosen zero reference; it is not evidence that
the physical upper boundary has zero force change. Different levels have
different spatial support, so changes in their summary statistics are not
an equal-domain vertical comparison. No time interval multiplies these
accelerations to manufacture a wind increment.

At 100000 Pa the maximum total occurs in Fortran triangle 75,455, with
vertices 37,889 / 37,890 / 38,125. The colocated east/north components are:

| Contribution | East, m/s² | North, m/s² |
| --- | ---: | ---: |
| Temperature | +0.0002301793533 | -0.0002482113572 |
| Moisture | +0.0145432778783 | -0.0132532645368 |
| Total | +0.0147734572316 | -0.0135014758940 |

The vector components add. Their magnitudes generally do not. The maximum
magnitude is a spatial-gradient diagnostic under the declared reference and
piecewise-affine model, not an observed acceleration error, a correction
request or a forecast prediction. The 100000 Pa relative total deltaPhi range
is -94.16173033 to +24.19179156 m²/s². The negative sign at a positive
thickness increase is expected when integrating downward from a fixed top.

The chart parameters retained from the earlier geometry are latitude0=38°,
longitude0=126°, and sphere radius 6,371,200 m. This calculation uses that
explicit sphere; it does not claim an ellipsoidal/native WRF metric.

## Reproduction and validation evidence

Run from the isolated Cloud-BAL checkout. The retained source directories are
absolute paths so a different current working directory cannot select another
case accidentally:

```bash
python3 tests/diagnose_qbal_relative_force.py \
  --thickness-dir /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/pr41_thickness_20260922/Cloud-BAL/scratch/pr41_validation/final \
  --geometry-dir /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/pr39_profile_20260922/Cloud-BAL/scratch/pr39_validation/final \
  --reference-pressure-pa 5000 \
  --output-dir scratch/pr42_validation/final
bash tests/run_qbal_relative_pressure_force_tests.sh
. tests/intel_toolchain.sh
python3 tests/test_qbal_relative_force_prepared.py \
  scratch/pr42_validation/final/O0/diagnose \
  scratch/pr42_validation/final/O2/diagnose \
  --artifact-dir scratch/pr42_validation/prepared_final
```

Both output directories must be new. The CLI compiles the Fortran driver in
fresh scratch using the pinned Intel profiles, then checks input/source hashes,
reference connectivity, unsupported NaNs, component closure and O0/O2 agreement.
The unit runner covers seven scenarios: affine gradient/metric, a spatially
varying reference shift, coordinate translation/orientation reversal,
reference-direction signs, disconnected/isolated support, unknown reference,
and invalid inputs. The unit runner and prepared-stream harness are separate
validation steps.
Scratch-only downward-sign, east-metric-reciprocal and gap-bridge mutations
are all detected at O0/O2. The prepared harness passes **30 cases across O0/O2**: five normal support/reference
configurations and ten malformed streams per build. Rejected streams do not
create an output file. Its manufactured force oracle solves an independent
3-by-3 affine system on explicitly declared chart coordinates.

In the retained actual replay, the largest closure-to-arithmetic-bound ratios
are 0.002218890 for relative geopotential and 0.001733180 for acceleration.
The O0/O2 maximum differences for both quantities are exactly zero in this
execution. This does not promise bitwise equality on another compiler/profile.
The actual replay uses the prior hash-bound prepared arrays; it does not rerun
raw NetCDF preparation, the HT producer, BALCON, native startup or a forecast.

Evidence lives in the PR42 source worktree under `scratch/pr42_validation/`:

- `final/report.json`, `final/arrays.npz`, and `final/{O0,O2}/result.bin`:
  source/input hashes, support, per-level colocated results and compiler outputs.
- `prepared_final.log` and `prepared_final/`: manufactured stream cases.
- `kernel_review.md`, `geometry_audit.md`, `independent_review.md`, and
  `basis_review.md`: focused implementation, geometry and team reviews.
- `validation.json` and `team_review.md`: frozen changed-file hashes and the
  consolidated validation/review record.

The related state-basis experiment is described in
[PROFILE_STATE_BASIS_20260922.md](PROFILE_STATE_BASIS_20260922.md). Neither
experiment supplies a physical lower prior, a reference-height adjustment,
a calibrated covariance or production permission.
