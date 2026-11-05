#!/usr/bin/env bash
set -euo pipefail
: "${PMI_RANK:?MPI rank is required}"
: "${CP05_OUTPUT:?output directory is required}"
: "${CP05_SCRIPT:?reviewed GDB script is required}"
exec /usr/bin/gdb -nx -q -batch \
  -ex 'set debuginfod enabled off' \
  -ex "source $CP05_SCRIPT" \
  -ex run --args ./wrf.exe >"$CP05_OUTPUT/gdb_rank${PMI_RANK}.log" 2>&1
