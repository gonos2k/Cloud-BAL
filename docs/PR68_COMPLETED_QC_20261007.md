# PR68 completed negative-QC boundary audit (2026-10-07)

## What was captured

A source-bound observer was added to a fresh copy of the retained PR67 `solve_em` observer. In a guarded run it records QC and QC tendency at `P1_POST`, `P2_POST`, `RK_TEND_PRE`, `RK_TEND_POST`, `UPDATE_PRE`, and `UPDATE_POST` for the 23,494 coordinates in the completed KDM6-entry negative mask. The audit checks that the runtime coordinate list equals the completed RK3 mask coordinate-for-coordinate. It does not change tendency or QC arrays. It does not read inactive SHCU or NC-SHCU process channels. The diabatic and boundary branch capture labels were available in the generated source, but no target rows were emitted for those branches; the checked runtime namelist reports `USE_Q_DIABATIC=0`, `HAVE_BCS_MOIST=F`, `SPECIFIED=T`, and `NESTED=F`.

The resulting `pr68_qc_stages.raw` has 328,916 unique keyed stage rows. For every target coordinate, the observed post-physics tendency equals the RK tendency entry at RK1 (23,494/23,494); after RK scalar tendency it equals the update entry at all three RK steps (70,482/70,482). At RK1 first-negative cells, the update-entry aggregate physical tendency exactly matches the PR67 aggregate `physical_tend` (21,441/21,441). The completed `UPDATE_POST` QC values match the PR67 `AFTER_UPDATE` capture for all 23,494 first-negative cells.

## Measured increments

All differences below are computed in binary32 from the captured tendency states, then summarized. They are observed increments, not separately accumulated physical rates.

| First-negative set | Boundary increment | Negative / positive / zero | Min / max | Sum of absolute increments |
|---|---|---:|---:|---:|
| RK1, 21,441 cells | `P2_POST − P1_POST` | 10,362 / 11,076 / 3 | −2.85731e−3 / +3.78565e−7 | 0.904938 |
| RK1, 21,441 cells | `RK_TEND_POST − RK_TEND_PRE` | 16 / 654 / 20,771 | −1.42888e−6 / +1.79099e−3 | 0.0199692 |
| RK2, 1,139 cells | `RK_TEND_POST − RK_TEND_PRE` | 0 / 0 / 1,139 | 0 / 0 | 0 |
| RK3, 914 cells | `RK_TEND_POST − RK_TEND_PRE` | 0 / 0 / 914 | 0 / 0 | 0 |

Runtime `namelist.output`, validated under its run receipt hash, shows `BL_PBL_PHYSICS=11`, `CU_PHYSICS=37`, `SHCU_PHYSICS=0`, `DIFF_OPT=1`, `DIFF_6TH_OPT=0`, `MOIST_MIX2_OFF=F`, `MOIST_MIX6_OFF=F`, and `KM_OPT=4`. In the observed call sequence, `P2_POST−P1_POST` isolates the configured `update_phy_ten` increment. Both PBL and convection tendency paths are enabled; SHCU is disabled. This measurement does not split the active aggregate numerically between PBL and convection. The valid active aggregate/PBL/CU fields in the separate PR64 channel capture match the prior run for all 9 selected channel rows; inactive SHCU and NC values are excluded from parsing.

In `rk_scalar_tend`, RK1 `diff_opt=1` calls horizontal diffusion when moisture `mix2_off` is false. The vertical diffusion branch is guarded by `bl_pbl_physics == 0`, which is false for this run. Sixth-order diffusion is disabled. Thus the RK1 `RK_TEND_POST−RK_TEND_PRE` increment measures the active horizontal diffusion tendency change for these cells. `rk_scalar_tend` applies that diffusion path at RK1; the measured RK2 and RK3 increments are exactly zero over the first-negative sets.

The completed update remains the coupled WRF update using the captured advection tendency, physical tendency, mass factors, and timestep. The observer confirms that these stage increments account for the physical aggregate entering that update at first-negative RK1 cells. It does not capture donor-face fluxes, so it cannot establish face-by-face conservation or identify which advection flux created an undershoot. The result also does not establish a PBL-versus-convection cause. No floor, tendency zeroing, physics option change, or operational WRF change is made or proposed by this evidence.

## Neutrality and provenance

The fresh run receipt reports success, output isolation, and input integrity. The audit independently rehashes all 102 declared run inputs against their before/after receipt hashes, including the executable and the runtime coordinate list. The compile argv binds the generated source to its object; the linked `solve_em.o` archive member matches that object; the link argv binds the archive output to the run executable.

These outputs are byte-identical to the pinned PR65 baseline: `wrfout`, `namelist.output`, transition masks and stages, KDM pre/post traces, geometry, and the PBL operator/NC captures. Keyed initialized values also match retained PR67 `PRE_COLUMNS` for 23,628 records and `AFTER_UPDATE` for 67,381 records. The active PR64 flags, aggregate tendency, PBL source, and CU source match for 9 keyed records. Whole-file hashes of `pr67_qc_rk.raw` and `pr64_qc_channels.raw` differ from PR67 run3; the audit reports those differences instead of calling the raw diagnostics byte-identical. Inactive source-channel values are never parsed for neutrality.

## Artifacts and validation

- Audit: [`tools/pr68_completed_qc_audit.py`](../tools/pr68_completed_qc_audit.py)
- Focused parser and integrity tests: [`tests/test_pr68_completed_qc_audit.py`](../tests/test_pr68_completed_qc_audit.py)
- Machine-readable audit, hashes, and per-boundary increments: [`pr68_completed_qc_audit.json`](evidence/pr68_completed_qc_20261007/pr68_completed_qc_audit.json)
- Observation-only source delta and exact compile/link/run argv: [`provenance.json`](evidence/pr68_completed_qc_20261007/provenance.json), [`observer.patch`](evidence/pr68_completed_qc_20261007/observer.patch)
- Generated observer source: `/var/tmp/pr68_completed_qc_20261007/source_pr68_completed_qc.f90`
- Fresh executable: `/var/tmp/pr68_completed_qc_20261007/link_final/main/wrf_pr68_completed_qc.exe`
- Fresh guarded run: `/var/tmp/pr68_completed_qc_20261007/run_final`

`python3 -m unittest tests/test_pr68_completed_qc_audit.py -v` passes. The pinned Intel `ifx` observer compile and host WRF relink completed in fresh scratch; the guarded matched run returned zero. This is source-bound runtime evidence for the selected run, not a general proof for other namelists or builds.

The source delta reconstructs the captured observer bytes from the pinned PR67
`solve_em` source (`54c26971…`) without changing its physical updates. The
observer capture is validated for this one-rank, one-tile run; broader parallel
safety and full host source/compiler closure remain unvalidated.
