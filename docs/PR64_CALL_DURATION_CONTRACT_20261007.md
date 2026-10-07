# PR64 host to KDM6 call-duration contract

## Source contract

The preserved selected host source is
`/var/tmp/pr63_native_transition_20261006/source/solve_em_pr63.F`. It assigns
`dtm = grid%dt` at line 583 and calls `microphysics_driver` with `DT=dtm` at
line 3794. The PR63 geometry record writes `dtm` and `grid%dt` as separate
fields at lines 3780-3781. This identifies `dtm` as the host argument supplied
to the microphysics driver. The maintained driver source is
`/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/phys/module_microphysics_driver.F`.
Its `CASE (KDM6SCHEME)` branch calls KDM6 with `DELT=dt` at line 2550. Together
these source statements establish the host-to-driver-to-KDM6 argument chain
`solve_em dtm -> microphysics_driver DT/dt -> KDM6 DELT`.

The selected KDM6 source,
`/var/tmp/pr63_native_transition_20261006/build_paired_matched/paired/module_mp_kdm6.F`,
declares the KDM6 duration argument as `delt` and writes that incoming argument
to the first-call trace as `dt_s` (lines 313-317). It passes `delt` into
`kdm62D` at lines 345-350. The runtime trace therefore exposes the actual
duration that reached KDM6.

The checker enforces the source-to-capture identity
`geometry.dtm_s == kdm6.params.dt_s`. Geometry's separate `dt_s` field is
`grid%dt` metadata. The selected source happens to set `dtm = grid%dt`, but the
checker does not treat that incidental equality as the general call contract;
it can accept another host `dt_s` when `dtm_s` still matches KDM6's recorded
`delt`. A mismatch between the host argument and recorded KDM6 argument is
rejected as an unsupported call-duration relation.

## PR63 capture replay

The paired capture at
`/var/tmp/pr63_native_transition_20261006/run_pair_paired` was audited with
the updated checker. Its PRE and POST geometry records both report
`dtm_s=20.0`, `dt_s=20.0`; the KDM6 pre/post trace reports `params.dt_s=20.0`.
The identity holds for the captured first call. The preserved capture has
timestep 1 and RK step 4 in geometry. KDM6's trace header does not carry RK
step, so that association follows the source placement and run capture rather
than an RK field in the KDM6 trace.

## Limits

This identity checks the duration passed by the selected host call against the
duration recorded at KDM6 entry, and the maintained driver source explicitly
shows the forwarding statement. The preserved run receipt does not bind the
compiled `module_microphysics_driver` object to this maintained source hash, so
compiled object lineage remains unverified. The identity does not establish a
mass or energy budget, multi-rank behavior, or scientific acceptance.
Revalidate the forwarding relation when changing the driver source or host call
signature.
