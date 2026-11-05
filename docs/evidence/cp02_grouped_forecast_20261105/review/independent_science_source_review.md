# Independent science and source review — grouped PH6hforecast

Status: source/data findings verified; native build-plan review pending.

## Graph and source boundary

Graphify query on the maintained KLAPS50 graph located `calc_p_rho_phi` in `module_big_step_utilities_em`. The pinned source in the prior boundary bundle shows the `hypsometric_opt == 2` numerator in the nonhydrostatic branch as

```fortran
(ph(i,k+1,j)-ph(i,k,j)+phb(i,k+1,j)-phb(i,k,j))
```

This is left-associated in the observed compiler trace: `(PH(k+1)-PH(k))+PHB(k+1)-PHB(k)`. The proposed grouped arithmetic is `(PH(k+1)-PH(k))+(PHB(k+1)-PHB(k))`. Both represent a layer geopotential difference in real arithmetic, with units m² s⁻²; the finite-precision result can differ. Downstream use enters the hypsometric `al` calculation and the pressure/EOS path. This makes it a narrow arithmetic candidate, not a rain-number, microphysics-threshold, or PSD policy change. The source capture/trace is bounded to the pinned baseline and selected locations; it does not prove what a new executable does until compiler-output/runtime verification.

## Independent frozen-data recount

I independently loaded the archived `entry_only_qr.npz` (154,317 same-initial-QNRAIN cells whose first wrapper ENTRY NR differs) and recounted raw QR sign/magnitude bins for both arrays. B1 and DM065 each yield:

| Raw ENTRY QR class | Count |
|---|---:|
| QR < 0 | 1,521 |
| QR = 0 | 391 |
| 0 < QR < 1e-9 | 104,517 |
| QR ≥ 1e-9 | 47,888 |

These are raw QR bins only. They do not show every active-PSD admissibility condition, do not cover all called cells, and do not identify an intervening writer or mechanism.

At native `(i,j)=(141,142)`, `flat_index_yx=20330`, k=2, I independently checked the four archived wrapper ENTRY samples (steps 1–4) in both B1 and DM065. All four in each arm satisfy `QR < qcrmin (1e-9)` and `NR*DEN < nrmin (0.01)`. This is a fixed-cell, four-call boundary result; it is not a domain-wide population or complete PSD validation.

## Independent 60-row arithmetic replay

I recomputed per-call B1/DM065 source-order and grouped REAL32 values from the frozen 60-row capture table and checked exact rational sums of the captured REAL32 operands. Grouped arithmetic is closer to the exact sum in all 60 samples; it reduces mean absolute error from 0.0023518880208333332 to 0.000012461344401041666 and the maximum from 0.0068359375 to 0.00005340576171875. This supports improved arithmetic accuracy for these captured operands only, not a forecast benefit or a physical truth claim.

The B1–DM065 separation is not uniformly reduced:

- At 20183, phi calls 7–8 change the source-order difference `+0.0009765625` to grouped `0`; call 9 changes `−0.0009765625` to `−0.0008544921875`; call 10 restores a positive grouped difference `+0.00042724609375` after source-order equality; calls 13–14 have larger-magnitude negative grouped differences (`−0.001708984375` and `−0.001953125`).
- At 17051, source-order B1/DM065 numerator values are equal through call 12; grouped arithmetic gives negative differences at calls 13–14 (`−0.0009765625` each), then returns to equality at call 15. This grouped-numerator difference first appears at phi 13, while a separate pressure boundary difference is already present at phi 11: at k=38, input `T` differs and returned `P` differs by −0.00146484375, with returned `AL` equal across all 15 calls and returned `PH` equal through call 12 (then differing at calls 13–15). Keep these endpoints distinct; the phi-11 pressure difference is not evidence of a PH numerator difference.

A grouped candidate must not be described as suppressing DM-B1 differences or as a mechanism that removes sensitivity. Actual C and D trajectories are needed because the first changed numerator can change pressure/EOS and later state, including B1 itself.

## Evaluation plan review guard

The proposed evaluation design is correctly paired over the fixed 3,688 RN1 keys, six hourly increments, six thresholds, and separate immutable ORIGINAL benchmark. Precipitation windows must remain one-hour `RAINC+RAINNC` increments, not cumulative totals; exact CSI must be computed from each cell’s integer H/M/F. The gates are fixed: 11 unique protection cells (C/D against old B1 arm A) plus 15 recovery cells (C/D against ORIGINAL), for 52 arm-cell verdicts. Every arm fails its gate set if any cell fails; no averaging, gate movement, or use of grouped B1 as its own baseline. Score both grouped arms independently; primary factorial contrasts are C−A and D−B, with difference-in-differences diagnostic only. Candidate preference follows the root-frozen qualified-only lexicographic CSI rule (+1 h ≥10 mm, then +2..+6 h ≥10 mm, then +1..+6 h ≥5 mm); exact ties prefer simpler C. These are paired results for one event and do not establish held-out generalization.

Native build/rebuild attribution review is pending the concrete build plan. Before execution, the plan must pin the exact source patch and baseline, compile an unchanged SHAM in a fresh scratch directory with the pinned `ifx` profile, preserve its outputs, and require the SHAM’s executable/forecast products to match the old baseline before attributing differences to grouped arithmetic. Grouped build C/D must then use the same approved source change and isolated fresh directories. No offline fixed-phi substitution can replace the actual new trajectories.

## Concrete native plan review (plan hash `9235146e884876e99bb297d52ad500ddcbbd001b91ecd140a1104d882599da38`)

**No-go for compile on this plan version.** Independent byte checks passed for the six frozen Fortran source units, the ten explicit object/archive inputs, the profile script, and single exact source replacement (one occurrence; derived grouped-source hash matches). The six source units and ten link inputs are separately named; no four extra Fortran units are implied by the ten linker-file count.

Three issues need correction before the profile audit and compile:

1. The manifest path/hash fields are crossed. The `native/source_lineage.json` hash is `3def32dbbde3cf31dff130751786ba94aefce1ffbd12a20592de88bca0144509`; `native/sourcepins/manifest.json` hash is `9bac690cbe8ec7ad32ea4bd5057fdf6fcb3e86c599c279b5758f2f7e145c41cb`. The plan currently assigns these values to the opposite manifest fields and gives only one path.
2. The plan's `setvars_sha256` is mistyped (`...b920...`). The profile pins the actual file to `26084d08db985eadb61adc43c7f18821be9e75156b60f920de363ea51c70887e`.
3. Ten explicit linker files do not close all link dependencies. Resolve and freeze the actual `-L/-l` inputs (including `esmf_time`, `wrfio_nf`, `netcdff`, and `netcdf`), relevant runtime libraries, and required `.mod` inputs; copy mutable link inputs privately and verify hashes before each build. Keep the original host tree read-only.

The plan's SHAM-first and no-old-PC rules are appropriate. A bounded one-hour SHAM can check compiler feasibility and localized state/operation behavior, but it cannot by itself qualify reuse of old six-hour histories. Before scoring C/D against old A/B histories, compare complete seven-boundary precipitation histories for OLD_SHAM against the old histories for both initial arms, or clearly mark any mismatch as a comparability failure and do not treat the result as a valid 2×2. No compile or model run was initiated by this review.

### Revised build plan check (hash `064a0d836d2f662c4c0293c7ad7899598708982913cff3d7c4852402cb7fa9e4`)

The revised plan fixed the crossed manifest references/hashes and the setvars hash typo. I independently verified all 41 referenced file identities: the pinned compiler/profile and setvars, source-lineage/sourcepins manifests, CP03 link receipt, six Fortran sources, ten explicit link files, five target `.mod` dependencies, four implicit `-l` archives, and ten baseline `ldd` closure files. All match. The target source expression occurs exactly once; substituting the grouped expression yields the planned source SHA-256. The five `.mod` names resolve from the pin set; source search and link dependency closure are now explicitly called out, including that final candidate `ldd` must be regenerated.

**Plan review: GO.** Execution remains conditional on a builder/recipe source plus SHA-256 freeze before compile, and on the pinned profile being rechecked from a clean shell. The bounded SHAM compile may establish build feasibility only. Its runtime actual-operation check must use symbols/PCs rediscovered from the newly built binary. The SHAM history comparability gate still applies before treating C/D against old A/B cache as a valid factorial result.

Portable independent outputs are [the recomputed 60-row table](independent_phi_arithmetic_60_rows.csv) and its [hash-bound recount receipt](independent_recount_receipt.json). They were recomputed directly from frozen raw PH/PHB capture words, the entry QR NPZ, and the four-step selected boundary array.
