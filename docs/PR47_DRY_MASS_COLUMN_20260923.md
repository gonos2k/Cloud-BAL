# PR47: conditional dry-mass-fixed gas column

This read-only calculation connects the PR44 cloud OFF/ON humidity pair to one
mass convention at the retained actual13 node `(55,162)`. It does not change
LT1, LQ3, HT, BALCON, WPS or native initialization. The full [19-layer
receipt](evidence/pr47_dry_mass_column.json) records the source hashes,
modeled integration interfaces, component masses and post-state repartition.

## Declared state and equations

The source has regular *pressure levels* from 100000 to 5000 Pa in 5000 Pa
steps. This study uses them as finite-volume integration interfaces; they are
not observed or native model faces. The retained surface pressure is
100512.09375 Pa, so the original 512.09375 Pa surface partial interval is
omitted. If that surface pressure were held fixed after the calculated lower
interface moved, the remaining unmodelled interval would be 415.20631 Pa;
no state or flux is assigned to it. At each regular layer, the endpoint mean
of LQ3 gas specific humidity is prescribed to that *same dry-mass cell* before
and after the cloud switch; the endpoint mean of retained final LT1 temperature
is held fixed. These are explicit piecewise-constant cell models, not claims
about the exact unresolved vertical profiles. They include dry air and vapor
only. The cloud OFF product is a causal counterfactual, not an approved initial
state.

For original layer width `dp`, gravity `g0 = 9.80665 m/s²`, and specific
humidities `q0`, `q1` in kg vapor per kg dry air plus vapor:

```text
md       = (1-q0) dp/g0
mv0      = q0 dp/g0
r1       = q1/(1-q1)
mv1      = md r1
dp1      = g0 (md+mv1) = dp (1-q0)/(1-q1)
```

The 5000 Pa upper interface is fixed and the new widths are accumulated
downward. Thus the lower interface moves by `g0 sum(mv1-mv0)`; it is **not**
the surface pressure. Both ends of this supported column cannot stay fixed
while its vapor mass changes and its dry mass is retained.

For the declared layer-constant temperature and humidity, the gas EOS uses
`Tv = T[(1-q)+q/0.622]`, and each conditional layer thickness is
`(287.05/g0) Tv log(p_bottom/p_top)`. Only thickness differences are computed;
no geometric datum, condensate load, latent/thermal response or full energy
budget is supplied. Holding `T` fixed is an imposed analysis condition, not
an energy-conservation result.

## Same-case result

| Quantity | Result |
|---|---:|
| Fixed original-pressure vapor increment (PR45 check) | +9.80216131324417 kg/m² |
| Vapor increment with each original dry layer mass fixed | +9.879769348405448 kg/m² |
| Retained dry mass over the 19 cells | 9640.216721889037 kg/m² |
| New lower study interface with 5000 Pa top fixed | 100096.88744008052 Pa |
| Lower-interface change | +96.88744008052 Pa |
| Conditional supported-column thickness, old to new | 21022.123749849474 to 21037.18554561183 m |

The dry-fixed vapor increment differs from the fixed-pressure diagnostic
because the gas mass and pressure widths change. The pressure response is a
conditional result for this truncated regular column, **not** a PS correction.
Likewise the thickness change is not an HT correction: the surface partial
layer, height datum and original HT producer operator remain separate.

The updated column alone is repartitioned by pressure overlap onto a second
grid spanning its *new* 100096.887–5000 Pa extent. Dry and vapor component
masses each close across that remap. Its extra 100096.887–100000 Pa strip is
included explicitly; comparing only the old 100000–5000 Pa range would drop
mass. This is a post-state conservation check, not a pre/post common-grid
comparison. This gas-only calculation is not the six-species/native remapper and
does not establish energy conservation or a WRF hybrid-grid handoff.

## Checks and remaining gates

`tests/test_qbal_dry_mass_column.py` checks the per-cell dry/vapor/pressure
identity, a 70-digit Decimal oracle over 120 manufactured four-layer cases,
EOS/hypsometry, identity, pressure-overlap split/merge, and invalid-input
rejection. The actual-case runner reopens the hash-pinned PR41/PR44 products,
checks support, time and target profile, reproduces PR45's vapor integral,
checks pressure/component closure, and writes nothing until validation passes.
Existing ground-reference and relative-force Fortran regressions pass with the
pinned Intel O0/O2 profile in fresh scratch build directories.

This one-column gas transform is `PASS_SCOPED / CONDITIONAL_DRY_MASS_COLUMN`.
A physical joint candidate still needs a supported surface partial layer,
condensate inventory, chosen height datum, full pressure/energy response,
lower and lateral fluxes, and a mass-conserving mapping into the native dry
hybrid coordinate. No BALCON ON, native or forecast authority is granted.

Reproduce the read-only receipt with:

```sh
python3 tests/diagnose_qbal_dry_mass_column.py \
  --cloud-report docs/evidence/pr45_cloud_force.json \
  --output /path/to/new/report.json
```
