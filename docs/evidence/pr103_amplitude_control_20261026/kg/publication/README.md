# PR103 bounded KG publication, 2026-10-26

The reviewed two-corpus incremental update completed once. `apply_stdout.json`
records `APPLY_COMPLETE`; `apply_execution.json` records exit code 0 and unchanged
invoked source pins. No weather integration or Graphify rerun was used to correct
receipt metadata.

| Maintained corpus | Nodes before → after | Edges before → after | Communities after |
|---|---:|---:|---:|
| KLAPS50 | 40,757 → 40,983 | 84,953 → 85,369 | 3,315 |
| Cloud-BAL | 14,929 → 15,155 | 26,495 → 26,911 | 1,344 |

Both graphs add 226 nodes and 416 edges net. Each has zero dangling endpoints,
self-loops, or exact duplicate edges in the bounded integrity checks. Extraction
uses 24 allowlisted source paths, with 121 evidence paths bound by hash only.
Fortran cross-file CALL extraction remains partial. Graph freshness is navigation
evidence and does not establish runtime validity or physical approval.

All 120 prior dated directories and their 472 member files are preserved. Four
new directories distinguish raw Graphify backup and final named PR103 snapshots
in each corpus. The 627-entry maintained source inventory, 197 inherited immutable
pins, protected wiki content/schema, and private profile are unchanged. Five
derived wiki report/index/log files were synchronized; no content pages were added.

The graph source is commit `e73203b9c2f070a58aeb8488bf1e5e67a66d5f2e`.
Final receipt metadata, the receipt-phase regression, and this publication are
subsequent administrative changes; they are not represented as new scientific
extraction or a new model result.

## Receipt correction

The original `raw_apply_receipt.json` is retained byte for byte. Its dict-unpack
order let preflight schema/status/writes fields overwrite completed publication
fields. Thus it incorrectly says `PREFLIGHT_PASS_NO_WRITES` despite the separate
successful execution and actual published outputs. The code now places final
phase fields after the preflight fields. The new regression evaluates this order
without a filesystem publication; all 151 focused Python checks pass.

`kg_receipt.json` supersedes only those phase labels, retains the raw receipt's
hash and all substantive graph results, and binds the actual invocation and
independent postreadback. This correction does not re-execute or republish graphs.
Raw receipts from prior unsuccessful attempts are also retained outside this
publication directory in the PR103 KG evidence.

Physical approval remains `FAIL_OPEN`; independent observation skill remains
`NOT_EVALUATED`. The original scientific and validation scopes are unchanged.
