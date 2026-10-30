# Native QSNOW sensitivity extension runtime

This prospective extension runs four factors above the previous 1.5 maximum (1.75, 2, 2.5, 3) in both fixed families, for eight six-hour forecasts. CONTROL uses the original WRF executable and original `wrfinput_d01`; IMPROVED uses the fixed executable and producer background-preserved B1 input. The extension reuses the same six-hour namelist and boundary as the prior sensitivity batch. Within each family, only native initial QSNOW values change: float64(source) × float64(alpha), then native float32. The other 207 variables, all 208 variables' metadata, dimensions, and global attributes are checked against the family baseline.

The frozen selection plan is `../selection_plan.json` (SHA-256 `36e094ac84d698351cdc477ec0bb58fd7580e0676e9ed830236a7d52b0818642`). It ranks one case by lead-1-hour CSI at 10 mm, then CSI at 5 mm, FAR at 10 mm, RMSE, distance from alpha=1, and case ID. No averages are used. The previous completed sensitivity evidence remains untouched.

The runtime allocates eight disjoint CPU sets, each with eight CPUs for eight MPI ranks and one OpenMP thread. It loads the repository's pinned Intel profile in `tests/intel_toolchain.sh` and Intel MPI 2021.18. Candidates run only from a fresh Lustre scratch tree at `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/snow_extension_20261030`.

These are diagnostic QSNOW-only perturbations. They deliberately change initial water without compensating other species or energy, and evaluate total surface precipitation rather than snowfall alone. Same-event selection is not independent skill validation or an operational recommendation.
