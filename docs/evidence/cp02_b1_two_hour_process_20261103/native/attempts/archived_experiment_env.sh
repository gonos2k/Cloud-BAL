#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-first-hour-improvement/tests/intel_toolchain.sh
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh >/dev/null 2>&1
export NETCDF=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel
export LD_LIBRARY_PATH="$NETCDF/lib:${LD_LIBRARY_PATH:-}"
ulimit -s unlimited
exec python3 /var/tmp/firsthour-runtime-plan-20261030/experiment/run.py "$@"
