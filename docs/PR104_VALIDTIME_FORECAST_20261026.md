# PR104 fixed-candidate, same-valid-time observation comparison

PR104 freezes the HYDRO (H), AMPLITUDE (A), and STRUCTURED (N) inputs and the
existing partial-host C2 executable. No new wind candidate, smoothing policy,
model physics, prior, precision, or tolerance is introduced. The purpose is to
compare actual station-interpolated predictions at the observation's valid time,
with separate N−A, A−H, and N−H contrasts.

## Observation and time contract

The actual `262281400.lso` file has SHA-256
`5897d4ec8d4979a71369f68de95c68f7229ae76fa6104619d893b204b9ad6ec9`.
Its header is 2026-08-16 14:00 UTC; all 803 reports have HHMM=1400, of which
765 temperatures are not the declared −99.9°F sentinel. These are counts before
model-domain/operator filtering, not an independent-QC acceptance count.

The new explicit shared contract requests 13:00→14:00 UTC, 3600 seconds at the
unchanged 20-second timestep (180 calls), with 640/1800/3600-second checkpoints.
It binds the three previous closed 640-second receipts and their input,
boundary, executable, and prerequisite identities. Prepare, launch, post-child
completion, and finalization all retain the time and identity checks. Historical
640-second receipts remain immutable. New directories are required for each run.

| Role | Frozen wrfinput SHA-256 |
|---|---|
| H | `46760bdf03e42cbc8e1f5b415e1b304b535d369689f95a421a287d1eb90b679c` |
| A | `9038d0a26896a630b7048091a97a2c0055b26934513392195eb8e609626e74e2` |
| N | `b26e5f3d712732c3459d59b82a4b44fe53eebd9be1fd450d13640d2d8398343f` |

All runs use C2 executable `387f46df…cc9a` and the same boundary
`885591e6…b25d7`, with one domain/rank/thread/tile. This is the existing selected
object overlay; it is not a clean full WRF/library rebuild.

## Reader and physical limits

`tools/pr104_validtime_observation.py` requires an explicit UTC valid time,
a matching full LSO header date/time, and one uniquely matching `Times` record
in each history. Declared fill values are rejected before interpolation. It
retains station rows for all three arms and compares operator outputs on exactly
the same station keys. Missing/duplicate times or unequal coverage fail; no
nearest-time substitution, temporal interpolation, or zero filling is used.

T0 T2 equality remains a known input-consistency null result. The new comparison
must first report whether H(XN)−H(XA) is nonzero; observation count alone cannot
establish discrimination. The 13Z maximum temperature residual is investigated
without removing that sample to improve a score. See the separate observation
source/outlier audit for original units, station metadata, and representativeness.

The initial/boundary analysis may share observation lineage. Until actual
consumption and independent QC/uncertainty authority are established, report raw
same-valid-time residuals and keep independent skill `NOT_EVALUATED`.

Normal output retains the existing C2 compact diagnostics and the frozen
one-minute history schedule, together with the required trace milestones. A
source-preserving postprocessor can reduce these closed outputs; it cannot create
missing step-level pressure or flux tendencies. Existing T1 accounting is not a
one-hour host water/energy closure. No raw RU/RV or state norms are combined into
an arbitrary energy or skill score.

## Execution status

The requested one-hour runs are not yet launched in this preparation record.
Launch and closed receipts will be appended separately. A completed 640-second
control or a successful preflight does not establish completion at 14:00.
Physical approval remains `FAIL_OPEN`; independent skill is `NOT_EVALUATED`.
