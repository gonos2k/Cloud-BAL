# PR82 team review

Four focused teams worked on signal readback, same-time delivery, native state
tracing, and independent review/KG preflight. Independent reviewers checked
the resulting source and bound artifacts before publication. The maintained
KLAPS50 and Cloud-BAL graphs were used for navigation; external WRF sources
were checked directly because graph coverage is incomplete.

## Findings addressed

- Observation readback now rejects invalid modeled fields, nonbinary masks,
  incompatible units and replacement output paths. The pre-density absolute
  dry-mass witness explicitly allows its persisted `kg` label. The independent
  review checked strict3 source/receipt hashes and the byte-identical replay.
- Complete same-time LAPSPREP caller arguments supply retained below-ground
  and surface slabs. The existing mapper handles ascending WPS and descending
  canonical pressure without a private reversal. Readback asserts exact
  values, including surface winds. Fresh runs bind the executed helpers.
- The WPS consumer uses the actual big-endian convention. Pinned WPS sources
  and dependencies were rebuilt with that declared file policy. The genuine
  geogrid's container conversion preserves all 60 variables and attributes.
  Metgrid offset comparisons are exploratory and do not decide acceptance.
- Archive comparison preserves duplicate member occurrences. The prior link
  audit is pinned, and each archive/executable replacement occurs exactly
  once. The final fresh build verifies all 373 rows and both `track_driver.o`
  occurrences, with only KDM6 replaced.
- Native preparation uses the common detached copier and rejects existing
  roots. Prior observer outputs are excluded from initialization inputs;
  required and conditional outputs are checked separately. The final 13 UTC
  run passes declared-path isolation and source/hash checks.
- Ambient NN/CCN is not paired with snow mass. Behavioral tests cover an empty
  condensate state with positive CCN and exclusive failure-class priority.
- The 12 UTC trace localizes the first changed NC field to RK2 scalar update
  and the positive minimum subnormal to RK3. Unchanged state snapshots do not
  exclude a physics/PBL tendency contribution. Those operands remain unobserved.

## Verification and scope

The fixed canonical launcher completed with exit 0 using the pinned Intel
profile; its 1,771-file inventory was unchanged. An earlier snapshot omitted
Git identification metadata and stopped at the transaction fixture; that
failed attempt is preserved separately. Later final helpers and launcher
registrations are covered by focused checks, not by that frozen full run.
See [validation](evidence/pr82_validation_20261012.json) and the
[canonical execution package](evidence/pr82_canonical_unit_20261012.zip).

The independent signal review passed 11 tests and verified the strict3 replay.
Copier/isolation tests passed 13 and 2 tests, root-reuse checks passed four
cases, the ordered-archive fixture passed, and the two behavioral CCN/class
tests passed. The source-bound conversion helpers passed Intel O0/O2. These
counts describe different checks and are not combined into a science score.
Source/test/tool whitespace checks pass. The two source-bound patch files retain
whitespace-only context lines from the executed originals; their exact hashes
are preserved rather than rewritten for patch-file whitespace warnings.

The same 13 UTC candidate was byte-identically replayed, written to WPS, and
consumed through pinned Intel metgrid, real and native initialization. The
independent review verified time, identity, units/staggering, actual state
changes and the final initializer's source/output integrity. It found no
remaining publication blocker for this scoped result.

Two nonblocking limitations remain: one-off readbacks use fresh-path checks
without atomic exclusive creation, and the native source namelist is aligned
with its detached copy/boundary contract but is not separately included in the
native before/after source map. Whole-host rebuilding and transitive link
provenance are not certified. The actual artifacts are consistent; these are
not claims of a protected runtime sandbox.

## Remaining physical work

The 13 UTC initialized file retains positive hydrometeor mass but zero cloud,
ice and rain number fields. Native initialization populates ambient CCN; the
first KDM6 entry rejects positive cloud mass with zero cloud number. This is
distinct from the separate 12 UTC positive-NC conversion underflow.

Joint native Q/N/B construction and completed transport, independent observation
fit, native water/energy/dry-mass closure, native force/continuity assessment,
and 10/30/60-minute response remain open. The initializer readback is
`PASS_SCOPED`; neither native candidate has completed first microphysics.
