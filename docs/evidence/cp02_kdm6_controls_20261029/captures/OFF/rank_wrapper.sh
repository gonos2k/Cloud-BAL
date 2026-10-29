#!/bin/bash
set -euo pipefail
rank=${PMI_RANK:?}
exec /usr/bin/gdb --batch -x "$CP02_CAPTURE_SCRIPT" "$CP02_BINARY" > "$CP02_CAPTURE_DIR/gdb_rank${rank}.txt" 2>&1
