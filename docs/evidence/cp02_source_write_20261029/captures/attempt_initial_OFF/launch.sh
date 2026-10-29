#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-source-write/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-thermo-response-20261029-5llcv4gf/OFF/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-thermo-response-20261029-5llcv4gf/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-thermo-response-20261029-5llcv4gf/OFF/capture_preclamp.gdb
export CP02_BINARY=/var/tmp/cp02-thermo-response-20261029-5llcv4gf/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-thermo-response-20261029-5llcv4gf/OFF/context.json
export CP02_EXPECTED_SCRIPT_SHA256=629f2deea8aec3f0d253dd6561b484357378b4ef06d9e213bfbf4a6382fc91d0
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-thermo-response-20261029-5llcv4gf/OFF/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-thermo-response-20261029-5llcv4gf/OFF/rank_wrapper.sh > /var/tmp/cp02-thermo-response-20261029-5llcv4gf/OFF/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-thermo-response-20261029-5llcv4gf/OFF/launcher.exit
exit "$rc"
