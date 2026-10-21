# PR97 C4 Compact Failure Classification

Both preserved PR94 C4 compact attempts stop at T32/RK1, pair 4 (QG/QIB).
The receipt-bound `pr85_joint_source_failure.raw.gz` has seven `FULL` rows for
OFF and six for COUPLED. The matching `pr92_graupel_source_capture.raw.gz`
contains exact candidate REAL64 Q/N bits and `failure_stage` for every one of
those cells (OFF 7/7, COUPLED 6/6). These captures are joined by timestep, RK,
and cell coordinates. Thus the runtime stage and candidate bits are known; the
15-digit ledger decimals are not used to infer them.

The run receipts both bind `/var/tmp/pr94_native_compact3600_20261021/`
`pr87_native_overlay_build.json`, SHA
`9ba94b0b0d4737641bd87d6237ff65e8b207bf8ae52c815521510d7d022f073d`. Its
staged `module_em.F` SHA is
`f88708844994a30540fc458aeede7e0eda4503a04a341caf714050e52f8c18af` and its
Intel profile SHA is
`5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`. A
source-form driver compiled with the pinned Intel O0 and O2 profiles replayed
each captured Q/N bit pattern, captured density, p4 bounds (100/900), and the
source call's optional arguments, and the REAL32 density bits from the
immediately following `PR92_STORE_R32` record. All thirteen exact operand
replays reproduce invalidity and the captured stage under both Intel profiles.
Captured stage 2 rows fail the initial strict continuous mass-ratio gate.
Stage 6 means the candidate passes that gate and reaches the subnormal-Q
handling path, where the routine ultimately rejects it. The exact stage
sequence is in the pinned `joint_moment_store` source.

The actual C4 p4 call enables normal-Q adjustment, joint quantum absence, and
strict mass ratio, passes `inactive_mass_limit=0` and
`allow_inactive_q_quantum_adjustment=.false.`, and uses the exact [100,900]
bounds. Consequently the generic helper's 8-ULP tolerance is not evidence of
source acceptance or rejection and is retained only as a comparison. The
exact runtime captures identify per-cell store rejections. The `FULL` callback
is emitted during the source diagnostic after the grouped candidate was found
infeasible; it does not establish which cell caused the grouped transaction
failure. Nothing in these records indicates a geometry/time mismatch or a
downstream consumer failure. They support a source/storage-path failure
classification while leaving the grouped-cause attribution open.

The focused classifier and evidence are
[`pr97_620_c4_failure_classify.py`](../tools/pr97_620_c4_failure_classify.py)
and [`pr97_620_c4_failure_classification.json`](evidence/pr97_620_c4_failure_classification.json).
The original receipts and compressed logs remain preserved under
`scratch/pr94_physics_20261021/runs_on_lustre/{OFF,COUPLED}_3600s_c4_compact`.

This does not implicate or resolve the separate C1/KDM6 state. Do not extend a
forecast solely from this C4 evidence. For C1, the shortest boundary probe
after the established 600 s point is 640 s (two additional 20 s steps), using
the same frozen image and a planned diagnostic observer if C1 still lacks
grouped-store stage/operand capture. No forecast was launched here.
