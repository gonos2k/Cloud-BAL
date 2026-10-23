# PR100: C2 repetition and source-owned physical diagnostics

This follow-up starts from merged PR99 main
`950fd7b41af5a10ab6dd36a17098e86dd8306197`. It keeps the three evidence
cohorts separate:

| Cohort | Model / input | Evidence scope |
|---|---|---|
| Original OFF/HYDRO/COUPLED | PR96-C1, original matched inputs | Closed 600-second baseline and first-call replays |
| Native U/V projection P | C1 diagnostic model, projected U/V input | Closed 20-second capture and first-call replay |
| C2 OFF/HYDRO/COUPLED | PR99 C2 storage policy, original matched inputs | Closed matched 640-second runs; 32 completed calls each |

No new wind, physics, precision, prior, or tolerance change is introduced
here. C1 replay diagnostics do not establish C2 water closure or projected
input repetition.

## C2 runtime result

The three requests launched once at 08:38:16 UTC on 2026-10-22 and
closed with return code 0, 32 completed KDM6 calls, and the required
640-second POST_KDM6 record. All use the same reviewed C2 executable and original
matched arm inputs. The closed-only auditor consumed the complete
receipt-bound streams and retained separate results:

| Check | OFF | HYDRO | COUPLED |
|---|---:|---:|---:|
| Procedural 640-second completion | PASS | PASS | PASS |
| C1 first-600 trace: 12 fields, 180 records | PASS | PASS | PASS |
| C1 first-600 raw history: 10 fields, 11 times | PASS | PASS | PASS |
| T1 pre/post and PR67 payload identity to C1 | PASS | PASS | PASS |
| Declared exact-source endpoint gate | PASS | PASS | PASS |
| Declared active/inactive ice policy | PASS | PASS | PASS |
| Generic Q/N/B failure records retained | 173 | 171 | 171 |
| Physical approval | FAIL_OPEN | FAIL_OPEN | FAIL_OPEN |

Trace comparison includes metadata, dtype, shape, and serialized array
bytes. History comparison validates original dtype, dimensions, units,
and stagger, then exact numeric values; it does not distinguish signed
zero or assert whole-NetCDF byte identity. The trace contains six states
per step through all 32 steps (192 records per arm). The source endpoint
gate applies at RK3, PRE_KDM6, and POST_KDM6; predictor diagnostics and
ice's separate policy are not promoted into an all-state exact PASS.
Generic failure counts are records, not unique error cells.

The [bounded runtime evidence](evidence/pr100_c2_native_closure_20261022/runtime/README.md)
binds the full private audit and its published summary. Matching T1
payloads link this first-call diagnostic lineage; they do not establish
C2's full 640-second water or energy budget. Projected U/V input repetition
remains limited to the separate P20 evidence.


Each arm also has all 96 expected step/RK storage rows and 39 aggregate
adjustment-5 events. Their printed signed sums are Q=−4.2446866198e−37
and B=−5.1286440882e−40 in separate pressure-carrier-weighted quantities,
not kilograms. These counts combine ordinary bulk absence and the new
certificate; certificate-only counts or cell locations are not observed.
There are 27 conditional tiny-B host witness rows per arm, associated
with completed calls. This validates the retained commit path and
aggregate ledger, not every rejected trial or rollback branch.

## Retained momentum response

The [momentum locality analysis](PR100_MOMENTUM_LOCALITY_20261022.md)
preserves PR99's observed mass-response improvement and locates the
remaining source-array differences. About 82% of the P−H squared
horizontal-diffusion difference occurs at active native levels k=37–39
on the fixed support. Advection differences peak lower, around k=26–28.
These locations narrow inspection of the wind transfer, stencil,
coupling, and diffusion coefficients. They do not prove a causal error,
physical acceleration, or observation improvement.

## First-call cloud response

Source-ordered QC observers follow the same fixed 613-cell input-derived
support in the original C1 arms and the separate projected-input replay.
Their actual stored increments must reconstruct each cell's first-call
QC change, with exact returned-state checks against its own native
capture. Ordinary condensation/evaporation branch labels must be
interpreted by the sign of stored QC change; zero-filled packet columns
at uncaptured direct writes mean N/A, not zero attempted physics.

The [QC process report](PR100_QC_PROCESS_20261022.md) and its independent
review bind four fresh-scratch replay results. Partial-evaporation-direction
writes in the general liquid adjustment branch, full evaporation, and
the warm commit dominate the change projected onto the fixed initial
QC contrast. This attribution explains where the contrast changes; it
does not establish why the thermodynamic target requests that change
or measure independent observation skill. The replay build is partial:
recorded interface copies and postcompile outputs are distinguished,
and exact precompile interface consumption is not independently proven.

## First-call water account

The [source-owned water account](PR100_T1_SNOW_MELT_20261022.md)
adds legacy snow sedimentation, the separate graupel-to-rain melt,
three direct paired cloud transfers, and the conversion between approved
R64 helper-ground packets and the actual R32 PR67 phasefall path. Each
term uses the original C1 arm's same-call input DEN/DELZ and map area.
Approved packet imbalance, actual stored change, arithmetic difference,
and ground-rate representation remain separate, with each outflow
counted once.

For OFF, the column L1 remainder falls from 11,972.616 kg to
0.000110796 kg, and the maximum absolute column remainder from
22.588586 kg to 5.34e−8 kg. Signed remainders are −1.16083e−5 kg (OFF),
−1.16277e−5 kg (HYDRO), and −1.15547e−5 kg (COUPLED). The actual
nonzero REAL64 reduction remainder is retained; it is not fitted,
rounded away, or declared exact zero. Earlier staged accounts and
independent reviews are preserved.

This explains the selected first-call arithmetic account. It does not
restore physical conservation: the existing cutoff still removes actual
water, and the full native hybrid host, energy, and 640-second budgets
remain open. The replay evidence also records excluded instrumentation
attempts and the corrected working-directory incident, with guarded
replacement runs and protected-source checks.

## Approval boundaries

Runtime, trace/history equivalence, source endpoint validity, generic
Q/N/B audits, and scientific approval are separate results. A legitimate
C2 prefix difference must be explained rather than forced to match C1.
Generic failures are retained. Native hybrid host water and energy
closure remain open; observation skill remains **NOT_EVALUATED** and
physical approval remains **FAIL_OPEN**.

Graph maintenance will include inherited PR99 and new PR100 changes,
because the last maintained graph update describes PR98. KLAPS50 and
Cloud-BAL will keep separate dated snapshots, graph deltas, and extraction
limits. Graph freshness is not runtime or scientific validation.
