#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-thermo-response/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-thermo-response-20261029-1xnf2120/HYDRO/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-thermo-response-20261029-1xnf2120/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-thermo-response-20261029-1xnf2120/HYDRO/capture_thermo_response.gdb
export CP02_BINARY=/var/tmp/cp02-thermo-response-20261029-1xnf2120/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-thermo-response-20261029-1xnf2120/HYDRO/context.json
export CP02_EXPECTED_SCRIPT_SHA256=3293dd49a858a780f396c2167dfa5fdf6b7938c7368f3c9df46b4d2f9a2359a7
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-thermo-response-20261029-1xnf2120/HYDRO/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-thermo-response-20261029-1xnf2120/HYDRO/rank_wrapper.sh > /var/tmp/cp02-thermo-response-20261029-1xnf2120/HYDRO/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-thermo-response-20261029-1xnf2120/HYDRO/launcher.exit
exit "$rc"
