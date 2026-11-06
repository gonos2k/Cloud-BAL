#!/usr/bin/env bash
set -euo pipefail
cloud_bal_root=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_protected_process_20261106/Cloud-BAL
source "$cloud_bal_root/tests/intel_toolchain.sh"
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh
export NETCDF=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel
export LD_LIBRARY_PATH="$NETCDF/lib:${LD_LIBRARY_PATH:-}"
ulimit -s unlimited
exec python3 -B "$cloud_bal_root/docs/evidence/cp02_protected_process_20261106/native/runs/run_native.py" \
  --plan "$cloud_bal_root/docs/evidence/cp02_protected_process_20261106/native/plans/quick_gate_plan.json" \
  --review "$cloud_bal_root/docs/evidence/cp02_protected_process_20261106/review/quick_prelaunch_review.json" \
  "$@"
