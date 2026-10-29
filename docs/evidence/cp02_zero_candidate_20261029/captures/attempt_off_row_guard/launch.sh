#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-zero-candidate/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-zero-candidate-20261029-te57ezkh/OFF/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-zero-candidate-20261029-te57ezkh/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-zero-candidate-20261029-te57ezkh/OFF/capture_preclamp.gdb
export CP02_BINARY=/var/tmp/cp02-zero-candidate-20261029-te57ezkh/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-zero-candidate-20261029-te57ezkh/OFF/context.json
export CP02_EXPECTED_SCRIPT_SHA256=c884c916b2269dd08045602ccf46f78b3df8c8d2b8fb0f8b528d687c4e4181fb
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-zero-candidate-20261029-te57ezkh/OFF/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-zero-candidate-20261029-te57ezkh/OFF/rank_wrapper.sh > /var/tmp/cp02-zero-candidate-20261029-te57ezkh/OFF/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-zero-candidate-20261029-te57ezkh/OFF/launcher.exit
exit "$rc"
