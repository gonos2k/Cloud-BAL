#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-zero-candidate/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-zero-candidate-20261029-xampu3o6/LIQUID/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-zero-candidate-20261029-xampu3o6/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-zero-candidate-20261029-xampu3o6/LIQUID/capture_preclamp.gdb
export CP02_BINARY=/var/tmp/cp02-zero-candidate-20261029-xampu3o6/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-zero-candidate-20261029-xampu3o6/LIQUID/context.json
export CP02_EXPECTED_SCRIPT_SHA256=c67847358611e171849f366468ff2875dee4d545dfd4f54a778a1d2f753e6661
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-zero-candidate-20261029-xampu3o6/LIQUID/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-zero-candidate-20261029-xampu3o6/LIQUID/rank_wrapper.sh > /var/tmp/cp02-zero-candidate-20261029-xampu3o6/LIQUID/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-zero-candidate-20261029-xampu3o6/LIQUID/launcher.exit
exit "$rc"
