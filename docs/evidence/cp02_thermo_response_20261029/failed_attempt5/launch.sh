#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-thermo-response/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-thermo-response-20261029-r_7ikeaw/HYDRO/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-thermo-response-20261029-r_7ikeaw/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-thermo-response-20261029-r_7ikeaw/HYDRO/capture_thermo_response.gdb
export CP02_BINARY=/var/tmp/cp02-thermo-response-20261029-r_7ikeaw/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-thermo-response-20261029-r_7ikeaw/HYDRO/context.json
export CP02_EXPECTED_SCRIPT_SHA256=33bc19c521f72217d6ce1ac93e5a05478b2db20047b26b813434aa8ca6d59c40
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-thermo-response-20261029-r_7ikeaw/HYDRO/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-thermo-response-20261029-r_7ikeaw/HYDRO/rank_wrapper.sh > /var/tmp/cp02-thermo-response-20261029-r_7ikeaw/HYDRO/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-thermo-response-20261029-r_7ikeaw/HYDRO/launcher.exit
exit "$rc"
