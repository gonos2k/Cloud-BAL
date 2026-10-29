# CP02 background hash contract review

**Decision: GO. No blocking findings.**

The analyzer now requires the selected background CSV’s SHA-256 to equal the archived capture’s `points_csv_sha256` before the inner or radar analysis proceeds. It reports the same verified digest in the summary. The check fails closed and does not silently replace a mismatching selected path with the canonical path.

Validation used the tracked radar capture and tracked prior outer capture. A byte-identical background CSV copied to another path succeeds and writes both outputs. Changing one HYDRO `background_rain` cell (`shadow_i=163`, `shadow_j=73`, `z_index=3`) by `0.001` fails with the expected error and writes neither output. Re-running that negative case against the analyzer source at base commit `28671ac5929c0f28aa667db27e769bcbefbaf4ec` reproduced the defect: the old CLI returned success, reported `SCOPED_PASS`, and wrote both files.

The focused suite passed: `12 passed in 21.29s`. `git diff --check` passed. Only the analyzer and its test file are modified in the review worktree.

## Hashes

- Analyzer: `6d61469b7ba89497200b840541552e44b3abc20f733357a4ca45ff5b7233c0b2`
- Tests: `b794607e4bf4dd477c9b5aff47dc658e37834712fc5247c3023c8cb66715c9fb`
- Tracked radar capture: `b41181187c3a3eacb1edd567cedfb029cd9bdc2cde1c247d9a556167eb01b4bf`
- Tracked background CSV: `bc765f17fef5b02c4b75d58bd503114259f779cfeffe51ed9e82c6672d37f0ca`
- Tracked prior outer capture: `a2b24dce7a7a85a838cb44e4465acdd442cf126e766241d4b786a45ec4f2e6fe`

Scope is limited to this Python analyzer contract. This review makes no model execution or scientific validation claim.
