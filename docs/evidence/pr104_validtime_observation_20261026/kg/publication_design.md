# PR104 valid-time observation KG publication design

Status: preparation only. No Graphify update, check-only plan, staging apply, or
maintained-tree write has been run for PR104.

## Source scope

The current PR104 source changes are limited to:

- `tools/pr103_surface_temperature_observation.py` — accept an explicit valid
  time, select exactly one matching WRF history record, and filter LSO reports
  to the corresponding report hour.
- `tools/pr104_validtime_observation.py` and
  `tests/test_pr104_validtime_observation.py` — compare H/A/N histories at one
  explicit UTC valid time, validate exact history-record selection and grid
  agreement, and report paired N-minus-A station-interpolated T2 deltas.
- `tools/pr86_time_response.py` and `tests/test_pr86_time_response.py` — include
  the 640-second response point in the shared compact time series.

At final source freeze, derive the allowlist from the committed PR104 diff. Add
only PR104-owned documentation under `docs/PR104_*` and focused tests that are
actually in that diff. Evidence JSON, run payloads, receipts, and KG guards are
hash-bound but excluded from Graphify source extraction. The KLAPS50 corpus
must map the selected Cloud-BAL paths under `Cloud-BAL/`; keep the two corpus
graphs separate.

## Parent baseline

Use the corrected PR103 publication receipt as the parent, not its retained raw
apply receipt:

- Receipt: `scratch/pr103_amplitude_control_20261026/Cloud-BAL/docs/evidence/pr103_amplitude_control_20261026/kg/publication/kg_receipt.json`
- SHA-256: `77e096bd1b1e8409c7f8a71d51b090ec5f8a2b88d8079120ac48f870dc15de82`
- Status: `PASS`, `writes_performed: true`, source commit
  `e73203b9c2f070a58aeb8488bf1e5e67a66d5f2e`.
- Parent state: 124 dated snapshots, 627 maintained-source entries
  (`0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`), 197
  inherited immutable pins, and 13 protected-content hash groups.
- PR103 already occupies the `2026-10-26` raw-date name; its retained raw
  snapshot is `2026-10-26-pr103-graphify-raw` and its named snapshot is
  `2026-10-26-pr103-amplitude-control`.
- The correction records that the original raw apply receipt was mislabeled by
  preflight dict-unpack. It remains immutable and is not authoritative. The
  corrected receipt records the independent post-readback, the source fix, and
  no additional maintained writes.

Validation receipt:
`scratch/pr103_amplitude_control_20261026/Cloud-BAL/docs/evidence/pr103_amplitude_control_20261026/kg/publication/validation_receipt.json`
(SHA-256 `8752676b4ad14d0bccd4cd5e5333f08bf09b38d32598e0929fa7bc41079d3dbe`)
records v4 PASS, 151 Python checks, and no compiler, model, or Graphify
invocation.

## Guarded publication shape

Reuse the corrected PR103 pinned helper chain and its staging-only report
normalizer. Before generating a plan, verify the exact parent receipt hash,
source commit ancestry/selection base, all 124 snapshot folders and members,
all 627 maintained-source entries, 197 pins, the 13 protected groups, and
both independent graph baselines. Do not copy or update the full clone: stage
only the graph artifacts, metadata, wiki files, and reviewed selected sources
needed by the pinned incremental helper. Hash the exact staged Graphify file
set before invoking Graphify; reject unexpected extraction/removal scope and
report-format drift.

If the final check-only review is approved, use the actual captured local date
and remap its automatic raw snapshot to
`2026-10-26-pr104-graphify-raw`. The named snapshot should be
`2026-10-26-pr104-validtime-observation`. Publish only those two additions in
each corpus (four exact destinations total), taking the total from 124 to 128.
Fail closed if any destination exists, any inherited snapshot differs, or any
other source/inventory/hash check changes. Preserve rollback and independent
post-readback checks. Any change to source, plan, PR URL, date, evidence
manifest, or parent receipt requires a new plan and root GO binding.

Keep `physical_approval: FAIL_OPEN` and `observation_skill: NOT_EVALUATED` in
the eventual receipt unless independent evidence changes those states. A
same-valid-time residual comparison and a fresh graph do not establish
forecast skill or scientific approval.

## Runtime evidence boundary

The existing PR103 observation output is a same-cycle 13Z comparison for
O/H/C/P/N with 765 matched station records. The PR103 amplitude 640-second
observation output evaluates only the generated T0 history. Neither is a
3600-second observation comparison. Existing frozen C2 run directories
contain compact and raw diagnostic/budget captures, but no reviewed
H/A/N-at-3600 observation receipt has been identified in this preparation.
Until the exact three history records and valid-time inputs are hash-bound, the
PR104 3600-second observation gate remains open. Do not build or run a new
compiler/model candidate for KG maintenance.

## Graph baselines and limitations

The corrected PR103 receipt reports KLAPS50 at 40,983 nodes / 85,369 edges /
3,315 communities and Cloud-BAL at 15,155 nodes / 26,911 edges / 1,344
communities. Its selected extraction reported 317 nodes / 904 edges per
corpus; final graph delta was +226 nodes / +416 edges, with 236 added IDs and
10 removed IDs. These are PR103 baselines, not predicted PR104 deltas.

The PR104 scratch graph is stale relative to its source checkout and is not a
publication baseline. Use maintained PR103 graph hashes and reports only as
read-only baseline evidence. Any final graph delta must be measured from
staged PR104 outputs. Graph freshness is structural evidence only.
