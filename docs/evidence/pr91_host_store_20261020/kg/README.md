# PR91 Graphify maintenance bundle

This package records the dated Graphify 0.9.53 refresh for the PR91 source commit. The KLAPS50 and Cloud-BAL corpora are maintained separately. The package contains compact reports, only the changed wiki section and appended log bytes, the selected-path receipt, and reproducibility/review records. It includes no full graph payloads and no private host-profile contents.

The integration manifest intentionally has `source_commit: null` and readiness flags false: it was committed before the final publication commit to avoid a self-referential commit hash. The exact final source commit and complete selected diff are instead bound by `kg_receipt.json` and `package.json`. These structural KG results do not promote runtime completion: paired 240-second runs completed; paired 600-second runs are incomplete at 14/30 steps; scientific and physical gates remain FAIL_OPEN.

See `postapply_review.md` for the independent preservation/delta review and `publication_review.md` for the final bounded publication check. Verify the package with `sha256sum -c SHA256SUMS`.
