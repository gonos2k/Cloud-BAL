# PR92 Graphify/KG maintenance bundle

This compact package binds the reviewed PR92 source commit and actual pull request to separate KLAPS50 and Cloud-BAL snapshots dated `2026-10-20-source-store`. It includes the selected-source receipt, derived reports, only the changed wiki section and appended log bytes, and independent preservation reviews. No full graphs or private host-profile contents are included.

The source integration manifest keeps `source_commit: null` to avoid self-reference. The actual frozen source commit, validated source hashes, build/executable, closed receipts and completed-state audits are bound by `kg_receipt.json` and `package.json`. The later publication commit changes evidence only.

Both C18 requests completed 23 steps (460 seconds), then stopped at T24 cloud–ice freezing with exit 128. Both 600-second requests remain INCOMPLETE. The separate declared QI/NI inactive/active ice policy passes over completed states; generic exact-source FAIL remains preserved. The immediate T24 predicate is reproduced, but its upstream cause and relationship to prior Q/B changes remain unresolved. Water/energy closure, mass–wind balance, independent observation fit and reduced initial shock remain FAIL_OPEN.

The first attempt used a different user-site Python package and aborted before merge; the guard restored the baseline. The retry uses `/home/korea_keun/.local/share/uv/tools/graphifyy/bin/python3` with actual Graphify 0.9.53. Environment and rollback evidence are retained. Run `update_kg.py` with that Graphify environment; no global package installation was made.

Extraction is a selected-source AST/Markdown overlay, not semantic re-ingestion. Generated Fortran in Python strings is hash-bound; cross-file Fortran CALL extraction is partial. Graph freshness provides navigation evidence only. Verify this package with `sha256sum -c SHA256SUMS`.

See [the bounded publication review](publication_review.md) and [the preservation review](postapply_review.md).
