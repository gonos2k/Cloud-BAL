# Cloud-BAL pipeline simplification and remediation plan

## Decision and objective

The current candidate is not ready for operational use.  The next change set
will not add a separate guard for every discovered failure.  It will replace
the overlapping cloud, radar, balance, and LAPSPREP policies with one traceable
state flow:

```text
canonical ingest
      -> one cloud/radar hydrometeor + omega diagnosis
      -> one localized divergent balance projection
      -> conservative output conversion
```

The objective is to keep cloud/radar mass support local, preserve total water,
avoid unsupported rotational wind changes, and reject wave-prone increments
without retaining two permanent implementations of the same physics.

## Rules that constrain the implementation

1. One authoritative representation exists for each physical field.  A stage
   may use a private work array, but it publishes only by committing a complete
   stage result.
2. Values, cell validity, valid time, dimensions, units, and source provenance
   cross stage boundaries together.  Missing-value sentinels are interpreted
   only in I/O adapters.
3. There is one stage success model: `FAILED`, `DEGRADED`, or `OK`, plus a
   changed-cell mask and coverage summary.  Cell-level uncertainty is carried
   by quality bits and does not automatically downgrade the whole stage.
   Legacy integer status values are converted at their adapter boundary.  In
   an active mode, stage-level `FAILED` or `DEGRADED` prevents publication of
   the whole candidate product; it never selects a hidden legacy physics
   branch.
4. There is one implementation each for cloud-layer detection, terminal fall
   speed, phase allocation, total-water transfer, and `omega <-> w` conversion.
5. The balance matrix, correction, and residual use the same face coefficients,
   staggering map, and discrete operators.  They may not contain algebraically
   duplicated formulas.
6. A replacement and the legacy code may coexist only during a named shadow
   gate.  The superseded branch is removed when that gate passes.
7. Radar evaporation remains disabled.  Reflectivity alone does not prescribe
   a rotational vortex, and no full-state spatial filter is introduced.
8. `ANAL` and `MODL` are read-only reference inputs.  All candidate execution
   uses an isolated output root.

## Target components

Keep the physics implementation to three cohesive modules, one authority-only
coordinator, and thin legacy adapters:

| Component | Owns | Does not own |
|---|---|---|
| `cloud_bal_state` | field metadata, validity/source masks, status, canonical units, `omega <-> w` | cloud or radar empirical physics |
| `cloud_bal_column_physics` | layer/regime support, radar phase diagnosis, one terminal-velocity function, conservative moisture/trajectory ledger, radar loading target | wind balancing or a cloud-type-only velocity amplitude |
| `cloud_bal_balance_operator` | one A-grid-to-face map `S`, flux divergence `D`, canonical operator `A=D S`, weighted A-grid correction `G`, exact `L=-A G`, residuals, compact support and increment gates | input fallback or hydrometeor diagnosis |
| `cloud_bal_pipeline` | the single mode/promotion boundary, stage order, compact support generation, rollback, and field-selective publication | empirical physics or a second numerical operator |

The S-band trajectory/downdraft routine is an internal procedure of
`cloud_bal_column_physics`, not a fourth permanent physics module.  Existing
F77 entry points remain thin adapters only until their full-tree callers are
migrated.

The published canonical state is on the LAPS A grid.  Staggered values, face
coefficients, and face masks are private work data owned by
`cloud_bal_balance_operator`; they are never alternative published states.

### One public contract and five public operations

The new pipeline exposes only the following state-transforming operations.
Their `state_in` argument is immutable, `state_out` has separate storage, and a
non-`OK` operation returns an exact copy of `state_in`; private work arrays can
never alias a background or published array.  A rejected calculation exposes
only metrics through `stage_result`, never a partially modified output state.

```fortran
call read_canonical_state(input_spec, state_out, result)
call derive_column_physics(state_in, state_out, result)
call apply_localized_balance(state_in, state_out, result)
call write_wps_state(state_in, output_spec, result)
call run_cloud_bal_pipeline(state_in, candidate_out, operational_out,
                            pipeline_result, config)
```

The public data model is conceptually:

```text
field = values + valid + quality_bits + source_bits
        + valid_time + dimensions/layout + canonical_unit

cloud_bal_state = schema/version/grid/metrics
                  + pressure/temperature/moisture/wind/omega fields
                  + hydrometeor fields
                  + obs_support/hydro_support/balance_beta
                  + optional radar_los_observation_set

stage_result = OK|DEGRADED|FAILED + changed + coverage
               + reason_code + numerical diagnostics
```

Phase 1 replaces that sketch with these public derived types in
`cloud_bal_state`; no other module declares a competing state type:

```fortran
integer, parameter :: STATUS_FAILED=-10, STATUS_DEGRADED=10, STATUS_OK=20
integer, parameter :: LOS_REJECTED=0, LOS_ASSIMILATED=1, LOS_HELD_OUT=2

type :: field3d
  real(real32), allocatable :: value(:,:,:)        ! (x,y,z)
  logical, allocatable :: valid(:,:,:)
  integer(int32), allocatable :: quality(:,:,:), source(:,:,:)
  integer(int64) :: valid_time
  character(len=16) :: unit
end type

type :: field2d
  real(real32), allocatable :: value(:,:)          ! (x,y)
  logical, allocatable :: valid(:,:)
  integer(int32), allocatable :: quality(:,:), source(:,:)
  integer(int64) :: valid_time
  character(len=16) :: unit
end type

type :: field4d
  real(real32), allocatable :: value(:,:,:,:)      ! (x,y,z,radar)
  logical, allocatable :: valid(:,:,:,:)
  integer(int32), allocatable :: quality(:,:,:,:), source(:,:,:,:)
  integer(int64) :: valid_time
  character(len=16) :: unit
end type

type :: integer_field3d
  integer(int32), allocatable :: value(:,:,:)      ! (x,y,z)
  logical, allocatable :: valid(:,:,:)
  integer(int32), allocatable :: quality(:,:,:), source(:,:,:)
  integer(int64) :: valid_time
  character(len=32) :: code_table
end type

type :: grid_spec
  integer :: nx, ny, nz
  character(len=64) :: grid_id
  real(real64), allocatable :: dx(:,:), dy(:,:), dp(:,:,:)
  real(real64), allocatable :: pressure_mass_measure(:,:,:)
  real(real64), allocatable :: dry_air_mass_measure(:,:,:)
end type

type :: radar_los_observation_set
  logical :: is_present = .false.
  integer :: nradar = 0
  type(field4d) :: vrad, nyquist, sigma_vrad        ! (x,y,z,radar)
  real(real32), allocatable :: beam(:,:,:,:,:)      ! (...,radar,xyz)
  integer(int64), allocatable :: observation_id_hi(:,:,:,:)
  integer(int64), allocatable :: observation_id_lo(:,:,:,:)
  integer(int32), allocatable :: usage(:,:,:,:)     ! ASSIMILATED/HELD_OUT
  integer(int32), allocatable :: radar_id(:)
  integer(int64), allocatable :: observation_time(:)
  real(real64), allocatable :: site_lat(:), site_lon(:), site_height(:)
  real(real64), allocatable :: wavelength(:)
  integer(int32), allocatable :: los_support(:,:,:,:)
  logical :: has_colocated_dbz = .false.
  type(field4d) :: colocated_dbz
  real(real32), allocatable :: geometry_condition(:,:,:)
  integer(int32), allocatable :: geometry_rank(:,:,:)
  logical :: has_spectrum_width = .false.
  type(field4d) :: spectrum_width
end type

type :: cloud_bal_state
  integer :: schema_version
  type(grid_spec) :: grid
  type(field3d) :: pressure, temperature, vapor, u, v, omega, omega_target
  type(field3d) :: cloud_fraction, radar_reflectivity
  type(integer_field3d) :: cloud_type, precipitation_phase, lightning_support
  type(field3d) :: cloud_water, cloud_ice, rain, snow, graupel
  type(field3d) :: vt_z_mean, vt_z_sigma
  type(field2d) :: surface_pressure, surface_temperature
  type(field2d) :: omega_top_boundary, omega_bottom_boundary
  logical, allocatable :: above_ground(:,:,:)
  integer(int32), allocatable :: obs_support(:,:,:)
  integer(int32), allocatable :: hydro_support(:,:,:)
  real(real32), allocatable :: balance_beta(:,:,:)
  type(radar_los_observation_set) :: radar_los
  ! separate field2d surface fields; never a synthetic z+1 level
end type

type :: stage_result
  integer :: status, reason_code
  logical, allocatable :: changed(:,:,:)
  type(coverage_summary) :: coverage
  real(real64) :: los_rms_input, los_rms_candidate, los_threshold
  logical :: los_gate_applied, los_gate_passed
  type(numerical_diagnostics) :: numerical
end type
```

`coverage_summary` contains required, usable, and excluded counts/fractions by
field plus assimilated and held-out LOS counts.  `numerical_diagnostics`
contains solver reason/iterations and pre/post continuity, momentum, increment,
mode, roughness, conservation, and LOS metrics.  With `is_present=.false.`,
`nradar=0` and every LOS array is unallocated.  With `is_present=.true.`, every required
array and item of metadata has consistent bounds or ingest returns `FAILED`.
The public procedures declare `state_in` as `intent(in)` and
`state_out/result` as `intent(out)`.  Only `cloud_bal_state` owns allocation,
deep copy, validation, and commit: it copies input to output, gives private work
storage to a stage, and swaps a complete work state into `state_out` only on
`OK`.

`cloud_fraction` (`1`) and versioned `cloud_type` code are required canonical
inputs to the cloud branch.  `radar_reflectivity` (`dBZ`) and
`lightning_support` (`0/1`) are optional canonical inputs with the same
metadata/mask rules.  They are read and,
when deriv/qbal run as separate processes, persisted by the canonical adapter;
`derive_column_physics` may obtain them only from `state_in`, never through a
hidden positional argument, common block, or file read.  The per-radar
`colocated_dbz` field is optional LOS evidence, not a substitute for the
canonical reflectivity used by column physics.

Every LOS array has a fixed in-memory order: `vrad`, `nyquist`, `sigma_vrad`,
optional `colocated_dbz`/`spectrum_width`, IDs, `usage`, and `los_support` are
`(x,y,z,radar)`; `beam` is `(x,y,z,radar,component)` with component order
east/north/up and unit `1`; geometry condition/rank are `(x,y,z)`; site,
wavelength, and volume time are `(radar)`.  Disk order is respectively
`(record,radar,z,y,x)`, `(record,radar,z,y,x,component)`,
`(record,z,y,x)`, and `(record,radar)`.  The round-trip fixture fills each axis
with distinguishable values so a transposition cannot pass.

Each name has exactly one meaning:

| Name | Meaning | Persistence |
|---|---|---|
| `valid(field)` | the field value can be used under that field's contract | with the field |
| `quality_bits(field)` | local uncertainty/exclusion reason such as unknown phase | with the field |
| `source_bits(field)` | origin and transformations applied to the value | with the field |
| `obs_support` | cells supported by an accepted cloud/radar observation | canonical state |
| `hydro_support` | cells occupied by the diagnosed cloud/precipitation column | canonical state |
| `balance_beta` | dimensionless `[0,1]` localization weight for wind balance | canonical state |
| `los_support` | gridded samples with an accepted post-QC LOS comparison | radar observation set |
| `face_active` | faces derived from adjacent valid cells, metrics, and `balance_beta` | private operator work |
| `changed` | cells changed by this one stage relative to its `state_in` | result/manifest |

No mask may stand in for another.  In particular, observed reflectivity cells,
the full tilted hydrometeor shaft, the tapered balance domain, and active
operator faces are related but are not interchangeable sets.

The serialization contract fixes every public mask as follows:

| Public item | On-disk name/type/order | Consumer/round-trip rule |
|---|---|---|
| per-field masks | `<field>_valid`, `<field>_quality`, `<field>_source`; NetCDF `int`; same order as field | every process that consumes the field; bitwise round trip |
| observation support | `cloud_bal_obs_support`; NetCDF `int` 0/1; `(record,z,y,x)` | column physics and balance; never reconstructed from `dbz`/COM |
| hydrometeor support | `cloud_bal_hydro_support`; NetCDF `int` 0/1; `(record,z,y,x)` | balance and output; never reconstructed from mixing ratio |
| localization | `cloud_bal_balance_beta`; NetCDF `float`; `(record,z,y,x)` | balance only; finite and in `[0,1]`, numeric round trip |
| LOS support | `cloud_bal_los_support`; NetCDF `int` 0/1; `(record,radar,z,y,x)` when LOS diagnostics are persisted | LOS gate only; absent with the whole optional record |
| changed cells | `<stage>_changed` in the stage manifest, with canonical `(x,y,z)` shape/hash | audit only; no downstream physics may consume it |
| active faces | none | derived once inside the operator and destroyed with work arrays |

The contract test asserts that replacing `obs_support`, `hydro_support`,
`balance_beta`, or `los_support` with `valid`, `source`, nonzero data, or
`changed` changes the fixture and is rejected.  It compares every persisted
mask, not only COM/hydrometeor provenance.

### Canonical units and schema

| Quantity | Internal unit | Conversion owner |
|---|---|---|
| pressure | Pa | ingest adapter |
| temperature/virtual temperature | K | ingest/state |
| cloud fraction/type/lightning | `1` / versioned integer code table / `0 or 1` | ingest/state |
| radar reflectivity | dBZ at input; linear backscatter only inside LOS/PSD work | radar adapter/column physics |
| radar LOS/Nyquist/spectrum width | m s-1 | external wind/LOS adapter |
| geometric vertical velocity | m s-1 | state |
| pressure vertical velocity | Pa s-1 | state |
| vapor and all cloud/precipitation species | kg kg-1 dry air | ingest/state |
| radar diagnostic mass concentration | kg m-3, private work only | column physics |

`pressure_mass_measure=A*dp/g` is the pressure-coordinate operator metric.
`dry_air_mass_measure=pressure_mass_measure/(1+r_t)` is used only for water
mass.  The two names and uses may not be interchanged.  Radar
reflectivity relations may diagnose a private mass concentration (C_h), but
the state stores (r_h=C_h/\rho_d); the relative precipitation mass flux is
(F_h=\rho_d r_h\max(V_{t,h}-w,0)).  No public stage may add a concentration to
a dry-air mixing ratio.

The sole vertical-velocity conversion is
`omega = -rho_air*g*w`, with `rho_air=p/(R_d*T_v)`.  A fixed scale-height
conversion may be retained only as an explicitly named legacy adapter during
shadow comparison and is removed before activation.

Persisted products receive a schema version and cell-level `valid`, `quality`,
and `source` variables for COM and each hydrometeor.  A legacy file without those variables
is accepted only by the versioned legacy reader and is marked `DEGRADED`; an
active new pipeline does not infer provenance from numeric values.

Schema version 1 freezes, rather than dynamically assigns, these bit positions:

```text
source_bits:
  0 BACKGROUND_MODEL       1 CONVENTIONAL_OBS     2 CLOUD_ANALYSIS
  3 RADAR_DBZ              4 RADAR_VRAD            5 LIGHTNING
  6 ANALYZED_WIND          7 COLUMN_PHYSICS        8 BALANCE_OPERATOR
  9 OUTPUT_ADAPTER

quality_bits:
  0 RAW_MISSING            1 QC_REJECTED           2 TIME_MISMATCH
  3 BELOW_GROUND_FILLED    4 PHASE_UNCERTAIN       5 BRIGHT_BAND_OR_MIXED
  6 FALL_SPEED_UNCERTAIN   7 GEOMETRY_POOR         8 LEGACY_PROVENANCE
```

A transformation ORs its source bit and preserves earlier bits.  It cannot
clear origin bits.  Invalid cells retain the applicable quality reason but are
never made valid merely because a source bit is present.  New meanings require
a schema-version change; configuration files cannot redefine these bits.

### Optional radar line-of-sight observation record

Cloud-BAL does not add another raw radial-velocity reader.  The existing KLAPS
wind path (`get_multiradar_vel -> qcradar -> wind analysis`) remains the sole
owner of ingest, velocity QC/dealiasing, and the first use of LOS velocity in
the analyzed wind.  A thin adapter may expose its accepted, post-QC
observations through this optional canonical subrecord:

```text
radar_los_observation_set
  radar_id, site latitude/longitude/height, wavelength
  observation_time and analysis_time_offset
  128-bit observation_id and ASSIMILATED/HELD_OUT lineage
  vrad [m s-1], nyquist [m s-1], sigma_vrad [m s-1]
  beam_unit_vector in the canonical grid frame
  valid, qc_bits, source_bits, los_support
  optional colocated_dbz and effective fall-speed mean/uncertainty
  local geometry rank/condition metric for simultaneous radars
  optional spectrum_width and polarimetric evidence, each as a full field
```

Absence of this entire subrecord is valid and must be bit-for-bit equivalent to
the radar-LOS gate being disabled.  Presence requires independent velocity QC;
the already completed reflectivity QC does not validate velocity folding,
Nyquist metadata, beam geometry, timing, clutter, or finite/range checks.  The
adapter computes beam vectors with one documented Earth/grid transformation,
not a second geometry formula in qbal.

Use the meteorological convention that positive radial velocity is away from
the radar, the beam unit vector points from radar to gate, `z` is upward, and
terminal fall speed `V_t` is positive downward.  A weather radar measures the
backscatter-power-weighted motion of the scatterer population, not a point air
parcel.  The measurement-definition reference equation is therefore

```text
W_j(D,r) = antenna_weight(r) * sigma_b,j(D,r) * N_j(D,r)

H_los = [sum_j integral_beam integral_D
           W_j(D,r) * n(r).(U(r) - V_t,j(D,r)*e_z) dD dr]
        / [sum_j integral_beam integral_D W_j(D,r) dD dr].
```

The canonical state does not carry ray-volume scattering integrals, so that
reference equation is not advertised as the Version-1 executable operator.
Version 1 has exactly one production surrogate:

```text
H_los_bulk = n . (U - V_t,Z*e_z)
r_los = vrad - H_los_bulk.
```

`cloud_bal_column_physics` owns and publishes `V_t,Z`, `sigma_Vt,Z`, and their
quality/source bits through its one phase/PSD/fall-speed policy.  After the
final wind candidate exists, `cloud_bal_balance_operator` alone evaluates
`H_los_bulk` and records the input/candidate LOS metrics and decision in
`stage_result`; the LOS adapter cannot invent another `Z-V_t` formula.  A
melting layer, mixed species, hail, uncertain DSD, unresolved beam filling, or
insufficient polarimetric evidence excludes a sample from a hard LOS gate and
retains it only as a high-uncertainty diagnostic.  A later implementation of
the reference integral requires explicit ray-volume antenna weights and
species/PSD/backscatter state in a separately versioned contract.

At low elevation `n_z` is small, so LOS chiefly tests horizontal along-beam
wind.  Higher elevation adds vertical sensitivity, but air vertical velocity
and particle terminal fall speed remain entangled.  A single beam constrains
only one scalar projection and therefore cannot directly retrieve full 3-D
wind, divergence, vorticity, or downdraft.  Multiple radars may strengthen a
claim only where time/space matching and a frozen rank/condition-number gate
show adequate nonparallel geometry.

Version 1 distinguishes reused and independent velocity evidence.  Every LOS
sample carries a stable observation ID and `ASSIMILATED`/`HELD_OUT` lineage.
A sample used by `qcradar`/wind analysis is correlated with `state_in`; it is a
report-only consistency monitor and cannot accept or reject Cloud-BAL.  A hard
acceptance diagnostic may use only deterministically withheld samples not used
in the analyzed wind:

```text
r_los = vrad_observed - H_los_bulk(candidate wind, candidate w, V_t,Z)
weighted_RMS_HELD_OUT(r_los_candidate)
  <= weighted_RMS_HELD_OUT(r_los_input) + tolerance.
```

For an accepted sample,
`sigma_los^2=sigma_vrad^2+n_z^2*sigma_Vt,Z^2+sigma_time^2+
sigma_beam^2+sigma_repr^2` and its weight is
`1/max(sigma_los^2,sigma_floor^2)`.  Every term and the floor has units of
`m2 s-2`; correlated neighboring samples are thinned or block-aggregated by
radar volume so grid oversampling cannot create false confidence.

The deterministic partition is made upstream by radar/site/volume/grid-sample
key and is recorded by both wind-analysis and Cloud-BAL manifests.  If no
independent samples are available, the LOS hard gate is unavailable rather than
evaluated on reused data.  LOS is not an extra qbal forcing term, its
perpendicular wind component is not called observed, and it cannot create
rotational support.  A future `J_los` term is a separately reviewed
joint-assimilation change permitted only after the existing wind-analysis use
and its error cross-covariance are removed or represented.

LOS availability does not introduce another status system:

| LOS input classification | Existing stage result/action |
|---|---|
| entire optional record absent | no LOS metric; core stage may remain `OK`; exact no-LOS equivalence |
| structurally valid, some independent samples accepted | apply the no-worse gate on `HELD_OUT` samples; reused/rejected samples remain report-only with lineage/quality bits |
| structurally valid, zero accepted samples | no LOS metric; core stage may remain `OK` when LOS is optional, or `DEGRADED` when the frozen case policy requires minimum LOS coverage |
| partial accepted coverage below a declared required minimum | `DEGRADED`; return unchanged input and do not publish |
| wrong dimensions/units/time encoding/site geometry or non-finite required metadata | `FAILED`; return unchanged input and do not publish |
| candidate worsens the independent weighted LOS metric | `DEGRADED`; return unchanged input and block any future `BALANCE_ACTIVE` publication |

Poor multi-radar rank marks `GEOMETRY_POOR` and prohibits a multi-Doppler or
rotational claim, but individually valid held-out samples can still execute the
scalar no-worse test.  `LOS_ABSENT`, `LOS_ZERO_ACCEPTED`, and related labels are result
reason codes and coverage counts, not a parallel success enum.

### What hydrometeor information LOS data can add

The first moment `vrad` contains a hydrometeor contribution, but the usable
information depends more on beam geometry and supplied radar moments than on
the S-band label alone:

| Available evidence | Defensible use in this pipeline | Not defensible |
|---|---|---|
| low-elevation `vrad` plus existing analyzed wind | along-beam innovation monitoring; an independent-held-out no-worse gate; indirect support for shaft advection | direct `w`, downdraft, phase, or DSD retrieval |
| higher-elevation `vrad`, accepted `dbz`, and an independent/background wind | a weak likelihood for `V_t,Z` or `w-V_t,Z`, with phase/DSD uncertainty | deterministic separation of air motion and fall speed |
| two or more simultaneous nonparallel beams | better wind projection where rank/condition gates pass | assuming that radar count alone proves usable multi-Doppler geometry |
| full Doppler spectrum or trustworthy spectrum width | evidence about velocity dispersion, size sorting, multiple particle populations, or melting | assigning width wholly to DSD; shear, turbulence, beam broadening, and antenna effects also contribute |
| separate H/V Doppler moments plus `ZDR` | research-grade differential Doppler-velocity evidence for particle size/shape | use when the operational ingest supplies only one mean velocity |
| `Z`, `ZDR`, `rhoHV`, `KDP` collocated with velocity | probabilistic phase/DSD/fall-speed bounds and bright-band flags | a unique hydrometeor species or terminal speed |

The current full-tree wind reader exposes gridded velocity, Nyquist velocity,
radar time, and site metadata.  The raw decoder/schema recognize spectrum
width, but its read is commented out in the active remap and the wind contract
does not carry it.  Phase 1 therefore performs a capability audit.  It may
preserve spectrum width or polarimetric moments only if their operational
source, units, QC, timing, and masks survive round trip.  Missing optional
moments select the simpler bulk-uncertainty operator and never trigger a guessed
value.

The literature establishes the information content but also its conditional
nature:

- Caumont and Ducrocq (2008),
  [doi:10.1175/2008JAMC1894.1](https://doi.org/10.1175/2008JAMC1894.1),
  formulate scanning-radar Doppler velocity as reflectivity-weighted
  hydrometeor motion and quantify fall-speed, beam-volume, and weighting
  approximations for kilometre-scale models.
- Wolfensberger et al. (2018),
  [doi:10.5194/amt-11-3883-2018](https://doi.org/10.5194/amt-11-3883-2018),
  give a species/PSD/backscatter-weighted polarimetric forward operator and
  separate spectrum-width contributions.
- Protat and Williams (2011),
  [doi:10.1175/JAMC-D-10-05031.1](https://doi.org/10.1175/JAMC-D-10-05031.1),
  use a vertically pointing S-band radar with independent profiler air motion
  to retrieve terminal fall speed, illustrating both the hydrometeor signal
  and the need for independent information to separate it from `w`.
- Williams (2016),
  [doi:10.1175/JTECH-D-15-0208.1](https://doi.org/10.1175/JTECH-D-15-0208.1),
  shows that S-band vertical Doppler spectra contain the hydrometeor-motion
  peak and can constrain rain DSD when combined with a profiler-derived air
  motion/broadening estimate.
- Teshiba et al. (2009),
  [doi:10.1175/2008JTECHA1102.1](https://doi.org/10.1175/2008JTECHA1102.1),
  combine S-band polarimetric variables with a vertical profiler to relate DSD,
  fall-speed spectra, and vertical air motion.
- Wilson, Illingworth, and Blackman (1997),
  [doi:10.1175/1520-0450-36.6.649](https://doi.org/10.1175/1520-0450-36.6.649),
  demonstrate at S band that separate H/V mean Doppler velocities can add DSD
  and particle-shape information; this requires measurements not present in a
  single operational `vrad` field.

Vertically pointing/profiler retrieval skill in these studies is evidence for
the physics, not permission to transfer their observability to routine
low-elevation PPI data.  The contract and tests retain that distinction.

### Cloud-regime vertical-air-motion evidence and replacement contract

Cloud type is evidence about a **distribution** of air motion, not a direct
measurement of a deterministic grid-cell mean.  The former depth/grid-ratio
amplitude and sine profile are therefore not eligible for active publication.
The following observations constrain the replacement:

- Ghate et al. (2010),
  [doi:10.1029/2009JD013091](https://doi.org/10.1029/2009JD013091), report
  near-zero ensemble-mean vertical velocity in nonprecipitating continental
  stratocumulus, with height-varying variance/skewness and coherent structures
  explaining only part of that variance.  A fixed positive stratus velocity is
  therefore not a defensible mean target.
- Jeong et al. (2022),
  [doi:10.1029/2022JD037021](https://doi.org/10.1029/2022JD037021), find
  distinct Sc and shallow-Cu velocity distributions: Cu has stronger,
  positively skewed extreme updrafts, while Sc is weaker and can be negatively
  skewed.  The regime should select a prior/PDF family and uncertainty, not one
  universal vertical shape.
- Lareau et al. (2018),
  [doi:10.1175/JAS-D-17-0244.1](https://doi.org/10.1175/JAS-D-17-0244.1), show
  shallow-Cu cloud-base updraft depends on updraft width relative to boundary-
  layer depth; boundary-layer velocity variance alone has almost no predictive
  skill for cloud-base updraft.  Cloud fraction or depth alone is not an
  adequate amplitude closure.
- Kumar et al. (2015),
  [doi:10.1175/JAS-D-14-0259.1](https://doi.org/10.1175/JAS-D-14-0259.1),
  separate deep-convective velocity from area fraction and find mass flux is
  regulated more strongly by area fraction; lower-level downdraft mass flux is
  associated with precipitation loading.  A core velocity may not be assigned
  to an entire analysis grid cell.
- de Roode et al. (2012),
  [doi:10.1175/MWR-D-11-00277.1](https://doi.org/10.1175/MWR-D-11-00277.1),
  derive the shallow-cumulus vertical-velocity budget and show pressure
  gradient is a dominant sink, with large uncertainty in simplified buoyancy/
  entrainment coefficients.  A prescribed sine curve is not a substitute for
  that budget.
- Bryan et al. (2003),
  [doi:10.1175/1520-0493(2003)131%3C2394:RRFTSO%3E2.0.CO;2](https://doi.org/10.1175/1520-0493(2003)131%3C2394:RRFTSO%3E2.0.CO;2),
  demonstrate that deep-convective structure and vertical velocity are
  resolution dependent and not converged even between some sub-kilometre
  simulations.  A model-level-count correction cannot make a core velocity a
  resolution-invariant grid-mean observation.

The replacement contract is deliberately smaller than an empirical catalogue:

1. **Sc/stratus/fog:** cloud analysis alone has zero-mean vertical-air-motion
   innovation.  It supplies layer support and a regime-dependent uncertainty;
   accepted boundary-layer convergence, turbulence, radiative-cooling, lidar,
   or other dynamic evidence is required for a nonzero mean target.
2. **Shallow/deep Cu:** a nonzero target requires a separately valid,
   grid-representative dynamic driver (cloud-base mass flux/area, resolved
   convergence plus buoyancy, or independent air-motion retrieval).  Cloud
   type selects the conditional prior and sign policy but never supplies the
   amplitude by itself.
3. **Mapping:** use grid-mean mass flux,
   `M=rho_d*(a_u*w_u+a_d*w_d+a_e*w_e)`, with area fractions closing to one.
   Core `w_u` is never copied to the whole grid box.  If a plume calculation is
   available, its kinetic-energy form is integrated with explicit buoyancy,
   pressure/entrainment closure and uncertainty; otherwise no plume is
   fabricated.
4. **Precipitating cloud:** air motion and hydrometeor fall motion remain
   separate.  Radar reflectivity/mean Doppler velocity alone cannot select a
   stratiform downdraft; the conservative precipitation/loading path owns that
   contribution.
5. **Resolution:** the observation operator averages a physical mass flux to
   the analysis grid, while unresolved variance enters `R_w`.  Resolution does
   not rescale a fixed core velocity through level count or `depth/dx`.

Until the dynamic-driver fields, `R_w`, and regime calibration are implemented
and independently validated, cloud-type-only vertical motion is SHADOW
diagnostic with zero publication authority.  Safety caps remain rejection
limits, never climatological amplitudes.

### Stage-result state machine

| Mode/result | Publish candidate | Run next candidate stage | Operational action |
|---|---:|---:|---|
| `SHADOW/OK` | no | yes | publish versioned legacy product; retain comparison artifact |
| `SHADOW/DEGRADED` | no | no | publish versioned legacy product; report candidate failure |
| `SHADOW/FAILED` | no | no | publish versioned legacy product; return nonzero shadow status |

The focused research build contains no active row: it accepts only `OFF` and
`SHADOW`, and all other mode integers fail with `REASON_AUTHORITY`.  Any future
ACTIVE contract belongs to a separate production-integration change after its
manifest and end-to-end gates exist.

Candidate files are written under a temporary versioned root and renamed into
place only after the last applicable stage gate passes.  Mode, schema version,
commit, compiler, and threshold-set identifier are recorded in the manifest.

Stage status is determined from the declared required inputs, usable coverage,
and numerical gate summary, never from the worst quality bit in a single cell:

- `FAILED`: structural contract violation, no usable required coverage,
  non-finite committed result, or solver/operator failure;
- `DEGRADED`: a usable diagnostic exists but a frozen stage coverage/quality or
  activation gate is not met;
- `OK`: all stage-level requirements pass; uncertain or excluded cells may
  remain explicitly marked without contaminating supported cells.

### Phase dependency contract

| Phase | Required input/API | Produced artifact | Production publication |
|---|---|---|---|
| 0A | current source and full-tree make system | ABI-safe linked executables | prohibited |
| 0B | tagged legacy bundle and complete input snapshot | isolated harness and manifests | legacy bundle only |
| 1 | 0A executables and 0B harness | canonical state/schema round trip | shadow only |
| 2 | canonical state and persisted source masks | column-physics candidate | shadow, then hydro only after its gate |
| 3 | accepted omega/support candidate | localized balance candidate and frozen thresholds | shadow until every production gate exists |
| 4 | accepted canonical state | atomic WPS/product set | only the cumulative active mode |
| 5 | all commands, cases, and frozen thresholds | activation/rollback evidence | allowed by state-machine result |

No phase may call a downstream fallback that reconstructs an artifact owned by
an earlier phase.  During migration, an old F77 symbol is converted into an
adapter that calls the canonical implementation; it is not retained as a
second physics path.  A separate old implementation is reachable only from the
tagged legacy executable used by `SHADOW` and rollback.

## Phase 0A - Restore ABI and full-tree build integrity

### Changes

- Add the new module objects to the full KLAPS make dependency order.
- Keep `get_laps_3d_analysis_data` at its legacy argument list and introduce
  `get_laps_3d_analysis_data_ex` for the independent COM status.  Migrate qbal
  explicitly; do not change an implicit-interface symbol in place.
- Add `libcloudbal` (or an equivalent ordered object target), `.mod` search
  paths, and link dependencies to deriv, qbal, LAPSPREP, wind, wind_openmp,
  `getradar`, and the active radar remap.  This is required because the LOS
  adapter/lineage boundary is part of the contract even though raw velocity
  ingestion remains owned by wind analysis.
- Because `Cloud-BAL` and `klaps-v5.0_` are separate repositories, keep the
  implementation commit and a parent-tree integration patch/commit together in
  each evidence manifest.  Record both repository SHAs and test only from a
  clean integration checkout.
- Add a reproducible full-tree build driver that accepts compiler and debug
  flags.  The release compiler and a bounds-checking build are both required;
  `-fallow-argument-mismatch` may not hide an ABI mismatch.

### Exit gate

- `tests/run_full_tree_build.sh --compiler release` and
  `tests/run_full_tree_build.sh --compiler bounds` both return zero in a clean
  build tree and link deriv, qbal, LAPSPREP, wind/wind_openmp, `getradar`, and
  radar remap.
- A link-symbol audit confirms one old ABI wrapper and one `_ex` implementation,
  with no mismatched caller.
- This phase is a build/link gate only.  It does not claim that the current
  default LAPSPREP runtime is valid.

## Phase 0B - Freeze data and create an isolated execution harness

### Changes

- Verify the archived baseline checksums and create a complete read-only input
  snapshot for the actual deriv/qbal/LAPSPREP call chain.
- Define a writable candidate `LAPS_DATA_ROOT` containing symlinks or copies of
  required inputs and separate product directories.  It must not resolve any
  output path into `ANAL`, `MODL`, or the baseline archive.
- Add pre/post hashes for `ANAL` and `MODL`, a product manifest, fixed compiler
  metadata, and a candidate artifact root
  `scratch/candidate/<commit>/<case>/<mode>`.
- Keep a tagged versioned legacy executable/config/schema bundle as the
  operational rollback artifact.  Rollback selects that bundle at run start;
  it does not revive deleted branches inside the new executable.
- Put the output transaction primitive here, before scientific activation:
  every legacy writer is redirected to the candidate temporary root and a
  single coordinator publishes the declared set.  Inject failure after each
  writer in turn and prove that no partial final product or stale temporary
  product is visible.
- Inventory and patch every actual write path, initially including generic
  `laps_io.f`, balance `writeballaps.f`, the `writelapsdata.f`/`rwl_v3.c`
  NetCDF backend, deriv COM/hydrometeor calls, and LAPSPREP/WPS direct opens.
  They receive only a resolved path from one `cloud_bal_output_context`; no
  candidate writer may consult `generic_data_root` or assemble a product root.
- The coordinator creates `.staging/<transaction_id>` on the same filesystem,
  and `resolve_output(context, product_id)` rejects paths outside that prefix.
  On success it writes/fsyncs the product manifest and `COMMITTED` marker,
  renames the staging directory to `generations/<transaction_id>`, and
  atomically replaces a `current` pointer.  Consumers resolve one generation
  once per run.  Recovery ignores uncommitted staging roots; cleanup may remove
  them only after verifying that neither `current` nor a rollback manifest
  refers to them.

### Exit gate

- `tests/run_isolation_gate.sh <case>` proves by resolved-path check, exact
  frozen inventory, declared-product hashes, and full-tree metadata/ctime that
  the scoped reference inputs did not change during the command.  It is not a
  kernel-enforced read-only sandbox.
- The harness can run the tagged legacy executable and compare only the
  declared product manifest with `tools/compare_baseline.py`.
- `tests/run_transaction_gate.sh <case>` traces all writes, exercises each
  inventoried writer failure point, rejects an out-of-root path, interrupts
  before/after marker creation, and proves that readers see either the complete
  prior generation or the complete new generation, never a mixture.

## Phase 1 - Establish one canonical state contract

### Changes

- Introduce canonical three-dimensional pressure-level arrays `(x,y,z)` and
  separate two-dimensional surface arrays `(x,y)`.  The legacy `z+1` layout may
  exist only inside the old writer adapter during shadow mode; contract and
  physics routines never receive it.  Remove that adapter in Phase 4.
- Replace LAPSPREP's repeated
  `NCVID -> NCVGT -> initialize -> validate -> STOP` blocks with a small
  declarative field-specification table and one reader adapter.
- Read and validate time, dimensions, and units from the file instead of
  assigning expected labels and validating those labels against themselves.
- Add versioned NetCDF variables and writer/reader adapters for cell-level
  validity and source provenance for persisted COM and hydrometeor products.
  Carry these masks from derivation into qbal and LAPSPREP.  Do not discard the
  radar support mask and reconstruct it later from numeric COM values.
- Freeze exact schema names and types before implementation.  For compatibility
  with the current NetCDF interface, the initial schema uses the physical
  variable's on-disk order `(record,z,y,x)` and adds `<field>_valid`,
  `<field>_quality`, and `<field>_source` with the same dimensions and NetCDF
  `int` storage (`valid` is restricted to 0/1; nonnegative documented bits are
  used for quality/source).  Variable attributes define units and bit meaning;
  global attributes define `cloud_bal_schema_version`, valid time convention,
  grid identifier, and disk order.  The in-memory radar LOS view is
  `(x,y,z,radar)`; if diagnostic persistence is enabled its disk order is
  `(record,radar,z,y,x)`, with site/time metadata indexed by `radar`.  The
  round-trip gate checks these exact definitions and Fortran/disk transposition,
  not just in-memory masks.
- Convert legacy `istatus`, radar status, `wind_available`, `omo_valid`, and
  missing sentinels into the single stage result at I/O boundaries.  Remove the
  downstream copies once their callers use the canonical result.
- Define required-field coverage policy once.  A partially valid below-ground
  humidity field is not automatically equivalent to an unreadable field.
- An optional gridded observation is still represented by correctly shaped
  canonical arrays and metadata.  If radar reflectivity is unavailable, every
  `radar_reflectivity%valid` cell is false with `RAW_MISSING`; values are never
  synthesized as zero or made valid.  This is `RADAR_ABSENT`, not stage
  failure: the radar transport/downdraft branch is an exact `OK` no-op while
  cloud-only column physics may continue.  If cloud and radar support are both
  absent the whole column stage is an exact no-op.  A supplied radar field with
  corrupt dimensions/units/time encoding remains `FAILED`.
- Add the existing post-QC radial-velocity path as an explicitly external
  observation adapter boundary.  Its absence is valid; if present, `vrad`,
  `nyquist`, time, site, beam geometry, QC/valid/source, and LOS uncertainty
  must enter together.  Cloud-BAL neither reads raw `vXX` files independently
  nor repeats the wind-analysis assimilation.
- Version 1 intentionally adapts the current remapped gridded samples, not a
  new ragged raw-ray format.  Its identity is the first 128 bits of
  `SHA-256(schema_version, grid_id, canonical cell-center coordinates and
  spacing, radar_id, volume_time, analysis_time, x, y, z)` and is stored as
  `observation_id_hi/lo`; the full digest and tuple are retained in the
  manifest.  Duplicate identity or reuse across a different grid is a contract
  failure.  The beam vector is computed once from radar site to the canonical
  grid cell.  After velocity QC but before wind
  insertion, wind analysis applies the frozen deterministic
  `ASSIMILATED/HELD_OUT` mask.  Both subsets keep `(x,y,z,radar)` shape and
  masks, while only `ASSIMILATED` samples can update analyzed wind.  Raw
  azimuth/range/sweep preservation and ray-volume integration are explicitly a
  future schema version, not an alternate Phase-1 representation.

### Exit gate

- `tests/run_contract_roundtrip.sh` writes and reads each schema version and
  proves byte-identical valid/source masks and exactly-once unit conversion.
- A NetCDF-backed LAPSPREP test with default contract enforcement accepts a
  normal input, preserves partial valid masks, and rejects wrong time, units,
  and dimensions before array use.
- No interior cloud/radar/balance routine compares a physical value with the
  LAPS missing sentinel.
- A source cell can be traced from ingest to qbal and WPS without losing source
  bits; a transformation may add a documented source bit but may not infer or
  erase provenance silently.
- A linked column-physics call receives cloud fraction/type, reflectivity, and
  lightning only through `cloud_bal_state`; deleting any one state field causes
  the declared coverage result rather than a common-block/file fallback.
- LOS axis-pattern and identity fixtures prove exact beam/component/disk order,
  grid-specific 128-bit IDs, and rejection of cross-grid key reuse.
- The real default-enforcement LAPSPREP smoke run now succeeds in the isolated
  harness.  This runtime gate was intentionally deferred from Phase 0A.

### Required-field policy

- `FAILED`: unreadable required field, wrong time/dimension/unit after
  permitted legacy conversion, or no valid cells for a field declared required
  by that stage.  Candidate processing stops.  An all-invalid optional field
  follows its explicit absent/no-op policy.
- `DEGRADED`: partial but policy-sufficient coverage or a legacy schema without
  persisted provenance.  Shadow diagnostics may run; active publication may
  not.
- `OK`: required metadata and frozen usable-coverage requirements pass.  Cells
  outside that support may be invalid or quality-marked without downgrading the
  stage.

Below-ground humidity follows one documented fill policy in the ingest adapter
before the canonical mask is committed; it is not rejected merely because the
raw file contains terrain-masked cells.

## Mandatory migration and deletion inventory

Each row must have a caller audit, shadow-end commit, and final linked-symbol
check.  A target phase cannot close while both old and new implementations are
reachable, except through the named shadow adapter.

| Existing implementation | Canonical replacement | Removal gate |
|---|---|---|
| `cloud_bal_field_contracts`, downstream `omo_valid`, `wind_available`, `valid_omega`, `source_valid` policies | `cloud_bal_state` and I/O adapters | Phase 1 contract round-trip and caller audit |
| base/top scans in `get_cloud_deriv`, layer/profile code in `vv.f`, `get_radar_deriv.f`, and `cloud_bal_cloud_profiles` | one layer map/profile in `cloud_bal_column_physics` | Phase 2 linked production layer tests |
| `pcpcnc:cpt_fall_velocity` and radar `phase_terminal_velocity` | one terminal-velocity API in `cloud_bal_column_physics` | Phase 2 phase/trajectory properties |
| fixed-height `vertical_motion_conversions` and radar-local conversion | local `rho*g` conversion in `cloud_bal_state` | Phase 2 conversion and shadow comparison |
| separate phase allocation and moisture-transfer branches | one column ledger in `cloud_bal_column_physics` | Phase 2/4 water and phase closure |
| `LEIBP3` coefficient formulas, `LEIB_SUB` correction formulas, and separate continuity indexing | `cloud_bal_balance_operator` public `S`, `D`, `A=D S`, weighted A-grid `G`, and exact `L` | Phase 3 manufactured and production tests |
| x/y/scalar boundary and destagger variants | one operator boundary policy | Phase 3 narrow-domain and support-ring tests |
| report-only `cloud_bal_wind_modes` formulas | final-candidate discrete mode metrics in the balance operator | Phase 3 gate implementation |
| raw/full-tree `get_multiradar_vel` and `qcradar` products | external wind owner plus one canonical post-QC LOS adapter; no Cloud-BAL raw reader | Phase 1 LOS absent/present round trip and no-double-use test |

`tests/check_obsolete_symbols.sh` fails if a removed symbol remains reachable
in a final executable, if a missing sentinel comparison exists outside the
listed I/O adapters, or if a dormant alternate implementation can be enabled by
a namelist/environment switch.  It combines source search with linker maps and
`nm` reachability and sweeps the supported namelist/environment combinations;
it explicitly audits `vv.f`, `vv_lgt_ct.f`, `get_radar_deriv.f`,
`cpt_fall_velocity`, every vertical-motion conversion, and `rfill_evap`.

The six current candidate modules migrate rather than remain as facades:
`cloud_bal_field_contracts -> cloud_bal_state` in Phase 1;
`cloud_bal_moisture`, `cloud_bal_cloud_profiles`, and
`cloud_bal_radar_downdraft -> cloud_bal_column_physics` in Phase 2;
`cloud_bal_localization` and `cloud_bal_wind_modes ->
cloud_bal_balance_operator` in Phase 3.  The named old modules and public
symbols are deleted at their phase removal gate.

## Phase 2 - Produce hydrometeors and omega once

### Changes

- Replace the production base/top scans and the newer helper with one layer-map
  routine.  It must close top-boundary layers and return all disjoint layers.
- Route cloud type, cloud fraction, and thin-cloud condensate through that
  layer map.  Cloud regime supplies local support only.  It cannot create a
  velocity amplitude until a separate grid-mean dynamic driver and uncertainty
  are present in the canonical state.
- Use one phase allocator and one terminal-velocity function for precipitation
  concentration and S-band fall trajectories.  Valid reflectivity with an
  unknown phase uses a temperature-based mixed-phase estimate, receives a
  cell-level phase-uncertainty quality bit, and carries
  concentration/fall-speed bounds.  The stage is `DEGRADED` only if the
  resulting usable coverage/uncertainty gate fails.  S-band reflectivity
  and temperature are not treated as a unique retrieval of particle phase,
  size distribution, bright-band state, or downdraft energy.
- Diagnose cloud-regime support, precipitation distribution, and radar downdraft
  in this stage only.  Publish `hydrometeor`, `omega_target`, `valid`, and
  `source/support` together.  qbal may balance this target but may not rediagnose
  it.
- Implement trajectory transport as a conservative fall-flux remap.  A source
  flux must equal accepted destination flux plus an explicit boundary or
  microphysical loss or suspended reservoir.  Normalize interpolation weights
  only over physically accepted destinations, substep excessive displacement,
  and do not force downward crossing when air ascent equals or exceeds terminal
  fall speed.  The per-source ledger is:

  ```text
  source fall flux = deposited + suspended + boundary exit + microphysical loss
  ```
- Use the same valid wind/omega masks in transport that were established at
  ingest.  Cb, Cu, and lightning updraft protection is expressed as one source
  policy, not separate cloud-type branches.
- Convert `omega` and `w` with local pressure and virtual temperature through
  the canonical `rho*g` relation.  Missing omega never enters trajectory
  arithmetic; it produces a documented no-air-motion estimate in shadow mode
  and blocks active radar downdraft publication unless the input policy supplies
  another valid source.
- Compute the effective reflectivity-weighted terminal-speed mean and variance
  through the same phase/PSD/fall-speed policy for the optional LOS operator.
  This is a diagnostic output with provenance, not a second hydrometeor
  retrieval.  Record any monotonic attenuation of `omega_target` in result
  diagnostics; attenuation is owned only by the balance stage and never changes
  the accepted hydrometeor ledger.
- Keep cooling/evaporation as diagnostic available energy only.  Do not change
  vapor, temperature, or hydrometeor mass until a paired water-and-energy
  budget is implemented and approved.

### Exit gate

- Property tests close layer mass, phase sum, paired water transfers, and every
  accepted fall-flux ledger.  Radar observation increments are reported
  separately and are not falsely labeled as conservation of pre-analysis total
  water.
- Top-boundary, multilayer, tilted shaft, strong-updraft/suspended particle,
  domain-boundary, partial observation, and missing-wind cases use the same
  kernel and require no case-specific fallback branch.
- Repeated execution is deterministic, observed radar cells are immutable, and
  the dormant evaporation routine is unreachable.
- LOS fixtures prove: missing velocity is an exact no-op; folded/bad-Nyquist or
  time-mismatched data are excluded; one beam leaves its perpendicular null
  space unclaimed; good and ill-conditioned multi-radar geometry are
  distinguished; fall-speed uncertainty increases through mixed phase and the
  bright band; and `ASSIMILATED` versus `HELD_OUT` lineage survives round trip.
- The linked production `get_cloud_deriv` test closes a cloud at `KCLOUD`, and
  the radar API rejects mismatched integer phase-array dimensions, nonphysical
  pressure, non-finite configuration values, and non-finite output before any
  commit through the same canonical validator.

## Phase 3 - Replace qbal correction with one exact localized operator

### Changes

- Make the optimization variable the published canonical A-grid increment
  `delta_x=(delta_u,delta_v,delta_omega)`.  There is no face-to-A-grid `C` and
  no claim that stagger/destagger is an identity.  One stagger operator `S`
  maps a canonical state or increment to x/y/p faces; `D` maps those oriented
  face fluxes to cell continuity.  Define the actual canonical continuity
  operator once as `A=D S`.
- Freeze `S` and `D` in pressure coordinates.  Let component direction
  `r=x,y,p` correspond to `u,v,omega`, with coordinate `xi_r` increasing
  eastward, northward, and toward increasing pressure.  For an interior face
  `f` between A-grid cells `L,R`:

  ```text
  S(r,f,L) = abs(xi_R-xi_f)/abs(xi_R-xi_L)
  S(r,f,R) = abs(xi_f-xi_L)/abs(xi_R-xi_L)
  (S_r x_r)_f = S(r,f,L)*x_r,L + S(r,f,R)*x_r,R.
  ```

  This one expression defines `S_x u`, `S_y v`, and `S_p omega`, including
  nonuniform `dx/dy/dp`.  For background-state residuals, external x/y faces
  use the nearest valid A-grid value and external p faces use canonical
  `omega_top_boundary`/`omega_bottom_boundary`.  For every cloud/radar
  increment, external, terrain-cut, and inactive-support face values are
  exactly zero.  An interior face is active only when both adjacent component
  values, metric distance, face measure, and localization are valid; otherwise
  its increment is zero and an adjacent cell requiring that face is excluded
  from the active residual domain.  No interpolation renormalizes over a
  missing side.

  For cell `c`, `M_c=dx_c*dy_c*dp_c/g`; x/y/p-face measures are respectively
  `dy*dp/g`, `dx*dp/g`, and `dx*dy/g`.  With a single global face orientation,

  ```text
  D(c,f) = s_cf*A_f/M_c,
  s_cf = +1 for outward and -1 for inward flux,
  A(c,r,j) = sum_f D(c,f)*S(r,f,j),
  (A delta_x)_c = sum_(r,j) A(c,r,j)*delta_x(r,j)  [s-1].
  ```

  Internal face fluxes cancel pairwise.  The signed Version-1 increment
  boundary flux `q_bc` is exactly zero; it is never fitted by removing a mean.
- Put all localization and change cost in one diagonal canonical coefficient
  `K(r,j)=balance_beta(j)*kappa(r,j)`.  `kappa_u/kappa_v` are the accepted wind
  increment variances and `kappa_omega` is the empirical target uncertainty,
  with the corresponding squared component units.  Outside support `K=0` and
  the variable is fixed at zero; every active `K` is finite and above the
  declared conditioning floor.  Using the cell-measure inner product, define
  the three published component corrections explicitly:

  ```text
  G_r(lambda)_j = -K(r,j) * sum_c M_c*A(c,r,j)*lambda_c,
                  r = x(u), y(v), p(omega)

  L(lambda) = -A G(lambda) = A*K*A^T*M*lambda.
  ```

  Thus `G` is exactly the weighted minimum-A-grid-increment solution of
  `0.5*sum_(r,j) delta_x(r,j)^2/K(r,j)` on active variables.  The matrix,
  published correction, and residual all call the same `S`, `D`, `A`, `K`, and
  `G`; no raw face gradient exists as a second intended operator.
- Balance the complete pre-correction residual, but only inside the compact
  cloud/radar support.  For monotonic attenuation `alpha`, let
  `Q(delta_omega)=(0,0,delta_omega)` on the A grid and let `R` denote the same
  `D/S` with immutable background boundary values:

  ```text
  delta_omega = alpha*(omega_target-omega_in),  0 <= alpha <= 1
  r_background = R(state_in)
  b_target     = A*Q(delta_omega)
  r_forced     = r_background + b_target
  L(lambda)    = r_forced
  delta_x      = G(lambda)
  r_final      = r_forced-L(lambda).
  ```

  Component compatibility is
  `sum_c(M_c*r_forced_c)=sum_boundary(s_cf*q_bc)` and the gauge is
  `sum_c(M_c*lambda_c)=0`.  `omega_target` is applied exactly once as a soft,
  uncertainty-weighted forcing.  The projection supplies local horizontal wind
  and may make a bounded vertical adjustment where the empirical target is
  uncertain.  No correction is allowed outside the compact support.  Final
  omega deviation from the attenuated target is an explicit gate, so the
  projection cannot silently cancel the diagnosis.  Background, forced, and
  final residuals are published from these exact equations.
- Define the momentum diagnostic once as `M(state; f,tau,delo,dp,metrics)` in
  this module.  The same routine and validated coefficients evaluate
  `m_background`, `m_forced`, and `m_final`; the gate applies to
  `m_final-m_background` relative to `m_forced-m_background`.  The solver may
  not assemble one momentum expression and validate with another.
- Remove the separate coefficient/index formulas currently present in the
  relaxation matrix, correction application, and residual routine.
- Build connected components of the actual nonzero `L=A K A^T M` graph induced
  by active canonical variables and `S/D`.  For each component,
  verify the metric/cell-volume-weighted compatibility condition
  `sum(cell_volume*rhs) = prescribed outward face flux`, fix the
  constant-lambda nullspace with a cell-volume-weighted zero-mean gauge, and
  reject undersized, isolated, or
  incompatible components without changing the input.  Do not hide an
  incompatible forcing by silently projecting its mean away.
- Correct only the divergent velocity-potential increment required by the
  accepted `omega_target`.  Preserve the observed/background rotational flow.
  Because terrain, metrics, and grid transforms can create a small discrete
  curl even from a gradient construction, bound the forcing-attributable
  rotational remainder relative to the divergent increment using the same
  discrete mode operator; do not require mathematical zero on every grid.  If
  `R_rot` is RMS discrete curl and `R_div` is RMS discrete divergence of the
  forcing-attributable wind increment, both in `s-1`, require
  `R_rot <= R_rot_atol + R_rot_rtol*R_div`, with a frozen dimensioned
  `R_rot_atol` and dimensionless `R_rot_rtol`.  This is defined even for zero
  and tiny targets.
- Define authoritative A-grid cell support and derived face support separately.
  A face is active only when its adjacent valid cells and metric are active.
  `G(lambda)` is already the final support-masked A-grid increment; it is
  committed directly and cannot cross `beta=0`.  `S` is used only to evaluate
  face fluxes and is never an output transform.  No post-`G` destagger,
  restagger, or additional support filter is permitted.
- Use one bounds-safe boundary stencil policy for x, y, scalar, and the internal
  `S` map.  The canonical operator precondition is `nx>=4` and `ny>=4`;
  both the public `balcon`/qbal adapter and direct operator validator check it
  before array access.  A smaller domain returns unchanged input and `FAILED`.
- Gate the complete candidate transactionally on:
  - exact operator identity in a manufactured solution;
  - lower final continuity RMS/max than `r_forced` by the frozen required
    fraction, recomputed from the actual published-precision candidate;
  - momentum residual that does not worsen beyond tolerance;
  - bounded wind/omega/temperature/height increments;
  - zero increment outside support;
  - bounded final high-pass divergent energy and increment roughness relative
    to the unsmoothed feasible candidate and the locked case threshold;
  - finite converged solver state.
- If increment-only smoothing is needed, apply it only to the divergent
  potential and reproject with the same exact operator.  Do not filter the full
  wind or thermodynamic state.

The gates have a fixed priority: finite/shape/support and component solvability;
operator identity and convergence; continuity; hard increment bounds; momentum
and final high-pass metrics.  If the last three cannot all pass, attenuate the
`omega_target` monotonically and retry the same operator.  If no nonzero target
passes within the configured attempts, return the unchanged input as
`DEGRADED`; do not choose another solver or expand support implicitly.

### Exit gate

- For smooth nonuniform Wendland `beta`, variable `dx/dy/dp/tau`, and terrain
  masks, the pointwise manufactured test satisfies
  `-A(G(lambda)) == L(lambda)` within the selected floating-point tolerance.
  Separate axis-pattern tests prove `A(delta_x)==D(S(delta_x))` for u, v, and
  omega, and the metric-adjoint identity
  `<lambda,A delta_x>_M == <A^T M lambda,delta_x>`.
- Constant, disconnected, terrain-split, isolated-cell, and near-zero-beta
  components test the gauge, compatibility, and conditioning policy.
- A published A-grid field is bitwise unchanged outside support, including the
  one-cell ring next to the support edge.
- Continuity and momentum residuals are recomputed once more from the final
  support-masked canonical A-grid candidate through the same `R/A` operator;
  an internal face/work-grid pass alone cannot authorize publication.
- No-cloud/no-radar input is an exact no-op.  Momentum, continuity, energy, and
  roughness gates all execute in the production call path.
- A nonuniform `dx/dy/dp` and terrain/cut-cell manufactured case with nonzero
  `delta_omega`, interior p-face interpolation, explicit top/bottom/terrain
  zero-increment boundary flux, and `q_bc=0` verifies signed-face
  cellwise target response, compatibility, gauge, units, and beta placement.
  `nx/ny=1,2,3` fail unchanged at both public entry points, while the declared
  `4x4` narrow case is bounds safe.
- Zero and tiny `delta_omega` fixtures verify exact no-op/scale behavior and the
  absolute-plus-relative rotational gate; no ratio is evaluated with a zero
  denominator.
- Reused `ASSIMILATED` LOS samples remain report-only.  When independent
  `HELD_OUT` samples exist, the final candidate must pass the frozen no-worse
  LOS metric; absence of held-out data never falls back to reused samples.
- `BALANCE_ACTIVE` remains prohibited while Helmholtz/high-pass quantities are
  report-only.  Activation requires final-candidate metrics, thresholds, and
  rejection to be linked through production `balcon`, not only an extracted
  test routine.

### Provisional numerical metrics

The build records the exact threshold-set identifier.  Synthetic operator and
conservation properties use deterministic numerical tolerances:

```text
identity_error_i <= C*epsilon(work_kind)
                    *(abs(A(G(lambda))_i) + abs(L(lambda)_i)
                      + sum_j(abs(L_ij*lambda_j)))
                    + identity_atol_with_declared_residual_units
paired water/phase error <= max(1e-12, 1e-6*abs(reference))
outside-support increment == 0 bit-for-bit on the published A grid
```

`identity_atol` is derived from and recorded with the manufactured test's
dimensioned reference scale; a unitless `max(1,...)` is prohibited.  Zero,
tiny, highly variable coefficient, and multiple-resolution cases verify that
the tolerance neither hides an indexing error nor rejects roundoff.

Real-case continuity, momentum, maximum increment, rotational-remainder, LOS,
and spectral thresholds are not guessed from one storm.  A declared
calibration subset spanning cases and resolutions produces a proposal; hard
physical/finite/support bounds remain non-calibratable.  Freeze the threshold
file, then require it to pass disjoint held-out storms, resolutions, radar
sites, elevation/range bins, scan-time offsets, and liquid/mixed/ice regimes
before `BALANCE_ACTIVE`.  Reusing any calibration observation key or regime
partition as activation evidence is prohibited.  Until both artifacts exist,
the gate returns report-only and active publication is impossible.

## Phase 4 - Make LAPSPREP an output transformation only

### Changes

- Consume the accepted canonical state; do not infer new cloud/radar support or
  replace missing omega independently.
- Invoke the canonical column ledger for any approved paired
  vapor/liquid/ice/rain/snow/graupel transfer, then recompute virtual
  temperature and density once.  LAPSPREP itself owns no second transfer rule.
- Convert concentration to dry-air mixing ratio and `omega` to geometric `w`
  once at the documented output boundary.
- Remove duplicate phase, fall-speed, layer, and fallback implementations after
  the shadow comparison passes.
- Remove the legacy `z+1` interior layout.  A compatibility writer, if still
  required for a non-WPS format, receives separate canonical 3-D and surface
  fields and performs layout adaptation without physics or validation policy.

### Exit gate

- Cell and column total-water budgets close, all published hydrometeors are
  finite and nonnegative, and output units match the WPS schema.
- LAPSPREP contains I/O, conservative output conversion, and writing logic; it
  contains no cloud/radar diagnosis or missing-data fallback policy.
- The obsolete-symbol audit proves that the superseded layer, fall-speed,
  conversion, moisture, radar, and balance implementations are absent from the
  final linked executables except for documented I/O/ABI adapters.

## Phase 5 - Operational evidence and rollout

### Test matrix

Use a small invariant-oriented matrix rather than one test per guard:

1. canonical contract: normal, partial, absent, and metadata mismatch;
2. column physics: clear, top-boundary, multilayer, convective, stratiform;
3. radar transport: straight, tilted, suspended, boundary exit, partial echo;
4. radar LOS: absent, single-beam, good/bad multi-beam geometry, high/low
   elevation, folded velocity, mixed phase, and bright band;
5. balance operator: constant and smooth variable coefficients, terrain, small
   valid islands, no-source identity;
6. end to end: radar off/on, more than one grid resolution, and separate
   calibration and held-out cases with different cloud/radar coverage.

Mandatory integration fixtures also include production `get_cloud_deriv` with
a top-at-`KCLOUD` layer; qbal `nx/ny=1,2,3` exact unchanged-`FAILED` rejection
and `nx=ny=4` bounds-safe execution; malformed phase-array dimensions; missing and finite-sentinel wind
and omega; tiny/nonphysical pressure; and NaN/Inf configuration/output.  These
exercise linked production entry points, not copied or text-extracted routines.

Every exit gate is implemented as a command that returns nonzero on failure and
writes a manifest containing fixture, compiler, command, artifact path, metric,
threshold-set identifier, and result.  The required command set is:

```text
tests/run_full_tree_build.sh
tests/run_isolation_gate.sh
tests/run_transaction_gate.sh
tests/run_contract_roundtrip.sh
tests/run_column_properties.sh
tests/run_balance_properties.sh
tests/run_production_integration.sh
tests/check_obsolete_symbols.sh
tests/run_forecast_spinup.sh
tests/run_rollback_gate.sh
```

The end-to-end fixture includes the complete deriv -> qbal -> LAPSPREP input
chain, including `vXX/v00` and site/time metadata for LOS cases, and compares an
explicit product manifest rather than recursively comparing an archive.  It
injects a radar-coupling failure and a failure after each writer and requires
unchanged input, nonzero status, and no published partial output.

`tests/run_rollback_gate.sh <case>` deliberately fails a candidate generation,
selects the archived executable/config/schema/threshold bundle at a new run
start, writes to a clean generation, and verifies the complete legacy manifest
and hashes.  It also proves that the failed candidate, new legacy generation,
and previously current generation are never mixed.

### Future activation sequence (not compiled in this research build)

1. `SHADOW`: calculate the canonical diagnosis and balance candidate but
   publish the legacy result.
2. `HYDRO_ACTIVE`: publish only the conservative hydrometeor result after its
   closure gates pass.
3. `RADAR_TARGET_VALIDATED`: authorize a radar-derived dynamic target only
   after phase, fall-speed, trajectory, displacement, water/energy, and
   forecast spin-up evidence is accepted.  This is an evidence gate, not a
   publication mode.
4. `BALANCE_ACTIVE`: publish a localized divergent correction only after both
   the dynamic-target and balance-operator gates pass.

The only future publication modes are `SHADOW`, `HYDRO_ACTIVE`, and
`BALANCE_ACTIVE`; target validation is a prerequisite attached to the target,
not another branch in the execution code.  Keep one mode enum and one dynamic
authority predicate; do not add independent booleans for every subroutine.
At production integration, existing `L_BOGUS_RADAR_W`, `l_flag_bogus_w`, and
`RADAR_W_MODE` controls must be removed or mapped once at the top-level adapter
to this enum.  Today the radar switch is forced off, but the linked
derived-cloud path still sets `l_flag_bogus_w=.true.` and lower legacy routines
still read it.  A non-`OK` canonical stage returns the input
state unchanged with its `DEGRADED` or `FAILED` result.  It does not select a
hidden alternate physical algorithm, and radar-coupling failure cannot be
logged and then followed by COM/hydrometeor publication.

### Forecast wave check

The analysis code can limit wave excitation but cannot prove removal of model
acoustic or gravity modes.  For each activation case, run paired legacy,
radar-off candidate, and radar-on candidate forecasts over a fixed 0-3 h window.
Compare local maxima and pressure/vertical-velocity spectra as well as
domain-integrated divergence tendency, surface-pressure tendency, vertical
kinetic energy, and high-frequency precipitation/pressure oscillation.  Local
metrics prevent opposite-phase waves from cancelling in a domain mean.
If a model-level IAU or digital filter is evaluated, apply it to the accepted
cloud/radar increment only and keep it outside this analysis pipeline.

Forecast tolerances and frequency bands are proposed from the complete shadow
case set, reviewed, and frozen before radar activation.  A paired control that
exceeds any frozen local, spectral, or integrated threshold blocks
radar-derived target authorization; report-only diagnostics do not count as a
gate.

### Git and evidence policy

- Use one reviewable commit per phase; do not mix physics, build integration,
  and calibration in one commit.
- Push a phase to GitHub only after its exit gate passes.  Record the commit,
  build command, test output, baseline manifest, and isolated result path.
- Calibration values (`Rh`, `Rp`, velocity and efficiency limits) are changed
  only in a separate evidence commit using multiple cases and resolutions.
- Tag and archive the last accepted executable, namelist, schema, and threshold
  set before activation.  Operational rollback selects this versioned bundle
  and a clean output root; candidate and legacy products are never mixed in one
  atomic product set.

## Adversarial-review acceptance checklist

This checklist merges the reviews pinned to
`main@cb0a5713f1acd737fa9a058f9d32adedf71bd9d1` and
`cloud-bal-shadow-contract-20260901@088a996f42424c4c743984cb666021956e9d4be6`
on 2026-09-01.  It is the
promotion authority for the implementation: a checked source change is not
equivalent to a checked scientific or operational gate.  `ACTIVE` remains
prohibited until every applicable P0 item is closed by the named executable
test and an exact-head manifest.

The current runtime enum is only `OFF -> SHADOW`.  There are no lower-level
authority booleans.  `OFF` does no candidate calculation and is
legacy-bitwise-identical; `SHADOW` may calculate but cannot modify operational
fields.  The longer activation sequence above is a future interface proposal,
not an authority present in this source tree.

### P0 implementation and promotion gates

| ID | Required invariant/change | Implementation owner | Executable evidence | Current state |
|---|---|---|---|---|
| P0-BASE | ANAL/MODL/reference executables are independent read-only inputs with verified hashes | Phase 0B harness | `run_isolation_gate.sh`, baseline `sha256sum -c` | frozen 21-file inventory and three-time snapshot manifest pass; legacy executable rerun and real candidate comparison remain blocked/not run |
| P0-ORIGIN-INPUT | one original-source-derived read closure supplies FUA `U3/V3/T3/HT/SH/OM`, FSF `PSF`, LT1 `HT/T3`, LQ3 `SH`, pre-QBAL LW3 `U3/V3/OM`, LCO `COM`, LSX `PS`, grid/pressure/config/time; final bigfile/WPS/met_em/balance output is never an input | real-data adapter and manifest | `check_qbal_real_inputs.py`, `run_real_input_inventory.sh`, undeclared-open trace | four hourly prepared source sets and static hashes pass; LT1/LQ3/LCO/LSX regeneration is missing, so all four direct closures correctly remain `BLOCKED` |
| P0-UPSTREAM-FRESH | the original radar/wind/surface/temp/cloud/humidity/derived DAG runs in an empty isolated generation; every stage checks all reads/writes, VRT completes before temperature, and a stale COM can never satisfy a failed derived stage | isolated original-chain runner | forced missing input/write failure, stale-COM fixture, complete open-path manifest | pending; original shell has asynchronous VRT ordering, zero-exit failure paths and unconditional product success assignments |
| P0-BACKGROUND | one explicitly pinned FUA/FSF pair supplies every background field and records valid/reftime; field-level fallback, mixed cycles and file-list-order selection are rejected | background adapter | multiple-cycle/order permutation and missing-variable tests | four 06 UTC-cycle pairs are pinned; original `get_best_fcst` minimum-lead assignment defect and per-field status overwrite remain to be removed in the isolated source |
| P0-RAD-PROVENANCE | candidate radar input is VRZ plus explicit coverage/QC provenance, not mixed LPS; `-10 dBZ` is no-echo/unknown and never support; VRT `TID=2` is bright-band quality, not phase; S-band comes from a hashed registry; reused wind LOS cannot be independent validation | radar adapter | real VRZ/VRT/Vxx contract test, no-echo/terrain mask, registry and no-double-use gates | canonical LOS now requires dealiased velocity, radar provenance for velocity/Nyquist/sigma, unique radar IDs and deterministic cell IDs; real source-time/site registry, terrain adapter and independent uncertainty remain pending |
| P0-IFX | all focused and full-chain Fortran uses one pinned ifx 2026 profile with exact flags, NetCDF/HDF5/Intel runtime hashes and no GNU/ifort fallback | toolchain/build harness | clean out-of-source strict/release link, `ldd/readelf`, endian round trip | focused strict ifx suite passes after missing-omega finite guard; full original tree and dependency stack remain pending |
| P0-MODE | one top-level mode enum; radar defaults `OFF`; non-`OK` never changes or publishes a candidate | state/coordinator and thin legacy adapters | OFF exact identity, SHADOW no-authority, invalid-mode deep-copy tests | focused coordinator accepts only OFF/SHADOW and tests pass; production callers and any future promotion adapter are absent |
| P0-STATE | value, valid, quality, source, time, dimensions/layout, unit, algorithm/config identity travel together; sentinels exist only in adapters | `cloud_bal_state` | contract/NetCDF round trip, partial/malformed/absent fixtures | one `cell_is_usable`, canonical bottom-to-top order, disjoint status values, `above_ground`, pressure/dry-air mass measures, and malformed/provenance tests pass; source age, NetCDF serialization and full adapter round trip pending |
| P0-RAD-VALID | no missing/invalid omega, pressure, wind, phase, dBZ, or configuration value enters a trajectory; valid fallback is explicit and degrades the stage | column physics | sentinel/NaN/Inf/all-false/missing-wind properties | core guards and missing-omega/high-dBZ/config tests implemented; full property matrix pending |
| P0-RAD-FLUX | for `r=Vt-w>vmin`, one rate `F=rho_d*q*r*area` is used for travel and concentration transfer; otherwise no trajectory is advanced and the nonnegative rate is suspended | column physics | strong up/down, suspended, variable-`Vt` manufactured ledgers | density-consistent relative rate and strong-ascent/downdraft tests implemented; storm-motion and manufactured convergence remain pending |
| P0-RAD-LEDGER | every source closes `input=deposited+suspended+boundary_exit+observation_blocked+microphysical_loss`; observed cells stay immutable | column physics | domain-exit, blocked-destination, partial-echo property tests | ledger, boundary-exit, blocked-observation and closure tests pass; per-source persisted ledger pending |
| P0-RAD-MERGE | one pristine background snapshot plus radar work: an observed echo replaces background precipitation at that cell, descendants add their transported increment, and a prior candidate is rejected as input | column physics | observed/descendant overlap, reuse and source-permutation tests | overlap policy and candidate-reuse rejection pass; explicit source-permutation test pending |
| P0-RAD-PHASE | phase-array shape and codes, configured S-band provenance/range, physical dBZ ceiling, type 3/10/11 protection, and empty-mask behavior are explicit | column physics | phase 0--5/out-of-range, high-dBZ, type and empty-support matrix | canonical phase contract, invalid-code rejection, configured S-band bounds, dBZ ceiling and type-11 test pass; wavelength is not used as an unsupported physical multiplier; complete matrix pending |
| P0-RAD-ENERGY | evaporation/sublimation/melting may affect downdraft only through paired hydrometeor, vapor, temperature and moist-enthalpy changes; until then cooling is report-only | column ledger | water plus moist-enthalpy closure and no-double-count test | bounded water/enthalpy kernel passes; evaporation coupling remains source-locked OFF as required |
| P0-QBAL-ONE | publish only the canonical A-grid increment from one `S`, `D`, `A=D S`, `K`, `G=-K A^T M`, `L=-A G`; no later taper/destagger/projection changes it | balance operator and qbal adapter | axis, manufactured identity, adjoint, final-published-state residual tests | standalone operator identities/axes/final residual pass; legacy qbal adapter and final writer path pending |
| P0-QBAL-EDGE | full-state residual includes immutable background faces across the support edge while normal increment flux is exactly zero | balance operator | uniform-flow compact-support and lateral-boundary tests | focused operator freezes normal velocity degrees of freedom at support/domain edges and the uniform-flow compact-support test passes; native terrain/lateral adapter evidence remains pending |
| P0-QBAL-COMP | connected components of nonzero `L` pass volume-weighted compatibility and gauge; only a component with an explicit dynamic target has modification authority | balance operator | disconnected, no-target component, terrain-split, near-zero-beta properties | compatibility/gauge, disconnected/isolated rejection and targetless-component bitwise identity pass; real terrain split remains pending |
| P0-QBAL-GATE | target-induced increment is projected once; recomputed physical residual cannot exceed background; increment, geostrophic, support and finite gates all pass | balance operator | nonconvergence/large-residual/rollback, background-nonworsening and final-state gates | attenuation retry and background rebalance were removed; one solve, real32 final-state recomputation, projected closure, background nonworsening and audit-preserving rollback pass; high-pass/production evidence remains pending |
| P0-TERRAIN | `above_ground` defines the only physics/coverage domain; below-ground values cannot create support; immutable terrain-surface omega supplies the lower flux | state ingest and balance operator | terrain-domain, terrain-touching support and boundary-flux closure | canonical domain/contiguity/support tests pass and stages mask it consistently; real PSFC adapter and pressure-tendency/advection lower-boundary construction remain pending |
| P0-THERMO | vapor and every hydrometeor use kg per kg dry air via dry-air density; any saturation transfer solves coupled water plus latent-heat temperature adjustment | column ledger/output adapter | analytical dry-air mass, water/enthalpy closure, liquid/ice bounded-root and failure-atomicity tests | separate pressure/dry-air measures, evaporation, supersaturation condensation and failure rollback tests pass; legacy LAPSPREP transaction wiring remains pending |
| P0-OUTPUT | calculation success and complete publication success are one transaction: stage, write, close, reread, validate, manifest, marker, atomic generation switch | output coordinator and all writer adapters | failure injection after every writer/open/write/close/verify step | primitive validates paths/hashes, holds a publication lock, compare-and-swaps expected current and rejects older valid times; product-specific reread, clean-tree/binary/input hashes and legacy writer migration remain pending |
| P0-STATUS | every reader/writer return is checked immediately; no later success overwrites an earlier failure and no routine assigns unconditional success | I/O adapters | 3-D-read then 2-D-success and first/middle/last writer failure tests | LAPS 3-D background status, all four balance writers and WPS OPEN/metadata/success checks pass; remaining I/O inventory pending |
| P0-LIGHTNING | lightning is integer value plus explicit validity/quality; no real sentinel is assigned to an integer | ingest/state adapter | absent/partial/invalid lightning fixture | real-to-integer sentinel removed and canonical validity field added; runtime partial/invalid fixture pending |
| P0-E2E | release and bounds full-tree builds link actual deriv/qbal/LAPSPREP/wind/radar entry points and run a zero-skip real-file smoke chain | integration tree | full-tree build plus production integration commands | pending |

### P1 scientific and engineering checklist

- [x] Cloud fraction/type contradictions are invalid or explicitly
  uncertainty-weighted; a zero cloud fraction cannot receive a minimum
  empirical updraft.
- [x] A connected layer is split into physically distinct sublayers when cloud
  type, precipitation regime, or accepted stability evidence changes; one
  embedded convective level cannot silently convert an entire deep layer.
- [x] The arbitrary depth/grid/level-count amplitude and sine profile have
  been removed.  Cloud type defines support only; a nonzero soft target awaits
  a separately valid dynamic driver and uncertainty.
- [x] Low-cloud/fog target is centered near zero unless accepted convergence or
  boundary-layer forcing supports a nonzero target.
- [ ] `dx` and `dy` remain independent, `dp` is nonuniform and cell-local, and
  legacy error constants/clamps have recorded occurrence rates and provenance.
- [x] Physical continuity residuals are unweighted.  Weighted objective norms
  may be reported separately but cannot hide taper-edge residuals.
- [ ] Before a rotational acceptance gate has authority, a boundary-defined
  Helmholtz solve reports divergent, rotational and harmonic energy plus
  reconstruction error.  Finite-difference divergence/vorticity RMS remains
  report-only.
- [x] WPS wind-coordinate metadata is derived and validated, not forced to
  grid-relative unconditionally.
- [x] Comparison tooling rejects duplicate field keys and fails rather than
  silently omitting a numerical summary after a parse error.
- [ ] CI separates strict and release Intel ifx profiles, enables bounds/FPE/
  uninitialized checks, records the exact HEAD, and is required on a protected
  promotion branch.  GNU and ifort fallback are intentionally prohibited.

### Required invariant, real-data integration and forecast matrix

Small manufactured cases are unit invariants only and never promotion
evidence.  The invariant matrix must contain clear/radar-absent exact no-op; all-missing
omega; positive/negative/NaN/Inf/sentinel values; all-false and disconnected
support; constant and variable beta; nonuniform `dx/dy/dp`; terrain contact;
boundary exit; observation-blocked transport; multiple-source permutation;
phase 0--5 and invalid phase; cloud type 3/10/11; solver nonconvergence; and
forced I/O failure.  Each failure returns the input unchanged and publishes no
partial product.

Real-case evidence cannot select only successful storms.  It spans clear,
fog/low cloud, nonprecipitating stratus, stratiform rain/snow, mixed/freezing
precipitation, convection/lightning/hail, partial radar coverage, terrain/
coast/domain edges, fast systems, and overlapping radars.  The fixed ablation
set is legacy, moisture only, cloud-target only, radar trajectory only,
localization only, and the full coupled candidate.

Promotion evaluates a fixed cold-start forecast window, including the first
10/30/60 minutes and 0--6 h precipitation, temperature/RH/water jumps, latent
heating/cooling, surface-pressure and gravity-wave noise, reflectivity and
precipitation skill, cloud ceiling, low-level bias, column water/enthalpy,
outside-support increments, and compiler/repeat reproducibility.  Calibration
and held-out seasons/cases remain disjoint.

## Definition of done

The improvement is complete only when all of the following are true:

- the full KLAPS tree builds and the canonical contract is used end to end;
- cloud/radar support remains local on the published grid;
- hydrometeor and total-water budgets close;
- the assembled and applied variable-coefficient operator are identical;
- continuity improves while momentum and high-frequency divergent measures do
  not worsen;
- reflectivity does not create an unsupported rotational vortex and the bounded
  discrete rotational remainder passes the frozen threshold;
- with one fixed compiler/toolchain, `SHADOW` publication is bitwise equal to
  the tagged isolated legacy result; candidate radar-off differences are fully
  declared by the product manifest and pass the frozen scientific gates;
- radar-on passes paired multi-case forecast spin-up checks;
- obsolete duplicate paths and temporary shadow code are removed;
- dormant radar evaporation remains disabled until a separately reviewed,
  paired water-and-energy implementation exists.
