# PR96 C1 closed-audit queue publication review

Status: **DRAFT-GO.** The publication HEAD guard blocker below is resolved. The native three-arm runs remain receipt-pending; this review makes no runtime-completion or audit-pass claim.

## Reviewed scope

- Read the public `closed_audit_queue.py`, `launch_snapshot.json`, runner `prepare()` / `run()` schema, and the existing frozen audit readers. Did not inspect any live executable or model history.
- The published queue source hash is `eb0c1b7d23653c5d5e4e079a4859bb60f53cb1ce00202bb40f3c7554988383fc`, matching the snapshot's waiter pin and `/var/tmp/pr96_closed_audit_queue_20261021.py`.
- Snapshot preflight SHA-256 values match the three actual `preflight.json` files. Each has the runner's expected 600-second, 20-second, 30-step fields and matches the snapshot's C1 build receipt, executable, compiler-profile, WRF input, boundary, and namelist identities. HYDRO's source-bound candidate-input binding is present and has the expected boundary/input identities. Runner schema confirms it writes this preflight before staging or execution, and binds candidate build/input identities into the final receipt.
- The seven frozen audit reader pins verify at checkout HEAD `50d11d631a59d461c37da2e8bc9666c6bcc9c380`. Queue source and build receipt hashes are also pinned during a run.
- The queue waits for all three terminal (`COMPLETE` or `INCOMPLETE`) receipts before opening preflights, staged executables, or invoking per-arm audits. Result status remains `REVIEW_REQUIRED`, `review_required: true`, and `physical_approval: FAIL_OPEN`. Generic Q/N/B, exact source endpoint, and active-ice 8-ULP statuses remain separate in each saved audit; incomplete steps are not promoted to complete. The launch snapshot remains explicitly pending.

## Blocker and minimal fix

The initial review found that `run_queue()` recorded both startup and result HEADs, and its `head_scope` allowed publication advances, but the final guard still rejected that advance. The root removed that one equality clause. Re-review confirms:

- The startup HEAD and end HEAD remain recorded as provenance; there is no HEAD equality rejection.
- The seven reader-pin equality check remains, along with the queue-source, build-receipt, executable, and compiler-profile hash checks.
- The published queue source, private waiter source, and refreshed launch-snapshot waiter pin all have SHA-256 `317ff289a22acce9ddbfb27dce432e507de2bf91c04357c4c033ef2aada1bbaf`.
- Snapshot still reports all three arms as `NATIVE_LAUNCHED_CLOSED_RECEIPT_PENDING` with `closed_receipt_observed: false`. The queue change and metadata-waiter restart do not change the forecast state or establish completion.

The HEAD-change blocker is resolved. Draft publication is allowed at the stated pending scope; any runtime completion or audit result remains pending until closed receipts are processed by the queue.

The source-level audit confirms generic, exact-source, and active-ice separation. There is no separate queue-level “procedural PASS” field: the queue stays review-required, while its per-arm artifacts are the frozen checks. Keep publication wording at that scope and do not describe these pending native runs as complete or passing.
