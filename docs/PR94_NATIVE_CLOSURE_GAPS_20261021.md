# PR94 Native Closure Capture Gaps — 2026-10-21

## Scope and source pins

This is a source audit for planning future closure diagnostics. It records where the frozen PR93-C4 WRF update obtains transport, lateral-boundary, and surface-moisture contributions. No model source was edited, and no closure or budget claim is made here.

The selected C4 source mapping is recorded in `/var/tmp/pr93_sources_c4_overrides_20261020.json`. The relevant source hashes are:

| Source | SHA-256 | C4 role |
|---|---|---|
| `/var/tmp/pr92_sources_c18_final_20261020/module_em.F` | `f88708844994a30540fc458aeede7e0eda4503a04a341caf714050e52f8c18af` | selected C4 `module_em.o`; scalar advection and RK scalar update |
| `/var/tmp/pr91_sources_c14_20261020/solve_em.F` | `d0ff9110811811c01ad13709bf5b538f7b92a49739211b0519aac55a81bc04a6` | selected C4 `solve_em.o`; RK ordering, boundary hooks, physics calls |
| `/var/tmp/pr87_joint_cycle_sources_20261016_v42/module_first_rk_step_part1.F` | `b902d535a0f6ca2eeb538192c623db53c3e172aebd55ee41b3911b28f81246ef` | selected C4 `module_first_rk_step_part1.o`; physics-driver setup |
| `/var/tmp/pr87_joint_cycle_sources_20261016_v42/module_first_rk_step_part2.F` | `6712dae70238e7d1c21786784698847dcee367f5a69c4f99fb7bd5c541ee9082` | selected C4 `module_first_rk_step_part2.o`; PBL physics tendency assembly |
| `/var/tmp/pr87_joint_cycle_sources_20261016_v42/module_pbl_driver.F` | `19585dd32f72e1172e15b072ecab5857c8f50092b4bc2114ba281e07282ba676` | selected C4 PBL driver; QFX-to-PBL surface boundary forcing |
| `/var/tmp/pr87_joint_cycle_sources_20261016_v42/module_bl_shinhong.F` | `92843e196b0e1fcae0af134b8f5a6e4d534dd9b47e76abc09de25531418b7ea3` | selected C4 Shin-Hong PBL tendencies |
| `/var/tmp/pr61_ccn_origin_20261006/hostcopy/dyn_em/module_small_step_em.F` | `cabf1a177d50fb0096db79644af20cfe6d75217dbe63ab406a7e29bb54c17634` | parent WRF `sumflux` and `advance_mu_t` implementations |
| `/var/tmp/pr61_ccn_origin_20261006/hostcopy/dyn_em/module_bc_em.F` | `6cfb52b849e3dd0b24769709cf502faa75886da454d9b668af725cccdc56d47f` | parent WRF scalar boundary relaxation routines |
| `/var/tmp/pr61_ccn_origin_20261006/hostcopy/share/module_bc.F` | `5cd9d775c88caf44d378040071a14c2dc1501d80a860c7a7b38dd8ec35a23c5b` | parent WRF final specified-boundary application |
| `/var/tmp/pr61_ccn_origin_20261006/hostcopy/dyn_em/module_big_step_utilities_em.F` | `27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c` | parent WRF moisture physics preparation and diagnostic fields |

These source hashes identify the audited file contents; they do not establish runtime closure or scientific validation.

## Native transport and continuity

`solve_em.F` calls `advance_mu_t` for every large-step RK stage (`solve_em.F:1457–1468`). The routine in `module_small_step_em.F:969–1121` advances column perturbation mass `mu`, constructs the column continuity tendency `DMDT`, updates `mu` with `DMDT + mu_tend`, and diagnoses `ww`. Its documented flux-form equation uses map factors, eta thickness `dnw`, and the staggered mass-coupled horizontal winds. The same routine states that the scalar equation transports `mu*q`, not just `q` (`:1128–1133`).

The small-step routine `sumflux` accumulates `ru_m`, `rv_m`, and `ww_m` over acoustic substeps and adds the linear large-step contribution before dividing by the number of small steps (`module_small_step_em.F:1480–1610`). The Registry identifies `ru`/`rv` as `MU_U`/`MU_V` with units `Pa m s-1`, and `ww_m` as time-averaged mu-coupled eta-dot with units `Pa s-1` (`Registry/Registry.EM_COMMON:160–190`). These are face-staggered and mass-coupled fields. They are the minimum native transport/continuity payload to retain at each RK stage, along with `mu`/`mut`, `muu`, `muv`, `mu_tend`, `c1h/c2h/c1f/c2f`, `dnw`, map factors, timestep weights, and the active domain/tile bounds.

The selected C4 solve applies physical boundary conditions to `ru_m`, `rv_m`, and `ww_m` before scalar use (`solve_em.F:1823–1848`) and passes the arrays into `rk_scalar_tend` (`:2297–2327`). For the active scalar advection option, `rk_scalar_tend` passes those transport arrays to the chosen `advect_scalar*` routine (`module_em.F:2419–2494`). The conservative state update uses the geometry-weighted `mu_old` and `mu_new` denominator (`module_em.F:3041–3070`). Capture therefore needs the finalized arrays and geometry from the same RK stage immediately before scalar advection, plus the matched pre/post scalar state and actual advection option. A later history sample cannot supply that stage context.

History `U`, `V`, and `W` are physical velocities, while the native arrays above are time-averaged, staggered, map-factor-coupled transport quantities. `ww_m` is eta-dot in pressure units rather than physical vertical velocity. The parent trajectory conversion divides `ru_m` and `rv_m` by staggered mass carriers and applies map factors to recover physical `u`/`v`; the reverse operation needs the same RK-time `muu/muv`, coefficients, map factors, and time averaging. Output-time velocities also omit acoustic-substep accumulation, RK-stage timing, filters, boundary fills, and the scalar scheme's actual donor/limiter face values. Thus history winds cannot reconstruct the integrated native dry-mass flux or constituent flux after the fact.

## Lateral-boundary moisture terms

During the moisture loop, `solve_em.F` calls `relax_bdy_scalar` and then `spec_bdy_scalar` on `moist_tend(:,:,:,im)` at RK step 1 when the domain is specified or nested and the corresponding moisture boundary data are active (`:2348–2383`). The relaxer consumes current scalar values, boundary tendency/value strips, relaxation-zone widths, `dtbc`, and `fcx/gcx` (`module_bc_em.F:348–410`). Later `spec_bdy_final` modifies the final moisture state at specified/nested boundaries (`solve_em.F:4970–4984`; `module_bc.F:2066–2216`). These boundary tendencies/state increments are separate contributions to the moisture budget and are not recoverable from interior history fields alone.

For future closure, record the `moist_tend` increment immediately before and after the relax/spec calls, the current moisture state, boundary strips and timing/relaxation coefficients, and the state increment from `spec_bdy_final`. Preserve the runtime flags (`specified`, `nested`, `have_bcs_moist`, `spec_bdy_width`, `relax_zone`) so inactive branches are distinguishable from missing observations.

## Surface QFX and dry-air carrier

The selected surface/PBL path defines `QFX` as upward moisture flux with units kg m-2 s-1 (`module_bl_shinhong.F:80`). The PBL driver applies the surface boundary term as `b_q = qfx/(rho*dz8w)` (`module_pbl_driver.F:1132–1138`) and passes `QFX` into the selected Shin-Hong routine (`:1186–1202`). That routine returns `rqvblten`, obtained from its PBL-profile tendency `rqvbl2dt` (`module_bl_shinhong.F:290–320`). The tendencies are assembled into `moist_tend` by `update_phy_ten` (`module_first_rk_step_part2.F:971–1001`), then enter the dynamics scalar update.

`QFX` is a boundary flux, not the volume-integrated dry-carrier tendency. Capturing it alone cannot recover PBL entrainment and vertical redistribution. To evaluate its water contribution on a dry-air basis, retain `QFX`, the generated `rqvblten`, the combined `moist_tend(P_QV)` before/after PBL assembly, and same-stage dry-air carrier/geometry (`rho_dry`, layer thickness or the native eta-mass equivalent, map area, and RK weight). The conversion must keep the distinction between QV mixing-ratio tendency and water mass per physical area explicit.

## Closure status and next capture

Existing history states and PR85 observer records do not include native RK transport fluxes, stage continuity, lateral moisture boundary increments, or surface-driven dry-carrier tendencies. No closure can be claimed from current histories. The next diagnostic design should capture the arrays above at the producer/consumer call sites with timestep, RK stage, domain/tile bounds, units, and source/build hashes. It should sum the actual RK-weighted updates, including boundary and surface terms, before comparing with stored species changes. The capture should be validated for bitwise read-only behavior against the frozen C4 executable before any science interpretation.
