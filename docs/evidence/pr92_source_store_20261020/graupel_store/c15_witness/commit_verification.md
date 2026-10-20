# C15 T15/RK1 commit verification

This additive check compares all 17 frozen local mixture trials with the committed `RK_STAGE_END` endpoint at timestep 15, RK step 1. Every QG and public QIB (BG) REAL32 bit pattern matches in its arm. The row-level comparisons and capture/source hashes are in [`commit_verification.json`](commit_verification.json).

| Arm | Witness rows | QG and BG committed bit matches |
|---|---:|---:|
| OFF | 6 | 6/6 |
| COUPLED | 11 | 11/11 |
| **Total** | **17** | **17/17** |

The extra stage-6 target `(2,218,13)` is `QG=00000000`, `BG=00000000` in both committed T15/RK1 endpoints. It has no local mixture-witness row because this path did not call the mixture helper.

The frozen raw witness files equal the decompressed `pr92_valid_mixture.raw.gz` payloads from the closed C15 OFF and COUPLED runs. The actual `add_graupel_diffusion_mixture`, `strict_graupel_pair`, and `store_graupel_mixture` bodies are byte-identical between pinned C15 and C16 `module_em.F` sources.

**Scope:** both 600-second C15 runs are incomplete. They completed 14 post-KDM6 timesteps and failed during timestep 15 / RK2. This evidence establishes only the T15/RK1 endpoint, not a successful model run or later endpoint. Earlier local replay reports remain `LOCAL_TRIAL_REPLAY_CLOSED_COMMIT_UNVERIFIED`; this report adds endpoint comparison without changing them.
