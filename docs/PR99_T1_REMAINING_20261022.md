# PR99 — signed C1 T1 residual column extrema

This adds the most positive and most negative columns after subtracting the
independently reduced liquid-store, cutoff-store, and accepted rain/ice
face-store terms from the same-call water residual. Both coordinates are found
from the full C1 tile using the actual pre/post arrays, input `DEN × DELZ`,
and the receipt-bound history map area. The reduction does not fit a term to
the endpoint residual.

## Signed extrema

All values are kg. OFF, HYDRO, and COUPLED produce the same two extrema.

| Coordinate | `R_raw` | Liquid store | Cutoff store | Accepted rain/ice face term | Remaining |
|---|---:|---:|---:|---:|---:|
| Largest positive `(192,71)` | +23.656073147 | −13.328006463 | −0.000000283 | −1.305231575 | **+38.289311467** |
| Most negative `(161,57)` | −50.660658649 | −10.945631591 | effectively 0 | +0.585856804 | **−40.300883863** |

Thus `(161,57)` is the maximum absolute column residual. The positive extreme
is `(192,71)`; `(208,79)` remains a previously selected example at
`+30.273653 kg`, not the tile maximum. Full-tile signed residuals after these
terms are −22,658.253498 kg (OFF), −22,655.157443 kg (HYDRO), and
−22,683.387674 kg (COUPLED). Their L1 column sums are 169,744.749093,
169,675.042508, and 169,671.599561 kg, respectively.

## Process classification and limits

The initial warm ledger was sparse and the cold per-cell writer was disabled,
so the old replay could not evaluate approved-packet versus stored-Q error at
these columns. A focused read-only observer replay enabled those two ledgers
only for `(192,71)` and `(161,57)`; it also retained freezing, melt, rain
freezing, and ice-transition operands. Each arm completed the full active-tile
component replay and returned all 17 fields and `XLAND` byte-for-byte equal to
the native state. The stage reducer weights the captured store discrepancies
with actual input `DEN × DELZ` and the receipt-bound history map area.

The initial process reduction used level-zero `DEN × DELZ` for every event
and read the ice-transition fields at the wrong offsets. Both errors are
corrected in the current reducer and its regression test. With the actual
one-based event level, the independently reduced process-stage discrepancies
at the positive and negative extrema respectively are: melt `+0.121478` /
`+0.134924 kg`, freezing `+3.154973` / `+0.030683 kg`, rain freezing `0` /
`0`, cold KDM6 `+4.898102` / `−6.006279 kg`, warm KDM6 `+26.864948` /
`−34.938959 kg`, and ice transition `+1.353059` / `0 kg`. These measured
terms total `+36.392561` and `−40.779631 kg`; the remaining column terms are
`+1.896751` and `+0.478747 kg`. The source-ordered residual first grows
substantially at warm KDM6, but the smaller final remainders have not been
identified to an independent process term.

Per-assignment REAL32 total-water checkpoints for those two columns telescope
to the native pre/post change within `7.4e-8 kg`. They confirm that the
checkpoint interval accounting is complete for the selected columns; they do
not by themselves classify the remaining stage discrepancy. The rain and ice
sedimentation Q-stage residuals remain separate narrow operator checks and
are not added as whole-call terms. No residual is assigned to rounding,
physical loss, or an external host boundary.

An attempted broad OFF-only raw process capture produced multi-gigabyte warm
and cold ledgers. It is diagnostic-only and superseded; it is not the compact
observer or evidence for H/C. A compact six-stage process observer has now run on all three actual C1 first-call replays. It records source-ordered melt, both PINU/PFRZ freezing rows, rain freezing, cold, warm, and ice-transition stored-minus-approved water terms as per-column R64 Kahan sums with L1, maximum absolute event, and event counts. It emits a fixed stage row for every active column, including zero-event rows, and applies the receipt-bound map area once in the reducer. All three replay manifests report subprocess return code 0, the full-active-tile completion marker, and byte identity for all 17 fields and XLAND.

The full-tile account after the six stored-minus-approved stages is:

| Arm | Signed (kg) | L1 column sum (kg) | Max absolute column (kg) | Largest positive column | Most negative column |
|---|---:|---:|---:|---:|---:|
| OFF | −184.122643 | 12,201.602011 | 23.878633 | `(169,227)` +21.999347 | `(32,116)` −23.878633 |
| HYDRO | −185.289866 | 12,191.576998 | 23.878633 | `(169,227)` +21.999347 | `(32,116)` −23.878633 |
| COUPLED | −187.618126 | 12,202.606570 | 23.878633 | `(169,227)` +21.999347 | `(32,116)` −23.878633 |

After separately subtracting the signed cold/warm approved-packet amount, the open column account is:

| Arm | Signed (kg) | L1 column sum (kg) | Max absolute column (kg) | Largest positive column | Most negative column |
|---|---:|---:|---:|---:|---:|
| OFF | −159.837148 | 12,023.263034 | 23.830359 | `(169,227)` +22.568657 | `(32,116)` −23.830359 |
| HYDRO | −161.622412 | 12,012.034991 | 23.830359 | `(169,227)` +22.568657 | `(32,116)` −23.830359 |
| COUPLED | −163.744454 | 12,022.335115 | 23.830359 | `(169,227)` +22.568657 | `(32,116)` −23.830359 |

## Supplemental source-owned Q stores

The additive v5 reduction uses only existing successful C1 T1 replay rows; it
does not change the frozen six-stage v4 account or run a forecast. Source review
established that the public cloud/rain store writes whenever the store makes a
Q adjustment or the public number differs from the ordinary conversion. When
the joint store reports no adjustment, its R32 Q input is promoted and rounded
back unchanged, so omitted rows have exactly zero Q delta. The emitted
`delta_q`, `DEN`, and `DELZ` are integrated with the same-call map area.

The graupel source ledger writes one row for each active-column substep. Its
source operator sweeps every `kts:kte` face, updates the graupel Q/B pair,
weights stored Q change with actual `DEN × DELZ`, adds approved ground Q, and
records `residual_q = stored_delta_q + ground_approved_q`. The existing
captures cover all 64,960 active columns, 78,926 substeps, and all 39 vertical
levels in each row; substeps are contiguous for each column. This is a separate
QG operator term, independent of the rain/ice face terms and six v4 stages.

| Arm | Public cloud/rain Q store (kg) | Graupel sedimentation Q term (kg) | Open after both additions (kg) | L1 column sum (kg) | Max absolute column (kg) | Largest positive | Most negative |
|---|---:|---:|---:|---:|---:|---:|---:|
| OFF | −2.338923 | +16.599401 | −174.097625 | 11,972.616106 | 22.588586 | `(169,227)` +22.588586 | `(146,215)` −20.178284 |
| HYDRO | −2.341580 | +12.772652 | −172.053484 | 11,960.407587 | 22.588586 | `(169,227)` +22.588586 | `(146,215)` −20.178284 |
| COUPLED | −2.269038 | +12.099224 | −173.574639 | 11,970.601398 | 22.588586 | `(169,227)` +22.588586 | `(146,215)` −20.178284 |

Public-store row counts are 243/244/246 for OFF/HYDRO/COUPLED. The count is
sparse because unchanged Q stores are omitted, not because nonzero Q
adjustments are unobserved. At `(32,116)`, the graupel term is −7.493480 kg;
at `(169,227)` it is −0.019929 kg. These actual source terms make the
remaining signed account more negative; they do not close it or establish the
cause of other remaining terms. Per-arm details, selected-column checks, and
input hashes are in [`compact_v5`](evidence/pr99_t1_remaining_20261022/compact_v5/).

The full-tile signed terms by stage are:

| Arm | Stage | Signed (kg) | L1 event sum (kg) | Max absolute event (kg) | Event count |
|---|---|---:|---:|---:|---:|
| OFF | Melt | −82.749150 | 2,694.123205 | 4.719345 | 58,826 |
| OFF | PINU/PFRZ freezing | +948.184151 | 12,397.722095 | 3.175273 | 519,835 |
| OFF | Rain freezing | −0.179787 | 1.559534 | 0.132234 | 7,736 |
| OFF | Cold | −3,853.488358 | 164,460.998939 | 9.582080 | 1,510,488 |
| OFF | Warm | −19,408.972507 | 470,458.090586 | 11.529187 | 1,022,952 |
| OFF | Ice transition | −76.925205 | 6,247.055220 | 5.127334 | 7,084 |
| HYDRO | Melt | −79.114393 | 2,695.644145 | 4.719345 | 58,827 |
| HYDRO | PINU/PFRZ freezing | +943.966152 | 12,398.207931 | 3.175273 | 519,835 |
| HYDRO | Rain freezing | −0.179787 | 1.559534 | 0.132234 | 7,734 |
| HYDRO | Cold | −3,867.127167 | 164,441.836408 | 9.582080 | 1,510,488 |
| HYDRO | Warm | −19,389.859157 | 470,410.892917 | 11.529187 | 1,022,952 |
| HYDRO | Ice transition | −77.553226 | 6,246.277707 | 5.127334 | 7,084 |
| COUPLED | Melt | −78.905559 | 2,694.921046 | 4.719345 | 58,835 |
| COUPLED | PINU/PFRZ freezing | +949.574290 | 12,399.243592 | 3.175273 | 519,835 |
| COUPLED | Rain freezing | −0.179787 | 1.559534 | 0.132234 | 7,729 |
| COUPLED | Cold | −3,902.988414 | 164,461.690952 | 9.582080 | 1,510,488 |
| COUPLED | Warm | −19,385.705454 | 470,440.996064 | 11.529187 | 1,022,952 |
| COUPLED | Ice transition | −77.564624 | 6,243.856117 | 5.127334 | 7,081 |

The full-tile baseline and combined stored-term account is:

| Arm | Baseline after liquid, cutoff, and accepted face (kg) | Stored-minus-approved process terms (kg) | Remainder after process terms (kg) | Approved cold/warm packet net water (kg) | Remainder after packet net (kg) |
|---|---:|---:|---:|---:|---:|
| OFF | −22,658.253498 | −22,474.130855 | −184.122643 | −24.285495 | −159.837148 |
| HYDRO | −22,655.157443 | −22,469.867577 | −185.289866 | −23.667454 | −161.622412 |
| COUPLED | −22,683.387674 | −22,495.769549 | −187.618126 | −23.873672 | −163.744454 |

The approved packet amount is recorded independently from its storage discrepancy; it is not folded into the process-store term. For OFF/HYDRO/COUPLED, the cold approved net is −10.002924/−10.202705/−10.744457 kg and warm approved net is −14.282571/−13.464749/−13.129214 kg; the other four stages have no packet observer contribution. The packet field is a diagnostic sum of approved cold/warm water vectors and does not label the nonzero net as physical water creation or loss. At the two selected extrema, compact source-stage terms reproduce the earlier selected reduction: `+36.392560622 kg` and `−40.779630650 kg`, leaving `+1.896750845 kg` and `+0.478746787 kg`. Their cold/warm approved packet sums are `+0.175685526 kg` and `−0.085756663 kg`; after also listing those packet sums separately, the selected open amounts are `+1.721065318 kg` and `+0.564503450 kg`. These remain unclassified. The six-stage v4 interim account leaves about 160 kg signed after separately subtracting the approved packet net; the additional captured Q stores and updated v5 account are listed below. Its L1 column sum and signed extrema are reconstructed from the full per-column baseline and compact stage arrays; the values are listed above. The six-stage v4 account leaves other uncaptured source terms open; the two independently reduced source-owned Q terms and updated remainder are reported above.

The OFF compact per-stage/per-column values and counts exactly match the superseded streamed full-row diagnostic at `(192,71)` and `(161,57)` before area weighting; the hash-bound cross-check is retained with the evidence. The compact outputs and replay receipts are in [`compact_v4`](evidence/pr99_t1_remaining_20261022/compact_v4/). The compact observer source generator and reducer are `tools/pr99_compact_stage_source.py` and `tools/pr99_compact_stage_reducer.py`. This instrumentation changes ledger writes and adds R64 observers only; it does not change physical equations or state assignments. The large OFF raw capture noted above remains diagnostic-only and is not used for the compact full-tile results.

The compact replay manifests retain observed subprocess return code (`0`),
full-active-tile completion marker, byte identity for all 17 returned fields
and `XLAND`, and matching native/replay post-state hashes. The observer was
built with the pinned Intel profile in a fresh external scratch directory.
It adds compact R64 process and packet accumulators and suppresses broad raw
ledger writes; model equations and state assignments are unchanged.

Machine-readable per-arm reductions and receipt identities are in
[`docs/evidence/pr99_t1_remaining_20261022/`](evidence/pr99_t1_remaining_20261022/).
They preserve the pre/post, process, baseline report, replay, stage stream,
source, and executable hashes. The instrumentation-only source diff is in
[`selected_process_source_patch.diff`](evidence/pr99_t1_remaining_20261022/selected_process_source_patch.diff),
and the pinned build receipt is
[`selected_process_build_manifest.json`](evidence/pr99_t1_remaining_20261022/selected_process_build_manifest.json).
Raw tile arrays remain in private
`/var/tmp/pr98_face_v8_*` and `/var/tmp/pr99_selected_process_runs3_20261022`
directories. The graph query helped locate the relevant reducer, but its broad
traversal returned many unrelated Cloud-BAL nodes; source code and captured
artifacts are the evidence for these numerical results. No graph snapshot was
updated in this task.
