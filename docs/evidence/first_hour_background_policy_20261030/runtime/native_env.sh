#!/bin/bash
set -euo pipefail
source /var/tmp/firsthour-runtime-plan-20261030/producer_pair/export/tests/intel_toolchain.sh
ws=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
export LD_LIBRARY_PATH="$ws/Cloud-BAL/scratch/metgrid_netcdf_runtime.YPWjEW/install/lib:${LD_LIBRARY_PATH:-}" OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
ulimit -s unlimited
exec python3 /var/tmp/firsthour-runtime-plan-20261030/producer_pair/run_native.py "$@"
