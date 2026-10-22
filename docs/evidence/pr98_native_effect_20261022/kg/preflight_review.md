# PR98 frozen KG preflight review — 2026-10-22

## Decision

**GO for the guarded KG apply, subject to the helper's runtime guards.** This review validates the completed check-only preflight and the independently reviewed restore helper. No apply, restore, graph mutation, or model-data read was performed.

## Frozen source and PR binding

- Preflight: `/var/tmp/pr98_kg_preflight_20261022.json`, SHA-256 `2e61d79df671bd20988e0052b6d2309a7726ef01dba2fb3a13b2b775a6cbf48f`; JSON parses and reports `CHECK_ONLY_NO_WRITES`.
- Frozen source commit, local `HEAD`, and GitHub PR #98 head all match: `4d0baf151cd2669437f0341307c095fa95fb92e5`.
- PR #98 is open and its base is `b39da9bdb3015850b04e636ce4e247ff0df3a524`, matching the preflight base.
- All 78 selected path hashes match current files at the frozen source commit. The selected path set exactly equals the source commit diff against the base. Both non-null base-file hashes match their base versions.
- The extraction allowlist is internally consistent: all 28 `graph_source_paths` are classified `SELECTED`, with no extra selected paths. The other 50 changed paths are explicitly `HASH_ONLY`.

## Baselines and protected inputs

- Preflight binds the previous snapshot `2026-10-22-pr97-c1-budget` and new snapshot `2026-10-22-pr98-native-effect`.
- It records 197 inherited immutable pins; all are reported verified. The two baseline graph pins are recorded as KLAPS50 `69b2e3c156b0658478ee5448def42e041c9d40e9ef2da4ec037ed4bfbb841962` and Cloud-BAL `4190b55df2b4fcd22975f0d915bdce93429e9b61824ee89167c2d94b013c7616`.
- The baseline includes 422 dated snapshot files; every recorded file hash matches the corresponding on-disk file. The five wiki baseline hashes match the live files under the KLAPS50 repository root.
- Maintained-source pre-state is recorded as 627 entries with digest `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`.
- The prior receipt hash is `ff8aad5aaaf42f1d9038eb6d7163eea4d82b59c8b378c87cab8abc91b134442a`. The preflight's protected helper hash equals its expected hash; its nested chain is captured in the preflight.

## Reports and restore guard

- The final source docs and selected evidence hashes are included in the 78-path preflight manifest and match the frozen tree, including the science assessment, native effect/capture reports, review bundle, and validation artifact.
- The independent restore review `/var/tmp/pr98_kg_restore_peer_review_20261022.md` has SHA-256 `21168e440c6365a707772c160d0ef922345a1ce86717d38497515d5fb640d79f`. It records GO, verifies helper SHA `d3e54ce6929b9e8fa0857e2a63a2cf4c595b642f5c09173d6956e1925b9733d2`, test SHA `9246d8d83e3e45480f5f0a429e771473bcd00c6411daa9a36d270804cbd1d1b1`, and reports 8 focused / 46 PR98 tests passed.
- This reviewer independently matched the helper and restore-test hashes in the current frozen tree. The review report also records the prior PR97 receipt review and source binding.

## Scope

This is a pre-apply provenance and preservation check, not evidence that Graphify or the restored wiki has been applied. Apply should use the guarded helper against these exact pins and abort if any input changes. Runtime and scientific claims remain those in the reviewed PR98 evidence; this KG preflight adds no such validation.
