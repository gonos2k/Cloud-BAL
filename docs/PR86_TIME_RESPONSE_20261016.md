# PR86 10 minute time response

## Scope

Run the frozen PR85v17 executable for 600 model seconds in the existing OFF and
COUPLED candidate states. The run uses a 20 second timestep, one MPI rank,
one OpenMP thread, and one tile. The input and boundary files are hash-bound to
the original v17 run receipts. The run directories are isolated under
`/var/tmp/pr86_budget_response_20261016/`; the source v17 directories are read
only from the runner's perspective.

Only runtime duration and history cadence change in `namelist.input`:
duration becomes 600 seconds, end time is 13:10:00, and history interval is
one minute. `mp_physics`, coupling mode, model timestep, initial input,
boundary policy, and physics executable remain those of PR85v17. One minute,
five minute, and ten minute history outputs come from the WRF history stream.
The 20 second and exact later completed states are extracted from the native
`POST_KDM6` stage records, keyed by timestep number and model time.

The runner hashes all 101 original runtime inputs per arm before staging, keeps
the v17 executable and input hashes in its receipts, checks the active-run disk
projection before launch, and compresses closed raw ledgers after each run.
Compressed data is decompressed and rehashed before the uncompressed file is
removed. The existing KDM6 call guard marks its detailed process dump complete
after the first call; other stage and process outputs are still monitored for
actual disk growth during the run.

## Results

OFF ran in `/var/tmp/pr86_budget_response_20261016/OFF/run` with 710 GiB free
at collection. The executable returned 1 after completing the first 20 second
step (660.268 seconds wall time). Stage records entered timestep 2, but only
`POST_KDM6` timestep 1 completed; the only available selected snapshot is 20s.
Its preflight projected 383.4 GiB output with a 451.0 GiB required-free guard,
against 710.6 GiB available.
WRF stopped at the first FogDES paired Stokes settling guard:
`FogDES paired Stokes settling requires both cloud moments`. The exact fatal
context and the first-call OFF pre/post dump hash match are in
[`pr86_time_response_OFF_20261016.json`](evidence/pr86_time_response_OFF_20261016.json).
The raw launch receipt is preserved at
[`pr86_time_response_OFF_launch_20261016.json`](evidence/pr86_time_response_OFF_launch_20261016.json).
The first-call dump hashes match the PR85v17 baseline; this PASS is limited to
the first call and does not override the later fatal. The COUPLED first-call
pre/post dumps also match its PR85v17 baseline; both arms' digests are in their
strict receipts and the matched-response evidence.

The strict OFF receipt is **INCOMPLETE**: it has one of 30 expected model
timestamps, one completed post-KDM6 timestep, no 1m/5m/10m snapshots, and no
input or source-receipt hash changes. The launch-time runner source hash was not
captured because this run started before source hardening. Its original
launch receipt is retained separately, and the receipt identifies the strict
successor collector source hash.

COUPLED ran in `/var/tmp/pr86_budget_response_20261016/COUPLED/run` with the
same frozen executable and runtime settings. It returned 1 after the first
20 second timestep (660.497 seconds wall time), then hit the same FogDES paired
Stokes fatal. Only `POST_KDM6` timestep 1 completed; timestep 2 was entered
without reaching `POST_KDM6`. Its preflight also passed the 451.0 GiB required-
free guard, with 709.0 GiB available. Both 10 minute receipts are **INCOMPLETE**.

The matched history comparison found only the initial 13:00:00 history file
for each arm; no 1 minute history outputs were produced before the stop. See
[`pr86_matched_history_response_20261016.json`](evidence/pr86_matched_history_response_20261016.json).
The strict receipt gate requires all 30 contiguous timestamps and completed
`POST_KDM6` steps, all four selected snapshots, no fatal lines, unchanged
inputs, and intact output hashes. It also rejects duplicated timestamps
within a log or duplicated `POST_KDM6` steps while allowing mirrored timestamp
sequences across RSL logs.

The strict receipts and preserved launch records are available for both arms:
[`OFF strict`](evidence/pr86_time_response_OFF_20261016.json),
[`OFF launch`](evidence/pr86_time_response_OFF_launch_20261016.json),
[`COUPLED strict`](evidence/pr86_time_response_COUPLED_20261016.json),
[`COUPLED launch`](evidence/pr86_time_response_COUPLED_launch_20261016.json), and
[`COUPLED launch provenance`](evidence/pr86_time_response_COUPLED_launch_provenance_20261016.json),
[`COUPLED preflight`](evidence/pr86_time_response_COUPLED_preflight_20261016.json).
The strict collector source SHA is recorded in each strict receipt. COUPLED
records launch runner SHA `f0ff4e5e…`; OFF’s launch runner SHA was not captured
and is explicitly unavailable. Both strict receipts were rebuilt by the
successor collector SHA recorded in those receipts.

The matched first-call state response is summarized in
[`pr86_matched_first_call_response_20261016.json`](evidence/pr86_matched_first_call_response_20261016.json).

## Limits

These are isolated one-domain response diagnostics. They do not establish
global carrier-weighted water or energy closure, observational skill, or
operational acceptance. Graph freshness and a normal model exit do not provide
scientific validation.
