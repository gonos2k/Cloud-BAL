# PR100 C2 native closure KG wrapper

This isolated wrapper preserves the closed PR98 KG engine and PR98 maintained state. PR99 was merged at `950fd7b41af5a10ab6dd36a17098e86dd8306197` without a KG apply, so the existing maintained graphs and wiki still represent PR98. The new wrapper does not create or assume a PR99 snapshot or receipt.

There are two source bases with different jobs:

- The PR100 approval base is `950fd7b41af5a10ab6dd36a17098e86dd8306197`. The preflight requires the reviewed PR100 commit to descend from it and limits that PR's own diff to PR100 paths.
- Graph extraction compares the final PR100 commit with `6ac1ddb6a50c9e4f909e47243bbd656e09fc85a3`, the PR98 lineage base. This includes inherited PR99 source and documentation changes plus PR100 paths. Unknown changed paths fail closed. PR99's archived C1 core fixture stays hash-only; evidence payloads under `docs/evidence/` are also hash-only.

The existing PR98 receipt, graph pins, 627-file maintained-source inventory, 197 inherited immutable pins, 110 dated snapshots, protected wiki/profile hashes, and rollback inventory remain pinned. New snapshots and receipts use the PR100 C2 identity. The old PR99 wrapper and receipt artifacts are left alone.

The root integration manifest must bind the PR100 commit, actual open PR URL, both source bases, and all four runtime gates: `native_20s`, `off640`, `water_compact_fulltile`, and `bulk_candidate_640_three_arm`. Every gate must include a state, evidence SHA-256, candidate/revision label, and evidence scope. These labels must distinguish inherited C1/P20 evidence from C2 evidence and describe each artifact's actual time/step coverage. The manifest must preserve `physical_approval: FAIL_OPEN` and `observation_skill: NOT_EVALUATED`. A gate label or evidence hash does not establish scientific approval.

Both entry points disable bytecode-cache writes before loading pinned helpers. Preflight is read-only. Apply requires an exact check-only plan SHA reviewed by root; it revalidates all pins and backs up protected outputs before changing them. If output correction fails, rollback restores the bound backups and removes only the new PR100 snapshots. Runtime closure and root's final manifest are required before check-only; no apply is authorized by this wrapper alone.

After the PR100 source commit and open PR URL exist and the root-owned final manifest is complete, run with the pinned Graphify interpreter:

```sh
/home/korea_keun/.local/share/uv/tools/graphifyy/bin/python3 \
  docs/evidence/pr100_c2_native_closure_20261022/kg/apply_kg.py \
  --commit <reviewed-source-commit> \
  --pr-url <open-cloud-bal-pr-url> \
  --results-manifest <root-final-manifest> \
  --results-sha256 <manifest-sha256> \
  --check-only
```

Review the exact printed `plan_sha256` before any later `--apply --reviewed-plan-sha256 <plan_sha256>` invocation. The wrapper is being prepared while C2 runs; do not run check-only or apply against incomplete runtime evidence. The source-generation state and these documents provide no runtime or scientific validation.

The dated PR100 snapshots will remain separate in the KLAPS50 and Cloud-BAL corpora. Extraction limits, runtime gate states, open items, and graph deltas will be recorded in both reports and the final receipt. Graph freshness is navigation evidence only.
