#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-thermo-response/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-thermo-response-20261029-pxeyf30y/HYDRO/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-thermo-response-20261029-pxeyf30y/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-thermo-response-20261029-pxeyf30y/HYDRO/capture_thermo_response.gdb
export CP02_BINARY=/var/tmp/cp02-thermo-response-20261029-pxeyf30y/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-thermo-response-20261029-pxeyf30y/HYDRO/context.json
export CP02_EXPECTED_SCRIPT_SHA256=3ab8968fb49a436a0d79eefa523e9ddc2a7ba36f92af0fea72ab51c18ddfaff1
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-thermo-response-20261029-pxeyf30y/HYDRO/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-thermo-response-20261029-pxeyf30y/HYDRO/rank_wrapper.sh > /var/tmp/cp02-thermo-response-20261029-pxeyf30y/HYDRO/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-thermo-response-20261029-pxeyf30y/HYDRO/launcher.exit
exit "$rc"
