# PR92 graupel store replay

The source replay is bound to the current `src/common/cloud_bal_joint_transport.f90` and the actual `strict_graupel_pair` / `store_graupel_mixture` routines embedded in `tools/pr87_graupel_cone_mixture.py`. It compiles in fresh `/var/tmp` directories using only the pinned profile at `tests/intel_toolchain.sh`, once with O0 flags and once with O2 flags. Machine-readable results and source hashes are in [replay.json](replay.json).

## Known T15 candidate

The input is exact REAL64 Q=`370528AC448AD089` (1.1859961634011352e-43) and B=`3668384CB70114F1` (1.3257553714467398e-46). The replay uses `rho=1.0` only as a diagnostic argument; the actual density remains pending. It calls the full current `joint_moment_store` with Q/B bounds 100/900, subnormals enabled, normal-Q adjustment enabled, joint-quantum absence enabled, and strict mass ratio enabled.

Both builds reject at failure stage 6. The returned sentinel words are `BF800000/BF800000`; adjustment remains zero. The continuous ratio is 894.5814506539834, inside 100/900. Independent REAL32 conversion gives Q=`00000055` (85 Q quanta) and B=`00000000`. Stage 6 is reached after the input checks and conversion; B is zero, so the later positive-pair repair cannot run. This establishes the common-core failure for the supplied candidate and options. It does not identify the native model's initial storage failure stage.

## Joint REAL32 representations

Each field uses its own REAL32 subnormal quantum, 2^-149 = 1.401298464324817e-45. The candidate is 84.6355143886 Q quanta and 0.09460906475 B quanta. At fixed Q=`00000055`, no positive REAL32 B can satisfy Q/B >= 100: B's minimum positive value is one quantum, which would give a ratio of 85. The nearest feasible nonzero pair minimizing the Q increase is Q=`00000064` (100 Q quanta), B=`00000001` (one B quantum), with ratio exactly 100.

That pair has signed storage changes ΔQ=+2.1530230092368186e-44 and ΔB=+1.2687229271801431e-45, relative to the supplied R64 values. These are separate dimensional budgets. The zero pair has ΔQ=-1.1859961634011352e-43 and ΔB=-1.3257553714467398e-46. Neither proposal is approved here: a joint-store policy needs explicit per-field signed-loss budgets and confirmation that the candidate and physical density are the intended source values.

## Existing mixture helper controls

The actual helper source is compiled unchanged and exercised with synthetic inputs. Empty weights produce the absent `(0,0)` pair; a smallest-positive donor pair `(100 quanta, 1 quantum)` stores unchanged at the lower strict endpoint; and the existing normal donor bits `398DD8E4/34A16400` store unchanged. Those controls check the existing helper contract only. Native donor weights and terms were not supplied, so these cases do not reproduce or certify the actual T15 mixture.

## Validation

Both O0 and O2 produce the same four result rows: the candidate fails at stage 6, and all three manufactured mixture controls pass. The profile, current common-core source, and extracted-helper hashes are recorded in `replay.json`. Graph freshness and these focused source replays do not establish runtime or scientific validation.
