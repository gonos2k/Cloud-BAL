# PR87 graupel failure-context transform review

Date: 2026-10-19

## Scope

Reviewed `tools/pr87_graupel_failure_context.py` against the frozen V42 KDM6
source at `/var/tmp/pr87_joint_cycle_sources_20261016_v42/module_mp_kdm6.F`
(SHA256 `bdb1882afed860068cecbb6c7b958eef0938cadbd4225222ba7522e28ecc071a`).
The archived source at `docs/evidence/pr87_two_step_v42_20261016/` has the same
hash.

## Findings

- The source has seven native KDM6 `ProgB_param` call starts. The ending text
  also occurs as a substring in an eighth, differently indented call in another
  routine. The current transform pairs each of the seven starts with its first
  following ending, so it instruments exactly those seven calls and leaves the
  unrelated signature unchanged.
- The inserted label arguments are correctly sourced: KDM6 forwards `j` as
  `lat` and `itimestep` as `pr87_model_timestep` to KDM62D.
- Each reporter call reads only `qrs_tmp`, `brs`, and `progb_status`. The helper
  scans bounded `k` and `i` loops and returns after logging the first status
  other than `PROGB_ABSENT` or `PROGB_PSD_ACTIVE`; therefore each invocation
  emits at most one line and cannot loop indefinitely. It adds no state
  assignment or status gate. The decimal formatting converts REAL32 values to
  REAL64 with `dble`; a signaling NaN could raise IEEE invalid. The raw capture
  and hex fields preserve the bits, so bitwise-only output would remove this
  possible floating-point-status effect if strict no-FP-side-effect behavior is
  required.
- The T3 capture is separately gated on `itimestep == 3`, uses the existing full
  KDM6 trace schema, and selects `kdm6_third_call_pre.raw`; it does not alter
  ownership of the original first-call trace.
- Removing the reporter calls/body and the two T3 capture additions from the
  generated source yields byte-identical V42 source.

## Validation and limits

`pytest -q tests/test_pr87_graupel_failure_context.py` passed (1 test). The
regression covers seven matched call sites, exclusion of the unrelated eighth
signature match, and exact source recovery after stripping additions.

No model compilation or runtime replay was performed in this review. The
existing graph query did not return KDM6 relationships, so source and the
focused regression were authoritative here. If the diagnostic run uses
multiple KDM6 tiles/ranks sharing a working directory, the T3 trace's
`status='replace'` output may be concurrently overwritten; this review did not
verify the run's decomposition or threading configuration.
