# PR98 HYDRO input receipt relocation review

**Result: GO**

Reviewed `tools/pr98_boundary_audit.py` at SHA256 `77f911b4e4b552cc92c47885c3f7c875cad7028636fb06d9b8ec463e79282932` and `tests/test_pr98_boundary_audit.py` at SHA256 `594fdc7b33ba45b72f8cc4a570b18414b7d05bd550887cb743cf44d403f5e423`.

The HYDRO exception is narrowly implemented. The run and baseline candidate input bindings must each exactly match their own closed receipt and preflight. Their declared receipt hashes must match. Both named receipt files must exist and hash to that common pin. The comparator then requires every binding metadata field to match, excluding only the top-level `receipt_path`; nested metadata remains fully compared. This supports the observed relocation of an otherwise identical archived receipt without weakening the source, executable, namelist, or runtime identity gates.

Focused validation: `python3 -m pytest -q tests/test_pr98_boundary_audit.py` passed, 12 tests. Regressions cover successful same-hash relocation, changed nested metadata, receipt/preflight binding mismatch, and changed receipt bytes. No audit or model data were read or rerun as part of this review.

No blocker found.
