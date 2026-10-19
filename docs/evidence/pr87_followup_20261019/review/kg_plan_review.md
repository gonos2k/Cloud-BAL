# PR87 Graphify/KG refresh plan review

**Review target:** `/var/tmp/pr87_refresh_kg_followup_20261019.py`  
**Review mode:** static, read-only; the helper was not run and no graph/wiki files were changed.

## Decision

**Not ready to approve `--apply` yet.** The transaction and preservation design is broadly sound, but selected-source scope needs an explicit guard. The current checkpoint also records an unclean source worktree and the final integration manifest is not present yet, so the helper should refuse both check-only and apply until a clean committed candidate is ready.

## Findings

1. **Blocker — changed-path selection is too broad.** `make_plan()` selects every added or modified path in `git diff BASE..commit`; it rejects only the exact `config/cp01_private_host_profile.json` name. Any other newly committed private input, credential/config, raw array, or sensitive evidence file could be copied into the overlays and passed to Graphify if its suffix has an extractor. Hash-binding does not make parsing it safe. Add a positive allowlist for the intended source, test, and review/evidence paths (or deny sensitive/private/data directories and extensions comprehensively), and fail closed on everything else. Keep non-extractable hash-only artifacts restricted to explicitly named receipt/manifest files.

2. **Expected preflight blocker — candidate is not frozen yet.** `make_plan()` requires the requested SHA to equal `HEAD` and the source worktree to have empty `git status --porcelain`. The progress checkpoint reports in-progress uncommitted files. Do not run the helper until the final candidate is committed and clean; the existing check is correctly fail-closed.

3. **Expected receipt prerequisite — integration manifest is absent at review time.** `load_integration_receipt()` requires the manifest to be an added/modified selected path in the frozen commit, hash-matched against both the worktree and `git show`, and based on `d22a3887…`. This gives an external source-commit binding without a self-referential commit field in the manifest. Its required status objects are only checked for non-emptiness, however; add schema/value checks for the runtime and validation fields consumed later, especially the arm records used for the wiki log, so malformed records cannot silently be rendered as missing/default statuses.

4. **Preservation checks reviewed.** The plan pins both separate 2026-10-16 graph baselines and their dated/live artifacts, the preceding receipt and 164 prior immutable pins; snapshots the maintained active source inventory before/after; checks protected wiki content and private-profile graph nodes/links; writes only the dated 2026-10-19 graph snapshots plus derived reports, Graph snapshot index section, and append-only log; and has backups/rollback for declared graph/report/manifest/wiki outputs. Corpus counts are recorded separately, and the report text correctly limits extraction claims to selected AST/Markdown headings, notes partial cross-file Fortran CALL extraction, and distinguishes graph freshness from scientific validation.

## Required before apply

- Add the selected-path allowlist and narrow non-extractable hash-only artifacts.
- Validate the final integration manifest's consumed field shapes and required status values while keeping `physical_approval: FAIL_OPEN`.
- Freeze/commit the candidate, confirm the manifest is included, then run the pinned check-only preflight against that exact clean commit. Re-review its selected paths and manifest binding before apply.

No Graphify/KG operation was applied. Graphify and kg-update guidance was consulted; the planned AST-only incremental extraction and derived-only wiki sync align with those instructions, subject to the scope guard above.

## Follow-up static review

The helper was reviewed again after guard changes; it was still not run.

- **Path-scope finding addressed for now:** `APPROVED_SELECTED_PATHS=frozenset()` and the per-path membership check fail closed, so no changed source can enter overlays until a reviewed exact list is populated. Final approval remains pending review of that frozen list against the exact candidate diff; do not replace the empty set with a broad inferred list.
- **Manifest-shape finding mostly addressed:** it now requires explicit `latest_actual_host.status`, exactly `OFF` and `COUPLED` arm objects, typed per-arm status/return code/completed step, validation status, and nonempty string scientific-gate values, while keeping `physical_approval` at `FAIL_OPEN`. Tighten the arm and validation status checks to reject empty/whitespace-only strings, as the runtime status already does.
- **Final execution remains pending:** the reviewed path list, final manifest, clean frozen HEAD, and successful read-only check-only plan are all prerequisites. This follow-up does not authorize `--apply`.
