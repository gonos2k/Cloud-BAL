# PR97 post-apply KG review

**Result: GO.** This was a bounded, read-only verification of the applied receipt and current corpus/wiki artifacts. No graph update, KG mutation, or model run was performed.

## Apply, source, and PR binding

- Applied receipt: `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/pr97_c1_budget_20261022/kg/kg_receipt.json`; SHA-256 `ff8aad5aaaf42f1d9038eb6d7163eea4d82b59c8b378c87cab8abc91b134442a`; status `PASS`.
- Frozen source commit `876fbbd961e03a0cde90e4cbb8128d145cc714d7` equals the PR97 worktree HEAD. Its merge base is `72bab3a89ec3b74b552646cf44386cb7a3950672`.
- GitHub PR #97 is open, non-draft, points to that exact head commit, and targets `main`.
- All 51 changed-path entries in the receipt match their committed source hashes. The 15 selected extraction paths equal the receipt's `graph_source_paths`; the remaining 36 changed paths are hash-only.
- At review time, the PR worktree also has a modified package README and an untracked package summary under the evidence bundle. Those are post-apply publication metadata; they are outside the frozen selected-source set. The committed HEAD and remote PR binding remain unchanged.

## Live graphs, dated snapshots, and preservation

Both corpus-specific live graphs match their receipt SHA and their dedicated `2026-10-22-pr97-c1-budget` snapshot copies. Each dedicated snapshot has `graph.json`, `GRAPH_REPORT.md`, and `manifest.json`, byte-identical to the corresponding live files.

| Corpus | Nodes | Edges | Communities | Delta nodes | Delta edges | Integrity |
|---|---:|---:|---:|---:|---:|---|
| KLAPS50 | 39,691 | 82,845 | 3,246 | +70 | +115 | No missing/dangling endpoints, self-loops, duplicate edges, or same-endpoint groups |
| Cloud-BAL | 13,863 | 24,393 | 1,257 | +70 | +115 | No missing/dangling endpoints, self-loops, duplicate edges, or same-endpoint groups |

All 102 receipt-baseline dated snapshot directories remain present with unchanged file membership and hashes. There are also two standard Graphify automatic `2026-10-22` backup folders, one per corpus, in addition to the two named PR97 snapshots. They are expected side effects of the pinned `cluster-only` operation: its preserved logs state “backed up curated graph (5 files) -> 2026-10-22/”. Current dated-directory totals are 51 for KLAPS50 and 55 for Cloud-BAL (102 baseline + 2 automatic + 2 named PR97 snapshots).

The automatic backup folders are:

- `graphify-out/2026-10-22/` (KLAPS50)
  - `.graphify_analysis.json`: `84616c5abaa00effc17aa65079b60a15cdf1fddae29328e17043409e5b527903`
  - `.graphify_labels.json`: `f6f069dc28c7dfff0a9d06793bad98887459144ea68aeaa3cee78af34c8c9b70`
  - `GRAPH_REPORT.md`: `70767087ae040f82aa8d563c553fc157a5b958c630c74086c4f9e28b47622025`
  - `graph.json`: `ee1af11837d935477e92704c8d2c56ae25c5377da68adc415828d796a109ba8d`
  - `manifest.json`: `500d59c467f4f22863ce3f1d01c2b6ed067208f8c6ea97b969c821f7fa5b21c3`
- `Cloud-BAL/graphify-out/2026-10-22/`
  - `.graphify_analysis.json`: `b6c6d3cfdd87f1e2dccf76932d637e2e1307bafe4006f85d083e280be1b02563`
  - `.graphify_labels.json`: `b9f8c288d1e18088fc5f4221c4149d65ccff1982d3b0bf091804118b768f02ea`
  - `GRAPH_REPORT.md`: `d02fb8f4ec30cf31d23bbcb6b52b976e297f33910cdc2340b6c31413f0e8928e`
  - `graph.json`: `602269203b9d4debf2d6c11479e3d318aa78d116c15846f1faf19ea64466653b`
  - `manifest.json`: `6d02ee075fa9256804756ceeab0e3629180ac67ab4e940ad891f042485063dfd`

The `.graphify_analysis.json`, `.graphify_labels.json`, and `GRAPH_REPORT.md` in each automatic backup match the pre-apply backups. Its graph and manifest are the intermediate merged pre-cluster state, so they differ from the pre-apply graph/manifest and from the final named snapshot. These automatic backup file hashes are not individually listed in `kg_receipt.json`; the preserved cluster logs attest their creation. The receipt separately pins the previous 102 snapshots and the final named graph snapshots.

The maintained-source inventory remains 627 entries with the receipt's before/after SHA `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`. All 197 inherited immutable pins verify. Both baseline graph pins match the receipt. Protected wiki content matches the receipt (13 protected records), and a direct comparison against the receipt's pre-apply graph backups confirms the private profile is unchanged: zero KLAPS50 nodes/links and 134 Cloud-BAL nodes with 133 incident links.

## Wiki and publication scope

- All five live wiki files match the receipt hashes.
- `wiki/index.md` differs from its pre-apply backup only in the normalized Graph snapshot section and `date_modified` field.
- `wiki/log.md` is append-only; the appended entry records the PR97 selected overlay and the stated fail-open status.
- The corpus report mirrors match their live `GRAPH_REPORT.md` files, and the multi-corpus report index has exactly one row for each corpus.
- The bounded package README and summary correctly report 15 selected paths total, with 36 other changed paths hash-only. They distinguish 22 full cloud-evaporation events per column from 2 general-branch partial-evaporation events per selected column. The summary keeps the three C1 600-second arms COMPLETE (30/30, rc=0), source endpoint and active-ice checks PASS, generic Q/N/B audit FAIL, audit queue REVIEW_REQUIRED, T1 residuals near −66,060 kg per arm OPEN, and physical approval FAIL_OPEN.
- Package artifacts at review time: README SHA-256 `541bcee66e2840297923bb862c399c04fc03b625bb04aac4bf93d2baf881836d`; summary SHA-256 `09aa19eb86170546a13a604f2828e8128224fb538c404944263f994ca9580531`. The author may update these to link this review and should recompute final bundle hashes afterward.

## Scope limits

Graphify is `0.9.53`; cross-file Fortran `CALL` extraction remains partial. The graphs document navigation and source selection only. Runtime status remains scoped, the generic audit remains FAIL, and physical approval remains FAIL_OPEN. No scientific or forecast extension claim follows from this post-apply review.
