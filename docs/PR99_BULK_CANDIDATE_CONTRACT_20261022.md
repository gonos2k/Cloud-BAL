# PR99 bulk candidate absence contract

## Status

The v2 shared candidate certificate has passed the author’s pinned-Intel
local validation and an independent typed-input Fraction oracle. Independent
source/control-space review found no blocker. The oracle covered 40 cases at
each of FREE/O0 and REPRO/O2: 17 accepted, 23 rejected, no false accepts, and
the actual fatal typed input accepted; four exact-valid cases were rejected
conservatively. Native three-arm tests of the changed candidate have **not
started**. Any native
run using this storage-admissibility change is a distinct future candidate,
**PR99-C2**, with the original C1 inputs. It is not the unchanged C1 baseline
and is not the failure-only diagnostic executable.

This note documents a fail-closed proposal for one observed failure mode. It
does not claim that C1 has been fixed or validated, and it does not authorize a
forecast. See the [bounded evidence package](evidence/pr99_bulk_candidate_contract_20261022/README.md).

## Evidence that motivated the contract

The three receipt-bound C1 arms—OFF, HYDRO, and COUPLED—each stopped at 31 of
32 requested 20-second steps (620 seconds, return code 1). At T32/RK1, each has
the same local reason-6 graupel fallback event at `(i,j,k)=(2,241,14)` for
pair QG/QIB, with matching candidate/source bits. A separately instrumented
OFF diagnostic reproduces those bits. In the pinned source, this reason is a
bit mismatch between captured `qs64/ns64` and pointwise `qdiff/ndiff` source
recomputation in `add_graupel_diffusion_mixture`. It is not
`joint_moment_store` failure stage 6; the corresponding observed store failure
is stage 2. The bounded summary and per-arm excerpts are in the evidence
package.

This repeated local event motivates checking whether the existing full
candidate can be represented as paired REAL32 zeros within the existing
strict mass cone and a bounded volume loss. It does not establish a producer
cause, an invalid physical state, or that this local branch is the only run
failure.

## Contract

The new `joint_bulk_candidate_absence_is_valid` predicate is reached only
after the ordinary store rejects a candidate, only for the existing opt-in
bulk-volume absence policy, and only for pair 4 (QG) when strict mass bounds
are configured without a volume bound or inactive-mass shortcut. It checks
that the same theta-scaled full candidate regenerates the already computed
REAL64 reference Q/N bit-for-bit using the existing ordered expression.

The certificate then encloses the extensive endpoint numerators using
outward-rounded REAL128 intervals. Uncertain or nonfinite arithmetic rejects.
Both Q and N numerator intervals must be positive and satisfy the configured
minimum and maximum mass-ratio cone. The upper endpoint must also fit the
existing subnormal-volume loss policy: less than half a REAL32 minimum
subnormal times the new carrier for N, and less than half that quantity times
the maximum ratio for Q. Only then does the shared group transaction install
the paired `(0,0)` REAL32 endpoint and increment the existing bulk-adjustment
ledger.

Before the ordered REAL64 candidate is recomputed, the certificate retains the
REAL32 representability gate and requires conservative magnitude bounds to
stay below one quarter of `HUGE(REAL64)`, with carrier scaling where needed.
This headroom only narrows eligibility to protect the existing REAL64
recomputation from overflow; it does not expand the half-quantum budgets or
relax a storage bound.

The interval arithmetic is a fail-closed admission proof for these bounded
operands. REAL128 is not asserted to provide exact arithmetic for arbitrary
inputs. The operational REAL64 reference remains unchanged and bit-bound to
the proposed candidate; ambiguous interval bounds reject. There is no global
precision-mode change, tolerance relaxation, floor, or change to physical
source terms. The source generator applies the same shared core certificate
inside the pinned C1 host retry/commit path; it does not make the historical
archival core fixture a runtime source.

## Local validation and remaining gates

The frozen v2 shared core SHA-256 is
`6c844fe8a68ded3c653d800065d428c390b08845a584dc65ab070995adc7dd53`.
The v2 source generator SHA-256 is
`64f9b4fea53ae44ba15d0a4b331520c4b5931436e001ea4b8124fc8b348bfaf0`; its
transformed C1 host output is SHA-256
`98a44389d693ec28533d492c129204fc0bdba22e6ed3ae71acc9e65df7b9cb1a`.
It binds the pinned C1 `module_em` input and verifies that its embedded
pre-certificate module matches the archival source fixture before replacing
that module with the frozen shared core.

The pinned Intel IFX 2026.0 local tests pass at FREE/O0 and REPRO/O2, as do the
existing PR92 O0/O2 policy tests and the full shared-core O0/O2 regression.
The Python fixtures, historical source fixture, transformed-host validation,
and three focused source-wiring tests pass; `py_compile` and
`git diff --check` pass. Commands, logs, executable hashes, source hashes,
the independent oracle inputs/results, the bounded reviewer report, and
bounded C1 arm excerpts are in the evidence package. No full WRF build or
forecast was run. These tests validate local admissibility and wiring only.

Before any PR99-C2 native run, remaining gates include review of the assembled
host build and explicit root launch authorization. The future
three-arm results must retain separate receipts and keep incomplete/failure
states open; a local PASS cannot substitute for actual native consumption,
full-run closure, or scientific approval.
