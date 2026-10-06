# PR62 pre-call cloud moment gap

## Finding

At Fortran global cell `(i,j,k)=(172,76,1)`, the retained runtime input has
`QCLOUD=0` and `QNCLOUD=0`, while the timestep-1 KDM6 first-call pre-capture has
`QC=5.03652699990198e-7` and `NC=0`. The QC/NC gap therefore exists by the
first KDM6 call, but these captures do not locate which intervening startup,
transport, or physics step generated QC. No causal step is assigned here.

The raw parser stores active 3-D fields as `[j,k,i]`; the cell maps to zero-based
parser index `[74,0,170]` using `jts=2`, `kts=1`, and `its=2`. This is not an
array index in `(i,j,k)` order.

## Artifact identity and observations

The actual runtime directory is
`/var/tmp/kdm6_pr61_process_trace_20261006/native_run_combined_pure_strict/`.
Its retained `wrfinput_d01` has SHA-256
`aecc4885da1d612e57ec8c603b6c85df6a89e3c53cda5a4a302ec65d33866739`.
That file reports `QCLOUD` units `kg kg-1` and `QNCLOUD` units `  kg(-1)`.
At the target and four horizontal face-neighbors, runtime-input QCLOUD and
QNCLOUD are all zero. The level-above cell `(172,76,2)` has input QCLOUD
`2.4288598069688305e-5` and QNCLOUD `21559104`; the lower vertical face is
outside the domain.

The first-call pre raw capture is
`kdm6_first_call_pre.raw`, SHA-256
`d2331e90aee601dd9a1aa2549230fa7f388231ce224e53fdf60cb4b4b9b7e2bb`.
It is stage 1, timestep 1, with active dimensions `(232,280,39)` in `(x,y,z)`.
At the target, pre-call QC is `5.03652699990198e-7`, NC is zero, QR is
`1.2699329818133265e-4`, and NR is `1971.324462890625`. Face-neighbor QC/NC
values are recorded in `docs/evidence/pr62_precall_cloud_gap.json`; the nearby
cells show both zero and positive NC at positive QC. The retained post-capture
has SHA-256 `526285dedd8e27eb3f59529671193c723d6519d99ea4f98d13b89dae39eb7f30`.

`geometry.json` records a different file as its host input:
`Cloud-BAL/scratch/cp02_actual12_liquid_wps.HisIOM/real_HYDRO/wrfinput_d01`,
SHA-256 `7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126`.
That geometry-referenced file has QCLOUD `1.8210486132375081e-6` and
QNCLOUD `0` at the target, and positive QCLOUD/zero QNCLOUD at every in-domain
face-neighbor. It is not the retained runtime `wrfinput_d01`: hydrometeor arrays
differ across many cells. The geometry record itself says
`host_binary_equivalence: UNVERIFIED`. The two files are reported separately;
the geometry reference is not used as the runtime initial state in this finding.

## Configuration and limits

The retained `namelist.input` (SHA-256
`0bc3b9c1e8f4bb1898de6627dbf4c464d4f43a2bc451c88a0c7d306fc3f660b8`) sets
`mp_physics=37`, `mp_zero_out=2`, `moist_adv_opt=1`, and `scalar_adv_opt=1`.
It does not explicitly set `mp_zero_out_thresh`; `README.namelist` documents
`1.e-8` as the default. `QC` at first-call pre is above that documented
threshold. The retained run artifacts do not bind the executable to a source
revision or Registry file, so the effective startup fill/threshold execution
and Registry declarations are not source-attributed here. The raw trace only
brackets KDM6 itself; it does not capture QC/NC at each earlier stage. Existing
CCN stage traces cover CCN state and are not evidence of QC history.

This finding is limited to one retained runtime input and one timestep-1
first-call capture. It does not identify the producer step or establish
scientific validity.
