#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-wrf-first-call/tests/intel_toolchain.sh
export OMP_NUM_THREADS=1
ulimit -s unlimited
export CP02_CAPTURE_DIR=/var/tmp/cp02-wrf-first-call-20261029-1lo2fl6b/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-wrf-first-call-20261029-1lo2fl6b/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-wrf-first-call-20261029-1lo2fl6b/capture_first_call.gdb
export CP02_BINARY=/var/tmp/cp02-wrf-first-call-20261029-1lo2fl6b/wrf.exe
cd /var/tmp/cp02-wrf-first-call-20261029-1lo2fl6b/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-wrf-first-call-20261029-1lo2fl6b/rank_wrapper.sh > /var/tmp/cp02-wrf-first-call-20261029-1lo2fl6b/launcher.txt 2>&1
rc=$?
set -e
printf '%s\n' "$rc" > /var/tmp/cp02-wrf-first-call-20261029-1lo2fl6b/launcher.exit
exit "$rc"
