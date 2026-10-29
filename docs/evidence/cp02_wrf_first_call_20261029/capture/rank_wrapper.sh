#!/bin/bash
set -eu
rank=${PMI_RANK:?Intel MPI rank required}
exec /usr/bin/gdb --batch -x "$CP02_CAPTURE_SCRIPT" "$CP02_BINARY" > "$CP02_CAPTURE_DIR/gdb_rank${rank}.txt" 2>&1
