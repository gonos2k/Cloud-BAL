# Physical candidate readiness after PR43

Base: `5f51fbbcec8d7908ce4e91f9d59394927348a917`.
This is an execution record for resolving candidate prerequisites, not a
balance candidate or a production permission change. It includes the PR43
conditional ground-reference calculation and a same-support comparison with
retained HT. Physical candidate gates remain separate from these scoped
implementation and reproducibility checks.

## Closed diagnostics and the next physical decision

PR41's matched-layer attribution and PR42's common-reference relative force
are `PASS_SCOPED`. The fixed-basis sample row is
`PASS_SCOPED / MANUFACTURED_STATE_BASIS`. The thickness test's runtime count is
52; no further count correction is needed. External reviewer GNU evidence is
separate from the repository's pinned Intel evidence. The two supplied review
versions have different detailed test inventories, so their counts are not
combined or presented as one new run.

For the same triangle, metric and connected support,

```
a_candidate(p) = a_relative(p) - grad(b)
a_candidate(p1) - a_candidate(p2) = a_relative(p1) - a_relative(p2)
a(k) - a(k+1) = g0 grad(deltaZ(k))
```

Thus a reference choice changes a common horizontal contribution, but cannot
remove the vertical difference. The local two-plane minimax bound is half the
norm of that difference. It is a bound within this declared thermodynamic
change, not a bound on actual model error or a required wind increment.
Independent choices at each triangle also need not be gradients of a single
admissible scalar reference field. The diagnostic gradient is not the balance
multiplier's adjoint operator.

## Actual source values at the retained maximum

The retained maximum triangle 75,455 has nodes 37,889 / 37,890 / 38,125,
or grid locations (54,162), (55,162), (55,163). Values below are copied from
the hash-bound PR41 prepared thermodynamic state and PR39 prepared winds;
no fit, wind rotation, state update or new data assimilation is performed.

| Node (i,j) | PS, Pa | AVG, m | HT at 1000 hPa, m | Raw LSX U10/V10, m/s |
|---|---:|---:|---:|---|
| (54,162) | 100514.0390625 | 0 | 45.0031738 | 0.7121715 / 0.4765435 |
| (55,162) | 100512.09375 | 0 | 45.0161743 | 0.4561372 / 0.7022047 |
| (55,163) | 100510.9296875 | 0 | 45.0882568 | 0.6559613 / 0.6311141 |

At 850 hPa, final minus stage specific humidity is respectively
0 / 2.3635486 / 0 g/kg. At 600 hPa it is 0 / 4.296323 / 0 g/kg (rounded).
The complete collocated profiles are in `scratch/pr43_validation/local_inputs.json`.
These are analyzed state differences, not observed humidity errors. Raw wind
components retain the existing conditional frame status.

The same retained LC3 product has cloud fraction 1 at height indices 2–27
at (55,162), with substantially different neighboring profiles. Those indices
are not pressure levels. `humid/mak_cld_grid.f` maps cloud height using FUA
heights obtained through `humid/getmapsdf.f`; it does not simply use the LT1
height printed above. `humid/cloud_sat.f` applies cloud moistening above a
cloud-fraction threshold, and `lq3_driver1a.f` calls it when eligible. The
retained `moisture_switch.nl` has `CLOUD_SWITCH=1`, and the historical humidity
read inventory includes FUA, LT1, LC3 and LSX.

At PR43 this was source-path and spatial evidence, without a same-case
per-node causal separation. The subsequent PR44
[controlled humidity replay](CLOUD_MOISTURE_CAUSAL_REPLAY_20260923.md) now
isolates the **net late cloud-block effect**, including its final QC
consequence, at the target node. It still does not split the raw
`cloud_sat` call from clipping or certify the humidity change as physically
correct. Do not erase the central humidity change merely because its
relative force is large. Preserve the cloud/observation lineage when defining
which thermodynamic changes a candidate may alter.

## Completed local force localization

The existing Fortran driver was rebuilt in fresh scratch with pinned Intel
O0/O2 at reference pressures 5000 and 100000 Pa. At triangle 75,455 and its
three edge-sharing neighbors (74,988, 75,458, 75,456), all 20 regular levels
from 100000 to 5000 Pa have common support. No surface partial layer is added.
The retained 5000 Pa force and fresh runs agree exactly at those locations;
O0/O2 selected force arrays also agree exactly.

The largest adjacent-layer total force differences at the target are:

| Bottom–top pressure, hPa | Norm of layer force difference, m/s² |
|---|---:|
| 600–550 | 0.004078915590 |
| 650–600 | 0.004035388561 |
| 700–650 | 0.002498404171 |
| 550–500 | 0.002320648376 |
| 850–800 | 0.001876499082 |

Moisture dominates these colocated layer vectors. Their magnitudes must not
be added as vector contributions. An independent Python layer-gradient check
against the Fortran force differences has maximum vector residual
5.70e-18 m/s². Changing the reference leaves the selected adjacent-layer total
force differences unchanged within 4.68e-18 m/s². This closes the bounded
same-location vertical-localization task, not a physical anchor selection.

The 1000–50 hPa target difference has norm 0.0200136176113 m/s²; its conditional
two-plane minimax lower bound is 0.0100068088056 m/s². Neighbor comparisons in
`neighbor_jumps.csv` are contrasts between different triangle centroids and
P1 gradients, not a single-point force discontinuity or a claim that one
common gauge cancels between different horizontal positions.

## Current-source temperature replay

The current temperature target was rebuilt from source at pinned Intel O0/O2,
using fresh objects and the builder-generated verified launchers. Both actual
13 UTC runs returned `LT1_PRODUCER_SUCCESS`; each final LT1 is byte-identical
to the retained 11,715,108-byte file, SHA-256
`3c8a1bf0be2149826a6050101e8371d072e7511be194f66f2c86dcb74a7186dd`.
T3 and HT each match all 1,463,110 float32 cells. The original retained file
is unchanged. Both runs were repeated after removing only the owned scratch
LT1 output and asserting its absence; newly generated files again match.

This resolves the stale-launcher limitation for this fresh temperature build
and case under the declared runtime environment. It does not update or bypass
the historical launcher's stale pin. It does not verify every KLAPS producer,
ON, BALCON or native startup. An initial invocation without the Intel runtime
library environment failed before execution; the successful runs explicitly
source the pinned environment and use the recorded stack/runtime contract.
Build/source/link/runtime hashes and output comparisons are retained in
`producer/comparison.json` and its associated evidence directory.

## Bounded ground-reference option

For the next conditional experiment, keep final T/q and LSX PS fixed. There
is no independently supported covariance here for adjusting the cloud-linked
humidity analysis. A ground anchor `Phi_s = g0*AVG` is an explicit datum and
constant-gravity approximation, not an observed reference geopotential.

The existing constant LSX T2/MR prior supports only the declared 0–10 m layer.
It can connect to the first regular level only where
`p10 <= p_first <= PS`, with continuous valid regular layers to the reference.
Apply that eligibility test before looking at any force or residual; require
all three vertices for a triangle. A first regular level above 10 m needs a
separate lower thermodynamic profile. Extending the prior to it is not covered
by the existing 10 m experiment. The retained maximum's first LT1 height is
about 45 m AGL and cannot be connected by asserting a 10 m height bracket.
Pressure eligibility is audited separately from that inconsistent HT datum.

The hash-bound 13 UTC selection gives 876 of 66,505 nodes and 98 of 131,976
triangles. The first eligible triangle by index is 35,819. No residual or
force criterion is used. At target triangle 75,455, all regular layers reach
5000 Pa, but each `p10` is about 100398–100401 Pa and the first regular level
is 100000 Pa: the thin-layer pressure bracket fails at every vertex. This is
the input-only support inventory, separate from the conditional integration
below. See `ground_anchor/ground_anchor_inventory.json`.

The bounded implementation evaluates, for both states a/f,

```
Phi_a/f(p_first) = g0*AVG + Rd*Tv_surface*log(PS/p_first)
Phi_a/f(p[k+1]) = Phi_a/f(p[k]) + g0*Z_a/f[k]
b_model = Phi_f(p_ref) - Phi_a(p_ref)
deltaPhi_model(p) = b_model + psi(p)
```

It also accumulates the layer changes directly, so the change is not inferred
only by subtracting two large absolute geopotentials. Both computations use
an arithmetic bound based on uncancelled magnitudes. The surface partial
layer is common to both states and cancels from their difference. Therefore
this experiment does not estimate a surface-state change or calibrate that
prior. Prior changes can still alter support, which is frozen before this
calculation.

The regular-layer endpoint model and constant thin-layer model may have a Tv
jump at their junction. This explicit piecewise model is not a measured
continuous thermodynamic profile. Nor is the constructed stage geopotential
the retained HT: the old producer's constants/approximations and datum are
not silently carried into this reconstruction. No HT array is overwritten.

The result remains conditional on the surface datum and partial-layer
representation. It does not resolve missing wind transport, calibrated errors
or candidate boundary authority.

## Lower-source evidence

The retained FUA and FSF form a matched file pair with common navigation and
valid/reference times. The paired reader reverses the pressure order but does
not rotate or regrid wind. FUA HT/U/V must remain one source family. Their
navigation differs slightly from the analysis products; full coordinate and
projection comparison must decide whether this is metadata rounding or needs
explicit mapping. Metadata differences alone do not establish either outcome.

The retained `drag_coef.dat` is not aerodynamic roughness length. The static
builder derives it from terrain slopes, and `frict` uses it as a multiplier in
`fu = ak*uu*abs(uu)*akk` (and the V counterpart). It cannot supply `z0`,
displacement height or a below-10 m wind profile. LSX provides a labeled 10 m
sample; a single sample does not determine its vertical transport profile.
The exact source/artifact hashes and remaining producer questions are in
`lower_prior.md` and `writer_binding.md`. A candidate `lfmpost_wrfv3.exe`
exists, but the searched retained case contains no native WRF input or writer
execution binding it to the retained FUA/FSF hashes. Its current source maps
U10/V10 into FSF; that conditional source connection is not historical proof.
The differing corner metadata are 0–3 float32 steps; this does not establish
full-grid identity or a need to regrid.

## Conditional ground-reference execution

`tests/qbal_ground_reference.f90` constructs the two conditional absolute
geopotential profiles and independently accumulates their temperature,
moisture and total changes. `tests/diagnose_qbal_ground_reference.py` verifies
PR39/PR41 hashes, pressure, time and support before using the original state
and prior. It compiles the small Fortran driver in fresh pinned Intel O0/O2
scratch directories. All output arrays remain NaN outside eligible columns
and their supported levels. An invalid declared input rejects the stream
before opening its result file.

The same 876 columns and 98 triangles pass the input-only selection. On this
support, the reference-pressure change at 5000 Pa has these ranges:

| Contribution | Minimum, m²/s² | Maximum, m²/s² |
|---|---:|---:|
| Temperature | -22.29855305 | +9.20371891 |
| Moisture | -15.18302343 | +41.27600286 |
| Total | -24.17321652 | +49.41959399 |

These are ranges of the constructed model difference, not HT corrections or
reference observations. Extrema in different rows need not be colocated.
The maximum-force triangle 75,455 remains ineligible and receives no result.

Final artifacts: `scratch/pr43_validation/ground_final_v3/`. O0/O2 output
arrays, including unsupported NaNs, are identical. The new unit suite passes
55 assertions at each optimization. Nine stream cases at each optimization
cover a supported column, a gap, and seven malformed-input rejections with no
result file. Existing thickness (52 assertions) and relative-force regressions
also pass with the pinned profile.

An independent 80-digit direct integration of seven actual columns covers
all four first-level pressures and the first eligible triangle. Maximum
absolute differences are 3.73e-11 / 4.87e-11 m²/s² for stage/final Phi and
4.37e-12 m²/s² for their change. This is sampled arithmetic verification,
not a physical error estimate. Separately, adding the new model reference
change to hash-verified retained PR42 relative Phi reproduces the new change
on common support within 1.43e-14 m²/s². PR42 force arrays are not inputs to
the new ground reconstruction.

The partial-layer arithmetic scale includes `Rd*Tv`, because forming PS/p
can round before its logarithm when PS approaches the first level. Scaling
only by the small final partial-layer geopotential would miss that error.
This is an arithmetic comparison allowance, not a physical uncertainty.

Reproduction (run from the worktree, with a new output directory):

```bash
bash tests/run_qbal_ground_reference_tests.sh
python3 tests/diagnose_qbal_ground_reference.py \
  --thickness-dir /path/to/pr41/final \
  --geometry-dir /path/to/pr39/final \
  --output-dir scratch/ground_reference_replay
```

## Required candidate decisions

The PR44 [same-support retained-HT comparison](CONDITIONAL_GROUND_HT_COMPARISON_20260923.md)
separates the constructed stage defect from the final T/q change at 17,182
supported node-level values. Their RMS values are 163.955 and 8.832 m²/s²,
respectively. These are different terms in the identity leading from retained
HT to the conditional final profile; neither is an authorized HT adjustment.
The target maximum-force triangle remains unsupported by the 10 m bracket.
The PR44 [cloud-switch replay](CLOUD_MOISTURE_CAUSAL_REPLAY_20260923.md)
reproduces retained LQ3 byte-for-byte with cloud ON. At `(55,162)`, ON–OFF
accounts for the entire 850–500 hPa stage-to-final humidity increase; the
1000–900 hPa increase belongs to earlier humidity processing in this replay.
This is causal source attribution, not permission to change the analyzed
moisture or its error covariance.

The PR45 [same-case force link](PR45_SCOPED_FORCE_LINK_20260923.md) applies
the common PR42 triangle metric to `S`, direct T/q change `D`, and their sum
on the 98 ground-supported triangles. Separately, it evaluates the cloud
ON–OFF relative force at triangle 75,455 with final T held fixed. These
diagnostics use different supports and gauges. They do not supply the missing
physical datum, lower transport, or a joint balance candidate.

| Quantity | Current evidence | Condition before changing a state |
|---|---|---|
| Reference geopotential b | PR42 only fixes a diagnostic gauge | Accepted height/geopotential datum plus a complete supported hydrostatic path, including the surface partial layer, common EOS/operator and gap policy |
| Final T/q | Actual final LT1/LQ3 and stage difference are bound; cloud-linked structure is present | Declare fixed vs adjustable variables and independently supported errors; no removal selected by force magnitude |
| Lower wind coefficients | Manufactured basis works; actual low-level source family remains conditional | Bind location, physical height, frame, prior and shared-analysis errors |
| 0–10 m transport | Missing strip remains explicit | Actual surface-layer model/data with parameters and representation limits; no residual-matching fill |
| Finite-top transport | LW3 omega is derived from analyzed wind | Declare dependent prior/constraint role, not an independent duplicate observation |
| Actual joint candidate | None approved | Same geometry, time contract, full fluxes, admissible increments and observation compatibility |

The retained fixed-face incompatibility is not removed by choosing a different
optimizer. The above conditions must define the changed physical problem
before a new solve. Numerical diagnostics already closed by PR42 remain closed;
missing physical evidence is tracked separately.

## Execution receipts

The current isolated worktree uses `scratch/pr43_validation/` for:

- `local_inputs.json`, `local_cloud.json`: raw collocated state/product values
  and source hashes.
- `local_force/`: pinned Intel evaluation of the same triangle and its
  edge-sharing neighbors, with layerwise temperature/moisture contributions.
- `lower_prior.md`, `candidate_contract.md`: source/authority investigation.
- `ground_anchor/`: frozen pressure-bracket and connected-support inventory.
- `ground_final_v3/`: final conditional ground integration, source/input hashes.
- `publish/independent_ground_final.json`: sampled high-precision and retained
  relative-geopotential comparisons; `publish/stream_final_O0` and
  `publish/stream_final_O2`: stream rejection evidence.
- `producer/`: fresh current-source temperature build and verified-launcher
  same-case replay evidence.

Only completed results are promoted in the checklist. The PR reports the
scoped implementation and evidence; no operational input update, BALCON solve,
ON product, native startup or forecast follows from this record.
