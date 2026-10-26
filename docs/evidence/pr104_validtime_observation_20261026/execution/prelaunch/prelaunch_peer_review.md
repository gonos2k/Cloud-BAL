# PR104 prelaunch peer review — 2026-10-26

## Result

**GO for root launch review** of the three one-hour `HYDRO`, `AMPLITUDE`, and `STRUCTURED` arms under the frozen contract. This review is read-only: no Graphify/KG apply, compiler, build, or model launch was run. All three destinations remained absent when checked; each prepare receipt says `READY_FOR_ROOT_REVIEW_NO_LAUNCH` with `launch_attempted: false`.

## Bound inputs and prior C2 runs

The contract at `/var/tmp/pr104_validtime_preparation_20261026/shared_time_contract.json` matches SHA-256 `ed7f89aae5bac96e1e80a3282a7277174a3a65a045df88cac19ab8ec41b38df0`. It binds 2026-08-16 13:00:00 through 14:00:00, 3,600 seconds, a 20-second timestep, 180 steps, and checkpoints at 640, 1,800, and 3,600 seconds. It leaves `launch_authorized: false`, with physical approval `FAIL_OPEN` and observation skill `NOT_EVALUATED`.

For each arm, the old receipt and preflight hashes match the contract. All old 640-second receipts are `COMPLETE`, return code 0, 32/32 steps, with candidate build and input unchanged and no recorded changed inputs, processing errors, or duplicate post-KDM6 timesteps. Their preflights bind 640 seconds / 20 seconds / 32 steps. Candidate initial-state inputs and their proposal/input-receipt hashes match the arm-specific contract pins. The active executable is the same frozen C2 executable in all three arms (`387f46df…62cc9a`), and each arm uses the same boundary pin (`885591e6…706b25d7`) and 640-second namelist pin (`58c194b8…7d2fc8`). The HYDRO source receipt is the arm-specific `65fe2113…1a187a3e`; AMPLITUDE and STRUCTURED share the pinned `8dc7aa4c…2f32d675` receipt as declared in the contract.

The common PR99 build receipt is 1.5 MB and matches the recorded SHA-256 `9c4802e1…2d45dafb`; its bound executable pin agrees across all arms. I did not rehash the large executable or model artifacts. The preparation receipts carry the validated source/input pins, and the separate reference receipts and preflights were hash-checked.

## Prepared run checks

| Arm | Prepare receipt SHA-256 | Candidate `wrfinput` SHA-256 | Output |
|---|---|---|---|
| HYDRO | `f1e75f3ac03d61dcddadbabfd89244f84cef42dfaf066f7c54e03b6cc283e72a` | `46760bdf03e42cbc8e1f5b415e1b304b535d369689f95a421a287d1eb90b679c` | `/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr104_validtime_forecast_20261026/HYDRO` |
| AMPLITUDE | `93dea6837b807bd84a2ec464aad2d88606b647c69e6f2769cadeec3355106a7b` | `9038d0a26896a630b7048091a97a2c0055b26934513392195eb8e609626e74e2` | `/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr104_validtime_forecast_20261026/AMPLITUDE` |
| STRUCTURED | `4e78a0e93f9f5e265ba1518e06381ae5a947bad48297d9efe1812d925d4daeec` | `b26e5f3d712732c3459d59b82a4b44fe53eebd9be1fd450d13640d2d8398343f` | `/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr104_validtime_forecast_20261026/STRUCTURED` |

All three receipts agree on 3,600 seconds, 20-second steps, 180 expected timesteps, end time `2026-08-16_14:00:00`, the shared contract hash, the frozen C2 executable, the same candidate boundary, and the same expanded namelist SHA-256 `36941d6ce0ded8e1ca0e1912574b0aa3a839f3a6caea0a30c1987d5b34dcd21b`. The generated namelist changes are limited to runtime/end time and one-minute history output; no physics, precision, or tolerance edits appear. The 100 shared staged-input hash entries other than arm-specific `wrfinput_d01` are identical across preparations. The 640/1,800/3,600-second schedule corresponds to steps 32/90/180.

The contract-bound 14Z LSO file exists, has SHA-256 `5897d4ec8d4979a71369f68de95c68f7229ae76fa6104619d893b204b9ad6ec9`, and its first-line date is 16-Aug-2026. Its size is 370,433 bytes; no large model artifact was reread for this check.

## Disk and execution state

All three per-arm disk guards report PASS. Their combined required free space is 3,013,853,921,578 bytes; the combined active-run projection is 2,561,775,833,340 bytes. Current Lustre available space at `/NHNHOME/WORKSPACE/26weather002_A/yhlee` was 61,970,192,797,696 bytes, leaving 58,956,338,876,118 bytes above the combined required guard. This measurement is from Lustre, where the three target output directories reside (not the `/var/tmp` overlay filesystem).

At review time all three forecast output directories were absent. No large executable, history, or runtime trace was rehashed. The review supports launch only under the frozen contract and existing root authorization; it does not evaluate runtime outcome, observation skill, or scientific approval.
