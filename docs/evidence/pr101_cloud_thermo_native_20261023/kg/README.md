# PR101 guarded KG update

This wrapper stages an incremental Graphify publication on the closed PR100 maintained state. `preflight_kg.py` is read-only. `apply_kg.py` defaults to no mode: invoke it with `--check-only` to create a deterministic plan, then root must review that exact `plan_sha256` before a later `--apply --reviewed-plan-sha256` invocation. This preparation did not run preflight, Graphify, check-only, or apply.

The approval base is `d531fdd02bb4d83c5f01e08fb780211d899e854e`. The graph-selection base is the PR100 source commit `870dd5c9dac9aa1fae9f836c051cffd5699c6f85`. The preflight checks both ancestry and both diffs separately. It reuses the pinned PR98 engine/helper and PR100 receipt, verifies the 627-entry maintained-source inventory, 197 inherited immutable pins, 112 dated snapshots, current KLAPS50 and Cloud-BAL graph pins, protected wiki/profile state, and both closed PR100 snapshot additions.

The approval diff allows PR101 source/doc/evidence paths and only the changed PR86 runner/test. Graph selection includes PR101 paths, the exact changed PR86 paths, and any PR100 lineage delta since the graph-selection base. All other changed paths fail closed. Evidence under `docs/evidence/` is hash-bound but excluded from Graphify extraction. Known malformed fixtures remain excluded by the inherited source-selection policy.

The root-owned final results manifest must bind the clean PR101 commit, open PR URL, approval base, and graph-selection base. It must provide `P_C2_640`, `cloudthermo`, `upperwind`, and `T1sum` gate rows, each with an explicit `COMPLETE`, `INCOMPLETE`, or `OPEN` state, evidence SHA-256, candidate/revision, and evidence scope. It must retain `physical_approval: FAIL_OPEN` and `observation_skill: NOT_EVALUATED`.

The pinned PR98 engine writes its historical PR98 table label, log suffix, and 2026-10-22 index date. The PR101 wrapper checks those generated forms against saved rollback copies, changes only the two generated table rows and snapshot section/date, and replaces only the generated log suffix. Historical wiki bytes remain the saved baseline outside those bounded generated sections. The adjacent focused tests exercise these boundaries and the hash-only treatment of inherited PR100 evidence.

After source freeze, use the pinned Graphify interpreter and a root-owned manifest:

```sh
/home/korea_keun/.local/share/uv/tools/graphifyy/bin/python3 \
  docs/evidence/pr101_cloud_thermo_native_20261023/kg/apply_kg.py \
  --commit <reviewed-source-commit> \
  --pr-url <open-cloud-bal-pr-url> \
  --results-manifest <root-final-manifest> \
  --results-sha256 <manifest-sha256> \
  --check-only
```

Review the printed plan hash and selected-path manifest. Applying requires a separate root GO and the exact reviewed plan hash. Graph freshness remains navigation evidence and does not establish runtime or scientific validation. KLAPS50 and Cloud-BAL snapshots stay separately dated; extraction limits and gate states are recorded in both reports and the receipt.
