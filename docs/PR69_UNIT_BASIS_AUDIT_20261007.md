# PR69 number and density basis audit (2026-10-07)

This is a scoped source and executable audit. It does not approve a physical
unit bridge or identify the historical host executable's runtime behavior.

## Source and producer evidence

- The host Registry declares `QNRAIN` in `kg(-1)`; retained source SHA-256 is
  `b01855ed80569be04bbd99e43ea1672a60e35590db00145c839b8f74cfd9b07f`.
- The PR61 initializer receipt records `QNRAIN` as `dry_air`, `kg-1`, with
  `QRAIN` as `kg kg-1`, and 206,095 initialized cells. The retained receipt is
  `/var/tmp/kdm6_pr61_psd_prior_20261006/initializer_receipt.json`. Its
  source preflight is scoped and explicitly says host/source authentication
  was not assessed.
- The isolated PR67 input hash is `aecc4885…`, matching the PR61 initializer
  output receipt. This connects the declared initializer product to the
  runtime input bytes, not to the selected host object's field interpretation.
- Retained host source shows `moist_physics_prep_em` sets `rho=1/alt*(1+QV)`;
  the selected KDM6 driver passes that `rho` as `DEN` and passes `qnr_curr`
  directly as `NR`. The selected wrapper directly copies `NR` to `nrs` and
  back. Retained host source SHA-256 for the registry, KDM6 module and
  `module_big_step_utilities_em.F` is respectively
  `b01855ed…`, `02c9dc1f…` and `27ce690b…`. Existing
  [PR68 source findings](PR68_RAIN_PROCESS_ORIGIN_20261007.md) record that
  host source/object closure remains partial.
- The retained first-call capture reports positive finite `DEN` from
  `0.0839427859` to `1.162660003 kg m-3`; it does not alone prove dry density.
  Host source maps the dry carrier as `rho_dry=DEN/(1+QV)` at call entry.

## Selected KDM6 density roles

The source is the retained PR67 combined KDM6 source
`/var/tmp/pr67_budget_capture_20261007/source/module_mp_kdm6_combined_research.f90`
(SHA-256 `9efc09257a46102073b6d5a3d7cd12eb9ecd485526bc6e9cb349e4b2b037680d`).
It has separate `den_tmp` (PSD helper input), `dend` (sedimentation mass
carrier) and `denfac` (fall-speed correction), but the incoming moist `DEN`
is still reused for many roles.

| Role | Source evidence | Research routing decision |
|---|---|---|
| PSD mass-number carrier | `lamdac`, rain/cloud/ice lambda inversions and clamp reconstruction use `DEN*Q`; `slope_kdm6` and `slope_rain` receive `den_tmp`. | Dry-carrier density is the consistent interpretation if `Q` and public number are both per kg dry air. |
| Number production and pair conversion | `nraut=3.5e9*DEN*praut`; `nsaut=psaut*DEN/Miaut`; `ninud` converts between number and mass using `DEN`; `nmul*` is converted with `DEN`. | Route through the same dry carrier as PSD mass-number equations. |
| Collision and growth rates | Collision pair terms divide by `DEN`; diffusion/growth uses `diffac`, whose latent-resistance term takes density while `xka(T,DEN)` is algebraically density-independent. | Collision divisions use dry carrier. For `diffac`, keep ambient pressure/temperature transport and pass dry density only to the latent carrier term. This interpretation needs an equation review before any physical claim. |
| Sedimentation | `dend` multiplies mixing-ratio species before fall transport and divides the returned flux; `denfac` separately scales terminal speeds. | `dend` is a dry mass carrier; `denfac` remains based on gas density. |
| Ambient gas transport | `viscos`, `diffus`, `venfac`, ventilation and `vsrec` use density in gas transport or drag corrections. `xka=1.414e3*viscos(T,DEN)*DEN` cancels density algebraically. | Keep moist gas density for ambient transport and fall-speed correction. |
| Ice threshold `qi0` | Two branches define `qi0 = coefficient(T)*DEN`, then compare it with `qci`. | **Unresolved.** Do not reroute until this equation's units and intended carrier are source-authenticated. |
| Precipitation output | Surface accumulators divide by water density `DENR`, not atmospheric density. | Keep `DENR`; it is the hydrometeor material density. |

This role map supports a two-density research prototype, but it is not yet a
complete audit of thermodynamic, saturation, latent-heating and phase-change
terms. `ProgB_param` receives no air-density argument in this selected source;
`denfac` is independently prepared with `vsrec`/`vssqrt`. Do not globally
rename or replace every `DEN` occurrence.

## Executable wrapper-only result

`patches/kdm6_unit_basis_pr69.patch` is a research-only wrapper candidate. It
converts public number per kg dry air with frozen
`rho_dry=DEN/(1+QV)` on entry and converts back using the same density. Its
helpers reject nonfinite, invalid, overflow and positive-to-zero underflow
cases; invalid input uses `ERROR STOP`, so this is fail-fast and does not
promise rollback of already-mutated wrapper state.

Pinned Intel test command:

```text
tests/run_pr69_kdm6_unit_basis.sh
```

The runner builds in fresh `/var/tmp/pr69_kdm6_unit_basis.*` directories using
`tests/intel_toolchain.sh`; the latest receipt is
`/var/tmp/pr69_kdm6_unit_basis.EedxJR`. The helper, O0/O2 candidate, density
round-trip, and direct-copy negative-control checks pass. The density-scaled
direct-volume control agrees in transformed number outputs, but the wrapper
candidate does not establish full physical closure. The runner reports
`FAIL_OPEN` rather than a physical pass.

The current O0 comparison sees `re_cloud=1.3931971807e-5 m` in the converted
candidate and `1.3978257812e-5 m` in the direct-volume control at
`rho_dry=0.25 kg m-3`. This diagnostic requires deeper equation review; the
wrapper-only patch cannot be accepted as closure. A previous isolated O2
direct-volume run at `/var/tmp/pr69_kdm6_unit_basis.CiQWwY` stopped at
`kdm62d:763` with Intel floating-invalid after its `0.50` case. A fresh,
all-density O2 rerun in `EedxJR` passed. The earlier failure is preserved as
non-reproduced evidence and is not used to omit a density from the current
control.

## Decision and remaining gates

The historical public boundary is **PARTIAL/UNVERIFIED**: Registry and
initializer establish the public dry-specific basis, host source establishes
moist `DEN`, and inspected driver/wrapper source directly copies the number
field. The retained host object/executable closure does not prove what
historical runtime bytes meant. The wrapper-only adapter is **FAIL_OPEN**.

An earlier fixture-only dual-density prototype was exercised at
`/var/tmp/pr69_kdm6_dual_density.3dV4w2`. It is retained as historical scratch
evidence only; the fixture patch and duplicate runner were removed in favor of
one transformer bound to the retained selected source.

The selected-source path now uses
`tools/pr69_transform_selected_kdm6.py`, which rejects any input other than
the retained selected KDM6 SHA `9efc09257a46102073b6d5a3d7cd12eb9ecd485526bc6e9cb349e4b2b037680d`
and checks exact transformation anchor counts. It generated source SHA
`9f0ab3e37099eaebfc7380d12f7f166a20e20ce11e219e899d53bf375c522a31` and was
compiled by `tests/run_pr69_kdm6_selected_dual_density.sh`. The pinned Intel
run directory `/var/tmp/pr69_kdm6_selected_dual_density.7tWCee` contains
`receipt.json`, which hash-binds the source, transformer, runner, harness,
toolchain, compiler, dependencies, executables, object files, build logs, and
captured compiler argument lines. It shows paired-call agreement at all four
densities and candidate O0/O2 equivalence. Its line
inventory records 59 dry-carrier uses, 2 growth-latent carrier uses, 2
dynamic-viscosity uses retained moist, 2 moist ventilation uses, 2
density-cancelling thermal-conductivity uses, and 2 unresolved `qi0` uses.
Its receipt and full source-line role map are retained in
`docs/evidence/pr69_selected_kdm6_validation_20261007.json` and
`docs/evidence/pr69_selected_kdm6_density_roles_20261007.json`. The counts sum
to 69 direct density references over the inventoried source lines.
Separate injected-overflow runs also reached the explicit NC, NI, and NN
output guards; each terminated with its channel-specific `ERROR STOP` rather
than publishing zero. Each invalid value was injected into an exact-anchor
copy in its scratch build directory; the normal transformed source has no
test hooks, and each mutation source hash is in the receipt.

This establishes a source-bound selected-module executable check, not the
selected host object's build lineage or a native call. Historical driver,
object, and executable closure remains partial. Do not use the prototype for a
native run until `qi0`, thermodynamic and phase terms, same-call process
accounting, and independent review pass. No result here changes the overall
scientific status from **FAIL/OPEN**.
