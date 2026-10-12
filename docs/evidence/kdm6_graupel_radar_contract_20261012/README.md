# KDM6 graupel radar coefficient contract

KDM6 has a variable graupel mass coefficient in its radar calculation. Its
state-level density is `rhox = QG/BG`, bounded by the existing 100–900 kg m⁻³
scheme limits, and `ProgB_param` derives `cmg = π rhox/6`. With the existing
`dmg = 3`, the radar mass law is `m_g(D) = cmg D³`. This local coefficient
changes with QG/BG. The separate table-derived `avtg` and `bvtg` values are
used by bulk process moments and are not radar's `xam_g` and `xbm_g`.

`kdm6init` sets the shared radar exponent and shape (`xbm_g = dmg`,
`xmu_g = mug`) but does not set a global `xam_g`; it then called `radar_init`,
which evaluated `1/xam_g`. In KDM6, `cmg(i,k)` is copied to `cmg1d(k)` and
passed to `refl10cm_kdm6` as its level array `xam_g(k)`. That local value feeds
the graupel slope, Rayleigh reflectivity, and wet-particle mass. The wet
particle call previously used the stale scalar `xocmg`, even though its mass
argument was level-dependent.

The research patch preserves the exact zero-argument `radar_init()` entry for
already-compiled fixed-coefficient callers. A new KDM6 entry calls a private
shared initialization core that still sets the exponent reciprocal and radar
tables, while skipping scalar `xam_g` reciprocals. KDM6's wet-melting path now
derives `(1/xam_g(k))**xobmg` from the same level coefficient used to compute
particle mass. No fallback density or coefficient floor is introduced.

## Source and object lineage

The radar module source is the retained PR61 host copy at
`/var/tmp/pr61_ccn_origin_20261006/hostcopy/phys/module_mp_radar.F` (SHA256
`aa99da858be41efa579966680708d230123a7417560af0eb2e24f4c94e253688`). The
KDM6 build input starts from the pinned PR73 transformed source
`/var/tmp/pr73_native_first_violation.x3bvfn/build/source/module_mp_kdm6.f90`
(SHA256 `1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819`)
and the unchanged PR77 observer transform. That transform produces SHA256
`0575ece19473618adcfb1a937f92eb98a2f6155c8460452ac01c816760989981`, matching
the KDM6 object selected from the native scalar-Noah base archive
(`0b36a3d6ae2fe4d5ea4561fb456ff3961886dec9a1f1549d3b0eec95753d7cd5`). The
base radar object is `f6fafab46acba7136834c2b5957b3db85acef3b71e1ed1be50de8f35eb5334df`.

The patch was applied with `--fuzz=0` only to fresh scratch copies. The native
build used the pinned Intel `ifx 2026.0.0 20260331` profile and preserved
`-fpe0`. It copied the strict O0 plus `-no-vec` two-object Noah archive
(`747fab43af5d46187d549fe45d8501bbb88d744d358a8a423ec948a276633f26`) and
replaced only `module_mp_radar.o` and `module_mp_kdm6.o`. Its base executable
was `618b0bac7ce39b6c3ab686bf795d0503a5fed688ecab4dcbec7ab004b50b86f2`. The
candidate archive and executable are recorded in `receipt.json`; all runtime
inputs matched their pre-run hashes.

The linked archive retains the original `module_mp_radar_mp_radar_init_`
symbol, and KDM6 resolves the new
`module_mp_radar_mp_radar_init_variable_graupel_` symbol. A representative
inactive scheme caller still references the original zero-argument symbol.
This verifies symbol preservation; the inactive callers were not rebuilt or
run, so this is not a full inactive-scheme runtime ABI claim.

## Native result and limits

The candidate completed initialization through the first WRF output without
the prior `1/xam_g` divide-by-zero. The real output contains 1,468 cells with
positive `QGRAUP`, but `REFL_10CM` is zero in all those cells. The wet-graupel
consumer relation is therefore source-verified and compiled, but its local
wet-melting calculation was not observed at runtime in this case. This output
is `2026-08-16_12:00:00`; it is not the separate 13 UTC Cloud analysis
candidate. No QG, N, or BG values were injected into the WRF run.

## Initialization linkage and focused consumer

The inherited source call chain for this cold-start, single-domain run is:

`main/module_wrf_top.F:414 med_initialdata_input` →
`share/mediation_wrfmain.F:133 start_domain` →
`share/start_domain.F:58 start_domain_em` →
`dyn_em/start_em.F:1024 phy_init` →
`phys/module_physics_init.F:1758 mp_init` →
`phys/module_physics_init.F:4720-4722 CASE(KDM6SCHEME)/kdm6init` →
`phys/module_mp_kdm6.F:kdm6init/radar_init_variable_graupel`.

`start_em.F` gates `phy_init` around DFI backward stages (lines 1019-1021),
and the physics initialization dispatch is also tile/domain lifecycle code.
The observed candidate reached its time-zero WRF output, which confirms that
the cold-start KDM6 initialization path completed in this run. Restart,
nested-domain, DFI-backward, and multi-tile repeat behavior were not exercised;
the call-graph listing is static evidence for those paths, not runtime proof.
Retained source SHA256s for the WRF entry, start-domain wrapper, EM start,
physics initializer, and KDM6 source are recorded in `receipt.json`.

The focused pinned-Intel consumer executable separately calls the real
`kdm6init` twice with WRF's `rhoair0=1.28`, `rhowater=1000`, `rhosnow=100`,
`cliq=4190`, `cpv=4*r_v`, `hail_opt=0`, and `allowed_to_read=.TRUE.`. It
checks global `xam_g` stays zero through both calls, then calls `ProgB_param`.
This uses the same variable-graupel radar initializer reached from WRF, and
lets `ProgB_param` produce local `cmg` from two valid QG/BG states
(`rhox=200` and `700 kg m⁻³`). With global `xam_g=0`, it calls the
compiled `refl10cm_kdm6` wet/melting branch and gets finite, distinct
reflectivities (30.2968 and 26.8406 dBZ). A third column with absent graupel
and zero local coefficient remains finite. This is a definition-domain test
of the physical consumer call; it directly exercises `kdm6init` but does not
invoke full `phy_init`. It does not substitute for same-case wet-branch
consumption or forecast validation.

An independent input-to-time-zero readback on the same scratch candidate
found `MU` and six water components unchanged, `PH+PHB` unchanged, and `P+PB`
changed in 770,649 cells (maximum 0.0391 Pa). `W` changed in 1,476,306 cells
(maximum 0.6028 m s⁻¹); `QNCCN` changed in 2,573,532 cells (maximum
5.0292×10⁹ kg⁻¹); `U` and `V` and `QNCLOUD`, `QNICE`, and `QNRAIN` were
unchanged. The initial output exports QGRAUP but not graupel volume, so a full
Q/N/B initialization contract is not assessed. These initialization deltas
are recorded in the separate native readback receipt.

The run then stopped with floating invalid during first-step integration. The
captured first frames resolve to
`module_big_step_utilities_em::calc_ww_cp_` →
`module_em::rk_step_prep_` → `solve_em_` → `solve_interface_` →
`module_integrate::integrate_` → `wrf_run`. This later failure does not negate
the scoped radar initializer result and does not establish a valid initial
hydrometeor field, wet-graupel reflectivity, or forecast acceptance.

The receipt preserves the source, object, archive, executable, log, and output
hashes without embedding the large native sources or input manifest. The full
captured logs remain under the fresh `/var/tmp/pr80_kdm6_radar_contract.*`
work directory.
