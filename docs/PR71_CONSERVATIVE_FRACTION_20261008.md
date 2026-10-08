# PR71 conservative fraction scope — 2026-10-08

Base: merged PR70 `0ef49d1770db6d9ed0d35f60e35dcbd5d3e0db15`.

## Corrected claim

`kdm6_rain_process_fraction()` chooses a conservative valid float32 fraction
within its computed continuous admissible intervals. It does not prove the
largest float32 fraction accepted by the rounded stored-state predicate.
The process algorithm, cutoff, physical tolerance and admission policy are
unchanged by this wording correction.

For the independently reported case, rain has fixed mass
`2.5142206538930623e-8` and process increment `-2.44809541527502e-8`.
The number moments are proportional to these masses at source rain lambda
`5000 m^-1`. Other hydrometeor moments are zero, density is `1 kg/m^3`,
temperature is `270 K` and the rain cutoff is `1e-9`.

| Candidate | Float32 fraction | Stored rain mass | Direct state predicate |
|---|---:|---:|---|
| Helper return | 0.9861627817153931 | 1.000000082740371e-9 | PASS |
| Immediate next float32 value | 0.9861628413200378 | 1.000000082740371e-9 | PASS |

The pinned Intel O0/O2 reproduction checks both candidates through the original
state predicate. Rounded multiplication and addition allow the neighboring
fraction to store the same valid rain mass. The test proves this local
maximum-claim counterexample; it does not search all float32 fractions or
assert a global maximum.

## Evidence and historical records

- [Pinned Intel reproduction](evidence/pr71_conservative_fraction_validation_20261008.json)
  binds the source, unchanged PR70 patch, extracted helper, compiler/runtime,
  flags, driver, executables and logs.
- `tests/run_pr71_conservative_fraction.sh` runs the new regression in fresh
  scratch without replacing PR70 execution receipts.
- The current PR70 cutoff report and review wording are narrowed; the original
  documents and their receipts remain available at the PR70 commit. Their
  frozen hashes identify historical execution evidence, not the current edited
  documents. The inherited temperature regression assertion label now states
  valid positivity rather than maximum representability; its numerical test
  is unchanged.

Disposition: the P2 explanation issue is resolved by narrowing the guarantee.
The previous P1 cutoff counterexample still returns a valid reduced step.
This change supplies neither native acceptance nor atmospheric optimization.

## Separate full-module fixture correction

The inherited PR70 full-module fixture divided rain mass times `lambda**3`
by `cmr*6`. The selected source has `mur=1`, `dmr=3` and
`pidnr=cmr*Gamma(5)/Gamma(2)=cmr*24`. Its stated rain lambda of
`5000 m^-1` therefore represented approximately `7937.005 m^-1`, still
within the source PSD interval. This corrects the fixture description;
the earlier specific-number versus volume-number equivalence result remains
applicable to the actually tested state.

The new PR71 full-module fixture and conservative-fraction regression use
`cmr*24`. Historical PR70 numerical fixtures and execution receipts are
preserved. This correction does not introduce a new particle prior or change
the process helper.
