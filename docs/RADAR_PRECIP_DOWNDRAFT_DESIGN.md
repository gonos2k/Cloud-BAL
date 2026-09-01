# Radar-precipitation downdraft and localized mass-wind balance

## 1. Problem statement

`get_cloud_deriv` currently diagnoses cloud type and constructs a cloud-only
geometric vertical velocity before it diagnoses three-dimensional precipitation
type and precipitation concentration.  The resulting `lco/COM` therefore
contains a prescribed updraft in most active cloud columns but no corresponding
precipitation-driven descent.  The elliptic continuity correction in `qbalpe`
then supplies the missing mass compensation through a broad horizontal-wind
increment, including areas with no cloud/radar support.

The correction has two coupled requirements:

1. initialize descent from the same radar echo and hydrometeor fields used by
   precipitation initialization; and
2. give the balance operator compact observational support so that a local
   cloud/precipitation constraint cannot alter wind arbitrarily far away.

This is an initialization constraint, not a claim that reflectivity uniquely
observes air vertical velocity.  The output must carry explicit source and
validity information and remain bounded by the information actually present.

## 2. Sign and unit conventions

Geometric vertical air velocity uses `w > 0` for ascent.  Pressure vertical
velocity uses `omega > 0` for descent.  The existing scale-height conversion is

```text
omega = -(p/H) w,          w = -(H/p) omega,          H = 8000 m.
```

Radar reflectivity must be converted before a power-law relation is used:

```text
Z = 10^(dBZ/10)  [mm^6 m^-3].
```

Using dBZ itself as `Z`, as the experimental legacy routine does, is
dimensionally incorrect.

The operational radar is S band (nominal wavelength 10 cm).  This is the
default and a hard configuration contract (`8 <= wavelength_cm <= 12`).
Compared with shorter wavelengths, attenuation is usually smaller, so a
quality-controlled echo is treated as strong evidence for a falling
hydrometeor population.  It is not direct evidence that the surrounding air
is descending.  Particle motion and air motion remain separated:

```text
vertical particle velocity = w_air - Vt,       Vt > 0 downward.
```

The reflectivity entering this routine has already passed ingest QC.  That QC
decision is authoritative: the balance step does not repeat clutter or
dual-polarization filtering and therefore does not carve new holes into weak or
edge precipitation.  It performs only finite/range checks and requires
consistency with the existing precipitation-type/concentration analysis.
Bright-band enhancement and hail remain microphysical uncertainty handled by
bounded phase/fall-speed terms; high-reflectivity convective cores are not
automatically assigned descending *air* motion.

Hydrometeor concentrations are `rho_qx [kg m^-3]`.  Air-relative mixing ratios
used in buoyancy are

```text
qx = rho_qx/rho_air,       rho_air = p/(Rd T).
```

## 3. Legacy radar code retained as design evidence

The experimental path provides useful structural ideas:

- `get_con_str`/`dfconstr` distinguish convective and stratiform echo using
  column maximum reflectivity and neighborhood texture;
- `cpt_pcp_type_3d` supplies phase category by level;
- `cpt_pcp_cnc` supplies rain, snow, and precipitating-ice concentration;
- `radar_bogus_w` places stratiform descent below the melting level and ascent
  above it; and
- `rfill_evap` recognizes fall time, vapor deficit, and phase-dependent
  evaporation/sublimation.

The following behavior cannot be activated:

- time-seeded random selection of vertical-motion amplitude;
- an uninitialized `vvmax` branch;
- a vertical, single-column precipitation path;
- use of dBZ in a linear-reflectivity fall-speed power law;
- modification of reflectivity without a paired, unit-consistent water/energy
  budget; and
- recomputing `COM` before precipitation concentration exists.

`rfill_evap` therefore remains unreachable.  The replacement uses its physical
drivers but does not call or enable that routine.

## 4. Coupled analysis sequence

The safe order is

```text
3-D cloud analysis
  -> cloud type and cloud-only w
  -> radar QC and 3-D precipitation type
  -> radar-derived rain/snow/graupel concentration
  -> observed precipitation-flux support
  -> characteristic fill only across radar-unobserved lower gaps
  -> loading/evaporation/melting negative-buoyancy potential
  -> bounded downdraft w and COM omega
  -> compact cloud/radar influence beta
  -> localized mass-wind balance
```

Observed 3-D reflectivity is never geometrically re-tilted.  Its observed tilt
is primary.  Wind/fall-speed trajectories are used only where the lower part of
the precipitation shaft is unobserved or below the radar horizon.

### 4.1 Status of the empirical cloud vertical velocity

The cloud-type profile is not an observation of vertical air velocity.  It is
a scale-aware target with large representation error.  The historical kernel
already contains the useful similarity `w_target proportional to Hc/Dx`, but
previously had no explicit resolved cap, cloud-area factor, or vertical
sampling requirement.  The revised target is

```text
w_target = min(wcap,
               a_type (Hc/max(Dx,250 m)) fc fv),

fc = analyzed cloud fraction in [0,1],
fv = min(1,Ncloud_levels/3).
```

The defaults cap convective grid-mean ascent at 5 m/s and stratiform ascent at
0.5 m/s.  These are safety bounds, not universal physical constants.  A cloud
sampled by only one model level receives one third of the empirical target.
Thus refinement increases the resolvable vertical velocity until the cap,
whereas a coarse or poorly sampled grid receives a smaller grid-mean value.

The next calibration step should replace the fixed type coefficient with
background-dependent uncertainty using CAPE/CIN, static stability, boundary-
layer convergence, and any radial-velocity constraint.  Until those fields
are passed with explicit contracts, the profile remains an uncertain target:
it may constrain the local mass projection but must not overwrite model
vertical velocity as if it were directly observed.

## 5. Precipitation trajectory and hydrometeor alignment

For phase `x`, define the precipitation mass flux

```text
Jx = rho_qx (u-cx, v-cy, w-Vtx).
```

`(cx,cy)` is storm translation when a reliable estimate is available; version
1 uses zero and records degraded provenance because no time-adjacent radar
motion vector is present in this focused source boundary.  Along a descending
characteristic,

```text
dt       = dz/max(Vtx-w, Vmin)
dx_fall  = (u-cx) dt
dy_fall  = (v-cy) dt.
```

The lower-level mass flux is deposited with bilinear horizontal weights.  A
radar-observed target is immutable.  Only an unobserved target can be filled.
The phase mass-flux closure is

```text
rho_qx,lower Vtx,lower
  = rho_qx,upper Vtx,upper exp(-ke,x D dt),

D = clamp(1-RH/100, 0, 1).
```

The transport step preserves the sum of bilinear weights and therefore the
incoming flux, apart from the explicit bounded survival factor.  Rain, snow,
and precipitating ice are transported separately; phase repartition uses the
same conservative allocator as hydrometeor initialization.

Because `w` changes particle residence time and hydrometeors force `w`, use a
bounded Picard iteration:

```text
q_p^(n+1) = T[u,v,w^n,Vt](q_p,observed)
w*^(n+1)  = G[q_p^(n+1),T,RH,Z]
w^(n+1)   = (1-alpha) w^n + alpha w*^(n+1),   0 < alpha <= 0.5.
```

Two to three iterations are sufficient for initialization.  Failure to reduce
`max|w^(n+1)-w^n|` returns a degraded status and keeps the last bounded field;
non-finite values return failure without publishing work arrays.

## 6. Negative-buoyancy and downdraft constraint

The first implementation diagnoses *available* negative-buoyancy energy.  It
does not modify temperature, vapor, hydrometeor mass, or radar reflectivity.
Let `ql` be rain and `qi` the sum of snow and precipitating ice.  A bounded
negative-buoyancy magnitude is

```text
B- = g [ ql + qi
       + Lv/(cp T) fe D ql
       + Ls/(cp T) fs D qi
       + Lf/(cp T) fm(T) qi ],

fm(T) = fm0 exp[-0.5 ((T-T0)/dTm)^2].
```

The first two terms are hydrometeor loading.  The next terms are upper bounds
on evaporation, sublimation, and melting cooling.  Coefficients `fe`, `fs`, and
`fm0` are efficiencies in `[0,1]`, not hidden water sources.

Along the precipitation characteristic, accumulate downdraft energy

```text
Ed(k-1) = Ed(k) + 0.5 [B-(k)+B-(k-1)] dz.
```

The target velocity is

```text
wd = -Ssurface min(wmax, sqrt(2 eta_d Ed)),
```

where `eta_d` accounts for entrainment and pressure-gradient work, and
`Ssurface` tapers air vertical velocity to zero at the lower boundary.  Radar
and hydrometeor confidence is

```text
Cz = smoothstep((dBZ-Zmin)/(Zfull-Zmin)),
Cq = qp/(qp+qref),
C  = clamp(sqrt(Cz Cq),0,1).
```

The update is innovation-limited:

```text
wnew = wcloud + C clamp(wd-wcloud, -Delta_wmax, 0).
```

An observed convective updraft core (`Cu`, `Cb`, or lightning cloud with
positive `wcloud`) is protected.  Descent is allowed in stratiform cloud and in
precipitating subcloud air.  This avoids falsely putting a downdraft at every
high-reflectivity convective core when radial velocity is unavailable.

## 7. Localized balance operator

Let `m(i,j,k)` be the valid cloud/radar `COM` source mask.  Construct a compact
Wendland influence function

```text
r^2 = (dh/Rh)^2 + (dp/Rp)^2,
beta(r) = (1-r)^4 (1+4r),  0 <= r < 1,
beta(r) = 0,               r >= 1.
```

`beta=1` at a valid source.  Outside the compact support, increments must be
bitwise zero.  The first operational radius is scale-aware,
`Rh=clamp(6 Delta-x,30 km,60 km)`, with `Rp=150 hPa`; both values are printed
for every run and require multi-case calibration.  Apply `beta` to the full balance candidate and to the continuity
operator.  With wind inverse variance `eu` and omega inverse variance `tau`,
the localized correction is

```text
delta u     = Ch grad_h(lambda),       Ch = beta/(2 eu),
delta omega = Cp d(lambda)/dp,         Cp = beta/(2 tau),

div( C grad(lambda) ) = -beta div(V).
```

Face coefficients use the harmonic mean of adjacent nonnegative cell
coefficients.  If either side has `beta=0`, the face flux is zero; this is what
prevents an elliptic solution from leaking into an observation-free region.
The same localized flux-form operator is used in the solve and in its residual
check.

## 8. Divergent/rotational separation and wave control

The horizontal increment is diagnosed with a discrete Helmholtz split on each
pressure level,

```text
delta Vh = grad(chi) + k x grad(psi) + H,
laplacian(chi) = div(delta Vh),
laplacian(psi) = vertical_vorticity(delta Vh).
```

`H` is the boundary-dependent harmonic remainder.  The continuity multiplier
already generates the velocity-potential part `grad(chi)`: it is a divergent
increment required to support the imposed `omega`.  It would therefore be
physically wrong to project out all divergence.  The rotational part
`k x grad(psi)` represents the pre-existing balanced circulation and is not a
target of cloud-mass adjustment.  It is copied from the analysis/background
unless independent wind observations constrain it.

Only the *high-wavenumber divergent increment* is regularized.  A convenient
variational form is

```text
min_chi  || beta^(1/2) (D grad(chi) + d(omega)/dp + r0) ||^2
       + mu || beta^(1/2) laplacian(chi) ||^2
       + nu || grad(beta) dot grad(chi) ||^2.
```

The first term retains the low-wavenumber convergence/divergence required by
mass continuity.  The second suppresses grid-scale divergent kinetic energy;
the third prevents a sharp taper edge from becoming a new convergence ring.
In implementation this is an increment-only compact smoother followed by a
second solve with the exact localized continuity operator.  It must never be
applied to the full wind, and the projection step must not recreate increments
where `beta=0`.

The acceptance diagnostics separate the two horizontal modes:

```text
Ed = 0.5 sum |grad(chi)|^2,       Er = 0.5 sum |k x grad(psi)|^2,
Rd = rms(laplacian(chi)),         Zr = rms(laplacian(psi)).
```

The candidate is rejected if high-pass `Ed`, increment roughness `Rd`, maximum
divergence, or the shared continuity residual increases beyond its tolerance,
or if the rotational increment changes without observational support.

### 8.1 Required vertical mode structure

The decomposition is also applied in the vertical.  A precipitating cloud
column should normally contain low-level convergence and upper-level
divergence connected by the diagnosed vertical mass flux:

```text
lower layer:       div(Vchi) < 0
middle layer:      d(omega)/dp carries ascent/descent mass flux
upper layer:       div(Vchi) > 0
column closure:    integral div(Vchi) dp + [omega]bottom^top = 0.
```

The rotational circulation has a different constraint.  Midlevel rotation may
be strengthened by tilting and stretching of background vorticity, but radar
reflectivity alone does not determine its sign or magnitude.  Its local source
is therefore diagnosed from the vertical-vorticity budget,

```text
D(zeta+f)/Dt = -(zeta+f) div(Vh)
             + (d w/dx)(d v/dz) - (d w/dy)(d u/dz)
             + baroclinic + friction terms.
```

Version 1 does not prescribe a rotational vortex directly from reflectivity.
The existing momentum/geopotential balance may nevertheless diagnose a
localized `delta psi` through its Coriolis and background-flow terms.  That
response is now reported separately, but it is not yet accepted as an
independently observed vortex.  A later cycling version should bound a
midlevel `delta psi` with radial-velocity/3-D wind data or a time-integrated
vorticity tendency.  Its horizontal and pressure support must use the same
compact `beta`, peak in the cloud middle rather than at the outflow/inflow
layers, and close its column angular-momentum increment to the available
torque.  Until that gate exists, the rotational profile is a required
diagnostic and calibration warning, not a radar retrieval.

This hydrostatic, pressure-coordinate analysis cannot directly resolve or
remove acoustic modes.  It can reduce their excitation by bounding and
spatially smoothing the applied increment, but the remaining time imbalance
has to be handled by the forecast integration.  The preferred handoff is an
incremental-analysis-update ramp, for example

```text
g(t) = 0.5 [1-cos(2 pi t/T)] / mean_T(g),       0 <= t <= T,
```

applied to the cloud/radar increments, or a model-level digital-filter
initialization that filters the diabatic increments.  Strong filtering of the
complete state is prohibited because it can damp synoptic and rotational
balances together with the unwanted inertia-gravity/acoustic response.

## 9. Transactional failure and acceptance gates

No work array is published unless all applicable gates pass:

- finite, monotone height and pressure coordinates;
- finite `T`, `RH`, winds, reflectivity, and nonnegative hydrometeors on active
  cells;
- `0 <= confidence,beta <= 1`;
- observed radar/hydrometeor cells remain unchanged by characteristic fill;
- `omega > 0` wherever the accepted geometric velocity is downward;
- hydrometeor mass flux closes along each deposited trajectory to the explicit
  survival tolerance;
- maximum `w`, `omega`, wind increment, and horizontal displacement are bounded;
- `delta U = delta V = delta omega = 0` wherever `beta=0`;
- the rotational wind increment remains zero unless supported by a wind
  observation, while the required low-wavenumber divergent increment remains;
- high-pass divergent energy and increment roughness do not increase;
- continuity residual does not worsen under the same localized operator; and
- repeat runs are deterministic.

## 10. Rollout

1. Add deterministic trajectory, buoyancy, and compact-localization kernels
   with synthetic straight and tilted-shaft tests.
2. Run radar mode off/on from the same isolated ANAL/MODL baseline.  Radar-off
   must reproduce the pre-change result.
3. Validate `COM` sign/support, precipitation-flux closure, increment footprint,
   and before/after continuity and momentum residuals.
4. Calibrate `Rh`, `Rp`, efficiencies, and velocity bounds from several cases;
   do not tune from one storm.
5. Only after water/energy paired tests exist may a new conservative
   evaporation/cooling update be enabled.  The legacy `rfill_evap` path remains
   off throughout this rollout.

## 11. Physical basis

- Srivastava (1987), *A Model of Intense Downdrafts Driven by the Melting and
  Evaporation of Precipitation*, DOI
  `10.1175/1520-0469(1987)044<1752:AMOIDD>2.0.CO;2`.
- Weygandt et al. (2022), *Radar Reflectivity-Based Model Initialization Using
  Specified Latent Heating*, DOI `10.1175/WAF-D-21-0142.1`.
- Lynch and Huang (1992), *Initialization of the HIRLAM Model Using a Digital
  Filter*, DOI `10.1175/1520-0493(1992)120<1019:IOTHMU>2.0.CO;2`.
- Lee et al. (2006), *Incremental Analysis Updates Initialization Technique
  Applied to 10-km MM5 and MM5 3DVAR*, DOI `10.1175/MWR3129.1`.
- Bryan, Wyngaard, and Fritsch (2003), *Resolution Requirements for the
  Simulation of Deep Moist Convection*, DOI
  `10.1175/1520-0493(2003)131<2394:RRFTSO>2.0.CO;2`.
- NOAA/NCEI documents WSR-88D/NEXRAD as an operational S-band network and its
  hydrometeor/melting-layer products; the present input has already passed the
  upstream ingest QC contract.
- The reflectivity-weighted fall-speed formulation follows the standard use of
  linear `Z`, hydrometeor phase, and density correction described in radar
  retrieval literature; dBZ is converted to `Z` before evaluation.
