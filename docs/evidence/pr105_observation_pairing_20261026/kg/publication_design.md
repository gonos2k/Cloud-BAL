# PR105 observation-pairing KG maintenance plan

Status: guarded preparation only. No PR105 Graphify update, staging run,
check-only plan, or maintained-tree write has been performed. Maintained
`Cloud-BAL/` and top-level `graphify-out/` plus `wiki/` remain untouched.

## Current parent state

Use the corrected PR103 publication receipt as the parent:

- Receipt:
  `scratch/pr103_amplitude_control_20261026/Cloud-BAL/docs/evidence/pr103_amplitude_control_20261026/kg/publication/kg_receipt.json`
- SHA-256:
  `77e096bd1b1e8409c7f8a71d51b090ec5f8a2b88d8079120ac48f870dc15de82`
- Publication status: `PASS`, `writes_performed: true`; source commit
  `e73203b9c2f070a58aeb8488bf1e5e67a66d5f2e`.
- Parent has 124 dated snapshot folders across the two corpora, a 627-entry
  maintained-source snapshot (`0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`),
  197 inherited immutable pins, and 13 protected wiki/profile content groups.
- PR103's `2026-10-26` additions are
  `2026-10-26-pr103-graphify-raw` and
  `2026-10-26-pr103-amplitude-control` in each corpus.
- Runtime approval fields in the parent receipt remain
  `physical_approval: FAIL_OPEN` and `observation_skill: NOT_EVALUATED`.

The PR104 `preflight_kg.py` and `apply_kg.py` in its source worktree are
preparation artifacts, not evidence of publication. Independent readback of
the maintained roots found 124 dated folders, no PR104-named snapshot, all 124
folder/member hashes equal to the corrected PR103 receipt, all 197 immutable
pin hashes equal to that receipt, and all five derived wiki-file hashes equal
to it. This confirms PR104 KG publication was not applied.

## PR105 scope and freeze condition

The PR105 source worktree is based on `main` commit
`334969e120afff720f1b5da4eb1d8f0991f1a6c1`. Graph selection must wait for the
final committed PR105 source diff. Source changes are in progress. Do not use
the stale PR105 `graphify-out/` snapshot as a publication baseline.

After the PR105 source batch is frozen, derive the selected source list from
the committed diff against graph-selection base
`6d33aa06856e4e892dd792e8def350f15c54c058`. Use the explicit combined
PR104+PR105 allowlist so PR104 source paths missing from the PR103 maintained
graph are included alongside reviewed PR105 implementation, tests, and
documentation. Keep
`docs/evidence/**`, run payloads, receipts, ROOTGO files, and KG maintenance
scripts hash-bound but excluded from extraction. Reject unrelated or shared
paths unless an explicit, reviewed PR105 change requires one. Map selected
Cloud-BAL paths under `Cloud-BAL/` in the KLAPS50 corpus; keep the KLAPS50 and
Cloud-BAL graph snapshots separately dated.

The check-only plan generator is `preflight_kg.py`; the guarded publisher is
`apply_kg.py`. `--check-only` is read-only. `--stage-only` runs incremental
Graphify on private staged copies of both corpora, syncs staged report mirrors,
the Graph snapshot back-pointer, and append-only audit entry, then records a
hash-bound stage receipt without touching maintained roots. A later `--apply`
requires root GO bound to both the plan hash and the staged-receipt hash.

The check-only plan pins the exact source commit and PR URL, the corrected
PR103 receipt hash, both current graph/report/manifest baselines,
the dated-snapshot inventory, 627-entry source baseline, 197 immutable pins,
13 protected groups, helper hashes, Graphify interpreter/version, and the
exact selected-path hashes. Preserve the PR103 pinned helper chain and
staging-only update approach. Run incremental extraction against staged
copies of the two corpus roots; derive wiki report mirrors, the graph snapshot
back-pointer, and append-only KG audit entry from those staged results. Do not
recluster, force-rebuild, edit schema/content pages, or write directly to
maintained roots during preparation.

## Runtime status boundary

Code validation and model execution are separate evidence. A source/test
validation may be recorded as `code_validation: PASS` with its exact receipt
and hashes. The immutable runtime status snapshot is
`docs/evidence/pr105_observation_pairing_20261026/execution/status_at_start.json`
(SHA-256 `f1cb354108eeaa1eedbe2943fe019ceb60667c1ae9917536377462d1dbbdf6a2`,
observed `2026-10-26T10:54:49.477482+00:00`). Its three supervisors are
`RUNNING`; its 3600-second verdict is `PENDING`. Record that timestamped open
runtime observation separately. Do not convert `RUNNING` or `PENDING` into a
closed terminal state, and do not imply runtime PASS, observation skill, or
physical approval from code validation or graph freshness. There is no wait
period for structural KG work. Keep `physical_approval: FAIL_OPEN` and
`observation_skill: NOT_EVALUATED` unless new independent evidence changes
them.

## Snapshot names and publication boundary

Choose the actual local date only when generating a reviewed plan. If the
automatic raw date already exists, retain Graphify's automatic output under a
unique `<date>-pr105-graphify-raw` name. Name the final snapshot
`<date>-pr105-observation-pairing`. Publish only these two additions in each
corpus (four exact destinations), after a separate root review approves the
complete plan hash. Refuse any occupied target, baseline drift, changed
selected path, changed parent receipt, or changed runtime evidence manifest.
The active250 ROOTGO snapshot is
`docs/evidence/pr104_validtime_observation_20261026/execution/launch/root_go.json`
(SHA-256 `f3dcc7f68660fcff2905802fdd3bb076e08dcfa76b15b2c2f90c13689b47d411`)
and declares 250 source pins. Preflight and apply recheck its hash and all pin
hashes read-only; none of those paths is in the KG write set.

The wrapper preserves the PR104 backup/rollback/readback structure, with
PR105 identity, the combined PR104+PR105 allowlist, PR105 output paths, the
124-snapshot parent count, and the open runtime-evidence contract. A staging
failure leaves maintained roots unchanged; a publication failure restores
the captured baselines and proves rollback by independent readback.

## Graph deltas and extraction limits

Corrected PR103 baseline counts:

| Corpus | Nodes | Edges | Communities | Graph SHA-256 |
|---|---:|---:|---:|---|
| KLAPS50 | 40,983 | 85,369 | 3,315 | `e6cc085065e1adfb966a213621d8b63a6326359f62b2c1a70d5e136b54aa8a04` |
| Cloud-BAL | 15,155 | 26,911 | 1,344 | `f5b976c96939c99457f5e3f403b41ecadfa6bf381ff2076edf88999a0db51abc` |

These are parent counts, not predicted PR105 deltas. Report final per-corpus
node, edge, and community changes from the staged incremental update, including
added, removed, and modified nodes plus Graphify diagnostics. For reference,
the corrected PR103 receipt records the same selected extraction size in both
corpora (317 extracted nodes / 904 edges), and the same merged delta in both
(+226 nodes / +416 edges, 236 added IDs / 10 removed IDs). These figures are
historical PR103 results only. The inspected
PR105 scratch graph has 1,499 nodes and belongs to the scratch checkout; it is
not a maintained-root baseline. Graphify's structural Fortran extraction has
partial cross-file `CALL` edges, and graph freshness establishes no runtime or
scientific validation.

## Evidence required before review

1. Final PR105 commit, exact allowlist diff, and passing code-validation receipt.
2. Runtime manifest that preserves every active process as `RUNNING` with its
   evidence path/hash; no synthetic terminal result.
3. Read-only parent receipt, snapshot/member, pin, protected-group, graph, and
   derived-wiki revalidation.
4. A staged, check-only incremental update for both corpora with extraction
   diagnostics, exact graph deltas, derived wiki sync diff, and unchanged
   protected inventory.
5. Independent plan review before any root GO or maintained-tree apply.
