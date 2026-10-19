# PR89 C5 T7 rain public-store audit (read-only)

Scope: OFF 600-second C5 artifact at `/var/tmp/pr89_OFF_600s_c5_20261019/run`, checked against its exact C5 build inputs. No source edits, rebuilds, or reruns were performed.

## Runtime record

`receipt.json` records status `INCOMPLETE`, return code 128, and six completed 20-second steps (120 seconds); the next call stops with `PR87 invalid continuous or unrepresentable rain public pair`. In `rsl.out.0000.gz` (decompressed line 2,277,177), the diagnostic is `PR87_RAIN_PUBLIC_STORE_REJECT 7 222 193 4`, followed by printed Q=`1.0260397E-09`, N-volume=`8.1688224E-05`, dry density=`1.127288`. The write statement orders these fields as `(itimestep,j,i,k)`.

These are formatted default-real output values, not captured bit patterns. No exact REAL32 operand bits were found in the rejection record. The rain public-store raw ledger does not contain this rejected cell: it is written only after the validity check, for accepted pairs requiring an adjustment or number round-trip correction. Thus the failure receipt does not establish whether the initial continuous volume-envelope check or the subsequent shared store/round-trip checks rejected it.

## Predicate and units

The compiled KDM6 caller passes `qrs(i,k,1)`, `nrs(i,k,1)`, and `dry_density(i,k)` to `pr87_rain_public_store`. Its inputs are REAL32. The helper interprets Q as specific rain mass, N as rain number per volume, and divides N by dry-air density to form specific number. It then requires the pair to lie inside the source-derived rain PSD envelope, using:

- `minimum_ratio = pidnr / lamdarmax**dmr`
- `maximum_ratio = pidnr / lamdarmin**dmr`
- `volume_bounds = dry_density * [lamdarmin**dmr, lamdarmax**dmr] / pidnr`
- `N-volume` between `volume_bounds(1)*Q` and `volume_bounds(2)*Q`

The pinned KDM6 constants are `pidnr=12566.37109375`, `dmr=3`, `lamdarmin=961`, `lamdarmax=35000`. The helper then calls `joint_moment_store` with subnormal handling, normal-Q adjustment, and joint quantum absence enabled, plus `volume_number_bounds`. The caller stores the returned Q and specific N in host fields only after `valid` is true. Both the helper's precheck and store routine use strict volume comparisons; their failure is surfaced through the same `valid=false` outcome and generic fatal.

Using only the rounded diagnostic text gives approximate `Q/(N-volume/rho)=1.4159228646e-5`, close to the source upper ratio `pidnr/961^3=1.4159232646e-5`. This rounded calculation cannot identify which exact comparison failed or prove a PSD violation. No tolerance change or physical-cause attribution follows from this audit.

## Hash-bound files

| Artifact | SHA-256 |
|---|---|
| Compiled C5 KDM6 override `/var/tmp/pr89_native_build_20261019_c5/source/overrides/module_mp_kdm6.F` | `14c6145df549541fae2aab84e98ee480ba6ac8a7c769dd926a6d44f22451c35d` |
| Preprocessed compiled KDM6 `/var/tmp/pr89_native_build_20261019_c5/preprocessed/module_mp_kdm6.f90` | `f97265078fe3a10643fea37713817de1e6d44b21b0653a1c01b9867dfa9b78ed` |
| C5 em source input `/var/tmp/pr89_sources_20261019_c5/module_em_pr89.F` | `0d3b1fe91a01c747a2339487695d82c7109ad4df3da5cbc561ca338c1fecf91d` |
| Compiled/preprocessed module EM `/var/tmp/pr89_native_build_20261019_c5/preprocessed/module_em.f90` | `ed7a869669481708f5d6773ff635add67d7acb3d287f719f82b4b18d78fda808` |
| Native executable `/var/tmp/pr89_native_build_20261019_c5/wrf_pr87_overlay.exe` | `beb2da6745606566074e15a043d173a8be01d277f00c4cc90ad3915f5de5a2d6` |
| Native build manifest `/var/tmp/pr89_native_build_20261019_c5/pr87_native_overlay_build.json` | `1079c73676532bb6ee21c37c9143dcc74a5f93001be01e18f3a283504070dfaf` |
| Rain helper source `Cloud-BAL/tools/pr87_rain_public_store.f90` | `fdc3e4f115720e9996b0efa29180382d98dd8dcb5f881677fab7c224bde4e855` |
| Shared store source `Cloud-BAL/src/common/cloud_bal_joint_transport.f90` | `aef7f536f85983f4fcb9dd266fafc6c5e900dbf0e1c485b1afd55a8dee56bd51` |
| OFF run receipt `/var/tmp/pr89_OFF_600s_c5_20261019/receipt.json` | `80b6fa75e515751cb83992301b8b32a0cb858d9c58dafb57faf682296ae90e34` |
| OFF preflight `/var/tmp/pr89_OFF_600s_c5_20261019/preflight.json` | `cdcbd5999f610002ccd02257d0f8db4ed24bd358257d7f25e83d338f221c6460` |
| Runtime stdout `/var/tmp/pr89_OFF_600s_c5_20261019/run/rsl.out.0000.gz` | `baefdf8064c18d6ed23bd832f481cc2b6c4522fd51eeebf9030b8c88bb6a6e95` |
| Rain Q/N public-store ledger `/var/tmp/pr89_OFF_600s_c5_20261019/run/pr87_qn_public_store.raw.gz` | `07db2a404b08690ff73f44aa22f1b927710452581190209a46da78ff7b46a636` |
