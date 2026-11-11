# Model-input moment handoff

`tools/initialize_model_moments.py MANIFEST OUTPUT RECEIPT` runs the pinned,
caller-attested `real` producer in a fresh temporary working directory, then
calls `tools/model_moment_driver.f90` linked to the common Cloud-BAL state and
completion routines. It never launches the forecast. `OUTPUT` and `RECEIPT`
must be new, distinct paths. By default, the source model fields, including water masses,
wind and thermodynamic fields, are read back unchanged. A failed operation
removes its published output and temporary files.
Completion failures report the cell and slot, a reason code (1: invalid or
missing input, 2: empty analytical interval, 3: inadmissible candidate), and the
computed interval when available. The interval uses the ideal cap/density;
native REAL32 rounding can permit a candidate at its boundary. Failures do not
publish a completed file or receipt.

The JSON manifest contains `stage: "fresh_real_before_model_launch"`, an
explicit integer `use_theta_m`, `mp_physics: 37`, and `producer`, `driver`, `source`, `build`,
`policy`, and `candidates` objects, each containing an absolute `path` and its
SHA-256 as `sha256`. `inputs` is a list of these objects with a unique `name`
basename for each file to copy into scratch. Include `namelist.input`, all
required producer inputs, and an explicit `restart = .false.` and
`use_theta_m` matching the manifest and `mp_physics = 37`. The file attributes,
policy, manifest, and namelist must agree on the scheme; the file
`USE_THETA_M` attribute must match the manifest. Standard native field unit
attributes are required; only explicit equivalent spellings are accepted. Previously produced model input, restart,
and history files cannot be producer inputs. The executable runs with no
arguments. Source and build files and the identity of the executable are
operator attestations; hashes do not establish source-to-binary provenance.

The policy JSON has `source`, `mp_physics: 37`, `declared_before_experiment: true`, and arrays
`mass_threshold`, `lower`, `upper` (five slots each) and `number_cap` (four
slots). Bounds and number caps must lie within the pinned KDM6 CONTROL source profile;
strict subsets are allowed. The reference source hash is checked and recorded.
Thresholds remain explicit caller policy and are not asserted to cover every
native process branch. No per-case default is supplied.
Bounds are mean particle mass for the first three slots and bulk density for
BG. Thresholds are dry-air mass mixing ratios; caps are number per cubic
metre. The five slots are cloud, ice, rain, cloud-condensation nuclei (NN),
and graupel volume (BG).

The candidates NPZ contains a scalar string `source_sha256` matching the exact
fresh producer output. Each of `background`, `observed`, and `prior` has
`_value`, `_valid`, `_provenance` arrays of shape `(5,z,y,x)`. Values are dry
air specific numbers for cloud, ice, rain and NN and volume for BG, except
prior values specify particle mean mass for the first three, direct NN, and
BG bulk density. Validity is 0 or 1; provenance codes are observed 1,
background 2, explicit prior 3, and mass-zero 4. Background values must match
the native model file. The common kernel validates an observed moment first,
then background, then an explicitly supplied prior. Candidate hash binding
requires an exact matching prior run or an independently prepared NPZ for the
fresh file; this interface does not infer source data.

The receipt includes compressed cellwise source codes, policy and producer
identities, and hashes of file-state thermodynamic inputs. Density supplied to
the kernel is computed in real32 as `1/(AL+ALB)` from the model input. WRF may
recompute AL before advection, so this is a **file-state proxy**; the receipt
sets `native_first_use_verified` false. Its pressure, Exner and temperature
formulas describe the input state, not an observed first physics call. NetCDF
`T` is perturbation dry potential temperature for either `use_theta_m` setting;
temperature is `(T+300)*(pressure/100000)**(287/1004.5)`. The receipt records
the minimum and maximum temperatures computed by the driver. This
handoff does not establish scientific acceptance or forecast performance.

Run the focused fixture integration checks with
`tests/run_initialize_model_moments.sh`; it builds in fresh scratch using the
pinned Intel toolchain. The fixture producer is synthetic, not an actual
`real.exe` validation.

The pinned source-profile guard is an analytical envelope derived from the
nominal source slope/shape constants. The actual KDM6 builds REAL32 coefficients
and applies source-order branch arithmetic; exact non-adjustment at a PSD
boundary is not proven by this envelope. Native coefficient/boundary replay and
first-use evidence remain open.

## Joint ice-snow-number proposal

An optional manifest object `ice_snow_partition: {"path": "/absolute/proposal.npz", "sha256": "..."}`
selects `complete_ice_snow_initialization` in the same compiled driver. This is
an explicit external partition, not a cap-driven automatic conversion or a new
KDM6 process. Its SHA is checked before and after use. Default manifests keep
the original moment-only path.

The NPZ contains scalar string `source_sha256` matching the exact producer
output, nonempty UTF-8 string `source` (at most 256 bytes), scalar integer
`provenance` (observed 1, background 2, explicit prior 3), float32 arrays
`qi`, `qs`, `ni` in `(z,y,x)`, and a same-shape boolean/integer `valid` mask
with values 0/1. Mass fields are kg/kg dry air; NI is kg^-1 dry air. All three
values on the mask form one authoritative proposal. Invalid joint NI is not
replaced by other candidates. Observations for other moments retain their
usual priority. In the stream adapter, the field source bit means output
adapter; scientific provenance remains the caller's separately recorded
attestation, not proof of observational support.

The common routine requires equal masks, grid/time/units and usable metadata.
Stored QI+QS must preserve the prior frozen total within epsilon32 times the
larger total, using REAL64 arithmetic on stored REAL32 values. T and QV stay
unchanged because ice and snow have equal enthalpy in the common convention.
It supports no external frozen-mass increment and no other phase exchange.
The original analytical PSD envelope and REAL32 NI/cap check remain strict;
passing them does not prove native lambda will be unadjusted at first use.
Only complete STATUS_OK commits; DEGRADED or failure preserves the entire
output state.

This mode writes QICE and QSNOW along with the five moments and validates
returned selected QI/QS/NI/provenance, off-mask mass, nonnegative mass,
conservation and file readback. Other model fields remain unchanged. Its
receipt records the proposal source and selected-cell count and retains
`native_first_use_verified: false`. The historical B1 trace in the
[joint initialization report](ICE_SNOW_JOINT_INITIALIZATION_20261111.md)
is separate and does not certify a new joint proposal.
