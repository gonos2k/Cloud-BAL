# PR102 final runtime provenance review

Read-only review recorded 2026-10-26. The candidate run is closed. No live
model fields were read, no tests or model runs were performed, and no code or
frozen evidence was modified. The wind-structure status document was updated
separately to record the closed run and prefix bridge.

## Runtime identity

The STRUCTURED receipt is `COMPLETE`, return code 0, and records the exact 32
timestamps from 2026-08-16 13:00:20 through 13:10:40, 32 completed
POST_KDM6 steps, no fatal lines or processing errors, and no changed staged or
original inputs. Receipt SHA-256 is
`313295e9cbf9e30a12a437c501bf3db2cf25c0e6762ec5d51c31d54ba311d4d6`.

Its input hash is the one generated candidate
`b26e5f3d712732c3459d59b82a4b44fe53eebd9be1fd450d13640d2d8398343f`; the run
receipt binds proposal `451e4e9110d3b921507e311be56328ad05e13ee20e1fedd2d9c60ce8ef94eeb8`,
original P, HYDRO and COUPLED references, boundary, policy, composition, and
the U/V-only contract. The executable actually staged and executed is
`387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a`, matching
the four closed C2 controls; boundary and 640-second namelist hashes also
match those controls. Runner, candidate build, and candidate input identities
are reported unchanged by the closed receipt. The receipt's generic
`run_identity` and build `identity` strings retain PR87 wording; the exact
executed executable hash is the authoritative C2 identity here.

The N640-to-N_BASELINE20 prefix bridge is `PASS` with these component statuses
also `PASS`: T0 history fields, the first 20-second POST_KDM6 trace, and T1
post-call fields. Both arms bind the same candidate input, executable, and
boundary; the bridge records the intended run-duration/namelist difference.
Bridge SHA-256 is
`e3ef62b6f9a2792434d3471005ec59b5f6a7441f377946500fd91cb64c598194`. The
published five-arm history readback is `DESCRIPTIVE_ONLY`, uses all 11 times
from 0 through 600 seconds on the 613-cell support and fixed 196-column by
39-level buffer, and is pinned to the same closed candidate receipt. Its JSON,
PNG, and PDF hashes match the execution and publication manifests. These
results do not establish observation skill or physical approval; the report
records `NOT_EVALUATED` and `FAIL_OPEN` respectively. A separate generic
`FAIL` status is outside this runtime identity review and is not reclassified.

The producer, solver, and policy remain at the proposal-pinned hashes:
producer `f044c57605942504a0c8ece22b915e8bd64bc2ddacb46a9cecd6920081f15b85`,
solver `0ad9b38485b5d25f6fd70b3150688449e994665ffc6e16c5feb371c4ff3a35f5`,
policy `9ab0d468b9d46cce00fb9cc66162fa995beeda714f93cedba8c65d6e1891200d`.
No policy or candidate drift was found. This review does not state an outcome
for the separate v4 source audit.

## Documentation still to reconcile

The wind-structure document now records the completed 32/640 run, prefix
bridge, and available descriptive five-arm history result. Two other docs
still contain pre-closure statements and should be reconciled before
publication:

- `docs/PR102_EXECUTION_20261025.md` says no N20 run launched and says neither
  N20 nor the 640-second run has started.
- `docs/PR102_RESPONSE_ANALYSIS_20261025.md` says the 640-second reader remains
  uninvoked until the receipt closes.

The detailed final 640-second response/source-audit interpretation remains
separate from this provenance review.

## V4 source-audit execution addendum

The closed source-audit execution record has since been reviewed:
`docs/evidence/pr102_execution_20261025/source_policy_audit_v4_execution.json`,
SHA-256
`8a3ccdfa6a75f1f1c5fedb256a35cc0981c6cb6251c6e6feda980957d21a7235`. It is
`RECORDED`, return code 0, its source pins match before and after, and it binds
the same closed STRUCTURED receipt, execution preflight, candidate input, and
executed C2 executable listed above. The output report is
`source_policy_audit_v4.json`, SHA-256
`25222e49b6767091eeb29dff9a2144ae8354f192e0ea93be4149a1e44daf1e4a`.

The three scoped results are distinct: generic QNB pair/conversion audit
`FAIL` with 173 records; exact source endpoint audit `PASS` with no failures;
and active ice policy split `PASS`. The generic QNB failure remains visible
and is not waived or relabeled by the two passing checks. These execution and
scope facts provide no overall scientific pass, observation-skill result, or
physical approval. The integration/provenance review remains GO within its
stated scope; the response and source-audit interpretation remain separate.

## Staged whitespace exception addendum

The staged validation record
`docs/evidence/pr102_execution_20261025/validation/staged_whitespace_check.json`
(SHA-256
`d015d9d3308d20f57e50787b11376456b297a8406988beea3054e3c07a659b11`)
reports a full staged `git diff --cached --check` return code of 2 with 804
warnings. They are confined to the nine listed, hash-bound immutable Fortran
source/patch snapshots in the three `c2_capture_source_plan` versions. I
rechecked all nine current file hashes against the recorded values; all match.
The recorded authored-diff check excludes exactly those nine paths and returns
0. This supports an authored-diff whitespace check only; the entire staged
diff is not whitespace-clean. No immutable snapshot was changed or cleaned up.
