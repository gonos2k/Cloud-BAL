# PR65 NC donor and RK update cause investigation

## Finding

At global `(172,76,1)`, the first completed operator that makes cloud number concentration negative is the RK1 regular scalar-advection update. The target NC is zero before RK1, its non-advection scalar tendency is zero, and the completed update is `-1773.7578125`. The field is number per kg dry air. This identifies an internal RK-stage state; RK3 returns the selected target NC to zero. It does not establish physical closure or explain the global negative-QC population.

The exact-source face observer measured the target boundary and donor faces. At RK1, both horizontal face pairs are zero. The lower vertical face is the explicit zero boundary `vflux(i,kts)=0`. The upper face at the first interior interface is reconstructed by the source's linear interpolation:

`vflux(i,2) = rom(i,2,j) * (fzm(2)*NC(i,2,j) + fzp(2)*NC(i,1,j))`

The logged donor state is NC=`21,559,104` at `(172,76,2)`, NC=`0` at the target, `rom(i,2,j)=-0.0167626291513443`, `fzm(2)=0.44025471806526184`, and `fzp(2)=0.5597452521324158`. The reconstructed face flux is `-159102.448547`; the native stored flux is `-159102.4375`, within the operation-scaled binary32 bound. With `rdzw(1)=-161.673828125`, the source divergence is:

`Tz = -rdzw(1) * (vflux(i,2)-vflux(i,1)) = -25,722,700.1346`

This matches the native advective tendency `-25,722,700` within the binary32 reconstruction bound. The regular `advect_scalar` call, not a source term or limiter correction, is therefore the first completed operator that makes target NC negative.

At RK2, NC donor values adjacent to the already-negative target generate large horizontal face fluxes. Reconstructing source `flux5` from the recorded six-point donor stencils and face velocities gives:

| RK2 tendency component | Reconstructed value |
| --- | ---: |
| X | `+441,291.6301` |
| Y | `+345,852.2351` |
| Z | `-36,198,214.3634` |
| Sum | `-35,411,070.4982` |

The native RK2 NC advective tendency is `-35,411,072`. Its target update completes at `-3662.8056641`; `sc_tend` remains zero. Face flux checks use the order-5 six-donor `flux5` formula. The vertical face check uses the source interpolation above. All comparison bounds are derived from binary32 unit roundoff and the absolute magnitudes of the actual operands, so cancellation is included.

## Carrier update and limiter path

At both completed RK1/RK2 updates, QC and NC use identical carrier values. Their `den_old` and `den_new` are respectively `94933.0859375`/`94929.859375` at RK1 and `94933.0859375`/`94928.6015625` at RK2. The replay also verifies the denominator expressions from `c1`, `c2`, `muold`, `munew`, and `mub`, and the completed scalar update from the captured operands:

`new = (den_old*old + dt*(msfty*advect_tend + sc_tend))/den_new`

The selected NC uses `scalar_adv_opt=1` (positive-definite scalar advection), but the call to `advect_scalar_pd` is gated on `rk_step==rk_order`. RK1 and RK2 run regular `advect_scalar`; the observed RK3 target NC is zero. The final-stage value alone does not show which specific PD branch produced zero.

## Scope of the QC aggregate

The `23,494` negative-QC count is the aggregate at KDM6 entry inside the active overlap. Existing PR63 stage reductions show active-overlap counts of 0 at PRE_RK, 161,526 at RK1 end, 395,145 at RK2 end, and 23,494 at RK3 end; that same 23,494 persists through pre/post moist preparation and pre-microphysics, then the count is 0 post-microphysics. The full-tile RK-stage counts are 0, 163,244, 399,233, and 23,539. Thus negative QC first appears in the aggregate by completed RK1, and the KDM-entry-sized population is present by RK3. These reductions do not link cell identities between stages, so they cannot establish when each of the eventual KDM-entry cells first became negative or its per-cell cause. Paired graupel-cleanup evidence reproduces the same KDM-entry and stage counts; it is a paired replay, not a source attribution for QC.

The guarded run's namelist has `moist_adv_opt=1` and `scalar_adv_opt=1`. The namelist comments define 1 as positive-definite for scalar variables; QC is transported through the moisture loop, whereas NC follows the scalar loop. In the generated solver, the moist RK update uses `rk_update_scalar_pd` only at the final RK stage for non-ORIGINAL/non-WENO options. That routine's update equation has no nonnegative floor. The PBL tendency captured at the selected target is one cell's positive QC source; it does not map to the 23,494-cell aggregate, and the selected NC donor result is a separate cause investigation. The global QC cause remains open.

The next focused capture should bind the KDM-entry negative-QC mask to coordinates and follow only those cells through each completed RK stage. At each stage, record QC before/after, advection tendency, total physics tendency (with PBL and other contributors split if available), carrier inputs, option selection, and final update. This will classify the first negative completed operator for the eventual KDM-entry cells and determine whether source tendency or transport/update path dominates without imposing a floor.

## Source and run provenance

The observer was built from the exact generated PR61-bound advection source (SHA-256 `a1dc18bce40f84ad709d38fbe7b0658590e587d42528b1124f9c8b7e9c1830fa`) after applying `docs/evidence/pr65_nc_donor_observer.patch`. The patched source hash is `360148b1c68185f658192b0d2959cc6ba7f2e61255d73163a177c46be9e5550e`. The untouched archived `module_advect_em.o` member before replacement hashes to `0b9be5ea72d428ef66d5876a3820681a82471e319bdcbe7fabf8f67d1c30316c`; that archived member was preserved in the separate retained archive. The diagnostic module object and executable hashes are `1387f39b29c1c04d18ee48371cd01170fb46ffe5b68c2db8c72c398dc6cddf61` and `53d704da329058ea8fc8de044be9646a5ca470c0ddde8e2ee18a1ffcc49da3b3`.

The final native run used the pinned Intel profile in `tests/intel_toolchain.sh`, one rank, one tile, and the 20-second research namelist. A fresh `/var/tmp` tree was copied from the PR64 QC observer input tree, populated with detached single-link files, and used for new outputs. `run_isolated_native.py` checked 101 inputs and 18 output paths: return code 0, input integrity PASS, output isolation PASS, no changed inputs, and no output issues. The receipt and full command argv are preserved in `docs/evidence/pr65_nc_donor_run_isolation_20261007.json` and `docs/evidence/pr65_nc_donor_guard_command_20261007.json`.

The guarded run matches all ten recorded PR64 baseline artifacts byte-for-byte, including the model output and `pr62_extent_cells.txt`. An earlier manual observer run reused an already-populated `pr62_extent_cells.txt` and appended diagnostic rows; that run is explicitly excluded from equivalence. A first guarded attempt mistakenly declared `pr63_transition_masks.bin` as an input even though the run rewrites it; its return code was zero but input-integrity validation failed. That receipt is retained in `/var/tmp`; the final fresh run declares the mask as output and passes.

The compiler emitted a warning that `-real-size32` was unknown and ignored; this IFX build's default REAL is 32-bit. The compile output is retained in `docs/evidence/pr65_nc_donor_compile.log`. Maintained WRF source and the audited archive bytes were not changed. The observer and replay are research diagnostics only; there is no full-physics, multi-tile, or operational approval.

## Replay and validation

```bash
python3 tools/pr65_nc_donor_replay.py \
  docs/evidence/pr65_nc_donor_faces_20261007.raw \
  docs/evidence/pr65_nc_host_updates_20261007.raw \
  --time-step-seconds 20
python3 tests/test_pr65_nc_donor_replay.py
```

The replay checks exact target coordinates and row order, finite binary32 inputs and derived terms, the NC X/Y donor stencils and vertical interpolation, binary32 error bounds, carrier denominators, completed QC/NC carrier equality, RK1's zero-to-negative NC transition, and RK3's zero NC endpoint. It explicitly marks the global minimum as unassessed. The standalone test suite covers five cases, including donor/face mutations, time-sign sensitivity, incomplete rows, NaN/extreme inputs, subnormal ULP handling, and strong tendency cancellation.

Full values, hashes, guarded receipt, failed attempts, and comparison hashes are in [the PR65 evidence JSON](evidence/PR65_NC_DONOR_CAUSE_20261007.json).
