#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-thermo-response/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-thermo-response-20261029-tnj1g3a6/OFF/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-thermo-response-20261029-tnj1g3a6/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-thermo-response-20261029-tnj1g3a6/OFF/capture_thermo_response.gdb
export CP02_BINARY=/var/tmp/cp02-thermo-response-20261029-tnj1g3a6/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-thermo-response-20261029-tnj1g3a6/OFF/context.json
export CP02_EXPECTED_SCRIPT_SHA256=e6b9f5395a847fb3c475e9dd9d5b648cce0b224c5bd76562278df3e23f91c38b
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-thermo-response-20261029-tnj1g3a6/OFF/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-thermo-response-20261029-tnj1g3a6/OFF/rank_wrapper.sh > /var/tmp/cp02-thermo-response-20261029-tnj1g3a6/OFF/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-thermo-response-20261029-tnj1g3a6/OFF/launcher.exit
exit "$rc"
