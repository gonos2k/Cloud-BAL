# PR98 C1 boundary-auditor binding review — 2026-10-22

## Decision

**GO for the reviewed auditor code and focused tests.** The duration change matches the actual frozen runner receipt schema, and the replacement checks strengthen the run binding. This was a source/test and metadata review; no auditor run or model binary/history read was performed.

## Reviewed hashes and test

- `tools/pr98_boundary_audit.py`: SHA-256 `55c11ec55ba727121e256e50fdb1c64feb1fa0d074ede4e82505cc0ddd10d4c4`.
- `tests/test_pr98_boundary_audit.py`: SHA-256 `25a5f3ed47383b0f22e19a623b96308bc7376eb3ce47c21b0e966785608ba7ed`.
- Independently ran `python3 -m pytest -q tests/test_pr98_boundary_audit.py`: **11 passed**.

## Binding findings

- The three actual 640-second run receipts have no `duration_seconds` field. Their preflights each state the correct arm, 640 seconds, 20-second timestep, and 32 planned timesteps.
- Each receipt carries 32 `expected_model_timestamps`. The schedule equals the 32 timestamps derived at 20-second intervals from the pinned C1 baseline's first planned time minus one timestep. All three arms match.
- For each arm, `candidate_namelist_sha256` matches across preflight, closed receipt, and the actual staged `run/namelist.input` bytes.
- Preflight identity is reported transparently with its observed path and SHA. The result states that the frozen receipt has no preflight digest and that preflight identity fields are cross-checked; it does not claim the preflight file hash is receipt-bound.
- The diff removes only the unsupported `receipt.duration_seconds` check and redundant old preflight arm/duration check. It replaces these with the validated preflight schedule, receipt timestamp schedule, and staged namelist hash checks. Frozen executable, build, C1 input and source-namelist equality, source-receipt hash binding, input-unchanged flags, and candidate identity checks remain.
- The completion predicate remains strict: COMPLETE, return code 0, no fatal lines or processing errors, all 32 unique steps, and final step 32. The current three receipts are INCOMPLETE, return code 1, final step 31; the new checks do not make these completed runs or allow a passing procedural result.

No blocker found in the requested source/test changes.
