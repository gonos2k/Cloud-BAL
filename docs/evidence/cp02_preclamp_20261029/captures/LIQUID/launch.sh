#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-preclamp/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-thermo-response-20261029-hvp_teul/LIQUID/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-thermo-response-20261029-hvp_teul/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-thermo-response-20261029-hvp_teul/LIQUID/capture_preclamp.gdb
export CP02_BINARY=/var/tmp/cp02-thermo-response-20261029-hvp_teul/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-thermo-response-20261029-hvp_teul/LIQUID/context.json
export CP02_EXPECTED_SCRIPT_SHA256=68458787f9e868dafb7318fec358f00be15fc75147a79e9852f0b413d332f37e
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-thermo-response-20261029-hvp_teul/LIQUID/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-thermo-response-20261029-hvp_teul/LIQUID/rank_wrapper.sh > /var/tmp/cp02-thermo-response-20261029-hvp_teul/LIQUID/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-thermo-response-20261029-hvp_teul/LIQUID/launcher.exit
exit "$rc"
