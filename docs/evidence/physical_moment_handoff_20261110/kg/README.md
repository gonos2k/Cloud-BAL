# Physical moment handoff KG maintenance

`baseline.json` records the read-only inventory before this work. `verify_baseline.py`
compares all dated snapshot files, active graph trios, exact NUL-delimited Git
status and HEADs, wiki mirrors and AGENTS against it. The source worktree's
active graph trio is checked separately. It makes no maintained-root writes.

No source selection is frozen and no update has been applied. After independent
source review and the parent GO, select and hash the actual changed Fortran and
Python paths, then incrementally extract only those paths into isolated copies of
both graph layers. Preserve every unselected manifest entry, retain raw extraction,
check graph integrity and deltas, sync the two separately dated derived reports
and the wiki graph index and append-only audit log. Verify this baseline before
publication. The previous activation-path helper is not included in the clean
base and its Python-only wrapper cannot be used unchanged for this Fortran batch.

Fortran cross-file CALL edges and external import targets may be incomplete;
non-code evidence is hash-only unless separately extracted. Structural freshness
is not validation of execution, physical correctness, conservation, or science.
