# Independent review: WPSQC horizontal replay

Review date: 2026-10-20
Reviewed from the PR91 worktree, read-only. This review covers the archived 18-level QC horizontal replay and its scope statements; it does not validate the separate paired host-store runtime or a full operational WPS/real execution.

## Findings

The preserved v5 LAPS QC headers record earth radius `6.3712290039062500E+03` km. The inspected `read_met_module.F`/`process_domain_module.F` binding and replay driver pass the corresponding `6371229.00390625` m value into `push_source_projection`. The replay invokes the archived WPS `interp_sequence` with `four_pt+average_4pt`; the archived active `METGRID.TBL` QC section declares the same method and QC output flag. The replay uses fresh Intel-built operator modules in a fresh scratch path and hashed preserved WPS support objects.

Independent data checks found 288 output rows and exact row-for-row agreement with `direct_interp_288.json`; all 288 actual-radius predictions match the met_em QC REAL32 bit patterns. The wrong-radius output has 288 rows, 65 matches, and 223 mismatches. Independently filtering persisted target-corner coefficients to the original 3×3 source support yields the same 36 `(target, source, coefficient-hex)` links as `inverse_support_rows.txt`, across 16 targets and 9 source cells. The scan record reports all 65,988 native met_em mass-grid coordinates scanned, 16 supported targets, 36 links, and 36 coefficient-hex matches. The source record and met_em input hashes in the manifest match the preserved external files. All 67 entries in the replay bundle SHA256SUMS, including ignored `.log`/`.out` artifacts, exist and hash correctly.

The science gap document and `support_operator_lookup.json` correctly constrain the result to the QC horizontal component at the preserved input/time/pressure levels. They leave other fields and masks, QC-only attribution of final met_em values, and real.exe pressure-to-native-eta influence open; they make no claim that WPS or real.exe was run.

## Reproducibility follow-up (resolved)

The initial review found that `commands.sh` wrote derived JSON into the archived evidence bundle. The publication fix now copies the evidence parent to a fresh scratch bundle and runs `rebuild_footprint.py` from that copy; generated JSON stays in scratch. The manifest records a reproduction where archived JSON hashes stayed unchanged and scratch JSON matched the archived results.

The initial review also noted missing toolchain hashes. The manifest now pins the copied Intel profile at `toolchain/intel_toolchain.sh` and the ifx executable SHA-256, in addition to compiler version and build logs. Both hashes match the current profile and compiler files. These follow-ups close the review findings; no unresolved reproduction or toolchain-provenance blocker remains.

## Reviewed artifact hashes

- `direct_interp_288.json`: `06cfdb8ed68c24934bf2f2282dc06d37f5c85095be520c3d7a73d6c4b1b4db0f`
- `replay_18level/manifest.json` (updated publication manifest): `73cbbd104bf19072a1c6ceb8940c8ec37da4ed9c837fffd00aa3f21babacbbc9`
- `replay_18level/grid_rows_288.out`: `b4ea3fb18d333c9dfe362c396efe2ae1e905a3a6459dc7f3c568dcb2c7f6a213`
- `replay_18level/grid_rows_288_wrong_radius.out`: `f6fd5eba221477423ce41365bf2c7682b6353eaddf06efe77277c7556cbc38ce`
- `replay_18level/inverse_support_rows.txt`: `e8a79a42748c9e201287b53a25990f75883632f6576e7a21263e0cdb08f3f3db`
- `tests/intel_toolchain.sh`: `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`


## Publication re-review

Re-review status: **PASS; earlier reproduction and toolchain provenance findings closed.** `commands.sh` SHA-256 is `21c8982e45b5c90594c4fd2b4e0bcb1414e8f53b0797b1e77dbd48d94cfbaa93`; the updated `manifest.json` SHA-256 is `73cbbd104bf19072a1c6ceb8940c8ec37da4ed9c837fffd00aa3f21babacbbc9`. The archive checksum list contains 68 entries; all 68 files exist and match their recorded hashes, including the copied Intel profile and compiler build/output artifacts. The manifest records scratch reproduction with unchanged archived JSON and matching scratch outputs.
