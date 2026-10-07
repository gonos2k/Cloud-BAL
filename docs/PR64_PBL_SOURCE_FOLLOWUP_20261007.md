# PR64 Shinhong source follow-up

## Evidence boundary

The guarded native observer measured the target QC tendency as exactly equal
to `rqcblten`. Its runtime identities are preserved in
[the QC channel ledger](evidence/PR64_QC_CHANNEL_SOURCE_20261007.json).
This additional investigation reads the current maintained source; it makes
no new model run or change to that source.

Under `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2`:

| Source | SHA256 | Inspected relationship |
| --- | --- | --- |
| `frame/module_state_description.F` | `1999492fe9985d148229a39ea7ed66d6d9c9821f4437a17292c28b3d2a8e755b` | Line 144 defines `SHINHONGSCHEME=11`. |
| `phys/module_pbl_driver.F` | `90336e30296991fb397ffde87649a4bd20eaa2b7dc6e90639b043810c8420b56` | Lines 1294–1310 pass QC and RQCBLTEN to the Shinhong routine. |
| `phys/module_bl_shinhong.F` | `99f44dbeb5e586b96be14424b8ab27c9986ffbd81f007f41fb8528d8ea466d56` | The interface at lines 9–11 has water-vapor/cloud-water/ice inputs and tendencies, without an NC argument. |
| `phys/module_physics_addtendc.F` | `ecfe34c06bb3e91a5398a616a69a69a5aa155e73dc082ef0745421df46331894` | Lines 312–341 accumulate RQCBLTEN into the QC tendency. |

The Shinhong source packs vapor, cloud water and ice into three channels.
It enables their vertical mixing, solves the vertical tridiagonal system
and accumulates `(mixed_value - input_value) / time_interval` into each
tendency (approximately lines 1215–1370). Channel 2 returns as RQCBLTEN.
No saturation or particle activation source appears in this inspected path;
there is no corresponding cloud-number tendency argument in its interface.

These source relationships support a vertical-mixing interpretation of the
observed PBL QC contribution. The audited files have **not** been proven to
match the archived PBL/physics objects in the observer executable. Runtime
channel equality and current-source interpretation remain separate evidence.
The actual internal PBL fluxes and individual NC donor faces are unobserved.

## Next numerical investigation

1. Bind the PBL object's generated source, compiler profile and archive member
   to the native observer before attributing its internal operator.
2. Capture the completed PBL QC transport and the NC transport at the same
   state boundary, with their donor states, carrier and boundary terms. A QC
   update followed later by NC is not itself a completed coupled state.
3. If this source path is confirmed, implement cloud mass and number transport
   using the same air-mixing operator and independently declared boundary
   conditions. Check extensive conservation and the applicable joint moment
   inequalities at the completed update. Do not construct an NC source from
   the observed QC residual or add a number floor.
4. Keep differential sedimentation and physical particle creation/destruction
   in their separate process equations. Repeat the same native comparison
   only after the transport change preserves the required invariants.

This is a source-supported investigation plan. The selected-cell QC/NC
failure, incoming negative QC, same-call process/energy closure and full
physical initialization approval remain **FAIL/OPEN**.
