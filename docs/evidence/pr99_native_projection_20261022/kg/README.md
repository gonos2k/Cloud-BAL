# PR99 KG wrapper

`preflight_kg.py` validates PR99 source and runtime evidence without writes. `apply_kg.py` converts that verified snapshot into the pinned PR98 engine plan. The command requires an explicit mode; applying requires the exact plan hash from a root-reviewed check-only result. Graph updates use the immutable PR98 engine, followed by guarded PR99 report and receipt corrections.

Both entry points disable bytecode-cache writes before loading the pinned helpers. Runtime gate states are evidence labels; an `OPEN` or `INCOMPLETE` label does not authorize application. Root approves a fresh plan only after the diagnostic process has closed and its final integration manifest is reviewed.

The maintained selection includes the changed common transport core and its historical-fixture test. The archived pre-certificate C1 core is hash-only evidence; it is excluded from structural extraction to keep its historical functions separate from the current implementation.

Run after the PR99 source work is committed and reviewed, the checkout is clean, and the root-owned integration manifest is finalized:

```sh
/home/korea_keun/.local/share/uv/tools/graphifyy/bin/python3 \
  docs/evidence/pr99_native_projection_20261022/kg/apply_kg.py \
  --commit <reviewed-source-commit> \
  --pr-url <open-cloud-bal-pr-url> \
  --results-manifest docs/evidence/pr99_native_contract_20261022/manifest.json \
  --results-sha256 <manifest-sha256> \
  --check-only
```

The check-only output includes `plan_sha256`. Only after root review of that exact plan, use the same arguments with `--apply --reviewed-plan-sha256 <plan_sha256>`. The apply path revalidates the preflight, invokes the pinned PR98 helper, corrects its PR98-only labels and receipt schema using unique checked anchors, and writes the final PR99 receipt last. If post-apply correction fails, it restores the helper's hash-bound backups and removes only the new PR99 snapshots. Do not invoke `--apply` while runtime gates or the root integration manifest are pending.

The preflight pins main base `6ac1ddb6a50c9e4f909e47243bbd656e09fc85a3`, the closed PR98 receipt, the existing PR98 KG helper, both maintained graph hashes, 110 dated snapshot directories, the 627-file source inventory, 197 immutable pins, and protected wiki/profile content. The checked out `graphify-out/` in this PR99 scratch tree is historical and is never a target.

The integration manifest must bind the reviewed commit and PR URL, preserve `physical_approval: FAIL_OPEN` and `observation_skill: NOT_EVALUATED`, and include explicit `runtime_gates` records for `native_20s`, `off640`, `water_compact_fulltile`, and `bulk_candidate_640_three_arm`. The last gate separately binds the revised storage candidate's matched OFF/HYDRO/COUPLED cohort. Each record carries its actual `COMPLETE`, `INCOMPLETE`, or `OPEN` state and a SHA-256 evidence pin. Those states are recorded as evidence; KG freshness does not imply runtime completion or scientific approval.

At wrapper validation, source was still uncommitted and the root-owned integration manifest was pending. The check-only guard test returned `BLOCKED_NO_WRITES` at the clean-commit check. No apply or Graphify update had been run at that stage; the final maintenance receipt records any subsequent application.

Preflight source: `preflight_kg.py`. Guarded wrapper: `apply_kg.py`.
