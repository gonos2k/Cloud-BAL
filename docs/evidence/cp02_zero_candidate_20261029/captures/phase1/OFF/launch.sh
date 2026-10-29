#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-zero-candidate/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-zero-candidate-20261029-8407dkh6/OFF/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-zero-candidate-20261029-8407dkh6/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-zero-candidate-20261029-8407dkh6/OFF/capture_preclamp.gdb
export CP02_BINARY=/var/tmp/cp02-zero-candidate-20261029-8407dkh6/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-zero-candidate-20261029-8407dkh6/OFF/context.json
export CP02_EXPECTED_SCRIPT_SHA256=62f8ce27d95489f7d3f8c1c3521153f87fa23751ad66408746bbc099396dde1f
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-zero-candidate-20261029-8407dkh6/OFF/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-zero-candidate-20261029-8407dkh6/OFF/rank_wrapper.sh > /var/tmp/cp02-zero-candidate-20261029-8407dkh6/OFF/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-zero-candidate-20261029-8407dkh6/OFF/launcher.exit
exit "$rc"
