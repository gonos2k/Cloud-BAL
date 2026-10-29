#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-source-write/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-thermo-response-20261029-ekmt7h39/OFF/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-thermo-response-20261029-ekmt7h39/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-thermo-response-20261029-ekmt7h39/OFF/capture_preclamp.gdb
export CP02_BINARY=/var/tmp/cp02-thermo-response-20261029-ekmt7h39/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-thermo-response-20261029-ekmt7h39/OFF/context.json
export CP02_EXPECTED_SCRIPT_SHA256=3c13be72e6a5f09f98eeb09fbf87bfe62502a625075c4d8816d1053d1c29e1e7
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-thermo-response-20261029-ekmt7h39/OFF/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-thermo-response-20261029-ekmt7h39/OFF/rank_wrapper.sh > /var/tmp/cp02-thermo-response-20261029-ekmt7h39/OFF/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-thermo-response-20261029-ekmt7h39/OFF/launcher.exit
exit "$rc"
