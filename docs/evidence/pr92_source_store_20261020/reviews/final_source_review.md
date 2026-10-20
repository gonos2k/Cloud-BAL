# PR92 final source and publication review

Read-only review of the C17 source transform and pre-publication helpers on 2026-10-20. This review does not close the paired runtime gate.

## Pins checked

- C17 generated `module_em.F`: SHA-256 `99be82b97872bd5981facc1e75b167574e1fc10b7c5511130b494c8b989140fb`.
- Evidence finalizer `/var/tmp/pr92_finalize_evidence_20261020.py`: SHA-256 `0f28bf76130841b4ab5466fafd724fef63e09251f87b556461cb0ea310578a81`.
- Selected-source KG helper `/var/tmp/pr92_refresh_kg_source_store_20261020.py`: SHA-256 `f9829489b665d8f64f4738168f966a152764f0ca9afde59b1d62466ab78afd19`.
- C17 executable pin is consistently `1bdec2d56ad55f7e26c5d482eca7b4dae2aead629bb99279eeb8691858bdf645` in the finalizer, KG helper, and current contract.

## Review findings

- Generated C17 differs from the preserved C16 module only in `probe_failed_graupel_pair`: it declares local bulk count/delta outputs and forwards the existing opt-in plus those outputs to the certifier. The certifier initializes optional outputs. The probe does not pass or update committed ledger variables; clearing `failed_pairs(4)` still gates the existing whole-support retry.
- The finalizer checks the C16 canonical snapshot against the unchanged current core and fixture, the C17 focused-suite result and generated-source binding, then the C17 executable and closed runtime receipts. It hashes the C17 module and the archived C15/C16 generation inputs in final validation. The older C16 canonical-snapshot label is accurate for that separately frozen validation, while C17 build/source identity is bound separately.
- The finalizer distinguishes intensive per-event policy bounds from the extensive RK-row ledger sums. It states that the aggregate lacks event carriers and cannot establish those per-event bounds. COMPLETE ledgers require exact cadence; INCOMPLETE ledgers allow only an ordered RK prefix at the next step, tied to `maximum_seen_timestep`.
- The KG helper binds committed evidence bytes to the frozen source commit, checks the actual open PR head/base, validates source and log hashes, requires the C17 identity and paired receipts, and keeps physical approval `FAIL_OPEN`. Its fixed graph-source allowlist excludes evidence artifacts from extraction while retaining their commit/hash binding. Existing snapshot and protected-content checks remain in place.
- The contract and science report keep C14 scientific results separate from C15/C16/C17 engineering runs. They describe C17 as running, preserve the unresolved horizontal QC attribution and AUT/G binding-constraint limits, and leave all physical-approval gates open. `historical_source_aliases.json` preserves C15/C16 historical generator bindings and explicitly treats C17 as a separate current binding.

## Gate status

No source or publication-helper blocker found in this review. C17 paired runtime closure, finalizer execution against the closed receipts, and the later guarded KG check/apply remain pending and are not implied by this review.
