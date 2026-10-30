# Fine QSNOW sensitivity runtime

Eight six-hour runs cover CONTROL and IMPROVED at factors 1.1, 1.2, 1.3, and 1.4 (case suffixes 110, 120, 130, 140). CONTROL uses the original WRF executable and original initial input; IMPROVED uses the fixed executable and B1 input. Each case modifies only native initial QSNOW using float64(source) times float64(factor), then casts to float32. The other 207 fields, all variable metadata, dimensions, and global attributes are checked against the family baseline.

`../selection_plan.json` freezes ranking by lead-1-hour CSI at 10 mm, then CSI at 5 mm, FAR at 10 mm, RMSE, distance from factor 1, and case ID. No averages are used. The earlier 22 candidate results and prior selection are already known; the eight new runs extend that same-event diagnostic pool to 30 candidates and do not provide independent validation.

Runtime uses eight disjoint eight-CPU slots, eight MPI ranks per case, one OpenMP thread per rank, and the pinned Intel MPI runtime. Candidate files live in fresh scratch at `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/snow_fine_20261030`. The pinned Cloud-BAL Intel profile is recorded and sourced by `tests/intel_toolchain.sh`; no alternate compiler profile is used.
