#!/usr/bin/env bash
set -euo pipefail
exec /usr/bin/gdb -nx -q -batch -ex 'set debuginfod enabled off' -ex "source $ICE_SCRIPT" -ex run --args ./wrf.exe >"$ICE_OUT/gdb_rank${PMI_RANK}.log" 2>&1
