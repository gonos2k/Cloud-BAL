# Protected native run provenance

This directory preserves compact, tracked launch/build lineage. The generated OLD/FIX sources, exact executed build helper, build receipt, frozen plans and start authorization are in the sibling `source/`, `build/`, `plans/`, and `runs/` directories.

## Build

`final_source_compile_go.json` and `final_compile_provenance_review.json` are verbatim independent receipts. Compile/link commands, source/object/archive-member/executable pins and link-input checks are in `../build/build_receipt.json`. The four `build_logs/*.log` files are verbatim copies from the external build scratch: compile logs are empty (zero bytes), and both link logs contain Intel warning #10148 (`-ip` unsupported); compile/link exits are zero. The exact executed helper is `../build/build_pair_executed.py`.

## Quick lineage

`quick_v1/` contains the immutable raw one-step paired-run receipt, the v1 strict gate and per-arm capture receipts that authorized the five-hour run. Its frozen full-run authorization is copied as `full_start_authorization.json`; it binds the v1 gate SHA-256 `62e2055e01636425b8d0917f913ada7a97e0306e6e92593bd622f659ced6f992`.

The first retry failed at startup with SIGSEGV under the inherited 8192 KiB stack limit. `failed_stack_attempt/` preserves its raw receipt/manifest and rank-zero error logs. The successful retry used the pinned NetCDF runtime and unlimited stack, recorded in its raw receipt.

`collector_v2/` preserves the intermediate output-guard collector receipts (OLD SHA `399cd9026d4adba51fd54e46fe96ee34e069ef738223b46e95bdff5483955c03`; FIX SHA `d4bf7e02bb713e23c5e3576b9ad91be291149364c01eb6e56c52d9ab076b3aae`). `collector_v3/` records the final strict collector with the source-audited mstep coverage guard (tool SHA `1c34e6754d3a8306f37e30b2ba3dc47a0258d05882613b521277fb52b0d4808b`), quick-v3 receipts (OLD SHA `7e90039cfb0f43c8c4e7d86cbb8dc38c7000892d7b51f151bd1333b3ee3fb755`; FIX SHA `0f36e2fa1604a55afdc5f990c9b9793686dad9bea8052fd6d42c1409482f127b`) and updated gate SHA `d5f1bbaef3ec6b27edc0cb36aeed8d3c84c33d3e632c6f72d10d72b0e06ad9dc`. `collector_v4/` adds bitwise selected-wrapper-entry to CP04-phase-1 field binding (tool SHA `1959c943` as reported by the collector owner); quick-v4 receipts and current gate are stored with their exact hashes in the inventory. These updates postdate the full-run launch. They are retained as later collector provenance and do not replace the v1 gate hash in the immutable full-run authorization.

## External runtime data

Full raw WRF history, selected process/state/surface streams, executable files and build objects remain in the external runtime tree:

`/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_protected_process_20261106/runtime/native/`

Their hashes and exact paths are recorded in run receipts/manifests. No multi-gigabyte model output is copied into the source evidence tree. The five-hour run completed with PASS. `full_run/full_run_receipt.json` (SHA `41a1d6e8dd2b0821dc03bdc6927465513c31e877981497eb795ad349284201e5`) binds the run, exit status, input stability, and six hourly history comparisons per arm. `full_run/history_parity_proof.json` is a compact derived proof of the six byte-identical hourly files per arm. `full_run/full_raw_inventory.json` is the hash/size index of the raw CP04 process, selected-state, wrapper-state, surface, and call streams (3,439 files per arm); the raw streams and histories stay in the external runtime tree. Small step-1 representative chunks are under `../representative_raw/full/`, with their own hash/size manifest. Verbatim rank-0 `rsl.error` and `rsl.out` logs are under `full_run/rank0_logs/`. Strict full-capture receipts are produced separately by the collector owner.
