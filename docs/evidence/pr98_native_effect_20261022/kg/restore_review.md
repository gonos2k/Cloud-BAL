# PR98 KG restore-guard final peer review — 2026-10-22

## Decision

**GO for the restore helper and focused KG evidence guard.** The symlink gaps from the first review are fixed: both restore functions now invoke the inherited destination guard before hashing or taking the unchanged-file fast path. The rollback helper also guards its backup source and destination itself, then uses the inherited checked-copy path when restoration is needed. Regression cases exercise byte-identical symlinks in both restore paths.

## Reviewed artifacts

- `docs/evidence/pr98_native_effect_20261022/kg/update_kg.py`
  SHA-256: `d3e54ce6929b9e8fa0857e2a63a2cf4c595b642f5c09173d6956e1925b9733d2`
- `tests/test_pr98_kg_restore.py`
  SHA-256: `9246d8d83e3e45480f5f0a429e771473bcd00c6411daa9a36d270804cbd1d1b1`
- Inherited guard source: `/var/tmp/pr91_refresh_kg_host_store_20261020.py`; the tested apply/restore paths call its symlink- and path-aware `guard_destination` and `copy_checked` functions.

## Review findings and validation

- Changed-only restore preserves the mtime of unchanged regular snapshot members, checks the hash-bound backup before restore, restores changed regular files from that backup, and verifies the result.
- Strict snapshot membership checks reject unknown additions while preserving them for manual review. Restore errors are aggregated rather than silently treated as success.
- Rollback verifies the backup SHA and skips rewriting an already matching regular destination. Both source and destination are guarded before those checks; changed destinations use `guard.copy_checked`.
- Added tests verify rejection of a symlink snapshot member even when its target bytes match the backup, and rejection of a symlink rollback destination. Existing tests cover unchanged-file mtime, changed-file restore, bad backup refusal, and preservation/rejection of unknown members.
- Independently ran `pytest -q tests/test_pr98_kg_restore.py`: **8 passed**.
- Independently ran `pytest -q tests/test_pr98_*`: **46 passed**.

No graph update/apply was run. No source was edited during this review. The reviewer checked the final helper/test hashes above in the shared worktree.
