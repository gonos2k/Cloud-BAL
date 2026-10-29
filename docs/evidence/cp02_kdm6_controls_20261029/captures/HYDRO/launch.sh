#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-kdm6-controls/tests/intel_toolchain.sh
export OMP_NUM_THREADS=1
ulimit -s unlimited
export CP02_CAPTURE_DIR=/var/tmp/cp02-kdm6-controls-20261029-1_qjx_p3/HYDRO/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-kdm6-controls-20261029-1_qjx_p3/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-kdm6-controls-20261029-1_qjx_p3/capture_kdm6.gdb
export CP02_BINARY=/var/tmp/cp02-kdm6-controls-20261029-1_qjx_p3/wrf.exe
cd /var/tmp/cp02-kdm6-controls-20261029-1_qjx_p3/HYDRO/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-kdm6-controls-20261029-1_qjx_p3/HYDRO/rank_wrapper.sh > /var/tmp/cp02-kdm6-controls-20261029-1_qjx_p3/HYDRO/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-kdm6-controls-20261029-1_qjx_p3/HYDRO/launcher.exit
exit "$rc"
