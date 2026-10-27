# CP02 precipitation transitions: KG refresh

This bundle records the scoped Graphify refresh for PR115 source commit `cd2773a2951c9b635591124c970a1d3852620b8a`. It is a graph-structure update only.

## Scope and outcome

Four frozen Python paths were incrementally AST-extracted into copies of the maintained KLAPS50 and Cloud-BAL graphs. The other 23 changed paths were SHA-256-bound as hash-only inputs. Both corpora retained all baseline node IDs and edge records; each gained 38 nodes and 86 edges. The 164 prior dated snapshots were preserved, and four separate raw/named corpus snapshots bring the total to 168.

Graphify reported zero missing or dangling endpoints, self-loops, exact duplicate edges, or collapsed same-endpoint groups. Community assignments and names can shift after reclustering. Graph freshness does not establish runtime behavior or scientific validity.

The detailed counts, source hashes, baseline/stage/plan/publisher pins, target plan, and extraction limits are in `manifest.json`. `apply_receipt.json` records the root publisher result. `independent_preflight_review.json` records the pre-apply GO. The independent post-apply readback returned GO and confirmed the frozen source worktree is clean; see `independent_post_apply_review.json`. The clean-source check precedes addition of this evidence-only bundle.
