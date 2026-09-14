# Research-only host patches

Apply `kdm6_number_basis.patch` and `kdm6_ccn_initialization.patch` together
to private copies of the reviewed host's `phys/module_mp_kdm6.F` and
`dyn_em/start_em.F`, respectively (`patch --fuzz=0 -p1` within each directory).
Do not apply them to the shared operational host.

- Public number fields use #/kg dry air; KDM6 internal moments use #/m3.
- `start_em` initializes missing CCN from the existing configured volume
  concentration, converting with dry-air specific volume. Other schemes and
  the existing nonmissing-field guard are unchanged.
- KDM6 preserves supplied CCN instead of resetting it on the first call.
- Cloud/ice effective radii use consistent volume mass and number moments.

`kdm6_diagnostic_initialization.patch` separately initializes the output-only
graupel-density diagnostic before it is read. It removes an undefined read,
not a physical density prior. Apply it to the same private KDM6 copy for the
repeated first-call tests.

These changes do not initialize missing rain numbers, choose a PSD, resolve
graupel volume policy, or establish full native/forecast acceptance. The separate
`kdm6_missing_graupel_volume.patch` is a physical-prior experiment, not part of
this unit correction. The numerical legacy zero-volume guard is separately
documented in `../docs/patches/README.md`.


`native_input_w_preservation.patch` fixes ordinary (non-WRFPLUS) host startup
so explicit `use_input_w=.true.` also preserves input W with a zero surface
and nonzero interior. Apply with `patch --fuzz=0 -p1` to a private `dyn_em`
copy. It leaves the default false path unchanged. This is a prerequisite for
future native-W ingestion, not an implemented ingestion path: enable the
option only after the source-bound input has been validated and both W time
levels populated. Do not inject an epsilon surface velocity to bypass startup.

WRFPLUS still resets the option before this guard and is not covered. Normal
boundary/halo handling and subsequent physical evolution remain active. The
patch does not supply cloud forcing or convert pressure omega to W. Exact
application and independent RED review are recorded in
`../scratch/cp02_input_w_preserve_3hr6zty0/RESULT.json`; the exact startup branch also passed pinned Intel O0/O2 regression tests
with a fallback sentinel stub. A fresh full host build and pinned-runtime link check subsequently passed;
see `../scratch/cp02_native_host_build_9qvq0zru/RESULT_BUILD.json`.
The manufactured full-host startup run failed in KDM6 radar initialization
(`1./xam_g`) before initial W output; see
`../scratch/cp02_native_w_host_startup_20260911/RESULT_RUNTIME.json`.
After the radar correction below, the full initial W array exactly matched
the supplied manufactured input; see
`../scratch/cp02_native_w_host_startup_20260911/RESULT_RADAR_RETRY_RUNTIME.json`.
The subsequent first timestep failed in KSAS, so this verifies startup
preservation only. No operational host was modified.

`kdm6_variable_graupel_radar.patch` fixes KDM6 radar initialization and wet
graupel reflectivity. KDM6 skips the unset global graupel mass coefficient at
initialization and uses each cell's inverse mass law in reflectivity. Fixed
coefficient callers retain the default behavior; no density prior is added.
Apply with `patch --fuzz=0 -p1` in the private host's `phys` directory and
rebuild the full host because the `radar_init` module interface changes.
Pinned Intel O0/O2 tests and RED source review passed; see
`../scratch/cp02_kdm6_radar_mass_d575oozx/REVIEW.json`.
This is a radar correction, not a cloud omega algorithm. Test harnesses stay
in scratch and are not deployment code.

`ksas_inactive_convection.patch` limits the KSAS critical-work-function
timescale calculation to active convection columns. Inactive columns can have
zero updraft velocity; they retain the existing initialized timescale. Active
equations and limits are unchanged, and no denominator floor is added.
Apply with `patch --fuzz=0 -p1` in a private host's `phys` directory and rebuild.
RED source review, diagnostic tests, and pinned optimized O2 tests are in
`../scratch/cp02_ksas_inactive_gnkh1dyg/REVIEW.json`. The fresh full host then
passed the repaired KSAS site and reached microphysics, where ice-slope
evaluation failed; see `../scratch/cp02_ksas_inactive_gnkh1dyg/RESULT_RUNTIME.json`.
The first timestep remains incomplete; other divisions in KSAS are outside
this fix.

`kdm6_zero_ice_number_limit.patch` evaluates the existing bounded ice-size
formula at zero number without `log(0)` or division by zero. It uses
`1/lamdaimin` for the inverse-slope limit and zero for the two later unbounded
lambda evaluations; the existing size clamp then reconstructs number at its
original location. Positive-number formulas, mass, and sedimentation order
are unchanged. No new size or number constant is introduced. Apply with
`patch --fuzz=0 -p1` in the private host's `phys` directory and rebuild.
[RED source review](../scratch/cp02_kdm6_ice_limit_iado8lli/RED_REVIEW.md) and
[GREEN full-module tests](../scratch/cp02_kdm6_ice_limit_iado8lli/GREEN_REVIEW.md)
record the bounded verification.
Pinned Intel O0/O2 passed six candidate cases each; the original fails both
signed-zero cases, while the four other cases have identical reported results.
The fresh full-host build and runtime-link checks passed; see
`../scratch/cp02_kdm6_ice_limit_iado8lli/RESULT_BUILD.json`. The actual startup
run passes the ice-slope site but fails later at `bgevp=pgevp/rhox`; see
`../scratch/cp02_kdm6_ice_limit_iado8lli/RESULT_RUNTIME.json`.
This implements an existing numerical
limit, not observed ice-number input, physical-startup acceptance, or a cloud
omega algorithm. Test artifacts remain in scratch.

`kdm6_zero_graupel_volume_rate.patch` skips conversion to volume rate when
the corresponding graupel mass rate is zero. The minor loop has already
initialized the volume rate to zero. Nonzero rates retain the original
density division, so missing density is not filled or bypassed for them.
Apply with `patch --fuzz=0 -p1` in the private host's `phys` directory.
[RED review](../scratch/cp02_kdm6_zero_volume_rate_5bwvlcfr/RED_REVIEW.md)
endorses these two guards. [GREEN full-module tests](../scratch/cp02_kdm6_zero_volume_rate_5bwvlcfr/GREEN_REVIEW.md)
pass three cases each with pinned Intel O0/O2. The original warm no-graupel
case fails at the repaired division; the other two cases retain identical
logged results. That warm-only host build completed, but its actual run failed
at the cold deposition division; see
`../scratch/cp02_kdm6_zero_volume_rate_5bwvlcfr/RESULT_RUNTIME.json`.

The 2026-09-14 extension uses the existing zero-initialized `bgdep` for the
cold deposition contribution, assigning `pgdep/rhox` only when `pgdep` is
nonzero. The maintained patch now includes all three rate guards and applies
to the ice-limit source (before the warm guards); do not apply it twice.
[Fresh full-module evidence](../scratch/cp02_cold_clear_nvvvj7kw/RESULT.json)
reproduces the cold clear-cell failure at line 2611 with both pinned O0/O2
original builds. Both candidate builds pass all four cases; the three controls
and candidate O0/O2 logged outputs are identical. Exact patch application is
checked against the compiled candidate source. The earlier cold fixtures
passed even without the fix and were not regression reproductions.
The subsequent [full-host run](../scratch/cp02_native_current_run_95gbqi4y/RESULT_RUNTIME.json)
passes this site and stops in optional reflectivity. With that diagnostic off,
[the next run](../scratch/cp02_native_no_reflectivity_engdfdhc/RESULT_RUNTIME.json)
stops at nonzero graupel melting with unavailable density. Physical moment
initialization remains unresolved. All test code stays in scratch.

`kdm6_graupel_melting_domain.patch` requires available positive density for
graupel melting, enhanced melting, deposition/sublimation, and evaporation
rate generation. Zero-initialized inactive rates retain coupled mass/heat/volume
updates; the patch does not suppress a volume update alone. It also declares the
partially assigned `ProgB_param` diagnostic arrays `INTENT(INOUT)` to preserve
caller initialization and within-loop values with defined Fortran semantics.
Apply after the three-rate and `docs/patches/kdm6-zero-volume.patch` corrections,
together with `kdm6_diagnostic_initialization.patch`, using `patch --fuzz=0 -p1`
in the private host's `phys` directory. No new density or empirical parameter
is supplied. Retained density is not observational moment authority.
[Seven Intel O0/O2 cases](../scratch/cp02_graupel_defined_o5ecgopm/RESULT.json)
pass; original small-mass/zero-volume cases 5/6 fail. Five logged controls match,
including small mass with valid volume. Existing final trace-mass padding is
unchanged. This is bounded numerical repair, not physical cloud omega or CP02
completion. The melting-only full-host test passed that site but stopped at
nonzero `pgevp/rhox`, also reproduced with actual 12 UTC input. The subsequent
[11-case O0/O2 extension](../scratch/cp02_graupel_process_domain_46pn5bao/RESULT.json)
passes warm dry trace case 8 (original exit 134) and ten unchanged logged
controls. Cold fixtures are controls, not claimed new failure reproductions.
[GREEN](../scratch/cp02_graupel_process_domain_46pn5bao/TEAM_GREEN.md) and
[RED](../scratch/cp02_graupel_process_domain_46pn5bao/TEAM_RED.md) reviews retain
the bounded numerical scope. A fresh full-host build of this extension is underway.
