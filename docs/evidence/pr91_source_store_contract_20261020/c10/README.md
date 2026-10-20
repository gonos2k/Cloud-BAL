# PR91 C10 source-first diffusion candidate

## Candidate and validation status

C10 is generated directly from the immutable D3 host source, not layered on C8. It restores D3’s source-stage strict mass-only representation while applying the existing `horizontal_diffusion64` operator to the complete source-prepared public Q/N field and replacing the old-state diffusion contribution once. The existing final `joint_qnb_update` candidate store still enforces strict volume bounds. No tolerance, floor, core policy, or new storage API is added.

The generated source pair and C10 source manifest are included. The focused pinned Intel test suite passes all four tests. The diffusion expression fixture uses the separately maintained `tools/pr87_horizontal_diffusion64.f90` manufactured kernel, which has REAL64-internal arithmetic. The native C10 `pr87_horizontal_diffusion64` implementation is embedded in `module_em.F` lines 871–940 and uses REAL128-internal arithmetic; the fixture does not replay that native kernel. The T2/RK3 exact-decimal source-store fixture checks the store contract at O0 and O2. These fixtures do not establish exact native-kernel arithmetic or a complete native diffusion/air path. The C10 selected-object Intel overlay build passed (`full_clean_build=false`, `model_run=false`); see `native_overlay_build.json` and the module/solve compile logs. The executable remains external at `/var/tmp/pr91_native_build_c10_20261020/wrf_pr87_overlay.exe`; its size and SHA-256 are recorded in `evidence_manifest.json`. No binary is copied. Both separate OFF and COUPLED 240-second native attempts have closed `INCOMPLETE`, return code 1, after one completed T20 `POST_KDM6` state and first seeing T2. Both fail at T2/RK3 with `PR87 unsafe complete source-prepared virtual donor`. Completed-prefix strict-pair and native inactive-ice checks cover T1 only and pass; see `../c10_t20_completed_prefix_audit.json` and the adjacent review note. The only source-diffusion delta row is T2/RK3 and has no matching `JOINT_RK` record, so it is proposed pretransaction data and was not applied. The generic donor fatal contains no exact guard operands; no negative, orphan, or underflow cause is inferred. No paired 240-second completion or 600-second request has been obtained.

## C9 failure retained

Both C9 240-second runs (OFF and COUPLED) closed `INCOMPLETE`, return code 1, after one completed post-KDM6 step and first seeing timestep 2. Their source failure raw records are byte-identical. At T2/RK3, pair 1, cell `(106,55,6)`, the C8 strict continuous volume gate rejects the physical source endpoint at stage 3, before C9 reaches its prepared-state diffusion replacement. Both external receipts, preflights, the small compressed source-failure record, and the receipt-bound summary are retained under `c9_failed_runs/`; the earlier C9 source pair remains in `../c9/`.

## T2 intermediate-versus-final store classification

The exact SOURCE_STAGE inputs are copied into `t2_fixture/driver.f90` and interpreted by the existing D3 shared core at both Intel O0 and O2. The source candidate Q/N bits are `3E8F099B2388800A` / `418A530C7487AB13`; dry density is `3F92C8CA`; mass bounds are `3CF2DD58BFD7689A` / `3DF4D2954D1355A3`; volume bounds are `41EC32773795D5C2` / `42EF1FAB0FDF013B`.

With D3’s original source-stage options (strict mass ratio, no volume bounds), `joint_moment_store` accepts stage 0, adjustment 2, and returns the intermediate R32 pair `34784CDA/4C529864`. Adding C8’s source-stage volume bounds rejects the exact continuous candidate at stage 3. The intermediate’s continuous upper volume margin is positive `1.816743679344654`, while its stored R32 dual-product margin is `-0.10917108505964279`; it is therefore an intermediate mean, not a valid committed volume pair.

Passing that exact returned R32 pair through the existing final store with the same density, mass bounds, volume bounds, and normal-Q adjustment options succeeds at stage 0, adjustment 2, returning `34784CDB/4C529864`. This demonstrates the distinction between a temporary public mean that seeds diffusion and a completed representation that passes the final dual-product contract. It does not claim the full native source/diffusion/air path has completed; that is what the C10 native replay must verify.

A prior scratch calculation mistakenly used the continuous Q64 candidate when computing the returned-R32 product margin. It is superseded and is not included as authoritative evidence. `t2_fixture/classification.json` and the archived O0/O2 outputs use the corrected R32 values.

## Reproduction

From the Cloud-BAL checkout, run `python -m unittest -v tests/test_pr91_source_first_diffusion.py`. The test invokes only `tests/intel_toolchain.sh` and its pinned Intel ifx profile, compiling in fresh `/var/tmp` scratch directories at O0 and O2. `SHA256SUMS` covers this evidence tree and is verifiable with `sha256sum -c SHA256SUMS`.

## C10 closed-run evidence

The paired closed receipts and preflights, source-diffusion rows, JOINT_RK ledger, and rank-zero error logs are copied here as `off_*` and `coupled_*`. The complete stage trace remains in the receipt-bound external run roots `/var/tmp/pr91_{OFF,COUPLED}_240s_c10_20261020/`; its compressed and uncompressed payload hashes are recorded in each receipt and the completed-prefix audit. The live process snapshot is in `../c10_live_run_identity.json`.
