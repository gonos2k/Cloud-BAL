# Model-input moment handoff

`tools/initialize_model_moments.py MANIFEST OUTPUT RECEIPT` runs the pinned,
caller-attested `real` producer in a fresh temporary working directory, then
calls `tools/model_moment_driver.f90` linked to the common Cloud-BAL state and
completion routines. It never launches the forecast. `OUTPUT` and `RECEIPT`
must be new, distinct paths. The source model fields, including water masses,
wind and thermodynamic fields, are read back unchanged. A failed operation
removes its published output and temporary files.

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
formulas describe the input state, not an observed first physics call. This
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
