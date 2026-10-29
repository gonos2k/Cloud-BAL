#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-thermo-response/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-thermo-response-20261029-2c048zkl/HYDRO/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-thermo-response-20261029-2c048zkl/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-thermo-response-20261029-2c048zkl/HYDRO/capture_thermo_response.gdb
export CP02_BINARY=/var/tmp/cp02-thermo-response-20261029-2c048zkl/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-thermo-response-20261029-2c048zkl/HYDRO/context.json
export CP02_EXPECTED_SCRIPT_SHA256=c654e8243fa45f3e035e99134d0b53b9fe3e28bd88062360a0fd7b5b745c7129
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-thermo-response-20261029-2c048zkl/HYDRO/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-thermo-response-20261029-2c048zkl/HYDRO/rank_wrapper.sh > /var/tmp/cp02-thermo-response-20261029-2c048zkl/HYDRO/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-thermo-response-20261029-2c048zkl/HYDRO/launcher.exit
exit "$rc"
