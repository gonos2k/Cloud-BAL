# PR103 KG guard review fixes — 2026-10-26

Addressed four bounded findings in the pre-runtime PR103 KG guard:

- `SOURCE` now resolves from `HERE.parents[3]` to the PR103 Cloud-BAL checkout; `ROOT = SOURCE.parents[2]` still resolves KLAPS50.
- The PR103 source-selection base and approval base both bind merged PR102 `eff97afe9d562d5a2fb39d4b362a7cbf1b96252c`. PR102 source `394b2fb02726978ab8e12080afd80c9171f50762` remains parent-receipt provenance only.
- Test selection is restricted to `tests/test_pr103_*`, exact `tests/pr103_gdtost_oracle_program.f90`, and its exact six-case comparator `tests/compare_pr103_gdtost_oracle.py`, plus the two reviewed PR86 shared files. Neighboring `tests/pr103_unrelated_program.f90` and `tests/compare_pr103_unrelated.py` are rejected by the focused test.
- Immediately after copying graphify-out top-level files into staging, before any Graphify call, the wrapper hashes and compares the exact staged file set against the plan's graph artifact, report, manifest, and metadata baselines.
- The first final-source check-only attempt was blocked before plan generation because PR102's preflight module has no `GUARD` attribute; the pinned PR98 helper has it. The authorized focused fix changed the two PR103 preflight references and one post-source guard reference to `helper.GUARD`, retaining PR102's pinned `GUARD_SHA`. The captured failed output remains at `/var/tmp/pr103_kg_check_only_20261026/stdout.json` (SHA-256 `c54860cd4a7d1a7d678adca5bb04f8a3eca61a123db74c87c52f8ca2a86f84a4`); pre-fix preflight source SHA-256 was `d642a3854c9defe4dc4c1e35edeefbc39364d391c0bcabd0972fbfa3753af2b0`.

Focused validation command: `python -m pytest -q tests/test_pr103_kg_guard.py` — **15 passed in 0.38s**. This covers source-root resolution, exact oracle allowlisting, rejection of unrelated test programs, full staged file inventory hashing, actual pinned PR102/PR98/guard/updater/auditor API attributes, 120-folder lineage reconstruction, raw-date collision mapping, root-GO date binding, and hash-bound manifest evidence.

No check-only retry, Graphify query/update, or apply was run after the focused fix. The one prior check-only attempt was blocked without a plan or writes. No maintained KG or physical source was changed. The staging publisher remains unexecuted until the corrected committed PR103 source and actual runtime/evidence manifest are independently reviewed.
