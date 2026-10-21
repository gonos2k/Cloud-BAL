# PR96 — local HYDRO contract and liquid-store closure

Base: main `50d11d631a59d461c37da2e8bc9666c6bcc9c380` (PR95).
The original PR93-C4 executable and inputs remain preserved.

PR #96 was merged on 2026-10-21 at 11:48:38 UTC as
`72bab3a89ec3b74b552646cf44386cb7a3950672`. The draft/pending descriptions
in the retained launch artifacts are historical snapshots. Merge status
does not establish runtime completion or scientific approval. The later
C1 closed results are reported separately in [the PR97 result entry](PR97_C1_BUDGET_20261022.md).

## Results available before the new native comparison

| Work | Result | Scope |
|---|---|---|
| Area/coordinate missing-value reader | Fixed; 29 tests pass; actual C4 geometry unchanged | Reject declared finite fills before crop and area calculation |
| OFF T1 column `(117,141)` | Exact layerwise closure of the −10.784439 kg residual | Actual liquid-transfer REAL32 store errors; 17 returned fields unchanged |
| Independent OFF T1 column `(116,141)` | Exact layerwise closure of +1.734945 kg | Same diagnostic and reducer; 17 returned fields unchanged |
| Closed C4 compact longruns | Both incomplete after 620 seconds | First 600 seconds match C4 in the separately audited 12 trace and 10 history fields |
| Closed C4 HYDRO | Incomplete after 500 seconds | T26 strict ice NG base failure, not evidence of balance skill |

See [reader checks](PR96_READER_20261021.md),
[two-column closure](PR96_COLUMN_LIQUID_ROUNDING_20261021.md), and
[closed results](PR96_CLOSED_RESULTS_20261021.md).

## HYDRO producer–consumer contract

All six captured host boundaries from T25 POST_KDM6 through T26 PRE_KDM6
pass the strict ice condition. The later KDM6 NG base has a different ice
pair. Its mean mass passes the existing freezing 8-ULP cone, but its number
falls below the strict NG lower bound. The second internal PSD completion
does not repair it. No ice writes or subroutine calls occur between that
completion and the NG base copy. This identifies a missed completion
contract; it does not identify the earlier internal operation that first
crossed the strict boundary.

[The diagnosis](evidence/pr96_hydro_20261021/ice_ng_diagnosis.md) binds the
exact stdout bits, the closed trace selection, and source-derived tests.
`tools/pr96_ice_ng_contract.py` pins the original C4 KDM6 source and makes
the three existing PSD completion blocks and strict NG consumer share the
same number-bound calculation. It reuses the existing directed PSD bound
helper. The freezing 8-ULP allowance and inactive-ice policy are retained.
Number reconstruction is a PSD representation change, not physical
nucleation.

## PR96-C1 native comparison

The new partial-host overlay uses the same nine C4 source overrides and
cycle support; only KDM6's active-ice completion contract changes.

- Source manifest: `/var/tmp/pr96_sources_c1_20261021/manifest.json`.
- Build receipt: `/var/tmp/pr96_native_build_c1_20261021/pr87_native_overlay_build.json`.
- Executable SHA256: `a714f00d3f81c0b47d94aef815f1f765ae48842e9de629cb869323ccfc22a96d`.
- Pinned Intel 2026 `CLOUD_BAL_REPRO_FLAGS`: O2, strict FP, no FTZ.
- Full overlay compiled in fresh scratch; this is not a clean full-WRF build.
- The same executable is required for OFF, HYDRO, and COUPLED at 600 seconds.
- The three native runs started after source review and preflight. At PR96
  publication their closed receipts and endpoint audits were pending. Those
  launch records are retained; the PR97 result entry records the subsequent
  closed results. The successful build and local regression alone do not
  establish native runtime completion.

The [timestamped launch snapshot and closed-audit handoff](evidence/pr96_local_closure_20261021/runtime/README.md)
record those requests and the existing-auditor queue. The final focused
batch passed 93 tests; its source hashes and log are in
`evidence/pr96_local_closure_20261021/validation_sources.json`.

## Limits retained

The two local C4 column closures do not close the whole tile, the native
hybrid host water budget, energy, or mass–wind balance. The new C1 candidate
can legitimately differ from C4; its changed PSD reconstruction and
physical response require their own accounting. Generic audit failures,
source-defined consumer checks, procedural completion, and scientific
approval remain separate results. Independent observation skill is not
evaluated here. No duplicate 3600-second forecast is requested.
