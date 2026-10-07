# PR70 graupel volume process audit (workspace date 2026-10-08)

## Finding

The PR69 native rejection at `(i,k)=(125,17)` remains **OPEN / REJECTED**.
The exact selected source accepts a signed graupel mass tendency while its
`ProgB_param` density setup is inactive. A separate matched observer run now
captures all executed `ProgB_param` stages and the operands immediately before
the volume helper. It establishes why the tiny donor pair exists, but does not
establish a supported bulk-volume rule for that pair.

## Source path and process signs

The exact selected process source is
`/var/tmp/pr69_native_jointprocess_20261007_v3/source/selected_candidate_fbf_pr69_water.f90`,
SHA-256 `ee688498b32b7a1ccaf69858f62f4e457f7153df4fb8b965acfd069d8eefb425`.
`rhox` is explicitly initialized to zero at line 1259. Five `ProgB_param`
call sites precede the cold `pgdep` branch (lines 1389, 1492, 1583, 1732,
1927). The routine's density setup gate is `qg > qcrmin OR brs > brs_min`
(line 3864), where `qcrmin=1e-9` and `brs_min=1e-15`; inside that gate
`rhox=qg/brs` is clamped to 100–900 kg m⁻³ (line 3866).

The cold mass tendency instead runs for any `qg>0` when `ifsat != 1`
(line 2715). It is signed by `(rh_ice-1)` (line 2719); negative
`pgdep` is sublimation and is capped by available graupel mass `-qg/dtcld`
(lines 2722–24). The same signed tendency is consumed by vapor and graupel
mass updates. A supported positive `rhox` would provide a signed mass-to-bulk-
volume conversion, but this source supplies no density on the inactive path.

`ProgB_param` declares 18 outputs `INTENT(OUT)`:
`rhox, cmg, pidn0g, avtg, pvtg, precg2, bvtg, bvtg1, bvtg2, bvtg3, bvtg4,
rslopegbmax, g1pbg, g3pbg, g4pbg, g5pbgo2, g1pdgbgmg, dgbgmug1`.
The source audit found assignment sites for these outputs but does not find
assignment on every control path. When its density gate is false, the routine
returns without assigning these outputs; under Fortran `INTENT(OUT)` semantics
they are undefined on return. This is distinct from the PR69 and PR70 runtime
observation of `rhox=0`, which is consistent with the explicit earlier
initialization but is not guaranteed by the routine contract. No claim of
guaranteed runtime zero initialization is made.

## Matched native observer evidence

The observer-only run was freshly compiled and linked in
`/var/tmp/pr70_native_volume_trace_20261008_v3` using the pinned Intel profile
(`ifx 2026.0.0 20260331`), against the same 101-input receipt as PR69. It ran
one task and one WRF tile. The run occurred on UTC 2026-10-07 (workspace local
date 2026-10-08). The observer captured KDM6 argument `lat=2`; this is a local
latitude index, and no mapping to global `j` is asserted.

At `(lat,i,k)=(2,125,17)`, `dtcld=20`, stages 1, 2, 2, 3, and 4 each had
`qg=0`, `brs=0`; the density gate was false before and after each call. Stage 2
is entered twice at its source call site. Stage 5 had
`qg=1.5222058e-14`, `brs=1.5222057e-17`; its density gate was also false
before and after the call. Immediately before volume conversion the capture
records `pgdep=-7.6110288e-16`, observed `rhox=0`, and `rh_ice=0.9806284`.

The source-order trace identifies the first nonzero pair. Between stage 4 and
stage 5, rain freezing writes `qg += pfrzdtr` and `brs += pfrzdtr/denr`
(source lines 1897–98). Stage 4 is `(0,0)`; stage 5 equals the freezing
increment. The retained PR69 receipt binds `denr=1000 kg m⁻³`, so the captured
`qg/brs=1000.0000657 kg m⁻³` is directly explained by that material-density
conversion. It is not evidence that the donor lies in `ProgB_param`'s
100–900 kg m⁻³ supported interval: it lies above the interval. The prior
donor-proportional debit identity would preserve the unsupported ratio and is
not accepted as a replacement rule.

For scale only, the negative rate reaches the available-mass cap:
`pgdep*dtcld=-1.52220576e-14`, leaving approximately `4.0e-22` in the captured
pre-cleanup mass arithmetic. This identifies the mass donor and signed
sublimation direction; it does not define a valid volume tendency or cutoff
accounting. In particular, selected-model permission for the 1000 kg m⁻³
freezing-to-PSD transition and its water/latent-heat accounting remain
unresolved. Positive `pgdep` (deposition/growth) also lacks an established
incoming bulk-volume/source-density convention.

## Disposition

Do not force `pgdep` to zero, substitute a density floor, reuse an unsupported
prior density, or apply a donor-proportional formula here. Keep the volume
helper's unsupported nonzero-rate/nonpositive-density rejection. A general
direction-aware transfer helper is not yet justified: the negative donor
state is outside the supported density interval, and the positive source-growth
volume rule is unspecified. The rejection stays OPEN until the selected volume
model and cutoff water/latent accounting establish a supported rule.

This finding does not resolve whether `qi0` using moist `DEN` is appropriate,
nor whether the source carrier is on physical dry-water basis.

## Evidence and limits

- [PR69 native rejection receipt](evidence/pr69_coupled_process_native_20261007.json)
  records the exact failed operand pair and controlled fatal before the
  post-call checkpoint. Fatal exit is not rollback; this is not accepted native
  behavior or budget closure.
- [Source-bound trace receipt](evidence/pr70_native_volume_trace_20261008.json)
  binds the selected and instrumented source, retained input/native receipts,
  build and run receipts, runtime log, source audit, observer patch, and this
  final document hash.
- The fresh [build receipt](evidence/pr70_native_volume_trace_build_20261008.json),
  [run receipt](evidence/pr70_native_volume_trace_run_20261008.json),
  [observer patch](evidence/pr70_native_volume_trace_observer_20261008.patch),
  and [runtime log](evidence/pr70_native_volume_trace_rsl_20261008.log) are
  retained beside the [source anchor audit](evidence/pr70_volume_process_source_trace_20261008.json).
- Input integrity passed. The controlled fatal returned 128 before
  `kdm6_first_call_post.raw`; output isolation failed. The host closure is
  partial and its retained-host lineage was not newly established. This run is
  observer evidence only; it is not accepted behavior or closure evidence.
- Graph navigation used the separately dated maintained Cloud-BAL snapshot
  from 2026-10-07 (7,685 nodes). Extraction is AST/Markdown-structure based
  with partial cross-file Fortran call extraction. Exact source and receipts
  govern this audit. Graph delta is none: only isolated scratch audit artifacts
  changed; the maintained corpus was not re-extracted.
