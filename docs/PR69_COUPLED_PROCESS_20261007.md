# PR69 coupled cold-process acceptance

## Implementation

The research patch snapshots five source-paired cold tendencies before the
legacy donor limiters, restores each mass/number pair using the smaller of its
two limiter fractions, then computes one admissible process fraction for
`praut/nraut`, `praci/nraci`, `piacr/niacr`, `psacr/nsacr`, `pgacr/ngacr`, and
rain self-collection `nrcol`. The selected fraction scales every listed rate.
The source-derived five-phase mass, three-number, graupel bulk-volume, and
latent-temperature increments are evaluated together. At the pre-acceptance
point, the legacy `bracs/bgaci/baacw` arrays still contain their initialized
zeros, so the fixed BG increment is derived from the current mass rates
`pracs/dens + pgaci/deni + paacw/denr`. A shared mass-to-volume helper maps an
exact zero rate to zero even when its density is zero, and rejects a nonzero
rate with nonpositive or nonfinite density. The `pgdep/rhox` rate returned by
that helper is reused by the actual cold BG store. After the source's actual
Q/N/BG/T writes, the stored state is checked again using zero increments so
the check covers the exact rounded endpoint.

Rain uses the KDM6 source state interval λ=961–35,000 m⁻¹ and its internal
identity `N = DEN * Q * λ^dmr / pidnr`. Cloud and ice use the source λ intervals
12,000–500,000 and 9,080–1,820,000 m⁻¹. The cloud/ice envelope is applied to
every positive active Q/N endpoint as a candidate consistency policy, including
positive N below the native slope-activation threshold. This is stricter than
the native conditional slope calculation. Positive cloud/ice mass at or below
`qmin`, rain/snow/graupel mass at or below `qcrmin`, and positive mass with zero
number are rejected because downstream source cleanup would delete that
residue. Graupel BG must satisfy the source density interval 100–900 kg m⁻³.
The separate `nrmin` process threshold is not used as a PSD lower bound.

The kernel reports the cell, accepted fraction, coupled endpoints, and partner
terms before a fatal rejection. It does not roll back prior in-call source
mutations; a rejected state terminates the candidate timestep/run. No floor,
epsilon number source, or residual repair is introduced.

## Evidence and limits

The source-paired rate algebra and downstream writes are extracted verbatim by
`tests/generate_pr69_source_harness.py` into an executable Intel Fortran test.
The harness exercises internal DEN values 0.25 and 2.0, checks the common
fraction across stored mass/number/BG/temperature, and verifies water
conservation and exact stored-endpoint admissibility. The focused runner also
tests source-order-sensitive BG partner rates with zero stale arrays, the
zero-rate/zero-density and nonzero-rate/zero-density cases, exact-zero number
boundaries, source cutoffs, density response, NaN/Inf rejection under `-fpe0`,
and the captured PR68 rain failure projection at
`(i,j,k)=(169,59,17)`. That retained PR68 record omits DEN; its rain-only replay
uses DEN=1 explicitly and is not represented as an exact full-cell replay.

The `DEN*Q*λ^d/pidn` constraints establish consistency with the selected KDM6
internal equations. Host QNRAIN is documented as per kg dry air, while the
driver supplies moist DEN directly and wrapper copies NR unchanged; the
host-to-internal unit bridge remains partial. No physical unit closure is
claimed. The earlier matched native run used a draft source-order mapping that read
stale zero BG partner arrays. Its source, executable, receipt, and failure
diagnostics are preserved in
`docs/evidence/pr69_coupled_process_native_prior_attempt_20261007.json`; that
attempt is not treated as evidence that the input was infeasible.

A fresh strict-Intel build and guarded matched run used selected source
`fbfa823b7cba54f0fdd5ffb1cfeaf58fc5722e845508f954e6c992a7aa32a594` and the
observer composed from that exact source. It reached the first KDM6 gate and
rejected `(i,k)=(125,17)`: `pgdep=-7.6110288e-16` while `rhox=0`. The
mass-to-volume helper therefore returned a zero volume rate with
`feasible=false`; the combined BG-rate support flag became false, the process
fraction helper was skipped, and the source took its fatal rejection path.
The corrected `BGfixed` was finite (`3.9422497e-12`), and all stale BG partner
arrays were zero, confirming the source-order mapping was repaired. The run
receipt reports input integrity `PASS` and output isolation `FAIL` because the
fatal gate prevented `kdm6_first_call_post.raw`. This is a controlled rejection
of an unsupported nonzero-mass/zero-density partner term; it is not accepted
native behavior or a water-budget closure result. The printed subthreshold ice
Q/N values were not evaluated by the skipped fraction/PSD gate and are not
claimed as the actual cause. Full hashes and the source-derived control-flow
reason are recorded in `docs/evidence/pr69_coupled_process_native_20261007.json`.
Do not submit this rejected run to the successful-run water budget parser.

## Validation

`bash tests/run_pr69_coupled_process.sh` uses the pinned Intel `ifx` 2026
profile and a fresh `/var/tmp` directory. It compiles and runs helper and
source-extracted endpoint tests at O0 and O2. The machine-readable result is
`docs/evidence/pr69_coupled_process_validation_20261007.json`. The corrected matched native rejection is recorded in `docs/evidence/pr69_coupled_process_native_20261007.json`; the prior draft-mapping attempt is kept separately in `docs/evidence/pr69_coupled_process_native_prior_attempt_20261007.json`.
