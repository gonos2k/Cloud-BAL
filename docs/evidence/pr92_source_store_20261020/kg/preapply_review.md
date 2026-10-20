# PR92 KG check-only preapply review

Independent read-only review completed 2026-10-20. The maintained source/evidence working tree remains unchanged.

## Exact pins

- Frozen source commit: `5f645af5798a8d05ad6cbd429af7273bb530d2a4`.
- Base: `71b8c1d5dae181c163d04eabac9cf8f80134f417`.
- Actual PR: `https://github.com/gonos2k/Cloud-BAL/pull/92`, state `open`, head ref `fix/pr92-source-graupel-store`, head SHA equal to the frozen commit, base ref `main`.
- Check-only receipt: `/var/tmp/pr92_kg_check_only_20261020.json`, SHA-256 `70efc4bf0977c8a24d4d96d8b3826b9329fb8a5249d75fbd901b728b3f0b7768`, status `CHECK_ONLY_NO_WRITES`.
- KG helper: `/var/tmp/pr92_refresh_kg_source_store_20261020.py`, SHA-256 `f3fcf23ea71a92c8fbabdaaf931cb88c164f870a1b2f1ae1f49e5b94bcbd356b`.
- Finalizer: `/var/tmp/pr92_finalize_evidence_20261020.py`, SHA-256 `f219a2d42cdb78f3643aabb8a96149b215b7944a857420607193fe90f683ccc7`.
- Frozen validation SHA-256: `d864c751ff82b3eb148c1f566ff958d51daca8f43e848740cf4ab6fad90bf891`.
- Frozen integration SHA-256: `9dd668b20b427e77591a643da1e038d666b2357676f1c25a9544b3e84781b82b`.

## Check results

- Source checkout is clean at the frozen commit. I independently verified the current GitHub PR state/head/base through `gh api`.
- The selected graph-source set has 23 paths and matches the helper's frozen `GRAPH_PATHS` allowlist exactly. The 261 changed paths in the plan include PR92 evidence; evidence is commit/hash-bound but excluded from graph extraction.
- The helper's check-only gate passed its prior PR91 receipt and immutable pins, 627-entry maintained-source inventory/hash, protected wiki content, prior automatic/named snapshot membership and hashes, existing graph hashes, exact changed graph-source set, and derived-wiki baseline checks. No write branch runs without `--apply`.
- Candidate/evidence binding is consistent: base `71b8c1d...`, identity `PR92-C18-bounded`, executable SHA `32a324d...`, and both receipt hashes/statuses. Both arms remain `INCOMPLETE`, rc 128, 23 completed steps. The declared ice-only policy is `PASS`; generic exact-source status remains `FAIL` in both arms. Scientific gates remain `OPEN`; physical approval is `FAIL_OPEN`.
- The corrected integration scope now says the declared policy is ice-only and that the independent generic exact-source audit, including rain, remains FAIL; it makes no all-species exact-pass claim. `source_commit: null` is externally bound by the check's clean commit, `git show` evidence-byte equality, validated source hashes, and actual PR head SHA, avoiding an impossible self-referential commit field.

## Recommendation

No preapply blocker found. The bounded structural refresh is safe to apply under this exact checked commit/helper and the existing guarded rollback workflow. This approval covers only the structural Graphify/KG refresh and protected-content preservation; it does not promote runtime or scientific status. C18 remains a 460-second incomplete run with the T24 freezing-base failure and unresolved upstream causality.

## Interpreter/rollback addendum (2026-10-20)

The initial apply was aborted and rolled back after `/usr/bin/python` loaded user-site Graphify 0.5.0 without `rapidfuzz`. The preserved failed output is `kg_failed_python_environment_20261020`; the rollback check-only passed with no writes and the maintained-source digest remained unchanged. No global package changes were made.

Retry environment is now explicitly selected: `/home/korea_keun/.local/share/uv/tools/graphifyy/bin/python3`, Graphify 0.9.53, with `rapidfuzz.distance.JaroWinkler` and `graphify.build.build_merge` imports recorded in `/var/tmp/pr92_kg_environment_20261020.json` (SHA-256 `37f4db26af5973e2eb7540b2140e84f0fbfc9f051da5ed6a037df1de86ef3f5f`). A fresh correct-venv check-only passed at the same frozen source commit, returning `CHECK_ONLY_NO_WRITES`; its receipt SHA-256 is `70efc4bf0977c8a24d4d96d8b3826b9329fb8a5249d75fbd901b728b3f0b7768`. The helper remains unchanged at SHA-256 `f3fcf23ea71a92c8fbabdaaf931cb88c164f870a1b2f1ae1f49e5b94bcbd356b`.

Updated recommendation: the environment blocker is resolved and the guarded structural apply may be retried with this uv Graphify CLI/Python environment. Preserve and inspect the resulting apply receipt and post-apply checks; this review does not certify that apply has already succeeded.
