#!/usr/bin/env bash
set -euo pipefail
: "${PMI_RANK:?MPI rank is required}"
: "${GROUPED_OWNER:?target owner is required}"
if [[ $PMI_RANK == "$GROUPED_OWNER" ]]; then
  : "${GROUPED_OUTPUT:?output directory is required}"
  : "${GROUPED_GDB_SCRIPT:?GDB script is required}"
  exec /usr/bin/gdb -nx -q -batch \
    -ex 'set debuginfod enabled off' \
    -ex 'set disable-randomization off' \
    -ex "source $GROUPED_GDB_SCRIPT" -ex run --args ./wrf.exe \
    >"$GROUPED_OUTPUT/gdb_rank${PMI_RANK}.log" 2>&1
fi
exec ./wrf.exe
