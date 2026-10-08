# PR71 freezing to graupel property-domain audit (2026-10-08)

## Decision

The selected KDM6 source does not define a supported `QG/BG` property or signed
`pgdep` volume update for the observed freezing-created transient. Keep the
existing nonzero-mass-rate/invalid-density path fail-closed. Do not substitute
900 kg m-3, use a pre-freezing density, clamp the transient, zero its sublimation
rate, or infer a new lower graupel cutoff from this audit.

A future candidate may proceed only after the model policy states how freezing
creates the initial graupel bulk volume, how a below-PSD-cutoff transient may
participate in deposition/sublimation, and how its mass, volume, vapor, and
latent-heat changes reach the accepted endpoint. The policy then needs a
source-bound endpoint test for both signed directions and extinction. This
investigation does not identify that policy.

## Source identities and provenance

The generated selected source audited here is
`/var/tmp/pr70_native_volume_trace_20261008_v3/source/selected_candidate_fbf_pr69_water.f90`,
SHA-256 `ee688498b32b7a1ccaf69858f62f4e457f7153df4fb8b965acfd069d8eefb425`.
The PR70 source audit receipt identifies it as the source used for the native
volume observer. Its selected-source anchors and the already retained observer
receipt are indexed in `docs/evidence/pr71_freezing_domain_audit_20261008.json`.

The maintained research-host source is available at
`/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/phys/module_mp_kdm6.F`.
Its SHA-256 is
`02c9dc1f6711c9785d3c5841cbf2c14ebc454fa4628466407ae7f8879e965c5a`, matching
the maintained wrapper fixture byte-for-byte. `tests/fixtures/kdm6_wrapper/origin.json`
records the fixture origin and explicitly labels it a private serial-wrapper
fixture, not native-host authority. The generated selected file is a
patched/composed source and is not byte-identical to the maintained source. The
property gate, tendency gate, freezing assignments, and legacy terminal QG
cutoff were compared directly in both source files; the selected candidate
adds a paired BG clear at terminal extinction. Exact runtime claims use the
selected source and observer receipt; matching maintained-source behavior is
source comparison only.

## Source-bound domain and units

The KDM6 interface carries graupel mass `qrs(:,:,3)` (`QG`) as the selected
scheme's water mixing ratio and `brs` (`BG`) as its bulk particle-volume mixing
ratio. Their conventional dimensions are kg water per kg reference mass and m3
per kg of the same reference mass, respectively; the source ratio `QG/BG`
therefore diagnoses density in kg m-3. The selected equations and legacy
`brs_min` comment support those relative units, but the PR69 carrier-basis
question remains open: this audit does not establish that the host reference
mass is physically dry air. `pgdep` has units of the selected QG mixing ratio
per second, conditional on that source convention. The selected code has no
independently prognosed graupel number field: the wrapper sets the third `nrs`
component to zero, and the graupel PSD parameterization derives its parameters
from QG and BG/density.

`ProgB_param` uses `qcrmin = 1e-9` in the selected QG mixing-ratio units,
`brs_min = 1e-15 m3 kg-1` as commented in source, and a tabulated density
interval of 100–900 kg m-3. Its setup gate is
`QG > qcrmin OR BG > brs_min`. Only inside that gate does it evaluate `QG/BG`,
clamp the result to [100,900], replace BG by `QG/rhox`, and assign PSD
parameters. The clamp is not reached when both gate operands are below their
thresholds. On that false branch it assigns none of 18 `INTENT(OUT)` outputs:
`rhox, cmg, pidn0g, avtg, pvtg, precg2, bvtg, bvtg1`, `bvtg2`, `bvtg3`,
`bvtg4`, `rslopegbmax`, `g1pbg`, `g3pbg`, `g4pbg`, `g5pbgo2`, `g1pdgbgmg`, and
`dgbgmug1`. The earlier selected-source `rhox=0` initialization and an observed
runtime zero do not define the callee's `INTENT(OUT)` result.

By contrast, the cold `pgdep` branch runs for every `QG > 0` while the ice
saturation limiter is open. Its signed mass tendency is multiplied by `dtcld`
into QG, vapor, and latent-temperature updates. Negative `pgdep` is
sublimation, QG to vapor, and the source limits its magnitude by `QG/dtcld`.
Positive `pgdep` is deposition, vapor to QG. The selected volume consumer maps
that same mass rate through `pgdep/rhox`. It does not provide an incoming
material-density rule for positive deposition, nor a valid density when
`ProgB_param` skips its setup.

## Donor path and extinction

The matched observer trace identifies a precise donor path. Immediately before
the fifth `ProgB_param` call at the traced cell, the cold freezing tendency has
changed QG from zero to the source mixing-ratio value `1.5222058e-14` and BG
from zero to the source volume-mixing-ratio value `1.5222057e-17 m3 kg-1` on
the same reference-mass basis. The source writes these values as
`QG += pfrzdtr`, `BG += pfrzdtr/denr`, and applies the matching rain-loss and
latent-temperature terms. The retained input/build evidence records
`denr=1000 kg m-3`; thus the source-created pair has `QG/BG` about
1000.0000657 kg m-3. This is outside the selected `ProgB_param` interval,
although both values are below its setup thresholds. The correct characterization
is a below-threshold, source-created transient with a ratio outside the tabulated
PSD interval, not a supported 1000-density graupel PSD state.

At the next cold-process point, the selected-source tendency is
`pgdep=-7.6110288e-16` in QG mixing-ratio units per second, conditional on the
source mixing-ratio convention, and `dtcld=20 s`; the mass cap removes essentially the entire tiny QG donor. The
observer records the undefined-branch `rhox` as zero, after which the candidate
volume helper rejects the nonzero rate with nonpositive density. This run ended
at the controlled fatal gate (return 128, no post-call checkpoint), so it is
source-path capture evidence, not an accepted model result or a closure test.

At selected-source terminal cleanup, `QG <= qcrmin` sets both QG and BG to
zero. This is an extinction rule for the final arrays; it does not authorize
setting a transient nonzero QG to zero before its cold tendencies or silently
assigning it a prior density. The hash-pinned maintained host source and its fixture show the
older QG cutoff without paired BG clearing; the selected candidate includes the
paired BG cleanup. That source difference matters for endpoints and is recorded
here rather than attributed to the fixture.

## Is a property-domain gate justified?

A precommit property check can mechanically reject a trial that leaves the
selected closure domain: finite/nonnegative QG and BG, exact zero-pair handling,
the legacy property-setup predicate `QG > qcrmin OR BG > brs_min`, and density
`QG/BG` within 100–900 kg m-3 for positive paired states. Such a
check is only a numerical admissibility gate. It cannot choose the physical
transition for the existing freezing-created pair because the pair already
enters the subsequent PSD and `pgdep` path below the gate thresholds. Rejecting
that state preserves fail-closed behavior; accepting it requires a policy that
the current source does not provide. A Q/B/T common-fraction gate on later
process tendencies cannot supply the missing source density, decide whether
freezing-created subthreshold graupel is active, or derive a positive deposition
volume rate. The selected source's existing mass and temperature equations do
not resolve that volume rule.

No source-grounded physical policy was found that supports a 900 kg m-3 prior
or a 100–900 clamp on this path. In the cited Lin, Farley, and Orville scheme,
solid precipitating classes are parameterized with assumed size distributions;
that general background does not validate this selected code's below-threshold
state. A later WRF graupel-density study describes a different model that
prognoses integrated particle volume and specifies process-dependent volume
assumptions. Those choices illustrate that incoming volume is a model policy;
they cannot be imported into this selected source without a deliberate
scientific change. See the primary sources linked below.

## Evidence scope and limits

The selected-source trace and matched observer receipt support the call order,
source assignments, cutoff, threshold mismatch, exact traced values, and
controlled rejection. The retained trace does not capture the global `j`
coordinate or `QG` at the exact `pgdep` line; the QG/BG creation values are
captured at the adjacent `ProgB_param` boundary, and the tendency is captured
at the pre-volume consumer. No accepted native endpoint, water/energy closure,
material-density validation for deposition, or full production-source audit is
claimed. This is a scientific/source contract finding, not runtime validation.

Primary literature:

- Lin, Farley, and Orville (1983), [Bulk Parameterization of the Snow Field in a Cloud Model](https://doi.org/10.1175/1520-0450(1983)022%3C1065:BPOTSF%3E2.0.CO;2). Its bulk graupel/hail category description is background for the legacy scheme family, not a rule for this transient.
- Jensen et al. (2024), [Introducing graupel density prediction in WRF WDM6](https://doi.org/10.5194/gmd-17-7199-2024). The different prognostic-density model explicitly uses integrated volume and process-specific assumptions; it does not establish a policy for this selected KDM6 source.
