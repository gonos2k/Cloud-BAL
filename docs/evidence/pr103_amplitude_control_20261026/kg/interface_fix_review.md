# PR103 KG helper API compatibility review — 2026-10-26

## Scope

Read-only peer review of the PR103 KG preflight/apply delta and the actual
pinned-helper API regression. No Graphify command, KG preflight/check-only, or
apply operation was run during this review.

## Finding and fix

The preceding check-only attempt stopped before plan generation because the
PR102 preflight module exposes `GUARD_SHA` but not `GUARD`; the pinned PR98
helper returned by `_load_pinned_helper()` exposes both. The three changed PR103
references now load the guard using `helper.GUARD` while retaining the
independently pinned `pr102.GUARD_SHA`: two references in `preflight_kg.py` and
one in `apply_kg.py`.

The regression `test_guard_api_is_read_from_the_actual_pinned_helper` loads the
actual PR102 preflight and its actual pinned PR98 helper. It confirms the
attribute split, matching guard hash, guard path, prior protected-content
helper, and pinned PR59 updater / PR99 auditor interfaces and hashes. It does
not substitute mocks for these APIs. The recorded focused suite reports 15
passing tests; the focused source note records AST, private compile, and scoped
diff checks. No post-fix check-only retry was performed.

Reviewed file hashes:

- `preflight_kg.py`: `4b6a05b9af5590accc80f6f5239ad6589cbfc67fb8ed52d148c57025476ba165`
- `apply_kg.py`: `c0c8231bf318d8dc2fc8c39bb62b3aa6cbdeb34903727ef5d7c294491beb2ab3`
- `test_pr103_kg_guard.py`: `35687e4fbfd1e3d6762c71a32a08743ead4b477fa54544a381eccb3ce67d1fed`
- `guard_review_fix_20261026.md`: `c13adee503a8bea83b09dd2e0156114863ac2b4a791b172bbe7724514c4866c5`

## Outcome and limits

No blocker remains in the three-reference API fix or its actual pinned-API
regression. This is a source and test review only. The staging publisher has
not run; a corrected commit still needs the separately reviewed CHECK_ONLY
plan before any APPLY. Maintained graphs and derived wiki files were not
changed. Physical approval remains `FAIL_OPEN`; observation skill remains
`NOT_EVALUATED`.
