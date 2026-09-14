# Audit remediation — 2026-09-09

Scoped remediation validation: **PASS**. Whole CP01 remains `IN_PROGRESS / NOT_RUN`.

The common NetCDF reader now handles nonfinite field payloads without evaluating their magnitude first. It preserves invalid coverage, replaces nonfinite arithmetic operands with zero, then applies the existing raw-missing threshold. Both 2-D and 3-D readers use this ordering; finite input behavior is unchanged.

The shared reader's surface-vapor contract is clarified: absent MR remains invalid optional coverage. Consumers that require a vapor anchor enforce that requirement. The direct-reader regression now verifies success with no fabricated validity or provenance when MR is absent. It does not weaken the LAPSPREP QV input gate.

Targeted tests have passed 12 controlled nonfinite rejections (LWC and surface pressure, NaN/+Inf/-Inf, Intel O0/O2), two optional-MR cases, and 14 direct analysis-reference rejection cases. The full I/O suite completed with exit 0; O0/O2 SHADOW diagnostics are byte-identical. The named time suite additionally passed inclusive +/-0.5-second and exclusive +/-0.5001-second analysis/cycle checks, plus the forecast future boundary. The numerical boundary suite passed before/center/after cycle rejection with state unchanged. Both supplemental suites ran O0/O2 and passed source/input identity checks.

Evidence workspace: [audit_remediation_wmpwkuwf](../scratch/audit_remediation_wmpwkuwf/REMEDIATION.md).

The historical 63-character environment digest is corrected by an additive [supplement](../scratch/time_contract_receipt_correction.lmkJfw/correction.json), which binds the unchanged original receipt, actual dependency and pinned profile. No historical receipt was rewritten, and the supplement makes no runtime reexecution claim.

The [MR contract review](../scratch/mr_contract_followup.20260909T0915Z/REPORT.md) records the caller-specific requirements. The original [Red / Green report](../scratch/red_green_audit_9vjv_9kq/REPORT.md) remains the audit of the earlier source revision.

Final [execution receipt](../scratch/audit_remediation_wmpwkuwf/receipt.json) binds 56 captured suite sources, retained O0/O2 analysis binaries, logs, the pinned toolchain, supplemental runs and the historical metadata correction. Reader SHA-256: `e665a39b583d037462450b3858092aaae6e1effd97bd5464d648bbf8d74c17aa`.

The [independent implementation review](../scratch/remediation_review_9vjv_9kq/REPORT.md) confirms invalid masks remain authoritative. It identifies a separate, unverified hardening concern for finite values near the REAL32 maximum during downstream scaling. This change tests nonfinite values and does not claim to resolve every malformed finite payload. Numerical boundary checks do not grant physical or native authority.

## Finite extreme follow-up

The earlier finite-value concern has now been reproduced and repaired. Positive and negative REAL32 maximum in inactive LT1 height cells caused O0/O2 floating-overflow aborts. `assign_reversed_core` now evaluates scaling only within `WHERE (usable)`, preserving active coverage rejection and raw/retained-omega handling.

All eight new active/inactive cases passed, and the full pinned Intel I/O suite completed with exit 0. Current O0/O2 diagnostic bytes match both each other and the previous validated run. See the [follow-up report](../scratch/finite_payload_fix_j2i4kbu9/REPORT.md) and [execution receipt](../scratch/finite_payload_fix_j2i4kbu9/receipt.json). This closes the specific finite-extreme conversion concern, not whole CP01.

The separate [tool-use review](TOOL_USAGE_REVIEW_20260909.md) records two subagent cleanup commands rejected by a shell safety guard. No inspected response returned `cyber_policy`; the cause of the repeated product display notice remains unknown.
