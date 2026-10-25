# PR101 liquid cloud thermodynamic observer

## Scope

This observer adds rows to a PR100 prepared KDM6 source for every T1 call to
the source liquid saturation adjustment on the existing 613-cell support. The
tag `PR101THERMO_LIQUID` identifies the saturation formula actually called by
the source, including cells below freezing. It records both arms independently;
the reducer aligns records by timestep, loop, and cell before forming contrasts.

The row carries source `T,p,qv,qc`, liquid saturation vapor pressure before
the source cap, source saturation mixing ratio, `work1`, `pcond`, `dtcld`,
`xl`, `cpm`, and the `q` and `T` values that produced the carried `cpm` and
`xl`. It records source-formula saturation vapor pressure and mixing ratio at
the producer temperature and post-write temperature, plus source-style
relative humidity at producer, branch, and post-write states. All source
constants are recorded with those diagnostics. It distinguishes unbounded
evaporation demand `max(-work1,0)`, pcond-bounded evaporation
`max(-pcond*dtcld,0)`, the signed source transfer extent, and stored vapor/cloud
deltas. The full-evaporation decision is explicit.

The transform keeps the original saturation, `pcond`, QV, QC, and temperature
assignments intact. It adds local diagnostic arrays for the producer values of
`cpm`/`xl`; these are populated beside their source calculations. No physical
rate or branch decision is changed.

## Source equations being observed

The source stores `work1` in DOUBLE PRECISION, while its `conden` statement
function returns default REAL; PR101 records the stored value and the
unbounded demand in DOUBLE PRECISION after that source promotion. The source
chooses liquid saturation using
`es = psat*exp(log(ttp/T)*xa)*exp(xb*(1-ttp/T))`, caps `es` at `0.99*p`,
converts it with `ep2*es/(p-es)`, then applies `qmin`. It passes this `qs`
through `conden(T,qv,qs,xl,cpm)`. Source clipping limits the proposed vapor
loss by available `qv`; for negative `work1` with cloud water present, the
second clipping also limits the transfer by `qc`.

For full evaporation, the source transfers all remaining `qc`, zeros QC, and
cools T by `qc*xl/cpm`. Otherwise its signed source transfer is
`-pcond*dtcld`; the original QV, QC, and T assignments remain the authority
for their rounded stored changes. `xl` and `cpm` are captured as carried
values together with their producer inputs, because intervening source work
can make them differ from values recomputed from the state at the adjustment.

## Artifacts and current status

- Transform: `tools/pr101_cloud_thermo_source.py`.
- Reducer: `tools/pr101_cloud_thermo_reducer.py`.
- Focused source and reducer tests: `tests/test_pr101_cloud_thermo_*.py`.
- Original additive source patch: `docs/evidence/pr101_cloud_thermo_20261023/source.patch` (the first candidate exposed a writer type mismatch during compilation).
- Corrected diagnostic typing patch: `docs/evidence/pr101_cloud_thermo_20261023/source_r64.patch`.
- Private corrected observer source: `/var/tmp/pr101_cloud_thermo_private_20261023/module_mp_kdm6_pr101_r64.f90`.
- Input prepared source SHA-256: `0c76fdae6e58e336dfafd581779a0979415e7b0fa64c30f701d1e22594d3e2a1`.
- Its retained prepared-source path is `/var/tmp/pr100_qc_observer_build_fresh_20261022/src/module_mp_kdm6_pr100.f90` (same SHA-256). The 30 staged module inputs include the 27 retained PR100 pins plus three explicit dependency pins; only the fresh `/var/tmp/pr101_cloud_thermo_build_20261023_r64/mod` was on the module search/include path.
- The guarded build plan remains byte-identical to the build-plan file bound by all four replay manifests (SHA-256 `65478f6d…10a69`). Separate `build_r64/reproducibility_readback.json` and `link_inputs_post_link.json` record the prepared-source path and hashes for all 14 explicit object/archive paths. Those link hashes document post-link retained bytes, not bytes proven consumed by the linker; there was no linker input-open trace or build-time hash pin set. Named `-l` libraries and `-L` search paths are listed separately.
- Original generated source SHA-256: `893a4c1c4b14d8ffe35d968cb7dd3f6e31d907df7ca081ff07196a6a35b9eca8`.
- Corrected generated source SHA-256: `f7ef82b945c409ea2c54ce88139f544250c9360af611fdd8515cbae8e23c3dca`.
- Original source/reducer Python tests: 15 passed. The added reproducibility-focused suite now passes 20 tests, including fixed-pin rejection and aggregator template isolation.
- Failed compile argv/log/RC, module seed inventories, and missing object/link outputs for the prior source hash are in `docs/evidence/pr101_cloud_thermo_20261023/build_attempts_893a.json`.
- Corrected source build plan and precompile inventory: `docs/evidence/pr101_cloud_thermo_20261023/build_r64/`.
- Pinned IFX compile and mpiifx link both returned 0 in `/var/tmp/pr101_cloud_thermo_build_20261023_r64`; executable SHA-256 is `0fa1b8d44dc2a1fe9f438351c10f0e07e707e8c22c7850f32d54b484a12a3622`.
- Four guarded first-call replays completed: C1 OFF, HYDRO, COUPLED, and separate receipt-bound P20. Each reproduced its native 17 fields plus XLAND byte-for-byte and emitted 613 strict-parser-valid thermodynamic events. Replay receipts and manifests are under `docs/evidence/pr101_cloud_thermo_20261023/`; raw captures and logs remain in the corresponding `/var/tmp/pr101_thermo_replay_*_20261023*` directories.
- Compact arm absolutes, signed contrasts, ranked cells, parser status, and private raw/receipt hashes are in `docs/evidence/pr101_cloud_thermo_20261023/four_arm_summary.json`. OFF-only compact details are in `off_summary.json`.
- `tools/pr101_cloud_thermo_aggregate.py` regenerates that summary from `aggregation_inputs.json`, which pins each guarded manifest, receipt, executable, and private raw capture. It reuses the strict row reducer and recomputes arm totals, contrasts, rankings, and conditional counts. The current four-capture regeneration reproduced all published JSON values exactly.
- `tools/pr101_cloud_thermo_refresh_manifest.py` refreshes only declared derived-output hashes. It checks prepared-source, compiler profile, module inventory, executable, replay manifest, receipt, and capture pins as fixed inputs; stale pins fail without repair. Readback verifies each path/hash pair without mutating it.
- A fresh staging-only recheck produced 30 module seeds and one `-I` path, pointing to that fresh stage’s `mod` directory. No compile or link was run for this recheck. Two incompatible legacy link-argv inputs were preserved as failed staging attempts; the successful recheck used the retained PR100 argv shape expected by the stager.

## Replay findings

For COUPLED minus OFF over the same 613 event keys, the signed source extent
sum is lower by `0.028867724 kg/kg` (613-cell sum), while stored QC change is
higher by the same magnitude within REAL32 rounding. The unbounded
`max(-work1,0)` request sum is lower by `0.027888964`; the pcond-bounded
evaporation sum is lower by `0.028592044`. HYDRO gives a similar net source
extent contrast (`-0.028745120`). These are unweighted support sums, not an
area-integrated water budget. The captures preserve full-evaporation source
extent separately from stored QV/QC changes; no stored delta is labeled as
the exact approved transfer.

The largest general-branch COUPLED-minus-OFF stored-QC contrast cell is
`(i=136,j=17,k=11)`. OFF begins at `T=291.37485 K`, `qv=0.01358401`,
`qs_liquid=0.01655950` (`rh_branch=0.82032`) and has `work1=-8.47435e-4`,
so the source requests evaporation. COUPLED begins about `1.64 K` colder and
with higher vapor (`qv=0.01511214`); its source liquid `qs` is `0.01489216`
and producer-basis RH is `1.01538` (OFF: `0.81533`). Branch RH is `1.01477`
(OFF: `0.82032`). `work1` changes sign to `+6.68951e-5`, `pcond`
changes sign, and the source general-branch extent changes from
`+8.47435e-4` (evaporation) to `-6.68951e-5` (condensation). The source
liquid saturation and RH inputs therefore put this cell on opposite sides
of saturation in the two arms. Carried `xl` and `cpm` differ by about 0.16%
and 0.13% at this cell. This local contrast tracks the changed saturation
state and source-term sign, rather than a material change in latent heat or
heat capacity.

The largest same-full-branch stored-QC contrast is `(135,17,11)`: both arms
take the full-evaporation path, so the source extent is available `qc`.
OFF starts with `qc=5.53860e-4`, COUPLED with `1.27529e-4`; their accepted
source extents and QC removal differ by `4.26331e-4`. Here the contrast
tracks available cloud water, while the unbounded requests are separately
`9.19659e-4` and `4.41973e-4`.

Across QC-positive cells, branch RH counts (`qv_before / source qs_liquid`)
show the same direction pattern: OFF has 389 cells below 1 and none at or
above 1; HYDRO has 380 below and 9 at or above; COUPLED has 379 below and 10
at or above; separate P20 has 380 below and 9 at or above. Every QC-positive
full-evaporation event has positive source extent. In the general branch,
those above-saturation QC-positive events have negative source extent
(condensation). The 224 zero-QC events have zero source extent in each arm.
This count is restricted to QC-positive cells; all-613 RH means are omitted
because that set also includes clear/dry cells.

Among the 12 C1 COUPLED/OFF full-evaporation-flag mismatches, the largest
absolute stored-QC contrast is `(i=136,j=18,k=11)`. OFF takes the full branch
with `qc=8.07049e-4` and removes all of it; COUPLED takes the general branch
with `qc=1.89402e-4` and removes `1.63247e-4`. Both are evaporating
(`work1<0`), but OFF has the larger request and available cloud amount. The
stored-QC contrast is `+6.43802e-4` (COUPLED minus OFF). This case shows why
the arm contrast cannot be summarized as “COUPLED destroys more cloud” or
interpreted from RH alone: branch choice, request magnitude, and available
QC all enter the source transfer.

The QC-positive counts by source branch reinforce that mixed direction:

| Arm | QC-positive cells | Branch RH < 1 (full/general) | Branch RH ≥ 1 (full/general) | Full-branch extents | General-branch extents |
| --- | ---: | ---: | ---: | --- | --- |
| OFF | 389 | 389 (231/158) | 0 (0/0) | 231 evaporation | 158 evaporation, 224 zero |
| HYDRO | 389 | 380 (231/149) | 9 (0/9) | 231 evaporation | 149 evaporation, 9 condensation, 224 zero |
| COUPLED | 389 | 379 (231/148) | 10 (0/10) | 231 evaporation | 148 evaporation, 10 condensation, 224 zero |
| P20 | 389 | 380 (230/150) | 9 (0/9) | 230 evaporation | 150 evaporation, 9 condensation, 224 zero |

`Branch RH` is source `qv_before / qs_liquid`; RH counts above are restricted
to `qc_before > 0`. The 224 zero-extent rows have zero cloud water. The exact
branch-count table and mismatch-cell arm values are in the compact JSON
summary.

As a substantial-process control, `(i=137,j=16,k=23)` is the smallest
COUPLED-minus-OFF stored-QC contrast among events where both arms have
`qc_before` and unbounded request at least `1e-4`. The source extents are
`2.19451e-4` and `2.19432e-4`; stored-QC contrast is `1.94e-8`, with stored
temperature-response contrast `9.16e-5 K`.

P20 is kept separate from the C1 arms and from live C2/P640. Its 613-event
capture has 230 full-evaporation rows. Relative to COUPLED, its source
extent sum is higher by `2.50987e-4` and stored QC change is lower by that
amount. This is a P20 replay result only.

One initial OFF launch receipt records a loader-only return code 127 because
the profile did not include WRF library directories. It was preserved;
the successful fresh-directory retry explicitly prefixed the known C1
`WRF_LIBS/lib` and `lib64` paths. An earlier `893a` source compile returned
1 because of the diagnostic `work1` type mismatch; no failed candidate was
linked. The corrected `r64` source fixes only diagnostic typing. Its
30-module precompile seed inventory, separate compile/link argv and receipts,
source/object/executable/map hashes, and all replay bindings are recorded.

The source-computed Fortran saturation values are authoritative. The
Python REAL32 log/exp comparison is advisory because transcendental
implementations can differ by more than one ULP; it is not a replay gate.
The reducer still enforces source event keys, exact temperature bits, source
request/extent expressions, and stored QV/QC/T branch arithmetic. The
replays are standalone first-call diagnostics and do not establish later
forecast evolution or an area-integrated water conservation claim.
