# WPS OFF readback Graphify maintenance

This package records the scoped structural graph refresh for PR #117. Graphify 0.9.53 extracted the two frozen Python paths listed in `graph_manifest.json`, merged those nodes and edges into the existing KLAPS50 and Cloud-BAL graphs, and regenerated community assignments and graph reports.

The final graph artifacts, raw Graphify backups, named dated snapshots, and derived wiki files were copied from isolated reviewed stages and read back by SHA-256. All 172 earlier dated snapshot folders and their member hashes remained unchanged.

Only the two Python paths were extracted. The README, task report, and three JSON evidence files were hash-bound without semantic extraction. Fortran cross-file CALL extraction is partial. Graph freshness does not establish runtime or scientific validation.

A discarded CLI run on a two-file skeleton produced only a 15-node partial graph; it was not published. The accepted outputs came from the existing-graph selected-source merge and cluster-only path recorded in the receipt.
