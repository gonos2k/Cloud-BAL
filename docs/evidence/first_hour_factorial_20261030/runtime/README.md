# First-hour factorial runtime cell: B0

`run_BG_BASE` is B0: the original WRF executable with the producer background-preserved initial input. The sealed launch scripts call this combination `H0xB1` using executable-first factor indices; the paper consistently calls it B0 (B = background-preserved initialization, 0 = original executable). It was staged from the 89 declared `POLICY_BG` runtime inputs, replacing only `wrf.exe` with the original executable. The native input SHA is `9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5`; the one-hour namelist SHA is `23f5c3cb94d44831c22d86a754fa30d242456d8d14cd70a72d89b00cdec4f3a3`; the boundary SHA is `74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45`.

Preflight found all 89 declared inputs, producer evidence, and source hashes as expected. The run used 8 MPI ranks and 1 OpenMP thread, returned 0, emitted the WRF success marker, and wrote exactly the 12 and 13 UTC histories. Runtime was 136.041 seconds, from `2026-10-30T02:08:20.718852Z` to `2026-10-30T02:10:36.760223Z`. Staged inputs, source inputs, and existing producer evidence revalidated unchanged.

The 89 declared source files are regular files with no symlinks, so there were no linked targets requiring separate hash pins; see `source_link_audit.json`. `manifest.sha256` covers the evidence files in this folder.

Evidence files in this folder are the authoritative preflight and raw run record. `normalized_receipt.json` is a compatibility view containing legacy `staged_unchanged` and `source_unchanged` fields; its manifest pins the raw receipt SHA. Large WRF outputs remain under `/var/tmp/firsthour-factorial-runtime-20261030/run_BG_BASE/`. The scratch folder also retains all 89 staged inputs, its `inputs.json`, raw launcher and RSL logs, raw and normalized receipts, and both hourly histories. The first-hour output SHA is `8159eb06ca85695c533de590c27d9274c4fec4c31a11aeff58516171dae11468`.

This establishes runtime completion for one factorial cell. It does not establish forecast improvement, water balance, or operational suitability.
