# PR90 final pre-publication review

Read-only review of the candidate source diff, focused validation, integration manifest, C7 180/600 receipts and current PR90/C7 documentation. No maintained files were written and no broad tests were repeated. The 600-second run is closed and remains INCOMPLETE; its scientific/runtime status is not treated as a code acceptance gate.

## Validation and source bindings

- Integration manifest SHA-256 `f4eabb1c3a4b7ee891de4efb0c81e3c83aee22a77b06ce7d77ce314ad3131488` matches the requested artifact. It binds the C7 overlay build receipt SHA-256 `7a58ac2ae90eca9ffe0500515282b537e11db25ab9de8175856609bf812bba31`, whose executable SHA-256 is `5f5599e38759a9e2be27a9e7e0977370592c92cab328062d07eb359bddd19572`.
- Focused validation receipt SHA-256 `44b67fec1c1570597582bf1d97fe301fcd901ae3ae0d6e20c3f61ab1157fa841` records 95 tests, zero failures/errors/skips, `physical_approval: false`, and the pinned Intel profile SHA-256 `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`. All 21 source hashes match current candidate files. The JUnit/log artifacts record 95 passing tests; the standalone original transport test and log hashes match, with Intel O0 and O2 both recorded PASS.
- The changed production/helper code and its test/metadata changes are represented in the focused receipt’s source pins. The review did not find an unpinned changed source file or a source-to-receipt hash mismatch.

## Runtime receipt checks

Using the updated guarded refresher’s closed-window and receipt validators directly against the current integration data, all four arm receipts pass identity, executable, expected schedule, actual timestamp-prefix, timestep-count, and final-step consistency checks.

| Window | OFF | COUPLED |
|---|---|---|
| 180 s | COMPLETE, rc 0, 9/9, receipt `3dc57736…` | COMPLETE, rc 0, 9/9, receipt `72fe00a…` |
| 600 s | INCOMPLETE, rc 1, 9/30, receipt `d1802d60…` | INCOMPLETE, rc 1, 9/30, receipt `4142a65a…` |

Both 600-second receipts bind the same C7 executable and unchanged inputs/build. Actual timestamps form the nine-step prefix through 180 seconds; no tenth POST_KDM6 is claimed. The C7/600 archive verifies with its own SHA256SUMS, including receipt/preflight copies, prefix/tail audit and T10 failure classification. The 180-prefix comparison is byte-identical for 7,537,409,380 decompressed trace bytes in each arm.

The T10 evidence confirms six `FULL` rejections per arm at RK3 with the same pair indices and coordinates. The revised classification leaves each exact failing subpredicate and earlier producer **OPEN**, consistent with the absence of exact REAL64 words/failure-stage capture. Main PR90 and C7 docs accurately describe the run as incomplete and separate inferred boundary explanations from confirmed facts. The updated C7 README now links the closed C7/600 archive; current root and duration-level checksum manifests verify.

## Scientific and documentation scope

The 180-second PR90/C7 improvements are described as selected-object/partial-host and scoped diagnostics. Physical approval remains `FAIL_OPEN`. The documents preserve generic ice-gate FAIL while separately reporting the inactive-source split; keep the 27-column history support descriptive and distinct from the unmapped 162-pressure-cell support; and avoid claims of observation fit, physical continuity, global closure, complete number budget, or 600-second completion. Historical pre-run review notes are explicitly identified as contemporaneous and superseded by the closed receipts.

## Remaining publication gate

I found no concrete source, validation, manifest, receipt, or current-documentation blocker to the scoped 180-second code improvement. The final source commit, exact selected-path allowlist, actual PR URL, and frozen final receipt hashes still need the planned freeze/check-only step before any KG refresh; the external refresher remains fail-closed until those literals are frozen. Scientific approval remains open by design, and the 600-second candidate window remains INCOMPLETE.

## C6 archive metadata follow-up

A final one-byte EOF normalization in the C6 failure excerpt was verified. The archived excerpt is 1,598 bytes with SHA-256 `eea35ebd513559bc2d8b6125b1e13a6b9030ba22e20974d80969a1f0fe7591b7`; its diagnostic lines remain present. The C6 manifest pins that exact size/hash and has SHA-256 `a04153886d70c656f91d4e0dda8afd4198711c14fd083ce82c76d56f20c54186`. The archive-verification note and main report reference the updated manifest hash. This is metadata-only; C7 integration and the 21 focused source pins remain unchanged.

## Focused-log publication follow-up

The two newly staged evidence logs match their receipt and external source bytes: `focused_tests.log` SHA-256 `cec8e3b53d79799f1f12a83adcf85e24a722f311135e17154d76c06e07cea047` matches both the focused-validation receipt and `/var/tmp/pr90_final_focused_tests_20261019.log`; `standalone_joint_transport.log` SHA-256 `cbd3bdfc3f4a3673f5cc5b4945c5b85783737e46ec9a2c2f3014a27c08d5303b` matches the receipt, and embeds both fresh-scratch Intel outputs byte-for-byte (O0/O2 each report return code 0 and PASS). The recorded compiler remarks and Fortran runtime array-temporary warnings are warnings; no failed test or unexpected failure/traceback appears. Raw log bytes were preserved, including trailing whitespace. Staged diff check passes when excluding only the raw standalone log; the focused log itself has no trailing-whitespace lines. This closes the ignored-file publication gap and adds no new validation claim.
