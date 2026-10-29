#!/bin/bash
set -euo pipefail
source /var/tmp/cloudbal-cp02-source-write/tests/intel_toolchain.sh
ulimit -s unlimited
export OMP_NUM_THREADS=1
export CP02_CAPTURE_DIR=/var/tmp/cp02-thermo-response-20261029-957duac2/HYDRO/capture
export CP02_SELECTION_JSON=/var/tmp/cp02-thermo-response-20261029-957duac2/selection.json
export CP02_CAPTURE_SCRIPT=/var/tmp/cp02-thermo-response-20261029-957duac2/HYDRO/capture_preclamp.gdb
export CP02_BINARY=/var/tmp/cp02-thermo-response-20261029-957duac2/wrf.exe
export CP02_STAGE_CONTEXT_JSON=/var/tmp/cp02-thermo-response-20261029-957duac2/HYDRO/context.json
export CP02_EXPECTED_SCRIPT_SHA256=cc732171bf108da5a4f2788787dde3b30f07edeb2b6c7199582378e4583c7f34
export CP02_PEER_WAIT_SECONDS=500
cd /var/tmp/cp02-thermo-response-20261029-957duac2/HYDRO/run
set +e
timeout --kill-after=10 600 mpirun -np 8 /var/tmp/cp02-thermo-response-20261029-957duac2/HYDRO/rank_wrapper.sh > /var/tmp/cp02-thermo-response-20261029-957duac2/HYDRO/launcher.txt 2>&1
rc=$?
printf '%s\n' "$rc" > /var/tmp/cp02-thermo-response-20261029-957duac2/HYDRO/launcher.exit
exit "$rc"
