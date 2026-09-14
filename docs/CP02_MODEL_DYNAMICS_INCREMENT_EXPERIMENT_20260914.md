# CP02 model-dynamics increment experiment

Status: retained comparison experiment; superseded as the production generation
plan by the diagnostic mass-continuity scope, 2026-09-14. This is a separate
research contract from the observational target/sigma experiment in
[CP06-A v3](CP06_A_EXPERIMENT_SPEC_20260816T130000Z.md). CP02 requirement 4 remains
open. Numerical completion does not establish forecast skill or operational
approval.

## User scope correction — external model dependency removal

The user clarified that the intended replacement must remove dependence on an
external model or externally produced omega target. Porting the WRF-history
producer from Python to Fortran does not meet that goal and is cancelled.
Retain this experiment as bounded comparison and native-transport evidence;
it is not the production cloud-omega generation architecture. The next physical
operator must calculate omega inside Cloud-BAL from the existing Barnes winds,
observations, cloud/hydrometeor and thermodynamic inputs, with explicit equations,
boundaries and conservation checks. No external trajectory becomes a required
runtime input through this experiment.

## Current implementation scope — diagnostic mass continuity

Added scope, 2026-09-14: follow the
[multi-radar localized balanced-initialization plan](https://github.com/gonos2k/Cloud-BAL/blob/docs/cp02-multiradar-balanced-init-20260914/docs/CP02_MULTI_RADAR_BALANCED_INITIALIZATION_PLAN_20260914.md).
Existing Barnes U/V already contain radial-velocity information. The added task
evaluates the remaining vertical observational constraint, hydrometeor localization,
joint balance and startup shock before any physical time advance. Continuity-only
diagnostics below are preparation evidence, not sufficient initialization acceptance.

The current task assigns omega diagnostically at the analysis time so that the
existing discrete mass-continuity balance and boundary mass fluxes are satisfied.
It does not advance a model in time. Reuse the analyzed Barnes winds and the
current pressure, mass basis and geometry; verify boundary compatibility and
report incompatible constraints rather than concealing a mass residual.
Solver iterations at this same analysis time are distinct from physical time
integration. New active physical feedback and model time integration belong to
a later stage. The trajectory experiments below are retained comparison records,
not prerequisites for this diagnostic implementation.

## Physical driver and comparison

Use the same actual 12 UTC inputs, 12–15 UTC boundary file and pinned Intel host
for OFF, HYDRO and LIQUID_RADAR_RH1 trajectories. The last comparison adds the
existing liquid-only saturation research ablation, including its coupled
feedback. It is not a new KDM6 phase policy. The paired number-basis and CCN
initialization patches are required together; earlier trajectories without them
remain numerical pilots.

At 13 UTC diagnose material pressure velocity from native dynamics:

```
omega = p_t|eta + u*p_x|eta + v*p_y|eta + eta_dot*p_eta
eta_dot = MAPFAC_MY*WW / (C1F*(MU+MUB)+C2F)
p = P + PB
```

Use the serialized 12:59:40, 13:00:00 and 13:00:20 fields for the centered time
derivative. Destagger grid-relative winds, apply native horizontal map factors,
and interpolate full-level eta-dot at the actual ZNU/ZNW brackets. A nonuniform
three-point eta derivative is a numerical approximation, not a claim to reproduce
the host's discrete pressure or geopotential advection exactly. WW itself is
not omega; geometric W is not converted with a hydrostatic density shortcut.

Remap each trajectory separately onto the same canonical pressure levels and
horizontal coordinates before subtraction. Retain the intersection of supported
stencils without extrapolation. The primary model response is LIQUID minus
HYDRO; LIQUID minus OFF is the full-analysis comparison. The analysis target is
its existing omega plus the model response, with explicit model provenance and
valid time. A valid zero response is different from a missing target. No
observational sigma or radar-LOS authority is manufactured. Existing multivariate
Barnes wind analysis remains the source of the analyzed horizontal background.

## Closed interior increment

A declared model-only boundary mode preserves the complete baseline boundary
payload and imposes zero boundary **increments**. It does not label copied
interior omega as a physical boundary measurement. For fixed geometry, the
finite-volume identity is

```
R(candidate) - R(background) = D(delta_u, delta_v, delta_omega).
```

Internal face fluxes cancel pairwise. Localization must remain within covered
interior cells, with a covered active halo sufficient for both adjacent pressure
faces. Unsupported cells have beta zero and no target. The native top is 5000 Pa;
it supplies no information for the canonical top interface at 2500 Pa. Preserve
the canonical pressure inventory and exclude unsupported upper support. No
zero fill, top extrapolation or changed pressure geometry is authorized by this
experiment.

Keep the existing solver, increment-residual, response, trust-region, wind and
omega caps, geostrophic nonworsening, finite-value and rollback gates. In this
explicit increment mode, the candidate absolute continuity residual must not
exceed the unchanged background residual plus the existing tolerance. This is
not the observational mode's absolute physical-residual ceiling, and must not
be reported as absolute physical-continuity certification. The observational
mode and its stricter contract remain unchanged. Failure is retained as failure;
thresholds and support are not tuned after viewing candidate results.

The maintained `MODEL_DYNAMICS` SHADOW dispatch uses the existing pressure-analysis
settings: 10000 m horizontal and 20000 Pa vertical localization radii, 800 solver
iterations and one pipeline pass. `CLOUD_BAL_MODEL_TARGET` names the explicit
paired response file. The reader checks its time, coordinates, pressure and
target/coverage masks against the actual analysis before installing any target.
The first and last two usable covered levels are excluded from target seeds.
The actual 22-level inventory ends in 20000, 15000, 10000 and 5000 Pa;
7500 Pa is an interface, not a represented center.

## Actual native handoff

After pressure analysis and WPS/metgrid/real, carry the accepted wind increments
into the actual staged native input. At fixed collocated pressure/height geometry,
the coordinate transformation implies

```
delta_W = delta_u*(z_x - p_x*z_eta/p_eta)
        + delta_v*(z_y - p_y*z_eta/p_eta)
        + delta_omega*z_eta/p_eta.
```

This increment relation assumes equal pressure/height time tendencies between
the paired states. Identical geometry snapshots do not establish that assumption;
the handoff is a conditional fixed-geometry reconstruction. Derive spatial metrics from the actual native geometry and preserve the native
baseline W; an approximate absolute reconstruction must not overwrite it.
Validate pressure/height monotonicity independently of whether eta increases or
decreases with array index. Invalid or unsupported stencils cannot be updated.

The Fortran consumer must update W in a fresh staged `wrfinput_d01`, with matching
serialized time, grid, staggering and mask, and exact preservation outside the
mask. An independent readback must verify the computed W increment and all
required transported fields, frame, mass basis and masks. A standalone kernel,
custom seed file or unconsumed sidecar cannot close CP02 requirement 4. OFF must
preserve the baseline. Tests and diagnostic receipts remain outside deployment.

## RED review and gate interpretation

This driver is admissible only as a covered-interior increment experiment: boundary
increments are explicitly zero, both adjacent pressure faces require an active
covered halo, first and last two usable levels are excluded from target seeding,
and unsupported cells have beta zero with no target. The increment-residual gate
compares candidate against background and cannot be relabeled absolute physical
continuity; observational sigma and LOS gates remain unchanged, with no sigma
injection. The fixed-geometry `delta_W` relation above is the native handoff
contract, so unsupported levels receive neither copied absolute omega nor
extrapolated pressure. Finite trajectories, including the current small negative
moments, remain research diagnostics and cannot authorize CP02 requirement 4.

## Current bounded evidence

- [Unit and number-domain checks](../scratch/cp02_host_unit_contract_x3bcr8ui/RESULT_UNIT.json):
  pinned Intel O0/O2; density conversion, CCN, effective radius and 20 domain cases.
- [Current run directories](../scratch/cp02_unit12_runs.json): all three trajectories
  reached 13:00:20 and produced the three required histories.
- [Independent kinematic diagnostic](../scratch/cp02_unit12_kinematic_check/RESULT.json):
  predicted mass-level W differs from serialized W by about 0.0163 m/s RMS;
  maximum differences reach about 0.66 m/s. This quantifies one discretization
  discrepancy and is not a calibrated uncertainty or a passing skill criterion.
- [Fresh core O0/O2 checks](../scratch/cp02_model13_wps_884yawpm/core_tests/RESULT.json)
  pass in separate scratch compiler directories. The actual-13 UTC baseline/OFF
  comparison is [bitwise exact for all 208 native variables](../scratch/cp02_model13_wps_884yawpm/BASELINE_OFF_RESULT.json).
- The initial actual-13 model diagnostic was [rejected at the unchanged target-response
  gate](../scratch/cp02_model13_wps_884yawpm/diagnostic_driver/RESULT.json): failure
  bitmask 64 identifies this one gate, with an 8.725159% failure fraction against
  the fixed zero allowance. Its continuity residual is slightly below background,
  but this is a failed research proposal and does not establish CP02 requirement 4.
- The [positivity diagnostic](../scratch/cp02_unit12_kinematic_check/POSITIVITY_DIAGNOSTIC.json)
  finds small negative number and volume moments in the unmodified histories,
  including liquid QNCLOUD about -0.01155 #/kg, QNRAIN about -3.88e-7 #/kg,
  and QIB about -1.81e-23 m3/kg. These finite-value trajectories therefore do
  not constitute strict moment-positivity certification; no clipping or moment
  reinitialization is authorized by this experiment.

The [common-pressure response](../scratch/cp02_native_omega_remap_6v2c9m1a/RESULT.json)
is available. A [scratch bounded projection](../scratch/cp02_pocs_strict_Mwu1La/RESULT.json)
passes focused Intel O0/O2 checks in five cycles with unchanged target, support,
trust factor and final gates. Repeated projection uses the original scaled
proposal's RMS/MAX as its fixed solver reference; it does not renormalize the
convergence threshold against each smaller residual. The final stored increment
also meets the original strict solver limits. The maintained implementation
limits the initial solve and all refinements together to 800 iterations and
commits only after the strict stored-value checks pass. The actual O0/O2
[pipeline comparison](../scratch/cp02_model13_wps_884yawpm/MODEL_REPRODUCIBILITY.json)
uses 286 total iterations, has no failed acceptance gates, and produces identical
WPS bytes. Its original shadow target metadata mixed in legacy column diagnostics;
that output must not be used as the native target-lineage receipt.

The [target-preservation correction](../scratch/cp02_model13_wps_884yawpm/MODEL_TARGET_PRESERVATION.json)
keeps the complete supplied target values, masks, quality and provenance in model
mode. The corrected actual O0/O2 runs retain exactly 892,339 input target cells and
identical WPS bytes and shadow arrays; only those four shadow metadata arrays change. Focused
Intel O0/O2 pipeline regressions cover absent-cell payload preservation as well.
The unchanged WPS bytes bind reuse of the existing successful metgrid/real run.

The [actual native payload attempt](../scratch/cp02_model13_wps_884yawpm/native_w_staged__2_a5a5g/PRESERVED_TARGET_PAYLOAD.json)
is **rejected**: 105,794 native interior points have nonzero horizontal wind
increments outside the strict omega interpolation mask (maximum 0.222186 m/s).
The [independent paired readback](../scratch/cp02_model13_paired_readback_6m4v2n/RESULT.json)
finds only UU/VV changed through WPS/metgrid and only U/V changed among all
208 native variables; fixed geometry and scalar fields are exact. This is a
relative transport check, not absolute conservation certification. The
[support breakdown](../scratch/cp02_model13_paired_readback_6m4v2n/support_mismatch_RESULT.json)
locates every rejected point in native full levels 1–7: the lower canonical
pressure bracket lacks a four-corner above-ground stencil near terrain.
No native W was written. Missing stencils are not filled, nonzero increments are
not discarded, and this rejection is not a numerical pipeline failure. Native
support compatibility, actual W ingestion and complete coupled readback remain
open; CP02 requirement 4 is not complete.

The [surface trace check](../scratch/cp02_model13_wps_884yawpm/native_w_staged__2_a5a5g/SURFACE_BOUNDARY_REVIEW.json)
also rejects an assumed zero surface wind response. The current host's
`diagnose_w` computes terrain-following lower-boundary geometric W from the
serialized CF1/CF2/CF3 weighted lowest three U/V levels; zero WW is a different
condition. Those surface wind increments are nonzero in this pair. A future
surface endpoint therefore needs a declared coordinate-consistent boundary
operator, not zero filling of the missing interior omega. The present frozen
native-transfer experiment remains rejected while that boundary contract is
reviewed.

## Native surface reconstruction v2 — declared before execution

Status: PASS_SCOPED — actual fixed-geometry native transport, 2026-09-14.
This is a new boundary experiment; the v1
105,794-cell rejection above remains unchanged. Canonical targets, localization,
solver thresholds and accepted pressure-analysis arrays are frozen. The native
lower boundary supplies an additional independently defined endpoint; it does
not expand canonical coverage or turn missing canonical cells into zero values.

For the actual nonperiodic native pair, form staggered surface wind increments
from the serialized CF1/CF2/CF3 weighted lowest three U/V levels. Require those
coefficients, HGT, PSFC, map factors, DX/DY and all fixed native geometry to match
between the pair. Bind the nonperiodic configuration to the actual native run.
For a native surface scalar q define

```
A(q) = mx/(2*dx) * ((q[ip,j]-q[i,j])*du_s[i+1,j]
                  +(q[i,j]-q[im,j])*du_s[i,j])
     + my/(2*dy) * ((q[i,jp]-q[i,j])*dv_s[i,j+1]
                  +(q[i,j]-q[i,jm])*dv_s[i,j])
im=max(i-1,1); ip=min(i+1,nx)
jm=max(j-1,1); jp=min(j+1,ny)
delta_W_surface = A(HGT)
delta_omega_surface = A(PSFC)
```

The W boundary stencil and nonperiodic edge clamping follow the pinned host's
`dyn_em/module_bc_em.F:set_w_surface`; no atmospheric W decay initialization is
copied. Applying this stencil to PSFC is the declared numerical pressure-advection
closure under fixed surface pressure tendency and zero eta-coordinate motion
increment. The terrain-W source does not prove an exact host pressure-tendency
operator. Zero coordinate-normal motion does not mean zero Cartesian W response.

At each native column, find the lowest canonical pressure node with complete
four-corner support and pressure strictly below native PSFC (above the actual
native surface). Select this node from geometry and support alone. With its
pressure p1 and increment omega1, interpolate
between that node and the independently supplied native surface endpoint only:

```
omega(p) = ((PSFC-p)*omega1 + (p-p1)*omega_surface)/(PSFC-p1)
p1 <= p <= PSFC; PSFC > p1
```

Above that first supported node, existing fully supported interior interpolation
remains unchanged. Within the declared surface interval use the surface bracket;
a canonical node below native terrain is not its lower endpoint even when
neighboring canonical columns cover it. Reject missing
surface inputs, absent supported upper nodes, nonmonotonic geometry, out-of-bracket
pressure, or any untransmitted nonzero native wind increment. No nearest-level
fill, canonical mask expansion, extrapolation or amplitude adjustment is allowed.
For this actual pair the highest three native U/V levels have exactly zero
increments; require this fact before preserving the top W boundary.

The payload contract is `native_w_increment_surface_v2`, with
`surface_boundary_contract=NATIVE_CF123_NONPERIODIC_FIXED_GEOMETRY_ZERO_ETA_DOT`.
It adds staggered `DELTA_U_SURFACE` and `DELTA_V_SURFACE` in m/s. The maintained
Fortran consumer evaluates the explicit surface W stencil using native geometry;
it uses the existing pointwise coordinate relation only for interior levels.
The surface stencil is not asserted to equal a product of independently centered
pointwise gradients and winds. The full surface update mask must be valid, the
top remains preserved, and failure must retain the staged input unchanged.

Before actual acceptance, require manufactured surface/interpolation tests,
pinned Intel O0/O2 consumer tests, independent source-bound surface and interior
W readback, exact unchanged non-W native fields and outside-mask W, and complete
paired input/configuration binding. A successful v2 transport result still does
not establish absolute conservation, observational authority, full CP06-A coupled
validation, forecast skill or whole CP02 completion.

The first actual v2 consumer attempt exposed the native MAPFAC empty-unit
encoding (one NUL character); the reader now explicitly accepts that encoding,
empty text, or `1`, and rejects other units. Intel O0/O2 regressions pass.
The next attempt [rejected 32 bottom pressure metrics](../scratch/cp02_model13_wps_884yawpm/native_surface_v2_b6vh1l6k/METRIC_REJECTION.json)
before any W write: the three-point quadratic endpoint derivative reverses sign
although every native pressure and height column is strictly monotone. V2 now
specifies two-point one-sided eta secants at both endpoints for P_ETA and Z_ETA;
three-point interior derivatives remain unchanged. This numerical endpoint
convention follows the actual coordinate orientation and retains the consumer's
strict metric gate. Original failed payloads are retained; the corrected payload
and actual readback require a separate receipt.


The corrected [metric comparison](../scratch/cp02_model13_wps_884yawpm/native_surface_v2_b6vh1l6k/METRIC_CORRECTION_RESULT.json)
confirms that only P_ETA and Z_ETA endpoints changed; all interior metrics and
all other payload arrays are exact. Every pressure derivative is positive and
every height derivative negative in the native eta orientation. The actual
[pinned Intel consumer retry](../scratch/cp02_model13_wps_884yawpm/native_surface_v2_b6vh1l6k/CONSUMER_MONOTONE_RESULT.json)
then exited 0 and wrote W to the private staged native file. The source native
file remained SHA256 `eb3b3571d22d94b787ebc6d08a56583373f697e696ce46f41d5398556b88c644`;
the consumed file is `7c294fd64e27a32ab9b29d0149d926b53b09a82e863d38c7c8191f4e95fd2ba0`.
The corrected [independent readback](../scratch/cp02_native_w_independent_check.onVsQp/NATIVE_W_RESULT_STRICT_BRACKET.json)
passes the declared v2 transport gates: 2,507,544 interior W cells match the
coordinate relation within two ULP; all 65,988 surface W values match the
float32 stencil result exactly. All 172,650 surface-bracket bindings pass,
including strict selection of an upper node above native terrain. The 65,988
outside-mask W values and all 207 non-W variables are unchanged, including
layout and attributes. Declared DX/DY define the operator; stored RDX/RDY
separately match their float32 inverses exactly. The initial independent checker
omitted strict above-terrain selection and the outside-mask gate; its historical
result is retained and superseded by this corrected readback. No native data
or tolerance changed to satisfy these checks.

This closes the bounded v2 native handoff experiment. The implementation still
uses an externally produced model increment and a conditional equal-tendency
mapping. Coupled thermo/geometry validation and the original CP02 #4 closure
remain outstanding; this result does not promote CP02 or CP06-A to PASS.
