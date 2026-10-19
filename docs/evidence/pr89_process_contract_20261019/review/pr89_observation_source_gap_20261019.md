# PR89 observation source and grid gap audit — 2026-10-19

## Finding

The 13:00 UTC case has a real, hash-pinned processed LWC analysis product and a source-defined direct LWC operator, but those do not directly apply to the paired native WRF history arrays. The horizontal and vertical grids differ, and no existing source-bound inverse mapping from native WRF history to the LAPS pressure-level observation grid was found. Do not compare `rho_d*QCLOUD` directly against LWC by trimming, offsetting, or assuming coincident cells.

## Verified 13:00 UTC evidence

`Cloud-BAL/config/cp06a_observation_inputs_20260816T130000Z.json` identifies case `20260816T130000Z` and pins the processed product `Cloud-BAL/scratch/cp02_maintained_derived_O0_qej27s72/matched_control_chain13_O0.b07iv296/prepared/lapsprd/lwc/262281300.lwc`, SHA-256 `9e70f80275cb2cf48b3db9dd189fba04936d6587fa57bf15692100548b242cca`. The file exists and its bytes match the manifest hash. Its shape is `[1,22,283,235]`, units `kg/meter**3`. The other nine 13Z products listed in the same manifest also exist and match their hashes.

The PR82 compact readback receipt `docs/evidence/pr82_observation_signal_readback_strict3_compact_20261012.json` binds case `20260816T130000Z`, valid-time epoch `1786885200`, and the LWC grid `[22,283,235]`. It records the direct operator

```text
H(x) = rho_d * qc
rho_d = p / [287.05 * T * (1 + qv/0.622)]
```

for pressure-grid states, using the source path `src/common/cloud_bal_real_netcdf.f90` (`read_real_shadow_state`, `read_and_assign_hydrometeor`, and `dry_density`; lines 499–503, 4021–4056, 4371–4378 in the cited evidence). The product is an analyzed input already used to construct background cloud water. Its established scope is same-time analysis consistency, not independent observation fit or forecast verification. The receipt freezes a 1,294,696-cell above-ground finite/nonnegative LWC footprint and a distinct PR78 analysis support of 162 cells on that pressure grid.

## Native history grid and mapping check

The PR89 paired-history receipt and `docs/PR89_HISTORY_DIAGNOSTICS_20261019.md` bind the paired native history comparison to mass-grid dimensions `282 × 234` (`south_north × west_east`) and native hybrid vertical levels. The PR82 same-13 handoff records native `wrfinput`/`wrfout` mass fields at `234 × 282 × 39`, with 40 staggered vertical levels; its source LAPS/WPS grid is `235 × 283`. Thus LWC has 22 pressure levels on a 235×283 grid, while native history has 39 mass levels on a 234×282 grid.

The existing `map_pressure_candidate_to_wps` path maps a LAPS pressure candidate into captured LAPSPREP/WPS source-grid arrays. PR82 then records metgrid output on 234×282. Its four source-grid offset QV checks are explicitly exploratory; no offset was selected or certified as a cell mapping. The existing pressure-to-native W consumer maps pressure-level omega to native W, not native hydrometeor history back to pressure-level LWC. The PR82 observation readback only compares same-grid 235×283×22 pressure-level candidates. No verified horizontal-plus-vertical native-history-to-LWC observation operator or inverse WPS/metgrid mapping was found in the reviewed source/tools/docs. Metgrid's forward WPS processing is not, by itself, an authorized inverse map for these diagnostics.

Therefore an actual native T0 `rho_d*QCLOUD - LWC` calculation is not presently well-defined. A valid comparison requires a source-bound mapping specifying horizontal projection/grid correspondence, vertical interpolation from native hybrid pressure levels to the 22 LAPS pressure levels, terrain/valid-cell handling, and its mask/hash. Do not infer this map from equal nominal 5-km spacing, dimensions differing by one, or exploratory offsets.

## Footprints are not interchangeable

The PR82 162-cell PR78 analysis support is authoritative within the LAPS pressure-grid evidence and has its own pinned mask hash. PR89's 27-column `initial native analysis water support` is a separate descriptive mask selected from exact OFF/COUPLED native water-species differences at T0, then held fixed through T60. PR89 documents that mask as outcome-selected, not observation validation. No grid mapping connects these masks; the 162-cell support cannot be transferred to native history, and the 27-column support cannot stand in for it.

## Defensible scope and next evidence

Available now: retain PR82's same-grid pressure-candidate versus 13Z LWC consistency result as the T0-prehost analysis check, with its stated non-independent scope. The paired native history supports same-grid OFF/COUPLED T0/T60 diagnostics only. No time-matched 13:01 LWC observation was identified, so native T60 observation verification is also unavailable. To extend comparison, first provide and validate the missing native-to-pressure-grid mapping against actual grid coordinates/pressure, then freeze a mapped support; a separate 13:01 observation product/operator would still be needed for time-matched T60 verification.
