# PR89 post-apply KG preservation review

Read-only review of `Cloud-BAL/scratch/pr89_process_contract_20261019/kg_receipt.json`, SHA-256 `80df43e8df44698c597119db5bb70466e7bc265ee77e2f76c0cfc5bcaa5589c3`. I did not run Graphify or modify source, graph, wiki, or receipt files.

## Frozen validation and runtime bindings

- Receipt identity is PR 89, base `f1809781e8be49e063de6728a85374a4ebcc334f`, frozen source commit `da48cca65c57aeaad9daf717abe0a0d6b6df9e25`. The candidate checkout HEAD remains that SHA.
- The frozen `pr89_focused_validation_v1` receipt hash matches, with PASS / 43 tests, the pinned Intel profile hash, all 10 source pins matching both checkout and `git show` at the frozen commit, and the joint transport Intel O0/O2 log hash matching its committed bytes.
- The integration manifest hash matches its frozen-commit bytes. Its seven diagnostic evidence bindings all match: V50 history, C1/C3/C4 summaries, C5 120s and 600s summaries, and the T7 rain-store audit.
- The selected C5 build receipt hash and executable SHA-256 `beb2da6745606566074e15a043d173a8be01d277f00c4cc90ad3915f5de5a2d6` match the manifest. Both 120s receipts are `COMPLETE`, return code 0, final step 6. Both 600s receipts are `INCOMPLETE`, return code 128, six completed steps, with the same executable identity. Their source receipts match the committed evidence files, and the live compressed cold summaries match receipt hashes and the C5 600s summary's bindings. Each 600s summary has 1,901 parsed rows: 1,680 for complete steps 1–6 and 221/280 rows at partial step 7.

## Graph, wiki, and protected-content preservation

- Live and dated graph hashes match the receipt. Current live counts are KLAPS50 38,322 nodes / 80,555 edges / 3,123 communities and Cloud-BAL 12,494 / 22,105 / 1,121. Both corpora gained 319 net nodes and 443 edges. Each has its separately dated `2026-10-19-process-contract` graph, manifest, and report.
- The five derived wiki file hashes match the receipt. The two mirrored corpus reports match their live Graphify reports; the graph report table, index snapshot section, and appended PR 89 log entry agree with receipt snapshot identities and counts.
- Recomputed maintained-source inventory is exactly 627 entries with SHA-256 `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`, matching the recorded pre/post-equal claim. All 173 prior PR88 immutable pins are present and hash-correct; all 181 pins in the new receipt are hash-correct. Both delegated importer pins also match.
- All 13 protected wiki page/directory hashes match. The private Cloud-BAL profile remains recorded at 134 nodes / 133 incident links and unchanged; KLAPS50 remains at zero private nodes/links.

## Checkout state and conclusion

The frozen HEAD remains correct. The source worktree now has a post-apply documentation-only diff in `docs/PR89_PROCESS_CONSUMER_CONTRACT_20261019.md` linking the KG publication, plus untracked `docs/PR89_KG_UPDATE_20261019.md` and three files under `docs/evidence/pr89_process_contract_20261019/kg/`. These are follow-up publication metadata and are not part of frozen commit `da48cca`; the active maintained-source snapshot and all receipt-bound graph/wiki outputs still match. No preservation blocker found. The 600s runtime remains explicitly incomplete; graph freshness and the receipt do not imply scientific approval (`FAIL_OPEN`).
