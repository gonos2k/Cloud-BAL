# PR103 KG guard review fixes — 2026-10-26

Addressed four bounded findings in the pre-runtime PR103 KG guard:

- `SOURCE` now resolves from `HERE.parents[3]` to the PR103 Cloud-BAL checkout; `ROOT = SOURCE.parents[2]` still resolves KLAPS50.
- The PR103 source-selection base and approval base both bind merged PR102 `eff97afe9d562d5a2fb39d4b362a7cbf1b96252c`. PR102 source `394b2fb02726978ab8e12080afd80c9171f50762` remains parent-receipt provenance only.
- Test selection is restricted to `tests/test_pr103_*`, exact `tests/pr103_gdtost_oracle_program.f90`, and its exact six-case comparator `tests/compare_pr103_gdtost_oracle.py`, plus the two reviewed PR86 shared files. Neighboring `tests/pr103_unrelated_program.f90` and `tests/compare_pr103_unrelated.py` are rejected by the focused test.
- Immediately after copying graphify-out top-level files into staging, before any Graphify call, the wrapper hashes and compares the exact staged file set against the plan's graph artifact, report, manifest, and metadata baselines.

Focused validation command: `python -m pytest -q tests/test_pr103_kg_guard.py` — **14 passed in 0.54s**. This covers source-root resolution, exact oracle allowlisting, rejection of unrelated test programs, full staged file inventory hashing, 120-folder lineage reconstruction, raw-date collision mapping, root-GO date binding, and hash-bound manifest evidence.

No PR103 preflight, Graphify query/update, check-only, or apply was run. No maintained KG or physical source was changed. The staging publisher remains unexecuted until the committed PR103 source and actual runtime/evidence manifest are available and reviewed.
