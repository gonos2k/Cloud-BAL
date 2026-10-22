# PR99: source-recorded first-call cutoff removal context

This supplement measures the existing KDM6 `qmin`/`qcrmin` threshold
assignments in the frozen C1 first call. It compares each recorded condensate
removal with pre-call condensate inventory on the same explicit spatial and
vertical masks. These are diagnostic quantities; the threshold cleanup is a
numerical removal and is not labeled as evaporation, sublimation, or another
phase process.

## Measurement

The retained `PR85_KDM6_CUTOFF` rows include I/J/K, loop, the threshold mask,
and each of QC/QI/QR/QS/QG before and after the existing assignment. The
instrumented source writes a row when one of those Q fields, number fields, or
graupel volume state changes. The reducer checks threshold-mask consistency,
thresholded stores cleared to zero, unchanged stores above threshold, unique
assignment keys, complete row counts, and the receipt hashes.

Both amounts use the original fixed measure:

`DEN(k,j,i) × DELZ(k,j,i) × map_area(j,i)`.

Removal is `Qbefore − Qafter`; inventory is the pre-call Q value, summed over
the same selected levels and columns. Only condensate species enter the
denominator; QV is excluded. Three masks are reported: the full active tile,
the exact 613-cell source-composed QC support, and the fixed five-cell
Chebyshev buffer across all 39 native levels in its 196 columns. A fourth
region is the union of cells with any Q cutoff event.

## Results

Amounts below are kg. The inventory ratio is a contextual ratio against the
pre-call condensate mass in that same region.

| Arm | Region | Removed | Pre-call condensate | Ratio |
|---|---|---:|---:|---:|
| OFF | Full active tile | 43,406.915 | 3,461,109,771,927 | 1.254e−8 |
| HYDRO | Full active tile | 43,418.203 | 3,460,604,734,443 | 1.255e−8 |
| COUPLED | Full active tile | 43,395.755 | 3,460,604,733,348 | 1.254e−8 |
| OFF | Exact 613 QC support cells | 17.919 | 3,656,766,021 | 4.900e−9 |
| HYDRO | Exact 613 QC support cells | 26.232 | 3,156,236,381 | 8.311e−9 |
| COUPLED | Exact 613 QC support cells | 10.374 | 3,154,023,473 | 3.289e−9 |
| OFF | Five-cell buffer, all levels | 302.211 | 21,872,489,048 | 1.382e−8 |
| HYDRO | Five-cell buffer, all levels | 313.499 | 21,367,451,578 | 1.467e−8 |
| COUPLED | Five-cell buffer, all levels | 291.053 | 21,367,450,441 | 1.362e−8 |

Full-tile removal by species:

| Arm | QC | QI | QR | QS | QG |
|---|---:|---:|---:|---:|---:|
| OFF | 0 | 0.024570 | 30,688.414 | 12,688.304 | 30.172 |
| HYDRO | 0 | 0.024560 | 30,688.415 | 12,699.592 | 30.172 |
| COUPLED | 0 | 0.024628 | 30,691.112 | 12,674.447 | 30.172 |

Most of the measured threshold removal is QR and QS. In the species-specific
cutoff-event footprints, the contextual removal/pre-call inventory ratios are
about 16.9% for QR, 0.220% for QS, 0.00274% for QG, and 0.000051% for QI;
QC has no recorded Q removal. These percentages are **not** fractions of the
original cloud physically lost: species can form, convert, replenish, and
cross the threshold repeatedly during the call. The event-footprint
denominators are pre-call values at cells where that species had a recorded
cutoff removal, so they show local scale only.

The full-tile signed removal matches the existing PR98 same-call cutoff term
exactly in the reducer's reported R64 totals in all three arms. This is an
independent inventory context for that already-accounted numerical removal; it does not explain the
remaining call-water residual or establish a physical conservation result.

## Evidence and limits

The machine-readable results and bindings are in
[cutoff_inventory.json](evidence/pr99_cutoff_inventory_20261022/cutoff_inventory.json).
The reducer validates the source-composed 613-cell support and 196-column
buffer counts, pre-state and cutoff-ledger hashes, the pinned C1 replay
executable, matching full-tile face-replay state hashes, the history map, and
the prepared source writer hash. All three arm replays preserve all 17 returned fields
and XLAND byte-for-byte. No forecast was run for this analysis.

The pre-call ratio is a contextual comparison. It is not attribution of the
removed mass to an atmospheric phase process, and the event ledger records
only changed threshold-assignment events. A zero Q removal does not imply
that the species had no other process activity.
