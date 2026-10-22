# PR99: native consumption, first grouped failure, and T1 accounting

This is the entry point for the PR98 follow-up. The frozen PR96-C1 OFF,
HYDRO, and COUPLED 600-second baseline remains unchanged. The U/V projection
below is a separate, non-default research treatment; it is not a replacement
for those three completed runs.

## Results and limits

| Workstream | Result | Interpretation |
|---|---|---|
| Pressure-level transfer | The actual C1 candidate's horizontal and omega flux increments are separated. Holding omega fixed makes the retained pressure-level solve incompatible before iteration. | Removing an unexported control requires a feasibility check; the old solution cannot simply be relabeled as native balanced. |
| Native dry-flux proposal | Project only the additional C−H U/V increment inside the fixed QC buffer, retaining HYDRO's nonzero reference motion. | A local, frozen-carrier mass constraint, with no omega-to-W substitution. |
| Archived native consumer | The actual C1 `calc_ww_cp` object consumes the proposed stored REAL32 winds. | Initial mass-coordinate `ww` is checked in Pa/s, not physical W or pressure-level omega. |
| Native integration | One closed 20-second proposal run, using the same capture model and boundary as the original three diagnostic arms. All 208 input variables are audited; only U/V differ from the original C1 COUPLED input. | This verifies one subsequent native consumption, not 600-second stability or observation benefit. |
| First grouped rejection | The OFF diagnostic closed after 620 seconds; its first 600 seconds match the original C1 trace and history. The first store rejection and separate fatal fallback are replayed. | An ordinary transport boundary rejection precedes a different tiny source candidate whose fallback assumes pure diffusion. |
| Revised storage contract | The actual full candidate equation has a conservative, shared quantum-absence certificate. Intel O0/O2 and the independent exact-input oracle pass locally. | The distinct PR99-C2 model still requires a matched three-arm native test. |
| Same-call water budget | Independent process/store terms are reduced from full-tile replays with unchanged post-state fields. | Explained numerical removal or storage change is accounting evidence, not restored physical conservation. |

## Native proposal outcome

The proposal retains 95.77% of the equal-face L2 norm of the additional C−H
wind increment. Every other stored input field, including W, mass, pressure,
Phi, temperature, and hydrometeor moments, remains unchanged.
The applied U/V change has L2 norm 30.381 m/s, or 28.77% of the original
extra-wind norm; its component maxima are 1.744 m/s in U and 1.872 m/s in V.
These maxima need not occur together. Retaining a norm does not establish
observation-signal preservation.

During the first captured 20-second step, at each measure's own source boundary:

| Measure | HYDRO | Original C1 COUPLED | U/V proposal |
|---|---:|---:|---:|
| Captured dry-column mass-rate L2, kg/s | 17,899,337 | 383,305,796 | 15,276,841 |
| Assembled RU L2, source-array units | 24,361.97 | 41,212.46 | 37,999.03 |
| Assembled RV L2, source-array units | 23,908.72 | 34,050.81 | 33,199.72 |

The dry-column rate uses the first acoustic MU update in 16 QC columns.
RU/RV use the first assembled tendency capture on the 769/767 faces linked
to the fixed QC support. They are not a simultaneous vector or energy norm;
the completed-step timestamp does not identify each tendency's instant.

The mass response decreases strongly. RU and RV decrease relative to the old
COUPLED treatment, but remain about 1.56 and 1.39 times HYDRO. The proposal
therefore remains **non-default; physical approval `FAIL_OPEN` and observation
skill `NOT_EVALUATED`**. Raw RU/RV are not acceleration or energy norms. A
nonzero column mass tendency is not itself a continuity-conservation error.

## Grouped rejection and revised storage

The first T32/RK1 grouped rejection is a normal-size transport candidate at
`(163,63,22)`, rejected at strict store stage 2. The later decisive fallback
is at `(2,241,14)`: its composed source is nonzero while diffusion replay of
the captured old field is zero. All three historical C1 arms have the same
compared fatal operands. Local reason 6 is not common-store stage 6.

The revised common predicate certifies the existing complete source-plus-air
equation using outward numerator bounds. It requires the whole bound to lie
inside the strict density cone and the existing quantum-loss budget, and
bit-binds the original REAL64 candidate. It authorizes only paired-zero
representation with adjustment 5 and the existing signed ledger. Uncertain
bounds are rejected; no density tolerance, physical source, or candidate
arithmetic is changed. This remains a storage-policy revision, so the matched
OFF/HYDRO/COUPLED test must use the same distinct PR99-C2 executable. The old
C1 diagnostic failure remains preserved.

## T1 accounting outcome

Six process/store stages, the separately recorded cold/warm approved packet
sum, public-Q storage changes, and graupel sedimentation are added to the
earlier liquid/cutoff/rain-and-ice account. The final same-call remainder is:

| Arm | Signed, kg | L1 of column remainders, kg |
|---|---:|---:|
| OFF | −174.098 | 11,972.616 |
| HYDRO | −172.053 | 11,960.408 |
| COUPLED | −173.575 | 11,970.601 |

All three full-tile diagnostic replays preserve the 17 returned fields and
XLAND byte-for-byte. The small signed remainder includes spatial cancellation:
the largest remaining column magnitude is about 22.59 kg. The account remains
**OPEN**. No remainder is fitted as a correction, and no water is returned to
the model to force closure. Cutoff remains a measured numerical removal,
not evaporation or sublimation. This is the fixed input `DEN × DELZ × area`
measure of one KDM6 call, separate from the host's hybrid water/energy budget.

The cutoff supplement keeps the source-composed QC support and the fixed
buffer. No QC mass is removed by the recorded T1 threshold assignments;
most removal is rain and snow. Ratios to pre-call condensate inventory are
context only, since species can form and replenish during the call.

The closed first-call captures also localize a QC pattern change. In the
613-cell support, HYDRO, original COUPLED, and the U/V proposal retain strong
alignment with the initial C1−OFF QC contrast at KDM6 entry (cosines
0.997–1.000), but their POST contrasts have negative cosines. The change
develops across that measured call; no individual process or observation
skill is inferred from this Eulerian diagnostic.

## Evidence map

- [Pressure candidate, omega authority, and feasibility](PR99_PRESSURE_TRANSFER_20261022.md)
- [Native U/V projection and closed 20-second response](PR99_NATIVE_PROJECTION_20261022.md)
- [Actual archived native consumer replay](PR99_NATIVE_WW_CONSUMER_REPLAY_20261022.md)
- [Physical dry-column mass-rate measure](PR99_NATIVE_DRY_MASS_RATE_20261022.md)
- [First grouped rejection capture and scalar replay](PR99_GROUPED_FAILURE_DIAGNOSTIC_20261022.md)
- [Shared full-candidate storage certificate](PR99_BULK_CANDIDATE_CONTRACT_20261022.md)
- [Same-call T1 remaining water accounting](PR99_T1_REMAINING_20261022.md)
- [Cutoff removal and same-region condensate context](PR99_CUTOFF_INVENTORY_20261022.md)
- [First-call hydrometeor entry and response](evidence/pr99_hydrometeor_response_20261022/README.md)

The linked receipts bind the source, compiler/profile, generated driver,
candidate, boundary, and output artifacts. Native work uses pinned Intel
IFX 2026 in fresh scratch working directories. Actual runs remain partial-host
research runs; they are not clean full-WRF/library rebuilds.

## Remaining scientific gates

Full momentum balance, whole-host hybrid water/energy closure, retained cloud
and precipitation signals, and independent observation skill remain open.
The frozen C1 three-arm comparison and one-step wind proposal must stay
separate from the revised storage candidate. Its three comparison arms must
use the same new executable; local certification is not native completion.

Graphify/KG updates describe source relationships and extraction limits only.
They cannot promote any runtime or scientific status.
