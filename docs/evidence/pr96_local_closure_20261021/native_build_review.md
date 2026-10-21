# PR96-C1 native build review

Review outcome: **GO for the planned 600-second OFF, HYDRO, and COUPLED
comparison.** This is a source/build/launch-provenance review. It does not
evaluate the in-progress forecast results or establish physical approval.

## Build identity

The source manifest is
`/var/tmp/pr96_sources_c1_20261021/manifest.json` (SHA-256
`1d1e2d28b0bfbf531ecfd66c2193936836ce2df62625a3354e40b15f02178f22`); its
override map is SHA-256
`12ad4948b13f6ab39fe66c7d1f517c722f5c2d809aeec0b6e2ae1edc0fbec3ac`.
The manifest binds to the C4 build receipt SHA-256
`3c4687e71dffea99000e7aa2835074f55a4ccf1782b31940bfdb4e234a19f669`.
All nine C1 override names are present. Eight staged source hashes match C4;
only `module_mp_kdm6.o` differs. Its C1 source SHA-256
`f09a413c36b7bda9fb7376f0276e00329179c68bdbef1e4766bae2811152f58b` was
reproduced by applying the manifest-pinned transform
`5e153b7581ca48c83752b1d552aa20de635478fce2877f7fe483018ee542e1d8` to the
C4 KDM6 source. C1 and C4 cycle-support source hashes both equal
`d8ade43c7fe053e49a415b3de50680074bd56593ce9b5c9f31fdffb8036e91f6`.

C1 build receipt SHA-256:
`ac7b1cbefc2cbbf128b7bbe08573d79b575b3b50d51db3a955f1bb0d6d02ae56`.
The receipt reports `PASS_OVERLAY_BUILD`, `full_clean_build: false`, and
`model_run: false`. Its executable SHA-256 is
`a714f00d3f81c0b47d94aef815f1f765ae48842e9de629cb869323ccfc22a96d`.
The compiler is pinned Intel ifx 2026.0.0, SHA-256
`909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef`; the
C1 and C4 profiles and per-override O2 strict floating-point options match.
Both use the pinned `CLOUD_BAL_REPRO_FLAGS` profile with strict FP and FTZ
disabled. This is a partial-host overlay build, not a clean full-WRF build.

## Runner and input bindings

The frozen runner manifest SHA-256 is
`939b386a505491908b65ad06cb19c2c5cbe534bd5d86f1b24231281d0a14701b`.
Its runner source and Intel profile hashes match the manifest. Each 600-second
preflight binds the same C1 executable, requests 30 timesteps, and reports a
passing disk guard on the Lustre output filesystem. The HYDRO input receipt
SHA-256 is `967a481070c37286f6aef8d616679583f1c86afb7dd60ac64f1d411977eba39b`;
its artifact chain hashes verify and its boundary hash matches the frozen OFF
and COUPLED boundary.

The first wrapper attempt hit `FileExistsError` before model launch because
its dry preflight directory had already been reserved. The three dry preflight
files are preserved under
`/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/preflights/`.
The new runs use fresh directories under
`/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/runs_on_lustre/`;
each has a hash-bound preflight and
launch-provenance file. Current `rsl.out.0000` logs show all three WRF tasks
starting and accepting `wrfbdy_d01`. No closed run receipts or endpoint audits
exist yet. This review therefore records launch initialization only; final
run status and response remain pending.

| Arm | Dry preflight SHA-256 | Lustre preflight SHA-256 | Launch provenance SHA-256 |
|---|---|---|---|
| OFF | `7c011dff8b285e68017116ec7721ae7d40cc35fc66b946b6d96678c1070c0fd8` | `1748a87872b029bafaf3b77ce94e20726aed8618575ee714b0c7ef330db88d49` | `a7f8a905e7da4855636b85d692522c2b8c7eef1ed1b0ce011113809ea8065a57` |
| HYDRO | `a98a5c7866136b8fd22389324beec51d239f409bb4a57993858b804114832f38` | `857c313e057008437da76e24111301de27a52d827bf76abe999b66734e96f9c5` | `2873f532de7ec74229059f116c52d49ec7d9ffc4ecf405dec6e8bf1a7b85a4fb` |
| COUPLED | `6c40074195e4e723075624bba7633a901a367c5a132077f9c2ad95ea3d274a12` | `77b784f79bdde59c9b50bcfcffb6a5aaeb058601006873d1ad35b606171dafd8` | `d48806f6cd23e7710fedbda087a67fd35333c814ba95cb8aa5791c6409cc9651` |

## Scope checked

Compared the C1 source manifest and override map with the C4 build receipt;
verified all staged override hashes, the transformed KDM6 output hash, cycle
support identity, compile profile/compiler identity, runner manifest, HYDRO
receipt chain, and the three current preflight/launch-provenance bindings.
No model was launched by this review, and no code, input, or graph/KG data was
changed.
