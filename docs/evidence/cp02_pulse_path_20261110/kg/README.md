# Graph publication count reconciliation

`publish_kg.py`, `publish_receipt.json`, and `postpublish_copy_receipt.json` are the original executed and frozen evidence. The publisher incorrectly recorded `published_snapshot_count` as 258, repeating the count before publication. Use `publication_summary.json` for the independently recounted total: 260, comprising 128 KLAPS50 and 132 Cloud-BAL snapshots, including all 258 prior snapshots. The summary supersedes only that incorrect count; it does not replace the original receipt or claim a new publication.

`reconcile_published_count.py` verifies the retained snapshots, 13 publication targets, 9 copies, and all frozen source and evidence pins before writing the summary. It does not modify maintained graph or wiki files. Do not reuse the frozen executed publisher for a new batch.
