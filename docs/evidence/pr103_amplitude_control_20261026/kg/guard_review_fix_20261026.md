# PR103 KG guard review fixes — 2026-10-26

Addressed four bounded findings in the pre-runtime PR103 KG guard:

- `SOURCE` now resolves from `HERE.parents[3]` to the PR103 Cloud-BAL checkout; `ROOT = SOURCE.parents[2]` still resolves KLAPS50.
- The PR103 source-selection base and approval base both bind merged PR102 `eff97afe9d562d5a2fb39d4b362a7cbf1b96252c`. PR102 source `394b2fb02726978ab8e12080afd80c9171f50762` remains parent-receipt provenance only.
- Test selection is restricted to `tests/test_pr103_*`, exact `tests/pr103_gdtost_oracle_program.f90`, and its exact six-case comparator `tests/compare_pr103_gdtost_oracle.py`, plus the two reviewed PR86 shared files. Neighboring `tests/pr103_unrelated_program.f90` and `tests/compare_pr103_unrelated.py` are rejected by the focused test.
- Immediately after copying graphify-out top-level files into staging, before any Graphify call, the wrapper hashes and compares the exact staged file set against the plan's graph artifact, report, manifest, and metadata baselines.
- The first final-source check-only attempt was blocked before plan generation because PR102's preflight module has no `GUARD` attribute; the pinned PR98 helper has it. The authorized focused fix changed the two PR103 preflight references and one post-source guard reference to `helper.GUARD`, retaining PR102's pinned `GUARD_SHA`. The captured failed output remains at `/var/tmp/pr103_kg_check_only_20261026/stdout.json` (SHA-256 `c54860cd4a7d1a7d678adca5bb04f8a3eca61a123db74c87c52f8ca2a86f84a4`); pre-fix preflight source SHA-256 was `d642a3854c9defe4dc4c1e35edeefbc39364d391c0bcabd0972fbfa3753af2b0`.

Focused validation command: `python -m pytest -q tests/test_pr103_kg_guard.py` — **15 passed in 0.38s**. This covers source-root resolution, exact oracle allowlisting, rejection of unrelated test programs, full staged file inventory hashing, actual pinned PR102/PR98/guard/updater/auditor API attributes, 120-folder lineage reconstruction, raw-date collision mapping, root-GO date binding, and hash-bound manifest evidence.

No check-only retry, Graphify query/update, or apply was run after the focused fix. The one prior check-only attempt was blocked without a plan or writes. No maintained KG or physical source was changed. The staging publisher remains unexecuted until the corrected committed PR103 source and actual runtime/evidence manifest are independently reviewed.


## Subsequent authorized execution

The earlier no-execution statements describe their review checkpoint. After the
API fix was committed as `75052374bae2dcf9b5137e8f0fc840878d865e8e`, the corrected
CHECK_ONLY plan `8c64dffd…295c` passed. A mistyped manifest digest was rejected
before staging ([attempt record](apply_manifest_typo_failed.json)). Root then
constructed the authorized argv directly from the reviewed plan. Both private
corpus updates ran, but final staging validation rejected the CLI reports' absent
custom Graph Freshness section ([invocation](apply_staging_freshness_failed.json)).
No maintained publication occurred. Root and independent review confirmed all
142 live graph/metadata/wiki hashes and all 120 dated folders/472 members
unchanged; the four publication targets remain absent. The failed private output
is preserved.

The staging-only normalizer now appends a missing freshness section, replaces
one, and rejects duplicates. The fresh private output is
`/var/tmp/pr103_kg_apply_v2_20261026`. The focused guard suite passes 18 cases;
the broader current Python suite passes 150 cases. The
[freshness review](freshness_fix_review.md) approves source/tests only; a new
commit-bound CHECK_ONLY plan and review are required before another APPLY.
