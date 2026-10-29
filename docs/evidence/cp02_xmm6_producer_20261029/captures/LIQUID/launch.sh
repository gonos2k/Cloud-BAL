#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-xmm6/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-thermo-response-20261029-nhq0dvuj/LIQUID/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-thermo-response-20261029-nhq0dvuj/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-thermo-response-20261029-nhq0dvuj/LIQUID/capture_preclamp.gdb
export CP02_BINARY=/var/tmp/cp02-thermo-response-20261029-nhq0dvuj/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-thermo-response-20261029-nhq0dvuj/LIQUID/context.json
export CP02_EXPECTED_SCRIPT_SHA256=72c0c447e74e7f8e87bf490e496a1c3b5317aacaef6047d37c22989ac6a16b59
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-thermo-response-20261029-nhq0dvuj/LIQUID/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-thermo-response-20261029-nhq0dvuj/LIQUID/rank_wrapper.sh > /var/tmp/cp02-thermo-response-20261029-nhq0dvuj/LIQUID/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-thermo-response-20261029-nhq0dvuj/LIQUID/launcher.exit
exit "$rc"
