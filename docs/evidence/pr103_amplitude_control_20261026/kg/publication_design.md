# PR103 KG publication design (pre-runtime)

Status: design only. No Graphify query, preflight/check-only, graph update, or KG apply has been run for PR103.

## Frozen inheritance to bind at final check-only

- The parent is the merged PR102 receipt at `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/pr102_wind_structure_20261025/kg/kg_receipt.json`, SHA-256 `a68ff8a938fe055bb9a82465b243f806f0575eb5bc850f73d4627d74e834dba1`.
- It records the current separate graph hashes: KLAPS50 `09e24f672bd51561168e46850a3250f0df4706abb8caa63f049c5374be39d7d8`; Cloud-BAL `f17b778c628e67c63cfe5d72f1f6263c4457b520289ee074c5df37df89044be6`.
- The inherited inventory is 120 dated folders, 627 maintained-source entries, 197 immutable pins, and the exact protected wiki/profile content. A PR103 preflight must reconstruct and hash-check all 120 existing folders from the PR102 receipt, not rely on the older 116-folder PR101 baseline.
- The existing `graphify-out/2026-10-26` folder in each corpus belongs to PR102. It is immutable for this update. The new named target `2026-10-26-pr103-amplitude-control` is absent in both corpora at design time.

## Incremental selection

Use merged PR102 `eff97afe9d562d5a2fb39d4b362a7cbf1b96252c` as both the PR103 approval base and graph-selection base. The closed PR102 receipt remains bound to source commit `394b2fb02726978ab8e12080afd80c9171f50762`; that is receipt provenance, not the PR103 selection base. After PR103 source freeze, bind the clean commit, open PR, and integration manifest. Permit only PR103 docs/tools, Python `tests/test_pr103_*`, the exact IFX oracle `tests/pr103_gdtost_oracle_program.f90`, its exact six-case comparator `tests/compare_pr103_gdtost_oracle.py`, and the two explicitly reviewed shared PR86 response files. Extract the exact approved source paths; keep evidence payloads hash-only. Keep KLAPS50 and Cloud-BAL as separately rooted graphs. Reuse the pinned PR98 graph update and PR102 fixed rollback/publication helpers where their contracts match; retain strict rollback, inventory, content, graph-integrity, and root-GO gates. The selection allowlist must be finalized from the committed diff rather than inferred from this pre-runtime checkout.

## Same-day raw snapshot collision

The Graphify automatic snapshot path `2026-10-26` already exists in both maintained roots. The PR102 apply helper's raw-date path contract cannot be reused unchanged: it would collide with and risk replacing the existing PR102 raw snapshots.

Run the pinned incremental graph operation against isolated staging copies of the two current graph states. The prepared wrapper copies only top-level Graphify files and wiki files to a private `/var/tmp` stage; it omits all inherited dated directories, so the automatic date path is vacant there. The current graph roots both have curated `.graphify_labels.json` files, which are copied and hash-bound; Graphify's pinned `backup_if_protected` path therefore produces a raw date snapshot in staging. Capture that raw Graphify snapshot before the wrapper's final publication corrections. Only after staged graph/report/manifest outputs pass hash, integrity, removal-scope, and source-path checks, publish exactly these distinct additions per corpus:

- `2026-10-26-pr103-graphify-raw`: the staged automatic raw snapshot, retained as a distinct Graphify intermediate because the normal raw-date name is already occupied.
- `2026-10-26-pr103-amplitude-control`: the final named PR103 graph snapshot.

The plan and final receipt must bind the raw-name remap and role explicitly. Fail closed on an existing destination, any changed prior snapshot, or an addition set other than the four exact paths across both roots. The staged auto-date remains the actual local date; it is not overridden. Do not modify, merge, rename, or delete either PR102 `2026-10-26` folder.

## Later gates and publication

The future check-only plan must bind source commit, PR URL, captured automatic date, PR102 receipt and publication hashes, all inherited inventories/pins, exact graph selection and staging outputs, result-manifest hash, and the exact four output paths. Root GO must name the same plan hash, commit, and date; application must recheck date and all source/inventory/output pins before any write and roll back all graph/wiki/snapshot changes on failure.

The integration manifest should report the amplitude candidate, archived consumer, native capture, C2_640, and observation-input consistency as explicit hash-bound gates. Keep physical approval `FAIL_OPEN` and observation skill `NOT_EVALUATED`; graph freshness does not supply either approval. The eventual wiki/log publication date comes from the reviewed automatic snapshot date, while the named snapshot remains the PR103 work-start date.

## Current evidence boundary

The current scratch checkout is still based at merged PR102 `eff97afe9d562d5a2fb39d4b362a7cbf1b96252c` with uncommitted PR103 files. Runtime outputs and a final source commit/open PR are not yet available. This document and the prepared wrappers are pre-runtime artifacts only, not a check-only plan, root GO, or approval to publish.
