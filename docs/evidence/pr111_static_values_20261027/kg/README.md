# PR111 Graphify / KG maintenance

The independently verified publication updates only the two maintained graph
corpora and five derived wiki files. Source commit: `3c0deb764a5b6624ba185c1da5d431867d1f95b2`.

- KLAPS50: 41,241 nodes / 85,679 edges / 3,366 communities (+9 nodes, +17 edges).
- Cloud-BAL: 15,413 nodes / 27,222 edges / 1,372 communities (+9 nodes, +18 edges).
- Six changed code/test paths were extracted (51 nodes / 154 edges); five documentation/evidence paths were hash-bound only.
- All 144 prior snapshots remain; four separately dated snapshots were added.
- Independent readback confirms 21 targets, maintained source/pins, and non-target dirty-state preservation.

Fortran cross-file CALL extraction is partial. Community labels may change with
hub-based names; no LLM label refresh was run. Graph freshness is not runtime or
scientific validation. Native test results are in the parent validation.json;
T39, the one-hour forecast and 14 UTC skill remain open as documented there.

The initial staging receipt is preserved in `/var/tmp/pr111_kg_stage_20261027_v1`.
The final receipt includes the requested native-evidence and open-item wiki audit
lines; only that final version was applied. The archived stage finalizer matches
those lines. Publication receipt is a root envelope over the successful apply and
the independent review readback, rather than a new model or graph extraction run.
