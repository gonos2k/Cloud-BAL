# PR93 bounded KG snapshot

This package publishes a small, reviewable summary of the PR93 incremental Graphify update. It does not contain either complete graph, a private profile, or protected wiki content.

## Provenance

- Pull request: [PR #93](https://github.com/gonos2k/Cloud-BAL/pull/93)
- Frozen source commit used to build the snapshot: `475062cc04deb42af8f008aa2901e69383d23d08`
- The bundle is a derived documentation-only publication after the frozen extraction source. Identify its publication commit from the PR head/history; it is distinct from the source commit above.
- Snapshot labels: KLAPS50 and Cloud-BAL each use `2026-10-20-active-ice`, following their own `2026-10-20-source-store` snapshot.
- Tool: Graphify 0.9.53. The maintained source manifest had 627 entries; 197 immutable pins were verified.
- The unchanged private receipt is bound by SHA-256 in [public_summary.json](public_summary.json); its contents are not included.

## Graph deltas

| Corpus | Before nodes / edges / communities | After nodes / edges / communities | Delta nodes / edges | Extracted nodes / edges |
|---|---:|---:|---:|---:|
| KLAPS50 | 39,132 / 81,807 / 3,225 | 39,220 / 81,934 / 3,207 | +88 / +127 | 144 / 365 |
| Cloud-BAL | 13,304 / 23,357 / 1,193 | 13,392 / 23,483 / 1,210 | +88 / +126 | 144 / 365 |

Counts describe the selected-source incremental extraction; they are not evidence of scientific validity. Integrity checks recorded zero unverified nodes, missing/dangling endpoints, self-loops, and exact duplicate edges.

## Runtime and validation pointers

The paired C4 runtime evidence records completed 600-second requests and 30 completed timesteps in each arm. The pinned Intel canonical suite exited 0; the focused suite passed 23 tests. The generic policy gate remains **FAIL**, and physical approval remains **FAIL_OPEN**. These are evidence pointers only; they are not inferred from graph contents.

See the [active-ice contract](../../../PR93_ACTIVE_ICE_CONTRACT_20261020.md), [paired runtime summary](../runtime/c4_runtime_summary_20261020.md), and the machine-readable [public summary](public_summary.json).

The independent post-apply preservation and publication review is in
[independent_review.md](independent_review.md).

## Extraction limits

Graphify processed selected PR93 source and documentation structure. Evidence payloads were hash-bound only. Cross-file Fortran `CALL` extraction is partial. Graph freshness is navigation evidence and does not establish runtime correctness, physical validity, observational skill, or scientific approval.
