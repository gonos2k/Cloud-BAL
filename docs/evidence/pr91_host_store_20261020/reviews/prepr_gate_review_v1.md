# PR91 pre-PR source/evidence gate review v1

Date: 2026-10-20. Scope is read-only review of the current staged Cloud-BAL tree. WPS-footprint evidence was excluded because its artifact is being revised. This review does not attest native runtime completion, conservation closure, or scientific approval.

## Result

No source/evidence blocker was found that prevents a draft PR, provided its title/body clearly state that paired C14 240-second OFF/COUPLED runs remain open, the same-candidate 600-second runs are pending, and scientific approval is open. Do not describe this as runtime validated or accepted. KG/readiness remains false.

The reviewed index tree is `0c439aa7dae0ecc4529c7effdb23ba3bd06714cd`.

## Hash and identity checks

- Canonical 63-test receipt `docs/evidence/pr91_host_store_20261020/final_validation.json`: SHA-256 `1ff23ca627ec459f595f852e3e5e183c13a83e7e1e23c5d97adcf4b1569f2b24`; staged and worktree bytes match. Receipt reports 63 PASS, pins 57 sources and 6 logs, names the pinned Intel profile (`tests/intel_toolchain.sh`, SHA-256 `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`), states native runtime is not claimed, and keeps physical approval false.
- Source-pin receipt `docs/evidence/pr91_host_store_20261020/final_c14/source_pins.json`: SHA-256 `bc8a3256e0fec329fbd115fd8e4501f383227541dc6f14088b1c0922fe4f7569`; staged and worktree bytes match. I recomputed every declared source and log SHA against its current file; all matched. The four `/var/tmp` source/build pins also exist and match their recorded bytes.
- C14 bundle pins: `build_binding.json` SHA-256 `6295797499611ccf97dbd3f63b3c6825f0c5d2a95b3688c5671bf4a24bc87d77`; `build_receipt.json` SHA-256 `273b08fa9bb31d4070f59c817b3d59f77154947366dbcf8edb53c546360e053f`; `manifest.json` SHA-256 `b134ad8da2ac7b78b54973fda07bac3420af14b72380a34ab31b4fe41019f2c1`. Build binding matches the current C14 generated source hashes and pinned compiler profile. Its executable SHA `5581e1be3febd54409304ccf7cbe305830a75968858075bf0d95f68b48d812be` matches `/var/tmp/pr91_native_build_c14_20261020/wrf_pr87_overlay.exe`. Receipt accurately calls this a partial overlay, not a clean build, and says `model_run=false`.
- C14 independent opt-in/source review: `docs/evidence/pr91_science_sources_20261020/final_c14_validation/independent_source_review.md`, SHA-256 `3d79cfcd810652eb123287ad2b26e3665d0abaaba41bc2401931c511f8f7a7cd`. It binds the same maintained core, generated host, transform, and tests as the final pins; states the positive-Q representation policy is opt-in/default-off and documents transaction rollback/counter behavior. It explicitly does not claim runtime success, conservation closure, or science approval.
- Historical C13 close receipt: `docs/evidence/pr91_source_store_contract_20261020/c13/runtime/closed_runtime_audit.json`, SHA-256 `7542f469dbcd9e42a8ae060009c8c3ec69ce6b5a0cc8234fb16474af897d81ac`; it says INCOMPLETE after eight completed steps, T9/RK2 failure, and no 600-second attempt. Current contract text correctly says C13 is not an accepted replacement for C7.
- D3 original-17 replay: `docs/evidence/pr91_host_store_20261020/replay_provenance/d3_bound_replay.json`, SHA-256 `43493ba3c017c40e9fe58995d9431f888c91a123a38ede7d058a378ffca7f2f3`, reports 17 records and binds trace hashes to the closed diagnostic. `diagnostic_d3/receipt.json` SHA-256 `5777b1992fd4ceafa56004b45663635eb0d9186a8810bae86808166d8a748ccc` correctly identifies the run as INCOMPLETE after 9 steps/180s, not a corrected candidate success. The contract scopes the 17 failures to six selected coordinates.

## Open status and exclusions

At review time, root reports paired C14 240-second OFF/COUPLED runtime still running (both reached T20); 600-second runs are pending. The C14 manifest is consistent with this state and makes no runtime-success claim. The changing WPS footprint artifact was intentionally not reviewed or bound here; it must receive its own final review before publication if included. No KG update/apply was performed.
