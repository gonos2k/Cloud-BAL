# Cloud-BAL improvement plan

## Objective

Improve cloud vertical motion, mass-wind balance, background use, and the five
hydrometeor initial fields without hiding missing data or losing total water.
Every algorithmic change must be independently switchable and must preserve the
legacy result when its feature flag is disabled.

The target flow is:

```text
validated cloud/radar/background sources
                 |
                 v
      source mask + confidence + provenance
                 |
                 v
         bounded omega target
                 |
                 v
       weak/bounded balance candidate
                 |
                 v
   residual and increment acceptance gate
                 |
                 +----> balanced U/V/T/HT/OM
                 |
                 v
 conservative vapor/hydrometeor reconciliation
                 |
                 v
              WPS output
```

## 1. Consolidated problems

### 1.1 Missing values and source status are destroyed

- Failure to read `lco/COM` initializes the whole cloud-omega array to zero.
  This makes a missing field indistinguishable from a physically valid zero.
- Background `OM` missing values are also changed to zero before source fusion.
- The qbal input readers reuse one status variable, so a later successful read
  can hide an earlier field failure.
- Radar, cloud, and hydrometeor paths frequently use one domain-level status for
  partially covered three-dimensional fields.

Consequences include failed background fallback, false strong radar echo from a
positive missing sentinel, and apparently successful degraded products.

### 1.2 Balance strength is hard-coded and not tied to data quality

- `sldata=1200` is fixed instead of using actual observation density and error.
- The wind and height error-weight blocks assign the same arrays consecutively;
  the second assignment silently overwrites part of the first policy.
- `delo` depends strongly on domain-mean wind and Rossby scaling without finite
  guards or lower/upper bounds. Calm wind and small Coriolis values are unsafe.
- `tau` is derived from domain-mean omega/thermal quantities and then copied over
  the whole horizontal grid. The available terrain-varying path is disabled.
- Continuity is applied before and after dynamic balance without separate source
  confidence, increment limits, or acceptance diagnostics.
- Solver controls (`lmax`, `itmax`, `err`, `erf`) are fixed and change effective
  behavior with grid spacing and meteorological regime.
- The final qbal humidity adjustment caps vapor at saturation but does not move
  removed vapor into a condensate species.

The code therefore cannot distinguish a well-observed convective column from a
clear, missing, or weakly constrained column when deciding correction strength.

### 1.3 Hydrometeor initialization is not mass conservative

- `ice` is not initialized; other optional species use `-999`, which can pass the
  current whole-array validity test.
- A single positive missing value can zero an entire species, while negative
  sentinel values and NaNs can reach the output.
- `hydrometeor_scale=2/dx` changes every concentration solely from grid spacing.
  Its meaning as grid-box mean, in-cloud value, or empirical calibration is not
  encoded.
- LWC and ICE caps discard the excess instead of transferring it to rain and
  snow/graupel.
- Active saturation helpers modify vapor without subtracting liquid or ice.
- Precipitation is assigned to one phase category at a time; mixed phase and
  unknown precipitation types are not closed conservatively.
- The fall-speed density correction modifies a local implicit variable rather
  than the precipitation rate supplied by the caller.
- Thin-cloud condensate is inserted after omega generation, so condensate and
  vertical-motion support can disagree.

### 1.4 Background use is all-or-nothing

- Clear and missing cloud omega do not have an explicit source mask.
- Cloud omega, optional radar omega, and background omega have no independent
  uncertainty or provenance fields.
- The background is either silently substituted, changed to zero, or treated as
  fully valid. Forecast age, coordinate agreement, and local spread are absent.
- Radar may already influence cloud classification and hydrometeor allocation;
  treating radar and the resulting cloud field as independent observations
  would double-count the same information.

## 2. Data contract introduced before physics changes

For omega and every hydrometeor species, maintain parallel arrays:

```text
value(i,j,k)       physical value
valid(i,j,k)       finite, in range, and present
confidence(i,j,k)  [0,1]
source(i,j,k)      bit mask/provenance
status             OK | DEGRADED | FAILED
```

Required source bits include background, cloud, radar-3D, radar-2D, model
reflectivity, lightning, thin-cloud insertion, and fallback.

Never convert missing to zero until the final policy explicitly chooses zero.
Validate time, dimensions, pressure levels, units, and each NetCDF return code
before setting `valid`.

Internal units are fixed as follows:

```text
pressure physics       Pa
temperature            K
omega                  Pa s-1
geometric w             m s-1
derived concentration  kg m-3
WPS hydrometeors        kg kg-1 dry air
vapor for water budget kg kg-1 dry air (mixing ratio)
```

Specific humidity must be converted to vapor mixing ratio before being combined
with WPS hydrometeor mixing ratios in a total-water budget.

## 3. Background and omega fusion

### 3.1 Safe first policy: missing-only fallback

Implement this before any weighted blending:

```text
valid COM, valid background -> COM
missing COM, valid background -> background
valid COM, missing background -> COM with DEGRADED status
both missing -> explicit zero only with FAILED/DEGRADED provenance
```

This corrects the current silent-zero failure while leaving valid cloud omega
unchanged.

### 3.2 Confidence blend after the fallback is validated

For valid sources, form one combined cloud/radar observation first, then blend
it with background:

```text
w_source = confidence / variance
omega_target = sum(w_source * omega_source) / sum(w_source)
```

Confidence components may include cloud-cover quality, layer continuity, cloud
type, radar coverage/range/time, radar-to-radar spread, and background age or
spread. Radar used to create the cloud product must not be counted a second time
as an independent source.

Limit only the innovation, not the absolute field:

```text
delta_omega = omega_target - omega_background
delta_omega = taper * clamp(delta_omega, -limit(p), +limit(p))
```

The pressure-level limit is derived from baseline distributions and physical
checks; it is not introduced as an unvalidated fixed constant.

## 4. Bounded mass-wind balance

### 4.1 Preserve the legacy solver as a candidate generator

Do not immediately rewrite or weaken qbal. First calculate a candidate and keep
the pre-balance analysis:

```text
x_candidate = legacy_qbal(x_input, background)
delta_x = x_candidate - x_input
```

The final output is accepted or blended using source confidence and residual
improvement:

```text
x_output = x_input + beta(i,j,k) * limited(delta_x)
```

`beta=0` must reproduce the pre-balance input exactly; `beta=1` represents the
accepted candidate. Wind, geopotential/temperature, and omega require separate
limits and confidence.

### 4.2 Correct the control parameters

- Separate analysis/background inverse variances for wind, height/temperature,
  and omega. Remove the consecutive overwrite and expose them through a
  namelist.
- Replace fixed `sldata` with actual usable-observation density or a documented
  fallback.
- Compute Rossby scaling with a guarded effective wind and `abs(f)`; preserve
  hemispheric signs only where physically required by the equations.
- Bound `delo`, `tau`, and the resulting increments using baseline-derived
  ranges. Reject non-finite or zero denominators.
- Make `tau` local only after the global guarded version is validated. Terrain,
  cloud confidence, and background spread are candidates for local scaling.
- Treat the two continuity stages as distinct solver stages. Record their
  separate residual and increment contributions before considering removal of
  either stage.
- A solver that reaches its iteration limit, increases residuals, or generates
  a non-finite value returns `DEGRADED/FAILED`; it does not silently publish.

### 4.3 Acceptance gate

Accept a balance candidate only when all conditions hold:

- mass-continuity residual improves by an agreed metric;
- dynamic residual does not exceed its gate;
- wind, omega, temperature, and height increments remain within their
  pressure-level and confidence-dependent limits;
- cloud-omega sign/support is not destroyed in high-confidence columns;
- kinetic energy and omega RMS remain within baseline-derived ranges;
- no new missing, NaN, or infinite values appear.

The final `ub/vb/omb -> u/v/om` moves inside `balcon` must be verified by runtime
tracing before modification. Those arrays are reused as work/output arrays by
the final continuity call, so treating that code as an unconditional background
overwrite from static reading alone is unsafe.

## 5. Conservative hydrometeor allocation

### 5.1 Cell-level validation

Initialize all five species and process every cell independently:

```text
valid = finite(value) and value >= 0 and value < missing_limit
```

Invalid cells follow an explicit background-or-zero policy and receive fallback
provenance. A partial missing field never invalidates an entire species.

### 5.2 Remove implicit mass sinks and sources

Use vapor mixing ratio and hydrometeor mixing ratios in one budget:

```text
r_total = r_v + q_l + q_i + q_r + q_s + q_g
```

All phase changes are paired transfers:

```text
liquid evaporation: q_l -= dq; r_v += dq
ice sublimation:    q_i -= dq; r_v += dq
liquid conversion:  q_l -= dq; q_r += dq
ice conversion:     q_i -= dq; q_s/q_g += dq
```

The transfer is limited by available source mass. If vapor is already above the
chosen saturation target, either preserve supersaturation or move the excess to
an explicitly selected condensate phase; never delete it silently.

### 5.3 Grid scaling and cloud fraction

Default empirical grid scaling to `1.0`. Keep the legacy `2/dx` behavior only as
an independently flagged calibration mode with pre/post column-mass diagnostics.

If the source is an in-cloud concentration, convert it to a grid-box mean using
validated cloud fraction. If it is already a grid-box mean, do not scale it by
cloud fraction or grid spacing. This source meaning must be stored in metadata.

### 5.4 Phase allocation

- Enforce `PCN = RAI + SNO + PIC` wherever PCN is valid.
- Initialize outputs to zero before branching and reject unknown phase codes.
- Replace hard phase jumps with documented liquid/snow/graupel fractions in the
  mixed-phase interval after the legacy categories are reproduced in tests.
- Preserve the existing mass-conserving radar LWC-to-ICE transfer only where
  reflectivity is valid; missing reflectivity cannot trigger depletion.
- Allocate thin-cloud layer mass using cloud fraction and geometric layer
  thickness so the sum over the layer equals the diagnosed target column mass.

### 5.5 Order of operations

1. Validate pressure, temperature, vapor, cloud, radar, and species inputs.
2. Resolve source units and convert specific humidity to mixing ratio.
3. Compute an initial air density and convert concentrations to mixing ratios.
4. Apply conservative phase and vapor/condensate transfers.
5. Recompute virtual temperature/density where the vapor change is material.
6. Convert omega to geometric vertical velocity with the final valid density.
7. Validate nonnegative finite species and total-water closure before WPS output.

## 6. Feature flags and rollout

```text
OMEGA_SOURCE = LEGACY | MISSING_ONLY | CONFIDENCE_BLEND
BALANCE_MODE = LEGACY | SHADOW | BOUNDED
HYDRO_MODE   = LEGACY | SHADOW | CONSERVATIVE
RADAR_W_MODE = OFF | QUALITY_GATED
GRID_SCALE   = LEGACY_2KM | NONE | CALIBRATED
CAP_POLICY   = LEGACY_DROP | KEEP | TRANSFER | REJECT
```

Recommended rollout:

1. **Instrumentation:** preserve legacy output bitwise; add masks, provenance,
   per-stage residuals, increments, water budgets, and status propagation.
2. **Correctness:** initialize all fields, check every I/O result, preserve
   missing masks, add denominator/finite guards, and fix missing-only fallback.
3. **Hydrometeor shadow:** calculate conservative output without publishing it;
   compare total-water and species distributions against legacy.
4. **Bounded-balance shadow:** retain legacy output while measuring candidate
   increments and residual improvement.
5. **Selective activation:** enable conservative hydrometeors and bounded balance
   independently by verified case class.
6. **Confidence fusion:** activate only after missing-only fallback and source
   provenance are stable.
7. **Radar omega:** keep disabled until deterministic radar QC, missing handling,
   and partial-coverage tests pass.

Recommended initial production defaults remain conservative:

```text
OMEGA_SOURCE = MISSING_ONLY
BALANCE_MODE = LEGACY
HYDRO_MODE   = LEGACY
RADAR_W_MODE = OFF
GRID_SCALE   = LEGACY_2KM
CAP_POLICY   = LEGACY_DROP
```

New algorithms are activated only after their shadow gates pass. This avoids
changing balance strength, hydrometeor mass, and radar omega simultaneously.

## 7. Diagnostics and acceptance tests

Record at minimum:

```text
valid/fallback fraction by source and species
confidence and provenance distribution
RMS and max delta U, V, omega, T, and height
continuity and dynamic residual before/after each solver stage
delo and tau min/median/max
solver iterations and convergence status
r_total before/after and column-integrated water residual
PCN minus (RAI + SNO + PIC)
negative/non-finite counts
```

Required cases:

```text
cloud:      clear | thin | thick | multilayer | top-boundary
radar:      absent | partial | valid | stale | malformed
omega:      COM valid | partial | absent; background valid | absent
hydrometeor: each species valid | absent | partial missing | NaN | negative
regime:     calm | strong wind | near-equator | both hemispheres | terrain
grid:       multiple horizontal and vertical resolutions
```

Acceptance rules:

- Every feature flag in legacy/off mode is bitwise identical to the baseline.
- Missing masks remain explicit and valid cells are never discarded because of
  a missing value elsewhere in the field.
- All published species are finite and nonnegative.
- Cell and column water closure satisfy a tolerance appropriate for float32;
  the initial test target is `max(1e-12, 1e-6 * abs(r_total_before))`, subject to
  confirmation from baseline roundoff measurements.
- `w > 0` maps to `omega < 0`; implemented downdraft has the opposite sign.
- A balance candidate is not published when residuals worsen, limits are
  exceeded, or the solver does not converge.
- Repeated runs are deterministic for the same input and configuration.
- Multi-date tests cover different cloud/radar availability and more than one
  grid resolution before a scientific default is changed.

## 8. First implementation slice

The first code change should remain small and result-neutral where possible:

1. add field-specific read status and valid masks;
2. initialize all five hydrometeor arrays to zero plus explicit validity masks;
3. replace whole-array `MAXVAL` decisions with cell-level finite/range checks;
4. preserve missing `COM` and implement `MISSING_ONLY` background fallback;
5. add diagnostic-only total-water and balance-increment calculations;
6. add feature flags with legacy defaults;
7. add synthetic tests for missing/zero distinction and water-budget closure.

Only after this slice passes should mass-transfer or qbal weighting equations be
changed.
