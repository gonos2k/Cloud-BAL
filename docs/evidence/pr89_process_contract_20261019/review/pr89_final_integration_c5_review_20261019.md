# PR89 final integration review (C5, 2026-10-19)

## Scope and result

Read-only review of the current PR body, process contract, cold summary, paired-history diagnostics, evidence manifest, focused-test receipt, and live 600-second preflights. No source, test, documentation, or graph files were edited; no tests or model runs were started by this review.

I found no integration blocker to publishing the 120-second result as a draft PR. The current claims remain bounded to implementation/test evidence and closed-run diagnostics. The 600-second outcomes are still pending and must not be described as successful until their receipts close.

## Identity and evidence checks

Current file SHA-256 pins checked:

- `docs/PR89_PROCESS_CONSUMER_CONTRACT_20261019.md`: `7d92922f18c7581986fa0461f71ceca2f7efc24a22b6f5a550672fc23ff374c0`
- `docs/PR89_COLD_SUMMARY_20261019.md`: `68287a8f1eae733bd3f1f34bde2b1be702c48d25c5f55dbf97c1f9cc636f3c06`
- `docs/PR89_HISTORY_DIAGNOSTICS_20261019.md`: `834ca2bf5ecbc54766adef1c7bbc0273d8b013fc022968b583fe39cf3977e7b0`
- `docs/evidence/pr89_process_contract_20261019/manifest.json`: `cda7e64c51503de9cfecedcfb4aa1b2d291db512666cce009b8efffa14521cd5`
- `docs/evidence/pr89_process_contract_20261019/review/focused_validation.json`: `db85ec83caef05ba2a8415f39c82b1987a08f957f95028c42332512a1bc9e62c`

The manifest binds the current C5 core/build/test pins and labels the native artifact as a partial host overlay (`PASS_OVERLAY_BUILD`, `full_clean_build: false`). The focused receipt records 43 passing checks. The C5 OFF and COUPLED 120-second receipts both report complete six-step runs, return code 0, unchanged staged/original inputs, and matching candidate executable hashes. The cold summaries agree with the ledger-derived row counts and column-unit description; they do not present the column sums as area-integrated/global kilograms. The paired-history note keeps its T0/T60 comparisons descriptive and does not claim observation fit, native-to-observation mapping, physical face-flux closure, energy closure, or shock reduction. Manifest approval remains `FAIL_OPEN`.

## 600-second in-progress state

At review time both 600-second runners and their `wrf.exe` processes were live. Each preflight binds a 600-second duration, 30 expected steps, the C5 build receipt (`1079c73676532bb6ee21c37c9143dcc74a5f93001be01e18f3a283504070dfaf`), and arm-specific initial input hashes. I checked the copied run executables directly: both `run/wrf.exe` files hash to the candidate build executable `beb2da6745606566074e15a043d173a8be01d277f00c4cc90ad3915f5de5a2d6`. Boundary input hashes match the 120-second candidate; the namelist carries the intended 600-second end time and one-minute history interval. There was no closed 600-second receipt at the time of review.

The preflight field named `executable_sha256` is the frozen parent-runtime executable hash (`9642a471...`), while the candidate build and copied run executable are represented in `candidate_build.executable_sha256`. For PR wording, “same C5 executable” is supported by the latter/copy hashes, but the preflight field name alone could be misread. The draft links the manifest and does not cite the parent hash as the executable used.

The current resource projection is explicitly an estimate, not an upper bound. Available scratch space had fallen slightly from the plan snapshot while remaining above the projected requirement; continue monitoring capacity until both runs close.

## PR body review

`/var/tmp/pr89_pull_request_body_20261019.md` is accurate for the current state: it says 120 seconds completed and 600 seconds are running, marks the PR draft pending that validation, and preserves the scientific `FAIL_OPEN` scope. It correctly describes same-call cold column weights and endpoint diagnostics with their limits. No wording change is required before draft publication. After the long-window runs close, update the PR body and manifest with their receipts/results and retain any failed/open gates.
