# PR89 T5 graupel contract diagnosis — 2026-10-19

Read-only review of the two C4 FULL diagnostics for strict pair 4 (QG/QIB). No G code or tests were changed.

## Provenance

- COUPLED C4 receipt: `/var/tmp/pr89_COUPLED_120s_c4_20261019/receipt.json`, SHA-256 `a24c4d30c2d2bcaf9b3df1c4375e2bce56027952425f9bb6b29808cbae289c0b`.
- FULL/source-failure ledger: `run/pr85_joint_source_failure.raw.gz`; compressed SHA-256 `b78cde3f3a2a5afbc41ff86e7b3034ca8c9847c43542cc6eb81fd6d2629224a9`, uncompressed SHA-256 `ee261c9a334294b54fb80a884394b530b2eafdc4e98fede6027745efd7a6cd2f` per receipt.
- C4 source manifest `docs/evidence/pr89_process_contract_20261019/sources/c4_sources.json`, SHA-256 `0e6555606fa3303636dbdd92e0e0224637e2d3fc96064707860b2a715a14af91`; prepared `module_em_pr89.F`, SHA-256 `0bb7be7844100beb8562c8d3d1bf11b0278e92d4a24e5bfee5769fcb87a96483`.
- Both rows are `FULL` at step 5, RK1, pair 4; the report prints values with about 16 significant decimal digits, not binary64 transfer bits. Treat its decimals as diagnostics, not exact runtime R64 operands.

## What the records show

At `(i,j,k)=(185,72,20)`, base Q/N and source Q/N print as zero; transport tendencies print `2.830959328204250e-7` and `3.145510364671388e-10`. Candidate Q/N print `1.982213633411026e-11` and `2.202459592678917e-14`.

At `(23,244,18)`, source Q/N print `2.317945677672934e-6` and `2.575495197414371e-9`; transport Q/N print `5.996661464935781e-6` and `6.662957183261979e-9`. Candidate Q/N print `6.307610900059707e-10` and `7.008456555621895e-13`.

Exact decimal-rational arithmetic on the printed candidate strings gives Q−900N of `7e-27` and `1.5e-25` respectively (nominal Q/N excesses about `3.18e-13` and `2.14e-13`). These residuals are near the output's decimal rounding uncertainty; they are not evidence of exact candidate binary64 bits or a source-level cone violation. In particular, deriving a Python float from the printed decimal and comparing its exact binary rational to 900 is not an actual-runtime bit proof. FULL output records failed direct storage (`-1,-1`), not successful fallback results.

## Producer and existing fallback

The prepared C4 producer's direct QG candidate is formed from separately computed REAL64 source/transport Q and B tendencies and `oldcarrier*base + dt*(source+transport)`, divided by `newcarrier`; QG/QIB direct storage requests `strict_mass_ratio=.TRUE.`. That arithmetic can lose the common-mixture cone property through independent tendency rounding, especially near the exact 900 upper bound. No evidence here justifies relaxing 900, adding tolerance, or expanding precision in the ordinary producer path.

The same actual source already has a witness-based fallback inside `certify_graupel_storage`: it replays `air_tendency` and bit-compares the replayed source; builds nonnegative donor weights from the actual staggered transport; adds actual diffusion face contributions with REAL128 coefficients; verifies each contributing donor QG/QIB pair strictly; accumulates both moments with the same weights in REAL128; divides by the carrier; then, if necessary, moves stored QG by up to four adjacent REAL32 values until the stored pair satisfies the unchanged strict bound. Its signed extensive deltas are recorded. The fallback is also callable via `probe_failed_graupel_pair` for the graupel pair.

This is a source- and donor-witnessed repair of a computed candidate, not an epsilon relaxation. The evidence inspected does not include a successful fallback witness for these two coordinates: earlier pair-2 failure can return before pair 4 is certified, so the FULL rows alone cannot establish whether this fallback was executed or cleared pair 4. Root's current C5 full-population audit reports 11 ICE candidates and two G candidates; all 11 ICE N values are below the derived one-mass-quantum cap. Do not interpret that ICE policy as fixing the G candidates.

## Recommendation

No new G policy or tolerance change is warranted. Keep the existing strict validator and source-witness fallback. Before attributing a T5 G event to either genuine source inconsistency or a floating evaluation artifact, obtain exact runtime candidate/source/transport bits or the fallback witness fields (`witness_i/j/k`, Q/N64, stored Q/N32, canonical/stored validity, and fallback count) for these coordinates. A native retry/follow-up should verify the witness fallback outcome without changing the cone; the current C4 FULL diagnostics do not prove fallback pass/fail or final completion.
