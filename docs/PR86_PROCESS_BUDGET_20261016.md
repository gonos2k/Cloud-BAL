# PR86 first-call process suppression audit (2026-10-16)

## Scope

This audit weights the saved PR85 v17 OFF and COUPLED first-call cold, warm,
rain-freezing, ice-sedimentation, and graupel-sedimentation ledgers. It does not
run the model or change physics. Each raw ledger is checked against the actual
run receipt hash before it is decoded.

## Geometry and process measures

Cold and warm rows carry native `(i,j,k)` coordinates and `rhoDry`; `j` is the
KDM6 call's actual horizontal row. The audit maps those coordinates to the
same `(j,k,i)` first-call slot. It weights mass-specific Q/QV by the
cell's `rhoDry * DELZ * map area`, and number concentration by
`DELZ * map area`. The cold ledger's `rhoDry` must exactly match the same-cell
first-call DEN readback. Sedimentation budgets already integrate vertically
per horizontal area, so their mass and inventory values are multiplied only by
same-cell map area.

For cold NG, AUT, G, and warm process groups, mass is the half-L1 activity of
the logged Q(5) plus QV vector; count is the L1 activity of the logged N(3)
vector. These are vector-activity proxies for requested, applied, and deferred
changes. They are not independent primitive-process gross mass/count and do
not close the global water or number budget. Applied/proposed and
deferred/proposed ratios use the corresponding proposal activity as their
denominator; zero proposals have a null ratio.

Cold temperature changes are reported as signed and absolute K kg diagnostics.
The cold ledger lacks a source-matched heat-capacity term, so no cold energy
value is claimed. Warm heat is reported as the source-logged `cpm` times
temperature change times dry-air mass (J proxy), not total enthalpy or energy
closure. Rain-freezing mass and count are reported as explicit
proposal/approval/withheld transfers; observed temperature change is shown
separately because the ledger does not include the source-matched `xlf/cpm`
needed to reconstruct proposed heat. The empty-graupel-receiver subset is
identified from its logged pre-process QG and BG values.

Stored-minus-approved Q+QV residuals from cold and warm are reported as
separate signed and absolute pieces. They are not added to process requests.
Ice and graupel sedimentation requests are likewise reported as separate
column-integrated pieces. First-call area uses initial-wrfout MAPFAC_M and
captured call DELZ/DEN; same-call hybrid MU geometry was not captured, so this
is not an equality proof for native hybrid dry-air mass.

## Results

The table reports deferred mass activity divided by proposed mass activity.
The proposed process activity is the denominator; total atmospheric water is
not used as a normalizer.

| Process group | OFF deferred / proposed | COUPLED deferred / proposed |
| --- | ---: | ---: |
| Cold NG | 24.3271% | 24.3248% |
| Cold AUT | 95.1913% | 95.1935% |
| Cold G | 85.0916% | 85.0877% |
| Warm | 0.0000007804% | 0.0000007811% |

Cold AUT and G therefore have substantial withheld vector activity in both
actual v17 arms. The proposed-to-applied fractions, count activity, and heat
diagnostics are preserved per process in the JSON evidence. Cold heat remains
in K kg; warm heat remains a `cpm` weighted J proxy.

Rain freezing proposed/applied/deferred mass activity was 488.153/39.292/448.861
kg in OFF and 488.194/39.292/448.902 kg in COUPLED. For rows whose logged
pre-process graupel mass and volume were both zero, 7,426 OFF and 7,419 COUPLED
records proposed 417.371 and 417.412 kg; all of that mass was withheld. The
ledger records no temperature increment for this arm subset and lacks the
source-matched `xlf/cpm` terms needed to estimate proposed heat.

Ice sedimentation withheld 353.438 kg (OFF) and 353.309 kg (COUPLED), with
applied/proposed mass fractions above 0.99999999. Graupel sedimentation
withheld about 0.000663 kg in each arm. These are separate per-column process
pieces. Cold stored-minus-approved Q+QV residuals were -3,737.465 kg signed
(192,074.153 kg L1) in OFF and -3,763.466 kg signed (192,055.084 kg L1) in
COUPLED. Warm residuals were -19,402.238 kg signed (490,466.622 kg L1) in OFF
and -19,378.939 kg signed (490,444.361 kg L1) in COUPLED. Residuals remain
separate and are not added to requested/deferred activity.

## Evidence outputs

- `docs/evidence/pr86_process_budget_20261016.json`: receipt-bound summaries,
  ratios, residual pieces, rain-freezing receiver subset, and sedimentation.
- `docs/evidence/pr86_process_budget_off_map.npz` and
  `docs/evidence/pr86_process_budget_coupled_map.npz`: same-cell spatial maps
  with one-based `i` and `j` axes and separate fields by process, stage, and
  measure.

The summary JSON SHA256 is
`31a3ea8ab9d78376043a457dc626fe97c6f262fdc5a61f194a215bc3b1fd22eb`.

Graph snapshot freshness records structural extraction only; it does not
establish runtime or scientific validation.
