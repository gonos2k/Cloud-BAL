# Force and initialization batch review

Four parallel roles covered independent stored-state flux/force reconstruction,
the continuity-preserving refinement and real producer, native initialization,
and pipeline/writer contracts. Primary and independent agent review found no
remaining implementation blocker in this scoped batch.

Resolved implementation findings include preserving failure reasons, verifying
rounded hard caps, distinguishing boundary-face authority from center omega,
resolving NetCDF dimension lengths rather than using dimension IDs as lengths,
including omega in the changed mask, and rejecting quiet-NaN receipts without
FP traps. WRF initialization readback rejects consistently wrong unit/stagger
metadata. Native radar initialization preserves the legacy zero-argument ABI.

[Validation](evidence/pr80_validation_20261012.json) binds the final source and
evidence hashes. Fresh pinned Intel O0/O2 actual producer executions, writer
replay, and readback pass; both wind and NetCDF products are byte-identical.
The [compact run archive](evidence/pr80_force_producer_20261012/manifest.json)
was independently checked against all 19 original members. The full unit
launcher cannot start because its pinned ncgen is absent; final focused
writer, force, pressure-overlap, and Python checks are reported separately.

The wind-only result reaches its cap and leaves force RMS about 10.2 times
background. Original retained VT/phase and candidate wind metadata omissions
are explicit readback limitations. Observation fit, physical-time budgets,
same-candidate native delivery and initial time response remain open. The
separate 12 UTC native case reaches initial output, then fails its first
integration. CP06-A scientific status and operational promotion are unchanged.
