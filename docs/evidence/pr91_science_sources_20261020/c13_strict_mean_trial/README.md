# C13 strict mean comparison replay

This read-only fixture re-emits the C12 `SOURCE_STAGE` capture's round-trip REAL64 decimal tokens through pinned Intel O0/O2, compares the FogDES product predicate with the maintained `joint_moment_store` strict-mean path, and makes no native run or source change.

Inputs are the one captured C12 source-stage row, `SOURCE_STAGE T3/RK3/pair1` at `(162,132,3)`. Its writer uses `WRITE(a,6i10,1p,20es26.17)`, whose 18 significant digits round-trip the REAL64 values. The fixture uses the captured Q, N, `minmass`, and `maxmass`; density is passed as the captured REAL32 value. Both runs output identical binary64 words:

- `Q64=3E4048B6F24832C2`, `N64=413B9F5F69B64B8F`
- `MMIN64=3CF2DD58BFD7689A`
- `Q/N=3CF2DD58BFD76899` (one binary64 ULP below `MMIN64`)
- Binary64 `mmin*N=3E4048B6F24832C2`, the same word as Q, so the FogDES test `q < mmin*n` passes at rounded equality. The exact rational difference of the captured binary64 operands is `q-mmin*n = -8.1929894441447625e-25`; it rounds to zero in the source product comparison.
- `joint_moment_store` with `strict_mass_ratio=.true.`, no `volume_number_bounds`, `allow_normal_q_adjustment=.true.`, and `allow_joint_quantum_absence=.true.` rejects at failure stage 2, before either storage adjustment can apply.

The source definitions produce the same cloud lower mean mass: `cloud_pidn=REAL(523.59881591796875_real32,real64)`, `cloud_lambda_max=500000.0_real64`, and `cloud_power=3.0_real64`; the host `minmass(1)` uses the promoted REAL32 values of the same constants. Q has kg/kg-dry units, N has number/kg-dry, and Q/N is kg per particle. Density is checked positive by the strict store but does not enter its ratio predicate.

This confirms a predicate mismatch for the exact captured source-stage pair. It does not prove that FogDES later receives identical state operands or that its `stored REAL32 rate + REAL64 correction` reconstruction yields this same Q/N. In C12, that later reconstruction is explicitly `REAL(stored_dq,R64)+output_delta_q`, followed by `qc+dt*reconstructed`; it must be captured/rechecked in the owner's C13 trial. No operator/cause or physics result is inferred here.
