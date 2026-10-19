# PR90 C7 source and build bindings

This directory archives the exact C7 generated source manifest, source overrides, and partial overlay build receipt. The copies were byte-compared with their sources under `/var/tmp` before this note was written. The source/build files at this directory root are separate from the arm receipts in the duration subdirectories; no native arm arrays are archived here.

## Source set

- Identity: `PR90-C7`; base commit: `3bc7bb8df6a100b60c6f8908ad93a7c3d981f360`.
- `sources.json` SHA-256: `216c442320d7c24af078fe42adc680ef4c61f53fd3517c35a1e3bb2513493525`.
- `overrides.json` SHA-256: `4a10821c65fbecc29f4a221050004dd202305cfba4fa4e596ae9d1dc99e9db2d`.
- Parent C5 manifest SHA-256: `67d5bff1712704ce6b8a53df628c80f737d226e988f85e9826e782354382c851`.
- Generated KDM source at `/var/tmp/pr90_sources_c7_20261019/module_mp_kdm6.F`: SHA-256 `983095a0aa0c76eab4efdda27f9435e61634e08e542ef9bd096aa4cf8004eca4`.
- KDM preprocessed source at `/var/tmp/pr90_native_build_c7_20261019/preprocessed/module_mp_kdm6.f90`: SHA-256 `38b9932d66f216687ead37a957a6d909cd4c632a39d86b6cd7a2b86239e0ed09`.
- Replaced KDM object SHA-256: `ad2ef857a24be6bf6640c59d444221184c701dd678eb8dcb5ca23a7a4c112c59`.
- Other changed-source identities are in `sources.json`; the build receipt records each requested and staged source hash. The current maintained core and public-store helper hashes are recorded in the manifest.

## Build

`build_receipt.json` SHA-256 is `7a58ac2ae90eca9ffe0500515282b537e11db25ab9de8175856609bf812bba31`. Its status is `PASS_OVERLAY_BUILD`; `full_clean_build` and `model_run` are false. This is a selected-object partial-host overlay, not a clean whole-WRF build.

- Executable `/var/tmp/pr90_native_build_c7_20261019/wrf_pr87_overlay.exe`, SHA-256 `5f5599e38759a9e2be27a9e7e0977370592c92cab328062d07eb359bddd19572`.
- Pinned profile `tests/intel_toolchain.sh`, SHA-256 `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`.
- Compiler: Intel `ifx` 2026.0.0, build profile/path and compiler hash are in the receipt.
- Physics/metadata scope: warm packet output admission plus exact final rain PSD reconstruction after the last number cap; selected-object partial host; no initial-input, prior, or FP-policy changes. `physics_changed` is true.

The paired 180-second C7 receipts and their hashes are archived under [180/](180/README.md). The receipt-bound history comparison is archived under [science/](science/README.md). The same-executable 600-second pair closed INCOMPLETE after nine completed steps (180 seconds), with a timestep-10 host joint-moment candidate fatal; its exact receipts and prefix audit are under [600/](600/README.md). This source/build archive contains no native arm arrays.
