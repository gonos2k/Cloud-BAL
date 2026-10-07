# PR63 native state-transition trace

Status: research-source evidence; this does not authorize changes to maintained WRF/KDM6. The full moment and physical-initialization gates remain **FAIL/OPEN**.

## Scope and source attribution

This trace follows the PR62 NE57 case at 2026-08-16 12 UTC through the host RK transport boundaries and the first public KDM6 call. It uses a copied WRF source tree and a fresh, one-rank/one-tile scratch run. The maintained WRF tree and preserved PR61/PR62 run artifacts were not edited.

The valid, instrumented host/KDM executable for the unmodified PR62 KDM source is the v2 run rooted at `/var/tmp/pr63_native_transition_20261006/run_transition_v2`. Its guarded receipt is `run-isolation.json` (SHA256 `3570a95c63702d548f18de3417369d210b749a0ba46ee704dd1a4794e524e7e6`). The executable SHA is `d0b260a721f1df37c045ae08e7c5fe1d7b0c1e0d8f11cba9490e34f60f309c30`; its archived `solve_em.o` and KDM6 member SHA values are respectively `8670703c8229399709caaf5fb47e8c9dc865ad5def98cc7d4baaed6054bfd772` and `7717a8531a40b42fa46b9c7fe2be57a844e4692ab820dcf1728a0b3170c971f2`. The linked executable contains both host transition symbols. It is a new instrumented executable, not the retained PR62 executable.

The v2 run used byte-identical `wrfinput`, `wrfbdy`, and namelist to the retained PR62 run. Its KDM6 pre/post captures are byte-identical to the PR62 captures. The first malformed host-probe link attempt is excluded: it retained the old archive member and its executable had no `pr63_transition_state_` symbol. The earlier stage2 attempt is also excluded from attribution because it failed a bounds check. Those failed attempts and their receipts remain preserved under the external scratch root.

During paired-build preparation, an extracted helper copy at `build_cutoff_v2/link/module_mp_kdm6.o` was found at SHA `522a1c07…`, while the archive member and the executed v2 binary remained at their recorded SHA values. The helper copy was restored from the independent `build_cutoff/link/module_mp_kdm6.o` at SHA `7717a853…`; the before/current hashes and stats are recorded in [`pr63_artifact_incident_restore_20261006.json`](evidence/pr63_artifact_incident_restore_20261006.json). The exact command that replaced that unlinked helper copy could not be recovered. This does not change the retained executable, archive member, or raw run captures.

## Q/N transition at the RK boundaries

The runtime comparison threshold is the exact imported `module_model_constants%epsilon` value, `1.0000000036274937e-15 kg kg-1` in this IFX binary. It is distinct from KDM6 `qcrmin=1e-9`, which is the graupel/rain/snow mass cleanup threshold. The configuration is `moist_adv_opt=1`, `scalar_adv_opt=1`; the WRF source's `README.namelist` maps scalar option 1 to positive-definite scalar advection. `module_em.F` invokes its positive-definite scalar update only at the final RK stage. These settings describe the configured algorithm; they do not prove that a particular source term caused an observed negative value.

Exact active KDM6 window: global `i=2..233, j=2..281, k=1..39`, 2,533,440 cells. The host transition sampler spans the larger solve tile `i=1..234, j=1..282, k=1..39`; its full-tile counts must not be compared directly with KDM6 counts. `tools/pr63_transition_replay.py` crops by global bounds and checks the predicates against the saved public KDM6 arrays.

| Boundary | Full solve tile: `QC>epsilon & NC=0` | Full solve tile: `QC<0` | Note |
|---|---:|---:|---|
| Before RK | 13,383 | 0 | Target `(172,76,1)` has QC=NC=0. |
| RK1 end | 4,079 | 163,244 | Intermediate negative QC includes RK-stage state; not a standalone physics rejection. |
| RK2 end | 258 | 399,233 | Negative count is transient and must be interpreted by stage. |
| RK3 end | 29,545 | 23,539 | Includes the outer solve-tile cells. |
| Before microphysics preparation | 29,545 | 23,539 | Same fields as RK3 end. |
| Before first KDM6 | 29,545 | 23,539 | Host solve-tile count; exact inner-window count is reported separately below. |

On the exact KDM6 active window before the call, `QC>epsilon & NC=0` is 29,310, `QC>1e-9 & NC=0` is 981, and `QC<0` is 23,494. The 235 difference between full-tile and active-window gap counts is in the solve tile's outer horizontal buffer.

The per-call `rk_update_scalar` cuts localize the target transition more closely. It starts with QC=NC=0 before RK1. Immediately after the RK1 QC scalar update, QC is `1.6839790362e-7` while NC remains zero; the subsequent RK1 NC update leaves this target NC zero. At RK1 end the target QC is negative (`-1.7737578125e-5`) while NC is still zero; after RK2 it is negative again, and after RK3 it is positive (`5.0365270e-7`) with NC zero. Thus the RK1 post-QC cut is the first observed positive-QC/zero-NC boundary, while the exact target's negative excursion and recovery occur later. This does **not** identify the donor face, tendency component, or operator that created/recovered the QC without NC. That source attribution remains OPEN.

The solve-tile and KDM6 active-window counts are not interchangeable. At `POST_MICROPHYSICS`, the host sampler reports 236 QC gaps and 45 negative QC values over its larger tile. The exact KDM6 active intersection contains one gap and zero negative QC; the other 235 gaps and all 45 negatives lie outside the KDM6 active window. The saved mask and KDM6 raw arrays have zero predicate mismatches on the common window.

For the actual KDM6 returned arrays, all three predicates give the same result: `QC>0 & NC=0`: 1; `QC>epsilon & NC=0`: 1; `QC>1e-9 & NC=0`: 1. Returned QC<0: 0. Thus PR62's one-cell return count is reproduced; it was not an epsilon-versus-1e-9 threshold artifact. This does not make the full Q/N/BG moment gate pass.

## Graupel bulk-volume transition

The v2 stage counts are 11 `QG=0,BG>0` cells before the terminal cutoff and 2,465 afterward. Thus 2,454 is the net increase across the cutoff; the 11 earlier cells are pre-existing by that boundary and remain unlocalized. Their summed BG cell values are `1.1734889742467643e-16 m3 kg-dry-1`; the sum over all cells at or below the cutoff before cleanup is larger (`3.642089051517024e-9 m3 kg-dry-1`) and must not be attributed to those 11 ghosts. The terminal loop contains the existing `if (QG <= qcrmin) QG=0` cleanup but did not clear BG. A research-only paired change sets BG=0 in that same existing branch. It does not change the threshold, add water, add a number floor, or modify a PSD prior. Since the existing branch already discards QG at or below `qcrmin`, the paired update removes the corresponding bulk descriptor when that species is declared extinct.

### Matched paired result

The source pair changes only that one `brs(i,k)=0` assignment. The separately staged control and paired sources have SHA256 `2c3c77b2…` and `099b4a74…`; their preprocessed source hashes are `ad0e0022…` and `dea09e05…`. Both archives contain the same 372 member names and differ in only `module_mp_kdm6.o`; the `solve_em.o` archive member is identical. The control staged object SHA (`6c58c715…`) differs from its archived KDM6 member (`de145f8c…`), so this report records staged source/object/archive/executable identities separately and does not claim an exact staged-object-to-archive byte chain. The paired staged object and archive member are both `659a50b8…`. The two executable hashes are bound by their respective successful run-isolation receipts.

The matched control and paired runs used identical detached `wrfinput`, `wrfbdy`, namelist, launch script, and runtime inputs. Both one-rank/one-tile runs completed 20 seconds with return code 0, input-integrity PASS, output-isolation PASS, 104 inputs and 15 declared outputs. Receipts and full hashes are in [`pr63_paired_graupel_cleanup_20261006.json`](evidence/pr63_paired_graupel_cleanup_20261006.json). The exact one-line research patch is [`pr63_paired_graupel_extinction.patch`](evidence/pr63_paired_graupel_extinction.patch); stage-count instrumentation is kept separately in [`pr63_stage_summary_instrumentation.patch`](evidence/pr63_stage_summary_instrumentation.patch). Both KDM6 pre-call captures are byte-identical to each other and to the retained PR62 pre-call raw (`d2331e90…`).

At the terminal cleanup, both runs had 11 `QG=0,BG>0` cells before the branch. Afterward, the unmodified control had 2,465 such cells and the paired candidate had zero. The aggregate BG values over cells with `QG<=qcrmin` changed from `3.64208905151702e-9` before cleanup to the same value after cleanup in the control, and to zero after cleanup in the paired run. Those are unweighted sums of per-cell specific-volume values, not a budget. Comparing post-call public KDM6 arrays shows exactly 2,465 BG values changed, with maximum difference `9.984235660454033e-12 m3 kg-dry-1`; QG is bitwise unchanged.

Using the byte-identical same-call geometry and source-defined hybrid dry carrier, the paired BG removal diagnostic is `44.97818557873736 m3` over those 2,465 cells. The measure is `sum((BG_control-BG_paired)*md_cell)`, with `md=dp*DX*DY/(MSFTX*MSFTY*g)` and `dp=−[C1H*(MU2+MUB)+C2H]*DNW`. It is a mapped bulk-volume descriptor removal, not closure of a sedimentation, boundary, water, or energy budget. The separate `DEN*DELZ` measure differs by 0.05856% and is retained as a non-closure diagnostic. [`pr63_paired_bg_volume.py`](../tools/pr63_paired_bg_volume.py) replays this calculation from the two run captures.

The paired return has zero `QG=0,BG>0` cells and zero nonfinite QC/NC/QG/BG values, but one exact KDM6-active cell still has `QC>runtime epsilon, NC=0`. The incoming 23,494 negative-QC cells also remain an observed input-state problem. In the two-record WRF history files, only QIB differs (2,465 values); `REFL_10CM` and other numeric fields are bitwise equal, with no nonfinite reflectivity in either file. This history comparison does not erase the remaining KDM6 QC/NC failure.

The earlier `run_paired_v2b` attempt remains preserved as an incomplete run: it was terminated in a prolonged KDM6 loop before post-call/terminal output. Its receipt and executable identity are corrected in the failure evidence file. This failed attempt is not part of the matched effect comparison.

## Same-call geometry and carrier

The binary geometry capture records a `PR63GEO2` header before and after the public microphysics call: stage, timestep/RK/HYBRID_OPT, `dtm`, grid timestep, DX/DY, gravity, P_TOP, memory/tile bounds, array extents, and arrays `MU1`, `MU2`, `MUB`, `C1H`, `C2H`, `C3F`, `C4F`, `DNW`, `MSFTX`, `MSFTY`. The schema is positional; the unit meanings are source-derived rather than encoded as strings, a limitation to retain in downstream replayers.

The replay code and frozen v2 replay are `tools/pr63_transition_replay.py` and `docs/evidence/pr63_transition_v2_replay_20261006.json`. The independent geometry reader's output is `independent_geometry_audit.json` under the external run root; it confirms the positional parse and reports maximum layer/interface pressure difference `0.0024998 Pa` and MU-column closure `0.00010944 Pa`.

At the first KDM call (timestep 1, RK bookkeeping value 4, HYBRID_OPT=2), `solve_em` has already run `calc_p_rho_phi` using current `MU2+MUB`; `MU1` is the previous RK slot. `microphysics_driver` receives `grid%rho` as DEN and `grid%delz` as DELZ. In the private KDM wrapper, public cloud/ice/rain number fields are converted to internal number per volume by multiplying by DEN and divided by DEN on return. This supports the public number-per-dry-air convention for this interface. The captured carrier is therefore bound to the same-call host state, but separate process/source/boundary budgets are still required.

For the hybrid dry-mass measure, the captured source geometry gives

\[
\Delta p_k=-\left[C1H_k(MU2+MUB)+C2H_k\right]DNW_k,\qquad
m_{d,k}=\frac{DX\,DY}{MSFTX\,MSFTY\,g}\Delta p_k.
\]

The integrated mapped carrier is `1.6204030034989608e16 kg`. The alternative contemporaneous diagnostic `DEN*DELZ*DX*DY/(MSFTX*MSFTY)` is `1.6213518543290812e16 kg` (+0.05856%); it is retained as a separate diagnostic, not substituted for the hybrid measure and not called closure. PRE/POST geometry arrays are bitwise equal in the v2 run. With the hybrid carrier, observed same-call KDM6 component state deltas are QC `-6.657809021e11 kg`, QI `-1.284139376e12 kg`, QR `+3.860153412e10 kg`, QS `+1.478087827e10 kg`, QG `+2.270886303e10 kg`. These are state differences, not a closed budget: sedimentation/process transfers, boundary terms, and energy terms are not all captured.

## Remaining physical gate

The paired result establishes that, in this research execution, QG extinction at the existing terminal cutoff is paired with BG cleanup and removes 2,465 post-cutoff ghosts. It does not explain the 11 pre-cutoff ghosts, the one QC/NC return gap, transient negative-QC RK stages, full-domain source/flux attribution, or native energy closure. The configured KDM6 run is one rank/tile and 20 seconds. No BASE/HYDRO/COUPLED early-wave or forecast comparison is part of this trace. Full physical initialization remains **FAIL/OPEN**.


## PR64 erratum — selected RK values and capture provenance (2026-10-07)

The earlier selected-cell description above mislabels QC and NC. The raw
writer emits the aggregate minimum QC before the selected `QC, NC, QG, BG`
values. In both successful matched PR63 runs the target `(172,76,1)` has:

| Completed stage | QC (kg/kg dry air) | NC (number/kg dry air) |
|---|---:|---:|
| PRE_RK | 0 | 0 |
| RK1 end | +1.6839790362155327e-7 | -1773.7578125 |
| RK2 end | +2.5137100578831451e-7 | -3662.8056640625 |
| RK3 end | +5.0365269999019802e-7 | 0 |

Thus the selected intermediate negative values belong to NC, not QC. The
independent aggregate negative-QC counts, including 23,494 KDM6-entry cells,
are unchanged. The finer `pr63_rk_update_cuts.raw` captures exist only in the
incomplete `run_paired_v2b`; they are investigation leads, not successful
matched-run evidence. In those cuts the following NC updates produce
negative NC at RK1/RK2, rather than leaving NC zero. The successful matched
stage captures establish the zero-NC gap after completed RK3, without yet
identifying its first responsible donor, flux, tendency, or limiter.

The successful control stage file SHA256 is
`3f51d87ab0320df86ce4e4cffc1b73acf36d2faf7ac1ba8eff3d145c8e8f9d89`;
the paired stage file SHA256 is
`46283bca2a1666ac42ec3fae113264b9f5de8490edb21492767a8d6064a991cf`.
Their original files and receipts are preserved. This correction does not
resolve the physical acceptance failures or replace the original execution
history. See [PR64 team review](PR64_TEAM_MATH_REVIEW_20261007.md).
