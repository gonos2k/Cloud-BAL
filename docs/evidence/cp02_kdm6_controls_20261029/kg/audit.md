# CP02 KDM6 controls KG preparation

Status: baseline captured; source extraction pending root freeze and review GO.

## Maintained baseline

The two corpus roots are dated separately. Under the maintained snapshot rule (direct directories under `graphify-out/` whose names start with a four-digit year), the baseline has 192 snapshots: 94 KLAPS50 and 98 Cloud-BAL. The two additions from the prior 190-snapshot baseline are each `2026-10-29-cp02-wrf-first-call`. All prior dated snapshot inventories and file hashes are recorded in `baseline.json`.

There are also 51 direct `kg-update-*` backup/staging directories containing graph and manifest files (28 under KLAPS50, 23 under Cloud-BAL); these are not counted as dated snapshots. The baseline records their wider directory counts separately for audit clarity.

Current maintained graphs:

| Corpus | Nodes | Edges | Communities | Manifest rows |
|---|---:|---:|---:|---:|
| KLAPS50 | 41,741 | 86,787 | 3,418 | 5,426 |
| Cloud-BAL | 15,913 | 28,329 | 1,423 | 5,788 |

Relative to the pre-PR125 graph state recorded in the prior evidence receipt, PR125's graph delta is +35 nodes, +82 edges, +24 communities for KLAPS50, and +35 nodes, +82 edges, +6 communities for Cloud-BAL. That prior PR125 graph has already been staged into the maintained roots; this preparation has made no graph updates, so the current task delta is zero.

## Manifest audit

Both maintained manifests omit the two PR125 source paths despite the corresponding graph nodes being present:

- KLAPS50 keys missing: `Cloud-BAL/tools/cp02_wrf_first_call.py` and `Cloud-BAL/tests/test_cp02_wrf_first_call.py`.
- Cloud-BAL keys missing: `tools/cp02_wrf_first_call.py` and `tests/test_cp02_wrf_first_call.py`.

`baseline.json` records their SHA-256 hashes. The replacement helper will add these rows and the three newly frozen PR126 paths to staged manifests only. It uses a distinct explicit manifest path and subset-only updates that preserve all untouched manifest rows. Root publication is not part of this preparation.

## Validation boundary

No source code was extracted for this task because the PR126 source selection is not frozen. Capture GDB scripts, evidence plots, and extraction scripts remain SHA-256-bound only. After freeze, the helper will require exactly five selected paths (two PR125 repair paths and three PR126 paths), verify their SHA-256 hashes, and stage updates under `/var/tmp/cp02_kdm6_controls_kg_20261029`. It does not write to maintained graph or wiki files.

Graphify extraction provides structural relationships only. It does not validate runtime behavior, the physical model, or scientific approval. Fortran cross-file `CALL` extraction is partial; graph freshness does not establish runtime or scientific validation.

## Staged, published, and independently read back

Root froze five maintained source hashes and issued GO. Only three newly added Python paths were AST-extracted; the two PR125 files received manifest-row repair only because their graph nodes were already present. GDB capture scripts, input extraction scripts, evidence plots, and other evidence remain hash-bound only.

The isolated stage and maintained readback both passed. KLAPS50 changed by +46 nodes, +101 edges, and -29 communities; Cloud-BAL changed by +46 nodes, +101 edges, and -1 community. Each gained five manifest rows. All five edge-integrity diagnostics were zero for both corpora. The prior 192 dated snapshots (94 KLAPS50, 98 Cloud-BAL) remain byte-identical; the two newly dated snapshots bring the total to 194.

Graphify 0.9.53 completed the merge with `rapidfuzz==3.14.3` installed under the task-specific `/var/tmp` dependency directory, because the installed Graphify environment lacked that imported package. The source worktree `graphify-out/graph.json` and `manifest.json` still match their HEAD hashes.

The clean focused test shard passed 155 tests. Captures cover OFF, HYDRO, and LIQUID, with two consecutive calls per rank; observed `itimestep` values are 1 and 2 and `dt` is 20 s. The controlled debugger stop is not a completed forecast.

OPEN: RK-substep ordinal interpretation, direct model-clock binding, same-call MU/hybrid dry-mass state, process budgets/response, and forecast skill. Structural graph freshness and sampled endpoint arrays do not settle these items.

The published Graphify/wiki files match `publish_receipt.json`. After publication, one append-only validation/open-items addendum was added to `wiki/log.md`; `readback.json` records both the original published log hash and its final hash. Publication and readback receipts are preserved unchanged.
